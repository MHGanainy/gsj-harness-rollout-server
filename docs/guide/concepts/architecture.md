[Documentation](../README.md) › Concepts

# Architecture

This page explains how the pieces fit: the one rule that bounds the server, the split between our ~2,000-line shell and the ~14,200-line Polar layer it drives, what each of our eight modules does, what Polar provides and where we patched it, how one episode flows through as data, and why nothing in `gsj_rollout/` assumes Docker. Read it once before you configure a server or write a training loop against one.

## The scope law

The whole design follows from one sentence:

> The rollout server owns **task → sandbox → agent → trace**. Nothing else. If it stores, schedules, scores, weights, versions, or trains — it's out.

Given a task `(case, timestep, prompt)`, the server runs a pinned coding agent (pi 0.83.0) in an isolated sandbox where everything the agent can see is truncated at `timestep`, captures every token and logprob the model produced, and emits one validated trace. It does not keep the trace, compute a reward (every callback carries `reward: null`), manage weights, or train. Those belong to the trainer that calls it — see [Running a training loop](../guides/training-loop.md).

The corollary is that there are two roles, and they are easy to confuse on first contact:

| role | what it needs | what it uses |
| --- | --- | --- |
| **Server** | a machine you operate with an *estate*: an inference engine, a Forgejo git host, the retrieval service, the ingested corpus — plus this repository checked out and Polar's venv built | `gsj-rollout serve`, two Polar processes, `pi_harness.py`, `builder.py`, `receiver.py` |
| **Trainer** | `pip install gsj-harness-rollout-server` (Python ≥ 3.12; pydantic + httpx) — no estate, no Polar | `gsj_rollout.RolloutClient`, `gsj_rollout.checks` |

The published wheel is for the trainer role only. It contains `gsj_rollout/`, the two pins sets and `ingest_corpus.py`; it ships no `vendor/`, so it cannot run an episode by itself. See [Installation](../getting-started/installation.md).

## Our shell and the Polar layer

Episode execution and trajectory reconstruction are not ours. They come from NVIDIA's Polar ([`NVIDIA-NeMo/ProRL-Agent-Server`](https://github.com/NVIDIA-NeMo/ProRL-Agent-Server)), vendored by commit into `vendor/polar/` — Polar has no releases or tags, so the pin is a SHA recorded in `POLAR_SHA` (`f0e8343a…`, branch `stable`), with three carried patches. Our code is the thin shell that points Polar at our corpus, our retrieval service, our pinned agent, and our checks.

![The code map as three regions: our shell, eight pictogram tiles tagged TRAINER, BOTH or SERVER; the Polar layer beneath it, five package tiles chained rollout API, gateway, harness factory, runtime, trajectory; and the operator-run estate beside them, four tiles for the corpus, git host, retrieval service and inference engine. Solid arrows carry HTTP submit and poll, the TaskResult callback and runtime.backend downward; two dashed arrows, agent.import_path and builder.strategy, point up from Polar into pi_harness.py and builder.py](../img/component-map.png)

<sub>Our shell above the five Polar packages it drives, the estate beside them. Solid arrows are things we call or configure; the two dashed arrows are the only places Polar reaches into our code, and it does so by import-path string. Sizes are in the tables below: 1,999 lines of ours against ~14,200 vendored.</sub>

### Our eight modules

`gsj_rollout/` is 1,999 lines, held under a 2,000-line budget by design — a growth that pushes past it has to be justified, which keeps the shell a shell. Each module is tagged with the side that runs it.

