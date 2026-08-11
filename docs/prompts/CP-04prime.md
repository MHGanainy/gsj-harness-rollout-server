# CP-04′ — M4d: the H200 golden pair, under the symmetric template

You are executing CP-04′ of `gsj-harness-rollout-server`. The cluster is
free. This is the first of the two converting conditions in CP-12's
provisional adopt.

Scope: bring the estate up on the H200, adopt the symmetric chat template,
re-derive the pins against what the engine actually serves, and collect a
golden reference the H200 fidelity comparison (CP-09′) will measure
against.

**Freeze-lift: `pins/**` (the walk — this is its purpose), `staging/**` if
a bring-up recipe needs correcting, `docs/**`, plus
`gsj_rollout/pi_harness.py` **only** if the template adoption forces a
config value through it. NOT lifted: `checks.py`, `builder.py`,
`config.py`, `receiver.py`, `client.py`, `cli.py`, `corpus/`,
`mcp-service/`, `vendor/`, `spike/`. No fidelity comparison — that is
CP-09′.**

Read first: the predecessor's `staging/BRINGUP.md` (accurate as written —
the operator confirms); `docs/reports/CP-04.md` (the Mac pair: the
feasibility gate, the estate adaptations, the greedy finding, the
`max_model_len` coupling); `docs/golden/COMPARISON.md` (the contract
CP-09′ executes — this CP produces its H200 half); `docs/CHARTER.md` §6's
CP-04′ inherited DoD (six items) and A-16; `docs/reports/CP-10.md` §the
template findings; the template investigation's findings document
(TRL's `qwen3_training.jinja`, the three-line diff, Direction B's
refutation).

## Step 0 — Protocol
Prompt at `docs/prompts/CP-04prime.md`; commit with the CP. Corrupted
spans: reconstruct, apply, list each under `questions:`.

## Step 1 — Bring the estate up
Per `BRINGUP.md`, with this repo's components: staging Forgejo, the
**split-shaped** corpus scaffolded from `corpus/staging`, **mcp-service
0.3.0** (chromadb — note the image is ~310 MB heavier over the
`docker save | ssh load` link; if the transfer is impractical, say so and
record what a slimmer image would need), and vLLM serving
**`Qwen/Qwen3-0.6B`** — the same model as the Mac pair, delib in numerics and not in model.

Engine configuration, all three legs (CP-09's F1 is the reason this is a
step rather than a footnote):
- `--generation-config` pinned to the codec snapshot's own file — the mlx
  conversion shipped none on the Mac and an unpinned engine samples at
  T=1.0 silently. On CUDA the snapshot may carry it; **verify rather than
  assume**, and record the mechanism and the applied block from the
  engine's own request log.
- `--enable-auto-tool-choice --tool-call-parser hermes` — pi sends
  `tool_choice: auto` and vLLM 400s without them (CP-07).
- `--max-model-len` ≥ the config's `context_window` (32768). CP-04
  measured what happens otherwise: every call 400s, pi retries into empty
  turns, and the episode lands `completed` with gates green and zero
  trainable content.

Assert readiness the way BRINGUP does: anonymous clone, MCP `/health`
`ready` with the per-case census **and the chromadb backend block**,
serving healthy with a tool round trip.

## Step 2 — The template: ddopt, prove
The inherited DoD's centre. Three parts, in order.

**Choose.** Fetch TRL's `qwen3_training.jinja` and read it against the
served snapshot's template. Is it scoped to `enable_thinking: false` or
unconditional? Does it drop the positional conditional entirely (which is
what would cover thinking-on)? How does it handle the `reasoning_content`
fallback? Then decide: TRL's file, the three-line diff from the
investigation, or a hybrid. Record the choice and the reasoning. If TRL's
is a superset that also covers thinking-on, prefer it — A-22 says a
fixed-ids stitch cannot repair variable-length reasoning, and a template
that does is worth having even unused.

**Prove it before serving it.** Render both variants against the same
captured pi history (`docs/polar/pi/pi_request.raw.json` carries a real
4-message body) and confirm the symmetric variant makes turn-2's
`prompt_ids` a **strict prefix-extension** of turn-1's. The investigation
measured the current template diverging at index 2004 of 2008 on actly
the four glue ids; the symmetric one should diverge nowhere. Show the
before and after.

**Adopt.** Serve it via `--chat-template <file>`, with the file recorded
in the serve argv and committed under `staging/` so the estate is
reproducible.

## Step 3 — The pins walk
`derive_pins.py` at bring-up **is** G4's measure-at-serve instrument
(ADR-0011). Run it against the served snapshot and the served template —
not the codec snapshot's.

