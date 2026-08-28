[Documentation](../README.md) › Getting started

# Trainer quickstart

This page walks the trainer side of a first run against a rollout server that somebody else already operates: install the package, write the one YAML, submit a task from the command line, do the same from Python, and read what comes back. By the end you will have collected one validated `Trace` and know exactly what `--episodes N` promises — and what it does not.

The trainer role needs no estate and never imports Polar. Everything below runs on any machine with Python 3.12 or newer that can reach the server's rollout API over HTTP. If you are the one bringing the server up, read the [server quickstart](server-quickstart.md) first and come back here.

## Before you start

You need three things from whoever operates the server:

| you need | why |
| --- | --- |
| the URL of Polar's rollout API | the client submits to and polls `<rollout>/rollout/task/…` |
| the operator's YAML, or the six estate values in it | the trainer renders every `TaskRequest` from the same file the server was started with |
| the case ids and timesteps that exist in the corpus | `case_0001` at `timestep 12` is only meaningful if that branch exists on the git host |

> [!TIP]
> **Ask for the YAML, not for the values**
>
> The one YAML is designed to be shared. `gsj-rollout serve` reads it to start the receiver and render Polar's topology; `gsj-rollout submit` and `render_task_request` read the same file to build task requests. Copying the operator's file verbatim guarantees your requests describe the estate the sandboxes actually run in — the clone URL, the retrieval service, the model name, the receiver's callback address.

## 1. Install

```bash
pip install gsj-harness-rollout-server
```

The wheel pulls in `pydantic`, `httpx` and `pyyaml` — nothing else. `import gsj_rollout` never imports `polar`; the server-only modules (`pi_harness`, `builder`, `receiver`, `cli`) stay out of the public import surface and are reached by import path or by the console script. Details and the optional extras are on the [installation page](installation.md).

```python
>>> import gsj_rollout
>>> gsj_rollout.__version__
'0.1.2'
>>> gsj_rollout.__all__
['RolloutClient', 'Trace', 'checks', 'load_config', 'RunConfig', '__version__']
```

## 2. Write the minimal YAML

Six values have no default and must be supplied. Everything else — the sandbox image, the tool roster, the token budget, the builder's end-of-turn id, the check policy — defaults to the measured reference values and may be omitted wholesale.

| key | what it is |
| --- | --- |
| `estate.clone_url_for` | the git host's clone URL with a `{case_id}` placeholder; the sandbox clones it itself, so it must resolve from *inside* the sandbox network |
| `estate.mcp_url_base` | the retrieval service, again sandbox-reachable |
| `estate.serving_base_url` | the inference engine's root — **without** a `/v1` suffix (Polar's proxy appends `/v1/chat/completions` itself; a suffixed value is rejected at load) |
| `estate.model` | the served model name, byte-for-byte what the engine was started with; the request's `model_name` becomes `<provider>/<model>` (`provider` defaults to `gsj`) |
| `polar.gateway.public_url` | one URL for the gateway that is reachable both from host dispatch and from inside the sandboxes; its port must agree with `polar.gateway.port` (default 8100) |
| `receiver.traces_dir` | where accepted traces land on the server; required so that no `/tmp` default can lose training data silently |

Save this as `rollout.yaml`, substituting the operator's values:

```yaml
estate:
  clone_url_for: "http://forgejo.estate:3000/gsj-staging/{case_id}.git"
  mcp_url_base: "http://mcp.estate:8790"
  serving_base_url: "http://vllm.estate:8000"        # no /v1
  model: "Qwen/Qwen3-0.6B"
polar:
  rollout:
    public_url: "http://rollout.estate:8080"         # where YOUR client submits and polls
  gateway:
    public_url: "http://10.0.0.5:8100"               # port must equal polar.gateway.port
receiver:
  public_url: "http://10.0.0.5:8300"                 # rides in every request as callback_url
  traces_dir: /data/gsj/traces
```

