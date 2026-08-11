# staging/ — this repo's H200 estate recipe (CP-04′)

Created at CP-04′. The authoritative one-pass estate restore is the
predecessor's `gsj-envloader/staging/BRINGUP.md` (accurate as written —
law 3 keeps it the predecessor's); this directory carries only what THIS
repo's estate does differently, so the estate is reproducible from the
committed tree:

| component | recipe | delta vs BRINGUP |
|---|---|---|
| Forgejo | BRINGUP §1 verbatim (`gsj-envloader/staging/forgejo/up.sh`) | none — same instance, same data dir |
| corpus | `python3 corpus/ingest_corpus.py scaffold --corpus corpus/staging` from THIS repo's checkout on the H200 (`~/gsj-harness-rollout-server`) | the split-shaped v2 tree (CP-14) — SHAs converge to the frozen estate byte-identically |
| MCP service | `mcp-service/compose.yml` from THIS repo's checkout (image `gsj-mcp-service:0.3.0`, the CP-15 ChromaDB backend; ship per `mcp-service/README.md`) | 0.3.0 replaces 0.2.0; `/health` gains the `backend` block; cold start re-indexes (INDEX_FORMAT 2) |
| vLLM | `staging/serving/serve.sh` (this directory) | the CP-04′ deltas, enumerated in the script header: the symmetric chat template (`qwen3_training.jinja`), the explicit `--generation-config` pin, GPU default 3, no LoRA flags; venv + snapshot provisioning stays BRINGUP §3's |
| self-forwards | BRINGUP §4 as needed by the consumer (the predecessor's collector needs the bridge-IP forward; this repo's Polar gateway reads the engine host-locally and needs none) | — |

## serving/serve-updated.sh — serving a trainer checkpoint (CP-17)

The weight-sync half of the loop. `serve.sh` with exactly two deltas: the
model argument is a local HF-format directory (the trainer's export, so no
`--revision`), and `--served-model-name Qwen/Qwen3-0.6B` keeps the wire
identity constant across the sync. **The four legs are byte-identical** —
a weight sync must not perturb what makes a trace comparable to CP-09′'s.
Stop-then-start, not reload: vLLM at this pin has no in-place weight swap
for a non-LoRA model, and the stop is also A-13's drain point.

## The trainer side (CP-17) — what the estate did NOT already provide

| need | how | delta vs the collection estate |
|---|---|---|
| slime v0.3.0 + Megatron + torch + Ray | the official `slimerl/slime:v0.3.0` image (24.4 GB pulled / ~55 GB on disk) | a second, entirely separate runtime; nothing in the estate's venvs is reused |
| the image, on this box | **`docker pull` fails**: dockerd's registry egress runs as root and the uid-scoped firewall drops it (`lockdown.sh`). Cure: fetch as uid 1000 with a static `skopeo` (`skopeo copy docker://… docker-archive:…`, needs a `~/.config/containers/policy.json`), then `docker load -i` | the estate's own images predate the lockdown or were built locally; this is the first checkpoint that needed a NEW image from a public registry |
| GPUs | serving on GPU 3, training on GPU 5 — **disjoint**, discovered free at run time | CP-09′ used one GPU; co-residency is answered by separation, not by sharing |
| slime + Megatron checkouts | `git clone --branch v0.3.0` (slime) and `--branch 26.04-alpha.rc1` (Megatron-LM — Polar's stated slime-v0.3.0-compatible pin), plus Polar's `scripts/patch/patch_slime_router_tokens.sh` | mounted into the container; the image supplies the heavy stack, the checkouts supply the code |

## serving/qwen3_training.jinja — the adopted symmetric template

HuggingFace TRL's `trl/chat_templates/qwen3_training.jinja`, **byte-verbatim**
(sha256 `1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`,
upstream commit `63b7c3f547d3e06d0eae72712e36b7b64e9d5a45`, 2026-07-16).
Adopted at CP-04′ per the inherited DoD (charter §6) and ADR-0007's
Direction A: the history branch always emits the think block, so
consecutive pi prompts are strict token-prefix-extensions and Polar's
grouping (`prefix_merging.py:399`) merges natively — no
`generation_prompt_glue_ids` stitch needed. The choice, the proof
(turn-1 byte-identity across templates; turn-2 strict prefix-extension),
and the serve-path compatibility evidence (`{% generation %}` accepted by
vLLM 0.26.0's renderer) are in `docs/reports/CP-04prime.md` Step 2.

Served via `--chat-template` (the file, not a per-request override);
`pins/pins.gsj.json` `chat_template_hash` pins its sha256.
