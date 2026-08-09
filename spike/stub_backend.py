#!/usr/bin/env python3
"""CP-06 stub backend — a minimal OpenAI-compatible /v1/chat/completions server.

Its ONLY job is to speak a dialect Polar's capture actually works against
(CP-03 proved mlx-lm's does not: `{"id","logprob"}` entries, no `token_ids`
=> empty `prompt_ids` => S1 chain degeneration). Requirements derived from
`vendor/polar/src/polar/trajectory/builder/record_utils.py:82-140`:

- `prompt_token_ids` on the response top level (accepted at record_utils
  :136-140 third slot) so `prompt_ids` is non-empty;
- response ids as `choices[0].token_ids` (record_utils :87-88) AND a
  `logprobs.content` list whose entries carry `token_id` + `logprob`
  (:23-47) with ids exactly equal to `token_ids`, so logprobs attach
  (:94-101 "without mixing unaligned sources");
- logprobs finite and < 0, one per response token, never 0.0;
- a tool call on early turns, a final answer on the last, so a session is
  a multi-completion chain;
- deterministic (fixed ids, `created: 0`, seq counter) and stdlib-only.

The "tokenizer" is byte-level with special tokens, chosen so that the
rendered conversation is PREFIX-STABLE: appending messages never rewrites
earlier tokens, which is exactly the property `prefix_merging`'s grouping
test (`prompt_ids[:n] == tip`, prefix_merging.py:399) needs.

    ids 0-255      = the UTF-8 byte values of message bodies
    256 <|system|> 257 <|user|> 258 <|assistant|> 259 <|tool|>
    260 <|eot|>    = the end-of-turn token

A prompt renders as  [role_id] body_bytes [EOT] ... [258]  (the trailing
258 is the generation prompt). An assistant reply samples
`body_bytes + [EOT]`, so the echoed assistant message in the next request
extends the previous prompt exactly — `p_{m+1}[:len(p_m)] == p_m` holds on
token ids, and the canonical tail contains the sampled body followed by
EOT, the tool messages, and the next generation prompt.

**A-15 derivation**: `end_of_turn_token_id` for the builder config is
`EOT_ID == 260`, read from the SPECIALS table below — the stub's vocab IS
the tokenizer, so the value is derived by looking the token up in this
file, not by auto-detection.

Every request is appended verbatim (with its response) to the capture
file — because the gateway's true outbound wire body is never persisted
(CP-03 finding 4; `gateway/proxy.py:118-136` builds and posts it without
storing it), the stub's dump is the ONLY observation point for what the
engine actually received.

Usage:
    python3 stub_backend.py --port 8021 --capture captures/foo.jsonl \
        [--tool-turns 1]
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SPECIALS = {
    "<|system|>": 256,
    "<|user|>": 257,
    "<|assistant|>": 258,
    "<|tool|>": 259,
    "<|eot|>": 260,
}
EOT_ID = SPECIALS["<|eot|>"]
ROLE_IDS = {
    "system": SPECIALS["<|system|>"],
    "user": SPECIALS["<|user|>"],
    "assistant": SPECIALS["<|assistant|>"],
    "tool": SPECIALS["<|tool|>"],
}
_ID_TO_TOKEN = {v: k for k, v in SPECIALS.items()}


def _content_text(content) -> str:
    """Flatten OpenAI content (string or content-part list) to text.

    pi 0.83.0 sends user/tool content as content-part lists (predecessor
    A-20), so the flattening must be part of the render.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )
    if content is None:
        return ""
    return str(content)


def _canon_tool_calls(tool_calls) -> str:
    """Render tool calls canonically (sorted-key args) so a client that
    re-serializes `arguments` on echo still renders the same bytes."""
    out = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        args = fn.get("arguments", "")
        try:
            args = json.dumps(json.loads(args), sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            args = str(args)
        out.append(f"<call:{tc.get('id', '')}:{fn.get('name', '')}:{args}>")
    return "".join(out)


def message_body(msg: dict) -> str:
    role = msg.get("role", "user")
    body = _content_text(msg.get("content"))
    if role == "assistant" and msg.get("tool_calls"):
        body += _canon_tool_calls(msg["tool_calls"])
    if role == "tool":
        body = f"[{msg.get('tool_call_id', '')}]" + body
    return body


def message_tokens(msg: dict) -> list[int]:
    rid = ROLE_IDS.get(msg.get("role", "user"), ROLE_IDS["user"])
    return [rid] + list(message_body(msg).encode("utf-8")) + [EOT_ID]


def prompt_tokens(messages: list) -> list[int]:
    toks: list[int] = []
    for m in messages:
        if isinstance(m, dict):
            toks += message_tokens(m)
    return toks + [ROLE_IDS["assistant"]]  # generation prompt


def token_str(token_id: int) -> str:
    if token_id in _ID_TO_TOKEN:
        return _ID_TO_TOKEN[token_id]
    return bytes([token_id]).decode("utf-8", errors="replace") if token_id < 256 else "?"


def _find_tool(tools, name: str) -> str | None:
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else {}
        tool_name = fn.get("name") or t.get("name")
        if tool_name == name:
            return tool_name
    return None


def decide(messages: list, tools, tool_turns: int) -> tuple[dict, str]:
    """Deterministic policy: a bash tool call for the first `tool_turns`
    assistant turns, then a final answer."""
    n_assistant = sum(
        1 for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
    )
    bash = _find_tool(tools, "bash")
    if n_assistant < tool_turns and bash is not None:
        args = json.dumps(
            {"command": "printf 'hello from the stub\\n' > hello.txt"},
            sort_keys=True,
            separators=(",", ":"),
        )
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_stub_{n_assistant:04d}",
                    "type": "function",
                    "function": {"name": bash, "arguments": args},
                }
            ],
        }
        return message, "tool_calls"
    return {"role": "assistant", "content": "Done. hello.txt has been written."}, "stop"


