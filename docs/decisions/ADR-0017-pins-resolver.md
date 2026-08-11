# ADR-0017 — the pins resolver: ship the defaults, honour an override

Date: 2026-08-11 (CP-16). Status: accepted.

## Context

Law 6 says the trainer runs the same `checks` the receiver ran. From an
installed wheel that was non-functional: `pyproject` packaged
`gsj_rollout` only, so `PINS_PATH` (`Path(__file__).parent.parent /
"pins" / "pins.gsj.json"`) resolved into site-packages and the first
`approved_set` call raised `PinsConfigurationError`. CP-11b measured this
and dispositioned it as noise — "both legs run from the checkout by
design". M4's bridge kills that design assumption: the trainer of record
consumes the wheel from its own training environment (slime + Megatron +
torch), not from a checkout of this repo. The CP-16 prompt offered:
ship the pins as package data, resolve them from a configurable path with
a clear error when absent, or both — recommending both, with the tension
named: shipped pins are *this estate's* approved sets, and a consumer on
a different estate must override or they validate against the wrong set.

## Decision

Both, resolved at import time in `checks.py` — the seam, no rule changes:

1. **`GSJ_PINS_PATH`** environment override, taken verbatim. A wrong or
   absent target raises `PinsConfigurationError` naming the path at the
   first `approved_set` call — it never falls through to the shipped
   values. An env var rather than a `checks:` config key because
   `config.py` is frozen this CP and because the library must resolve
   pins with no config loaded at all (CP-08's client tests exercise
   exactly that path).
2. **The repo checkout** (`CHECKOUT_PINS`, the pre-CP-16 path) when it
   exists — a checkout keeps `derive_pins.py` → re-pin → validate
   workflows live with no rebuild step.
3. **The wheel's packaged copy** (`PACKAGED_PINS` =
   `gsj_rollout/pins/pins.gsj.json`), force-included from
   `pins/pins.gsj.json` at build time. `pins/` stays the single source;
   nothing is duplicated in the tree.

The estate-mismatch tension is carried by the gates themselves: approval
is set membership, so a foreign estate's hashes fail loudly as
`*_not_approved` findings naming the unapproved digest — rejection, never
a silent pass. The failure mode of wrong pins is the same fail-closed
posture as every other pins fault.

## Consequence

`pip install` of the wheel gives a working trainer leg out of the box on
this estate (proven at CP-16: scratch venv outside every repo, the real
CP-09′ callback body, findings `[]`). A different estate sets
`GSJ_PINS_PATH` before the first import of `gsj_rollout.checks` (pins
load once per process). `checks.py` grows 9 lines (509 → 518, inside
ADR-0014's 250–520). The spec's operational-facts section records the
resolution order; four tests pin it (env wins, absent override raises,
wheel layout serves, force-include mapping present). The wheel version
stays 0.1.0 — there is no release channel yet; the first published
release must postdate this fix or the shipped artifact is the broken leg.
