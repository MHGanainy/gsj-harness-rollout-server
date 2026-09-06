# gsj-harness-rollout-server

[![CI](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml/badge.svg)](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml)

A rollout server for the gsj corpus: given a task `(case, timestep, prompt)`, it runs a pinned coding agent (pi 0.83.0) in an isolated sandbox whose git checkout and retrieval are both truncated at `timestep`, captures every token and logprob the model produced, and emits one validated, training-ready trajectory — **task → sandbox → agent → trace**, nothing else (no storage, scheduling, rewards, weights, versioning, or training; those belong to the trainer that calls it).
Episode execution and trajectory reconstruction are NVIDIA's Polar, vendored by commit with three carried patches; our own code is the 2,034-line shell that points Polar at our corpus, retrieval service, agent, and checks. The evaluation behind it ended in **ADOPT** (provisional 2026-08-09, converted 2026-08-11 on production hardware) — [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) is the standalone statement, with the conditions that would reverse it.

![One task enters from the training loop, Polar runs the agent in a sandbox fed by the operator's estate, the trace is reconstructed, checked, and either accepted or quarantined](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/overview-shape.png)

<sub>One task triple in, one validated trace out. Everything around the sandbox is Polar's, the operator's estate, or the trainer's; ours is the harness, the builder, the receiver, and the checks.</sub>

## Install

```bash
# trainer: any Python >= 3.12, anywhere; deps pydantic, httpx, pyyaml; runs no episodes
pip install gsj-harness-rollout-server

# server: a checkout, Polar's venv (it must also host gsj_rollout — Polar loads our harness and builder by import path), and an estate no pip install provides
git clone https://github.com/MHGanainy/gsj-harness-rollout-server && cd gsj-harness-rollout-server
python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd vendor/polar && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . && uv pip install -p .venv/bin/python -e ../.. && cd ../..
gsj-rollout serve --config rollout.yaml    # renders topology.rendered.yaml, prints the two Polar commands, runs the receiver
```

## Quick start

```python
from gsj_rollout import RolloutClient, load_config
from gsj_rollout.config import render_task_request
cfg = load_config("rollout.yaml")            # one YAML describes the whole deployment
request = render_task_request(cfg, task_id="demo", instruction="Fix the failing test.", case_id="case_0001", timestep=12)
traces = RolloutClient(cfg.polar.rollout.base_url).collect([request])   # Polar's rollout API, not the receiver; list[Trace], only checks-clean sessions come back
```
```bash
gsj-rollout submit --config rollout.yaml --case case_0001 --timestep 12 --prompt "Fix the failing test."
# exit codes: 0 all collected · 1 partial · 2 usage · 3 server unreachable
```

## The two roles

| | Server role | Trainer role |
| --- | --- | --- |
| You need | the four estate services — an inference engine (vLLM, pinned chat template), a Forgejo git host (one repository per case, one branch per timestep), the MCP retrieval service, the ingested corpus — plus this checkout with Polar's venv under `vendor/polar/` | Python ≥ 3.12, anywhere: `pip install gsj-harness-rollout-server` (0.1.8, wheel-only: `gsj_rollout/`, both pins sets, the G2 reference capture, `ingest_corpus.py`, `estate.py`). No `vendor/`, no Polar |
| You run | `gsj-rollout serve --config <yaml>`, then the two printed Polar commands yourself: `serve_rollout` (rollout API + scheduler — the trainer's `base_url`) and `serve_gateway` (gateway + capture proxy, one sandbox per episode, loading `pi_harness.py` and `builder.py` by import path) | `RolloutClient`: `submit` · `wait` · `collect` — `collect` submits, polls `GET /rollout/task/{id}`, re-runs `checks` on every result, returns the `Trace`s of clean sessions |
| You validate | every callback: clean → `traces/`, bad → `quarantine/` with its findings — the same `checks.py` on both sides of the wire | `checks.validate_session_result(result)` — the identical validators the receiver ran, because nothing upstream is trusted |
| Start here | [Server guide](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/server-guide.md); an estate from nothing: [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo) | [Trainer guide](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/trainer-guide.md); a loop against an existing server: [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples) + its `RUNBOOK.md` |

**One trap worth naming at the door.** `checks` validates traces against pinned approved sets (tool rosters, system prompts, skill cards, settings), and the wheel ships **this estate's** pins — on any other estate every hash gate fails `*_not_approved`, loudly, by design. Point `GSJ_PINS_PATH` at your own pins file before the first import of `gsj_rollout.checks`; resolution is `GSJ_PINS_PATH` → repo checkout → packaged copy (a `UserWarning` when the packaged copy is what resolved), and an unusable path raises `PinsConfigurationError` rather than falling through. The thinking-on reference set rides at `gsj_rollout/pins/thinking-on/pins.gsj.json` — gate G6 compares against per-mode pins data. Format and reasoning: [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

## The timestep cutoff

![The task carries T into the sandbox; a filesystem wall stands between the agent's checkout and the git host, a retrieval wall between its search tool and the retrieval service, and the estate holds the full document behind both](https://raw.githubusercontent.com/MHGanainy/gsj-harness-rollout-server/main/docs/guide/img/cutoff-walls.png)

<sub>`timestep` is a boundary the agent cannot cross — one wall on the filesystem, one in front of retrieval — enforced twice and audited once.</sub>

- **The filesystem wall.** The sandbox clone is branch `timestep-T`, `--depth 1`, remote removed, reflogs scrubbed — git history cannot reach a page past T even offline.
- **The retrieval wall.** The harness mints an HS256 token host-side with claims `{case_id, timestep, episode_id, exp}`; the signing secret never enters the sandbox; the service verifies the signature, then filters to `page ≤ T` *before* ranking, with T from the verified claims only. The agent may read its own token but cannot widen its timestep — any mutation invalidates the signature (tampered claims, timestep 12→18 with the original signature: HTTP 401).
- **The audit.** `checks.py` gate G5, from the trace alone: every retrieved page ≤ T; the checkout shallow, zero remotes, branch `== timestep-T`; checkout pages contiguous `1..T`.

## Documentation

- The guide, six flat pages under [`docs/guide/`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/README.md): [index](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/README.md) · [how it works](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/how-it-works.md) · [validation and pins](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/validation-and-pins.md) · [server guide](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/server-guide.md) · [trainer guide](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/trainer-guide.md) · [troubleshooting](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/troubleshooting.md)
- Normative: [Verdict](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) (read first) · [Charter](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) (scope laws; assumptions §4; gap register §7; standing rules §8) · [Checks spec](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) · [Corpus contract](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md)

## What has been proven

| claim | measured — as of 2026-08-24 (the audit re-executed every suite and census that day; per-checkpoint figures carry their report's date) | evidence |
| --- | --- | --- |
| traces match the predecessor's golden reference | `loss_mask` exact at zero tolerance; `prompt_ids` byte-identical (2965/2965) — on the Mac pair and again on the H200 pair | CP-09, CP-09′; `docs/golden/COMPARISON.md` |
| the logprobs are real captures | H200 replay-vs-replay bit-deterministic (0.000000); capture-vs-replay floor mean ≈ 0.005–0.007 on both traces symmetrically (platform-classified, per the contract); Mac identical-context agreement mean \|Δ\| = 0.000114 | CP-09′, CP-09 |
| the cutoff holds under a forged claim | tampered token (timestep 12→18, original signature) rejected HTTP 401 from inside the sandbox; valid token 200; live episode retrieved pages [1, 5, 7, 9, 11], all ≤ 12 | CP-07 |
| two trainers, two loops, zero server changes | slime: 27 qualifying traces → one optimizer step → weight sync (logprobs moved at 5623/5782 positions) → 8/8 re-collect; verl: 110 qualifying → one step → sync (310/310 tensors, exactly one AdamW step) → 8/8; `gsj_rollout/` untouched both times | CP-17, CP-21 |
| two model families, no code change | Qwen3-0.6B (both golden pairs); Llama-3.1-8B — 8 completions merged into one full chain, quarantine empty, gates green | CP-04′/CP-09′, CP-38 |
| a stranger can run it from nothing | fresh machine, demo README the only input: clone → pip → estate up → first episode accepted, ≈ 5 minutes wall plus the model endpoint; two manual image pulls needed (amd64-only images on an ARM host — registered) | CP-36 |
| the shell stays thin | ours 1,999/2,000 lines vs Polar's ~14,200 driven; the predecessor spent ~1,800 lines on episode execution alone | audit 2026-08-24; VERDICT §1 |
| the fixture suites | root 161 + corpus 58 + mcp-service 89, all green by execution | audit 2026-08-24 |

The badge covers none of this — not the golden pairs, fidelity, the loops, or any episode (episodes need an estate and GPU time). Green means the fixtures still pass, not that the harness runs.

## What it does not do

- **It never trained anything, and says so.** Each loop above is exactly one optimizer step bracketed by two collections; the post-sync 8/8 reward reads as the onset of mode collapse, not competence. Concurrent collection-and-training and weight sync at cadence have zero data points.
- **The trainer's problems stay the trainer's**: storage, retention, mixing, staleness, collation, reward — every callback carries `reward: null` — and weight sync. Dropped deliberately, at the start ([charter](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) §7 rows 16–21).
- **Sampling and codec provenance are the estate's, not the trace's.** pi sends no sampling parameters, so the engine's configuration *is* the sampling policy — an unpinned engine silently samples at neutral defaults (measured). Codec identity is verified at bring-up by the pins walk, not per-trace.
- **Two open gaps**, of a 32-row capability register (21 parity, 7 dropped by decision, 1 better, 1 TBD): row 12 — G4 codec evidence never rides the callback, receiver-side by decision; row 22 — per-episode binding of traces to engine identity (serve argv, generation config, codec), owned by the first production bring-up. The separate anonymous-read gap is closed: the reference estate and demo require Forgejo sign-in and use credentialed clones (CP-58/59; re-measured at CP-82). This repository defense leaves the engine and MCP reachable, as episodes require; it does not close row 22's provenance gap.
- **Model-agnostic in mechanism, Qwen-fitted in defaults.** One foreign family is one data point; a different reasoning geometry is the wall. Thinking-on requires the symmetric served template.

## Repository layout

| Path | What it is |
| --- | --- |
| `gsj_rollout/` | the server, eight modules (`pi_harness`, `builder`, `receiver`, `checks`, `config`, `client`, `cli`, the package surface: `RolloutClient`, `Trace`, `checks`, `load_config`, `RunConfig`) — the whole of what the wheel ships, plus the pins, `ingest_corpus.py` and `estate.py` copied in at build time |
| `vendor/polar/` | Polar at the commit in `POLAR_SHA`, patched (`vendor/patches/` P1–P3, `vendor/apply_patches.sh --verify`, re-vendor recipe `vendor/REVENDOR.md`); ships in no artifact |
| `estate/` | this repository's test estate: `estate.sh` front door, `estate.py` (the estate's one tool — scaffold · validate · up · ingest · update · status · down), `corpus/`, `mcp-service/`, `forgejo/`, `serving/` — outside the line budget |
| `docs/` · `pins/` | the guide, the four normative documents, and the seven Polar run bodies CI/tests/pins-walk read; the approved sets (reference + `thinking-on/`) with derive scripts — the single source for the wheel copies |
| `tests/` | the root suite (176 tests, no estate needed) and the tracked golden fixtures `tests/fixtures/golden-mac/` |

`pytest -q` requires the Docker CLI and Compose plugin for credential parsing checks; no Docker daemon or running estate is needed.

The CP-06 feasibility spike (stub backend, spike harness, the stub-side wire captures, `p1_verdict.py`, `wire_diff.py`) left the tree at CP-68 and is frozen at tag [`spike-cp06`](https://github.com/MHGanainy/gsj-harness-rollout-server/tree/spike-cp06/spike) — commit `a769771`, tree `2082a24f`; restore with `git checkout spike-cp06 -- spike`.

## Where the record lives

**The development record is maintained privately.** The per-checkpoint reports and prompts, the 37 ADRs, the 2026-08-24 adversarial audit (24 agents; no live gate, pin value, or code path wrong; zero of 91 findings refuted), and the raw `docs/golden/`/`docs/polar/` artifacts exist unchanged in the operator's working tree, not in this repository — so the evidence column above, the shelf map in [`docs/README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/README.md), and two report paths in the shipped `pins.gsj.json` provenance resolve only there; for anyone else those claims reduce from "checkable at the cited path" to "asserted". What stays checkable from a clone: the code, the three suites, the pins walk, the wheel assertions, and the evidence bodies they execute against.

## Licence

Apache-2.0 — [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE). `vendor/polar/` is NVIDIA's, carries its own Apache-2.0 `LICENSE`, and ships in no released artifact: the wheel contains `gsj_rollout/`, the two pins sets, the G2 reference capture (`pins/container/system_prompt.container.derived.txt`), `ingest_corpus.py` and `estate.py` (as `gsj_rollout.ingest_corpus` / `gsj_rollout.estate` — `gsj_rollout.bringup` on wheels 0.1.3–0.1.5) — nothing else, asserted at build time (18 entries since 0.1.3). Predecessor: `gsj-envloader` @ v0.8.0, archived 2026-08-25 — still the goldens' collecting stack, readable at v0.8.0; no longer the fallback, a term that expired at the verdict's conversion on 2026-08-11. Its frozen [`sandbox/` recipe](https://github.com/MHGanainy/gsj-envloader/tree/v0.8.0/sandbox) also supplied the harness image's arm64 build at CP-64, and its [`staging/BRINGUP.md`](https://github.com/MHGanainy/gsj-envloader/blob/v0.8.0/staging/BRINGUP.md) remains the cold-start reference linked from [the living estate recipe](estate/README.md). Reuse is recorded here; the archive stays frozen.

## Provenance

- The verdict provisional at CP-12, converted at CP-17 · the predecessor archived at CP-45 (2026-08-25, ADR-0026), the fallback term expired at CP-17 (2026-08-11) · the wheel's contents asserted at build time — CP-19, `ingest_corpus.py` in the wheel since CP-34.
- The filesystem wall — CP-11 · gate G6 as per-mode pins data, the thinking-on set in the wheel — ADR-0024 · the two ARM image pulls registered — wishlist row 40 · an unpinned engine at neutral defaults — CP-09 finding F1 · codec at bring-up via the pins walk, G4 estate-side — ADR-0011.
- One optimizer step per loop, 8/8 read as mode-collapse onset — CP-21 · zero data points on concurrent collect-and-train and cadence sync — charter A-13 · the trainer's problems dropped — CP-00, charter §7 rows 16–21 · row 22 and credentialed-clone/egress owned by the first production bring-up — CP-40 · "Qwen-fitted in defaults" — CP-38's own words · the symmetric served template — charter A-22.
