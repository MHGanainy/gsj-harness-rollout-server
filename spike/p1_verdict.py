#!/usr/bin/env python3
"""CP-06 Step 3 — run P1's shape test against pi 0.83.0's captured wire
bodies (spike/captures/pi_local_stub.jsonl) and against synthetic
pi-dialect auxiliary calls. Answers A-12: does the drop arm ever fire on
pi traffic?

Run: PYTHONPATH=spike vendor/polar/.venv/bin/python spike/p1_verdict.py
"""

import json
import sys
from pathlib import Path

from polar.trajectory.builder.record_filters import (
    exclude_completion_reason,
)
from polar.trajectory.models import CompletionRecord


def record_for(request: dict, response: dict | None = None) -> CompletionRecord:
    return CompletionRecord(
        completion_id="msg_p1verdict",
        timestamp="2026-08-09T00:00:00Z",
        request=dict(request),
        original_request=dict(request),
        response=response
        or {"choices": [{"index": 0, "message": {"role": "assistant", "content": "x"}, "finish_reason": "stop"}]},
        metadata={},
    )


def main() -> None:
    capture = Path("spike/captures/pi_local_stub.jsonl")
    entries = [json.loads(line) for line in capture.open()]

    print("== captured pi agent-loop requests ==")
    for e in entries:
        req = e["request"]
        reason = exclude_completion_reason(record_for(req, e["response"]))
        defeats = {
            "len(messages)!=1": len(req.get("messages", [])) != 1,
            "system message present": any(
                isinstance(m, dict) and m.get("role") == "system"
                for m in req.get("messages", [])
            ),
            "tools non-empty": bool(req.get("tools")),
            "SDK key present (stream/...)": any(
                k in req for k in ("context_management", "thinking", "output_config", "stream")
            ),
        }
        print(
            f"seq {e['seq']}: exclude_reason={reason!r}  "
            f"drop-shape defeated by: {[k for k, v in defeats.items() if v]}"
        )

    print()
    print("== synthetic pi-dialect auxiliary calls (the A-12 leak shape) ==")
    # pi-ai's openai-completions client streams unconditionally (measured:
    # every captured request carries stream=true). A hypothetical auxiliary
    # completion through the same client — one bare user message, no system,
    # no tools — would still carry the client's transport keys:
    aux_pi_dialect = {
        "model": "stub-model",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "<file body>"}]}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "store": False,
        "max_completion_tokens": 8192,
    }
    reason = exclude_completion_reason(record_for(aux_pi_dialect))
    print(f"aux via pi-ai client (carries stream): exclude_reason={reason!r}  -> "
          f"{'DROPPED' if reason else 'KEPT (false negative)'}")

    # The only shape P1 would drop — a bare completion with no transport keys.
    # No path in pi 0.83.0 emits this through the gateway (pi-ai always
    # streams), so on pi traffic this arm is unreachable:
    aux_bare = {
        "model": "stub-model",
        "messages": [{"role": "user", "content": "<file body>"}],
    }
    reason = exclude_completion_reason(record_for(aux_bare))
    print(f"bare single-user-message call (no stream key): exclude_reason={reason!r}  -> "
          f"{'DROPPED' if reason else 'KEPT'}")

    print()
    print(
        "P1 VERDICT: inert against pi 0.83.0 — every request pi's client emits "
        "carries `stream` (plus system+tools+multi-message on agent turns), so "
        "the non_agent_side drop arm can never fire on pi traffic."
    )


if __name__ == "__main__":
    sys.exit(main())
