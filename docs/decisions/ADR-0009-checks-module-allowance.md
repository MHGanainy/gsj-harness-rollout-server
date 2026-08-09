# ADR-0009 — `checks.py`'s per-module allowance rises to 250–420

Date: 2026-08-09 (CP-11). Status: accepted.

## Context

The charter's §3 module table budgeted `checks.py` at 150–250 lines when
the plan imagined it as "trace validators". What it actually absorbed by
CP-10 is the project's entire evidence law: the admission layer, the
eleven-rule logprob discipline, the G5 census backstop — 367 lines, with
six gates and four hashing conventions still owed. CP-11's migration
moved every line of reasoning prose into `docs/checks-spec.md` (the
normative home, where an auditor already looks) leaving one-line pointers
in code; that recovered 82 lines (367 → 285) with every rule body
byte-identical — the one code change is ADR-0010's declared
`policy=None` seam — and the 59-test suite passing unmodified. 285 still exceeds 250, and
CP-11b's remaining load — gates G1/G2/G3/G7 over the new approved sets,
G4, G6, the G7 stats conjunction, pins-file loading that raises on a
missing key, and the four hashing conventions — is estimated at another
120–140 lines of code that has no prose left to shed.

## Decision

`checks.py`'s allowance becomes **250–420 lines**. The 1,500-line law is
untouched and still binds the total; this ADR reallocates share, it does
not create headroom. The reasoning: the per-module table was sized for a
thin shell whose checks mirrored the predecessor's gates one-to-one, but
law 6 concentrates *every* trace-trusting decision of both wire legs into
this one module by design — it is genuinely the largest thing here, and
splitting it (a `gates.py` beside a `checks.py`) would manufacture the
drift between rule families that one-module-both-sides exists to prevent.

## Consequence

CP-11b lands its gates inside 420. Projected totals stay the honest
problem: 1,438 today plus ~120–140 of gates reaches ~1,560–1,580, past
the 1,500 law, so CP-11b must recover ~60–80 lines elsewhere before or
while landing — the named candidates are `cli.py`'s operator-guidance
prints (~30 lines reproducible from `--help`), `builder.py`'s in-code
prose (~25 lines, same migration as this CP once its freeze lifts), and
`config.py`'s comment blocks (~15). If those do not suffice, the law's
own escape applies verbatim: the checkpoint stops and justifies in an
ADR — that decision is NOT pre-taken here.
