# gsj-harness-rollout-server

A rollout server for our corpus: given a task `(case, timestep, prompt)` it
runs our agent in an isolated sandbox with temporally-scoped retrieval and
emits a training-ready trajectory. Trainer-agnostic, algorithm-agnostic,
parameterization-agnostic. Episode execution and trajectory reconstruction
are NVIDIA Polar's, vendored by SHA.

**Status: CP-00 — scaffold only.** No logic anywhere yet. The plan, the
scope laws, the assumption register, and the gap register this repo is
judged by all live in [`docs/CHARTER.md`](docs/CHARTER.md) — the normative
document.

Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not retired; the
fallback and the golden reference.
