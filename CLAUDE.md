# CLAUDE.md — gsj-harness-rollout-server

## Project

**gsj-harness-rollout-server** is a **rollout server for our corpus**. Given a task `(case, timestep, prompt)` it runs our agent in an isolated sandbox with temporally-scoped retrieval and emits a training-ready trajectory. It is trainer-agnostic, algorithm-agnostic, and parameterization-agnostic. Episode execution and trajectory reconstruction are built on NVIDIA's Polar, vendored by SHA (`POLAR_SHA`; three carried patches). Published on PyPI as `gsj-harness-rollout-server` **0.1.17** (wheel-only, 18 entries: `gsj_rollout/`, both pins sets + the G2 container capture, `ingest_corpus.py`, `estate.py` — `bringup.py` on wheels 0.1.3–0.1.5). Predecessor: `gsj-envloader` @ v0.8.0 — **archived at CP-45** (2026-08-25, ADR-0026): still the golden reference (the collecting stack for both goldens, readable at v0.8.0), no longer the fallback — that term expired when the verdict converted (CP-17, 2026-08-11). Consumer repos, both public: `gsj-harness-rollout-server-examples` (trainer-side; external register F-01–F-53, F-79 minted there at CP-69 and F-81 recording the CP-82 training findings) and `gsj-rollout-demo` (bring-your-own estate; register F-54–F-78 plus F-80, the CP-81 decisions/case-content finding, F-82 recording the CP-82 reader findings, F-83–F-86 minted at CP-92 for what four containerised strangers found in the demo, F-87–F-92 at CP-94 for round three's four, F-93–F-100 at CP-96 for round four's, F-101–F-105 at CP-99 — row 100's demo half plus what round five's two demo-door strangers found — and F-106–F-117 at CP-101 for round six's two demo-door strangers plus the demo half of wishlist row 107, F-118–F-120 at CP-103 for the step-1b instrument, and F-121–F-128 at CP-104 for round seven's two demo-door strangers — the last round) — one F-series across both, next fresh id F-129 (the examples trailer still says F-83 until its next mint). The library's own register (`docs/VERDICT.md` wishlist) runs to row 112; next fresh row 113. The normative document is `docs/CHARTER.md`; this file governs process only.

Current release: **0.1.17**, source `0bc15de7f034d6f031b4135d1fe0245ec31ddb52` / `v0.1.17`, normal PR #3 merge `08421222b7d37d9f14792c156730c66580ca2bfc`; retrieval is independently versioned **0.5.1**. The wheel on both public indexes, matching retrieval/Polar images and the tested demo `aefe16b4e363a4892676bbd44b64f322eb5f3ad2` are delivered. CHARTER §7 records the executed gates, qualified recovery inventory guard, fresh t=2 hallucination and preserved production obligations; this later factual record does not change the immutable release source.

## Scope laws

1. **The scope law**: "The rollout server owns: task → sandbox → agent → trace. Nothing else. If it stores, schedules, scores, weights, versions, or trains — it's out."
2. **Size budget**: our own code stays within its 2,034-line budget (raised from 1,500 at CP-12, ADR-0012; re-set to the landed size exactly at CP-65, ADR-0028, and again at CP-75, ADR-0033); the census is `wc -l gsj_rollout/*.py` — everything else (vendored Polar, tests, all of `estate/` incl. `estate.py` — one roof since CP-50) sits outside it. Standing at CP-75: **2,034/2,034, headroom 0 by design**, machine-checked as a suite equality (`test_size_law_census_is_machine_checked`) — a checkpoint that adds any net line must stop and justify AND move the equality test with its ADR, and a new `checks.py` line additionally needs an ADR-0021 allowance.
3. **The predecessor is frozen — historical since CP-45.** No checkpoint CP-00–CP-44 modified `gsj-envloader`, and it reached the archive byte-untouched; CP-45 made the single permitted write (the README archive header, one commit past v0.8.0, ADR-0026) and set the GitHub repo to archived, so the freeze is platform-enforced from here. Read it and compare against it freely — it must stay readable as the goldens' collecting stack.
4. **Vendor, don't depend.** Polar has no releases. Pin a SHA, record it, document the re-vendor recipe (`vendor/REVENDOR.md`), expect to carry patches.
5. **Nothing in `gsj_rollout/` assumes Docker semantics.** The runtime is a config value; Polar's interface is start/stop/exec/upload/download. This keeps Apptainer free when we want it (A-11).
6. **`checks.py` runs on both sides** — the receiver drops bad traces at the source, the trainer verifies what arrived. Same code, no trust required across the wire.
7. **Findings over features.** This is an evaluation. A checkpoint that discovers Polar cannot do something is as valuable as one that builds.

