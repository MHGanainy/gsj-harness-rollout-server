[Documentation](../README.md) › Reference

# Wire formats

Every JSON body that crosses a process boundary in this library, with a real example of each: the `TaskRequest` the trainer submits, the response to a submit, the task status the trainer polls, the `SessionResult` that Polar produces once per attempt (the same object in the poll, in the callback and on the receiver's disk), the receiver's own responses, and the wrapper a quarantined result is stored in. Read this page when you are writing a client of your own, inspecting a file in `traces_dir`, or working out which key a finding was computed from.

## The bodies at a glance

| body | direction | defined by | where you meet it |
| --- | --- | --- | --- |
| `TaskRequest` | trainer → Polar's rollout API, `POST /rollout/task/submit` | Polar's `TaskRequest` model; rendered by `gsj_rollout.config.render_task_request` | `RolloutClient.submit`, `gsj-rollout submit` |
| submit response | Polar → trainer | Polar's rollout API | the return value of `submit` is its `task_id` |
| `TaskStatus` | Polar → trainer, `GET /rollout/task/{task_id}` | Polar's `TaskStatus` model | `RolloutClient.wait`, the `on_poll` callback |
| `SessionResult` | Polar → everyone | Polar's `SessionResult` model, with `trajectory.metadata.gsj_validation` added by our builder | `TaskStatus.results[i]`, the callback envelope's `results[i]`, an accepted file, `quarantine_wrapper.session_result` |
| `TaskResult` envelope | Polar's rollout API → the receiver, `POST <callback_url>` | Polar's `TaskResult` model | the body the receiver ingests |
| receiver responses | receiver → Polar | `gsj_rollout.receiver` | Polar's manager log; `receiver.ingest` when embedded |
| quarantine wrapper | receiver → disk | `gsj_rollout.receiver` | `<quarantine_dir>/<session_id>.<pins_mode>.json` |

Polar's models are pydantic and live in the vendored tree (`vendor/polar/src/polar/rollout/models.py` and `trajectory/models.py`); the trainer never imports them. `gsj_rollout.client.Trace` is our mirror of the trace fields, with `extra="allow"` so a key Polar adds later rides along.

## `TaskRequest`

This is `tests/golden/task_request.json`, verbatim. The test suite asserts that `render_task_request(cfg, task_id="golden-task", instruction="Summarize the case.", case_id="case_0001", timestep=12, episodes=1, timeout_seconds=900.0)` on `tests/fixtures/rollout.yaml` produces exactly this object, so it is the reference for the shape:

```json
{
  "task_id": "golden-task",
  "instruction": "Summarize the case.",
  "num_samples": 1,
  "timeout_seconds": 900.0,
  "metadata": {
    "case_id": "case_0001",
    "timestep": 12,
    "prompt_source": "free"
  },
  "runtime": {
    "backend": "docker",
    "image": "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3",
    "network": "bridge"
  },
  "agent": {
    "import_path": "gsj_rollout.pi_harness:PiHarness",
    "model_name": "gsj/Qwen/Qwen3-0.6B",
    "settings": {
      "case_id": "case_0001",
      "timestep": 12,
      "clone_url_for": "http://host.docker.internal:3000/gsj-staging/{case_id}.git",
      "mcp_url_base": "http://host.docker.internal:8790",
      "mcp_token_secret_env": "GSJ_MCP_TOKEN_SECRET",
      "mcp_token_ttl_s": 3600,
      "tools_allowlist": [
        "read",
        "ls",
        "grep",
        "find",
        "write",
        "edit",
        "bash",
        "mcp_gsj_search_case",
        "mcp_gsj_search_decisions",
        "mcp_gsj_case_status",
        "mcp_gsj_decision_stats"
      ],
      "artifacts_dir": "/tmp/gsj-artifacts",
      "workdir": "/workspace",
      "context_window": 32768,
      "max_tokens": 8192,
      "thinking": "off"
    }
  },
  "builder": {
    "strategy": "gsj_rollout.builder:ValidatingPrefixMergingBuilder",
    "config": {
      "end_of_turn_token_id": 151645,
      "generation_prompt_glue_ids": [
        151667,
        271,
        151668,
        271
      ]
    }
  },
  "callback_url": "http://127.0.0.1:8300/callbacks/session_result"
}
```

![The TaskRequest block by block: the top-level scalars and metadata come from the call arguments, runtime from the runtime section, agent from estate and harness, builder from the builder section, callback_url from the receiver section; case_id and timestep land in both metadata and agent.settings](../img/task-request-anatomy.png)

<sub>Every block of the request traced to the call argument or YAML section it is rendered from; <code>case_id</code> and <code>timestep</code> are stated twice, once for the trace's metadata and once for the harness.</sub>

Key by key:

| key | type and constraint (Polar) | rendered from |
| --- | --- | --- |
| `task_id` | `str`; a second submit with the same id is refused with 409 while the first is still `running`, and replaces its record once it is terminal | the `task_id` argument |
| `instruction` | `str`; the prompt handed to the agent | the `instruction` argument |
| `num_samples` | `int ≥ 1`; the number of sessions Polar schedules — attempts, not accepted traces | `episodes` (default 1) |
| `timeout_seconds` | `float > 0`; the per-session execution budget, from which Polar counts a session's deadline | `timeout_seconds` (default 900.0) |
| `metadata` | `dict`; registered as the session's metadata, stamped on every completion, hoisted into each trace's `metadata` | `case_id`, `timestep` (coerced to `int`), `prompt_source`; plus `skill_card_hash` when `skill_card_text` is given, `split` when stated |
| `runtime.backend` | `"docker"` or `"apptainer"` | `runtime.backend` |
| `runtime.image` | non-empty `str` | `runtime.image` |
| `runtime.network` | `str` or `null`; Polar's own default is `"host"`, the render always states a value | `runtime.network` |
| `agent.import_path` | `str`; Polar requires exactly one of `harness` / `import_path`, and the render always uses `import_path` | `harness.import_path` |
| `agent.model_name` | `str` | `"<estate.provider>/<estate.model>"` |
| `agent.settings` | `dict`; opaque to Polar, handed to `PiHarness.setup` | see below |
| `builder.strategy` | `str`; an import path Polar resolves on the gateway | `builder.strategy` |
| `builder.config` | `dict`; passed to the builder's constructor | `end_of_turn_token_id` always; `generation_prompt_glue_ids` only when the YAML sets it |
| `callback_url` | `str` or `null`; where the manager POSTs the terminal result | `receiver.base_url` + `/callbacks/session_result` |

`agent.settings` is the harness's whole configuration document. Twelve keys are always present: `case_id` and `timestep` (the call arguments again — the harness needs them to pick the clone and the cutoff), `clone_url_for`, `mcp_url_base` and `mcp_token_secret_env` from `estate:`, and `mcp_token_ttl_s`, `tools_allowlist`, `artifacts_dir`, `workdir`, `context_window`, `max_tokens` and `thinking` from `harness:`. Two more, `pi_entry` and `pi_mcp_extension`, appear only when the YAML sets them. The [configuration guide](../guides/configuration.md#what-the-trainer-renders-taskrequest) lists what every YAML key means; this page only fixes where it lands.

> [!NOTE]
> **What the render refuses**
>
> `render_task_request` raises `ValueError` before anything is sent when `prompt_source` is neither `"free"` nor `"skill:<name>"`, when `skill_card_text` is given with a `free` source or is empty, when the card text cannot be UTF-8 encoded, or when `split` is not `"train"`, `"eval"` or `None`. `skill_card_hash` is the SHA-256 hex digest of the card's UTF-8 bytes, which is why the card must be read as bytes and decoded, not `read_text()`. Polar's reserved metadata keys — `session_id`, `task_id`, `evaluation`, `policy_version` — are never written into `metadata`.

> [!NOTE]
> **Keys the render never sends**
>
> Polar's `RuntimeSpec` accepts more than the three keys above (`env`, `prepare`, `workdir`, `cpus`, `memory_mb`, `gpus`, `allow_internet`, …) and `AgentSpec` accepts `env`, `mcp_servers` and `skills_path`. The render sends none of them, and there is no YAML key that would — by design, so that nothing in the request depends on one container runtime's semantics. The agent's working directory is `agent.settings.workdir`, which the harness applies itself.

### The submit response

`POST /rollout/task/submit` is non-blocking. Polar answers as soon as the task is registered:

```json
{"task_id": "golden-task", "status": "running"}
```

`RolloutClient.submit` returns the `task_id`. Any non-2xx status raises `httpx.HTTPStatusError` from `raise_for_status()` — a 409 for a still-running duplicate `task_id`, a 422 when the body fails Polar's model validation.

## The task status poll

`GET /rollout/task/{task_id}` returns Polar's `TaskStatus`. While sessions are running:

```json
{
  "task_id": "golden-task",
  "status": "running",
  "total_sessions": 4,
  "completed_sessions": 1,
  "results": [ { "session_id": "sk-polar-…", "status": "COMPLETED", "…": "…" } ],
  "result_paths": []
}
```

| key | meaning |
| --- | --- |
| `status` | `"running"`, `"completed"` or `"failed"`. `completed` is the normal end, whatever the individual sessions did; `failed` means the task itself raised inside Polar's manager |
| `total_sessions` | `num_samples` |
| `completed_sessions` | sessions that reached a terminal state — `COMPLETED`, `ERROR` and `TIMEOUT` all count |
| `results` | the `SessionResult` of every terminal session so far, verbatim; on `completed` the full list in Polar's order, on `failed` whatever had resolved before the failure |
| `result_paths` | Polar's own on-disk copies, when it was started with a `save_dir`; the client never reads them |

An unknown `task_id` is a 404 (`{"detail": "Task not found"}`), which `wait` raises as `httpx.HTTPStatusError`.

`RolloutClient.wait` is the loop around this endpoint:

```python
def wait(self, task_id: str, *, timeout_s: float,
         on_poll: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Poll until the task is terminal; the SessionResult bodies, verbatim."""
```

It polls every `poll_interval_s` seconds (constructor argument, default 2.0; each HTTP call has a 30 s timeout), hands every status body to `on_poll` if one is given, and returns `status["results"]` the first time `status` is `completed` or `failed`. If `timeout_s` elapses first it raises `TimeoutError("task <id> not terminal after <n>s (<completed>/<total> sessions)")`. `collect` calls it with `timeout_s=1020.0` by default — the 900 s task budget plus 120 s for the callback and the build — and `gsj-rollout submit` uses `on_poll` to print `task <id>: <completed>/<total> sessions terminal` whenever the count changes.

> [!WARNING]
> **`wait` returns bodies, not verdicts**
>
> The list `wait` returns includes `ERROR` and `TIMEOUT` sessions, and `COMPLETED` sessions whose trajectory would fail a check. Nothing in the poll path has been validated by our code yet. `collect` runs `partition_session_results` on the list, which is `checks.validate_session_result` per body; if you call `wait` yourself, do the same before training on anything ([Validation](../concepts/validation.md)).

## `SessionResult`

One `SessionResult` per attempt, built on the gateway node and returned to the rollout server. Its top-level structure, printed from the real callback body under `docs/polar/pi-corpus/`:

```bash
python - <<'EOF'
import json
body = json.load(open("docs/polar/pi-corpus/callback_session_result.json"))
print(sorted(body))
print(sorted(body["trajectory"]))
print(sorted(body["trajectory"]["metadata"]))
print(sorted(body["trajectory"]["traces"][0]))
EOF
```

```text
['error', 'metadata', 'node_id', 'session_id', 'status', 'task_id', 'timing', 'trajectory']
['error', 'metadata', 'status', 'traces']
['api_type', 'builder', 'completion_filter', 'gsj_validation', 'model_requested', 'model_used',
 'reconstruction_stats', 'record_count', 'session_id', 'task_id', 'task_metadata', 'trace_count']
['finish_reason', 'loss_mask', 'metadata', 'prompt_ids', 'prompt_messages', 'response_ids',
 'response_logprobs', 'response_messages', 'reward', 'tools']
```

![The SessionResult: session_id, task_id, node_id, status, error, timing and metadata at the top; trajectory with its status, error, metadata (reconstruction_stats, gsj_validation and more) and traces; the trainer's poll on the left returns the same bodies in TaskStatus.results, the callback on the right carries them in the TaskResult envelope, and the receiver lands each one as an accepted file (verbatim) or a quarantine file wrapping it with its findings](../img/session-result-anatomy.png)

<sub>The same body on all three paths; the annotations between the body and the disk name the admission rules and the gate that read each block.</sub>

### Top level

| key | type | meaning |
| --- | --- | --- |
| `session_id` | `str` | `sk-polar-<uuid4>`, minted by the manager; becomes the file name on the receiver's disk |
| `task_id` | `str` | the request's `task_id` |
| `status` | `str` | `COMPLETED`, `ERROR` or `TIMEOUT` — the terminal members of Polar's `SessionStatus`; copied from `trajectory.status` when the build ran |
| `error` | `str` or `null` | the trajectory's error when it has one, else the harness or runtime error |
| `trajectory` | object | below |
| `timing` | object | `register_to_init_queue_ms`, `init_ms`, `run_ms`, `postrun_ms` — floats, milliseconds |
| `node_id` | `str` or `null` | the gateway node that ran the session (`polar.gateway.id` in the YAML) |
| `metadata` | `dict` | the request's `metadata`, echoed unchanged (`{"case_id": …, "timestep": …, "prompt_source": …}` on a current body; `{}` on the pi-corpus fixture, which predates the metadata channel) |

The receiver's admission rule `ADM1:status_not_completed:<status>` reads `status` and nothing else at this level.

### `trajectory`

| key | meaning |
| --- | --- |
| `status` | `COMPLETED`, `ERROR` or `TIMEOUT` (Polar validates the set). Our builder sets `ERROR` on a completed session whenever its own findings are non-empty, so `status` and `gsj_validation.findings` never disagree |
| `error` | `null`, or the reason: `"gsj validation failed (<n> findings)"` from our builder, `"no completions"` / `"no trainable completions after completion filter"` from Polar's prefix merging, the harness or runtime error otherwise |
| `metadata` | the builder's report on the session, keys below |
| `traces` | the list of `Trace` objects; one per reconstructed chain, which for this harness is one |

`trajectory.metadata` as Polar's prefix-merging builder writes it, plus our one addition:

| key | written by | meaning |
| --- | --- | --- |
| `builder` | Polar | `"prefix_merging"` (the strategy our builder extends) |
| `session_id`, `task_id` | Polar | identity again |
| `api_type`, `model_requested`, `model_used` | Polar | `"openai_chat"` and the model name on the wire, as seen by the capture proxy |
| `record_count`, `trace_count` | Polar | completion records captured, traces produced |
| `task_metadata` | Polar | the session's registered metadata: the request's `metadata`, the harness's `gsj_settings` and `gsj_workspace` echoes, and `session_id` / `task_id` |
| `reconstruction_stats` | Polar | `chains_total`, `chains_reconstructed_full`, `chains_reconstructed_truncated`, `raw_completions_total`, `completions_total`, `completions_merged` — all `int` |
| `completion_filter` | Polar | `input_completions`, `kept_completions`, `excluded_completions`, `excluded_reasons`, `excluded_completion_ids`, `excluded` |
| `gsj_validation` | our builder | `{"builder": "gsj_rollout.builder:ValidatingPrefixMergingBuilder", "findings": [...], "glue_stitched": <int>}` |

`reconstruction_stats` is what the session-level gate G7 reads: it requires exactly one chain, zero truncated chains, and `completions_merged == completions_total == raw_completions_total`, and fails closed when any of the five keys it reads (`chains_reconstructed_full` is not checked) is absent or not an integer: `G7:missing_evidence:reconstruction_stats` when the object is missing or empty, `G7:missing_evidence:reconstruction_stats.<key>` naming the first bad key otherwise. `gsj_validation.findings` is what `ADM2:builder_findings_present:<n>` reads; the builder's own findings (`A12`, `A15`, `S1`, `S3`, `S6`–`S9`, `R11`) are re-emitted after it verbatim, so a quarantine file shows both layers. `ADM3:trajectory_missing` fires when `trajectory` is not an object, `ADM4:no_traces` when `traces` is missing or empty, `ADM5:malformed_trace` per entry that is not an object.

An attempt that fails before the build — the container did not start, the harness raised, the deadline passed — still has this shape: `status` and `trajectory.status` are `ERROR` or `TIMEOUT`, `traces` is `[]`, `trajectory.metadata` is reduced to `builder`, `record_count: 0` and `task_metadata`, and the same message sits in both `error` keys.

### `traces[i]`

| field | type | notes |
| --- | --- | --- |
| `prompt_ids` | `list[int]` | the first request's prompt tokens |
| `response_ids` | `list[int]` | every response position across the merged turns |
| `loss_mask` | `list[int]` of `0`/`1` | same length as `response_ids`; Polar validates both |
| `response_logprobs` | `list[float]` or `null` | same length as `response_ids` when present; `0.0` at mask-0 positions |
| `prompt_messages`, `response_messages` | `list[dict]` | the chat-message views |
| `tools` | `list[dict]` | the tool definitions on the wire; G3 hashes this list |
| `finish_reason` | `str` or `null` | `stop`, `length`, … from the last completion |
| `reward` | `float` or `null` | always `null` from this server |
| `metadata` | `dict` | `case_id`, `timestep`, `prompt_source` (and `skill_card_hash`, `split` when stated), `gsj_settings`, `gsj_workspace`, `session_id`, `task_id`, `completion_metadata` |

What each array means for training, how the turns are merged, and what every metadata key is evidence for are on the [traces page](../concepts/traces.md); the rules that read them are on the [validation page](../concepts/validation.md) and in the [Finding vocabulary](findings.md). On the trainer side, `traces_of(session_result)` turns the list into `Trace` models.

## The callback

When a task reaches its terminal state, Polar's manager POSTs the `TaskResult` to the request's `callback_url`, with a 10-second HTTP timeout, best effort: a failure is logged as a warning on Polar's side ("trainer must fall back to polling") and never retried. The body is an envelope around the same `SessionResult`s the poll returns:

```json
{
  "task_id": "golden-task",
  "status": "completed",
  "results": [ { "session_id": "sk-polar-…", "…": "…" } ],
  "result_paths": []
}
```

The receiver unwraps `results` and ignores the envelope's other keys. It also accepts a bare `SessionResult` as the whole body — the shape Polar's gateway pushes per session to the rollout server's own `/callbacks/session_result`, and the shape of the fixture files under `docs/polar/` — so a captured body can be replayed against a receiver with `curl` unchanged. Either way, each member must be a JSON object with a `trajectory` key and a `session_id` matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` in full, or the whole request is a 400.

> [!WARNING]
> **A failed callback is a missing file, not lost data**
>
> The receiver's archive is fed only by this POST. If it is unreachable from Polar's rollout-server process, or answers 400/500, nothing lands there — but the trainer still collects everything through the poll and validates it itself. Check `GET /healthz` counters against `completed_sessions` when the two disagree.

### The receiver's responses

All responses are JSON with `Content-Type: application/json`. The full account, including the atomicity guarantee behind a multi-result envelope, is in [the receiver guide](../guides/receiver.md#endpoints).

| request | status | body |
| --- | --- | --- |
| `POST /callbacks/session_result` | 200 | `{"accepted": n, "rejected": m}` — this request's counts; every member landed, in `traces_dir` or in quarantine |
| | 400 | `{"error": "<reason>"}` — not JSON, not an object, a member failing the shape screen, or a member that will not serialize; nothing landed |
| | 500 | `{"error": "pins configuration: <detail>"}` — the pins file or a key in it is unusable; nothing landed |
| | 500 | `{"error": "receiver: <ExceptionType>: <detail>"}` — a stage or commit failure on disk; nothing landed |
| `GET /healthz` | 200 | `{"status": "ok", "accepted": n, "rejected": m}` — process-lifetime totals |
| anything else | 404 | `{"error": "not found"}` |

A 200 with `rejected > 0` is a successful delivery: the rejection is our validation verdict on a body Polar delivered correctly, and Polar has no use for the distinction.

## The quarantine wrapper

An accepted body is written to `<traces_dir>/<session_id>.<pins_mode>.json` exactly as received (`json.dumps` defaults: one line, no indentation). A rejected body is written to `<quarantine_dir>/<session_id>.<pins_mode>.json` inside a two-key wrapper:

```json
{
  "findings": ["<rule>:<slug>[:<detail>]", "..."],
  "session_result": { "the SessionResult, untouched": "..." }
}
```

`findings` is the list `checks.validate_session_result` returned, in the order the rules ran; `session_result` is the member verbatim, so re-running the validator on it in any process reproduces (or, under different pins, revises) the verdict. `<pins_mode>` is the `mode` key of the pins file the receiver was started with — `thinking-off` when the file has none, `pins-unresolved` when it could not be read ([the receiver guide](../guides/receiver.md#on-disk) has the table).

A real one, `docs/polar/h200-stitch/attempt4.quarantined.json`, trimmed to its shape:

```json
{
  "findings": ["LP6:zero_logprob_rate_at_mask1:34/237>0.0"],
  "session_result": {
    "session_id": "sk-polar-688d8dc3-aa74-4b8d-803b-4b969b129487",
    "task_id": "cp04prime-stitch-a4",
    "status": "COMPLETED",
    "trajectory": {
      "status": "COMPLETED",
      "metadata": { "gsj_validation": { "builder": "gsj_rollout.builder:ValidatingPrefixMergingBuilder", "findings": [], "glue_stitched": 0 }, "…": "…" },
      "traces": [ { "…": "…" } ],
      "error": null
    },
    "timing": { "register_to_init_queue_ms": 3.52, "init_ms": 555.35, "run_ms": 7822.20, "postrun_ms": 416.85 },
    "node_id": "gsj-node-01",
    "error": null,
    "metadata": { "case_id": "case_0001", "timestep": 12, "prompt_source": "free" }
  }
}
```

Note what this example shows: the session completed, the builder found nothing, and the receiver still rejected it — the logprob discipline (`LP6`) is a receiver-side rule with a policy knob, and the body carries no verdict of its own beyond `gsj_validation`. The trainer's `partition_session_results` produces the in-memory equivalent of this wrapper, `(session_result, findings)` pairs, for every body its own checks refuse.

> [!TIP]
> **Reading the archive back**
>
> A file in `traces_dir` loads as a `SessionResult`; a file in `quarantine_dir` loads as the wrapper. One loop handles both:
>
> ```python
> import json, pathlib
> from gsj_rollout import checks
> from gsj_rollout.client import traces_of
>
> for path in pathlib.Path("/data/traces").rglob("*.json"):
>     doc = json.loads(path.read_text())
>     body = doc["session_result"] if "findings" in doc else doc
>     print(path.name, doc.get("findings", []), checks.validate_session_result(body))
>     for trace in traces_of(body):
>         print("  ", len(trace.response_ids), "response positions,", sum(trace.loss_mask), "trained")
> ```
>
> The third column is this process's verdict under its own pins; it can differ from the stored `findings` when the pins do.

## See also

- [Traces](../concepts/traces.md) — what the arrays and metadata keys mean, and how a session becomes one chain.
- [Validation](../concepts/validation.md) and the [Finding vocabulary](findings.md) — the rules that read these bodies and the strings they emit.
- [The receiver](../guides/receiver.md) — the ingest path, atomicity, file naming, logging.
- [Configuration](../guides/configuration.md) — every YAML key the request is rendered from.
- [Python API](api.md) — `RolloutClient`, `Trace`, `partition_session_results`, `traces_of`, `render_task_request`.
