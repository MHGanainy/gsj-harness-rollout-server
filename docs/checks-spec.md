# checks-spec — the `checks.py` specification

Captured at CP-01, while the predecessor is fresh, so CP-10/CP-11
**implement rather than re-derive**. **[CP-11] This document is the SOLE
home of rule reasoning**: the budget migration moved `checks.py`'s
in-code prose here wholesale (367 → 285 lines; every rule body
byte-untouched, the one code change being the declared `policy=None`
call-time-default seam of §The CheckPolicy operator surface; the 59-test
suite the proof), leaving one-line pointers in code — an auditor reads
here, the module enforces (ADR-0009). Normative sources: the predecessor's
`gsj/envloader/gates.py` and `gsj/envloader/pin.py` @ v0.8.0 (frozen — read
them, never modify them, law 3), its README §6, `mcp-service/README.md`
(the G3/G5 surface), and CP-00's report notes. `checks.py` runs on **both
sides of the wire** (law 6): the receiver drops bad traces at the source,
the trainer re-verifies what arrived — same code, no trust required.

## The pins and the approved-set format

All fingerprints are **generated data — never literals in code** (the
predecessor's delta law; its ADR-0013). Seven pins:

`tokenizer_hash` · `chat_template_hash` · `settings_hash` ·
`tool_roster_hash` · `system_prompt_hash` · `skill_card_hash` ·
`g6_expected_tail`

Every pin value is a **set**: an order-preserving, deduplicated list of
approved hashes (`format: gsj-pins/1`). Entries for path schemes that no
longer exist are dropped, not kept — dead entries only weaken a gate. A
missing pins key at check time **raises loudly**; the gates never fail
open. The predecessor's pinned values did not move (ADR-0002, gap row 23):
they are stale by construction under Polar's mounts, and the first valid
approved sets in this repo come from the derive → re-pin →
first-episode-validate walk (CP-07/CP-10/CP-11). The captured evidence the
walk starts from is in `pins/` (inventory at the end of this doc).

**[CP-11] The walk executed — `pins/pins.gsj.json` is the approved-set
home, `pins/derive_pins.py` re-derives it (exit nonzero on divergence).**
Every value on the walk's list came out derivable from evidence this repo
owns, and every one **reproduced the predecessor's pinned value exactly**
— which is a measurement, not an inheritance: G3 hashed from the wire
`tools` array of both real episodes (CP-07 and CP-09), G2 from both
episodes' wire system prompts (the docker-mode `/workspace` singleton
property HOLDS on this stack — 4,466 chars / 4,476 UTF-8 bytes,
byte-identical across episodes
and to the derived singleton), G7 from the harness's own rendered
constant, G1 from the corpus staging cards, G4's tokenizer OID from both
model snapshots (identical — the mlx conversion carries `tokenizer.json`
byte-for-byte), and G4's template pinned to the **served** snapshot's
hash per finding (a) with the codec hash recorded-not-approved. "Stale by
construction" therefore resolved to *value-stable in practice*, exactly
as CP-04's estate-invariance measurement predicted; what changed is the
provenance — the values are now first-class artifacts of THIS repo's wire
evidence, not literals trusted across repos. The `first-episode-validate`
leg stays open for CP-11b (it needs a gate consuming the file plus a
fresh episode; estate re-collection was STOP-walled this CP). Only
`chat_template_hash` is Mac-estate-specific (the served snapshot is the
Mac's vllm-metal serving artifact); CP-04′ re-derives it by design when
the Direction-A template lands.

## The four hashing conventions

Four distinct conventions across the gates — reproduce **exactly**, one
shared implementation per convention, no inline copies:

1. **UTF-8 text sha256** — G1 (the skill-card text *as resolved at
   rollout*) and G2 (the *effective wire* system-prompt text). Hash the
   exact bytes of the text, UTF-8, no normalization, no stripping.
2. **Canonical-JSON sha256** — G3 (the tools array as sent on the wire)
   and G7 (the parsed settings document). Canonicalization is the
   predecessor's `canonical_json` (`gsj/envloader/store.py`): sorted keys,
   compact separators, UTF-8 — byte-for-byte, or every hash silently
   changes. Anchor for a correctness test: hashing
   `pins/tools.captured.json`'s wire array with the predecessor's
   convention reproduced the pinned roster hash `a7a7956b…48e56` at its
   CP-29 (a historical anchor for testing the *convention* — the value
   itself stays DATA, never a literal in `checks.py`).
3. **git-blob OID sha1 + template-string sha256** — G4. The tokenizer
   identity is the git blob OID (`sha1("blob <len>\0" + bytes)`) of
   `tokenizer.json`; the chat-template identity is the sha256 of the
   template *string extracted from the JSON field* of
   `tokenizer_config.json` (not of the file). Two different algorithms in
   one gate — do not "simplify" them into one.
4. **No hash at all** — G6. The decoded assistant-turn opening is compared
   **verbatim** with `str.endswith` against `g6_expected_tail`
   (`pins/g6_tail.captured.txt`, 41 bytes of Qwen chat-template tail).

## The gates (what survives is CP-11's call — gap rows 9–15)

| gate | verifies | evidence | mechanism |
|---|---|---|---|
| G1 | skill-card integrity | `prompt_source`, raw `skill_card_text` as resolved at rollout | `skill_card_hash` ∈ approved set (free rows: n/a, pass) |
| G2 | clean containerised system prompt | effective wire `system_prompt_text` | `system_prompt_hash` ∈ approved set; **path-sensitive** — the checkout path is the only case-dependent span, so constant container paths collapse the set to a singleton, and different Polar mounts change every hash on day one |
| G3 | the 11-tool roster, unmodified | `tools_wire` **as sent** | canonical-JSON `tool_roster_hash` match |
| G4 | pinned template + tokenizer | codec fingerprint (measured, never config-echoed) | `tokenizer_hash`/`chat_template_hash` ∈ approved sets |
| G5 | search respects the page cutoff | `timestep`, checkout page census, `search_case` result pages | max checkout page == T ∧ pages contiguous from 1 ∧ every search-result page ≤ T |
| G6 | thinking disabled | decoded assistant-turn openings | each ends with the pinned tail; **zero assistant turns fails closed** |
| G7 | no compaction, ever | `settings_text` read back from disk + chain snapshot | `settings_hash` ∈ approved set ∧ `compaction.enabled == false` ∧ the chain snapshot below |

## The failure vocabulary

Failures are **byte-stable strings** `G{n}:{slug}` (e.g.
`G5:search_page_gt_timestep` — the predecessor's actual constant), with the missing-evidence form
`G{n}:missing_evidence:<field>`. Downstream forensics **greps these
strings** — never reword, never localize, never restructure them. The
posture is fail-closed everywhere: evidence that was never gathered fails
its owning gate; any non-empty failure list means the trace is dropped at
the receiver (the trainer-side quarantine/forensics story is the trainer's
problem — gap row 16).

**[CP-10] The vocabulary is now a code-level contract**:
`checks.FINDING_VOCABULARY` enumerates every `{id}:{slug}` the module can
emit and is **snapshot-tested** — a rename breaks the test, which is the
point. Four families are live: `ADM*` (admission, CP-08), `LP1`–`LP8`
(the logprob discipline's array rules), `TR1`/`TR2` (the same section's
two non-array tripwires — the `finish_reason` allowlist and the re-vendor
canary), and `G5:*`. The gate families `G1`–`G4`/`G6`/`G7` are CP-11's.
Per-position rules report **one finding per rule** with
`:first={index}:count={n}` rather than one per position, so a
systematically broken array cannot flood the list.

## The logprob discipline

`rollout_log_probs` must be **finite and ≤ 0 everywhere**, with a literal
`0.0` permitted **only** at `mask == 0` positions (the record-semantics
placeholder). Consequences:

- **[corrected at CP-02]** the original text here claimed the `-9999.0`
  sentinel "is exactly what this rejects" — that is **arithmetically
  false**: `-9999.0` is finite, ≤ 0, and not `0.0`, so it passes every
  rule above. The guard must be **explicit**: any `mask == 1` logprob
  **≤ −9000.0 is a hard failure** (vLLM writes `-9999.0` both as the
  missing-logprob field default and as its clamp floor — verified at the
  pin that upstream never value-checks it; CP-02, A-7/D2). Known FP
  surface, accepted: a genuine ultra-low logprob clamped to the floor is
  indistinguishable from missing — degenerate either way;
- NaN/±inf anywhere is a hard failure;
- a positive logprob anywhere is a hard failure;
- **[platform-conditioned at CP-10 — this bullet as written is
  superseded]** `0.0` at a `mask == 1` position is suspicious enough to
  fail — a real sampled token with probability exactly 1.0 does not occur
  in this regime. **CP-04 and CP-09 measured that it does**, on both
  stacks, as a bf16 artifact; the landed rule is an allowance (`LP6`,
  default 0.25 of `mask == 1` positions) and `0.0` restores exactly the
  behavior this bullet describes. See §[CP-10] As landed;
- **[added at CP-02, corrected at CP-05]** absent/`None` `response_logprobs`
  on a trainable trace is a hard failure. The pin's `_finalize_logprobs`
  nulls the **entire array** if any `mask == 1` slot lacks a logprob
  (`prefix_merging.py:364`). Correction: at the pin, upstream's rejection
  is **status-derived, not config-gated** — `require_trainable_logprobs`
  is only a kwarg fed from `trainable = status not in (ABORTED, FAILED)`
  (`adapter.py:120,268`; full-tree grep found no config surface), so a
  trainable trace with any `mask == 1` and missing logprobs raises
  `RolloutLogprobError` trainer-side. Our rule stays: the receiver fails
  it earlier, at the source, and on both sides of the wire;
- **[added at CP-05]** an **empty** `loss_mask` on a trace with non-empty
  `response_ids` is a hard failure. The pin's `Trace` validator skips the
  length check whenever the mask is empty (`models.py:116` —
  `if self.loss_mask and …`), so the wire contract admits an N-token trace
  with no mask; `checks.py` must never inherit that escape;
- **[added at CP-02]** trace `finish_reason` must be in the allowlist
  `{stop, tool_calls, stop_sequence, length}` — this catches **tail**
  aborts (`finish_reason == "abort"`) for free; **mid-chain** aborts are
  invisible on the wire at the pin and are guarded by carried patch P2,
  not by `checks.py` (D3);
- **[added at CP-02]** re-vendor canary: a trace whose metadata carries a
  `reasoning_loss_mask` key with `masked_tokens > 0` fails — the
  reasoning-masking code is fork-only today (D4 refuted upstream), and
  this tripwire costs one line while making its silent arrival via a
  future re-vendor loud.

Alignment note carried from the predecessor: the response arrays
(`responses`, `response_mask`, `loss_mask`, `rollout_log_probs`) are
**R-aligned** (response-length), not P+R — validation that indexes them
over the full sequence is wrong by construction.

### [CP-10] As landed, rule by rule

The section above is the specification; this is what `checks.py` now
implements, with the finding id each rule emits. All of it runs inside
`run_trace_checks`, so both legs of law 6 get the identical rules.

| id | rule | threshold / source |
|---|---|---|
| `LP1:response_logprobs_absent` | null/absent array on a trainable trace | trainable = any `mask == 1` (also fires on non-empty `response_ids` with an empty mask) |
| `LP2:response_logprobs_length_ne_response_ids` | length ≠ `len(response_ids)` | the spec says "shorter"; ≠ subsumes it and catches the longer case the pin's validator would also reject |
| `LP3:sentinel_logprob_at_mask1` | logprob ≤ `sentinel_threshold` at `mask == 1` | **−9000.0**, `CheckPolicy.sentinel_threshold` |
| `LP4:nonfinite_logprob` | NaN/±inf **anywhere**, or a non-numeric value | Python's `json` accepts `NaN`/`Infinity` literals, so the wire really can carry them |
| `LP5:positive_logprob` | value > 0 **anywhere** | — |
| `LP6:zero_logprob_rate_at_mask1` | exact-`0.0` share of `mask == 1` positions above the allowance | **0.25**, `CheckPolicy.zero_at_mask1_max_rate` — platform-conditioned, see below |
| `LP7:empty_loss_mask` | empty mask with non-empty `response_ids` | the `models.py:116` validator escape |
| `LP8:loss_mask_length_ne_response_ids` | mask length ≠ `len(response_ids)` | — |
| `LP9:loss_mask_value_not_binary` | any mask entry that is not int `0`/`1` (bools excluded) | **the rule every other mask-keyed rule depends on** — see below |
| `TR1:finish_reason_not_allowed` | `finish_reason` ∉ `{stop, tool_calls, stop_sequence, length}` | tail aborts |
| `TR2:reasoning_loss_mask_masked_tokens` | metadata `reasoning_loss_mask.masked_tokens` is anything but a recognized zero | the re-vendor canary — deliberately NOT type-narrowed |

**`LP9` is not decoration; it closes a fail-open the CP-10 adversarial
pass found in the first implementation.** Every other mask-keyed rule
tests `flag == 1`, which is `False` for `"1"`, `2`, `1.0`-as-string and
JSON `NaN`. So a mask whose entries were stringified by a serializer bug
(or a hostile payload on either wire leg) made `LP1`, `LP3` and `LP6`
simultaneously vacuous — a trace with null logprobs, or an array of pure
`-9999.0` sentinels, was ACCEPTED on both legs of law 6, with `LP7` and
`LP8` blind to it because the mask was neither empty nor mis-sized. The
mask is 0/1 ints or it is not evidence. The same reasoning explains why
`TR2` no longer type-checks its value: a canary for an unknown future
upstream change must not assume the encoding that change will use (a
`masked_tokens` of `3.0` or `"3"` used to pass silently).

**The suspicious-zero rule is platform-conditioned, not inherited and not
dropped** (row 27 resolves). It is an *allowance*, `CheckPolicy.
zero_at_mask1_max_rate`, defaulting to **0.25** of `mask == 1` positions.
The numbers behind that default, both from CP-09 and both on
otherwise-discipline-clean traces: the predecessor's golden 20/292
(6.8%) and Polar's collected 15/363 (4.1%), measured to be **bf16
rounding of genuinely-near-zero RAW logprobs** (the raw replay hypothesis
fits at the platform numerics floor; the sampling-renormalized hypothesis
fits ~6× worse). 0.25 is ~3.6× the higher measurement: no measured trace
trips it, a degenerate mostly-zero array still does. A CUDA estate that
wants the original strictness sets it to `0.0` — the rule then fires on
any single `0.0` at `mask == 1`, exactly as first specced. The mechanism
is a knob rather than an engine sniff because the trace carries no
engine identity (row 22: sampling and engine provenance are ESTATE
provenance, not trace provenance).

Two consequences of RAW semantics, recorded so no later rule re-derives
them: no renormalization transform appears anywhere in the discipline
math, and a trainer consuming `response_logprobs` as behavior-policy
values is consuming raw model logprobs (plus, at turn ≥ 2, the
4-token-per-prior-turn context approximation of F2).

### [CP-11] The CheckPolicy operator surface

"A CUDA estate sets it to `0.0`" now has a mechanism. The one YAML gains
a `checks:` section (`config.ChecksConfig`) that mirrors `CheckPolicy`
field-for-field, with defaults **read from `CheckPolicy` itself** so the
two can never drift. The threading is deliberate and worth recording,
because the obvious route was unavailable: both law-6 call sites
(`receiver.ingest`, `client.partition_session_results`) call
`validate_session_result(result)` with the default policy, and both files
were frozen at CP-11 — so `load_config` **rebinds
`checks.DEFAULT_POLICY`** from the section, and the checks entry points
resolve their `policy=None` default **at call time**, not at def time
(the one-line seam change in `checks.py`; rules untouched). Consequences,
stated plainly: an explicitly passed policy always wins; the last
`load_config` in a process wins (one YAML per process is the design —
ADR-0008 §1); and a library consumer that never loads a config gets the
spec defaults. ADR-0010 records the decision and its alternatives.
Proven end to end in `tests/test_config.py`: loading a YAML with
`zero_at_mask1_max_rate: 0.0` makes the frozen call shape reject the
CP-07 trace with `LP6:…:27/441>0.0`.

### Replay: deliberately NOT implemented (CP-10 decision)

No replay-style rule lives in `checks.py`, and the reasons are recorded
here so a later CP re-opens the decision with evidence rather than
appetite:

1. it needs an engine — `checks.py` runs receiver-side and trainer-side,
   neither of which has one;
2. **it cannot run at all on Mac estates** (F3): vllm-metal hardcodes
   `prompt_logprobs_dict={}` (`vllm_metal/v1/model_runner.py:2235`) and
   the `/v1/completions` `echo` path 500s;
3. **its tolerance anchor does not transfer** (F4): the 0.005/0.05 bounds
   are the predecessor's same-engine CP-18 measurement, while the
   beside-the-engine floor measured at CP-09 is mean 0.007–0.016 on BOTH
   stacks symmetrically;
4. **on a multi-turn trace the check itself could be wrong** (F2): it
   must first de-stitch the ADR-0007 generation-prompt glue, and the
   de-stitch identity is *session-specific, not structural* — the merged
   stream keeps prior turns' RAW sampled ids while the wire prompt
   carries the canonical re-render. They coincided on the CP-09 session
   (6554/6554 tokens, verified) but the vendored builder's own header
   warns they can diverge, and the raw wire body is not persisted at the
   pin (row 7).

If one is ever built, the binding rules are: de-stitch via the
config-pinned `generation_prompt_glue_ids` before teacher-forcing
anything; re-render and calibrate rather than assume the identity; and
prefer **capture-vs-capture on identical contexts** (CP-09: mean |Δ| =
0.000114), which is the sharpest instrument this platform admits and
needs no tolerance re-anchoring.

## G7's chain snapshot

G7 is not a static config check. Beyond the settings hash and
`compaction.enabled == false`, the predecessor demanded a gateway-side
chain snapshot of **exactly**:

- 1 active chain,
- 0 rollbacks,
- 0 dropped trainable tokens,
- 1 finalized trajectory.

Polar's capture layer must surface an equivalent snapshot **or G7 fails
closed** (gap row 15). **CP-02 verified both halves of this**: the pin's
`prefix_merging` emits `reconstruction_stats` (chains_total,
chains_reconstructed_full/truncated, completions_total/merged) into
trajectory metadata, so the snapshot is readable receiver-side with zero
vendored patching — but the abort→ERROR defect (D3) is **confirmed**: at
the pin a mid-chain abort merges cleanly and DOES present a clean
snapshot, so G7 alone cannot see it. The guard is carried patch P2
(abort → session `status=ERROR`); `checks.py` adds the `finish_reason`
allowlist (logprob-discipline section) as defense-in-depth for tail
aborts. Note also: silent chain truncation at the pin still returns
COMPLETED — G7 must fail on `chains_reconstructed_truncated > 0`, not
just on chain counts.

**[tightened at CP-05]** The receiver-side G7 stats rule is the
conjunction, never a subset:

```
chains_total == 1
∧ chains_reconstructed_truncated == 0
∧ completions_merged == completions_total
∧ raw_completions_total == completions_total     # A-12 at CP-06: no auxiliary
                                                 # calls observed on the spike
                                                 # episode — AND P1 is inert
                                                 # against pi, so this equality
                                                 # is the only receiver-side
                                                 # signal there were no drops
```

`completions_merged == completions_total` is what catches **filter
amputation**: P1's filter runs *before* grouping, so a chain whose tail
completions were dropped still counts `chains_reconstructed_full` — the
`kept == len(chain)` test runs against the post-filter chain
(`prefix_merging.py:261-262`) and the first two conditions are blind to
it. The fourth condition makes any filter drop loud; under A-12 a pi
episode has no legitimate drops, so `completion_filter.excluded` must be
empty.

## The silent-degradation catalogue (CP-05 source audit)

The exact conditions under which the pin produces a degenerate trace that
LOOKS clean — every one of these ends `status=COMPLETED` with plausible
stats. This is the class our checks exist to catch. All confirmed in code
and adversarially re-verified; citations are into `vendor/polar/`.

| # | condition | mechanism | looks like | caught by |
|---|---|---|---|---|
| S1 | no engine token ids (the CP-03 live case) | empty `prompt_ids` ⇒ `0 < n` fails (`prefix_merging.py:399`) ⇒ every completion its own chain, each counted `chains_reconstructed_full` | N clean length-1 chains, `truncated == 0` | `chains_total == 1` |
| S2 | merge break: EOT unknown (no natural-stop completion in the chain — e.g. every turn `length`) or EOT absent from a canonical tail | `_slice_interstitial` → None (`prefix_merging.py:326-331`) → `break` (`:230-239`) → tail completions dropped | `chains_reconstructed_truncated ≥ 1`, still COMPLETED | `truncated == 0` |
| S3 | retry/resample with an identical prompt | equal tip passes the prefix test, canonical tail is empty, `.index` raises → break (`:328-331`) — retry and everything after it dropped, first attempt trained | one truncated chain | `truncated == 0`; builder-subclass duplicate-prompt check |
| S4 | context compaction / harness edits earlier messages | prompt no longer extends the tip → fresh chain (`:123-127`) | 2+ clean "full" chains | `chains_total == 1` |
| S4′ | **generation-prompt-only template glue** (CP-07, measured): the served chat template appends glue to each *generation* prompt but omits it from the *history* re-render (Qwen3 `enable_thinking: false` → empty think block `[151667, 271, 151668, 271]`), so consecutive prompts are never token-prefix-stable | same mechanism as S4 (`:123-127`), but on EVERY multi-turn episode, not just on compaction | 2+ clean "full" chains, `chains_total == N turns` | **repaired, not just detected**: the `ValidatingPrefixMergingBuilder` stitches the glue out of the grouping input before delegating (config `generation_prompt_glue_ids`, A-21/ADR-0007, strict-extension only); the receiver's `chains_total == 1` is the backstop if the ids are unpinned or mis-pinned (fails closed to split chains) |
| S5 | **EOT misdetected** (auto-detect adopted the last token of a stop-parameter/stop-sequence finish, which is arbitrary) | `_resolve_eot_id` trusts the first natural-stop completion (`:293-302`); `.index(wrong_id)` then mis-splits every tail — assistant-body fragments duplicated into the stream as mask-0 tokens, or real interstitial swallowed | full clean chain, correct stats | **prevention only**: A-15 — explicit `end_of_turn_token_id` in builder config, subclass rejects when unset |
| S6 | a mid-chain completion with EMPTY `response_ids` (partial capture) | `prev_raw_response == []` → `canonical_tail[k:]` (`:332-334`) drops the canonical assistant body before the first EOT — a token gap vs what the engine saw; no stat records it | full clean chain | builder-subclass per-completion `response_ids` non-empty |
| S7 | harness discards a truncated reply and re-prompts (`finish_reason=="length"` mid-chain) | prefix check passes; the first EOT in the tail closes the *new user message*, so its content is dropped while the discarded raw body stays at `mask==1` — trains on thrown-away tokens, omits real context (`:212-239,326-334`) | full clean chain | builder-subclass rule: mid-chain `finish_reason=="length"` is a hard failure |
| S8 | `n > 1` sampling, or a harness continuing from `choices[j>0]` | only `choices[0]` is ever read (`record_utils.py:131-134`); other choices vanish; a continue-from-`j>0` merges choice 0's body at `mask==1` against conditioning the model never had | full clean chain | builder-subclass: `len(choices) == 1` per completion |
| S9 | mixed policy versions merged into one chain | `_chain_metadata` presents the FIRST completion's metadata as the chain's (`prefix_merging.py:371-375`), no homogeneity check; the storage comment's "cross-version fallback" does not exist in the vendored builder | single-version-looking trace | receiver + subclass: all `completion_metadata[*].policy_version` equal (P3; A-13 until versions are declared) |

Two standing consequences:

- **G6 must decode token ids, never `response_messages`.** The
  message-level record can silently desync from the token stream: `msg_acc`
  bookkeeping is count-only (`prefix_merging.py:197-198,246-254`), so a
  harness/transformer that splits or merges messages shifts the slice while
  the token stream stays correct. `response_messages` is advisory,
  forensic-only; every gate that reads "decoded turns" decodes
  `response_ids` spans at `loss_mask` transitions.
- **Where checks live (the CP-05 registry-seam recommendation): both.**
  A `PrefixMergingBuilder` subclass in `gsj_rollout` (selected by
  `builder.strategy = "gsj_rollout.<module>:<Class>"`, zero vendored
  patches) runs the *session-level* checks that the callback payload
  cannot carry (per-completion token presence, choices arity, roster
  stability, per-turn version homogeneity, filter-drop review, EOT config
  present) and REJECTS via `status=ERROR` — the node only escalates,
  never clears (`node.py:579-624`). The receiver runs `checks.py` on the
  POSTed body (trace-level gates, logprob discipline, the G7 stats rule)
  because law 6 trusts nothing across the wire. Shared validators live in
  `checks.py`; the subclass imports them.
  **CP-07 built the subclass** (`gsj_rollout/builder.py`,
  `ValidatingPrefixMergingBuilder`): all ten subclass-only rows from the
  CP-06 sized table landed — explicit-EOT-present (`A15:`), per-completion
  `prompt_ids`/`response_ids` non-empty (`S1:`/`S6:`), `len(choices) == 1`
  (`S8:`), duplicate-consecutive-prompt (`S3:`), mid-chain
  `finish_reason == "length"` (`S7:`), roster stability (`R11:`), per-turn
  `policy_version` homogeneity (`S9:`), the pi agent-shape check replacing
  inert P1 (`A12:non_agent_shape`), and `completion_filter.excluded == []`
  (`A12:completion_filter_excluded_nonempty`). Findings are byte-stable
  `{id}:{slug}[:detail]` strings on
  `trajectory.metadata["gsj_validation"].findings`; any non-empty list
  flips the trajectory to `status="ERROR"`. **None had to move to the
  receiver** — every check found what it needed on the `CompletionSession`.
  The subclass also carries the ADR-0007 glue stitch (a merge repair, not
  a check). The receiver's list is unchanged: the G7 conjunction, logprob
  discipline, and gates G1–G7 stay `checks.py`'s job at CP-10/CP-11 —
  duplicating them in the subclass now would guarantee drift.
  **CP-08 fixed the seam** (rules untouched, per the STOP wall): one
  entry point, `checks.validate_session_result(session_result) ->
  list[str]` (byte-stable `{id}:{slug}[:detail]` findings, empty =
  accepted, never raises on content), called by BOTH the receiver
  (`receiver.ingest`) and the client (`client.partition_session_results`)
  — law 6's two legs on the same code. It composes an **admission**
  layer, live now, that only honors what the builder already decided
  (`ADM1:status_not_completed`, `ADM2:builder_findings_present` + the
  builder's own findings re-emitted, `ADM3:trajectory_missing`,
  `ADM4:no_traces`, `ADM5:malformed_trace`) with
  `run_trace_checks(trace)`, the stub every rule
  in this document lands in at CP-10/CP-11 — it returns no findings
  unconditionally today.

## The pi 0.83.0 wire dialect (CP-06, measured)

The facts the checks key on, captured live (`spike/captures/*.jsonl`,
artifacts in `docs/polar/pi/`); every one was identical across the direct
run and the through-Polar run:

- **`stream: true` on every request, always** — pi-ai's openai-completions
  client streams unconditionally, with `stream_options:
  {"include_usage": true}`. Consequences: (a) **P1 is inert against pi**
  (the `key in request` membership test at `record_filters.py:108` is
  defeated by every pi call, auxiliary or not — verified by executing the
  filter against captured bodies, `spike/p1_verdict.py`); the
  agent-shape defense moves to the builder subclass; (b) the gateway
  answers pi with its synthetic single-chunk SSE
  (`gateway/server.py:736,771-810`) while the engine-side wire is always
  `stream: false` — pi 0.83.0 parses the single-chunk form correctly;
  (c) a persisted `transformed_request` may carry `stream: true` while
  the wire sent `false` — never key a check on the persisted `stream`
  value.
- **Request keys, agent turns** (both forms): `model`, `messages`,
  `tools`, `stream`, `stream_options`, `store` (false — bare key present),
  `max_completion_tokens` (from models.json `maxTokens`; the field NAME
  follows `compat.maxTokensField` — unset here, so the 0.83.0 default
  `max_completion_tokens`), `chat_template_kwargs: {"enable_thinking":
  false, "preserve_thinking": true}` (the `thinkingFormat:
  "qwen-chat-template"` + `--thinking off` path; `preserve_thinking` is
  new relative to the predecessor's record). **Never present**: `n`,
  `stop`, `temperature`, `top_p`, `context_management`, `thinking`,
  `output_config` — so `len(choices) == 1` holds and S5's stop-parameter
  hazard is dormant on today's pi (A-15 stays pinned regardless).
- **Message shapes**: exactly one `system` message, top of list, plain
  string (so the gateway's system-fold is a no-op); `user` content is a
  content-part list (`[{"type":"text","text":...}]` — G2/G6 code must
  flatten); `tool` results may be plain strings; the assistant echo is
  verbatim (`content: null` + OpenAI `tool_calls`, `arguments` string
  byte-preserved) — which is exactly why the token-prefix test holds
  across pi turns.
- **Roster**: the `--tools` allowlist renders 1:1 into the wire `tools`
  array (7 requested → 7 sent), byte-identical across
  `original_request` == `transformed_request` == engine wire (G3's input
  — gap rows 11/31).
- **Session-key binding is load-bearing**: capture attribution is the
  `Authorization: Bearer` key == Polar session id. The harness MUST
  substitute `$OPENAI_API_KEY` into pi's `models.json` `apiKey`; a static
  apiKey fragments capture into per-request orphan sessions (the real
  session then builds with zero completions → builder ERROR "no trainable
  completions" — loud, but the episode is lost). CP-07 inherits this as a
  harness requirement.

## The H-41 lesson (why loud failure is load-bearing)

In the predecessor, sglang was silently load-bearing for tool-call
parsing: its *absence* produced *gates-green but tool-free* episodes,
measured live (H-41). The lesson for `checks.py`: **validation must fail
loudly when the tool-parser stack is incomplete** — plausible-looking
degenerate traces are the enemy. Concretely: a trace whose roster (G3)
says tools were offered but which contains zero parsed tool calls is a
red flag, and the environment guard (the predecessor's `driver_factory`
refuses a parser-less env) must have an equivalent on the Polar side —
absence of a parser must be an error, never a silent no-tools episode.
**CP-07 measured the Polar-side equivalent, from the engine side**: pi
sends `tool_choice: auto`, and vLLM/vllm-metal answer HTTP 400 —
`"auto" tool choice requires --enable-auto-tool-choice and
--tool-call-parser to be set` — unless the engine is served with
`--enable-auto-tool-choice --tool-call-parser hermes`. The first CP-07
submit ERRORed "no completions" (loud, per design) until the engine was
restarted with those flags. This is the H-41 dependency from the vLLM
side: a tool-parser-less engine yields zero completions, not a silent
no-tools episode — so CP-09's engine bring-up must pin those serve flags,
and `checks.py`'s "roster offered but zero tool calls" red flag stays the
receiver-side backstop. **CP-09 adds a second mandatory engine pin, and
this one fails SILENT, not loud**: pi sends no sampling parameters, so the
engine's request defaults ARE the sampling — and the served
`mlx-community/Qwen3-0.6B-bf16` snapshot ships **no
`generation_config.json`**, so under vLLM's default `--generation-config
auto` the diff-sampling-params set is empty and every pi request samples
at vLLM neutral defaults (`temperature 1.0, top_p 1.0, no top_k` —
`vllm/config/model.py:1502-1555`). The CP-07 episode was collected this
way and NOTHING flagged it: the trace carries no sampling evidence, the
wire is not persisted (gap row 7), and every gate stays green — the exact
clean-presenting class this document exists for. The bring-up rule:
serve with an explicit generation-config pin (CP-09:
`--generation-config <dir>` holding the codec snapshot's
`generation_config.json`, sha256 `2325da0f…`), confirm the engine's
startup override warning, and keep `--enable-log-requests` so the applied
`SamplingParams` per request are auditable engine-side. No trace-side
check can catch this at the pin.

## CP-09 fidelity findings (what replay-style validation must know)

The CP-09 comparison (`docs/reports/CP-09.md`, verdict PASS WITH
FINDINGS) surfaced three facts any future logprob-validation rule or
replay harness must respect:

1. **Captured `response_logprobs` are RAW model logprobs**, not
   sampling-renormalized values: teacher-forced replay under the raw
   hypothesis fits at the platform numerics floor while the
   temperature/top-k/top-p-renormalized hypothesis fits ~6× worse, on
   both the golden and the Polar trace. The row-27 exact-`0.0`s are
   near-delta raw logprobs rounded by bf16, present on both stacks
   (20/292 golden, 15/363 collected).
2. **Turn≥2 logprobs are conditioned on the WIRE context, not the merged
   stream.** The S4′ repair (ADR-0007) stitches the generation-prompt
   glue into the merged stream so grouping holds, but the engine's actual
   turn≥2 prefill never contained the prior turns' glue (pi's history
   re-render omits it). A replay that teacher-forces the merged stream
   therefore reports phantom drift at turn≥2 (measured: mean |Δ| 0.0676
   against the stream context vs 0.0133 against the reconstructed wire
   context — `prompt_ids[:-len(glue)] + response_ids[:span_start]`). Any
   replay check must de-stitch using the config-pinned
   `generation_prompt_glue_ids`; the predecessor's token-in dialect has
   no analogue (its wire context IS the stream). Trainers consuming
   `response_logprobs` as behavior-policy values inherit the same
   4-token-per-turn context approximation. **Caveat (CP-09 verification):
   the de-stitch identity is session-specific, not structural** — the
   merged stream keeps prior turns' RAW sampled ids while the wire prompt
   carries the canonical re-render; they retokenized identically on the
   CP-09 session (verified by exact re-render, 6554/6554 tokens), but the
   vendored builder's own header warns they can diverge, and the raw wire
   body is not persisted at the pin (gap row 7) — a replay harness must
   re-render and calibrate, not assume.
3. **vllm-metal cannot teacher-force at all**: the plugin hardcodes
   `prompt_logprobs_dict={}` (`vllm_metal/v1/model_runner.py:2235`) and
   the `/v1/completions` `echo` path 500s (`KeyError` in
   `_create_completion_logprobs` because the prompt-logprob dicts never
   include the actual token). Replay validation on Mac estates runs
   beside the engine (CP-09: mlx_lm forward over the served snapshot,
   same mlx version); the H200 pair replays through vLLM proper. The
   contract's tolerance anchor (mean 0.005 / per-position 0.05, from the
   predecessor's same-engine CP-18 measurement) does NOT transfer to a
   beside-the-engine replay — CP-09 measured the cross-implementation
   floor at mean ≈ 0.007–0.016 on both stacks symmetrically; the sharper
   instrument is capture-vs-capture on identical contexts (CP-09: mean
   |Δ| = 0.000114), which needs no tolerance re-anchoring.

## G3's actual mechanism (stricter than a config field)

G3 hashes the tools array **as sent on the wire** — `tools_wire`, captured
from the request pi actually made, canonical JSON. It does *not* hash the
`tools_allowlist` config field: matching the pin requires reproducing the
key order, whitespace-free canonical encoding, and schema shape of the
wire encoding (the SDK generates tool schemas from the declarations in
`mcp-service/gsj_mcp_service/tools.py`; the `mcp==2.0.0` pin is part of
the G3 surface — bumping it risks schema-serialization drift and a re-pin
walk). Two register consequences: gap row 11 (wire-roster capture must
exist under Polar's proxy) and gap row 31 (the roster must stay a pinned
config field rendered to the wire, or G3 has no pinned input).

## G5's transcript backstop

The structural clamp is server-side (`mcp-service`: filter to `page ≤ T`
**then** rank, T from verified token claims only). The trace-side backstop
parses the transcript's tool-result texts with two regexes — the
compatibility contract every backend and `checks.py` share:

```
"page"\s*:\s*(\d+)          # the "page" member of a search_case hit
md/page_(\d{4})\.md         # the file path of a hit
```

(the predecessor's `gates.extract_case_search_pages`, inlined at CP-01
into `mcp-service/tests/helpers.py`; `checks.py` reimplements it at
CP-11). A backend that renames the key or reformats the path blinds the
gate — `mcp-service/README.md` §Compatibility requirements is binding. If
the page census is unreconstructable from what Polar captures, that is an
abandonment trigger (§9).

**[CP-10] Landed, one CP earlier than planned** (`checks.check_page_cutoff`),
and the abandonment trigger is not touched — the census IS reconstructable
from what Polar captures. Mechanics as built:

- **Inputs**: the trace's `prompt_messages` + `response_messages`, scanned
  in order. Tool names ride the assistant turn's
  `tool_calls[].function.name`; results carry only `tool_call_id`, so the
  name is resolved by id. Content is flattened through the finding-(b)
  normalizer before matching (below).
- **Filter**: `mcp_gsj_search_case` results only. Decisions results are
  cutoff-exempt (the predecessor's ADR-0007(e)), and a built-in `read` of
  `md/page_0007.md` cites the *checkout*, which the `timestep-{T}` branch
  already clamps — both are measured live on the fixtures: the CP-07
  episode's `read` results cite `md/page_0007.md` and correctly
  contribute nothing.
- **T comes from the trace, never from a caller.** Precedence:
  `metadata.timestep`, then `metadata.task_metadata.timestep`, then the
  `mcp_gsj_case_status` result's own `"timestep"` — which the service
  states from the same verified token claims that drive the clamp.
  Neither source ⇒ `G5:missing_evidence:timestep`, fail-closed.
- **Findings**: `G5:search_page_gt_timestep:{page}>{T}` (the
  predecessor's constant, detail included) and
  `G5:missing_evidence:timestep`.
- **What did NOT land, and why**: the predecessor's other two G5 clauses
  — max checkout page == T, checkout pages contiguous from 1 — need the
  *checkout* census, which is a property of the sandbox filesystem and
  appears nowhere in the trace. They are not reconstructable receiver-side
  at all; the enforcement they backstopped is the `timestep-{T}` branch
  clone itself (CP-07, live). Recorded rather than faked.
- **The known weakness — RESOLVED at CP-11, the structural timestep.**
  `config.render_task_request` now puts `{case_id, timestep}` into
  `TaskRequest.metadata`, and the leg was verified hop-by-hop against the
  vendored code (executed, not read): the manager copies it verbatim into
  the dispatch (`pipeline.py:189`), the gateway proxy stamps it onto every
  completion record (`server.py:371-377` — this is also where
  `session_id`/`task_id` are `setdefault`-added, which is why the CP-09
  bodies carried exactly those two keys), and the builder hoists the first
  completion's metadata to the **top level of each trace's metadata**
  (`prefix_merging.py:371-375`) — precisely the `metadata.timestep` the
  check reads FIRST. So the `case_status` fallback is now a redundancy,
  kept (it covers traces predating the change, e.g. every dumped fixture),
  and the fail-closed posture is unchanged. Reserved-key constraint,
  binding on anything ever added to task metadata: `session_id`/`task_id`
  are setdefault-shadowed by ours, `evaluation` is clobbered by the eval
  merge (`node.py:737`), `policy_version` collides with the version stamp
  (`storage.py:152`) — never use them. Note `TaskRequest` is pydantic
  `extra="ignore"`: a typo'd top-level key is silently dropped, so the
  golden-file test is the guard that the `metadata` key stays spelled
  right. Residual circularity: none for post-CP-11 episodes; a service
  misreporting T only matters for fixture-era traces that lack metadata.
- **The census's known blind spots**, enumerated so a shape change is
  recognized rather than rediscovered: the two regexes are quote-anchored
  and decimal (`"page": "18"` as a string does not match — the binding
  compatibility contract, `mcp-service/README.md`); a tool result whose
  `tool_call_id` resolves to no scanned call is dropped from the census
  (its pages go uncounted) while T may still resolve; and duplicate
  `tool_call_id`s resolve last-write-wins, so a search call shadowed by a
  same-id exempt call disappears. Content-envelope blindness was the
  fourth and is fixed: `_content_text` now accepts typed parts, a bare
  part mapping, and plain-string list items.

## [CP-10] The template findings that bind the gates

From the template investigation (the same session that produced the
ADR-0007 amendment). Two of the three findings are binding on `checks.py`.

**Finding (a) — G4's blind spot.** G4 as specced pins the *codec*
snapshot's chat template (`Qwen/Qwen3-0.6B` @ `c1899de…`, template sha256
`a55ee1b1…`), but the engine serves and renders with the *served*
snapshot's (`mlx-community/Qwen3-0.6B-bf16` @ `42096995…`, template sha256
`87a2728c…`). **The two are different files** — 4168 vs 4116 chars — and
the gate as specced would pass while never having measured the artifact
that actually built the prompt. Harmless today and measured to be so: the
differences are confined to `content`/`reasoning_content` type guards, the
`add_generation_prompt` tail is byte-identical, and both render
byte-identically on pi's normalized message shapes. **The binding rule:
G4's chat-template input is the template the engine actually renders
with.** Where both snapshots are in play, the gate needs both hashes in
its approved set, or an explicit statement of which one it pins and why.
CP-04′'s template flip fixes this incidentally — adopting a template via
`--chat-template <file>` makes the served template an explicit pinned
file with a hash of its own.

**Finding (b) — the silent one, and the only one that changed code this
CP.** Both templates coerce a non-string `content` to `''` (codec:
`{%- if message.content is string %}…{%- else %}{%- set content = '' %}`).
pi sends `user` content as a content-part list. So an **offline re-render**
of a message log through the pinned template silently produces *empty
user turns* — a prompt that never existed, hashed and compared as though
it did. Live serving is safe (vLLM flattens content parts before
templating), which is exactly why this would never surface in an episode.
**The binding rule: any check that re-renders prompts from message logs,
or reads message content at all, normalizes content parts first.**
Landed as `checks._content_text`, used by the G5 census; G2/G6 at CP-11
inherit it.

**Finding (c)** is an assumption, not a check: thinking-ON is a strictly
worse regime for the stitch (A-22 in the charter) — the history render
strips *variable-length* reasoning per turn, so a fixed-ids stitch cannot
repair it and the receiver rejects, loudly. No `checks.py` consequence
beyond that guarantee of loudness.

## CP-11's inherited list

What this CP touched and deliberately left, so CP-11 starts from evidence:

1. **Gates G1–G4, G6, G7** and the G7 stats conjunction — untouched by
   the STOP wall, fully specified above.
2. **G5's structural timestep**: put the episode timestep into
   `TaskRequest.metadata` in `config.py:render_task_request` so it rides
   into trace metadata; then the `case_status` fallback becomes a
   redundancy rather than the only source.
3. **G5's checkout-census clauses** (max page == T, contiguity):
   unreconstructable from the trace — either drop them with a note or
   source them from a sandbox-side probe the harness records.
4. **The H-41 red flag** ("roster offered but zero tool calls") — named
   in this document, not yet a rule.
5. **The pins walk**: no approved sets exist in this repo yet (row 23),
   so every hash-based gate needs derive → re-pin → first-episode-validate
   before it can be turned on.
6. **The size budget**: `checks.py` is at 367 lines against its 150–250
   charter allowance, and `gsj_rollout/` totals 1480/1500. Six gates and
   four hashing conventions do not fit in 20 lines — CP-11 must either
   move the reasoning wholesale into this document and leave one-line
   pointers in code, or raise the per-module allowance in an ADR.
7. **`CheckPolicy` has no operator surface.** `receiver.ingest` and
   `client.partition_session_results` call `validate_session_result` with
   the defaults, and `config.py` (frozen this CP) has no policy section —
   so this document's "a CUDA estate sets it to `0.0`" currently has no
   mechanism. Wire it to the one YAML, or the H200 estate silently
   inherits Mac-calibrated thresholds.
8. **`mcp-service/README.md` §Compatibility still says `checks.py`
   reimplements the G5 regexes "at CP-11"** — they landed at CP-10. The
   component was frozen this CP; the one-line correction rides the next
   freeze-lift, and until then an auditor reading from the service side
   is told a live gate does not exist yet.
9. **The `--depth 1` clone** (see the cutoff note below) — the fix is in
   `pi_harness.py`, frozen this CP.

**[CP-11] Disposition.** Items 2 (the structural timestep), 5 (the pins
walk — derive and re-pin legs), 6 (the budget: prose migrated here,
`checks.py` 367 → 285; ADR-0009 raises its allowance), 7 (the
`CheckPolicy` operator surface, ADR-0010) and 9 (the `--depth 1` clone,
plus the reflog scrub the verification forced) landed this CP. Item 3
(G5's checkout-census clauses) is **decided: dropped with a note** (gap
row 13 carries the reasoning). Still open for CP-11b: item 1 (gates
G1–G4/G6/G7 + the G7 stats conjunction — G3/G7/G1/G2 now have approved
sets and are landable; G4 has its sets but needs a decision on where the
receiver gets codec evidence; G6 has its tail but needs the decode-side
tokenizer question answered), item 4 (the H-41 red flag), item 8 (the
`mcp-service/README.md` correction — the component stayed frozen again),
and the pins walk's `first-episode-validate` leg.

## [CP-10] A cutoff hole that no trace-side check can see

Found while adversarially verifying G5, verified end to end, and recorded
here because it is exactly the class §7 of `CLAUDE.md` calls a deliverable:
**the page cutoff is bypassable inside the sandbox through git history,
and neither the server-side clamp nor G5's backstop can see it.**

The mechanism, each step verified: `corpus/ingest_corpus.py:601-612` builds
every `timestep-{T}` branch as ONE truncation commit on top of `main`'s
full-document commit, so the branch tip's parent contains every page;
`pi_harness.py:127` clones `--branch timestep-{T} --single-branch` with no
`--depth`, so that parent commit and all its blobs land in
`/workspace/.git`; and `bash` is on the measured wire roster (both
fixtures: `[read, ls, grep, find, write, edit, bash, mcp_gsj_*]`).
Reproduced with the exact recipe and clone flags: with the worktree
showing pages 1–2 at T=2, `git show HEAD~1:md/page_0003.md` returns the
future page, offline, with no MCP call involved. `git log` alone leaks the
document's total page count via the commit subject.

Attribution and severity, stated honestly:

- **It is inherited, not introduced.** The predecessor clones the WHOLE
  repository (`task.py:826-839`, `git clone -q <url>`, no `--branch`, no
  `--depth`) and then pins the worktree to `origin/timestep-{T}` — so its
  sandbox contains every branch including `main`. Ours is strictly
  narrower. Row 2's PARITY claim survives; §5's "nothing past page T
  visible through any channel" does not, on either stack.
- **No trace-side check can catch it**, by construction: the leak flows
  through `bash` output, not through an `mcp_gsj_*` result, so the census
  is blind to it by the same scoping decision that makes the decisions
  exemption correct. G5 is not the wrong shape; this is simply not G5's
  channel.
- **The fix is one flag**, at the next `pi_harness.py` freeze-lift:
  `--depth 1` on the clone (plus dropping the `origin` remote, since the
  clone URL is reachable and credentialed from inside the sandbox). Cheap,
  and it closes the channel at the source rather than trying to detect it
  downstream.

**[CP-11] Closed, verified, and one finding the fix itself produced.**
The clone step is now `git clone --depth 1 --branch timestep-{T}
--single-branch <url> <workdir> && git -C <workdir> remote remove origin
&& rm -rf <workdir>/.git/logs`. Reproduction and cure ran in a scratch
clone of a corpus case repo built with the exact ingest recipe and the
real `case_0001` staging pages (the estate is torn down on this host —
said plainly): before, `git show HEAD~1:md/page_0018.md` returned the
post-cutoff page and `git log` leaked "full document (18 pages)"; after,
`HEAD~1` is `fatal: invalid object name`, `git log` shows the one
truncation commit, `git remote` is empty, and `git cat-file -e` proves
both main's commit and the page-18 blob are absent from the object store
— closed at the object level, not the ref level. The worktree is
byte-identical to the unshallow clone (`diff -r`), and `read`/`grep`/
`find`/`ls`/`rg` all work unchanged. **The finding: dropping the remote
does NOT deny re-fetch by itself** — `.git/logs/HEAD` retains `clone:
from <url>` (measured), which is why the reflog scrub is part of the
step; after it, no URL is recoverable anywhere under `.git/`. **The
residual, named honestly**: an agent that *guesses* the Forgejo endpoint
can still re-clone over the network, because the estate as built allows
anonymous read (CP-04: "anonymous clone 4 refs/repo"). That is estate
posture, not a rollout-server property, it is shared with the
predecessor's estate, and its cure (credentialed clone URLs or egress
policy) belongs to the estate bring-up — recorded in gap row 2.

## Carried evidence inventory (`pins/`)

| file | anchors |
|---|---|
| `system_prompt.captured.txt` | G2 derivation source (CP-05 capture; embeds the predecessor's host paths — byte-load-bearing, never rewrite) |
| `container/system_prompt.container.derived.txt` | G2 docker-mode singleton (`/workspace`-constant; the text the CP-04/CP-09 golden-reference comparison needs) |
| `tools.captured.json` | G3 wire roster (11 tools) — the canonical-JSON convention's test anchor |
| `settings.rendered.json` | G7 settings text (`{compaction: {enabled: false}}`) |
| `g6_tail.captured.txt` | G6 verbatim tail (41 bytes) |
| `derive_g2.py` | the byte-substitution derivation (`--work-root` per-case mode; `--constant-path` docker-singleton mode) |
| `pins.gsj.json` | **[CP-11] the approved sets** — this repo's first valid pins, one provenance block per key (episode, artifact, host, Mac-specific flag) |
| `derive_pins.py` | **[CP-11] the reproducible walk** — re-derives every approved value from the provenance-named evidence, exits nonzero on divergence; CP-04′ reruns it (served template diverges there by design) |
