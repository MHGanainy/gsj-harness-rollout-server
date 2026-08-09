"""Session-level abort detection (carried patch P2, fork dev_09).

A completion with ``finish_reason == "abort"`` (weight-update cutoff) anywhere
in a session marks the whole trajectory ERROR. The merged Trace keeps only the
last kept completion's ``finish_reason`` (see ``_finalize_chain``), so a
mid-chain abort is otherwise invisible on the wire — the session-level scan in
``build()`` is the only reliable detection point.
"""

from __future__ import annotations

import asyncio

from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder
from polar.trajectory.models import CompletionRecord, CompletionSession


def _record(
    completion_id: str,
    prompt_ids: list[int],
    response_ids: list[int],
    *,
    finish_reason: str = "stop",
) -> CompletionRecord:
    return CompletionRecord(
        completion_id=completion_id,
        timestamp=f"2026-01-01T00:00:{int(completion_id[-1]):02d}+00:00",
        # `system` marks agent-side traffic so record_filters keeps the record.
        request={"system": "harness", "messages": [{"role": "user", "content": completion_id}]},
        response={
            "choices": [
                {
                    "input_token_ids": prompt_ids,
                    "message": {"role": "assistant", "content": completion_id},
                    "finish_reason": finish_reason,
                    "logprobs": {
                        "content": [
                            {"token_id": token_id, "logprob": -0.1}
                            for token_id in response_ids
                        ]
                    },
                }
            ]
        },
    )


def test_mid_chain_abort_marks_session_error() -> None:
    # c1 aborts mid-chain; c2 resumes on new weights and stops naturally. The
    # merged trace carries c2's clean finish_reason — only the session-level
    # scan can see the abort.
    c1 = _record("c-1", [1, 2], [3], finish_reason="abort")
    c2 = _record("c-2", [1, 2, 3, 9], [4], finish_reason="stop")
    session = CompletionSession(session_id="s1", completions=[c1, c2])

    trajectory = asyncio.run(
        PrefixMergingBuilder(end_of_turn_token_id=9).build(session)
    )

    assert trajectory.status == "ERROR"
    assert trajectory.error == "aborted generation (weight-update cutoff)"


def test_tail_abort_marks_session_error() -> None:
    c1 = _record("c-1", [1, 2], [3], finish_reason="abort")
    session = CompletionSession(session_id="s1", completions=[c1])

    trajectory = asyncio.run(
        PrefixMergingBuilder(end_of_turn_token_id=9).build(session)
    )

    assert trajectory.status == "ERROR"
    assert trajectory.error == "aborted generation (weight-update cutoff)"


def test_clean_session_stays_completed() -> None:
    c1 = _record("c-1", [1, 2], [3], finish_reason="stop")
    session = CompletionSession(session_id="s1", completions=[c1])

    trajectory = asyncio.run(
        PrefixMergingBuilder(end_of_turn_token_id=9).build(session)
    )

    assert trajectory.status == "COMPLETED"
    assert trajectory.error is None
