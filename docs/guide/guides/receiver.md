[Documentation](../README.md) › Guides

# The receiver

The receiver is the server-side endpoint that Polar delivers finished episodes to. This page explains what it is and how `gsj-rollout serve` starts it, the two HTTP paths it answers and every response they can give, the atomicity guarantee behind a multi-result callback and why it exists, where accepted and quarantined results land on disk and how the files are named, the shape of a quarantined file, what the counters and log lines tell you, and how to read a quarantined file to find out why a trace was refused.

## What it is

`gsj_rollout/receiver.py` is a small HTTP server built on the standard library's `http.server.ThreadingHTTPServer` — no web framework, by design: the endpoint has one job, and a framework would add a dependency and a process model of its own. It is our code, not Polar's. Polar's rollout manager knows it only as the `callback_url` that `render_task_request` puts on every `TaskRequest`:

```python
"callback_url": f"{cfg.receiver.base_url}/callbacks/session_result"
```

When a task reaches its terminal state, Polar `POST`s the results to that URL. The receiver runs every result through `checks.validate_session_result` — the same function the trainer runs on what it collects (see [Validation](../concepts/validation.md)) — and lands it on disk as either an accepted trace or a quarantined one, with its findings. That is the whole surface: one `POST` path, one `GET` path for health, two directories.

Two properties are worth knowing before the details:

- **It validates the POSTed body, never Polar's on-disk copy.** Polar's own `ses_*.json` files strip `trajectory.status` and `error`; the body it POSTs carries them. The receiver persists the body it received, byte-for-byte after JSON re-serialization, so `status` and `error` are in the archive.
- **It installs no signal handlers.** `Receiver` is constructed, then `serve_forever()` and `shutdown()` are called by whoever owns the process. `gsj-rollout serve` owns them for its own lifetime; an embedder owns them otherwise.

## Starting it

`gsj-rollout serve` is the console script that starts the receiver. Given the one YAML it:

1. loads and validates the config (a bad config exits 2 before anything is written);
2. renders `topology.rendered.yaml` next to the YAML and prints the two Polar commands (`serve_rollout`, `serve_gateway`) for you to run yourself — the receiver never supervises Polar's processes;
3. prints the callback line: `callbacks: <base_url>/callbacks/session_result | traces -> <traces_dir> | quarantine -> <quarantine_dir>`;
4. constructs `Receiver(host, port, traces_dir, quarantine_dir)`, which creates both directories if they do not exist (`makedirs`, `exist_ok=True`) and reads the pins mode (below);
5. prints `receiver listening on <host>:<port>`, serves in a daemon thread, and waits for `SIGINT` or `SIGTERM`;
6. on the signal, shuts the server down, restores the previous signal handlers, and prints `receiver stopped: accepted=<n> rejected=<m>`.

`--render-only` stops after step 3 and exits 0 without starting the receiver.

```bash
GSJ_PINS_PATH=/etc/gsj/pins.gsj.json gsj-rollout serve --config rollout.yaml
```

The `receiver:` section of the YAML is everything the receiver reads from configuration ([Configuration](configuration.md) covers the whole file):

| key | default | meaning |
| --- | --- | --- |
| `host` | `127.0.0.1` | bind address |
| `port` | `8300` | bind port |
| `public_url` | none | the URL Polar should call back on, when it differs from `http://<host>:<port>` — for example when the receiver listens on `0.0.0.0` behind a LAN address |
| `traces_dir` | **required** | where accepted traces land; no default on purpose, because this is the training data and a temporary-directory default would lose it silently |
| `quarantine_dir` | `<traces_dir>/quarantine` | where rejected results land with their findings |

`base_url` is `public_url` when set, else `http://<host>:<port>` with `0.0.0.0`/`::` rewritten to `127.0.0.1`. The callback URL must be reachable **from Polar's rollout-server process**, wherever that runs — it is embedded in every `TaskRequest`, and a URL Polar cannot dial means every callback fails to deliver.

