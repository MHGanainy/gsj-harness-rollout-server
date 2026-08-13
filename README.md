# gsj-harness-rollout-server

[![CI](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml/badge.svg)](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml)

A **rollout server for our corpus**: given a task `(case, timestep, prompt)`
it runs our agent in an isolated sandbox with temporally-scoped retrieval and
emits a training-ready trajectory. Trainer-agnostic, algorithm-agnostic,
parameterization-agnostic. Episode execution and trajectory reconstruction
are NVIDIA Polar's, vendored by SHA.

It has **two roles**, and the split is the thing to understand first. The
**server** side (`pi_harness`, `receiver`, `config`, `cli`) needs an estate —
a served engine, a Forgejo git host, the MCP retrieval service — and is not
useful without one. The **trainer** side (`client`, `checks`) is a small pure
library a training loop imports to submit tasks and to verify the traces that
come back. **The published package is for the trainer side**; the server side
is here because it is the same repo, not because `pip install` makes it run.

This repository is an **evaluation**, run as numbered checkpoints (`CP-NN`,
each with a prompt in `docs/prompts/` and a report in `docs/reports/`). It
asks whether Polar can own the episode-execution layer our predecessor
`gsj-envloader` owns today. The answer, and the conditions that would reverse
it, are in [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) — **the document to read
first.**

## Install

```
pip install gsj-harness-rollout-server
```

Gives you `gsj_rollout.client` (submit + collect) and `gsj_rollout.checks`
(the trace validators). Requires Python ≥ 3.12. Until the first PyPI
upload lands (wishlist 17 — the release path exists, nothing is uploaded),
build the same wheel from a checkout: `python -m build --wheel`, then
install `dist/gsj_harness_rollout_server-*.whl`.

**To actually run a training loop**, start from the examples repo
(`gsj-harness-rollout-server-examples`, beside this one — not yet
published) and its `example_project/` (CP-25): a commented `config.yaml`
a stranger can fill in (six required
values), the committed taskbank, a readable `train.py`, one install
command, and `RUNBOOK.md` — the start-to-finish document, including what
an estate is and what collection costs. There are deliberately no
`[verl]`/`[slime]` extras on this package (ADR-0023): verl installs
`--no-deps` from git at a pinned SHA, slime is a container image — each
bridge's install is one documented command over there.

### The approved sets that ship with it are ours, not defaults

`checks` validates traces against pinned hashes — approved tool rosters,
system prompts, skill cards, settings. Those pins are **this estate's**, and
the wheel ships them so the trainer leg works on install without a checkout
(ADR-0017). They are a working reference, **not meaningful defaults**: on any
other estate every hash gate will fail `*_not_approved`, loudly and by
design, because approval is set membership and your hashes are not in our
set. The library says so once, at import, when it falls back to them.

If you have your own estate, point `GSJ_PINS_PATH` at your own pins file
before the first import of `gsj_rollout.checks` (they load once per process):

```
export GSJ_PINS_PATH=/path/to/your/pins.gsj.json
```

A wrong or absent path raises `PinsConfigurationError` naming it — it never
falls through to ours. Resolution order is `GSJ_PINS_PATH` → a repo checkout →
the packaged copy; the format is specified in
[`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

## What the badge covers

The badge covers the fixture-driven half and nothing else: the root suite
(136), the corpus suite (58), the mcp-service suite (89), and the wheel
build with the packaged-pins install proof. It does not cover — and a
hosted runner cannot — the golden pairs, fidelity, the loop, or any episode
at all: an episode needs an estate (a served engine, Forgejo, the MCP
service), and the numbers that govern need the H200 and cluster time.
**Green means the fixtures still pass. It is not evidence that the harness
runs.**

## Status

**ADOPT** — the CP-12 provisional verdict converted at CP-17, both
converting conditions met (the standalone verdict, with its reversing
conditions, is
[`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md)). The evaluation ran thirteen
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
components (ADR-0002). None of those four ship in the package.

Run the tests:

```
pip install -e ".[dev]"
pytest -q
```

## Licence

Apache-2.0 — [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE). **`vendor/polar/` is not covered by it**:
the vendored Polar is NVIDIA's, carries its own Apache-2.0 `LICENSE` file at
`vendor/polar/LICENSE`, and stays there. The two never mix in a released
artifact, because `vendor/` is in neither the wheel nor the sdist — the
published package contains `gsj_rollout/` and one pins file, nothing else
(asserted at build time, CP-19).

The plan, the scope laws, the assumption register, and the gap register
this repo is judged by all live in [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) —
the normative document. Rule reasoning lives in `docs/checks-spec.md`;
per-checkpoint reports in `docs/reports/`; decisions in `docs/decisions/`.

Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not retired; the
fallback and the golden reference.
