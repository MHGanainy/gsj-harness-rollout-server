[Documentation](../README.md) › Guides

# The estate

The rollout server runs the agent; it does not host what the agent needs. The inference engine, the git host with the case repositories, the retrieval service, the corpus loaded into both, and the Docker runtime that isolates each episode are the **estate** — operator-run, named in the `estate` and `runtime` sections of the one YAML, and replaced piece by piece in production. This page explains what the repository ships under `estate/` to stand a reference estate up, the `estate.sh` front door and every verb it has, the networking facts that cost an episode when they are forgotten, the two serving recipes and the flags that differ between model families, and why the served chat template is the symmetric one.

If you want to run the server against an estate that already exists, the [server quickstart](../getting-started/server-quickstart.md) is the shorter read. The corpus pipeline and the retrieval service each have their own page: [The corpus](corpus.md) and [The retrieval service](retrieval-service.md).

## What an estate is

Five pieces, each dialed by a different process, each named by a YAML key. The reference implementation in `estate/` is the estate the library was measured on — a shared Linux GPU host, referred to as the H200 throughout the tree — and it exists to stand a **test** estate up. Production brings its own counterpart to every row.

| Piece | What the server needs from it | Reference implementation in `estate/` | YAML keys |
| --- | --- | --- | --- |
| Inference engine | An OpenAI-compatible chat-completions endpoint serving `estate.model` under that exact `--served-model-name`, returning logprobs, behind a pinned chat template and a pinned generation config | vLLM, started by `serving/serve.sh` (Qwen3-0.6B) or `serving/serve-llama31.sh` (Llama-3.1-8B-Instruct) | `estate.serving_base_url`, `estate.model`, `polar.gateway.engine` |
| Git host | One repository per case, one `timestep-T` branch per timestep, cloneable from **inside** an episode container | Forgejo 16.0.2 from `forgejo/docker-compose.yml`, at a static container IP on the compose network `gsj-staging-net` | `estate.clone_url_for`, `runtime.network` |
| Retrieval service | The MCP server the agent's `mcp_gsj_*` tools call; it verifies the per-episode token and clamps every search to the token's timestep | `mcp-service/` — image `gsj-mcp-service:0.3.0`, `compose.yml`, `config.yaml` | `estate.mcp_url_base`, `estate.mcp_token_secret_env` |
| The corpus | The case dataset scaffolded into the git host and indexed by the retrieval service | `corpus/ingest_corpus.py` and the source tree `corpus/staging/` | — (the pipeline reads `corpus.yaml`) |
| Sandbox runtime | A container runtime with the harness image loaded, on a network from which the three services above are reachable | Docker; image `ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3` | `runtime.backend`, `runtime.image`, `runtime.network` |

The server's own processes — Polar's rollout API and gateway, and our receiver — are not the estate. They run beside it on the host and are the subject of the [server quickstart](../getting-started/server-quickstart.md).

## What `estate/` ships

```text
estate/
├── estate.sh                 # the front door: one verb per script, nothing reimplemented
├── README.md                 # the recipes: what THIS estate does differently from the full bring-up
├── rollout.h200.yaml         # the one YAML for the reference host, with the measured networking facts as comments
├── forgejo/
│   ├── docker-compose.yml    # Forgejo 16.0.2, static IP 172.28.9.10 on gsj-staging-net, no published ports
│   ├── up.sh                 # compose up, health wait, admin user, API token — idempotent
│   ├── create_owner.sh       # a pipeline owner user + its push token
│   └── down.sh               # compose down; --wipe deletes instance data and the token
├── mcp-service/              # the retrieval service: Dockerfile, compose.yml, config.yaml, package, tests
├── corpus/
│   ├── ingest_corpus.py      # validate → scaffold → ingest → taskbank → verify (also shipped in the wheel)
│   └── staging/              # the source tree the reference estate is built from (corpus.yaml, cases, the lock)
└── serving/
    ├── serve.sh              # vLLM serving Qwen/Qwen3-0.6B under the symmetric template
    ├── serve-llama31.sh      # vLLM serving Llama-3.1-8B-Instruct under its embedded template
    ├── serve-updated.sh      # vLLM serving a trainer's HF-format export as Qwen/Qwen3-0.6B
    ├── healthcheck.sh        # /health, /v1/models, one full tool round trip
    ├── model-0.6b.env        # GSJ_MODEL_ID + GSJ_MODEL_REVISION for the reference family
    ├── model-llama31-8b.env  # the same two values for the second family
    └── qwen3_training.jinja  # the symmetric chat template, byte-verbatim from TRL
```

