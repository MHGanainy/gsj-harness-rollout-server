# checks-spec — the `checks.py` specification

Captured at CP-01, while the predecessor is fresh, so CP-10/CP-11
**implement rather than re-derive**. Normative sources: the predecessor's
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
- `0.0` at a `mask == 1` position is suspicious enough to fail — a real
  sampled token with probability exactly 1.0 does not occur in this
  regime;
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
receiver-side backstop.

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

## Carried evidence inventory (`pins/`)

| file | anchors |
|---|---|
| `system_prompt.captured.txt` | G2 derivation source (CP-05 capture; embeds the predecessor's host paths — byte-load-bearing, never rewrite) |
| `container/system_prompt.container.derived.txt` | G2 docker-mode singleton (`/workspace`-constant; the text the CP-04/CP-09 golden-reference comparison needs) |
| `tools.captured.json` | G3 wire roster (11 tools) — the canonical-JSON convention's test anchor |
| `settings.rendered.json` | G7 settings text (`{compaction: {enabled: false}}`) |
| `g6_tail.captured.txt` | G6 verbatim tail (41 bytes) |
| `derive_g2.py` | the byte-substitution derivation (`--work-root` per-case mode; `--constant-path` docker-singleton mode) |
