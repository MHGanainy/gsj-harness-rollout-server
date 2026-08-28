[Documentation](../README.md) › Reference

# Python API

This is the reference for everything `gsj_rollout` exports, generated from the source of version **0.1.2**: the trainer-side client (`RolloutClient`, `Trace`, and the two helpers `collect` is built from), the validators in `gsj_rollout.checks`, and the configuration loader and renderers in `gsj_rollout.config`. Each section opens with what the object is for and how to call it; the signatures underneath are read from the installed code. For the narrative behind these objects read [Traces](../concepts/traces.md), [Validation](../concepts/validation.md), [Pins and approved sets](../concepts/pins.md), and [Configuration](../guides/configuration.md).

## The surface at a glance

`pip install gsj-harness-rollout-server` installs one package, `gsj_rollout`, with three runtime dependencies (`pydantic`, `httpx`, `pyyaml`). Importing it never imports `polar`: the trainer side is a light client, and Polar lives in its own environment on the server side. After the import, `sys.modules` holds exactly four of the package's modules — `gsj_rollout`, `gsj_rollout.checks`, `gsj_rollout.client`, and `gsj_rollout.config`; the four server-side modules are never loaded.

```python
import gsj_rollout

gsj_rollout.__version__          # "0.1.2"
gsj_rollout.__all__              # RolloutClient, Trace, checks, load_config, RunConfig, __version__
```

![A trainer process imports gsj_rollout and gets four exported tiles — RolloutClient for submit, wait and collect; Trace, one trajectory as a pydantic model; checks, the validators run on both sides; and load_config producing RunConfig from the one YAML — each tile standing on the submodule it comes from](../img/api-surface.png)

<sub>What `import gsj_rollout` gives a trainer: the exported names, each standing on the submodule it comes from — `gsj_rollout.client` adds `partition_session_results` and `traces_of`, `gsj_rollout.config` adds `render_task_request` and `render_topology`, and `checks` is the whole module.</sub>

| Name | Module | Role |
|---|---|---|
| `RolloutClient` | `gsj_rollout.client` | submit tasks, wait for them, collect validated traces |
| `Trace` | `gsj_rollout.client` | the pydantic model of one training trace |
| `partition_session_results` | `gsj_rollout.client` | split fetched results into accepted / rejected-with-findings |
| `traces_of` | `gsj_rollout.client` | the `Trace` objects of one session result |
| `checks` | `gsj_rollout.checks` | the validators — the same code the receiver runs |
| `load_config`, `RunConfig` | `gsj_rollout.config` | the one YAML, loaded and validated |
| `render_task_request`, `render_topology` | `gsj_rollout.config` | one Polar `TaskRequest` body; Polar's topology file |
| `__version__` | `gsj_rollout` | the installed version string |

Four modules ship in the package but are not part of this surface, by design:

| Module | Why it is not exported |
|---|---|
| `gsj_rollout.pi_harness` | imports `polar`; Polar loads it by the import-path string in `harness.import_path` (`gsj_rollout.pi_harness:PiHarness`) |
| `gsj_rollout.builder` | imports `polar`; Polar loads it by `builder.strategy` (`gsj_rollout.builder:ValidatingPrefixMergingBuilder`) |
| `gsj_rollout.receiver` | the callback endpoint, started by `gsj-rollout serve` — see [The receiver](../guides/receiver.md) |
| `gsj_rollout.cli` | the console script — see [Command line](../guides/cli.md) |

![The four server-side modules and who reaches them instead of the trainer: Polar loads pi_harness and builder by their import-path strings, the operator at the shell runs the cli, whose serve command starts the receiver; a crossed-out arrow marks that the trainer never imports any of them](../img/api-server-side.png)

<sub>Who reaches the four server-side modules: Polar loads `pi_harness` (`harness.import_path`) and `builder` (`builder.strategy`) by import path, and the operator's `gsj-rollout serve | submit` console script runs `cli`, with `serve` starting the `receiver` — never the trainer's `import gsj_rollout`.</sub>

> [!NOTE]
> **Two of them cannot be imported trainer-side at all**
>
> `pi_harness` and `builder` import `polar`, which exists only in Polar's own virtual environment on the server. That is why `import gsj_rollout` does not touch them: the trainer's install stays `pydantic + httpx + pyyaml`, and the two modules are reached only through the import-path strings Polar reads from each `TaskRequest`.

## `RolloutClient`

The trainer's whole surface is three methods on one object. `submit` posts a `TaskRequest` body (the dict `render_task_request` returns) to `POST {base_url}/rollout/task/submit` and returns Polar's `task_id`; `wait` polls `GET {base_url}/rollout/task/{task_id}` until the status is `completed` or `failed` and returns the `SessionResult` bodies verbatim; `collect` chains the two over any number of requests, re-runs `checks.validate_session_result` on every result, logs the rejected ones at `WARNING`, and returns the `Trace` objects of the clean sessions only.

```python
from gsj_rollout import RolloutClient, load_config
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")
client = RolloutClient(cfg.polar.rollout.base_url)   # e.g. "http://127.0.0.1:8080"

request = render_task_request(
    cfg,
    task_id="case_0004-t13-000",
    instruction="Draft the response to the claimant's letter of 3 March.",
    case_id="case_0004",
    timestep=13,
    episodes=2,
)
traces = client.collect([request])                   # list[Trace], validated
```

The constructor takes the rollout API's base URL (a trailing slash is stripped), an optional `poll_interval_s` (default `2.0`), and an optional `httpx.Client` — pass your own to set timeouts, proxies, or auth; the default is `httpx.Client(timeout=30.0)`.

