# ADR-0011 — G4/G6 codec evidence: measure-at-serve, at the pins walk

Date: 2026-08-09 (CP-11b). Status: accepted.

## Context

G4 verifies the codec (tokenizer git-blob OID + chat-template sha256 ∈
approved sets); G6 verifies thinking-off by comparing assistant-turn
openings against `g6_expected_tail`. Both need codec evidence the receiver
does not have, and CP-11b was chartered to decide where it comes from:
**measure-at-serve** (the estate records the artifacts it actually served;
the check compares measurements) versus **trust-provenance** (the gate
verifies a fingerprint the trace declares).

The facts, measured this CP:

1. **No fingerprint of any kind rides the callback.** Both real callback
   bodies (CP-07 `sk-polar-c4eef751…`, CP-09 `sk-polar-180dd057…`) contain
   zero occurrences of `fingerprint`, `tokenizer`, `chat_template`, or
   `settings`. The word `fingerprint` appears nowhere in the vendored
   Polar tree.
2. The one fingerprint that exists anywhere is `response.system_fingerprint`
   on the persisted per-completion record
   (`docs/polar/completion_record.json`:
   `0.31.3-0.32.0-macOS-15.6.1-arm64-arm-64bit-applegpu_g16s`) — an
   **engine platform string**, not a codec identity: it names neither the
   tokenizer nor the template. And per-completion records do not ride the
   callback at all (CP-05, A-5 caveat).
3. CP-09's F1 is the precedent for what trusting claims costs: the served
   snapshot shipped no `generation_config.json`, the engine silently
   sampled at neutral defaults, and nothing on the trace could see it —
   the trace-side gates stayed green. Sampling and engine provenance are
   ESTATE provenance, not trace provenance (row 22).
4. The measure-at-serve instrument already exists: `pins/derive_pins.py`
   hashes the **actual served snapshot's** `tokenizer.json` (git-blob OID)
   and `tokenizer_config.json` `chat_template` (sha256 of the JSON field)
   against the approved sets, estate-side, exiting nonzero on divergence.
5. G6's decode needs a tokenizer at check time, and no process on either
   wire leg has one: this package's deps are pydantic/httpx/pyyaml,
   Polar's are fastapi/uvicorn/httpx/pydantic/pyyaml (A-14) — so the
   builder subclass is NOT a viable home either, despite running in
   Polar's process.

## Decision

**Measure-at-serve, executed at the pins walk on the serving estate.**
Neither gate lands receiver-side at this pin, each with its mechanism
named:

- **G4** is verified by running `pins/derive_pins.py` against the served
  snapshot at estate bring-up (CP-04′'s inherited DoD already pins the
  serve argv and the template file in the MANIFEST — items 3–5; the walk
  is the hash comparison of exactly the artifacts that argv serves). The
  check compares the artifact, not a claim about it.
- **G6** lands receiver-side **without a tokenizer** once the next walk
  pins `g6_expected_tail_ids` — the pinned tail *as token ids* under the
  served tokenizer. The check is then an ids-`endswith` over the mask-0
  interstitial span preceding each mask-1 span of `response_ids`, **and,
  for the first turn, over the suffix of `prompt_ids`** — measured on
  both real traces: the first mask-1 span starts at `response_ids[0]`
  with no preceding interstitial, and the turn-1 tail (the 7-id sequence
  ending in the ADR-0007 glue) sits at the end of `prompt_ids`
  (`prompt_ids[-7:] == [151644, 77091, 198, 151667, 271, 151668, 271]`
  on both episodes — the CP-11b verification pass caught the
  response_ids-only wording checking zero turns on a single-turn
  episode). Per the spec's standing rule, G6 reads token ids, never
  `response_messages`. Deriving the ids needs the tokenizer at PIN time
  only, which is estate-side by construction. Blocked this CP by the
  no-re-pin wall; CP-04′ re-derives the tail anyway (the Direction-A
  template changes it by design).

**Trust-provenance is rejected**, twice over: it verifies the claim rather
than the artifact (a mis-configured estate that reports the right
fingerprint passes — the exact F1 shape), and at this pin it is not even
implementable — there is no codec claim on the callback to verify, so it
would have required a vendored patch (stamping fingerprints into metadata
Polar forwards) just to obtain a weaker guarantee.

## Consequence

Rows 12 and 14 stay GAP with their blockers named as mechanism, not
mystery: G4 = estate-side walk at bring-up (CP-04′), G6 = `g6_expected_
tail_ids` on the next walk, then a receiver-side ids rule. The residual
that measure-at-serve does NOT close, named honestly: **per-episode
binding** — nothing ties episode N's traces to the bring-up measurement,
so a snapshot swap after the walk is invisible to every trace-side check
(row 22's estate-provenance finding; its cure is an estate provenance
surface, out of this repo's scope by the scope law). CP-12 inherits both
gates on the not-checked-here list with these pointers.
