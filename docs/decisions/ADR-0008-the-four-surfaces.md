# ADR-0008 — The four surfaces: config, receiver, client, CLI

## Context

CP-08 makes the rollout server startable, submittable, and consumable:
`config.py`, `receiver.py`, `client.py`, `cli.py`, and the consumer
surface in `__init__.py`. The facts these decisions rest on, all
line-verified in the vendored tree or measured in CP-03..CP-07:

- Polar's rollout server API: `POST /rollout/task/submit` (returns
  `{task_id, status}` immediately), `GET /rollout/task/{task_id}`
  (a `TaskStatus` whose `results` list is the callback-validated
  `SessionResult` objects appended **verbatim**, status/error intact —
  `manager.py:214`; this is the exact provenance of our CP-07 fixture).
- The gateway node POSTs each per-session `SessionResult` to the
  callback URL in its dispatch request — but the pipeline **overwrites**
  that field with its own `{rollout.public_url}/callbacks/session_result`
  (`pipeline.py:184`), so the node's per-session callback cannot be
  redirected to us without a vendored patch.
- `TaskRequest.callback_url` is a separate, trainer-suppliable hook: when
  set, the manager POSTs the terminal `TaskResult`
  (`{task_id, status, results: [SessionResult…], result_paths}`) to that
  URL, best-effort with fallback-to-polling semantics
  (`manager.py:164-179`). This is the one zero-patch push channel to us.
- The on-disk `ses_*.json` strips `trajectory.status`/`error`
  (`pipeline.py:423-436`) — the rollout server's disk is never a valid
  source of traces (CP-07 finding 5, binding).
- Polar's operator surface is `polar serve_rollout -c topology.yaml` and
  `polar serve_gateway -c topology.yaml [--node-id]` (`polar/cli.py`),
  run from `vendor/polar/.venv` with `PYTHONPATH` carrying `gsj_rollout`
  (the `import_path` harness/builder) and the token secret env var set in
  the gateway process (ADR-0006).

## Decision

### 1. `config.py` — one YAML, and it GENERATES Polar's surfaces

One YAML (`load_config(path) -> RunConfig`, pydantic, `extra="forbid"` in
every library section) is the complete construction surface for both
sides (gap row 25). We **generate** Polar's `topology.yaml` and
`TaskRequest` bodies from it — `render_topology(cfg)` and
`render_task_request(cfg, task_id=…, instruction=…, case_id=…,
timestep=…, episodes=…, timeout_seconds=…)` — rather than sitting beside
hand-maintained Polar files. A consumer writes one file; every value that
must agree across our receiver, Polar's topology, and the task request
(URLs, model names, roster, builder pins) has exactly one home.

Sections: `estate` (Forgejo clone pattern, MCP base URL + token secret
env name, serving/engine base URL, provider + model), `runtime` (backend,
image, network — backend is a **value**, law 5; `runtime.workdir` is
deliberately unrepresentable, the CP-06/CP-07 rule), `harness` (the
ADR-0006 settings keys: roster, artifacts dir, workdir, context window,
max tokens, thinking, pi paths, token TTL, and the harness import path),
`builder` (strategy = our subclass; `end_of_turn_token_id` **required**,
A-15; `generation_prompt_glue_ids` optional, A-21 — both model-specific),
`polar` (rollout host/port/public_url/save_dir; one gateway node:
id/host/port/public_url/engine/workers/heartbeat), `receiver` (bind
host/port, public URL, traces dir, quarantine dir), and a reserved
free-form `user:` mapping the library validates as a mapping and never
reads (the predecessor's §9 pattern — the trainer's knobs live in the
same file without touching our schema).

An unknown key in a library section raises naming section and key.

### 2. `receiver.py` — validate the POSTed body; quarantine, don't drop

