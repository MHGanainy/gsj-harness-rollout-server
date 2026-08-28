# estate/ — the reference estate
Everything here stands the **test** estate up on the host the library was measured on (a shared Linux GPU box, "the H200") — the inference engine, the git host holding one repository per case, the retrieval service, the corpus loaded into both, and the container runtime that isolates each episode: everything the rollout server needs but does not host and reads only through one YAML, `rollout.h200.yaml`; production brings its own counterpart to every piece.
`estate.sh` is the front door (`./estate.sh --help`) and only routes: every verb runs an existing script or compose file in place, and the scripts **start** services — they do not install them. Restore-from-cold (Docker, the host's firewall conventions, the vLLM venv, the model snapshot) is the predecessor's [`gsj-envloader/staging/BRINGUP.md`](https://github.com/MHGanainy/gsj-envloader/blob/v0.8.0/staging/BRINGUP.md) (archived at `v0.8.0`, accurate as written: §1 Forgejo, §3 venv + snapshot, §4 self-forwards); bring-up on an empty machine is [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo)'s `bootstrap.py`. YAML keys and validators are [the server guide](../docs/guide/server-guide.md)'s; this file is the recipe.
## The components
| Component | Recipe here | Delta vs the predecessor's `BRINGUP.md` |
| --- | --- | --- |
| Forgejo | `forgejo/up.sh`: `docker compose up -d`, health wait ≤90 s, admin `gsj-admin`, API token → `forgejo/.token`; image `codeberg.org/forgejo/forgejo:16.0.2`, static IP `172.28.9.10:3000` on the compose network `gsj-staging-net`, no published ports, HTTP only (SSH disabled) | none — BRINGUP §1 verbatim, same instance and data directory |
| Corpus | `python3 estate/corpus/ingest_corpus.py scaffold --corpus estate/corpus/staging`, from the host checkout (`~/gsj-harness-rollout-server`) after `estate.sh owner gsj-staging` (the owner `corpus.yaml` names) and `export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat estate/forgejo/.token-gsj-staging)"`; the same command with `ingest` after `mcp-up` reindexes and waits for ready | the split-shaped v2 source tree (train/eval is the directory layout); commit identity and dates fixed in `corpus.yaml`, so the SHAs converge byte-identically |
| Retrieval service | `mcp-service/compose.yml`: image `gsj-mcp-service:0.3.0` (the ChromaDB backend), `network_mode: host` on `0.0.0.0:8790`, `user: 1000:1000`, `./data` as the volume; shipped per `mcp-service/README.md` — build on the workstation, `docker save \| ssh h200-admin docker load` | 0.3.0 replaces 0.2.0: `/health` gains the `backend` block; a cold start rebuilds any previous-format index (`INDEX_FORMAT` is 2 and part of the corpus fingerprint) |
| vLLM | `serving/serve.sh`: Qwen/Qwen3-0.6B at the pinned revision, driven from the workstation over SSH | five deltas (script header): the symmetric template `qwen3_training.jinja`, an explicit `--generation-config` pin, GPU default 3 (not 7), no LoRA flags (`--enable-lora`, `VLLM_ALLOW_RUNTIME_LORA_UPDATING` dropped), venv + snapshot must pre-exist (BRINGUP §3) |
| Self-forwards | BRINGUP §4, as the consumer needs them | the predecessor's collector needed the bridge-IP forward; this repo's Polar gateway reads the engine host-locally and needs none |
| *Run-time state* | `forgejo/forgejo-data/` (the live instance), `forgejo/.token*` (mode 0600), `mcp-service/data/` (clone cache + index), `serving/run/` (`endpoint.env`, tunnel pid per engine) | written at run time, never committed; survives `git pull` |

![The two networks of the reference estate: host-bound services split by bind address, the compose network holding Forgejo and the episode containers, and the YAML key that names each address](../docs/guide/img/estate-topology.png)

<sub>Which process listens where. The episode container lives on the compose network next to Forgejo and reaches host services through the network's gateway address; the engine is reached only from the host — where Polar's two processes, the receiver and submission all run as uid 1000.</sub>
## `estate.sh` — the front door
| Verb | Runs / needs |
| --- | --- |
| `up` | `forgejo/up.sh` — idempotent, every step checks before it creates; needs `docker` |
| `owner <name>` | `forgejo/create_owner.sh` — the owner user if absent, a push token → `forgejo/.token-<name>`; prints the `export GSJ_FORGEJO_TOKEN_<NAME>=…` line the pipeline reads (owner uppercased, `-` becomes `_`); needs Forgejo up |
| `down [--wipe]` | `forgejo/down.sh` — `docker compose down --remove-orphans`; `--wipe` also deletes `forgejo-data/` and `.token` (owner tokens stay); after a wipe, `up` + `owner` + `scaffold` reproduce byte-identical case repos — `corpus/staging/corpus.lock.json` is the freeze record |
| `mcp-up` / `mcp-down` | `docker compose -f mcp-service/compose.yml up -d` / `down`; `mcp-up` needs the `gsj-mcp-service` image loaded and `GSJ_MCP_TOKEN_SECRET` exported — the verb refuses before compose does, and the value never lands in a file |
| `serve <0.6b\|llama31>` | `serving/serve.sh` / `serving/serve-llama31.sh`; needs the host's venv + snapshot (BRINGUP §3) |
| `serve-updated <dir>` | `serving/serve-updated.sh` — the weight-sync half; needs a trainer's HF-format export directory on the serving host |
| `health` | `serving/healthcheck.sh` — `/health`, `/v1/models` lists the pin, one full tool round trip; needs `serving/run/<dir>/endpoint.env` |
| `status` | `docker compose ps` for Forgejo and the retrieval service, then the engine probe |

![estate.sh verbs in bring-up order, up through health, with the corpus pipeline's scaffold and ingest between them and the on-demand verbs below](../docs/guide/img/estate-bringup.png)

<sub>The bring-up order and what each step needs. There is no corpus verb — the pipeline tool sits between `owner` and `mcp-up`. The script `cd`s to `estate/` first (invoke it from anywhere); an unknown verb, a missing argument or a missing tool exits 1 with a one-line reason.</sub>
## The networking facts — `rollout.h200.yaml` holds values, never code
- **Our harness clones inside the sandbox** (`git clone --depth 1`), so the episode container itself must reach Forgejo's static IP — and a container on Docker's default bridge cannot reach `172.28.9.10`. The cure is one value, `runtime.network: gsj-staging-net`; forgetting it costs an episode.
- **`host.docker.internal` never resolves in an episode** — Polar's Docker runtime passes only `--network`, never `--add-host`. Host-bound services (the retrieval service on `0.0.0.0:8790`, the gateway on `0.0.0.0:8200`) are addressed by the compose network's own gateway IP `172.28.9.1`, the host as seen from that network; `172.17.0.1` also answers but names the default bridge.
- **`serving_base_url` carries no `/v1` suffix** — Polar's proxy appends `/v1/chat/completions` itself, so a suffixed value requests `/v1/v1/…` and gets a 404. vLLM listens on `127.0.0.1:8000` and only the gateway dials it, from the host, so no bridge forward is needed; port `8100` stays free for BRINGUP §4's self-forward convention.

| Key | Value here | Reachable from / note |
| --- | --- | --- |
| `estate.clone_url_for` | `http://172.28.9.10:3000/gsj-staging/{case_id}.git` | inside the episode container |
| `estate.mcp_url_base` | `http://172.28.9.1:8790` | inside the episode container |
| `estate.serving_base_url` | `http://127.0.0.1:8000` | the gateway, on the host |
| `polar.gateway.public_url` | `http://172.28.9.1:8200` | the host **and** the container — one URL, both dialers |
| `polar.rollout` | `127.0.0.1:8080` | a same-host trainer |
| `receiver` | `127.0.0.1:8300` | the rollout API, on the host |
| `runtime.network` | `gsj-staging-net` | every episode joins the compose network |
| `builder.end_of_turn_token_id` | `151645` | `<\|im_end\|>` under the served tokenizer — a measurement, not an address |
| `checks.zero_at_mask1_max_rate` | `0.25` | this CUDA bf16 engine emits exact-`0.0` logprobs at ~14 % of `mask == 1` positions (34/237 measured); the default allowance covers it |
## Serving
All three serve scripts run on the workstation and drive the serving host over an SSH alias (every remote step is `bash -s`), keep the pidfile + tunnel discipline, and write `serving/run/<dir>/endpoint.env` (`GSJ_VLLM_URL`, the remote log path). Defaults: `GSJ_VLLM_SSH_HOST=h200-admin`, `GSJ_VLLM_PORT=8000` (the engine, on `127.0.0.1`), `GSJ_VLLM_LOCAL_PORT=8100` (the tunnel), `GSJ_VLLM_GPU=3` (`CUDA_VISIBLE_DEVICES`), `GSJ_VLLM_GPU_FRAC=0.30` (`--gpu-memory-utilization`), `GSJ_VLLM_REMOTE_DIR=gsj-vllm`, `GSJ_VLLM_MODEL_ENV=model-0.6b.env` (sets `GSJ_MODEL_ID` + `GSJ_MODEL_REVISION`; `healthcheck.sh` sources it too — with the Llama engine up, run `GSJ_VLLM_MODEL_ENV=serving/model-llama31-8b.env ./estate.sh health`).
- `serve.sh` (`serve 0.6b`) — `Qwen/Qwen3-0.6B` @ `c1899de2…`. Idempotent: if `/v1/models` through the tunnel already lists the pin, it rewrites `endpoint.env` and exits 0; otherwise it copies `model-0.6b.env` + the jinja to `~/gsj-vllm/`, requires the venv, resolves the pinned snapshot (`huggingface_hub`), byte-copies its `generation_config.json` into `~/gsj-vllm/genconfig/` (printing its sha256), starts `vllm serve` under `nohup` unless `run/vllm.pid` is alive (log `run/vllm.log`, local state `serving/run/gsj-vllm/`), opens the tunnel unless `run/tunnel.pid` is alive, and waits ≤900 s on `/health`. Flags: `--chat-template ~/gsj-vllm/qwen3_training.jinja`, `--tool-call-parser hermes`, `--reasoning-parser qwen3`, `--default-chat-template-kwargs '{"enable_thinking": false}'`; the generation config is pinned in the argv on purpose — pi sends no sampling parameters, and an unpinned engine samples them at `T=1.0` silently.
- `serve-updated.sh <dir>` — `serve.sh` with exactly two deltas: the model is a **local HF-format directory** on the serving host (the trainer's export; no `--revision`; refuses a directory without `config.json`), and `--served-model-name Qwen/Qwen3-0.6B` keeps the wire identity constant across the sync; the four legs — template, generation-config pin, parsers, context length — stay byte-identical, so a post-sync trace compares to a pre-sync one. Stop-then-start, not reload (SIGTERM, ≤60 s, then SIGKILL — vLLM at this pin has no in-place swap for a non-LoRA model; the stop is the drain point between collection phases), then waits ≤600 s on `/health`.
- `serve-llama31.sh` (`serve llama31`) — `unsloth/Meta-Llama-3.1-8B-Instruct` @ `a2856192…` (the origin repo is gated; the mirror carries Meta's weights and full chat template), pinned in `model-llama31-8b.env`; genconfig `~/gsj-vllm/genconfig-llama31`, byte-copied from the snapshot (temperature 0.6, top-p 0.9, eos `[128001, 128008, 128009]`). No template flag — the snapshot's own **embedded** template, its sha256 and the tokenizer's blob hash recorded from the snapshot actually served (mirrors ship different templates); `--tool-call-parser llama3_json` (under `hermes` every call stays unparsed text); neither Qwen-only flag — `enable_thinking` is a measured wire no-op on a Llama template. State `run/vllm-llama31.{pid,log}`, `serving/run/gsj-vllm-llama31/`; refuses to start while the Qwen pidfile is alive (one engine, one port); otherwise `serve.sh`'s shape plus `--max-model-len 32768`, `--enforce-eager`, DEBUG request logging.
- `qwen3_training.jinja` — HuggingFace TRL's `trl/chat_templates/qwen3_training.jinja` **byte-verbatim**: sha256 `1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`, upstream commit `63b7c3f547d3e06d0eae72712e36b7b64e9d5a45` (2026-07-16); served via `--chat-template` (the file, not a per-request override) and pinned as `chat_template_hash` in `pins/pins.gsj.json`. Its history branch always emits the think block, so consecutive pi prompts are strict token-prefix extensions and Polar's prefix grouping merges them natively — `generation_prompt_glue_ids` deliberately unset; the `{% generation %}` markers are accepted by the served vLLM 0.26.0 renderer.
## Closing anonymous read (CP-56)
By default the estate serves anonymous git read, so a sandbox agent that guesses `http://172.28.9.10:3000/gsj-staging/<case>.git` can re-clone a repo it was never given — or its own repo at a later `timestep-` branch — and read past its cutoff over the network. The in-sandbox git-history channel is already closed (CP-11: `--depth 1`, no remote, no reflog); this is the *network* channel, and it only matters for an estate someone intends to **train** from (every estate so far has been synthetic-corpus evaluation).

The cure is **mechanism (a): credentialed clone URLs + Forgejo sign-in.** `estate.sh owner gsj-staging` now mints a read-scoped token (`read:repository,read:user`) into `estate/forgejo/.token-gsj-staging-read` beside the push token, and prints its export line; `rollout.h200.yaml`'s `clone_credential_env` splices it into the sandbox clone URL at render (the token never lands in the config or a trace — `pi_harness` strips userinfo from the echo). Enabling it:

```bash
./estate.sh up                                   # forgejo, sign-in still OFF
./estate.sh owner gsj-staging                    # mints BOTH tokens; prints the exports
export GSJ_FORGEJO_TOKEN_GSJ_STAGING=$(cat estate/forgejo/.token-gsj-staging)
export GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING=$(cat estate/forgejo/.token-gsj-staging-read)
python3 estate/corpus/ingest_corpus.py all --corpus estate/corpus/staging   # scaffold + index, ANONYMOUS
./estate.sh mcp-up                               # cold index build, ANONYMOUS
# --- now, and only now, flip: ---
#   uncomment REQUIRE_SIGNIN_VIEW in estate/forgejo/docker-compose.yml
#   uncomment clone_credential_env  in estate/rollout.h200.yaml
./estate.sh up                                   # recreates forgejo with sign-in ON
```

**Order matters, and it is a freeze finding, not a preference.** Turning sign-in on breaks two read paths that this CP left frozen: the pipeline's `phase_scaffold`/`verify` re-clone (`estate/corpus/ingest_corpus.py` reads anonymously and its push re-splices, so no single `--base-url` authenticates both) and a *cold* MCP index build (`estate/mcp-service/config.yaml` ships `auth_token_env: null`). Both are bring-up-time, not episode-time — so scaffold and build the index first, then flip; a warm MCP index serves episodes without re-cloning, and the harness clones with the read token. Making the H200 flip a one-shot needs those two lifted to present the token (`auth_token_env` + a verify credential) — gap row 2's remaining work. The demo estate (`gsj-rollout-demo`, all consumers lifted) already does the flip in `bootstrap.py` as its last step and closes it live.

## The trainer side — what the estate did not already provide
| Need | How |
| --- | --- |
| slime v0.3.0 + Megatron + torch + Ray | the official `slimerl/slime:v0.3.0` image (24.4 GB pulled, ~55 GB on disk) — a second, entirely separate runtime; nothing in the estate's venvs is reused |
| The image, on this box | **`docker pull` fails**: dockerd's registry egress runs as root and the uid-scoped firewall (`lockdown.sh`) drops it. Fetch as uid 1000 with a static `skopeo` (`skopeo copy docker://… docker-archive:…`, needs a `~/.config/containers/policy.json`), then `docker load -i` |
| GPUs | serving on GPU 3, training on GPU 5 — disjoint, discovered free at run time |
| slime checkout + Megatron | slime: `git clone --branch v0.3.0` plus Polar's `scripts/patch/patch_slime_router_tokens.sh`, mounted into the container; Megatron: the **image's own** `/root/Megatron-LM` (`1dcf0dafa`, the Dockerfile's `MEGATRON_COMMIT`) — Polar's stated slime-v0.3.0-compatible pin `26.04-alpha.rc1` dies at import (`ModuleNotFoundError: No module named 'megatron.training.tokenizer'`). The recipe that ran: [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples)' `slime_bridge/cp17_loop/train_one_step.sh`; the loop — collect, train one step, export, `serve-updated`, collect again — is in [the trainer guide](../docs/guide/trainer-guide.md) |
## If your checkout predates `estate/`
This tree used to live at the repository root (`forgejo/`, `mcp-service/`, `corpus/`, `staging/`); `git pull` moves the **tracked** files only, so the ignored instance data stays at the old paths, and a compose up from the new location would mount an empty `./data` and start a **blank Forgejo** — it reads as data loss and is only a wrong mount. From the checkout root, before the first bring-up (move any other untracked keepsakes — venvs, caches — the same way; the compose project names are pinned as `gsj-envloader-staging` and `gsj-mcp-service`, so running containers are not renamed out from under you):
```bash
mv forgejo/forgejo-data estate/forgejo/forgejo-data; mv forgejo/.token* estate/forgejo/
mv mcp-service/data estate/mcp-service/data; mv staging/serving/run estate/serving/run
rmdir forgejo mcp-service staging/serving staging 2>/dev/null || true  # tidy the husks
```
## Provenance
- CP-04′: this directory, the `serve.sh` deltas, the symmetric template (glue unset), the networking measurements (attempt 1 died at the default bridge, attempt 2 404'd on `/v1/v1/…`), the zero-logprob measurement · CP-50: grouped under `estate/` (until then `staging/README.md`, components at the repo root).
- CP-03: one `public_url` for both dialers · CP-09: the unpinned-engine `T=1.0` lesson · CP-09′: single-GPU collection · CP-10: the 0.25 allowance · CP-11: the hardened `--depth 1` clone · CP-14: the v2 corpus tree · CP-15: `gsj-mcp-service:0.3.0` · law 3: `BRINGUP.md` stays the predecessor's.
- CP-17 (`a647359`): `serve-updated.sh` + the trainer side — the same commit wrote the Megatron erratum it contradicted, which stood until CP-39 · CP-37: the embedded Llama template measured prefix-extending offline · CP-38: `serve-llama31.sh` + `model-llama31-8b.env` · CP-39: this recipe listed (audit S9 — the reproducibility claim was two files short).
## See also
[Server guide](../docs/guide/server-guide.md) · [Trainer guide](../docs/guide/trainer-guide.md) · [Troubleshooting](../docs/guide/troubleshooting.md)
