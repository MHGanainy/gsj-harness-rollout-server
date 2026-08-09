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
