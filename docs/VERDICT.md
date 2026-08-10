# VERDICT — should we adopt Polar? (CP-12, closing M3)

Date: 2026-08-09. Status: **ADOPT PROVISIONALLY** — the evidence supports
the architecture; it does not yet support the outcome. What converts it,
and what reverses it, is named in §5. This document is standalone: it
cites the checkpoint reports (`docs/reports/CP-XX.md`) for evidence but
does not require reading them.

## What was tested

`gsj-envloader` (the predecessor — alive, frozen, the fallback) runs our
corpus episodes with ~1,800 lines of its own episode execution and
capture: a checkout→run→harvest→reset lifecycle with docker bolted
inside, per-episode gateway sessions, and a finalize pipeline. That layer
worked and was externally verified, but it was expensive: approved sets
re-derived at nearly every image or mount change, a capture transport
that changed three times, a silently load-bearing parser dependency that
once produced gates-green but tool-free episodes (H-41), and two
dedicated checkpoints just to dismantle the dev harness around it.

This repo tested one bet across twelve planned checkpoints — thirteen
executed, CP-11 having split in two (CP-00 – CP-11b) — in three
milestones: **can NVIDIA's Polar own that layer**, leaving us a thin
shell — the corpus, the temporally-scoped retrieval service, a harness
for our pinned agent (pi 0.83.0), and the validation? Episodes run
against an *estate* — the Forgejo git host, the MCP (Model Context
Protocol) retrieval service, and the inference engine brought up around
the repo. The success criterion (charter §5): *one real episode against
our corpus, through our MCP service, with the cutoff enforced, producing
a trace whose token ids, `loss_mask`, and logprobs verifiably match the
golden reference the predecessor produced for the same task.* Five
abandon conditions were stated in advance (charter §9) so the decision
would not be made under sunk cost.

---

## 1. What did Polar give us?

The whole layer the predecessor paid ~1,800 lines and years of
maintenance for, plus capabilities nobody here would have built. At the
pin, Polar is ~14,200 lines of Python (measured over `src/polar`); we
drive it with 1,496 lines of shell, of which only ~400 (the harness, 237;
the builder subclass, 159) touch episode execution at all.

- **The episode lifecycle.** Sandbox start/exec/upload/download/stop
  behind a runtime-agnostic interface, per-session async gateway workers,
  heartbeats, timeouts, teardown. Ran live from the first vendor: 4
  parallel sandboxes with clean teardown (CP-03), our pi under
  DockerRuntime end to end on real corpus episodes (CP-07), seven
  submissions in one collection loop (CP-09). We wrote zero lifecycle
  code — `pi_harness.py` is contract (clone, mint token, render config,
  download artifacts), not machinery.
- **Proxy capture across provider dialects.** The gateway proxied pi
  0.83.0's traffic **unmodified** — zero translation errors, `messages`
  and `tools` byte-identical from harness to wire (CP-06's three-way
  diff). It absorbed pi's unconditional streaming with a synthetic SSE
  reply pi parses, and its capture normalizers read vLLM, SGLang, and
  OpenAI token-id dialects. The predecessor's capture transport changed
  three times; here it is Polar's problem.
- **Trajectory reconstruction** (`prefix_merging`) — the central bet.
  Line-verified faithful to its paper's algorithm with no tokenizer
  anywhere in the builder, so assistant tokens are engine-sampled ids,
  never a re-rendering (CP-05, adversarially re-verified). Then verified
  empirically against the predecessor's golden reference on the same
  task: masks exact, `prompt_ids` byte-identical, capture agreement at
  mean |Δ| = 0.000114 on identical contexts (CP-09; §4 below).
- **Async staging.** Push-by-callback into our receiver plus an
  independent poll path — the trainer never blocks on collection (CP-08).
- **Two runtimes.** Docker (exercised throughout) and Apptainer (native
  at the pin, unexercised here — register row 30).