**`submit(task_request)`** posts the mapping as JSON and returns the `task_id` string from the response. It raises `httpx.HTTPStatusError` on any non-2xx answer and whatever `httpx` raises when the server is unreachable.

**`wait(task_id, *, timeout_s, on_poll=None)`** polls every `poll_interval_s` seconds. Each status body is passed to `on_poll` if you give one — it has `status`, `results`, `completed_sessions`, and `total_sessions`. When the deadline passes without a terminal status it raises `TimeoutError` naming the task and the `completed/total` session count; the task keeps running on the server.

**`collect(task_requests, *, timeout_s=1020.0)`** is `submit` for every request, then `wait` for each task in order, then `partition_session_results` and `traces_of`. The default timeout is the default task timeout (900 s) plus a callback grace period (120 s). Rejected sessions are reported through the `gsj_rollout.client` logger as `rejected <session_id>: [findings]` and never returned.

> [!WARNING]
> **`collect` raises on a pins fault, not on a bad trace**
>
> Content never raises: a malformed or failing result becomes findings and is dropped. Configuration does: if the pins file cannot be used, the first hash gate raises `checks.PinsConfigurationError` out of `collect`. Set `GSJ_PINS_PATH` to your estate's pins file before collecting — see [Pins and approved sets](../concepts/pins.md).

### `RolloutClient`

```python
class RolloutClient:
    def __init__(self, base_url: str, *, poll_interval_s: float = 2.0,
                 http: httpx.Client | None = None): ...
```

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `base_url` | `str` | required | the rollout API's base URL (`cfg.polar.rollout.base_url`); a trailing `/` is stripped |
| `poll_interval_s` | `float` | `2.0` | seconds between two status polls in `wait` |
| `http` | `httpx.Client \| None` | `None` | your own client, for timeouts, proxies, or auth; `None` means `httpx.Client(timeout=30.0)` |

The two attributes `base_url` and `poll_interval_s` are public and can be read back; the HTTP client is private.

### `RolloutClient.submit`

```python
def submit(self, task_request: Mapping[str, Any]) -> str: ...
```

Posts `dict(task_request)` as JSON to `POST {base_url}/rollout/task/submit` and returns the `task_id` string from the response body.

| | |
|---|---|
| Returns | the `task_id` Polar assigned |
| Raises | `httpx.HTTPStatusError` on a non-2xx response; `httpx.HTTPError` subclasses (for example `httpx.ConnectError`) when the server cannot be reached |

```python
task_id = client.submit(request)
```

### `RolloutClient.wait`

```python
def wait(
    self,
    task_id: str,
    *,
    timeout_s: float,
    on_poll: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]: ...
```

Polls `GET {base_url}/rollout/task/{task_id}` every `poll_interval_s` seconds (the last sleep is shortened to the remaining time) and returns the task's `results` list — the `SessionResult` bodies, verbatim and unvalidated — as soon as the status is `completed` or `failed`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `task_id` | `str` | required | the id `submit` returned |
| `timeout_s` | `float` | required | seconds to keep polling before giving up |
| `on_poll` | `Callable[[dict], None] \| None` | `None` | called with every status body (`status`, `results`, `completed_sessions`, `total_sessions`) — use it for progress output |

| | |
|---|---|
| Returns | `list[dict]` — every `SessionResult` of the task, exactly as the poll returned them |
| Raises | `TimeoutError` — `task {task_id} not terminal after {timeout_s}s ({completed}/{total} sessions)`; the task keeps running on the server. `httpx.HTTPStatusError` on a non-2xx poll response |

```python
results = client.wait(task_id, timeout_s=1020.0,
                      on_poll=lambda st: print(st["completed_sessions"], "/", st["total_sessions"]))
```

### `RolloutClient.collect`

```python
def collect(
    self,
    task_requests: Iterable[Mapping[str, Any]],
    *,
    timeout_s: float = 1020.0,
) -> list[Trace]: ...
```

Submits every request first, then waits for each task in submission order with the same `timeout_s`, then partitions the pooled results with `partition_session_results` and returns the `Trace` objects of the accepted ones. Each rejected result is logged once at `WARNING` on the `gsj_rollout.client` logger as `rejected <session_id>: <findings>`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `task_requests` | `Iterable[Mapping]` | required | `TaskRequest` bodies, normally from `render_task_request` |
| `timeout_s` | `float` | `1020.0` | per-task wait: the default `timeout_seconds` of a request (900) plus 120 s for the callback to land |

| | |
|---|---|
| Returns | `list[Trace]` — the traces of every session with zero findings, in result order |
| Raises | everything `submit` and `wait` raise, plus `checks.PinsConfigurationError` when the pins file cannot be used |

```python
traces = client.collect([request_a, request_b], timeout_s=1500.0)
```

## `Trace`

`Trace` is the trainer-side mirror of the fields Polar puts on each trace of a `SessionResult` — the token arrays, the mask, the logprobs, the message views, the tool roster, and the metadata block. It is a pydantic model with `extra="allow"`, so any field the wire carries that is not listed here is kept and reachable as an attribute; every listed field has a default, so a partial trace validates. What each field means, and how the arrays line up, is in [Traces](../concepts/traces.md).

```python
trace = traces[0]
len(trace.response_ids) == len(trace.loss_mask) == len(trace.response_logprobs)   # True on a validated trace
trace.metadata["timestep"], trace.metadata["case_id"], trace.metadata.get("split")
trace.model_dump()                                                                # back to a plain dict
```

### `Trace`

