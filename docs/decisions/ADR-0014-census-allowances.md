# ADR-0014 — allowances for the returning checkout census: `checks.py` 520, `pi_harness.py` 350

Date: 2026-08-10 (CP-13a). Status: accepted.

## Context

CP-13a lands the workspace identity echo and, with it, **G5's checkout
census clauses return** — the two clauses CP-11 dropped as
"unreconstructable from the trace" (gap row 13(a)). Neither ADR-0009 nor
ADR-0013 anticipated that: both sized `checks.py` for the gates as they
stood, and the census was a *dropped* capability at the time each was
written. Landing it costs `checks.py` 37 lines (460 → 497: `check_workspace`
plus five vocabulary constants), which passes ADR-0013's 480.

`pi_harness.py` has a second, older problem this ADR settles rather than
inherits. Charter §3's per-module table budgets it at **50–150**; it has
stood above that since CP-07 (224 at CP-10, 237 at CP-11b, 258 after
CP-13's settings echo) without any ADR ever saying so, because §3 frames
those numbers as a planning estimate against the real law ("Sum 490–740 —
the ceiling is headroom, not a target"). CP-13a's probe takes it to 322.
Two modules drifting from one table, only one of them ever ADR'd, is the
condition where a budget stops being enforceable.

## Decision

1. **`checks.py`: 250 → 520.** The rationale is ADR-0009's, unchanged and
   now applying to a wider surface: law 6 concentrates every
   trace-trusting decision of both wire legs into this one module by
   design, and splitting it manufactures the rule-family drift that
   one-module-both-sides exists to prevent. The 23 lines of headroom above
   today's 497 are for G6's tokenizer-free ids rule (designed at
   ADR-0011, owed when CP-04′ pins `g6_expected_tail_ids`) and nothing
   else.
2. **`pi_harness.py`: 50–150 → 50–350**, recorded now rather than left as
   silent drift. What the module actually owns, none of it foreseen at
   CP-00: the ADR-0006 harness contract, the stdlib HS256 episode-token
   mint, the CP-11 clone hardening (`--depth 1`, remote drop, reflog
   scrub), the artifact exit, and now two statements about execution — the
   settings echo (G7) and the workspace probe (G5's census).
3. **The 2,000-line law is untouched.** Both are share reallocations, as
   ADR-0009 and ADR-0013 were. The tree stands at 1,746/2,000.

## Consequence

CP-13a closes at `checks.py` 497/520 and `pi_harness.py` 322/350. G6 lands
inside 520; anything past either number stops and justifies again, per §3's
own law. Charter §3's module table is updated to carry both allowances with
pointers to the ADRs that set them, so a future reader sees the current
numbers rather than the CP-00 estimate.
