[Documentation](../README.md) › Getting started

# Server quickstart

This page brings the server side up on a host that already runs an estate, and collects a first trace. You will write the one YAML, run `gsj-rollout serve`, start the two Polar processes it prints, submit a task from the same host, and find the accepted and quarantined traces on disk. The worked example is the repository's own H200 estate file, `estate/rollout.h200.yaml`.

If you only want to *call* a server someone else operates, you are on the wrong page: read the [trainer quickstart](trainer-quickstart.md) instead.

## Prerequisites

The server role needs an estate and a repository checkout. Nothing here comes from the PyPI wheel — the wheel ships `gsj_rollout/`, the pins sets and the corpus tool, but not the vendored Polar that runs episodes.

| You need | What it is | How to check it is there |
| --- | --- | --- |
| An inference engine | vLLM serving `estate.model` under that exact `--served-model-name`, at `estate.serving_base_url` (the engine root, no `/v1`) | `estate/estate.sh health` — probes `/health`, `/v1/models` and a full tool round trip |
| A Forgejo git host with the case repos | One repository per case, one `timestep-T` branch per timestep, reachable from **inside** episode containers | `curl -fsS http://172.28.9.10:3000/api/healthz` on the H200; `estate/estate.sh status` |
| The retrieval service | The token-scoped MCP search service the agent's `mcp_gsj_*` tools call; needs `GSJ_MCP_TOKEN_SECRET` in its environment | `curl -s localhost:8790/health` until it reports `"state": "ready"` |
| The corpus ingested | The case dataset scaffolded into Forgejo and indexed by the retrieval service | `python3 estate/corpus/ingest_corpus.py validate --corpus estate/corpus/staging` |
| Docker | `runtime.backend: docker` is the default; the harness image must be pullable or already loaded | `docker image ls ghcr.io/mhganainy/gsj-pi-harness` |
| A checkout of this repository | With a venv holding `gsj_rollout` and Polar's own venv built at `vendor/polar/.venv` | `vendor/polar/.venv/bin/polar --help` |

Bringing those up is covered in [The estate](../guides/estate.md), [The corpus](../guides/corpus.md) and [The retrieval service](../guides/retrieval-service.md). The checkout and both venvs are covered in [Installation](installation.md); the Polar venv recipe is `vendor/REVENDOR.md` in the repository, and its `uv pip install -p .venv/bin/python -e ../..` step is not optional — Polar's process loads our harness and our builder by import path, so `gsj_rollout` must be importable there.

> [!NOTE]
> **Everything runs on one host in this quickstart**
>
> The H200 file assumes the Polar processes, the receiver and the submission all run on the estate host as the same user. A trainer on another machine changes only `polar.rollout` (see [Configuration](../guides/configuration.md)); nothing else on this page moves.

## The YAML

One file configures both audiences: `gsj-rollout serve` renders the receiver and Polar's topology from it, and `gsj-rollout submit` renders the task request from the same file. Six values have no default and must come from your estate — `estate.clone_url_for`, `estate.mcp_url_base`, `estate.serving_base_url`, `estate.model`, `polar.gateway.public_url` and `receiver.traces_dir`. Everything else defaults to the measured reference values.

Here is `estate/rollout.h200.yaml` with its explanatory comments trimmed (the checked-in file carries them in full):

```yaml
estate:
  clone_url_for: "http://172.28.9.10:3000/gsj-staging/{case_id}.git"
  mcp_url_base: "http://172.28.9.1:8790"
  mcp_token_secret_env: GSJ_MCP_TOKEN_SECRET
  serving_base_url: "http://127.0.0.1:8000"     # NO /v1 suffix
  provider: gsj
  model: Qwen/Qwen3-0.6B

runtime:
  backend: docker
  image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3
  network: gsj-staging-net

harness:
  tools_allowlist:
    [read, ls, grep, find, write, edit, bash,
     mcp_gsj_search_case, mcp_gsj_search_decisions,
     mcp_gsj_case_status, mcp_gsj_decision_stats]
  artifacts_dir: /home/sysadmin/cp04prime/artifacts
  workdir: /workspace
  context_window: 32768
  max_tokens: 8192
  thinking: "off"

builder:
  strategy: gsj_rollout.builder:ValidatingPrefixMergingBuilder
  end_of_turn_token_id: 151645   # <|im_end|> under the served tokenizer

checks:
  zero_at_mask1_max_rate: 0.25

polar:
  rollout:
    host: 127.0.0.1
    port: 8080
  gateway:
    id: gsj-node-01
    host: 0.0.0.0
    port: 8200
    public_url: "http://172.28.9.1:8200"
    engine: vllm

receiver:
  host: 127.0.0.1
  port: 8300
  traces_dir: /home/sysadmin/cp04prime/traces
```

