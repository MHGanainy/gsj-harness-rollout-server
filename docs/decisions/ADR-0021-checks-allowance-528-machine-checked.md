# ADR-0021 — `checks.py`'s allowance rises to 528, exactly, and becomes machine-checked

Date: 2026-08-12 (CP-23). Status: accepted.

## Context

ADR-0014 set `checks.py` at 520 with the 23 lines above 497 earmarked for
"G6's tokenizer-free ids rule and nothing else". The earmark was spent by
other work without any checkpoint noticing — measured from `git show` at
this CP, because the CP-19 account ("CP-16 spent 9, CP-19 the last 2")
was itself incomplete: **CP-14's TR3 tripwire took the first 12**
(497 → 509), CP-16's resolver seam 9 (509 → 518), CP-19's pins signal
the last 2 (518 → 520). Three checkpoints, 12 + 9 + 2 = 23, none of them
citing the earmark; CP-19's arithmetic surfaced the result — 520/520, G6
designed (ADR-0011), unblocked (CP-04′ pinned `g6_expected_tail_ids`),
and zero lines to land it in (charter §3 [CP-19], wishlist row 18).

CP-23 resolved the budget in the ordered way its prompt demands. First
the CP-11 banking mechanism, re-applied and measured: the gate docstrings
that had crept back to 2–4 lines across CP-13/13a/14 were re-compressed
to one-line spec pointers, with the two fragments not already in
`docs/checks-spec.md` (TR3's presence-based clause, genuinely new there;
the G3 caveat's framing corrected in place — its content already had a
spec home) — **520 → 497 (−23)**, AST identical after docstring strip,
all 129 tests passing unmodified. Then the arithmetic, stated before any
rule code: G6 per ADR-0011's landing design measures **31 lines** (three
vocabulary constants, one snapshot line, one `run_trace_checks` line, a
24-line rule including its spec-pointer docstring, two blanks).
497 + 31 = **528 > 520**. The two do not close, and there is no honest
prose left — every docstring is down to the pointer form CP-11 defined.

## Decision

1. **`checks.py`'s allowance becomes 528 — the landed size exactly, with
   zero headroom by design.** The rationale for the raise is ADR-0009's,
   unchanged through ADR-0013 and ADR-0014: law 6 concentrates every
   trace-trusting decision of both wire legs into this one module, and
   splitting it manufactures the rule-family drift one-module-both-sides
   exists to prevent. The rationale for *zero headroom* is new and is
   ADR-0014's own failure: an earmark nobody re-reads is spent silently.
   An allowance equal to the measured size cannot erode — the next line
   added to this module, whatever it is for, triggers §3's
   stop-and-justify by construction.
2. **The allowance is machine-checked, as an equality.** `tests/
   test_checks.py::test_checks_allowance_is_machine_checked` asserts the
   file's line count is **exactly** 528 — not merely ≤ — so the ceiling
   is enforced by the suite on every push (CP-18's CI) rather than by a
   paragraph a checkpoint may not re-read, and in BOTH directions: growth
   trips it (the stop-and-justify), and a shrink trips it too, forcing
   the allowance down to the new size in the same change instead of
   silently recreating unpoliced headroom — the miniature of the
   ADR-0014 failure this ADR exists to close. Moving the number is
   editing that test plus an ADR — the decision and its tripwire move
   together or the suite goes red.
3. **The 2,000-line law is untouched.** This is a share reallocation, as
   ADR-0009/0013/0014 were. The tree stands at 1,792/2,000 with G6
   landed.

## Consequence

CP-23 closes at `checks.py` 528/528 and the tree at 1,792/2,000. G6 is
live on both law-6 legs (charter row 14 → PARITY); the module's next
line, of any kind, stops and justifies in an ADR that also moves the
test's ceiling. If Phase C's thinking-on work re-conceives G6 (the spec's
§G6 note), that CP inherits this discipline: re-pinning is free (pins are
data), but any rule reshaping that costs lines names them first.
