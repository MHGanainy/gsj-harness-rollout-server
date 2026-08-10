# ADR-0013 — `checks.py`'s per-module allowance rises to 250–480

Date: 2026-08-09 (CP-13). Status: accepted.

## Context

ADR-0009 set `checks.py` at 250–420 when the module held the admission
layer, the logprob discipline, the G5 backstop, and CP-11b's four gates
(407 lines at CP-12's close). CP-13 lands the two gates the CP-12 verdict
named as the wishlist's purpose — G1 (the stated `prompt_source` + card
hash, unblocked by the `config.py` freeze-lift) and G7's settings clause
(unblocked by the harness echo) — plus their five vocabulary constants and
`PinsConfigurationError` (the CP's adversarial pass measured the pins
lookup failing open on a non-list value and four load faults escaping
classification): 460 lines, 40 over the ADR-0009 top. The size LAW was raised to 2,000 at
CP-12 (ADR-0012) explicitly "FOR the four wishlist items … and gates
G1/G4/G6 if their blockers clear"; the per-module share was not re-cut
then because the gates had not landed.

## Decision

`checks.py`'s allowance becomes **250–480 lines**. The 2,000-line law is
untouched and still binds the total; this reallocates share, exactly as
ADR-0009 did. The rationale is ADR-0009's, unchanged: law 6 concentrates
every trace-trusting decision of both wire legs into this one module by
design, and splitting it manufactures rule-family drift. The extra 25
lines of headroom above today's 455 are for G6's tokenizer-free
ids-`endswith` rule, already designed (ADR-0011) and owed to this module
when CP-04′ pins `g6_expected_tail_ids`.

## Consequence

CP-13 closes at 460/480 with the total at 1,642/2,000. G6 lands inside
480 at its CP-04′-unblocked checkpoint; anything beyond that stops and
justifies in a new ADR, per §3's own law.
