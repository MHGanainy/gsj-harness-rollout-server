# gsj-harness-rollout-server

The rollout server turns one task triple `(case, timestep, prompt)` into one validated, training-ready trace — this page is the documentation index: what the server does, how to start in either of its two roles, and where the deeper record lives.

## What it does

The server runs a pinned coding agent (pi 0.83.0) in an isolated sandbox in which everything the agent can see — the git checkout and the retrieval service — is truncated at `timestep`, captures every token and logprob the model produced, and emits one validated trace. That is the whole job: **task → sandbox → agent → trace**. It stores no traces, schedules no work, computes no rewards (every callback carries `reward: null`), and never touches weights or training — those belong to the trainer that calls it.

Episode execution and trajectory reconstruction come from NVIDIA's Polar ([`NVIDIA-NeMo/ProRL-Agent-Server`](https://github.com/NVIDIA-NeMo/ProRL-Agent-Server)), vendored by SHA with three carried patches; our code is the 2,000-line shell — harness, builder, receiver, config, CLI, checks — that points Polar at our corpus, our retrieval service, our agent, and our checks. The property the server exists for is the cutoff: `timestep` is a boundary the agent cannot cross, enforced twice (a shallow checkout of branch `timestep-T`; a signed token the retrieval service verifies before filtering to pages `≤ T`) and audited after the fact from the trace alone — see [how-it-works.md](how-it-works.md).

![The overall shape: a task enters from the training loop, Polar runs the agent in a sandbox fed by the operator's estate, and the receiver validates the resulting trace](img/overview-shape.png)

<sub>One task triple in, one validated trace out; everything around the sandbox is either Polar's, the operator's estate, or the trainer's.</sub>

## Quick start

The two roles talk over HTTP only — one task JSON in, `SessionResult`s back, re-checked on arrival by the same `checks.py` the receiver already ran; never weights, rewards, or storage. Decide which one you are.

![Two lanes side by side: the server role holds gsj-rollout serve, two Polar processes, the estate, and checks.py; the trainer role holds RolloutClient, the training loop, checks.py, and the pip-installed wheel; only a task JSON and SessionResults cross the gap](img/two-roles.png)

<sub>Left, the server: an estate you operate, the two Polar processes, the receiver. Right, the trainer: the wheel, `RolloutClient`, and the same `checks.py` — because nothing upstream is trusted.</sub>

**Trainer** ([trainer-guide.md](trainer-guide.md)) — Python ≥ 3.12, anywhere. The wheel (0.1.3) is the client plus the validators (and the corpus pipeline as `python -m gsj_rollout.ingest_corpus` since 0.1.2, the estate bring-up as `python -m gsj_rollout.bringup` since 0.1.3): no `vendor/`, no Polar, no way to start a sandbox — it talks to a server somebody operates.

```bash
pip install gsj-harness-rollout-server
```

**Server** ([server-guide.md](server-guide.md)) — a machine you operate running the four estate services (vLLM with the pinned chat template, a Forgejo git host, the MCP retrieval service, the ingested corpus), plus this checkout with Polar's venv built under `vendor/polar/`.

```bash
git clone https://github.com/MHGanainy/gsj-harness-rollout-server && cd gsj-harness-rollout-server
pip install -e ".[dev]" && gsj-rollout serve --config <yaml>
```

> [!WARNING]
> The wheel ships the pins of the estate it was built for; on any other estate every hash gate fails `*_not_approved`, by design. Point `GSJ_PINS_PATH` at your own pins file before the first import of `gsj_rollout.checks` — see [validation-and-pins.md](validation-and-pins.md).

## The guide

| File | What it answers |
| --- | --- |
| [README.md](README.md) | This page: the pitch, both quickstarts, the map. |
| [how-it-works.md](how-it-works.md) | The architecture, the episode dataflow, the timestep cutoff, and what a trace contains. |
| [validation-and-pins.md](validation-and-pins.md) | The checks, the gates, pins and approved sets, and the complete finding vocabulary. |
| [server-guide.md](server-guide.md) | `serve`, the one YAML, the CLI, the receiver, the estate, the corpus, the retrieval service. |
| [trainer-guide.md](trainer-guide.md) | Install, the first collect, the Python API, the wire formats, running a training loop. |
| [troubleshooting.md](troubleshooting.md) | Symptom → cause → fix, with the exact messages. |

## The record behind this

The library is the product of an evaluation, not a greenfield build: could Polar own episode execution and capture, leaving only a thin shell? The verdict is **ADOPT** — provisional 2026-08-09, converted 2026-08-11 when the golden pair passed on the production H200 estate and a trainer took one real optimizer step on traces collected through this path. The predecessor, `gsj-envloader` at `v0.8.0`, is archived and read-only: it stays readable as the golden reference the fidelity claims are measured against (`loss_mask` exact at zero tolerance, `prompt_ids` byte-identical), and it is not a fallback. Our code is Apache-2.0; `vendor/polar/` carries NVIDIA's own Apache-2.0 licence and ships in no released artifact — publication is wheel-only (`gsj_rollout/`, both pins sets, `ingest_corpus.py`), and the release workflow fails any wheel containing a path under `vendor/`, `estate/`, `spike/`, `tests/`, `docs/`, or `.github/`.

Four tracked documents are normative; this guide is the consumer view of them.

| Document | What it holds |
| --- | --- |
| [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) | The adoption verdict: the evidence, the reversing conditions, the open wants. Standalone — the short path to a trust decision. |
| [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) | The scope laws, the assumption register (§4), the capability and gap register (§7), the standing rules (§8). |
| [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) | Why each validator rule exists: the pins format, hashing, gates, admission, findings, the logprob discipline. |
| [`docs/corpus-contract.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md) | The corpus source-tree contract that `ingest_corpus.py validate` enforces. |

> [!NOTE]
> The per-checkpoint development record — prompts, reports, decision records, the audit, the raw run evidence — is maintained privately by the operator and is not in the repository. The tracked documents cite it (`docs/reports/CP-NN.md`, `ADR-NNNN`); from a clone those citations are footnotes you cannot follow — treat a claim resting only on one as asserted, not checkable. What stays checkable from a clone: `pytest -q`, `bash vendor/apply_patches.sh --verify`, `cat POLAR_SHA`, and the pins walk (`pins/derive_pins.py`) over the tracked evidence bodies.

## See also

- [Repository README](../../README.md) — the front door: the shape, the cutoff, the two roles, what has been measured, the licence.
- [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples) — trainer side: a training loop against an existing server, including the slime and verl bridges.
- [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo) — bring-your-own estate: from a fresh machine to the first accepted episode.
