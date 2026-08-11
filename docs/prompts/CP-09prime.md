# CP-09′ — M4e: H200 fidelity

You are executing CP-09′ of `gsj-harness-rollout-server`. This is CP-12's
first converting condition, and per A-16 **this verdict governs the
numerics** — the Mac pair screened structure; this establishes whether
capture is faithful on production hardware, with the replay running as
written for the first time.

Scope: collect one episode through our path against the CP-04′ estate, and
execute `docs/golden/COMPARISON.md` against `docs/golden/h200/`.

**No new features. Freeze-lift is limited to fixing what the comparison
exposes, and only if the fix is ours** — a Polar-attributable mismatch is a
finding, not a patch target. `checks.py` stays frozen (including G6, whose
pin CP-04′ derived). `vendor/` read-only. If you find yourself writing a
capability rather than a comparison, stop and record why.

Read first: `docs/golden/COMPARISON.md` — **this CP executes it, including
its new §H200 half**, it does not redesign it; `docs/golden/h200/
MANIFEST.md` (the mparison rests on); `docs/reports/
CP-04prime.md` (the estate recipe, the three engine legs, the networking
finding, the uid-in-instruction fact, the row-27 measurement); `docs/
reports/CP-09.md` (the Mac execution — the shape to repeat, and F3/F4
which no longer apply); `docs/CHARTER.md` (A-1, A-16, §5, §9).

## Step 0 — Protocol
Prompt at `docs/prompts/CP-09prime.md`; commit with the CP. Corrupted
spans: reconstruct, apply, list each under `questions:`.

## Step 1 — Bring the estate back and re-pin the engine
CP-04′ tore down but left data dirs, venvs and snapshots — the fast path.
Bring up per `staging/README.md` and `staging/serving/serve.sh`, with all
three engine legs verified again rather than assumed:

- `--generation-config` pinned, with the override warning and the applied
  block from the request log recorded. **This is not optional ceremony** —
  F1 was the failure that would have silently invalidated CP-09, and a
  re-bring-up is exactly when it recurs.
- `--enable-auto-tool-choicparser hermes`
- `--max-model-len 32768`
- `--chat-template` pointing at the committed symmetric template, sha
  verified on the serving host against `staging/serving/qwen3_training.jinja`

Plus the CP-04′ estate facts: GPU discovered free at run time, episode
containers on `gsj-staging-net`, `serving_base_url` without the `/v1`
suffix, MCP data dir user-owned, the 0.25 zero-allowance policy.

Assert readiness: `/health` ready with census and the chromadb backend,
serving healthcheck including the tool round trip, corpus verify PASS.

## Step 2 — Collect
Submit through `gsj-rollout submit` on the golden's triple —
`case_0001`, `timestep-12`, `skill:summarize` — **using the golden's own
instruction bytes**. The uid rides in the resolved instruction text
(CP-04′ finding 3), so this is binding on the exact-equality row, not a
convenience: the instruction must be byte-identical to what the golden's
episode received, with whatever the uid substitution implies stated
plainly.

Glue ids **unset** — CP-he template makes them unnecessary,
and a comparison run with a dormant repair active would measure the wrong
thing.

Assert the CP-07 standard before comparing: `COMPLETED`, no builder
findings, `chains_total == 1` with the full G7 conjunction, completions ==
pi turns, ≥1 `mcp_gsj_*` and ≥1 **successful** built-in, cutoff held. A
trace failing these is not a comparison candidate — collect another and
report the attempt count (CP-04′ took seven; expect similar).

Deposit under `docs/polar/h200-fidelity/`.

## Step 3 — Execute the comparison
Per `COMPARISON.md`'s procedure, in its severity order, as a table:
field · golden · collected · verdict · attribution.

**1. Masks — zero tolerance.** `loss_mask` semantics exact: 1 on
engine-sampled spans, 0 elsewhere, boundaries aligned to turn structure.
Compare per trace through the stated structural mapping. A mask divergence
attributable to Polar is a §9 Path C trigger.

**2. Token ids on the sampling-independent spans.** `prompt_ids` and the
inteNote what changed since CP-09**: on the Mac these were
byte-identical; here the uid substitution means turn-1 renders vary per
episode unless the instruction bytes match exactly. State what you compare
and why — if an exact match is unobtainable, say what remains comparable
(the constant spans, the glue vocabulary, the structure) and what that
costs the claim.