```python
class Trace(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_ids: list[int] = Field(default_factory=list)
    response_ids: list[int] = Field(default_factory=list)
    loss_mask: list[int] = Field(default_factory=list)
    prompt_messages: list[dict[str, Any]] = Field(default_factory=list)
    response_messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str | None = None
    response_logprobs: list[float] | None = None
    reward: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `prompt_ids` | `list[int]` | `[]` | token ids of the prompt the first turn was generated from |
| `response_ids` | `list[int]` | `[]` | token ids of everything after the prompt: every model turn and the tool results between them |
| `loss_mask` | `list[int]` | `[]` | one `0`/`1` per `response_ids` entry; `1` marks a trainable (model-generated) token |
| `prompt_messages` | `list[dict]` | `[]` | the chat messages behind `prompt_ids` — the system prompt is the `role: system` entry |
| `response_messages` | `list[dict]` | `[]` | the assistant and tool messages behind `response_ids` |
| `tools` | `list[dict]` | `[]` | the tool roster offered to the model, as sent on the wire |
| `finish_reason` | `str \| None` | `None` | the engine's finish reason for the last turn |
| `response_logprobs` | `list[float] \| None` | `None` | one logprob per `response_ids` entry; `None` when the engine gave none |
| `reward` | `float \| None` | `None` | the grader's reward, when one was attached |
| `metadata` | `dict` | `{}` | `case_id`, `timestep`, `prompt_source`, optional `skill_card_hash` and `split`, plus the `gsj_settings` and `gsj_workspace` evidence blocks |

Because the model is `extra="allow"`, any key Polar adds to a trace that is not listed above survives validation and is reachable as an attribute (and through `model_extra`). Because every field has a default, `Trace.model_validate({})` succeeds — `Trace` describes the shape, `checks` decides whether the content is acceptable.

## Partitioning and extracting traces yourself

`collect` is a convenience. When you want the rejected results too — to count them, inspect their findings, or file them yourself — call `wait` and then these two functions, which are exactly what `collect` calls.

`partition_session_results` runs `checks.validate_session_result` on every result and returns `(accepted, rejected)`: accepted results as shallow-copied dicts, rejected ones paired with their finding list. `traces_of` returns the `Trace` objects of one result, reading `trajectory.traces` and returning `[]` when either key is missing.

```python
from gsj_rollout.client import partition_session_results, traces_of

results = client.wait(task_id, timeout_s=1020.0)
accepted, rejected = partition_session_results(results)
for result, findings in rejected:
    print(result["session_id"], findings)
traces = [trace for result in accepted for trace in traces_of(result)]
```

### `partition_session_results`

```python
def partition_session_results(
    session_results: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], list[str]]]]: ...
```

Runs `checks.validate_session_result(result)` — with the process default policy — on every result, in order.

| | |
|---|---|
| Parameter | `session_results` — `SessionResult` mappings, as `wait` returns them |
| Returns | `(accepted, rejected)`: `accepted` is a list of shallow copies (`dict(result)`) with no findings; `rejected` is a list of `(copy, findings)` pairs, `findings` being the non-empty `list[str]` |
| Raises | `checks.PinsConfigurationError` when a hash gate cannot read the pins file |

### `traces_of`

```python
def traces_of(session_result: Mapping[str, Any]) -> list[Trace]: ...
```

Returns `Trace.model_validate(trace)` for every element of `session_result["trajectory"]["traces"]`. A missing or `null` `trajectory`, or a missing or `null` `traces`, yields `[]`; it does not validate the result first, so call it on accepted results only unless you mean to inspect rejected traces.

## Validation: `gsj_rollout.checks`

`checks` is the one module that runs on both sides of the wire: the receiver calls it on every callback and quarantines what fails; the client calls it again on what it fetched. It has one entry point, `validate_session_result`, which takes the callback-shaped `SessionResult` mapping and returns a list of byte-stable finding strings — empty means accepted. It never raises on content; the only exception it throws is `PinsConfigurationError`, and that is a server configuration fault. The rule reasoning is in [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md); the finding strings are catalogued in [Finding vocabulary](findings.md).

```python
from gsj_rollout import checks

