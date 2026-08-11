#!/usr/bin/env bash
# staging/serving/serve-updated.sh — CP-17 weight-sync half: serve a LOCAL
# checkpoint directory (trainer output) instead of the pinned HF snapshot,
# under the SAME four legs and the SAME served model name.
#
# This is `serve.sh` with exactly two deliberate deltas and nothing else:
#   1. positional arg 1 = the local HF-format checkpoint directory on the
#      serving host (slime's torch_dist -> HF export). `--revision` is
#      dropped because a local directory has none.
#   2. --served-model-name Qwen/Qwen3-0.6B — so the estate's config
#      (`estate.model`, the pi harness, every collected trace) keeps naming
#      the same model across the sync. The WEIGHTS change; the identity the
#      wire speaks does not.
# Everything else is byte-identical to serve.sh: the symmetric chat template,
# the explicit --generation-config pin, --max-model-len 32768, the two
# tool-parser flags, --enforce-eager, DEBUG request logging, the pidfile and
# tunnel discipline. The four legs are what make a collected trace
# comparable to CP-09''s; a weight sync must not perturb them.
#
# Usage: serve-updated.sh <remote-checkpoint-dir>          # e.g. ~/cp17/ckpt/cp17_hf_updated
set -euo pipefail

CKPT="${1:?usage: serve-updated.sh <remote HF checkpoint dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST="${GSJ_VLLM_SSH_HOST:-h200-admin}"
PORT="${GSJ_VLLM_PORT:-8000}"
LOCAL_PORT="${GSJ_VLLM_LOCAL_PORT:-8100}"
GPU="${GSJ_VLLM_GPU:-3}"
RDIR="${GSJ_VLLM_REMOTE_DIR:-gsj-vllm}"
GPU_FRAC="${GSJ_VLLM_GPU_FRAC:-0.30}"
MODEL_ENV="${GSJ_VLLM_MODEL_ENV:-$HERE/model-0.6b.env}"
# shellcheck source=model-0.6b.env
source "$MODEL_ENV"

log() { echo "[serve-updated.sh cp17] $*"; }

log "stopping the current engine (the sync boundary — A-13's drain point)"
ssh "$SSH_HOST" bash -s "$RDIR" <<'REMOTE_STOP'
set -euo pipefail
RDIR="$1"; cd ~/"$RDIR"
if [ -f run/vllm.pid ] && kill -0 "$(cat run/vllm.pid)" 2>/dev/null; then
  kill "$(cat run/vllm.pid)"
  for _ in $(seq 1 60); do
    kill -0 "$(cat run/vllm.pid)" 2>/dev/null || break
    sleep 1
  done
  kill -9 "$(cat run/vllm.pid)" 2>/dev/null || true
  echo "engine stopped (was pid $(cat run/vllm.pid))"
else
  echo "no live engine"
fi
rm -f run/vllm.pid
REMOTE_STOP

log "starting vllm on the updated checkpoint: $CKPT"
ssh "$SSH_HOST" bash -s "$RDIR" "$GPU" "$PORT" "$GPU_FRAC" "$CKPT" "$GSJ_MODEL_ID" <<'REMOTE_START'
set -euo pipefail
RDIR="$1"; GPU="$2"; PORT="$3"; GPU_FRAC="$4"; CKPT="$5"; MODEL_ID="$6"; cd ~/"$RDIR"
[ -f "$CKPT/config.json" ] || { echo "ERROR: $CKPT is not an HF checkpoint dir"; exit 1; }
CUDA_VISIBLE_DEVICES="$GPU" VLLM_LOGGING_LEVEL=DEBUG \
VLLM_ATTENTION_BACKEND=FLASH_ATTN VLLM_USE_FLASHINFER_SAMPLER=0 \
nohup ./venv/bin/vllm serve "$CKPT" \
  --served-model-name "$MODEL_ID" \
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
echo "vllm started on updated weights (pid $(cat run/vllm.pid), gpu $GPU, ckpt $CKPT, served as $MODEL_ID)"
REMOTE_START

log "waiting for /health"
ssh "$SSH_HOST" bash -c '
for i in $(seq 1 120); do
  curl -sf -m 3 "http://127.0.0.1:'"$PORT"'/health" >/dev/null 2>&1 && exit 0
  sleep 5
done
echo "ERROR: /health not up after 600s"; exit 1'
ssh "$SSH_HOST" "curl -sf http://127.0.0.1:${PORT}/v1/models" | grep -q "\"${GSJ_MODEL_ID}\"" \
  || { log "ERROR: /v1/models does not list ${GSJ_MODEL_ID}"; exit 1; }
log "serving the UPDATED weights as ${GSJ_MODEL_ID} — same four legs, same served name"