### The networking values, in plain words

The file's comments record facts measured on that host, and the rule behind all of them is *who dials the value*: `clone_url_for` and `mcp_url_base` are dialed from inside the episode container (so they must resolve on `runtime.network`, and `host.docker.internal` does not exist there), `serving_base_url` only from the gateway process on the host (no `/v1` suffix), and `polar.gateway.public_url` from both the rollout API and pi inside the container (so never `localhost`, and its port must equal `polar.gateway.port`). Each value, its reference setting and why it is what it is are explained on [The estate](../guides/estate.md#the-networking-facts).

> [!WARNING]
> **The value that costs an episode when it is wrong**
>
> The clone happens inside the sandbox. If `clone_url_for` is only reachable from the host, or `runtime.network` leaves episodes on the default bridge, every episode fails at setup with a loud `PiHarness setup failed` on the `git` step — after the container was started and the scheduler consumed the attempt.

Loading is strict: an unknown key anywhere is an error naming the section and key, and a section reduced to comments is normalised to `{}` so the error names the missing field (`'polar.gateway.public_url': Field required`) rather than the section. The full key reference is in [Configuration](../guides/configuration.md).

## Run `serve`

From the checkout, with the venv that holds `gsj_rollout` active:

```bash
gsj-rollout serve --config estate/rollout.h200.yaml
```

![The four steps of gsj-rollout serve: load and validate the YAML, render topology.rendered.yaml, print the two Polar commands, start the receiver and block](../img/serve-startup.png)

<sub>`serve` validates, renders, prints, then runs only our receiver; with `--render-only` it returns after printing.</sub>

In order, `serve`:

1. **Loads and validates the YAML.** An invalid file is one message on stderr and exit code 2.
2. **Renders `topology.rendered.yaml`** next to the YAML — for the example, `estate/topology.rendered.yaml`. This is Polar's own `topology.yaml`, generated from your config on every run. Never hand-edit it; edit the YAML and re-run.
3. **Prints the two Polar commands** for you to run, then one line with the callback URL, the traces directory and the quarantine directory.
4. **Starts our receiver** — an HTTP endpoint at `receiver.host:port` that validates every callback body and lands it — and blocks until SIGINT or SIGTERM.

`serve` is not a process supervisor: it starts nothing but the receiver. The output for the example looks like this (absolute paths shortened):

```text
topology rendered: <checkout>/estate/topology.rendered.yaml — run Polar's two processes yourself:
  PYTHONPATH=<checkout> <checkout>/vendor/polar/.venv/bin/polar serve_rollout -c <checkout>/estate/topology.rendered.yaml
  GSJ_MCP_TOKEN_SECRET=<secret> PYTHONPATH=<checkout> <checkout>/vendor/polar/.venv/bin/polar serve_gateway -c <checkout>/estate/topology.rendered.yaml
callbacks: http://127.0.0.1:8300/callbacks/session_result | traces -> /home/sysadmin/cp04prime/traces | quarantine -> /home/sysadmin/cp04prime/traces/quarantine
receiver listening on 127.0.0.1:8300
```

The rendered topology for the example is short enough to read whole; note that `model_served` and `inference.base_url` come from the `estate` section, and the node's `public_url` is passed through unchanged:

```yaml
rollout:
  host: 127.0.0.1
  port: 8080
gateway:
  heartbeat_interval_seconds: 30
  nodes:
  - id: gsj-node-01
    host: 0.0.0.0
    port: 8200
    public_url: http://172.28.9.1:8200
    model_served: Qwen/Qwen3-0.6B
    inference:
      engine: vllm
      base_url: http://127.0.0.1:8000
    max_init_workers: 4
    max_run_workers: 2
    max_postrun_workers: 4
```