findings = checks.validate_session_result(session_result)             # [] means accepted
strict = checks.CheckPolicy(zero_at_mask1_max_rate=0.0, reject_toolless_roster=True)
findings = checks.validate_session_result(session_result, policy=strict)
```

`validate_session_result` produces findings in a fixed order: the admission layer (`ADM1`–`ADM5`), the chain snapshot on `trajectory.metadata.reconstruction_stats` (`G7`), then `run_trace_checks` on each trace. `run_trace_checks` is the per-trace seam — the same ten rules in the same order, callable on one trace when you already hold it:

| Order | Function | Findings |
|---|---|---|
| 1 | `check_logprob_discipline(trace, policy)` | `LP1`–`LP9` |
| 2 | `check_trace_tripwires(trace)` | `TR1`–`TR3` |
| 3 | `check_page_cutoff(trace)` | `G5:search_page_gt_timestep`, `G5:missing_evidence:timestep` |
| 4 | `check_workspace(trace)` | the `G5` checkout census |
| 5 | `check_tool_roster(trace)` | `G3` |
| 6 | `check_system_prompt(trace)` | `G2` |
| 7 | `check_skill_card(trace)` | `G1` |
| 8 | `check_settings_echo(trace)` | `G7:settings_hash_not_approved`, `G7:missing_evidence:settings` |
| 9 | `check_thinking_tail(trace)` | `G6` |
| 10 | `check_toolless_roster(trace, policy)` | `H41` — only when the policy arms it |

`check_chain_snapshot(trajectory_metadata)` is the session-level `G7` stats rule that `validate_session_result` runs before the per-trace loop. All of these are public functions with the same `list[str]` contract.

`CheckPolicy` is a frozen dataclass holding the three platform-conditioned knobs. Passing `policy=None` (the default) resolves `checks.DEFAULT_POLICY` at call time, and `load_config` rebinds `DEFAULT_POLICY` from the YAML's `checks:` section — so a trainer that loads the config gets the estate's policy without threading it through every call.

| Field | Default | Effect |
|---|---|---|
| `sentinel_threshold` | `-9000.0` | a mask-1 logprob at or below this is `LP3:sentinel_logprob_at_mask1` |
| `zero_at_mask1_max_rate` | `0.25` | a higher share of exactly-zero mask-1 logprobs is `LP6:zero_logprob_rate_at_mask1` |
| `reject_toolless_roster` | `False` | when `True`, a roster offered with zero tool calls is `H41:roster_offered_zero_tool_calls` |

The hash gates compare against the approved sets in the pins file. `approved_set(key)` returns the list for one key (`tool_roster_hash`, `system_prompt_hash`, `skill_card_hash`, `settings_hash`, `g6_expected_tail_ids`) and raises `PinsConfigurationError` when the file is unreadable, corrupt, wrongly shaped, or the key is missing, empty, or not a list. The file is read once per process and cached; changing pins means restarting.

The module's public constants:

| Constant | Value | Meaning |
|---|---|---|
| `FINDING_VOCABULARY` | a tuple of 42 `{id}:{slug}` strings | every finding prefix the module can emit; snapshot-tested, never reworded |
| `PINS_PATH` | a `Path` | the pins file in use: `GSJ_PINS_PATH` if set, else the repo checkout's `pins/pins.gsj.json` if it exists, else the packaged copy |
| `CHECKOUT_PINS`, `PACKAGED_PINS` | `Path`s | the two fallback candidates behind `PINS_PATH` |
| `DEFAULT_POLICY` | `CheckPolicy()` | the process-wide policy; rebound by `load_config` |
| `ACCEPTED_STATUS` | `"COMPLETED"` | the one `SessionResult.status` admission accepts |
| `ALLOWED_FINISH_REASONS` | `{"stop", "tool_calls", "stop_sequence", "length"}` | anything else is `TR1` |
| `ALLOWED_SPLITS` | `("train", "eval")` | a present `metadata.split` outside this is `TR3` |
| `CUTOFF_SCOPED_TOOLS` | `{"mcp_gsj_search_case"}` | the tool results `check_page_cutoff` scans for page numbers |

> [!WARNING]
> **The packaged pins file is the reference estate's, not a default**
>
> When `GSJ_PINS_PATH` is unset and there is no repo checkout, `PINS_PATH` resolves to the copy inside the wheel and the module emits a `UserWarning` at import. Those are the reference estate's approved hashes: against your own estate every hash gate fails `*_not_approved`. Point `GSJ_PINS_PATH` at your own file — [Pins and approved sets](../concepts/pins.md) explains how to produce one.

### `validate_session_result`

```python
def validate_session_result(
    session_result: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]: ...
```

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `session_result` | `Mapping[str, Any]` | required | one callback-shaped `SessionResult` — the body the receiver got or the poll returned, never the on-disk quarantine wrapper |
| `policy` | `CheckPolicy \| None` | `None` | the knobs for `LP3`, `LP6`, and `H41`; `None` resolves `DEFAULT_POLICY` when the check runs |

| | |
|---|---|
| Returns | `list[str]` of findings in emission order; `[]` means accepted |
| Raises | `PinsConfigurationError` only — every content problem is a finding |

The order is fixed: `ADM1` (status), `ADM3` (no trajectory — the remaining checks are skipped), `ADM2` (builder findings, followed by the builder's own strings), `ADM4` (no traces), then `check_chain_snapshot` on `trajectory.metadata`, then `run_trace_checks` per trace; a trace that is not a mapping contributes `ADM5:malformed_trace` instead.

```python
from gsj_rollout import checks

findings = checks.validate_session_result(session_result)
if findings:
    print("rejected:", findings)
```

### `run_trace_checks`

```python
def run_trace_checks(
    trace: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]: ...
```

The ten per-trace rules from the table above, concatenated in that order, on one trace mapping (a `Trace.model_dump()` works). Returns the findings; raises `PinsConfigurationError` when a gate cannot read its approved set.

### The `check_*` functions

Every function below takes one trace mapping (`check_chain_snapshot` takes `trajectory.metadata`) and returns `list[str]`; the two policy-aware ones accept `policy: CheckPolicy | None = None`.

| Function | Signature | One line |
|---|---|---|
| `check_logprob_discipline` | `(trace, policy=None)` | `LP1`–`LP9`: mask present, binary, and aligned; logprobs present, aligned, finite, non-positive, no sentinels or excess zeros at mask-1 |
| `check_trace_tripwires` | `(trace)` | `TR1` finish reason in `ALLOWED_FINISH_REASONS`; `TR2` no masked reasoning tokens; `TR3` a present `metadata.split` in `ALLOWED_SPLITS` |
| `check_page_cutoff` | `(trace)` | `G5`: no page above the episode timestep in any `mcp_gsj_search_case` result; `G5:missing_evidence:timestep` when no timestep can be read |
| `check_workspace` | `(trace)` | `G5` checkout census from `metadata.gsj_workspace`: shallow, zero remotes, pages contiguous from 1, max page and branch equal to the timestep |
| `check_tool_roster` | `(trace)` | `G3`: the canonical-JSON SHA-256 of `tools` is in `tool_roster_hash` |
| `check_system_prompt` | `(trace)` | `G2`: the SHA-256 of every `role: system` message text is in `system_prompt_hash`; none present is missing evidence |
| `check_skill_card` | `(trace)` | `G1`: `prompt_source` is `free`, or `skill:<name>` with a `skill_card_hash` in the approved set |
| `check_settings_echo` | `(trace)` | `G7` settings clause: the canonical-JSON SHA-256 of `metadata.gsj_settings` is in `settings_hash` |
| `check_thinking_tail` | `(trace)` | `G6`: every turn opens with one of `g6_expected_tail_ids` (turn 1 at the end of `prompt_ids`, later turns in the mask-0 interstitial) |
| `check_toolless_roster` | `(trace, policy=None)` | `H41`: a non-empty roster with zero tool calls — only when `policy.reject_toolless_roster` is `True` |
| `check_chain_snapshot` | `(trajectory_metadata)` | `G7` stats: `chains_total == 1`, nothing truncated, `completions_merged` and `raw_completions_total` equal to `completions_total`; missing or non-integer stats are `G7:missing_evidence:reconstruction_stats` |

### `CheckPolicy`

```python
@dataclass(frozen=True)
class CheckPolicy:
    sentinel_threshold: float = -9000.0
    zero_at_mask1_max_rate: float = 0.25
    reject_toolless_roster: bool = False
