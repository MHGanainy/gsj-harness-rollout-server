# COMPARISON.md — the CP-09 comparison contract

What CP-09 compares against the golden reference in `docs/golden/mac/`
(the H200 pair, CP-04′/CP-09′, repeats this contract verbatim against
`docs/golden/h200/`), field by field, and what counts as a match. Written
at CP-04, before any Polar trace exists, so the criteria cannot be
back-fitted to what Polar happens to produce.

## The two records being compared

| | golden (predecessor, this CP) | CP-09 (Polar) |
|---|---|---|
| producer | `gsj-envloader` 0.8.0 `collect_episodes` — uni-agent gateway codec, token-in/token-out `/v1/completions` with `return_token_ids: true`, `logprobs: 1` | vendored Polar @ `f0e8343a`+P1-P3 — pi 0.83.0 through the gateway proxy, `/v1/chat/completions`, engine-prepare adds `logprobs`/`return_token_ids` |
| token layout | `input_ids = prompts + responses`; `loss_mask`, `response_mask`, `rollout_log_probs` all **R-aligned** (response-length) | `prompt_ids` + `response_ids` separate; `loss_mask`, `response_logprobs` R-aligned |
| capture | sampling-time, from the engine response, capture-once (§2.3) | sampling-time, from the engine response, via proxy capture |

