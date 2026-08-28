[Documentation](../README.md) › Guides

# Command line

This page is the reference for the `gsj-rollout` console script: both subcommands with every flag and its default, what each one prints, the exit-code contract, how `--from-bank` reads a taskbank row, what `--out` writes, and how to drive the same code from Python. Read the [trainer quickstart](../getting-started/trainer-quickstart.md) first if you have never submitted a task; read the [server quickstart](../getting-started/server-quickstart.md) if you are the one bringing the receiver up.

## One entry point, two subcommands

```text
usage: gsj-rollout [-h] {serve,submit} ...

Rollout server for the gsj corpus: task -> sandbox -> agent -> trace.

positional arguments:
  {serve,submit}
    serve         start the receiver; render topology; print the Polar
                  commands
    submit        submit a task triple; wait; collect validated traces
```

| subcommand | role | what it does |
| --- | --- | --- |
| `serve` | server | loads the YAML, writes `topology.rendered.yaml`, prints the two Polar commands for the operator, then runs the receiver until a signal arrives |
| `submit` | trainer | loads the same YAML, renders one `TaskRequest`, submits it, polls until terminal, re-validates every session, reports, exits with a code that states the count |

The console script is `gsj-rollout = gsj_rollout.cli:main`, installed by the wheel and by an editable checkout alike. `python -m gsj_rollout.cli …` is the same program: the module ends in `raise SystemExit(main())`, so the module form prints the same output and returns the same exit codes as the script. Without that guard the module form used to exit 0 silently having started nothing, which is why it is tested explicitly.

```bash
gsj-rollout submit --help
python -m gsj_rollout.cli submit --help     # identical
```

`--help` on the top level or on either subcommand exits 0. Every usage error argparse itself detects — a missing `--config`, an unknown flag, a non-integer `--timestep`, `--prompt` together with `--prompt-file` — exits 2, the same code the subcommands use for their own configuration and usage errors.

