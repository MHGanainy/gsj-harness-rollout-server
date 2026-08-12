# gsj-harness-rollout-server

[![CI](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml/badge.svg)](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml)

The badge covers the fixture-driven half and nothing else: the root suite
(129), the corpus suite (44), the mcp-service suite (89), and the wheel
build with CP-16's packaged-pins install proof. It does not cover — and a
hosted runner cannot — the golden pairs, fidelity, the loop, or any episode
at all: an episode needs an estate (a served engine, Forgejo, the MCP
service), and the numbers that govern need the H200 and cluster time.
**Green means the fixtures still pass. It is not evidence that the harness
runs.**

A rollout server for our corpus: given a task `(case, timestep, prompt)` it
runs our agent in an isolated sandbox with temporally-scoped retrieval and
emits a training-ready trajectory. Trainer-agnostic, algorithm-agnostic,
parameterization-agnostic. Episode execution and trajectory reconstruction
are NVIDIA Polar's, vendored by SHA.

**Status: ADOPT** — the CP-12 provisional verdict converted at CP-17, both
converting conditions met (the standalone verdict, with its reversing
conditions, is
[`docs/VERDICT.md`](docs/VERDICT.md)). The evaluation ran thirteen
checkpoints end to end: Polar vendored by SHA with three carried patches
(`vendor/`), real corpus episodes collected through our pi harness under
Polar on the Mac estate, and the collected trace verified against the
predecessor's golden reference (CP-09: masks exact, sampling-independent
tokens byte-identical, logprob capture agreeing at mean |Δ| = 0.000114).
Both converting conditions have since closed on the H200: the golden pair
and fidelity on production numerics (CP-04′/CP-09′) and one training loop
end to end (CP-17).

`gsj_rollout/` is the working server, not a scaffold: `pi_harness.py`
(our pi under Polar, per-episode cutoff tokens, the settings echo),
`builder.py` (the validating reconstruction subclass), `checks.py` (both
law-6 legs: admission, the logprob discipline, gates G1/G2/G3/G5/G7
against `pins/pins.gsj.json`), `receiver.py` (callback endpoint +
quarantine), `config.py` (the one YAML), `client.py` (the trainer's leg),
`cli.py` (`gsj-rollout serve | submit`). Beside it: `corpus/`,
`mcp-service/`, `forgejo/`, `pins/` — the moved Polar-independent
components (ADR-0002).

Run the tests:

```
pip install -e ".[dev]"
pytest -q
```

The plan, the scope laws, the assumption register, and the gap register
this repo is judged by all live in [`docs/CHARTER.md`](docs/CHARTER.md) —
the normative document. Rule reasoning lives in `docs/checks-spec.md`;
per-checkpoint reports in `docs/reports/`; decisions in `docs/decisions/`.

Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not retired; the
fallback and the golden reference.
