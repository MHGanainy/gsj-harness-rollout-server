# CLAUDE.md — gsj-harness-rollout-server

## Project

**gsj-harness-rollout-server** is a **rollout server for our corpus**. Given a task `(case, timestep, prompt)` it runs our agent in an isolated sandbox with temporally-scoped retrieval and emits a training-ready trajectory. It is trainer-agnostic, algorithm-agnostic, and parameterization-agnostic. Episode execution and trajectory reconstruction are built on NVIDIA's Polar, vendored by SHA (`POLAR_SHA`; three carried patches). Published on PyPI as `gsj-harness-rollout-server` **0.1.2** (wheel-only: `gsj_rollout/`, both pins sets, `ingest_corpus.py`). Predecessor: `gsj-envloader` @ v0.8.0 — **archived at CP-45** (2026-08-25, ADR-0026): still the golden reference (the collecting stack for both goldens, readable at v0.8.0), no longer the fallback — that term expired when the verdict converted (CP-17, 2026-08-11). Consumer repos, both public: `gsj-harness-rollout-server-examples` (trainer-side; external register F-01–F-53) and `gsj-rollout-demo` (bring-your-own estate; register F-54–F-68). The normative document is `docs/CHARTER.md`; this file governs process only.

## Scope laws

1. **The scope law**: "The rollout server owns: task → sandbox → agent → trace. Nothing else. If it stores, schedules, scores, weights, versions, or trains — it's out."
2. **Size budget**: our own code stays under 2,000 lines (raised from 1,500 at CP-12, ADR-0012), excluding vendored Polar, tests, and the moved components (`corpus/`, `mcp-service/`, `forgejo/`). Standing at CP-39: **1,999/2,000, headroom 1** — a checkpoint that pushes past it must stop and justify, and a new `checks.py` line additionally needs an ADR-0021 allowance.
3. **The predecessor is frozen — historical since CP-45.** No checkpoint CP-00–CP-44 modified `gsj-envloader`, and it reached the archive byte-untouched; CP-45 made the single permitted write (the README archive header, one commit past v0.8.0, ADR-0026) and set the GitHub repo to archived, so the freeze is platform-enforced from here. Read it and compare against it freely — it must stay readable as the goldens' collecting stack.
4. **Vendor, don't depend.** Polar has no releases. Pin a SHA, record it, document the re-vendor recipe (`vendor/REVENDOR.md`), expect to carry patches.
5. **Nothing in `gsj_rollout/` assumes Docker semantics.** The runtime is a config value; Polar's interface is start/stop/exec/upload/download. This keeps Apptainer free when we want it (A-11).
6. **`checks.py` runs on both sides** — the receiver drops bad traces at the source, the trainer verifies what arrived. Same code, no trust required across the wire.
7. **Findings over features.** This is an evaluation. A checkpoint that discovers Polar cannot do something is as valuable as one that builds.

## Assumptions

`docs/CHARTER.md` §4 is the assumption register. Every new assumption gets a row there immediately, with its basis and its if-false consequence. Unverified is not false — a reported defect stays UNVERIFIED until a checkpoint verifies it.

## Workflow

Work happens only inside numbered CP prompts, one at a time, saved verbatim to `docs/prompts/CP-XX.md` and committed with the CP. Each CP ends with a hard STOP wall — never begin the next CP even if obvious. Mid-CP questions: choose a best-guess default, proceed, list it under `questions:`. Every CP writes `docs/reports/CP-XX.md` in the exact template below, prints it, makes one commit `CP-XX: <summary>`, and leaves the tree clean. **A CP ends at the remote, not the working tree: push every repo the CP touched before the report claims done (charter §8 rule 8 — written at CP-33 and then ignored three CPs running, CP-36–38, found at CP-39), and state the push outcome in the report either way — silence is non-compliance.** **Every CP updates the gap register in `docs/CHARTER.md` §7.** ADRs are append-only in `docs/decisions/`, one file per decision (`ADR-0001-title.md`), Context → Decision → Consequence.

