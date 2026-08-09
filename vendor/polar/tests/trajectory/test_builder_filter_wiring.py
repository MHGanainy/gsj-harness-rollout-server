"""Builder-level wiring for the completion filter (carried patch P1).

The fork validated the wiring inside its own ``test_per_request_builder.py``
and ``test_prefix_merging_builder.py``; neither fork-base file matches the pin
(the second does not exist here at all), so the portable assertions are
re-hosted in this file. The prefix-merging assertions drop the fork-base-only
stats keys (``completions_preserved`` / ``completions_dropped``) the pin does
not emit.
"""

from __future__ import annotations

import asyncio

from polar.trajectory.builder.per_request import PerRequestBuilder
from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder
from polar.trajectory.models import CompletionRecord, CompletionSession


def _normal_record(
    completion_id: str,
    prompt_ids: list[int],
    response_ids: list[int],
) -> CompletionRecord:
    return CompletionRecord(
        completion_id=completion_id,
        timestamp=f"2026-01-01T00:00:{len(completion_id):02d}+00:00",
        # `system` marks agent-side traffic so record_filters keeps the record.
        request={"system": "harness", "messages": [{"role": "user", "content": completion_id}]},
        response={
            "choices": [
                {
                    "input_token_ids": prompt_ids,
                    "message": {"role": "assistant", "content": completion_id},
                    "finish_reason": "stop",
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


def _side_read_record(completion_id: str) -> CompletionRecord:
    # A bare request the harness emitted outside the agent loop, carrying the body of
    # a file the agent just Read. Dropped on shape (lone user message, no system /
    # tools / SDK fields), so any payload is covered — not just one known document.
    request = {
        "messages": [
            {
                "role": "user",
                "content": "# Copyright (c) 2025 Huawei\nfunction(ascendc_compile_kernel)\nendfunction()\n",
            }
        ],
    }
    return CompletionRecord(
        completion_id=completion_id,
        timestamp=f"2026-01-01T00:00:{len(completion_id):02d}+00:00",
        original_request=request,
        request=request,
        response={
            "choices": [
                {
                    "input_token_ids": [1],
                    "message": {"role": "assistant", "content": "doc review"},
                    "finish_reason": "stop",
                    "logprobs": {"content": [{"token_id": 10, "logprob": -0.1}]},
                }
            ]
        },
    )


def _truncated_record(completion_id: str) -> CompletionRecord:
    return CompletionRecord(
        completion_id=completion_id,
        timestamp=f"2026-01-01T00:00:{len(completion_id):02d}+00:00",
        request={"messages": [{"role": "user", "content": completion_id}]},
        response={"id": "r1", "__truncated": True},
    )


def _empty_record(completion_id: str) -> CompletionRecord:
    return CompletionRecord(
        completion_id=completion_id,
        timestamp=f"2026-01-01T00:00:{len(completion_id):02d}+00:00",
        request={"messages": [{"role": "user", "content": completion_id}]},
        response={"id": "r1", "choices": []},
    )


def test_per_request_builder_filters_non_trainable_completions() -> None:
    session = CompletionSession(
        session_id="session-1",
        completions=[
            _normal_record("keep-1", [1], [10]),
            _side_read_record("side-1"),
            _truncated_record("truncated-1"),
            _empty_record("empty-1"),
        ],
    )

    trajectory = asyncio.run(PerRequestBuilder().build(session))

    assert trajectory.status == "COMPLETED"
    assert len(trajectory.traces) == 1
    assert "source_completion_ids" not in trajectory.traces[0].metadata
    assert trajectory.metadata["record_count"] == 4
    assert trajectory.metadata["trace_count"] == 1
    completion_filter = trajectory.metadata["completion_filter"]
    assert completion_filter["input_completions"] == 4
    assert completion_filter["kept_completions"] == 1
    assert completion_filter["excluded_completions"] == 3
    assert completion_filter["excluded_reasons"] == {
        "empty_completion": 1,
        "non_agent_side_completion": 1,
        "persisted_truncated_completion": 1,
    }
    assert set(completion_filter["excluded_completion_ids"]) == {
        "side-1",
        "truncated-1",
        "empty-1",
    }
    assert {
        (item["completion_id"], item["reason"])
        for item in completion_filter["excluded"]
    } == {
        ("side-1", "non_agent_side_completion"),
        ("truncated-1", "persisted_truncated_completion"),
        ("empty-1", "empty_completion"),
    }


def test_per_request_builder_returns_error_when_filter_removes_everything() -> None:
    session = CompletionSession(
        session_id="session-1",
        completions=[
            _side_read_record("side-1"),
            _empty_record("empty-1"),
        ],
    )

    trajectory = asyncio.run(PerRequestBuilder().build(session))

    assert trajectory.status == "ERROR"
    assert trajectory.error == "no trainable completions after completion filter"
    assert trajectory.traces == []
    assert set(trajectory.metadata["completion_filter"]["excluded_completion_ids"]) == {
        "side-1",
        "empty-1",
    }


def test_prefix_merging_filters_before_grouping_and_reports_raw_counts() -> None:
    session = CompletionSession(
        session_id="session-1",
        completions=[
            _normal_record("keep-1", [1], [10]),
            _side_read_record("side-1"),
            _truncated_record("truncated-1"),
            _empty_record("empty-1"),
        ],
    )

    trajectory = asyncio.run(
        PrefixMergingBuilder(end_of_turn_token_id=99).build(session)
    )

    assert trajectory.status == "COMPLETED"
    assert len(trajectory.traces) == 1
    stats = trajectory.metadata["reconstruction_stats"]
    assert stats["raw_completions_total"] == 4
    assert stats["completions_total"] == 1
    assert stats["chains_total"] == 1
    completion_filter = trajectory.metadata["completion_filter"]
    assert completion_filter["excluded_completions"] == 3
    assert set(completion_filter["excluded_completion_ids"]) == {
        "side-1",
        "truncated-1",
        "empty-1",
    }


def test_prefix_merging_returns_error_when_filter_removes_everything() -> None:
    session = CompletionSession(
        session_id="session-1",
        completions=[
            _side_read_record("side-1"),
            _empty_record("empty-1"),
        ],
    )

    trajectory = asyncio.run(PrefixMergingBuilder().build(session))

    assert trajectory.status == "ERROR"
    assert trajectory.error == "no trainable completions after completion filter"
    assert trajectory.traces == []