```

Frozen, so build a new one rather than mutating: `CheckPolicy(zero_at_mask1_max_rate=0.0)`. The field table is above.

### `DEFAULT_POLICY`

```python
DEFAULT_POLICY: CheckPolicy = CheckPolicy()
```

The process-wide policy every `policy=None` call resolves at call time. `load_config` rebinds it to `CheckPolicy(**cfg.checks.model_dump())`; the last `load_config` wins. Rebind it yourself (`checks.DEFAULT_POLICY = CheckPolicy(...)`) when there is no YAML on the trainer side.

### `approved_set`

```python
def approved_set(key: str) -> list[str]: ...
```

| | |
|---|---|
| Parameter | `key` — one of `tool_roster_hash`, `system_prompt_hash`, `skill_card_hash`, `settings_hash`, `g6_expected_tail_ids` |
| Returns | the `pins[key]` list from the pins file (for `g6_expected_tail_ids`, a list of token-id lists) |
| Raises | `PinsConfigurationError` — `pins file <path> unusable: <error>` when the file cannot be read, parsed, or has no `pins` object; `pins key '<key>' missing, empty, or not a list in <path>` otherwise |

The file is read on the first call and cached for the life of the process — change the pins, restart the process.

### `PinsConfigurationError`

```python
class PinsConfigurationError(Exception): ...
```

The one exception the validators raise. It always means the server side is misconfigured (a missing, corrupt, or incomplete pins file), never that a trace is bad.

### `PINS_PATH`, `CHECKOUT_PINS`, `PACKAGED_PINS`

```python
CHECKOUT_PINS: Path   # <checkout>/pins/pins.gsj.json — two levels above checks.py
PACKAGED_PINS: Path   # <site-packages>/gsj_rollout/pins/pins.gsj.json — the copy in the wheel
PINS_PATH: Path       # GSJ_PINS_PATH if set, else CHECKOUT_PINS if it exists, else PACKAGED_PINS
```

All three are resolved once, at import; setting `GSJ_PINS_PATH` after `import gsj_rollout` has no effect on the running process. When the resolution lands on `PACKAGED_PINS` without an override, the module emits a `UserWarning` saying so.

### `FINDING_VOCABULARY`

```python
FINDING_VOCABULARY: tuple[str, ...]   # 42 entries
```

Every `{id}:{slug}` prefix the module can emit — a finding on the wire is one of these, optionally followed by a `:detail` suffix. The complete list, with what each one means, is [Finding vocabulary](findings.md). Each entry is also a module constant (`checks.G5_SEARCH_PAGE_GT_TIMESTEP == "G5:search_page_gt_timestep"`), and `ACCEPTED_STATUS == "COMPLETED"` is the status `ADM1` requires.

### `ALLOWED_FINISH_REASONS`, `ALLOWED_SPLITS`, `CUTOFF_SCOPED_TOOLS`

```python
ALLOWED_FINISH_REASONS = frozenset({"stop", "tool_calls", "stop_sequence", "length"})
ALLOWED_SPLITS = ("train", "eval")
CUTOFF_SCOPED_TOOLS = frozenset({"mcp_gsj_search_case"})
```

`ALLOWED_SPLITS` is a tuple on purpose: membership is tested by equality, so an unhashable value in `metadata.split` becomes a `TR3` finding rather than an exception. `CUTOFF_SCOPED_TOOLS` names the tools whose results `check_page_cutoff` scans for page numbers; `mcp_gsj_case_status` results are read only to recover the timestep, and decision searches and file reads are exempt from the cutoff.

## Configuration: `gsj_rollout.config`

One YAML file serves both sides: the server renders Polar's topology and starts the receiver from it, the trainer renders every `TaskRequest` from it. `load_config(path)` parses the file, validates it into a `RunConfig`, and — as a deliberate side effect — rebinds `checks.DEFAULT_POLICY` from the `checks:` section. It raises `ValueError` for invalid YAML, for a file whose top level is not a mapping, and for any validation failure, naming each offender: an unknown key reads `section 'harness': unknown key 'foo'`, a missing required value reads `'polar.gateway.public_url': Field required`. The field-by-field reference, with every default, is [Configuration](../guides/configuration.md).

```python
from gsj_rollout import load_config
from gsj_rollout.config import render_task_request, render_topology

