# VERDICT — should we adopt Polar? (CP-12, closing M3)

Date: 2026-08-09. Status at CP-12: **ADOPT PROVISIONALLY**.
**Status now (2026-08-11, CP-17): ADOPT — both converting conditions are
met.** The two dated sections at the end of this document record how each
condition closed; §5's body is preserved as written so the conversion can
be audited against the conditions as they were stated in advance, not as
they might be remembered. This document is standalone: it cites the
checkpoint reports (`docs/reports/CP-XX.md`) for evidence but does not
require reading them.

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

### 2026-08-11 — converting condition 1: MET (CP-09′, the H200 pair)

The H200 golden pair is done and the pair that governs is green:
`docs/golden/COMPARISON.md` executed in full against
`docs/golden/h200/`, with the replay run **as written** through the
serving engine for the first time — verdict **PASS WITH FINDINGS**
(`docs/reports/CP-09prime.md`). Masks exact (the zero-tolerance row, on
both traces), `prompt_ids` byte-identical, decode-fidelity exact to the
byte, glue constants identical, discipline clean, cutoff held; the
reversal condition (a mask or retokenization divergence attributable to
Polar) did not fire — **nothing in the comparison is attributable to
Polar's code**. The one finding is the platform's: capture-time
decode-path numerics sit above the contract's CP-18-anchored replay
bounds on BOTH stacks symmetrically (golden 0.005246 / collected
0.007141 mean |Δ| vs 0.005; replay itself bit-deterministic at exactly
0.000000), and the identical-context capture floor is ≈ 30× the Mac's
(0.003672 vs 0.000114) — invisible trace-side, recorded in
`docs/checks-spec.md` §CP-09′, binding on any replay-style trainer
check. A-1 is resolved on the governing platform; A-16's counterpart is
closed; charter §5's criterion is met on both pairs.

**The verdict now stands on**: condition 1 met (this entry) + condition
2 open — **M4's training loop is the only thing between ADOPT
PROVISIONALLY and full ADOPT.** The reversal doors narrow accordingly:
the CP-09′ door (mask/retokenization divergence) is closed by
measurement; what remains are the slime-bridge door and the re-vendor
door, as written above.

### 2026-08-11 — converting condition 2: MET (CP-17, the loop) → **ADOPT**

The loop closed on the H200, measured at every step
(`docs/reports/CP-17.md`; evidence in `docs/polar/h200-loop/`):
**collect** — 28 submissions through `gsj-rollout submit`, 27 qualifying
(COMPLETED, findings `[]`, `chains_total == 1`, cutoff held), zero
receiver rejections, zero quarantines; **convert** — 27 bodies → 27
**real** `slime.utils.types.Sample`s through the CP-16 bridge with its
three assertions live and `checks` running trainer-side from the packaged
wheel pins; **train** — one optimizer step in real slime v0.3.0 +
Megatron, `global_batch_size 27`, `train/grad_norm 0.4513` (non-zero and
below the clip, so unclipped), on a **non-degenerate** reward (1 of 27
episodes cited 4 pages within cutoff → 1.0), TIS consuming our captured
logprobs; **sync** — checkpoint reload (torch_dist → HF → the engine
restarted under the same served model name with all four legs
byte-identical), proven three ways, decisively by a probe whose control
measurement on identical weights is `mean|Δ| = 0.000000, nonzero 0/5782`
and whose across-the-sync measurement is
`mean|Δ| = 0.041835, nonzero 5623/5782`; **collect again** — 8/8
qualifying against the updated policy, gates green, cutoff held, all 8
still converting clean.

**A-6 is resolved** — slime runs against Polar traces, end to end, for
real. **A-26 holds** — the vendored adapter's `Sample` surface is the
installed surface (`session_id`, `group_id`, `remove_sample`,
`Status.FAILED` all accepted on first construction). **A-13's drain rule
met a real sync** and was satisfied *by construction* (serialized loop,
zero in-flight sessions verified at the boundary) — the situation was
exercised, the mechanism was not.

**Verdict: YES WITH FINDINGS**, three of which are named with owners —
Polar's vendored LOO post-processor explodes an advantage to 1e6 on
degenerate variance (only `clip_grad` prevents divergence, nothing warns);
slime silently no-ops an entire train loop while reporting SUCCESS when
`--load` reads as a resume; Polar's documented Megatron pin lacks the
module its own comment requires. All three are worked around at
trainer-side cost; none is in this repo's code, and **nothing in
`gsj_rollout/` had to change for the loop to run.**

**The CP-12 verdict converts to ADOPT.** What that means: the architecture
and the outcome both have evidence — traces produced by this server drove
a real optimizer step and came back as an updated policy demonstrably
serving the next collection. What it does **not** mean: one loop at 0.6B
on 27 episodes is not a training result, and nothing here shows learning
(the post-sync reward and length changes are one crude step at n=8, not a
curve). **What would still reverse it**: a re-vendor that breaks the patch
posture — the pending `prefix_merging` refactor, A-8, still untested, no
second vendor executed. The slime-bridge door is now closed by
measurement; the re-vendor door is the one that remains.

