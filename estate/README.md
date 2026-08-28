# estate/ — the reference estate

Everything in this directory exists to stand a **test** estate up on the host the library was measured on (a shared Linux GPU box, called the H200 throughout the tree). An estate is what the rollout server needs but does not host: an inference engine, a git host holding one repository per case, the retrieval service, the corpus loaded into both, and the container runtime that isolates each episode. Production brings its own counterpart to every piece; the server reads the estate only through the values in one YAML — here, `rollout.h200.yaml`.

`estate.sh` is the front door (`./estate.sh --help`). It only routes: every verb runs an existing script or compose file in place, and the scripts keep their homes — `serve.sh` reads its sibling `model-*.env` files and ships its own jinja, `up.sh` changes into its compose directory. These scripts **start** services; they do not install them. The one-pass restore from cold — Docker, the host's firewall conventions, the vLLM venv, the model snapshot — lives in the predecessor's document, described in [Where the full bring-up lives](#where-the-full-bring-up-lives). A bring-up on an empty machine is the companion repository's job: [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo) and its `bootstrap.py`.

The reader-facing guide to the same material, with the YAML keys and their validators, is [The estate](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/estate.md); this file is the recipe.

## What is here

```text
estate/
├── estate.sh                 # the front door: one verb per script, nothing reimplemented
├── rollout.h200.yaml         # the one YAML for this host, networking facts as comments
├── forgejo/                  # docker-compose.yml, up.sh, create_owner.sh, down.sh
├── mcp-service/              # the retrieval service: Dockerfile, compose.yml, config.yaml, package, tests
├── corpus/                   # ingest_corpus.py and the source tree staging/
└── serving/                  # serve.sh, serve-updated.sh, serve-llama31.sh, healthcheck.sh,
                              # model-0.6b.env, model-llama31-8b.env, qwen3_training.jinja
```

Four paths are written at run time and never committed: `forgejo/forgejo-data/` (the live instance), `forgejo/.token*` (API tokens, mode 0600), `mcp-service/data/` (the service's clone cache and index) and `serving/run/` (`endpoint.env` and the tunnel pid per engine). They survive `git pull`.

## The components

| Component | Recipe in this directory | Delta vs the predecessor's `BRINGUP.md` |
| --- | --- | --- |
| Forgejo | `forgejo/up.sh` — `docker compose up -d`, a health wait of up to 90 s, the admin user `gsj-admin`, an API token into `forgejo/.token`. Image `codeberg.org/forgejo/forgejo:16.0.2`, static container IP `172.28.9.10:3000` on the compose network `gsj-staging-net`, no published ports, HTTP only (SSH disabled) | none — the same instance, the same data directory, BRINGUP §1 verbatim |
| Corpus | `python3 estate/corpus/ingest_corpus.py scaffold --corpus estate/corpus/staging`, run from this repository's checkout on the host (`~/gsj-harness-rollout-server`) after `estate.sh owner gsj-staging` and `export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat estate/forgejo/.token-gsj-staging)"` | the split-shaped v2 source tree (train/eval is the directory layout). Commit identity and dates are fixed in `corpus.yaml`, so the SHAs converge to the frozen estate byte-identically |
| Retrieval service | `mcp-service/compose.yml`: image `gsj-mcp-service:0.3.0` (the ChromaDB backend), `network_mode: host` on `0.0.0.0:8790`, `user: 1000:1000`, `./data` as the volume; shipped per `mcp-service/README.md` (build on the workstation, `docker save \| ssh h200-admin docker load`) | 0.3.0 replaces 0.2.0: `/health` gains the `backend` block, and a cold start rebuilds any index written under the previous format (`INDEX_FORMAT` is 2 and part of the corpus fingerprint) |
| vLLM | `serving/serve.sh` — Qwen/Qwen3-0.6B at the pinned revision, driven from the workstation over SSH | five deltas, enumerated in the script header: the symmetric chat template `qwen3_training.jinja`, an explicit `--generation-config` pin, GPU default 3 (not 7), no LoRA flags (`--enable-lora`, `VLLM_ALLOW_RUNTIME_LORA_UPDATING` dropped — this estate has no LoRA consumer), and the venv + snapshot required to pre-exist — still BRINGUP §3's to provision |
| Self-forwards | BRINGUP §4, as the consumer needs them | the predecessor's collector needs the bridge-IP forward; this repository's Polar gateway reads the engine host-locally and needs none |

![The two networks of the reference estate: host-bound services split by bind address, the compose network holding Forgejo and the episode containers, and the YAML key that names each address](../docs/guide/img/estate-topology.png)

<sub>Which process listens where. The episode container lives on the compose network next to Forgejo; the host's services are reached from there through the network's gateway address, and the engine is reached only from the host.</sub>

## The front door: `estate.sh`

The script `cd`s to `estate/` first, so it can be invoked from anywhere. An unknown verb, a missing argument or a missing tool exits 1 with a one-line reason.

| Verb | Runs | Needs |
| --- | --- | --- |
| `up` | `forgejo/up.sh`: compose up, health wait, admin user, API token — idempotent, every step checks before it creates | `docker` |
| `owner <name>` | `forgejo/create_owner.sh <name>`: the owner user if absent, a push token into `forgejo/.token-<name>`; prints the `export GSJ_FORGEJO_TOKEN_<NAME>=…` line the pipeline reads (owner uppercased, `-` becomes `_`) | Forgejo up |
| `down [--wipe]` | `forgejo/down.sh`: `docker compose down --remove-orphans`; `--wipe` also deletes `forgejo-data/` and `.token` (the owner tokens stay) | — |
| `mcp-up` | `docker compose -f mcp-service/compose.yml up -d` | `docker`, the `gsj-mcp-service` image loaded, `GSJ_MCP_TOKEN_SECRET` exported — the verb refuses before compose does, and the value never lands in a file |
| `mcp-down` | `docker compose -f mcp-service/compose.yml down` | `docker` |
| `serve <0.6b\|llama31>` | `serving/serve.sh` or `serving/serve-llama31.sh` | the host's venv and snapshot (BRINGUP §3 — these scripts start, they do not install) |
| `serve-updated <dir>` | `serving/serve-updated.sh <dir>` — the weight-sync half | a trainer's HF-format export directory on the serving host |
| `health` | `serving/healthcheck.sh`: `/health`, `/v1/models` lists the pin, one full tool round trip | a served endpoint (`serving/run/<dir>/endpoint.env`) |
| `status` | `docker compose ps` for Forgejo and for the retrieval service, then the engine probe | `docker` |

![estate.sh verbs in bring-up order, up through health, with the corpus pipeline's scaffold and ingest between them and the on-demand verbs below](../docs/guide/img/estate-bringup.png)

<sub>The bring-up order and what each step needs. There is no corpus verb: the pipeline tool sits between `owner` and `mcp-up`.</sub>

The whole sequence, from the checkout root on the host:

```bash
cd estate

./estate.sh up                                   # Forgejo at http://172.28.9.10:3000, admin + token
./estate.sh owner gsj-staging                    # the owner named in corpus/staging/corpus.yaml
export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat forgejo/.token-gsj-staging)"
export GSJ_MCP_TOKEN_SECRET='<the shared secret>'

python3 corpus/ingest_corpus.py scaffold --corpus corpus/staging   # deterministic case repos, pushed
./estate.sh mcp-up                                                # the retrieval service; cold start indexes
python3 corpus/ingest_corpus.py ingest   --corpus corpus/staging   # trigger the reindex, wait for ready

./estate.sh serve 0.6b                           # vLLM on the host, tunnel on 127.0.0.1:8100
./estate.sh health
./estate.sh status
```

> [!TIP]
> After `down --wipe`, `up` + `owner` + `scaffold` reproduce byte-identical case repositories — `corpus/staging/corpus.lock.json` is the freeze record. Instance data is disposable by design.

## The networking facts

`rollout.h200.yaml` is the one YAML for this host: values only, swapped for another host, never code. Polar's two processes, the receiver and submission all run on the host as uid 1000. Four facts are encoded in it, measured on this host.

> [!WARNING]
> **The one that costs an episode when forgotten.** Our harness clones **inside** the sandbox (`git clone --depth 1`), where the predecessor cloned host-side and mounted the checkout. So the episode container itself must reach Forgejo's static IP, and Docker isolates its networks: a container on the default bridge cannot reach `172.28.9.10`. The cure is one value — `runtime.network: gsj-staging-net` puts every episode on the compose network, container to container.

- **`host.docker.internal` never resolves in an episode.** Polar's Docker runtime passes only `--network`, never `--add-host`. Host-bound services — the retrieval service on `0.0.0.0:8790`, the gateway on `0.0.0.0:8200` — are addressed by the compose network's own gateway IP, `172.28.9.1`, which is the host as seen from inside that network. `172.17.0.1` also answers, but it names the default bridge's interface.
- **The engine is host-local.** vLLM listens on `127.0.0.1:8000`; only the gateway dials it, from the host, so no bridge forward is needed. `serving_base_url` carries **no `/v1` suffix** — Polar's proxy appends `/v1/chat/completions` itself, and a suffixed value requests `/v1/v1/…` and gets a 404. Port `8100` stays free for the self-forward convention of BRINGUP §4.
- **One `public_url` serves two dialers.** `http://172.28.9.1:8200` is reachable both from the host (the rollout API dispatching) and from the sandbox (pi's model calls), so one URL does both jobs.

| Key | Value here | Reachable from |
| --- | --- | --- |
| `estate.clone_url_for` | `http://172.28.9.10:3000/gsj-staging/{case_id}.git` | inside the episode container |
| `estate.mcp_url_base` | `http://172.28.9.1:8790` | inside the episode container |
| `estate.serving_base_url` | `http://127.0.0.1:8000` | the gateway, on the host |
| `polar.gateway.public_url` | `http://172.28.9.1:8200` | the host and the container |
| `polar.rollout` | `127.0.0.1:8080` | a same-host trainer |
| `receiver` | `127.0.0.1:8300` | the rollout API, on the host |
| `runtime.network` | `gsj-staging-net` | — |

Two more values in the file are estate measurements rather than addresses: `builder.end_of_turn_token_id: 151645` is `<|im_end|>` under the served tokenizer, and `checks.zero_at_mask1_max_rate: 0.25` is stated explicitly because this CUDA bf16 engine emits exact-`0.0` logprobs at about 14 % of `mask == 1` positions (34/237 measured) — the default allowance covers it, the file makes the policy visible.

## Serving

### `serve.sh` — Qwen3-0.6B under the symmetric template

Runs on the workstation and reaches the serving host over an SSH alias; every remote step is delivered as `bash -s`. If `/v1/models` through the local tunnel already lists the pinned model, it rewrites `endpoint.env` and exits 0. Otherwise it copies `model-0.6b.env` and `qwen3_training.jinja` to `~/gsj-vllm/`, requires the venv to exist, resolves the pinned snapshot with `huggingface_hub`, byte-copies the snapshot's `generation_config.json` into `~/gsj-vllm/genconfig/` (printing its sha256), starts `vllm serve` under `nohup` unless `run/vllm.pid` is alive, opens the tunnel unless `run/tunnel.pid` is alive, waits up to 900 s on `/health`, checks `/v1/models`, and writes `serving/run/gsj-vllm/endpoint.env` (`GSJ_VLLM_URL`, the remote log path).

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSJ_VLLM_SSH_HOST` | `h200-admin` | the SSH alias of the serving host |
| `GSJ_VLLM_PORT` | `8000` | the engine's port on the host (`127.0.0.1`) |
| `GSJ_VLLM_LOCAL_PORT` | `8100` | the workstation end of the tunnel |
| `GSJ_VLLM_GPU` | `3` | `CUDA_VISIBLE_DEVICES` |
| `GSJ_VLLM_REMOTE_DIR` | `gsj-vllm` | the directory under the host's home: venv, run state, pinned files |
| `GSJ_VLLM_GPU_FRAC` | `0.30` | `--gpu-memory-utilization` |
| `GSJ_VLLM_MODEL_ENV` | `model-0.6b.env` | the file setting `GSJ_MODEL_ID` and `GSJ_MODEL_REVISION` |

The generation config is pinned in the argv on purpose: pi sends no sampling parameters, so an unpinned engine samples its parameterless requests at `T=1.0` silently. On this snapshot the file exists and equals the codec pin — verified, not assumed.

### `serve-updated.sh <dir>` — serving a trainer checkpoint

The weight-sync half of the training loop. It is `serve.sh` with exactly two deltas: the model argument is a **local HF-format directory** on the serving host (the trainer's export — no `--revision`), and `--served-model-name Qwen/Qwen3-0.6B` keeps the wire identity constant, so `estate.model`, the harness and every collected trace keep naming the same model across the sync. **The four legs are byte-identical** — the template, the generation-config pin, the tool and reasoning parsers, the context length — because they are what makes a trace collected after the sync comparable to one collected before.

Stop-then-start, not reload: vLLM at this pin has no in-place weight swap for a non-LoRA model (SIGTERM, up to 60 s, then SIGKILL), and the stop is also the drain point between collection phases. It refuses a directory without `config.json` and waits up to 600 s for `/health`.

### `serve-llama31.sh` + `model-llama31-8b.env` — the second family

Llama-3.1-8B-Instruct through the `unsloth` mirror (the origin repository is gated; the mirror carries Meta's weights and Meta's full chat template), revision pinned in `model-llama31-8b.env`. Same shape as `serve.sh` — port, GPU default, memory fraction, `--max-model-len 32768`, `--enforce-eager`, DEBUG request logging, the pidfile and tunnel discipline, the pre-existing `~/gsj-vllm` venv — with the family's own four legs, each enumerated in the script header:

| Leg | Qwen3-0.6B (`serve 0.6b`) | Llama-3.1-8B (`serve llama31`) |
| --- | --- | --- |
| Model | `Qwen/Qwen3-0.6B` @ `c1899de2…` | `unsloth/Meta-Llama-3.1-8B-Instruct` @ `a2856192…` |
| Chat template | `--chat-template ~/gsj-vllm/qwen3_training.jinja` | no flag: the snapshot's own **embedded** template; the script records its sha256 and the tokenizer's blob hash from the snapshot actually served, because mirrors ship different templates |
| Tool-call parser | `--tool-call-parser hermes` | `--tool-call-parser llama3_json` — Llama's own JSON dialect; under `hermes` every call stays unparsed text |
| Qwen-only flags | `--reasoning-parser qwen3`, `--default-chat-template-kwargs '{"enable_thinking": false}'` | neither — `enable_thinking` is unused context on a Llama template, a measured wire no-op |
| Generation config | `~/gsj-vllm/genconfig` | `~/gsj-vllm/genconfig-llama31`, byte-copied from the snapshot (temperature 0.6, top-p 0.9, eos `[128001, 128008, 128009]`) |
| State | `run/vllm.{pid,log}`; `serving/run/gsj-vllm/` | `run/vllm-llama31.{pid,log}`; `serving/run/gsj-vllm-llama31/` — refuses to start while the Qwen pidfile is alive: one engine, one port |

`healthcheck.sh` sources `model-0.6b.env` by default; with the Llama engine up, run `GSJ_VLLM_MODEL_ENV=serving/model-llama31-8b.env ./estate.sh health`.

### `qwen3_training.jinja` — the adopted symmetric template

HuggingFace TRL's `trl/chat_templates/qwen3_training.jinja`, **byte-verbatim**: sha256 `1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`, upstream commit `63b7c3f547d3e06d0eae72712e36b7b64e9d5a45` (2026-07-16). Served through `--chat-template` — the file, not a per-request override — and `pins/pins.gsj.json` pins that sha256 as `chat_template_hash`.

Why this variant: its history branch always emits the think block, so consecutive pi prompts are strict token-prefix extensions of each other and Polar's prefix grouping merges them natively — no `generation_prompt_glue_ids` stitch, which is why that key is deliberately unset in `rollout.h200.yaml`. The proof was turn-1 byte-identity across templates and turn-2 strict prefix extension; the `{% generation %}` markers are accepted by the vLLM 0.26.0 renderer the estate serves.

## The trainer side — what the estate did not already provide

| Need | How | Delta vs the collection estate |
| --- | --- | --- |
| slime v0.3.0 + Megatron + torch + Ray | the official `slimerl/slime:v0.3.0` image (24.4 GB pulled, ~55 GB on disk) | a second, entirely separate runtime; nothing in the estate's venvs is reused |
| The image, on this box | **`docker pull` fails**: dockerd's registry egress runs as root and the uid-scoped firewall (`lockdown.sh`) drops it. Fetch as uid 1000 with a static `skopeo` (`skopeo copy docker://… docker-archive:…`, needs a `~/.config/containers/policy.json`), then `docker load -i` | the estate's own images predate the lockdown or were built locally; this was the first image needed from a public registry |
| GPUs | serving on GPU 3, training on GPU 5 — **disjoint**, discovered free at run time | collection used one GPU; co-residency is answered by separation, not sharing |
| slime checkout + Megatron | slime: `git clone --branch v0.3.0` plus Polar's `scripts/patch/patch_slime_router_tokens.sh`, mounted into the container. Megatron: the **image's own** `/root/Megatron-LM` (`1dcf0dafa`, the Dockerfile's `MEGATRON_COMMIT`) — not a separate checkout. Polar's stated slime-v0.3.0-compatible pin `26.04-alpha.rc1` lacks `megatron.training.tokenizer` and dies at import; the recipe that ran is the examples repository's `slime_bridge/cp17_loop/train_one_step.sh` | the image supplies the heavy stack and the Megatron code; the slime checkout supplies the patched router |

The loop itself — collect, train one step, export, `serve-updated`, collect again — is documented in [Running a training loop](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/training-loop.md) and run from [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples).

## Where the full bring-up lives

The authoritative one-pass estate restore is the predecessor's [`gsj-envloader/staging/BRINGUP.md`](https://github.com/MHGanainy/gsj-envloader/blob/v0.8.0/staging/BRINGUP.md) (archived, tag `v0.8.0`; accurate as written). The predecessor is frozen: that document stays theirs, and this directory carries only what this repository's estate does differently, so the estate is reproducible from the committed tree plus that document. The references above — §1 Forgejo, §3 the vLLM venv and snapshot, §4 the self-forwards — are sections of it.

## If your checkout predates `estate/`

This tree used to live at the repository root (`forgejo/`, `mcp-service/`, `corpus/`, `staging/`). `git pull` moves the **tracked** files only — the ignored instance data stays at the old paths, and a `docker compose up` from the new location would mount an empty `./data` and start a **blank Forgejo**: it reads as data loss and is only a wrong mount. Before the first bring-up after pulling, from the checkout root:

```bash
mv forgejo/forgejo-data   estate/forgejo/forgejo-data   # the live instance
mv forgejo/.token*        estate/forgejo/               # API tokens, if present
mv mcp-service/data       estate/mcp-service/data       # clone cache + index
mv staging/serving/run    estate/serving/run            # endpoint.env, tunnel.pid
rmdir forgejo mcp-service staging/serving staging 2>/dev/null || true
```

Move anything else untracked you keep in the old directories (venvs, caches) the same way. The compose project names are set explicitly in both files (`gsj-envloader-staging`, `gsj-mcp-service`), so the running containers are not renamed out from under you; only the `./data` bind mounts needed the `mv`.

## Provenance

The development record is private; these are the references the body used to carry, kept here verbatim.

- This directory: created at CP-04′; grouped under `estate/` at CP-50 (until then `staging/README.md`, with the components at the repo root).
- The predecessor's `BRINGUP.md` staying theirs: law 3.
- The split-shaped v2 corpus tree: CP-14.
- `gsj-mcp-service:0.3.0`, the ChromaDB backend: CP-15.
- The `serve.sh` deltas: recorded in `docs/reports/CP-04prime.md`; the generation-config lesson (an unpinned engine samples at `T=1.0`): CP-09 F1.
- `serve-updated.sh`: CP-17. The four legs make a trace comparable to CP-09′'s; the stop is A-13's drain point.
- `serve-llama31.sh` and `model-llama31-8b.env`: CP-38, deltas recorded in `docs/reports/CP-38.md`; the embedded template measured prefix-extending offline at CP-37. The recipe was added to this README at CP-39 — CP-38 committed it without listing it here, which left the "reproducible from the committed tree" claim two files short (audit S9).
- The symmetric template: adopted at CP-04′ per the inherited DoD (charter §6) and ADR-0007's Direction A; the proof and the serve-path compatibility evidence are in `docs/reports/CP-04prime.md` Step 2; Polar's grouping is `prefix_merging.py:399`; `generation_prompt_glue_ids` left unset at CP-04′ Step 4 (ADR-0007 stands).
- `checks.zero_at_mask1_max_rate`: row 27's "a CUDA estate sets 0.0" measured false at CP-04′ attempt 4; the 0.25 default allowance is CP-10's.
- The networking facts: measured at CP-04′ (attempt 1 failed at the default bridge; attempt 2 404'd on `/v1/v1/…`); the hardened `--depth 1` clone is CP-11's; one `public_url` for both dialers is CP-03 finding 2.
- The trainer side: CP-17. The Megatron import failure is finding F-06 in the examples repository's register; single-GPU collection was CP-09′.
- Erratum (CP-39), kept as a plain note: until CP-39 the Megatron row instructed `git clone --branch 26.04-alpha.rc1` — the exact pin CP-17 itself measured broken (F-06: `ModuleNotFoundError: No module named 'megatron.training.tokenizer'`). The contradiction and the report contradicting it were written by the same commit (`a647359`, CP-17), and an estate restore from this table failed at import for as long as the row stood.
- The migration section: CP-50 moved this tree from the repo root to `estate/`.
