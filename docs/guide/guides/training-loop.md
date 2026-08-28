[Documentation](../README.md) › Guides

# Running a training loop

This page shows how a trainer integrates the rollout server into a loop: the shape of one iteration, what the server guarantees about every trace it hands you and what it deliberately leaves to you, what "collect N" does and does not promise, how updated weights get back into the estate's engine without changing what the wire calls the model, and where the two worked bridges (slime and verl) live. It assumes you have already collected a trace once — if not, start with the [trainer quickstart](../getting-started/trainer-quickstart.md).

## The loop shape

The server's job ends at the trace. Everything around it — storing traces, deciding what to train on, scoring, the optimizer step, exporting weights, serving them — is the trainer's and the estate's. A loop therefore has one fixed shape: collect a batch, do your own work, put new weights on the engine, collect again. Nothing in the server side changes between iterations; only the weights behind the engine do.

![Six numbered steps — collect N, score and store, train one step, export weights, serve-updated, collect again — above two lanes: the trainer's lane holds the training loop, score and store, one optimizer step and the HF-format weights; the server-side lane holds the rollout server, the inference engine and serve-updated. Tasks go down from the training loop to the rollout server and traces come back up; the weights go down to serve-updated, which feeds the engine; a line from serve-updated loops back to the start.](../img/training-loop.png)

<sub>One iteration, strictly serialized: the trainer's lane on top, the server side below. Only the weights cross downward, only traces come back up, and the server side never learns that a loop exists.</sub>

Reading the picture left to right: your training loop submits N attempts as `TaskRequest`s, and `collect` polls the `SessionResult`s and re-runs `checks` on each one before handing back `Trace`s. The rollout server runs every attempt as a Polar episode — pi in a sandbox checked out at `timestep-T`, every model call proxied through the capture layer so tokens and logprobs are recorded — and then builder, receiver and `checks.py` decide accept or quarantine. The engine is the estate's: vLLM serving `estate.model` under `--served-model-name`. Scoring, storage, mixing, the optimizer step (slime, verl, or your own) and the export are yours; the export is an HF-format directory (`config.json` plus the tensors) on the serving host, and `serve-updated` stops the engine and starts it on that directory under the same served name, so the next `collect` samples from the new weights with the same requests and the same checks. Everything in the trainer's lane — storage, scheduling, reward, weights, versioning and the training itself — is deliberately outside the server.

In Python the trainer-facing surface is three calls: `load_config` for the YAML, `render_task_request` for each task, `RolloutClient.collect` for the batch. Everything after `collect` returns is your code.

```python
import logging
import subprocess

from gsj_rollout import RolloutClient, Trace, load_config
from gsj_rollout.config import render_task_request

logging.basicConfig(level=logging.WARNING)      # rejected sessions are logged on "gsj_rollout.client"

cfg = load_config("rollout.yaml")               # the operator's file, copied verbatim
client = RolloutClient(cfg.polar.rollout.base_url, poll_interval_s=2.0)

tasks = [("case_0001", 12, "Summarize the case."), ("case_0002", 9, "Summarize the case.")]

def requests_for(step: int) -> list[dict]:
    return [
        render_task_request(cfg, task_id=f"step{step:04d}-{i}", instruction=prompt,
                            case_id=case_id, timestep=timestep, episodes=4)
        for i, (case_id, timestep, prompt) in enumerate(tasks)
    ]

def sync_weights(export_dir: str) -> None:
    # the estate's recipe: stop the engine, start it on <export_dir>, same served name
    subprocess.run(["./estate/estate.sh", "serve-updated", export_dir], check=True)

for step in range(num_steps):
    traces: list[Trace] = client.collect(requests_for(step))   # 1. checks-clean sessions only
    rows = [(trace, score(trace)) for trace in traces]         # 2. your reward, your storage
    export_dir = train_one_step(rows)                          # 3. your optimizer; HF-format export
    sync_weights(export_dir)                                   # 4. the estate serves the new weights
```

Three things about this skeleton are load-bearing:

- **`collect` blocks until every submitted task is terminal** and returns only the traces of sessions that pass `checks.validate_session_result` on the trainer's side — the same rules the receiver ran. Rejections are logged at `WARNING` and never returned. When you need the rejected bodies (to account for consumed attempts, say), call `submit`, `wait` and `partition_session_results` yourself; the quickstart shows the three-step form.
- **Steps 1 to 4 do not overlap.** The engine restart in step 4 is the drain point: no session is in flight when the weights change, so no trace mixes two policies. See [why the sync is a stop-then-start](#weight-sync-via-serve-updated).
- **The requests do not change across iterations.** `estate.model` is the same string before and after a sync, so every rendered `TaskRequest` names the same model and every collected trace is comparable to the last batch's.

## What the server guarantees per trace — and what it does not

Every `Trace` you get from `collect` carries the same guarantees, and the same silences. Knowing which is which is what keeps the loop honest.

![Left, three green guarantee tiles — the cutoff held, checked twice, aligned raw arrays — each pointing at one Trace whose reward is null. Right, six concerns wired to their owner: reward and scoring, storage and retention, resubmits and mixing point at the trainer; sampling parameters and engine/codec provenance point at the estate; weight sync points at both.](../img/responsibility-split.png)

<sub>Three guarantees flow into every trace; the rest is wired to the trainer, the estate, or both — and the trace carries none of it.</sub>

**Guaranteed, per accepted trace:**

| guarantee | what it means for the loop | what stays yours |
| --- | --- | --- |
| the cutoff held | the sandbox was a shallow clone of branch `timestep-T` with no remote, retrieval was clamped to page ≤ T from verified token claims, and gate G5 audited both from the trace itself — see [the timestep cutoff](../concepts/timestep-cutoff.md) | nothing: the cutoff is enforced twice and audited once, and nobody else has to enforce it |
| the session passed the same checks on both sides | the receiver validated the callback body at the source and `collect` re-ran every rule on what it fetched; a trace in your hands has passed twice | resubmitting: a rejected attempt is consumed, and the server never retries, so when the goal is N accepted traces you submit again — see [collect-N semantics](#collect-n-semantics) |
| the arrays are aligned and raw | `response_ids`, `loss_mask` and `response_logprobs` are indexed together; the logprobs are the engine's own at sampling time, never renormalized — see [Traces](../concepts/traces.md) | collation and mixing, and what to do with a row whose `finish_reason` is `length` |

**Deliberately not the server's:**

- **Sampling parameters are the estate's.** The pinned agent sends none, so the engine's configuration *is* the sampling policy, and the trace records nothing about it. An engine started without an explicit generation-config pin samples at its neutral defaults, silently. The reference estate pins `--generation-config` in the serve argv for exactly this reason; on your estate, do the same.
- **`reward` is `null` in every callback.** The server never scores an episode. What you score from is the trace plus the episode's artifacts, which the harness lands on the server host under `<artifacts_dir>/<session_id>/` — `pi_transcript.jsonl` and, when the agent produced one, its `out/` deliverable. `trace.metadata["session_id"]` is the join key. `harness.artifacts_dir` defaults to `/tmp/gsj-artifacts`; point it at durable storage before a real run.
- **Codec and engine provenance are the estate's.** No engine identity, snapshot revision or tokenizer hash rides the callback; codec identity is verified at bring-up by the pins walk, not per trace. `estate.model_revision` in the YAML is an optional pin the server never reads — a trainer can check its own snapshot against it before spending GPU time, but it is not evidence carried by a trace.
- **Storage, retention, mixing, staleness and collation are the trainer's**, and so is the drain before each sync. The receiver writes accepted bodies verbatim to `traces_dir` and rejected ones to `quarantine/`, and that is the whole of its persistence: no index, no rotation, no policy-version stamp.
- **Weight sync is the trainer's and the estate's.** The trainer exports HF-format weights; the estate runs `serve-updated <dir>` — a stop, then a start on the new directory under the same `--served-model-name`. Nothing in `gsj_rollout/` reads, writes or serves weights.

> [!WARNING]
> **It has never trained anything, and says so**
>
> The two bridges that exist each ran exactly one optimizer step bracketed by two collections, proved that the sync changed the served policy, and stopped. Concurrent collection-and-training, and weight sync at a cadence, have zero data points. The mechanism is model-agnostic; the defaults are fitted to Qwen3, and one other model family has been run once. Treat the loop shape above as the tested envelope, not as a claim about what a long run will do.

> [!NOTE]
> **Two open gaps you should know about**
>
> Codec evidence never rides the callback — that is a decision, not an omission, and it is why provenance sits with the estate. And traces are not bound per episode to the engine's identity (serve argv, generation config, codec); that binding is owned by the first production bring-up. Both are listed in the capability register in [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) §7.

## Collect-N semantics

`episodes=N` (the CLI's `--episodes N`) asks Polar for N *attempts* (`num_samples=N`), not for N accepted traces: a session counts as collected only when it is `COMPLETED` with no builder findings and no `checks` findings, and a rejected session is a consumed attempt, quarantined and never retried. The definition itself ships as `gsj_rollout.config.COLLECT_SEMANTICS` and is quoted on the [command line page](cli.md#what---episodes-n-means).

For a loop this means the batch size you *get* is at most the batch size you *asked for*, and the server will never top it up. If an iteration needs a fixed number of accepted traces, the trainer resubmits — with an attempt budget, so a broken estate cannot turn into an infinite loop:

```python
def collect_at_least(client: RolloutClient, make_request, n_accepted: int, max_attempts: int) -> list[Trace]:
    """Resubmit until n_accepted traces are in hand or max_attempts are consumed."""
    traces: list[Trace] = []
    attempted = 0
    while len(traces) < n_accepted and attempted < max_attempts:
        batch = min(n_accepted - len(traces), max_attempts - attempted)
        traces += client.collect([make_request(episodes=batch)])
        attempted += batch
    return traces

traces = collect_at_least(
    client,
    lambda episodes: render_task_request(cfg, task_id="step0001-0", instruction="Summarize the case.",
                                         case_id="case_0001", timestep=12, episodes=episodes),
    n_accepted=8, max_attempts=16,
)
```

> [!TIP]
> **Length-terminated tails count as collected**
>
> A session whose last completion ended with `finish_reason == "length"` is accepted by design: its ids, mask and logprobs are real up to the cut. `gsj-rollout submit` counts them out loud (`length-terminated: K/N`); in Python, read `trace.finish_reason`. Whether such rows enter a training batch is your policy, not the server's.

Two details of `collect` matter at loop scale. It submits every request first and then waits for each task in turn, so a batch of many single-task requests is fine, and so is one request with a large `episodes`; Polar schedules the attempts either way. And its `timeout_s` (default `1020.0` — the 900 s task timeout plus 120 s of callback grace) is per task, so raise it together with `timeout_seconds` if your prompts need longer episodes; a task that is not terminal by the deadline raises `TimeoutError` out of `collect`.

## Weight sync via `serve-updated`

The engine that the sandboxes talk to is the estate's, and the server never touches it. Putting a trainer's checkpoint behind it is therefore an estate operation, and the reference estate ships one script for it: `estate/serving/serve-updated.sh`, reachable as `estate.sh serve-updated <dir>`.

```bash
# from a checkout of the repository, on a host with ssh access to the serving host;
# <dir> is the HF-format export ON THE SERVING HOST (it must contain config.json)
./estate/estate.sh serve-updated /home/gsj/ckpt/step-0001-hf
```

What it does, in order:

1. **Stops the running engine** (the pidfile's process; SIGTERM, then SIGKILL after 60 s). This is the drain point: the loop is serialized, so nothing is in flight when the stop happens, and the stop makes that physical.
2. **Starts vLLM on `<dir>`** with the same argv as the reference `serve.sh` except for two deliberate deltas: the model argument is the local directory (so there is no `--revision`), and `--served-model-name` is set to the pinned model id — `Qwen/Qwen3-0.6B` on the reference estate — so the name the wire sees does not change. The chat template, the `--generation-config` pin, `--max-model-len` and the tool-parser flags are byte-identical to the base serve.
3. **Waits for `/health`** (up to 600 s) and **verifies `/v1/models` lists the served name**; either failure is a non-zero exit before any collection can start.

It is configured by the same environment as `serve.sh`: `GSJ_VLLM_SSH_HOST` (default `h200-admin`), `GSJ_VLLM_PORT` (`8000`), `GSJ_VLLM_GPU` (`3`), `GSJ_VLLM_REMOTE_DIR` (`gsj-vllm`), `GSJ_VLLM_GPU_FRAC` (`0.30`) and `GSJ_VLLM_MODEL_ENV` (the `model-*.env` file that supplies the served model id).

### Why the wire identity must stay constant

`estate.model` is one string used in three places: the topology the server renders for Polar's gateway (`model_served`), the `model_name` of every `TaskRequest` (`<provider>/<model>`, which the harness writes into the agent's model configuration), and — through those — the `model` field of every request the capture proxy records. The engine, for its part, only answers requests whose model matches a name it serves.

If a sync changed the served name, the YAML would have to change, every rendered request would change, and every trace collected after the sync would name a different model than the ones collected before it — comparable only by convention. Keeping `--served-model-name` fixed means the *weights* change and nothing else does: the config, the requests, the harness, the checks and the pins are all untouched across the sync. That is the property the loop's step 4 relies on.

> [!WARNING]
> **Serialize collection and sync — the traces cannot tell you if you did not**
>
> A trace carries no policy version. A session that spans a weight sync would be assembled as `COMPLETED` with a clean chain snapshot and nothing on the wire to show that its turns were sampled from two different policies; the receiver cannot catch what the capture layer never records. The only protection today is procedural: let `collect` (or every `wait`) return before you run `serve-updated`, and do not submit again until it has exited 0. The reference loops verified the drain at each sync — zero episode containers, engine reporting no running or waiting requests — rather than assuming it.

> [!NOTE]
> **On your own estate**
>
> `serve-updated.sh` is a recipe for the reference estate, not part of the wheel. Any estate can do the equivalent: stop the engine, start it on the exported weights, keep the served name, the chat template and the generation-config pin identical to the base serve, and confirm `/v1/models` before collecting. After a sync the served weights no longer correspond to `estate.model_revision`; treat that key as the pin of the base snapshot the loop started from.

## The examples repository

Two complete bridges — one for [slime](https://github.com/THUDM/slime), one for [verl](https://github.com/volcengine/verl) — live in [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples), together with the `RUNBOOK.md` that ran them on the reference estate. Each collects with this library, converts traces into the trainer's native sample type, takes one optimizer step, exports HF-format weights and syncs them through `serve-updated`. Start there rather than from a blank file; the shape above is what they implement.

## See also

- [Trainer quickstart](../getting-started/trainer-quickstart.md) — the first collection, the CLI's exit codes, the three-step form of `collect`.
- [Traces](../concepts/traces.md) — every field of `Trace`, the mask discipline, and how an episode becomes one chain.
- [Validation](../concepts/validation.md) — the admission checks and gates that decide accepted or rejected, on both sides of the wire.
- [The estate](estate.md) — the services the server side needs, including the serving recipes.
- [Configuration](configuration.md) — `estate.model`, `harness.artifacts_dir`, timeouts, and every other key.