> [!TIP]
> **`--render-only`**
>
> `gsj-rollout serve --config … --render-only` performs steps 1–3 and exits 0 without listening. Use it to check a config edit, or to regenerate the topology while a receiver is already running elsewhere.

> [!NOTE]
> **Running from an installed wheel**
>
> If `vendor/polar/.venv/bin/polar` does not exist, `serve` says so on a `NOTE:` line and prints the commands with a `<checkout>` placeholder instead of a path. A pip install ships no `vendor/`; clone the repository and build Polar's venv per `vendor/REVENDOR.md`, then substitute the checkout path.

## Run the two Polar processes

Start them in two more shells, in this order, using the lines `serve` printed. The gateway registers with the rollout API when it starts, so the rollout API goes first.

```bash
# shell 2 — the rollout API: task queue, scheduler, dispatch, the callback to our receiver
PYTHONPATH=<checkout> <checkout>/vendor/polar/.venv/bin/polar serve_rollout -c <checkout>/estate/topology.rendered.yaml

# shell 3 — the gateway node: sandbox lifecycle, the capture proxy, result push
GSJ_MCP_TOKEN_SECRET=<secret> PYTHONPATH=<checkout> <checkout>/vendor/polar/.venv/bin/polar serve_gateway -c <checkout>/estate/topology.rendered.yaml
```

Two things about these lines are deliberate:

- **`GSJ_MCP_TOKEN_SECRET` goes on the gateway command only.** Our harness runs inside the gateway process and mints each episode's HS256 token there, host-side, with claims `{case_id, timestep, episode_id, exp}`. The secret is read from the environment variable named by `estate.mcp_token_secret_env`; if it is unset the episode fails immediately with `token secret env var 'GSJ_MCP_TOKEN_SECRET' is unset in the gateway process`. The same value must be the retrieval service's secret, or every retrieval call is refused with HTTP 401.
- **`PYTHONPATH=<checkout>`** makes `gsj_rollout` importable in Polar's process however its venv was built. Polar loads `gsj_rollout.pi_harness:PiHarness` and `gsj_rollout.builder:ValidatingPrefixMergingBuilder` by the import-path strings carried in every task request.

![The processes on the server host with their ports and URLs: vLLM engine, Forgejo, retrieval service, Polar rollout API, Polar gateway node, the receiver, and episode containers, with arrows for who dials whom](../img/server-processes.png)

<sub>Every process on the H200 host with the value that names it, and the direction of each connection.</sub>

Reading the arrows: the trainer talks only to the rollout API (`POST /rollout/task/submit`, then `GET /rollout/task/{task_id}` until terminal). The rollout API dispatches each session to the gateway at `public_url` and, when the task is terminal, POSTs the whole `TaskResult` to our receiver's `callback_url`. The gateway starts one container per session on `runtime.network`, execs the harness steps in it, proxies the container's model calls to the engine while capturing tokens and logprobs, and pushes each `SessionResult` back to the rollout API. Nothing dials into the container; it dials out to the gateway, to Forgejo and to the retrieval service.

## Submit a first task

From the same host, with all four processes up:

```bash
gsj-rollout submit --config estate/rollout.h200.yaml \
  --case case_0001 --timestep 12 \
  --prompt "Summarise the state of the case as of the latest page and list the open questions." \
  --out ./first-run
```

`--case` is the repository name substituted into `clone_url_for`; `--timestep` selects branch `timestep-12` and becomes the retrieval cutoff the token carries. `--prompt-file` takes the instruction from a file instead, and `--from-bank <parquet> [--row N]` submits a taskbank row (triple, prompt and split all from the row; needs `pyarrow`). The command submits, polls, and prints one line each time the count of terminal sessions changes:

```text
task gsj-task: 1/1 sessions terminal
collected 1/1 episodes -> ./first-run
length-terminated: 0/1 accepted episodes ended finish_reason=length — qualified by design; …
```

| Exit code | Meaning |
| --- | --- |
| 0 | every attempt was collected |
| 1 | not every attempt was collected — rejected, errored, or timed out (the command still wrote what it did collect) |
| 2 | config or usage error |
| 3 | the rollout API was unreachable or returned an HTTP error |