> [!TIP]
> **Embedding the receiver**
>
> Because it has no signal handling and no global state beyond the process-wide pins cache, the receiver embeds in a few lines. Port `0` binds an ephemeral port; read it back from `.port`.
>
> ```python
> import threading
> from gsj_rollout.receiver import Receiver
>
> receiver = Receiver("127.0.0.1", 0, "/data/traces", "/data/traces/quarantine")
> thread = threading.Thread(target=receiver.serve_forever, daemon=True)
> thread.start()
> print(receiver.port)            # the bound port
> ...
> receiver.shutdown()             # safe whether or not serve_forever ran
> thread.join(timeout=5.0)
> ```
>
> `receiver.ingest(body)` is the same code path the `POST` handler calls; it returns `(accepted, rejected)` and raises exactly what the handler would map to a 400 or 500 (see below). It is how the test suite drives the receiver without HTTP.

## Endpoints

Every response is JSON with `Content-Type: application/json` and a `Content-Length`. There are two paths; anything else is a 404.

| method and path | status | body | when |
| --- | --- | --- | --- |
| `GET /healthz` | 200 | `{"status": "ok", "accepted": n, "rejected": m}` | always; the counters are process-lifetime |
| `GET <anything else>` | 404 | `{"error": "not found"}` | |
| `POST /callbacks/session_result` | 200 | `{"accepted": n, "rejected": m}` | every member of the body was dispositioned — accepted traces and quarantined ones both count as delivered |
| | 400 | `{"error": "<reason>"}` | the body is at fault: not JSON, not an object, a member without `trajectory` or with an unsafe `session_id`, or a member whose payload cannot be serialized |
| | 500 | `{"error": "pins configuration: <detail>"}` | the pins file or one of its keys is unusable; the detail names the path or key |
| | 500 | `{"error": "receiver: <ExceptionType>: <detail>"}` | anything else raised while landing the batch — in practice a filesystem fault during staging or commit |
| `POST <anything else>` | 404 | `{"error": "not found"}` | answered before the body is read |

The `POST` body is one of two shapes, and both are unwrapped to a list of `SessionResult`s ([Wire formats](../reference/wire-formats.md) has the full schemas):

- **a single `SessionResult`** — a JSON object with a `trajectory` key and a `session_id`. This is the per-session shape the golden fixtures carry.
- **a `TaskResult` envelope** — a JSON object whose `results` key is a list of `SessionResult`s. This is what Polar's manager actually sends at task end; its other keys (`task_id`, `status`, `result_paths`) are ignored. An envelope with `results: []` answers `200 {"accepted": 0, "rejected": 0}`.