Four paths under `estate/` are written at run time and never committed: `forgejo/forgejo-data/` (the live Forgejo instance), `forgejo/.token*` (API tokens, mode 0600), `mcp-service/data/` (the service's clone cache and index) and `serving/run/` (`endpoint.env` and the tunnel's pid file per engine; the engine's own pid and log live on the serving host). They survive `git pull`; `estate.sh down --wipe` deletes the first two — `forgejo-data/` and `.token`, not the owner tokens — and leaves the rest.

> [!NOTE]
> **Where the full bring-up lives**
>
> These scripts **start** services; they do not install them. The Python venv with vLLM, the model snapshot, Docker itself and the host's firewall conventions are provisioned once by the one-pass restore in the archived predecessor repository, `gsj-envloader` (tag `v0.8.0`), file `staging/BRINGUP.md`. `estate/README.md` deliberately carries only the deltas against that document, so it is not reproduced here either. A bring-up from an empty machine is the job of the companion repository `gsj-rollout-demo` and its `bootstrap.py`.

## `estate.sh`, the front door

`estate.sh` is thin by design: every verb `exec`s an existing script or compose file in place, so each script keeps its home and its relative files keep resolving — `serve.sh` sources its sibling `model-*.env` and ships its own jinja, `up.sh` changes into its compose directory. The script `cd`s to `estate/` first, so it can be invoked from anywhere. An unknown verb, a missing argument or a missing tool exits 1 with a one-line reason; `--help` prints the verb table.

| Verb | What it runs | What it needs |
| --- | --- | --- |
| `up` | `forgejo/up.sh`: `docker compose up -d`, waits up to 90 s for `/api/healthz`, creates the admin user `gsj-admin` if absent, mints an API token into `forgejo/.token` if the existing one no longer works | `docker` |
| `owner <name>` | `forgejo/create_owner.sh <name>`: creates the pipeline owner user if absent and a push token into `forgejo/.token-<name>`; prints the `export GSJ_FORGEJO_TOKEN_<NAME>=…` line the pipeline needs | Forgejo up |
| `down [--wipe]` | `forgejo/down.sh`: `docker compose down --remove-orphans`; with `--wipe` also deletes `forgejo-data/` and `.token` | — |
| `mcp-up` | `docker compose -f mcp-service/compose.yml up -d`: the service runs `network_mode: host` on `0.0.0.0:8790`, as `user: 1000:1000`, with its clone cache and index under `mcp-service/data/` | `docker`; the image `gsj-mcp-service:0.3.0` already loaded (shipped by `docker save \| ssh … docker load` on a host whose daemon cannot pull); `GSJ_MCP_TOKEN_SECRET` exported — the verb refuses before compose does, and the value never lands in a file |
| `mcp-down` | `docker compose -f mcp-service/compose.yml down` | `docker` |
| `serve <0.6b\|llama31>` | `serving/serve.sh` or `serving/serve-llama31.sh` | the serving host's venv and model snapshot already provisioned; one engine per port |
| `serve-updated <dir>` | `serving/serve-updated.sh <dir>` | an HF-format export directory on the serving host |
| `health` | `serving/healthcheck.sh` | a served endpoint (`serving/run/<dir>/endpoint.env`) |
| `status` | `docker compose ps` for Forgejo and for the retrieval service, then `serving/healthcheck.sh` | `docker` |

There is no corpus verb: loading the corpus is the pipeline tool's job, and it sits between `owner` and `mcp-up` in the order below.

![The bring-up order as a numbered strip — up, owner, scaffold, mcp-up, ingest, serve, health — each step above a tile naming what it stands up and what it needs, with the on-demand verbs serve-updated, status, down and mcp-down in a row below](../img/estate-bringup.png)

<sub>Seven numbered steps, one tile each: what the step stands up and the prerequisite it checks or assumes. Steps 3 and 5 are the corpus pipeline, not `estate.sh` verbs; the on-demand row below holds the update, probe and teardown verbs.</sub>

The whole sequence, from the repository checkout on the estate host:

```bash
cd estate

./estate.sh up                                   # Forgejo at http://172.28.9.10:3000, admin + token
./estate.sh owner gsj-staging                    # the corpus owner named in corpus/staging/corpus.yaml
export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat forgejo/.token-gsj-staging)"
export GSJ_MCP_TOKEN_SECRET='<the shared secret>'

python3 corpus/ingest_corpus.py scaffold --corpus corpus/staging   # deterministic case repos, pushed
./estate.sh mcp-up                                                # the retrieval service, cold start indexes
python3 corpus/ingest_corpus.py ingest   --corpus corpus/staging   # trigger the reindex, wait for ready

./estate.sh serve 0.6b                           # vLLM on the serving host, tunnel on 127.0.0.1:8100
./estate.sh health                               # /health, /v1/models, one tool round trip
./estate.sh status                               # compose ps × 2 + the engine probe
```

`ingest_corpus.py all` runs `validate → scaffold → ingest → taskbank → verify` in order and stops at the first failure; only `taskbank` needs `pyarrow`. The owner token's variable name is derived from the owner: uppercase, `-` becomes `_`. The full pipeline is on [The corpus](corpus.md).

> [!TIP]
> **Every verb is idempotent where it can be**
>
> `up` re-run against a healthy instance creates nothing and reports the existing token valid; `serve` re-run against a healthy engine writes `endpoint.env` and exits 0 with "already serving"; `owner` keeps an existing user and a still-valid token. `down` keeps the instance data unless you say `--wipe`, and after a wipe `up` + `owner` + `scaffold` reproduce byte-identical repositories because the corpus commits carry a fixed identity and date.

## The networking facts

`rollout.h200.yaml` encodes four facts measured on the reference host. They are worth understanding on any host, because the first one fails every episode when it is wrong and the others fail in ways that look like something else.

![One tile per process on the reference estate's two networks: on the host, vLLM and the Polar rollout API bound to 127.0.0.1 and the Polar gateway and retrieval service bound to 0.0.0.0; on the compose network gsj-staging-net, the episode container reaching Forgejo by clone_url_for and the host services through 172.28.9.1; below, a red strip where an episode on the default bridge is lost at git setup](../img/estate-topology.png)

<sub>Which process listens where, and the YAML key on each arrow; 172.28.9.1 is the host itself as seen from inside the compose network, and an episode started on the default bridge never reaches Forgejo.</sub>

Two processes share the `127.0.0.1` column with the engine and the rollout API without a tile of their own: the trainer (`gsj-rollout submit`, or a loop over `RolloutClient`) submits and polls the rollout API on `127.0.0.1:8080`, and our receiver listens on `127.0.0.1:8300` for the terminal `TaskResult` the rollout API posts to `callback_url`. Every non-container process on the reference host — the engine, both Polar processes, the receiver, the submission — runs as one uid (1000), and the host's firewall is scoped to that uid, which is what breaks the root-originated legs of Docker's port publishing and registry pulls.

**The clone happens inside the sandbox.** Our harness runs `git clone --depth 1 --branch timestep-T` from within the episode container, so `estate.clone_url_for` must resolve from *there*, not merely from the host. On the reference host, published ports do not work at all (the host's uid-scoped firewall drops the root-originated leg of Docker's port proxy), so Forgejo publishes nothing and lives at the static container IP `172.28.9.10:3000` on the compose network `gsj-staging-net`. Docker isolates its networks from each other: a container started on the default bridge cannot reach that address. The cure is one config value, `runtime.network: gsj-staging-net`, which starts every episode container on the same network as Forgejo.

> [!WARNING]
> **The value that costs an episode when it is forgotten**
>
> With `runtime.network` unset or wrong, the container starts, the scheduler consumes the attempt, and the episode dies at its `git` setup step with `PiHarness setup failed`. Nothing on the host side looks broken. Check `runtime.network` first whenever every episode fails at setup.

**`host.docker.internal` never resolves in an episode.** Polar's Docker runtime passes only `--network` when it starts a container; it never passes `--add-host`, so on a Linux host the name does not exist inside the sandbox. Host-bound services — the retrieval service on `0.0.0.0:8790`, the Polar gateway on `0.0.0.0:8200` — are therefore addressed by the compose network's **gateway IP**, `172.28.9.1`, which is the host as seen from inside that network. (`172.17.0.1` also answers from there, but it names the default bridge's interface; do not use it.) This is why `estate.mcp_url_base` is `http://172.28.9.1:8790` and why both services bind `0.0.0.0` rather than loopback.

**The engine is host-local.** vLLM listens on `127.0.0.1:8000` and only the gateway process dials it, from the host, so `estate.serving_base_url` is `http://127.0.0.1:8000` and no bridge forward is needed. Two details ride along: the value carries **no `/v1` suffix**, because Polar's capture proxy appends `/v1/chat/completions` itself (a suffixed value requests `/v1/v1/…` and gets a 404 — the loader rejects it for that reason); and port `8100` on the host stays free for the serving scripts' tunnel convention described below.

**One `public_url` serves two dialers.** The rollout API dispatches sessions to `polar.gateway.public_url` from the host, and pi inside the container sends its model calls to the same URL plus `/v1`. `172.28.9.1` is reachable from both places, so `http://172.28.9.1:8200` does both jobs; `localhost` would do neither. Its port must equal `polar.gateway.port`, and the loader checks that too.

| Key | Reference value | Reachable from |
| --- | --- | --- |
| `estate.clone_url_for` | `http://172.28.9.10:3000/gsj-staging/{case_id}.git` | inside the episode container (on `gsj-staging-net`) |
| `estate.mcp_url_base` | `http://172.28.9.1:8790` | inside the episode container, via the network's gateway IP |
| `estate.serving_base_url` | `http://127.0.0.1:8000` | the gateway process, on the host |
| `polar.gateway.public_url` | `http://172.28.9.1:8200` | the rollout API on the host **and** pi in the container |
| `polar.rollout` | `127.0.0.1:8080` | a same-host trainer |
| `receiver` | `127.0.0.1:8300` | the rollout API, on the host |
| `runtime.network` | `gsj-staging-net` | — (the network episodes are started on) |

The full key reference, with the validators behind each rejection, is on [Configuration](configuration.md).

## Serving

### What `serve.sh` does

The serving scripts are written to run from an operator workstation that has an SSH alias to the serving host (`h200-admin` by default); every remote step is delivered as `bash -s` over that connection, and nothing is installed. In order, `serve.sh`:

1. Probes `http://127.0.0.1:8100/v1/models` through the local tunnel. If the pinned model is already listed it rewrites `endpoint.env` and exits 0.
2. Copies `model-0.6b.env` and `qwen3_training.jinja` to `~/gsj-vllm/` on the serving host.
3. On the host: requires `~/gsj-vllm/venv/bin/vllm` to exist (it errors with a pointer to the provisioning document otherwise), resolves the pinned snapshot with `huggingface_hub.snapshot_download(model, revision=…)`, and byte-copies the snapshot's `generation_config.json` into `~/gsj-vllm/genconfig/`, printing its sha256.
4. Starts `vllm serve` under `nohup` unless `run/vllm.pid` is alive, on GPU 3 by default, logging to `run/vllm.log`.
5. Opens `ssh -N -L 127.0.0.1:8100:127.0.0.1:8000` if no tunnel pid is alive, then polls `/health` for up to 900 s (the first start includes the weight load), verifies `/v1/models` lists `GSJ_MODEL_ID`, and writes `serving/run/gsj-vllm/endpoint.env` with `GSJ_VLLM_URL` and the remote log path.

Every host-bound value is an environment override:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSJ_VLLM_SSH_HOST` | `h200-admin` | the SSH alias of the serving host |
| `GSJ_VLLM_PORT` | `8000` | the engine's port on the serving host (`--port`, bound to `127.0.0.1`) |
| `GSJ_VLLM_LOCAL_PORT` | `8100` | the workstation end of the tunnel |
| `GSJ_VLLM_GPU` | `3` | `CUDA_VISIBLE_DEVICES` for the engine |
| `GSJ_VLLM_REMOTE_DIR` | `gsj-vllm` | the directory under the serving host's home holding the venv, the run state and the pinned files |
| `GSJ_VLLM_GPU_FRAC` | `0.30` | `--gpu-memory-utilization` |
| `GSJ_VLLM_MODEL_ENV` | `model-0.6b.env` (`model-llama31-8b.env` for `serve-llama31.sh`) | the file that sets `GSJ_MODEL_ID` and `GSJ_MODEL_REVISION` |

> [!NOTE]
> **The generation config is pinned on purpose**
>
> pi sends no sampling parameters with its requests, so the engine's generation defaults *are* the sampling policy. An engine started without `--generation-config` samples at whatever its defaults happen to be, silently. Both serving scripts copy the snapshot's own `generation_config.json` at serve time and pass the directory explicitly, so the pin is visible in the argv of the running process.

### The two model families

`serve 0.6b` and `serve llama31` share the same shape — the same host, port, GPU default, memory fraction, tunnel and pidfile discipline, `--max-model-len 32768`, `--enable-auto-tool-choice`, `--enable-log-requests`, `--enforce-eager`, and the environment `VLLM_ATTENTION_BACKEND=FLASH_ATTN VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_LOGGING_LEVEL=DEBUG`. Four flags are decided per family:

| | Qwen3-0.6B — `serve 0.6b` | Llama-3.1-8B-Instruct — `serve llama31` |
| --- | --- | --- |
| Model and revision | `Qwen/Qwen3-0.6B` @ `c1899de2…` (`model-0.6b.env`) | `unsloth/Meta-Llama-3.1-8B-Instruct` @ `a2856192…` (`model-llama31-8b.env`; the origin repository is gated, the mirror carries Meta's weights and template) |
| Chat template | `--chat-template ~/gsj-vllm/qwen3_training.jinja` — the symmetric file below | no flag: the snapshot's own embedded template. The script prints its sha256 and the tokenizer's blob hash from the snapshot actually served, because mirrors of this model ship different templates |
| Tool-call parser | `--tool-call-parser hermes` | `--tool-call-parser llama3_json` — Llama emits tool calls in its own JSON dialect; under `hermes` every call would stay unparsed text |
| Reasoning flags | `--reasoning-parser qwen3` and `--default-chat-template-kwargs '{"enable_thinking": false}'` | neither — both are Qwen legs; `enable_thinking` is unused context on a Llama template |
| Generation config | `--generation-config ~/gsj-vllm/genconfig` | `--generation-config ~/gsj-vllm/genconfig-llama31` (temperature 0.6, top-p 0.9, three EOS ids, byte-copied from the snapshot) |
| State | `run/vllm.{pid,log}` on the host; `serving/run/gsj-vllm/` locally | `run/vllm-llama31.{pid,log}`; `serving/run/gsj-vllm-llama31/` locally. Refuses to start while the Qwen pidfile is alive: one engine, one port |

> [!NOTE]
> **`health` checks the Qwen pin unless told otherwise**
>
> `healthcheck.sh` sources `model-0.6b.env` by default and asserts that `/v1/models` lists *that* model. With the Llama engine up, run it as `GSJ_VLLM_MODEL_ENV=serving/model-llama31-8b.env ./estate.sh health`; the tunnel port is the same for both families, so nothing else changes.

Switching the server to the second family is a YAML change, not a code change: `estate.model` must equal the served name byte for byte, and `builder.end_of_turn_token_id` must be re-derived against the served tokenizer (the default `151645` is `<|im_end|>` under Qwen3's). The pins document the repository ships is derived against the Qwen reference — see [Pins and approved sets](../concepts/pins.md) for what is verified per trace and what is verified once at bring-up by `pins/derive_pins.py`.

### `serve-updated <dir>` — the weight-sync half

`serve-updated.sh` is `serve.sh` with exactly two differences: the model argument is a **local HF-format directory** on the serving host (a trainer's export, so there is no `--revision`), and `--served-model-name Qwen/Qwen3-0.6B` keeps the wire identity constant, so `estate.model`, the harness and every collected trace keep naming the same model across the sync. Everything else in the argv — the symmetric template, the generation-config pin, the tool and reasoning parsers, the context length — is byte-identical, because those are what make a trace collected after the sync comparable to one collected before.

It stops the running engine first (SIGTERM, up to 60 s, then SIGKILL) and only then starts the new one: vLLM at this pin has no in-place weight swap for a non-LoRA model, and the stop is also the natural drain point between collection phases. It refuses a directory without `config.json`, waits up to 600 s for `/health` on the serving host, and checks `/v1/models` lists the served name. Because it is invoked with a directory that already exists on the serving host, the trainer's export has to land there first; how it gets there is the trainer's business ([Running a training loop](training-loop.md)).

## The symmetric chat template

`serving/qwen3_training.jinja` is HuggingFace TRL's `trl/chat_templates/qwen3_training.jinja`, byte-verbatim (sha256 `1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`). It is served as a file through `--chat-template`, not as a per-request override, and that hash is the `chat_template_hash` pinned in `pins/pins.gsj.json`.

Why a training variant of the template rather than the one embedded in the snapshot: pi sends one chat-completions request per turn, each carrying the whole conversation so far, and Polar reconstructs a trajectory from those requests by **prefix merging** — consecutive requests are merged into one token sequence only when each prompt is a strict token-prefix extension of the previous prompt plus its completion. The stock Qwen3 template breaks that property: when it re-renders history it strips the `<think>…</think>` block from every assistant turn except the last, so the bytes of turn *N* as re-rendered inside turn *N+1*'s prompt are not the bytes the engine produced at turn *N*. TRL's variant removes that conditional and always emits the think block. With thinking off, the generation prompt ends in `<think>\n\n</think>\n\n`, and the history re-render emits exactly the same bytes in the same place — the template is symmetric between generation and re-rendering, so every prompt extends the previous one and Polar's grouping merges natively.

The consequence in the YAML is an absence: `builder.generation_prompt_glue_ids` is deliberately unset. The stitch it configures exists for asymmetric templates and stays dormant on this estate. The template's `{% generation %}` markers are accepted by the vLLM renderer the estate serves; they are inert at serve time and exist for assistant-only loss masking in offline SFT.

> [!WARNING]
> **Change the template, and the traces change**
>
> The served template determines the prompt bytes, the tokenizer determines their ids, and the pins record both identities. Serving a different template file — or the same model from a mirror whose embedded template differs — is a new estate as far as the pins are concerned; re-derive them before collecting. The Llama recipe needs no file because Meta's full template already re-renders history as a prefix extension, which was measured offline before that family was added; the serve script prints the hash of the template it actually served so the identity is on record.

## Production brings its own

Nothing in `estate/` is a dependency of `gsj_rollout/`. The server reads the estate only through the YAML values, and every reference piece has a counterpart in a production deployment:

| Reference piece | What production replaces it with | What must still hold |
| --- | --- | --- |
| Forgejo at a static container IP | Any git host with one repository per case and `timestep-T` branches | Cloneable from inside the sandbox network; the URL template goes in `clone_url_for` |
| `gsj-staging-net` | Whatever network the sandbox runtime starts containers on | Episodes and the git host on a network with a route between them; `runtime.network` names it |
| The retrieval service on `network_mode: host` | The same service, deployed however you deploy services | Reachable from the sandbox; shares one `GSJ_MCP_TOKEN_SECRET` with the gateway process |
| vLLM on `127.0.0.1:8000` | Any OpenAI-compatible engine that returns logprobs | Serves `estate.model` under that served name, a pinned template and a pinned generation config; the gateway must reach it |
| `serve.sh` over SSH | Your process supervisor | The four per-family flags stay decided and visible |
| Docker on one host | A runtime Polar can drive with start/stop/exec/upload/download | `runtime.backend` is a value; nothing in `gsj_rollout/` assumes Docker semantics |

Two things do not move with the estate: the pins document, which describes the estate the traces came from and must be re-derived on a new one (`GSJ_PINS_PATH` points both the receiver and the trainer at it), and the `checks.py` gates, which are the same code on both sides of the wire. The normative statement of the split is the charter's scope law: [docs/CHARTER.md](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md).

## See also

- [Server quickstart](../getting-started/server-quickstart.md) — the YAML, `gsj-rollout serve`, the two Polar processes, the first trace.
- [The corpus](corpus.md) — the source tree contract and the pipeline's five phases.
- [The retrieval service](retrieval-service.md) — the token, the cutoff, the index.
- [Configuration](configuration.md) — every key with its default and its validator.
- [Troubleshooting](troubleshooting.md) — the messages behind this page's warnings.
