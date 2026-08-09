#!/usr/bin/env python3
"""CP-06 sanity-gate probe — a scripted two-turn OpenAI client.

Runs INSIDE the Polar sandbox (shell harness), talks to the gateway proxy
via the injected OPENAI_BASE_URL / OPENAI_API_KEY, and plays a minimal
agent: request -> tool call -> tool result -> request -> final answer.
The assistant message is echoed back verbatim, so the stub's prefix-stable
rendering makes the two completions one chain. The gate: the resulting
trajectory must report reconstruction_stats.chains_total == 1.

stdlib only (urllib) — the sandbox image is bare python:3.11-slim.
"""

import json
import os
import urllib.request

BASE = os.environ["OPENAI_BASE_URL"].rstrip("/")
KEY = os.environ.get("OPENAI_API_KEY", "")

TOOLS = [
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


def call(messages):
    body = json.dumps(
        {"model": "stub-model", "messages": messages, "tools": TOOLS}
    ).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main():
    messages = [
        {"role": "system", "content": "You are the CP-06 sanity-gate probe."},
        {"role": "user", "content": "Write hello.txt via the bash tool."},
    ]
    first = call(messages)
    first_msg = first["choices"][0]["message"]
    messages.append(first_msg)  # verbatim echo
    for tc in first_msg.get("tool_calls") or []:
        messages.append(
            {"role": "tool", "tool_call_id": tc["id"], "content": "ok"}
        )
    second = call(messages)
    print(
        json.dumps(
            {
                "turn1_finish": first["choices"][0]["finish_reason"],
                "turn2_finish": second["choices"][0]["finish_reason"],
                "turn2_content": second["choices"][0]["message"].get("content"),
            }
        )
    )


if __name__ == "__main__":
    main()