Every member must pass the **shape screen** before anything is validated: it is an object, it has a `trajectory` key (of any type — a malformed trajectory is a *finding*, not a 400), and its `session_id` is a string matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` in full. The regex exists because the id becomes a file name: `../evil` is refused with a 400 rather than walking the filesystem. It is the same pattern Polar's gateway applies to its own session ids (`SESSION_ID_PATTERN`, 128 characters at most), so an id Polar would refuse is refused here too, and an over-long-but-legal id fails at the shape screen instead of at the write.

![Polar's manager delivers a callback to the receiver, and three answers fan out: 200, every member dispositioned, pointing at the accepted and quarantined folders; 400, the body is at fault; 500, the server's fault; the 400 and 500 arrows both end at a "nothing lands, archive untouched" tile](../img/receiver-responses.png)

<sub>The three answers to a callback. A 200 carries the counts and covers both verdicts; a 400 or a 500 means nothing landed in either directory, and the body says whose fault it was.</sub>

> [!NOTE]
> **200 does not mean accepted**
>
> A rejection is the receiver's validation verdict on a delivered result, not a delivery failure, so Polar gets a 200 for it. Read the counts. A 400 or 500 is the only signal that a callback did **not** land, and in that case it landed nowhere — see the next section.

## The envelope is atomic

A callback may carry many `SessionResult`s, and validating one of them can raise: a hash gate needs the pins file, and an unreadable pins file, or a key that is missing, empty, or not a list, raises `PinsConfigurationError` — the server's configuration fault, never the caller's. A payload can also defeat `json.dumps` (deeply nested but legal JSON can exhaust the serializer's stack). Without care, either failure in the middle of a batch would leave the first members on disk, the rest unwritten, an orphaned temporary file, and the connection dropped with no HTTP response — an archive that disagrees with what Polar was told.

`Receiver.ingest` therefore works in two phases, and the guarantee is: **every member of an envelope is dispositioned, or none is.**

![Map of the two-phase ingest: Polar's callback envelope enters an in-memory lane (shape screen, validate, plan) and then an on-disk lane (stage, commit), landing in traces_dir or quarantine_dir; a fault in the memory lane exits to "nothing written" (400 or 500), a fault in the disk lane to "stages unlinked" (500)](../img/receiver-ingest.png)

<sub>The five steps of an ingest. The first three run in memory and can only abort with nothing written; the last two touch disk, and a fault there unlinks every staged file before the error is answered. Both landing places name the file after the session id and the pins mode.</sub>

**Phase 1 — in memory.** For every member, in order: `checks.validate_session_result(result)` produces the findings list; the payload to persist is the result itself when the list is empty, or `{"findings": [...], "session_result": result}` otherwise; and that payload is serialized with `json.dumps` *now*, so an unserializable member raises here, as a `ValueError` (a 400: the body is the caller's). The member is then **planned**: one target path and one serialized text per `session_id`. If the same `session_id` appears twice in one envelope, the later member wins — one id must never land as both an accepted trace and a quarantined one, and two members must never contend for the same temporary file.

**Phase 2 — disk.** Every planned entry is written to `<path>.<i>.tmp` (where `<i>` is its index in the plan, so stages are unique), and only when all of them are staged is each one committed with `os.replace` — an atomic rename within one filesystem, which is why the stage sits beside its target rather than in a temporary directory. If anything in this phase raises, every staged `.tmp` is unlinked and the exception propagates; nothing half-lands, and no orphan is left behind.

The two 500 bodies map onto the two phases: `pins configuration: <detail>` can only come from phase 1, where a hash gate opened the pins file, so it always means nothing was written; `receiver: <ExceptionType>: <detail>` is the catch-all for phase 2, a stage or commit that raised, and by the time it is answered every stage has been unlinked. A 400 is always phase 1: the shape screen or the serializer refused the body.

Only after the commit do the counters move and the log lines fire. The consequences, all of which the test suite pins down over HTTP:

- A missing pins file with a batch of `[pins-free member, real member]` answers 500 and leaves both directories empty — not even the member that needed no pins is written, and the counters stay at zero.
- A member that will not serialize answers 400 and nothing lands.
- A `traces_dir` that is not writable answers `500 {"error": "receiver: PermissionError: ..."}`, and the quarantine member that *could* have been written is not.
- Two members with one `session_id`, the second one erroring, answer `200 {"accepted": 0, "rejected": 1}` with a single quarantine file and no `.tmp` left over.

> [!NOTE]
> **What a 400 or 500 costs**
>
> Only the receiver's archive. The trainer collects through Polar's `GET /rollout/task/{id}` and re-validates on its own side ([Validation](../concepts/validation.md)); it never reads `traces_dir`. So a failed callback is a missing record on the server, which is exactly what the counters and the log will tell you — not lost training data.

## On disk

```text
<traces_dir>/
├── sk-polar-c4eef751-….thinking-off.json      accepted: the SessionResult, verbatim
├── sk-polar-180dd057-….thinking-off.json
└── quarantine/                                 <quarantine_dir>, default location
    └── sk-polar-9a1e0b3c-….thinking-off.json  rejected: {"findings": [...], "session_result":}