def build_response(request: dict, seq: int, tool_turns: int) -> dict:
    messages = request.get("messages") or []
    p_ids = prompt_tokens(messages)
    message, finish_reason = decide(messages, request.get("tools"), tool_turns)

    body = message_body(message)
    r_ids = list(body.encode("utf-8")) + [EOT_ID]
    # Finite, strictly negative, deterministic, never 0.0.
    logprobs = [-0.03125 * ((i % 7) + 1) for i in range(len(r_ids))]

    return {
        "id": f"chatcmpl-stub-{seq:08d}",
        "object": "chat.completion",
        "created": 0,
        "model": request.get("model", "stub-model"),
        "prompt_token_ids": p_ids,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
                "token_ids": r_ids,
                "logprobs": {
                    "content": [
                        {"token": token_str(t), "token_id": t, "logprob": lp}
                        for t, lp in zip(r_ids, logprobs)
                    ]
                },
            }
        ],
        "usage": {
            "prompt_tokens": len(p_ids),
            "completion_tokens": len(r_ids),
            "total_tokens": len(p_ids) + len(r_ids),
        },
    }


def response_to_stream_chunk(response: dict) -> dict:
    """Mirror of the gateway's `_response_to_stream_chunk`
    (`gateway/server.py:771-810`): one chunk carrying the whole message.

    pi 0.83.0 always sends `stream: true` (measured — CP-06 Step 2), so the
    direct-run stub must speak SSE. Polar's gateway answers a streaming
    client with exactly one synthetic delta chunk + `data: [DONE]`; the stub
    replays that same shape so the direct run previews what pi will receive
    through the proxy (A-2 evidence).
    """
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message", {}) or {}
    tool_calls_delta = []
    for i, tc in enumerate(message.get("tool_calls") or []):
        func = tc.get("function", {}) or {}
        tool_calls_delta.append(
            {
                "index": i,
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", ""),
                },
            }
        )
    delta: dict = {"role": "assistant"}
    if message.get("content") is not None:
        delta["content"] = message.get("content")
    if tool_calls_delta:
        delta["tool_calls"] = tool_calls_delta
    return {
        "id": response.get("id"),
        "object": "chat.completion.chunk",
        "created": response.get("created"),
        "model": response.get("model"),
        "choices": [
            {"index": 0, "delta": delta, "finish_reason": choice.get("finish_reason")}
        ],
        "usage": response.get("usage"),
    }


class _State:
    def __init__(self, capture_path: Path, tool_turns: int) -> None:
        self.capture_path = capture_path
        self.tool_turns = tool_turns
        self.seq = 0
        self.lock = threading.Lock()

    def next_seq(self) -> int:
        with self.lock:
            self.seq += 1
            return self.seq

    def capture(self, entry: dict) -> None:
        with self.lock:
            self.capture_path.parent.mkdir(parents=True, exist_ok=True)
            with self.capture_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _send_json(self, obj: dict, status: int = 200) -> None:
            payload = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path.rstrip("/") == "/v1/models":
                self._send_json(
                    {
                        "object": "list",
                        "data": [{"id": "stub-model", "object": "model", "created": 0, "owned_by": "cp06"}],
                    }
                )
            elif self.path.rstrip("/") == "/health":
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": {"message": f"no GET {self.path}"}}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            try:
                request = json.loads(raw)
            except ValueError:
                self._send_json({"error": {"message": "invalid JSON"}}, 400)
                return
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send_json({"error": {"message": f"no POST {self.path}"}}, 404)
                return
            seq = state.next_seq()
            response = build_response(request, seq, state.tool_turns)
            streamed = bool(request.get("stream"))
            state.capture(
                {
                    "seq": seq,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "streamed": streamed,
                    "request": request,
                    "response": response,
                }
            )
            if streamed:
                self._send_sse(response)
            else:
                self._send_json(response)

        def _send_sse(self, response: dict) -> None:
            chunk = response_to_stream_chunk(response)
            payload = (
                f"data: {json.dumps(chunk)}\n\n" + "data: [DONE]\n\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--capture", required=True, help="JSONL capture file")
    parser.add_argument(
        "--tool-turns",
        type=int,
        default=1,
        help="assistant turns that answer with a tool call before the final answer",
    )
    args = parser.parse_args()

    state = _State(Path(args.capture), args.tool_turns)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"stub backend on http://{args.host}:{args.port} (EOT_ID={EOT_ID}, tool_turns={args.tool_turns})")
    server.serve_forever()


if __name__ == "__main__":
    main()