### 2026-08-12 — M6: the second trainer, and the boundary (CP-20 + CP-21)

**The trainer-agnostic claim is now measured, not argued.** M6 asked
whether the boundary this repo drew — task → sandbox → agent → trace,
nothing else — holds against a second trainer with a completely
different batch shape. It does, at both halves:

- **M6a (CP-20, the bridge)**: callback-shaped `SessionResult` → real
  verl `DataProto` (padded, uid-grouped, tensor — nothing like slime's
  per-sample objects), 26 fixture-driven tests against real verl, zero
  changes in this repo.
- **M6b (CP-21, the loop)**: collect → convert → train → sync → collect
  closed on the H200 — **YES WITH FINDINGS** (`docs/reports/CP-21.md`):
  112 submissions (110 qualifying), one real verl optimizer step
  (`TrainingWorker`/FSDP, `pg_loss −0.0944`, `grad_norm 2.32` pre-clip,
  GRPO advantages over ONE uid group of 110 — F-10 closed by design),
  the captured logprobs load-bearing (sequence-TIS; recompute agreement
  mean |Δ| 0.009442 = the third instrument at the CP-09′ floor), the
  sync proven with a zero-noise instrument, and a second collection
  8/8 qualifying against a demonstrably different policy (no learning
  claim — the post-sync batch is format-copying with visibly narrowed
  lengths, the entropy/KL caution for any real run). This repo's diff:
  **`docs/**` only**. The findings (verl's F-12/F-13, reward sparsity,
  the clipped step) are all trainer-, evaluator-, or config-side — none
  at the boundary.

**What two loops prove that one could not**: the same server surface —
the same wheel, the same callback JSON, the same estate recipes — fed a
per-sample trainer (slime) and a padded-batch trainer (verl) through
one submit path and one sync script, with the server changed in exactly
zero places. Scope law 1 held under contact twice; the DROPPED
trainer-side rows (16–21) were needed nowhere, twice.

### 2026-08-12 — M7a: the re-vendor door — NARROWED (CP-22)

The last reversal door on this verdict was written as: *a re-vendor
breaks the patch posture and A-8 fails*. CP-22 executed the second
vendor — the first since the recipe was written — and the door did not
fire (`docs/reports/CP-22.md`):

- **The mechanism is rehearsed, not estimated.** Upstream `stable` had
  not moved (still `f0e8343a`, still no tags or releases), so the
  rehearsal re-vendored to the same SHA and exercised the whole recipe:
  the re-vendored tree came out **byte-identical to the committed tree**
  (empty `git diff`, file modes kept), all three patches applied clean by
  script, reverse-apply walked back to the pristine pin exactly, same
  175/3 vendored-suite split, all approved pins reproduced, the registry
  seam resolving. Mechanical cost: ~2 minutes; with full verification
  ~15. **A-8 is resolved** (charter §4), with its residuals named there.
- **The named risk inside the door is now priced.** The pending
  `prefix_merging` refactor (frozen on the `polar` branch since
  2026-06-06), simulated as landed: P1/P2/P3's source hunks all apply
  clean — P2's finalize-site anchor and P1's stats-dict anchor both
  survive — and only P1's two fixture-marker test hunks need mechanical
  re-anchoring. The wholesale re-port the door feared is, against
  today's refactor, a fixture edit.

**The door is NARROWED, not closed**: no moved-pin re-vendor has run,
and the refactor measurement is a point-in-time reading of an unlanded
branch — what eventually squash-lands may differ, and the vendored
suite at that future pin remains the real gate. But the failure mode
the door named — the patch posture breaking at a re-vendor — now has
measured evidence against it on both halves: the mechanism reproduces,
and the riskiest known upstream change costs fixtures, not patches.
One finding the rehearsal surfaced is recorded where it belongs: the
recipe's venv rebuild omitted the A-14 `gsj_rollout` install (followed
verbatim, it breaks the registry seam) — corrected in
`vendor/REVENDOR.md`, which has now been followed once and reflects the
execution, not the intention.

### 2026-08-12 — M7b: the budget, and G6 — LANDED (CP-23)