- **Eleven harness preset modules** at the pin (claude_code, codex,
  gemini_cli, hermes, mini_swe_agent, openclaw, opencode, openhands_sdk,
  pi, qwen_code, shell — counted at CP-12), plus the two seams that
  matter more than any preset: `import_path` loaded **our** non-preset
  harness with zero vendored edits (CP-06), and the builder registry let
  a validating subclass insert itself into trajectory construction with
  zero patches (CP-05/CP-07). The predecessor is single-harness by
  design — register row 29 is this repo's one BETTER.
- **The parts nobody would have built**: background evaluator-runtime
  prewarming during the agent run, the Apptainer runtime, and the rollout
  API itself (manager, dispatch, task polling, a dashboard) — pure upside
  we inherit without owning.

## 2. What did it cost?

- **Three carried patches, forever.** Upstream at the pin has no
  non-agent completion filter at all (every auxiliary harness call would
  become a trainable trace carrying session reward), treats a mid-chain
  abort as a clean COMPLETED session, and loses in-memory metadata before
  persistence (CP-02: D1/D3/D5, all confirmed at source). None of the
  fixes exists on any upstream branch; none cherry-picks cleanly. P1
  (filter), P2 (abort→ERROR), P3 (policy-version stamping) are hand
  adaptations we re-anchor on every re-vendor. P1's protection then
  measured **inert for pi** — pi streams unconditionally, defeating the
  filter's shape test — so our builder subclass carries the replacement
  check (CP-06).
- **The vendoring posture.** No releases, no tags, squash-merges on
  `stable`, and the real development line (`polar`) 80 commits ahead with
  a pending `prefix_merging` refactor (+49/−156) that will force
  re-porting two patches. First vendor cost ~one working day; re-vendor
  is estimated at ~half a day with the recipe and symbol tripwires in
  `vendor/REVENDOR.md` (CP-03) — an estimate, not yet a measurement: no
  second vendor has been executed (assumption A-8 stays live).
- **Silent degradation is the layer's universal failure mode.** The
  source audit catalogued nine modes (S1–S9, CP-05) in which the builder
  emits a clean-looking `COMPLETED` trajectory that is degenerate —
  split chains, truncated merges, mis-split interstitials, amputated
  tails, mixed policy versions — with **nothing at the pin raising an
  error for any of them**, and zero value-level logprob validation
  anywhere in the tree (grep-verified twice). Three silent classes were
  hit live, not hypothesized: **S1** at CP-03 (a token-id-less backend
  yielded 10 single-completion chains reported `full=10, truncated=0`),
  **S4′** at CP-07 (the Qwen3 no-think template's asymmetric glue split
  every multi-turn episode into per-turn chains, silently COMPLETED),
  and — beyond the catalogue — **F1** at CP-09 (a snapshot shipping no
  `generation_config.json` silently sampled at neutral defaults; no
  trace-side evidence exists even in principle).
- **The validation we wrote because of it.** `checks.py` (407 lines,
  both wire legs), the validating builder subclass (159), and the
  receiver's admission layer (143) exist in this size *because* the
  layer degrades silently rather than failing — nearly half of our
  1,496 lines, with the pins walk (re-deriving every approved-set hash
  from live evidence, `pins/derive_pins.py`) and the checks spec beside
  them outside the count. The shell is thin on execution and thick on
  evidence, which is the correct shape but was not free.
- **The honest half of the bill.** Much of this is the price of
  harness-agnosticism, not defect. A layer that must accept any harness
  and any engine dialect cannot fail loud on shapes it does not know;
  degrade-to-empty is what makes the retokenization guarantee general.
  The predecessor had its own version of the same disease (H-41's
  silently load-bearing parser). The difference is that here the cures
  are all in **our** code — config, subclass, checks — which is exactly
  the architecture the charter mandates.

## 3. What do we still own, and is it the right set?

`corpus/` (the source of truth + ingestion), `mcp-service/` (retrieval
with per-episode JWT cutoffs, enforced server-side from verified claims —
the tamper probe returns 401, CP-07), `forgejo/` (git-host bring-up),
`pi_harness.py`, `builder.py`, `checks.py`, and the config/CLI/client
surfaces. Scrutinized both ways:

- **Should Polar be doing any of it?** Partly, yes — and the seam
  handles it. The glue-stitch repair in `builder.py` (ADR-0007) works
  around a template-asymmetry failure of Polar's grouping that other
  trainer and RL frameworks (verl, OpenRLHF, NeMo-RL) have open in the
  same class, and Polar's own
  builder README describes message-level grouping that does not exist at
  the pin — if upstream's pending refactor lands it, our stitch retires
  (it is already scheduled to go dormant at the template flip). The
  session-level S-checks arguably belong upstream too; at the pin nobody
  validates, so we must, and the zero-patch subclass is the right
  insertion point either way. The rest — corpus, MCP cutoffs, the
  harness contract — is our world, not the rollout layer; Polar's pi
  preset (pinned at 0.67.68) knows nothing of our estate, token mint, or
  clone discipline. Correctly ours.
- **Should a trainer be doing any of it instead?** The client leg
  already IS the trainer's (law 6 runs `checks.py` on both sides;
  `client.py` is the reference implementation of the trainer's leg and
  could migrate wholesale). Storage, retention, mixing, staleness,
  collation were dropped to the trainer at CP-00 and stayed dropped. The
  receiver is the one piece a skeptic could challenge — it exists so bad
  traces die at the source with forensics attached rather than reaching
  a trainer at all; 143 lines is a defensible price for that. Nothing we
  hold fails the scope law: nothing stores, schedules, scores, weights,
  versions, or trains.

## 4. Does it work?

**The success criterion is MET, on the Mac pair** — CP-04's golden
reference plus CP-09's comparison, both run on a Mac estate; primed
checkpoint numbers (CP-04′/CP-09′) are their pending H200 re-runs —
(CP-09, verdict PASS WITH FINDINGS). Exactly what that means: one real
episode
(`case_0001` / `timestep-12` / `skill:summarize`) ran through
`gsj-rollout submit` against our corpus and MCP service; the cutoff held
(every search-result page ≤ 12, the tampered token rejected 401);
the collected trace was compared field-by-field against the golden
reference the predecessor produced for the same triple, under a written
contract (`docs/golden/COMPARISON.md`):

- `loss_mask` semantics **exact** (zero tolerance — mask 1 exactly on
  engine-sampled spans, boundaries aligned to turn structure, on both
  traces);
- sampling-independent tokens **byte-identical** — `prompt_ids`
  2965/2965, and the interstitial glue vocabulary identical across
  stacks (sampled ids are compared per-trace by decode fidelity, exact
  on both — sampling makes cross-stack id equality unreachable by
  design, measured at CP-04);
- logprob capture agreeing with the predecessor's at mean
  |Δ| = 0.000114 on identical-context positions, captured values proven
  RAW on both stacks;
- **no divergence attributable to Polar.** The findings are ours (F1
  engine config, F2 stitch semantics) and the platform's (F3/F4/F5 — a
  teacher-forcing gap and MLX bf16 numerics appearing symmetrically on
  both stacks).

What it does **not** mean: Mac numerics do not govern — the platform
cannot teacher-force, so the replay leg ran beside the engine, and by
assumption A-16 the H200 pair re-establishes production numbers. One
model (Qwen3-0.6B), one task family, two-turn episodes, thinking off.
And the gates' pins — the gates being the predecessor's seven
episode-acceptance checks G1–G7 (hash and evidence rules over each
trace), re-implemented here in `checks.py` — were derived from and
validated against the same two episodes this repo owns; a genuinely
fresh episode first passes them at CP-04′ (CP-11b said this plainly; it
bears repeating here).

**And the honest gap: nothing has been trained.** The predecessor
trained end to end — three regimes, per this CP's charge; the repo's
own record cites the recorded runs in `gsj-envloader-examples` as the
evidence (charter §2). This repo has produced traces and proved they
match the predecessor's — the strongest statement this evaluation could
make short of training, and not the same achievement. A-6 — that slime,
the trainer framework Polar ships a bridge for, can run OPD (the target
training regime) against Polar traces — is the one assumption bearing
on this verdict that remains unresolved; its if-false column predicted
at CP-00 that it "weakens the CP-12 verdict," and that is precisely the
provisionality below. Gradient plumbing, throughput under batch load,
weight-sync semantics (P3 is inert until a trainer declares versions;
A-13's rule — drain all in-flight sessions before every weight sync —
is untested under a real sync) — all unexercised.