Stdlib `http.server.ThreadingHTTPServer`. R1 candidate named: FastAPI +
uvicorn (Polar's own stack). Rejected: the root package's `[server]`
extra is deliberately empty (ADR-0005/A-14 — Polar's venv hosts us, our
deps stay a subset of Polar's), the endpoint is one POST route, and
stdlib keeps the receiver runnable from any venv including the trainer's.

`POST /callbacks/session_result` accepts **two body shapes**, both
landing in the same admission path: a single `SessionResult` (the
per-session shape — the contract of the real callback body, our fixture,
and any future patched/direct wiring) and the manager's terminal
`TaskResult` envelope, unwrapped to its `results` (the zero-patch live
delivery: `render_task_request` sets `TaskRequest.callback_url` to our
receiver). Every `SessionResult` goes through
`checks.validate_session_result(body)`:

- **no findings** → the POSTed body is persisted **verbatim** to
  `<traces_dir>/<session_id>.json` (one file per session, status/error
  intact — never reconstructed from rollout disk);
- **findings** → quarantined to `<quarantine_dir>/<session_id>.json` as
  `{"findings": […], "session_result": <body>}` plus a log line —
  quarantined, not dropped, because forensics beat counters (row 16's
  surviving half).

What the receiver returns to Polar: **200 with
`{"accepted": n, "rejected": m}` for every well-formed delivery**,
accepted or quarantined — a rejection is our validation decision, not a
delivery failure; a non-2xx would only make the manager log a spurious
"fall back to polling" warning (`manager.py:172-179`), and the CP-02
lesson stands that validation-critical signals must ride durable
structures (the quarantine file, the client's own re-check), never a
status hint nothing acts on. Malformed bodies (not a `SessionResult`, not
a `TaskResult`) get 400. `GET /healthz` reports counters. No signal
handlers at import; the server object exposes start/shutdown.

### 3. `client.py` — poll the manager, re-check everything

`RolloutClient(base_url)` with `submit(task_request) -> task_id`,
`wait(task_id, …) -> list[SessionResult dict]`, and
`collect(task_requests, …) -> list[Trace]`. It **polls
`GET /rollout/task/{id}`**, not the receiver's output directory, because:
(a) the poll returns the callback-validated `SessionResult` objects
verbatim with status/error intact — the same bytes the receiver got, from
the same in-memory source our fixture was captured from; (b) the trainer
need not share a disk with the receiver; and (c) law 6 wants the client's
verdict independent of the receiver's — the client re-runs the **same**
`checks.validate_session_result` on what *it* fetched, so a compromised
or buggy receiver cannot launder a bad trace into the trainer. Traces
whose session passes are returned as `Trace` (our pydantic mirror of the
callback trace fields — Polar is not importable in the trainer's env);
rejected sessions are reported, never returned.

### 4. `cli.py` — `serve` starts our receiver and prints the two Polar commands

The smallest honest thing: `gsj-rollout serve` loads the config, renders
`topology.rendered.yaml` next to the config file, starts **our receiver**,
and prints the two Polar commands (`polar serve_rollout` /
`polar serve_gateway`, with the venv path, `PYTHONPATH`, and the token
secret env reminder) for the operator to run — no process supervisor. The
predecessor's `gsj-collect` lesson (F-08/F-14/F-17) was about
observability and bounded exit, not owning process lifecycle; owning
Polar's processes would also couple us to their restart semantics (the
gateway caches the imported harness module — CP-06). SIGINT/SIGTERM
handlers are installed **inside** `serve()` (never at import — the
embeddability property), stop the receiver cleanly, and print the
accepted/rejected summary. `gsj-rollout submit` renders the task request
from the config plus `(--case, --timestep, --prompt|--prompt-file,
--episodes)`, submits, polls with one bounded progress line per state
change, re-checks client-side, writes accepted traces to `--out`, and
exits with stated codes (0 all collected / 1 task done but not all
collected / 2 config or usage error / 3 rollout server unreachable).

### 5. Collect-N semantics (gap row 26 — the answer, stated once, inherited nowhere)

- A **collected** episode is a `SessionResult` that is (a) status
  `COMPLETED`, (b) carries no builder findings
  (`gsj_validation.findings == []`), and (c) yields zero `checks`
  findings. `ERROR` and `TIMEOUT` never count. (The predecessor's
  `truncated`-counts-toward-target ambiguity has no analogue here by
  construction: our builder flips truncation-class defects to `ERROR`.)
- `submit --episodes N` targets **N attempts** (`num_samples=N` on one
  `TaskRequest`) — Polar's scheduler owns episode counts. It is **not**
  collect-until-N-accepted.
- A rejected trace **counts as a consumed attempt, is quarantined with
  its findings, and is never retried automatically**; the exit code (1)
  says collected < attempted, and resubmission is the operator's call.

This text lives in `config.py`'s module docstring and `submit --help`.

### 6. `checks.py` — the seam now, the rules later

One entry point both sides call:
`checks.validate_session_result(session_result: Mapping) -> list[str]` —
findings as byte-stable `{id}:{slug}[:detail]` strings, empty list means
accepted; it never raises on content. Composition: **admission** (live
now — honors the CP-05/CP-07 escalation contract: status must be
`COMPLETED`, `ADM1`; the builder's `gsj_validation.findings` must be
empty, `ADM2`; a trajectory and at least one trace must be present,
`ADM3`/`ADM4`; every trace must at least be a mapping, `ADM5`) followed
by **`run_trace_checks(trace)`**, the CP-10/CP-11
stub that returns no findings unconditionally (gates G1–G7, the logprob
discipline, the G7 stats conjunction land there). Admission is not a
trace rule — it is the receiver honoring what the builder already
decided — which is how the doctored-body rejection works this CP while
the STOP wall on check rules holds.

### 7. `__init__.py` — the consumer surface

Exports: `RolloutClient`, `Trace`, `checks` (the module), `load_config`,
`RunConfig`, `__version__`. Deliberately not exported: `pi_harness` and
`builder` (Polar loads them by import path; importing them requires
Polar's venv), and `receiver`/`cli` (server-internal, reached via the
console script). Importing `gsj_rollout` must never import `polar`.

## Consequence

One YAML is the whole construction surface (row 25); the receiver
consumes the real callback payload — A-5 resolves; the at-source
rejection half of row 16 lands with forensic quarantine; row 26's
semantics are written down and printed in `--help`; row 28's "async
staging" pins to what it means here (results arrive by push at the
receiver while the trainer's client polls — asynchronous by
construction, nothing more). The known cost: the TaskResult-envelope
hook is task-terminal, so the receiver sees results only when the whole
task resolves — per-session immediacy would need the vendored callback
patched, a finding for the register, not a blocker (the client's poll
path is unaffected).