The last designed-but-unlanded gate is live, and the budget mechanism
that blocked it is now self-enforcing (`docs/reports/CP-23.md`). Wishlist
row 18 closed in the order its finding demanded: the CP-11 banking pass
re-applied first (`checks.py` 520 → 497, AST identical modulo docstrings,
suite unmodified), the arithmetic stated before any rule code (G6
measures 31 lines; 497 + 31 = 528 > 520 — the two do not close), then
ADR-0021 raised the allowance to **528, the landed size exactly, zero
headroom by design, machine-checked by a suite tripwire** — the answer
to ADR-0014's earmark being spent by CP-16/CP-19 without either
noticing. `check_thinking_tail` landed exactly per ADR-0011's design
(register row 14 → PARITY; the running tally 20 PARITY · 7 DROPPED ·
3 GAP · 1 BETTER · 1 TBD): tokenizer-free ids-`endswith` of the CP-04′
pin over the turn-1 `prompt_ids` suffix and each pre-turn interstitial,
fail-closed at zero turns, clean on all four real bodies, one doctored
failure per clause, the single-turn case proven actually-checked. What
it asserts under the symmetric template: thinking stayed off at every
turn opening the merged stream carries. The Phase-C caveat is recorded
in the spec §G6: as pinned, a thinking-on estate fails every episode
loudly — C-2 re-pins, re-conceives, or retires the gate before the
first thinking-on episode reaches a receiver.

### 2026-08-12 — M7c: the taskbank — LANDED (CP-24)

