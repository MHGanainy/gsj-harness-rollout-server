# CHARTER — gsj-harness-rollout-server

The normative document. `CLAUDE.md` governs process; this file governs
content. Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not
retired; the fallback and the golden reference.

**The M3 adoption verdict lives in `docs/VERDICT.md` (CP-12): ADOPT
PROVISIONALLY, with the converting and reversing conditions named there.**

## 1. What we are building

A **rollout server for our corpus**. Given a task `(case, timestep,
prompt)` it runs our agent in an isolated sandbox with temporally-scoped
retrieval and emits a training-ready trajectory. Trainer-agnostic,
algorithm-agnostic, parameterization-agnostic. Episode execution and
trajectory reconstruction are NVIDIA Polar's, vendored by SHA; our code is
the thin shell that points Polar at our corpus, our MCP service, our pinned
pi, and our checks.

**The scope law**: "The rollout server owns: task → sandbox → agent →
trace. Nothing else. If it stores, schedules, scores, weights, versions,
or trains — it's out."

**Size budget**: our own code stays under **2,000 lines** (raised from
1,500 at CP-12, ADR-0012), excluding vendored Polar, tests, and the moved
components (`corpus/`, `mcp-service/`, `forgejo/`). A checkpoint that
pushes past it must stop and justify.

## 2. Why this repo exists