## Assumptions

`docs/CHARTER.md` §4 is the assumption register. Every new assumption gets a row there immediately, with its basis and its if-false consequence. Unverified is not false — a reported defect stays UNVERIFIED until a checkpoint verifies it.

## Workflow

**The development record is untracked since CP-48** (the operator's decision, taken on CP-47's classification): `docs/prompts/`, `docs/reports/`, `docs/decisions/`, the audit, the classification, and the non-load-bearing `golden/`/`polar/` evidence are `.gitignore`d — since CP-49a no prompt is tracked (`CP-48.md`, the last one, untracked at the operator's direction). The practice otherwise continues unchanged: work happens only inside numbered CP prompts, one at a time, saved verbatim to `docs/prompts/CP-XX.md` — on disk, ignored, never committed. Each CP ends with a hard STOP wall — never begin the next CP even if obvious. Mid-CP questions: choose a best-guess default, proceed, list it under `questions:`. Every CP writes `docs/reports/CP-XX.md` in the exact template below and prints it — printing is now the report's only publication; the file stays on disk, untracked. Each CP makes one commit `CP-XX: <summary>` covering tracked material only (a release CP makes two: the release commit, tagged once its CI is green, then the record commit carrying the run ids — the CP-34/CP-60 shape) and leaves the tree clean — since CP-48 `git status --porcelain` comes back empty because the record paths are *ignored*, not because the record was committed: an empty porcelain no longer certifies the record is anywhere but this disk. The record has no remote; the operator's working tree (and whatever backup the operator keeps) is the only copy — do not delete record files, ever. **A CP ends at the remote, not the working tree: push every repo the CP touched before the report claims done (charter §8 rule 8 — written at CP-33 and then ignored three CPs running, CP-36–38, found at CP-39), and state the push outcome in the report either way — silence is non-compliance.** **Every CP updates the gap register in `docs/CHARTER.md` §7** — the charter stays tracked, so the §7 append is the one part of each CP's record that still reaches the remote. ADRs are append-only in `docs/decisions/`, one file per decision (`ADR-0001-title.md`), Context → Decision → Consequence — untracked like the rest of the record since CP-48.

```
### CP-XX REPORT
status: done | partial | blocked
scope_drift: none | <what and why>
files: <git show --stat summary>
tests: <command> → <counts> | n/a
ci: <the push's run id> → <every job's colour>; any red job → the register row it matches (never "runner-side" without a row — §8 rule 9 (b))
adrs: <ids or none>        assumptions: <ids or none>
gap_register: <rows touched>; waiting-on scanned: <grep -rn 'waiting-on:' docs/ count> — <none fired | the ids that did, and what moved>
questions: <each with the applied default> | none
next: <advisory>
```

## Engineering rules

- **R1 — do not reinvent**: name the off-the-shelf candidate before writing >50 lines of infrastructure; going custom needs an ADR.
- **R2 — if confused, search first**: look for prior art; found → adopt and cite; not found → propose with a default under `questions:` and never stall.
- **R3 — simplicity**: the simplest thing that satisfies the charter and the CP's Definition of Done; no abstraction the charter doesn't mandate.
- **R4 — fakes are measured, never written** (charter §8 rule 10, CP-98): a test that fakes a CLI takes its exit code and streams from `estate/corpus/tests/cli_shapes.json` through `conftest.cli_shape`; the suite re-measures that file against the real CLI wherever a daemon answers. A shape the file lacks is measured first. Two shipped defects taught it (CP-84's Compose grammar, row 100's `docker rm -f`).

## Layout & commands

```
.
├── CLAUDE.md
├── README.md                    # the front door: what the traces are for (above the fold, CP-105), three install routes by what each gets you, the two-role split
├── POLAR_SHA                    # the vendor pin record: f0e8343a…, branch stable, 3 carried patches
├── pyproject.toml               # 0.1.17; wheel force-includes both pins sets, the G2 container capture, ingest_corpus.py + estate.py
├── docs/
│   ├── guide/                   # the user documentation: seven plain Markdown pages (bring-your-own.md since CP-92: a foreign model's values from its endpoint, a foreign corpus's pins from its first quarantine; since CP-94 what an acceptance covers, the borrowed endpoint, probe step 5; since CP-96 round four's walks and the skeleton decision; since CP-97 the skeleton `up` writes and the script that reads it; since CP-99 the Polar boundary and the `gsj-polar` image named where the walk hits them, both pip-timeout signatures, and the pull checks corrected — `Retrying in N seconds` is not a failure and `df -h` is blind here; since CP-101 the two `docker run` invocations that actually start Polar's two processes from the named image, one clause per flag, with the checkout route beside them and `-e TMPDIR` among them; since CP-104 the hand-off `up` without the id it measures itself, `umask 077` on the gateway's env file, the session directory empty by design, both Polar routes on the server guide, and the admission-gate ordering beside every skeleton refusal) + img/ (PNG renders of PowerPoint decks kept OUTSIDE the repo)
│   ├── CHARTER.md               # the normative document: assumptions §4, gap register §7, standing rules §8
│   ├── VERDICT.md               # the adoption verdict + the wishlist (the read-first document)
│   ├── checks-spec.md           # the validators' rule reasoning (G1–G7, ADM, logprob discipline)
│   ├── corpus-contract.md       # the corpus tree contract
│   ├── AUDIT-2026-08-24.md      # the post-CP-38 three-repo audit — UNTRACKED since CP-48
│   ├── decisions/               # ADRs (0001–0043), one file per decision, append-only — UNTRACKED since CP-48
│   ├── prompts/                 # every CP prompt verbatim: CP-XX.md — fully UNTRACKED since CP-49a (CP-48.md came out too)
│   ├── reports/                 # one report per checkpoint: CP-XX.md — UNTRACKED since CP-48
│   ├── golden/                  # golden-pair evidence — fully untracked since CP-49 (the mac fixtures moved to tests/fixtures/golden-mac/)
│   └── polar/                   # real Polar run artifacts — only the 7 suite/CI/walk-read bodies tracked since CP-48
├── gsj_rollout/                 # 2,034 lines — the whole server
│   ├── __init__.py              # consumer surface: RolloutClient/Trace, checks, load_config/RunConfig
│   ├── pi_harness.py            # SERVER — our pi via Polar import_path
│   ├── builder.py               # SERVER — ValidatingPrefixMergingBuilder, loaded by import-path string
│   ├── receiver.py              # SERVER — callback endpoint + validation + quarantine
│   ├── checks.py                # BOTH  — trace validators (528 lines, ADR-0021 equality tripwire)
│   ├── config.py                # SERVER — one YAML
│   ├── client.py                # TRAINER — submit + collect
│   └── cli.py                   # SERVER — the console script, below
├── tests/                       # root suite: 176 tests across 9 modules (CI collects corpus 600 — 599 pass plus the existing missing adjacent demo fixture skip on hosted runners — and mcp-service 256; historical job labels remain 541/164)
├── pins/                        # the approved sets (reference + thinking-on/) + container/ (the G2 singleton) + derive scripts — single source for the wheel copies
├── vendor/                      # Polar @ POLAR_SHA + patches/ (P1–P3) + apply_patches.sh + REVENDOR.md
└── estate/                      # everything that stands the H200 test estate up — one roof since CP-50; outside the size law
    ├── README.md                #   the estate recipe (deltas vs the predecessor's BRINGUP) + the post-CP-50 data-migration note
    ├── estate.sh                #   the thin front door: bringup | up | owner | down | mcp-up | mcp-down | serve | serve-updated | health | status
    ├── estate.py                #   the estate's one tool: scaffold | validate | up | ingest | update | status | down (CP-59's bring-up, renamed CP-72, update CP-73, up --decisions-dir CP-79, status on a partial run + the split pull refusals CP-92, status's three states via the run lock + the sandbox image checked first + the pull heartbeat CP-94, the readiness probe by `docker exec` into the run's own container that degrades instead of aborting + monotonic wait budgets printing what they waited + the building collection on the poll line + the verify headline counting skips + the heartbeat naming the layer phase + the storage driver named CP-96, the pins skeleton written beside rollout.yaml with the G6 tail and end-of-turn id measured from the endpoint's own render and refused as pins CP-97 (ADR-0042), the fallback probe's reaper reading *removed* off the CLI's stdout so its bound engages CP-98, the gateway probe's sentinel answering a nonce and dialled from BOTH legs — a foreign listener no longer passes, `host.docker.internal` is appended rather than inserted first, a port it cannot bind is UNMEASURED rather than measured against somebody else's listener, and a `docker exec` that could not start the interpreter is a failure rather than a silent refusal — the storage-driver warning re-worded to round five's controlled pair, the skeleton's prose conditional on the pins in force (ADR-0042 amended) and six other `measured`-on-an-inference labels corrected CP-99, the `== run <name> ==` footer's skeleton row made conditional on the pins in force like the pins line above it — `skeleton_footer_row`, CP-101 (row 102); round seven's findings at CP-104 (row 111): the closing block spells the published Polar image with the page and lists the bank's rows, `status` lists them too and names a run that stopped before its record, printed commands carry `--runs-dir`, `--corpus` and the wheel's interpreter, a cut pull transfer is its own kind whose cure is the same command, the heartbeat carries the layer tally's age, and a `/tokenize` request with no answer is retried once and reported as measured; outside the size law; force-included into the wheel as gsj_rollout.estate from 0.1.6 — gsj_rollout.bringup on wheels 0.1.3–0.1.5)
    ├── runs/                    #   estate.py per-run directories (.env, run.json, traces) — ignored
    ├── rollout.h200.yaml        #   the one YAML for the H200 estate
    ├── serving/                 #   vLLM bring-up scripts + the served jinja + model envs (was staging/serving/)
    ├── forgejo/                 #   git-host bring-up: compose + up/down/create_owner
    ├── mcp-service/             #   the retrieval service — own suite (256), venv, Dockerfile, GHCR image
    └── corpus/                  #   the ingestion pipeline (ingest_corpus.py, force-included into the wheel; its own `python -m` entry deprecated since CP-72) + its suite (600 — since CP-98 it also re-measures `tests/cli_shapes.json` against the real CLI, skipping where no daemon answers; CP-99 added the gateway module and two measured `docker exec` shapes; CP-101 added the footer-conditional module; CP-104 the round-seven module) + staging/ (163 frozen fixture files)
```

`spike/` (the CP-06 evidence) is off the tree since CP-68 — frozen at tag [`spike-cp06`](https://github.com/MHGanainy/gsj-harness-rollout-server/tree/spike-cp06/spike) (commit `a769771`, tree `2082a24f`), ADR-0029; restore with `git checkout spike-cp06 -- spike`.

Commands:

`pytest -q` requires the Docker CLI and Compose plugin for credential parsing checks; no Docker daemon or running estate is needed.

```
pip install -e ".[dev]"
pytest -q                                  # the root suite: 176 (corpus: .venv/bin/python -m pytest -q estate/corpus/tests → 600)
gsj-rollout serve --config <yaml>          # renders topology.rendered.yaml, prints the two Polar
                                           # commands (operator-run), then runs OUR receiver
gsj-rollout submit --config <yaml> \
  --case … --timestep … --prompt …         # or --from-bank <parquet> [--row N]
                                           # submit + poll + collect; exit 0 all / 1 partial / 2 usage / 3 unreachable
estate/estate.sh --help                    # the estate front door (server side): each verb execs an existing script or compose in place
```