> [!NOTE]
> **`--episodes N` means N attempts**
>
> `--episodes` sets Polar's `num_samples`: N attempts are scheduled, not N accepted traces. A rejected trace is a consumed attempt, quarantined with its findings and never retried; exit code 1 tells you that collected is less than attempted. The default per-task timeout is 900 s plus a 120 s `--grace` for the callback.

The same submission from Python, for a loop that will replace the CLI later:

```python
from gsj_rollout import RolloutClient, load_config
from gsj_rollout.config import render_task_request

cfg = load_config("estate/rollout.h200.yaml")
request = render_task_request(
    cfg, task_id="first-run", instruction="Summarise the state of the case …",
    case_id="case_0001", timestep=12, episodes=1, timeout_seconds=900.0,
)
client = RolloutClient(cfg.polar.rollout.base_url)
task_id = client.submit(request)
results = client.wait(task_id, timeout_s=1020.0)   # the SessionResult bodies, unvalidated
traces = client.collect([request])                 # or: submit + wait + checks in one call
```

`wait()` returns the raw `SessionResult` bodies; `collect()` runs the same validators the receiver ran and returns only the `Trace`s of checks-clean sessions.

The [trainer quickstart](trainer-quickstart.md) continues from here; the [Python API](../reference/api.md) has the signatures.

## Where the traces land

Two copies of every accepted trace exist after a successful run, and they agree by construction — the receiver and the client run the same `checks.py`.

| Location | Written by | Contents |
| --- | --- | --- |
| `<traces_dir>/<session_id>.<pins_mode>.json` | the receiver, on the callback | the accepted `SessionResult`, verbatim |
| `<traces_dir>/quarantine/<session_id>.<pins_mode>.json` | the receiver, on the callback | `{"findings": [...], "session_result": …}` — the rejected result with the findings that rejected it |
| `<out>/<session_id>.json` | `submit --out`, after polling | each accepted `SessionResult`, re-validated client-side |
| `<artifacts_dir>/<session_id>/` | the gateway process, in the harness's post-run step | `pi_transcript.jsonl` and, if the agent wrote one, the `out/` deliverable |

`<pins_mode>` is the resolved pins file's declared mode (`thinking-off` unless you pointed `GSJ_PINS_PATH` at a thinking-on set), stamped so an archive that mixes modes across restarts stays attributable. Landing is atomic per callback: every result in the body is written to a `.tmp` and then renamed, or none is. Rejection is a validation decision, not a delivery failure — the receiver answers Polar `200 {"accepted": n, "rejected": m}` either way, and `GET http://127.0.0.1:8300/healthz` returns the running counts.

For the example config, accepted traces are in `/home/sysadmin/cp04prime/traces/` and rejected ones in `/home/sysadmin/cp04prime/traces/quarantine/` (the default; set `receiver.quarantine_dir` to move it). `harness.artifacts_dir` defaults to `/tmp/gsj-artifacts`, which is ephemeral — the example points it at durable storage, and so should you.

> [!WARNING]
> **Quarantine on a foreign estate**
>
> `checks.py` validates every trace against pinned approved sets — tool roster, system prompt, settings — and the repository ships **this** estate's pins. On any other estate every hash gate fails `*_not_approved` until you point `GSJ_PINS_PATH` at your own pins file, in the receiver's environment *and* the trainer's. If your first run lands entirely in `quarantine/`, read the `findings` list there before anything else. The rules are in [Validation](../concepts/validation.md) and [Pins and approved sets](../concepts/pins.md); the vocabulary is in [Finding vocabulary](../reference/findings.md).

## Stopping

Ctrl-C the `serve` shell. The receiver shuts down and prints its tallies:

```text
receiver stopped: accepted=1 rejected=0
```

The Polar processes are yours to stop separately, and so is the estate. Nothing in the receiver is lost by stopping it between runs: it holds no state beyond the files it already wrote.

## See also

- [The receiver](../guides/receiver.md) — the callback contract, the two accepted body shapes, the status codes.
- [Configuration](../guides/configuration.md) — every key, its default, and the validators that reject it.
- [Command line](../guides/cli.md) — `serve` and `submit` in full.
- [Running a training loop](../guides/training-loop.md) — collecting at scale from a trainer.
- [Troubleshooting](../guides/troubleshooting.md) — the failures this page's warnings point at, with their messages.
