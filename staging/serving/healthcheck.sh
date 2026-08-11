#!/usr/bin/env bash
# staging/serving/healthcheck.sh — CP-04' serving health check, the
# predecessor's staging/serving/healthcheck.sh adapted to this directory's
# defaults (model-0.6b.env; run/ layout identical). Verifies, against the
# serve.sh endpoint: (1) /health, (2) the pinned model listed by /v1/models,
# (3) a full tool round trip — the model emits a parsed tool_call, receives
# the tool result, and answers from it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RDIR="${GSJ_VLLM_REMOTE_DIR:-gsj-vllm}"
if [ -f "$HERE/run/$RDIR/endpoint.env" ]; then
  # shellcheck source=/dev/null
  source "$HERE/run/$RDIR/endpoint.env"
fi
BASE="${GSJ_VLLM_URL:-http://127.0.0.1:${GSJ_VLLM_LOCAL_PORT:-8100}/v1}"
BASE="${BASE%/v1}"
MODEL_ENV="${GSJ_VLLM_MODEL_ENV:-$HERE/model-0.6b.env}"
# shellcheck source=model-0.6b.env
source "$MODEL_ENV"

curl -sf -m 5 "$BASE/health" >/dev/null
echo "OK /health"

curl -sf -m 5 "$BASE/v1/models" | grep -q "\"${GSJ_MODEL_ID}\""
echo "OK /v1/models lists ${GSJ_MODEL_ID}"

python3 - "$BASE" "$GSJ_MODEL_ID" <<'PY'
import json, sys, urllib.request

base, model = sys.argv[1], sys.argv[2]

def chat(payload):
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

tools = [{
    "type": "function",
    "function": {
        "name": "get_utc_time",
        "description": "Return the current UTC time as an ISO-8601 string.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]
messages = [{"role": "user",
             "content": "What is the current UTC time? Use the get_utc_time tool."}]

r1 = chat({"model": model, "messages": messages, "tools": tools})
choice = r1["choices"][0]
calls = choice["message"].get("tool_calls") or []
assert calls, f"no tool_calls parsed; finish_reason={choice['finish_reason']}"
assert calls[0]["function"]["name"] == "get_utc_time", calls[0]
print(f"OK tool call parsed: {calls[0]['function']['name']}"
      f" (finish_reason={choice['finish_reason']})")

messages.append({"role": "assistant", "tool_calls": calls, "content": None})
messages.append({"role": "tool", "tool_call_id": calls[0]["id"],
                 "content": "2026-08-04T12:00:00Z"})
r2 = chat({"model": model, "messages": messages, "tools": tools})
answer = r2["choices"][0]["message"]["content"] or ""
assert "12:00" in answer, f"tool result not used in answer: {answer!r}"
print(f"OK tool round trip: {answer.strip()[:100]!r}")
PY

echo "healthcheck OK"