```
### CP-XX REPORT
status: done | partial | blocked
scope_drift: none | <what and why>
files: <git show --stat summary>
tests: <command> → <counts> | n/a
adrs: <ids or none>        assumptions: <ids or none>
gap_register: <rows touched>
questions: <each with the applied default> | none
next: <advisory>
```

## Engineering rules

- **R1 — do not reinvent**: name the off-the-shelf candidate before writing >50 lines of infrastructure; going custom needs an ADR.
- **R2 — if confused, search first**: look for prior art; found → adopt and cite; not found → propose with a default under `questions:` and never stall.
- **R3 — simplicity**: the simplest thing that satisfies the charter and the CP's Definition of Done; no abstraction the charter doesn't mandate.

## Layout & commands

```
.
├── CLAUDE.md
├── README.md                    # the two-role split: server side needs an estate; trainer side is the pip library
├── POLAR_SHA                    # the vendor pin record: f0e8343a…, branch stable, 3 carried patches
├── pyproject.toml               # 0.1.2; wheel force-includes both pins sets + ingest_corpus.py
├── docs/
│   ├── CHARTER.md               # the normative document: assumptions §4, gap register §7, standing rules §8
│   ├── VERDICT.md               # the adoption verdict + the wishlist (the read-first document)
│   ├── checks-spec.md           # the validators' rule reasoning (G1–G7, ADM, logprob discipline)
│   ├── corpus-contract.md       # the corpus tree contract
│   ├── AUDIT-2026-08-24.md      # the post-CP-38 three-repo audit — CP-39/40/41's specification
│   ├── decisions/               # ADRs (0001–0025), one file per decision, append-only
│   ├── prompts/                 # every CP prompt verbatim: CP-XX.md
│   ├── reports/                 # one report per checkpoint: CP-XX.md
│   ├── golden/                  # golden-pair evidence (mac/ + h200/ + COMPARISON.md)
│   └── polar/                   # real Polar run artifacts (fidelity, loop, thinking evidence)
├── gsj_rollout/                 # 1,999 lines — the whole server
│   ├── __init__.py              # consumer surface: RolloutClient/Trace, checks, load_config/RunConfig
│   ├── pi_harness.py            # SERVER — our pi via Polar import_path
│   ├── builder.py               # SERVER — ValidatingPrefixMergingBuilder, loaded by import-path string
│   ├── receiver.py              # SERVER — callback endpoint + validation + quarantine
│   ├── checks.py                # BOTH  — trace validators (528 lines, ADR-0021 equality tripwire)
│   ├── config.py                # SERVER — one YAML
│   ├── client.py                # TRAINER — submit + collect
│   └── cli.py                   # SERVER — the console script, below
├── tests/                       # root suite: 161 tests across 9 modules (CI adds corpus 58 + mcp-service 89)
├── pins/                        # the approved sets (reference + thinking-on/) + derive scripts — single source for the wheel copies
├── staging/                     # this repo's H200 estate recipe (deltas vs the predecessor's BRINGUP)
├── vendor/                      # Polar @ POLAR_SHA + patches/ (P1–P3) + apply_patches.sh + REVENDOR.md
├── corpus/  mcp-service/  forgejo/  # moved components, outside the size law (corpus pipeline, retrieval service, git host)
└── spike/                       # frozen CP-06 spike evidence
```

Commands:

```
pip install -e ".[dev]"
pytest -q                                  # the root suite: 161
gsj-rollout serve --config <yaml>          # renders topology.rendered.yaml, prints the two Polar
                                           # commands (operator-run), then runs OUR receiver
gsj-rollout submit --config <yaml> \
  --case … --timestep … --prompt …         # or --from-bank <parquet> [--row N]
                                           # submit + poll + collect; exit 0 all / 1 partial / 2 usage / 3 unreachable
```