## 5. Adopt or not?

**ADOPT PROVISIONALLY.**

What the evidence supports — the architecture: Polar owns the layer, the
shell stayed thin (1,496 lines against the predecessor's ~1,800 for
execution alone), the criterion is met on the Mac pair, and across
thirteen executed checkpoints **no §9 abandon condition ever fired**
despite each
being deliberately approached: `prefix_merging` matched the golden; the
proxy ran pi unmodified; the cutoff injected per-episode and survived a
forged-claim attack; G5's census reconstructed from the trace; the size
law held. Every defect found — and this evaluation found real ones —
had its fix in our code, never in a fork of Polar's.

What it does not yet support — the outcome: production numerics and a
training loop. So the adopt is provisional, with the conditions stated
as decisions, not hopes:

- **Converts to full ADOPT when both hold:**
  1. **CP-04′/CP-09′** — the H200 golden pair passes with the replay run
     as written and the template flip per the inherited DoD (charter
     §6); per A-16 that verdict governs numerics.
  2. **M4** — the slime bridge runs one OPD loop on collected traces,
     consuming masks and logprobs, resolving A-6.
- **Reverses to DO NOT ADOPT if:** CP-09′ shows a mask or
  retokenization divergence attributable to Polar with no fix in our
  code (§9's first condition — then cost Path C: take `prefix_merging`
  as an algorithm, keep our own capture); or the slime bridge proves
  unusable and a trainer-side adapter costs more than Path C; or a
  re-vendor (the named risk is the pending `prefix_merging` refactor)
  breaks the patch posture and A-8 fails.
- **While provisional:** the predecessor stays alive and frozen as the
  fallback (law 3); no production collection on the Mac pair (A-16);
  the wishlist's items 1–4 land before or with M4 (landed at CP-13).

Not full ADOPT, because adopting a rollout server that has never fed a
training step would be inflation. Not DO NOT ADOPT, because no stated
abandon condition is met and the architecture passed every test it was
given. This is the honest middle, with its exit doors labeled.

---

## The register, closed (charter §7 — 31 rows, final for M3)

**18 PARITY · 6 DROPPED · 5 GAP · 1 BETTER · 1 TBD.**

The number that matters — what the predecessor has that this repo does
not, and whether each absence was decided or is owed:

| capability (row) | dropped or gap? | disposition |
| --- | --- | --- |
| store, ready/mix, staleness, serve accounting, collation, quarantine's retention half (16–21) | **DROPPED, deliberate** | the trainer's problem, decided at CP-00 with owners named; the at-source rejection half of quarantine landed here (CP-08) |
| G5's checkout-census clauses (in row 13) | **DROPPED, deliberate** | decided CP-11: a sandbox-filesystem property no trace carries; enforced instead by the hardened `--depth 1`/no-remote/no-reflog clone |
| taskbank builder / skill-row resolution (4) | **GAP, deliberate deferral** (ADR-0003) | fix named: `TaskRequest`-shaped builder in `client.py`'s orbit + `prompt_source`; wishlist |
| gate G1 skill-card (9) | **GAP** | measured unimplementable: no trace states which card resolved; unblocked by `prompt_source` (wishlist item 1) |
| gate G4 codec, receiver-side (12) | **GAP by decision** (ADR-0011) | verified estate-side by the pins walk at bring-up instead; per-episode binding stays open (row 22) |
| gate G6 thinking-off (14) | **GAP** | tokenizer-free design recorded; needs `g6_expected_tail_ids` pinned at the next walk (CP-04′) |
| full trace provenance (22) | **GAP, half deliberate** | the channel is proven; sampling/codec/image identity are estate provenance (F1, ADR-0011) — the estate surface is CP-04′'s |
| G7's settings-hash clause (in row 15) | in-row residual | no settings evidence rides the callback (measured); one-line harness echo, wishlist |

