# ADR-0019 — the packaged pins on PyPI: ship them, and say so once

Date: 2026-08-12 (CP-19). Status: accepted.

## Context

ADR-0017 force-includes `pins/pins.gsj.json` into the wheel so the trainer
leg works from an installed package with no checkout. That decision was
made for a consumer who was, in practice, us: the slime bridge in our own
examples repo, installing our own wheel from our own `dist/`. CI has
proven it green on every push since CP-18.

Publication changes the audience, not the mechanism. On PyPI the
default approved set a stranger gets is **this estate's hashes**. The
outcome is not a silent pass — approval is set membership, so a foreign
estate's trace fails `G2:system_prompt_hash_not_approved:<digest>`,
`G3:tool_roster_hash_not_approved:<digest>`, and so on, naming the digest
that was not in the set. The exposure is confusion, not admission: a
reader who sees pins ship with a library may reasonably conclude the
library has an opinion about which rosters and prompts are legitimate. It
does not. It has an opinion about *ours*.

The CP-19 prompt offered three dispositions: ship as-is, ship empty
(making `GSJ_PINS_PATH` mandatory), or ship as-is with a loud signal.
Shipping empty is the honest-looking option and the wrong one: it deletes
the out-of-the-box property CP-16 built, invalidates the CI job that
guards it, and converts a working install into a configuration error for
every consumer including the one real consumer we have.

## Decision

**Ship as-is, and make the library say so once, at import.** When
`checks` resolves pins by falling through to the packaged copy — no
`GSJ_PINS_PATH`, no checkout — it emits a single `UserWarning` naming the
path, stating that these are the reference estate's approved sets rather
than defaults, naming `GSJ_PINS_PATH` as the cure, and stating the
consequence of ignoring it (`*_not_approved` on every hash gate).

Three properties of the signal, each deliberate:

1. **It fires only in the case that is actually ambiguous.** An explicit
   `GSJ_PINS_PATH` means the operator has chosen; a checkout means a
   developer is working in-tree. Both are silent. Only the
   installed-wheel-with-no-override path — precisely the PyPI stranger —
   warns. Verified in all three configurations at CP-19.
2. **It is a warning, not a raise.** The gates' fail-closed posture is
   unchanged, and no rule moved. Turning a working install into an
   exception is the "ship empty" option wearing a different hat.
3. **It is once per process**, because pins load once per process
   (ADR-0017), and a per-call warning would train people to filter it.

The same statement is made where a PyPI reader meets it first: a section
in `README.md`, which is the project's PyPI landing page.

**Sync and re-pin.** The packaged copy stays in sync with `pins/` **by
construction** — it is force-included from `pins/pins.gsj.json` at build
time and is never duplicated in the tree, so there is no second file to
drift. A re-pin therefore requires **nothing** of a checkout consumer
(resolution order puts the checkout above the packaged copy) and **a
rebuild** of any published artifact: pins are baked at build time, so a
wheel is a snapshot of the approved sets as of its build. A re-pin that
must reach installed consumers is a version bump, not a file edit.

## Consequence

`checks.py` grows **2 net lines** (518 → **520**; +5 / −3): `import
warnings`, the guard, and the two-line warning, paid for in part by
collapsing the resolver's four-line comment to two — the three lines
deleted said at rest exactly what the warning now says at runtime. No
rule body changed; the 129-test suite passes unmodified.

**This lands `checks.py` exactly on ADR-0014's 520 ceiling, and that is a
finding this ADR hands forward rather than hides.** ADR-0014 reserved the
23 lines above 497 for G6's tokenizer-free ids rule "and nothing else";
CP-16 spent 9 of them on the resolver seam without noting the earmark,
and CP-19 spends the last 2. G6 is owed (ADR-0011), and unblocked since
CP-04′ pinned `g6_expected_tail_ids` — it can no longer land inside 520.
Whoever lands it raises the allowance in an ADR or banks prose to
`docs/checks-spec.md` the way CP-11 did. Registered as wishlist row 18 so
it is discovered now rather than mid-checkpoint.

A consumer with their own estate sets `GSJ_PINS_PATH` before the first
import of `gsj_rollout.checks` and never sees the warning. A consumer who
ignores it gets loud per-gate rejections naming digests, which is the
same fail-closed posture as every other pins fault — and now a sentence
telling them why.
