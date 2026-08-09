# ADR-0012 — The size law rises to 2,000

Date: 2026-08-09 (CP-12). Status: accepted.

## Context

Scope law 2 capped our own code at 1,500 lines — a CP-00 guess, made
before the scope was known. What the number was guessed against did not
include: hostile-content guards on both wire legs (CP-11b's never-raise
battery — NaN, surrogates, big ints, unhashable ids, non-string enums,
each yielding a finding instead of a crashed handler), four distinct
hashing conventions plus pins loading that fails closed (CP-11b), the
eleven-rule logprob discipline with its platform conditioning (CP-10), or
the validating builder subclass that CP-05's source audit made mandatory
(the layer's universal failure mode is silent degradation to
`status=COMPLETED`; ~90 lines of session-level checks nobody planned at
CP-00). The per-module table summed to 490–740; the module that absorbed
both wire legs' entire evidence law (`checks.py`, ADR-0009) alone stands
at 407.

The law was honored under pressure, which is what makes raising it
meaningful rather than face-saving: CP-11 banked 82 lines of recovery a
checkpoint ahead of the gate code; CP-11b hit 1,518 mid-CP and cured it at that
moment (−21, then net −1 more under verification) rather than at the end;
CP-10 flagged the collision one checkpoint early instead of discovering
it. The tree stands at 1,496/1,500 with the suite green — the raise
happens at a verdict CP that needs none of the new room, under the old
law, not to cure an overrun.

## Decision

Scope law 2 becomes **2,000 lines**, same exclusions (vendored Polar,
tests, the carried components `corpus/`, `mcp-service/`, `forgejo/`).
Every echo of the number tracks the law: `CLAUDE.md` law 2, charter §1,
§8 rule 2, and §9's abandon condition (the "thin shell" premise is now
judged at ~2,000 — the premise itself is unchanged; 1,496 lines of shell
against Polar's ~14,200 and the predecessor's ~1,800-line episode layer
is the evidence it holds).

The new headroom is FOR named work, not drift: the four wishlist items
(the harness settings echo, `prompt_source` + the H-41 config mirror, the
receiver's pins-failure seam, the `mcp-service/README.md` one-liner —
`docs/VERDICT.md` §wishlist), the ADR-0003 taskbank landing in
`client.py`'s orbit, and gates G1/G4/G6 if their blockers clear
(G4 stays estate-side per ADR-0011). Generously estimated that is
~150–250 lines, landing well under 2,000 with real margin left for M4's
bridge work.

## Consequence

The same stop-and-justify discipline applies at 2,000: count every
checkpoint, crossing stops the work until justified in an ADR, and
per-module allowances (§3, ADR-0009) still bind their modules. A future
raise would need what this one has — a record of the law being enforced,
a tree under the old number, and named work for the room. If the shell
ever approaches 2,000 without the wishlist and the gates accounting for
the growth, that is §9's "thin shell premise is false" signal, not a
trigger for ADR-0013.
