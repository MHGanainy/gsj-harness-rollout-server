# ADR-0024 — G6 re-pins as per-mode pins data; `harness.thinking` becomes a validated knob

Date: 2026-08-14 (CP-30). Status: accepted.

## Context

CP-28's GO committed Phase C's C-2 to two things: land the G6 re-pin so a
thinking-on estate can have episodes *accepted* (at CP-28 every one was
correctly quarantined, G6-only findings), and close the silent-clamp trap
on `harness.thinking` (pi maps any unknown `--thinking` value to `"off"`
— `clampThinkingLevel` falls back to `availableLevels[0]` — so a typo
collects a control run wearing the measurement's label, with no error).

The measured geometry that shapes the pin (CP-28, `docs/polar/thinking/`):
under the symmetric served template a thinking-off turn opening ends with
the 41-byte empty think block — ids `[151644, 77091, 198, 151667, 271,
151668, 271]` — while a thinking-on opening ends at the bare generation
prompt `<|im_start|>assistant\n` — ids `[151644, 77091, 198]`, confirmed
on all 41 real thinking-on turn openings. The 3-id tail is **not** an
`endswith`-suffix of the 7-id tail (which ends `[271, 151668, 271]`), so
a single-tail pin selected per mode keeps G6 **mode-asserting in both
directions**: an off-opening fails the on-pin and an on-opening fails the
off-pin. Only pinning *both* tails in one approved set weakens the gate.
CP-23's three recorded options were re-pin / re-conceive / retire
(spec §G6); the evidence favours re-pin, and re-pin is pins *data* —
zero `checks.py` lines, ADR-0021's 528/528 untouched.

## Decision

1. **G6 re-pins as per-mode pins data — a per-mode approved set,
   delivered as a per-mode pins FILE selected through the existing
   ADR-0017 resolver.** The repo commits
   `pins/thinking-on/pins.gsj.json`: a complete `gsj-pins/1` document
   whose six non-G6 approved sets are identical to
   `pins/pins.gsj.json`'s (CP-28 measured them unmoved by the flag —
   same engine process served both legs) and whose two G6 keys carry the
   thinking-on tail: `g6_expected_tail` = `<|im_start|>assistant\n`
   (`pins/thinking-on/g6_tail.captured.txt`, 22 bytes — the byte-prefix
   of the off tail's 41), `g6_expected_tail_ids` = `[[151644, 77091,
   198]]`. **How the mode reaches the check**: `GSJ_PINS_PATH` — the
   thinking-on estate points every process on both law-6 legs (receiver
   and trainer) at the per-mode file; default resolution (checkout →
   packaged copy) keeps meaning the thinking-off reference. `checks.py`
   reads the same `g6_expected_tail_ids` key through the same
   `approved_set` call as before — zero code change, mechanically the
   rule CP-23 landed.

   Rejected alternatives, each of which moves code instead of data:
   *a second pins key* (`checks.py` would have to select between keys —
   a rule change ADR-0021 prices and the CP-28 measurement says is
   unnecessary); *both tails in one approved set* (measured: weakens G6
   to template-integrity-only in every mode — either opening passes
   anywhere); *a config value the check reads* (`checks` must resolve
   pins with no config loaded at all — the CP-16 no-config-import path
   the client tests exercise — and both frozen call sites pass no
   policy; threading config into the gate is exactly the reshaping the
   per-mode file avoids).

2. **The estate discipline, stated**: `harness.thinking` and the pins
   file are two statements of one fact and the estate owns their
   agreement. A mismatch fails every episode loudly with G6 findings —
   measured at CP-28 in the off-pin/on-mode direction, and symmetric by
   the non-suffix geometry — which is the correct, fail-closed failure.
   No code enforces the agreement (the server cannot know which pins the
   trainer leg resolves), and the wheel's packaged default stays the
   off-mode reference set (ADR-0019's posture: packaged pins are the
   reference estate's; `GSJ_PINS_PATH` is every other estate's surface,
   a thinking-on estate included).

3. **What G6 asserts, per mode.** Thinking-off (7-id empty-think tail):
   every assistant-turn opening of the merged stream carries the pinned
   empty think block — thinking was OFF at every position the template
   could have shown it, plus template integrity. Thinking-on (3-id
   tail): every opening ends at the pinned bare generation prompt —
   template integrity plus the mode assertion that no opening carries
   the empty-think block (i.e. the estate genuinely ran thinking-on);
   it no longer proves anything about thinking, because thinking is on
   and rides mask-1 sampled content, outside any opening.

4. **`harness.thinking` becomes a validated knob.** A `config.py` field
   validator accepts exactly pi's levels —
   `off|minimal|low|medium|high|xhigh|max` — and rejects everything else
   at load, naming the accepted values and the silent-clamp hazard
   (CP-27's message standard: key + measured symptom + cure). Under
   `thinkingFormat: "qwen-chat-template"` every non-off level is
   wire-equivalent (`enable_thinking: !!reasoningEffort` — CP-28), so
   the comment says that too, and `"medium"` stays the conventional ON.

5. **`pi_harness.py` needs nothing.** The harness already forwards
   `settings.thinking` verbatim to `pi --thinking <level>`
   (`pi_harness.py:264,286`), and CP-28 measured the whole path
   end-to-end at every hop with no harness change. That is the result.

6. **`derive_pins.py` handles the new shape as a drift guard.** The walk
   verifies the thinking-on file in the same run: the six non-G6
   approved sets must equal the primary's exactly (two committed files
   whose shared values could otherwise drift), the on-tail text must be
   the byte-prefix of the off tail and match its captured file, the ids
   must be the off ids' first three, and — whenever transformers is
   importable, estate-side — the ids must reproduce under the served
   tokenizer (skip-not-pass on a tokenizer-less host, ADR-0011's
   posture).

## Consequence

A thinking-on estate can now have episodes accepted through the full
seam: config validates the level, the harness forwards it, and G6 checks
the mode the pins state — with `checks.py` untouched at 528/528 and the
gate still failing loudly on any config/pins disagreement. G6's row 14
becomes mode-dependent: PARITY in off mode, and in on mode the gate's
subject is template integrity + mode assertion, never
thinking-suppression (recorded in the spec §G6 and the charter row).
The costs: `config.py` grows by the validator (§3's arithmetic in the
charter), `pins/` gains a second committed file whose non-G6 half is
guarded by the walk, and a wheel-installed thinking-on estate must
supply `GSJ_PINS_PATH` (it already must on any non-reference estate).
C-3 (thinking-on collection at scale) inherits a working seam.