The predecessor works and is externally verified — the zero-CLI proof and
the recorded runs in `gsj-envloader-examples` are real evidence. But
roughly **1,800 of its lines are episode execution and capture**
(`task.py`'s checkout→run→harvest→reset lifecycle with docker bolted
inside it, `uniagent_driver.py`'s per-episode gateway sessions,
`collector.py`'s finalize pipeline), and that layer was expensive to
maintain: the G2 approved set had to be re-derived at nearly every image,
rename, or mount change; the capture transport changed three times; a
silently load-bearing parser dependency (sglang, H-41) once produced
gates-green but tool-free episodes; and dismantling the dev harness around
it took two dedicated checkpoints. This repo tests whether Polar can own
that layer. **We are not migrating; the predecessor stays alive.** If the
answer is no, we say so and stop (§9).

## 3. What we start with

**Carried over** (moved, not rewritten — landed at CP-01; measured own-code
lines, ADR-0002 is the boundary):

| component | lines (measured, CP-01) | what it is |
| --- | --- | --- |
| `corpus/` | 1,195 pipeline + 662 tests + 163 staging data files | the corpus source of truth + five-phase ingestion pipeline (taskbank phase deferred to CP-07, ADR-0003) |
| `mcp-service/` | 1,390 package + 1,615 tests + ~480 config/docs | the hosted streamable-http MCP service: per-episode JWTs, per-session cutoff clamp |
| `forgejo/` | 191 | git-host bring-up: case repos with `timestep-{T}` branches |
| pins / G2 tooling | 174 + 5 captured-evidence files | `derive_g2.py` byte-substitution derivation + the captured G2/G3/G6/G7 evidence; the `gsj-pin` generator turned out to be predecessor *library* code and stayed frozen there (ADR-0002) — the approved-set format is specified in `docs/checks-spec.md` |
| the corpus contract | 309 | `corpus-contract.md`, the normative corpus document — byte-identical copy at CP-01; v2 since CP-14 (split-by-directory, ADR-0015 — the first deliberate divergence, row 1) |

**Adopted**:

| component | how | what it owns |
| --- | --- | --- |
| Polar (NVIDIA) | vendored by SHA at CP-03; no releases, so pinned commit + recorded re-vendor recipe + carried patches | episode execution, sandbox lifecycle (start/stop/exec/upload/download), the model proxy, trajectory reconstruction (`prefix_merging`), the slime bridge |

**Written here** (the budget per module):

| module | budget (lines) |
| --- | --- |
| `pi_harness.py` | 50–**350** (ADR-0014; 50–150 as a CP-00 estimate) |
| `receiver.py` | 50–100 |
| `checks.py` | 250–**528** (ADR-0009 → ADR-0013 → ADR-0014 → ADR-0021 — the landed size exactly, machine-checked by the suite) |
| `config.py` | ~100 |
| `client.py` | ~80 |
| `cli.py` | ~60 |

Sum 490–740 — the 1,500 ceiling (2,000 since ADR-0012) is headroom, not
a target.

**[CP-10] Budget status: 1,480 / 1,500, and the headroom is gone.**
`wc -l gsj_rollout/*.py` = 18 + 189 builder + **367 checks** + 175 cli +
123 client + 241 config + 224 pi_harness + 143 receiver. The law (≤ 1,500)
holds; the per-module allowance above does not — `checks.py` is at 367
against 150–250, having absorbed the logprob discipline, the G5 backstop,
and the reasoning the checkpoint required in-docstring. CP-11 must land
six gates and four hashing conventions in the remaining 20 lines, which
is not possible: it will either move the reasoning wholesale into
`docs/checks-spec.md` leaving one-line pointers in code, or raise
`checks.py`'s allowance in an ADR. Flagged now rather than discovered
then — this is the row the "thin shell" premise is judged by (§9).

**[CP-11] Budget status: 1,438 / 1,500 — both cures applied, and the
honest projection stays tight.** The prose migration recovered 82 lines
(`checks.py` 367 → 285, every rule body byte-identical — the one code
change is ADR-0010's declared `policy=None` seam — the 59 pre-existing
tests passing unmodified); CP-11's own sanctioned work added 40 elsewhere
(`config.py` +27: the structural timestep and the `checks:` section;
`pi_harness.py` +13: the leak fix). `checks.py`'s allowance is raised to
**250–420** in ADR-0009 — the module absorbed the whole evidence law of
both wire legs, and splitting it would manufacture rule-family drift.
The 1,500 law is untouched and still the binding number: CP-11b's gates
are estimated at +120–140, which projects to ~1,560–1,580, so CP-11b
must recover ~60–80 lines (candidates named in ADR-0009: `cli.py`'s
operator prints, `builder.py`'s prose once its freeze lifts, `config.py`
comments) or stop-and-justify per this section's own law.

**[CP-11b] Budget status: 1,496 / 1,500 — lawful, and thin, said
plainly.** Three measured movements (every endpoint reproducible from
`git show HEAD:` vs the tree — the first draft of this paragraph
misattributed the per-pass endpoints and the CP's own adversarial pass
caught it): (1) pre-gate banking −55 (`cli.py` 175→163, `config.py`
268→249, `builder.py` 189→165 — all three ADR-0009 candidates needed,
prose only, suite green); (2) the gates +135 (`checks.py` 285→420, the
top of ADR-0009's 120–140 estimate), putting the total at 1,518 — over
the law mid-CP, exactly the scramble Step 1 exists to prevent — cured by
a second prose pass −21 (`checks.py` 420→408 gate docstrings to spec
pointers, `config.py` 249→246, `builder.py` 165→159); (3) the
verification-forced never-raise fixes, net −1 (`checks.py` 408→407: +4
guard lines paid by −5 further prose). Final: 18 + 159 builder + 407
checks + 163 cli + 123 client + 246 config + 237 pi_harness + 143
receiver = **1,496**. `checks.py` sits at 407/420 (ADR-0009); four lines
of law headroom remain, so the next in-`gsj_rollout/` addition of any
size must recover first — CP-12 is a verdict CP and should need none.

**[CP-12] Budget status: 1,496 / 2,000 — the law raised by ADR-0012, at
a verdict CP that needed none of the new room.** The original 1,500 was a
CP-00 guess against a scope that had not yet met hostile-content guards
on both wire legs, four hashing conventions with pins loading, or the
validating builder subclass; the law was honored under pressure (CP-11
banked 82 lines a checkpoint ahead of the gates' landing; CP-11b cured a
mid-CP 1,518 at that moment, not at the end), so the raise is a
re-estimate, not an amnesty. The headroom is
FOR the four wishlist items, the ADR-0003 taskbank landing, and gates
G1/G4/G6 if their blockers clear (`docs/VERDICT.md` §wishlist); the same
stop-and-justify discipline applies at 2,000, and §8/§9 track the raised
number.

**[CP-13] Budget status: 1,642 / 2,000 — the first spend of the ADR-0012
headroom, on exactly what the raise was for.** Four measured movements,
all additions (`git show HEAD:` vs the tree): `checks.py` 407 → 460 (G1 +
G7's settings clause + five vocabulary constants + `PinsConfigurationError`),
`config.py` 246 → 280 (`prompt_source` render parameters, their type
validation, the H-41 mirror field), `pi_harness.py` 237 → 258 (the settings
echo), `receiver.py` 143 → 181 (the pins-failure seam: origin-classified
500s and the two-phase atomic write). Total 18 + 159 builder + 460 checks
+ 163 cli + 123 client + 280 config + 258 pi_harness + 181 receiver =
**1,642**. `checks.py` at 460 exceeded ADR-0009's 420 top; per §3's own law
the excursion is justified in **ADR-0013** (allowance 250 → 480, the
ADR-0009 rationale unchanged, the remaining headroom named for G6's CP-04′
rule) — not silently absorbed. The receiver's +38 is larger than the
seam alone because the CP's adversarial pass measured three further
failure shapes the first cure missed (§the report's verification).

**[CP-13a] Budget status: 1,746 / 2,000.** The addendum's echo and the
census clauses it unblocks cost `pi_harness.py` +64 (258 → 322: the
workspace probe, the credential strip, the shared echo) and `checks.py`
+37 (460 → 497: `check_workspace` plus five vocabulary constants), plus
`receiver.py` +3 (181 → 184, the duplicate-session_id fix CP-13's own
fresh-eyes critic found). `checks.py` passed ADR-0013's 480 and
`pi_harness.py` had stood above its CP-00 estimate since CP-07 without an
ADR; **ADR-0014** settles both (520 and 350) rather than letting one
module's overshoot be formal and the other's silent. The law itself is
untouched.

**[CP-14] Budget status: 1,773 / 2,000.** Two measured movements, both
small (`git show HEAD:` vs the tree): `config.py` 280 → 295 (the `split`
render parameter, its vocabulary validation, and the honest-absence
docstring — ADR-0015) and `checks.py` 497 → 509 (the `TR3` split-label
tripwire plus `ALLOWED_SPLITS`; +3 of that is the CP's own adversarial
pass making TR3 presence-based so an explicit null no longer waives it),
leaving `checks.py` at 509/520 (ADR-0014). The corpus pipeline absorbed
the split-by-directory rework outside the law (excluded component, §1);
nothing else in `gsj_rollout/` moved. Total 18 + 159 builder + 509
checks + 163 cli + 123 client + 295 config + 322 pi_harness + 184
receiver = **1,773**.

**[CP-16] Budget status: 1,782 / 2,000.** One measured movement:
`checks.py` 509 → 518 — the pins resolver seam only (`import os`, the
three path constants, the env-override → checkout → packaged-copy
conditional; ADR-0017), no rule changes, leaving `checks.py` at 518/520
(ADR-0014, two lines of headroom). The bridge itself is **zero lines
here** — it is the trainer's code, in
`gsj-harness-rollout-server-examples` (ADR-0018), which is the scope law
working as written: M4's trainer-side machinery never enters this count.

**[CP-18] Budget status: 1,782 / 2,000 — unchanged, and CI configuration
is outside the count.** Nothing in `gsj_rollout/` moved this checkpoint
(the DoD's frozen-path diff is empty). The one file that landed,
`.github/workflows/ci.yml`, is configuration for a hosted runner: it
declares which of the existing suites run and how, ships no importable
surface, and cannot be called by anything this repo produces. §1 law 2's
exclusion list is enumerated and closed — vendored Polar, tests, the moved
components — and CI config is not in it, because no such file existed when
it was written; this paragraph is the ruling that puts it on the same
footing rather than a claim that it was already there. The reasoning: the
budget exists to say how thin the shell is, and the number stops saying
that the moment it also counts the automation that runs the shell's tests.
A later CP that amends the enumeration itself should cite this paragraph.

**[CP-19] Budget status: 1,784 / 2,000 — and `checks.py` is now exactly on
its own ceiling, which is the number that matters.** The +2 is ADR-0019's
pins signal: `import warnings`, a guard, and a two-line `UserWarning` for
the case where resolution falls through to the wheel's packaged copy,
partly paid for by collapsing the resolver's four-line comment to two (+5 /
−3): the three lines deleted stated at rest what the warning now states at
runtime. No rule body moved and the suite is
unchanged at 129. `LICENSE`, `.github/workflows/release.yml` and
`pyproject.toml`'s metadata are outside the count on the [CP-18] footing
above — none ships an importable surface.

**The finding this creates, stated here because §3 is where budgets are
judged**: `checks.py` sits at **520 / 520** (ADR-0014). ADR-0014 reserved
the 23 lines above 497 for G6's tokenizer-free ids rule "and nothing
else"; CP-16 spent 9 of them on the resolver seam without noting the
earmark, and CP-19 spends the last 2. *[CP-23 correction, measured from
`git show`: the account here was incomplete — CP-14's TR3 tripwire took
the FIRST 12 (497 → 509) before CP-16's 9 (509 → 518) and CP-19's 2
(518 → 520); three checkpoints eroded the earmark, not two.]*
**G6 can no longer land inside 520.**
It is owed (ADR-0011) and unblocked (CP-04′ pinned
`g6_expected_tail_ids`), so whoever lands it must raise the allowance in an
ADR or bank prose to `docs/checks-spec.md` the way CP-11 did — a
stop-and-justify per this section's own law, flagged now rather than
discovered then. Wishlist row 18.

**[CP-23] Budget status: 1,792 / 2,000 — the ceiling resolved in the
ordered way, and the allowance now machine-checked.** Both mechanisms the
finding above named, in order and measured (`git show HEAD:` vs the
tree): the **banking pass first** — the CP-11 migration re-applied to the
gate docstrings that had crept back to 2–4 lines across CP-13/13a/14,
every one compressed to its spec-pointer form, with the one genuinely
un-migrated fragment (TR3's presence-based clause) moved into
`docs/checks-spec.md` and the G3 caveat's spec framing corrected in
place — recovered
**23 lines (520 → 497)**, AST identical after docstring strip, all 129
tests unmodified. The arithmetic, stated before the rule was written: G6
per ADR-0011's design measures **31 lines**; 497 + 31 = **528 > 520**, so
the two do not close and **ADR-0021** raises the allowance — to **528,
the landed size exactly, zero headroom by design**, with the ceiling
enforced by a suite EQUALITY tripwire
(`test_checks_allowance_is_machine_checked`) so ADR-0014's
silently-eroded-earmark failure — three CPs (14/16/19), 12 + 9 + 2 = 23
lines, the corrected account in the [CP-19] paragraph above — cannot
recur in either direction. G6 landed inside it:
`checks.py` 497 → 528, nothing else in `gsj_rollout/` moved, total 18 +
159 builder + 528 checks + 163 cli + 123 client + 295 config + 322
pi_harness + 184 receiver = **1,792**. The `cli.py`/`config.py`/
`builder.py` prose-recovery lift went **unused** — the tree had 216 lines
of law headroom and the module ceiling was the binding constraint, so no
logic-adjacent file was touched at all. Wishlist row 18 closes.

**[CP-25] Budget status: 1,828 / 2,000 — one module moved, for the
consumer surface.** `config.py` 295 → 331 (+36, measured `git show HEAD:`
vs the tree), all of it Step-2 material: four defaults that were required
fields (`runtime.image` — the published pinned harness image;
`harness.tools_allowlist` — the G3-pinned roster; `harness.artifacts_dir`;
`builder.end_of_turn_token_id` — the A-15 pin with its derivation stated),
three section-level `default_factory`s so `runtime:`/`harness:`/`builder:`
may be omitted wholesale, and the comments that say where each value came
from — the ~100-line CP-00 estimate for the module was passed long ago and
the (ADR-0012-raised) law is the binding number. `checks.py` untouched at
528/528 (the ADR-0021 equality tripwire passed unmodified). Total 18 +
159 builder + 528 checks + 163 cli + 123 client + 331 config + 322
pi_harness + 184 receiver = **1,828**.

**[CP-27] Budget status: 1,910 / 2,000 — two modules moved, all of it
strangerward.** `config.py` 331 → 398 (+67): wishlist 21's two validators
(the `/v1`-suffix reject and the gateway port/public_url agreement check,
with an explicit-scheme guard the CP's own adversarial pass forced — a
scheme-less `IP:8100` parses port-less and the port check would have
misdiagnosed it as "port 80"), F-25's null-section normalizer
(`_null_sections_to_empty`, model-driven rather than a hardcoded section
list, dict-typed sections included so a gutted `user:` still loads), and
F-23's optional `estate.model_revision` pin. The wishlist estimated ~6
lines; the executable checks ARE about that size — the excess is the
error messages themselves (three to five lines each, naming the key, the
measured runtime symptom, and the fix — the message a stranger can act on
is the deliverable, per CP-26's finding that both traps fail as bare 404
/ connection-refused) plus the house-style comments citing the findings.
`cli.py` 163 → 178 (+15): the `__main__` guard (wishlist 19), `flush=True`
on the six serve-session prints (F-20), and the absolute
`vendor/polar/.venv` path via the already-computed repo root (F-21's
one-line half). `checks.py` untouched at 528/528 (the ADR-0021 equality
tripwire passed unmodified). Total 18 + 159 builder + 528 checks + 178
cli + 123 client + 398 config + 322 pi_harness + 184 receiver =
**1,910**, headroom 90.

**[CP-30] Budget status: 1,944 / 2,000 — one module moved, the thinking
knob.** `config.py` 398 → 432 (+34): ADR-0024's `harness.thinking`
validator — pi's own 7-value level list, the rejection naming the silent
clamp (CP-28: pi maps any unknown `--thinking` value to `"off"` with no
error, so a typo collects a control run wearing the measurement's
label), and a `mode="before"` leg for YAML 1.1 — pyyaml parses bare
`off`/`on` as BOOLEANS, so the natural spelling of the default would
otherwise die as a type error naming no level, while bare `on` is
exactly the clamp typo and now gets the clamp message. The executable
checks are ~6 lines; the rest is the message (the CP-27 standard: key +
measured symptom + cure) and the house-style comments. `checks.py`
untouched at 528/528 (the ADR-0021 equality tripwire passed unmodified —
the per-mode G6 re-pin is pins DATA, zero code). Total 18 + 159 builder
+ 528 checks + 178 cli + 123 client + 432 config + 322 pi_harness +
184 receiver = **1,944**, headroom 56.

**Deliberately dropped** (and whose problem each becomes):

- the store — trainer's problem
- the loader (`ready`/`mix`/leases/serve accounting/SPI) — trainer's problem
- staleness tracking — trainer's problem
- collation — trainer's problem
- `GsjCaseTask` — Polar's problem
- `uniagent_driver` — Polar's problem
- `collector` — Polar's problem

## 4. What we assume

Every new assumption gets a row here immediately. **Unverified is not
false** — a reported defect stays UNVERIFIED until a checkpoint verifies
it.

| # | assumption | basis | if false |
| --- | --- | --- | --- |
| A-1 | Polar's `prefix_merging` reconstructs multi-turn token streams correctly | **RESOLVED — empirically on BOTH pairs; the H200 (the governing platform, A-16) at CP-09′.** [CP-09′] Against `docs/golden/h200/` on the same triple with the golden's own instruction bytes: `loss_mask` semantics exact on both traces (zero tolerance satisfied — 2 sampled spans == 2 assistant turns each, opens at r=0, closes at stream end), `prompt_ids` byte-identical (2965/2965), decode-fidelity EXACT-BYTES at mask==1 on both traces, glue framing constants byte-identical across traces with the pinned G6 tail, and the logprob replay run **as written** through the serving engine — bit-deterministic (rerun Δ exactly 0.000000), with the sole finding the platform's capture-path numerics floor (present identically on the predecessor's Polar-free capture); **nothing attributable to Polar** (`docs/reports/CP-09prime.md`, verdict PASS WITH FINDINGS). **At CP-09 — empirically, Mac pair** (the behavioral half; CP-05 verified the structural half): against `docs/golden/mac/` on the same triple, `loss_mask` semantics matched exactly (2 sampled spans == 2 assistant turns, boundaries aligned, per-span decode-fidelity exact on both traces), `prompt_ids` byte-identical to the golden's `prompts` (2965/2965 — the A-1 retokenization class is empirically clean), glue template constants identical across stacks, and logprob capture agreed with the predecessor's capture at mean&nbsp;|Δ|&nbsp;=&nbsp;0.000114 on identical-context positions (comparison table + findings: `docs/reports/CP-09.md`; the H200 pair CP-04′/CP-09′ re-confirms on production numerics). **LINE-VERIFIED at CP-05** (algorithm; token fidelity was CP-09's question): the retokenization guarantee holds in code — assistant tokens come only from engine-sampled ids, never from a prompt re-rendering (`record_utils.py:82-107`, `prefix_merging.py:337-353`; no tokenizer anywhere in the builder); grouping is a strict token-id prefix test (`prefix_merging.py:399`); the interstitial split implements the paper's §3.4.2 exactly (`prefix_merging.py:326-334`). Adversarially re-verified (6-agent pass, 17/18 claims confirmed, 1 scope-corrected). **But every discovered failure mode degrades silently to `status=COMPLETED`** — truncation, chain degeneration, EOT misdetection, filter amputation, `choices[0]`-only capture, discard-and-reprompt — catalogued in `docs/checks-spec.md` §silent-degradation; verdict: **GO WITH CONDITIONS** (CP-05 report) | CP-09 fidelity fails against the golden reference with no fix in our code → abandon (§9) |
| A-2 | Polar's proxy handles pi 0.83.0's traffic unmodified: **RESOLVED — CONFIRMED at CP-06** (stub backend, no GPU; engine-side fidelity stays CP-09's); **CP-07 adds a real-engine caveat**: pi sends `tool_choice: auto`, which vLLM/vllm-metal reject with HTTP 400 unless the engine is served with `--enable-auto-tool-choice --tool-call-parser hermes` — not a proxy translation failure (the proxy forwards `tool_choice` untouched), an engine-config requirement the harness cannot set; the first CP-07 submit ERRORed "no completions" until the engine was restarted with those flags (echoes the predecessor's H-41 sglang-parser dependency from the vLLM side) | CP-06 live: pi 0.83.0 (predecessor pins, ADR-0008 argv) through the gateway completed a 2-turn episode, `chains_total == 1`, zero translation errors. Measured facts: (a) pi **always sends `stream: true`** — the gateway forwards non-streaming (`proxy.py:121-122`) and replays the backend response to pi as ONE synthetic SSE delta chunk (`server.py:736,771-810`); pi 0.83.0's parser accepts that shape (verified twice: direct against the stub speaking the same shape, and through the proxy); (b) the transformer's only mutation on pi traffic is `max_tokens` added as a copy of `max_completion_tokens` (original key retained, `openai_chat.py:15-16`) — the system-message fold is a no-op because pi sends exactly one top-of-list system string; `messages`/`tools` byte-identical across original → transformed → wire (three-way diff, `spike/wire_diff.py`); (c) engine-prepare deltas are additive capture params only (`+logprobs`, `+return_token_ids`, `+top_logprobs: 0`, `stream→false`, `−stream_options`); (d) the capture keying works because our harness substitutes `$OPENAI_API_KEY` (= the session id) into pi's `models.json` `apiKey` — a harness with a static apiKey would fragment capture into per-request orphan sessions (builder then ERRORs "no trainable completions" — loud) | n/a (resolved); a translation failure on a real engine dialect at CP-09 would reopen it |
| A-3 | pi package identity: **RESOLVED** — same tool; `@mariozechner` deprecated → `@earendil-works`; Polar's preset pins 0.67.68, we run 0.83.0 | npm deprecation trail traced | n/a (resolved); if the rename hid a fork, the CP-05 source audit catches it |
| A-4 | the per-episode cutoff token is injectable via `run_steps()` — **RESOLVED at CP-07**: minted host-side in `run_steps()` (stdlib HS256, claims `{case_id, timestep, episode_id, exp}`, `episode_id` = the Polar session id), rendered into `.pi/mcp.json` as `<mcp_base>/mcp/<token>`, enforced server-side by the MCP service from **verified claims only** | Polar's episode API takes per-episode parameters; **CP-07 live**: the CP-04 triple ran end to end, every `mcp_gsj_*` call authorized under its own token's `timestep: 12` (`docs/polar/pi-corpus/mcp_authority_log.jsonl`), every `search_case` result page ≤ 12, and the adversarial probe (mutate `timestep` 12→18 keeping the signature, call the service from inside the sandbox) was rejected HTTP 401 `token invalid: Signature verification failed` (`docs/polar/pi-corpus/adversarial_probe.txt`) — the agent can read the token but cannot forge its scope | n/a (resolved); the cutoff rode `run_steps()` exactly as assumed, no fallback channel needed |
| A-5 | the callback payload is sufficient for `checks.py` (token ids, `loss_mask`, logprobs, metadata) — **RESOLVED at CP-08**: the receiver now consumes it for real — the CP-07 body (fetched `SessionResult`, status/error intact) round-trips through `POST /callbacks/session_result` → `checks.validate_session_result` → persisted verbatim, and the client re-validates the same bodies from `GET /rollout/task/{id}`; doctored bodies (ERROR status, builder findings) quarantine with findings attached | Polar emits training-ready traces for its slime bridge; **CP-05, verified at source**: the callback body is `SessionResult.model_dump(mode="json")` (`node.py:860`) carrying full traces (token ids, `loss_mask`, logprobs, messages, tools, `finish_reason`), `reconstruction_stats`, and a writable metadata channel — builder-subclass keys survive to the callback verbatim and on into slime `Sample.metadata["polar"]` (`adapter.py:141-160`); the endpoint revalidates pydantic shape only (`rollout/server.py:170-173`). **Caveat**: per-completion records do NOT ride the callback (only the `completion_metadata` extracts in trace metadata), so session-level checks must run builder-side — the receiver alone cannot see them. **CP-06, pi-side evidence** (`docs/polar/pi/callback_session_result.json`): with a token-id-bearing dialect the payload is fully populated end to end — `prompt_ids` 2734, `response_ids` 149, `loss_mask` aligned (119×1 + 30×0), `response_logprobs` aligned 149 with `0.0` only at mask-0 interstitials, the 7-tool roster on the trace, `reconstruction_stats` carrying the whole G7 conjunction — everything `checks.py` needs for the trace-level gates rides the callback | n/a (resolved); the CP-05 caveat stands — per-completion records do NOT ride the callback, so session-level checks stay builder-side (the CP-07 subclass) |
| A-6 | slime can run OPD against Polar traces — **RESOLVED at CP-17: CONFIRMED, with the qualification stated.** Real slime v0.3.0 + Megatron (in `slimerl/slime:v0.3.0`, GPU 5, disjoint from the serving GPU) took **one real optimizer step** on 27 episodes collected through our path and converted by the CP-16 bridge: `global_batch_size 27`, `train/grad_norm 0.4513` (non-zero, below `clip_grad 1.0`, so unclipped), `train/loss 4.909e−06`, TIS live (`tis 0.99985`) consuming our captured `rollout_log_probs`, loss taken under the builder's `loss_mask` verbatim. The qualification: the regime run was **GRPO, not OPD** — the loop's question was whether slime consumes these traces and takes a real step, and OPD's teacher-scoring half (the predecessor's `opd/`) adds an evaluator, not a new consumption path. Advantages were non-degenerate because the CP-17 reward attach made them so (1 of 27 episodes at reward 1.0) | Polar ships a slime bridge; **CP-17 ran it end to end** (`docs/reports/CP-17.md`) | n/a (resolved). What the resolution does NOT cover: multi-step training, concurrency between collection and training, weight sync at cadence, and OPD's teacher leg specifically |
| A-7 | **RESOLVED at CP-02 — partially confirmed**, per defect: **D1 leak CONFIRMED, worse than reported** — upstream at the pin has *no* non-agent completion filter at all (the whitelist was fork code; every auxiliary harness call becomes a trainable trace carrying session reward); **D2 PARTIAL** — vLLM `-9999.0` flows to the trainer unvalidated at the pin (confirmed; zero value-level logprob checks upstream), but `_logprob_integrity` is fork-only and the interstitial `0.0` is mask==0-only (benign, matches our rule); **D3 CONFIRMED end-to-end** — statuses are {COMPLETED, TIMEOUT, ERROR}, `finish_reason=="abort"` is handled nowhere, a mid-chain abort presents a *clean* chain snapshot; **D4 REFUTED for upstream** — reasoning masking is fork-only, the pin emits all-ones `loss_mask` unconditionally | commit patches read + upstream line-verified at `f0e8343a` (CP-02 report, ADR-0004) | D1/D3 become carried patches P1/P2 at CP-03; the sentinel guard lands in `checks.py` as an **explicit threshold rule** — the finite-and-≤0 rule does NOT auto-reject `-9999.0` (spec corrected at CP-02) |
| A-8 | vendoring a release-less branch is sustainable — **RESOLVED at CP-22: HOLDS, residuals named.** The second vendor ran (the re-vendor rehearsal, `docs/reports/CP-22.md`): upstream `stable` unmoved at `f0e8343a` (surveyed via `gh api` — zero commits since the pin, still no tags or releases; the `polar` dev branch frozen since 2026-06-06 at 80 ahead / 3 behind), so the rehearsal re-vendored to the SAME SHA and exercised the recipe end to end: fetch SHA-verified, tree re-extracted, all three patches applied CLEAN by the script (zero rejects), the re-vendored tree **byte-identical to the committed tree** (`git diff HEAD -- vendor/` empty, `prefix_merging.py` mode 100644 kept), and the reverse-apply walk landed on the pristine pin exactly (CP-03's fidelity standard held in both directions). Measured cost: **~2 minutes** for the mechanical loop (fetch → extract → patch → verify → venv rebuild → vendored suite, warm uv cache), ~15 minutes with the full five-suite + pins verification — the half-day budget is all patch-re-anchoring contingency, none of it mechanism. **The named risk was priced, not just named**: with today's `polar`-branch refactor (+49/−156 on `prefix_merging.py`) simulated as landed in a scratch tree, P1/P2/P3's **source hunks all apply clean** — P2's single-`status="COMPLETED"` anchor and P1's stats-dict anchor both survive the refactor — and only P1's two fixture-marker hunks reject, in test files the refactor rewrote (mechanical re-anchoring, not re-porting). Residuals: (a) no MOVED-pin re-vendor has run — an upstream delta under the patches stays estimated, now well-bounded; (b) the refactor diagnostic is a point-in-time measurement of an unlanded branch — what eventually squash-lands may differ, and the vendored suite at that future pin is the real gate; (c) one recipe defect was found and fixed (the venv-rebuild step omitted the A-14 `gsj_rollout` install — followed verbatim it broke the registry seam, measured live as `ModuleNotFoundError`; REVENDOR.md corrected) | pinned SHA + recorded re-vendor recipe + carried patches; **CP-03 evidence**: first vendor executed at moderate cost (~one working day incl. patch adaptation, component venv, smoke run; all three patches apply clean from `vendor/apply_patches.sh`; upstream suite 175 passed / 3 pre-existing failures); **CP-22 evidence**: the recipe followed by a second executor reproduced the committed tree byte-for-byte, same 175/3 suite split, all approved pins reproduced | n/a (resolved); a re-vendor whose measured cost balloons — the moved-pin case, or the refactor landing in a shape the diagnostic did not price — reopens it and re-decides the dependency posture in an ADR |
| A-9 | the carried components transfer unmodified | they were built host-portable behind the corpus contract; predecessor law forbade host-layout dependence in library code | fixes happen here (the predecessor is frozen) and the touched row flips to GAP until cured |
| A-10 | reward sparsity at demo scale is a method/scale property, not infrastructure | the predecessor's recorded runs show the same | still not a rollout-server defect — out of scope by the scope law |
| A-11 | **Apptainer deferred** — Polar supports it natively; we stay on Docker so the CP-09 comparison has one variable | Polar's README lists the Apptainer runtime; the predecessor was Docker-only, so Docker is the controlled variable | revisit on a cluster without a daemon; law 5 keeps `gsj_rollout/` runtime-agnostic so nothing needs rewriting |
| A-12 | our pi harness makes no auxiliary (non-agent-loop) LLM calls through Polar's gateway — **P1's status RESOLVED at CP-06: INERT against pi**; the no-auxiliary-calls observation holds on the spike episode (real corpus episodes re-measured at CP-09/CP-10) | CP-06 measured, wire-level: **every request pi 0.83.0 emits carries a bare `stream` key** (pi-ai's openai-completions client streams unconditionally; `stream: true` on all captured calls), and agent turns additionally carry a system message, a non-empty `tools` array, and ≥2 messages — all four of P1's drop conditions independently defeated, and the `key in request` membership test (`record_filters.py:108`) means even an auxiliary single-user-message call through the same client is KEPT (executed against the real filter: `spike/p1_verdict.py` — genuine turns kept ✓, pi-dialect aux call kept = false negative, only a stream-less bare call drops, and no pi 0.83.0 path emits one). **P1's protection is illusory for pi; it stays carried for non-pi harnesses and as the empty-choices guard.** Completions-vs-turns: 2 LLM calls in pi's `--mode json` transcript = 2 captured records = `raw_completions_total` (both direct and through Polar) — no auxiliary calls on the trivial episode. The defense obligation moves to the CP-07 builder subclass: a pi-dialect agent-shape check (~10 lines, sized in the CP-06 report) rejecting any completion whose `original_request` lacks the agent-turn shape (system + tools + `stream`), plus `completion_filter.excluded == []` | an auxiliary call on a real corpus episode would become a well-formed `chain_length=1` trainable trace carrying full session reward (fork-measured density up to 27%) with NO filter to stop it — the subclass check is mandatory, not optional |
| A-13 | until carried patch P3 (per-turn `policy_version` stamping) is active, the trainer drains all in-flight sessions before every weight sync — **[CP-17] MET AT A REAL SYNC, BY CONSTRUCTION.** The loop is strictly serialized (collect → train → sync → collect), so at the sync boundary the drain was already complete, and it was **verified rather than assumed**: zero episode containers on `gsj-staging-net` and the engine reporting `Running: 0 reqs, Waiting: 0 reqs`. The sync itself is a stop-then-start of the engine (`staging/serving/serve-updated.sh`), which makes the drain point physical. **What this does NOT establish**: that the rule can be honoured under concurrency. A real run overlaps collection with training, and then the rule needs an actual drain barrier or P3 live to detect a session that spanned the sync — one serialized sync exercises the *situation*, not the *mechanism*. Decision recorded in external ADR-0002: at ONE sync, declaring `policy_version` adds a claim no consumer checks; the second sync is where that stops being true. **[CP-21] The second real sync (a different trainer's export through the same `serve-updated.sh`): nothing differed** — drain again satisfied by construction (serialized loop) and again verified rather than assumed (zero episode containers, engine idle at the stop). Two syncs, both serialized: the *situation* now has two data points; the *mechanism* (a drain barrier or P3 live under concurrency) still has zero, and "the second sync is where that stops being true" refers to a second sync *within one run's collection window* — which neither CP has executed. **[CP-22] Upstream signal worth recording**: the unlanded `polar`-branch refactor grew a `policy_version` CONSUMER — `_top_level_scheduler_metadata` promotes `{group_id, policy_version, rollout_step}` from record metadata to trajectory-level scheduler metadata — while still shipping no producer (`gateway/storage.py` untouched by the refactor, P3 re-applied clean). If that lands, P3's stamp stops being a fork-only convention and becomes the key upstream's own scheduler layer reads | D5 audit: at the pin a session spanning a weight sync is assembled as COMPLETED with a clean chain snapshot and only the stale submission-time version — invisible on the wire and retroactively unauditable; CP-03: P3 landed inert (stamping + persistence fix present and verified; nothing declares versions yet — confirmed no `policy_version` key on a real persisted record) | mixed-weight traces train silently; the receiver cannot catch what the capture layer never records (the declared limit of law 6) |
| A-14 | `vendor/polar/.venv` (Python 3.12) can host `gsj_rollout` when CP-06 wires the `import_path` harness — the dependency points Polar→us, and our core deps (pydantic/httpx/pyyaml) are a strict subset of Polar's five (fastapi/uvicorn/httpx/pydantic/pyyaml) | ADR-0005; both dependency sets read from the two pyprojects at CP-03 | a version conflict forces re-deciding the environment split (dedicated harness venv, or loosening root pins); the root package never grows Polar deps either way |
| A-16 | the Mac golden pair is a **comparison baseline, not a production artifact**: `docs/golden/mac/` anchors CP-09's Mac-pair fidelity verdict only; the H200 pair (CP-04′/CP-09′) re-establishes the production numbers | CP-04: the Mac estate is adaptation-bearing (published-port networking, vllm-metal/MLX bf16 serving of the mlx-community conversion, amd64 pi image under emulation, wall-timeout 900) — every adaptation enumerated in `docs/golden/mac/MANIFEST.md`, and CP-04′ needs none of them. **Corrected en route**: the G-hashes are NOT Mac-path-specific as this row's first draft assumed — docker-mode execution keeps host paths out of the prompt (G2 is the `/workspace` singleton `f56e8a6e…`), and the whole pins file regenerated byte-value-identical on the Mac; the Mac-specific surface is the *numerics*, not the pins (MLX bf16: 20/292 mask-1 logprobs exactly `0.0` — row 27). **[CP-04′] The counterpart half is now real: the H200 governs the numerics, and the prediction held.** `docs/golden/h200/` exists (same triple, predecessor stack, native CUDA — zero Mac adaptations needed, exactly as this row predicted: no emulation, no published ports, no serving substitution, wall-timeout 480 stood), collected under a served snapshot whose weights == the codec snapshot (the Mac's served/codec split does not exist on the H200). Why the H200 governs, made concrete this CP: the numerics differ where only platform can differ — the row-27 exact-`0.0` artifact recurs on CUDA vLLM bf16 (16/258 on the golden; up to 24.9% on a repetitive-loop episode via our stack), so the Mac's MLX numbers were never generalizable, and every G-hash reproduced identically across estates while the numerics did not — the pins are estate-invariant, the numerics are the platform. **[CP-09′] The counterpart CLOSES — the governing verdict exists**: PASS WITH FINDINGS on the H200 pair, nothing attributable to Polar (`docs/reports/CP-09prime.md`); the two pairs' verdicts agree in kind, so the if-false branch (verdict divergence) never fired. The governing numbers, as measured: replay-as-written beyond the contract's 0.005/0.05 bounds on BOTH stacks' captures symmetrically (golden mean |Δ| 0.005246, collected 0.007141; the replay path itself bit-deterministic at exactly 0.000000), capture-vs-capture on identical contexts 0.003672 mean (the Mac's 0.000114 was an MLX-sequential property — CUDA cross-request numerics ≈ 30× noisier), exact-`0.0` rates 6.2%/7.3% within the 0.25 allowance | if the two pairs' verdicts diverge, the platform (engine numerics, emulation) is entangled in the comparison and the H200 pair's verdict governs; the Mac pair then only screens for gross structural defects |
| A-21 | gsj rollouts pin `generation_prompt_glue_ids` in the builder config whenever the served chat template appends generation-prompt-only glue — for Qwen3 with `enable_thinking: false` this is the empty think block `[151667, 271, 151668, 271]` (`<think>`,`\n\n`,`</think>`,`\n\n`) — **added and RESOLVED-in-practice at CP-07** (ADR-0007). **[CP-04′] The condition no longer obtains on the H200 estate**: the served template is the symmetric `qwen3_training.jinja` (Direction A), which appends NO generation-prompt-only glue — the H200 config leaves the ids UNSET and two fresh episodes merged natively (`chains_total == 1`, full G7 conjunction, `glue_stitched: 0` — `docs/polar/h200-stitch/`). The assumption stands as written for any future asymmetric template; the stitch code stays in place, dormant, as that fallback | CP-07 live: the first real multi-turn corpus episode reconstructed as **2 chains** because the Qwen3 no-think template appends the empty think block to each generation prompt but NOT to the history re-render, so consecutive pi prompts are never token-prefix-stable and the vendored grouping (`prefix_merging.py:399`) opens a fresh chain per turn (the S4 shape, silently COMPLETED). The subclass normalizes `prompt_ids` before grouping (strict-extension stitch, `glue_stitched` recorded); with the ids pinned the same episode merged to `chains_total == 1`, 441 sampled + 6755 interstitial tokens, logprobs aligned. The stub never surfaced this (byte tokenizer, no template) — it took an end-to-end episode | an unpinned glue on a real multi-turn run degrades every episode to per-turn chains that look COMPLETED; the receiver's `chains_total == 1` catches it (fails closed), but no trace merges until the ids are pinned — template-specific, re-derive per served tokenizer |
| A-22 | **thinking-ON is out of bounds for the ADR-0007 stitch, not merely untested** — `harness.thinking` stays `off`; flipping it needs Direction A (a symmetric served template), not a longer glue list | CP-10 template investigation: with thinking enabled the Qwen3 template's history branch re-renders each assistant turn *without* its reasoning content, so the per-turn divergence is **variable-length**, not the fixed 4-token empty-think pair the stitch is pinned to. `ValidatingPrefixMergingBuilder`'s strict-extension test then simply fails to match, no stitch is applied, and the episode degenerates to per-turn chains exactly as it did before ADR-0007. Publicly the same shape: `verl#6854` is this defect in a trajectory reconstructor's prefix guard with thinking on, and `OpenRLHF#1080`/`NVIDIA-NeMo/RL#2821` report the SFT analogues. HuggingFace TRL's `qwen3_training.jinja` (always emit the think block) is the shipped general fix | the failure is LOUD, not silent — split chains fail the receiver's `chains_total == 1` — so the cost is lost episodes, not corrupted training data; the cure is the CP-04′ template flip (ADR-0007 amendment, Direction A). **[CP-28] EXERCISED — the cure held in vivo**: 15/15 real thinking-on episodes merged natively on the H200 (`chains_total == 1`, `glue_stitched: 0`, zero builder findings) through pi's reasoning round-trip — vLLM 0.26 returns the parsed reasoning as `message.reasoning`, pi echoes it back under the field name it found, and the engine maps it into the template's `reasoning_content` path (measured, `docs/polar/thinking/probe_override.txt`) — so the variable-length divergence this row predicts for the stock template never materialized under the symmetric one; the stitch stayed dormant and was never needed. **[CP-30] Unchanged by C-2's landing**: the per-mode G6 pin is checks-side pins data and touches nothing in this row's mechanism; the symmetric served template remains the only supported thinking-on configuration, and the CP-30 live pair (one episode per mode, both through the real receiver) merged natively again — `chains_total == 1` on both |
| A-23 | the harness runs in the SAME process as the gateway proxy, and that process's `polar.gateway.server` module state is the live one — the ground the CP-13 settings echo stands on | the `import_path` architecture: the harness is loaded into the gateway process (CP-06, verified live incl. the module-cache trap) and the node, registry, and proxy share `GatewayState` (`server.py:70-179`, executed at CP-13's hop run); the echo's registry merge, the proxy stamp, and the builder hoist all executed against the real vendored classes | a future Polar that runs harnesses out-of-process (or a second disconnected state) makes `registry.get(session_id)` return None and `PiHarness.setup` RAISES — episodes fail loudly at dispatch, never silently unechoed; the receiver's `G7:missing_evidence:settings` is the fail-closed backstop either way |
| A-24 | the `chromadb==1.5.9` pin is a dependency with its own upgrade risk, and its opaque on-disk format never fails silently: the corpus fingerprint carries a `chroma_version` component, so any bump forces a loud rebuild (`if-stale`) or a startup error (`never`) — added at CP-15 | ADR-0016; the fingerprint doc includes `chroma.version` (`mcp-service/gsj_mcp_service/index.py: corpus_fingerprint`), and the simulated-upgrade test (`test_backend.py: test_chroma_version_change_rebuilds_loudly`) proves the rebuild path; telemetry off, the image stays offline | a Chroma regression at the pinned version forces a deliberate re-pin + re-index — cheap at this scale (full 4-case rebuild ≈ minutes on the workstation); an on-disk format change inside a same-version patch would be the silent case the fingerprint cannot see, accepted as the residual risk of any opaque store |
| A-25 | Chroma/HNSW retrieval is reproducible at this corpus scale — **measured IDENTICAL at CP-15 Step 4**: ids, order, and scores byte-equal across two fresh processes over the same store, across builder-vs-loader, and across two independent builds, at tool level AND raw chunk level (9/9 probes) — but reproducibility is NOT a guarantee and byte-reproducible retrieval is no longer a promise of this stack (ADR-0040(f) forfeited by design, ADR-0016) | `mcp-service/tests/measure_determinism.py`, run on the workstation over the staging corpus (213 chunks, full-candidate-set fetch — `n_results` = the whole cutoff-filtered set, which is what makes HNSW effectively exhaustive here) | a larger corpus, a bounded fetch, or a Chroma bump may break it. Cost audit, done at CP-15: nothing else depended on reproducible retrieval — the golden/fidelity comparisons key on token ids/logprobs (sampling was never deterministic), `checks.py` keys on the cutoff and shape, and the one true consumer (the service's own cross-process byte-identity test) stays as a regression canary that would fail loudly, to be relaxed knowingly if this row flips |
| A-15 | gsj rollouts always pin `end_of_turn_token_id` in the builder config — EOT auto-detection is never relied on. **[CP-25] The pin's HOME moved, the assumption did not**: `config.py` now defaults the field to 151645 (`<|im_end|>` under the Qwen3 tokenizer the default `estate.model` serves), with the re-derivation command in the field comment — every rendered `TaskRequest` still carries the explicit id, the builder-side reject-if-absent check is untouched, and detection is still never consulted; what changed is that a consumer config omitting the key states the reference pin instead of failing validation | CP-05: auto-detect takes the last sampled token of the FIRST natural-stop completion in the chain (`prefix_merging.py:286-302`, natural = `{stop, tool_calls, stop_sequence}`); a stop-parameter/stop-sequence finish makes that an arbitrary token (a newline, a `</tool_call>`), and a wrong EOT mis-splits every interstitial — duplicated assistant-body fragments ride in as mask-0 tokens, corrupted-but-COMPLETED; with no natural stop in a chain at all (every turn `length`), every merge silently truncates instead; detection is per-chain, so two chains in one trajectory can even resolve different ids. **CP-06 practice run**: the spike pinned `end_of_turn_token_id: 260`, derived by lookup in the serving tokenizer's vocab table (the stub's `SPECIALS` dict, `spike/stub_backend.py` — `"<|eot|>" = 260`; on a real engine the same derivation is `tokenizer.convert_tokens_to_ids("<|im_end|>")` against the served model's tokenizer.json, the G4 artifact); both spike task files carry it and the live 2-completion chain merged full with `truncated == 0`. **A-15's other half measured**: pi 0.83.0 sends NO `stop` parameter and no `n` (wire-verified, both turns, three request forms) — so auto-detect would not have been *actively* mis-keyed here, but the explicit pin stays mandatory (S5; nothing prevents a future pi/config from adding stop sequences) | an unconfigured EOT on a real run degrades every multi-turn chain to silent truncation or silent corruption; the builder-subclass check (explicit eot config present, else reject) fails closed |
| A-26 | the slime v0.3.0 `Sample` surface the vendored adapter constructs against (`group_index`/`index`/`prompt`/`tokens`/`response`/`response_length`/`group_id`/`reward`/`loss_mask`/`rollout_log_probs`/`status` incl. `Status.FAILED`/`remove_sample`/`session_id`/`metadata`) is the real installed surface — **RESOLVED at CP-17: HOLDS.** With real slime importable on-estate, `bridge.load_sample_type()` returned `slime.utils.types.Sample` and the first conversion of a real collected body constructed one with every field accepted: `tokens=5783 response_length=2818 mask1=233 status=Status.COMPLETED group_id=0 session_id='sk-polar-0692…' reward={'score': 0.0}`. The four fields examples-repo F-04 flagged as unverifiable off-estate — `session_id`, `group_id`, `remove_sample`, `Status.FAILED` — are all present on the installed dataclass. 35 conversions across two collections, zero TypeErrors, zero shape workarounds. The loop's rollout function additionally asserts `type(sample).__module__.startswith("slime.")` per sample, so the local double could not have stood in silently | the vendored `slime_bridge/adapter.py` constructs exactly this against slime v0.3.0 + the router-tokens patch (its own install recipe); unverifiable off-estate at CP-16 — slime was not importable there (examples-repo FINDINGS F-03/F-04), so the bridge mirrored the usage and tested on a local double. **CP-17 verified it against the installed surface** (`docs/reports/CP-17.md`) | n/a (resolved). The prediction held exactly: the check was cheap, loud, and trainer-side — and it passed |

| A-27 | **RESOLVED — HOLDS (CP-21).** The verl surface the CP-20 bridge was written against — the padded classic-trainer batch contract (`prompts`/`responses`/`response_mask`+`loss_mask`/`input_ids`/`attention_mask`/`position_ids`/`rollout_log_probs`/`rm_scores`, uid-grouped advantages, all-zero-mask zero-gradient) at verl `1ae945592754cbeb1350cbe092fe6117070fd4c7` — IS the surface CP-21 trained with: every key was consumed by verl's own fit-loop path on a real batch of 110 (`extract_reward` read `rm_scores`; GRPO grouped by `uid`; `ppo_loss` trained under `response_mask`; the decoupled rollout correction consumed `rollout_log_probs` as sequence-TIS weights; `check_consistency` and the engine's own asserts all passed first try). The fit-loop consumption half — the one thing off-estate tests could not verify — is now measured (`docs/reports/CP-21.md` §4). Two surface findings landed in the external register, neither a batch-contract miss: F-12 (the v0 conversion helper hard-requires flash-attn) and F-13 (chunked entropy dead on the non-rmpad branch) | the SHA is uni-agent's own submodule pin (the pair the predecessor's path was built for), exported as `bridge.VERL_SHA`; the contract is read from verl's own agent-loop worker and executed in the bridge's tests against REAL verl code (`DataProto`, `compute_grpo_outcome_advantage`, `agg_loss` — no double, unlike slime's A-26 situation, so the constructor-surface half is already verified off-estate). What off-estate tests cannot verify: the fit-loop *consumption* of a bridge-fed batch on a GPU estate, and the trainer-generation fork (examples-repo F-11: the pin's DEFAULT trainer is the v1 TransferQueue pipeline, which cannot ingest external batches at all — the bridge targets the classic path) | CP-21's first step either consumes the batch or names the key it missed — loudly, since `check_consistency` and the fit loop's own asserts fail fast; if the classic path is removed at a newer verl, the pin holds until CP-21 chooses the fork deliberately (run book item 1) |

## 5. What we are testing

Four questions:

1. **Does Polar run our pi?** Our pinned pi 0.83.0, launched by an
   `import_path` harness, through Polar's proxy, inside a Polar-managed
   sandbox.
2. **Does our cutoff survive?** The timestep's page cutoff enforced
   per-episode, end to end, through our MCP service — nothing past page T
   visible through any channel. **[CP-10] The "any channel" clause is
   measured false, on both stacks**: the sandbox checkout carries the
   pre-truncation commit in `.git` and `bash` is on the roster, so
   post-cutoff pages are reachable through git history without touching
   the MCP service (row 2 — inherited from the corpus recipe, the
   predecessor's exposure is wider, fix is `--depth 1`). The MCP channel
   itself holds, proven at CP-07 and backstopped at CP-10. **[CP-11] The
   claim is restored for THIS repo, scoped honestly**: the harness clone
   is now `--depth 1 --single-branch` with the `origin` remote dropped
   and `.git/logs` scrubbed (the reflog kept `clone: from <url>` after
   the remote drop — measured, hence the scrub), verified at the object
   level in a scratch clone of a recipe-exact case repo — `HEAD~1` is an
   invalid object, the full-document commit and the post-cutoff blobs are
   absent from the object store, no URL is recoverable under `.git/`, and
   the worktree plus `read`/`grep`/`find`/`rg` are byte-unchanged. So
   offline, nothing past page T is reachable from the checkout. What the
   restored claim does NOT cover: the estate serves anonymous git read
   (CP-04 measured), so an agent that *guesses* the Forgejo endpoint can
   re-clone over the network — estate posture, shared with the
   predecessor's estate, cure named in row 2. The predecessor's own wider
   exposure stays recorded as inherited and unfixed (law 3).
3. **Are the traces trustworthy?** Token ids, `loss_mask`, and logprobs
   that pass `checks.py` — the gates' evidence reconstructable from what
   Polar captures.
4. **Can a trainer consume them?** Submit with `client.py`, receive
   validated traces, feed slime.

The success criterion, verbatim: *one real episode against our corpus,
through our MCP service, with the cutoff enforced, producing a trace whose
token ids, `loss_mask`, and logprobs verifiably match the golden reference
the predecessor produced for the same task.*

**[CP-09′] MET, H200 pair — final status: the criterion is met on BOTH
pairs, and the pair that governs (A-16) is green.** One real episode
(`sk-polar-44620742-9323-4202-9b58-474b4ed45f26`, the golden triple with
the golden's own instruction bytes, COMPLETED, full G7 conjunction, glue
dormant, cutoff held, ≥1 `mcp_gsj_*` and a successful `write`; attempt
19 of 19 — the H-41 assertion refused 17, the receiver's LP6 rejected
one live) collected through `gsj-rollout submit` on the H200 estate,
whose token ids, `loss_mask`, and logprobs verifiably match
`docs/golden/h200/` per `docs/golden/COMPARISON.md` executed in full —
including the logprob replay **as written** through the serving engine,
for the first time. Verdict **PASS WITH FINDINGS**
(`docs/reports/CP-09prime.md`): masks and token structure exact;
nothing attributable to Polar; the one finding is the platform's
capture-path numerics floor (beyond the contract's replay bounds on
both stacks symmetrically, replay path bit-deterministic). CP-12's
converting condition 1 is met.

**[CP-09] MET, Mac pair**: the success criterion is satisfied on the Mac
pair — one real episode (`sk-polar-180dd057-3b69-49d2-b834-6b67cf1ccba4`,
the CP-04 triple, COMPLETED, G7 conjunction, cutoff held, ≥1 `mcp_gsj_*`
and ≥1 built-in executed) collected through `gsj-rollout submit`, whose
token ids, `loss_mask`, and logprobs verifiably match the golden reference
per `docs/golden/COMPARISON.md` — verdict **PASS WITH FINDINGS**
(`docs/reports/CP-09.md`: nothing attributable to Polar; the findings are
ours and the platform's). The H200 pair (CP-04′/CP-09′) remains the
pending cluster confirmation; nothing mixes across the two pairs.

**[CP-04] Half built, Mac pair**: the golden reference exists —
`docs/golden/mac/` (episode `ep-b4124a5aa0a8468d`, `case_0001` /
`timestep-12` / `skill:summarize`, completed, gates green, 9 tool
executions, provenance G-hashes == the pinned singletons) with
`docs/golden/mac/MANIFEST.md` as its provenance and
`docs/golden/COMPARISON.md` as the field-by-field match contract CP-09
executes. "Verifiably match" is DEFINED by that contract; note its
measured constraint: greedy decoding is uncollectible for Qwen3-0.6B on
this task family (turn-1 tool_call emission loop), so both runs sample the
reference block and token-id equality survives only where sampling cannot
reach (turn-1 `prompt_ids`, interstitial glue), with logprob capture
compared by replaying frozen ids. The H200 pair (CP-04′/CP-09′)
re-establishes the production numbers independently; nothing mixes across
`docs/golden/mac/` and `docs/golden/h200/`.

## 6. The plan

GPU needed only at CP-04 and CP-09. Decision points — where the plan may
legitimately stop — are **CP-05**, **CP-09**, and **CP-12**.

| CP | what | notes |
| --- | --- | --- |
| CP-00 | scaffold | this checkpoint |
| CP-01 | moves | `corpus/`, `mcp-service/`, `forgejo/`, pins tooling, corpus contract |
| CP-02 | fork audit | the four reported defects (A-7): verify or refute each |
| CP-03 | vendor Polar | pinned SHA, re-vendor recipe, `[server]` deps become real |
| CP-04 | golden reference | predecessor produces the reference trace (GPU) |
| CP-05 | source audit | Polar line-read against A-1/A-4/A-5 — **decision point** |
| CP-06 | harness spike + stub | smallest pi-under-Polar episode |
| CP-07 | the harness | `pi_harness.py` + first `checks.py` validators |
| CP-08 | receiver / config / CLI | `receiver.py`, `config.py`, `client.py`, `cli.py` |
| CP-09 | fidelity | trace vs golden reference (GPU) — **decision point** |
| CP-10 | sentinels + cutoff | logprob sentinel guard; cutoff enforcement proven — **done**: the logprob discipline (`LP1`–`LP9`, `TR1`/`TR2`) and G5's page-census backstop landed in `checks.py`, platform-conditioned per CP-09's measurements; replay deliberately not built (F2–F4); the git-history cutoff channel found and recorded (row 2) |
| CP-11 | surviving gates | which of G1–G7 survive as `checks.py` validators; the inherited list is `docs/checks-spec.md` §CP-11's inherited list (G5's structural timestep, the pins walk, the size budget) — **split in two. CP-11 (M3b) done**: the git-history cutoff leak closed and verified (row 2), G5's structural timestep landed and the checkout-census clauses dropped by decision (row 13 → PARITY), the pins walk executed (row 23 → PARITY, `pins/pins.gsj.json`), the budget resolved (367 → 285, ADR-0009), the `CheckPolicy` surface wired (ADR-0010). **CP-11b**: the gates — G3/G7/G2/G1 landable against the approved sets now; G4 needs the codec-evidence mechanism, G6 the decode-side tokenizer answer; plus the G7 stats conjunction, the H-41 red flag, and the walk's first-episode-validate leg — **done**: G2/G3 + G7's conjunction LANDED and validated (rows 10/11/15 → PARITY), G1 unimplementable as specced (row 9 → GAP, fix recorded), G4/G6 deferred to measure-at-serve (ADR-0011; rows 12/14 → GAP with mechanisms named), H-41 landed policy-gated, the validate leg closed row 23, budget 1,496/1,500 after three measured recovery movements (the third forced by the CP's adversarial pass — three pre-existing never-raise breaches fixed in `checks.py`) |
| CP-12 | the verdict | the gap register closes the argument — **decision point**. **done: ADOPT PROVISIONALLY** (`docs/VERDICT.md` — the standalone verdict; converts on the H200 pair + M4's training loop, reverses on §9); the register finalized (18 PARITY / 6 DROPPED / 5 GAP / 1 BETTER / 1 TBD-with-reason); the size law raised to 2,000 (ADR-0012) |
| CP-13 | M4a: wishlist items 1–4, 7–8 | post-plan freeze-lift CP — **done**: G1 landed (`prompt_source` + card hash through the render parameters; row 9 → PARITY), G7's settings clause landed (the harness echo through the gateway registry, hops executed; row 15's residual closed; A-23), the H-41 YAML mirror complete by test, the receiver's pins-failure seam cured over HTTP (seven fault shapes, origin-classified 500s, a genuinely atomic batch), both stale documents fixed; budget 1,642/2,000 (`checks.py` 460/480, ADR-0013); items 5–6 stay with CP-04′ and ADR-0003, and the CP's own adversarial pass opened wishlist item 9 (G1's card hash computed sandbox-side) |
| CP-14 | M4b: split-by-directory | **done**: contract v2 (ADR-0015) — the train/eval split is the corpus tree (`train/cases/`, `eval/cases/`), `eval_case_ids` retired with a validator rejection naming the migration, one-case-one-split a hard failure; the staging tree re-shaped with every page byte and every ref SHA measured unchanged (the lock re-derived, split per case; the frozen bank still sha-verifies); the split rides `TaskRequest.metadata` (render parameter, absent = unstated) and `TR3` polices the vocabulary at the receiver; the deferred taskbank's split path fully specified (row 4); row 32 added (carried-not-enforced, DROPPED with the loader); budget 1,773/2,000 |
| CP-15 | M4c: ChromaDB behind the MCP tools | **done** (ADR-0016): the hand-rolled `vectors.npy` + numpy scan replaced by one Chroma collection per case + `decisions` (pinned `chromadb==1.5.9`), every wire contract byte-identical — the roster pin now asserted in the service's own suite (the captured wire array reproduces `a7a7956b…` and the live declarations reproduce the captured entries), the cutoff a `where: page ≤ T` PRE-filter (verified empirically: a query aimed beyond the cutoff still returns the whole in-cutoff candidate set), T from verified claims only, G5 shape untouched; determinism measured IDENTICAL at this scale (A-25) and the Chroma pin fingerprint-gated (A-24); suite **89** vs the 73 baseline (73 carried + 16 new — CP-15's own report; the figure read 83 here until CP-18's verification pass caught the arithmetic against `mcp-service`'s live 89), root suite untouched; budget unchanged (mcp-service is outside the count) |
| CP-04′ | M4d: the H200 golden pair, under the symmetric template | **done** (`docs/reports/CP-04prime.md`): the estate up on the H200 with this repo's components (split corpus converged, mcp-service 0.3.0 shipped + ready with the chromadb backend block, vLLM CUDA serving the codec snapshot under the three pinned legs); the symmetric template chosen (TRL's `qwen3_training.jinja`, byte-verbatim), PROVEN (turn-1 byte-identity across templates; turn-2 a strict prefix-extension — the pinned template diverges on exactly the four glue ids) and ADOPTED via `--chat-template` in the serve argv; the pins walk re-run estate-side (`chat_template_hash` → `1d944ff8…` by design, everything else measured unmoved, `g6_expected_tail_ids` derived — wishlist 5); **the stitch retired**: two fresh episodes with the glue ids UNSET merged natively (`chains_total == 1`, full G7 conjunction, `glue_stitched: 0`) — F2 dissolves at the root; the H200 golden collected through the predecessor's stack (the Step-5 recommendation; 7 on-triple attempts, same count as CP-09) and frozen at `docs/golden/h200/`; row-27's CUDA-strictness premise measured FALSE (exact-`0.0` recurs on CUDA at 6–25%) |
| CP-16 | M4f: the slime bridge | **done** (ADR-0017, ADR-0018): the trainer leg fixed — pins ride the wheel (`force-include` → `gsj_rollout/pins/`), `PINS_PATH` resolves `GSJ_PINS_PATH` → checkout → packaged copy, proven from a scratch venv against the real CP-09′ body (findings `[]`); the bridge itself built in `gsj-harness-rollout-server-examples/slime_bridge/` — callback-shaped `SessionResult` → slime `Sample` (v0.3.0 surface read from the vendored adapter), three enforced assertions (mask-before-ratio, sentinel rejection at the bridge's own −9000 floor, `checks` called trainer-side), two-tier rejection (pipeline poison raises, episode badness masks to zero-gradient FAILED), 14 fixture-driven tests on the real CP-09′/CP-07 bodies, each assertion's test shown failing when the assertion is removed; **no loop run** — CP-17's inputs named (weight-sync mechanism, policy-version declaration/P3, reward attach, the 19-attempt cadence, on-estate Sample verification A-26, `max_tokens`) |

| CP-17 | M4g: the loop | **done** (external ADR-0002): the loop closed on the H200 and **converting condition 2 is MET — the CP-12 verdict converts to ADOPT**. collect (28 submissions → 27 qualifying, zero receiver rejections, zero quarantines) → convert (27 → 27 **real** slime `Sample`s, three assertions live, `checks` trainer-side from the packaged wheel pins) → train (one optimizer step in real slime v0.3.0 + Megatron, `global_batch_size 27`, `grad_norm 0.4513` non-zero and unclipped, on a non-degenerate citation reward — 1/27 at 1.0) → sync (checkpoint reload: torch_dist → HF → engine restarted under the same served name with the four legs byte-identical; **proven** — control probe on identical weights `mean|Δ| 0.000000 / nonzero 0/5782`, across the sync `0.041835 / 5623/5782`; plus 263/310 tensors changed) → collect again (8/8 qualifying, cutoff held, all converting clean). **A-6 and A-26 resolved; A-13 exercised** (drain satisfied by construction — the situation, not the mechanism). Findings, none of them ours: Polar's vendored LOO post-processor explodes an advantage to 1e6 on degenerate variance (F-08), slime silently no-ops a whole train loop while reporting SUCCESS (F-07), Polar's documented Megatron pin lacks the module its own comment requires (F-06). **Nothing in `gsj_rollout/` changed** — the freeze held on the checkpoint that had the most reason to break it |

| CP-18 | M5a: continuous integration | **done**: one `.github/workflows/ci.yml`, four jobs, Python 3.12 only (no matrix — 3.12 is what this project *deploys* into: the mcp-service image, Polar's uv venv, the H200 collector; the package's `>=3.11` floor and the operator's 3.13 workstation venv are deliberately not exercised), push + pull_request on `main`: root suite (129), corpus suite (44 — 43 + one module-level skip), mcp-service suite (89, its own venv at the path its helpers hardcode + the pinned MiniLM from a keyed HF cache), and the wheel build + CP-16's packaged-pins install proof run from a venv **outside** the checkout. First run green on all four (`31562436551`, 3m 10s). The covered/not-covered statement is in the file's header comment and beside the README badge, because a badge that implies more than it covers is worse than none: CI runs the fixture-driven half and cannot touch the golden pairs, fidelity, the loop, or any episode. Findings, neither ours to fix and neither fixed: the receiver's atomic-batch test needs a non-root user (`CAP_DAC_OVERRIDE` defeats its `0o500` premise — wishlist 15) and the mcp-service bit-exactness oracle is host-dependent (≤ 1 ULP on arm64 while the property holds — wishlist 14); vendor Polar's carried-patch tests stay with the re-vendor recipe, not CI (wishlist 16). Two declared scope excursions (the `.gitignore` line for wishlist 12; two stale README status clauses). No `gsj_rollout/` change, no `tests/` change, and CI config is outside the size law (§3, [CP-18]) |

| CP-19 | M5b: PyPI | **done, not published** (ADR-0019, ADR-0020): the release path built and locally rehearsed, and the operator's decision was to stop there rather than make an irrevocable first upload. Metadata gap closed — `readme`, `license` (**Apache-2.0**, matching the vendored Polar so the tree carries one set of terms; PEP 639 SPDX + `LICENSE`, terms body diff-verified byte-identical to `vendor/polar/LICENSE`), classifiers, four `urls`, and `requires-python` **narrowed `>=3.11` → `>=3.12`** because nothing ever ran 3.11. The pins decision (ADR-0019): **ship as-is with a loud signal** — one `UserWarning` at import, fired only when resolution falls through to the wheel's packaged copy, silent under an explicit `GSJ_PINS_PATH` or a checkout (all three verified); `checks.py` +2, no rule moved, suite unchanged at 129. `release.yml` (ADR-0020): `v*` tag → build wheel → assert exclusions → `twine check` → install proof → TestPyPI → PyPI, `permissions: {}` at the top with `id-token: write` only on the two publish jobs (trusted publishing, no stored token), PyPI tag-gated so `workflow_dispatch` rehearses the whole path unable to reach it; it re-runs the wheel job **only**, never CI's matrix. Findings: the DEFAULT sdist was 4.6 MB / 835 files including 215 `vendor/polar/` entries, and hatchling's `include` does **not** fix it (its default file selection globs README/LICENSE/pyproject recursively — `only-include` does); `Typing :: Typed` dropped as a false claim (no `py.typed`); `checks.py` now at 520/520, so **G6 can no longer land inside ADR-0014's ceiling** (§3 [CP-19], wishlist 18). The name is unclaimed on both indexes and stays that way (wishlist 17, OPEN) |

| CP-20 | M6a: the verl bridge | **done** (external ADR-0003): the second trainer's bridge built in `gsj-harness-rollout-server-examples/verl_bridge/` — callback-shaped `SessionResult` → **real** `verl.protocol.DataProto` (verl `1ae9455`, uni-agent's own submodule pin; no test double, unlike slime's F-03 — verl imports off-estate). Route: **direct**, decided after reading uni-agent @ `73b0f41`: its trainer-side path generates into TransferQueue and **cannot be fed externally-produced trajectories** (entry point returns `None`; `Trajectory` is a gateway type; the padded batch it was credited with does not exist in it) — the question open since the predecessor, settled. Conversion per verl's own agent-loop conventions (prompt LEFT-pad / response RIGHT-pad, fixed split at `prompt_length`, `position_ids` via verl's helper, both mask keys equal, rewards-not-advantages as `rm_scores` at the last real response token, uid as the advantage-group key); the three CP-16 assertions unchanged, each shown failing-when-removed (1/2/4 tests red), plus the batching-stage invariant slime never needed; ERROR/TIMEOUT/unknown statuses fail-closed to all-zero-mask rows — verl's own zero-gradient mechanism, proven by calling verl's `agg_loss` and GRPO estimator in-suite. **F-08 asked of verl: structurally immune** (inclusive std → 0/ε never 1/ε; RLOO divides by no variance) — test-pinned. New findings: F-10 (singleton uid group ⇒ raw uncentred reward as advantage) and F-11 (the pin's DEFAULT trainer is the v1 TransferQueue pipeline, which no external process can feed — the boundary finding generalizes beyond uni-agent). 26 fixture-driven tests; **nothing in this repo changed** — the freeze-lift was `docs/**` only and the boundary held at its second trainer |

| CP-21 | M6b: the verl loop | **done** (external ADR-0004): the loop closed with the second trainer, **YES WITH FINDINGS**, and the milestone's question is answered — **two trainers, two loops, the boundary held, measured**. collect (112 submissions — budget stated 28, extended loudly twice on an identically-zero citation reward — 110 qualifying under the CP-17 standard, zero rejections/quarantines, cutoff held) → convert (110 → one real `DataProto` of 110, ONE shared uid closing F-10, three assertions live, `checks` trainer-side from the packaged pins) → train (one optimizer step in real verl @ `1ae9455`: `TrainingWorker`/FSDP ws1 on GPU 7, decoupled recompute agreeing with the captured logprobs at mean\|Δ\| **0.009442** — the third instrument at the CP-09′ floor — sequence-TIS from our capture live in the loss, GRPO advantages over the one group of 110 **min −0.0953 / mean 0.0000 / max +10.39**, `pg_loss −0.0944`, `grad_norm 2.32` pre-clip → 1.0 clipped, loudly) → sync (verl's own `FSDPCheckpointManager` HF export served by the estate engine via the unchanged `serve-updated.sh`; **proven**: probe noise floor exactly `0.000000/0/6768`, across the sync `0.042168 / 6541/6768`, engine root = the export, 310/310 tensors at audited one-AdamW-step scale) → collect again (8/8 qualifying, converting clean, against a demonstrably different policy — reward 8/8 by format-copying with visibly narrowed lengths: no learning claim, and the entropy/KL caution recorded). **A-27 resolved; A-13's second real sync, nothing differed.** verl findings F-12 (flash-attn hard-required by the v0 conversion helper) and F-13 (chunked entropy dead on the non-rmpad branch, two H200 OOMs) recorded in the external register, worked around in the harness. **Nothing in `gsj_rollout/` changed — and this time nothing in `staging/**` either**: the estate recipes ran a second trainer as committed |

**CP-04′ (the H200 golden pair) inherits a Definition of Done from CP-10's
template investigation** — written here so it is inherited, not
remembered. In addition to repeating CP-04's collection on the cluster.
**[CP-04′] All six items DONE** (`docs/reports/CP-04prime.md`; the evidence
per item is noted in-line):

1. render **both** template variants (the pinned Qwen3 template and TRL's
   prefix-preserving `qwen3_training.jinja` shape) against the same
   multi-turn history — **done** (the captured `pi_request.raw.json`
   4-message body; turn-1 renders byte-identical across the two);
2. confirm the symmetric variant makes turn-2's prompt a **strict token
   prefix-extension** of turn-1's — the property `prefix_merging.py:399`
   tests and the empty-think asymmetry breaks — **done** (pinned: diverges
   at index 2018 of 2022 on exactly `[151667, 271, 151668, 271]`;
   symmetric: strict prefix-extension, diverges nowhere);
3. adopt it at serving time via `--chat-template <file>` (per-request
   overrides need `--trust-request-chat-template` and are not the
   mechanism) — **done** (`staging/serving/serve.sh`; TRL's
   `{% generation %}` tags verified accepted by vLLM 0.26.0's renderer);
4. record the template file **in the serve argv** in the MANIFEST, so the
   served template is a pinned artifact with a hash of its own — **done**
   (`docs/golden/h200/MANIFEST.md` §Model & serving; sha256 `1d944ff8…`,
   file committed at `staging/serving/qwen3_training.jinja`);
5. **re-derive G4** against that file — this is also the fix for finding
   (a), the codec-vs-served template blind spot (row 12) — **done** (the
   pins walk ran estate-side on the H200; both snapshot-embedded templates
   now recorded-not-approved);
6. retire `generation_prompt_glue_ids` from the task config while leaving
   the stitch code dormant as the fallback for any future asymmetric
   template (ADR-0007 stands as a decision; it stops being load-bearing)
   — **done** (unset in `staging/rollout.h200.yaml`; two fresh episodes
   merged natively, `glue_stitched: 0`, `docs/polar/h200-stitch/`).

## 7. Gap register

The table this repo is judged by. **Every CP updates this table.** A
capability silently disappearing is exactly the failure this table exists
to prevent — DROPPED is a decision with a named owner, never an accident.
Status ∈ `PARITY | DROPPED | GAP | BETTER | TBD`.

**[CP-12] Final tally for M3 — every row statused**: **18 PARITY** ·
**6 DROPPED** (rows 16–21, all deliberate, all the trainer's, decided
CP-00) · **5 GAP** (rows 4, 9, 12, 14, 22 — each with its blocker
measured and its fix named in-row) · **1 BETTER** (row 29) · **1 TBD**
(row 30, with the reason it was never reachable stated in-row). The
capability delta — what the predecessor has that this repo does not, and
whether each absence was decided or is owed — is summarized in
`docs/VERDICT.md` §the register, closed.

**[CP-13] Post-M3 update**: row 9 GAP → PARITY (G1 landed at the config
freeze-lift, wishlist item 1) and row 15's in-row settings residual
closed (the harness echo, item 3). The running tally: **19 PARITY ·
6 DROPPED · 4 GAP · 1 BETTER · 1 TBD**; the M3 tally above stands as the
verdict-time record.

**[CP-14] Row 32 added (train/eval split enforcement — DROPPED,
deliberate: the loader's role lock went with the loader at CP-00; the
split-by-directory carry that replaces the manifest key is ADR-0015's).
Rows 1 and 4 annotated in place.** The running tally over 32 rows:
**19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-15] Row 2 annotated in place** (the MCP clamp's enforcement
mechanism is now a Chroma metadata pre-filter — ADR-0016; the property is
unchanged and freshly test-verified). No status changes; the tally
stands: **19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-04′] Rows 8, 12, 14, and 27 annotated in place** (the symmetric
template's native merge — the stitch dormant; G4's measure-at-serve walk
executed on the H200 with the served template an explicit pinned file —
the CP-11 expiry note resolved; G6's `g6_expected_tail_ids` pin derived —
the rule still blocked on a `checks.py` freeze-lift; row 27's
CUDA-strictness premise measured false). No status changes; the tally
stands: **19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-09′] Rows 7, 8, and 27 annotated in place — their statuses enter
M4 final** (capture fidelity H200-confirmed with the CUDA capture-noise
floor measured; reconstruction/masks exact on the governing pair, the
central bet answered on BOTH pairs; the zero-rate posture corroborated
live, 3rd/4th in-allowance measurements plus one live LP6 rejection at
26.6%). No status changes; the tally stands: **19 PARITY · 7 DROPPED ·
4 GAP · 1 BETTER · 1 TBD**.

**[CP-16] Row 23 annotated in place; the DROPPED block gains its first
consumer.** The pins seam grew the resolver leg (ADR-0017): `PINS_PATH`
now resolves `GSJ_PINS_PATH` → repo checkout → the wheel's packaged copy,
which makes law 6's trainer leg functional from an installed wheel for
the first time (CP-11b's "both legs run from the checkout by design"
disposition retired; proven from a scratch venv against the real CP-09′
body). **The slime bridge now exists** — trainer-owned, in
`gsj-harness-rollout-server-examples/slime_bridge/` (ADR-0018), converting
callback-shaped results to slime v0.3.0 `Sample`s with the three enforced
assertions; rows 16–21's DROPPED verdicts hold at first contact — the
bridge needed **none** of store/ready/staleness/serve-accounting/collation
for its shape half, and anything the CP-17 loop turns out to need is a
finding, not a rebuild (ADR-0018). A-6 stays open until one real
optimization step consumes masks and logprobs. No status changes; the
tally stands: **19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-17] The DROPPED block survives a real loop; row 27 gains a
trainer-side measurement.** Rows 16–21 (store, ready/mix, staleness, serve
accounting, collation, quarantine's retention half) were needed in
**exactly zero** places by a loop that collected, converted, trained,
synced and collected again — the CP-00 decision to drop them to the
trainer holds under the only test that could have refuted it. Row 27
(logprobs) gains an independent number: slime's own recompute against our
captured values differs by `train_rollout_logprob_abs_diff = 0.008813`,
within 1% of the CP-09′ capture floor the bridge exports
(`H200_REPLAY_FLOOR_MEAN = 0.008`) — two instruments, two checkpoints, the
same estate property, now measured from inside the trainer. Row 22's
estate-provenance residual is untouched. No status changes; the tally
stands: **19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-18] No row moves; what changes is which rows have *standing*
evidence and which have one-shot evidence — and this table should say
which.** Continuous integration re-executes the fixture-driven half on
every push to a machine that holds none of this operator's local state.
Re-proven continuously from now on: row 23's CP-16 resolver leg (the
trainer validating from an installed wheel — one scratch venv on one Mac
became a job that runs on every commit), the trace-side gates behind rows
9/10/11/13/15 and the logprob discipline behind row 27 (the root suite's
129, every "passes clean" assertion of which runs against a real body),
rows 1/2/32's corpus contract and split rules (the corpus suite's 44), and
row 2's MCP clamp mechanism plus row 11's roster pin (the mcp-service
suite's 89). Re-proven by nothing, and unchanged in that respect: rows 7,
8 and 27's *measurements* — capture fidelity, mask semantics, the CUDA
capture floor — plus rows 12/14's measure-at-serve mechanisms, row 22's
estate provenance, and everything the H200 pairs and CP-17's loop
established. Those are dated readings from hardware no hosted runner can
rent, and a green badge says nothing whatever about them; that asymmetry
is why the badge's caption is worded the way it is and why it sits in the
README rather than being left to inference. No status changes; the tally
stands: **19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-19] No row moves, and one row acquires a *distribution* dimension it
did not have.** Row 23 (the checks module both legs share) has been about
whether the trainer can run law 6's second leg; CP-16 made that work from
an installed wheel, CP-18 made it re-prove itself every push, and CP-19
asks the question one step further out: *whose approved sets is it running
against?* The answer, recorded in-row and in ADR-0019, is that the wheel's
pins are this estate's and the library now says so once at import rather
than leaving it to a reader of `pyproject.toml`. The row's status is
unaffected — parity with the predecessor was never about who ships the
pins — but a capability that leaves the estate is a different capability
from one that does not, and that is worth the sentence.

What CP-19 does **not** change, said plainly because a packaging
checkpoint invites the opposite inference: no gate, no rule, no threshold
and no measurement moved. `checks.py` grew two lines of `UserWarning` and
the 129-test suite is byte-for-byte the same suite. The published artifact
contains `gsj_rollout/` and one pins file and nothing else — in
particular **not** `corpus/`, `mcp-service/`, `forgejo/` or `vendor/`, the
four components rows 1/2/11/32 are about, so nothing in this table became
distributable this checkpoint. No status changes; the tally stands:
**19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-20] No row moves; row 29's BETTER earns its second data point and a
standing question closes.** The second trainer's bridge exists
(`gsj-harness-rollout-server-examples/verl_bridge/`, external ADR-0003),
and the claim the milestone tests — trainer-agnosticism as a property of
the boundary, not a hope — now has the only evidence that counts: the
verl bridge needed **zero changes in this repo**, exactly as the slime
bridge's loop did at CP-17. The standing question from `docs/VERDICT.md`
(whether the predecessor's uni-agent path "already speaks verl" cheaply
enough to reuse) is settled by reading, not taste: uni-agent's
trainer-side entry point generates into TransferQueue and returns `None`;
its `Trajectory` is a gateway type; the padded batch does not exist in
it — it cannot be fed externally-produced trajectories, and the direct
bridge was the cheap one. The same investigation generalized the finding
(examples-repo F-11): verl's own DEFAULT trainer at the pin (the v1
TransferQueue pipeline) also accepts no external batches — every road
into a trainer that refuses outside trajectories runs through either the
classic padded contract (the bridge's target) or letting the trainer
drive generation. Rows 16–21's DROPPED verdicts pass contact with a
second trainer unchanged — the verl bridge needed a store, a scheduler,
staleness tracking and a collator in exactly zero places. F-08's row-27
adjacency gets its cross-trainer answer: verl's estimators are
structurally immune (inclusive std; RLOO divides by no variance),
test-pinned in the external suite. No status changes; the tally stands:
**19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD**.

**[CP-21] No row moves; rows 16–21's DROPPED verdicts now survive TWO
real training loops, and row 27 gains a third instrument.** The verl
loop ran collect → convert → train → sync → collect on the H200 with
zero changes anywhere in this repo — `docs/**` only; even `staging/**`
(lifted for exactly this case) needed nothing: the serve scripts and the
one YAML ran a second trainer as committed, and `serve-updated.sh`
served a verl FSDP export as readily as a slime Megatron one. The
trainer-side set (16–21) was needed in exactly zero places a second
time — the verl loop wanted a store, scheduler, staleness tracking and
collator nowhere, and its one storage-shaped need (a place to put one
checkpoint) stayed in trainer scratch, as CP-17's did. Row 27's capture
floor gets its third independent measurement: verl's decoupled recompute
against our captured logprobs sits at mean |Δ| 0.009442 over 40,635
positions (CP-09′ replay: 0.008; slime recompute: 0.008813) — three
instruments, two trainers, one number, with the honest tail note that
0.25% of positions exceeded the 0.21 per-position floor (max 1.01) at a
sample 80× CP-09′'s. The loop's findings (F-12, F-13, reward sparsity,
the clipped step, the post-sync distribution narrowing) are all
trainer-side, evaluator-side, or config-side — none at the boundary. No
status changes; the tally stands: **19 PARITY · 7 DROPPED · 4 GAP ·
1 BETTER · 1 TBD**.

**[CP-23] Row 14 GAP → PARITY — the last designed-but-unlanded gate
lands.** G6 was the register's longest-running deliberate deferral:
designed at CP-11b (ADR-0011), unblocked at CP-04′ (the
`g6_expected_tail_ids` pin), and budget-blocked from CP-19's arithmetic
until this CP resolved the ceiling in order (banking −23, then ADR-0021's
machine-checked 528). `check_thinking_tail` now runs on both law-6 legs;
the in-row annotation carries the mechanics, the clean four-body
validation, and the Phase-C thinking-on note. The remaining GAPs are
rows 4 (taskbank, ADR-0003's deliberate deferral), 12 (G4, GAP-by-decision
— estate-side by ADR-0011), and 22 (estate provenance). The running
tally: **20 PARITY · 7 DROPPED · 3 GAP · 1 BETTER · 1 TBD**.

**[CP-24] Row 4 GAP → PARITY — the register's last deliberate deferral
lands, and row 4's fix closes exactly as it was named.** The taskbank was
deferred at CP-01 (ADR-0003: Polar takes `TaskRequest`s, not §3.1 rows)
and every checkpoint since narrowed what remained: CP-13 built the
statement slot (`prompt_source`/`skill_card_text`, hash at render), CP-14
specified the split's path to zero decisions (ADR-0015's row-spec). What
lands (ADR-0022) is deliberately NOT the predecessor's bank — it is the
consumer's enumeration, flat rows shaped for `render_task_request`, skill
cards resolved at build time so the G1 statement has an honest source,
`verify` holding the bank to the tree row by row. The frozen bank's
triple set reproduced exactly (12 rows, train 9 / eval 3); the bytes
changed by decision and the lock records the new sha. The remaining GAPs
are two: row 12 (G4, GAP-by-decision — estate-side by ADR-0011) and
row 22 (estate provenance). The running tally: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-25] No row moves; the consumer surface now has a SHAPE, and it is
aimed at someone who wasn't here.** Phase D's deskwork half: the one YAML
is fillable from six values (four estate endpoints, the gateway
`public_url`, `traces_dir` — machine-checked by
`test_a_stranger_config_of_endpoints_only_loads`), everything else
defaulted at its source with provenance comments (row 25's capability
unchanged — same file, same two audiences, same `extra="forbid"`);
the commented example a consumer copies lives in the examples repo's
`example_project/` beside the committed CP-24 bank (sha `ae9e0bbd…`,
rebuild script pointing at the corpus generator), a 207-line `train.py`
(vs the 398-line CP-21 harness; machinery in `verl_bridge/loop.py`,
F-10/F-02/the three assertions/the replay floor/the entropy-KL caution
all visible in the script), the install decision (ADR-0023: no trainer
extras — verl is `--no-deps`-at-SHA which extras cannot express and PyPI
metadata may not carry; one `install.sh` + a stated closure instead), and
the run book. What this CP deliberately did NOT do: touch
`staging/rollout.h200.yaml` (not lifted — its header archaeology stands
as estate provenance), run anything against an estate, or test any of it
on a stranger — CP-26 is that test, and the run book's last section is
its hypothesis list. Wishlist rows 20–21 opened for what the stranger
read found and this CP could not fix (frozen files). No status changes;
the tally stands: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-26] No row moves; the consumer surface met its stranger, and the
loop RAN — the friction list is the deliverable.** The stranger test
executed end to end on the H200 estate from a fresh directory, a fresh
venv, and both repos side-loaded at HEAD (the first finding: side-loading
was the ONLY way — external F-14): install (2 attempts + an un-runnable
printed cure, F-15), configure (five of six SUPPLY values already correct
on the reference estate; the sixth, `traces_dir`, un-creatable as
exampled, F-26), collect (**71/72 attempts qualified in under 7 min**, 1
LP6 quarantine — the run book's attrition expectations described the
strict/serial regime, F-18), dry-run clean (reward **1/71**, inside the
measured sparse band — that expectation was exactly right), the GPU step
after five attempts (uvicorn/fastapi/peft missing — the stated closure
was the desk closure, F-17 — then the cu13x torch trap with its silent
pip no-op, F-16; grad_norm 0.1970, advantages centred, HF export
written), and the sync leg failing DIAGNOSED on its workstation-topology
assumption (the run book sent it "estate-side" — the wrong side, F-29).
Twenty-six findings, F-14–F-39 in the external register, 18 fixed same-CP
in docs/example within the enumerated set (RUNBOOK, example config,
install.sh, requirements.txt, README), the library-shaped rest opened as
wishlist rows 22–25 (serve's invisible instructions; two more
config-schema strangerward gaps; the unverifiable MCP secret; train.py
polish). CP-25's hypothesis list scored: (a) soft-confirmed, (b)
confirmed with runtime shapes measured, (c) wider than predicted (the
bring-up hole reaches the stranger through the session-start seam), (d)
(e) not hit (same estate, same box), (f) confirmed-latent, (g) worse
(the library repo is needed twice and its public mirror is six commits
stale). The members nobody predicted — F-15/16/17/18/19/20/26/29/30-35 —
outnumber the predicted list, which is the CP working as designed
(finding over feature, law 7). Estate torn down after; `~/cp26-stranger/`
stays as the evidence artifact beside `~/cp21`. No status changes; the
tally stands: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-27] No row moves; the strangerward lift — the CP-26 findings words
could not close, fixed in code.** Library side (`config.py` + `cli.py`,
the enumerated freeze-lift): wishlist 21's two validators land — a
`serving_base_url` ending in `/v1` and a `gateway.port` ≠
`public_url`-port mismatch now fail at load naming the key, the measured
runtime symptom (bare 404 on `/v1/v1/…`; connection-refused on the
advertised URL), and the fix, instead of at the first dead episode;
F-25's comment-only-section-reads-as-null trap now yields field-level
errors (`'polar.gateway.public_url': Field required`) via a model-driven
null→`{}` normalizer; F-23's config half lands as optional
`estate.model_revision` (the in-band snapshot pin — carried, never read
by the server); wishlist 19's `__main__` guard makes
`python -m gsj_rollout.cli` behave like the console script (the CP-21/
CP-26 silent 0-exit no-op is dead); and F-20/F-21's serve half — every
pre-block print flushes so a nohup'd log holds the session's
instructions, and the printed Polar path is absolute. Examples-repo side
(wishlist 25): train.py aggregates collect and reward counts (F-27),
takes `--gpu N` → `CUDA_VISIBLE_DEVICES` (F-34), and its closing
printout sends the sync to the workstation side (F-29); RUNBOOK and
FINDINGS rows updated to match. Every LIBRARY-side fix has a test that
fails with the fix removed (root suite 136 → 143; the flush verified
independently of the guard through a pipe); the examples-repo fixes are
code-inspected only — that repo has no suite. NOT touched: `checks.py`
(528/528 — F-39's warn-once needs its own ADR), `mcp-service/` (frozen —
wishlist 24's secret probe stays open), publishing (F-14 stays the one
BLOCKER, operator-owned, wishlist 17). What the next stranger hits,
updated from CP-26's list: F-14 first and still (they cannot get the
trees); the cold-cache install cost; F-22's secret (named, unverifiable
before spending); the sync topology unless seated at the workstation
(documented, not cured); and — new residual — a wheel-installed
`gsj-rollout serve` prints a `vendor/polar` path into site-packages
where no vendor tree exists (the path is now absolute and loud, but the
provisioning walk is still Polar's README — wishlist 22's missing-venv
hint remains). The config traps are off the list: they now fail at load,
by name. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER ·
1 TBD**.