```

The receiver writes only at the top level of each directory. A file name is `<session_id>.<pins_mode>.json` in either, and one callback never produces the same name in both — the plan holds one disposition per `session_id`. A later callback that re-delivers an id overwrites the earlier file in whichever directory it lands in (`os.replace`); the receiver does not remove a stale copy from the other directory. Session ids are Polar's (`sk-polar-<uuid4>` from the manager), which is why the name is safe to use once it has passed the shape screen. During a commit you may briefly see `<name>.json.<i>.tmp` beside the target; those are stages, and they never survive a request, successful or not.

**Where `<pins_mode>` comes from.** When the `Receiver` is constructed, it opens `checks.PINS_PATH` — the pins file resolved for this process ([Pins and approved sets](../concepts/pins.md) gives the resolution order) — and reads its top-level `mode` key:

| the pins file… | stamp |
| --- | --- |
| has no `mode` key (the shipped reference set) | `thinking-off` |
| declares `"mode": "thinking-on"` (the shipped thinking-on set) | `thinking-on` |
| declares any other string matching `[A-Za-z0-9][A-Za-z0-9_-]{0,31}` | that string |
| cannot be opened or is not valid JSON, or `mode` is not such a string | `pins-unresolved` |

The stamp exists because a single `traces_dir` typically outlives many `serve` runs, and a thinking-on collection and a thinking-off one are otherwise distinguishable only by reading token ids. With the mode in the name, a mixed archive stays attributable, and a quarantined file also says which pins document the process judged it under.

> [!WARNING]
> **`pins-unresolved` is a misconfiguration, not a mode**
>
> The stamp is read once, at construction, and it does not fail startup. A receiver whose pins file is unusable starts normally and answers 500 to every callback whose members reach a hash gate — but a member that never reaches one (a `trajectory` that is not an object, or an empty `traces` list — an `ERROR` status alone is not enough, because the trace checks still run on whatever traces the member carries; a member with no `trajectory` key at all is a 400 at the shape screen) is quarantined under the `pins-unresolved` name. If you see that token in a file name, the process that wrote it was pointed at a pins file it could not read: fix `GSJ_PINS_PATH` and restart, on both legs.

**What the files contain.** An accepted file is the `SessionResult` exactly as POSTed — `status`, `error`, `trajectory`, everything — written with `json.dumps` defaults (one line, no indentation). Loading it back and comparing to the body Polar sent is an equality, and the test suite asserts it on a real callback body. A quarantined file wraps the same untouched body:

```json
{
  "findings": [
    "ADM1:status_not_completed:ERROR"
  ],
  "session_result": {
    "session_id": "sk-polar-9a1e0b3c-…",
    "status": "ERROR",
    "error": "…",
    "trajectory": { "metadata": { "…": "…" }, "traces": [ "…" ] }
  }
}
```

`findings` is the list `validate_session_result` returned, in the order the rules ran; `session_result` is the member verbatim. Nothing is dropped or normalized on the way to quarantine — forensics beat counters, and the body you inspect is the body that was judged.

## Counters and logging

Two integers, `Receiver.accepted` and `Receiver.rejected`, count dispositions for the life of the process. They are incremented per member **after** the batch commits, so a 400 or 500 never moves them, and they are visible three ways: in every `POST` response (that request's counts, not the totals), in `GET /healthz` (the totals), and in the `receiver stopped: accepted=<n> rejected=<m>` line `serve` prints on exit. Nothing persists them; a restart starts from zero, and the directories are the durable record.

Log lines go to the `gsj_rollout.receiver` logger:

| level | line | when |
| --- | --- | --- |
| `INFO` | `accepted <session_id>` | per accepted member, after commit |
| `WARNING` | `rejected <session_id>: ['ADM1:…', …]` | per quarantined member, after commit — the full findings list |
| `ERROR` | `receiver failed to ingest` plus the traceback | an unforeseen exception in `ingest`, the one that becomes `500 receiver: …` |
| `DEBUG` | `<client address> "POST /callbacks/session_result HTTP/1.1" 200 -` | every request; the stdlib access log, rerouted from stderr |

The package configures no handler, and neither does `serve`. Under `gsj-rollout serve` that means Python's last-resort handler applies: `WARNING` and above reach stderr, so you see every rejection with its findings and every ingest failure with its traceback, but not the `accepted` lines. To see those, or to send the log anywhere in particular, configure logging in an embedding process:

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
```

Pins and validation faults are not logged by the receiver beyond the response body: a `PinsConfigurationError` answers 500 with the path or key in `error`, and a 400 answers with the reason. Polar's manager receives those bodies; what it prints is Polar's.

## Reading a quarantined file

