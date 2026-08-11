#!/usr/bin/env bash
# staging/serving/serve.sh — CP-04' bring-up of vLLM serving Qwen/Qwen3-0.6B
# on the H200, UNDER THE SYMMETRIC CHAT TEMPLATE (Direction A, ADR-0007).
#
# Adapted from the predecessor's staging/serving/serve.sh (gsj-envloader,
# accurate per BRINGUP.md — law 3 keeps that file authoritative for ITS
# estate). Deltas, each deliberate and recorded in docs/reports/CP-04prime.md:
#   1. --chat-template ~/<RDIR>/qwen3_training.jinja — the adopted symmetric
#      template (TRL's qwen3_training.jinja, byte-verbatim; sha256 1d944ff8…),
#      scp'd from this directory at serve time. The CP-04' inherited DoD
#      item 3: per-request overrides are NOT the mechanism.
#   2. --generation-config ~/<RDIR>/genconfig — the snapshot's own
#      generation_config.json, byte-copied at serve time and pinned
#      EXPLICITLY in the argv (CP-09 F1: an unpinned engine samples pi's
#      parameterless requests at T=1.0 silently). On this snapshot the file
#      exists and equals the codec pin (sha256 2325da0f…) — verified, not
#      assumed; the explicit flag makes the pin auditable from the argv.
#   3. GPU default 3, not 7 — GPUs 0/1/2/6/7 are occupied by other tenants
#      at CP-04'; still overridable via GSJ_VLLM_GPU.
#   4. --enable-lora + VLLM_ALLOW_RUNTIME_LORA_UPDATING dropped — that is
#      the predecessor's M2 training-loop capability; this estate has no
#      LoRA consumer (scope law), and the Mac pair's serve argv had none
#      either, which keeps the two pairs' engine surfaces symmetric.
#   5. The venv + snapshot are REQUIRED to pre-exist (~/<RDIR>/venv, the
#      predecessor's BRINGUP §3 provisioning — they survive teardown by
#      design). This script only starts the engine; it does not install.
# Everything else (ports, tunnel, nohup/pidfile discipline, FLASH_ATTN on a
# host without nvcc, --enforce-eager, the thinking-off default kwargs, DEBUG
# request logging) is the predecessor's recipe verbatim.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST="${GSJ_VLLM_SSH_HOST:-h200-admin}"
PORT="${GSJ_VLLM_PORT:-8000}"
LOCAL_PORT="${GSJ_VLLM_LOCAL_PORT:-8100}"
GPU="${GSJ_VLLM_GPU:-3}"
RDIR="${GSJ_VLLM_REMOTE_DIR:-gsj-vllm}"
RUN="$HERE/run/$RDIR"
mkdir -p "$RUN"
GPU_FRAC="${GSJ_VLLM_GPU_FRAC:-0.30}"
MODEL_ENV="${GSJ_VLLM_MODEL_ENV:-$HERE/model-0.6b.env}"
# shellcheck source=model-0.6b.env
source "$MODEL_ENV"

log() { echo "[serve.sh cp04'] $*"; }

write_endpoint_env() {
  {
    echo "GSJ_VLLM_URL=http://127.0.0.1:${LOCAL_PORT}/v1"
    echo "GSJ_VLLM_REMOTE_LOG=${SSH_HOST}:~/${RDIR}/run/vllm.log"
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

log "syncing model pin + symmetric template to ${SSH_HOST}:~/${RDIR}/"
ssh "$SSH_HOST" "mkdir -p ~/${RDIR}/run ~/${RDIR}/genconfig"
scp -q "$MODEL_ENV" "${SSH_HOST}:${RDIR}/model.env"
scp -q "$HERE/qwen3_training.jinja" "${SSH_HOST}:${RDIR}/qwen3_training.jinja"

log "remote: require venv + snapshot (BRINGUP §3 provisioning), pin genconfig"
ssh "$SSH_HOST" bash -s "$RDIR" <<'REMOTE_SETUP'
set -euo pipefail
RDIR="$1"; cd ~/"$RDIR"
[ -x venv/bin/vllm ] || { echo "ERROR: ~/$RDIR/venv missing — run the predecessor's staging/serving/serve.sh once (BRINGUP §3) to provision it"; exit 1; }
source model.env
SNAP="$(./venv/bin/python - "$GSJ_MODEL_ID" "$GSJ_MODEL_REVISION" <<'PY'
import sys
from huggingface_hub import snapshot_download
print(snapshot_download(sys.argv[1], revision=sys.argv[2]))
PY
)"
cp "$SNAP/generation_config.json" genconfig/generation_config.json
sha256sum genconfig/generation_config.json
REMOTE_SETUP

log "remote: starting vllm serve under the symmetric template (skipped when pidfile is alive)"
ssh "$SSH_HOST" bash -s "$RDIR" "$GPU" "$PORT" "$GPU_FRAC" <<'REMOTE_START'
set -euo pipefail
RDIR="$1"; GPU="$2"; PORT="$3"; GPU_FRAC="$4"; cd ~/"$RDIR"
source model.env
if [ -f run/vllm.pid ] && kill -0 "$(cat run/vllm.pid)" 2>/dev/null; then
  echo "vllm already running (pid $(cat run/vllm.pid))"
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
  --tool-call-parser hermes \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --chat-template "$HOME/$RDIR/qwen3_training.jinja" \
  --generation-config "$HOME/$RDIR/genconfig" \
  --enable-log-requests \
  --enforce-eager \
  > run/vllm.log 2>&1 &
echo $! > run/vllm.pid
echo "vllm started (pid $(cat run/vllm.pid), gpu $GPU, port $PORT, template qwen3_training.jinja)"
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
    log "ERROR: /health not up after 900s — see ${SSH_HOST}:~/${RDIR}/run/vllm.log"
    exit 1
  fi
done

healthy || { log "ERROR: /v1/models does not list ${GSJ_MODEL_ID}"; exit 1; }
write_endpoint_env
log "serving ${GSJ_MODEL_ID}@${GSJ_MODEL_REVISION} at http://127.0.0.1:${LOCAL_PORT}/v1 under the symmetric template"
