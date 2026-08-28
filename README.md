# gsj-harness-rollout-server

[![CI](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml/badge.svg)](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml)

A rollout server for the gsj corpus. Given a task `(case, timestep, prompt)`, it runs a pinned coding agent (pi 0.83.0) in an isolated sandbox in which everything the agent can see — the git checkout and the retrieval service — is truncated at `timestep`, captures every token and logprob the model produced, and emits one validated, training-ready trajectory. That is the whole job: **task → sandbox → agent → trace**. It does not store trajectories, schedule work, compute rewards, manage weights, version policies, or train — those belong to the trainer that calls it. Episode execution and trajectory reconstruction come from NVIDIA's Polar, vendored by commit with three carried patches; our own code is the 1,999-line shell that points Polar at our corpus, our retrieval service, our agent, and our checks. The repository is also the record of an evaluation — could Polar own the episode layer our predecessor owned? — whose verdict is **ADOPT**, provisional on 2026-08-09 and converted on 2026-08-11 with both converting conditions met on production hardware; [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) is the standalone statement, with the conditions that would reverse it.

![One task enters from the training loop, Polar runs the agent in a sandbox fed by the operator's estate, the trace is reconstructed, checked, and either accepted or quarantined](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/overview-shape.png)

<sub>One task triple in, one validated trace out. Everything around the sandbox is either Polar's, the operator's estate, or the trainer's; ours is the agent harness, the builder, the receiver, and the checks.</sub>

## Install

**Trainer** — any Python ≥ 3.12, anywhere. The wheel carries `gsj_rollout/`, both pins sets, and `ingest_corpus.py`; its dependencies are `pydantic`, `httpx`, `pyyaml`. It runs no episodes.

```bash
pip install gsj-harness-rollout-server
```

**Server** — a checkout, an editable install, and Polar's own venv (which must also host `gsj_rollout`, because Polar loads our harness and builder by import path).

```bash
git clone https://github.com/MHGanainy/gsj-harness-rollout-server && cd gsj-harness-rollout-server
python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd vendor/polar && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . && uv pip install -p .venv/bin/python -e ../.. && cd ../..
gsj-rollout serve --config rollout.yaml    # renders topology.rendered.yaml, prints the two Polar commands, runs the receiver
```

The server side additionally needs an estate — an inference engine, a Forgejo git host, the retrieval service, an ingested corpus — which no `pip install` provides. Full detail: [Installation](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/installation.md).

## Quick start

The trainer side, end to end, against the real signatures. One YAML describes the whole deployment; the trainer renders task requests from it and the server renders its topology from it.

```python
from gsj_rollout import RolloutClient, load_config
from gsj_rollout.config import render_task_request

cfg = load_config("rollout.yaml")
request = render_task_request(cfg, task_id="demo", instruction="Fix the failing test.",
                              case_id="case_0001", timestep=12)
client = RolloutClient(cfg.polar.rollout.base_url)   # Polar's rollout API, not the receiver
traces = client.collect([request])                   # list[Trace]; only checks-clean sessions come back
```

The same thing from the command line, with exit codes `0` all collected, `1` partial, `2` usage, `3` server unreachable:

```bash
gsj-rollout submit --config rollout.yaml --case case_0001 --timestep 12 --prompt "Fix the failing test."
```

## The two roles

Someone confuses these on first contact every time. The published package is for the trainer role; the server role runs from a checkout and needs an estate.

![Two lanes: the server role with gsj-rollout serve, the two Polar processes, the estate, and checks.py; the trainer role with RolloutClient, the training loop, the same checks.py, and the pip-installed wheel. Between them, HTTP only; weights, rewards, and storage never cross](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/two-roles.png)

<sub>Left, the server: an estate you operate, the two Polar processes, and this checkout's receiver. Right, the trainer: a wheel, a client, and the same `checks.py`. Between them, HTTP only — one task JSON in, `SessionResult`s back.</sub>

| | Server role | Trainer role |
| --- | --- | --- |
| What you need | A machine you operate, running the four estate services — an inference engine (vLLM, with the pinned chat template), a Forgejo git host (one repository per case, one branch per timestep), the MCP retrieval service, the ingested corpus — plus this repository checked out with Polar's venv built under `vendor/polar/` | Python ≥ 3.12, anywhere: `pip install gsj-harness-rollout-server` (0.1.2, wheel-only). No `vendor/`, no Polar |
| What you run | `gsj-rollout serve --config <yaml>` renders `topology.rendered.yaml`, prints the two Polar commands, then runs the receiver. You start the two Polar processes yourself: `serve_rollout` (the rollout API and scheduler — the trainer's `base_url`) and `serve_gateway` (the gateway and capture proxy, one sandbox per episode, loading our `pi_harness.py` and `builder.py` by import path). Every callback lands in `traces/` if clean, in `quarantine/` with its findings if not | `RolloutClient`: `submit`, `wait`, `collect` — `collect` submits, polls `GET /rollout/task/{id}`, re-runs `checks` on every result, and returns the `Trace`s of clean sessions. `checks.validate_session_result(result)` returns findings — the same validators the receiver ran, because nothing upstream is trusted |
| Start here | [Server quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/server-quickstart.md), then [The estate](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/estate.md) | [Trainer quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/trainer-quickstart.md), then [Running a training loop](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/training-loop.md) |

The same `checks.py` runs on both sides of the wire: the receiver drops bad traces at the source, the trainer re-runs the identical validators on everything it collects, so no trust is required across the wire. Ours is the shell around Polar — harness, builder, receiver, config, CLI, checks — **1,999 lines** against the ~14,200-line Polar layer they drive ([`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) §1).

**One trap worth naming at the door.** `checks` validates traces against pinned approved sets (tool rosters, system prompts, skill cards, settings), and the wheel ships **this estate's** pins so the trainer leg works on install. On any other estate every hash gate fails `*_not_approved` — loudly, by design. Point `GSJ_PINS_PATH` at your own pins file before the first import of `gsj_rollout.checks`. Resolution: `GSJ_PINS_PATH` → repo checkout → packaged copy (with a `UserWarning` when the packaged copy is what resolved); an unusable path raises `PinsConfigurationError` rather than falling through. The wheel also carries the thinking-on reference set at `gsj_rollout/pins/thinking-on/pins.gsj.json` — gate G6 compares against per-mode pins data. Format and reasoning: [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

To run a training loop against an existing server, start from [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples) and its `RUNBOOK.md`. To bring up your own estate from nothing, start from [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo).

## The timestep cutoff

The property this server exists for: `timestep` becomes a boundary the agent cannot cross, enforced twice and audited once.

![The task carries T into the sandbox; a filesystem wall stands between the agent's checkout and the git host, a retrieval wall between its search tool and the retrieval service, and the estate holds the full document behind both](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/cutoff-walls.png)

<sub>Two walls the agent cannot see past — one on the filesystem, one in front of retrieval — and, after the fact, an audit of the trace against the same T.</sub>

- **The filesystem wall.** The sandbox clone is branch `timestep-T`, `--depth 1`, remote removed, reflogs scrubbed — git history cannot reach a page past T even offline.
- **The retrieval wall.** The harness mints an HS256 token host-side with claims `{case_id, timestep, episode_id, exp}`; the signing secret never enters the sandbox. The token rides the MCP URL; the retrieval service verifies the signature, then filters to `page ≤ T` *before* ranking, with T taken from the verified claims only. Tampered claims (timestep 12→18, original signature) get HTTP 401.
- **The audit.** `checks.py` gate G5, from the trace alone: every retrieved page ≤ T; the checkout shallow, zero remotes, branch `== timestep-T`; checkout pages contiguous `1..T`.
- **Why reading the token does not help.** The agent may read its own token — it is in its own working directory — but cannot widen its timestep: the cutoff is decided server-side from verified claims, and any mutation invalidates the signature. That design was attacked, not assumed; see the forged-claim row below.

Full treatment: [The timestep cutoff](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/timestep-cutoff.md).

## Documentation

The user guide is plain Markdown under [`docs/guide/`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/README.md), readable on GitHub.

| Section | Pages |
| --- | --- |
| Getting started | [Installation](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/installation.md) · [Trainer quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/trainer-quickstart.md) · [Server quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/server-quickstart.md) |
| Concepts | [Architecture](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/architecture.md) · [The timestep cutoff](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/timestep-cutoff.md) · [Traces](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/traces.md) · [Validation](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/validation.md) · [Pins and approved sets](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/concepts/pins.md) |
| Guides | [Configuration](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/configuration.md) · [Command line](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/cli.md) · [The receiver](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/receiver.md) · [The corpus](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/corpus.md) · [The retrieval service](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/retrieval-service.md) · [The estate](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/estate.md) · [Running a training loop](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/training-loop.md) · [Troubleshooting](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/troubleshooting.md) |
| Reference | [Python API](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/reference/api.md) · [Finding vocabulary](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/reference/findings.md) · [Wire formats](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/reference/wire-formats.md) |
| About | [The design record](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/about/design-record.md) |
| Normative | [Verdict](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) · [Charter](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) · [Checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) · [Corpus contract](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md) |

## What has been proven

Measured as of **2026-08-24** (the audit re-executed every suite and census that day; per-checkpoint figures carry their report's date).

| claim | measured | evidence |
| --- | --- | --- |
| traces match the predecessor's golden reference | `loss_mask` exact at zero tolerance, `prompt_ids` byte-identical (2965/2965), on the Mac pair and again on the H200 pair | CP-09, CP-09′; `docs/golden/COMPARISON.md` |
| the logprobs are real captures | H200 replay-vs-replay bit-deterministic (0.000000); capture-vs-replay floor mean ≈ 0.005–0.007 on both traces symmetrically (classified platform, per the contract); Mac identical-context agreement mean \|Δ\| = 0.000114 | CP-09′, CP-09 |
| the cutoff holds under a forged claim | tampered token (timestep 12→18, original signature) rejected HTTP 401 from inside the sandbox; valid token 200; live episode retrieved pages [1, 5, 7, 9, 11], all ≤ 12 | CP-07 |
| two trainers, two loops, zero server changes | slime: 27 qualifying traces → one optimizer step → weight sync proven (logprobs moved at 5623/5782 positions) → 8/8 re-collect. verl: 110 qualifying → one step → sync (310/310 tensors, exactly one AdamW step) → 8/8. `gsj_rollout/` untouched both times | CP-17, CP-21 |
| two model families, no code change | Qwen3-0.6B (both golden pairs); Llama-3.1-8B: 8 completions merged into one full chain, quarantine empty, gates green | CP-04′/CP-09′, CP-38 |
| a stranger can run it from nothing | fresh machine, demo README the only input: clone → pip → estate up → first episode accepted, ≈ 5 minutes wall plus the model endpoint; two manual image pulls needed (amd64-only images on an ARM host — registered) | CP-36 |
| the shell stays thin | ours 1,999/2,000 lines vs Polar's ~14,200 driven; the predecessor spent ~1,800 lines on episode execution alone | audit 2026-08-24; VERDICT §1 |
| the fixture suites | root 161 + corpus 58 + mcp-service 89, all green by execution | audit 2026-08-24 |

What the badge does **not** cover: the golden pairs, fidelity, the loops, or any episode at all — an episode needs an estate, and the numbers that govern needed GPU time. Green means the fixtures still pass; it is not evidence that the harness runs.

## What it does not do

- **It never trained anything, and says so.** Each loop above is exactly one optimizer step bracketed by two collections; the post-sync 8/8 reward reads as the onset of mode collapse, not competence. Concurrent collection-and-training and weight sync at cadence have zero data points.
- **The trainer's problems stay the trainer's**: storage, retention, mixing, staleness, collation, reward — every callback carries `reward: null` — and weight sync. Dropped deliberately, at the start ([charter](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) §7 rows 16–21).
- **Sampling and codec provenance are the estate's, not the trace's.** pi sends no sampling parameters, so the engine's configuration *is* the sampling policy — an unpinned engine silently samples at neutral defaults (measured). Codec identity is verified at bring-up by the pins walk, not per-trace.
- **The two open gaps**, of a 32-row capability register (21 parity, 7 dropped by decision, 1 better, 1 TBD): row 12 — G4 codec evidence never rides the callback, a receiver-side gap by decision; row 22 — per-episode binding of traces to engine identity (serve argv, generation config, codec), owned by the first production bring-up. Same owner, same moment: the evaluation estates serve anonymous git read; the credentialed-clone/egress decision is also the first production bring-up's.
- **Model-agnostic in mechanism, Qwen-fitted in defaults.** One foreign family is one data point; a different reasoning geometry is the wall. Thinking-on requires the symmetric served template.

## Repository layout

![The top-level tree as a folder map: gsj_rollout is ours, vendor/polar is Polar's, estate is the operator's, docs holds the guide and the normative documents, with pins, tests, and spike beside them](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/repo-map.png)

<sub>Seven directories, four owners. `gsj_rollout/` is the product and the whole of what the wheel ships (plus the pins and `ingest_corpus.py` copied in at build time); `vendor/polar/` is NVIDIA's tree at the pinned commit; `estate/` is the test estate's recipes and moved components; the rest is evidence, approved sets, and tests.</sub>

| Path | What it is |
| --- | --- |
| `gsj_rollout/` | The server, eight modules: `pi_harness`, `builder`, `receiver`, `checks`, `config`, `client`, `cli`, and the package surface (`RolloutClient`, `Trace`, `checks`, `load_config`, `RunConfig`) |
| `vendor/polar/` | Polar at the commit in `POLAR_SHA`, patched (`vendor/patches/` P1–P3, `vendor/apply_patches.sh --verify`, re-vendor recipe in `vendor/REVENDOR.md`); ships in no artifact |
| `estate/` | This repository's test estate: `estate.sh` front door, `corpus/` (the pipeline and its suite), `mcp-service/` (the retrieval service), `forgejo/`, `serving/` — outside the line budget |
| `docs/` | The guide (`guide/`), the four normative documents, and the seven Polar run bodies that CI, the tests, and the pins walk read |
| `pins/` | The approved sets, reference and `thinking-on/`, with the derive scripts — the single source for the copies inside the wheel |
| `tests/` | The root suite (161 tests, no estate needed) and the tracked golden fixtures under `tests/fixtures/golden-mac/` |
| `spike/` | Frozen evidence from the first feasibility spike |

## Where the record lives

**The development record is maintained privately since checkpoint CP-48.** The per-checkpoint reports and prompts, the 26 ADRs, the 2026-08-24 audit, the file classification, and everything under `docs/golden/` and `docs/polar/` except the seven bodies that CI, the release gate, the test suites, and the pins walk read (the Mac golden fixtures moved, still tracked, to `tests/fixtures/golden-mac/`) exist unchanged in the operator's working tree — but not in this repository. The cost, stated plainly: the evidence column above, the shelf map in [`docs/README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/README.md), and two report paths inside the `pins.gsj.json` provenance that ships in every wheel cite `CP-NN` reports, ADR ids, and audit sections that resolve only in that private copy. They were left as written rather than rewritten, so for anyone but the operator the claims above reduce from "checkable at the cited path" to "asserted". What remains checkable from a clone: the code, the three suites, the pins walk, the wheel assertions, and the evidence bodies they execute against.

Every number above traces to a document of the record — tracked through CP-47, private since CP-48. What is still readable here: [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) (the adoption verdict, its reversing conditions, the wishlist — read this first), [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) (scope laws, the assumption register §4, the capability/gap register §7, the standing rules §8), and [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) (why each validator rule exists: gates G1/G2/G3/G5/G6/G7 as landed in `checks.py`, G4 estate-side by decision, admission, the logprob discipline). Private: `docs/reports/` (one report per checkpoint, every claim's primary evidence), `docs/prompts/`, `docs/decisions/` (the ADRs, append-only), `docs/AUDIT-2026-08-24.md` (a 24-agent adversarial audit of the whole record: the centre held — no live gate, pin value, or code path wrong; zero of 91 findings refuted — and the periphery's drift is itemised with owners), and the raw `docs/golden/` and `docs/polar/` artifacts. Nobody deciding whether to trust this needs forty reports; the audit read all of them adversarially, and this page plus the verdict is the summary that survived it.

## Licence

Apache-2.0 — [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE). `vendor/polar/` is NVIDIA's, carries its own Apache-2.0 `LICENSE`, and ships in no released artifact: the published wheel contains `gsj_rollout/`, the two pins sets, and `ingest_corpus.py` — nothing else, asserted at build time.

Predecessor: `gsj-envloader` @ v0.8.0 — archived on 2026-08-25: the golden reference (the goldens' collecting stack, readable at v0.8.0), no longer the fallback — that term expired at the verdict's conversion on 2026-08-11.

## Provenance

Citations the body used to carry inline, kept here verbatim so nothing is lost; they resolve in the operator's private record (see above).

- The verdict provisional then converted — "provisional at CP-12, converted at CP-17".
- The filesystem wall (shallow clone, remote removed, reflogs scrubbed) — CP-11.
- Gate G6 as per-mode pins data; the thinking-on set in the wheel — ADR-0024.
- The two manual image pulls on an ARM host, registered — wishlist row 40.
- One optimizer step per loop; 8/8 post-sync reward read as the onset of mode collapse — CP-21; concurrent collect-and-train and cadence weight sync having zero data points — charter A-13.
- The trainer's problems dropped deliberately — CP-00; charter §7 rows 16–21.
- An unpinned engine silently sampling at neutral defaults — CP-09 finding F1; codec identity verified at bring-up by the pins walk, not per-trace, and G4 estate-side — ADR-0011.
- Row 22 (engine-identity binding) and the credentialed-clone/egress decision owned by the first production bring-up — decided CP-40.
- "Model-agnostic in mechanism, Qwen-fitted in defaults" — CP-38's own words after the Llama run; thinking-on requiring the symmetric served template — charter A-22.
- The wheel's contents asserted at build time — CP-19; `ingest_corpus.py` in the wheel since CP-34.
- The predecessor archived — CP-45 (2026-08-25, ADR-0026); the fallback term expired at the verdict's conversion — CP-17 (2026-08-11).