**3. Logprobs by replay — as written, for the first time.** Teacher-force
the golden's frozen `input_ids` through the same engine and compare against
the golden's captured values within the contract's bounds (mean |Δ| ≤
0.005, per-position |Δ| ≤ 0.05). Then the same for the collected trace.

Three things make this different from CP-09 and each is worth stating:
F3 is gone (vLLM computes prompt logprobs; vllm-metal hardcoded them
empty), F4's anchor now applies (the 0.005/0.05 bounds are a same-engine
measurement and this is finally the same engine), and **F2 is gone — no
de-stitch step**, because the merged stream is the wire context underic template. If a de-stitch would still be needed, that contradicts
CP-04′ and is a finding.

Also run the capture-vs-capture comparison on identical-context positions
— CP-09's sharpest instrument (mean |Δ| = 0.000114 there). It needs no
tolerance anchoring and is the cleanest statement of capture agreement.

**4. Structure and discipline.** Lengths consistent, `0.0` only at
`mask==0`, no sentinel at `mask==1`, `finish_reason` sane, the
exact-`0.0` rate against the 0.25 allowance on both traces (CP-04′
measured 6.2% golden / 14.3% ours — record what this pair shows).

**5. The artifact.** Both episodes produced deliverables — the Mac pair
had none to compare. Whatever comparison is meaningful (existence,
citation shape, page census within cutoff), do it and say what it proves.

Attribution per mismatch — **ours** (config, harness, builder), **Polar's**
(capture, merging, masking), or **the platform's** (engine numerics,
sampling). An unattributed mismatch is an unfinished comparison.

## Stepict
**Does Polar's trajectory reconstruction match the predecessor's, on
production hardware, with the replay run as written?**

- **PASS** — masks exact, sampling-independent structure identical,
  replay within the stated bounds, discipline sound. A-1 resolves on the
  governing platform; §5's criterion is met on the pair that counts;
  CP-12's converting condition 1 is satisfied.
- **PASS WITH FINDINGS** — matches where it matters, divergences named and
  attributed with their consequences.
- **FAIL** — a mask or retokenization divergence attributable to Polar
  with no fix on our side. Name the §9 condition and cost Path C.

Do not soften a FAIL and do not inflate a PASS. Say explicitly whether
converting condition 1 is met, and what remains before the provisional
adopt converts (M4's training loop).

## Step 5 — Charter, register, close
- A-1 gains its governing-platform resolution; A-16's counterpart closes.
- §5's success criterion: state its final status across both pairs.
- Gap rows on tonstruction, capture, logprobs, and masks reach
  their final M4 statuses.
- `docs/checks-spec.md` gains anything the comparison surfaced — especially
  any divergence class that presented as clean.
- `docs/VERDICT.md` gains a dated section: converting condition 1's result
  and what the verdict now stands on.
- Tear the estate down per the standing rule, leaving the fast-path
  artifacts.

## Definition of Done — run and show output
```
git diff HEAD -- vendor/ corpus/ mcp-service/ forgejo/ pins/ spike/ \
  docs/golden/h200/ gsj_rollout/checks.py                  # → empty
pytest -q                                        # green, counts
# the three engine legs, verbatim
# the collection assertions and attempt count, verbatim
# the comparison table
# the replay result — as written, both traces, with the bounds
# the verdict, unsoftened
ls docs/polar/h200-fidelity/
grep -n 'A-1\b' docs/CHARTER.md
test -f docs/reports/CP-09prime.md && echo OK
git status --porcelain                           # → emptmmit
```
One commit: `CP-09prime: H200 fidelity`.

## STOP — hard wall
No new capabilities. No `checks.py` changes, G6 included. No vendored
edits. No training. Do not draft or begin M4's bridge work.

## Report
`docs/reports/CP-09prime.md` per the template, printed. Under notes: the
estate and its three legs; the collection assertions and attempts; **the
comparison table**; the replay-as-written result with per-position
failures listed if any; the capture-vs-capture number; per-mismatch
attribution; the verdict unhedged with an explicit statement on converting
condition 1; and what the H200 pair showed that the Mac pair could not.
