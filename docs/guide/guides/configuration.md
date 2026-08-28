[Documentation](../README.md) › Guides

# Configuration

Everything the rollout server and the trainer need lives in one YAML file, loaded by `gsj_rollout.load_config`. This page is the complete reference for that file: every section, every field with its type and exact default, the six values you must supply, what the loader rejects and with which message, what the server renders from it (Polar's topology) versus what the trainer renders from it (each `TaskRequest`), how the `checks` section becomes a `CheckPolicy`, and a fully annotated example.

## One file, two readers

The same file is read on both sides of the wire, and both sides start the same way:

```python
from gsj_rollout import load_config, RunConfig

cfg: RunConfig = load_config("rollout.yaml")   # raises ValueError on anything wrong
```

`load_config` parses the YAML, validates it into a pydantic `RunConfig`, and — as a side effect — rebinds the process-wide check policy from the `checks` section (see [From `checks` to `CheckPolicy`](#from-checks-to-checkpolicy)). What happens next depends on who called it:

| Reader | Entry point | Sections consumed | Output |
|---|---|---|---|
| Server (`gsj-rollout serve`) | `render_topology(cfg)` | `polar.rollout`, `polar.gateway`, `polar.heartbeat_interval_seconds`, `estate.model`, `estate.serving_base_url` | `topology.rendered.yaml`, next to the config — Polar's own config file, never hand-maintained |
| Server (`gsj-rollout serve`) | `Receiver(host, port, traces_dir, quarantine_dir)` | `receiver.*` | the callback endpoint that validates and files every trace |
| Trainer (`gsj-rollout submit`, your loop) | `render_task_request(cfg, ...)` | `estate.*`, `runtime.*`, `harness.*`, `builder.*`, `receiver.base_url` | one Polar `TaskRequest` per task triple |
| Trainer | `RolloutClient(cfg.polar.rollout.base_url)` | `polar.rollout` | where to submit, wait and collect |
| Both | `load_config` itself | `checks.*` | `checks.DEFAULT_POLICY` — the receiver validates with it at the source, the trainer re-runs `checks.validate_session_result` with it on every collected result |
| Nobody | — | `user` | round-trips into `cfg.user`, never rendered anywhere |

![A document labelled rollout.yaml with nine section stripes in the middle; arrows run left from polar.gateway, polar.rollout and estate to a topology.rendered.yaml tile and from receiver to a receiver tile in the SERVER lane; arrows run right from polar.rollout to a RolloutClient tile and from estate, receiver, runtime, harness and builder to a TaskRequest tile in the TRAINER lane; the user stripe is greyed out as never read; the checks stripe points down to a CheckPolicy bar spanning both lanes](../img/config-map.png)

<sub>Who reads which section: the server side renders `topology.rendered.yaml` from `polar.gateway`, `polar.rollout`, `estate.model` and `estate.serving_base_url` and starts the receiver from `receiver.*`; the trainer side posts through `RolloutClient` at `polar.rollout.base_url` and renders every `TaskRequest` from `estate`, `runtime`, `harness`, `builder` and (dashed, as `callback_url`) `receiver.base_url`; `checks` binds the `CheckPolicy` on both sides; `user` is read by nobody. A star marks a value with no default — four in `estate`, one each in `polar.gateway` and `receiver`.</sub>

Because both sides begin with `load_config`, a wrong file fails on both sides at load — unknown keys, gutted sections, the `/v1` suffix, a port mismatch, a bad thinking level — before any process starts (see [Validation at load](#validation-at-load)). Every field that is not starred carries the value the reference estate measured with, so a file holding only the six required values is complete.

> [!NOTE]
> **Nothing in this file assumes Docker**
>
> `runtime.backend` is a value, not an assumption. The library talks to Polar's runtime interface (start / stop / exec / upload / download) and never to a container engine directly, so a different backend is a configuration change on the estate side.

## The six required values

Every field in the file has a working default except these six. A file containing only them is a complete, loadable configuration:

```yaml
estate:
  clone_url_for: "http://git.example:3000/gsj/{case_id}.git"
  mcp_url_base: "http://mcp.example:8790"
  serving_base_url: "http://127.0.0.1:8000"
  model: Qwen/Qwen3-0.6B
polar:
  gateway:
    public_url: "http://192.0.2.1:8100"
receiver:
  traces_dir: /data/traces
```

| Value | Why it has no default |
|---|---|
| `estate.clone_url_for` | Your git host. Episode containers clone it **themselves**, so it must resolve from inside the sandbox network, not only from the host. |
| `estate.mcp_url_base` | Your retrieval service, again sandbox-reachable. |
| `estate.serving_base_url` | Your inference engine's root URL, as the gateway sees it. |
| `estate.model` | Must equal the engine's served model name byte-for-byte. |
| `polar.gateway.public_url` | One URL reachable from host dispatch **and** from inside episode containers — a LAN IP or the estate network's gateway IP, never localhost. |
| `receiver.traces_dir` | Where the training data lands. A `/tmp` default would lose it silently, so you choose durable storage explicitly. |

Everything else defaults to the value the reference estate measured with; the tables below state each one.

## Section reference

Types are the pydantic annotations in `config.py`. Every section forbids unknown keys.

### `estate`

The services the operator runs, and the model they serve.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `clone_url_for` | `str` | **required** | Clone URL pattern with a `{case_id}` placeholder. The harness formats it per episode and runs a `--depth 1` clone of branch `timestep-<T>` inside the sandbox. |
| `mcp_url_base` | `str` | **required** | Root URL of the retrieval service; the harness appends `/mcp/<token>` with a per-episode signed token. |
| `mcp_token_secret_env` | `str` | `"GSJ_MCP_TOKEN_SECRET"` | Name of the environment variable holding the HMAC secret for those tokens. It is read by the harness, which runs inside Polar's **gateway** process — so the variable must be set on `serve_gateway`, and must equal the retrieval service's own secret. |
| `serving_base_url` | `str` | **required** | The engine root the gateway proxies to. **No `/v1` suffix** — Polar's proxy appends `/v1/chat/completions` itself; the loader rejects the suffixed form. |
| `provider` | `str` | `"gsj"` | pi's provider key. The rendered `agent.model_name` is `"<provider>/<model>"`. |
| `model` | `str` | **required** | The served model name; goes into topology as `model_served` and into every `TaskRequest` as part of `model_name`. |
| `model_revision` | `str \| None` | `None` | Optional in-band pin: the served snapshot's revision (e.g. the Hugging Face commit sha). The server never reads it; a trainer can verify it against the engine before spending GPU time. |

### `runtime`

Passed through verbatim as `TaskRequest.runtime`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `backend` | `str` | `"docker"` | Polar runtime backend name. |
| `image` | `str` | `"ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"` | The pinned harness image (node, git, pi 0.83.0). Every measured episode ran this image; an estate that builds its own overrides it here. |
| `network` | `str` | `"bridge"` | The container network. On a compose-based estate this is the compose network name, so episodes can reach the git host and the retrieval service container-to-container. |

### `harness`

How the agent is launched inside the sandbox. All of it rides `TaskRequest.agent.settings`, except `import_path`, which becomes `TaskRequest.agent.import_path`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `import_path` | `str` | `"gsj_rollout.pi_harness:PiHarness"` | The harness class Polar's gateway imports. |
| `tools_allowlist` | `list[str]`, min 1 item | `[read, ls, grep, find, write, edit, bash, mcp_gsj_search_case, mcp_gsj_search_decisions, mcp_gsj_case_status, mcp_gsj_decision_stats]` | pi's tool roster. The wire `tools` array is hashed and compared to the approved set, so any other roster fails `G3:tool_roster_hash_not_approved` until you re-pin (see [Pins and approved sets](../concepts/pins.md)). |
| `artifacts_dir` | `str` | `"/tmp/gsj-artifacts"` | **Host-side** directory written by the gateway process after each session: pi's transcript and `<workdir>/out` land under `<artifacts_dir>/<session_id>/`. Point it somewhere durable for real runs. |
| `workdir` | `str` | `"/workspace"` | In-image checkout path. The approved system-prompt hash (G2) was pinned with `/workspace`; changing it means re-pinning. |
| `context_window` | `int` | `32768` | pi's `contextWindow` model setting. |
| `max_tokens` | `int` | `8192` | pi's `maxTokens` model setting. |
| `thinking` | `str` | `"off"` | pi's `--thinking` level: one of `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Validated at load — see below. A non-`off` level needs the thinking-on pins (`pins/thinking-on/pins.gsj.json`, selected with `GSJ_PINS_PATH`) on **both** sides, or the tail check (G6) fails every episode, loudly and by design. |
| `pi_entry` | `str \| None` | `None` | Override for pi's entry script inside the image; only rendered when set. |
| `pi_mcp_extension` | `str \| None` | `None` | Override for the MCP extension path inside the image; only rendered when set. |
| `mcp_token_ttl_s` | `int` | `3600` | Lifetime of the per-episode retrieval token. |

> [!WARNING]
> **`thinking: off` is safe, `thinking: on` is rejected**
>
> The YAML parser is YAML 1.1, so bare `off`/`on` (and `no`/`yes`/`true`/`false`) arrive as booleans. `False` is normalised to `"off"`; a truthy bool becomes `"on"` and is rejected by name, because pi silently clamps any unknown level to `off` — a typo would collect a thinking-off control run under a thinking-on label. Every non-`off` level is wire-equivalent under the served chat template; `medium` is the conventional "on".

### `builder`

Trajectory reconstruction. `strategy` becomes `TaskRequest.builder.strategy`; the rest becomes `TaskRequest.builder.config`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `strategy` | `str` | `"gsj_rollout.builder:ValidatingPrefixMergingBuilder"` | The builder class Polar loads by import-path string. |
| `end_of_turn_token_id` | `int` | `151645` | The end-of-turn token id under the **served** tokenizer; `151645` is `<|im_end|>` for Qwen3. Always rendered as an explicit pin, never auto-detected. Re-derive when `estate.model` changes: `tokenizer.convert_tokens_to_ids("<|im_end|>")` (or your template's end-of-turn token). |
| `generation_prompt_glue_ids` | `list[int] \| None` | `None` | Template-specific glue tokens the builder stitches between merged prefixes. Only needed under an asymmetric chat template; omitted from the render when `None`. |

### `checks`

A one-to-one mirror of `checks.CheckPolicy`, defaults read from it (a test enforces that the mirror is complete). See [From `checks` to `CheckPolicy`](#from-checks-to-checkpolicy).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `sentinel_threshold` | `float` | `-9000.0` | A logprob at or below this value on a trainable (`loss_mask == 1`) position is a sentinel, not a probability → `LP3:sentinel_logprob_at_mask1`. |
| `zero_at_mask1_max_rate` | `float` | `0.25` | Maximum fraction of trainable positions whose logprob is exactly `0.0` → `LP6:zero_logprob_rate_at_mask1:<zeros>/<trainable>><rate>`. Set `0.0` for an engine that must never emit exact zeros. |
| `reject_toolless_roster` | `bool` | `False` | When `True`, a trace that was offered a non-empty tool roster yet never made a tool call is rejected → `H41:roster_offered_zero_tool_calls`. Off by default: such a trace is admitted. |

### `polar`

What Polar's two processes need. `rollout` and `gateway` are the two halves of `topology.yaml`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `heartbeat_interval_seconds` | `int` | `30` | Rendered into `gateway.heartbeat_interval_seconds`. |
| `rollout` | section | all defaulted | The rollout API process — see below. |
| `gateway` | section | `public_url` required | The single gateway node — see below. |

#### `polar.rollout`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | Bind address of the rollout API. |
| `port` | `int` | `8080` | Its port. |
| `public_url` | `str \| None` | `None` | Advertised URL; rendered into topology only when set. |
| `save_dir` | `str \| None` | `None` | Polar's own save directory; rendered only when set. |
| `base_url` *(property)* | `str` | — | `public_url`, else `http://<host>:<port>` with `0.0.0.0`/`::` rewritten to `127.0.0.1`. This is where `submit` and `RolloutClient` post. |

#### `polar.gateway`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` | `str` | `"gsj-node-01"` | Node id in topology. |
| `host` | `str` | `"0.0.0.0"` | Bind address of the gateway. |
| `port` | `int` | `8100` | Its port. Must agree with the port `public_url` advertises. |
| `public_url` | `str` | **required** | The URL both host dispatch and episode containers dial. Must carry an `http://` or `https://` scheme. |
| `engine` | `str` | `"vllm"` | Rendered as `inference.engine`. |
| `max_init_workers` | `int` | `4` | Polar worker pool sizes, passed through. |
| `max_run_workers` | `int` | `2` | |
| `max_postrun_workers` | `int` | `4` | |

### `receiver`

The callback endpoint this library runs. The receiver binds `host:port`; the trainer's rendered `callback_url` is `<base_url>/callbacks/session_result`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | Bind address. |
| `port` | `int` | `8300` | Port. |
| `public_url` | `str \| None` | `None` | Advertised URL when the bind address is not what Polar should dial. |
| `traces_dir` | `str` | **required** | Where accepted traces are filed. |
| `quarantine_dir` | `str \| None` | `None` | Where rejected traces go with their findings; defaults to `<traces_dir>/quarantine`. |
| `base_url` *(property)* | `str` | — | `public_url`, else `http://<host>:<port>` with `0.0.0.0`/`::` rewritten to `127.0.0.1`. |
| `resolved_quarantine_dir` *(property)* | `str` | — | `quarantine_dir` or `<traces_dir>/quarantine`. |

> [!TIP]
> **The callback must be dialable by Polar**
>
> `callback_url` is built from `receiver.base_url`. If the receiver binds `0.0.0.0` on one machine and Polar's processes run on another, set `receiver.public_url` — otherwise the render advertises `127.0.0.1`.

### `user`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `user` | `dict[str, Any]` | `{}` | Reserved, free-form. Anything you put here round-trips into `cfg.user` and is never read by the library, never rendered into topology or a `TaskRequest`. Must be a mapping (a list is rejected); a gutted `user:` header loads as `{}`. |

## Validation at load

`load_config` raises `ValueError` — never a pydantic exception — and lists **every** failing field in one message:

```
config <path> invalid — 'section.field': <message>; section '<section>': unknown key '<key>'
```

The load is four steps, and only two of them can reject:

1. **Parse** — `yaml.safe_load`; the result must be a mapping. A parse error or a non-mapping top level raises its own `ValueError` (the two messages at the end of this section) before any validation runs.
2. **Normalise null sections** — `_null_sections_to_empty` turns a section that parsed as `null` (a header with only comments under it) into `{}`, so pydantic can name the missing fields instead of rejecting the section as a whole; the dict-typed `user:` gets the same treatment.
3. **Validate** — `RunConfig.model_validate`, with `extra="forbid"` on every section plus the field and model validators below. Every failure is collected and reported in the single `ValueError` above, `; `-joined.
4. **Bind the policy** — on success, `checks.DEFAULT_POLICY` is rebuilt from the `checks` section and the `RunConfig` is returned.

![A rollout.yaml document tile feeding a four-step chevron strip — parse YAML, null to empty mapping, validate, bind CheckPolicy — that ends in a green RunConfig tile; red arrows drop from step 1 to a reject tile for not-YAML or not-a-mapping and from step 3 to a reject tile for one ValueError listing every failing field](../img/config-validators.png)

<sub>The load pipeline: parsing rejects on its own, validation rejects with one `ValueError` that lists every failing field, and a file that passes leaves with the `CheckPolicy` already rebound.</sub>

Five validators exist specifically to catch files that are schema-plausible but would fail later as a bare 404, a connection refused, or a mislabelled run:

![Five red cards in a row, each with an emblem — a /v1 badge for serving_base_url ending in /v1, a not-equal sign for gateway port versus public_url port, an on badge for a thinking value that is not a pi level, a question mark for an unknown key, a hash sign for a section gutted to comments — all pointing down to one bar reading rejected at load, one ValueError](../img/config-traps.png)

<sub>The five look-right-but-fail files, each with the input that triggers it; the table below gives the message each one produces.</sub>

| Check | Trigger | Message (leading text, verbatim) |
|---|---|---|
| `/v1` suffix | `estate.serving_base_url` ends in `/v1` or `/v1/` | `'estate.serving_base_url': Value error, must not end in /v1 — Polar's proxy appends /v1/chat/completions itself …` (the message goes on to name the engine root to use, e.g. `http://127.0.0.1:8000`) |
| Gateway scheme | `polar.gateway.public_url` has no `http://` / `https://` | `'polar.gateway': Value error, public_url '192.0.2.1:8100' needs an explicit http:// or https:// scheme — without one the URL cannot be dialed and its port cannot be read` |
| Gateway port | the port `public_url` advertises (explicit, else 80/443 by scheme) differs from `polar.gateway.port` | `'polar.gateway': Value error, public_url advertises port 9100 but the gateway listens on port 8100 — one fact, two keys; set public_url's port to :8100 or set gateway.port to 9100 (a mismatch means connection-refused on the advertised URL at the first dispatch)` |
| Thinking level | `harness.thinking` not in `off\|minimal\|low\|medium\|high\|xhigh\|max` (bare YAML `on` included; bare `off` is accepted) | `'harness.thinking': Value error, 'on' is not a pi thinking level — use one of off\|minimal\|low\|medium\|high\|xhigh\|max; pi silently clamps any other value to 'off' …` |
| Unknown key | any key not in the section's model; the top level counts as `<root>` | `section 'estate': unknown key 'clone_pattern'` |
| Null section | a section whose body is only comments parses as YAML `null`; it is normalised to `{}` before validation so the missing fields are named | `'polar.gateway.public_url': Field required` (and for `estate:` gutted whole, all four required fields, `; `-joined) |

Ordinary pydantic messages surface the same way: `'receiver.traces_dir': Field required`, `'harness.max_tokens': Input should be a valid integer, unable to parse string as an integer`, `'harness.tools_allowlist': List should have at least 1 item after validation, not 0`, `'user': Input should be a valid dictionary`.

Two failures happen before validation and carry their own text: `config <path>: invalid YAML: <parser error>` and `config <path> must contain a top-level mapping`.

> [!NOTE]
> **Why reject instead of repair**
>
> The port validator could derive one key from the other; it refuses to, because silently rewriting either key would hide the typo it exists to catch. The same reasoning applies to `/v1` and to `thinking`: the wrong value is close enough to a right one that a quiet fix would mask a real mistake.

## What the server renders: topology

`gsj-rollout serve --config <yaml>` writes `topology.rendered.yaml` beside the config and prints the two Polar commands that consume it — Polar's processes are started by the operator, not by the library. `--render-only` stops after printing.

```bash
gsj-rollout serve --config estate/rollout.h200.yaml --render-only
# topology rendered: /…/estate/topology.rendered.yaml — run Polar's two processes yourself:
#   PYTHONPATH=/…/checkout /…/checkout/vendor/polar/.venv/bin/polar serve_rollout -c /…/estate/topology.rendered.yaml
#   GSJ_MCP_TOKEN_SECRET=<secret> PYTHONPATH=/…/checkout /…/checkout/vendor/polar/.venv/bin/polar serve_gateway -c /…/estate/topology.rendered.yaml
# callbacks: http://127.0.0.1:8300/callbacks/session_result | traces -> /home/sysadmin/cp04prime/traces | quarantine -> /home/sysadmin/cp04prime/traces/quarantine
```

The paths are absolute and point at the checkout the command ran from. An installed wheel ships no `vendor/polar`; there the output adds a `NOTE:` line saying so and prints `<checkout>` in place of the paths — clone the repository, provision `vendor/polar/.venv` per `vendor/REVENDOR.md`, and substitute.

The mapping is fixed:

| Topology key | Source |
|---|---|
| `rollout.host`, `rollout.port` | `polar.rollout.host`, `.port` |
| `rollout.public_url`, `rollout.save_dir` | `polar.rollout.public_url`, `.save_dir` — only when set |
| `gateway.heartbeat_interval_seconds` | `polar.heartbeat_interval_seconds` |
| `gateway.nodes[0].id`, `.host`, `.port`, `.public_url` | `polar.gateway.id`, `.host`, `.port`, `.public_url` |
| `gateway.nodes[0].model_served` | `estate.model` |
| `gateway.nodes[0].inference.engine` | `polar.gateway.engine` |
| `gateway.nodes[0].inference.base_url` | `estate.serving_base_url` |
| `gateway.nodes[0].max_init_workers`, `.max_run_workers`, `.max_postrun_workers` | `polar.gateway.max_*_workers` |

Rendered from the test fixture (`tests/fixtures/rollout.yaml`), the output is exactly `tests/golden/topology.yaml`:

```yaml
rollout:
  host: 127.0.0.1
  port: 8080
gateway:
  heartbeat_interval_seconds: 30
  nodes:
  - id: gsj-node-01
    host: 0.0.0.0
    port: 8100
    public_url: http://192.168.0.158:8100
    model_served: Qwen/Qwen3-0.6B
    inference:
      engine: vllm
      base_url: http://127.0.0.1:8021
    max_init_workers: 4
    max_run_workers: 2
    max_postrun_workers: 4
```

`render_topology(cfg)` is a plain function returning that mapping, so you can call it yourself. The secret named by `estate.mcp_token_secret_env` never appears in topology — it is read from the gateway process's environment at episode time.

## What the trainer renders: TaskRequest

`render_task_request` turns the config plus one task triple into the JSON body `RolloutClient.submit` posts. The full wire shape is documented in [Wire formats](../reference/wire-formats.md); this section covers which config fields land where.

```python
from gsj_rollout import load_config
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")
request = render_task_request(
    cfg,
    task_id="gsj-task",
    instruction="Summarize the case.",
    case_id="case_0001",
    timestep=12,
    episodes=1,                 # → num_samples: attempts, not accepted traces
    timeout_seconds=900.0,
    prompt_source="free",       # or "skill:<name>"
    skill_card_text=None,       # only with a skill: source; hashed into metadata
    split=None,                 # "train" | "eval" | None (unstated)
)
```

| `TaskRequest` key | Source |
|---|---|
| `task_id`, `instruction`, `num_samples`, `timeout_seconds` | the call arguments (`episodes` → `num_samples`) |
| `metadata.case_id`, `.timestep`, `.prompt_source` | the call arguments; `.skill_card_hash` when card text is given, `.split` when stated |
| `runtime.backend`, `.image`, `.network` | `runtime.*` |
| `agent.import_path` | `harness.import_path` |
| `agent.model_name` | `"<estate.provider>/<estate.model>"` |
| `agent.settings.case_id`, `.timestep` | the call arguments |
| `agent.settings.clone_url_for`, `.mcp_url_base`, `.mcp_token_secret_env` | `estate.*` |
| `agent.settings.mcp_token_ttl_s`, `.tools_allowlist`, `.artifacts_dir`, `.workdir`, `.context_window`, `.max_tokens`, `.thinking` | `harness.*` |
| `agent.settings.pi_entry`, `.pi_mcp_extension` | `harness.*`, only when set |
| `builder.strategy` | `builder.strategy` |
| `builder.config.end_of_turn_token_id` | `builder.end_of_turn_token_id` — always present |
| `builder.config.generation_prompt_glue_ids` | `builder.generation_prompt_glue_ids` — only when not `None` |
| `callback_url` | `f"{receiver.base_url}/callbacks/session_result"` |

The render validates its own arguments: `prompt_source` must be `"free"` or `"skill:<name>"`, `skill_card_text` is only legal with a skill source and must be non-empty text, and `split` must be `"train"`, `"eval"` or `None`. Polar's reserved metadata keys (`session_id`, `task_id`, `evaluation`, `policy_version`) are never written.

> [!NOTE]
> **`--from-bank` checks the image**
>
> When submitting a taskbank row, the CLI refuses a row whose `sandbox_image` differs from `runtime.image`: the render always reads the config's image, so a mismatch would run the wrong one. See [Command line](cli.md).

## From `checks` to `CheckPolicy`

`checks.CheckPolicy` is a frozen dataclass of three knobs; `ChecksConfig` mirrors it field for field with the same defaults. On every successful load:

```python
checks.DEFAULT_POLICY = checks.CheckPolicy(**cfg.checks.model_dump())
```

`validate_session_result(result)` and the other entry points resolve `DEFAULT_POLICY` at call time, so the knob turns without touching the receiver or the client — the receiver picks it up because `serve` loaded the file, the trainer picks it up because it loaded the same file before collecting. The last `load_config` in a process wins.

```yaml
checks:
  zero_at_mask1_max_rate: 0.0     # an engine that must never emit exact-0.0 logprobs
  reject_toolless_roster: true    # reject a trace that had tools and called none
```

Untouched fields keep the `CheckPolicy` defaults. How each knob feeds the validators is described in [Validation](../concepts/validation.md) and the [finding vocabulary](../reference/findings.md); the rule reasoning is in the [checks spec](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

> [!WARNING]
> **Same file, both sides**
>
> Because the receiver drops bad traces at the source and the trainer re-verifies what arrived with the same code, the two sides must load the same `checks` section. A stricter trainer will reject on collect (`submit` prints the findings and drops the result) what the receiver already accepted and filed.

## Annotated example: `estate/rollout.h200.yaml`

The repository ships the reference estate's file. It runs Polar's processes, the receiver and submission on one host, with the estate's services on a compose network. Values are the host-bound facts; the code is the same everywhere.

```yaml
estate:
  clone_url_for: "http://172.28.9.10:3000/gsj-staging/{case_id}.git"   # (1)
  mcp_url_base: "http://172.28.9.1:8790"                                # (2)
  mcp_token_secret_env: GSJ_MCP_TOKEN_SECRET                            # (3)
  serving_base_url: "http://127.0.0.1:8000"                             # (4)
  provider: gsj
  model: Qwen/Qwen3-0.6B                                                # (5)

runtime:
  backend: docker
  image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3
  network: gsj-staging-net                                              # (6)

harness:
  tools_allowlist:
    [read, ls, grep, find, write, edit, bash,
     mcp_gsj_search_case, mcp_gsj_search_decisions,
     mcp_gsj_case_status, mcp_gsj_decision_stats]                       # (7)
  artifacts_dir: /home/sysadmin/cp04prime/artifacts                     # (8)
  workdir: /workspace
  context_window: 32768
  max_tokens: 8192
  thinking: "off"                                                       # (9)

builder:
  strategy: gsj_rollout.builder:ValidatingPrefixMergingBuilder
  end_of_turn_token_id: 151645                                          # (10)
  # generation_prompt_glue_ids: deliberately unset                      # (11)

checks:
  zero_at_mask1_max_rate: 0.25                                          # (12)

polar:
  rollout:
    host: 127.0.0.1
    port: 8080
  gateway:
    id: gsj-node-01
    host: 0.0.0.0
    port: 8200                                                          # (13)
    public_url: "http://172.28.9.1:8200"
    engine: vllm

receiver:
  host: 127.0.0.1
  port: 8300
  traces_dir: /home/sysadmin/cp04prime/traces                           # (14)
```

1. The git host's static container IP on the compose network. Episode containers clone this themselves, so the address must work container-to-container; a host-only address costs an episode before the failure is visible.
2. The retrieval service is host-bound, so it is addressed by the compose network's gateway IP. Polar's Docker runtime passes only `--network` (no `--add-host`), so `host.docker.internal` does not resolve inside episode containers on this Linux host.
3. The default, stated explicitly. The gateway process must have this variable set, and its value must match the retrieval service's secret.
4. The engine root, host-local: only the gateway talks to it. No `/v1` — the loader rejects the suffixed form.
5. Byte-equal to the engine's `--served-model-name`.
6. The value that puts episodes on the compose network, where the git host's container IP is reachable. On the default bridge, inter-network isolation blocks it.
7. The default roster, written out for visibility. Any other roster fails the tool-roster hash gate until re-pinned.
8. Host-side and durable: the gateway writes transcripts and deliverables here; a reward grader reads them.
9. Quoted so the YAML 1.1 parser does not turn it into a boolean (a bare `off` would still load as `"off"`, but quoting makes the intent explicit).
10. `<|im_end|>` under the served Qwen3 tokenizer. Re-derive if `model` changes.
11. The served chat template is symmetric, so consecutive prompts stay prefix-stable and Polar's merging needs no glue; the stitch path stays dormant.
12. The default, stated so the estate's policy is visible: this engine emits exact-`0.0` logprobs at roughly 14 % of trainable positions in bf16, well under the allowance.
13. `port` and `public_url` agree on `8200` — the validator requires it. `172.28.9.1` is both host-local and reachable from episode containers, so one URL serves dispatch and the sandbox.
14. Durable storage for the training data; quarantine defaults to `traces_dir/quarantine`.

## See also

- [Server quickstart](../getting-started/server-quickstart.md) — bringing up the receiver and Polar with this file.
- [Trainer quickstart](../getting-started/trainer-quickstart.md) — submitting with the same file from the training side.
- [The estate](estate.md) — the services these values point at.
- [Wire formats](../reference/wire-formats.md) — the full `TaskRequest` and callback bodies.
- [Python API](../reference/api.md) — `load_config`, `RunConfig`, `render_topology`, `render_task_request`.