> [!WARNING]
> **Two more keys matter as soon as the trainer is not on the server host**
>
> The six required values describe the estate. Two *optional* keys describe where things are reached from:
>
> - `polar.rollout.public_url` is the address the client submits to and polls. It defaults to `http://127.0.0.1:8080`, which is only right when your training loop runs on the rollout host.
> - `receiver.public_url` is rendered into every request as `callback_url` (`<receiver>/callbacks/session_result`). Polar posts the task's `TaskResult` envelope (`results: [SessionResult, …]`) there once, when the task ends — for every session, errored ones included. It defaults to `http://127.0.0.1:8300`, which is only right when the receiver runs next to Polar's rollout process — the trainer's copy of the YAML decides where callbacks go, so a wrong value here means the receiver never sees a session.
>
> Both are already correct in the operator's file, which is the other reason to copy it.

Loading is strict: an unknown key anywhere is an error naming the section and key, a section reduced to comments is treated as empty so the missing-field message still names the field, and `user:` is a free-form area the library never reads. `load_config` also rebinds the process-wide check policy from the file's `checks:` section, so a trainer whose YAML matches the server's applies the same policy when it re-validates. The full key reference is in the [configuration guide](../guides/configuration.md).

## 3. Submit one task from the command line

```bash
gsj-rollout submit --config rollout.yaml \
  --case case_0001 --timestep 12 \
  --prompt "Summarize the case."
```

`submit` renders the request, posts it, polls until the task is terminal, re-validates every session it gets back, and reports. It prints one line each time the number of terminal sessions changes, never one per poll. A clean single-episode run looks like this (last line abridged):

```text
task gsj-task: 0/1 sessions terminal
task gsj-task: 1/1 sessions terminal
collected 1/1 episodes
length-terminated: 0/1 accepted episodes ended finish_reason=length — qualified by design; …
```

Read the exit code before anything else:

| exit | meaning | what produced it |
| --- | --- | --- |
| `0` | every attempt was collected | `len(accepted) == --episodes` |
| `1` | not all collected | a session was rejected or ended in error, or the task was not terminal within `--timeout` + `--grace` (`TimeoutError`) |
| `2` | config or usage error | the YAML failed to load, or the triple is incomplete (`--case`, `--timestep` and `--prompt`/`--prompt-file` are all required unless `--from-bank` supplies them) |
| `3` | server unreachable or HTTP error | any `httpx.HTTPError` during submit or poll — transport failures and 4xx/5xx responses alike |

Options you will reach for on the first day:

| flag | default | effect |
| --- | --- | --- |
| `--episodes N` | `1` | attempts to run — see [collect-N semantics](#6-what---episodes-n-means) below |
| `--out DIR` | report only | write each accepted `SessionResult` to `DIR/<session_id>.json` |
| `--task-id` | `gsj-task` | the Polar task id, visible in the progress lines and in every trace's metadata |
| `--timeout` | `900` | the request's `timeout_seconds`; the client waits this plus `--grace` (default `120`) before giving up |
| `--poll-interval` | `2.0` | seconds between polls |
| `--prompt-file PATH` | — | read the instruction from a file instead of `--prompt` |
| `--from-bank PARQUET [--row N]` | — | take the whole triple, prompt, source and split from a taskbank row (needs `pyarrow`) |

Every session that fails re-validation is printed as `rejected <session_id>: [findings]`. The `length-terminated` line counts accepted episodes whose trace ended with `finish_reason == "length"`: those are accepted by design — a truncated tail is a qualified trace, not a broken one — and whether to train on them is your call. The complete flag list is on the [command line page](../guides/cli.md).

> [!NOTE]
> **Pins travel with the wheel**
>
> `checks` validates traces against pinned approved sets (tool roster, system prompt, skill cards, settings). The wheel ships the reference estate's pins so the trainer leg works on install; against any other estate every hash gate fails `*_not_approved`, loudly and by design. Point `GSJ_PINS_PATH` at that estate's pins file *before* the first import of `gsj_rollout.checks`. See [pins and approved sets](../concepts/pins.md).

![Five numbered steps across three lanes: the trainer submits to Polar's rollout API and polls it, Polar's sandboxes run the episodes and call the receiver back at task end, the receiver files each session into traces_dir or quarantine, and the trainer re-validates the SessionResult bodies it collects into Trace objects or rejections](../img/submit-collect-lifecycle.png)

<sub>The trainer talks only to Polar's rollout API; the receiver validates on arrival and the trainer runs the same `checks` on what it fetches. Navy is our code, slate is vendored Polar, amber a payload, green accepted, red rejected.</sub>

The five steps in the figure, in the order they happen:

1. **Submit** — `RolloutClient.submit(request)` posts the `TaskRequest` JSON to `POST /rollout/task/submit` and gets back Polar's `task_id`.
2. **Episodes run** — Polar schedules `num_samples` attempts; each runs in its own sandbox with pi behind the capture proxy, and the builder reconstructs the trajectory and records its session-level verdict under `trajectory.metadata.gsj_validation`.
3. **Receiver validates** — when the task ends, Polar posts one `TaskResult` envelope to `callback_url`; the receiver runs `checks.validate_session_result` on every session in it, one verdict each, and writes accepted bodies to `traces_dir/` and rejected ones, with their findings, to `quarantine/`. None of this reaches the trainer: no callback goes to the trainer and it shares no disk with the receiver.
4. **Poll until terminal** — meanwhile `client.wait(task_id, timeout_s=…)` polls `GET /rollout/task/{id}` every `poll_interval_s` until the task status is `completed` or `failed`; if that has not happened by the deadline it raises `TimeoutError`. The terminal status response carries the `SessionResult` bodies in its `results` field — the same bodies the receiver validated, verbatim, one per attempt.
5. **Re-validate** — `partition_session_results(results)` runs the same `checks.validate_session_result` on each body: accepted sessions become `Trace` objects, rejected ones are logged and never returned.

## 4. The same run in Python

The CLI is a thin wrapper over three public pieces: `load_config` for the YAML, `render_task_request` for the body, and `RolloutClient` for the wire. Compact form first:

```python
from gsj_rollout import RolloutClient, load_config
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")

request = render_task_request(
    cfg,
    task_id="first-run",
    instruction="Summarize the case.",
    case_id="case_0001",
    timestep=12,
)

client = RolloutClient(cfg.polar.rollout.base_url)
traces = client.collect([request])      # list[Trace] — checks-clean sessions only
print(len(traces), "trace(s) collected")
```

`collect` submits every request, waits for each task in turn (default `timeout_s=1020.0`: the 900 s task timeout plus 120 s of callback grace), partitions the results with the same validators the receiver ran, logs each rejected session at `WARNING` on the `gsj_rollout.client` logger, and returns only the traces of accepted sessions. Rejected sessions are reported and never returned.

When you want the rejections in hand — for a taskbank that tracks consumed attempts, say — use the three steps `collect` is made of:

```python
from gsj_rollout.client import partition_session_results, traces_of

task_id = client.submit(request)                    # -> str, Polar's task id
results = client.wait(                              # -> the SessionResult bodies, verbatim
    task_id,
    timeout_s=1020.0,
    on_poll=lambda status: print(
        status["completed_sessions"], "/", status["total_sessions"], "sessions terminal"
    ),
)

accepted, rejected = partition_session_results(results)
for result, findings in rejected:
    print("rejected", result["session_id"], findings)

traces = [trace for result in accepted for trace in traces_of(result)]
```

`wait` raises `TimeoutError` when the task is not terminal (`completed` or `failed`) by the deadline, and any `httpx.HTTPError` from submit or poll propagates as-is; the CLI is what maps those to exit codes 1 and 3.

`render_task_request` takes the config positionally and everything else by keyword:

| parameter | default | note |
| --- | --- | --- |
| `task_id` | required | Polar's task id |
| `instruction` | required | the prompt text the agent receives |
| `case_id` | required | e.g. `case_0001` |
| `timestep` | required | `T` — both the branch checked out and the retrieval cutoff |
| `episodes` | `1` | becomes `num_samples` |
| `timeout_seconds` | `900.0` | per-task, carried in the request |
| `prompt_source` | `"free"` | or `skill:<name>`; recorded in every trace's metadata for gate G1 (see [Validation](../concepts/validation.md)) |
| `skill_card_text` | `None` | only valid with a `skill:` source; its UTF-8 bytes hash to `metadata.skill_card_hash` |
| `split` | `None` | `"train"` or `"eval"`; absent means unstated, never `train` |

The rendered body is Polar's `TaskRequest`: `task_id`, `instruction`, `num_samples`, `timeout_seconds`, `metadata` (`case_id`, `timestep`, `prompt_source`, and the optional card hash and split), plus the `runtime`, `agent`, `builder` and `callback_url` sections filled from the YAML. The [wire formats reference](../reference/wire-formats.md) shows a full example.

## 5. What comes back

Polar returns one `SessionResult` per attempt — the exact JSON body the receiver was sent, with `status` and `error` intact. Its top level carries `session_id`, `task_id`, `status`, `error`, `node_id`, `timing`, `metadata` and `trajectory`; the trajectory holds `status`, `error`, `metadata` (including the builder's `gsj_validation` verdict) and `traces`. `traces_of` turns the `traces` list into `Trace` objects:

| field | type | meaning |
| --- | --- | --- |
| `prompt_ids` | `list[int]` | the token ids of the prompt as the model saw it |
| `response_ids` | `list[int]` | the token ids the model produced, across every turn |
| `loss_mask` | `list[int]` | `1` on the tokens the model generated, `0` elsewhere; same length as `response_ids` |
| `response_logprobs` | `list[float] \| None` | the logprob the engine reported for each response token, as captured by the proxy |
| `prompt_messages` | `list[dict]` | the chat messages behind `prompt_ids` |
| `response_messages` | `list[dict]` | the assistant and tool messages behind `response_ids` |
| `tools` | `list[dict]` | the tool definitions on the wire — the roster gate G3 hashes exactly this |
| `finish_reason` | `str \| None` | `stop`, `length`, … from the last completion |
| `reward` | `float \| None` | always empty from this server: scoring is the trainer's job |
| `metadata` | `dict` | `session_id`, `task_id`, and the request's `metadata` (`case_id`, `timestep`, `prompt_source`, …) hoisted by Polar |

`Trace` is a pydantic model with `extra="allow"`, so any field a future Polar adds rides along without breaking the trainer. What each field means for a training step, and how the ids, mask and logprobs line up, is on the [traces page](../concepts/traces.md); the gates and admission checks that decide accepted-or-rejected are on the [validation page](../concepts/validation.md).

## 6. What `--episodes N` means

`--episodes N` (or `episodes=N` in `render_task_request`) asks Polar for N *attempts*, not for N accepted traces: a session counts as collected only when it is `COMPLETED` with no builder findings and no `checks` findings, and a rejected session is a consumed attempt, quarantined with its findings and never retried by the server. Exit 0 means `collected == attempted` exactly, so a `2/4` run exits 1 and is the honest count, not a failure of the server — the full definition (`gsj_rollout.config.COLLECT_SEMANTICS`) is quoted on the [Command line](../guides/cli.md#what---episodes-n-means) page, and [Running a training loop](../guides/training-loop.md#collect-n-semantics) shows a loop that resubmits under an attempt budget.

![Four attempts fanned out from num_samples 4 — two collected, one quarantined, one that never counts — converging on a tally of 2 of 4 and exit 1](../img/collect-n-semantics.png)

<sub>One `--episodes 4` run: a check for each collected attempt, a cross for the quarantined one, a warning sign for the errored one, and the tally that sets the exit code.</sub>

The three ways an attempt in the figure ends, and what each one counts as:

| the session ends | what decides it | counts as |
| --- | --- | --- |
| `COMPLETED`, `gsj_validation.findings: []`, no `checks` finding | the builder's verdict and the trainer's re-validation are both clean | collected — a `Trace` |
| `COMPLETED` with builder findings, or with a `checks` finding | the receiver quarantines it with its findings | a consumed attempt |
| `ERROR` or `TIMEOUT` | admission fails first: `ADM1:status_not_completed:ERROR` | never counts — still a consumed attempt |

The CLI never re-submits to reach N accepted traces and the server never retries a consumed attempt. The run in the figure prints `collected 2/4 episodes` and exits 1; exit 0 needs `4/4`. Exit codes 2 and 3 — a usage error, an unreachable server — never get as far as a tally; they are in the [exit code table](#3-submit-one-task-from-the-command-line) above.

## See also

- [Command line](../guides/cli.md) — every flag of `serve` and `submit`.
- [Configuration](../guides/configuration.md) — the complete YAML reference with every default.
- [Traces](../concepts/traces.md) — ids, mask, logprobs, and how a trainer consumes them.
- [Validation](../concepts/validation.md) — the admission checks and gates, and why the same code runs on both sides of the wire.
- [Python API](../reference/api.md) — the signatures, generated from the source.