> [!NOTE]
> **Nothing happens at import**
>
> `import gsj_rollout.cli` installs no signal handlers and starts nothing. `serve` installs its `SIGINT`/`SIGTERM` handlers for its own lifetime and restores the previous ones on exit, so the module is safe to embed — see [calling the CLI from Python](#calling-the-cli-from-python).

## `gsj-rollout serve`

```text
usage: gsj-rollout serve [-h] --config CONFIG [--render-only]
```

| flag | default | meaning |
| --- | --- | --- |
| `--config CONFIG` | required | the one YAML; see the [configuration guide](configuration.md) |
| `--render-only` | off | render the topology and print the commands, then exit 0 without starting the receiver |

`serve` does four things in order:

1. **Load and validate the YAML.** A missing file, invalid YAML, an unknown key, or any other validation failure prints one `gsj-rollout: …` line on stderr and exits 2. Nothing is written.
2. **Render Polar's topology.** `render_topology(cfg)` is dumped to `topology.rendered.yaml` in the directory that holds your config file — the path is derived from `--config`, not from the working directory — and overwritten on every run. It is generated output; never hand-edit it.
3. **Print the operator's instructions**, flushed line by line so they survive a pipe or `nohup … > log`:
    - the two Polar commands, with absolute paths — `serve_rollout` and `serve_gateway`, both run from `<checkout>/vendor/polar/.venv/bin/polar` with `PYTHONPATH=<checkout>`, the gateway line prefixed with the MCP secret's environment variable (`estate.mcp_token_secret_env`, default `GSJ_MCP_TOKEN_SECRET`);
    - the callback URL the receiver will answer on, the traces directory and the quarantine directory.
4. **Run the receiver** (unless `--render-only`): `Receiver(receiver.host, receiver.port, receiver.traces_dir, <quarantine dir>)` starts on a daemon thread, `receiver listening on <host>:<port>` is printed with the port actually bound (so a `port: 0` config shows the ephemeral port), and the process blocks until `SIGINT` or `SIGTERM`. On the signal it shuts the server down, waits up to five seconds for the thread, restores the previous signal handlers, prints `receiver stopped: accepted=<n> rejected=<m>` and exits 0.

```bash
gsj-rollout serve --config estate/rollout.yaml
```

```text
topology rendered: /srv/gsj/estate/topology.rendered.yaml — run Polar's two processes yourself:
  PYTHONPATH=/srv/gsj/checkout /srv/gsj/checkout/vendor/polar/.venv/bin/polar serve_rollout -c /srv/gsj/estate/topology.rendered.yaml
  GSJ_MCP_TOKEN_SECRET=<secret> PYTHONPATH=/srv/gsj/checkout /srv/gsj/checkout/vendor/polar/.venv/bin/polar serve_gateway -c /srv/gsj/estate/topology.rendered.yaml
callbacks: http://127.0.0.1:8300/callbacks/session_result | traces -> /data/gsj/traces | quarantine -> /data/gsj/traces/quarantine
receiver listening on 127.0.0.1:8300
```

`serve` runs *our* receiver only. Polar's rollout API and gateway are separate processes that you start yourself from the two printed lines; `serve` never supervises them. `serve` exits 0 on a clean stop and 2 on a config error — there are no other codes.

> [!WARNING]
> **The printed Polar path depends on where `gsj_rollout` is installed**
>
> The path is computed as `<parent of the gsj_rollout package>/vendor/polar/.venv/bin/polar`. From an editable checkout that is the vendored Polar's venv. From a wheel install it would be a path under `site-packages` that cannot exist — no wheel ships `vendor/` — so `serve` prints a `NOTE` saying so and substitutes `<checkout>` placeholders in the commands. A checkout whose Polar venv has not been built yet gets a different `NOTE` pointing at `vendor/REVENDOR.md`. Either way `serve` still renders the topology and, without `--render-only`, still runs the receiver. See [installation](../getting-started/installation.md#polars-own-venv).

> [!TIP]
> **`--render-only` is the dry run**
>
> It performs steps 1–3 and stops: a cheap way to check the YAML loads, look at the generated topology, and copy the two commands into your process manager before anything listens.

What the receiver does with each callback — validation, the `<session_id>.<pins_mode>.json` file naming, the atomic landing, the `/healthz` counters — is on the [receiver page](receiver.md).

## `gsj-rollout submit`

```text
usage: gsj-rollout submit [-h] --config CONFIG [--case CASE]
                          [--timestep TIMESTEP] [--prompt PROMPT |
                          --prompt-file PROMPT_FILE] [--from-bank PARQUET]
                          [--row ROW] [--episodes EPISODES]
                          [--task-id TASK_ID] [--timeout TIMEOUT]
                          [--grace GRACE] [--poll-interval POLL_INTERVAL]
                          [--out OUT]
```

| flag | type | default | meaning |
| --- | --- | --- | --- |
| `--config CONFIG` | path | required | the one YAML; `polar.rollout` says where to submit, `receiver` where callbacks go |
| `--case CASE` | str | — | case repo name, e.g. `case_0001` (or `--from-bank`) |
| `--timestep TIMESTEP` | int | — | `T` — the branch checked out *and* the retrieval cutoff claim (or `--from-bank`); `0` is a valid value |
| `--prompt PROMPT` | str | — | the instruction text |
| `--prompt-file PROMPT_FILE` | path | — | file whose entire contents are the instruction text; mutually exclusive with `--prompt` |
| `--from-bank PARQUET` | path | `None` | submit a taskbank row: triple, prompt, source and split all come from the row |
| `--row ROW` | int | `0` | 0-based row index into the bank (`--from-bank` only) |
| `--episodes EPISODES` | int | `1` | **attempts** to run — becomes `num_samples`; see [collect-N semantics](#what---episodes-n-means) |
| `--task-id TASK_ID` | str | `gsj-task` | Polar's task id; appears in the progress lines and in every trace's metadata |
| `--timeout TIMEOUT` | float | `900.0` | the request's per-task `timeout_seconds` |
| `--grace GRACE` | float | `120.0` | extra seconds the client keeps polling beyond `--timeout` (callback grace) |
| `--poll-interval POLL_INTERVAL` | float | `2.0` | seconds between status polls |
| `--out OUT` | path | `None` | directory for the accepted `SessionResult` JSON files; without it `submit` only reports |

The flow from argv to exit code:

![gsj-rollout submit as a flowchart: parse args, load config (exit 2 on failure), resolve the task from flags or a taskbank row (usage errors exit 2), render_task_request, submit and wait (HTTP errors exit 3, a timeout exits 1), partition the results with checks, write --out, and exit 0 only when every attempt was accepted](../img/cli-submit-flow.png)

<sub>Eight steps, three early exits, and a final tally that is exact: exit 0 means accepted == --episodes, nothing looser.</sub>

### Naming the task

There are exactly two ways, and they do not mix.

**From flags.** `--case`, `--timestep` and one of `--prompt`/`--prompt-file` are all required; any missing piece is a usage error (exit 2, `submit needs --case, --timestep and --prompt/--prompt-file — or --from-bank`). `--prompt-file` is read whole, in text mode, with no trimming. The rendered request carries `prompt_source: "free"` and no `split`.

```bash
gsj-rollout submit --config rollout.yaml \
  --case case_0001 --timestep 12 \
  --prompt-file prompts/summarize.md \
  --episodes 4 --task-id case_0001-t12 --out collected/
```

**From a taskbank row.** `--from-bank PARQUET [--row N]` takes everything from one row of the parquet the corpus pipeline's `taskbank` phase writes (see [the corpus](corpus.md)):

| column | becomes |
| --- | --- |
| `case_id`, `timestep` | the triple's case and timestep |
| `prompt_text`, `skill_card_text` | the instruction: `prompt_text` if it is set, else the resolved skill card text |
| `prompt_source` | `metadata.prompt_source` (`free` or `skill:<name>`); a skill row's card text is also hashed into `metadata.skill_card_hash` |
| `split` | `metadata.split` (`train` or `eval`) |
| `sandbox_image` | checked against the YAML's `runtime.image` — the request is rendered from the config, so a mismatch is refused rather than run on the wrong image |

All seven columns must be present or the file is refused as not a taskbank. The bank's `prompt_id` column is not read by the CLI.

```bash
gsj-rollout submit --config rollout.yaml --from-bank corpus/taskbank.parquet --row 17
```

Every refusal names its cause and exits 2: `--row` out of range (the message states the valid range), `--from-bank` combined with any of `--case`/`--timestep`/`--prompt`/`--prompt-file` (`drop --case/--timestep/--prompt`), a missing column, the image mismatch, or an unreadable file.

> [!NOTE]
> **`pyarrow` is imported lazily**
>
> The core package depends on `pydantic`, `httpx` and `pyyaml` only. `pyarrow` is imported inside the `--from-bank` code path, on first use, so `import gsj_rollout.cli` and every other flag work without it. If it is absent the CLI exits 2 with a message beginning `--from-bank needs pyarrow (pip install pyarrow)` — install it yourself, or use the `[dev]` extra, which includes it.

### Timing

`render_task_request` puts `--timeout` into the request as `timeout_seconds` — that is the budget Polar gives the task. The client then polls `GET /rollout/task/<task-id>` every `--poll-interval` seconds and gives up after `--timeout + --grace` (`1020` s by default): the grace covers the gap between Polar's own timeout and the moment the terminal status is visible. If the task is not `completed` or `failed` by then, `wait` raises `TimeoutError`, the CLI prints `gsj-rollout: task <id> not terminal after 1020.0s (k/N sessions)` on stderr and exits 1 **without** collecting anything — no partition, no `--out` files — even if some sessions had already finished. Whatever Polar delivers later still reaches the receiver, which lands it independently of the CLI.

Any `httpx.HTTPError` during submit or during a poll — connection refused, DNS failure, a 4xx or 5xx response — prints `rollout server unreachable or errored at <base_url>: …` and exits 3. An HTTP error is never reported as exit 1; the two codes mean different things.

### Progress and the report

On stdout, in order:

```text
task case_0001-t12: 0/4 sessions terminal
task case_0001-t12: 2/4 sessions terminal
task case_0001-t12: 4/4 sessions terminal
rejected ep-9c01f2d7e3a54b18: ['G2:system_prompt_hash_not_approved']
collected 3/4 episodes -> collected/
length-terminated: 1/3 accepted episodes ended finish_reason=length — qualified by design; …
```

- One `task <id>: k/N sessions terminal` line each time the count of terminal sessions changes — the first poll always prints, later polls print only on a change, so a long wait stays quiet.
- One `rejected <session_id>: [findings]` line per session that fails re-validation, with the finding codes from `checks.validate_session_result` (the [finding vocabulary](../reference/findings.md) explains each).
- `collected <accepted>/<episodes> episodes`, with ` -> <out>` appended when `--out` was given.
- `length-terminated: <k>/<accepted> accepted episodes ended finish_reason=length — …`, printed unconditionally, zero included. An episode counts here when any of its traces ended `finish_reason=length` — a completion that stopped at the token budget is accepted by design; whether to train on it is the trainer's decision, so the CLI counts it out loud rather than hiding it. Errors go to stderr, prefixed `gsj-rollout: `.

> [!TIP]
> **Progress lines under a pipe**
>
> `serve` flushes every line it prints because those lines are the operator's only instructions. `submit` uses plain `print`, so through a pipe its progress lines are block-buffered and may only appear at exit. Run it with `python -u -m gsj_rollout.cli submit …` or `PYTHONUNBUFFERED=1` when a supervisor is reading the stream.

### What `--out` writes

`--out DIR` creates `DIR` if needed (it is created even when nothing was accepted) and writes one file per **accepted** session:

```text
collected/
├── ep-b4124a5aa0a8468d.json     # the SessionResult body, verbatim, as returned by GET /rollout/task/<id>
├── ep-2f7d0c6b19e84a03.json
└── ep-d51e8a7c4b0f4e92.json
```

Each file is the full `SessionResult` JSON — `session_id`, `task_id`, `status`, `error`, `node_id`, `timing`, `metadata`, and the `trajectory` with its `traces` — exactly what the [Python client](../reference/api.md) returns from `wait`; the [wire formats page](../reference/wire-formats.md) documents the shape. Rejected sessions are printed, never written here; their bodies and findings are in the receiver's quarantine directory if you need them. Note the naming difference: the CLI writes `<session_id>.json`, the receiver writes `<session_id>.<pins_mode>.json`.

`--out` is a convenience for one-off runs and inspection. A training loop should use `RolloutClient` directly and keep the results in its own storage — the server owns no storage by design (see the [training loop guide](training-loop.md)).

### Exit codes

The contract, as printed at the end of `submit --help`:

| exit | meaning | produced by |
| --- | --- | --- |
| `0` | all collected | `len(accepted) == --episodes` |
| `1` | not all collected | a session was rejected by the checks or ended `ERROR`/`TIMEOUT` (`collected < attempted`), **or** the task was not terminal within `--timeout + --grace` (`TimeoutError`) |
| `2` | config or usage error | the YAML failed to load; an incomplete triple; `--from-bank` mixed with the triple flags, an out-of-range `--row`, a non-taskbank file, an image mismatch, or missing `pyarrow`; any argparse usage error |
| `3` | server unreachable or HTTP error | any `httpx.HTTPError` raised by submit or by a poll — transport failures and 4xx/5xx responses alike |

A script can branch on them directly:

```bash
gsj-rollout submit --config rollout.yaml --from-bank corpus/taskbank.parquet --row "$ROW" --out "out/$ROW"
case $? in
  0) echo "all attempts collected" ;;
  1) echo "partial — read the rejected lines; re-submit if you need more" ;;
  2) echo "fix the config or the flags" ;;
  3) echo "server down or erroring" ;;
esac
```

### What `--episodes N` means

`--episodes N` asks Polar for N **attempts** (`num_samples: N`). It is not a request for N accepted traces, and the CLI never re-submits to reach one. The definition, straight from `gsj_rollout.config.COLLECT_SEMANTICS` — the epilog of `submit --help`:

```text
Collect-N semantics (gap row 26):
- COLLECTED = status COMPLETED + gsj_validation.findings == [] + zero
  `checks` findings; ERROR and TIMEOUT never count.
- `submit --episodes N` targets N ATTEMPTS (num_samples=N) — Polar's
  scheduler owns episode counts; NOT collect-until-N-accepted.
- A rejected trace is a consumed attempt, quarantined with its findings,
  never auto-retried; exit 1 says collected < attempted.
```

("Gap row 26" is a row of the capability register in [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) §7.)

So a `3/4` run exits 1 and that is the honest count, not a failure of the server: one attempt was consumed by a session that did not pass, the receiver quarantined it with its findings, and the loop that wants a fourth trace submits again. The reasoning behind each check is on the [validation page](../concepts/validation.md).

## Calling the CLI from Python

`gsj_rollout.cli.main(argv)` is the console script's body: it parses `argv` (or `sys.argv[1:]` when `None`) and returns the exit code as an `int` instead of exiting. Only `--help` and argparse usage errors raise `SystemExit`. The module is not part of the package's public `__all__`, but it is importable and stable.

```python
from gsj_rollout import cli

code = cli.main([
    "submit", "--config", "rollout.yaml",
    "--case", "case_0001", "--timestep", "12",
    "--prompt", "Summarize the case.",
    "--episodes", "2", "--out", "collected/",
])
assert code in (0, 1, 2, 3)
```

This is the path the test suite uses. For anything beyond a wrapper, skip the CLI and use the three pieces it is made of — `load_config`, `render_task_request` and `RolloutClient` — as shown in the [trainer quickstart](../getting-started/trainer-quickstart.md#4-the-same-run-in-python); they give you the rejected results and their findings as data instead of printed lines.

## See also

- [Trainer quickstart](../getting-started/trainer-quickstart.md) — a first `submit`, then the same run in Python.
- [Server quickstart](../getting-started/server-quickstart.md) — `serve`, the two Polar processes, and a first end-to-end episode.
- [Configuration](configuration.md) — every key `--config` accepts, with defaults.
- [The receiver](receiver.md) — what happens to each callback `serve` accepts.
- [Troubleshooting](troubleshooting.md) — the messages behind exit codes 2 and 3.