Expect to re-derive: `chat_template_hash` (the whole point — the Mac's
`87a2728c…` is replaced by the symmetric variant's), and whatever else
the H200 estate changes. Expect **not** to move: `tool_roster_hash`
(CP-15 asserted it), `settings_hash`, `skill_card_hash`, `tokenizer_hash`
(the tokenizer file is unchanged by a template swap — verify).

Then wishlist item 5: derive **`g6_expected_tail_ids`** — the token ids of
the assistant-turn opening under the *adopted* template. Note this is
where the symmetric template changes G6's subject: the tail now appears inders too. Record what the ids are and what a G6 rule keyed on
them would check. **Do not implement G6** — `checks.py` is frozen; this
produces the pin, CP-11c or later lands the rule.

Every re-derived value gets provenance: which episode or artifact, which
host, which template.

## Step 4 — Retire the stitch, and prove it
The claim to test: with the symmetric template, Polar's grouping merges
natively and `generation_prompt_glue_ids` is unnecessary.

Collect one episode **with the glue ids unset**. If `chains_total == 1`
with the full G7 conjunction holding, the template did its job — that is
the cleanest possible evidence, and F2 dissolves at the root because the
merged stream now *is* the wire context.

If chains still split, the asymmetry is deeper than the think block: say
so, keep the stitch configured, and record what the residual divergence
actually is (diff the two prompts' ids and name the tokens).

Either way, leave the stitch code in place and dormant — it is the
fallback and A-22's ansa thinking-on estate.

## Step 5 — Collect the golden
One episode on the CP-04 triple — `case_0001`, `timestep-12`,
`skill:summarize` — collected through **this repo's** path
(`gsj-rollout submit`), not the predecessor's.

**Note the difference from CP-04 deliberately**: the Mac golden came from
the *predecessor's* stack (uni-agent capture) because CP-09 was comparing
two capture layers. CP-09′'s question is different — it is establishing
the production numerics with the replay running as written. So decide and
record: does the H200 golden come from the predecessor's stack (a true
repeat of the Mac pair's design) or from ours (the production path)?
**Recommendation: the predecessor's**, so CP-09′ is the same comparison
CP-09 was, on real hardware — otherwise you are comparing our stack
against itself and the fidelity question goes unasked. If the
predecessor's collector stack cannot be stood up on the H200, that is a
finding, and CP-09′'s question narrows accordingly.

Assert before freezingdard: `completed`, gates green,
**tools actually executed** (≥1 `mcp_gsj_*` and ≥1 *successful* built-in —
CP-04 refused an episode on this and CP-09 took seven attempts), logprobs
present, finite, ≤0 at `mask==1`, masks and lengths internally
consistent. Record the attempt count.

Freeze into `docs/golden/h200/` — `record.json`, tokens, transcript,
artifact if any, and `MANIFEST.md` carrying: model id/revision/dtype,
engine and version, **the served template's identity and hash**, pi and
extension versions, the exact task triple, the applied sampling block from
the engine's request log, every G-hash, sha256 per file, and every
H200-specific fact. Nothing may ever compare across `mac/` and `h200/`.

## Step 6 — Charter, register, spec
- A-16 (the Mac-pair posture) gains its counterpart: the H200 governs
  numerics, and why.
- The pins' provenance updates; the template hash's known-expiry note
  from CP-11 resolves.
- Row 14 (G6) — the pin exists; the rule is still blocked on a
  `checks.py` li`docs/golden/COMPARISON.md` gains an H200 section, or a note that the
  contract holds unchanged and CP-09′ executes it against `h200/`.
- Wishlist items 5 and the CP-04′ DoD items marked done.

## Definition of Done — run and show output
```
git diff HEAD -- gsj_rollout/checks.py gsj_rollout/builder.py \
  gsj_rollout/config.py gsj_rollout/receiver.py gsj_rollout/client.py \
  gsj_rollout/cli.py corpus/ mcp-service/ vendor/ spike/   # → empty
pytest -q                                        # unchanged, counts
# the estate: /health with census + backend, serving tool round trip
# the template: before/after prefix-extension evidence, verbatim
# the pins walk: what re-derived, what didn't, with provenance
# the stitch retirement: chains_total with glue ids unset, verbatim
# the golden's assertions and attempt count, verbatim
ls docs/golden/h200/
grep -c '^' docs/golden/h200/MANIFEST.md
test -f docs/reports/CP-04prime.md && echo OK
git status --porcelain                           # → empty after come commit: `CP-04prime: the H200 golden pair`.

## STOP — hard wall
No fidelity comparison (CP-09′). No `checks.py` changes — including G6.
No training. Do not draft or begin CP-09′.

## Report
`docs/reports/CP-04prime.md` per the template, printed. Under notes: the
estate as brought up and every deviation from BRINGUP; the engine's three
pinned legs with evidence; the template choice with its reasoning and the
prefix-extension proof; the pins walk table; **the stitch-retirement
result** — the single most consequential line in this CP; the golden's
provenance decision and its assertions; and anything the H200 surfaced
that the Mac could not.
