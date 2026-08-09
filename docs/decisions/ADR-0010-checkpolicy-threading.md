# ADR-0010 — the `CheckPolicy` operator surface threads through a rebindable process default

Date: 2026-08-09 (CP-11). Status: accepted.

## Context

CP-10 landed `CheckPolicy` with the documented operator move "a CUDA
estate sets `zero_at_mask1_max_rate: 0.0`" — and no mechanism: both law-6
call sites (`receiver.ingest`, `client.partition_session_results`) call
`checks.validate_session_result(result)` with the default policy, and
CP-11's freeze-lift kept `receiver.py`, `client.py` and `cli.py` frozen
(the DoD diffs them empty) while granting `config.py` "the CheckPolicy
operator surface". A knob nobody can turn is not a knob; a knob that
requires editing frozen files is not available.

## Decision

The one YAML gains a `checks:` section (`config.ChecksConfig`) mirroring
`CheckPolicy` field-for-field with defaults **read from `CheckPolicy`'s
own class attributes** (no restated numbers, no drift). `load_config`
rebinds `checks.DEFAULT_POLICY` from it after validation, and the checks
entry points' `policy` parameter defaults changed from def-time-bound
`= DEFAULT_POLICY` to `= None` resolved **at call time** against the
module global — one line, no rule touched. An explicitly passed policy
always wins; the last `load_config` in a process wins.

Alternatives rejected: (a) threading a policy parameter through
`Receiver`/`partition_session_results` — the right long-term shape, but
those files were frozen and the DoD is unambiguous; revisit at their next
freeze-lift if the global ever bites. (b) Mutating the frozen
`DEFAULT_POLICY` instance via `object.__setattr__` — subverts the
dataclass's own immutability declaration to avoid a one-line seam; worse
in every way but diff size. (c) An explicit `install_policy()` the
operator must call — nothing frozen would ever call it, so the CLI paths
would silently keep the defaults, which is the exact defect being fixed.

## Consequence

`gsj-rollout serve` and `submit` (and any library user of `load_config`)
apply the YAML's policy on both wire legs with zero frozen-file changes;
`tests/test_config.py` proves the thread end to end (a `0.0`-rate YAML
makes the frozen call shape reject the CP-07 trace). The accepted cost is
a module-global rebind as a `load_config` side effect — acceptable
because one YAML per process is the design (ADR-0008 §1) — and the known
sharp edge is multi-config processes, where the last load wins; the spec
§The CheckPolicy operator surface records both.
