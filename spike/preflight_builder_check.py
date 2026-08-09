#!/usr/bin/env python3
"""CP-06 pre-flight: feed a simulated two-turn stub exchange straight into
the vendored PrefixMergingBuilder (no servers) and assert chains_total == 1.

This is NOT the sanity gate (which runs through the full proxy topology) —
it is a fast dialect check so a stub bug is caught here, not after a full
episode. Run with the polar venv python, spike/ on sys.path:

    PYTHONPATH=spike vendor/polar/.venv/bin/python spike/preflight_builder_check.py
"""

import asyncio
import json

from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder
from polar.trajectory.models import CompletionRecord, CompletionSession

import stub_backend


def main() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }
    ]
    messages = [
        {"role": "system", "content": "You are the CP-06 sanity-gate probe."},
        {"role": "user", "content": "Write hello.txt via the bash tool."},
    ]
    records = []
    for turn in range(2):
        request = {"model": "stub-model", "messages": list(messages), "tools": tools}
        response = stub_backend.build_response(request, seq=turn + 1, tool_turns=1)
        records.append(
            CompletionRecord(
                completion_id=f"msg_{turn:012d}",
                timestamp=f"2026-08-09T00:00:0{turn}Z",
                request=request,
                original_request=dict(request, stream=False),
                response=response,
                metadata={"session_id": "preflight", "task_id": "preflight"},
            )
        )
        msg = response["choices"][0]["message"]
        messages.append(msg)
        for tc in msg.get("tool_calls") or []:
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": "ok"})

    session = CompletionSession(
        session_id="preflight",
        created_at="2026-08-09T00:00:00Z",
        task_id="preflight",
        model_requested="stub-model",
        model_used="stub-model",
        api_type="openai_chat",
        metadata={},
        completions=records,
    )
    builder = PrefixMergingBuilder(end_of_turn_token_id=stub_backend.EOT_ID)
    trajectory = asyncio.run(builder.build(session))
    stats = trajectory.metadata["reconstruction_stats"]
    print(json.dumps(stats, indent=2))
    trace = trajectory.traces[0]
    print(
        json.dumps(
            {
                "status": trajectory.status,
                "trace_count": len(trajectory.traces),
                "prompt_ids_len": len(trace.prompt_ids),
                "response_ids_len": len(trace.response_ids),
                "loss_mask_ones": sum(trace.loss_mask),
                "loss_mask_zeros": len(trace.loss_mask) - sum(trace.loss_mask),
                "logprobs_present": trace.response_logprobs is not None,
                "finish_reason": trace.finish_reason,
            }
        )
    )
    assert stats["chains_total"] == 1, f"chains_total={stats['chains_total']} (want 1)"
    assert stats["chains_reconstructed_truncated"] == 0
    assert stats["completions_merged"] == stats["completions_total"] == 2
    assert trace.response_logprobs is not None and all(
        lp <= 0 for lp in trace.response_logprobs
    )
    print("PREFLIGHT OK: two-turn stub session merges into one chain")


if __name__ == "__main__":
    main()
