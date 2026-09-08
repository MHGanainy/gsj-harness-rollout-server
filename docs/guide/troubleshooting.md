[← Documentation index](README.md)

# Troubleshooting

Every failure surfaces in one of four places — at `submit` (an exit code and a stderr line), at `serve` (a stdout line or an import warning), inside the episode (the `serve_gateway` log plus a session arriving `status: "ERROR"`), or at the callback (a finding in a quarantine file); the exit codes (also in `gsj-rollout submit --help`) are `0` all collected, `1` not all collected (rejected/errored/timed out), `2` config or usage error, `3` server unreachable or HTTP error.

![Three lanes — at submit, at the receiver, in the episode — each holding red symptom tiles over the one place to look: exit 2 over the YAML or the flags, exit 3 over Polar's rollout API, exit 1 over the quarantine file, HTTP 500 over the pins file, and a session ERROR over the sandbox setup](img/triage-tree.png)

<sub>Where the failure surfaced says where to look: the `submit` exit code points at the config, the rollout API, or the quarantine file; the receiver's 500 at the pins file; a session `ERROR` at the sandbox setup.</sub>

## At `submit` — exit 2, config or usage

Nothing was started. `load_config` raises one `ValueError` listing **every** failing field joined by `; `, printed as `gsj-rollout: config <path> invalid — …`; usage errors print `gsj-rollout: …` too. The distinctive text of each:

| Symptom (stderr) | Fix |
|---|---|
| `must not end in /v1 — Polar's proxy appends /v1/chat/completions itself` | point `estate.serving_base_url` at the engine root, e.g. `http://127.0.0.1:8000` (else: 404 on `/v1/v1/chat/completions` at run time) |
| `public_url '172.28.9.1:8200' needs an explicit http:// or https:// scheme` | write `http://172.28.9.1:8200` — scheme-less parses as a path |
| `public_url advertises port 8100 but the gateway listens on port 8200 — one fact, two keys` | make `polar.gateway.public_url`'s port and `polar.gateway.port` agree; the loader never derives one from the other |
| `'on' is not a pi thinking level — use one of off\|minimal\|low\|medium\|high\|xhigh\|max` | bare YAML `on` arrives as boolean `True`; use `medium` — any non-`off` level also needs the thinking-on pins on **both** legs |
| `section 'estate': unknown key 'clone_pattern'` (a stray top-level key names section `<root>`) | fix the spelling, or move free-form data under `user:` |
| `'polar.gateway.public_url': Field required` | supply it — the six no-default values are in [server-guide.md](server-guide.md) |
| `config <path>: invalid YAML: …` / `config <path> must contain a top-level mapping` | fix the YAML |
| `gsj-rollout: [Errno 2] No such file or directory: 'rollout.yaml'` | give the right `--config` path |
| `submit needs --case, --timestep and --prompt/--prompt-file — or --from-bank` | pass all three, or a bank parquet |
| `--from-bank carries the triple itself — drop --case/--timestep/--prompt` | the bank row already holds the triple |
| `--from-bank needs pyarrow (pip install pyarrow)` | install it — not a core dependency |
| `--row 7 out of range: bank.parquet holds rows 0..4` | `--row` is 0-based (default 0) |
| `bank.parquet is not an … taskbank: no 'split' column` | the parquet needs all seven columns: `case_id` `timestep` `split` `prompt_source` `prompt_text` `skill_card_text` `sandbox_image` |
| `bank row wants sandbox_image '…' but runtime.image is '…' — the render reads the config's` | set `runtime.image` to the row's value |

## At `submit` — exit 3, the rollout API unreachable or errored

`gsj-rollout: rollout server unreachable or errored at http://127.0.0.1:8080: …` catches every `httpx.HTTPError` on the submit or any poll. The URL is `polar.rollout.public_url` if set, else `http://<host>:<port>` with `0.0.0.0`/`::` rewritten to `127.0.0.1` (default `http://127.0.0.1:8080`), and it belongs to Polar's **rollout API** — the `polar serve_rollout -c topology.rendered.yaml` process `serve` printed — not the gateway (8200 on H200), receiver (8300), or engine (8000). Probe: `curl -sS -i http://127.0.0.1:8080/rollout/task/does-not-exist | head -1` — any 404 means the right process answered; `Connection refused` means it is not running there.

| Message tail | Fix |
|---|---|
| `Connection refused` | start `serve_rollout`; a trainer on another machine needs `polar.rollout.host` bound reachable and `polar.rollout.public_url` set |
| `Client error '404 Not Found' for url '…/rollout/task/submit'` | wrong port — the receiver answers unknown paths `{"error": "not found"}`, the gateway and engine in their own words |
| `Server error '5xx …'` | read the `serve_rollout` log |
| `ReadTimeout` | no answer within 30 s (`httpx.Client(timeout=30.0)`); pass a longer-lived client via `RolloutClient(http=…)` |

## At `submit` — exit 1, collected < attempted

`--episodes N` is N **attempts** (Polar's `num_samples`), not collect-until-N-accepted: a session counts only when its status is `COMPLETED` *and* `checks.validate_session_result` returns no findings. Each rejection prints `rejected <session_id>: [findings]`, and the receiver wrote the same list to `<traces_dir>/quarantine/<session_id>.<pins_mode>.json` (`<pins_mode>`: `thinking-off` | `thinking-on` | `pins-unresolved` when the pins file was unreadable at start-up) — body `{"findings": [...], "session_result": …}` with `status` and `error` verbatim. `finish_reason: length` is accepted by design; `submit` counts those on its `length-terminated:` line. From Python, `partition_session_results(results)` returns `(accepted, rejected-with-findings)`; `RolloutClient.collect` logs rejections at `WARNING` via the `gsj_rollout.client` logger and returns only accepted traces.

`gsj-rollout: task gsj-task not terminal after 1020.0s (0/1 sessions)` is `TimeoutError` from `RolloutClient.wait` — the client's own deadline, `--timeout` + `--grace` (900 + 120 s by default), passed first, so there is no quarantine file yet; Polar's per-task `timeout_seconds` (the `--timeout` value) later turns a stuck episode into `ADM1:status_not_completed:TIMEOUT`. A `(0/N sessions)` count with a quiet gateway log means no gateway ever registered with the rollout API — see the `public_url` trap below.

The first token of each finding names its family; the complete vocabulary and each rule's reasoning are in [validation-and-pins.md](validation-and-pins.md) and the [checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md). Only `ADM` means the episode itself failed — every other family is a completed episode whose trace the validators refused:

| Family | What it says | Where to look |
|---|---|---|
| `ADM1`–`ADM5` | the episode did not complete, or no completion was captured | `session_result.error` in the quarantine file, then the gateway log — [During the episode](#during-the-episode) |
| `G1` `G2` `G3` `G7` `*_not_approved` / `missing_evidence` | the pins file does not describe this estate | `GSJ_PINS_PATH` on both legs, or re-pin — the walk from this first quarantine to your own pins is [bring-your-own.md#your-pins](bring-your-own.md#your-pins); the format, [validation-and-pins.md](validation-and-pins.md) |
| `G5` | cutoff evidence wrong: branch ≠ `timestep-<T>`, pages ≠ 1..T, a searched page > T | the case repo's branch, the retrieval service — [server-guide.md](server-guide.md) |
| `LP1`–`LP9` | logprob capture: absent, misaligned, sentinel, zero-rate | the engine's serve flags; policy knobs `checks.sentinel_threshold` (default `-9000.0`), `checks.zero_at_mask1_max_rate` (default `0.25`) |
| `G6` | thinking mode ≠ pins mode: `harness.thinking` and `GSJ_PINS_PATH` must agree on **both** legs (one right leg = one side rejects everything); or the served chat template is not the pinned one — on a non-reference model the tail and the end-of-turn id are measured from the endpoint, [bring-your-own.md#your-model](bring-your-own.md#your-model) | the pins file each leg resolves |
| `H41:roster_offered_zero_tool_calls` | tools offered, none called — fires only with `checks.reject_toolless_roster: true`; catches a broken retrieval service (wrong `mcp_url_base`, secret mismatch → `401`) | the retrieval service, from inside the sandbox |

## At `serve` and the callback

| Symptom | Cause → fix |
|---|---|
| `NOTE: … does not exist — this is an installed wheel — no wheel ships vendor/polar; clone https://github.com/MHGanainy/gsj-harness-rollout-server and substitute <checkout>` | the wheel is trainer-side; the server role needs a checkout — [trainer-guide.md](trainer-guide.md) |
| `NOTE: … does not exist — vendor/polar's venv is unbuilt — provision per vendor/REVENDOR.md's recipe` | build Polar's venv with the README's first-install one-liner (`uv` required — a fresh Ubuntu has none): `cd vendor/polar && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . && uv pip install -p .venv/bin/python -e ../.. && cd ../..`; `vendor/REVENDOR.md` is the pin-moving recipe (its first steps delete `vendor/polar`) — only when moving the pin. The receiver still starts in both NOTE cases |
| `UserWarning: gsj_rollout.checks: … holds the REFERENCE ESTATE's approved sets, not defaults — set GSJ_PINS_PATH to your own or every hash gate fails *_not_approved.` | once at first import with `GSJ_PINS_PATH` unset — correct against the reference estate, a trap for anyone else: set it in **every** process that imports `gsj_rollout`, before the first import |
| `PinsConfigurationError: pins file /etc/gsj/pins.gsj.json unusable: FileNotFoundError(…)` | `GSJ_PINS_PATH` points at a missing/unreadable/non-JSON file or one without a top-level `pins` key; a wrong override never falls back to the packaged copy |
| `PinsConfigurationError: pins key 'tool_roster_hash' missing, empty, or not a list in …` | the key a gate needs is absent, empty, or a string (substring membership would fail open) |
| the receiver answers **500** — `{"error": "pins configuration: …"}` in the `serve_rollout` log | the server-leg face of `PinsConfigurationError`: atomic, nothing landed in `traces_dir` or `quarantine/`; the rollout API still holds the results — fix the pins, restart |
| a traceback ending `gsj_rollout.checks.PinsConfigurationError` from `submit`/`collect` | the trainer-leg face; the CLI does not catch it |
| `collected` looks right but `traces_dir`/`quarantine/` stay empty | the callback is not arriving: check `serve` is up (`curl http://127.0.0.1:8300/healthz` → `{"status": "ok", "accepted": n, "rejected": m}`), the printed `callbacks:` URL dials **from the rollout API's host**, and the `serve_rollout` log for `Callback POST to … failed for task …; trainer must fall back to polling` (best-effort, 10 s timeout — `submit` still collects by polling; only the archive is lost) |

> [!WARNING]
> Pins are read on the first `approved_set()` call and cached for the life of the process. Fixing the file or `GSJ_PINS_PATH` takes effect only on restart — of the receiver *and* the trainer.

## The retrieval service stays `error`

`curl -s <mcp_url_base>/health` answers `{"state": "error", "error": …}` and every tool call gets a `503`. The service refuses at startup rather than serving wrong vectors (all three are named startup errors since CP-57; the service's own reference is `estate/mcp-service/README.md`):

| `error` starts with | Cause → fix |
|---|---|
| `StoreMismatchError: EMBEDDING MODEL MISMATCH — refusing to serve. The stored index at … was built by '<model>' @ '<revision>' (<d> dims), but the config names embedding.model …` | `embedding.model`/`revision` changed against an existing store — a re-pin, not staleness. To re-embed with the configured model start once with `index.rebuild: always` (or delete `index.path`); to keep the store, restore the model and revision that built it |
| `StoreMismatchError: <case>: chroma collection holds <n>-dim vectors but the configured embedding.model embeds at <d> dims` | the store's vectors are another model's (a lost or forged identity record) — same two fixes |
| `EmbeddingModelError: embedding.model '…' @ embedding.revision '…' could not be loaded (…)` | the id does not exist or is not sentence-transformers-loadable, the revision is not a commit of that repo, or the deployment runs offline (`HF_HUB_OFFLINE=1`, the H200 image) and that snapshot was not baked — rebuild the image with `EMBEDDING_MODEL`/`EMBEDDING_REVISION` |
| `EmbeddingModelError: chunking.max_tokens <n> does not fit embedding.model '…': its window is <w> tokens including <s> specials` | lower `chunking.max_tokens` well below `w − s`, or configure a model with a larger window — the shipped 220 was sized for MiniLM's 256 |
| `EmbeddingModelError: <case>: <k> of <n> chunks re-tokenize past embedding.model '…''s <w>-token window (worst: chunk <i>, <t> tokens with specials)` | the static bound passed but the real chunks overflow — a chunk is a character slice that re-tokenizes a few tokens longer than its window; lower `chunking.max_tokens` to leave headroom (220 leaves 34 under 256; a 100-token window wants ≈ 96) |

## During the episode

A sandbox failure surfaces twice: `Agent execution failed for session <id>` in the gateway log, and a callback session with `status: "ERROR"`, `traces: []`, and the exception in `error` prefixed `agent execution failed: ` — quarantined as `ADM1:status_not_completed:ERROR` + `ADM4:no_traces` + `G7:missing_evidence:reconstruction_stats`. Read `session_result.error` first:

| `error` contains | Cause → fix |
|---|---|
| `docker create failed with exit code 125: Unable to find image '…'` | image not pullable from this host (a firewalled registry — every published image is two-platform since CP-64, so not a platform miss), a daemon that cannot run a container (`docker run --rm alpine true` fails), or `runtime.network` does not exist — `docker pull <runtime.image>`, `docker network ls` |
| `PiHarness setup failed (rc=128) on 'git': "fatal: unable to access '…'"` | the harness clones **inside the sandbox** (`git clone --depth 1 --branch timestep-<T> --single-branch`), so `estate.clone_url_for` must resolve from the episode container, not the host. If the message is `Authentication failed` / `could not read Username` (not a DNS/route error), the estate requires sign-in for read and `estate.clone_credential_env` is unset, names a variable that is neither exported nor in the `.env` beside the config (CP-75, shipped at 0.1.7; wheels through 0.1.6 read the environment only), or holds a wrong/expired read token (CP-56) — mint it with `estate.sh owner` and export it, or let an `estate.py` run directory carry it (`submit` reads the `.env` beside its `rollout.yaml`, never exported) |
| `PiHarness setup failed (rc=…) on 'mkdir'` | the first step — pi settings under `/tmp/pi-agent` — failed: wrong `runtime.image` (no `sh`, or read-only `/tmp`) |
| `PiHarness workspace probe failed` / `probe returned no ['branch', …]` | the clone "succeeded" but the checkout is wrong — check the case repository has a `timestep-<T>` branch |
| `PiHarness: token secret env var 'GSJ_MCP_TOKEN_SECRET' is unset in the gateway process` | export the variable named by `estate.mcp_token_secret_env` before the gateway command (`serve` prints it with `GSJ_MCP_TOKEN_SECRET=<secret>` in front); it must equal the retrieval service's own secret, else `search_case` gets `401` and the episode completes with no pages (→ `H41` if armed) |
| `PiHarness settings missing required keys: […]` | the request was not rendered by `render_task_request` — `agent.settings` needs `case_id` `timestep` `clone_url_for` `mcp_url_base` `tools_allowlist` `artifacts_dir` |
| `PiHarness requires model_name as 'provider/model'` | the renderer builds `<estate.provider>/<estate.model>`; a hand-built request must too |
| `step <i> exited with code <rc>` | pi exited non-zero — its output is in `<session_dir>/logs/agent/step.<ii>.stdout.log` / `.stderr.log` on the gateway host, its transcript in `<artifacts_dir>/<session_id>/pi_transcript.jsonl` |

> [!WARNING]
> The three networking traps that cost live episodes:
> 1. **Docker isolates networks.** With `runtime.network: bridge` (the default) the sandbox cannot reach a Forgejo at a static IP on the compose network (`172.28.9.10` on the H200 file). Fix in config, not code: `runtime.network: gsj-staging-net`.
> 2. **No `--add-host` on Linux.** Polar's Docker runtime passes only `--network`, so `host.docker.internal` never resolves inside episode containers — any of `estate.clone_url_for`, `estate.mcp_url_base`, `polar.gateway.public_url` written with it fails from the sandbox. Use the compose network's own gateway IP instead (`172.28.9.1` on H200, where the retrieval service `0.0.0.0:8790` and gateway `0.0.0.0:8200` bind the host; `172.17.0.1` names the default bridge, not the episodes' network). Find yours: `docker network inspect <runtime.network> --format '{{(index .IPAM.Config 0).Gateway}}'`.
> 3. **`polar.gateway.public_url` has two callers** — the rollout API dispatches sessions to it from the host, and pi inside the container sends every model call to it + `/v1`. Never `localhost`: `http://127.0.0.1:8200` dispatches fine but pi cannot reach the capture proxy → `ADM4:no_traces` with a quiet gateway log; an address the rollout API cannot reach → the gateway never registers → `(0/N sessions)` timeout. H200's `http://172.28.9.1:8200` works because that IP is host-local *and* on the sandbox network.

Probe `public_url` from both sides — any HTTP status means the gateway answered:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://172.28.9.1:8200/                        # from the host
docker run --rm --network gsj-staging-net curlimages/curl -sS -o /dev/null -w '%{http_code}\n' http://172.28.9.1:8200/   # from the sandbox network
```

Quick reference — who dials what:

| Value | Dialled by | Wrong-value symptom |
|---|---|---|
| `estate.clone_url_for` | the episode container (`git clone`) | `PiHarness setup failed (rc=128) on 'git'` → `ADM1` |
| `estate.mcp_url_base` | pi inside the container | no retrieved pages; `H41` if armed |
| `estate.serving_base_url` | the gateway process only | `/v1` suffix rejected at load; otherwise pi's calls fail through the proxy |
| `polar.gateway.public_url` | the rollout API **and** pi in the container | no registration → `(0/N sessions)` timeout; or `ADM4:no_traces` |
| `polar.rollout.host/port/public_url` | the trainer, the gateway | exit 3 |
| `receiver.host/port/public_url` | the rollout API (callback) | nothing lands on disk; `submit` still collects |

## At `estate/estate.py` — REFUSED

Every refusal prints `found:` / `expected:` / `what to do:`; the message is the fix. Run-boundary and service refusals:

| Refusal | Cause → fix |
|---|---|
| `run name … is not a token` / `run … escapes its named directory` / `run ownership is unproved` / `refusing to use … as a run` | Use a name beginning with a lowercase letter or digit, followed only by lowercase letters, digits, `-` or `_`, and the original `--runs-dir`; a run must be its direct directory, without a symlink. `.estate-run`, a supported matching `run.json` or a generated run file proves ownership. Restore this run's metadata from backup or choose another name; preserve unrecognized data. `down` without `--wipe` can stop recoverable owned services. |
| `run … is busy` / a run lock directory or lock file cannot be created or opened | Wait for the mutating command to finish — `status --name <run> --runs-dir <root>` says `ACTIVE` while one holds the lock (since CP-94), reports the phases that stand and exits 0; it never prescribes a second `up`. The runs root must already exist and be writable; correct `--runs-dir` or its permissions. If `.locks/` is inaccessible, the refusal names its owner uid and your effective uid: run as its owning user with directory write/search permissions. Restore a damaged lock directory or file as directed, preserving live lock inodes. `<runs-dir>/.locks/<name>.lock` survives `--wipe`; **do not delete lock files**. |
| `Docker cleanup failed or is unverified` / an adopted run's network is unverified before `--wipe` | Run data is preserved until owned resources are verified absent. Restore Docker daemon/socket access or fix the reported Compose/resource error, inspect the run's Compose-labelled containers and `docker network inspect gsj-<run>-net`, resolve active endpoints with their owner, then re-run `down`. With no usable `run.json` and no `compose.yaml`, ownership of the network is unknown: restore `run.json` from backup and re-run `down`; `down` warns and `--wipe` refuses rather than discarding that recovery directory. |
| `… run.json is not a supported run record` / a `.env` line is malformed or has an unsupported credential value | Restore `run.json` from backup or use the tool version that wrote its supported schema; `down` can recover partial state without loading `.env`. For a refused `.env` line, rotate the credential at its service if needed, then edit the named line **by hand** to `KEY='value'` with a compatible value and LF framing. After that repair, re-run `up` to adopt from the named environment variable or credential file; exporting a replacement alone does not bypass the refused stored line. Alternatively, `down --name <run> --runs-dir <root> --wipe` and start over. |
| `the retrieval service in gsj-<run>-mcp crashed (its process died; the container still shows running)` — `qemu: uncaught target signal 11` in its log | the amd64 `gsj-mcp-service` image under emulation on an arm64 daemon dies at the embed step (0.3.0 survived it, 0.4.0 does not); build it natively (`docker build --platform linux/arm64 -t gsj-mcp-service:0.5.0-arm64 estate/mcp-service`) and pass `--mcp-image gsj-mcp-service:0.5.0-arm64`. Production is amd64 and runs the shipped image as is |
| `the adopted retrieval service serves a different embedding identity` / `the run's index store was built by a different embedding model` | CP-57's posture: a model change is a re-pin, never a silent rebuild — ask for the identity that built the store, or `--rebuild` (own store) / `index.rebuild: always` once on the adopted service |
| `owner '…' on <url> holds N repo(s) whose content is NOT what this corpus builds` — branches named per case | someone else's (or an edited) repo under a case id; another `--owner`, delete them there, or `--overwrite-repos` (a `--force --prune` push) |
| `the admin credential for … was rejected` with a valid token | Forgejo mints another user's tokens only under **basic auth**: give the admin's password (`$GSJ_FORGEJO_ADMIN_PASSWORD` or `--forgejo-admin-password-file`), not a token |
| `the adopted retrieval service rejected the token secret` — `POST /admin/reindex -> 401 … Signature verification failed` | the secret given (`$GSJ_MCP_TOKEN_SECRET` / `--mcp-secret-file`) is not the one the service's `config.yaml` `token_secret_env` names — ask its operator |
| `run '…' recorded the owner = '…'; this invocation asks for '…'` (also the Forgejo/MCP URL, the network, create vs adopt) | a re-run reuses the recorded estate; a different identity is another run (`--name`), a wipe, or `--retarget` — which rewrites the record and prints `changed:` lines |
| `no host address is dialable from a container on '…'` — `tried [...] — every one timed out from the container` | CP-03's one-URL rule has no answer on this host: on Docker Desktop add `127.0.0.1 host.docker.internal` to `/etc/hosts` and pass `--gateway-host host.docker.internal`; `--gateway-host <address>` writes one unprobed (the episode then fails `no completions` if a sandbox cannot dial it — the gateway log shows session polls and no `/v1/chat/completions`). The run is resumable: every phase before the probe is recorded and reused. Since CP-96 the dial runs by `docker exec` inside the run's own retrieval container — nothing is created, nothing can leak; `up --help` says how to choose an address when the probe cannot run |
| `WARNING: the gateway-host probe could not run — timed out after N s via …` (CP-96; before it, a bare `subprocess.TimeoutExpired` traceback one file short of `rollout.yaml`, and a `Created` container from the sandbox image left behind on every attempt) | the probe, not the estate, failed: the run continues with the first candidate written **UNMEASURED** and names the candidates it was about to try. Round four measured why: on a copy-on-create storage driver (`vfs`) creating a container from the 731 MiB sandbox image alone outlasts any probe budget. The exec form needs no container; the `docker run` fallback (an adopted retrieval service and no container of the run's own) is named `gsj-probe-<pid>` and removed in a `finally` whatever happens. If a sandbox cannot dial the written address, re-run `up` with `--gateway-host <address>` (the run is resumable) |
| `run '…' exists but its .env is missing` | restore it — a re-mint would invalidate the running service's secret and every token the record names; or `down --wipe` and start over |
| the corpus pipeline's `scaffold` fails `post-push read-back … terminal prompts disabled (anonymous read — … needs GSJ_FORGEJO_READ_TOKEN_<OWNER> exported)` | an estate requiring sign-in and no read token in the environment (CP-59 — the push itself succeeded); `estate.py` exports it from the run's `.env` |
| `the Forgejo image … could not be pulled` — `failed to copy: httpReadSeeker: failed open: content at …/manifests/sha256:… not found` | the tag's registry dropped a platform manifest its index still lists (codeberg did this to `16.0.2`, measured 2026-08-30 — wishlist 52); pass `--forgejo-image <ref>` naming a live one: another tag, the mirror `code.forgejo.org/forgejo/forgejo:<tag>` (the same digests), or `name@sha256:…`; on a host that cannot reach registries at all, `docker save \| docker load` the image and re-run (CP-62) |
| `the retrieval service image … is not present on this daemon and could not be pulled` | both estate defaults select `ghcr.io/mhganainy/gsj-mcp-service:0.5.0` from library 0.1.8; it supports `--decisions-dir`. Registry images are pulled when absent; `--mcp-image` selects a custom or offline loaded image. Wheel 0.1.7 defaults to 0.4.1 and needs the explicit published 0.5.0 override for a drop (wishlist 77); wheels 0.1.4–0.1.6 default to 0.4.0 and have no `--decisions-dir`. |
| `WARNING: … resolved to […], not the index this script measured` | the pinned tag was re-cut on its registry since it was measured: the run continues, but the admin-CLI/token/sign-in measurements were made on the recorded bytes — pin them with `--forgejo-image name@sha256:…` if the phases behave differently |
| `… is absent on this daemon — pulling it` then nothing for minutes, or `still pulling <image> — Nm elapsed; this host received … / NOTHING` (the CP-94 heartbeat, once a minute) | a large layer on a slow pipe prints nothing until it lands — 21 minutes measured on a healthy pull at ~155 KB/s, 39 for the 1.28 GiB retrieval image; `docker pull` prints a line only when a layer changes state. Three checks before you conclude it hung, in order: (1) the heartbeat's byte line — this host still receiving means slow, not hung (on a remote daemon the counters are that host's, not the daemon's); (2) `df -h` on the daemon's data root twice a minute apart — it grows as layers land (**not** `docker system df`: measured flat through an actively progressing pull on Docker 29.8, which accounts an image only once it is complete — round four); since CP-96 the heartbeat also names the layer phase (`N/M layers complete, K extracting …`) and says when **no bytes are expected** — an extraction moves the disk, not the pipe, and a stranger counted `Download complete` against `Pull complete` by hand to tell the two apart; (3) the two failure signatures (`Retrying in N seconds`/`unexpected EOF`, `failed to extract`/`failed to mount`) — a hung pull eventually prints one on stderr, a healthy one never does. Only then interrupt `up` (Ctrl-C; exit 130) and re-run it: every phase is idempotent and the daemon resumes from the layers it kept. Do not start a second pull of the same image beside it — a stranger did and measured its own rate drop from 156 to 4 KiB/s |
| `the sandbox image … is not present on this daemon` | `up` checks presence only, it never pulls the harness image — and since CP-94 it checks **first**, before any container is pulled or created (a round-three stranger met this refusal after 41 minutes of pipeline; the text is unchanged): a plain `docker pull ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3` (a two-platform index since CP-64 — native on arm64, measured by a stranger 2026-09-06: `linux/arm64`, Node ran); `--platform linux/amd64` only if that pull answers `no matching manifest` for your platform; `--skip-sandbox-image` records the absence and continues (CP-92: the refusal used to build the amd64 override on every arm64 daemon) |
| `… could not be pulled` / `docker compose up … failed` after the daemon downloaded every layer, then `failed to extract layer … whiteout … operation not permitted` or `failed to mount … overlay … invalid argument` | the registry answered — this daemon's storage cannot extract or mount OCI layers (a nested daemon whose data root sits on overlayfs, measured 2026-09-06: `docker info` fine, `docker pull debian:stable-slim` fine, no container starts). Prove it with `docker run --rm alpine true`; fix the daemon (`-v /var/lib/docker` on a nested daemon, or `--storage-driver vfs`), not the registry — `docker save \| docker load` fails on the same layers. Since CP-92 the pull refusals split by where the pull failed: a download failure keeps the registry cure, an extraction or mount failure says this |
| `run '…' is incomplete` (an `up` that died mid-phase — the lock is free; a held lock is `ACTIVE`, not this) | since CP-92 `status` first prints the phases that completed and the services that stand (Forgejo's health, the tokens, the pushed repos, what was not reached — since CP-94 the retrieval-service row asks the daemon, because the record's `mcp` block lands only after ingest, and the engine/config rows say `not recorded`/`not written` rather than guessing), then the cure: re-run `up --name <run> --corpus <the run's corpus root>` to resume (`reused:` lines — the corpus is asked before the record is read: the wheel has no default and a checkout's default is its staging fixture; the printed cure carries the recorded path), or `down --name <run>` to stop what it created |

| `the retrieval service did not reach state=ready within the N s budget (--ingest-timeout)` — `found: waited N s on this process's clock (the wall clock advanced M s); last: …` | the budget is spent on this process's clock since CP-96 (a host that slept no longer burns it — round four's overnight run fired a wall-clock deadline on wake and printed the configured 1800 s as if enforced), and the refusal prints what it waited beside what was budgeted; a poll that has not changed for a minute is repeated with the measured wait, and the collection the service is BUILDING (its `build` block — `building decisions: batch i/N (v/t vectors)`) is on the line, so a decisions embed no longer reads as finished-and-idle. `last: indexing …` means the service is still working: re-run `up` **without** `--rebuild` to keep waiting — the index survives and a `--rebuild` re-run attaches to a build still in progress rather than embedding from zero (CP-96) — or raise `--ingest-timeout` (the demo forwards it since library CP-96). A cold embed on a contended CPU host is minutes, not seconds; `last: unreachable` is a service that stopped answering — `docker logs --tail 80 gsj-<run>-mcp` |
## See also

- [validation-and-pins.md](validation-and-pins.md) — the complete finding vocabulary, the gates, re-pinning.
- [bring-your-own.md](bring-your-own.md) — a foreign model's values from its endpoint, and a foreign corpus's pins from its first quarantine.
- [server-guide.md](server-guide.md) — the YAML fields, the receiver contract, the estate services these values point at.
- [checks-spec.md](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) — each rule's reasoning.
