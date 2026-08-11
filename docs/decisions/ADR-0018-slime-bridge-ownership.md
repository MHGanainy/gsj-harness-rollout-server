# ADR-0018 — the slime bridge is the trainer's code, in its own repo

Date: 2026-08-11 (CP-16). Status: accepted.

## Context

M4's converting condition needs a bridge: callback-shaped `SessionResult`
→ slime `Sample`. The scope law says the rollout server owns "task →
sandbox → agent → trace. Nothing else. If it stores, schedules, scores,
weights, versions, or trains — it's out." A bridge exists to feed a
trainer; by the law it cannot live in `gsj_rollout`. Polar set the same
precedent at CP-00: its `slime_bridge` sits outside the `polar` package
because slime, Ray, Megatron and torch are installed separately and Polar
depends on none of them. The predecessor's consumer proof
(`gsj-envloader-examples`) set the repo-shape precedent: an unpackaged
external repo, self-contained project directories, a FINDINGS register,
the library reached only through its published faces.

## Decision

The bridge lives in **`gsj-harness-rollout-server-examples`**
(`slime_bridge/` project directory), written at CP-16 *for* the
evaluation, owned by the trainer. Recorded here because it bears on the
scope law; its own ADR-0001 (external repo, `slime_bridge/decisions/`)
states field-by-field what it converts and asserts. Boundaries:

- It reaches the library only through the published import surface —
  `gsj_rollout.checks` (law 6's trainer leg) — plus the callback-shaped
  bodies a collect returns. It never imports `polar` or server modules.
- What it converts: `prompt_ids + response_ids` → `tokens`; `loss_mask`
  verbatim over the response span (prompt implicitly zero — slime's mask
  is per-response-token); `response_logprobs` → `rollout_log_probs` (the
  behaviour policy); `reward` → `{key: value}`; status → maskable
  (`TIMEOUT` → ABORTED, `ERROR` → FAILED, `finish_reason == "length"` →
  TRUNCATED, findings → FAILED + fully masked).
- What it asserts (each with a test that fails when removed): mask before
  ratio, sentinel rejection at ingest, and `validate_session_result`
  actually called on what arrived.
- What it deliberately omits: **no store, no staleness tracking, no ready
  grammar, no scheduler, no weight sync, no replay.** If the CP-17 loop
  needs any of those, that is a finding about the architecture — not a
  licence to rebuild the predecessor.

## Consequence

`gsj_rollout/` gains zero lines for M4's bridge; the size law is
untouched by trainer-side code forever. The bridge repo carries its own
FINDINGS register (frictions in the library surface discovered from the
consumer seat — that register is part of the point, per the predecessor's
precedent). A-6 stays open until the bridge feeds one real optimization
step (CP-17); what CP-16 resolves is the bridge *shape* half — the
conversion exists, is tested against the real CP-09′/CP-07 bodies, and
targets the exact `Sample` surface the vendored adapter constructs.
