# ADR-0007 — The generation-prompt glue stitch in the builder subclass

## Context

CP-07's first real multi-turn corpus episode reconstructed as **two
chains, not one** — `chains_total == 2`, each counted "full", a clean
COMPLETED trajectory with zero merging (the S4 shape from the
silent-degradation catalogue). Root cause, measured on the wire: the Qwen3
chat template with `enable_thinking: false` appends an **empty think
block** — `<think>\n\n</think>\n\n`, token ids `[151667, 271, 151668,
271]` — to the *generation prompt* of every assistant turn, but omits it
when the same turn is later re-rendered as history for the next turn's
prompt. So consecutive pi prompts are never token-prefix-stable:
`C_{i+1}.prompt_ids` does not begin with `C_i.prompt_ids`, the vendored
grouping test `prompt_ids[:n] == tip` (`prefix_merging.py:399`) fails, and
every turn opens its own chain. The vendored builder cannot merge any
multi-turn pi episode on this template — a real defect, surfaced only by
an end-to-end episode (the CP-06 stub never exercised the template because
it tokenized bytes).

R1 candidates considered: (a) strip the glue at the harness by disabling
the empty-think emission — rejected, it changes what pi sends on the wire
and therefore G2/G6 and the golden comparison; (b) configure the vendored
`end_of_turn_token_id` differently — rejected, the break is in *grouping*,
before EOT is ever consulted; (c) a custom builder that normalizes the
grouping input. (c) is the only option that leaves pi's traffic and the
vendored builder untouched.

## Decision

`ValidatingPrefixMergingBuilder` normalizes `prompt_ids` **before**
delegating to the vendored `build()`. For each consecutive pair, when
`orig_i` ends with the configured glue ids and `orig_{i+1}` extends
`orig_i` minus that glue, it rewrites
`norm_{i+1} = norm_i + orig_{i+1}[len(orig_i) - len(glue):]` and patches
the record's captured `prompt_ids` surface. The vendored grouping then
sees prefix-stable prompts and merges the chain; the glue rides the
stream exactly once in the initial prompt and once per interstitial
(the predecessor's per-turn G6-tail shape), so no engine-sampled token is
added or dropped — only the *canonical* prompt tokenization is repaired.

Rules that keep it safe:

- **Strict extension only.** A retry with an identical prompt (S3) does
  NOT stitch — the length-strictly-greater test fails — so S3 stays a
  fresh chain plus its `S3:` finding. Any non-matching boundary (genuine
  compaction, edited history) is left untouched, preserving the vendored
  fresh-chain behavior for real S4.
- **Explicit config, fails closed.** The glue ids are a builder-config
  value (`generation_prompt_glue_ids`), derived from the served
  tokenizer the same way A-15's EOT is (`[151667, 271, 151668, 271]` =
  `<think>`,`\n\n`,`</think>`,`\n\n` for Qwen3). Unset → vendored
  behavior (split chains). A mis-pin cannot corrupt a trace silently: it
  either fails to match (no stitch, split chains) and the receiver's
  `chains_total == 1` rejects, or it over-matches and the EOT split /
  the receiver's mask discipline catches it. The builder records
  `gsj_validation.glue_stitched` (count) for auditability.

## Consequence

Multi-turn pi episodes on the Qwen3 no-think template merge to a single
chain (`chains_total == 1`, verified live: 441 sampled + 6755
interstitial tokens, logprobs aligned, `0.0` only at mask-0). The
mechanism is **template-specific, not model-specific** — any harness/
template that appends generation-prompt-only glue needs its ids pinned;
a template without the asymmetry sets nothing and gets vendored behavior.
This is the one place the subclass does more than validate, and it is
recorded here because it is a "going custom" step under R1. The
receiver's G7 conjunction still governs correctness across the wire —
the stitch makes a correct single chain *possible*; it cannot
manufacture a passing stat, because a bad stitch splits rather than
merges.

## Amendment — 2026-08-09 (CP-10): the alternatives, with prior art

Appended, not rewritten: the decision above stands. A template
investigation between CP-09 and CP-10 established that this defect is a
**known, publicly reported, multi-framework problem** with two shipped
classes of fix, which changes what we know without yet changing what we
do. Recording it so the re-decision is made on evidence.

**The prior art** (all verified at the sources named):

