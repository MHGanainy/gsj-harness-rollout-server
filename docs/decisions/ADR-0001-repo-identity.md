# ADR-0001 — repo identity

## Context

Naming decisions taken before CP-00, recorded so they are on the record
rather than folklore. The predecessor used a PEP 420 namespace package
(`gsj.envloader`) because it anticipated siblings under `gsj.`; this repo
has no sibling packages to share with. The word "harness" is already taken
twice in our stack — Polar's `BaseHarness` and pi itself — so a module
named `harness.py` would be ambiguous three ways. The server and trainer
halves could ship as two distributions, but Polar's own `slime_bridge`
keeps the trainer bridge inside the one package, and extras achieve the
same split with less machinery.

## Decision

- Repo and distribution: **`gsj-harness-rollout-server`**.
- Import package: **`gsj_rollout`**, flat — no PEP 420 namespace
  machinery, no sibling packages to share with.
- Module: **`pi_harness.py`**, not `harness.py` — "harness" alone already
  means Polar's `BaseHarness` and pi itself.
- **One package rather than two** — Polar's own `slime_bridge` precedent,
  and the reason the trainer half installs light: core deps are only
  `pydantic`, `httpx`, `pyyaml`; everything heavy sits behind the
  `[server]` extra.

## Consequence

Trainers `pip install gsj-harness-rollout-server` and get `client` +
`checks` with three light dependencies; the server host installs
`.[server]` once CP-03 vendors Polar and the real runtime deps are known.
Repo/distribution and import name differ (`gsj-harness-rollout-server` vs
`gsj_rollout`) — accepted deliberately: the long name identifies the repo,
the short one is what code types. The CP-00 prompt span recording this ADR
arrived corrupted ("three  rather than two packages"); reconstructed as
"one package rather than two" from the surviving rationale, flagged in the
CP-00 report.