cfg = load_config("rollout.yaml")          # ValueError on anything wrong
topology = render_topology(cfg)            # the dict `gsj-rollout serve` writes as topology.rendered.yaml
request = render_task_request(cfg, task_id="t-000", instruction="...", case_id="case_0004", timestep=13)
```

`RunConfig` is the root model. Every section forbids unknown keys, and a section whose body is empty in the YAML is treated as `{}` so the error names the missing field rather than the section. The sections:

| Class | YAML key | Required? | What it holds |
|---|---|---|---|
| `EstateConfig` | `estate` | yes — `clone_url_for`, `mcp_url_base`, `serving_base_url`, `model` | where the git host, the retrieval service, and the inference engine are, and which model is served; `serving_base_url` must not end in `/v1` |
| `RuntimeConfig` | `runtime` | no | the sandbox backend, image, and network Polar starts each episode with |
| `HarnessConfig` | `harness` | no | the agent's import path, tool allowlist, workdir, context and token limits, and the `thinking` level — validated against pi's own level list |
| `BuilderConfig` | `builder` | no | the trajectory builder's import path and the end-of-turn token id it stitches on |
| `ChecksConfig` | `checks` | no | the `CheckPolicy` mirror; `load_config` copies it into `checks.DEFAULT_POLICY` |
| `PolarConfig` | `polar` | yes — `gateway.public_url` | the rollout API (`RolloutConfig`) and the one gateway node (`GatewayNodeConfig`) |
| `RolloutConfig` | `polar.rollout` | no | Polar's rollout API host and port; `base_url` is what `RolloutClient` connects to |
| `GatewayNodeConfig` | `polar.gateway` | yes — `public_url` | the gateway node Polar dispatches to; the port in `public_url` must equal `port` |
| `ReceiverConfig` | `receiver` | yes — `traces_dir` | where the callback endpoint listens and where accepted and quarantined results land |

`render_topology(cfg)` returns the content of Polar's `topology.yaml` as a dict — `gsj-rollout serve` writes it next to the config as `topology.rendered.yaml`. It reads `polar.*` plus `estate.model` and `estate.serving_base_url`; nothing else.

`render_task_request(cfg, *, task_id, instruction, case_id, timestep, ...)` returns one Polar `TaskRequest` body for the task triple. `episodes` becomes `num_samples` — the number of attempts Polar schedules, not a target of accepted traces. `prompt_source` states the prompt's origin for the `G1` gate: `"free"`, or `"skill:<name>"` with the resolved card text in `skill_card_text` so its hash is stated in the trace metadata. `split` (`"train"` or `"eval"`) is carried in metadata when given and omitted — meaning unstated — when `None`. It raises `ValueError` for a `prompt_source` outside those two forms, for `skill_card_text` paired with `"free"`, for empty or non-UTF-8 card text, and for a `split` outside the two values. The rendered body is described key by key in [Wire formats](wire-formats.md).

> [!TIP]
> **Read the skill card as bytes**
>
> The hash `render_task_request` states is the SHA-256 of the card's UTF-8 bytes. Read the file with `path.read_bytes().decode("utf-8")`, not `read_text()`, so locale and newline translation cannot change the digest you pin.

### `load_config`

```python
def load_config(path: str | Path) -> RunConfig: ...
```

| | |
|---|---|
| Parameter | `path` — the YAML file |
| Returns | a validated `RunConfig` |
| Raises | `ValueError` — `config <path>: invalid YAML: <error>`; `config <path> must contain a top-level mapping`; or `config <path> invalid — <detail>; <detail>…` where each detail is `section '<section>': unknown key '<key>'` or `'<dotted.path>': <pydantic message>`. `OSError` when the file cannot be opened |
| Side effect | rebinds `checks.DEFAULT_POLICY` from the `checks:` section |

A section written as a bare key (`polar:` with nothing under it, or only comments) parses as YAML `null`; `load_config` turns it into `{}` before validation so the error names the missing field, for example `'polar.gateway': Field required`.

```python
from gsj_rollout import load_config

try:
    cfg = load_config("rollout.yaml")
except ValueError as exc:
    raise SystemExit(str(exc))