**[CP-28] No row moves; Phase C's go/no-go measured — thinking-on is GO,
and G6's three-way decision has its evidence.** Two 15-episode
collections on the golden triple, same engine process never restarted,
the only config delta `harness.thinking: off → medium` (scratch configs
outside both repos, the CP-04 pattern; everything deposited under
`docs/polar/thinking/`). The mechanism, measured end-to-end: pi always
sends `chat_template_kwargs: {enable_thinking: !!level,
preserve_thinking: true}` per request, Polar's openai-chat path forwards
it untouched, and vLLM lets it override the serve argv's thinking-off
default — so the flag is config-side and the four legs never move (G4's
served file byte-unchanged, same sha). The gates: all 15 thinking-on
episodes quarantined **through the receiver** on G6 findings alone —
G2's wire sha equalled the pin on all 30 episodes of both legs, G3/G5/G7
and the LP rows stayed silent — and every one of the 41 turn openings
ends `[151644, 77091, 198]` (the empty-think tail appeared zero times):
the CP-23 re-pin candidate confirmed total. The stitch question: A-22
EXERCISED — `chains_total == 1` on 15/15, the symmetric template's cure
held through pi's `reasoning`-field round-trip, glue dormant. The cost:
~2.7× wall (median 21.1 s vs 7.7 s/episode), response ids ~1.9× (median
7136 vs 3705), think tokens median 1100 (p25–p75 713–1430, max 2523) at
a median 67% of sampled tokens (0.44–0.95); zero `finish_reason: length`
(context median 31% of 32k, worst 81%). The return: tool use does NOT
degrade — MCP successes 4.1 vs 2.5 mean — and the deliverable landed
**8/15 vs 1/15** (`page:N`-cited 3/15 vs 1/15); no CP-04-style
`<tool_call>` runaway under the pinned reference sampling. Verdict GO,
committed in the report: C-2 lands the G6 re-pin as per-mode pin data
and turns `harness.thinking` into a validated knob (pi silently clamps
unknown values — `"on"` means OFF today, a trap the knob must close);
trainability per regime — OPD yes (the teacher scores the reasoning,
which is the point), RLVR yes with eyes open (67% of the trainable mass
is think tokens), SFT-on-own-reasoning no at 0.6B (the traces mostly
restate the prompt; supervising on them is circular). Reasoning tokens
are indistinguishable in `loss_mask` (upstream emits all-ones over
sampled tokens; TR2 stays the re-vendor canary) — "don't train on
reasoning" is expressible only by consumer-side ids segmentation over
the `<think>` span ids, not by the shipped mask. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-29] No row moves; M8d — published. F-14, CP-26's only BLOCKER, is
RETIRED by demonstration, not assertion.** The release path ran end to
end for the first time. The public mirror pushed current — nine commits,
CP-20..CP-28, +9615/−279, 42 of 43 new files under `docs/` — preceded by
a five-finder secret sweep over the unpushed range and the examples
repo's entire history (adversarially verified, completeness-critiqued):
**zero credential values anywhere**; the CP-04′ 0600 scratch file's
contents never entered git (`log -S` across all refs); the two note-level
exposures are the MCP secret's *filename* (`~/.gsj-mcp-secret-cp04prime`,
one occurrence, CP-26's report — the value arrives only by operator
handover, which is what the report says) and `/data/gsj/traces`; every
estate IP the push adds (`172.28.9.10`, `172.28.9.1`, `192.168.0.158` —
all RFC1918) was already public since CP-19. The examples repo got its
public remote and its full history pushed
(github.com/MHGanainy/gsj-harness-rollout-server-examples) — F-14's
other half; a published wheel whose run book lives nowhere fetchable
would have been half a cure. TestPyPI rehearsed via `workflow_dispatch`
— the three never-executed things all passed first try: the OIDC
exchange (no `invalid-publisher`), the exclusion assertions in CI, a
real index accepting PEP 639's SPDX + `license-files` — with the PyPI
job structurally skipped; then `v0.1.0` tagged at `1565813` and the tag
run went green through build → TestPyPI → PyPI. Proof on both indexes,
scratch venvs outside every repo, the real CP-09′ body: TestPyPI with
`--extra-index-url https://pypi.org/simple/` (no dependency mirror
there), then the one that retires F-14 — `pip install
gsj-harness-rollout-server`, no flags, no local wheel → packaged pins →
findings `[]`. ADR-0023's local-wheel-first ordering in the examples
repo's install.sh reversed (index by default, sibling wheel = developer
override): its stated justification was the unclaimed name, which no
longer exists. **The finding (wishlist 26): main's CI is RED at the
published tag** — CI's first contact with five checkpoints of drift:
the corpus job's dependency set stale since CP-24 (17 failures:
pyarrow absent, `gsj_rollout` not installed, the job comment's "no
import of the root package" now false) and, beneath it, the CP-24
corpus fixture pinning the exact `/v1` trap the CP-27 validator now
rightly rejects (2 failures, `corpus/tests/test_taskbank.py:37`) — the
cure is one fixture line plus CI deps, both outside this CP's lift; the
release-relevant jobs (root 143, wheel + packaged-pins proof,
mcp-service) are green at the tag, and the red job's subject ships in
no artifact. Second finding (wishlist 27): 0.1.0's landing page
immutably embeds the pre-publication README — structural to the
one-commit protocol, cured by any next version. **What the next
stranger hits, re-ordered now that F-14 is gone**: (1) the red badge,
fronting both landing pages (wishlist 26 — a reader told "green means
the fixtures still pass" reasonably concludes they don't); (2) the
stale 0.1.0 landing text (wishlist 27); (3) the cold-cache install cost
(~15–25 min of downloads CP-26's warm caches hid); (4) — server role
only — F-22's secret (named, still unprobeable, wishlist 24), the
site-packages `vendor/polar` path from a wheel-installed serve
(wishlist 22's residual), and the sync topology unless seated at the
workstation (F-29, documented); (5) the pins warning shouting on the
reference estate (F-39, wishlist 22). The structural change underneath:
the trainer role now needs **zero handover** — clone the examples repo,
`bash install.sh`, done; the operator-held list (secret, revision,
estate values) matters only once an estate enters. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-30] No row moves; M9b — the badge greened, and thinking landed
(C-2 done).** The wishlist-26 cure was exactly the estimated size where
it executes: one fixture line (`corpus/tests/test_taskbank.py:37`, the
`/v1` drop — the validator untouched, per the prompt's own rule) and one
CI install line (`pip install -e . pytest -r corpus/requirements.txt` —
refreshed from the corpus's own requirements file rather than named by
hand), plus label/comment truth (root 150, corpus 58; the corpus job's
"no import of the root package" claim retired). Counts: 56/58 local and
39/58 CI before; 58/58 local after, with the CI job's exact recipe
additionally reproduced in a fresh venv. CI's own green arrives with
this commit's push — the one-commit protocol cannot carry its own CI
result (the CP-29 structural note); verified live in-session
post-push, badge healing on both landing pages on that run. Wishlist
27's stale landing text heals at the next release, untouched here. C-2 landed per ADR-0024: G6 re-pinned as
per-mode pins data (`pins/thinking-on/`, selected via `GSJ_PINS_PATH`;
row 14 carries the mode-dependence), `harness.thinking` became a
validated knob closing CP-28's silent-clamp trap (plus the YAML-1.1
discovery: pyyaml parses bare `off`/`on` as booleans, so the validator
maps them before rejecting — the natural spelling of the default must
not die as a type error), `pi_harness.py` needed NOTHING (the flag
already rides `settings.thinking` → `--thinking`, measured at CP-28),
and `checks.py` is byte-untouched at 528/528. Proven live: one
thinking-on and one thinking-off episode through the real receiver,
both accepted clean on attempt 1, `chains_total == 1`
(`docs/polar/thinking-on/`) — the acceptance CP-28 structurally could
not have. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER ·
1 TBD**.

| # | capability | gsj-envloader | here | status | notes |
| --- | --- | --- | --- | --- | --- |
| 1 | corpus contract | `docs/corpus-contract.md` — the normative corpus document | moved at CP-01, byte-identical (zero library references, measured); **v2 since CP-14** | PARITY | landed CP-01 (ADR-0002). **[CP-14] The first deliberate divergence from the predecessor's document (ADR-0015)**: contract v2 makes the train/eval split a directory property (`train/cases/`, `eval/cases/`), retires `eval_case_ids` with a validator rejection naming the migration, and adds the one-case-one-split invariant (rule 5) plus root strictness. The predecessor's corpus stays readable by ITS pipeline (law 3); this repo's pipeline reads only v2 trees, and a v1 tree fails validate with the migration spelled out. PARITY stands on the capability — a normative contract with a strict validator — now with this repo as the document's owner rather than its custodian |
| 2 | retrieval cutoff | timestep T = page cutoff: checkout pinned to `timestep-{T}` branch; MCP per-session cutoff clamp; G5 enforces at collection | injected per episode via `run_steps()` (A-4); the MCP clamp carries over | PARITY | CP-01: the clamp's owner (`mcp-service/`) and the timestep-branch tooling (`corpus/`, `forgejo/`) are here — component-level parity; end-to-end enforcement proven at CP-10; not injectable at all → abandon (§9). **CP-07: proven end to end, the first time an actual episode exercises it** — the harness clones `case_0001` at `timestep-12`, mints the per-episode token in `run_steps()`, renders `.pi/mcp.json`; the MCP service enforced the cutoff from the token's verified claims (every `search_case` result page ≤ 12; census-boundary page 12 itself visible in other samples), the authority logged per call (`docs/polar/pi-corpus/mcp_authority_log.jsonl`), and the adversarial tamper (timestep 12→18, original signature, called from inside the sandbox) rejected 401. The remaining GAP-to-PARITY gap is only G5's trace-side backstop as a `checks.py` validator (CP-10/CP-11) — the enforcement itself is at parity. **CP-10: the backstop landed** (`checks.check_page_cutoff`, row 13) — the page census reconstructs from the trace's own `mcp_gsj_search_case` results and every page > T fails `G5:search_page_gt_timestep`; the residual is where T comes from (row 13(b)). **CP-10 also found a cutoff channel no trace-side check can see, and it is inherited rather than introduced**: `corpus/ingest_corpus.py:601-612` builds each `timestep-{T}` branch as one truncation commit ON TOP OF `main`'s full-document commit, `pi_harness.py:127` clones `--branch … --single-branch` with **no `--depth`**, and `bash` is on the measured wire roster — so `git show HEAD~1:md/page_0018.md` returns a post-cutoff page from inside the sandbox, offline, with no MCP call involved (reproduced end to end with the exact recipe and clone flags; `git log` alone leaks the document's page count). The predecessor is WIDER — it clones the whole repository, every branch (`task.py:826-839`) — so this row's PARITY claim survives, but §5's "nothing past page T visible through any channel" does not, on either stack. G5 is blind to it by construction (the leak is `bash` output, not an `mcp_gsj_*` result). **Fix: `--depth 1` on the harness clone plus dropping the `origin` remote**, at the next `pi_harness.py` freeze-lift (frozen this CP). **[CP-11] FIXED and verified**: the clone step is `--depth 1 --branch timestep-{T} --single-branch` + `git remote remove origin` + `rm -rf .git/logs` (the reflog retained `clone: from <url>` after the remote drop — a CP-11 measurement, so the remote drop alone did not deny re-fetch); reproduction and cure ran in a scratch clone of a recipe-exact `case_0001` (estate torn down on this host): `git show HEAD~1:md/page_0018.md` went from returning the post-cutoff page to `fatal: invalid object name`, `git log` from 2 commits (subject leaking the 18-page total) to 1, `git cat-file -e` proves commit and blob absent, `git remote` empty, no URL under `.git/`, worktree byte-identical (`diff -r`), `read`/`grep`/`find`/`rg` unbroken; regression-tested on the rendered command (`tests/test_pi_harness.py`). **Residual, estate-owned**: anonymous Forgejo read (CP-04: 4 refs/repo anonymous-clonable) lets a URL-guessing agent re-clone over the network — cure is credentialed clone URLs or sandbox egress policy at estate bring-up (CP-04′); shared with the predecessor's estate. The predecessor's wider in-sandbox exposure (whole-repo clone, every branch) stays inherited and unfixed (law 3). **[CP-15] The MCP clamp's MECHANISM changed, the property did not (ADR-0016)**: the service-side filter is now a ChromaDB metadata pre-filter (`where: page ≤ T`, one collection per case) instead of the numpy candidate mask — verified empirically to constrain candidates BEFORE ranking (a post-filter would return fewer than requested and move the recall boundary; the discriminating test aims a query at a fact beyond the cutoff and still receives the whole in-cutoff candidate set), T still sourced from verified token claims only, the SN-serial probes and G5's shape contract green and unchanged (`mcp-service` suite 89 vs the 73 baseline — corrected from 83 at CP-18) |
| 3 | git host | Forgejo estate: case repos with timestep branches; compose + bring-up/teardown scripts | moved at CP-01: `forgejo/` (data dir re-rooted inside the component; live H200 estate keeps its compose-project identity) | PARITY | tooling parity — no bring-up ran at CP-01 (out of scope); the H200 networking archaeology (static container IP, `host.docker.internal`) is documented in-file, inherit deliberately or not at all; CP-04: **first live bring-up of the moved components** — Forgejo + `corpus/ingest_corpus.py` scaffold converged on macOS (frozen SHAs reproduced, taskbank byte-identical `9eb8e3c2…`, corpus verify PASS 25/25, MCP census 18/22/15/20); Mac networking needs published ports (host→container-IP is dead on Docker Desktop) while container→container static-IP routing works unchanged — scratch-copy deltas only, both repos untouched |
| 4 | taskbank | `taskbank.py` builds the §3.1 parquet: skill rows resolve at rollout, free rows verbatim | tasks arrive as `(case, timestep, prompt)` via `client.submit`; **[CP-24]** `corpus/ingest_corpus.py`'s `taskbank` phase builds the ADR-0022 bank — flat rows shaped for `render_task_request`, skill cards resolved at build, free rows verbatim | PARITY | CP-01: builder NOT moved — deferred to CP-07 (ADR-0003); the phase raises, verify's row checks deferred with it; the frozen bank + lock carried as data (ADR-0002), still sha256-verified; CP-08: the arrival path is real — `render_task_request` turns the triple into a Polar `TaskRequest` (validated against Polar's own model) and `gsj-rollout submit --case --timestep --prompt` submits it; skill-row resolution stays deferred. **[CP-12] FINAL: GAP, deliberate (ADR-0003)** — the arrival path is real and at parity (CP-08), but the builder and skill-row resolution never landed anywhere: a skill row cannot resolve here, and without `prompt_source` no trace states what the task was (row 9's measured blocker). Deferred with a named owner at CP-01 and still owned; the fix is the `TaskRequest`-shaped builder in `client.py`'s orbit plus `prompt_source` at `config.py`'s next freeze-lift (`docs/VERDICT.md` §wishlist). **[CP-13] Half of that fix landed** — `render_task_request` now takes `prompt_source`/`skill_card_text` and states both in task metadata, so a resolved skill row has a place to declare itself and G1 verifies it (row 9 → PARITY). The row stays **GAP**: nothing here still RESOLVES a skill row — the builder and the resolution step remain ADR-0003's, and until they land every submitted task is definitionally `free` (the frozen `cli.py`'s only truth). What CP-13 removed is the blocker, not the deferral. **[CP-14] The split half is now fully specified even though the builder stays deferred (ADR-0015)**: each bank row carries a `split` field, value `train` \| `eval`, case-level — every row of a case takes the case's directory split as recorded in `corpus.lock.json` `cases.<case_id>.split` — and the builder passes it to `render_task_request(split=…)`, which states it in `TaskRequest.metadata` beside `case_id`/`timestep`/`prompt_source` (landed and test-proven this CP; absent = unstated, never defaulted to train). The deferred implementation has no split decisions left; the row stays GAP on the builder and skill-row resolution only. **[CP-24] GAP → PARITY — the builder lands (ADR-0022; ADR-0003's deferral resolves)**: `phase_taskbank` builds `taskbank.parquet` — one flat row per `(case, timestep, prompt)` carrying the triple, `split` (lock-sourced, ADR-0015's row-spec), `prompt_source`, the free row's verbatim `prompt_text` / the skill row's **resolved** `skill_card_text`, and `sandbox_image` — deterministic (byte-identical rebuilds; sorted rows, fixed schema), sha256 in the lock, `verify` running the row-level half deferred since CP-01 (counts, triples-exactly-once, set-equality with the tree, split/text/image re-derived). A row submits with zero translation (every column is the triple or a `render_task_request` argument — no `config.py` change needed, the CP-13/CP-14 result), and G1's story closes end to end: card bytes → bank text → render-computed hash → task metadata → trace metadata → `check_skill_card` ∈ the pinned set (proven on both real callback bodies, stamped per the CP-13 pattern). The frozen staging bank's 12 triples + splits reproduced exactly; its bytes did not (§3.1 nesting dropped by decision) — lock sha `9eb8e3c2…` → `ae9e0bbd…`. Skill-row resolution is build-time and corpus-level by decision: the sandbox-side instrument stays wishlist 9 |
| 5 | episode isolation | fresh per-episode checkout + ephemeral `docker run --rm` + per-episode gateway actor | Polar sandbox: start/stop/exec/upload/download | PARITY | CP-06/CP-07; CP-02: a fork (yichuan-w) works around two reported Docker-runtime defects — event-loop starvation in `DockerRuntime.start()` and task timeout not killing containers — UNVERIFIED here, check live at CP-06; CP-03: DockerRuntime ran live on macOS (4 parallel sandboxes via docker CLI create/exec/cp/rm, clean teardown observed; the two reported defects stay UNVERIFIED — nothing timed out); macOS networking fact for CP-06: task `network: "host"` does NOT reach the macOS host loopback unless Docker Desktop host networking is enabled — set `node.public_url` to the host LAN IP, which works from bridge and host-net containers *and* from the host-side rollout dispatch (the same URL serves both); CP-06: the LAN-IP topology confirmed again live (sanity + pi runs); `import_path` harness loading verified in the gateway process (PYTHONPATH-provided module, zero vendored edits) — note the module is CACHED after first import, so harness edits need a gateway restart; **operational trap found**: `runtime.workdir` applies to EVERY exec including the harness `setup()` that would create that workdir — `docker exec -w <nonexistent>` fails before setup can run, and because the presets discard exec results the failure surfaces only as "step 0 exited with code 127" with zero records; rule for CP-07: never point `runtime.workdir` at a directory the harness itself creates, and check `setup()` exec return codes loudly; the two reported Docker-runtime defects (event-loop starvation, timeout-not-killing) remain UNVERIFIED (nothing timed out); CP-04 (predecessor-side but platform-relevant): the linux/amd64 pi image runs fine under Docker Desktop emulation on arm64 (13.7 s episode wall), and `--add-host host.docker.internal:host-gateway` reaches host-loopback services on macOS unchanged; **CP-07: the harness ran our pi under DockerRuntime end to end on the real corpus** — clone at `timestep-{T}`, render config, run, download — all as `exec`/`download` against `BaseRuntime` (law 5, image needs only `node`+`git`); two new traps found and cured in `pi_harness.py`: (a) pi's managed-binary installer (ripgrep/fd into `<agent dir>/bin`) renames across filesystems, so a session-bind-mount agent dir silently breaks the built-in `grep`/`find` on every episode (the golden run hit the same class via its ro `/agent`) — the agent dir must be **container-local** (`/tmp/pi-agent`, also non-root-safe: the pinned image is uid 1000); (b) `PI_OFFLINE=1` (the spike's carry-over) gates that download unconditionally regardless of the `--offline` flag, so it is NOT set — pi fetches rg once per episode from GitHub (reachable from the bridge; a per-episode network dependency the golden run also carried). **[CP-12] FINAL: PARITY** — the lifecycle ran live at CP-03 (4 parallel sandboxes, clean teardown observed), CP-06 (`import_path` in the gateway process), CP-07 (our pi under DockerRuntime end to end, fresh per-episode clone), and CP-09 (seven submissions); per-episode isolation held every time. The two fork-reported Docker-runtime defects (event-loop starvation, timeout-not-killing) remain UNVERIFIED — nothing here ever timed out, and unverified is not false (§4) |
| 6 | harvest-before-reset | type-level guarantee: `_reset` requires a `HarvestResult`; artifacts copied out before any git command | Polar's problem — its lifecycle must give an equivalent guarantee | PARITY | CP-05 source audit checks for it; CP-05: the ordering EXISTS but as control flow, not types — `_handle_postrun` runs `_build_session_result` (build+eval, `node.py:505`) before teardown starts (`node.py:513-531`); trace data itself is proxy-time capture into the in-memory `SessionStore`, so trajectory construction never depends on the sandbox at harvest time; **CP-06 live confirmation**: the spike harness's `postprocess()` downloaded pi's in-sandbox transcript and the build produced a full trajectory, both before runtime stop — ordering held; caveat stands: control-flow parity, not the predecessor's type-level guarantee, and the gateway's temp session dir is REMOVED after the session, so anything not downloaded in `postprocess()` (or persisted by the CompletionWriter) is gone; **CP-07: the production `postprocess()` exit works on a real episode** — it downloaded pi's transcript AND the `out/` deliverable into `<artifacts_dir>/<session_id>/` before teardown, keyed by the Polar session id so the trace joins to them; loud-but-non-fatal on a missing `out/` (normal) |
| 7 | token/logprob capture | gateway codec renders the pinned template; token-level loss mask; sampling-time `rollout_log_probs`; capture-once | Polar's proxy + trace reconstruction | PARITY | **CP-09 (Mac pair): capture fidelity verified against the golden** — on identical-context positions (the two traces' 20-token common response prefix, same engine) Polar's captured logprobs agree with the predecessor's at mean |Δ| = 0.000114 / max 0.0018, well inside the contract bounds; discipline clean (finite, ≤ 0, no sentinel, `0.0` only at mask==0); captured values are RAW model logprobs, not sampling-renormalized (measured: raw replay hypothesis fits at the numerics floor, the renormalized hypothesis fits ~6× worse). Three CP-09 caveats: (a) **vllm-metal cannot teacher-force** — `prompt_logprobs_dict={}` is hardcoded (`vllm_metal/v1/model_runner.py:2235`) and the `echo` path 500s (`KeyError` in `_create_completion_logprobs`), so replay-style validation on Mac estates must run beside the serving engine (CP-09 used mlx_lm on the served snapshot; the H200 pair can replay through vLLM proper); (b) **turn≥2 `response_logprobs` are computed under the engine's wire context**, which differs from the merged stream by the ADR-0007 stitched glue ids (4 tokens/prior turn) — verified causally at CP-09 (replay vs wire ctx mean 0.0133 vs 0.0676 against the stream ctx); (c) the row-27 MLX exact-`0.0` artifact recurs on the Polar side (15/363). fidelity was CP-09; CP-02: at the pin nothing value-validates logprobs (the slime adapter checks presence and length only) — vLLM's `-9999.0` sentinel flows to the trainer; our guard supplies a missing check, not a duplicate (row 27); CP-03 live run: with no engine token ids the trace ships empty `prompt_ids`/`response_ids` and null logprobs (mlx-lm's `{"id",logprob}` entries are a dialect the pin's normalizers don't read) — value-level capture genuinely requires vLLM/SGLang (CP-09); also upstream's own sglang meta_info-recovery test FAILS at the pin (engine.py stamping skips on length mismatch → `KeyError: token_id`) — pre-existing test-vs-src drift, verified not introduced by our patches; CP-05: the capture surface line-verified — `prompt_ids` from `choice.input_token_ids`/`choice.prompt_token_ids`/`response.prompt_token_ids` (`record_utils.py:136-140`, NOT int-coerced), `response_ids` from `choice.token_ids`/`response.token_ids` else `logprobs.content` pairing (requires the `token_id` key — mlx's `id` fails at `:38`) else sglang `meta_info` (`:82-107`); NO value-level logprob validation exists anywhere in the vendored tree (grep isfinite/isnan/isinf/9999: zero hits), and the missing-logprob rejection at the pin is STATUS-derived, not config-gated (`adapter.py:120,274-278`; `require_trainable_logprobs` is a kwarg, not a config surface) — checks-spec corrected; `choices[0]` is the only choice ever consumed (`record_utils.py:131-134`) — `n>1` sampling loses every other choice silently; **CP-06**: with a token-id-bearing dialect (the stub: `prompt_token_ids` + `token_ids` + `logprobs.content[].token_id`) the whole capture path works end to end — `prompt_ids`/`response_ids`/`response_logprobs` fully populated in the callback, `0.0` placeholders only at mask-0 interstitials; the engine-prepare additions (`logprobs`, vllm `return_token_ids`, `top_logprobs: 0`) confirmed on the actual wire (stub dump); **the true wire request/response are not persisted or loggable anywhere at the pin** (CP-03 finding 4 sharpened at source: `proxy.py:118-136` builds and posts the outbound body without storing it, sglang `meta_info` is popped before save) — the engine-side dump is the only wire observation point, fine for a stub, GONE on a real vLLM (CP-09 must plan its own capture); pi never asks for `n>1` (wire-verified) so `choices[0]`-only capture is safe for pi traffic, enforced by the subclass `len(choices) == 1` check; **CP-04 platform fact for CP-09**: vllm-metal (vLLM 0.26.0+cpu arm64, MLX backend) speaks the full token-id dialect on `/v1/completions` — token-id prompts accepted, `return_token_ids` honored (`choices[0].token_ids`), `logprobs.token_logprobs` aligned, `choices[0].prompt_token_ids` echoed — so the Mac CP-09 pair has a real engine for the capture path; caveat: MLX/bf16 sampled logprobs round near-delta distributions to exactly `0.0` (20/292 mask-1 positions on the golden episode — row 27); **[CP-09′] H200-confirmed — the final M4-entry status**: capture fidelity holds on the governing platform with the replay run AS WRITTEN (vLLM proper teacher-forces; bit-deterministic, rerun Δ exactly 0.000000); caveat (a) is Mac-only by measurement, caveat (b) is GONE on symmetric-template estates (glue_stitched 0 — the merged stream teacher-forced directly with no F2-shaped excess: collected turn-2 drift 0.0121 vs F2's 0.0676, worse-span direction reversing across traces), caveat (c) recurs (37/510 = 7.3%). NEW and load-bearing for M4: the CUDA cross-request capture-noise floor — capture-vs-replay mean |Δ| 0.005246 (golden, Polar-free) / 0.007141 (collected) against the 0.005 bound, capture-vs-capture 0.003672 on identical contexts (the Mac's 0.000114 was MLX-sequential); invisible trace-side, every discipline rule passes — recorded in checks-spec §CP-09′ |
| 8 | multi-turn stitching | chains over the rendered stream; call offsets cross-checked against mask transitions | Polar `prefix_merging` (A-1 — line-verified at CP-05; **resolved empirically at CP-09, Mac pair**) | PARITY | **the central bet of the whole repo — CP-09 answers it for the Mac pair: PASS WITH FINDINGS** (`docs/reports/CP-09.md`): masks exact per the zero-tolerance row, `prompt_ids` byte-identical, decode-fidelity exact at mask==1 on both traces, glue template constants identical across stacks; nothing attributable to Polar. The one stitching-semantics finding is OURS (ADR-0007): the merged stream carries the stitched generation-prompt glue that the engine's turn≥2 prefill never saw, so turn≥2 logprobs are conditioned on a context 4 tokens away from what the trace implies (row 7(b); the golden's token-in dialect has no analogue). H200 confirmation pending (CP-04′/CP-09′); CP-02: the pin emits `reconstruction_stats` (chains_total, truncated, merged counts) into trajectory metadata — the G7 snapshot is readable receiver-side with zero patches, BUT silent chain truncation still returns COMPLETED, and `trajectory/registry.py` resolves builder strategies by import path — a validating `PrefixMergingBuilder` subclass in `gsj_rollout` is a zero-patch insertion seam; CP-03: real artifacts dumped (`docs/polar/`), live `reconstruction_stats` shape confirmed incl. P1's `raw_completions_total`; DEGENERATION PROVEN LIVE: with empty `prompt_ids` every completion starts its own chain — 10 length-1 chains reported as `full=10, truncated=0`, a clean-looking snapshot with zero actual merging — so G7 must require `chains_total == 1`, never just `truncated == 0`; CP-05 LINE-VERIFIED (A-1): retokenization guarantee + §3.4.2 interstitial split confirmed in code; degenerate-case mechanism confirmed at `prefix_merging.py:399` (`0 < n` guard; each length-1 chain counts `chains_reconstructed_full`); the finalize-loop prefix break (`:212-221`) is defensive dead code (grouping guarantees the pair property — adversarially re-verified); the builder README's "message-level grouping key" does NOT exist at the pin (grouping is token-prefix only — README-vs-code divergence, likely the unlanded `polar`-branch refactor); seven silent-degradation modes catalogued in `docs/checks-spec.md` §silent-degradation, ALL presenting as COMPLETED (CP-12 erratum, surfaced by the verification pass: the catalogue as landed at CP-05 holds NINE modes, S1–S9 — "seven" here and in the CP-05 report is the error; S4′ joined at CP-07); **CP-06: first live MERGED multi-turn chain** — pi 0.83.0, 2 completions, explicit EOT 260: `chains_total == 1`, `full == 1`, `truncated == 0`, merged stream = 119 sampled (mask 1) + 30 interstitial (mask 0) tokens with logprobs aligned and `0.0` only at mask-0 — the stitching layer does the right thing when fed a token-id dialect; token *fidelity* against a real engine stays CP-09's question; **CP-07: first MERGED chain on a real corpus episode + a real defect found** — the vendored grouping FAILS on pi's Qwen3 no-think template (the empty think block `[151667, 271, 151668, 271]` is appended to every generation prompt but not the history re-render, so consecutive pi prompts are never prefix-stable → 2 chains, silently COMPLETED, the S4 shape). Fixed in the subclass with a config-pinned generation-prompt glue stitch before grouping (A-21, ADR-0007, strict-extension only so S3 retries still don't merge); the same episode then merged `chains_total == 1` (441 sampled + 6755 interstitial, logprobs aligned, `0.0` only at mask-0). A stitching-layer defect the CP-06 stub could not surface (byte tokenizer, no template) — exactly the end-to-end-only class this row exists to catch. **[CP-04′] The defect's root cause is CURED at the estate**: under the served symmetric template (`qwen3_training.jinja`, Direction A) the vendored grouping merges natively with `generation_prompt_glue_ids` UNSET — two fresh H200 episodes, `chains_total == 1`, full G7 conjunction, `glue_stitched: 0` (`docs/polar/h200-stitch/`). The CP-09 stitching-semantics finding (F2 — turn≥2 logprobs conditioned 4 tokens away from the merged stream) dissolves at the root on this estate: the merged stream now IS the wire context. The stitch code stays dormant (A-21's fallback); the Mac-pair evidence stands unchanged for its estate; **[CP-09′] The central bet answered on BOTH pairs — the governing one included**: masks exact (zero-tolerance row satisfied on the H200 pair: 2 spans == 2 assistant turns per trace, r=0 open, stream-end close), prompt_ids byte-identical 2965/2965, decode-fidelity EXACT-BYTES at mask==1 both traces, glue framing byte-identical with the pinned G6 tail; native merge held live end-to-end (glue ids unset, glue_stitched 0, full G7 conjunction) and at REPLAY (the merged stream IS the wire context — teacher-forced directly, no de-stitch, nothing F2-shaped). Nothing attributable to Polar; verdict PASS WITH FINDINGS (docs/reports/CP-09prime.md). **[CP-22] The registry seam re-verified at the re-vendored tree** (`ValidatingPrefixMergingBuilder` resolves, MRO `→ PrefixMergingBuilder → BaseTrajectoryBuilder`) — with the finding that the recipe-verbatim venv rebuild BREAKS it (`gsj_rollout` never installed; REVENDOR.md corrected). **And the unlanded refactor this row has tracked since CP-02 is now priced**: simulated as landed, the refactored `build()` keeps a single `status="COMPLETED"` site and the stats dict, so P1/P2's source hunks apply clean against it — the message-level grouping the pin's README promises would arrive with it, which is what would retire the ADR-0007 stitch (dormant since CP-04′) |
| 9 | gate G1 skill_card | sha256 of the rollout-resolved skill-card text ∈ approved set; free prompts pass — **the predecessor read the card from the episode's own checkout** (`gsj-envloader task.py:878-885`) and hashed those bytes itself | `checks.check_skill_card` (CP-13) over the **submit-stated** `prompt_source`/`skill_card_hash` in trace metadata — the same contract on evidence gathered one hop earlier | PARITY | CP-11 decides survival; **[CP-11] approved set derived** (row 23): both staging cards, predecessor values reproduced; "as resolved" == card bytes while skill-row resolution stays ADR-0003-deferred — CP-11b's open question is the trace-side evidence for WHICH card a task resolved. **[CP-11b] DECIDED: unimplementable as specced, blocker named** — nothing on the trace states which card resolved (measured: both real episodes' first user message, 626 chars, neither equals nor contains the 616-byte card), and without `prompt_source` a hash test cannot distinguish a skill row from a free row that must pass n/a. Fix recorded in the spec: state `prompt_source` (+ card hash) in `TaskRequest.metadata` — one line in `config.render_task_request` at its next freeze-lift, natural landing with the taskbank (ADR-0003); the approved set is ready and waiting. **[CP-13] LANDED — GAP → PARITY**: `config.render_task_request` states `prompt_source` (`free` \| `skill:<name>`) in `TaskRequest.metadata` — arriving through the render parameters since `cli.py` stays frozen (its path is definitionally `free`: resolution never happens there) — and, for skill sources, `skill_card_hash` computed at render from the resolved card bytes (convention 1; the real summarize card reproduces the pinned value, test-proven); the taskbank (ADR-0003) passes `skill:<name>` + card text when it lands. `checks.check_skill_card` reads the hoisted statement (the CP-11 channel): `free` passes n/a finding-free, a skill source verifies the stated hash ∈ `skill_card_hash`, anything else — absent, bare `skill:`, unrecognized — fails closed `G1:missing_evidence:prompt_source`, a skill source without its hash fails `G1:missing_evidence:skill_card_hash`. Clean on both real episodes in the post-CP-13 stamped shape; fixture-era bodies (no statement) earn the missing-evidence finding honestly, the golden-mapping precedent. **The delta from the predecessor, named rather than implied**: it hashed the card file read from the episode's own checkout, so a case repo whose `skills/<name>/SKILL.md` had drifted was caught; this hashes a statement made before the sandbox exists, so it catches a wrong or unpinned card but not a drifted checkout. Two residuals, both owned: (i) **the card hash computed sandbox-side** — the instrument the predecessor had — is a wishlist item owned by `pi_harness.py`, not row 4; (ii) tying the *instruction text* to the card (the `<task_id>` substitution semantics) is genuinely skill-row resolution, ADR-0003's, row 4. The API deliberately keeps (i) open: `render_task_request` accepts `skill:<name>` with no card text, states no hash, and G1 fails closed `G1:missing_evidence:skill_card_hash` until whoever reads the checkout supplies it — so ADR-0003 is not forced into submit-side resolution |
| 10 | gate G2 system_prompt | sha256 of the wire system prompt ∈ approved set; path-sensitive, collapsed to a singleton by constant container paths | `checks.check_system_prompt` (CP-11b), the `/workspace` singleton set; different sandbox mount paths still change every hash — re-derive walk then | PARITY | expect a re-derive walk when Polar's mounts differ. **CP-10 finding (b), binding on G2 and G6 both — the one genuinely silent hazard the template investigation found**: both pinned chat templates coerce a non-string `message.content` to `''`, and pi sends `user` content as a content-part list, so an OFFLINE re-render of a message log through the pinned template silently produces **empty user turns** — a prompt that never existed, hashed and compared as though it did. Live serving is safe (vLLM flattens content parts before templating), which is exactly why an episode would never surface it. **Rule: any check that re-renders prompts from message logs, or reads message content at all, normalizes content parts first.** Landed as `checks._content_text` (used by the G5 census, tested across four content envelopes); G2/G6 must use it at CP-11 rather than reading `message["content"]`. **[CP-11] approved set derived** (row 23): the `/workspace` singleton property HOLDS on this stack — both real episodes' wire system prompts byte-identical to the derived singleton (4,466 chars, 4,476 UTF-8 bytes), hash reproducing the predecessor's pin; G2 is landable at CP-11b. **[CP-11b] LANDED and validated — GAP-class TBD → PARITY**: `checks.check_system_prompt` hashes every wire `system` message through `_content_text` (finding (b) honored — the typed-parts re-envelope of the same prompt passes, a one-byte edit fails `G2:system_prompt_hash_not_approved`, zero system messages fail closed `G2:missing_evidence:system_prompt`); clean on both real episodes, doctored failures verbatim in the CP-11b report |
| 11 | gate G3 tool_roster | sha256 over canonical JSON of the tools array **as sent on the wire** | `checks.check_tool_roster` (CP-11b) over `trace.tools` — persisted == wire for tools (CP-06) | PARITY | inseparable from row 31; CP-03: the wire tools array IS captured — persisted completion records carry it in both `original_request` and `transformed_request` (`docs/polar/completion_record.json`); caveat: the persisted `transformed_request` is pre-engine-shaping (the `logprobs`/`return_token_ids` fields sent on the wire are absent from disk); CP-05: the MERGED trace's `tools` field is the FIRST completion's transformed-request tools only (`record_utils.py:117-122,150` via `prefix_merging.py:276`) — a mid-session roster change is invisible in the merged trace, so receiver-side G3 must be complemented by a builder-subclass per-completion roster check; **CP-06 ANSWERS the wire question**: three-way diff on live pi traffic (`spike/wire_diff.py`) shows `tools` byte-identical across `original_request` == `transformed_request` == the engine wire body (neither the transformer nor engine-prepare touches `tools` or `messages`; the wire-only deltas are exactly `logprobs`/`return_token_ids`/`top_logprobs`/`stream`/`stream_options`) — **the persisted `transformed_request` IS the wire form for everything G3 hashes**, so G3 is implementable from captured requests (per-completion, builder-side) and from `trace.tools` (receiver-side, first-completion caveat standing). **[CP-11] approved set derived** (row 23): both real episodes' `trace.tools` canonical-hash to the predecessor's pin exactly — pi 0.83.0 + mcp==2.0.0 generate byte-identical wire schemas under Polar's proxy; G3 is landable at CP-11b. **[CP-11b] LANDED and validated — TBD → PARITY**: `checks.check_tool_roster` canonical-JSON-hashes `trace.tools` against the approved set (predecessor's `store.py` convention byte-exact, `allow_nan=False` with unhashable content a finding rather than a raise); clean on both real episodes, one renamed tool fails `G3:tool_roster_hash_not_approved:<hash>`, an absent roster fails closed; the CP-05 first-completion caveat stands in the docstring, complemented by the builder's `R11` |
| 12 | gate G4 codec | tokenizer.json git-blob OID + chat-template sha256 ∈ approved sets | not landed receiver-side — no codec evidence rides the callback; verified estate-side by the pins walk at bring-up (ADR-0011) | GAP | four distinct hashing conventions across the gates — reproduce exactly. **CP-10 finding (a), the G4 blind spot**: G4 as specced pins the CODEC snapshot's chat template (`Qwen/Qwen3-0.6B` @ `c1899de…`, sha256 `a55ee1b1…`, 4168 chars) while the engine renders with the SERVED snapshot's (`mlx-community/Qwen3-0.6B-bf16` @ `42096995…`, sha256 `87a2728c…`, 4116 chars) — two different files, so the gate would pass without ever having measured the artifact that actually built the prompt. Harmless today and measured to be so (the diffs are confined to `content`/`reasoning_content` type guards; the `add_generation_prompt` tail is byte-identical; both render byte-identically on pi's normalized shapes) — but the binding rule is now recorded in `docs/checks-spec.md`: **G4's chat-template input is the template the engine actually renders with**. CP-04′ fixes it incidentally by adopting a template via `--chat-template <file>`, making the served template an explicitly pinned file. **[CP-11] approved sets derived per the binding rule** (row 23): `tokenizer_hash` = the git-blob OID, measured IDENTICAL across codec and served snapshots (the mlx conversion carries `tokenizer.json` byte-for-byte) and equal to the predecessor's pin; `chat_template_hash` pinned to the SERVED snapshot's `87a2728c…` (4116 chars) with the codec's `a55ee1b1…` (4168) recorded in provenance and deliberately NOT approved (a dead entry weakens the gate). Mac-estate-specific: the served template re-derives at CP-04′ by design. CP-11b's residual is mechanism, not values: where the receiver gets codec evidence to hash. **[CP-11b] The mechanism is DECIDED — ADR-0011: measure-at-serve, at the pins walk — and the gate stays GAP receiver-side with the blocker measured, not assumed**: zero codec evidence rides the callback (both real bodies probed — no fingerprint/tokenizer/template keys anywhere), and the only fingerprint that exists at the pin (`response.system_fingerprint` on the persisted per-completion record, an engine platform string) is not a codec identity and never rides the callback (CP-05). Trust-provenance rejected — the CP-09 F1 shape: it verifies the claim, not the artifact. G4 is verified estate-side by `pins/derive_pins.py` against the served snapshot at bring-up (CP-04′ DoD items 3–5); residual named: per-episode binding (row 22, estate-owned). **[CP-04′] The measure-at-serve walk EXECUTED on the H200, and finding (a)'s fix landed as designed**: the engine serves an explicit template file (`--chat-template staging/serving/qwen3_training.jinja`), so `chat_template_hash` now pins the file's own bytes (`1d944ff8…` — the CP-11 known-expiry note resolves); BOTH snapshot-embedded templates are recorded-not-approved (on the H200 the codec and served snapshots are the same `c1899de…`, so the split that created the blind spot does not exist, and the served file is the one artifact that builds wire prompts); `tokenizer_hash` re-verified unchanged from the H200 served snapshot. Status stays GAP receiver-side by decision (ADR-0011), exactly as before |
| 13 | gate G5 page_cutoff | pin-free: max checkout page == T, pages contiguous from 1, every search-result page ≤ T | `checks.py`; needs a page census reconstructable from the trace | PARITY | unreconstructable from the trace → abandon (§9) — **not triggered: CP-10 landed the backstop and the census IS reconstructable**. `checks.check_page_cutoff` rebuilds the page census from the trace's own tool-result texts with the two spec regexes, filtered to `mcp_gsj_search_case` (decisions are exempt; a built-in `read` of `md/page_0007.md` cites the already-clamped checkout), and fails `G5:search_page_gt_timestep:{page}>{T}`. Verified on both real episodes (CP-07: pages [1,5,7,9,11] ≤ 12; CP-09: same) and on doctored copies (page 18 at T=12 fails; the same page cited by a decisions result does not). **Two reasons this is GAP, not PARITY**: (a) the predecessor's other two clauses — max checkout page == T and contiguity from 1 — need the CHECKOUT census, a property of the sandbox filesystem that appears nowhere in the trace and is backstopped instead by the `timestep-{T}` clone itself; (b) T currently reaches the check only through the `mcp_gsj_case_status` result's own statement, because nothing puts the timestep into trace metadata — the structural home is `TaskRequest.metadata` via `config.py` (frozen this CP), a one-line CP-11 change, and until then an episode that never calls `case_status` is rejected `G5:missing_evidence:timestep` (fail-closed, loud, and a live rejection risk). **[CP-11] Both reasons resolved — GAP → PARITY.** (b) landed structurally: `render_task_request` puts `{case_id, timestep}` into `TaskRequest.metadata`, verified hop-by-hop by executing the vendored code (dispatch copy `pipeline.py:189`, proxy stamp `server.py:371-377`, trace-top-level hoist `prefix_merging.py:371-375`, `checks._episode_timestep` reads it first); the `case_status` fallback stays as redundancy for fixture-era traces; fail-closed unchanged; reserved metadata keys (`session_id`/`task_id`/`evaluation`/`policy_version`) documented and test-guarded. (a) is **DECIDED: the checkout-census clauses are DROPPED, owner this row** — the checkout census is a sandbox-filesystem property no trace carries; its enforcement is the `timestep-{T}` clone itself (proven live at CP-07) now hardened to `--depth 1`/no-remote/no-reflog (row 2), which closes the only checkout-side bypass ever found; a harness-recorded probe was rejected because the harness attesting its own checkout is the same self-reporting class as the `case_status` circularity, bought with budget lines the law does not have. The trace-side census guards what the agent actually SAW (search results), which is the clause that matters for training data. **[CP-13a] The dropped clauses RETURN — the reason they were dropped no longer holds.** They were dropped because the checkout census is "a sandbox-filesystem property no trace carries"; the workspace echo now carries it (`gsj_workspace`: branch, commit, tree, shallow posture, surviving remotes, page census), captured after the clone and before pi launches, riding the same A-23 channel as the settings echo — hops executed. `checks.check_workspace` enforces **max checkout page == T** and **pages contiguous from 1**, plus the CP-11 clone cure attested per-episode (`shallow=true`, zero remotes) instead of assumed. CP-11's objection — that a harness-recorded probe is "the same self-reporting class as the `case_status` circularity" — is answered rather than waved away, and the answer is scoped: the branch and max-page clauses cross-check the harness's echo against the TRAINER's independently-sourced `timestep`, so those two compare two sources; contiguity and clone posture are single-source and detect an honest misconfiguration (wrong branch, missing `--depth 1`, a truncated or mis-built checkout), not a hostile harness. What it is not: proof against a harness that lies about its own sandbox — that would need an attestation channel this repo does not have, and the row says so rather than implying otherwise. A missing echo fails closed (`G5:missing_evidence:workspace`) |
| 14 | gate G6 thinking_off | every assistant-turn opening ends with a pinned verbatim tail; zero turns fails closed | `checks.check_thinking_tail` (CP-23): tokenizer-free ids-`endswith` against `g6_expected_tail_ids` over the turn-1 `prompt_ids` suffix and each pre-turn mask-0 interstitial; zero mask-1 spans fail closed | PARITY | **[CP-11b] blocker named and the tokenizer-free mechanism designed (ADR-0011)**: neither this package (pydantic/httpx/pyyaml) nor Polar's venv (A-14's five) carries a tokenizer, so the builder subclass is not a home either. The landing design: pin `g6_expected_tail_ids` — the 41-byte tail as token ids under the served tokenizer — on the next pins walk (tokenizer needed at PIN time only, estate-side by construction), then G6 lands receiver-side as an ids-`endswith` over the mask-0 interstitial span preceding each mask-1 span of `response_ids` AND, for the first turn, over the suffix of `prompt_ids` (measured on both real traces: the first mask-1 span starts at `response_ids[0]` and the turn-1 tail sits at the end of `prompt_ids` — a response_ids-only rule would check zero turns on a single-turn episode; per the standing rule G6 reads token ids, never `response_messages`). Blocked this CP by the no-re-pin wall; CP-04′ re-derives the tail anyway (the Direction-A template changes it by design). **[CP-04′] The pin EXISTS — wishlist item 5 done**: `g6_expected_tail_ids = [151644, 77091, 198, 151667, 271, 151668, 271]`, derived and verified by the served tokenizer estate-side (`pins/derive_pins.py` re-verifies whenever transformers is importable). Measured correction to the anticipation above: the Direction-A template does NOT change the tail bytes — the TRL template's generation-prompt branch under `enable_thinking: false` is byte-identical to the pinned template's (turn-1 renders byte-identical across the two) — what changes is G6's SUBJECT: the tail now also appears in history re-renders, so every assistant-turn opening in the merged stream carries it, which is exactly the shape the CP-11b rule design (prompt_ids suffix + per-mask-1-span interstitial endswith) already covers. The rule itself stays blocked on a `checks.py` freeze-lift (CP-11c or later); status GAP unchanged. **[CP-23] LANDED — GAP → PARITY**: the freeze lifted, the budget resolved first (banking 520 → 497, then ADR-0021's raise to a machine-checked 528 — the ADR-0014 earmark lesson answered), and `check_thinking_tail` landed exactly per the ADR-0011 design pins provenance records: ids-`endswith` of `g6_expected_tail_ids` over the turn-1 `prompt_ids` suffix (plus any leading mask-0 run) and the mask-0 interstitial preceding each later mask-1 span; zero spans fail `G6:missing_evidence:turns`; token ids only, no tokenizer, never raises on content. What it asserts under the symmetric template: thinking stayed OFF at **every** turn opening of the merged stream, history re-renders included. Clean on all four real bodies (CP-07, CP-09, the CP-04′ stitch-retirement episode, the CP-09′ H200 fidelity body — the last two being the history-render subject itself); one doctored failure per clause and the single-turn case proven actually-checked (`docs/reports/CP-23.md`). Thinking-on note for Phase C recorded in the spec §G6: as pinned, a thinking-on estate fails every episode loudly — C-2 re-pins, re-conceives, or retires before the first thinking-on episode reaches a receiver. **[CP-28] The evidence half exists (M9a, `docs/polar/thinking/`)**: on a real 15-episode thinking-on collection the gate failed every episode exactly as designed (G6-only findings, fail-closed, quarantined with forensics, gate unweakened), and every one of the 41 turn openings ends `[151644, 77091, 198]` — the empty-think tail appeared zero times. The measurement favours **re-pin as per-mode pin data**: the 3-id tail is not an `endswith`-suffix of the 7-id tail, so a thinking-on estate pinning it ALONE keeps the gate mode-asserting (thinking-off openings fail it); `pins/` data plus a walk, zero `checks.py` lines, 528/528 untouched. Decision and landing stay C-2's. **[CP-30] C-2 LANDED — re-pin as per-mode pins data (ADR-0024), and the gate is now MODE-DEPENDENT, recorded here**: `pins/thinking-on/pins.gsj.json` is a complete pins document — six non-G6 approved sets byte-equal to the primary's (drift-guarded by `derive_pins.py`), G6 keys carrying the 3-id tail — and the mode reaches the check as the pins FILE the estate selects via `GSJ_PINS_PATH` on both law-6 legs; `checks.py` reads the same key through the same `approved_set` call, byte-unchanged at 528/528. What the gate proves, per mode: **off** — every assistant-turn opening carries the pinned empty-think block, i.e. thinking was OFF at every position the template could have shown it; **on** — every opening ends at the pinned bare generation prompt, i.e. template integrity plus the assertion that the estate genuinely ran thinking-on (no opening carries the off signature) — it no longer proves thinking-suppression, because thinking is on and rides mask-1 sampled content outside any opening. Mode-asserting in BOTH directions by the non-suffix geometry, test-proven both ways (the CP-28 quarantined exemplar passes the full seam under the on-pins and reproduces its recorded quarantine findings byte-stable under the off-pins; a real off trace fails the on-pins). Proven live at CP-30: one thinking-on and one thinking-off episode through the real receiver, both accepted clean, `chains_total == 1` (`docs/polar/thinking-on/`). The estate owns `harness.thinking`/pins agreement — a mismatch fails every episode loudly, the correct failure. Status stays PARITY with the mode-dependence stated: in on mode the gate is deliberately the weaker template-integrity + mode assertion |
| 15 | gate G7 no_compaction | settings canonical-JSON hash + `compaction.enabled == false` + chain snapshot exactly (1 chain, 0 rollbacks, 0 dropped tokens, 1 finalized) | `checks.check_chain_snapshot` (CP-11b) + `checks.check_settings_echo` (CP-13): the CP-05 stats conjunction on `reconstruction_stats` ∧ the settings-hash clause over the harness's echoed rendered settings | PARITY | CP-02: abort→ERROR defect (D3) CONFIRMED at the pin — a mid-chain abort presents a *clean* snapshot, so the snapshot alone cannot satisfy G7's premise; carried patch P2 (abort→session ERROR) is the guard, and `checks.py` adds a `finish_reason` allowlist that catches tail aborts for free; CP-03: P2 landed, adversarially verified faithful, abort tests green, and the propagation chain (builder ERROR → node → SessionResult → slime FAILED → zero loss mask) re-verified link-by-link at the vendored tree; the live run adds the second G7 requirement — a token-id-less backend produces a CLEAN snapshot of N length-1 chains, so require `chains_total == 1` too (row 8); CP-05 tightens the equalities again: require `chains_total == 1` ∧ `chains_reconstructed_truncated == 0` ∧ `completions_merged == completions_total` ∧ (with A-12 verified) `raw_completions_total == completions_total` — filter amputation of a chain TAIL still counts `chains_reconstructed_full` (the `kept == len(chain)` test runs against the post-filter chain, `prefix_merging.py:261-262`) and is invisible to the first two conditions alone; CP-06: the full conjunction observed holding on a real pi multi-turn session (2/2/2/1/0) — the rule is satisfiable in practice, not merely specifiable. **[CP-11] approved set derived** (row 23): `settings_hash` reproduces from the harness's own rendered constant (`{compaction:{enabled:false}}` — the same parsed document, canonical-hashed); G7 is landable at CP-11b. **[CP-11b] The stats conjunction LANDED and validated — TBD → PARITY, with the settings clause a named in-row residual**: `checks.check_chain_snapshot` (session-level — the stats ride `trajectory.metadata.reconstruction_stats`) enforces the CP-05 conjunction verbatim, one byte-stable finding per violated clause, any missing/non-int stat failing closed; clean on both real episodes, all four doctored clauses fire each for its own reason. The residual, honest: **the settings-hash clause has no callback evidence** (measured: zero `settings`/`compaction` occurrences on both real bodies) — compaction-off is enforced at source by the harness's `settings_json` constant (the exact document `settings_hash` pins), but the receiver cannot verify what it never receives; fix is a one-line harness echo into trace-reachable metadata at `pi_harness.py`'s next freeze-lift. PARITY claimed on the degeneration-catching half (the conjunction — the clause CP-03 proved `truncated == 0` alone is blind to), not on the unverifiable clause. **[CP-13] The settings residual is CLOSED**: `PiHarness.setup` echoes the rendered settings document — the object written into the sandbox settings.json, not a template — into the session's gateway-registry metadata (`SessionRegistry.register` on the existing id merges under the lock with status preserved, `session.py:87-88`; A-23: harness and proxy share the gateway process by the `import_path` architecture), from where the CP-11-proven channel carries it: proxy stamp onto every completion (`server.py:371-377`) → builder hoist into trace top-level metadata (`prefix_merging.py:371-375`) — all four hops EXECUTED against the real vendored classes in the component venv, not read. `checks.check_settings_echo` canonical-hashes the echoed document (convention 2) against `settings_hash`; a missing echo fails closed `G7:missing_evidence:settings`, a compaction-ON echo fails `G7:settings_hash_not_approved:<hash>`. The registry-absent case raises loudly at `setup()` (the unechoed episode would be rejected fail-closed at the receiver anyway; earlier is cheaper). Honest limit unchanged: the echo is the harness's own statement — self-reported evidence, law 6's declared class. **[CP-22] P2 re-applied byte-faithful at the re-vendor rehearsal** (clean by script, reverse-apply exact, abort tests green), and the named refactor risk is priced: P2's anchor — the single `status="COMPLETED"` finalize site — SURVIVES today's `polar`-branch refactor (dry-run applied clean in the scratch simulation, `session_had_abort` landing immediately at the finalize site); no upstream abort→ERROR path exists anywhere (zero `abort` occurrences in the refactored builder), so P2 stays ours |
| 16 | quarantine | two layers: hygiene (any gate failure ⇒ never served, kept for forensics) + row-level cap-quarantine | receiver drops failing traces at the source; no store to quarantine into | DROPPED | dropped with the store (§3); the at-source rejection half survives by law 6 — forensic retention is the trainer's problem; CP-02: `node._push_result` → callback → our receiver confirmed as the natural zero-patch checks home; upstream's own failed experiment (a `had_abort` metadata flag dropped in Polar→slime serialization) says validation-critical signals must ride status/structural fields, never metadata flags; CP-03: one real callback payload dumped (`docs/polar/callback_session_result.json` — the exact `node._push_result` body); NOTE the rollout server's persisted `ses_*.json` is NOT that body — `_storage_payload` strips `trajectory.status`/`trajectory.error` before writing — the receiver must validate the POSTed payload, never reconstruct it from rollout disk; CP-05: strip confirmed disk-only at `pipeline.py:423-436`; the callback endpoint validates pydantic shape only (`rollout/server.py:170-173`); and the rejection seam is REAL — a builder-subclass `status=ERROR` survives the whole path because the node only escalates, never clears (`node.py:579-587,602-610,615-624`; eval merge preserves status, `:700-738`); **CP-08: the at-source half LANDED** — the receiver validates the POSTed body through `checks.validate_session_result` and quarantines rejects to `<quarantine_dir>/<session_id>.json` carrying the findings AND the full body (forensics beat counters, ADR-0008 §2), answering Polar 200 either way (rejection is our decision, not a delivery failure); fixture + doctored bodies tested; the trainer-side retention story stays the trainer's |
| 17 | store | append-only content-addressed Parquet `TrajectoryStore` | — | DROPPED | trainer's problem |
| 18 | ready/mix | pinned predicate grammar + composition planner | — | DROPPED | trainer's problem |
| 19 | staleness | `policy_lag` vs the shared version counter; teacher tapes null-lag by definition | — | DROPPED | trainer's problem |
| 20 | serve accounting | lease-based serve/commit in one transaction; `serve_count`; SPI thermostat | — | DROPPED | trainer's problem |
| 21 | collation | four shipped collators (`Default`/`SFT`/`OPD`/`RLVR`); no truncation anywhere by design | — | DROPPED | trainer's problem |
| 22 | provenance | `env.provenance`: the four evidence hashes, codec fingerprint, applied sampling block, exact invocation argv | trace metadata must carry an equivalent | GAP | CP-08/CP-09; CP-02: pin bug — anything a hook adds to `record.metadata` in memory never reaches the persisted completion files (the writer enqueues `dict(metadata or {})`, not `dict(record.metadata)`); P3 carries the fix; provenance must not rely on in-memory metadata mutation; CP-03: P3 landed and verified — the persisted record's metadata is now record-truthful, so provenance MAY ride `record.metadata` and reach disk; inertness confirmed on a real persisted record (no `policy_version` key with no declared version); CP-05: builder-subclass metadata keys survive to the callback verbatim and into slime `Sample.metadata["polar"]` (`adapter.py:141-160` deep-copies both trajectory and trace metadata); the key `evaluation` is RESERVED (overwritten by the eval merge, `node.py:737`); chain-level trace metadata presents the FIRST completion's values as the chain's (`prefix_merging.py:371-375`) with no homogeneity check — per-turn truth lives only in the `completion_metadata[]` list, so the receiver's "all per-turn stamps equal" rule must iterate that list, and the `prefix_merging cross-version fallback` referenced by a `storage.py:150` comment does NOT exist in the vendored builder (fork half, deliberately not carried); **CP-07: the builder-subclass metadata channel used for real** — `gsj_validation` (builder id, `findings`, `glue_stitched`) rides the callback verbatim (`docs/polar/pi-corpus/callback_session_result.json`), never touching the reserved `evaluation` key; the harness's `postprocess()` artifact directory is joined to the trace by the session id, the provenance seam CP-08/CP-09 build on; CP-08: the receiver persists the full callback body verbatim (status/error intact) at `<traces_dir>/<session_id>.json` — same join key as the artifact dir; provenance *content* (the evidence hashes) stays CP-09+. **CP-09 sampling-provenance finding**: pi sends no sampling parameters, the wire is not persisted (row 7), and nothing on the trace records what sampling the engine applied — the applied block is knowable only from engine-side evidence (the serve argv + the engine request log) and is therefore ESTATE provenance, not trace provenance. The served mlx-community conversion ships no `generation_config.json`, so an unpinned engine silently samples pi's parameterless requests at vLLM neutral defaults (T=1.0 — CP-07's episode did exactly this); CP-09 pins `--generation-config <dir>` with the codec snapshot's file (sha256 `2325da0f…`) and verifies application from the request log. Any future provenance surface must carry the engine's generation-config pin. **[CP-12] FINAL: GAP, half deliberate** — the CHANNEL is proven end to end (builder metadata → callback → slime, CP-05/CP-07; `{case_id, timestep}` structural since CP-11; artifacts joined by session id), but the predecessor's provenance CONTENT does not ride the trace: the applied sampling block is estate provenance (CP-09 F1 — knowable only from the serve argv + request log), the codec identity is estate-verified at the pins walk rather than stamped (ADR-0011 — zero codec evidence on the callback, measured), and no image tag or argv is stamped anywhere. The deliberate half: trust-provenance was REJECTED for cause (ADR-0011 — verifying a claim instead of the artifact is the F1 shape). The open residual: per-episode binding — nothing ties episode N's traces to the bring-up measurement; the cure is an estate provenance surface at CP-04′ bring-up, outside this repo by the scope law. **[CP-13a] The CORPUS half of the residual closes**: the workspace echo binds each episode to the exact commit and tree it ran against (`gsj_workspace.commit`/`.tree`, plus the credential-stripped clone URL and the page census), so "nothing ties episode N to what it actually read" is no longer true for the corpus. The CODEC and SAMPLING halves are untouched and stay estate-owned (ADR-0011, F1) — the echo is the harness's view of the sandbox filesystem, and the engine's identity is not visible from there |
| 23 | pins | `gsj-pin`: approved-set JSON, generated data, zero hash literals in code | `derive_g2.py` + captured evidence carried (`pins/`); the pinned VALUES did not move — stale by construction under Polar's mounts (ADR-0002); the `gsj-pin` generator is predecessor library code and stayed frozen there | PARITY | deliberate: no valid approved sets exist here until the derive → re-pin → first-episode-validate walk under Polar's mount scheme (CP-07/CP-10/CP-11); the format `checks.py` consumes is specified in `docs/checks-spec.md`. **[CP-11] The walk ran — GAP → PARITY**: `pins/pins.gsj.json` (format `gsj-pins/1`, one provenance block per key: episode, artifact, host, Mac-specific flag) holds this repo's first valid approved sets, every value derived from repo-owned or estate-resident evidence — G3 from both real episodes' wire `tools` (convention anchored on `pins/tools.captured.json`), G2 from both episodes' wire system prompts (the `/workspace` singleton holds here, byte-identical across episodes), G7 from the harness's rendered constant, G1 from the staging cards, G4's tokenizer OID from both snapshots (identical) and its template pinned to the SERVED snapshot per finding (a), codec hash recorded-not-approved. Every derivable value reproduced the predecessor's pin — "stale by construction" measured out as value-stable under docker mounts, with provenance now this repo's own. `pins/derive_pins.py` re-runs the whole walk and fails loud on divergence (CP-04′ reruns it; served template diverges there by design). Residual: the first-episode-VALIDATE leg needs a consuming gate + a fresh episode — CP-11b, STOP-walled here. Only `chat_template_hash` is Mac-estate-specific. **[CP-11b] The validate leg is DONE — the row CLOSES**: gates G2/G3/G7 consume `pins/pins.gsj.json` at check time (`checks.approved_set`, repo-relative `PINS_PATH`, missing file/key raises — never fail-open, and a snapshot test proves no pinned value appears as a literal in `checks.py`); both real episodes pass the full seam clean and every landed gate fails on one doctored input for its own reason (verbatim lines in the CP-11b report). "Fresh episode" was STOP-walled again (no estate), so "first episode" = the two real episodes this repo owns — the same two the sets were derived from; a genuinely fresh episode first passes these gates at CP-04′/CP-09′. **[CP-16] The seam grew the resolver leg (ADR-0017)**: `PINS_PATH` = `GSJ_PINS_PATH` override → checkout → the wheel's packaged copy (`pins/pins.gsj.json` force-included at build, single source) — the trainer leg works from a wheel, and a foreign estate that skips the override fails loudly as `*_not_approved` (set membership), never silently. **[CP-19] And now it SAYS so (ADR-0019)**: on the third resolution case only — an installed wheel with no `GSJ_PINS_PATH` and no checkout, which is exactly the PyPI stranger — `checks` emits one `UserWarning` at import naming the packaged path, stating that these are the reference estate's approved sets rather than defaults, and naming the cure. Silent under an explicit override (the operator has chosen) and under a checkout (a developer is in-tree); a warning and never a raise, so the fail-closed posture and every rule body are untouched. The packaged copy cannot drift from `pins/` (force-included from it, never duplicated), so a re-pin costs a checkout consumer nothing and costs a published artifact a rebuild — a wheel is a snapshot of the approved sets as of its build |
| 24 | deterministic env pinning | uni-agent by SHA; sglang exact-pinned; generated `collector-requirements.txt`; image tag in provenance | Polar vendored by SHA (law 4) + pinned pi 0.83.0 | PARITY | CP-03: the Polar half landed — `/POLAR_SHA`, patched tree committed, component venv per upstream's own recipe. **[CP-12] FINAL: PARITY** — Polar pinned by SHA with recorded recipe and carried patches (CP-03, `vendor/REVENDOR.md`), pi 0.83.0 restored from the predecessor's byte-exact lockfile via `npm ci` (CP-06 image), upstream's own `uv.lock` kept, component venvs recreated per recipe (never moved — CP-01's rule), the sandbox image a pinned config value (law 5). The one predecessor clause not reproduced — identity stamps riding TRACE provenance — is row 22's GAP, not a pinning gap. **[CP-22] The pin is now proven REPRODUCIBLE, not just recorded**: the re-vendor rehearsal re-fetched `f0e8343a`, re-extracted, re-applied the patch set by script, and produced a tree byte-identical to the committed one (`git diff HEAD -- vendor/` empty; reverse-apply walks back to the pristine pin exactly) — A-8 resolved, mechanical cost ~2 minutes, `vendor/REVENDOR.md` corrected where execution proved it wrong (the A-14 venv install, the byte-fidelity tripwire, the conditional smoke) |
| 25 | one-YAML config | one YAML is the complete construction surface for both sides | `config.py`: seven sections + reserved free-form `user:`; renders Polar's `topology.yaml` and `TaskRequest` bodies | PARITY | CP-08 (ADR-0008 §1): GENERATE, not sit-beside — the server renders the topology, the trainer renders task requests, from the same file; both renders golden-tested AND validated against Polar's own `TopologyConfig`/`TaskRequest` models; unknown keys raise naming section+key; `user:` is validated as a mapping and never read (the predecessor's §9 pattern) |
| 26 | bounded collection | `gsj-collect`: bounded rounds, graceful drain, stated exit codes | `gsj-rollout submit`: bounded wait (`--timeout` + `--grace`), one progress line per state change, stated exit codes (0/1/2/3), SIGINT-clean `serve` | PARITY | H-34's table stakes landed at CP-08. **The row's question, ANSWERED** (stated in `config.py` and `submit --help`, ADR-0008 §5): a COLLECTED episode = status `COMPLETED` ∧ `gsj_validation.findings == []` ∧ zero `checks` findings — ERROR/TIMEOUT never count; `--episodes N` targets **N attempts** (`num_samples=N`), NOT collect-until-N-accepted (Polar's scheduler owns episode counts); a rejected trace counts as a consumed attempt, is quarantined, and is never retried automatically — exit 1 says collected < attempted. The predecessor's `truncated`-counts ambiguity has no analogue by construction: our builder flips truncation-class defects to ERROR (CP-07) |
| 27 | logprob sentinel guard | validators require `rollout_log_probs` finite and ≤ 0 everywhere — written to admit the `0.0` that record semantics place at mask==0 positions | `checks.py` guards the `-9999.0` sentinel with an **explicit threshold rule** — the finite-and-≤0 rule alone passes it (A-7 audit, spec corrected) | **PARITY** | **RESOLVED at CP-10 — landed and platform-conditioned.** `checks.check_logprob_discipline` implements the whole spec section: `LP3` sentinel (≤ −9000.0 at `mask==1`, `CheckPolicy.sentinel_threshold`), `LP1` absent array on a trainable trace, `LP2`/`LP8` length rules, `LP4` NaN/±inf (Python's `json` really does accept those literals off the wire), `LP5` positive, `LP7` the empty-mask validator escape, plus `TR1` the `finish_reason` allowlist and `TR2` the reasoning-mask re-vendor canary. **The row-27 question itself — the suspicious zero — is answered as an allowance, not a hard fail**: `CheckPolicy.zero_at_mask1_max_rate`, default 0.25 of `mask==1` positions, against CP-09's measurements on BOTH stacks (golden 20/292 = 6.8%, collected 15/363 = 4.1%, both otherwise discipline-clean, both bf16 rounding of genuinely-near-zero RAW logprobs — the raw replay hypothesis fits at the numerics floor, the renormalized one ~6× worse). 0.25 is ~3.6× the higher measurement: no measured trace trips it, a degenerate mostly-zero array still does, and a CUDA estate restores the original strictness with `0.0`. A knob rather than an engine sniff because the trace carries no engine identity (row 22). Fixture-verified: the CP-09 trace, the CP-07 trace, and the predecessor's golden tokens all pass clean; one doctored trace per rule fails with its exact finding string. Replay-style validation deliberately NOT built (CP-09 F2–F4; reasons recorded in `docs/checks-spec.md` §Replay). Earlier notes: CP-02: upstream has no value-level guard at all, so ours is load-bearing; also make absent/None `response_logprobs` a hard failure; CP-05 corrections: (a) the pin's missing-logprob rejection is STATUS-derived, not config-gated — `require_trainable_logprobs` is only a kwarg fed from `trainable = status not in (ABORTED, FAILED)` (`adapter.py:120,268`); a trainable trace with any `mask==1` and no logprobs RAISES trainer-side — our receiver rule stays because it fires earlier and on both sides; (b) zero value-level checks tree-wide re-confirmed by grep; (c) `models.py:116` lets an EMPTY `loss_mask` bypass the length validator — `checks.py` must hard-fail an empty mask on a trainable trace, never inherit that escape; (d) the builder's `0.0` placeholders can never land at `mask==1` (`prefix_merging.py:364,368` — any missing trainable slot nulls the WHOLE array first), so a `0.0` observed at `mask==1` is engine-reported and our suspicious-zero rule stands; **CP-04 measured a false-positive surface**: on vllm-metal (MLX bf16) 20/292 mask-1 sampled logprobs are engine-reported as exactly `0.0` (near-delta renormalized distributions under top_k 20 round to p=1.0) — the golden episode is otherwise clean, so the rule as specced would reject genuine Mac-pair traces; CP-10 must decide platform-conditioning (e.g. rule active on CUDA engines, demoted to counter/warn on MLX) instead of silently inheriting either behavior. **CP-09 confirms the artifact recurs on the Polar side** (15/363 mask-1 logprobs exactly `0.0` on the collected trace, 20/292 on the golden — same engine, both otherwise discipline-clean), so the platform-conditioning question is now symmetric across both stacks, and CP-09 additionally measured that captured values are RAW model logprobs (row 7), so the near-delta `0.0`s are bf16 rounding of genuinely-near-zero raw logprobs, not renormalization semantics. **[CP-04′] The conditioning premise "a CUDA estate restores the original strictness with `0.0`" is MEASURED FALSE**: on the H200 (CUDA vLLM 0.26.0, bf16, native) exact-`0.0` at `mask==1` recurs on every episode both stacks produced — golden 16/258 (6.2%), our stack 34/237 (14.3%), and 2119/8506 (24.9%) on a repetitive-loop episode that came within 0.1pp of the 0.25 allowance. The artifact is bf16-near-delta rounding, not an MLX platform quirk; the strict-0.0 policy rejected a clean H200 episode live (the receiver did its job — fail-closed, loud) before the estate config moved to the 0.25 default. Two consequences, recorded: (a) the H200 estate runs `zero_at_mask1_max_rate: 0.25` (`staging/rollout.h200.yaml`), not 0.0; (b) repetitive-loop episodes push the rate toward the boundary — the allowance is doing real work on CUDA, and CP-09′ should treat the zero-rate as a measured platform property, not a defect signal **[CP-09′] corroborated live, twice**: the qualifying clean episode measured 37/510 = 7.3% (golden 16/258 = 6.2% — the pair's 3rd/4th in-allowance CUDA measurements), and the receiver REJECTED a repetitive-loop episode at 2181/8192 = 26.6% > 0.25 during collection (attempt 2) — the allowance is load-bearing on CUDA, fail-closed and loud, exactly as this row predicted |
| 28 | async staging | no capability by this name; nearest referents: per-episode asyncio gateway loop, collector streaming rounds | the receiver is a callback endpoint — asynchronous by construction | PARITY | pinned down at CP-08: at our layer this means only that results arrive by push (the threaded receiver accepts callbacks without the trainer blocking) while the client polls independently — nothing more survives from the predecessor referents. Finding recorded en route: the node's per-session callback is pinned to Polar's own rollout server (`pipeline.py:184` overwrites the dispatch `callback_url`), so the zero-patch push channel to us is the manager's **task-terminal** `TaskResult` envelope (`TaskRequest.callback_url`, `manager.py:164-179`) — per-session push immediacy would need a vendored patch; the client's poll path is unaffected |
| 29 | multi-provider harness support | deliberately single-harness: pi via pinned uni-agent; "provider" meant only the pi models.json id and the tool-call parser | Polar's `import_path` runs arbitrary harnesses; we need only pi | BETTER | **[CP-12] FINAL: BETTER** — the predecessor is single-harness by design; Polar's `import_path` loaded OUR non-preset harness into the gateway process with zero vendored edits (CP-06) and ran it end to end on real corpus episodes (CP-07/CP-09), and the pin ships eleven preset harness modules (`src/polar/agent/presets/`, counted at CP-12 — the prompt's "nine" is the only correction; pi's own preset pins 0.67.68, which is why we bring our harness). BETTER claimed on the mechanism, exercised by construction — our harness IS an arbitrary harness; only pi was ever run here, deliberately |
| 30 | HPC runtime | none — Docker-only, single H200 host, SSH-tunnel topology | Polar supports Apptainer natively; deferred by A-11 | TBD | potential BETTER; law 5 keeps it free; CP-02: two forks (leeyykk, skzhang1) independently rework `runtime/apptainer.py` on real clusters (direct-exec instead of instance start/stop, dropped resource limits, proot wrapper) — field evidence the pin's Apptainer runtime needs work before A-11 is exercised. **[CP-12] FINAL: TBD, with the reason it was never reachable** — A-11 deliberately kept Docker as the Mac pair's single controlled variable, and no daemon-less cluster exists in this project's estate (the H200 estate is Docker too), so no checkpoint could exercise Apptainer without inventing a platform to run it on. Potential BETTER, genuinely unassessed; the field evidence stands (two forks independently rework `runtime/apptainer.py` before using it at scale), and law 5 keeps `gsj_rollout/` runtime-agnostic so nothing here blocks the attempt when a cluster demands it |
| 31 | tool roster visible in config | `tools_allowlist` is a required, pinned `TaskConfig` field rendered to `--tools` argv; G3 hashes the wire-rendered roster | `tools_allowlist` is a required `AgentSpec.settings` list, rendered 1:1 to `--tools` (CP-07); config == argv == wire, byte-identical | PARITY | keep the roster a hashed field in `config.py`; close at CP-07/CP-08. **CP-06 answer to the row's question**: the chain config-field → `--tools` argv → wire `tools` array is fully observable — pi renders exactly the `--tools` allowlist as the request's `tools` (7 requested, 7 on the wire, schemas pi-generated), and the wire array survives byte-identical into the persisted `transformed_request` and the trace's `tools` (row 11) — so a pinned config field gives G3 a pinned input with zero extra capture machinery; the spike's argv-literal roster (`spike/pi_harness_spike.py:_TOOLS`) is exactly the anti-pattern the row names, acceptable only because the spike is not the harness; CP-07 must make it an `AgentSpec.settings`/config field. **CP-07 CLOSES the row**: `tools_allowlist` is now a required `AgentSpec.settings` list; the harness renders it 1:1 into `--tools`, and the full chain was verified live — the configured 11-name allowlist == the rendered `--tools` argv == the wire `tools` array on the persisted trace (`docs/polar/pi-corpus/trace.json`), all byte-identical. G3 has a pinned input with zero extra capture machinery. CP-08: the roster's one home is now `harness.tools_allowlist` in the one YAML, rendered 1:1 into `AgentSpec.settings` (golden-tested: config == rendered settings) |
| 32 | train/eval split enforcement | three layers: `eval_case_ids` in the manifest → the taskbank's per-row `split` → **the loader's role lock** (serving eval rows for training refused at the source) | the split is a **directory property of the corpus tree** (ADR-0015, CP-14), carried end to end — tree → `corpus.lock.json` `cases.<id>.split` → the (deferred) bank row → `TaskRequest.metadata.split` → trace metadata — and verified for reality by the pipeline (`verify`'s split-vs-lock clause) and for vocabulary at the receiver (`TR3:split_not_train_or_eval`; both legs of law 6). **Nothing here enforces the split's meaning**: the loader was dropped at CP-00 (§3, trainer's problem), so no component refuses to train on a correctly-labeled eval trace | DROPPED | added at CP-14 — the enforcement half is deliberate, decided at CP-00 with the loader and made explicit here rather than left implied by row 18's `ready/mix` drop. The carry half is real and improved over the predecessor's manifest key (the split is now un-missable in the tree, exactly-one-membership is a hard validation failure, and a moved case that skips re-scaffold fails `verify`), but a label is not a lock: the trainer owns not training on eval, stated in ADR-0015, the contract's "what the split means downstream", and the spec's §The split label. Nothing to cross-source trace-side, measured: case repos are split-agnostic (ADR-0006 — no branch, file, or ref differs by split), deliberately, so the sandbox cannot reveal held-out status to the agent |

## 8. Standing rules

The seven scope laws as operating rules:

1. Own task → sandbox → agent → trace and refuse everything else: no
   storing, scheduling, scoring, weighting, versioning, or training.
2. Count our own lines every checkpoint; crossing 2,000 (ADR-0012; 1,500
   until CP-12) stops the work until justified in an ADR.
3. Never touch `gsj-envloader` — read it, compare against it, fall back to
   it, but no checkpoint modifies it.
4. Vendor Polar by pinned SHA with a recorded re-vendor recipe; carry
   patches as first-class, documented artifacts.
5. Keep `gsj_rollout/` runtime-agnostic: the runtime is a config value and
   Polar's sandbox interface (start/stop/exec/upload/download) is the only
   contract assumed.
6. Ship one `checks.py` and run it on both sides of the wire — the
   receiver drops bad traces at the source, the trainer re-verifies on
   arrival.
7. Treat findings as deliverables: a checkpoint that proves Polar cannot
   do something is a success, recorded in the gap register, not a failure
   to route around.

## 9. What would make us abandon this

Stated in advance so the decision isn't made under sunk cost. Any of:

- `prefix_merging` output does not match the golden reference and the
  mismatch has no fix in **our** code.
- The proxy needs a forked translation layer to speak to pi 0.83.0.
- The cutoff cannot be injected per-episode through any sanctioned channel.
- G5 (the page cutoff) is unreconstructable from the trace.
- Our own code exceeds ~2,000 lines (ADR-0012; ~1,500 until CP-12) — the
  "thin shell" premise is false.