**Structural mapping** (the predecessor's `input_ids == prompts +
responses` is asserted at freeze time, so `prompts`/`responses` carry all
information):

```
golden.prompts            ==  polar.prompt_ids
golden.responses          ==  polar.response_ids
golden.loss_mask          ==  polar.loss_mask          (both R-aligned)
golden.response_mask      ==  golden.loss_mask         (identity, asserted at freeze)
golden.rollout_log_probs  ~=  polar.response_logprobs  (tolerance below)
```

## The sampling decision: the reference block, NOT greedy — and why

Greedy was the first choice (token-id equality against the same
engine+weights is the strongest possible yardstick) and it was **measured
uncollectible at CP-04**: under `temperature: 0.0` Qwen3-0.6B's first
assistant turn falls into an infinite `<tool_call>` emission loop on this
task family's rendered context — observed twice live (uncapped: >25k
tokens, ~9 min, wall-timeout; capped: exactly 8192 tokens, `length`,
zero tool executions). The loop sits in the sampling-independent part of
the context (skill instructions + tool schemas, before any case content),
so greedy retries and other task triples reproduce it. A golden collected
greedy does not exist for this model; a golden collected with `stop`
tricks would carry the S5 stop-sequence hazard into the reference itself.

**Both runs therefore sample at the predecessor's frozen reference block:
`{temperature: 0.6, top_p: 0.95, top_k: 20}`** (the golden sends it
explicitly per call; the CP-09 engine inherits the identical values from
Qwen3's own `generation_config.json` defaults on pi's parameterless
requests — CP-09 must confirm its engine applies them and record the
mechanism). The golden's driver additionally sends a per-episode `seed`
(`derive_seed(traj_id)`, recorded in provenance) — it makes the golden
re-runnable, but pi sends no seed, so **cross-stack sampled-token-id
equality is out of reach by construction and is NOT a criterion.** What
survives as token-level comparison:

1. **`prompt_ids` stay exactly comparable** — the turn-1 rendered context
   is sampling-independent (same case checkout, same system prompt
   singleton, same roster, same pinned template ⇒ same bytes ⇒ same ids).
2. **Interstitial glue stays exactly comparable** — the mask-0 spans are
   template constants given each trace's own turn contents.
3. **Logprob capture is compared by replay, not across traces** — CP-09
   teacher-forces the GOLDEN's frozen `input_ids` through the same engine
   (`prompt_logprobs`/echo) and checks the golden's `rollout_log_probs`
   against the replay within tolerance; it does the same for Polar's own
   trace. Capture is thereby validated on identical token streams even
   though the two episodes sampled different text.

## Field-by-field criteria

| field | criterion | a mismatch means |
|---|---|---|
| `prompt_ids` vs `prompts` | **exact sequence equality** (sampling-independent) | the rendered context diverged — system-prompt bytes (G2), skill-card resolution (G1), roster rendering (G3), template application (G4), or the user-message assembly. **Ours** (harness/estate config) unless the divergence is inside Polar's proxy mutating `messages`/`tools` — CP-06 measured it does not for pi 0.83.0, so start from ours. Diagnose by decoding both and diffing text before blaming token layers. |
| `response_ids` at `mask==1`, per trace | decode-fidelity: the mask-1 spans of EACH trace decode exactly to that trace's own transcript's assistant text (golden asserted at freeze; Polar checked at CP-09). Sampled ids are NOT compared across traces (see the sampling section). | decoded-vs-transcript divergence on Polar's side is retokenization — **Polar's fault** (the A-1 guarantee that assistant tokens come only from engine-sampled ids is broken, an abandonment trigger). |
| `response_ids` at `mask==0` (the interstitial glue), per trace | the glue spans are the pinned template's turn constants: each mask-0 span byte-decodes to the expected inter-turn scaffold (`<|im_end|>`, `<|im_start|>user/assistant`, the G6 empty-think tail, tool-result framing) around that trace's own turn contents; the golden's glue spans are the reference rendering | glue divergence: chat-template application differences (platform/config — e.g. `preserve_thinking`, a pi-0.83.0 novelty the predecessor's codec does not send) or EOT mis-splitting (**Polar's**, the S5 class — check `end_of_turn_token_id` was pinned per A-15 before blaming the template). |
| `loss_mask` semantics | **zero tolerance, per trace**: mask==1 exactly on engine-sampled spans, mask==0 exactly on glue; mask-span boundaries align with the trace's own turn boundaries; `loss_mask == response_mask` on the golden side (asserted at freeze) | **Polar's** `prefix_merging` mask semantics differ from the gateway codec's (1 = engine-sampled, 0 = interstitial context). This is the comparison that matters most: it decides whether Polar's traces are trainable on the same positions the predecessor's would be. No mismatch here is attributable to platform or sampling. |
| logprobs at `mask==1` | finite, ≤ 0, no exact `0.0`, no ≤ −9000 sentinel (both traces); **replay check**: teacher-force the frozen `input_ids` through the same engine and compare captured logprobs to the replay at **mean abs Δ ≤ 0.005, per-position abs Δ ≤ 0.05** (anchor: the predecessor's CP-18 measured prefill-vs-decode drift at mean abs Δ = 0.0036); positions failing the per-position bound are individually listed | within tolerance: capture-path numerics, expected. Beyond it on Polar's trace but not the golden's: **Polar's** capture/stamping. Beyond it on both: the engine drifted between runs (**platform** — batching/MLX nondeterminism; rerun to bound it). |
| logprobs at `mask==0` | exactly `0.0` on both sides | record-semantics placeholder violated — whichever side is non-zero is at fault (golden side is asserted at freeze; a Polar violation is **Polar's**). |
| `finish_reason` | ∈ {stop, tool_calls, stop_sequence} (the checks-spec allowlist minus `length` — the golden finished naturally; a `length` finish on CP-09's side means budget config diverged) | config divergence (ours) or mid-episode abort (**Polar's**, P2 territory). |
| `reconstruction_stats` (CP-09 side only) | the full G7 conjunction: `chains_total == 1 ∧ truncated == 0 ∧ merged == total ∧ raw == total` | **Polar's** stitching degraded (S1–S9); the trace is disqualified before any token comparison. |
| transcript semantics | ≥ 1 `mcp_gsj_*` execution and ≥ 1 built-in tool execution in the CP-09 transcript (the H-41 precondition, same as the golden's Step-3 assertion) | a tool-free CP-09 episode is not comparable regardless of token agreement — gates-green-tool-free is the exact artifact this reference exists to catch. |

## Comparison procedure (CP-09 runs it in this order)

1. Disqualifiers first: G7 stats conjunction, tools-executed, sampling
   confirmed (the engine applies the reference block to pi's
   parameterless requests; no unexpected sampling params on the wire).
2. `prompt_ids` vs `prompts` exact. Fail ⇒ report the first diverging
   index and the decoded windows around it, then stop — everything
   downstream is conditioned on the same rendered context.
3. `loss_mask` semantics per trace (boundaries vs turn structure,
   golden's `loss_mask == response_mask` identity). Fail ⇒ stop.
4. Per-trace decode-fidelity at `mask==1`; glue byte-decode at `mask==0`.
5. Logprob discipline both traces; the replay check at the stated
   tolerances over `mask==1`; exact-`0.0` over `mask==0`.
6. Only then: reward/artifact comparison (informational — reward is not
   part of the match criterion; the scope law keeps scoring out).

## Known asymmetries, stated in advance

- **max_tokens**: the golden's driver caps each turn at
  `min(8192, remaining trajectory capacity)` (`sampling_student.max_tokens:
  8192`, chosen to mirror pi's wire-measured `max_completion_tokens: 8192`);
  under natural `stop`/`tool_calls` finishes neither cap binds. If either
  side ever finishes `length`, fix budgets, don't compare. The cap exists
  because greedy Qwen3-0.6B can repetition-loop on some contexts (observed
  live at CP-04: an uncapped greedy turn ran past 25k tokens); it converts
  a looping attempt into a fast, honest failure.
- **The wire dialect differs by construction** (token-in `/v1/completions`
  vs messages-in `/v1/chat/completions` + server-side template). The
  contract deliberately compares *outputs* (ids/masks/logprobs), not
  requests; G2/G3/G4 pins are the guard that the *inputs* were equivalent.
- **`chat_template_kwargs`**: pi sends
  `{"enable_thinking": false, "preserve_thinking": true}`; the
  predecessor's codec renders thinking-off itself (G6 tail pinned). If
  interstitials mismatch, look here first.
- **Session-count**: the golden is one uninterrupted pi session; a CP-09
  episode fragmented by session-key misbinding (CP-06's orphan-session
  hazard) fails loudly builder-side before reaching this contract.