print(cfg.polar.rollout.base_url, cfg.receiver.resolved_quarantine_dir)
```

### `RunConfig`

```python
class RunConfig(_Section):
    estate: EstateConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    builder: BuilderConfig = Field(default_factory=BuilderConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    polar: PolarConfig
    receiver: ReceiverConfig
    user: dict[str, Any] = Field(default_factory=dict)
```

Every section class extends `_Section`, a pydantic `BaseModel` with `extra="forbid"`. `user` is a free mapping the library never reads — put your own keys there rather than in a section.

### `EstateConfig` — `estate:`

```python
class EstateConfig(_Section):
    clone_url_for: str
    mcp_url_base: str
    mcp_token_secret_env: str = "GSJ_MCP_TOKEN_SECRET"
    serving_base_url: str
    provider: str = "gsj"
    model: str
    model_revision: str | None = None
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `clone_url_for` | `str` | required | the git host's clone URL pattern with a `{case_id}` placeholder; episode containers clone it themselves, so it must resolve from inside the sandbox network |
| `mcp_url_base` | `str` | required | the retrieval service's base URL, again sandbox-reachable |
| `mcp_token_secret_env` | `str` | `"GSJ_MCP_TOKEN_SECRET"` | the environment variable holding the HMAC secret shared with the retrieval service |
| `serving_base_url` | `str` | required | the inference engine's root URL, without `/v1` — Polar's proxy appends `/v1/chat/completions` itself; a value ending in `/v1` is rejected |
| `provider` | `str` | `"gsj"` | pi's provider key; the wire `model_name` is `<provider>/<model>` |
| `model` | `str` | required | must equal the engine's served model name byte for byte |
| `model_revision` | `str \| None` | `None` | an optional record of the served snapshot revision; never read by the server, available to a trainer that wants to verify the engine |

### `RuntimeConfig` — `runtime:`

```python
class RuntimeConfig(_Section):
    backend: str = "docker"
    image: str = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
    network: str = "bridge"
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `backend` | `str` | `"docker"` | the Polar runtime backend each episode sandbox is started with |
| `image` | `str` | `"ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"` | the harness image (node, git, pi); override with your own build |
| `network` | `str` | `"bridge"` | the container network; the estate's compose network when services are addressed container-to-container |

### `HarnessConfig` — `harness:`

```python
class HarnessConfig(_Section):
    import_path: str = "gsj_rollout.pi_harness:PiHarness"
    tools_allowlist: list[str] = Field(
        default=["read", "ls", "grep", "find", "write", "edit", "bash",
                 "mcp_gsj_search_case", "mcp_gsj_search_decisions",
                 "mcp_gsj_case_status", "mcp_gsj_decision_stats"],
        min_length=1)
    artifacts_dir: str = "/tmp/gsj-artifacts"
    workdir: str = "/workspace"
    context_window: int = 32768
    max_tokens: int = 8192
    thinking: str = "off"
    pi_entry: str | None = None
    pi_mcp_extension: str | None = None
    mcp_token_ttl_s: int = 3600
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `import_path` | `str` | `"gsj_rollout.pi_harness:PiHarness"` | the agent class Polar loads by string |
| `tools_allowlist` | `list[str]` | the eleven tools shown | the roster offered to the model; at least one entry; a different roster hashes outside `tool_roster_hash` until you re-pin |
| `artifacts_dir` | `str` | `"/tmp/gsj-artifacts"` | host-side directory the gateway writes deliverables to; point it at durable storage for real runs |
| `workdir` | `str` | `"/workspace"` | the agent's working directory inside the image; part of what `G2` pins |
| `context_window` | `int` | `32768` | the context length pi is told the model has |
| `max_tokens` | `int` | `8192` | the per-completion token limit |
| `thinking` | `str` | `"off"` | one of `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` — pi's own list; any other value is rejected because pi would silently clamp it to `off`. YAML's bare `off`/`on` booleans are mapped back to strings first. A non-`off` level needs the thinking-on pins file on both sides |
| `pi_entry` | `str \| None` | `None` | an alternative pi entry point inside the image |
| `pi_mcp_extension` | `str \| None` | `None` | an alternative MCP extension path inside the image |
| `mcp_token_ttl_s` | `int` | `3600` | lifetime of the per-episode retrieval token |

### `BuilderConfig` — `builder:`

```python
class BuilderConfig(_Section):
    strategy: str = "gsj_rollout.builder:ValidatingPrefixMergingBuilder"
    end_of_turn_token_id: int = 151645
    generation_prompt_glue_ids: list[int] | None = None
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `strategy` | `str` | `"gsj_rollout.builder:ValidatingPrefixMergingBuilder"` | the trajectory builder Polar loads by string |
| `end_of_turn_token_id` | `int` | `151645` | the end-of-turn token the builder stitches between turns — `<\|im_end\|>` under the Qwen3 tokenizer; re-derive against the served tokenizer when `estate.model` changes |
| `generation_prompt_glue_ids` | `list[int] \| None` | `None` | extra ids between turns for an asymmetric chat template; omitted from the request when `None` |

### `ChecksConfig` — `checks:`

```python
class ChecksConfig(_Section):
    sentinel_threshold: float = checks.CheckPolicy.sentinel_threshold        # -9000.0
    zero_at_mask1_max_rate: float = checks.CheckPolicy.zero_at_mask1_max_rate  # 0.25
    reject_toolless_roster: bool = checks.CheckPolicy.reject_toolless_roster   # False
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `sentinel_threshold` | `float` | `-9000.0` | copied into `CheckPolicy.sentinel_threshold` |
| `zero_at_mask1_max_rate` | `float` | `0.25` | copied into `CheckPolicy.zero_at_mask1_max_rate`; a CUDA estate that returns exact logprobs sets `0.0` |
| `reject_toolless_roster` | `bool` | `False` | copied into `CheckPolicy.reject_toolless_roster` |

### `PolarConfig` — `polar:`

```python
class PolarConfig(_Section):
    rollout: RolloutConfig = Field(default_factory=RolloutConfig)
    gateway: GatewayNodeConfig
    heartbeat_interval_seconds: int = 30
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `rollout` | `RolloutConfig` | all defaults | the rollout API |
| `gateway` | `GatewayNodeConfig` | required | the one gateway node |
| `heartbeat_interval_seconds` | `int` | `30` | the gateway heartbeat written into the topology |

### `RolloutConfig` — `polar.rollout:`

```python
class RolloutConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8080
    public_url: str | None = None
    save_dir: str | None = None

    @property
    def base_url(self) -> str: ...
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | where Polar's rollout API listens |
| `port` | `int` | `8080` | its port |
| `public_url` | `str \| None` | `None` | the URL clients dial when it differs from `http://<host>:<port>` |
| `save_dir` | `str \| None` | `None` | Polar's own on-disk session store, when you want one |

`base_url` is `public_url` when set, else `http://<host>:<port>` with `0.0.0.0` and `::` rewritten to `127.0.0.1`. It is what `RolloutClient` takes.

### `GatewayNodeConfig` — `polar.gateway:`

```python
class GatewayNodeConfig(_Section):
    id: str = "gsj-node-01"
    host: str = "0.0.0.0"
    port: int = 8100
    public_url: str
    engine: str = "vllm"
    max_init_workers: int = 4
    max_run_workers: int = 2
    max_postrun_workers: int = 4
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` | `str` | `"gsj-node-01"` | the node id in the topology |
| `host` | `str` | `"0.0.0.0"` | the gateway's bind address |
| `port` | `int` | `8100` | the gateway's port |
| `public_url` | `str` | required | one URL reachable both from the host and from inside episode containers — a LAN or estate-network address, never `localhost`; must carry an `http://` or `https://` scheme, and its port (80/443 when implicit) must equal `port` |
| `engine` | `str` | `"vllm"` | the inference engine kind written into the topology |
| `max_init_workers` | `int` | `4` | Polar's concurrency for sandbox start-up |
| `max_run_workers` | `int` | `2` | Polar's concurrency for running episodes |
| `max_postrun_workers` | `int` | `4` | Polar's concurrency for trajectory building and callbacks |

### `ReceiverConfig` — `receiver:`

```python
class ReceiverConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8300
    public_url: str | None = None
    traces_dir: str
    quarantine_dir: str | None = None

    @property
    def base_url(self) -> str: ...

    @property
    def resolved_quarantine_dir(self) -> str: ...
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | where the callback endpoint listens |
| `port` | `int` | `8300` | its port |
| `public_url` | `str \| None` | `None` | the URL the gateway posts callbacks to when it differs from `http://<host>:<port>` |
| `traces_dir` | `str` | required | where accepted results are written — no default, because a `/tmp` default would lose training data silently |
| `quarantine_dir` | `str \| None` | `None` | where rejected results go; `resolved_quarantine_dir` is `<traces_dir>/quarantine` when unset |

`base_url` follows the same rule as `RolloutConfig.base_url`; the rendered `callback_url` is `<base_url>/callbacks/session_result`.

### `render_topology`

```python
def render_topology(cfg: RunConfig) -> dict[str, Any]: ...
```

Returns a dict with two keys, `rollout` and `gateway` (the latter holding `heartbeat_interval_seconds` and a one-element `nodes` list) — the content of Polar's `topology.yaml`. The `rollout` mapping carries `host` and `port`, plus `public_url` and `save_dir` only when set; the single node carries `id`, `host`, `port`, `public_url`, `model_served` (from `estate.model`), `inference: {engine, base_url}` (the engine kind and `estate.serving_base_url`), and the three worker limits. Never raises on a valid `RunConfig`.

```python
import yaml
from gsj_rollout.config import render_topology

Path("topology.rendered.yaml").write_text(yaml.safe_dump(render_topology(cfg)))
```

### `render_task_request`

```python
def render_task_request(
    cfg: RunConfig,
    *,
    task_id: str,
    instruction: str,
    case_id: str,
    timestep: int,
    episodes: int = 1,
    timeout_seconds: float = 900.0,
    prompt_source: str = "free",
    skill_card_text: str | None = None,
    split: str | None = None,
) -> dict[str, Any]: ...
```

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `cfg` | `RunConfig` | required | the loaded YAML |
| `task_id` | `str` | required | your identifier for the task; Polar echoes it on every session |
| `instruction` | `str` | required | the prompt text the agent receives |
| `case_id` | `str` | required | the corpus case |
| `timestep` | `int` | required | the page cutoff; coerced with `int()` |
| `episodes` | `int` | `1` | `num_samples` — attempts Polar schedules, not accepted traces |
| `timeout_seconds` | `float` | `900.0` | Polar's per-task timeout |
| `prompt_source` | `str` | `"free"` | `"free"` or `"skill:<name>"`; written to `metadata.prompt_source` for `G1` |
| `skill_card_text` | `str \| None` | `None` | the card's text; its UTF-8 SHA-256 becomes `metadata.skill_card_hash`. Only valid with a `skill:` source; omitting it leaves `G1` to fail closed |
| `split` | `str \| None` | `None` | `"train"` or `"eval"`, written to `metadata.split`; `None` omits the key |

| | |
|---|---|
| Returns | the `TaskRequest` dict: `task_id`, `instruction`, `num_samples`, `timeout_seconds`, `metadata`, `runtime`, `agent` (`import_path`, `model_name`, `settings`), `builder` (`strategy`, `config`), `callback_url` |
| Raises | `ValueError` — `prompt_source must be 'free' or 'skill:<name>', got ...`; `skill_card_text is only valid with a skill: prompt_source`; `skill_card_text must be non-empty text`; `skill_card_text is not UTF-8-encodable`; and, for a `split` outside the two values, a message naming the value |

```python
from pathlib import Path
from gsj_rollout.config import render_task_request

card = Path("skills/drafting.md").read_bytes().decode("utf-8")
request = render_task_request(
    cfg,
    task_id="case_0004-t13-000",
    instruction="Draft the response to the claimant's letter of 3 March.",
    case_id="case_0004",
    timestep=13,
    episodes=4,
    prompt_source="skill:drafting",
    skill_card_text=card,
    split="train",
)
```

### `COLLECT_SEMANTICS`

```python
COLLECT_SEMANTICS: str
```

A short plain-text statement of what "collected" means, appended to the module docstring and printed as the epilog of `gsj-rollout submit --help`: a session counts only when its status is `COMPLETED`, the builder recorded no findings, and `checks` returns none; `episodes` is a number of attempts, never a target of accepted traces; a rejected attempt is quarantined with its findings and never retried, and `gsj-rollout submit` exits `1` when it collected fewer than it attempted.

## See also

- [Trainer quickstart](../getting-started/trainer-quickstart.md) — the first end-to-end submit and collect.
- [Running a training loop](../guides/training-loop.md) — `RolloutClient` inside a real loop.
- [Finding vocabulary](findings.md) — every string `checks` can return.
- [Wire formats](wire-formats.md) — the `TaskRequest`, the `SessionResult`, and the on-disk files.