- **The defect is upstream Qwen's and unfixed.** `QwenLM/Qwen3#1826`
  ("Chat template breaks KV-cache reuse when `enable_thinking=false`",
  open since 2026-03-03, no maintainer response, bot-marked inactive);
  the Qwen3-0.6B template on HF main is byte-identical to our pinned
  snapshot. Qwen fixed only the Qwen3.5/3.6 line and closed the
  community's template-fix issue `not_planned`.
- **Direction A (symmetric template) is shipped by TRL.** HuggingFace TRL
  carries `qwen3_training.jinja`, which drops the
  `loop.index0 > ns.last_query_index` conditional so the think block is
  always emitted, plus `is_chat_template_prefix_preserving` and
  `get_training_chat_template` to detect and patch non-prefix-preserving
  templates — Qwen3-0.6B explicitly supported. The recommendation in the
  wild is to deploy the patched template at serving time too, for
  train/serve parity.
- **Direction C (a stitch/normalization at the trainer) is verl's
  choice.** verl documents Qwen3's strip behavior and works around it
  with delta-based tokenization against a fixed base conversation plus an
  end-of-rollout tokenization sanity check; its AgentLoop is append-only
  token-in/token-out. `verl#6854` is the same structural failure in a
  trajectory reconstructor's prefix guard (thinking-ON variant).
- **Everyone else has it open too**: `NVIDIA-NeMo/RL#2821` (incremental
  string-diff tokenization duplicating content for "reasoning chat
  templates that re-render history differently from the last turn"),
  `OpenRLHF#1080` (multi-turn SFT response ranges), and the DeepSeek-R1
  analogue in both engines — SGLang merged `--strip-thinking-cache`
  (#23315), the equivalent vLLM PR is unmerged.
- **In Polar itself: nothing.** All 47 issues/PRs of
  `NVIDIA-NeMo/ProRL-Agent-Server` scanned — none touches templates,
  think blocks, or `prefix_merging`; the two known forks modify
  `prefix_merging.py` only for abort handling, `policy_version`, and
  completion filtering. The exact-prefix grouping test is untouched
  upstream, so nobody is going to fix this for us.

**The three alternatives, judged:**

| direction | what it is | verdict here, today |
|---|---|---|
| **A — symmetric served template** | serve with a patched Qwen3 template whose history branch and generation branch agree (TRL's `qwen3_training.jinja`); grouping then holds with no stitch | **the right end state, deferred to CP-04′** — it re-derives G4 and breaks golden comparability, and CP-04′ does both anyway |
| **B — strip the glue** (disable the empty-think emission) | make the generation prompt stop emitting `<think>\n\n</think>\n\n` | **refuted, with a citation.** The empty pair IS the reasoning-suppression signal: on vLLM issue #28089 a maintainer reports that without it "the LLM does not output `</think>`". Removing it changes what the model does, not just what the prompt looks like |
| **C — keep the stitch** (the landed decision) | normalize `prompt_ids` before grouping, strict-extension only | **stands for now** — zero vendored edits, zero change to pi's wire traffic, and CP-09 measured its exact cost (F2: turn ≥ 2 logprobs are conditioned on a wire context 4 tokens per prior turn away from the merged stream) |
| **D — patch Polar's grouping** | teach `_find_extendable_chain` to tolerate a configured suffix | rejected: a vendored patch to the one algorithm this repo exists to evaluate, carried forever across re-vendors, to fix a defect that is the template's |

**Why the stitch won *at this point in time*, stated plainly**: the flip
to Direction A re-derives the G4 pins and invalidates golden
comparability, and both of those costs are already paid by CP-04′ (new
estate, new pins walk, fresh golden pair on the H200). Paying them twice
to gain nothing before then is waste. The stitch's cost is known and
bounded, and it is measured rather than assumed.

**The trigger that forces the flip earlier** — one line, watch for it: a
session in which turn-1's response body does **not** retokenize
identically inside turn-2's canonical prompt. The merge still succeeds
(the stitch only compares `prompt_ids` prefixes) but the de-stitch
identity that F2's whole analysis rests on breaks, so any wire-context
reconstruction silently reports the wrong context. CP-09 verified the
identity held on its session (6554/6554 tokens) and the vendored
builder's own header warns it need not hold in general.

**A second, worse regime is out of bounds, not merely untested**:
thinking-ON. There the history render strips *variable-length* reasoning
per turn, so a fixed-ids stitch structurally cannot repair it — the
strict-extension test simply fails, chains split, and the receiver
rejects (loudly, which is the one good property). The fix there is
Direction A's general template, not a longer glue list. Recorded as
charter assumption **A-22** so nobody flips `thinking` expecting coverage.
