# ADR-0025 — length termination is surfaced, never screened

Date: 2026-08-18 (CP-33). Status: accepted.

## Context

CP-32's stranger run measured the finding this ADR answers: **7 of 72
pooled thinking-on episodes ended `finish_reason: length`** — one at
32,645 ids of the 32,768 window (99.6%) — **and every one qualified and
entered the batch silently** (external F-47, wishlist row 30's harder
half). CP-28 had measured zero at n=15 serial in both modes, so this is
a scale-and-mode property, not a constant: pooled thinking-on collection
presses the window hard enough that ~10% of episodes truncate, and
nothing anywhere said so.

The mechanism is not an oversight; it is a decision this repo already
made twice and never stated as one. `checks.py`'s TR1 allowlist has
admitted tail `length` since CP-02 (`ALLOWED_FINISH_REASONS = {stop,
tool_calls, stop_sequence, length}` — the spec's own bullet says the
tripwire "catches tail aborts", and `length` at the tail is not an
abort), while *mid-chain* `length` is an S7 hard failure in the builder
subclass (a truncated reply the harness discarded and re-prompted past —
training on thrown-away tokens). And both bridges already classify the
tail case: slime maps it to `Sample.Status.TRUNCATED`
(`slime_bridge/bridge.py:363`), verl labels the row `TRUNCATED` with the
comment "still trainable — CP-17 trained one live"
(`verl_bridge/bridge.py:357`). The trajectory layer knows; the consumer
was never shown.

## Decision

**A length-terminated episode is trainable, and qualification does not
screen it — anywhere. What changes is that every collection surface now
says the count out loud.**

1. **Trainable, because it is real.** The episode is a trajectory the
   policy actually produced: engine-sampled ids, exact mask, captured
   logprobs, every gate green up to the cut. Both trainer bridges accept
   TRUNCATED samples as first-class (loss on the tokens that exist), and
   one was trained on live at CP-17 with nothing downstream objecting.
   Discarding it at qualification would throw away ~10% of a thinking-on
   batch — real data, at measured collection cost — to enforce a policy
   preference that belongs to the trainer.

2. **No `checks.py` rule, and not only because the file is frozen.** The
   gates' subject is evidence integrity: that the trace faithfully
   records what happened and the estate that produced it is the approved
   one. A tail-`length` trace is a *faithful record of a real episode* —
   rejecting it at the receiver would quarantine correct evidence, and
   nothing downstream can recover a quarantined trace. H-41's lesson
   (loud failure is load-bearing) is about silent *absence* of evidence,
   not about policy-screening data that is honestly labeled. The
   mid-chain case stays where it is: S7, a hard builder failure, because
   there the trace genuinely misrepresents the episode. If a consumer
   one day wants fail-closed screening, that is a `CheckPolicy` knob —
   a `checks.py` change, CP-34+ with its own allowance ADR (ADR-0021's
   528/528 tripwire prices it). Nothing measured so far justifies it.

3. **Surfacing, three places, all owned by surfaces that already exist:**
   - **`cli.py submit`** prints one aggregate line after the collect
     summary — `length-terminated: K/N accepted episodes ended
     finish_reason=length …` — computed client-side from the accepted
     bodies (each trace carries `finish_reason`; the CP-27 aggregate-line
     pattern). Printed unconditionally: zero is a measurement too, and
     F-47's harm was invisibility.
   - **`train.py` (examples repo)** prints the same count at collect and
     again at grade, where the bridge's TRUNCATED classification is
     aggregated instead of silently absorbed.
   - **The spec** states the posture where TR1 is specified: the
     allowlist admits tail `length` deliberately; qualification does not
     screen it; the collection surfaces count it; training on it is the
     trainer's call, exercised through the bridge status that already
     exists.

Rejected alternatives: *screening at qualification* (silently discards
real trajectories — the exact failure shape this repo exists to prevent,
pointed the other way); *a `checks.py` rule* (fail-closed at the one
point of no recovery, and the file is at its ADR-0021 ceiling); *the
bridge dropping TRUNCATED rows* (the bridges' contract is conversion,
not curation — and verl's own zero-gradient masking is the trainer-side
mechanism for exclusion when a trainer wants it).

## Consequence

`cli.py` grows the count line (~6 lines, §3 arithmetic in the charter);
train.py grows two; `checks.py` stays at 528/528 untouched; no gate
moves. The spec carries the statement (§The logprob discipline, an
`[added at CP-33]` bullet beside TR1's allowlist). A consumer reading
any collection surface now sees exactly how many episodes hit the wall
before the GPU spends on them — and the decision to train on them, or
mask them, stays with the trainer, made visible rather than made for
them. Wishlist row 30's screening half closes as "decided: surfaced,
never screened"; its ingest-surfacing half (F-49) is cured
examples-side where the masking happens.
