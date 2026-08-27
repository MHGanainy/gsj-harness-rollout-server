#!/usr/bin/env bash
# estate/serving/serve-llama31.sh — CP-38: the estate's SECOND model family.
# Serves Llama-3.1-8B-Instruct (unsloth mirror, pinned revision) on the H200
# under the family's own four legs. This is serve.sh's shape with the legs
# re-decided for Llama — each delta deliberate, recorded in
# docs/reports/CP-38.md:
#   1. --tool-call-parser llama3_json (not hermes) — Llama renders tool calls
#      in its own JSON dialect; hermes would leave every call unparsed text.
#   2. NO --chat-template flag: the served template is the snapshot's own
#      EMBEDDED one — Meta's full template, the artifact CP-37 measured
#      prefix-extending offline. serve-time output records its sha256 from
#      the snapshot actually served (mirrors of this model ship different
#      templates; the hash is the identity).
#   3. NO --reasoning-parser and NO --default-chat-template-kwargs — both
#      are Qwen legs (qwen3 parser; enable_thinking is unused jinja context
#      on Llama templates, a measured wire no-op).
#   4. --generation-config genconfig-llama31 — the snapshot's own
#      generation_config.json, byte-copied at serve time (temperature 0.6,
#      top_p 0.9, eos [128001, 128008, 128009]); the CP-09 F1 lesson holds
#      across families: pin it or pi's parameterless requests sample at
#      the engine's accidental defaults.
#   Unchanged from serve.sh: --max-model-len 32768 (>= the demo config's
#   context_window), port 8000, GPU default 3 (override GSJ_VLLM_GPU),
#   gpu-frac 0.30, nohup/pidfile/tunnel discipline, --enforce-eager,
#   DEBUG request logging, the pre-existing ~/gsj-vllm venv.
#   Distinct state so the Qwen recipe is untouched: model-llama31.env,
#   genconfig-llama31/, run/vllm-llama31.{pid,log}, local run dir
#   run/gsj-vllm-llama31/. Refuses to start while the Qwen pidfile is
#   alive (one engine, one port).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST="${GSJ_VLLM_SSH_HOST:-h200-admin}"
PORT="${GSJ_VLLM_PORT:-8000}"
LOCAL_PORT="${GSJ_VLLM_LOCAL_PORT:-8100}"
GPU="${GSJ_VLLM_GPU:-3}"
RDIR="${GSJ_VLLM_REMOTE_DIR:-gsj-vllm}"
RUN="$HERE/run/gsj-vllm-llama31"
mkdir -p "$RUN"
GPU_FRAC="${GSJ_VLLM_GPU_FRAC:-0.30}"
MODEL_ENV="${GSJ_VLLM_MODEL_ENV:-$HERE/model-llama31-8b.env}"
# shellcheck source=model-llama31-8b.env
source "$MODEL_ENV"

log() { echo "[serve-llama31.sh cp38] $*"; }

write_endpoint_env() {
  {
    echo "GSJ_VLLM_URL=http://127.0.0.1:${LOCAL_PORT}/v1"
    echo "GSJ_VLLM_REMOTE_LOG=${SSH_HOST}:~/${RDIR}/run/vllm-llama31.log"
  } > "$RUN/endpoint.env"
}

healthy() {
  curl -sf -m 3 "http://127.0.0.1:${LOCAL_PORT}/v1/models" 2>/dev/null \
    | grep -q "\"${GSJ_MODEL_ID}\""
}

if healthy; then
  write_endpoint_env
  log "already serving ${GSJ_MODEL_ID} at http://127.0.0.1:${LOCAL_PORT}/v1 — nothing to do"
  exit 0
fi

log "syncing model pin to ${SSH_HOST}:~/${RDIR}/"
ssh "$SSH_HOST" "mkdir -p ~/${RDIR}/run ~/${RDIR}/genconfig-llama31"
scp -q "$MODEL_ENV" "${SSH_HOST}:${RDIR}/model-llama31.env"