The register's last deliberate deferral resolves
(`docs/reports/CP-24.md`; ADR-0022 resolving ADR-0003; register row 4 →
PARITY, the running tally 21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER ·
1 TBD). What landed is deliberately not the predecessor's §3.1 bank —
Polar still takes `TaskRequest`s — but the consumer's enumeration:
`phase_taskbank` builds one flat row per `(case, timestep, prompt)`
carrying the triple, the lock-sourced `split` (ADR-0015's row-spec,
honored verbatim), `prompt_source`, the free row's verbatim text or the
skill row's **resolved** card text, and `sandbox_image` — every column
either the triple or a `render_task_request` argument, so a row submits
with zero translation and **zero `config.py` change** (the CP-13/CP-14
parameters fit as built). Deterministic (byte-identical rebuilds, sorted
rows, no timestamps), sha256 in the lock, and `verify` finally runs the
row-level half deferred since CP-01: counts vs the lock, triples
exactly-once and set-equal to the tree, split/text/image re-derived from
the tree. G1's end-to-end story closed with it, proven fixture-driven on
both real callback bodies: card bytes → bank text → render-computed hash
→ task metadata → trace metadata → `check_skill_card` ∈ the pinned set.
The frozen staging bank's 12 triples and splits reproduced exactly; its
bytes did not (the §3.1 nesting dropped by decision) — the lock records
`ae9e0bbd…`. Wishlist row 6 closes; row 9 (sandbox-side hashing) is
restated, narrower but real: binding G1 to the bytes the episode
actually saw.

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
| 5 | **DONE (CP-04′)** — `g6_expected_tail_ids` pinned under the served tokenizer: `[151644, 77091, 198, 151667, 271, 151668, 271]`, derived and tokenizer-verified estate-side at the H200 pins walk (`pins/pins.gsj.json`; `derive_pins.py` re-verifies wherever transformers is importable) | none — the next pins walk (CP-04′; blocked at CP-12 by the checkpoint's own no-re-pin rule) | ADR-0011: the tokenizer exists at pin time only, estate-side | **gate G6** (row 14), incl. the first-turn `prompt_ids` clause — the rule itself still needs a `checks.py` freeze-lift (CP-11c or later) |
| 6 | **DONE (CP-24)** — the taskbank landing (`TaskRequest`-shaped builder, skill-row resolution) — **[CP-14] the split half is now fully specified** (ADR-0015: per-row `split` from the lock's `cases.<id>.split`, passed to `render_task_request(split=…)` — landed and test-proven; no split decisions left for the builder). **Landed as ADR-0022**: `corpus/ingest_corpus.py`'s `taskbank` phase builds flat rows shaped for `render_task_request` (triple + `split` + `prompt_source` + verbatim `prompt_text` / **resolved** `skill_card_text` + `sandbox_image`), deterministic with the sha in the lock, `verify` running the row-level half; a row submits with zero translation and **no `config.py` change** — the CP-13/CP-14 parameters fit as built, which was those checkpoints' aim. (The landing is `corpus/`-side, not `client.py`'s orbit as this row guessed at CP-12 — the builder produces rows a consumer renders, not `TaskRequest`s directly, per ADR-0022 §1) | `client.py`'s orbit + `corpus/` | ADR-0003 (CP-01): no consumer existed; still true until a trainer drives volume — resolved with Phase D's consumer story as the named driver | row 4 (→ PARITY); G1's end-to-end story with #1 (closed — proven on both real callback bodies) |
| 7 | **DONE (CP-13)** — `mcp-service/README.md` one-liner (said "at CP-11"; the regexes landed at CP-10) | `mcp-service/` | frozen three CPs running (CP-10/11/11b) | auditor accuracy only |
| 8 | **DONE (CP-13)** — `README.md` status section (said "CP-01 — the moves"; now states the CP-12 verdict, the working server, and the test commands) | none standing — excluded only by CP-13's lift list | noticed at the CP-12 re-read; eleven checkpoints stale | the repo's front door telling the truth |
| 9 | **NEW (CP-13)** — G1's card hash computed **sandbox-side**, from the episode's own checkout, the way the predecessor did (`gsj-envloader task.py:878-885`). **[CP-24] Restated now that the bank states a hash**: the statement is honest — computed at render from the corpus-level card the taskbank resolved, verified against the pins, with `verify` holding the bank to the tree — so what sandbox-side hashing still buys is exactly one thing, and it is real: binding G1 to the bytes **the episode actually saw**. A checkout drifted from the corpus (a bad push, a tampered estate repo, a stale clone) passes today's G1 with a true statement about the *corpus* while the *sandbox* read something else; corpus-side `verify` only catches it when someone runs `verify` against that estate. Narrower than before CP-24 (bank staleness vs the tree is now a named `verify` FAIL), but not closed | `pi_harness.py` | CP-13's own verification: the submit-side statement landed, but a drifted `skills/<name>/SKILL.md` in a case repo stays invisible to G1 | row 9's remaining delta from the predecessor's instrument |
| 10 | **NEW (CP-14)** — `skills/<name>/` interior strictness: the validator ignores files beside `SKILL.md` and the scaffolder silently drops them from repos (v1-inherited behavior, surfaced by CP-14's stranger-read pass; contract v2 now documents it as an honest exception rather than leaving it a surprise) | `corpus/` | CP-14 scoped to the split; tightening skills validation is a separate contract decision | the "everything it can check, it checks" doctrine holding for the one directory it currently skips |
| 12 | **NEW (CP-17) + DONE (CP-18)** — `staging/serving/run/` (the serve script's runtime `endpoint.env` + `tunnel.pid`) is untracked and un-ignored, so every estate bring-up leaves the tree dirty and every CP's `git status --porcelain` DoD line has to step around it. One `.gitignore` line — landed as `staging/serving/run/`, three comment lines of provenance above it. (CP-18's lift enumerated `.github/**`, `pyproject.toml`, `README.md`, `docs/**` and did **not** name `.gitignore`; its Step 5 named this item by number. The explicit instruction was taken over the enumeration for one inert line, and the excursion is declared in `docs/reports/CP-18.md` `scope_drift`) | root `.gitignore` — outside CP-17's `docs/**` + `staging/**` lift, so CP-17 removed the directory at teardown instead | first noticed CP-17 (the artifacts predate it — they were already untracked at session start) | the clean-tree DoD stops depending on an operator remembering to delete a run directory |
| 14 | **NEW (CP-18)** — `mcp-service/tests/test_backend.py::test_stored_vectors_are_the_pinned_encoders` asserts BIT-equality between the stored Chroma vector and a fresh encode. The property it guards (the pinned MiniLM embedded the corpus; Chroma's default ONNX EF never touched it) holds everywhere measured, but the oracle is host-dependent: on `linux/arm64` 15 of `case_0001`'s 51 vectors differ by ≤ 1 ULP (worst |Δ| 1.490e-08, cosine 0.999999940) while a wrong embedder would sit at cosine ≈ 0.80. Passes on x86_64 and on macOS, so CI is green and nothing is owed today | `mcp-service/` | opened CP-18; no action taken deliberately — a tolerance would weaken a real canary for an architecture this project does not deploy on | the day the suite must run on arm64 (an arm64 runner, an Apple-silicon container, a Graviton box), which is when it needs a tolerance-based sibling rather than an edit |
| 15 | **NEW (CP-18)** — `tests/test_receiver.py::test_a_staging_failure_leaves_no_partial_batch_and_no_orphan_tmp` needs a non-root user: it chmods the staging dir to `0o500` and expects the write to fail, which `CAP_DAC_OVERRIDE` defeats, so the assertion reads `200 == 500` under root. Hosted `ubuntu-latest` runs as `runner`, so CI is unaffected | `tests/` | opened CP-18 (found in a root container during the pre-flight rehearsal, not on the runner); frozen this CP and correct as written — the finding is about where the suite may run, not about the test | anyone moving CI to a `container:` job, or running the suite inside a Docker build — both root by default, both would see a spurious failure |
| 16 | **NEW (CP-18)** — `vendor/polar/tests` is not run by CI, including the four carried-patch tests `vendor/REVENDOR.md` makes mandatory at re-vendor time (`test_record_filters.py`, `test_builder_filter_wiring.py`, `test_prefix_merging_abort.py`, `test_storage_policy_version.py`). They are fixture-driven and would fit a hosted runner; what stops them is that they need Polar's own uv venv and belong to the re-vendor recipe, which runs at a re-vendor and not on every push | `.github/**` only (adding a fifth job); `vendor/` stays frozen either way | opened CP-18 — the CP's own verification pass caught that "the fixture-driven half" was one suite short of true, and the caption now names the omission instead of implying coverage | a re-vendor that regresses a carried patch being caught by CI rather than by the operator remembering step 5 of `REVENDOR.md` |
| 19 | **NEW (CP-24)** — the pins seam for card *edits*, three small facts found by CP-24's adversarial pass, none fixable this CP (`pins/` frozen): (a) `pins/pins.gsj.json`'s `skill_card_hash` provenance note still says "skill-row RESOLUTION stays taskbank-deferred (ADR-0003)" — stale since CP-24 (resolution now happens at bank build; the *values* are untouched and correct); (b) `pins/derive_pins.py` hardcodes the two staging skill names, so a brand-new card needs a script edit before it can be pinned at all; (c) nothing warns at bank build when a resolved card's hash is not in the estate's pins — the first symptom of a routine card edit is a wave of `G1:skill_card_hash_not_approved` quarantines (the contract now tells the data-prep team to warn the operator, but a build-time advisory where pins are reachable would catch it mechanically) | `pins/` | opened CP-24; the pipeline is deliberately pins-unaware (a moved component; law 6's approved sets are the rollout side's) — the *seam between the two* is what has no owner | a card edit landing as a pins re-derivation instead of as quarantined episodes |
| 13 | **NEW + DONE (CP-18)** — continuous integration: nothing ran the suites but an operator on a Mac, so the only evidence that any of them still passed was a paragraph in the last report to run them. Landed as one `.github/workflows/ci.yml`, four jobs, Python 3.12 only (root 129 · corpus 44 · mcp-service 89 · wheel build + the CP-16 packaged-pins install proof from a venv outside the checkout), push + pull_request on `main`, with the covered/not-covered statement in the file's header comment and beside the README badge. (CP-18's Step 5 called this "wishlist item 12"; item 12 was CP-17's `.gitignore` row — the CI work had no row until this one, the same numbering slip CP-16 hit and recorded) | none — `.github/**` was new, and CI config is outside the size law (CHARTER §3, [CP-18]) | never registered: the repo has had suites since CP-01 and a public remote since CP-13a, and no checkpoint until now was scoped to connect them | every later CP starts from a checkout whose fixture-driven half is known-green, instead of from a claim |
| 11 | **NEW + DONE (CP-16)** — the trainer leg from an installed wheel: `pins/` did not ship (`pyproject` packaged `gsj_rollout` only), so `checks.PINS_PATH` resolved into site-packages and every trainer-side `validate_session_result` raised `PinsConfigurationError` — recorded at CP-11b, dispositioned there as "both legs run from the checkout by design"; M4's bridge killed that design assumption. Landed as ADR-0017: pins force-included into the wheel (`gsj_rollout/pins/`), `PINS_PATH` resolves `GSJ_PINS_PATH` → checkout → packaged copy, mismatch fails loudly as `*_not_approved`; proven from a scratch venv against the real CP-09′ body (findings `[]`). (The CP-16 prompt called this "wishlist item 10"; item 10 is the skills-interior row above, untouched — the trainer-leg fix had no row until now) | `pyproject.toml` + the `checks.py` seam (CP-16's lift) | never registered — CP-11b called it noise while both legs ran from checkouts | **the slime bridge** (examples repo), and any trainer that installs rather than clones |
| 17 | **NEW (CP-19), DONE (CP-29)** — the package was not on PyPI until CP-29. The release path existed and was rehearsed locally end to end (wheel clean and exclusions asserted, `twine check` PASSED on both artifacts, CP-16's install proof green from a scratch venv outside every repo against the real CP-09′ body), but nothing was uploaded: the operator was asked and chose to stop at the path rather than make an irrevocable first upload (ADR-0020 §5). **The name is unclaimed on both indexes and therefore NOT reserved** — verified via the JSON API (`gsj-harness-rollout-server` → 404, `httpx` → 200; the HTML project pages sit behind a bot challenge that returns 200 for names that do not exist, so the HTML is not an oracle). Anyone may claim the name before we do; accepted, because the alternative is an irrevocable upload made to win a race. (The CP-19 prompt called this "wishlist row 13"; row 13 is CP-18's CI row — the same numbering slip CP-16 hit at item 10/11 and CP-18 at item 12, recorded here in the row rather than silently renumbered). **[CP-29] DONE — published, and proven from the public index.** The operator registered both pending publishers out-of-band; CP-29 pushed the mirror current (nine commits, CP-20..CP-28), rehearsed via `workflow_dispatch` — the first-ever execution of `release.yml`: build + CI-side exclusion assertions green, the OIDC exchange accepted by TestPyPI (no `invalid-publisher`), PEP 639's SPDX expression + `license-files` accepted by a real index, the PyPI job structurally skipped — then tagged `v0.1.0` at `1565813` (CP-28) and the tag run published to TestPyPI and PyPI, all jobs green. The proof, CP-16's shape against the PUBLIC artifact: a scratch venv outside every repo, `pip install gsj-harness-rollout-server` with no index flags and no local wheel → the packaged pins resolve from site-packages, the real CP-09′ body → findings `[]`. The examples repo simultaneously gained its public remote (github.com/MHGanainy/gsj-harness-rollout-server-examples). The name-race risk this row carried for ten checkpoints closed unexercised: 404 on both indexes the hour before the upload | none — `pyproject.toml`, `.github/workflows/**`, `LICENSE` and `docs/**` were all lifted at CP-19 and all landed | opened CP-19; nothing before it was scoped to publish | **two prerequisites, both operator-side and neither performable from this repo**: (1) a pending publisher configured at test.pypi.org and pypi.org (owner `MHGanainy`, repo `gsj-harness-rollout-server`, workflow `release.yml`, environments `testpypi` / `pypi`) — done by the operator before CP-29; (2) a `v0.1.0` tag pushed at a commit CI has already validated — pushed at CP-29 (with the CI caveat that is wishlist 26). The workflow did the rest, exactly as this row predicted |
| 18 | **NEW (CP-19), DONE (CP-23)** — `checks.py` was at **520 / 520**, exactly on ADR-0014's ceiling, so **G6's tokenizer-free ids rule could no longer land inside it**. ADR-0014 reserved the 23 lines above 497 for G6 "and nothing else"; measured from `git show` at CP-23, three CPs eroded it without noticing — CP-14's TR3 tripwire took the first 12 (497→509), CP-16's resolver seam 9, CP-19's pins signal the last 2 (the CP-19 account here originally named only the last two). **Resolved at CP-23, both mechanisms in order**: the CP-11 banking pass re-applied (520 → 497, AST identical modulo docstrings, suite unmodified), the arithmetic stated (G6 measures 31 lines; 497 + 31 = 528 > 520), then ADR-0021 raised the allowance to **528 — the landed size exactly, zero headroom, enforced by a suite tripwire** so the silently-spent-earmark failure cannot recur. G6 landed the same CP (register row 14 → PARITY) | `checks.py` (banking + the gate), `tests/test_checks.py` (the tripwire), ADR-0021 | opened CP-19 by its own arithmetic; the earmark was silently eroded across CP-16 and CP-19 and is surfaced here rather than discovered mid-checkpoint | **gate G6** (register row 14), the last designed-but-unlanded gate — landed |
| 19 | **NEW (CP-21), DONE (CP-27)** — `gsj_rollout/cli.py` had no `if __name__ == "__main__"` guard, so `python -m gsj_rollout.cli serve …` defines `main` and **exits 0 silently having done nothing** — an invocation that looks like success (the console-script entry `gsj-rollout` is the only working form). Hit live at CP-21 bring-up: the receiver "started" three times with an empty log before the cause was found; the estate now runs the CLI via `python -c "from gsj_rollout.cli import main; …"`. Two inert lines, but `gsj_rollout/` was frozen at CP-21. **[CP-27] Landed at the freeze-lift**: the guard is in, `python -m gsj_rollout.cli --help` exits 0 and prints, `serve` with a bad config exits 2 saying why — both proven by subprocess tests that fail with the guard removed | `cli.py` (any future freeze-lift; counts ~2 lines against §3) | opened CP-21; every estate that installs no console script (venv-less hosts driving the CLI through an interpreter path) | a silent no-op stops masquerading as a started server |
| 20 | **NEW (CP-25), OPEN** — the CLI cannot submit a taskbank row. `gsj-rollout submit` is definitionally `prompt_source="free"` (frozen `cli.py` — resolution never happens there), so the CP-24 bank — the deliverable a consumer is handed — submits only through Python (`render_task_request` with the row's columns, as `example_project/train.py` does). A `--from-bank <parquet> [--row K]` flag is the natural fix; it raises the pyarrow-in-core question ADR-0022 deliberately kept out of the root closure, so the flag likely belongs behind a lazy import with a named error, the corpus pipeline's own pattern | `cli.py` | opened by CP-25's stranger read: the run book's collect path is `train.py --collect-only` where a CLI one-liner would be expected | a consumer collecting from the bank without writing Python |
| 21 | **NEW (CP-25), DONE (CP-27)** — two config traps the comments carried but the schema could reject: (a) `polar.gateway.public_url`'s port vs `polar.gateway.port` — one fact stated twice; a mismatch dispatches to a URL nothing listens on, found only at the first dead submit (the CP-25 example itself shipped this mismatch in draft and was caught by its own validation pass); (b) `estate.serving_base_url` ending in `/v1` — Polar's proxy appends `/v1/chat/completions` itself and the suffixed form 404s as `/v1/v1/…` (the CP-04′ measured trap, today a comment). Each is a two-line model validator; both were out of CP-25's lift (defaults and comments only, logic only where a default can't express the thing — these are cross-field logic) | `config.py` (a logic lift; ~4 lines against §3) | opened by CP-25's stranger read; both traps are documented in the example config but documentation is the weakest guard the file has. **[CP-27] Both validators landed**: the `/v1` suffix and the port mismatch fail at load naming the key, the measured symptom, and the fix (messages verbatim in the CP-27 report); the correct forms accepted; each test fails with its validator removed. The executable checks are the estimated size — the growth beyond it is the actionable messages, accounted in CHARTER §3 [CP-27] | the two likeliest stranger misconfigurations failing at load time, naming the key, instead of at the first dead episode |
| 22 | **NEW (CP-26), PARTIALLY DONE (CP-27)** — the `gsj-rollout serve` session-start prints were correct and invisible: the topology print (the rendered path + the two Polar commands — the session's only instructions) is block-buffered python stdout, so under `nohup … > log` the log holds only the pins warning while the receiver listens silently (external F-20); the printed Polar path is RELATIVE to an unstated cwd and assumes a `vendor/polar/.venv` that no fresh checkout has, with no hint when it is missing (F-21); and the packaged-pins warning prints in full on every import even on the reference estate where the correct response is to do nothing (F-39). Three small serve-time changes: flush/line-buffer before serving, print absolute paths + a missing-venv hint, and consider a warn-once (or estate-matched silence) for the pins line | `cli.py` (+2 lines-ish against §3); the pins-warning half touches `checks.py` (ADR-0021 tripwire — needs its own decision) | opened by CP-26's stranger run: the operator backgrounded serve exactly as a stranger would and lost the instructions. **[CP-27] Two of three landed**: every pre-block serve print carries `flush=True` (verified through a pipe with the process still running — the test fails with the flush stripped), and the printed Polar path is absolute via the computed repo root (F-21's one-line half; note a wheel install's repo root is site-packages, loud-but-wrong — the missing-venv HINT stays open here with it). **The F-39 pins warn-once half stays OPEN**: it lives in `checks.py`, 528/528 under the ADR-0021 equality tripwire, and needs its own ADR | the server's own instructions surviving a nohup, and a fresh estate learning what to provision from the error instead of from spelunking |
| 23 | **NEW (CP-26), DONE (CP-27)** — two config-schema strangerward gaps beside row 21's validators: (a) a required-key line deleted whole leaves a comment-only section parsing as YAML null, and the error is pydantic's "Input should be a valid dictionary or instance of GatewayNodeConfig" — naming no field where the unknown-key/missing-leaf errors are excellent (external F-25; normalize None sections to `{}` so the field-level message fires); (b) the served snapshot's revision has no home in the YAML — the engine pins a revision, `--snapshot` must match it, and CP-26's stranger matched it by luck (F-23; an optional `estate.model_revision` would let the pin travel with the config and lets train.py-shaped consumers verify before the GPU) | `config.py` (a logic lift; rides with row 21's ~4 lines) | opened by CP-26's error-quality probes and the snapshot-by-luck moment. **[CP-27] Both halves landed**: `_null_sections_to_empty` normalizes null sections model-driven (not a hardcoded list), so the deleted-line mistake reports `'polar.gateway.public_url': Field required`; `estate.model_revision` is an optional in-band pin the server never reads — a train.py-shaped consumer can verify `--snapshot` against it before the GPU | the deleted-line mistake naming its field, and the snapshot pin arriving in-band instead of over a handover chat |
| 24 | **NEW (CP-26), OPEN — untouched at CP-27, `mcp-service/` frozen** — the MCP HMAC secret cannot be verified before it is spent: gateway and service must share `GSJ_MCP_TOKEN_SECRET`, an inherited estate's value arrives only by operator handover, and a wrong value first surfaces MID-EPISODE as failed tool calls (external F-22). A cheap authenticated probe (the service already has `/health`; an HMAC-checked variant, or a one-shot `verify-secret` request the gateway can issue at startup) would fail the mismatch at session start, naming the env var | `mcp-service/` (a moved component — its own release cadence), plus a gateway-side probe call | opened by CP-26: the stranger's secret came from out-of-band memory of the operator's dotfile | a wrong secret costing one loud startup error instead of a quarantined episode |
| 25 | **NEW (CP-26), DONE (CP-27), examples-repo-side** — train.py polish the stranger run showed and CP-26's fix set (docs + example config + install.sh + README only, by the prompt's enumeration) deliberately did not touch: an aggregate summary line for collect and for rewards (71/72 and 1/71 were hand-counted — external F-27), a device argument or CUDA_VISIBLE_DEVICES passthrough instead of the hardcoded first-visible-GPU (F-34), and the closing sync pointer saying "estate-side" where the sync is workstation-side (F-29's second half — the run book is fixed, the last thing the script prints still misleads) | the examples repo's `example_project/train.py` (external repo — no library freeze involved; deferred only to keep CP-26's fix set to the enumerated files) | opened by CP-26; **[CP-27] all three landed**: `collect total:` and `reward distribution: k/N nonzero` aggregate lines (F-27), `--gpu N` → `CUDA_VISIBLE_DEVICES` before the first CUDA call with the nvidia-smi instruction in `--help` (F-34), and the closing printout sends the sync WORKSTATION-side naming `GSJ_VLLM_SSH_HOST` (F-29); RUNBOOK + FINDINGS rows updated in the same external commit | the script's own output matching the corrected run book |
| 26 | **NEW (CP-29), OPEN** — main's CI is RED at the published tag. The corpus-suite job fails 19/58 on CI's first contact with CP-20..CP-28 (nothing was pushed between CP-19 and CP-29, so five checkpoints of drift arrived at once), and the red decomposes into two independent layers, both measured at CP-29: (a) `ci.yml`'s corpus job still installs only `pytest pyyaml` and its comment still claims "no import of the root package" — both true when written at CP-18, both false since CP-24 (the taskbank phase needs pyarrow behind its lazy-import named error, exit 2; two tests import `gsj_rollout`) — 17 of the failures, plus a stale job label ("corpus suite (44)": the suite is 58); (b) with full deps the suite still fails 2/58 — `corpus/tests/test_taskbank.py:37`'s `MINIMAL_CFG` pins `serving_base_url: http://serve.invalid:8000/v1`, the exact `/v1` trap wishlist 21's CP-27 validator now rejects at load. The validator is right and doing its documented job; the CP-24 fixture predates it, and no checkpoint ran the corpus suite against the new config code because CI is where the two components meet and CI never ran. What a stranger sees: the RED BADGE fronting the README on GitHub AND on the PyPI landing page ("green means the fixtures still pass" reads as "broken"). At the tag itself the release-relevant jobs — root suite (143), wheel + packaged-pins install proof, mcp-service — are green; the red job's subject ships in no artifact | `corpus/tests/` (one fixture line) + `.github/**` (corpus-job deps, label, comment) — the first frozen at CP-29, the second untouched deliberately since a deps-only fix still leaves the job red on (b) | opened CP-29 by the push itself; invisible for five checkpoints precisely because the guard that would have caught it is the thing that never ran | the badge telling the truth again, and CI actually guarding the corpus suite's post-CP-24 closure — a ~5-line lift, and the first thing any next CP should do |
| 27 | **NEW (CP-29), OPEN** — 0.1.0's PyPI landing page immutably embeds the pre-publication README. The wheel bakes the README at build time; the tag sits at `1565813` (CP-28); and the CP-29 README fix lands in the CP-29 commit AFTER the tag — structural, not an oversight: the one CP commit must contain the report, the report must contain the publish results, so the tag cannot point at it. The project page therefore says "Until the first PyPI upload lands…" about itself, and "not yet published" about an examples repo that has a public remote, until the next version uploads (PyPI descriptions cannot be edited without a new version). The badge half of the page heals on its own when row 26 lands — the badge image is fetched live | none — the repo README is already fixed in the CP-29 commit; the cure is any next release (0.1.1+), PyPI's only mechanism | opened CP-29; structural to the prompt's own ordering (publish at Step 4, the doc pass at Step 5, one commit at the end) | the landing page telling the truth, at the cost of a version bump |

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
  drain rule is exercised against a real weight sync.
  **[CP-16] The bridge half exists**: trainer-owned, in
  `gsj-harness-rollout-server-examples/slime_bridge/` (ADR-0018) — the
  conversion to slime v0.3.0 `Sample`s with three enforced assertions
  (mask-before-ratio, sentinel rejection, `checks` trainer-side), tested
  against the real CP-09′/CP-07 bodies from a wheel install (ADR-0017
  fixed the wheel's pins — wishlist 11). Still owed by the loop CP:
  the optimization step itself, weight sync + policy-version declaration
  (P3/A-13), reward attach (every real body carries `reward: null`),
  cadence against the 19-attempt qualification rate, and A-26's
  on-estate Sample-surface verification. *Proves:* the loop
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
  **[CP-20] LANDED — M6a, and the starting-point hypothesis is answered
  NO by reading uni-agent @ its pin**: its trainer-side path generates
  into TransferQueue (entry point returns `None`, `Trajectory` is a
  gateway type, no padded batch exists in it) — it cannot consume
  externally-produced trajectories, so the direct bridge was the cheap
  one (`verl_bridge/`, external ADR-0003; the boundary needed zero
  changes here). What *Proves* asked for, it got: two trainers, one
  unchanged repo.
  **[CP-21] M6 CLOSED — the verl LOOP ran** (external ADR-0004): one
  real optimizer step in verl @ `1ae9455` on 110 collected episodes,
  synced back through the unchanged `serve-updated.sh` and proven by
  the zero-noise probe (0.000000 → 0.042168, 6541/6768 positions),
  second collection 8/8 qualifying and converting. This repo's diff:
  `docs/**` only — `staging/**` ran a second trainer as committed. The
  trainer-agnostic claim is **measured, not argued** (the dated M6
  section below).
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
