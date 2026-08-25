# gsj-harness-rollout-server

[![CI](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml/badge.svg)](https://github.com/MHGanainy/gsj-harness-rollout-server/actions/workflows/ci.yml)

Given a task `(case, timestep, prompt)`, this server runs a pinned coding
agent in an isolated sandbox in which everything the agent can see — the
git checkout, the retrieval service — is truncated at `timestep`, captures
every token and logprob the model produced, and emits one validated,
training-ready trajectory. That is the whole job: **task → sandbox →
agent → trace**. It deliberately does nothing else: it does not store
trajectories, schedule work, compute rewards, manage weights, version
policies, or train — those belong to the trainer that calls it. Episode
execution and trajectory reconstruction come from NVIDIA's Polar, vendored
by SHA with three carried patches (`vendor/`, `POLAR_SHA`); our code is
the thin shell that points Polar at our corpus, our retrieval service, our
pinned agent (pi 0.83.0), and our checks.

This repo is the record of an evaluation: could Polar own the episode
layer our predecessor owned? The verdict is **ADOPT** — provisional at
CP-12, converted at CP-17 with both converting conditions met on
production hardware. [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md)
is the standalone statement, with the conditions that would reverse it.

## The shape

```
 your training loop ── submits (case, timestep, prompt) ── collects traces
      │  client.submit                                      ▲  client.collect
      │                                                     │  (re-validated by
══════╪═ HTTP ══ the server side below needs an estate ═════╪═ checks.py) ═════
      ▼                                                     │
 ┌─ POLAR — NVIDIA's, vendored by SHA ──────────────────────┴──────┐
 │ task API · scheduling · sandbox lifecycle · capture proxy ·     │
 │ trajectory reconstruction (our builder.py plugged into it)      │
 │   ┌─ sandbox ────────────────────────────┐                      │
 │   │ pi, the pinned agent                 │   the estate,        │
 │   │  git checkout @ branch timestep-T ◀──┼── Forgejo git host   │
 │   │  search clamped to page ≤ T ◀────────┼── MCP retrieval svc  │
 │   │  model calls → capture proxy ◀───────┼── inference engine   │
 │   └──────────────────────────────────────┘   (all operator-run) │
 └─────────────────┬───────────────────────────────────────────────┘
                   │ callback: one JSON body per session
                   ▼
      receiver.py + checks.py (ours): the gates → accept | quarantine
```

Ours is the shell around Polar: harness, builder, receiver, config, CLI,
checks — **1,999 lines** against the ~14,200-line Polar layer they drive
(`docs/VERDICT.md` §1). The same `checks.py` runs on both sides of the
wire — the receiver drops bad traces at the source, the trainer re-runs
the identical validators on everything it collects — so no trust is
required across the wire.

## The cutoff

The property this server exists for: `timestep` becomes a boundary the
agent cannot cross, enforced twice and audited once.

```
 timestep T arrives with the task
   │
   ├─ the filesystem wall: the sandbox clone is branch timestep-T,
   │    --depth 1, remote removed, reflogs scrubbed — git history
   │    cannot reach a page past T even offline (CP-11)
   │
   └─ the retrieval wall: the harness mints an HS256 token, host-side,
        claims {case_id, timestep, episode_id, exp}; the signing secret
        never enters the sandbox. The token rides the MCP URL.
          │
          ▼
        the MCP service verifies the signature, then filters to
        page ≤ T BEFORE ranking — T from verified claims only.
        Tampered claims (timestep 12→18, original signature) → HTTP 401.

 the audit, after the fact — checks.py, from the trace alone (gate G5):
   every retrieved page ≤ T · checkout shallow, zero remotes,
   branch == timestep-T · checkout pages contiguous 1..T
```

The agent may read its own token — it must, it is in its own working
directory — but cannot widen its timestep, because the cutoff is decided
server-side from verified claims and any mutation invalidates the
signature. That design was attacked, not assumed: see the table below.

## The two roles

Someone confuses these on first contact every time.

```
 SERVER role — needs an estate           TRAINER role — pip install, no estate
 ─────────────────────────────           ─────────────────────────────────────
 a machine you operate, running:         any Python ≥ 3.12, anywhere:
   an inference engine (vLLM)              pip install gsj-harness-rollout-server
   a Forgejo git host                      gsj_rollout.client — submit + collect
   the MCP retrieval service               gsj_rollout.checks — re-verify traces
   the ingested corpus                     installs light: pydantic + httpx
 plus this repo checked out:
   gsj-rollout serve --config …          the wheel alone runs no episodes —
   + two Polar processes (printed        it talks to a server somebody
     by serve, run by the operator)      operates on the left
```

The published package (PyPI: `gsj-harness-rollout-server` 0.1.2,
wheel-only) is for the trainer role. To run a training loop against an
existing server, start from
[`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples)
and its `RUNBOOK.md`. To bring up your own estate from nothing, start
from [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo).

One trap worth naming at the door: `checks` validates traces against
pinned approved sets (tool rosters, system prompts, skill cards,
settings), and the wheel ships **this estate's** pins so the trainer leg
works on install. On any other estate every hash gate fails
`*_not_approved` — loudly, by design. Point `GSJ_PINS_PATH` at your own
pins file before the first import of `gsj_rollout.checks` (resolution:
`GSJ_PINS_PATH` → repo checkout → packaged copy; a wrong path raises
rather than falling through to ours). The wheel also carries the
thinking-on reference set at `gsj_rollout/pins/thinking-on/pins.gsj.json`
in site-packages — gate G6 is per-mode pins data (ADR-0024). Format and
reasoning: [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

## What has been proven

Measured as of **2026-08-24** (the audit re-executed every suite and
census that day; per-checkpoint figures carry their report's date).

| claim | measured | evidence |
| --- | --- | --- |
| traces match the predecessor's golden reference | `loss_mask` exact at zero tolerance, `prompt_ids` byte-identical (2965/2965), on the Mac pair and again on the H200 pair | CP-09, CP-09′; `docs/golden/COMPARISON.md` |
| the logprobs are real captures | H200 replay-vs-replay bit-deterministic (0.000000); capture-vs-replay floor mean ≈ 0.005–0.007 on both traces symmetrically (classified platform, per the contract); Mac identical-context agreement mean \|Δ\| = 0.000114 | CP-09′, CP-09 |
| the cutoff holds under a forged claim | tampered token (timestep 12→18, original signature) rejected HTTP 401 from inside the sandbox; valid token 200; live episode retrieved pages [1, 5, 7, 9, 11], all ≤ 12 | CP-07 |
| two trainers, two loops, zero server changes | slime: 27 qualifying traces → one optimizer step → weight sync proven (logprobs moved at 5623/5782 positions) → 8/8 re-collect. verl: 110 qualifying → one step → sync (310/310 tensors, exactly one AdamW step) → 8/8. `gsj_rollout/` untouched both times | CP-17, CP-21 |
| two model families, no code change | Qwen3-0.6B (both golden pairs); Llama-3.1-8B: 8 completions merged into one full chain, quarantine empty, gates green | CP-04′/CP-09′, CP-38 |
| a stranger can run it from nothing | fresh machine, demo README the only input: clone → pip → estate up → first episode accepted, ≈ 5 minutes wall plus the model endpoint; two manual image pulls needed (amd64-only images on an ARM host — registered, wishlist row 40) | CP-36 |
| the shell stays thin | ours 1,999/2,000 lines vs Polar's ~14,200 driven; the predecessor spent ~1,800 lines on episode execution alone | audit 2026-08-24; VERDICT §1 |
| the fixture suites | root 161 + corpus 58 + mcp-service 89, all green by execution | audit 2026-08-24 |

What the badge does **not** cover: the golden pairs, fidelity, the
loops, or any episode at all — an episode needs an estate, and the
numbers that govern needed GPU time. Green means the fixtures still
pass; it is not evidence that the harness runs.

## What it does not do

- **It never trained anything, and says so.** Each loop above is exactly
  one optimizer step bracketed by two collections; CP-21 reads its own
  post-sync 8/8 reward as the onset of mode collapse, not competence.
  Concurrent collection-and-training and weight sync at cadence have
  zero data points (charter A-13).
- **The trainer's problems stay the trainer's**: storage, retention,
  mixing, staleness, collation, reward — every callback carries
  `reward: null` — and weight sync. Dropped deliberately at CP-00
  (charter §7 rows 16–21).
- **Sampling and codec provenance are the estate's, not the trace's.**
  pi sends no sampling parameters, so the engine's configuration *is*
  the sampling policy — an unpinned engine silently samples at neutral
  defaults (measured, CP-09 finding F1). Codec identity is verified at
  bring-up by the pins walk, not per-trace (ADR-0011).
- **The two open gaps**, of a 32-row capability register (21 parity,
  7 dropped by decision, 1 better, 1 TBD): row 12 — G4 codec evidence
  never rides the callback, GAP receiver-side by decision (ADR-0011);
  row 22 — per-episode binding of traces to engine identity (serve
  argv, generation config, codec), owned by the first production
  bring-up (decided CP-40). Same owner, same moment: the evaluation
  estates serve anonymous git read; the credentialed-clone/egress
  decision is also the first production bring-up's (CP-40).
- **Model-agnostic in mechanism, Qwen-fitted in defaults** — CP-38's
  own words after the Llama run. One foreign family is one data point;
  a different reasoning geometry is the wall. Thinking-on requires the
  symmetric served template (charter A-22).

## Where the record lives

Every number above traces to a committed document. The map:

- [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) — the adoption verdict, its reversing conditions, and the wishlist. Standalone; read this first.
- [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) — the normative document: scope laws, the assumption register (§4), the capability/gap register (§7), the standing rules (§8).
- `docs/reports/` — one report per checkpoint, CP-00 through the present; every claim's primary evidence. `docs/prompts/` holds each checkpoint's instructions verbatim.
- [`docs/AUDIT-2026-08-24.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/AUDIT-2026-08-24.md) — a 24-agent adversarial audit of the whole record against the working trees, executed suites, and the published artifacts. Its verdict: the center held (no live gate, pin value, or code path wrong; zero of 91 findings refuted), the periphery had drifted — and the drift is itemized with owners.
- `docs/decisions/` — 25 ADRs, append-only, one decision each.
- [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) — why each validator rule exists: gates G1/G2/G3/G5/G6/G7 as landed in `checks.py` (G4 estate-side by decision), admission, the logprob discipline.
- `docs/golden/`, `docs/polar/` — the raw artifacts: golden-pair manifests and comparisons, real run bodies, the adversarial probe transcript.

Nobody deciding whether to trust this needs to read forty reports; the
audit read all of them adversarially, and this page plus the verdict is
the summary that survived it.

## Licence

Apache-2.0 — [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE).
`vendor/polar/` is NVIDIA's, carries its own Apache-2.0 `LICENSE`, and
ships in no released artifact: the published wheel contains
`gsj_rollout/`, the two pins sets, and `ingest_corpus.py` — nothing else
(asserted at build time: CP-19; `ingest_corpus.py` since CP-34).

Predecessor: `gsj-envloader` @ v0.8.0 — archived at CP-45 (2026-08-25,
ADR-0026): the golden reference (the goldens' collecting stack, readable
at v0.8.0), no longer the fallback — that term expired at the verdict's
conversion (CP-17, 2026-08-11).