log "remote: require venv, fetch the pinned snapshot, pin genconfig, record the embedded template's identity"
ssh "$SSH_HOST" bash -s "$RDIR" <<'REMOTE_SETUP'
set -euo pipefail
RDIR="$1"; cd ~/"$RDIR"
[ -x venv/bin/vllm ] || { echo "ERROR: ~/$RDIR/venv missing — run the predecessor's staging/serving/serve.sh once (BRINGUP §3) to provision it"; exit 1; }
source model-llama31.env
SNAP="$(./venv/bin/python - "$GSJ_MODEL_ID" "$GSJ_MODEL_REVISION" <<'PY'
import sys
from huggingface_hub import snapshot_download
print(snapshot_download(sys.argv[1], revision=sys.argv[2]))
PY
)"
echo "snapshot: $SNAP"
cp "$SNAP/generation_config.json" genconfig-llama31/generation_config.json
echo -n "generation_config.json  "; sha256sum genconfig-llama31/generation_config.json | cut -d' ' -f1
./venv/bin/python - "$SNAP" <<'PY'
import hashlib, json, sys
snap = sys.argv[1]
tpl = json.load(open(f"{snap}/tokenizer_config.json"))["chat_template"]
print(f"embedded chat_template   sha256 {hashlib.sha256(tpl.encode()).hexdigest()}  ({len(tpl)} chars)")
raw = open(f"{snap}/tokenizer.json", "rb").read()
print(f"tokenizer.json           blob-sha1 {hashlib.sha1(b'blob %d\x00' % len(raw) + raw).hexdigest()}")
PY
REMOTE_SETUP

log "remote: starting vllm serve on the embedded Llama template (skipped when pidfile is alive)"
ssh "$SSH_HOST" bash -s "$RDIR" "$GPU" "$PORT" "$GPU_FRAC" <<'REMOTE_START'
set -euo pipefail
RDIR="$1"; GPU="$2"; PORT="$3"; GPU_FRAC="$4"; cd ~/"$RDIR"
source model-llama31.env
if [ -f run/vllm.pid ] && kill -0 "$(cat run/vllm.pid)" 2>/dev/null; then
  echo "ERROR: the Qwen engine is alive (run/vllm.pid) on this port — stop it first"; exit 1
fi
if [ -f run/vllm-llama31.pid ] && kill -0 "$(cat run/vllm-llama31.pid)" 2>/dev/null; then
  echo "vllm (llama31) already running (pid $(cat run/vllm-llama31.pid))"
  exit 0
fi
CUDA_VISIBLE_DEVICES="$GPU" VLLM_LOGGING_LEVEL=DEBUG \
VLLM_ATTENTION_BACKEND=FLASH_ATTN VLLM_USE_FLASHINFER_SAMPLER=0 \
nohup ./venv/bin/vllm serve "$GSJ_MODEL_ID" \
  --revision "$GSJ_MODEL_REVISION" \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len 32768 \
  --gpu-memory-utilization "$GPU_FRAC" \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json \
  --generation-config "$HOME/$RDIR/genconfig-llama31" \
  --enable-log-requests \
  --enforce-eager \
  > run/vllm-llama31.log 2>&1 &
echo $! > run/vllm-llama31.pid
echo "vllm started (pid $(cat run/vllm-llama31.pid), gpu $GPU, port $PORT, template: snapshot-embedded)"
REMOTE_START

if [ -f "$RUN/tunnel.pid" ] && kill -0 "$(cat "$RUN/tunnel.pid")" 2>/dev/null; then
  log "tunnel already up (pid $(cat "$RUN/tunnel.pid"))"
else
  log "opening tunnel 127.0.0.1:${LOCAL_PORT} -> ${SSH_HOST}:127.0.0.1:${PORT}"
  ssh -N -o ExitOnForwardFailure=yes -o BatchMode=yes \
    -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${PORT}" "$SSH_HOST" &
  echo $! > "$RUN/tunnel.pid"
  disown
fi

log "waiting for /health (first start includes weight load)"
for i in $(seq 1 180); do
  if curl -sf -m 3 "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 5
  if [ "$i" -eq 180 ]; then
    log "ERROR: /health not up after 900s — see ${SSH_HOST}:~/${RDIR}/run/vllm-llama31.log"
    exit 1
  fi
done

healthy || { log "ERROR: /v1/models does not list ${GSJ_MODEL_ID}"; exit 1; }
write_endpoint_env
log "serving ${GSJ_MODEL_ID}@${GSJ_MODEL_REVISION} at http://127.0.0.1:${LOCAL_PORT}/v1 under the embedded Llama template"