| module | side | lines | what it does |
| --- | --- | --- | --- |
| `__init__.py` | TRAINER | 18 | The consumer surface: `RolloutClient`, `Trace`, `checks`, `load_config`, `RunConfig`. Importing `gsj_rollout` never imports `polar`; `pi_harness`, `builder`, `receiver` and `cli` are deliberately not exported. |
| `client.py` | TRAINER | 123 | Submit + collect. Polls `GET /rollout/task/{id}` (never the receiver's disk) and re-runs `checks.validate_session_result` on every result it fetches. |
| `checks.py` | BOTH | 528 | The trace validators — admission (`ADM`), the logprob discipline (`LP`), the tripwires (`TR`) and the gates `G1`–`G7`. One entry point, `validate_session_result`, returns byte-stable `{id}:{slug}[:detail]` findings; an empty list means accepted. Runs on the receiver *and* in the trainer — see [Validation](validation.md). |
| `config.py` | SERVER | 413 | The one YAML, two audiences: the server renders the receiver settings and Polar's `topology.yaml` from it; the trainer renders `TaskRequest` bodies from it. Unknown keys reject loudly. See [Configuration](../guides/configuration.md). |
| `cli.py` | SERVER | 241 | The `gsj-rollout` console script: `serve` renders the topology, prints the two Polar commands, and runs our receiver; `submit` submits, polls and collects. See [Command line](../guides/cli.md). |
| `receiver.py` | SERVER | 195 | The callback endpoint (`POST /callbacks/session_result`, stdlib HTTP). Validates each `SessionResult` and lands it verbatim under `traces/`, or with its findings under `quarantine/`. See [The receiver](../guides/receiver.md). |
| `pi_harness.py` | SERVER | 322 | Our pi as a Polar harness. Clones the case at branch `timestep-T`, mints the per-episode cutoff token, writes pi's config, runs pi, downloads the transcript and deliverable. |
| `builder.py` | SERVER | 159 | `ValidatingPrefixMergingBuilder`, a subclass of Polar's `PrefixMergingBuilder`. Runs the session-level checks the callback cannot carry and fails the trajectory closed with `status="ERROR"`. |

> [!NOTE]
> **Two of these live in Polar's process**
>
> `pi_harness.py` and `builder.py` import `polar`, which exists only in Polar's venv (`vendor/polar/.venv`). They are loaded *by Polar* — the gateway process — from the import-path strings in every `TaskRequest`; nothing else imports them. This is why `gsj_rollout` must be installed into Polar's venv on the server side and why the trainer wheel never needs Polar.

### What Polar provides

At the pin, Polar is ~14,200 lines of Python under `vendor/polar/src/polar/`. We drive four things:

- **The episode lifecycle** (`runtime/`, `gateway/`). Sandbox start/exec/upload/download/stop behind a runtime-agnostic interface, per-session async gateway workers with configurable init/run/post-run concurrency, heartbeats, timeouts, teardown. We wrote no lifecycle code: `pi_harness.py` is a contract (clone, mint token, render config, download artifacts), not machinery.
- **The capture proxy** (`gateway/`). pi's model calls go to the gateway, which rewrites each request to ask the engine for token ids and per-token logprobs, forwards it to the inference engine, and records request and response per completion against the session. pi's traffic is proxied unmodified — `messages` and `tools` reach the wire byte-identical — and the capture normalizers read vLLM, SGLang and OpenAI token-id dialects.
- **Prefix-merging reconstruction** (`trajectory/`). `PrefixMergingBuilder` groups a session's completions into chains by token-prefix extension and merges them into one trajectory, with no tokenizer anywhere in the builder: assistant tokens are the engine-sampled ids, never a re-rendering. The [Traces](traces.md) page shows what comes out.
- **The task API** (`rollout/`). `POST /rollout/task/submit`, scheduling across gateway nodes, `GET /rollout/task/{id}` for polling, and a push path: each finished `SessionResult` returns to the rollout server, which posts the terminal `TaskResult` envelope to the `callback_url` in the request.

| Polar package | lines | role |
| --- | --- | --- |
| `gateway/` | 6,463 | session nodes, the capture proxy, session storage, callback delivery |
| `trajectory/` | 1,875 | builders (`prefix_merging`, `per_request`), evaluators, the strategy registry |
| `rollout/` | 1,578 | the task API, manager, scheduler, dispatch pipeline |
| `platform/` | 1,470 | the dashboard server — not driven by this server |
| `agent/` | 1,373 | `BaseHarness`, eleven harness presets, the `import_path` factory |
| `runtime/` | 795 | `BaseRuntime`, `DockerRuntime`, `ApptainerRuntime`, the backend factory |

### The two seams

Polar reaches into our code at exactly two points, and both are strings in the `TaskRequest` that `config.render_task_request` builds from your YAML:

```yaml
# the defaults in config.py — you rarely set these
harness:
  import_path: gsj_rollout.pi_harness:PiHarness
builder:
  strategy: gsj_rollout.builder:ValidatingPrefixMergingBuilder
  end_of_turn_token_id: 151645       # pinned, never auto-detected
```

```python
from gsj_rollout import load_config
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")
request = render_task_request(cfg, task_id="demo", instruction="Summarise the case so far.",
                              case_id="case_0001", timestep=12)
request["agent"]["import_path"]    # 'gsj_rollout.pi_harness:PiHarness'
request["builder"]["strategy"]     # 'gsj_rollout.builder:ValidatingPrefixMergingBuilder'
request["callback_url"]            # 'http://127.0.0.1:8300/callbacks/session_result'
```

Polar's harness factory resolves `agent.import_path` to a `BaseHarness` subclass; its strategy registry resolves any `module:Class` string to a `BaseTrajectoryBuilder` subclass and instantiates it with `builder.config`. Neither required a vendored edit — the registry and the factory are upstream features — which is why the whole validation layer could be inserted without forking Polar.

### The estate

The third region of the map is not code the server runs but services it needs running. The repository ships a reference of each under `estate/`; production brings its own of each, named in the `estate` and `runtime` sections of the one YAML.

| `estate/` | what it is | who talks to it |
| --- | --- | --- |
| `corpus/` | `ingest_corpus.py` and the staging tree it builds from: one repository per case, a `timestep-T` branch per timestep, and the lock file that records what was ingested — see [The corpus](../guides/corpus.md) | the ingest, at bring-up |
| `forgejo/` | the git host holding the case repositories | `pi_harness.py` clones `timestep-T` from it, depth 1 |
| `mcp-service/` | the retrieval service; every request carries the episode's cutoff token, which it verifies before clamping results to page ≤ T — see [The retrieval service](../guides/retrieval-service.md) | pi, through its MCP tools |
| `serving/` | the vLLM serving recipes with the pinned chat template | the gateway's capture proxy forwards pi's model calls to it |

[The estate](../guides/estate.md) is the operator's page for all four.

## One episode, as data

Every hop in an episode is a payload or a file you can read. This is the same flow the [Trainer quickstart](../getting-started/trainer-quickstart.md) drives from the outside.

![One episode as an eight-step strip and a map beneath it: a TaskRequest document goes to the rollout API, which opens a gateway node whose runtime starts a sandbox; inside the sandbox, setup clones at T, pi runs, and postprocess collects artifacts; pi's model calls drop to the capture proxy, whose completions feed builder.build; a SessionResult document leaves the node and returns through the rollout API, which fans out to receiver.py on the callback leg and to the trainer's poll on the other](../img/episode-dataflow.png)

<sub>TaskRequest in, SessionResult out. The numbered badges match the eight steps below; the rollout API both posts the terminal envelope to our receiver and serves the trainer's poll, and both legs run the same checks.</sub>

1. **TaskRequest.** `render_task_request` produces one body for the triple: `instruction`, `num_samples`, `timeout_seconds`, `metadata {case_id, timestep, prompt_source}`, `runtime {backend, image, network}`, `agent {import_path, model_name, settings}`, `builder {strategy, config}` and `callback_url`. `metadata.timestep` is hoisted by Polar into every trace's top-level metadata, which is what gate G5 later reads (see [Validation](validation.md)).
2. **The rollout API schedules.** `POST /rollout/task/submit` creates one session per sample and dispatches each to a gateway node.
3. **The runtime starts the sandbox.** The node creates a runtime from `runtime.backend` and starts `runtime.image` on `runtime.network`. From here the node only ever calls `start`, `stop`, `exec`, `upload_*`, `download_*` on it.
4. **`PiHarness.setup`** — `runtime.exec` only. Writes pi's settings and a models template; `git clone --depth 1 --branch timestep-T --single-branch`, then removes the remote and scrubs the reflogs so history cannot reach a page past T even offline; probes the checkout (branch, commit, shallow posture, remotes, page census); and echoes two statements — `gsj_settings` and `gsj_workspace` — into the gateway's session registry *before any model call*, so the chain's first completion carries them. See [The timestep cutoff](timestep-cutoff.md).
5. **`run_steps`** — pi runs. The harness mints an HS256 cutoff token host-side (claims `{case_id, timestep, episode_id, exp}`; the secret never enters the sandbox), writes `.pi/mcp.json` with the token in the MCP URL, and substitutes the proxy's base URL and the session id into `models.json` — the session id is pi's API key, which is how the gateway maps captures to the session. pi's model calls go through the capture proxy, which records token ids and per-token logprobs per completion; its `mcp_gsj_*` tool calls go to the retrieval service, which verifies the token and clamps results to page ≤ T.
6. **`postprocess`** — `runtime.download_*` only. pi's transcript and the `out/` deliverable land under `<artifacts_dir>/<session_id>/`; the trace points at that directory through `trajectory.metadata.session_id`. Loud but non-fatal: evidence collection never fails the run.
7. **The builder reconstructs one trajectory.** `ValidatingPrefixMergingBuilder.build` first computes session-level findings — empty prompt or response ids (`S1`, `S6`), duplicate consecutive prompts (`S3`), a mid-chain `finish_reason=length` (`S7`), more than one choice (`S8`), a non-agent-shaped request (`A12`), a roster that changed across completions (`R11`), mixed policy versions (`S9`), an unconfigured end-of-turn id (`A15`) — then applies the optional generation-prompt glue stitch, then runs Polar's prefix merging. The findings go to `trajectory.metadata["gsj_validation"]`; any finding turns a `COMPLETED` trajectory into `status="ERROR"`. The gateway node only ever escalates a status, never clears one.
8. **SessionResult → callback and poll.** The gateway posts the `SessionResult` (`session_id`, `task_id`, `status`, `error`, `trajectory {traces[], metadata}`) to the rollout server, which holds it verbatim — status and error intact — for `GET /rollout/task/{id}` and, once the task is terminal, posts the `TaskResult` envelope (`results: [SessionResult…]`) to `callback_url` — our receiver. Each entry of `trajectory.traces[]` carries `prompt_ids`, `response_ids`, `loss_mask`, `response_logprobs`, the `prompt_messages` and `response_messages` views, `tools`, `finish_reason` and `metadata`; `trajectory.metadata` carries `reconstruction_stats`, `gsj_validation` and more. The receiver runs `checks.validate_session_result`, lands the result under `traces/` (no findings) or `quarantine/` (with them), and answers 200 either way; the trainer's `RolloutClient.wait` fetches the same results from the poll and runs the identical checks. Wire shapes are in [Wire formats](../reference/wire-formats.md).

> [!TIP]
> **Same checks on both sides of the wire**
>
> The receiver drops bad traces at the source with forensics attached; the trainer verifies everything that arrives. Because both run the same `checks.py`, no trust is required across the wire and nothing upstream can launder a bad trace into a training batch. This is a design rule, not a convenience — `client.py` deliberately never reads the receiver's disk.

## The three carried patches

Upstream at the pin has no releases, and three defects found at source had no fix on any upstream branch. Each is carried as a hand-adapted patch in `vendor/patches/`, applied in order by `vendor/apply_patches.sh`; the committed `vendor/polar/` tree is the *patched* tree. Each patch header records its origin commit, its anchors, and every adaptation, so the next re-vendor can re-anchor it.

| patch | what it does |
| --- | --- |
| **P1 — non-agent completion filter** | Adds `trajectory/builder/record_filters.py`, a shape-based filter for non-agent completions (single user message, no system, no tools, no SDK-only keys), wired into both builders; an all-filtered session becomes `ERROR`, and `reconstruction_stats` gains `raw_completions_total` beside `completions_total` so gate G7 can compare them. Without it, every auxiliary harness LLM call would become a well-formed one-completion trainable trace. The filter's shape test does not fire for pi, which streams unconditionally, so `builder.py` carries the pi-shaped replacement (`A12:non_agent_shape`). |
| **P2 — abort → session ERROR** | Any completion with `finish_reason == "abort"` anywhere in a session sets `trajectory.status="ERROR"` with `error="aborted generation (weight-update cutoff)"` in `PrefixMergingBuilder.build()`. At the pin a mid-chain abort merged cleanly into a `COMPLETED` session; the trace-level allowlist can only see a *tail* abort, so this capture-layer check is the only possible guard. |
| **P3 — policy-version stamping (storage half)** | `SessionStore` gains a live policy version (`set_policy_version`/`get_policy_version`), a per-session `gen_version` and `session_would_span()`; `save_message` stamps the live version onto each completion's metadata per turn. It also fixes metadata persistence: the writer payload is built from `dict(record.metadata)`, so post-construction stamps actually reach the persisted completion files. Inert until a trainer calls `set_policy_version` — no stamp is written and the persisted JSON is byte-identical to the unpatched pin. |

```bash
bash vendor/apply_patches.sh --verify     # asserts all three are present: ten symbol checks
```

`vendor/REVENDOR.md` is the recipe for moving the pin: fetch the new `stable` HEAD by SHA, replace the tree, re-apply P1–P3, verify by symbol and by suite, install `gsj_rollout` into Polar's venv, and prove the registry seam still resolves. The mechanical loop takes about two minutes on a warm cache; re-anchoring patches when upstream moves under them is the contingency.

> [!WARNING]
> **The registry seam is the tripwire**
>
> A Polar venv without `gsj_rollout` installed cannot resolve `agent.import_path` or `builder.strategy` — the seam fails with `ModuleNotFoundError: gsj_rollout`, and the server will not run our config. The recipe's `uv pip install -e ../..` step and its `issubclass(ValidatingPrefixMergingBuilder, PrefixMergingBuilder)` check exist for exactly this; run them after any venv rebuild. See [Server quickstart](../getting-started/server-quickstart.md).

## Nothing assumes Docker

Every measured episode ran under Docker, and Docker is the default. But the container runtime is a config value, not a design assumption:

```yaml
runtime:
  backend: docker                                   # or apptainer — Polar's built-in map
  image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3  # node + git + pi 0.83.0
  network: bridge                                   # the estate's compose network when
                                                    # services are addressed container-to-container
```

`render_task_request` copies these three values into `TaskRequest.runtime`; Polar's runtime factory maps `backend` to `DockerRuntime` or `ApptainerRuntime` (or an `import_path` of your own) and hands the harness a `BaseRuntime`. That interface is the entire contract our code sees:

| `BaseRuntime` method | used by `pi_harness.py` |
| --- | --- |
| `start()` / `stop()` | no — the gateway node owns lifecycle |
| `exec(command, cwd=…, env=…)` | yes — setup steps, the workspace probe, and pi itself (`run_steps` returns `ExecInput`s the node runs) |
| `upload_file()` / `upload_dir()` | no |
| `download_file()` / `download_dir()` | yes — `postprocess` collects the transcript and `out/` |

The harness never shells out to `docker`, never names a container, and never sets `runtime.workdir` to a path it creates itself (the run step carries its own `cwd` instead — the image must provide `node` and `git`, nothing else is assumed about it). `config.py` likewise has no Docker-shaped field. Apptainer is native at the pin but has not been exercised by this project; switching is a one-key change plus an estate that provides the image in Apptainer's format.

## The evaluation record

This repository is the record of an evaluation — could Polar own the episode layer our predecessor owned? — and the answer is **adopt**. Two tracked documents carry the reasoning and the conditions that would reverse it:

- [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) — what Polar gave us, what it cost (the three patches, the vendoring posture, silent degradation as the layer's universal failure mode and the validation written because of it), what we still own, and the adopt/reverse conditions. Read this first.
- [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) — the normative document: the scope laws, the assumption register, the capability and gap register, and the standing rules.

The validators' rule-by-rule reasoning is in [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md); the corpus tree the estate must present is in [`docs/corpus-contract.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md). The design record page in this guide summarises both: [The design record](../about/design-record.md).

## See also

- [Installation](../getting-started/installation.md) — the two installs, Polar's own venv, and what the wheel contains.
- [The timestep cutoff](timestep-cutoff.md) — the property the harness step in the episode walk-through exists for.
- [Traces](traces.md) — what the builder's reconstruction produces.
- [Validation](validation.md) — the checks both legs of the episode run.
- [Wire formats](../reference/wire-formats.md) — the `TaskRequest` and `SessionResult` bodies named above.