Everything else the predecessor had is at PARITY here with live evidence
(the cutoff end to end with a rejected forgery, capture fidelity, the
merged multi-turn chain, the pins walk reproducing every derivable
predecessor value, bounded collection, the logprob discipline), row 29
(multi-harness) is BETTER, and row 30 (Apptainer/HPC) is the one TBD —
never reachable on this estate, reason in-row.

## The wishlist, consolidated (the next working CP's agenda)

Ordered by what unblocks the most. Items 1–4 are one freeze-lift CP
(~10–40 lines total — the size law's new headroom is for exactly this);
items 5–6 ride CP-04′ and the taskbank milestone. **[CP-13] Items 1–4, 7
and 8 are DONE** (`docs/reports/CP-13.md`): G1 landed (row 9 → PARITY),
G7's settings clause landed (row 15's residual closed), the H-41 mirror
is complete by test, the receiver's two failure shapes are cured over
HTTP, and both stale documents tell the truth. Items 5 and 6 stay with
their owners (CP-04′; ADR-0003), and CP-13's own adversarial pass opened
one new item — **9**, the sandbox-side card hash that is row 9's
remaining delta from the predecessor's instrument.

| # | item | needs freeze-lift of | deferred since / why | unblocks |
| --- | --- | --- | --- | --- |
| 1 | **DONE (CP-13)** — `prompt_source` (+ resolved-card hash) in `TaskRequest.metadata` | `config.py` | CP-11b measured G1 unimplementable without it; rooted in the CP-01 taskbank deferral | **gate G1** (row 9), and with #6 closes row 4 |
| 2 | **DONE (CP-13)** — the H-41 knob's YAML mirror (`reject_toolless_roster` in `ChecksConfig`, mirror-completeness test) | `config.py` (same lift) | CP-11b: config logic was frozen; drift declared in the docstring | the operator arming the toolless-roster check from the one YAML |
| 3 | **DONE (CP-13)** — the settings echo (harness renders its `settings_json` into trace-reachable metadata via the gateway registry merge, A-23) | `pi_harness.py` | CP-11b measured zero settings evidence on the callback | **G7's settings-hash clause** (row 15's residual) |
| 4 | **DONE (CP-13)** — the receiver's pins-failure seam (was: missing KEY → 400 masquerade, missing FILE → dropped connection mid-batch; now: 500 naming the key/path, batch atomic) | `receiver.py` | CP-11b verification measured both shapes live; fail-closed already, ugly | operational robustness at the wire; blocks nothing downstream |
| 5 | `g6_expected_tail_ids` pinned under the served tokenizer | none — the next pins walk (CP-04′; blocked at CP-12 by the checkpoint's own no-re-pin rule) | ADR-0011: the tokenizer exists at pin time only, estate-side | **gate G6** (row 14), incl. the first-turn `prompt_ids` clause |
| 6 | the taskbank landing (`TaskRequest`-shaped builder, skill-row resolution) | `client.py`'s orbit + `corpus/` | ADR-0003 (CP-01): no consumer existed; still true until a trainer drives volume | row 4; G1's end-to-end story with #1 |
| 7 | **DONE (CP-13)** — `mcp-service/README.md` one-liner (said "at CP-11"; the regexes landed at CP-10) | `mcp-service/` | frozen three CPs running (CP-10/11/11b) | auditor accuracy only |
| 8 | **DONE (CP-13)** — `README.md` status section (said "CP-01 — the moves"; now states the CP-12 verdict, the working server, and the test commands) | none standing — excluded only by CP-13's lift list | noticed at the CP-12 re-read; eleven checkpoints stale | the repo's front door telling the truth |
| 9 | **NEW (CP-13)** — G1's card hash computed **sandbox-side**, from the episode's own checkout, the way the predecessor did (`gsj-envloader task.py:878-885`) | `pi_harness.py` | CP-13's own verification: the submit-side statement landed, but a drifted `skills/<name>/SKILL.md` in a case repo stays invisible to G1 | row 9's remaining delta from the predecessor's instrument |

## What comes next

- **CP-04′/CP-09′ — the H200 golden pair.** Repeat the collection and
  comparison on the production platform with zero Mac adaptations; run
  the replay **as written** (vLLM proper can teacher-force; the Mac
  could not — F3); execute the six-item inherited DoD (charter §6):
  render both template variants, prove the symmetric one
  prefix-preserving, adopt it via `--chat-template`, pin it in the serve
  argv and the golden reference's MANIFEST (its provenance file),
  re-derive G4, retire the glue ids leaving the stitch dormant; rerun
  `pins/derive_pins.py` (G4's measure-at-serve) and pin
  `g6_expected_tail_ids`; cure the estate residuals (credentialed clone
  URLs or egress policy — row 2; the generation-config pin + request
  log — F1; an estate provenance surface binding each episode to the
  bring-up measurement — row 22). *Proves:* the numbers that govern
  (A-16). *Unnecessary
  if:* never — only abandoning the H200 as the production platform
  would void it; the Mac verdict cannot govern numerics by A-16.
- **M4 — the slime bridge and one OPD loop.** Submit → collect → slime
  `Sample`s → at least one real optimization step consuming masks and
  logprobs; declare policy versions so P3 stops being inert and A-13's
  drain rule is exercised against a real weight sync. *Proves:* the loop
  trains — converts trace-correctness into the outcome, resolves A-6,
  and is the second condition of the full adopt. *Unnecessary if:* the
  trainer of record becomes verl-only (its budget then moves to the
  verl bridge).
- **M5 — the template, then M6 — thinking, in that order.** M5 makes
  the symmetric (prefix-preserving) template the serving standard
  everywhere, retires the ADR-0007 stitch from load-bearing, and
  refreshes golden + pins on top of CP-04′'s work. M6 then flips
  `harness.thinking` on. The sequencing argument: thinking-ON is out of
  bounds for the stitch (A-22 — variable-length divergence the
  fixed-ids repair structurally cannot fix), so M6 needs M5's template
  first; and the template changes both the trajectory layer's input and
  the golden reference, so changing it in the same milestone as
  thinking would destroy attribution — one variable at a time, the same
  discipline that kept the Mac pair interpretable. *Unnecessary if:*
  M5 — upstream's pending grouping refactor tolerates asymmetric
  templates at a future re-vendor; M6 — the training recipe stays
  no-think.
- **The verl bridge — its own milestone, informed by M4.** The cheaper
  starting point is trainer-side: the predecessor's uni-agent path
  already speaks verl, so an adapter consuming our validated callback
  bodies through `client.py` costs less than a second Polar-side bridge
  — decide after M4 shows what the slime bridge actually required.
  *Proves:* trainer-agnosticism is real, not aspirational.
  *Unnecessary if:* slime remains the only trainer.
- **Production.** Gated on artifacts only the operator can supply: H200
  cluster access and estate bring-up (with the credentialed-clone/egress
  posture), the corpus beyond the staging cases, secret management for
  the MCP token, and the trainer integration of record. *What it would
  take:* both pairs green, M4 done, the wishlist's items 1–4 landed
  (done at CP-13).
  *Unnecessary if:* never — it is the point; the gate exists so it is
  entered deliberately.

## Sources

Charter (`docs/CHARTER.md`): §5 criterion + MET note, §7 register
(final), §9 abandon conditions, §4 assumptions. Reports: CP-02 (fork
audit), CP-03 (vendor + costs), CP-04 (golden reference), CP-05 (source
verdict, S1–S9), CP-06 (harness spike, pi dialect), CP-07 (the harness,
the cutoff proof), CP-08 (the four surfaces), CP-09 (fidelity), CP-10
(discipline + cutoff hole), CP-11 (leak cure, pins walk), CP-11b (the
gates). Decisions: ADR-0003 (taskbank), ADR-0004/0005 (pin + vendoring),
ADR-0007 (the stitch), ADR-0009 (checks allowance), ADR-0011 (codec
evidence), ADR-0012 (this CP's size-law raise).
