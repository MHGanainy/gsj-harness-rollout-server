[Documentation](../README.md) › Guides

# Troubleshooting

Every failure in this system surfaces in one of four places: at `submit` (an exit code and a line on stderr), at `serve` (a line on stdout or a warning at import), inside the episode (the gateway process log, and a session that arrives with `status: "ERROR"`), or at the callback (a finding in a quarantine file). This page is organised by where the failure surfaces. For each symptom it gives the exact message the code emits, what that message means, and the fix — including the three networking traps that cost episodes on a real estate.

![Three lanes — at submit, at the receiver, in the episode — each holding red symptom tiles over the one place to look: exit 2 over the YAML or the flags, exit 3 over Polar's rollout API, exit 1 over the quarantine file, HTTP 500 over the pins file, and a session ERROR over the sandbox setup (image, network, URL, secret)](../img/triage-tree.png)

<sub>Where the failure surfaced says where to look: the `submit` exit code points at the config, the rollout API, or the quarantine file; the receiver's 500 at the pins file; a session `ERROR` at the sandbox setup. The messages behind each tile are in the sections below.</sub>

## Where to look first

| Where it surfaced | What you see | Section |
|---|---|---|
| `gsj-rollout submit` exits **2** | `gsj-rollout: config <path> invalid — …` or a usage line on stderr | [Exit 2](#exit-2--config-or-usage-error) |
| `gsj-rollout submit` exits **3** | `gsj-rollout: rollout server unreachable or errored at <url>: …` | [Exit 3](#exit-3--the-rollout-api-is-unreachable-or-errored) |
| `gsj-rollout submit` exits **1** | `rejected <session_id>: [...]` then `collected n/N episodes` with n < N, or `task <id> not terminal after <t>s` | [Exit 1](#exit-1--collected--attempted) |
| `gsj-rollout serve` | a `NOTE:` line, a `UserWarning` at import, or nothing landing on disk | [At serve](#at-serve) |
| The receiver answers **500** | `{"error": "pins configuration: …"}` in Polar's log | [Receiver 500](#the-receiver-answers-500) |
| The episode never starts | `Agent execution failed for session …` in the gateway log; the session arrives `ERROR` with `traces: []` | [During the episode](#during-the-episode) |
| A finding you do not recognise | one token of the vocabulary in a quarantine file | [Findings by family](#at-the-callback-findings-by-family) |

The exit codes are documented in `gsj-rollout submit --help`: `0` all collected; `1` not all collected (rejected, errored, or timed out); `2` config or usage error; `3` server unreachable or HTTP error.

## At `submit`

### Exit 2 — config or usage error

Nothing was started. The YAML did not load, or the flags did not make a task.

`load_config` raises one `ValueError` listing **every** failing field, joined by `; `, and the CLI prints it prefixed with `gsj-rollout: `. The leading text of each message, verbatim:

| Symptom (stderr) | Cause | Fix |
|---|---|---|
| `'estate.serving_base_url': Value error, must not end in /v1 — Polar's proxy appends /v1/chat/completions itself …; drop the suffix and point at the engine root, e.g. http://127.0.0.1:8000` | `serving_base_url` ends in `/v1` (or `/v1/`). Left alone it would fail at run time as a 404 on `/v1/v1/chat/completions` that reads like a wrong host. | Point at the engine root: `http://127.0.0.1:8000`. |
| `'polar.gateway': Value error, public_url '172.28.9.1:8200' needs an explicit http:// or https:// scheme — without one the URL cannot be dialed and its port cannot be read` | `public_url` has no scheme. A scheme-less `IP:port` parses as a path, so the port check would misread it. | Write `http://172.28.9.1:8200`. |
| `'polar.gateway': Value error, public_url advertises port 8100 but the gateway listens on port 8200 — one fact, two keys; set public_url's port to :8200 or set gateway.port to 8100 (a mismatch means connection-refused on the advertised URL at the first dispatch)` | The port in `public_url` (explicit, else 80/443 by scheme) differs from `polar.gateway.port`. | Make the two agree. The loader refuses to derive one from the other, because a silent rewrite would hide the typo. |
| `'harness.thinking': Value error, 'on' is not a pi thinking level — use one of off\|minimal\|low\|medium\|high\|xhigh\|max; pi silently clamps any other value to 'off' …` | `thinking` is not one of pi's level names. A bare YAML `on` arrives as the boolean `True` and is rejected by name; a bare `off` is accepted as `"off"`. | Use `medium` for the conventional ON. Any non-`off` level also needs the thinking-on pins on both legs — see [G6](#g6--the-thinking-tail). |
| `section 'estate': unknown key 'clone_pattern'` | Every section forbids unknown keys; a stray top-level key names section `<root>`. | Fix the spelling, or move free-form data under `user:`. |
| `'polar.gateway.public_url': Field required` | A required value is missing. A section gutted to comments parses as YAML `null` and is normalised to `{}` first, so the message names the field, not the section. | Supply it. The six values with no default are listed in [Configuration](configuration.md#the-six-required-values). |
| `config <path>: invalid YAML: <parser error>` / `config <path> must contain a top-level mapping` | The file did not parse, or parsed to a scalar or list. | Fix the YAML. |
| `gsj-rollout: [Errno 2] No such file or directory: 'rollout.yaml'` | `--config` names a file that does not exist. | Give the right path. |

The usage errors, also exit 2:

| Symptom (stderr) | Fix |
|---|---|
| `gsj-rollout: submit needs --case, --timestep and --prompt/--prompt-file — or --from-bank` | Give all three of `--case`, `--timestep`, and one of `--prompt` / `--prompt-file`; or a `--from-bank` parquet. |
| `gsj-rollout: --from-bank carries the triple itself — drop --case/--timestep/--prompt` | A bank row already holds the triple; do not pass both. |
| `gsj-rollout: --from-bank needs pyarrow (pip install pyarrow); …` | `pyarrow` is not a core dependency. Install it. |
| `gsj-rollout: --row 7 out of range: bank.parquet holds rows 0..4` | `--row` is 0-based. |
| `gsj-rollout: bank.parquet is not an … taskbank: no 'split' column` | The parquet lacks one of the seven taskbank columns (`case_id`, `timestep`, `split`, `prompt_source`, `prompt_text`, `skill_card_text`, `sandbox_image`). |
| `gsj-rollout: bank row wants sandbox_image '…' but runtime.image is '…' — the render reads the config's, so the row would run the wrong image; align the config` | The row was authored against a different image than the YAML's `runtime.image`. Set `runtime.image` to the row's value. |

The full validation reference — including the ordinary pydantic messages such as `'harness.max_tokens': Input should be a valid integer, …` — is in [Configuration → Validation at load](configuration.md#validation-at-load).

### Exit 3 — the rollout API is unreachable or errored

```text
gsj-rollout: rollout server unreachable or errored at http://127.0.0.1:8080: [Errno 61] Connection refused
```

The `try` around `client.submit` and `client.wait` catches every `httpx.HTTPError`: a transport failure *and* any 4xx/5xx reply, on the submit or on any later poll. Two questions settle it:

**Which URL.** The URL in the message is `cfg.polar.rollout.base_url` — `polar.rollout.public_url` if set, otherwise `http://<host>:<port>` with `0.0.0.0`/`::` rewritten to `127.0.0.1`; the default is `http://127.0.0.1:8080`. Nothing else in the config is dialled by `submit`.

**Which process.** That URL belongs to Polar's **rollout API** — the `polar serve_rollout -c topology.rendered.yaml` process that `serve` prints for you to run. Not the gateway (`serve_gateway`, port 8200 on the H200 file), not the receiver (8300), not the engine (8000).

| Tail of the message | Meaning | Fix |
|---|---|---|
| `Connection refused` | Nothing listens at that host:port. | Start `serve_rollout`; or, for a trainer on another machine, bind `polar.rollout.host` to a reachable address and set `polar.rollout.public_url`. |
| `Client error '404 Not Found' for url '…/rollout/task/submit'` | You reached *a* process, but not the rollout API — the receiver answers every unknown path with `{"error": "not found"}`, and so do the gateway and the engine in their own words. | Check the port against the process you meant. |
| `Server error '5xx …'` | The rollout API is up and failed on the request. | Read the `serve_rollout` log. |
| `ReadTimeout` | The rollout API accepted the connection and did not answer within 30 s (`httpx.Client(timeout=30.0)`). | Check the host's load; pass your own `httpx.Client` to `RolloutClient(http=…)` for a longer timeout. |

A quick probe from the trainer host, using the same path the client polls:

```bash
curl -sS -i http://127.0.0.1:8080/rollout/task/does-not-exist | head -1
# HTTP/1.1 404 … from the rollout API is fine — it means the right process answered
# "Connection refused" means it is not running there
```

### Exit 1 — collected < attempted

```text
task gsj-task: 1/1 sessions terminal
rejected ses_a1b2c3: ['ADM1:status_not_completed:ERROR', 'ADM4:no_traces', 'G7:missing_evidence:reconstruction_stats']
collected 0/1 episodes
length-terminated: 0/0 accepted episodes ended finish_reason=length — qualified by design; training on them is the trainer's call …
```

`--episodes N` is N **attempts** (Polar's `num_samples`), not collect-until-N-accepted. A session counts as collected only when its status is `COMPLETED` *and* `checks.validate_session_result` returns no findings. Every rejected session is printed with its findings, and the same list was written by the receiver to the quarantine file — that file is where to look:

```text
<traces_dir>/quarantine/<session_id>.<pins_mode>.json
```

`<pins_mode>` is the pins file's declared mode (`thinking-off` for the reference set, `thinking-on` for the other; `pins-unresolved` if the receiver could not read its pins file at start-up). The body is `{"findings": [...], "session_result":}` — the findings first, then the callback body verbatim, including `status` and `error`.

```python
import json, pathlib

doc = json.loads(pathlib.Path("/data/traces/quarantine/ses_a1b2c3.thinking-off.json").read_text())
print(doc["findings"])                        # ['ADM1:status_not_completed:ERROR', 'ADM4:no_traces', ...]
sr = doc["session_result"]
print(sr["status"], sr.get("error"))          # ERROR  agent execution failed: PiHarness setup failed (rc=128) on 'git': ...
```

The first token of every finding names its family; [Findings by family](#at-the-callback-findings-by-family) below maps each family to a cause. Only the `ADM` family means the episode itself failed — every other family is a completed episode whose trace the validators refused.

![A quarantine file tile, named session_id dot mode dot json, with a big arrow labelled the first token pointing at six red family badges: ADM episode not completed, G1 G2 G3 G7 pins not this estate, G5 cutoff evidence wrong, LP1 to LP9 logprobs not evidence, G6 thinking mode not the pins, H41 no tool was called — each with the place to look](../img/quarantine-families.png)

<sub>The first token of each finding names its family, and the family names the place to look. `findings` come first in the file, then `session_result`; `submit` printed the same list. A `not terminal after <t>s` line is exit 1 too, but the poll gave up before the session finished, so there is no quarantine file for it yet.</sub>

| Family | What it says | Where to look |
|---|---|---|
| `ADM` — `ADM1:status_not_completed:ERROR` or `:TIMEOUT` | the episode did not complete | `session_result.error` in the file, then the gateway log |
| `G1` `G2` `G3` `G7` — `*_not_approved` | the pins file does not describe this estate | `GSJ_PINS_PATH` on both legs, or re-pin |
| `G5` | cutoff evidence from the trace: branch ≠ `timestep-<T>`, pages ≠ 1..T, a page > T | the corpus branch, the retrieval service |
| `LP1`–`LP9` | logprob capture: absent, misaligned, sentinel, zero-rate | the engine's logprobs, the `checks:` policy |
| `G6` — `prompt_suffix_ne_tail_ids` | mode mismatch: `harness.thinking` and `GSJ_PINS_PATH` must agree on **both** legs | the pins file each leg resolves |
| `H41` — `roster_offered_zero_tool_calls` | the agent was offered tools and called none; fires only with `reject_toolless_roster: true` | the retrieval service, from inside the sandbox |

From Python, `RolloutClient.collect` logs rejections at `WARNING` through the `gsj_rollout.client` logger and returns only accepted traces. To see the findings programmatically, use the lower-level pair:

```python
from gsj_rollout import load_config, RolloutClient
from gsj_rollout.client import partition_session_results
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")
client = RolloutClient(cfg.polar.rollout.base_url)
task_id = client.submit(render_task_request(
    cfg, task_id="probe", instruction="Summarise the case file.", case_id="case_0001", timestep=12))
results = client.wait(task_id, timeout_s=1020.0)          # 900 s task timeout + 120 s grace

accepted, rejected = partition_session_results(results)
for result, findings in rejected:
    print(result["session_id"], result["status"], result.get("error"), findings)
```

> [!TIP]
> **The receiver being down does not fail `submit`**
>
> Polar POSTs the terminal task result to `callback_url` best-effort (10 s timeout) and logs `Callback POST to … failed for task …; trainer must fall back to polling` if it cannot. The trainer never reads the receiver's disk — it polls `GET /rollout/task/{id}` and re-runs the same checks — so `submit` still collects. What you lose is the archive: nothing lands in `traces_dir` or `quarantine/`. If `collected` looks right but the directories stay empty, check that `serve` is running and that `receiver.base_url` (the `callbacks:` line `serve` printed) is dialable from the rollout API's host.

#### The poll timed out

```text
gsj-rollout: task gsj-task not terminal after 1020.0s (0/1 sessions)
```

This is `TimeoutError` from `RolloutClient.wait`, exit 1. The task was still `running` when the client's own deadline — `--timeout` plus `--grace`, 900 + 120 s by default — passed. The `(c/N sessions)` count says how many sessions had reached a terminal status. There is no quarantine file for a session that has not finished; Polar's own per-task `timeout_seconds` (the `--timeout` value) is what turns a stuck episode into a `TIMEOUT` session, and that arrives later, as `ADM1:status_not_completed:TIMEOUT`.

If the count is `0/N` after the full window and the gateway log shows no session activity, the rollout API never dispatched — usually because no gateway node registered with it (the gateway was not started, or its `public_url` is not reachable from the rollout API's host; see [public_url must be dialable from both places](#public_url-must-be-dialable-from-both-places)).

## At `serve`

### `NOTE: … does not exist`

`serve` renders `topology.rendered.yaml` next to your config and prints the two Polar commands. When `<checkout>/vendor/polar/.venv/bin/polar` is absent it says which case you are in:

| Line | Meaning |
|---|---|
| `NOTE: … does not exist — this is an installed wheel — no wheel ships vendor/polar; clone https://github.com/MHGanainy/gsj-harness-rollout-server and substitute <checkout>` | You ran `serve` from a pip install. The wheel is the trainer-side package; the server side needs a checkout with Polar's venv built. See [Installation](../getting-started/installation.md#server-role-a-checkout). |
| `NOTE: … does not exist — vendor/polar's venv is unbuilt — provision per vendor/REVENDOR.md's recipe …, then rerun` | The checkout is there but Polar's venv is not. Build it per `vendor/REVENDOR.md`. |

The receiver still starts in both cases; only the printed commands carry a `<checkout>` placeholder.

### The pins `UserWarning` at import

```text
UserWarning: gsj_rollout.checks: /…/site-packages/gsj_rollout/pins/pins.gsj.json holds the REFERENCE ESTATE's approved sets, not defaults — set GSJ_PINS_PATH to your own or every hash gate fails *_not_approved.
```

Emitted once, at the first import of `gsj_rollout.checks`, whenever resolution falls through to the packaged copy with `GSJ_PINS_PATH` unset. It is correct for a trainer talking to the reference estate and a trap for anyone else: the packaged pins describe one estate's tool roster, system prompt, skill cards, settings, and chat-template tail, and every hash gate will reject traces from a different one. Set `GSJ_PINS_PATH` in the environment of **every process that imports `gsj_rollout`** — the receiver (`serve`) and the trainer — before the first import. The resolution order, the file format, and how to derive your own file are in [Pins and approved sets](../concepts/pins.md).

### `PinsConfigurationError`

`checks.approved_set` raises `PinsConfigurationError` — never a finding — when the pins file it resolved cannot be used:

| Message | Cause |
|---|---|
| `pins file /etc/gsj/pins.gsj.json unusable: FileNotFoundError(2, 'No such file or directory')` | `GSJ_PINS_PATH` points at a missing, unreadable, or non-JSON file, or a file without a top-level `pins` key. A wrong override does **not** fall back to the packaged copy, by design. |
| `pins key 'tool_roster_hash' missing, empty, or not a list in /etc/gsj/pins.gsj.json` | The file parsed but the key a gate needs is absent, empty, or a string instead of a list (a string would make membership a substring test — a fail-open). |

The error surfaces on first use, not at import, and on both legs:

- **Receiver:** the callback answers 500 — see [the receiver answers 500](#the-receiver-answers-500).
- **Trainer:** `partition_session_results` (and so `RolloutClient.collect` and `gsj-rollout submit`) raises; the CLI does not catch it, so you see a traceback ending in `gsj_rollout.checks.PinsConfigurationError: …` rather than an exit-code line.

> [!WARNING]
> **Pins are cached for the life of the process**
>
> The file is read on the first `approved_set()` call and never again. Fixing the file or the variable takes effect on restart — of the receiver *and* of the trainer.

### The receiver answers 500

Polar's `serve_rollout` log shows the callback POST failing with a 500 whose body is:

```json
{"error": "pins configuration: pins key 'tool_roster_hash' missing, empty, or not a list in /etc/gsj/pins.gsj.json"}
```

This is the server-leg face of `PinsConfigurationError`. The receiver classifies by origin: an unusable pins file is *its* configuration fault, so it answers 500 naming the key or path — never a 400 (that would blame Polar's body) and never a dropped connection. The envelope is atomic: nothing from that callback landed on disk, neither in `traces_dir` nor in `quarantine/`. The results are not lost — the rollout API still holds them and `submit`'s poll still returns them — but there is no archive of them until the pins are fixed and the receiver restarted.

The receiver's other replies are a `200` with counts (a rejection is a validation verdict, so it is still `200`), a `400` naming a body-shape problem (nothing Polar sends triggers it; a hand-rolled POST might), and a `404` for any other path; the full table is on [The receiver](receiver.md#endpoints).

`GET /healthz` returns `{"status": "ok", "accepted": n, "rejected": m}` with the running counts, which is the quickest way to confirm the receiver you think is listening is the one Polar is reaching. The full contract is in [The receiver](receiver.md).

### Nothing lands on disk

If `submit` reports `collected` counts but `traces_dir` and `quarantine/` stay empty, the callback is not arriving. Check, in order: `serve` is running (`curl http://127.0.0.1:8300/healthz`); the `callbacks:` URL that `serve` printed is dialable **from the rollout API's host** (it is the only process that POSTs to it); and the `serve_rollout` log for `Callback POST to … failed`. A receiver whose pins file could not be read at start-up answers every callback 500 before writing anything (its mode token would be `pins-unresolved`), which is the pins fault above.

## During the episode

A failure inside the sandbox surfaces twice: in the **gateway process log** (`serve_gateway`) as `Agent execution failed for session <id>` with a traceback, and in the **callback** as a session with `status: "ERROR"`, `traces: []`, and the exception text in `error`, prefixed `agent execution failed: `. The receiver quarantines it with `ADM1:status_not_completed:ERROR`, `ADM4:no_traces` and `G7:missing_evidence:reconstruction_stats`; `submit` prints the same list. So an `ADM1` finding is your cue to read `session_result.error` in the quarantine file, then the gateway log.

### The sandbox cannot be created

```text
RuntimeError: docker create failed with exit code 125: Unable to find image 'ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3' locally …
```

Polar's Docker runtime runs `docker create --name … --network <runtime.network> … <runtime.image> sleep infinity` followed by `docker start`, and raises on either non-zero exit with docker's own stderr appended. The usual causes: the image is not pullable from this host (a firewalled registry; an amd64-only image on an ARM host), or `runtime.network` names a Docker network that does not exist. Pull the image by hand (`docker pull <runtime.image>`) and confirm the network (`docker network ls`).

### The clone fails: `PiHarness setup failed … on 'git'`

```text
RuntimeError: PiHarness setup failed (rc=128) on 'git': "fatal: unable to access 'http://172.28.9.10:3000/gsj-staging/case_0001.git/': Failed to connect to 172.28.9.10 port 3000 …"
```

The harness clones **inside the sandbox**: `git clone --depth 1 --branch timestep-<T> --single-branch <clone_url_for> <workdir>`, then removes the remote and scrubs the reflogs so the history cannot reach past the cutoff. So `estate.clone_url_for` must resolve *from the episode container*, not from the host — and this is the value that costs an episode when it is wrong, because the container was already started and the scheduler already consumed the attempt.

> [!WARNING]
> **Trap: the default bridge cannot reach the compose network**
>
> Docker isolates networks from each other. With `runtime.network: bridge` (the default) an episode container cannot reach a Forgejo that lives at a static IP on the estate's compose network (`172.28.9.10` on the H200 file). The cure is a config value, not code: `runtime.network: gsj-staging-net` puts episodes **on** that network, container to container. Polar's Docker runtime passes only `--network`, so there is no other way to bridge the two.

A `PiHarness setup failed (rc=…) on 'mkdir'` is the first step failing — writing pi's settings under `/tmp/pi-agent` inside the container — which in practice means a wrong `runtime.image` (no `sh`, or a read-only `/tmp`). `PiHarness workspace probe failed …` or `… probe returned no ['branch', …]` means the clone reported success but the checkout is not a git repository with the expected branch — check that the case repository actually has a `timestep-<T>` branch.

### `host.docker.internal` does not resolve

> [!WARNING]
> **Trap: no `--add-host` on Linux**
>
> Polar's Docker runtime passes only `--network`; it never passes `--add-host host.docker.internal:host-gateway`. On a Linux host `host.docker.internal` therefore does **not** resolve inside episode containers, and any of `estate.clone_url_for`, `estate.mcp_url_base` or `polar.gateway.public_url` written with it fails from the sandbox. Address host-bound services by the compose network's own gateway IP instead — `172.28.9.1` on the H200 file, where the retrieval service (`0.0.0.0:8790`) and the gateway (`0.0.0.0:8200`) both bind the host. `172.17.0.1` also works but names the default bridge's interface, not the network the episodes are on.

Find your network's gateway address with `docker network inspect <runtime.network> --format '{{(index .IPAM.Config 0).Gateway}}'`.

### `public_url` must be dialable from both places

`polar.gateway.public_url` is one URL with two callers: the **rollout API** dispatches sessions to it from the host, and **pi inside the container** sends every model call to `public_url` + `/v1` — the capture proxy that records tokens and logprobs. It is never `localhost`.

| Wrong value | What happens |
|---|---|
| `http://127.0.0.1:8200` | Dispatch works (same host); pi cannot reach the proxy. The episode ends with **no completions**: the session comes back without traces and is quarantined `ADM4:no_traces` (plus `ADM1:status_not_completed:ERROR` if pi exited non-zero). Nothing in the gateway log says "connection refused" — the failure is on pi's side, inside the container. |
| `http://host.docker.internal:8200` | Same shape on Linux; see above. |
| `http://172.28.9.1:8100` with `port: 8200` | Rejected at load (`public_url advertises port 8100 but the gateway listens on port 8200 …`). |
| An address the rollout API cannot reach | The gateway never registers, no session is ever dispatched, and `submit` times out with `(0/N sessions)`. |

The H200 value, `http://172.28.9.1:8200`, works because the compose network's gateway IP is host-local and on the sandbox network at once. Probe both directions:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://172.28.9.1:8200/           # from the host
docker run --rm --network gsj-staging-net curlimages/curl -sS -o /dev/null -w '%{http_code}\n' http://172.28.9.1:8200/   # from the sandbox network
```

Any HTTP status means the gateway answered; `Connection refused` or a DNS failure means that caller cannot reach it.

### The token secret is unset

```text
RuntimeError: PiHarness: token secret env var 'GSJ_MCP_TOKEN_SECRET' is unset in the gateway process
```

The harness mints the per-episode retrieval token host-side, in the **gateway** process, from the variable named by `estate.mcp_token_secret_env`. `serve` prints the gateway command with `GSJ_MCP_TOKEN_SECRET=<secret>` in front for exactly this reason. The secret must equal the retrieval service's own — a token signed with a different secret fails the service's signature check, and the agent's `search_case` calls come back `401`; the episode then completes with no retrieved pages, which the checks read as a *valid* but useless trace unless the policy flags it (see [H41](#h41--a-roster-with-zero-tool-calls)).

### Other setup messages

| Message | Cause |
|---|---|
| `ValueError: PiHarness settings missing required keys: [...]` | The `TaskRequest` was not rendered by `render_task_request` — one of `case_id`, `timestep`, `clone_url_for`, `mcp_url_base`, `tools_allowlist`, `artifacts_dir` is absent from `agent.settings`. |
| `ValueError: PiHarness requires model_name as 'provider/model' (got '…')` | `agent.model_name` has no `/`. The renderer builds it as `<estate.provider>/<estate.model>`; a hand-built request must do the same. |
| `step <i> exited with code <rc>` in `session_result.error` | pi itself exited non-zero during the run step; its stdout and stderr are in `<session_dir>/logs/agent/step.<ii>.stdout.log` and `.stderr.log` on the gateway host, and pi's own transcript lands under `<artifacts_dir>/<session_id>/pi_transcript.jsonl`. |

## At the callback: findings by family

Every finding is a byte-stable `<ID>:<slug>[:<detail>]` token, and the same `checks.validate_session_result` produces it on both sides of the wire. The complete vocabulary with each rule's reasoning is in [Validation](../concepts/validation.md), [Finding vocabulary](../reference/findings.md) and the [checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md). This section is the triage view: which family, what it usually means, what to change.

### ADM — the episode did not complete

| Finding | Meaning | Fix |
|---|---|---|
| `ADM1:status_not_completed:ERROR` | The session's status is not `COMPLETED`. `ERROR` is a harness or agent failure — read `session_result.error`. | See [During the episode](#during-the-episode). |
| `ADM1:status_not_completed:TIMEOUT` | Polar's per-task `timeout_seconds` (`--timeout`, default 900) expired. | Raise `--timeout`, or look at why the agent stalled (an engine that never answers keeps pi waiting; the proxy's own liveness timeout is 900 s). |
| `ADM2:builder_findings_present:<n>` | Our builder found `n` session-level defects and downgraded the status to `ERROR`; the builder's own findings follow in the same list (`S1:empty_prompt_ids:…`, `S3:duplicate_consecutive_prompt:…`, `S7:mid_chain_finish_length:…`, `R11:roster_changed_across_completions`, `A15:end_of_turn_token_id_not_configured`, …). | `A15` means `builder.end_of_turn_token_id` was not rendered — use `render_task_request`. The `S*`/`R11` findings describe the capture and are explained in [Traces](../concepts/traces.md#how-a-multi-turn-session-becomes-one-chain). |
| `ADM3:trajectory_missing` | No `trajectory` object in the body. | Not something Polar sends; a hand-rolled POST. |
| `ADM4:no_traces` | `trajectory.traces` is empty — no completion was captured. Rides along with every `ADM1:…:ERROR` from setup; on its own it means pi ran but produced no model call the proxy saw. | If it comes without `ADM1`, check [`public_url`](#public_url-must-be-dialable-from-both-places). |
| `ADM5:malformed_trace` | A member of `traces` is not an object. | As `ADM3`. |

`G7:missing_evidence:reconstruction_stats` accompanies every `ADM4` — an empty trajectory carries no stats — and needs no separate action.

### `*_not_approved` — the pins do not describe this estate

| Finding | Gate | What was hashed |
|---|---|---|
| `G3:tool_roster_hash_not_approved:<sha256>` | G3 | the wire `tools` array (canonical JSON) |
| `G2:system_prompt_hash_not_approved:<sha256>` | G2 | the text of each `role: system` message |
| `G1:skill_card_hash_not_approved:<sha256>` | G1 | `metadata.skill_card_hash` from the task request |
| `G7:settings_hash_not_approved:<sha256>` | G7 | `metadata.gsj_settings` — the pi `settings.json` the harness wrote and echoed (`{"compaction": {"enabled": false}}`) |

All four say the same thing: the hash computed from the trace is not in the approved set the resolved pins file holds for that key. When **all of them** fire on every episode, the pins file is another estate's — the packaged reference copy on a pip install, or the thinking-off file on a thinking-on run. Set `GSJ_PINS_PATH` on both legs and restart. When **one** fires, that one property changed: a different `harness.tools_allowlist` (G3), a different `harness.workdir` or pi image with a different system prompt (G2), a skill card whose bytes changed (G1), or a harness that writes a different pi `settings.json` (G7 — `context_window` and `max_tokens` go into `models.json`, not the settings echo, so changing them does not fire G7). Either revert the change or re-pin: [Re-pinning for your own estate](../concepts/pins.md#re-pinning-for-your-own-estate).

The `missing_evidence` variants — `G3:missing_evidence:tools`, `G2:missing_evidence:system_prompt`, `G1:missing_evidence:prompt_source`, `G1:missing_evidence:skill_card_hash`, `G7:missing_evidence:settings` — mean the trace lacks the field altogether: a request not rendered by `render_task_request` (G1's `prompt_source`, G7's settings echo) or a harness that is not ours.

### G5 — the cutoff evidence

| Finding | Meaning | Where to look |
|---|---|---|
| `G5:workspace_branch_ne_timestep:<branch>!=timestep-<T>` | The checked-out branch is not `timestep-<T>`. | The clone step cloned something else — check the case repository's branches. |
| `G5:checkout_max_page_ne_timestep:<max>!=<T>` | The checkout's highest `md/page_NNNN.md` is not T. | The `timestep-<T>` branch of that case does not truncate at T: a corpus ingest problem. See [The corpus](corpus.md). |
| `G5:checkout_pages_not_contiguous:<min>-<max>/<count>` | Pages are not 1..T without gaps. | Same. |
| `G5:checkout_history_posture:shallow=…,remotes=…` | The checkout is not shallow, or still has a remote. | The clone command was altered (a custom `pi_entry` or image that re-fetches). |
| `G5:search_page_gt_timestep:<page>><T>` | A `search_case` result returned a page past T. | The retrieval service is not filtering on the verified claim: wrong service version, or a token minted with a different timestep. See [The retrieval service](retrieval-service.md). |
| `G5:missing_evidence:timestep` / `G5:missing_evidence:workspace` | The trace carries no timestep, or no `gsj_workspace` echo. | A request not rendered by `render_task_request`; a harness that is not ours. |

### LP — the logprob capture

| Finding | Meaning | Where to look |
|---|---|---|
| `LP1:response_logprobs_absent` | `response_logprobs` is missing or null while there are trainable tokens. | The engine did not return logprobs for at least one completion — a missing slot nulls the whole array upstream. Check the engine's serve flags. |
| `LP2:response_logprobs_length_ne_response_ids:<n>!=<m>` | The arrays are misaligned. | A capture or reconstruction fault; keep the quarantine file. |
| `LP3:sentinel_logprob_at_mask1:first=<i>:count=<n>` | A trainable position carries a value at or below `checks.sentinel_threshold` (default `-9000.0`) — a sentinel, not a probability. | The engine's placeholder for "no logprob". |
| `LP4:nonfinite_logprob:…` / `LP5:positive_logprob:…` | NaN/Infinity, or a value above 0. | Not evidence of a probability; an engine or serialisation fault. |
| `LP6:zero_logprob_rate_at_mask1:<zeros>/<trainable>><rate>` | More than `checks.zero_at_mask1_max_rate` (default `0.25`) of trainable positions are exactly `0.0`. | Near-delta rounding happens on real engines (the reference estate measured ~14 %); a rate far above that means logprobs are not being captured as sampled. The knob is [`checks.zero_at_mask1_max_rate`](configuration.md#checks). |
| `LP7:empty_loss_mask` / `LP8:loss_mask_length_ne_response_ids:…` / `LP9:loss_mask_value_not_binary:…` | The mask is empty, misaligned, or not 0/1 ints. | Reconstruction fault; keep the file. |

The `checks:` section of the YAML is the only tuning surface; `load_config` rebinds `checks.DEFAULT_POLICY` from it on both sides. Loosening a threshold to make a finding go away is the trainer's decision, not the server's — the reasoning per rule is in the [checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

### G6 — the thinking tail

| Finding | Meaning |
|---|---|
| `G6:prompt_suffix_ne_tail_ids` | The first assistant turn does not open with a pinned `g6_expected_tail_ids` sequence. |
| `G6:interstitial_ne_tail_ids:first=<turn>:count=<n>` | Later turns do not. |
| `G6:missing_evidence:turns` | The loss mask has no trainable span at all. |

When both fire on every episode, the harness mode and the pins file disagree: `harness.thinking` is a non-`off` level and `GSJ_PINS_PATH` still resolves to the thinking-off set (or vice versa). Each pins file asserts its own mode in both directions, and nothing selects the thinking-on file for you — it must be set on **both** legs. Details and the tails themselves: [The thinking-on set](../concepts/pins.md#the-thinking-on-set). If only one leg was pointed at the right file you will see the receiver quarantine everything while the trainer's own re-validation passes, or the reverse — the two legs must agree, by design.

When G6 fires on a mode-consistent estate, the served chat template is not the pinned one (a different model or a different `--chat-template`): the generation-prompt tail is a property of the template, and the pins walk is where it is re-derived.

### G7 — the chain snapshot

`G7:chains_total_ne_1:<n>`, `G7:chains_truncated:<n>`, `G7:completions_merged_ne_total:<m>!=<t>`, `G7:raw_completions_ne_total:<r>!=<t>` mean Polar's prefix merging did not fold the session into exactly one untruncated chain with every completion merged. On a symmetric chat template this does not happen; on an asymmetric one it means `builder.generation_prompt_glue_ids` is needed — see [When the template is asymmetric](../concepts/traces.md#when-the-template-is-asymmetric).

### TR — the tripwires

| Finding | Meaning |
|---|---|
| `TR1:finish_reason_not_allowed:<reason>` | The trace's `finish_reason` is not one of `stop`, `tool_calls`, `stop_sequence`, `length`. `content_filter` lands here, and a missing value as `TR1:finish_reason_not_allowed:None`. |
| `TR2:reasoning_loss_mask_masked_tokens:<n>` | Polar's reasoning mask hid tokens; our traces must carry every sampled token unmasked. |
| `TR3:split_not_train_or_eval:<value>` | `metadata.split` is present but neither `train` nor `eval`. Omit it or fix the bank row. |

`finish_reason: length` is **accepted** by design — `submit` counts those on its `length-terminated:` line so the trainer can decide what to do with them.

### H41 — a roster with zero tool calls

`H41:roster_offered_zero_tool_calls` fires only when `checks.reject_toolless_roster: true`: the agent was offered tools and never called one. Off by default because a legitimate episode can answer without tools; on, it catches the silent shape of a broken retrieval service (a wrong `mcp_url_base`, a secret mismatch → `401`) where pi runs to completion having retrieved nothing.

## Quick reference: the networking values

| Value | Dialled by | Must be reachable from | Wrong-value symptom |
|---|---|---|---|
| `estate.clone_url_for` | the episode container (`git clone`) | inside `runtime.network` | `PiHarness setup failed (rc=128) on 'git': …` → `ADM1` |
| `estate.mcp_url_base` | pi inside the container | inside `runtime.network` | no retrieved pages; `H41` if armed |
| `estate.serving_base_url` | the gateway process only | the host | 404 on `/v1/v1/…` (suffixed form is rejected at load); otherwise pi's calls fail through the proxy |
| `polar.gateway.public_url` | the rollout API **and** pi in the container | both | no registration → `submit` times out `(0/N sessions)`; or `ADM4:no_traces` |
| `polar.rollout.host/port/public_url` | the trainer, the gateway | the trainer's host | exit 3 |
| `receiver.host/port/public_url` | the rollout API (callback) | the rollout API's host | nothing lands on disk; `submit` still collects |

## See also

- [Configuration](configuration.md) — every field, every validator message.
- [The receiver](receiver.md) — the callback contract and status codes.
- [Pins and approved sets](../concepts/pins.md) — resolution order, the thinking-on set, re-pinning.
- [Validation](../concepts/validation.md) and [Finding vocabulary](../reference/findings.md) — the complete vocabulary.
- [The estate](estate.md) — the services these values point at.
