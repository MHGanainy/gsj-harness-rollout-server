# CLAUDE.md — gsj-harness-rollout-server

## Project

**gsj-harness-rollout-server** is a **rollout server for our corpus**. Given a task `(case, timestep, prompt)` it runs our agent in an isolated sandbox with temporally-scoped retrieval and emits a training-ready trajectory. It is trainer-agnostic, algorithm-agnostic, and parameterization-agnostic. Episode execution and trajectory reconstruction are built on NVIDIA's Polar, vendored by SHA. Predecessor: `gsj-envloader` @ v0.8.0 — **alive, frozen, not retired**; it is the fallback and the golden reference. The normative document is `docs/CHARTER.md`; this file governs process only.

## Scope laws

1. **The scope law**: "The rollout server owns: task → sandbox → agent → trace. Nothing else. If it stores, schedules, scores, weights, versions, or trains — it's out."
2. **Size budget**: our own code stays under 1,500 lines, excluding vendored Polar, tests, and the moved components (`corpus/`, `mcp-service/`, `forgejo/`). A checkpoint that pushes past it must stop and justify.
3. **The predecessor is frozen.** No checkpoint here modifies `gsj-envloader`.
4. **Vendor, don't depend.** Polar has no releases. Pin a SHA, record it, document the re-vendor recipe, expect to carry patches.
5. **Nothing in `gsj_rollout/` assumes Docker semantics.** The runtime is a config value; Polar's interface is start/stop/exec/upload/download. This keeps Apptainer free when we want it (A-11).
6. **`checks.py` runs on both sides** — the receiver drops bad traces at the source, the trainer verifies what arrived. Same code, no trust required across the wire.
7. **Findings over features.** This is an evaluation. A checkpoint that discovers Polar cannot do something is as valuable as one that builds.

## Assumptions

`docs/CHARTER.md` §4 is the assumption register. Every new assumption gets a row there immediately, with its basis and its if-false consequence. Unverified is not false — a reported defect stays UNVERIFIED until a checkpoint verifies it.

## Workflow

Work happens only inside numbered CP prompts, one at a time, saved verbatim to `prompts/CP-XX.md` and committed with the CP. Each CP ends with a hard STOP wall — never begin the next CP even if obvious. Mid-CP questions: choose a best-guess default, proceed, list it under `questions:`. Every CP writes `docs/reports/CP-XX.md` in the exact template below, prints it, makes one commit `CP-XX: <summary>`, and leaves the tree clean. **Every CP updates the gap register in `docs/CHARTER.md` §7.** ADRs are append-only in `docs/decisions/`, one file per decision (`ADR-0001-title.md`), Context → Decision → Consequence.

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
├── README.md                    # short: what it is, status, pointer to CHARTER
├── pyproject.toml
├── .gitignore
├── docs/
│   ├── CHARTER.md               # the normative document
│   ├── decisions/               # ADRs, one file per decision, append-only
│   └── reports/                 # one report per checkpoint: CP-XX.md
├── prompts/                     # every CP prompt verbatim: CP-XX.md
├── gsj_rollout/
│   ├── __init__.py              # consumer surface (empty for now)
│   ├── pi_harness.py            # SERVER — our pi via Polar import_path
│   ├── receiver.py              # SERVER — callback endpoint + validation
│   ├── checks.py                # BOTH  — trace validators
│   ├── config.py                # SERVER — one YAML
│   ├── client.py                # TRAINER — submit + collect
│   └── cli.py                   # SERVER — gsj-rollout serve | submit
└── tests/
    └── test_scaffold.py         # imports the package, asserts version
```

Commands:

```
pip install -e ".[dev]"
pytest -q
gsj-rollout serve       # subcommand of the one console script — does nothing yet (CP-08)
gsj-rollout submit      # subcommand of the one console script — does nothing yet (CP-08)
```
