# CP-11b — M3c: the gates

You are executing CP-11b of `gsj-harness-rollout-server`. CP-11 cleared the
ground — approved sets exist, the budget has an allowance, the timestep is
structural. This lands the gates that are landable and decides the two that
aren't.

**Freeze-lift: `gsj_rollout/checks.py` (the gates), plus the budget-recovery
edits named in ADR-0009 (`cli.py` operator prints, `config.py` comments) and
`builder.py` prose **only** if its freeze-lift is genuinely needed for
recovery — no logic changes anywhere but `checks.py`. NOT lifted:
`receiver.py`, `client.py`, `pi_harness.py` logic, `vendor/`, `corpus/`,
`mcp-service/`, `forgejo/`, `spike/`. No estate, no GPU, no template change,
no re-pin.**

Read first: `docs/checks-spec.md` (the four hashing conventions and the gate
definitions — implement, do not re-derive); `pins/pins.gsj.json` (the
approved sets and their provenance); `docs/reports/CP-11.md` (what's
landable, what's blocked, the budget arithmetic); `docs/reports/CP-10.md`
(the vocabulary and fail-closed posture); `docs/CHARTER.md` (rows 9–15, §3's
budget law, ADR-0009's recovery obligation).

## Step 0 — Protocol
Prompt at `docs/prompts/CP-11b.md`; commit with the CP. Corrupted spans:
reconstruct, apply, list each under `questions:`.

## Step 1 — Budget first
ADR-0009 raised `checks.py`'s allowance to 250–420 and named ~60–80 lines of
recovery elsewhere. CP-11's own estimate says six gates cost 120–140, and
1,438 + 130 overruns the 1,500 law.

**Bank the recovery before writing gates**, so the CP cannot end with a law
violation discovered at the last gate. Measure what you recover and report
it. If the arithmetic still doesn't close after recovery, say so *now* and
land fewer gates rather than more — a stop-and-justify at the start is a
decision; at the end it's a scramble.

## Step 2 — The four landable gates
Per the spec's conventions, each keyed on the approved sets, each
fail-closed on missing evidence (`G{n}:missing_evidence:<field>`), each
using the byetail]` vocabulary.

- **G3 — tool roster.** Canonical-JSON hash of the trace's `tools` array
  against `tool_roster_hash`. CP-06 proved persisted == wire for `tools`;
  CP-11 derived the set from both real episodes. Note the CP-05 caveat in
  the docstring: merged traces carry the *first* completion's tools, so
  cross-completion roster stability is the builder's check, not this one.
- **G7 — settings + chain.** Two clauses: the settings hash against
  `settings_hash`, and the CP-05 stats conjunction (`chains_total == 1` ∧
  `truncated == 0` ∧ `completions_merged == completions_total` ∧
  `raw_completions_total == completions_total`). The second is the one
  that catches degeneration — CP-03 proved `truncated == 0` alone is
  blind. Where does the settings evidence live in a trace? If it doesn't,
  say so and land the conjunction alone with the gap recorded.
- **G2 — system prompt.** sha256 of the wire system prompt against the
  singleton set. **Use `checks._content_text`** — finding (b) i: a raw read of a content-parts message yields empty text and would
  hash a prompt that never existed.
- **G1 — skill card.** The card's bytes against `skill_card_hash`. Note
  the honest edge: the trace must state *which card resolved*, and the
  taskbank deferral (ADR-0003) means prompts arrive as resolved text. If
  the trace cannot identify the card, G1 is unimplementable as specced —
  say so and record what would fix it (a `prompt_id` in task metadata,
  one line in `config.py`, next freeze-lift).

## Step 3 — The G4/G6 evidence decision
Both are blocked on the same question and it needs an explicit answer, not
a default: **where does the receiver get codec evidence?**

- **G4** needs a tokenizer hash and a template hash to compare. The trace
  carries neither artifact — only Polar's `fingerprint` metadata, which is
  a *claim about* the codec rather than the codec itself.
- **G6** needs to decode assistant-turn openings to compare against
  `g6_expected_tail`. Decoding needs the tokenizer atime.

Two candidate answers, genuinely different in strength:

**Measure-at-serve** — the estate records what it actually served
(tokenizer file, template file), the check compares those measurements
against the approved sets. Strong: it verifies the artifact. Costs: an
estate-side recording mechanism, and a channel from there to the check.

**Trust-provenance** — the gate verifies that the trace's declared
fingerprint is in the approved set. Cheap: no new machinery. Weak: it
verifies the *claim*, so a mis-configured estate that reports the right
fingerprint passes. Note this is what CP-09's F1 already burned you on —
the sampling defaults were wrong and nothing on the trace could see it.

Decide, write an ADR, and implement whichever you choose — or record both
as deferred with the reason if neither is landable this CP. For G6
specifically: if decoding needs a tokenizer the checks layer does not
have, that is a legitimate "not implementable receiver-side" finding, and
the builder subclass (which rue Polar's process) may be the right
home instead. Say so rather than forcing it.

## Step 4 — The H-41 red flag
A roster offered with **zero tool executions** is the shape that produced
gates-green semantically-empty episodes in the predecessor. It is not a
gate — a legitimate episode can call no tools — so land it as a *warning*
finding or a policy-gated check, and say which. The point is that the
condition becomes visible rather than silent.

## Step 5 — The first-episode-validate leg
Row 23's remaining half: a gate consuming `pins/pins.gsj.json` plus a real
episode, proving the approved sets admit known-good traces. You have two —
CP-07's and CP-09's — and they are exactly what "first episode" means here.

Assert: every landed gate passes clean on both, and each gate fails on one
doctored input (the CP-10 pattern: prove the rule fires for its own
reason). If a gate passes on the doctored input, the pin or the convention
is wrong — investigate rather than adjusting the test.

## Step 6 — C, spec
- Rows 9–15 move to their earned statuses: PARITY where landed and
  validated, GAP where blocked with the blocker named.
- Row 23 closes if Step 5 succeeds.
- §3's budget status, post-recovery, with the honest arithmetic.
- The G4/G6 decision recorded as an ADR.
- Anything that turned out unimplementable moves to CP-12's list with the
  reason — CP-12 is the verdict, and it should inherit a complete picture
  of what this repo does and does not check.

## Definition of Done — run and show output
```
git diff HEAD -- vendor/ corpus/ mcp-service/ forgejo/ spike/ \
  gsj_rollout/receiver.py gsj_rollout/client.py            # → empty
pytest -q                                                   # green, counts
wc -l gsj_rollout/*.py                                      # against 1,500
# per gate: clean pass on both real traces, one doctored failure, verbatim
# the budget recovery, measured
grep -n 'row 9\|row 1[0-5]\|row 23' docs/CHARTER.md | head
test -f docs/reports/CP-11b.md && echo OK
git stacelain                                      # → empty after commit
```
One commit: `CP-11b: the gates`.

## STOP — hard wall
No estate, no GPU, no template change, no re-pin, no logic changes outside
`checks.py`. Do not draft or begin CP-12.

## Report
`docs/reports/CP-11b.md` per the template, printed. Under notes: the budget
recovery measured, before and after; per gate — landed or not, its evidence
source, its clean-pass and doctored-failure lines; the G4/G6 decision with
its reasoning and what the weaker option would have cost; the H-41 flag's
shape; the validate leg's results; and the complete list of what this repo
checks and what it does not, for CP-12 to inherit.
