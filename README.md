# gsj-harness-rollout-server

A rollout server for our corpus: given a task `(case, timestep, prompt)` it
runs our agent in an isolated sandbox with temporally-scoped retrieval and
emits a training-ready trajectory. Trainer-agnostic, algorithm-agnostic,
parameterization-agnostic. Episode execution and trajectory reconstruction
are NVIDIA Polar's, vendored by SHA.

**Status: CP-01 — the moves.** The Polar-independent components are here
and stand alone: `corpus/` (source of truth + ingestion pipeline; taskbank
phase deferred to CP-07, ADR-0003), `mcp-service/` (the hosted retrieval
service), `forgejo/` (git-host bring-up), `pins/` (G2 derivation tooling +
captured gate evidence), and `docs/corpus-contract.md`. `gsj_rollout/`
itself is still the CP-00 scaffold — no logic yet. The plan, the
scope laws, the assumption register, and the gap register this repo is
judged by all live in [`docs/CHARTER.md`](docs/CHARTER.md) — the normative
document; the ownership boundary of the moves is ADR-0002.

Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not retired; the
fallback and the golden reference.