Quarantine is forensics, not a queue: the receiver never re-reads it, the trainer never reads it, and nothing moves a file from `quarantine/` to `traces/`. What it gives you is the exact body that was judged, next to the verdict. To find out why a trace was refused:

**1. Read the findings.** The list is the answer; everything else is context.

```bash
python -c 'import json, sys; print(*json.load(open(sys.argv[1]))["findings"], sep="\n")' \
  /data/traces/quarantine/sk-polar-9a1e0b3c-….thinking-off.json
```

Every finding is `<rule>:<slug>[:<detail>]`, byte-stable, and the rule prefix says which layer refused the trace. The full vocabulary is in [Finding vocabulary](../reference/findings.md); the families are:

| prefix | layer | typical meaning |
| --- | --- | --- |
| `ADM1`–`ADM5` | admission | the builder or Polar already decided: `ADM1:status_not_completed:ERROR` (the episode did not complete — read `session_result.error`), `ADM2:builder_findings_present:<n>` (the builder's own findings follow, re-emitted verbatim), `ADM3:trajectory_missing`, `ADM4:no_traces`, `ADM5:malformed_trace` |
| `G1`–`G7` | the gates | an approved-set or cutoff gate failed; `*_not_approved:<digest>` carries the digest the gate computed; `G<n>:missing_evidence:<what>` means the trace did not carry what the gate needs |
| `LP1`–`LP9` | logprob discipline | `response_logprobs` and `loss_mask` against `response_ids`: absent, wrong length, non-binary mask, empty mask, non-finite or positive values, sentinel or zero logprobs at trained positions beyond the policy's rate |
| `TR1`–`TR3` | tripwires | `finish_reason` not allowed, reasoning tokens masked out of the loss, `split` not `train`/`eval` |
| `H41` | policy-gated | the toolless-roster rule, off by default |

**2. Decide whether it is the trace or the estate.** Some patterns say "this estate's pins do not match this receiver's" rather than "this trace is bad":

- Every episode quarantines with the same `*_not_approved:<digest>` — the receiver is validating against the wrong approved sets (a fresh `pip install` validates against the reference estate's). Point `GSJ_PINS_PATH` at your own file and restart; [Pins and approved sets](../concepts/pins.md) explains how to derive one, and the digest in the finding is the value you would pin.
- Every episode quarantines with `G6:prompt_suffix_ne_tail_ids` plus a `G6:interstitial_ne_tail_ids:first=…:count=…` — a thinking-mode mismatch between `harness.thinking` and the pins file. The file name's `<pins_mode>` tells you which side is wrong.
- `pins-unresolved` in the file name — the pins file was unreadable when this receiver started (see the warning above).

**3. Re-judge it yourself.** Because `session_result` is the untouched body, you can run the same validator on it in any process — for example under a corrected pins file, to confirm that the findings were a configuration problem before you collect again:

```python
import json
from gsj_rollout import checks

with open("/data/traces/quarantine/sk-polar-9a1e0b3c-….thinking-off.json") as handle:
    doc = json.load(handle)

print(doc["findings"])                                  # the receiver's verdict
print(checks.validate_session_result(doc["session_result"]))   # this process's verdict, under its own pins
```

An empty list from the second call means the body would be accepted now; it does not retroactively accept it. The archive records what each process decided under the pins it had, which is the point of the stamp in the name.

> [!TIP]
> **When nothing was written at all**
>
> A callback that answered 400 or 500 has no quarantine file to read. The 500 body names the pins path or key, or the exception class of the write fault; the 400 body names the shape problem; and an ingest failure of the `receiver: …` kind also leaves a traceback on stderr under `serve`. `GET /healthz` still answers during any of this — the receiver never lets an exception leave a connection unanswered, and never stops serving because one batch failed.

## See also

- [Validation](../concepts/validation.md) — the function the receiver runs on every member.
- [Wire formats](../reference/wire-formats.md) — the callback envelope, the `SessionResult`, and the quarantine wrapper.
- [Finding vocabulary](../reference/findings.md) — every string a quarantine file can carry.
- [Configuration](configuration.md#receiver) — the `receiver:` section.
- [Troubleshooting](troubleshooting.md#at-serve) — the 500, the pins warning, and nothing landing on disk.
