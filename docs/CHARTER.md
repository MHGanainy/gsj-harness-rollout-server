# CHARTER — gsj-harness-rollout-server

The normative document. `CLAUDE.md` governs process; this file governs
content. Predecessor: `gsj-envloader` @ v0.8.0 — **archived at CP-45**
(2026-08-25, ADR-0026): still the golden reference, no longer the
fallback (that term expired at the conversion — CP-17, 2026-08-11);
§8 rule 3 records what the freeze protected and how it is enforced now.

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

**Size budget**: our own code stays within **2,034 lines** (raised from
1,500 at CP-12, ADR-0012; re-set to the landed size exactly at CP-65,
ADR-0028, and again at CP-75, ADR-0033 — zero headroom by design,
machine-checked as an equality in the suite), excluding vendored Polar, tests, and the moved components
(`estate/corpus/`, `estate/mcp-service/`, `estate/forgejo/` — under
`estate/` since CP-50). A checkpoint that adds any net line must stop
and justify, and the equality test moves only with an ADR.

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
answer is no, we say so and stop (§9). (Written at CP-00; the answer
was yes — the verdict converted at CP-17 — and CP-45 archived the
predecessor, its evidence role intact.)

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

Sum 490–740 — the 1,500 ceiling (2,000 since ADR-0012, 2,016 since
ADR-0028, 2,034 since ADR-0033) is headroom, not
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

**[CP-33] Budget status: 1,999 / 2,000 — the cluster lands, paid for by a
banking pass.** `cli.py` 178 → 241 (+63: F-45's which-case printout with
the unbuilt-venv hint, ADR-0025's length-terminated count line, and
wishlist 20's `--from-bank` — a whole consumer path with the CP-27
message standard, the biggest single spend); `receiver.py` 184 → 195
(+11: the F-48 pins-mode filename stamp); `config.py` 432 → 413 (−19)
NOT from feature work — row 32's fix already existed (CP-30) — but from
re-applying the CP-11/CP-23 **banking pass**: comment and docstring prose
whose content is verbatim-recorded elsewhere moved out, pointers kept
(`render_task_request`'s prompt_source/split paragraphs → ADR-0022 /
ADR-0015 / spec §TR3; the thinking and YAML-bool comments → ADR-0024 and
the §3 [CP-30] paragraph above; `_null_sections_to_empty`'s narrative →
wishlist 23 / the CP-27 report; two validator comments condensed). Every
stranger-facing MESSAGE kept in full — the banked lines are commentary,
not output. Total 18 + 159 builder + 528 checks + 241 cli + 123 client +
413 config + 322 pi_harness + 195 receiver = **1,999**, headroom 1.
`checks.py` untouched at 528/528 (ADR-0021 tripwire green). **Handed
forward, ADR-0019-style**: one line of headroom means CP-34's likely
`checks.py` rule needs a §1 budget decision alongside its ADR-0021
allowance ADR — discovered now, not mid-checkpoint.

**[CP-34] Budget status: unchanged, 1,999 / 2,000 — the CP that spent
zero.** The handed-forward `checks.py` rule never came due: CP-34 was the
estate bootstrap, not a rule CP, and its one library change is packaging
only — `pyproject.toml` force-includes `corpus/ingest_corpus.py` into the
wheel as `gsj_rollout/ingest_corpus.py` (the pins mechanism applied to a
module, so a pip-install consumer reaches the contract's `validate` with
no clone), released as 0.1.2. The file's home stays `corpus/` — a moved
component this section has excluded since [CP-01]; copying it into the
artifact at build time moves no line into `gsj_rollout/` and the count
stands as CP-33 left it. Root suite 159 → 161 (+2, the mapping test and
the wheel-layout PASS-table proof, both in `tests/`).

**[CP-65] Budget status: 2,016 / 2,016 — the law re-set to the landed
size and machine-checked (ADR-0028).** The `cli.py` allowance CP: rows
51 (f)/(g) and 37 priced at the file, then re-priced after the CP's own
adversarial review hardened the first cut — (f) **+2** (the 409 hint as
a conditional; CP-62's zero-line estimate priced an UNCONDITIONAL edit,
which the CP-27 message standard rejects), (g) **+7** (the render
guard, never-raise: a bytes compare under EAFP — an undecodable or
vanished file re-renders instead of crashing serve — a pid-unique tmp
name so two concurrent serves cannot cross-truncate, `os.replace` for
the landing), 37 **+7** (the `shutil.which` third-shape branch, taken
only when the found `polar` sits BESIDE this interpreter — the
co-installed estate-image shape; a foreign PATH polar falls through to
the hints; `import shutil` counted). Banking was unavailable — the
freeze-lift confines it to `cli.py`, which CP-33 banked to pointer
form; what remains is the F-register-cited F-21/F-20 and F-45 comments.
So the law moved instead, ADR-0021's way: 2,016 exactly, zero headroom
by design, `tests/test_cli.py::test_size_law_census_is_machine_checked`
asserting the census as an equality in both directions (its glob is
`[!.]*.py` — `wc -l`'s shell-glob universe, dotfiles excluded). Total
18 + 159 builder + 528 checks + 257 cli + 123 client + 414 config +
322 pi_harness + 195 receiver = **2,016**, headroom 0 by design.
`checks.py` untouched at 528/528 (ADR-0021 tripwire green). One
citation moved, disclosed: the examples register's `cli.py:43` (the
F-21/F-20 comment) now sits at `cli.py:51` — insertions above it, the
comment byte-untouched; no cited line was banked. Root suite
164 → 169.

**Deliberately dropped** (and whose problem each becomes):

- the store — trainer's problem
- the loader (`ready`/`mix`/leases/serve accounting/SPI) — trainer's problem
- staleness tracking — trainer's problem
- collation — trainer's problem
- `GsjCaseTask` — Polar's problem
- `uniagent_driver` — Polar's problem
- `collector` — Polar's problem

**[CP-75] Budget status: 2,034 / 2,034 — the law re-set to the landed
size again (ADR-0033).** The `.env` read-not-exported CP: CP-70's item 1
priced at the file — `config.py` gains `_named_value` (the value of a
variable the config names by NAME: the environment wins, else the `.env`
beside the config parsed as `KEY='value'` exactly as `estate.py` writes
it, read lazily at the `clone_credential_env` seam and never exported; a
malformed line — a bare or `"`-quoted hand-edit included — refused naming
file and line) **+20**, the `RunConfig` private attribute and its
assignment in `load_config` **+2**, the seam's old read-and-refuse
collapsed into one call **−4** — **+18** total, `config.py` 414 → 432.
The price moved twice under measurement: a first cut at +17 checked
quote parity for the malformed rule and refused the writer's own escape
(`'\''` has an odd quote count — the probe against `Run.write_env`
caught it); a second cut at +17 read a bare value as-is, the way
`estate.py`'s own `Run.load` does, and the CP's adversarial review showed
that reader tolerates a shape it never receives while this one would
receive it from a hand-edit and splice the quotes, a trailing comment or
a literal `$HOME` into the clone URL — the landed grammar refuses bare
values, one more line (the `quoted` binding). Banking was checked, not
assumed: `config.py` is not `cli.py` (its two line citations name a code
line and a def line, both already stale at HEAD — the F-25 def −5 since
CP-56, the `model_name` line +1 — now at 242 and 427, the CP-50 footnote
clause covering both), but it PAID a feature by comment recovery once
already (CP-56, net +0), and what remains is one-to-three-line pointers,
the printed `COLLECT_SEMANTICS`, the CP-27 messages and the ADR-cited
docstrings — squeezing eighteen out of that deletes pointers, and
squeezing three to make the raise smaller is cosmetic; the review's one
−1 (an undeclared private attribute riding pydantic's `__setattr__`
fall-through) was declined for cause. "Do not take it" was argued and
answered in the ADR: one convenience, but the trainer-side command every
batch runs, a discipline that failed once by measurement (during CP-72's
Mac lifecycle proof a hand-rolled export of the secret answered 401
where sourcing worked — the operator's session notes, not the CP-72
report), a class of leak removed, the examples trainer reached
in-process, and the server-side half (a gateway launcher in `estate.py`)
outside the law. So the law moved, ADR-0021's way, for the second time:
**ADR-0033**, 2,034 exactly, zero headroom, the equality test moved with
it (the literal and its docstring in `tests/test_cli.py`, outside this
CP's lift, taken under ADR-0028's "an ADR plus that test, together"
clause and declared). Total 18 + 159 builder + 528 checks + 257 cli +
123 client + **432 config** + 322 pi_harness + 195 receiver = **2,034**,
headroom 0 by design. `checks.py` untouched at 528/528. No citation moved
by deletion. Root suite 169 → 176 (+7, all in `tests/`).

## 4. What we assume

Every new assumption gets a row here immediately. **Unverified is not
false** — a reported defect stays UNVERIFIED until a checkpoint verifies
it.

**Numbering (CP-51, audit M3):** A-17–A-20 were never assigned — the
register skipped them at CP-12, and the only statement of that fact lived
in the CP-12 report, untracked since CP-48 — and A-15 is filed after A-25
(added out of order at CP-25). CP-06's "(A-20 nuance)" and
`spike/stub_backend.py:81`'s *(at `spike-cp06`)* A-20 are the predecessor's register ids, not
this one's.

| # | assumption | basis | if false |
| --- | --- | --- | --- |
| A-1 | Polar's `prefix_merging` reconstructs multi-turn token streams correctly | **RESOLVED — empirically on BOTH pairs; the H200 (the governing platform, A-16) at CP-09′.** [CP-09′] Against `docs/golden/h200/` on the same triple with the golden's own instruction bytes: `loss_mask` semantics exact on both traces (zero tolerance satisfied — 2 sampled spans == 2 assistant turns each, opens at r=0, closes at stream end), `prompt_ids` byte-identical (2965/2965), decode-fidelity EXACT-BYTES at mask==1 on both traces, glue framing constants byte-identical across traces with the pinned G6 tail, and the logprob replay run **as written** through the serving engine — bit-deterministic (rerun Δ exactly 0.000000), with the sole finding the platform's capture-path numerics floor (present identically on the predecessor's Polar-free capture); **nothing attributable to Polar** (`docs/reports/CP-09prime.md`, verdict PASS WITH FINDINGS). **At CP-09 — empirically, Mac pair** (the behavioral half; CP-05 verified the structural half): against `docs/golden/mac/` on the same triple, `loss_mask` semantics matched exactly (2 sampled spans == 2 assistant turns, boundaries aligned, per-span decode-fidelity exact on both traces), `prompt_ids` byte-identical to the golden's `prompts` (2965/2965 — the A-1 retokenization class is empirically clean), glue template constants identical across stacks, and logprob capture agreed with the predecessor's capture at mean&nbsp;|Δ|&nbsp;=&nbsp;0.000114 on identical-context positions (comparison table + findings: `docs/reports/CP-09.md`; the H200 pair CP-04′/CP-09′ re-confirms on production numerics). **LINE-VERIFIED at CP-05** (algorithm; token fidelity was CP-09's question): the retokenization guarantee holds in code — assistant tokens come only from engine-sampled ids, never from a prompt re-rendering (`record_utils.py:82-107`, `prefix_merging.py:337-353`; no tokenizer anywhere in the builder); grouping is a strict token-id prefix test (`prefix_merging.py:399`); the interstitial split implements the paper's §3.4.2 exactly (`prefix_merging.py:326-334`). Adversarially re-verified (6-agent pass, 17/18 claims confirmed, 1 scope-corrected). **But every discovered failure mode degrades silently to `status=COMPLETED`** — truncation, chain degeneration, EOT misdetection, filter amputation, `choices[0]`-only capture, discard-and-reprompt — catalogued in `docs/checks-spec.md` §silent-degradation; verdict: **GO WITH CONDITIONS** (CP-05 report). **[CP-45] The evidence's collecting stack (`gsj-envloader` @ v0.8.0, both golden dirs) is ARCHIVED — one README-header commit past the v0.8.0 tag, GitHub read-only (ADR-0026); the golden bytes, hashes, and this row's resolution are unchanged, and the citation names an archived stack by design** | CP-09 fidelity fails against the golden reference with no fix in our code → abandon (§9) |
| A-2 | Polar's proxy handles pi 0.83.0's traffic unmodified: **RESOLVED — CONFIRMED at CP-06** (stub backend, no GPU; engine-side fidelity stays CP-09's); **CP-07 adds a real-engine caveat**: pi sends `tool_choice: auto`, which vLLM/vllm-metal reject with HTTP 400 unless the engine is served with `--enable-auto-tool-choice --tool-call-parser hermes` — not a proxy translation failure (the proxy forwards `tool_choice` untouched), an engine-config requirement the harness cannot set; the first CP-07 submit ERRORed "no completions" until the engine was restarted with those flags (echoes the predecessor's H-41 sglang-parser dependency from the vLLM side) | CP-06 live: pi 0.83.0 (predecessor pins, ADR-0008 argv) through the gateway completed a 2-turn episode, `chains_total == 1`, zero translation errors. Measured facts: (a) pi **always sends `stream: true`** — the gateway forwards non-streaming (`proxy.py:121-122`) and replays the backend response to pi as ONE synthetic SSE delta chunk (`server.py:736,771-810`); pi 0.83.0's parser accepts that shape (verified twice: direct against the stub speaking the same shape, and through the proxy); (b) the transformer's only mutation on pi traffic is `max_tokens` added as a copy of `max_completion_tokens` (original key retained, `openai_chat.py:15-16`) — the system-message fold is a no-op because pi sends exactly one top-of-list system string; `messages`/`tools` byte-identical across original → transformed → wire (three-way diff, `spike/wire_diff.py` *(at `spike-cp06`)*); (c) engine-prepare deltas are additive capture params only (`+logprobs`, `+return_token_ids`, `+top_logprobs: 0`, `stream→false`, `−stream_options`); (d) the capture keying works because our harness substitutes `$OPENAI_API_KEY` (= the session id) into pi's `models.json` `apiKey` — a harness with a static apiKey would fragment capture into per-request orphan sessions (builder then ERRORs "no trainable completions" — loud) | n/a (resolved); a translation failure on a real engine dialect at CP-09 would reopen it. **[CP-51, audit S4]** the CP-07 caveat is family-bound, not *the* engine requirement: `--tool-call-parser hermes` is Qwen's parser; CP-38 served Llama-3.1 with `llama3_json` (`estate/serving/serve-llama31.sh`; hermes "would leave every call unparsed text", CP-38's measurement) — the demo's `preflight.py:217/:241` already says so. The resolution itself stands |
| A-3 | pi package identity: **RESOLVED** — same tool; `@mariozechner` deprecated → `@earendil-works`; Polar's preset pins 0.67.68, we run 0.83.0 | npm deprecation trail traced | n/a (resolved); if the rename hid a fork, the CP-05 source audit catches it |
| A-4 | the per-episode cutoff token is injectable via `run_steps()` — **RESOLVED at CP-07**: minted host-side in `run_steps()` (stdlib HS256, claims `{case_id, timestep, episode_id, exp}`, `episode_id` = the Polar session id), rendered into `.pi/mcp.json` as `<mcp_base>/mcp/<token>`, enforced server-side by the MCP service from **verified claims only** | Polar's episode API takes per-episode parameters; **CP-07 live**: the CP-04 triple ran end to end, every `mcp_gsj_*` call authorized under its own token's `timestep: 12` (`docs/polar/pi-corpus/mcp_authority_log.jsonl`), every `search_case` result page ≤ 12, and the adversarial probe (mutate `timestep` 12→18 keeping the signature, call the service from inside the sandbox) was rejected HTTP 401 `token invalid: Signature verification failed` (`docs/polar/pi-corpus/adversarial_probe.txt`) — the agent can read the token but cannot forge its scope | n/a (resolved); the cutoff rode `run_steps()` exactly as assumed, no fallback channel needed |
| A-5 | the callback payload is sufficient for `checks.py` (token ids, `loss_mask`, logprobs, metadata) — **RESOLVED at CP-08**: the receiver now consumes it for real — the CP-07 body (fetched `SessionResult`, status/error intact) round-trips through `POST /callbacks/session_result` → `checks.validate_session_result` → persisted verbatim, and the client re-validates the same bodies from `GET /rollout/task/{id}`; doctored bodies (ERROR status, builder findings) quarantine with findings attached | Polar emits training-ready traces for its slime bridge; **CP-05, verified at source**: the callback body is `SessionResult.model_dump(mode="json")` (`node.py:860`) carrying full traces (token ids, `loss_mask`, logprobs, messages, tools, `finish_reason`), `reconstruction_stats`, and a writable metadata channel — builder-subclass keys survive to the callback verbatim and on into slime `Sample.metadata["polar"]` (`adapter.py:141-160`); the endpoint revalidates pydantic shape only (`rollout/server.py:170-173`). **Caveat**: per-completion records do NOT ride the callback (only the `completion_metadata` extracts in trace metadata), so session-level checks must run builder-side — the receiver alone cannot see them. **CP-06, pi-side evidence** (`docs/polar/pi/callback_session_result.json`): with a token-id-bearing dialect the payload is fully populated end to end — `prompt_ids` 2734, `response_ids` 149, `loss_mask` aligned (119×1 + 30×0), `response_logprobs` aligned 149 with `0.0` only at mask-0 interstitials, the 7-tool roster on the trace, `reconstruction_stats` carrying the whole G7 conjunction — everything `checks.py` needs for the trace-level gates rides the callback | n/a (resolved); the CP-05 caveat stands — per-completion records do NOT ride the callback, so session-level checks stay builder-side (the CP-07 subclass) |
| A-6 | slime can run OPD against Polar traces — **RESOLVED at CP-17: CONFIRMED, with the qualification stated.** Real slime v0.3.0 + Megatron (in `slimerl/slime:v0.3.0`, GPU 5, disjoint from the serving GPU) took **one real optimizer step** on 27 episodes collected through our path and converted by the CP-16 bridge: `global_batch_size 27`, `train/grad_norm 0.4513` (non-zero, below `clip_grad 1.0`, so unclipped), `train/loss 4.909e−06`, TIS live (`tis 0.99985`) consuming our captured `rollout_log_probs`, loss taken under the builder's `loss_mask` verbatim. The qualification: the regime run was **GRPO, not OPD** — the loop's question was whether slime consumes these traces and takes a real step, and OPD's teacher-scoring half (the predecessor's `opd/`) adds an evaluator, not a new consumption path. Advantages were non-degenerate because the CP-17 reward attach made them so (1 of 27 episodes at reward 1.0) | Polar ships a slime bridge; **CP-17 ran it end to end** (`docs/reports/CP-17.md`) | n/a (resolved). What the resolution does NOT cover: multi-step training, concurrency between collection and training, weight sync at cadence, and OPD's teacher leg specifically |
| A-7 | **RESOLVED at CP-02 — partially confirmed**, per defect: **D1 leak CONFIRMED, worse than reported** — upstream at the pin has *no* non-agent completion filter at all (the whitelist was fork code; every auxiliary harness call becomes a trainable trace carrying session reward); **D2 PARTIAL** — vLLM `-9999.0` flows to the trainer unvalidated at the pin (confirmed; zero value-level logprob checks upstream), but `_logprob_integrity` is fork-only and the interstitial `0.0` is mask==0-only (benign, matches our rule); **D3 CONFIRMED end-to-end** — statuses are {COMPLETED, TIMEOUT, ERROR}, `finish_reason=="abort"` is handled nowhere, a mid-chain abort presents a *clean* chain snapshot; **D4 REFUTED for upstream** — reasoning masking is fork-only, the pin emits all-ones `loss_mask` unconditionally | commit patches read + upstream line-verified at `f0e8343a` (CP-02 report, ADR-0004) | D1/D3 become carried patches P1/P2 at CP-03; the sentinel guard lands in `checks.py` as an **explicit threshold rule** — the finite-and-≤0 rule does NOT auto-reject `-9999.0` (spec corrected at CP-02) |
| A-8 | vendoring a release-less branch is sustainable — **RESOLVED at CP-22: HOLDS, residuals named.** The second vendor ran (the re-vendor rehearsal, `docs/reports/CP-22.md`): upstream `stable` unmoved at `f0e8343a` (surveyed via `gh api` — zero commits since the pin, still no tags or releases; the `polar` dev branch frozen since 2026-06-06 at 80 ahead / 3 behind), so the rehearsal re-vendored to the SAME SHA and exercised the recipe end to end: fetch SHA-verified, tree re-extracted, all three patches applied CLEAN by the script (zero rejects), the re-vendored tree **byte-identical to the committed tree** (`git diff HEAD -- vendor/` empty, `prefix_merging.py` mode 100644 kept), and the reverse-apply walk landed on the pristine pin exactly (CP-03's fidelity standard held in both directions). Measured cost: **~2 minutes** for the mechanical loop (fetch → extract → patch → verify → venv rebuild → vendored suite, warm uv cache), ~15 minutes with the full five-suite + pins verification — the half-day budget is all patch-re-anchoring contingency, none of it mechanism. **The named risk was priced, not just named**: with today's `polar`-branch refactor (+49/−156 on `prefix_merging.py`) simulated as landed in a scratch tree, P1/P2/P3's **source hunks all apply clean** — P2's single-`status="COMPLETED"` anchor and P1's stats-dict anchor both survive the refactor — and only P1's two fixture-marker hunks reject, in test files the refactor rewrote (mechanical re-anchoring, not re-porting). Residuals: (a) no MOVED-pin re-vendor has run — an upstream delta under the patches stays estimated, now well-bounded; (b) the refactor diagnostic is a point-in-time measurement of an unlanded branch — what eventually squash-lands may differ, and the vendored suite at that future pin is the real gate; (c) one recipe defect was found and fixed (the venv-rebuild step omitted the A-14 `gsj_rollout` install — followed verbatim it broke the registry seam, measured live as `ModuleNotFoundError`; REVENDOR.md corrected) | pinned SHA + recorded re-vendor recipe + carried patches; **CP-03 evidence**: first vendor executed at moderate cost (~one working day incl. patch adaptation, component venv, smoke run; all three patches apply clean from `vendor/apply_patches.sh`; upstream suite 175 passed / 3 pre-existing failures); **CP-22 evidence**: the recipe followed by a second executor reproduced the committed tree byte-for-byte, same 175/3 suite split, all approved pins reproduced | n/a (resolved); a re-vendor whose measured cost balloons — the moved-pin case, or the refactor landing in a shape the diagnostic did not price — reopens it and re-decides the dependency posture in an ADR |
| A-9 | the carried components transfer unmodified — **EXERCISED at CP-01: HELD, four caveats** (in the CP-01 report since day one; surfaced to this register at CP-41, audit S14): (1) the `gsj-pin` generator is predecessor *library* code and could not move — the derive tooling + captured evidence + `docs/checks-spec.md` carry the capability instead; (2) the mcp-service suite hardcodes its own `.venv/bin/python` — environment *recreation* is load-bearing for the suite, not just deployment; (3) the same suite reaches into the sibling `corpus/` tree at import time and hardcodes its ground-truth constants — the side-by-side layout is preserved deliberately, so a future corpus change breaks mcp tests by design; (4) the compose project name `gsj-envloader-staging` is the live estate's identity, deliberately kept, and the captured G2 texts embed predecessor host paths by nature (byte-load-bearing hash inputs, exempt by ADR-0002) | they were built host-portable behind the corpus contract; predecessor law forbade host-layout dependence in library code | fixes happen here (the predecessor is frozen) and the touched row flips to GAP until cured |
| A-10 | reward sparsity at demo scale is a method/scale property, not infrastructure | the predecessor's recorded runs show the same | still not a rollout-server defect — out of scope by the scope law |
| A-11 | **Apptainer deferred** — Polar supports it natively; we stay on Docker so the CP-09 comparison has one variable | Polar's README lists the Apptainer runtime; the predecessor was Docker-only, so Docker is the controlled variable | revisit on a cluster without a daemon; law 5 keeps `gsj_rollout/` runtime-agnostic so nothing needs rewriting. **[CP-51] REWORDED**: the stated reason (one controlled variable for the CP-09 comparison) expired at CP-09′; the standing reason is gap row 30's — no daemon-less cluster exists in any estate, and two upstream forks reworked `runtime/apptainer.py` before using it. `waiting-on: a daemon-less cluster in the estate — no owner until then` |
| A-12 | our pi harness makes no auxiliary (non-agent-loop) LLM calls through Polar's gateway — **P1's status RESOLVED at CP-06: INERT against pi**; the no-auxiliary-calls observation holds on the spike episode (real corpus episodes re-measured at CP-09/CP-10) | CP-06 measured, wire-level: **every request pi 0.83.0 emits carries a bare `stream` key** (pi-ai's openai-completions client streams unconditionally; `stream: true` on all captured calls), and agent turns additionally carry a system message, a non-empty `tools` array, and ≥2 messages — all four of P1's drop conditions independently defeated, and the `key in request` membership test (`record_filters.py:108`) means even an auxiliary single-user-message call through the same client is KEPT (executed against the real filter: `spike/p1_verdict.py` *(at `spike-cp06`)* — genuine turns kept ✓, pi-dialect aux call kept = false negative, only a stream-less bare call drops, and no pi 0.83.0 path emits one). **P1's protection is illusory for pi; it stays carried for non-pi harnesses and as the empty-choices guard.** Completions-vs-turns: 2 LLM calls in pi's `--mode json` transcript = 2 captured records = `raw_completions_total` (both direct and through Polar) — no auxiliary calls on the trivial episode. The defense obligation moves to the CP-07 builder subclass: a pi-dialect agent-shape check (~10 lines, sized in the CP-06 report) rejecting any completion whose `original_request` lacks the agent-turn shape (system + tools + `stream`), plus `completion_filter.excluded == []` | an auxiliary call on a real corpus episode would become a well-formed `chain_length=1` trainable trace carrying full session reward (fork-measured density up to 27%) with NO filter to stop it — the subclass check is mandatory, not optional |
| A-13 | until carried patch P3 (per-turn `policy_version` stamping) is active, the trainer drains all in-flight sessions before every weight sync — **[CP-17] MET AT A REAL SYNC, BY CONSTRUCTION.** The loop is strictly serialized (collect → train → sync → collect), so at the sync boundary the drain was already complete, and it was **verified rather than assumed**: zero episode containers on `gsj-staging-net` and the engine reporting `Running: 0 reqs, Waiting: 0 reqs`. The sync itself is a stop-then-start of the engine (`staging/serving/serve-updated.sh`), which makes the drain point physical. **What this does NOT establish**: that the rule can be honoured under concurrency. A real run overlaps collection with training, and then the rule needs an actual drain barrier or P3 live to detect a session that spanned the sync — one serialized sync exercises the *situation*, not the *mechanism*. Decision recorded in external ADR-0002: at ONE sync, declaring `policy_version` adds a claim no consumer checks; the second sync is where that stops being true. **[CP-21] The second real sync (a different trainer's export through the same `serve-updated.sh`): nothing differed** — drain again satisfied by construction (serialized loop) and again verified rather than assumed (zero episode containers, engine idle at the stop). Two syncs, both serialized: the *situation* now has two data points; the *mechanism* (a drain barrier or P3 live under concurrency) still has zero, and "the second sync is where that stops being true" refers to a second sync *within one run's collection window* — which neither CP has executed. **[CP-22] Upstream signal worth recording**: the unlanded `polar`-branch refactor grew a `policy_version` CONSUMER — `_top_level_scheduler_metadata` promotes `{group_id, policy_version, rollout_step}` from record metadata to trajectory-level scheduler metadata — while still shipping no producer (`gateway/storage.py` untouched by the refactor, P3 re-applied clean). If that lands, P3's stamp stops being a fork-only convention and becomes the key upstream's own scheduler layer reads. **[CP-41, recording CP-32] A third serialized sync**: CP-32's pooled thinking-on walk synced through the same `serve-updated.sh` — probe→sync→probe mean\|Δ\| 0.040184, 7,327/7,609 (96%) positions moved, post-sync collect 9/9 accepted — again drain-by-construction (the strictly serialized loop), again verified rather than assumed. The *situation* now has three data points; the *mechanism* under concurrency still has zero, unchanged (audit S14) | D5 audit: at the pin a session spanning a weight sync is assembled as COMPLETED with a clean chain snapshot and only the stale submission-time version — invisible on the wire and retroactively unauditable; CP-03: P3 landed inert (stamping + persistence fix present and verified; nothing declares versions yet — confirmed no `policy_version` key on a real persisted record) | mixed-weight traces train silently; the receiver cannot catch what the capture layer never records (the declared limit of law 6). `waiting-on: a concurrent collect+train loop (P3 live under concurrency) — the mechanism's first data point; every loop so far was serialized` |
| A-14 | `vendor/polar/.venv` (Python 3.12) can host `gsj_rollout` when CP-06 wires the `import_path` harness — the dependency points Polar→us, and our core deps (pydantic/httpx/pyyaml) are a strict subset of Polar's five (fastapi/uvicorn/httpx/pydantic/pyyaml). **[CP-41, recording CP-22] RE-VERIFIED LIVE at the re-vendor rehearsal — HOLDS, one defect named**: CP-06 wired the harness and the venv has hosted `gsj_rollout` on every run since; CP-22's recipe-verbatim venv rebuild then found the defect with teeth — the rebuild omitted the `gsj_rollout` install and the registry seam failed measured (`ModuleNotFoundError: No module named 'gsj_rollout'`); with the install applied (`uv pip install -e ../..`), `ValidatingPrefixMergingBuilder` resolves with the expected MRO (→ `PrefixMergingBuilder` → `BaseTrajectoryBuilder`) and no version conflict appeared — the dependency-subset half held exactly. The install is now a REVENDOR.md recipe step with the seam check as a verify tripwire. CP-22's report claimed this row gained the note that day; it had not until CP-41 (audit C6) | ADR-0005; both dependency sets read from the two pyprojects at CP-03 | a version conflict forces re-deciding the environment split (dedicated harness venv, or loosening root pins); the root package never grows Polar deps either way |
| A-16 | the Mac golden pair is a **comparison baseline, not a production artifact**: `docs/golden/mac/` anchors CP-09's Mac-pair fidelity verdict only; the H200 pair (CP-04′/CP-09′) re-establishes the production numbers | CP-04: the Mac estate is adaptation-bearing (published-port networking, vllm-metal/MLX bf16 serving of the mlx-community conversion, amd64 pi image under emulation, wall-timeout 900) — every adaptation enumerated in `docs/golden/mac/MANIFEST.md`, and CP-04′ needs none of them. **Corrected en route**: the G-hashes are NOT Mac-path-specific as this row's first draft assumed — docker-mode execution keeps host paths out of the prompt (G2 is the `/workspace` singleton `f56e8a6e…`), and the whole pins file regenerated byte-value-identical on the Mac; the Mac-specific surface is the *numerics*, not the pins (MLX bf16: 20/292 mask-1 logprobs exactly `0.0` — row 27). **[CP-04′] The counterpart half is now real: the H200 governs the numerics, and the prediction held.** `docs/golden/h200/` exists (same triple, predecessor stack, native CUDA — zero Mac adaptations needed, exactly as this row predicted: no emulation, no published ports, no serving substitution, wall-timeout 480 stood), collected under a served snapshot whose weights == the codec snapshot (the Mac's served/codec split does not exist on the H200). Why the H200 governs, made concrete this CP: the numerics differ where only platform can differ — the row-27 exact-`0.0` artifact recurs on CUDA vLLM bf16 (16/258 on the golden; up to 24.9% on a repetitive-loop episode via our stack), so the Mac's MLX numbers were never generalizable, and every G-hash reproduced identically across estates while the numerics did not — the pins are estate-invariant, the numerics are the platform. **[CP-09′] The counterpart CLOSES — the governing verdict exists**: PASS WITH FINDINGS on the H200 pair, nothing attributable to Polar (`docs/reports/CP-09prime.md`); the two pairs' verdicts agree in kind, so the if-false branch (verdict divergence) never fired. The governing numbers, as measured: replay-as-written beyond the contract's 0.005/0.05 bounds on BOTH stacks' captures symmetrically (golden mean |Δ| 0.005246, collected 0.007141; the replay path itself bit-deterministic at exactly 0.000000), capture-vs-capture on identical contexts 0.003672 mean (the Mac's 0.000114 was an MLX-sequential property — CUDA cross-request numerics ≈ 30× noisier), exact-`0.0` rates 6.2%/7.3% within the 0.25 allowance | if the two pairs' verdicts diverge, the platform (engine numerics, emulation) is entangled in the comparison and the H200 pair's verdict governs; the Mac pair then only screens for gross structural defects |
| A-21 | gsj rollouts pin `generation_prompt_glue_ids` in the builder config whenever the served chat template appends generation-prompt-only glue — for Qwen3 with `enable_thinking: false` this is the empty think block `[151667, 271, 151668, 271]` (`<think>`,`\n\n`,`</think>`,`\n\n`) — **added and RESOLVED-in-practice at CP-07** (ADR-0007). **[CP-04′] The condition no longer obtains on the H200 estate**: the served template is the symmetric `qwen3_training.jinja` (Direction A), which appends NO generation-prompt-only glue — the H200 config leaves the ids UNSET and two fresh episodes merged natively (`chains_total == 1`, full G7 conjunction, `glue_stitched: 0` — `docs/polar/h200-stitch/`). The assumption stands as written for any future asymmetric template; the stitch code stays in place, dormant, as that fallback | CP-07 live: the first real multi-turn corpus episode reconstructed as **2 chains** because the Qwen3 no-think template appends the empty think block to each generation prompt but NOT to the history re-render, so consecutive pi prompts are never token-prefix-stable and the vendored grouping (`prefix_merging.py:399`) opens a fresh chain per turn (the S4 shape, silently COMPLETED). The subclass normalizes `prompt_ids` before grouping (strict-extension stitch, `glue_stitched` recorded); with the ids pinned the same episode merged to `chains_total == 1`, 441 sampled + 6755 interstitial tokens, logprobs aligned. The stub never surfaced this (byte tokenizer, no template) — it took an end-to-end episode | an unpinned glue on a real multi-turn run degrades every episode to per-turn chains that look COMPLETED; the receiver's `chains_total == 1` catches it (fails closed), but no trace merges until the ids are pinned — template-specific, re-derive per served tokenizer |
| A-22 | **thinking-ON is out of bounds for the ADR-0007 stitch, not merely untested** — `harness.thinking` stays `off`; flipping it needs Direction A (a symmetric served template), not a longer glue list | CP-10 template investigation: with thinking enabled the Qwen3 template's history branch re-renders each assistant turn *without* its reasoning content, so the per-turn divergence is **variable-length**, not the fixed 4-token empty-think pair the stitch is pinned to. `ValidatingPrefixMergingBuilder`'s strict-extension test then simply fails to match, no stitch is applied, and the episode degenerates to per-turn chains exactly as it did before ADR-0007. Publicly the same shape: `verl#6854` is this defect in a trajectory reconstructor's prefix guard with thinking on, and `OpenRLHF#1080`/`NVIDIA-NeMo/RL#2821` report the SFT analogues. HuggingFace TRL's `qwen3_training.jinja` (always emit the think block) is the shipped general fix | the failure is LOUD, not silent — split chains fail the receiver's `chains_total == 1` — so the cost is lost episodes, not corrupted training data; the cure is the CP-04′ template flip (ADR-0007 amendment, Direction A). **[CP-28] EXERCISED — the cure held in vivo**: 15/15 real thinking-on episodes merged natively on the H200 (`chains_total == 1`, `glue_stitched: 0`, zero builder findings) through pi's reasoning round-trip — vLLM 0.26 returns the parsed reasoning as `message.reasoning`, pi echoes it back under the field name it found, and the engine maps it into the template's `reasoning_content` path (measured, `docs/polar/thinking/probe_override.txt`) — so the variable-length divergence this row predicts for the stock template never materialized under the symmetric one; the stitch stayed dormant and was never needed. **[CP-30] Unchanged by C-2's landing**: the per-mode G6 pin is checks-side pins data and touches nothing in this row's mechanism; the symmetric served template remains the only supported thinking-on configuration, and the CP-30 live pair (one episode per mode, both through the real receiver) merged natively again — `chains_total == 1` on both |
| A-23 | the harness runs in the SAME process as the gateway proxy, and that process's `polar.gateway.server` module state is the live one — the ground the CP-13 settings echo stands on | the `import_path` architecture: the harness is loaded into the gateway process (CP-06, verified live incl. the module-cache trap) and the node, registry, and proxy share `GatewayState` (`server.py:70-179`, executed at CP-13's hop run); the echo's registry merge, the proxy stamp, and the builder hoist all executed against the real vendored classes | a future Polar that runs harnesses out-of-process (or a second disconnected state) makes `registry.get(session_id)` return None and `PiHarness.setup` RAISES — episodes fail loudly at dispatch, never silently unechoed; the receiver's `G7:missing_evidence:settings` is the fail-closed backstop either way |
| A-24 | the `chromadb==1.5.9` pin is a dependency with its own upgrade risk, and its opaque on-disk format never fails silently: the corpus fingerprint carries a `chroma_version` component, so any bump forces a loud rebuild (`if-stale`) or a startup error (`never`) — added at CP-15 | ADR-0016; the fingerprint doc includes `chroma.version` (`mcp-service/gsj_mcp_service/index.py: corpus_fingerprint`), and the simulated-upgrade test (`test_backend.py: test_chroma_version_change_rebuilds_loudly`) proves the rebuild path; telemetry off, the image stays offline | a Chroma regression at the pinned version forces a deliberate re-pin + re-index — cheap at this scale (full 4-case rebuild ≈ minutes on the workstation); an on-disk format change inside a same-version patch would be the silent case the fingerprint cannot see, accepted as the residual risk of any opaque store |
| A-25 | Chroma/HNSW retrieval is reproducible at this corpus scale — **measured IDENTICAL at CP-15 Step 4**: ids, order, and scores byte-equal across two fresh processes over the same store, across builder-vs-loader, and across two independent builds, at tool level AND raw chunk level (9/9 probes; re-run at CP-77: still 9/9) — **and re-measured at CP-77 at 19,215 chunks + 12,000 decisions: same-store and builder-vs-loader IDENTICAL 7/7, two independent builds identical at tool level but NOT at the chunk tail** (see the third cell) — but reproducibility is NOT a guarantee and byte-reproducible retrieval is no longer a promise of this stack (ADR-0040(f) forfeited by design, ADR-0016) | `mcp-service/tests/measure_determinism.py`, run on the workstation over the staging corpus (213 chunks, full-candidate-set fetch — `n_results` = the whole cutoff-filtered set, which is what makes HNSW effectively exhaustive here) AND, at CP-77 with the script's `--base-url/--repos/--decisions/--probe` flags, over a synthetic 19,215-chunk / 12,000-decision store (exhaustive at 213, ≈0.1% short at 19k — the same-store legs identical, the two-builds leg not) | a larger corpus, a bounded fetch, or a Chroma bump may break it. Cost audit, done at CP-15: nothing else depended on reproducible retrieval — the golden/fidelity comparisons key on token ids/logprobs (sampling was never deterministic), `checks.py` keys on the cutoff and shape, and the one true consumer (the service's own cross-process byte-identity test) stays as a regression canary that would fail loudly, to be relaxed knowingly if this row flips **[CP-77] Re-measured at scale — three legs, one departs.** `measure_determinism.py` (now taking `--base-url`, `--repos`, `--decisions`, `--probe`) over a synthetic 1,300-page case of **19,215 chunks** and **12,000 decisions**, both builders above chroma's 5,461-item single-add ceiling on the batched path (wishlist 66): (i) two fresh processes over the same store **IDENTICAL 7/7** — the canary's property holds; (ii) builder vs fresh loader **IDENTICAL 7/7**; (iii) two independent builds from the same inputs: the six tool-level probes IDENTICAL (top-10/20 pages at T 325/650/975/1300; both decisions probes over the 12,000), the raw full-candidate probe **NOT identical** — stored vectors bit-identical across the builds (max\|Δ\| 0), the distance-sorted lists identical on every id both return, but the `where`-filtered full fetch is not exhaustive at this scale (9,571 of 9,581 candidates at T=650; 4,820/4,819 of 4,825 at T=325; 19,203 of 19,215 at T=1300; the unfiltered decisions fetch 12,000 of 12,000) and each build misses a slightly different tail (first private miss at rank 452/352/451, score 0.31/0.23/0.47 against tops of 0.44/0.46/0.63); a bounded fetch of 100 or 1,000 differs between the builds at the top, 10 agrees. Reading: the HNSW graph differs per build in the pinned chroma — **cause not established**: the CP's review rebuilt the same 19,215 bit-identical vectors (all of them compared, not a sample) in the same insertion order twice under `hnsw.num_threads: 1` and still got two graphs, and the persisted configuration carries no thread knob — and it is not tuned, by ADR-0016's own decision; same-store reproducibility stands (the canary's property); build-to-build reproducibility — which no estate relied on, each having one store of ≤62-chunk collections, but which the suite does assert at 213 chunks (`test_batched_build_serves_what_a_single_add_served` at raw level; the kill test's rebuilt-vs-built comparison) — does not hold at the chunk tail; ADR-0016 Mechanics 4's exact-scan parity — asserted at 4 in-cutoff chunks by `test_cutoff_prefilters_candidates_not_postfilters`, whose message would misdiagnose a graph miss as post-filtering at scale, and promised by `CaseIndex.search`'s docstring, now qualified — is ≈0.1% short at 19k (first private miss at 1-based rank 453/353/452; qualified in the CP-77 amendment; wishlist 68). The 213-chunk measurement stands (re-run this CP through the extended script: IDENTICAL 9/9 on all three legs; the canary green at 114) **[CP-79] Re-measured over a real decisions drop, the fetch bounded.** `measure_determinism.py --decisions-path` over an every-17th-file slice of the March 2026 drop (1,999 decisions → 43,760 units → 71,946 pieces) plus `case_0003`, four German decision probes (k 5/20/10/20) and a raw probe of the bounded fetch itself, two runs: (i) two fresh processes over the same store IDENTICAL 8/8, both runs; (ii) builder vs fresh loader IDENTICAL 8/8, both runs; (iii) two independent builds: every tool-level probe identical (the top-5/10/20 units of all four probes, the case pages), the raw case probe identical, the raw decisions probe identical at a 100-piece fetch (the first run, under the interim 20·k) and NOT identical at the shipped 1,000-piece fetch (200·k, k = 5: 999 of 1,000 piece ids shared, the order differing below the top) — CP-77's build-to-build tail, now located inside a bounded fetch, with no effect on the returned units. The bound's recall against an exact scan is 1.000 at k = 5 and 0.998 at k = 20 (wishlist 68); a store of ≈ 1.16 M pieces (the full drop) is unmeasured. |
| A-15 | gsj rollouts always pin `end_of_turn_token_id` in the builder config — EOT auto-detection is never relied on. **[CP-25] The pin's HOME moved, the assumption did not**: `config.py` now defaults the field to 151645 (`<|im_end|>` under the Qwen3 tokenizer the default `estate.model` serves), with the re-derivation command in the field comment — every rendered `TaskRequest` still carries the explicit id, the builder-side reject-if-absent check is untouched, and detection is still never consulted; what changed is that a consumer config omitting the key states the reference pin instead of failing validation | CP-05: auto-detect takes the last sampled token of the FIRST natural-stop completion in the chain (`prefix_merging.py:286-302`, natural = `{stop, tool_calls, stop_sequence}`); a stop-parameter/stop-sequence finish makes that an arbitrary token (a newline, a `</tool_call>`), and a wrong EOT mis-splits every interstitial — duplicated assistant-body fragments ride in as mask-0 tokens, corrupted-but-COMPLETED; with no natural stop in a chain at all (every turn `length`), every merge silently truncates instead; detection is per-chain, so two chains in one trajectory can even resolve different ids. **CP-06 practice run**: the spike pinned `end_of_turn_token_id: 260`, derived by lookup in the serving tokenizer's vocab table (the stub's `SPECIALS` dict, `spike/stub_backend.py` *(at `spike-cp06`)* — `"<|eot|>" = 260`; on a real engine the same derivation is `tokenizer.convert_tokens_to_ids("<|im_end|>")` against the served model's tokenizer.json, the G4 artifact); both spike task files carry it and the live 2-completion chain merged full with `truncated == 0`. **A-15's other half measured**: pi 0.83.0 sends NO `stop` parameter and no `n` (wire-verified, both turns, three request forms) — so auto-detect would not have been *actively* mis-keyed here, but the explicit pin stays mandatory (S5; nothing prevents a future pi/config from adding stop sequences) | an unconfigured EOT on a real run degrades every multi-turn chain to silent truncation or silent corruption; the builder-subclass check (explicit eot config present, else reject) fails closed. **[CP-51, recording CP-38]** on the first foreign family the render-side closer and the engine's stop id DIFFER (Llama-3.1: `<\|eot_id\|>` 128009 rendered, `<\|eom_id\|>` 128008 sampled under tools — wishlist 43, A-30 [CP-38]); the pin is the render-side closer, as this row always meant, and the fail-closed check held on that episode (accepted, `chains_total: 1`) |
| A-26 | the slime v0.3.0 `Sample` surface the vendored adapter constructs against (`group_index`/`index`/`prompt`/`tokens`/`response`/`response_length`/`group_id`/`reward`/`loss_mask`/`rollout_log_probs`/`status` incl. `Status.FAILED`/`remove_sample`/`session_id`/`metadata`) is the real installed surface — **RESOLVED at CP-17: HOLDS.** With real slime importable on-estate, `bridge.load_sample_type()` returned `slime.utils.types.Sample` and the first conversion of a real collected body constructed one with every field accepted: `tokens=5783 response_length=2818 mask1=233 status=Status.COMPLETED group_id=0 session_id='sk-polar-0692…' reward={'score': 0.0}`. The four fields examples-repo F-04 flagged as unverifiable off-estate — `session_id`, `group_id`, `remove_sample`, `Status.FAILED` — are all present on the installed dataclass. 35 conversions across two collections, zero TypeErrors, zero shape workarounds. The loop's rollout function additionally asserts `type(sample).__module__.startswith("slime.")` per sample, so the local double could not have stood in silently | the vendored `slime_bridge/adapter.py` constructs exactly this against slime v0.3.0 + the router-tokens patch (its own install recipe); unverifiable off-estate at CP-16 — slime was not importable there (examples-repo FINDINGS F-03/F-04), so the bridge mirrored the usage and tested on a local double. **CP-17 verified it against the installed surface** (`docs/reports/CP-17.md`) | n/a (resolved). The prediction held exactly: the check was cheap, loud, and trainer-side — and it passed |

| A-27 | **RESOLVED — HOLDS (CP-21).** The verl surface the CP-20 bridge was written against — the padded classic-trainer batch contract (`prompts`/`responses`/`response_mask`+`loss_mask`/`input_ids`/`attention_mask`/`position_ids`/`rollout_log_probs`/`rm_scores`, uid-grouped advantages, all-zero-mask zero-gradient) at verl `1ae945592754cbeb1350cbe092fe6117070fd4c7` — IS the surface CP-21 trained with: every key was consumed by verl's own fit-loop path on a real batch of 110 (`extract_reward` read `rm_scores`; GRPO grouped by `uid`; `ppo_loss` trained under `response_mask`; the decoupled rollout correction consumed `rollout_log_probs` as sequence-TIS weights; `check_consistency` and the engine's own asserts all passed first try). The fit-loop consumption half — the one thing off-estate tests could not verify — is now measured (`docs/reports/CP-21.md` §4). Two surface findings landed in the external register, neither a batch-contract miss: F-12 (the v0 conversion helper hard-requires flash-attn) and F-13 (chunked entropy dead on the non-rmpad branch) | the SHA is uni-agent's own submodule pin (the pair the predecessor's path was built for), exported as `bridge.VERL_SHA`; the contract is read from verl's own agent-loop worker and executed in the bridge's tests against REAL verl code (`DataProto`, `compute_grpo_outcome_advantage`, `agg_loss` — no double, unlike slime's A-26 situation, so the constructor-surface half is already verified off-estate). What off-estate tests cannot verify: the fit-loop *consumption* of a bridge-fed batch on a GPU estate, and the trainer-generation fork (examples-repo F-11: the pin's DEFAULT trainer is the v1 TransferQueue pipeline, which cannot ingest external batches at all — the bridge targets the classic path) | CP-21's first step either consumes the batch or names the key it missed — loudly, since `check_consistency` and the fit loop's own asserts fail fast; if the classic path is removed at a newer verl, the pin holds until CP-21 chooses the fork deliberately (run book item 1) |
| A-28 | the demo estate's published images track the library release: `ghcr.io/mhganainy/gsj-polar` (Polar at `POLAR_SHA` from the public repo's vendored, patched tree + the PyPI wheel, one interpreter — tag encodes both, `f0e8343a-gsj0.1.2`) and `ghcr.io/mhganainy/gsj-mcp-service` (the mcp-service image as shipped, `0.3.0`) are rebuilt/republished, **multi-arch**, whenever a release changes what they carry — added at CP-34 (demo-repo external ADR-0001) | the demo repo (`gsj-rollout-demo`) is built ONLY from published artifacts (PyPI wheel, GHCR images, the public library repo at a pinned ref) — nothing of ours by path; the images are therefore load-bearing artifacts of the consumer surface exactly like the wheel. Polar's dependency bounds are floors (no lockfile), so each image build resolves them fresh and the image tag IS the effective pin. Single-platform builds measured fatal at the CP-34 smoke: an Apple-Silicon build died `exec format error` on the amd64 estate box — hence multi-arch is part of the assumption, not a nicety | a stale `gsj-polar` image serves an old wheel to every demo estate silently (the bootstrap pins the tag, so it fails STALE, not loud); the cure is mechanical — rebuild with `LIB_REF`/`LIB_VERSION` at the new release and re-push — but nothing enforces it yet; wishlist row 34's visibility flip and any future release checklist item are where it becomes enforced. **[CP-51, audit W3] QUALIFIED**: "multi-arch" holds for `gsj-polar` only — `gsj-mcp-service:0.3.0` and `gsj-pi-harness:pi0.83.0-3` publish linux/amd64 only (F-54, CP-36; live manifest probe 2026-08-27 unchanged, no newer tags); ARM hosts pull `--platform linux/amd64` (the demo bootstrap's cure). The intent stands; the fact was false when written. `waiting-on: the operator republish wishlist row 40 names — nothing schedules one` **[CP-61]** `gsj-polar` rebuilt multi-arch at `LIB_REF=v0.1.3`/`LIB_VERSION=0.1.3` — tag `f0e8343a-gsj0.1.3`, index `ae64cf2c…`, `issubclass(PiHarness, BaseHarness)` and `import gsj_rollout.bringup` verified on both platforms; `gsj-mcp-service:0.4.0` published two-platform (wishlist 40 [CP-61]). "Multi-arch" now holds for two of the three images; the harness image remains the qualifier. `waiting-on: the harness republish wishlist row 40 names — nothing schedules one` **[CP-64]** `gsj-pi-harness:pi0.83.0-3` published two-platform (wishlist 40 [CP-64], CLOSED): the index composed from the measured amd64 child `864dc885…` (byte-unchanged — the H200's frozen load and prior provenance stand) and a fresh arm64 build from the archived predecessor's `sandbox/`, pins-walk-verified with one episode per platform (G2/G3 reproduced on both). **Multi-arch now holds for all three images**; both earlier tokens' events (the operator republish, the harness republish) occurred here. **[CP-81] The rebuild duty honoured for 0.1.7, and the retrieval image moved with it — the token's event occurred.** `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.7` built two-platform from the demo's own `estate/polar.Dockerfile` (`LIB_REF=v0.1.7`, `LIB_VERSION=0.1.7`) and pushed: index `sha256:98361f0a…`, `linux/amd64` + `linux/arm64`, the index and both children fetched with an anonymous registry token, and a plain `docker pull` on this arm64 workstation resolving to an image that reports `gsj_rollout 0.1.7` with CP-75's `_named_value` in its packaged `config.py`. The demo's other two answers moved in the same commit: `MCP_IMAGE` `0.4.0` → `0.5.0` (the decisions surface — `0.4.x` refuses the `decisions.path` key a drop needs, wishlist 77 measured at CP-81) and `SANDBOX_IMAGE` unchanged at `pi0.83.0-3`. Three of the demo's four images are therefore current with 0.1.7; the assumption's mechanical half worked as designed, and its "nothing enforces it yet" clause still stands — this rebuild happened because a checkpoint needed the wheel inside the image, not because anything scheduled it. `waiting-on: the next release that changes what an image carries — the A-28 rebuild duty (gsj-polar rides every release; nothing schedules it)` **[CP-85] The 0.1.8 event occurred.** After PyPI publication, demo `3286271` raises its floor and image to 0.1.8. `gsj-polar:f0e8343a-gsj0.1.8` index `30e9d940…` publishes amd64 `b6a74e33…` and arm64 `7f5898b7…`; anonymous index/child reads and container import/payload proofs pass for both. Both report release source `effd658` and estate payload `ddbb661c…`. Fresh-clone arm64 up/preflight/row-2 submit/read/export/down passed with the unchanged read-only `.env` mount and no exported submit token. The core submit implementation stayed byte-identical, but the image carries the changed estate/pipeline payload; the report’s phase-3 obligation and A-28 duty require the recut. `waiting-on: the next published library release that changes the image payload — recut and prove both platforms plus the consumer again` |
| A-29 | a trace's contiguous `loss_mask==1` runs correspond one-to-one, in order, with its `response_messages` assistant turns — added at CP-35, where the demo reader's thinking decode rests on it | measured, never assumed blind: runs == assistant-message count on every real body inspected (the CP-09 fidelity body, CP-34's 71-turn episode, CP-35's two, the 153 CP-32 archives sampled, and — added CP-41, audit S14 — CP-38's Llama-3.1 body, the strongest point: 8 mask-1 spans == 8 assistant turns == 8 merged completions on the first non-Qwen, two-terminator family), and it is how the prefix-merging builder works — one sampled span per completion, tool/glue spans masked. The REASON the demo needs it: message-side reasoning is LOST in the archive (vLLM's reasoning parser strips `<think>` from `content` into `reasoning_content`, which Polar's message capture does not map — its `reasoning` field is null in all 156 bodies measured), so thinking-on reasoning survives ONLY in the token arrays and rendering it means decoding the k-th mask-1 run as turn k | the demo's `read.py` REFUSES rather than guesses — a run/turn count mismatch decodes nothing and the transcript says the archive's own evidence is inconsistent; no library surface depends on this assumption (wishlist row 39 is the durable message-side fix). **[CP-51]** wishlist row 39 FOLDED here: message-side reasoning is a tokenizer dependency by design until a served vLLM's response field is measured — and the "null in all bodies" evidence has an on-disk counter-example (`docs/polar/thinking-on/episode-on.accepted.json`, CP-30: `reasoning_content` populated on all three assistant messages), so the dependency is vLLM-version-bound, not universal. `waiting-on: a measured vLLM response field on the served stack — a carry-patch row then` |
| A-30 | a chat template's turn terminator — the first non-whitespace token it emits after assistant content — is also the id the engine stops generation on, so deriving `builder.end_of_turn_token_id` from a template render is sound — added at CP-37, where the demo bootstrap derives it from a foreign endpoint's `/tokenize`+`/detokenize` | the derived id, on every family probed: Qwen3 `<\|im_end\|>`=151645 (the snapshot config.json's scalar `eos_token_id`, and a member of its generation_config.json's `[151645, 151643]`), Qwen2.5-Coder 151645, Llama-3.1 official template `<\|eot_id\|>`=128009 (a member of its config's `[128001, 128008, 128009]`), and a wild simplified Llama mirror (the first-non-whitespace rule survives its unconditional trailing generation prompt where last-non-whitespace does not — the CP-37 heuristic correction); the STOP half of the assumption is measured live on the reference stack only — elsewhere it rests on the eos-membership cross-checks above; the demo's preflight re-derives and FAILs loudly when the effective id disagrees. **[CP-38] the STOP half measured FALSE on the first live foreign family — and harmless, which sharpens the assumption**: Llama-3.1 under tools STOPS tool-call turns at `<\|eom_id\|>`=128008 (Meta's ipython protocol; observed as `stop_reason` on every tool-call completion and as the last mask-1 id of every tool-call span in the accepted CP-38 episode) while its template re-renders those turns closed with `<\|eot_id\|>`=128009 — and the derived 128009 is still the RIGHT id, because the vendored merge is canonical-vs-canonical: the builder matches `end_of_turn_token_id` against the NEXT prompt's render to slice the interstitial, never against the engine's stop token, and the sampled `<\|eom_id\|>` rides the merged stream as mask-1 data followed by the canonical `<\|eot_id\|>` at mask-0 (`chains_total: 1`, 8/8 merged, zero findings). A-30's sound core is narrower than drafted: derive the RENDER-side closer; the engine's stop id need not equal it | a family whose template closes turns with plain text, or an engine with custom stop ids, derives a wrong split id — reconstruction mis-splits every multi-turn episode; the named cure is the config override (`end_of_turn_token_id`, explicit-wins, disagreement WARNed at `up`) plus the snapshot's `generation_config.json` cross-check documented in the demo's MODEL-SURFACE page |
| A-31 | the benign-drift end of the encoder oracle's bound scales with a unit vector's component magnitude — 1/√d for a normalized d-dimensional vector — so the MiniLM-measured max|Δ| 4e-08 at 384 dims transposes to 4e-08·√(384/d) for a configured model of dimension d (added at CP-57, where `embedding.model` became configuration; `estate/mcp-service/tests/test_backend.py: encoder_max_abs_delta`) | reasoned, not measured: float32 drift is relative to magnitude (ULPs), the rms component of a unit vector is exactly 1/√d (measured 0.0510 at 384, 0.0361 at 768), and at the default model the transposition is the CP-55 constant bit for bit (√1 = 1) so the measured path is unchanged; the same-process re-encode under the second model (`paraphrase-albert-small-v2`, 768) measured max|Δ| 0 — no cross-host drift data exists for any non-default model | a non-default model's benign drift exceeds the transposed bound on some host → the oracle FIRES there, loudly (the message prints max\|Δ\| and cosine against the bound — the CP-55 shape), and the bound is re-argued for that model from its own numbers (wishlist row 46 parks this on the first production re-pin). It cannot fail silent in the dangerous direction: for a non-default model the substitution class is the cross-model class — cosine 0.23–0.31 measured at CP-57 (MiniLM vs bge-small, same 384 dims, same texts), or a width the store refuses before any bound is consulted — which the 0.999 floor and the load-time width check catch independently of \|Δ\| |
| A-32 | a rii drop is DTD-ordered and doknr-unique, with the `doknr` equal to the filename stem — the identity the decisions surface rests on (added at CP-78; drafted at CP-76) | measured 33,979/33,979 on the March 2026 drop (CP-76 §2.1/§2.4; spec `docs/decisions-surface.md` §2) | `validate` refuses the drop (spec §2.2) and the unit rule never sees the file; a `doknr` that is not the filename stem breaks the lock's file census, nothing on the wire |
| A-33 | the Randnummer anchor is `<dt><a name="rd_N">` beside one `<dd>` — never inside a `<p>`, never nested, at most one per row (added at CP-78; drafted at CP-76) | 667,371/667,371 anchors in a `<dt>`; 1,768,022/1,768,022 rows with exactly one `<dt>` and one `<dd>` (CP-76 §2.3, re-measured at CP-78 under the spec's row rule) | the unit walk misses text or mis-numbers it; the validator's anomaly report is the tripwire, and the conformance fixture's `expected.json` stops being reproducible from the rule |
| A-34 | Randnummer numbering is decision-global, so `(doknr, rn)` names one paragraph (added at CP-78; drafted at CP-76) | contiguous `1..K` in 99.64% of anchored files, running from `tatbestand` into `entscheidungsgruende` in 9,370 of 9,382 Urteile; 13 files with duplicate numbers, 3 restarts inside `sonstlt` (CP-76 §2.3) | `dec:<doknr>:rn:<N>` is ambiguous inside that decision — spec §5.4 keeps both units and names the ambiguity; a grader still grounds the citation (one of the two hits carries it) |
| A-39 | `<p style="…margin-left…">` marks quoted material in the publisher's rendering, so an indented row after a section's last anchor belongs to that Randnummer and a plain one does not — the one attribute test in the unit rule (added at CP-78) | 37,745 + 2,573 indented rows between anchors with a median of 18–30 words; 480 after the last anchor with a median of 40–41 words; the 32,547 plain rows after the last anchor have a median of 3 words — judges' names (CP-78's probe over all 33,979 files, spec §4.3) | the tail rule drops a quotation or keeps a signature block; the fixture catches a rule change, a later drop with a different renderer needs a re-measurement and a surface version bump |
| A-40 | the decisions fetch's measured recall transfers to a larger drop: what the bound `200·k` loses is HNSW's search beam (`ef_search` 100, widened by `n_results`), a property of the graph's local search that does not grow with the corpus the way an exhaustive-scan shortfall would (added at CP-79) | measured at 71,946 pieces: the unbounded fetch exact (1.000), 20·k 0.953/0.984, 200·k 1.000/0.998 at k = 5/20, identical results at 25, 50 and 100 pieces (the beam, not the count, is the variable); `tests/measure_decisions_recall.py` re-runs it for any drop | recall at the full 34k-file drop (≈ 1.16 M pieces) is lower than measured — the constant rises (a code change, no store change: the fetch is query-time) or `ef_search` is tuned (ADR-0016's untouched knob); nothing on the wire moves, a consumer sees fewer of the true top units until then |

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
   predecessor's estate, cure named in row 2. **[CP-56] The network channel
   is now closed where sign-in is enabled** (Forgejo `REQUIRE_SIGNIN_VIEW` +
   a read-scoped clone token spliced by `clone_credential_env`): the two
   re-clone probes return 401 with sign-in ON, proven container-faithful.
   The demo estate closes it live; the H200 flip is a documented two-phase
   pending its frozen MCP/corpus consumers (row 2). The predecessor's own
   wider exposure stays recorded as inherited and unfixed (law 3).
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
| CP-16 | M4f: the slime bridge | **done** (ADR-0017, ADR-0018): the trainer leg fixed — pins ride the wheel (`force-include` → `gsj_rollout/pins/`), `PINS_PATH` resolves `GSJ_PINS_PATH` → checkout → packaged copy, proven from a scratch venv against the real CP-09′ body (findings `[]`); the bridge itself built in `gsj-harness-rollout-server-examples/slime_bridge/` *(at `slime-cp17` since the examples repo's CP-69)* — callback-shaped `SessionResult` → slime `Sample` (v0.3.0 surface read from the vendored adapter), three enforced assertions (mask-before-ratio, sentinel rejection at the bridge's own −9000 floor, `checks` called trainer-side), two-tier rejection (pipeline poison raises, episode badness masks to zero-gradient FAILED), 14 fixture-driven tests on the real CP-09′/CP-07 bodies, each assertion's test shown failing when the assertion is removed; **no loop run** — CP-17's inputs named (weight-sync mechanism, policy-version declaration/P3, reward attach, the 19-attempt cadence, on-estate Sample verification A-26, `max_tokens`) |

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
`gsj-harness-rollout-server-examples/slime_bridge/` *(at `slime-cp17`
since the examples repo's CP-69)* (ADR-0018), converting
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

**[CP-31] No row moves; M9c — thinking in the consumer surface
(external repo + `docs/**` only; every library path byte-untouched).**
The examples project ships thinking ON: `thinking: "medium"` is a
first-class documented value in `example_project/config.yaml` (the
comment carries CP-28's cost/benefit, the YAML-1.1 quoted-form trap,
and the pins coupling), `train.py --thinking` overrides it, and every
run prints its mode. The load-bearing piece was pins: the wheel carries
only the off-mode set, so a pip-only consumer had NO thinking-on pins —
the examples repo now carries a byte-identical copy
(`example_project/pins/thinking-on/`, provenance in `pins/README.md`),
train.py sets `GSJ_PINS_PATH` from the effective mode BEFORE its first
`gsj_rollout` import (the CP-11b once-per-process fact forced the
import restructure) and refuses a visible mode/pins mismatch in words
before the estate is spent; the RUNBOOK's serve command carries the
variable inline for the receiver leg, and an all-G6 collect wipeout is
named in train.py's own output (the F-18 lesson applied to the new
regime — the run book's §Thinking section gives each mode dated,
attributed expectations and labels every pre-CP-31 number as
off-measured). Interim, stated as such: the durable cure is the wheel
carrying both mode files — **wishlist 28 opened** (external F-40; the
ordering trap is F-41). CP-32 (the stranger test, both modes) inherits
the section written to be followed literally. Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-32] No row moves; M9d — the stranger test, both modes (external
repo + `docs/**` only; every frozen path byte-untouched).** The shipped
triple ran end to end from the public artifacts alone — GitHub clones
(~2 s), `install.sh` from PyPI (~11 min, the torch warning firing as
documented), one config value edited (`traces_dir`) — and the honest
answer is YES with one carried workaround: a stranger can run this in
both modes today, but the serve printout's Polar commands are broken
under a PyPI install (F-45, wishlist 29) and only the rewritten §Run
sentence carries them past it. Measured, replacing CP-31's
extrapolations (all 2026-08-14): pooled ON collect **72/72 in 13m35s**
vs same-day OFF **72/72 in 4m36s** — **2.95× pooled** (the 15–20 min
guess was high; the yield beat ~98% at 100/100); the first ON GPU leg
— replay **mean|Δ| 0.016546, 0.35% of positions over 0.21** (~2× the
off floor, same order: F-43's reading guidance holds), peak **135 GB /
94%** of the device at rows to 32,645 ids (F-13's prediction, real),
advantages centring exactly (mean 0.0000, nonzero 8/72) though reward
came SPARSER not denser (1/72 vs CP-28's 3/15), think-share 61% vs the
67% median; and the sync proving 0.040184 mean|Δ| over 96% of
positions. Hunt list scored: 1 CONFIRMED (72/72 accepted, nothing
hand-set), 2 CONFIRMED (symptom matches §Thinking verbatim; the cure
is findable only there — train.py's own healthy-reading line was the
misleader, F-51, fixed), 3 & 4 MEASURED (above), 5 WRONG SHAPE (no
G6-named ingest failure exists — silent masking then an undiagnosable
assert, F-49, mitigated), 6 WRONG SHAPE (a pydantic type traceback,
not the documented by-name rejection, F-50), 7 HIT AND WORSE (7/72
`finish_reason: length`, max row 32,645/32,768, all qualifying
silently — F-47), 8 NOT HIT (no artifacts dir >1 `.md`). Not
predicted: F-45 (the PyPI-era print), F-46 (trainer-side buffering,
fixed), F-48 (the archive mixes modes), F-52 (both repos' CP-31
commits sat unpushed — "public" lagged "landed" by one checkpoint),
F-53 (serve-updated.sh's health gate runs by accident — verified).
External register F-45–F-53; **wishlist rows 29–33 opened**; fixes
landed examples-side only (RUNBOOK ×7, config comment, train.py ×3 —
each verified live). Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP
· 1 BETTER · 1 TBD**.

**[CP-33] No row moves; M10a — the wishlist cluster (freeze-lift:
cli/config/receiver, pyproject, ci.yml, serve-updated.sh, pins packaging,
tests, docs, the external repo).** The CP's one real design call is
**ADR-0025: length termination is surfaced, never screened** — CP-32's
7/72 thinking-on episodes at the wall stay trainable (TR1's allowlist has
admitted tail `length` since CP-02, both bridges already label it
TRUNCATED, CP-17 trained one live); what changes is that `gsj-rollout
submit` and train.py's collect AND grade now print `length-terminated:
K/N` unconditionally, the bridge's TRUNCATED label is aggregated at
grade, and the spec §logprob-discipline carries the posture as an
`[added at CP-33]` bullet. No `checks.py` rule — fail-closed at the one
unrecoverable point would quarantine correct evidence — so no CP-34 stop.
Wishlist row 28 landed as pure packaging: the wheel force-includes
`pins/thinking-on/pins.gsj.json` beside the off reference (ADR-0019/0024
posture unchanged — default resolution still means thinking-off), the
examples repo's interim copy and its drift guard are RETIRED (train.py
locates the packaged file via `find_spec`, before its first import), and
the packaged path is documented in the README's pins section. The CP-32
cluster closed with failing-when-removed tests: F-45's printout says
which install shape it is (NOTE + `<checkout>` placeholders on a wheel,
runnable absolutes on a checkout — wishlist row 22's missing-venv hint landed in
the same branch), F-48's receiver stamps the resolving pins document's
declared mode into every archived filename, F-53's health gate rides
`bash -s` like the script's other two remote blocks (a content tripwire
guards it), and wishlist row 32 was found ALREADY CURED at HEAD — CP-30 landed
both the `True → "on"` mapping and its test; F-50 measured the 0.1.0
wheel, which predates it, so the row closes by documentation plus the
release. Wishlist 20 landed as `submit --from-bank <parquet> [--row K]`
(lazy pyarrow behind a named error; zero-translation proven against the
recorded TaskRequest). Wishlist row 26's flake: **waits, recorded** — no committed
report evidences the hosted-runner ULP flake (the repo's record, wishlist row 14,
is the arm64 story; the last three CI runs are green), and by §4's own
rule a reported defect stays UNVERIFIED until a checkpoint verifies it —
weakening ADR-0016's named-hazard guard with `np.allclose` on unverified
evidence would be backwards, and `mcp-service/tests` is frozen this CP
regardless. (The CP's own push then EVIDENCED it — run `32126927920`,
the wishlist-26 row records the details; the tolerance decision now
waits only on an oracle that prints its numbers.) Wishlist row 24 untouched (`mcp-service/` frozen). F-52's durable
cure: §8 rule 8. Release 0.1.1 cut (wishlist row 27 heals with it). Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-34] No row moves; M11a — the estate bootstrap (a NEW public repo,
plus a packaging release here).** The demo repo exists:
**github.com/MHGanainy/gsj-rollout-demo** — the demo a stranger uses to
go from their own corpus to a running estate, and the third public
artifact beside the library and `-examples`. The difference is the
audience: `-examples` shows a TRAINER how to train against an estate
that already exists; the demo shows someone with documents, a config,
and an inference endpoint how to get an estate at all. Three inputs
(corpus in the contract's shape; `config.yaml` carrying exactly the
stranger's values — corpus path, endpoint URL, served-model name, plus
three documented optionals that exist because endpoints differ; the
endpoint itself), one command (`./bootstrap.py up`), and the estate
stands with the corpus ingested and verified. How Polar runs is the
demo's external ADR-0001, decided on measurement: a published container
(`ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.2` — the public repo's
vendored patched Polar tree + the PyPI wheel in ONE interpreter, so
`import_path` resolves with no PYTHONPATH; DockerRuntime drives sibling
episode containers through the mounted socket; `GSJ_PINS_PATH` rides
compose env on the gateway and receiver and the printed submit command),
composed beside Forgejo and the published mcp-service image on a
DNS-named network with NO host ports. The library change is Step 3's
minimum: `pyproject.toml` force-includes `corpus/ingest_corpus.py` as
`gsj_rollout/ingest_corpus.py` (the pins mechanism applied to a module),
released as **0.1.2**, so `python -m gsj_rollout.ingest_corpus validate`
reaches the PASS table from a bare pip install — proven from the built
wheel in a scratch venv, and by two new root-suite tests (159 → 161).
The bootstrap derives THIS estate's pins (G1 from the corpus's own
cards; G2 by AGENTS.md byte-substitution on the reference capture,
sha-tripwired) and stops loudly on an invalid tree before anything runs.
The smoke, on the H200 as a clean box (fresh tree, PyPI install, GitHub
clone, nothing side-loaded; the endpoint was the operator's H200 engine
via the pinned serve.sh recipe — a stranger's endpoint may differ, a
CP-35 hunt item): attempt 1 died at the first in-network probe — the
Apple-Silicon-built image was arm64 on an amd64 box, cured by buildx
multi-arch and now load-bearing in A-28 — and attempt 2 stood the whole
estate in **33.5 s** (verify 13/13 PASS, engine check ok), after which
**one episode was submitted and ACCEPTED end to end**: dispatch →
sibling sandbox → in-sandbox clone → retrieval under the episode JWT →
gateway proxy → receiver, `collected 1/1`, the trace archived with the
F-48 mode stamp, quarantine empty (`finish_reason: length` on the 0.6B
model, surfaced by the ADR-0025 line, screened by nothing). Wishlist
rows **34–37 opened** (the GHCR visibility flip only the operator's UI
can perform — until then a true stranger's pull fails; the foreign-model
pins walk not yet one-command; the G2 capture as a demo-repo copy rather
than wheel data; the serve printout's third install shape). Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-35] No row moves; M11b — trajectories a person can read (external
demo-repo work; `docs/**` only here).** The demo repo is now the whole
stranger loop: stand the estate up (bootstrap), check the endpoint
BEFORE spending episodes (preflight), submit, and READ what the agent
did (read.py) — four surfaces, all derived from published artifacts and
the receiver's archive, none of them a library change. What CP-32's
stranger hand-counted is now two commands: `./read.py show` renders the
archived body as a session transcript (task, checkout pages, every
turn/call/result with retrieval hits page-checked against the timestep
on the spot, thinking decoded and `|`-marked, truncation labelled twice,
the deliverable or the honest statement that none was written, runs of
byte-identical turns collapsed with a count), and `./read.py export`
projects the body for programs (counts, boundaries, gates, census,
per-turn calls; the arrays REFERENCED — they are ~95% of the bytes and
the archive holds them verbatim). `./read.py quarantine` explains every
finding code in `checks.py`'s vocabulary with what-to-do — the most
actionable object in the system is no longer the least visible. The
Step-1 finding that shaped all of it: **the archive's messages lose
reasoning** (the vLLM parser seam; A-29) — thinking-on reasoning lives
only in the token arrays, so the transcript decodes mask-1 runs
(`tokenizers` + the served model's tokenizer; without them it says, per
turn, what it could not render). The demo also grew the mode surface
CP-34 lacked: `thinking: medium` in config.yaml re-derives pins from
the wheel's per-mode documents and recreates the Polar services when
the generated files changed since the last bring-up (`.polar-digest`),
so the receiver's stamp follows the mode — proven live both directions,
and the run-through archive now holds `.thinking-off` and `.thinking-on`
episodes side by side, attributable (F-48's answer visible in `ls`).
CP-34's hunt item 1 (the foreign-endpoint wild card) is now LEGIBLE
though not closed: `./preflight.py` probes reachability, the served
name, the stated window, the tool parser, and — via vLLM's `/tokenize`
— the served tokenizer against THIS estate's pinned tail ids and EOT
id, each mismatch named with its consequence; against the reference
stack all six probes pass (the control), and what an API cannot see is
said once, out loud (sampling defaults — wishlist row 38). The
run-through: preflight control PASS; one episode per mode submitted and
accepted (OFF: 41 turns, `finish_reason: length`, the 0.6B looping a
decisions-search 36× — the transcript collapses it and says NO
deliverable was written; ON: 2 turns, 1,200 think tokens of 1,285
trainable, decoded and rendered). An adversarial review fan-out (18
agents) confirmed and fixed eleven defects in the new surfaces before
they shipped, including `latest` resolving to quarantined bodies, three
crash shapes on malformed evidence, and the missing LP/TR/H41 finding
explanations. Wishlist rows **38–39 opened**. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-36] No row moves; M11c — the stranger test, from nothing
(external demo-repo work; `docs/**` only here).** The first ungated
stranger run: a fresh directory and venv, `git clone` from the public
URL, the wheel from PyPI (4.6 s), images from GHCR **anonymously** —
the wishlist-34 flip verified live during a genuine cold `up`, row 34
retired — with the README as the only input, on an Apple Silicon Mac
(the H200 cannot play the stranger: dockerd egress still firewalled,
re-measured). The deliverable is findings **F-54..F-68**. The one wall:
**F-54** — `gsj-mcp-service` and `gsj-pi-harness` publish linux/amd64
only, and an ARM docker REFUSES a manifest list with no matching
platform rather than emulating, so `up` died at the mcp pull and again
at the sandbox pull, the second message misdiagnosing the cause; cured
demo-side (the bootstrap now detects ARM, pulls both explicitly
`--platform linux/amd64`, and says so — the mcp embed ran 115 s under
emulation, episodes unaffected), with the durable multi-arch publish
opened as **wishlist row 40**. Everything else was friction, not walls,
and the injected failures all diagnosed themselves (the /v1 trap, the
unknown key, the page gap with its exact census row, bad/ambiguous ids,
a SIGTERM mid-`up` healed by an 11.4 s idempotent re-run) — except the
"missing prompts.yaml" injection, which the contract itself blesses
(§4: absent prompts.yaml is legal; scored wrong-shape, F-67). The
fresh-context readers' verdict on the trajectories is the P4 answer:
"pipeline works, model is tiny — conditionally", the condition being
that the transcript's honesty (the collapse, the NO-deliverable line,
the labelled truncation) earned the separation — and their sharpest
converged demand, that the OUTCOME live in the header rather than a
footer parenthetical ("accepted, 95% trainable" one line above a
buried no-write notice), landed as fixes (the `show` header
`deliverable` line; export `deliverable`, `archive.sha256`, and a
`conventions` block for the span/mask/logprob semantics a consumer had
to guess). The honest answer, unhedged: amd64 + Docker + a
reference-shaped endpoint → nothing-to-read-trajectory is real in ~5
wall-minutes plus the endpoint; Apple Silicon needed this CP's fix;
a non-Qwen endpoint remains the named, untested seam (wishlist 35,
CP-37). Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER ·
1 TBD**.

**[CP-37] No row moves; M12a — the model-dependent surface (external
demo-repo work + `docs/**` and A-30 here).** Everything the model
decides is now enumerated, classified (endpoint-derivable /
snapshot-derivable / estate-side / human decision), and — where an API
can reach it — **derived instead of detected**: the demo bootstrap
derives the G6 tail and `builder.end_of_turn_token_id` from the
endpoint's own template render (vLLM `/tokenize`+`/detokenize`) at
`up`, writes them where `GSJ_PINS_PATH` points, and leaves G4's byte
hashes **empty, named, never defaulted** (no API exposes those bytes;
the local-snapshot recipe is documented). The control: forced through
the foreign-model branch against the reference stack, the derivation
reproduced every pinned value exactly — off tail
`[151644,77091,198,151667,271,151668,271]`, on tail `[151644,77091,198]`,
EOT 151645, both modes, mode stamp intact. CP-04′'s hand-measured
template proof is now a preflight probe (strict prefix-extension over
`/tokenize`; it reproduces the CP-04′ divergence at n−4 on exactly the
four think-block ids against the embedded template, and measures the
reference stack prefix-extending live, 40→93 ids); on failure it prints
the lost span and the cures in order (symmetric template / the
now-config-reachable glue stitch `generation_prompt_glue_ids` / stop),
because the alternative is every multi-turn episode quarantining at
`G7:chains_total_ne_1` — caught, but only after each episode is spent.
First non-Qwen evidence, tokenizer-only: **Llama-3.1's official
template is prefix-extending** (TRUE, 59→99 ids) and derives tail
`[128006,78191,128007,271]`, EOT `128009` — sane values; a wild mirror
of the same model ships a simplified template that ignores
`add_generation_prompt` (no tail exists; the derivation refuses) —
template identity varies by *mirror*, not just family. G6's
thinking-off/mode-asserting meanings are **Qwen-family-specific** —
plainly said in the spec §G6 [CP-37]: elsewhere the gate asserts
template integrity, and both modes derive the same tail (measured:
`enable_thinking` is unused jinja context on Llama templates — a
non-off `thinking` is a wire no-op there, while the archive still
stamps thinking-on). One enumerated hazard DISSOLVED under the review's
verification: an unslashed served name is safe — `config.py` prepends
its own provider label (`estate.provider`, default `gsj/`) before the
harness's `provider/model` split, so `pi_harness.py:104`'s raise is
unreachable through the one YAML; a demo guard drafted on the wrong
premise was deleted before commit. Wishlist **35 narrowed** (the
endpoint-derivable half
closed; the residual is G4's snapshot walk + endpoints without
`/tokenize` + the first foreign episode), rows **41–42 opened**
(the harness's Qwen-bound constants; non-Qwen hybrid-reasoning
geometry), **A-30 registered** (the turn-terminator derivation
assumption). The stranger-facing deliverable is the demo's
`docs/MODEL-SURFACE.md`. Tally unchanged: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-38] No row moves; M12b — the second family (external demo-repo
work + `staging/serving/` + `docs/**` here; `gsj_rollout/` untouched
at 1,999 lines).** The first non-Qwen episode ran end to end through
the demo's own printed one-liner — Llama-3.1-8B-Instruct (unsloth
mirror, pinned revision) served on the estate under the family's own
four legs (`--tool-call-parser llama3_json`, the snapshot's embedded
Meta template, its own generation config pinned: temperature 0.6 /
top_p 0.9 / **no top_k**, `--max-model-len 32768`) — and was
**ACCEPTED: `chains_total: 1`, 8/8 completions merged, zero
findings**, after a preflight that was all-ok with the sampling warn
the only warn. The derivation's live values equal CP-37's offline
snapshot measurement exactly (tail `[128006,78191,128007,271]`, EOT
128009, mode pair byte-identical — row 42's no-mode half now
measured live). The CP's central finding is the **two-terminator
geometry** (wishlist row 43): the model SAMPLES `<|eom_id|>`=128008
as its tool-call stop while the template re-renders those turns
closed with `<|eot_id|>`=128009 — and reconstruction absorbed it,
because the vendored merge is canonical-vs-canonical (renders
against renders; the sampled stop rides the stream at mask-1, the
canonical close at mask-0). A-30's stop half is thereby measured
false-but-harmless and the assumption re-scoped (derive the
RENDER-side closer); CP-37's "sampled-vs-rerendered identity is an
unprobed extra condition" claim is withdrawn in MODEL-SURFACE — the
probe's prefix-extension row IS the chain-GROUPING condition, with
the slicing half covered by the end-of-turn row and failing closed at
`G7:chains_truncated`. What the
episode showed that no probe could: the healthcheck round trip's
answer half fails 4/4 on this model (meta-commentary / repeat-call —
model temperament; the parser half is the load-bearing half), a
handful of raw newlines inside a sampled JSON string (7, beside 19
escaped ones) turned the final `write` into a text answer and quietly ended the episode with only
the turn-1 stub written, and an accepted episode can be entirely
retrieval-free (7 file-tool calls, zero `mcp_gsj_*` — the gates
check provenance, not retrieval). Zero-logprob rate at mask-1:
**1.8%** vs the reference's 6–14% (an estate property, not a
constant). MODEL-SURFACE.md corrected and extended from first use;
no library change was needed for this family — rows 41's constants
still never bit (thinking-off by design). Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-39] No row moves; M13a — publish, and de-trap (freeze-lift:
`CLAUDE.md`, `release.yml`, `staging/README.md`, `docs/**`, the demo
repo, plus one continuation-pointer line in the examples register;
`gsj_rollout/` untouched at 1,999).** The post-CP-38 three-repo audit
(committed verbatim at `docs/AUDIT-2026-08-24.md` — the specification
for CP-39/40/41) named the publish failure first: the library sat 3
commits behind its public mirror, CP-36/37/38 unpushed, so the entire
stranger-test record, the model-surface derivation, `serve-llama31.sh`
and rows F-54–F-68 were invisible outside this machine (O1) — while §8
rule 8, written at CP-33 for exactly this class, was ignored three CPs
running (the finding under rule 8's own [CP-39] amendment: the demo
repo, which "both repos" doesn't name, WAS pushed each time, and no
report claimed the library pushed, so the evidence clause passed
vacuously). Pushed; verified from outside by a fresh clone showing the
three checkpoints and the second serve recipe; rule 8 widened and
copied into CLAUDE.md's workflow section — the process file CP-39 also
rewrote from its 26-CP-stale CP-08 stub (S1: serve/submit real since
CP-09′, `builder.py` load-bearing, 161 tests, 0.1.2 exports,
1,999/2,000 standing). F-54–F-68 got their register home (M1): a
demo-repo `FINDINGS.md` carrying the fifteen rows, plus a pointer under
the examples register's F-53 — the F-series is ONE register across both
consumer repos, a new row takes the next id after the highest anywhere,
next fresh id F-69 from either file. The two traps: `release.yml`'s
required-entries tuple now asserts all five must-ships — the
thinking-on pins (ships since 0.1.1) and `ingest_corpus.py` (since
0.1.2) were unguarded on the tag path, which deliberately does not
re-run CI (O2; wishlist row 28-adjacent, its [CP-39] note); and
`staging/README.md`'s Megatron row (line 34 at HEAD, W1's citation) no
longer instructs the checkout its own CP measured broken — `26.04-alpha.rc1` lacks
`megatron.training.tokenizer` (F-06); the image's `/root/Megatron-LM @
1dcf0dafa` is what actually ran, and the in-file erratum records that
the contradiction and the report contradicting it shipped in the same
commit (`a647359`, CP-17) (W1). The same file gains the CP-38
second-family recipe it omitted (S9). Recorded as staying: `forgejo/`'s
five mis-resolving predecessor citations remain under freeze until
CP-41's conscious lift (W2); the consumer-surface refresh and the
orphan re-owning are CP-40's; the namespace collisions, the ADR
amendments and the `dist/` residue are CP-41's. Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-40] No row moves; M13b — the consumer surface, and the orphans
(freeze-lift: both consumer repos unrestricted, `docs/**` here;
`gsj_rollout/` untouched at 1,999).** The refresh half: the examples
repo — the one a stranger consumes, and the audit's least accurate —
stopped teaching the past as the present. The two bridge install
commands glob the NEWEST sibling wheel instead of naming a 0.1.0 file
that ENOENTs (W5 — proven by a run: with the stale 0.1.1 still sitting
in `dist/`, the corrected command installed 0.1.2 and the slime suite
passed 14/14; note the deliberate divergence from `install.sh`'s
first-match glob, whose lexical `[0]` would have picked the OLD wheel —
the run-one-release-behind trap CP-39 recorded for CP-41); the five
v0.1.0-as-current texts say 0.1.2/CP-34 (S2, plus the slime
requirements' "no release channel exists yet" block, which now names
PyPI); the RUNBOOK's closing surprise list no longer teaches the three
CP-27-fixed bugs as live (S3 — the module-form no-op and both
URL-shape traps left the list as named departures; the MCP-secret
bullet stays, still true); the slime rider's pins sentence tells the
both-mode-files truth (S6); seven register cells caught up with the
checkpoints that outran them (W4: F-25 → FIXED CP-27; S5: F-02 →
CLOSED CP-17, F-04 → VERIFIED CP-17, F-43 → MEASURED CP-32, F-20/F-21/
F-23 code-halves → FIXED CP-27/33; C5: F-42's rider-vouching corrected
in the same pass); and the two Qwen-bound recipe texts are
family-labelled (S4's examples half: the four legs' VALUES named
family-bound per CP-38's measurements, and the EOT re-derive recipe
derives the family's OWN token — `<|im_end|>` has no answer outside
ChatML; Llama's `<|eot_id|>` → 128009 is the worked example). Same-pass
accuracy riders, taken because Step 1's own bar is "accurate, not just
corrected": the RUNBOOK's root-suite count (150 → 161) and the
zero-logprob band (4–25% → 1.8–25%, CP-38's Llama at the low end) —
S14's examples half — and `smoke.py` joined its own run book's file
table (O9's minor half). The Step-1 stranger re-read then caught what
the first pass missed, and its yield was folded in the same sitting:
an eighth and ninth lagging register cell (F-52 still teaching §8 rule
8's sentence as unwritten; F-18 carrying "~9.5 min" against its own
cited report's thrice-stated 6m37s), the bridge recipes' wrong `cd`
depth (one level short from the bridge dir, in the exact blocks W5
corrected), the two bridge run books' missing PyPI path (they
installed only from a sibling `dist/` while their own requirements
headers name PyPI — both now lead with the PyPI line, proven by a
second run: 0.1.2, slime 14/14), and the dist-override run-behind trap
absent from the surprise list, now its own bullet. An adversarial
fact-check of every claim the refresh introduced (eleven, from
`_null_sections_to_empty`'s F-25 docstring to Llama's 128009) came
back eleven-for-eleven CONFIRMED against primary evidence.

The orphans, decided — the CP's rule was that no row may end it
waiting on something that already happened, and none does. **O3/C-3:
CLOSED, satisfied in substance by CP-32** — the measurements C-3
existed to obtain are on the record from the 72-episode pooled-ON run
(yield 72/72, wall-clock multiplier 2.95× pooled, replay mean|Δ|
0.016546 in-band, reward density 1/72, one real optimizer step); what
C-3 imagined beyond that — a training-scale ON corpus — is production
collection, owned with the estate-posture set below, and this sentence
is the disposition note the audit found missing. **O4/gap row 2 and
O5/gap row 22: DECIDED — production-prep, not permanently accepted**,
each annotated in place with its reasoning; the demo half of row 2's
residual is now the demo register's own F-69 (anonymous read is
load-bearing there, and undocumented until this CP). One register
correction recorded here rather than silently absorbed: the CP-40
prompt calls rows 2 and 22 "the last two GAPs"; the two GAP-status
rows are 12 and 22 (rows 4 and 14 closed at CP-24/CP-23; row 2 is
PARITY carrying the estate residual) — the prompt's referent is the
two open estate-posture residuals, which is what was decided.
**O6/wishlist 19: re-parked on a real event** (the first card edit on
any estate; its stale-note half handed to the next conscious `pins/`
lift, named in-row). **O6/wishlist 10: CLOSED** — the documented
exception is the decision. **O7/F-44 (examples register): re-owned**
— the CP-32 park expired with the A/B; the next reward-graded
collection fixes the grader before grading. **O8/wishlist 24: CLOSED
for the evaluation** — production-prep; the cadence it deferred to
never existed. **O8/wishlist 26: kept on a live trigger** — the next
CI firing of the evidenced flake buys the magnitude instrumentation.
**O9: wishlist 9 transferred to production-prep; row 22's F-39
warn-once half CLOSED, declined for cost; wishlist 16 CLOSED** — the
carried-patch tests can only regress at a re-vendor and REVENDOR.md
step 5 binds exactly there. The mechanic behind all of it — the OPEN
side of registers decaying while the DONE side stays true (the
audit's decay mode 2) — got the smallest durable catch: §8 rule 9,
one sentence — parks name observable events and every CP's register
pass checks them. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP ·
1 BETTER · 1 TBD**.

**[CP-41] No row moves; M13c — namespaces, amendments, residue
(freeze-lift: `forgejo/` — W2's conscious lift, `corpus/
ingest_corpus.py` — C2's header comment, `gsj_rollout/checks.py:97` —
W9's citation comment, `pins/**` — the recorded ask, `docs/**`, and
`dist/`; `gsj_rollout/` otherwise untouched at 1,999).** The audit's
last third: every item a correction to a document or a citation, zero
behaviour changes. The namespace collisions: `forgejo/`'s five
predecessor citations qualified — the CP-01 convention ("The
predecessor's CP-02 recipe") applied to the five sites CP-01 missed —
and the CP-01 report's "predecessor citations qualified" claim,
contradicted by the files, now carries a dated [CP-41 erratum] (W2);
the corpus contract's header and `ingest_corpus.py:65` qualify v1's
"CP-33 / ADR-0046" as the predecessor's (C2); `checks.py:97` qualifies
"ADR-0007(e)" IN PLACE — one line rewritten, 528/528 held, the suite's
equality tripwire green, no ADR-0021 question raised (W9's library
half — its demo half, the README's 25–50 s band, stays open in the
report's ledger); the three
golden-MANIFEST `staging/collector|pins` cites are named the
predecessor's, with this repo's `pins/g6_tail.captured.txt` pointed to
where the file exists here (M5). Five ADR amendments appended in the
ADR-0003 shape, dated: ADR-0005 (the `>=3.11` clause superseded at
CP-19 by ADR-0020 §4 — C8), ADR-0011 (the tokenizer-at-pin-time
premise moved at CP-37's endpoint-only derivation — S12), ADR-0019
(the 9+2 earmark arithmetic corrected to ADR-0021's measured 12+9+2 —
C7), ADR-0020 (the standing risk closed at CP-29: name claimed, row 17
DONE, 0.1.2 current — S12), ADR-0008 (the archive filename's F-48 mode
stamp, with gap rows 16 and 22 annotated in place — S13). A-14 finally
carries CP-22's live re-verification note (C6 — the CP-22 report
claimed the row gained it that day; it gained it here). The residue:
the stale 0.1.1 wheel deleted from `dist/` — the 0.1.2 that remains
matches PyPI, so `install.sh`'s lexical-first sibling-wheel preference
has nothing older to pick — and the recorded ask TAKEN: `pins/
pins.gsj.json`'s two shipping notes (lines 86 and 102) now state the
CP-24/ADR-0022 and CP-23 truths, `derive_pins.py` reproduced every
approved value before AND after the edit, no value moved (S8; wishlist
19(a) FIXED in-row). The remaining leftovers: checks-spec's carried-
evidence inventory gains the two `pins/thinking-on/` rows,
`docs/polar/README.md` now indexes all nine evidence directories,
A-9's four CP-01 caveats surfaced to this register, A-13 gained CP-32's
third serialized sync, A-29's evidence list gained CP-38's Llama body
(S14's library half, less ci.yml), the VERDICT's M5/M6 bullet is
marked LANDED with the verl "M6" naming collision stated (S11), the
[CP-33] paragraph above now reads "wishlist row" at its seven bare row
cites (C3 — an in-place disambiguation of a past block, recorded here
rather than absorbed silently), and both wishlist rows numbered 19
carry the numbering note in-row (C4). Recorded, not fixed, each with
its owner: `ci.yml:23`'s `>=3.11` header comment (S14 — `.github/`
frozen; the next `.github` lift), `mcp-service/README.md:6-8`'s
blanket predecessor-numbers disclaimer, false since CP-15 put this
repo's own numbers in the body (C1 — file frozen; the next conscious
`mcp-service/` lift), and one CP-41 discovery outside C2's named
scope: `ingest_corpus.py` carries five more un-namespaced predecessor
ADR-0047 cites (lines 2, 815, 877, 1052, 1478 — the lift was the
header comment only; the next conscious `corpus/` lift owns them, and
they ship in the wheel exactly as S8's notes did). This closes the
audit: every id CP-39/40/41 could reach is closed or recorded; the ids
remaining open — W3, W6, W7, W8, W9's demo half, S4's remainder, S7,
S10, C9, C10, C11, M2, M3, M4 — are enumerated with owners in the
CP-41 report.
Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-42] No row moves; S7 closed — the README lift the CP-41 ledger
named.** `README.md` rewritten as the front door (CP-42: one paragraph,
three diagrams — the shape, the cutoff, the two roles — the proven
table with per-row sources under a measured-as-of date, the not-done
list, the record map). The S7 trio corrected in the rewrite: the badge
paragraph's root-suite count now 161 (was 136), the gate roster now
G1/G2/G3/G5/G6/G7 with G4's estate-side posture stated (G6 was
omitted), and the wheel-contents claim now `gsj_rollout/` + both pins
sets + `ingest_corpus.py` (the "nothing else" wording predated CP-34).
The §8 rule 9 scan over the CP-41 open-ids ledger: none of the
remaining parks' named events fired this CP (no VERDICT register pass,
no charter §4 register pass — see the CP-42 report's questions on that
park's wording — no consumer-repo sitting, no CI firing for wishlist
row 26); thirteen ids remain open, owners unchanged. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-43] No row moves; the demo, in brief (freeze-lift: the demo repo
+ `docs/**` here).** The demo repo's front door rewritten for its
actual audience — someone with documents and an inference endpoint
deciding whether this is worth an afternoon: the three-inputs →
one-command → trajectory sequence drawn; CP-36's measured expectations
moved up front under F-18's lesson (install in seconds, 6–7 GB of
images, cold `up` ~2.5 min composed from the measured pieces, an
episode ~20–40 s, the two platform facts — the ARM amd64 pull
automatic, a non-Qwen endpoint derived automatically with the serve
argv still the operator's — and a "normal, not broken" list); a real
transcript excerpt (the stranger run's `case_orchard@t2` episode — the
cutoff-holds line, the deliverable line, the trainable count —
verbatim with one marked trim, machine-diffed against the reader's
actual output); and the contract's tree drawn from the actual
synthetic corpus, with `md/` named as the generated layout. The
audit's demo-side remainder closed in the same sitting: W6 taken
code-side (G4's hashes emptied for ANY non-reference model, success or
failure — four derivation paths executed), W7, W9's demo half
(~20–40 s, containing its own citations), C9, C10 (the four
template-derived rows NAMED — class-counting re-embedded the
off-by-one: the context-window row is [endpoint]-classed on vLLM too),
C11 (the generated pins.gsj.json now tells the truth about its own
provenance on every path — host/walk_status/G1-G2 blocks rewritten,
derived_at narrating what the run derived, carried, emptied, or FAILED
to derive, the thinking-on collective block rescoped), M2, and S4's
four demo texts. An 11-agent adversarial workflow over the working
tree (two stranger readers, eight id verifiers, one code review) plus
a follow-up verifier reopened C10 once and C11 twice before the
closures held. Demo commit `16810d3`, pushed. No new findings; the
demo register stands at next fresh id F-70. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-44] No row moves; the examples, in brief (freeze-lift: the
examples repo + `docs/**` here).** The examples repo's front door
rewritten for its actual audience — a trainer engineer deciding whether
to train with this: what the bridges give (traces in, batches out, two
trainers, the three assertions drawn on the path), the two bridges
compared with ownership stated plainly (consumer code, not library code
— ADR-0018), the measured costs (collection 13m35s ON / 4m36s OFF
pooled at CP-32, the relaxed-vs-strict qualification split, reward
1/27–1/112 and not a stable constant, the replay floor in both modes,
the ~1-min sync downtime, the 94%-of-an-H200 GPU leg), and the
seven-item not-solved list assembled from CP-17's and CP-21's "what a
real training run would need". Every number carries its mode and source
checkpoint — the F-18/F-42 discipline applied to the front door itself.
No new findings; the F-register stands at next-fresh-id F-70. Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-45] No row moves; the predecessor archived (freeze-lift: `docs/**`
+ `gsj-envloader` itself — the one CP permitted to write there).** The
Step-1 sweep (six read-only enumerators) found nothing archiving breaks:
every past frozen-assertion (CP-00–CP-24 scope_drift lines, CP-41's
tag-anchored audit) is time-stamped and survives; the goldens'
provenance is content-addressed (wheel sha256 `a6921de6…`, checkout
`4037bc2` = the v0.8.0 tag commit) and stays checkable on an archived
repo; the H200's predecessor state (`.venv-cp04prime`, the checkout,
the `gsj-envloader-staging` compose project) is local disk the platform
action cannot reach; no documented procedure pushes to the GitHub repo.
What archived means (ADR-0026): the fallback role RETIRED (the
frozen-alive term was a term of the provisional adopt and expired at
the conversion — CP-17, 2026-08-11), the evidence role CONTINUES (the
goldens' collecting stack, readable at v0.8.0), law 3 HISTORICAL
(bound CP-00–CP-44, did its job — the predecessor reached the archive
byte-untouched; the freeze is platform-enforced from here). The
predecessor's diff against v0.8.0 is one file, its README (the archive
header); the GitHub repo set to archived via `gh repo archive`. Law 3's
out-of-lift statement sites (CLAUDE.md, README.md) amended in the same
commit — declared scope_drift, §8 rule 8's CP-33/CP-39 history being
the recorded cost of amending one site and leaving another stale.
Audit M5 adjacent only (the manifests' predecessor-path citations need
exactly the readability archiving preserves); no wishlist row moves
(row 9's `task.py:878-885` citation stays checkable at the tag). Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-46] No row moves; the repository framed in place — nothing
moved (operator-confirmed at the Step-4 wall).** The shape question
measured out against its own premises: GitHub's language bar already
reads 94.4% Python by linguist defaults (`vendor/` vendored, `docs/`
documentation, Markdown prose — no attribute needed; the 541,579
counted Python bytes are exactly the non-vendor, non-docs Python), a
clone is 5,926 KB with the record ~21% of compressed content against
vendor's ~57%, and the record's paths are load-bearing in code — 740
breaking citations across the three repos (725 here, incl. 7
pathlib-joined test constants the substring census cannot see),
CI/release's `docs/polar/h200-fidelity/` fixture, `derive_pins.py`'s
runtime reads of `docs/polar/*/trace.json` and
`corpus/staging/skills/*/SKILL.md`, and the shipped wheel's
`pins.gsj.json` provenance strings, which PyPI immutability puts
beyond repair. So: `docs/README.md` and `spike/README.md` added
(indexes — the `docs/polar/README.md` mechanism of CP-41/S14, one
level up), the GitHub description set (was null) and seven topics
added (were empty), `.gitattributes` declined (the bar was already
truthful; `spike/` is first-party evidence, not vendored code), and
`corpus/staging/` kept (the freeze record the lock's SHAs, both
golden manifests, the mcp bares, and the wheel's `skill_card_hash`
pins hang off — its collector is archived, so byte-identical
regeneration is unprovable in principle). Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-47] No row moves; every tracked file classified, read-only
(the operator's consumer-repo question).** The two-axis census
(audience × coupling) is `docs/CLASSIFICATION.md`: 701 tracked files
— CONSUMER 20 · OPERATOR 416 · CONTRIBUTOR 58 · INTERNAL 207 on
audience; RUNTIME 458 · DERIVED-FROM 6 · CITED 237 · **FREE 0** on
coupling. The zero is the deciding measurement: nothing tracked is
free to leave — every evidence shelf is cited by path from something
that must keep resolving. Seventeen INTERNAL files are live
dependencies (the contradiction list: seven `docs/polar/` bodies
read by the suite/CI/release gate/pins walk, `docs/golden/mac/
tokens.npz` plus its two transcription sources, the six pins
captures, `CLAUDE.md` via the session harness), and `corpus/staging/`
(OPERATOR, 163) stays the densest coupling in the repo (six runtime
readers, five derivation chains — the CP-46 keep, re-verified). One
accidental coupling found: the root suite fails if `vendor/polar/`
is absent as a directory (test_cli.py:232 monkeypatches `exists`
but not cli.py:51's `isdir`) — a few-line edit at the next test
freeze-lift. The strict CONSUMER+FREE repository is 20 files and
does not build; three options priced against the counts (split /
untrack / frame harder) and (c) recommended — the decision is the
operator's, nothing acted on. Rule-9 pass: no parked row's named
event fired in this CP's read-only scope. Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-48] No row moves; the development record untracked (the
operator's decision on CP-47's classification — the census's option
(b), taken with the priced costs accepted).** 197 files left `HEAD`
and stay on disk, byte-untouched: `docs/prompts/` (52), `docs/reports/`
(52), `docs/decisions/` (26), the audit, the classification, and the
`golden/`/`polar/` evidence not on the keep list (8 + 57). What stays
tracked under `docs/` is 15 files plus the CP-48 prompt (the last
tracked one): the four normative documents (PyPI-published URLs),
`docs/README.md` (carries the disclosure), and the ten load-bearing
evidence files — re-verified before removal, every reader confirmed at
its line (conftest.py:19-22, test_checks.py:707/720-721/935/1007/1018,
ci.yml:150, release.yml:133, derive_pins.py:76). The six `pins/`
captures and `CLAUDE.md` stay tracked (the captures are outside
`docs/`; CLAUDE.md is the workflow's instruction file, not record —
every session reads it). One reader CP-47's §4 missed, found by this
CP's re-sweep: `corpus/tests/test_taskbank.py:255-258` opens BOTH real
callback bodies (rows 1/3) in the CI corpus job — the keep list
survives, its proof list grows. The consumer repos and the archived
predecessor read nothing under this repo's `docs/` (four-repo sweep,
grep-verified, code-readers zero). The cost is disclosed rather than
rewritten (README and docs/README each carry one paragraph): every
CP/ADR citation in the surviving documents dangles publicly, including
the two report paths in the wheel-shipped pins provenance — immutable
on PyPI; the record is checkable by the operator only from here. After
the removal, everything green with the removals staged and again from
a fresh clone: root 161, corpus 58, mcp-service 89, the pins walk
reproduced, the wheel's 16 entries. From CP-49 the record writes to
the same paths, ignored, never committed (CLAUDE.md §Workflow states
the practice; this §7 append is the one per-CP artifact that still
reaches the remote). Rule-9 pass: no parked row's named event fired —
this CP touched tracking metadata, prose, and `.gitignore` only.
Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-49] No row moves; the Mac-golden fixtures re-homed (the
operator's follow-through on CP-48: fixtures out of `docs/`).** The
three files CP-48 kept tracked under `docs/golden/mac/` because the
suite reads them — `tokens.npz` (conftest.py:22, opened :117 by the
stdlib `_read_npz`) and its two transcription sources `MANIFEST.md` /
`record.json` (DERIVED-FROM only: `timestep: 12`, `finish_reason:
"stop"` from `env.steps[*].stop_reason`, both re-verified against the
bytes) — moved by `git mv` to `tests/fixtures/golden-mac/`, the
provenance travelling with the fixture (the CP's one judgment: a
fixture whose provenance is a comment is a fixture nobody can
re-derive, and untracking the sources would split the A-1 chain
across the public/private boundary). The five-agent four-repo
re-sweep confirmed CP-48's census with no missed reader this time:
the sole code reader is conftest.py:22, `MANIFEST.md`/`record.json`
are opened by no code anywhere, CI and the release gate touch only
`docs/polar/h200-fidelity/`, the pins walk reads only `docs/polar/`
trace bodies, both consumer repos read none of the three, and the
archived predecessor's one mention is its frozen CP-45 header
(platform read-only, left as written). release.yml:87 additionally
asserts the wheel excludes both `docs/` and `tests/`, so the
destination ships in no artifact — the wheel's 16-file entry list is
byte-identical before and after. `docs/golden/` now has zero tracked
content and ignores whole (the CP-48 negations collapsed to one
`.gitignore` row; `transcript.txt` and `artifact/` stay on disk,
untouched, the operator's copy — 5 entries before the move, 2
after). The `docs/` keep list is seven — the polar bodies — and both
disclosures state the corrected arithmetic (ten at CP-48, seven
since CP-49, `docs/golden/` entirely untracked). Green after the
move: root 161, corpus 58, mcp-service 89, the pins walk reproduced.
Rule-9 pass: no parked row's named event fired — one path constant,
tracking metadata, and prose only. Tally unchanged: **21 PARITY · 7
DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-49a] No row moves; the last tracked prompt untracked (the
operator's direction, post-CP-49).** `docs/prompts/CP-48.md` — kept
at CP-48 as the prompt that records the untracking decision — leaves
the index by the same pattern (`git rm --cached`, disk untouched),
and `docs/prompts/` now ignores whole, like `docs/reports/` and
`docs/golden/`. Tracked under `docs/` from here: **12 files** — the
four normative documents, `docs/README.md`, and the seven polar
bodies. No code reads any prompt (CP-48's sweep held); root suite
green after the removal. The "last tracked prompt" statements
amended where they were current-state claims (CLAUDE.md §Workflow
and layout, docs/README.md's disclosure parenthetical, the
`.gitignore` comment); the §7 [CP-48] paragraph stays as written —
the historical statement of what CP-48 kept. Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-50] No row moves; the estate grouped under one roof (the
operator's decision on a counted proposal, four answers).** CP-47
classified by audience and got 416 OPERATOR files — true, unhelpful;
CP-50 reclassified the 507 tracked files by *role* (product ·
extension point · estate · scaffolding · evidence) and found the
estate — everything that exists to stand the H200 test environment up,
production bringing its own counterpart — spread over four top-level
directories, 213 files (42%). Three directories split on that axis:
`corpus/` (`ingest_corpus.py` is product — it rides every wheel as
`gsj_rollout.ingest_corpus`; `tests/` is scaffolding; `staging/` is 163
frozen fixture files), `pins/` (the approved sets ship; the derive
scripts are the walk; the captures are evidence — stays at the root as
a unit, three suites and the build anchor to it), and `staging/`
(`serving/` is scripts, the YAML a config example, the README *the*
estate recipe). The coupling was counted before anything moved — an
eight-agent four-repo sweep, 507 path references, and an adversarial
verifier that caught two readers all seven finders missed
(`corpus/tests/test_taskbank.py:26` climbing `parents[2]` to
`docs/polar/`; `mcp-service/tests/test_roster_pin.py:28-29` reading
root `pins/` through the helpers' one-level climb) — the CP's own
prediction, true a third time. Must-edit counts per move: `forgejo/`
9, `mcp-service/` 6, `staging/` 14, `corpus/` ~24; the joint move of
`mcp-service/` and `corpus/` is what made it cheap — the mcp helpers
find `corpus/staging` via `SERVICE_DIR.parent`, so moving both under
`estate/` preserved every corpus coupling with a one-line re-anchor
(`ESTATE_DIR`). The three named questions, answered by the operator:
`mcp-service/` goes under `estate/` (its sibling-product traits — own
suite, GHCR image — are real, but the role axis decides: it stands the
test estate up and the demo proves production brings its own
retrieval); `ingest_corpus.py` stays with the pipeline at
`estate/corpus/` (moving it into `gsj_rollout/` would put ~1,400 lines
inside the size law at headroom 1, break the mcp suite's `import
ingest_corpus` rail, and reverse CP-34's single-source decision for
zero consumer-visible gain — the force-include's *source key* changed,
the wheel's 16-entry list and every entry's CRC did not, no release
forced); and the entry point is one thin `estate/estate.sh` (nine
verbs, each `exec`-ing the existing script in place, every failure
saying what to do; no `scripts/` collection, because the scripts read
their siblings — `serve.sh` sources `model-*.env` and ships its own
jinja). Executed by `git mv` (history follows; 213 renames, 7 with
content edits), every executable reference fixed in the same commit:
this repo 45 edit groups (CI ×6, release tuple, `.gitignore` ×3,
pyproject force-include + sdist key, the derive scripts ×4, root tests
×7, the mcp helpers' re-anchor + `test_admin` + `test_taskbank`'s
`parents[3]`, the scripts' own echoed hints); the examples repo 16
literals (`rebuild_taskbank.sh` ×5, `train.py:527`, both loop READMEs,
the RUNBOOK ×4, README); the demo 2 comment lines. Left stale by
design, each covered by the disclosures' footnote clause: the
wheel-shipped comments (`checks.py:92`, `pi_harness.py:7/:78` — wheel
bytes, unchanged by law), the `pins.gsj.json` provenance strings
(PyPI-immutable), the freeze-record bytes (`corpus.lock.json:3`, the
`corpus.yaml` headers), this register's history and §3's CP-01 table,
VERDICT's wishlist rows, and the examples' FINDINGS/ADR rows. Green
after the move: root 161, corpus 58, mcp-service 89 (one resume-seam
NameError fixed — `test_admin.py`'s import), the pins walk reproduced,
the fresh-clone check passed. The honest residual: the clone is the
same size, `vendor/` is still 215 files, `spike/` still sits at the
root; the top level went 16 → 12 entries and the `staging/` vs
`corpus/staging/` double name is gone — **legibility, not
simplicity**, CP-46's distinction, which held. One operational cost:
on the H200 `git pull` moves tracked files only — `forgejo-data/`,
`.token*`, `mcp-service/data/`, `serving/run/` stay at the old paths
and a compose `up` from `estate/` would start a *blank Forgejo*;
`estate/README.md` carries the four `mv` commands to run before the
next bring-up. Rule-9 pass: no parked row's named event fired —
paths, tracking metadata, a thin wrapper, and prose only. Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-51] No row moves; the red badge, the register, and engine
provenance (freeze-lift: `docs/**`, `CLAUDE.md`, `ci.yml`'s one
comment, `tests/test_cli.py`, `estate/mcp-service/{tests,README.md}`,
`pins/derive_pins.py`, the examples repo; `gsj_rollout/` untouched at
1,999).** The 2026-08-28 estimate's Now bundle. **The badge**: the
encoder oracle (`estate/mcp-service/tests/test_backend.py:107-112`)
now states max|Δ| and cosine when it fails — strictness unchanged, 89
passed, forced locally `max|Δ| 9.686e-08, cosine 1.000000000` — so the
next red run carries the numbers wishlist 26's tolerance decision has
waited for since CP-33; the row now records the six post-CP-40 firings
that five rule-9 passes missed. **Engine provenance, the simple form**
(gap row 22 narrowed, gap 12 owned, wishlist 38 corrected):
`pins/derive_pins.py` states the engine beside the values it measured —
served model (asked of `GSJ_SERVED_ENDPOINT`'s `/v1/models`), snapshot
revision, sha256 of the generation config, the tokenizer and the served
template — and `--record` writes it into both pins documents'
`provenance.engine`, refusing if an approved value would move; zero
library lines; every value names its source, every absence its reason.
The walk reproduced all 16 approved values before and after; on this
host it printed the block with the served-model line a named absence
and wrote nothing (the H200 walk with `--record` will — proven in a
scratch clone: both documents gain the block, `pins` byte-identical, a
diverged walk refuses). Not covered, said in-row: a mid-run engine
restart without a re-derive, and the applied sampling itself. **The
small fixes**: `ci.yml:23` says `>=3.12`; the mcp-service README's
disclaimer is scoped to the predecessor's numbers and its quick-start
says `cd estate/mcp-service` (its three `staging/README.md` cites were
already qualified); `test_cli.py` answers `isdir(vendor/polar)` itself
— proven in a scratch clone without `vendor/polar/`: HEAD's file 1
failed, this one 18 passed; `derive_pins.py` globs the skill cards
(wishlist 19(b)); the examples grader reads the deliverable the task
declared and refuses several undeclared ones by name (F-44; five
tests, slime 14 → 19). **The cells**: wishlist 14 (superseded into
26), 26, 38 ("gap row 22"), 41 (W8 struck); A-2 (S4), A-15, A-28 (W3),
the §4 numbering note (M3); gap rows 9 and 12; `CLAUDE.md`'s
F-54–F-69; examples F-22, F-39, F-41, F-43 and F-53 (unescaped pipes).
**The closures**: F-05/06/07/12/13 ACCEPTED; wishlist 14 SUPERSEDED, 37
COSMETIC, 43 RECORDED, 39 FOLDED into A-29 with its on-disk
counter-example named; F-41's code half DOCUMENTED-AND-CLOSED; A-11
REWORDED. F-08 stays open and unowned, deliberately — a decision for
its own sitting. **Rule 9's teeth** (§8): every park carries a
`waiting-on:` token and lives in a row; a red job on the push is a
fired trigger until it names its row (the report template gains the
`ci:` line and the scan count); "the next lift of X" and "the next
register pass" are rejected wordings. The CP-41 prose parks were taken
(S14 ci.yml, C1, W8, S4/A-2, M3, S10), closed, or moved into wishlist
rows 44 (the wheel-shipped cites + M4) and 45 (the H200 `mv`); the
CP-47 coupling taken. Retrofit: **30** tokens in the tracked register
(VERDICT 20, CHARTER 10) + 10 in the examples register; the demo's
three parks (F-54, F-56, F-69) are owed at the demo's next sitting
(not lifted). Nothing wanted a library line. Tally unchanged: **21
PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-52] No row moves; the user documentation (new: `docs/guide/` —
21 plain-Markdown pages + 37 PNG diagrams; touched: `README.md`'s
Documentation line, `docs/README.md`'s shelf row, `CLAUDE.md`'s layout
line; `gsj_rollout/` untouched at 1,999; nothing in CI, no extra, no
site).** The operator asked for professional consumer documentation
with diagrams "as frequent as possible", drawn in PowerPoint and
rendered to images; two directions arrived mid-CP and both bind: the
decks and their generator live **outside** this repository (the sibling
`gsj-harness-rollout-server-diagrams/` on the operator's disk — a
python-pptx drawing vocabulary with one house style, one 37-slide deck,
PowerPoint → PDF → PNG via `pdftoppm`, LibreOffice as the preview
engine), and the pages are **plain GitHub-flavoured Markdown only** — a
MkDocs Material site was built, reviewed and then withdrawn at the
operator's word, so there is no site generator, no `[docs]` extra and
no Pages workflow; `docs/guide/README.md` is the index GitHub shows for
the folder. Shape: Getting started (3) · Concepts (5) · Guides (8) ·
Reference (3: a hand-written Python API, the 42-string finding
vocabulary, the wire formats) · About (1). **What the pages may not
do**: cite `CP-NN`, ADRs, wishlist rows or the audit — the record is
private since CP-48 (§8 rule; the one `docs/reports/` mention is the
disclosure itself) — or link anything but the four tracked normative
documents. **How they were checked**: written one agent per page from
the source; reviewed twice by independent readers per page (every
signature, default, message string, finding string, path and port
opened against `gsj_rollout/*.py`, `estate/**`, the spec), each pass
closed by a whole-set consistency editor; the second pass also rendered
every page through GitHub's own Markdown API and a checker that
verifies links, heading anchors (GitHub keeps the `--` of `--episodes`
in a slug — three links fixed), images, alerts and angle-bracket
placeholders GitHub would strip: final run **21 pages, 0 problems**;
root suite 161 passed. Real corrections the reviews landed, so the
docs say what the code does: `ADM1:status_not_completed:<status>`
carries the status; G7 reads five stat keys, not six; `gsj_settings`
is pi's `settings.json` (compaction off), not the model limits;
`down --wipe` removes only `forgejo-data/` and `.token`; `serve` from a
wheel still renders and prints, with a `NOTE:` line. **Said, not
hidden**: the index's "what has been proven" strip copies the README's
figures verbatim — a reader of the tracked tree cannot re-derive them
(the CP-48 cost, restated on the About page); the PNGs add 7.3 MB of
tracked binaries (200 dpi, palette-quantised — 150 dpi would halve it);
a clone cannot regenerate a diagram, by the operator's decision — the
regeneration recipe is the sibling directory's `README.md`. Consumer
artefact, outside the size law and outside the record. Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-53] No row moves; the diagrams redrawn illustratively and the
READMEs refactored (touched: `docs/guide/` — every page, `img/` now 54
slides, was 37; `README.md`, `docs/README.md`, `estate/README.md`,
`estate/mcp-service/README.md`, `vendor/REVENDOR.md`, `spike/README.md`;
`gsj_rollout/` untouched at 1,999).** Two operator directions, both
applied whole. **First: "the figures are too wordy where it should have
been more illustrative"** — the drawing kit grew an illustrative layer
(pictogram glyphs, icon tiles, numbered chevron strips, block arrows;
≤ 6 words per shape, ≥ 12 pt, the sentence moves to the page), an
exemplar was approved in Preview, and every module was redrawn against
it: table-slides became maps (the gates as seven padlocks over the keys
they compare against, G4 unlocked and estate-side; a trace as aligned
token strips with logprob bars; the triage as symptom tiles over the
one place to look), eight dense slides split rather than shrank
(cutoff-audit, trace-fields, glue-stitch, trace-rules-order,
pins-gate-map, corpus-tree-rules, cli-task-sources, release-gate,
session-result-paths, quarantine-families, repo-map, revendor-recipe
are new), and every fact that left a slide was relocated into its
page's prose — stated per-slide in the workflow record, not assumed.
**Second: the six consumer/operator READMEs rewritten in place with
figures**, under one rule: the body carries no CP/ADR/wishlist
citations (facts stay; each displaced citation moves verbatim into a
closing "Provenance" section, so nothing is lost), with two stated
exceptions — the root README's proof-table evidence column and
`docs/README.md`'s banner/shelf map, which describe the private record
itself. The root README is also the PyPI page: absolute raw-URL
images, no GitHub-only alert syntax, verified through PyPI's own
renderer (`readme-renderer`: renders, 5 images, zero alert artifacts).
Every page and README passed the GitHub-render checker (links,
anchors, images, alerts, stripped placeholders): 21 pages + 6 READMEs,
0 problems; the deck manifest and `img/` agree at exactly 54; no PNG
is unreferenced; `img/` weighs 6.7 MB (was 7.3 at 37 — the flat style
compresses better). The decks and generator stay OUTSIDE the
repository (the operator's standing direction). Root suite 161 passed.
Consumer artefact, outside the size law and outside the record. Tally
unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-54] No row moves; the documentation condensed (touched:
`docs/guide/` — 21 pages merged into SIX flat pages, 1,189 lines total
(was ~5,800); `img/` pruned to the 33 referenced slides, 3.3 MB (was 54
/ 6.7 — the full 54-slide deck survives outside the repo); the six
READMEs tightened again to 506 lines total; `gsj_rollout/` untouched at
1,999).** The operator: "the guide and markdown files are too many …
condensed and compact and to the point." The new shape, by reader
intent: `README.md` (index, 70) · `how-it-works.md` (175) ·
`validation-and-pins.md` (224 — the complete 42-string vocabulary
survives as a one-line-per-finding table) · `server-guide.md` (302 —
the full YAML field reference and every CLI flag survive as tables) ·
`trainer-guide.md` (299 — the API as signatures + short notes) ·
`troubleshooting.md` (119). The condensing rule, enforced per file and
reported per agent: hard line caps; every command, flag, default,
port, env var, finding string, message text, hash, and number
survives; depth is delegated by link to the four normative documents —
**zero operative facts dropped, by each condenser's own accounting**.
The record documents stay untouched (the operator's CP-53 scope
answer, carried forward). Verified: the GitHub-render checker on all
12 files → 0 problems (the root README's absolute-URL images are the
checker's known false positive, resolved by hand); PyPI's renderer on
the root README → renders; no PNG unreferenced, none referenced and
missing; root suite 161 passed. Consumer artefact, outside the size
law and outside the record. Tally unchanged: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-55] No §7 row moves; wishlist row 26 CLOSED — the encoder
oracle's tolerance decided (ADR-0016 amendment; touched:
`estate/mcp-service/tests/test_backend.py`, `docs/VERDICT.md` rows 26
and 14; `gsj_rollout/` untouched at 1,999).** Row 26's token fired
three times with one measurement (CP-53 run 33171819467 attempts 1
and 2, CP-54 run 33178592668: chunk p0001c0000, max|Δ| 7.451e-09,
cosine 1.000000119, docs-only diffs) and CP-55 is the sitting the
reports promised. Step 1 found the hazard end of the margin was never
in the record: the quoted "wrong embedder ≈ 0.80" is CP-18's
different-chunks baseline under the SAME encoder (reproduced
0.799976), so CP-55 measured the real thing — Chroma's default EF is
an fp32 ONNX export of the SAME all-MiniLM-L6-v2 checkpoint (90 MB,
unquantized; ADR-0016's "ONNX-quantized" corrected) sitting at
max|Δ| 1.155e-07..2.719e-07 / cosine within 1 ULP of 1.0 across all
51 case_0001 rows. The margin is [1.490e-08 … 1.155e-07], 7.75× end
to end, not six orders. The bound: max|Δ| ≤ 4e-08 (the geometric
midpoint — 2.7× above the worst benign drift, arm64's 1.490e-08, and
2.9× below the substitution floor) AND cosine ≥ 0.999 (the
wrong-model floor; cosine measured unable to resolve either near
class). `np.array_equal` retired; a both-directions test pins the
bound (the drift classes pass, the measured substitution delta fails,
a wrong-direction vector fails the cosine floor alone); mcp suite 90
(89 + the new test), root 161. Unknown, named: WHY the runner's
arithmetic differs (reduction order / BLAS / torch build) — the
amendment's reopen conditions (a drift crossing the bound, a
substitute under ~1.155e-07, any encoder re-pin) stand in for the
investigation. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP ·
1 BETTER · 1 TBD**.

**[CP-56] Row 2's estate residual closed where every consumer is lifted;
the network re-clone channel is proven refusable.** The gap this CP was
scoped to (gap row 2, open since CP-01, dispositioned production-prep at
CP-40) is the *estate residual* under a row already at PARITY — anonymous
Forgejo read letting a URL-guessing sandbox agent re-clone past its
cutoff. The cure landed as mechanism (a) (credentialed clone URLs +
`REQUIRE_SIGNIN_VIEW`), chosen over (b) sandbox-egress because (b) breaks
the episode's own MCP/engine reach unless per-host-allowlisted; (a)
defends the repository and leaves the model/MCP reachable as they must be.
`config.py` gained `clone_credential_env` at **net +0 lines** (comment
recovery kept `gsj_rollout/` at 2,000/2,000 — no ADR-0012 raise; the
credential is env-sourced, never a YAML value). The three probes were run
container-faithful: sign-in ON returns 401 on both re-clone channels where
anonymous read returned the pages, the harness's own credentialed clone is
unbroken (CP-11 hardening intact, token absent from `.git/` and — via the
existing `_strip_credentials` — from the trace echo), and the forged
later-timestep MCP token stays refused (`mcp-service` suite, 14/14). **A
finding rides with it:** `REQUIRE_SIGNIN_VIEW` breaks two consumers frozen
this CP — the MCP index build and the pipeline's scaffold/verify re-clone,
both anonymous-read and both bring-up-time — so the H200 flip is a
documented two-phase (build anonymous, then flip) while the demo estate,
all consumers lifted, does the flip in `bootstrap.py` and closes it live.
Row 2's status is unchanged (PARITY was never the residual's question),
its cell records the close and the two-phase, and its `waiting-on` token
is re-pointed at the H200 frozen-consumer lift. Demo F-69 gets the same
disposition, cross-referenced. Tally unchanged: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-57] No row moves; the embedding model is configuration, and
everything that was pinned about the embedder follows the config
(touched: `estate/mcp-service/` — `embedding.py`, `index.py`, `state.py`,
`config.py`, `config.yaml`, `Dockerfile`, `README.md`, `tests/`; `docs/**`;
`gsj_rollout/` untouched at 2,000/2,000).** Step 1 found the id itself was
never hardcoded — `embedding.model` has carried it, MiniLM-defaulted and
fingerprint-hashed, since CP-01 — what assumed MiniLM was everything
downstream: the oracle's `shape == (384,)` and its two MiniLM-measured
ends, the Dockerfile's bake by name (`MINILM_REVISION`), the chunk window
sized for 256 by a YAML comment, and a store that recorded only the
opaque hash — a mismatch detectable, never nameable. The corpus lock and
census are page-byte/git-SHA derived (no vector enters them; the lock's
sha256 unmoved). Decided (ADR-0016 amendment): **refuse, not rebuild** — a
model change against an existing store is a re-pin, not staleness, so the
store now records `embedding: {model, revision, dimension}` beside its
fingerprint (the pins-document shape) and a startup — or `/admin/reindex`
— under a different model/revision lands in `state: error` naming both
models and the fix (`index.rebuild: always` is the explicit re-embed ask
and skips the gate; a pre-CP-57 store backfills the record on its first
matching reuse), before the model even loads; the identity is
also stamped into every collection's metadata and the vectors' width
cross-checked at load (a forged record over foreign vectors, or a
`chroma/` restored out-of-band, is refused at startup, where Chroma alone
raises at the first query); a pre-CP-57 store — every store that exists
today — is assumed the one pin that built those and refused under any
other; a rebuild writes the new identity before it drops anything, so an
interrupted re-pin is never served; `embedding.revision` must be a full
commit SHA; the chunk window is checked statically against the model's
window minus its specials AND exactly on the real chunks after ingest
(the review measured 127/814 staging chunks overflowing a 100-token
window at the static boundary — a character slice re-tokenizes longer);
an unresolvable id fails at startup with the id, revision and three
checks named. Four of those guards are the adversarial review's (an
interrupted same-width re-pin rolled back served the wrong model; the
pre-CP-57 rebuild-over; the backfill inside the corrupt-rebuild catch;
the boundary overflow), fixed in-CP and each test-pinned. **How the bound survives:** the |Δ| end transposes by component
scale, 4e-08·√(384/d) — the CP-55 constant bit for bit at the default
model, a reasoned extrapolation elsewhere (A-31); the hazard end is the
cross-model class for any non-default model — measured at CP-57, MiniLM
vs bge-small at the same 384 dims: cosine 0.23–0.31, which the 0.999
floor fails by ~0.7 — or a width the store refuses. Proven on real server
processes with `paraphrase-albert-small-v2` (768 dims, 100-token window,
chunking 96/16): the default path unchanged (mcp suite 107 = 90 + 17,
root 161, fingerprint identity recorded, corpus lock unmoved); the second
model indexed and served with the oracle green at 768; the model change
refused verbatim with the store untouched; the bogus id named at startup.
Frozen-side notes: `.github/`'s HF cache key is MiniLM-only and never
re-saved, so the second model (~45 MB) downloads once per CI run at suite
import (after which the suite runs offline); the CI job label,
CLAUDE.md:73/82 and the root README's dated proven-claims row
(README.md:76) still say 89. Wishlist row 46 opened (the per-model measurement, parked on
the first training re-pin). Tally unchanged: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-58] No row moves in the tally; row 2's estate residual CLOSED on
the H200, row 22's record filled, wishlist 45 DONE — the H200 session
(touched: `estate/` — `mcp-service/config.yaml` + `compose.yml`,
`forgejo/docker-compose.yml`, `rollout.h200.yaml`, `estate.sh`,
`corpus/ingest_corpus.py` + its tests, `README.md`; `pins/` — the
`provenance.engine` block in both documents, written by the walk on the
box; `docs/**`; `gsj_rollout/` untouched at 2,000/2,000).** Three things
on the box, in order, each operator-pasted and ssh-verified before the
next: the four moves (wishlist 45 — after a survey that found the record
wrong about the box twice: no git checkout there, only an rsync-era copy
at 0.1.0, so the migration was a fresh clone at the same absolute path
with the two path-bound uv venvs adopted; and a root-owned
`forgejo-data` whose cross-parent rename needs `sudo`), the bring-up on
the moved data (`existing token still valid`; `gsj-mcp-service:0.4.0`
built here from CP-57's code with the read credential baked, loaded on
the box, and its first start on the pre-CP-57 store — fingerprint
`ea063721…`, no identity block — did what CP-57 said it would:
`index reused` + `stored index predates the identity record — backfilled
embedding {MiniLM @ 1110a243…, 384}`, `/health` carrying the block), and
the engine provenance recorded by the walk on the box with every
approved value reproduced, including the tokenizer leg only an estate
can run. Then the sign-in flip's one-shot completion: both frozen
consumers lifted (the MCP's `auth_token_env`, verify's clone-back
credential — the same `GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING` the sandbox
clone presents), the estate recreated closed (anonymous `info/refs`
200 → 401), the three probes refused container-faithfully on the H200
itself, verify PASS 30/30 through the token, and one episode collected
with the token absent from its trace (row 2 [CP-58], verbatim). Left
open on purpose and tokened: any scaffold's post-push `ls-remote` still
reads anonymously and escapes as a traceback under sign-in (outside the
CP's "verify credential only" lift — one argument; a fresh or wiped
estate scaffolds with sign-in temporarily off, documented); a production
bring-up owes its own `--record` (rows 22/38).
Frozen-side, recorded: `estate/mcp-service/README.md`'s build line and
the Dockerfile's header still say `0.3.0` (a fresh build must be tagged
`0.4.0` — the compose asks for it), `CLAUDE.md` still says 89, and the
MCP's cold `clone --bare` persists the read token in its clone cache's
`config` (wishlist 47, found by the review — the H200's warm cache holds
none, measured). Teardown per the standing rule:
engine and our three host processes stopped, Forgejo and the MCP left
UP in the closed state, data dirs and venvs surviving. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-59] No row moves in the tally; row 2's last anonymous reader closed
and its park resolved; the estate gains its one-command bring-up
(touched: `estate/bringup.py` new, `estate/estate.sh` — the `bringup`
verb, `estate/runs/.gitignore`, `estate/corpus/ingest_corpus.py` — the
one-argument scaffold fix + two tests, `estate/README.md`; `docs/**`;
`gsj_rollout/` untouched at 2,000/2,000).** Step 1 read the demo's
`bootstrap.py` whole and found most of it transfers: the phase order,
the secret-in-env pattern, the elapsed-time line, the idempotent re-run,
the `/health` wait; what does not is everything that assumed the estate
was the demo's — a fixed owner, in-network-only URLs, `check_corpus_yaml`
dying on a `corpus.yaml` that names another estate, the pins derivation
(G1/G2 from the corpus — this script does not write pins, it reports
which cards the packaged set lacks), Polar and the receiver in compose
(here they are the operator's: the script stops at the estate and prints
the three commands), and `ensure_amd64_image` (dropped: production is
amd64, the image-pull path is the operator's registry decision; the
refusal names `--platform linux/amd64` on an arm64 daemon). The
two-phase sign-in ordering transferred as *credentials before readers*
and then collapsed: with the scaffold read-back credentialed (Step 2:
`resolve_read_auth` → `ls_remote_heads`, a `PipelineError` naming the
variable, test-pinned — the test fails with the argument removed) every
reader presents the token, so a created Forgejo is closed from its
first start and the OFF→ON flip is retired (`--anonymous-read` keeps an
evaluation estate open). The adopt paths are measurements: Forgejo by
URL + the admin's username and PASSWORD — Forgejo 16 refuses to mint
another user's tokens under token auth (`auth method not allowed`,
measured), and anonymous `GET /api/v1/version` answers 200 open / 403
closed; an existing owner's repos named like the case ids are compared
branch-by-branch against the corpus's deterministic build (equal →
adopted, different → refused naming each branch; `--overwrite-repos`
is the explicit push-over); the retrieval service by URL + secret, its
`/health.embedding` against the requested identity (refused on
mismatch — CP-57's posture, not a second one), its `cases` against the
corpus, the secret proven by the reindex it triggers. Six runs on this
Mac (arm64, no GPU, the vllm-metal engine): (1) everything created in
35 s, the MCP's fingerprint `ea063721…` byte-identical to the H200's
store, the lock and bank byte-identical to the tracked staging tree;
(2) the re-run reused 8 / backfilled 0 with every artifact byte-stable;
(3) run 1's Forgejo adopted with owner `gsj-prod`, run 3's MCP cloning
through `host.docker.internal`; (4) both adopted, the owner's colliding
repos verified equal, and the identity check firing verbatim when a
second model was asked of the adopted service; (5) the second model
(`paraphrase-albert-small-v2`, 768 dims) indexed under a mounted host
snapshot, its identity recorded, `--rebuild` re-embedding it back with
the identity following; (6) the refusals — a model change against run
1's store, a tampered `gsj-prod/case_0001` named per branch, a missing
`.env`. Then a straight-enter interactive run (13 prompts: Enter on twelve,
the image prompt answered with the native arm64 build — wishlist 49;
the script now defaults to that build when the daemon is arm64 and it
is present) on the tracked staging corpus with `git status` clean, and **one
episode collected from the emitted config** (`COMPLETED`, `findings:
[]`, the clone URL stripped, 0 secret values in the trace). Three
findings: the amd64 `gsj-mcp-service:0.4.0` image segfaults under qemu
on an arm64 daemon at the embed step (0.3.0 survived emulation for 10
days as the demo's) — the script reads the container's log and refuses
naming the native build (wishlist 49); CP-03's one-URL rule has no
derivable answer on a Docker Desktop Mac — the LAN IP was host-only,
`host.docker.internal` container-only, a VPN interface both and then
neither within the hour — so the gateway host is *probed* (a listener
on the port, a container on the run's network dialing every host IPv4)
and recorded with its evidence; and wishlist 47 measured on a created
estate (the read token in 4/4 clone-cache `config` files — the run
directory is `0700`, `.env` `0600` from birth; measured on the
final script's runs). The in-CP adversarial review (five lenses, two refuters per finding)
confirmed 33 findings — one high on the code (an adopted-only run
named a sandbox network nothing had created; now created or verified,
removed by `down`), the rest re-run defaults not taken from the record,
a re-run silently switching identity (now refused unless `--retarget`),
`down` blocked on the runs its own refusal sends there, `.env` values
unquoted, the probe listener serving a directory, the no-dialable-address
case continuing into a broken estate (now a refusal), and doc lines
still prescribing the retired recipe — all fixed in-CP and the fresh,
re-run and adopt-both runs repeated on the final script (`rollout.yaml`
and `run.json` byte-stable across the re-run). The demo/library
consolidation is decided, not
done: `bootstrap.py` should become a config-writer that calls
`estate/bringup.py` once the wheel ships it (wishlist 48, on the 0.1.3
release with row 44). Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP ·
1 BETTER · 1 TBD**.

**[CP-60] Release 0.1.3 — no row moves in the tally; three parks fire
(wishlist 36, 44, 48 each waited on this CP) and the wheel goes 16 → 18
entries (touched: `pyproject.toml` — 0.1.3, two force-includes and their
sdist entries, the ADR-0027 sdist note; `gsj_rollout/__init__.py` — the
literal; three `gsj_rollout/` comments rewritten in place — `wc -l`
2,000 before and after, `checks.py` 528; `estate/corpus/ingest_corpus.py`
— the five predecessor `ADR-0047` cites and the lock's runtime string,
comments and strings only; `estate/bringup.py` — a two-way layout shim,
the one declared excursion; `.github/workflows/release.yml` — the
required tuple 5 → 7; `.github/workflows/ci.yml` — the labels 161/58/89
→ 164/67/107; `tests/test_wheel_pipeline.py` +3, `tests/test_scaffold.py`;
`README.md`, `docs/guide/`, ADR-0027).** The version sweep, recounted:
41 lines carrying `0.1.2` outside the record across the three repos —
CP-34 counted ~27 — (21 here excluding `vendor/polar/uv.lock`'s unrelated
`mdurl`, 9 in the examples, 11 in the demo). Moved, current-state: `pyproject.toml`, `__init__.py`,
`test_scaffold.py`, `README.md:43`, `docs/guide/{trainer-guide:9,
README:23}`. Left, dated-historical (CP-49's footnote clause): the §3
[CP-34] note, the §7 [CP-34]/[CP-41]–[CP-45] paragraphs, A-28's image tag
(the published image IS still `gsj0.1.2` until the demo rebuilds it),
wishlist 28's history, `release.yml:93`'s comment; eight of the nine
examples literals carry "as of library CP-34" (or CP-41) and are
historical by construction — the ninth, examples `README.md:5` ("PyPI
0.1.2"), is a bare current-state claim that the examples repo's next CP
moves (not lifted here). Left, **current-state and frozen-side,
recorded**: `CLAUDE.md:5` and `:51` ("0.1.2", and their wheel-contents
clause — both pins sets + `ingest_corpus.py`, now also the G2 capture and
`bringup.py`), `:64` ("1,999 lines" — 2,000 since CP-56), its
`161`/`58`/`89` counts and its layout tree (no `bringup.py`, `runs/`, or
the `bringup` verb) — CP-59's class, one CP older. Also moved, in lifted
paths and pre-existing: the "1,999" census in `README.md:6`,
`docs/guide/how-it-works.md:15/:24` → 2,000 (README.md:75's audit row is
dated and stays); `docs/guide/img/wheel-contents.png` still renders
0.1.2's four crossings (the deck lives outside the repo — the alt text
says so until the diagrams dir re-renders it). The demo's literals are a floor (`>=0.1.2`, satisfied by 0.1.3)
and the image tag (`gsj0.1.2` — true of the published image; A-28 says the
demo checkpoint rebuilds it at `LIB_VERSION=0.1.3`): neither is a lie
today, both are the demo checkpoint's to move. **The size law, argued
before the force-include**: §3's measure has been `wc -l gsj_rollout/*.py`
at every budget note since CP-10; a force-include is a build-time copy
that adds no line to it; ADR-0027 decision 3 rejected moving the
pipeline INTO `gsj_rollout/` precisely because that would enter the
census while the force-include's *source key* does not; and CP-59
landed `estate/bringup.py` at 1,893 lines with the census reported
2,000/2,000 and no ADR — the file's home was ruled outside the law when
it was written, and packaging does not move a home. The reading holds;
no ADR. **The finding the artifact gave**: the bring-up was not
standalone by construction — the pre-shim 0.1.3 wheel died at `import
gsj_rollout.bringup` (`bringup.py:72: ModuleNotFoundError: No module
named 'ingest_corpus'`), a packaging failure, not workflow or metadata:
the file found the pipeline (import and subprocess path) and `runs/`
relative to `estate/`. The cure is inside the file (row 48 carries the
inventory: `CHECKOUT`, `INGEST = ic.__file__`, `RUNS` = `./runs` from the
wheel, the record's script name, the Polar line of the closing
printout; after the review, the pyarrow refusal's remedy — `pip install
pyarrow` from the wheel, where `estate/corpus/requirements.txt` does not
exist), pinned by a root-suite test that imports the wheel layout with
the checkout off the path; the remaining wheel-shape residuals are
inventoried in row 48 for the demo checkpoint. **The scaffold fix rides**: CP-59's
one-argument change to `phase_scaffold` (`resolve_read_auth` on the
post-push read-back) has been checkout-only since 2026-08-30 and reaches
PyPI in this wheel — the fix that lets a consumer's `bringup.py`
scaffold a closed estate. **The CI labels**: wishlist row 46 names the
mcp-service label as a related frozen-side item (annotated: the label
half fixed, the cache-key half unchanged); no row named the corpus
label (CP-55 and CP-57 recorded both in report prose and in the
[CP-57]/[CP-58] paragraphs above); fixed here with `.github/` lifted —
the root label moves too, 161 → 164 for the three CP-60 tests, against
Step 5's "161 (correct)". `release.yml`'s header parenthetical ("the
`estate/` components ship in neither artifact") was false since CP-50 —
the sdist carries the two force-included files at their `estate/` paths
— and is reworded in the same lifted file. **ADR-0027's
consequence stated**: the pipeline's path inside the sdist moved at
CP-50; publication is wheel-only, so no published artifact ever carried
the old path. Rule-9 scan: 59 `waiting-on:` tokens; fired — 36, 44, 48
(annotated above: 36 and 48 re-parked on the demo checkpoint F-70, 44
closed with audit M4 moved to row 50 as source work under its own
observable event); row 40's "an operator republish … a library release
does not force it" did not fire by its own wording, but the demo
checkpoint's `gsj-polar` rebuild is where A-28 makes this release land.
**The release record** (the CP-34 two-commit shape: `d161672` is the
tagged release, this amendment is the CP's second commit). Push of
`d161672`: CI run 33315521689 — root suite (164) green · corpus suite
(67) green · mcp-service suite (107) green · wheel + packaged-pins
install proof green. Rehearsal, `workflow_dispatch` on `main` at
`d161672`: release run 33315532707 — build green (`twine check` PASSED,
the seven-entry tuple and the six banned prefixes asserted on the
artifact, `findings: []` / `PROOF OK` from `$RUNNER_TEMP`) · TestPyPI
green · PyPI **skipped** by the tag gate, as designed. TestPyPI proof,
a scratch venv outside every repo (`--index-url test.pypi.org`,
`--extra-index-url pypi.org` for the three deps): 18-entry wheel;
`checks.validate_session_result` on the CP-09′ body → `[]`; both pins
sets present; the G2 capture present and `f56e8a6e…` ∈
`pins.system_prompt_hash`; `python -m gsj_rollout.ingest_corpus validate`
→ `PASS (12 pass / 0 fail)`; `import gsj_rollout.bringup` → `CHECKOUT=
False`, `INGEST` the packaged sibling, `RUNS=./runs`. Tag `v0.1.3` at
`d161672`: release run 33315736384 — build green (`tag v0.1.3 matches
version 0.1.3`) · TestPyPI green (skip-existing) · **PyPI green**. PyPI
proof (CP-29's shape): a fresh venv outside every repo, `pip install
gsj-harness-rollout-server` with no index flags and no local wheel —
0.1.2 on the first two attempts (index propagation, ~45 s), **0.1.3 on
the third**; the same five checks and the validate table green from the
published wheel. Every repo the CP touched is pushed: this one only
(`main` at the second commit, tag `v0.1.3`); the consumer repos were not
touched. Frozen-side, recorded: `CLAUDE.md` (above). Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-61] The demo on the wheel — no row moves in the tally; four parks
fire (wishlist 36, 48, 49 each waited on this CP's demo checkpoint F-70;
row 40's mcp half on the image cut) and one row reopens (37, on the
container-user register row it asked for). Touched here: `docs/VERDICT.md`
(rows 36/40/47/48/49 annotated, 37 reopened, row 51 new), this §7, A-28,
`estate/mcp-service/{Dockerfile,README.md}` (the version header CP-58
left at 0.3.0 → 0.4.0 — the one lifted `estate/` path); NOT touched:
`gsj_rollout/` (`wc -l` 2,000/2,000), `vendor/`, `pins/`, `tests/`,
`.github/`, the examples repo — the DoD diff on the frozen list EMPTY,
the root suite 164.** **The image decision, first**: `gsj-mcp-service`
0.4.0 is published multi-arch this CP — not by a fresh `buildx`
(row 40's own warning: a rebuild resolves different layers than the
measured artifacts) but by pushing the two MEASURED single-arch images
and composing an index with `buildx imagetools create`: the amd64 half
is the local build `6e27f067…` the H200 loaded at CP-58 byte-for-byte,
the arm64 half is CP-59's native build `32a78aae…`; verified by anonymous
`docker pull` on this arm64 daemon with no `--platform` (F-54's exact
failing step) and with `--platform linux/amd64`, and by an anonymous
registry-token fetch of the index. Row 47 was NOT folded in: the lift
covered the Dockerfile/README header only, not `ingest.py` or the
service's suite, so the cut carries the same `clone_or_fetch` — re-measured
on the demo's fresh estate (the read token in 2/2 bare-clone configs,
the run directory 0700) and re-tokened on an observable event (a tag
above 0.4.0 on GHCR). `gsj-pi-harness` stays amd64-only (row 40's
harness half; the demo keeps the `--platform linux/amd64` cure for it
alone). **A-28 fires**: `gsj-polar` rebuilt multi-arch at
`LIB_REF=v0.1.3`/`LIB_VERSION=0.1.3` (`f0e8343a-gsj0.1.3`, index
`ae64cf2c…`; `issubclass(PiHarness, BaseHarness)` and `import
gsj_rollout.bringup` verified in both platforms' interpreters).
**The demo (F-70)**: `bootstrap.py` 1,241 → 1,163 lines and a READER —
config.yaml's three values → `work/bringup-answers.yaml` → `python -m
gsj_rollout.bringup up --answers … -y`, run from `work/` so the run lands
at `work/runs/demo/` (compose project `gsj-demo`, network `gsj-demo-net`
— the demo's old names, now the bring-up's), with `GSJ_PINS_PATH` naming
the demo's pins derived FIRST (the import-time warning's honest cure);
what remains is the demo's own — the three-value reader, the pins
derivation (G1/G2/G6), the Polar leg as three containers of one image
(`work/estate/rollout.yaml` re-addressed from the bring-up's host-run
shape: `0.0.0.0` + compose-DNS `public_url`s, `/estate/traces`,
`/estate/artifacts`; the receiver gets a byte-copy in its own directory
because `serve` re-renders the topology beside its config at every
start) — and not one function of `bringup.py` re-implemented (the
`validate` verb is the pipeline's). The four survivals: the three-input
promise (every other answer is the tool's default); the arm64 cure
(`ensure_image`, now for the sandbox image alone, gated to it); the
measured expectations (re-measured below); Polar and the receiver.
**Retired duplicates**: `estate/system_prompt.reference.txt` (sha
`f56e8a6e…`, byte-equal to the wheel's `gsj_rollout/pins/container/
system_prompt.container.derived.txt`, tripwired against the packaged
`system_prompt_hash` on read) and — CP-35's second copy — `estate/
AGENTS.reference.md` (sha `5308b28e…`): pi embeds the workspace
AGENTS.md between `<project_instructions path="/workspace/AGENTS.md">`
and `</project_instructions>` markers, and the span so sliced from the
packaged capture is byte-equal to the copy (1,244 bytes, once), so the
G2 byte-substitution is unchanged with one source; `make_corpus.py`
writes the worked example's AGENTS.md from the same slice.
`clone_credential_env` is used as designed: named in both configs, its
value only in the run's `.env`, spliced by `submit` (the recipe sources
`.env` in a subshell and passes the variable by name — `docker run
--env-file` keeps the bring-up's quotes literally, compose strips them),
absent from both archived traces. **Measured** (this Mac, arm64, the
vllm-metal engine on 8100): working tree with images present — `up`
51.2 s (the bring-up 41.9 s; the native first embed 21.6 s vs ~2 min
emulated), warm 13.3 s (`reused: 8; backfilled: 0`), `down` 5.5 s, `up`
after `down` 33.7 s; the from-nothing run (a fresh clone, a fresh venv,
`pip install` from PyPI, the images removed) — clone 1.7 s (GitHub), venv + `pip install gsj-harness-rollout-server pyarrow` 5.5 s, the three GHCR pulls ~90 s, then the refusal above; resumed with the loaded Forgejo image, `up` 134.4 s (the bring-up 126.2 s: Forgejo's first start 31.3 s, scaffold 27.2 s and verify 20.9 s all under emulation, the native first embed 27.6 s; the working tree measured the same bring-up at 41.9 s with the native Forgejo) — the daemon grew 5.4 GB for the four images; one accepted
episode (`case_orchard@2`, 2 turns, `commit 48499faa81` — CP-36's
transcript's commit) in 21 s / 19 s / 21.6 s (working tree, working tree after the review's fixes, the from-nothing clone), `./read.py show` reading it.
**Findings the run produced** (the demo's F-70–F-77; the library halves in
row 51): the bring-up's `rollout.yaml` is host-run-Polar-only (51 a);
`--mcp create` never pulls and defaults to a local tag (b); its G1 check
reads the PACKAGED set even under `GSJ_PINS_PATH` — a false `WARNING` on
every demo `up` (c); the arm64 native-image default is announced before
the answer is read (d); the wheel's `estate/…` strings and no `--runs-dir`
(e); the client's fixed `--task-id gsj-task` → an opaque `409 Conflict` on
a second concurrent submit (f, cli.py); `serve` re-renders the topology
beside its config on every start, receiver included (g, cli.py); the
host-port scan for a container leg (h). **One blocking finding the run produced, a row of its own (52)**: `codeberg.org/forgejo/forgejo:16.0.2` — the bring-up's pin, which the demo cannot override — is dead on its registry: the tag's index is served, both platform manifests it lists answer 404 (16.0.1/16.0.3/16.0/16 answer 200 on both platforms); every estate so far had the image locally, the from-nothing run was the first to pull it and died at `compose up forgejo` (F-78); the run then executed the bring-up's own cure (`ssh h200-admin docker save … | docker load`, the box's amd64 image, emulated here) and continued. Two observations, not rows: the
0.6B floor model looped 463 turns on the skill-card row (`read
/workspace` → `EISDIR`, pi compacting at the window) until stopped —
`timeout_seconds` 900 s is the ceiling the README now states, and the
receiver quarantined it as `ADM1:status_not_completed:ERROR`; and the
pre-push review (six lenses, 88 agents, two refuters per finding: 41
findings, 27 confirmed, every one fixed in-CP — the stale-record
regression on re-run answers, the corpus-driven sandbox pull, the env
scrub, the forwarded flags, the receiver's own config directory, the
subshell recipe, the `make_corpus` ordering). **Frozen-side, recorded**:
`CLAUDE.md` (0.1.2, 1,999, 161/58/89, the tree — CP-59's class, two CPs
older). Rule-9 scan: 66 `waiting-on:` tokens; fired — 36, 48, 49
(closed), 40 (the mcp half closed, the harness half re-tokened), 47 (its
"next lift" wording replaced by an observable event); 37 reopened by its
own condition. Push: the demo's `main` at `949fa4e` (one commit, `CP-61: the demo on the wheel`, amended once with the measured numbers before the push; a from-GitHub clone validated afterwards); this repo's `main` at this CP's commit — the report carries its hash and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED ·
2 GAP · 1 BETTER · 1 TBD**.

**[CP-62] The Forgejo pin, and the residuals — no row moves in the
tally; wishlist 52 CLOSED, row 51's bring-up residuals taken, (f)/(g)
recorded. Touched here: `estate/bringup.py` (+~170 lines, outside the
size law), `estate/forgejo/docker-compose.yml`, `estate/README.md`,
`docs/guide/{troubleshooting,trainer-guide}.md`, `docs/VERDICT.md`
(rows 37/51/52), this §7; the demo (`bootstrap.py`, `README.md`,
`FINDINGS.md`). NOT touched: `gsj_rollout/` (`wc -l` 2,000/2,000),
`vendor/`, `estate/mcp-service/`, `estate/corpus/staging/`, `pins/`,
`tests/`, `.github/`, the examples repo — the DoD diff on the frozen list
EMPTY; the root suite 164, the corpus suite 67.** **Re-measured first**
(2026-08-30 16:51 UTC, an anonymous registry token, both platforms):
`codeberg.org/forgejo/forgejo:16.0.2` — index served, amd64 and arm64
manifests 404, `docker pull` failing with either `--platform`; `16.0.1`,
`16.0.3`, `16.0`, `16` (one index, `sha256:7c4e1db440be…`), `15.0.3`,
`16.0.3-rootless` pullable; no `16.0.4`/`17`. One method error on the
way, said so it is not repeated: the first per-manifest probe of the
morning-style loop mis-split lines whose platform has no variant and
reported every amd64/arm64 child 404 — `docker pull` was the ground
truth that caught it, and the measurement was redone in Python. **A
finding beside the measurement**: the Forgejo project's mirror
`code.forgejo.org/forgejo/forgejo` serves `16.0.2` at codeberg's exact
index digest (`2fdfe28b…`) with both platform manifests 200 — the CP-59
bytes are still pullable, and a PyPI 0.1.3 stranger has a cure with no
second host (`docker pull` the mirror's tag, `docker tag` it as
codeberg's: the same digest, no provenance lie — the demo README's
recipe). **The route around, first** (Step 2): `--forgejo-image <ref>`
— an answer and a flag, default the pin, a re-run's default its record,
recorded in `run.json` with the image id, RepoDigests, platform and
`image_pulled_by_run`; the pull is the script's own step now, so a dead
tag is a refusal naming the flag, the mirror, `name@sha256:…` and the
out-of-band load (measured with `…:16.0.4`, a tag that does not exist).
**The re-pin** (Step 3): `codeberg.org/forgejo/forgejo:16.0.3` in the
script (with `FORGEJO_IMAGE_DIGEST`, checked after a pull — a re-cut tag
warns), the compose file and the estate README — by tag, not digest,
because the H200 only ever `docker load`s (no RepoDigests to match; a
digest reference would make compose pull on a firewalled host). The four
CP-59 measurements repeated on `16.0.3+gitea-1.22.0`, each unchanged:
the CLI's `--random-password` parsed by the create path; a token for the
owner under an admin token `401 auth method not allowed`, under basic
auth 201; anonymous `/api/v1/version` 403 and `ls-remote` 401 closed,
200 and the refs on a `--anonymous-read` instance of the same tag,
the credentialed read listing four refs; the healthz, owner, repos and
branches shapes as before. **Row 51** (Step 4): (a) `--polar-leg
host|container` (a container leg needs `--gateway-host` — the probe
measures this host — and warns on a loopback engine URL) plus the
documented keys, `estate.serving_base_url` among them; (b) a registry reference
pulled when absent, the wheel's default the published index; (c)
`pins_g1_check` on `checks.PINS_PATH` — the false warning gone at the
source; (d) the native-image line after the answer; (e) `--runs-dir`
and `PROG` in every generated header and refusal; (h) unscanned ports
for a container leg; (f)/(g) recorded — `cli.py` lines at 2,000/2,000,
row 37 not touched. **Proven** (Step 5, this arm64 Mac, the vllm-metal
engine on 8100): the image removed from the daemon, `bringup.py up`
from nothing 79.4 s with the pull inside Forgejo's 27.4 s; the re-run
25.1 s `reused: 8`; `--forgejo-image …:16.0.1` (absent → pulled) under
`--runs-dir` 60.1 s, `forgejo version 16.0.1` in the container, the
record saying so; one episode accepted in 24.6 s, the trace holding no
secret value and a userinfo-free `clone_url`. The demo legs are in the
report (a PyPI 0.1.3 clone with the mirror recipe; the same clone on
this commit's library, the default pulling by itself). **Frozen-side,
recorded**: `estate/forgejo/down.sh:18` still names `16.0.2` for its
root-owned wipe helper; `tests/fixtures/golden-mac/MANIFEST.md` is
historical; the H200's live instance keeps its local 16.0.2 until
16.0.3 is `skopeo copy`'d there (the compose comment names the order).
Rule-9 scan: 69 lines by the DoD's grep over `docs/` on disk (38 in the
tracked register — VERDICT 26, this file 12 — and 31 in the untracked
record: the prompts and reports name the token; rows 51 and 52 carry
their new tokens on their existing lines; CP-62's prompt and report are
the +2 over CP-61's 66, the third the [CP-61] paragraph's own mention —
this one spells the token without its colon);
fired — 52 (closed), 51 (the wheel half taken, re-tokened on 0.1.4 for
the ride, (f)/(g) on the `cli.py` allowance with 37); 37 not fired
(annotated). Push: this repo's `main` and the demo's at this CP's
commits — the report carries the hashes and the CI run. Tally unchanged:
**21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-63] Release 0.1.4, and CLAUDE.md — wishlist 51's wheel half DONE
(the park fired; re-tokened on the `cli.py` allowance), row 52 annotated
(published). Touched here: the three version literals (`pyproject.toml`,
`gsj_rollout/__init__.py`, `tests/test_scaffold.py` — 0.1.3 → 0.1.4),
`CLAUDE.md` (the repair below), `README.md`,
`docs/guide/{README,trainer-guide}.md` (the three current-state 0.1.3
literals), `docs/VERDICT.md` (rows 51/52), this §7; the demo (floors to
`>=0.1.4`, the retired pre-guard, the README mirror recipe as history).
NOT touched: `gsj_rollout/` source (`wc -l` 2,000/2,000 — the version
literal replaces a line), `vendor/`, `estate/`, `pins/`, `tests/` beyond
the version assertion, `.github/` (the CI labels did not move — 164/67/107
stand since CP-60), the examples repo — its bare `README.md:5` "PyPI
0.1.2" stays open for its next sitting, two releases stale now.**
**CLAUDE.md, first** — four checkpoints stale and injected into every
session (the CP-39 failure at a shorter interval); every claim verified
against the tree, not the prompt's list, by a ten-agent sweep: the
version 0.1.2 → 0.1.4 with the wheel's real contents (18 entries — the
G2 container capture and `bringup.py` were missing from the clause); the
census "Standing at CP-39: 1,999/2,000, headroom 1" → CP-62's
2,000/2,000, headroom 0 (at budget since CP-56), the law's "stays under
2,000 lines" reworded to "stays within its 2,000-line budget" with the
census named (`wc -l gsj_rollout/*.py`) and the exclusion restated as
all of `estate/` (the three-component enumeration under-described it by
~2,200 Python lines); the suite counts 161/58/89 → 164/67/107 (root 9
modules stands); the layout tree gains `estate/bringup.py` and
`estate/runs/`, `estate.sh`'s verb list gains `bringup`, `pins/` gains
`container/`, ADRs 0001–0026 → 0001–0027; the demo register F-54–F-69 /
next F-70 → F-54–F-78 / next F-79 (the examples' F-01–F-53 verified
unchanged); the one-commit workflow sentence now names the release CP's
two-commit shape (CP-34/CP-60, applied again here); "each verb execs an
existing script" → "… or compose in place" (`mcp-up`/`mcp-down` run
compose directly). Verified true and left alone: POLAR_SHA
(f0e8343a…/stable/3 patches), `checks.py` 528, staging 163, the
predecessor, untracking and docs-shelf claims, the report template.
Kept curated on purpose: the tree still omits `LICENSE`, `.github/` and
`docs/README.md`. **What 0.1.4 ships** — no new force-includes; the
content of the already-shipped `bringup.py` (CP-62: the 16.0.3 re-pin,
`--forgejo-image`, `--polar-leg`, `--runs-dir`, the registry
pull-when-absent, `pins_g1_check` on `checks.PINS_PATH`, the `PROG`
strings; `ingest_corpus.py` untouched by CP-62). Proven on the built
artifact before the push: 18 entries, the nine CP-19 exclusions and
`estate/` absent, `twine check` PASSED, and from a scratch-venv install
the packaged `FORGEJO_IMAGE` reads `codeberg.org/forgejo/forgejo:16.0.3`
(digest `7c4e1db4…` and the mirror constant carried) — six proof checks
green locally. Rule-9 scan at this commit: 70 lines by the DoD's grep
over `docs/` on disk (38 tracked register — VERDICT 26, this file 12 —
and 32 untracked; this paragraph spells the token without its colon);
fired — 51 (the wheel half, as above; its 0.1.4 token was the register's
last, row 52's being closed history). **The record** — push `b4541ab` →
CI run **33336280250**: root suite (164) green · corpus suite (67) green
· mcp-service suite (107) green · wheel + packaged-pins install proof
green — no red job; row 26 did not fire. Rehearsal (`workflow_dispatch`
at `b4541ab`) → **33336284589**: build green (`twine check` PASSED, the
18 names under the assertions) · TestPyPI green · PyPI **skipped** by
the tag gate. **TestPyPI proof** (a scratch venv outside every repo,
`==0.1.4` with the extra-index for deps): six checks green — the CP-09′
body validates to `[]`, both pins sets present, the G2 capture's sha
`f56e8a6e…` ∈ `system_prompt_hash`, `python -m gsj_rollout.ingest_corpus
validate` → PASS (12/12), `gsj_rollout.bringup` imports on the wheel
layout (`CHECKOUT False`, the packaged `INGEST`, `RUNS` under cwd, the
three verbs), and the packaged `FORGEJO_IMAGE` reads
`codeberg.org/forgejo/forgejo:16.0.3`. Tag `v0.1.4` at `b4541ab` → run
**33336519222**: tag-matches-version, build green · TestPyPI green ·
**PyPI green**. **PyPI proof** (a fresh venv, no index flags): 0.1.3 on
attempt 1 (~20 s of index lag — and one method error said so it is not
repeated: the first version check ran with the checkout as cwd, where
`import gsj_rollout` binds to the source tree and reported 0.1.4 while
pip had fetched 0.1.3; re-measured from a neutral cwd), **0.1.4 on
attempt 2**; `pip show -f` lists all four ride-alongs; the same six
checks green. **The demo, from PyPI — the release's claim measured**: a
fresh clone of `ea048d8`, `pip install 'gsj-harness-rollout-server>=0.1.4'
pyarrow` from PyPI (4.3 s, no index flags) → 0.1.4, the three config
values, the daemon holding **no 16.x Forgejo image**: `validate` PASS;
`./bootstrap.py up` with defaults exit 0 in **80.9 s** wall (the
bring-up 73.0 s; the Forgejo phase 50.0 s with the pull its own step —
`…16.0.3 is absent on this daemon — pulling it` → `pulled; sign-in ON`)
— **no mirror step**; `pins — every skill card (1) is in the approved
set at …/work/estate/pins.gsj.json (GSJ_PINS_PATH)` (no false G1
warning, its correction line retired), no Polar port scan (`--gateway-host
(not probed)`, gateway `http://polar-gateway:8200`); the README
one-liner episode collected 1/1 in **15.4 s**, accepted
(`case_orchard@t2`, turns 1, `stop`); `down` clean, data under `work/`.
Push: this repo `main` at the record commit (`b4541ab` beneath it, tag
`v0.1.4` at `b4541ab`); the demo `main` at `ea048d8` (a from-GitHub
clone of it validated — PASS). What a stranger gets now: `pip install`,
clone, three values, `./bootstrap.py up` — the pull, the flag, the named
pins, no recipe.**

**[CP-64] The H200's Forgejo, and the harness image — no row moves in the tally; wishlist 40 CLOSED (the harness half published, pins-walk-verified), row 2 re-measured on the box under the new image, A-28 annotated (multi-arch holds for all three images). Touched here: `estate/forgejo/docker-compose.yml` (the comment: the re-pin applied at CP-64), `estate/forgejo/down.sh:18` (the wipe helper's 16.0.2 → 16.0.3 — CP-62's recorded residue, taken under this CP's `estate/forgejo/` lift), `estate/README.md` (the Forgejo row), `docs/VERDICT.md` (rows 40/52), this file (A-28, row 2, this paragraph). NOT touched: `gsj_rollout/` (`wc -l` 2,000/2,000), `vendor/`, `estate/` beyond forgejo and the README, `estate/corpus/staging/`, `pins/` (Step 4 held the pins — the re-derivation clause never fired), `tests/`, `.github/` — the DoD diff on the frozen list EMPTY; the root suite 164.** **The Forgejo re-pin, on the box, in the compose comment's order**: 16.0.3 `skopeo copy`'d as uid 1000 and loaded (amd64 id `f02d6cf9…` — the registry's amd64 child config digest, predicted before the load and matched), `estate.sh down` (the bind-mounted `forgejo-data` intact before and after, 8.1 M), the checkout pulled `96b309c` → `4c2d808` (CP-62 and CP-63 arrived together), `up` — Forgejo started on its migrated data, no refusal, the admin token STILL VALID across the migration (`existing token still valid` from `up.sh`'s own probe). Measured there and then: `{"version":"16.0.3+gitea-1.22.0"}`, healthz 200, the four repos with all 16 deterministic branch SHAs (case_0001 `main 29515d3dfc` — CP-59's build values), anonymous `/api/v1/version` 403 and `info/refs` 401 with the read token's 200 and four refs (row 2's cell), and the CP-59 API measurements repeated on the box's own instance: `POST /users/gsj-staging/tokens` under an admin token 401 `auth method not allowed`, under basic auth 201 (the test token deleted, 204), the `/api/v1/user` and `/users/{owner}` shapes, the past-the-end repos page `[]`. **The harness image — Step 3's finding first, then the build it authorized**: the recipe is READABLE and COMPLETE at the archived predecessor (`sandbox/` byte-identical at v0.8.0; build context `sandbox/` itself, three allowlisted pin files; ADR-0041/0043 are sections of its `DECISIONS.md` — this repo's record never named ADR-0043, only "the archived predecessor's sandbox/"); every pinned input still obtainable (both npm pins integrity-equal to the committed lockfile, `mcp==2.0.0` on PyPI, the node base tag last re-cut 2025-06-11, BEFORE the 2026-08-06 original build); nothing on the box can rebuild it (`~/gsj-envloader` there is a dirty CP-22 checkout, no `sandbox/`). Rebuilt both platforms from the recipe on this Mac: the amd64 rebuild's `/opt/pi` tree byte-identical to the published image (a fully layer-cached build — this workstation still holds the predecessor-era layers — so the honest fresh-derivation proof is the arm64 build: of 41,052 files it differs ONLY in the four `@mariozechner/clipboard-*` platform natives, the materialized `.package-lock.json` naming them, and newer `/opt/mcp-venv` transitives, which sit outside the remote-MCP episode path). One method error, said so it is not repeated: the first amd64 "rebuild" was read as a from-scratch re-derivation until the build log's 8× CACHED said otherwise. **Proven by the pins, one episode per platform**: on the H200 through the amd64 rebuild (`sk-polar-c2b7498c…` — G2 `f56e8a6e…` ∈ approved, G3 `a7a7956b…` ∈ approved, `run_trace_checks` `[]`, `finish_reason: stop`, docker events tying the session container to the rebuild tag, the three estate tokens 0 occurrences; the engine on GPU 3 at `GSJ_VLLM_GPU_FRAC=0.078` — the crowded-card cure, 12.9 G free) and on this arm64 Mac through the arm64 build (`sk-polar-99512d4d…`, same hashes, findings `[]`, a `bringup.py` estate). G2 and G3 did NOT move; `pins/` untouched. **Published per CP-61's method** — no fresh amd64 bytes: `buildx imagetools create` composed the same tag from the EXISTING measured amd64 child `864dc885…` (byte-unchanged, so the H200's frozen load `f7a6d63a…` and every prior trace's provenance stand) plus the fresh arm64 `1dd08d75…` (`pi0.83.0-3-arm64` beside it); new index `1fc083d4…`. Verified anonymously: the credential-less manifest fetch lists both platforms with the amd64 child unchanged; after `docker logout`, `docker pull` with no `--platform` on this arm64 daemon — F-54's exact failing step — pulled native arm64, and `--platform linux/amd64` resolved; the login restored after. **A dated correction (CP-63 next (f))**: the [CP-63] paragraph's and `b4541ab`'s "four checkpoints stale" headline undercounts — the CLAUDE.md drift dated to CP-50 (the ADR range) and CP-56 (the census), its last repair being CP-52; recorded 2026-08-31, the facts around the headline unchanged. Rule-9 scan: 73 lines by the DoD's grep over `docs/` on disk (this paragraph spells the token without its colon); fired — 40 (the harness republish happened HERE: closed), A-28's both tokens (the same event: annotated, re-tokened on the release rebuild duty); rows 22 (no production bring-up this CP), 47 (no mcp cut), 51 (no `cli.py` allowance) did not fire; row 26 per the push's run in the report. Push: this repo's `main` at this CP's commit — the report carries the hash and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-65] The cli.py allowance — rows 51 (f)/(g) and 37 CLOSED under ADR-0028; the size law re-set to the landed size, 2,016, and machine-checked; row 53 NEW (the untracked-lift echoes). Touched here: `gsj_rollout/cli.py` (241 → 257 — the CP's only source change), `tests/test_cli.py` (+5 tests, the two install-shape tests re-pinned hermetic (`which → None`), the pipe test's subprocess PATH pinned empty, the 500-path counter-assert; root suite 164 → 169), `docs/CHARTER.md` (§1, §3 preamble + [CP-65], §8 rule 2, §9, this paragraph), `docs/VERDICT.md` (rows 37, 51, 53), `docs/guide/{README,how-it-works}.md` (the 2,000 echoes), `CLAUDE.md` (law 2's echo — the one edit outside the freeze-lift, ADR-0012's own echo duty, declared in the report). NOT touched: `checks.py` (528/528, the ADR-0021 tripwire green), every other `gsj_rollout/` module, `vendor/`, `estate/`, `pins/`, `.github/`, `README.md`, the consumer repos — the DoD diff on the frozen list EMPTY; the tracked 2,000 echoes OUTSIDE the lift (`README.md:6`, `.github/workflows/ci.yml:27`) are row 53's, parked with a token instead of fixed out-of-lift. **Priced at the file, then re-priced after the CP's own adversarial review** (six lenses, two refuters per finding, 13 confirmed — every one closed in-CP): (f) **+2** — CP-62's "in-place, no line" priced an UNCONDITIONAL string edit, which would put 409 advice on every exit-3 transport error against the CP-27 message standard; the honest conditional (`exc.response.status_code == 409`) needs its own binding, the hint prints ONLY on a 409 and lands on the `gsj-rollout:`-prefixed line BEFORE `str(exc)` (httpx's status str is two lines; a cure after its MDN link is a cure nobody greps), the 500 path asserted hint-free. (g) **+7** — `serve` renders to a string and the guard NEVER RAISES: a bytes compare under EAFP (an undecodable, unreadable, or mid-read-vanished file counts as different and re-renders — the review reproduced the naive text-read dying on non-UTF-8 where pre-CP-65 code overwrote and proceeded), byte-identical content left untouched (a receiver restart is a no-op on the shared file: same inode, same mtime), a real re-render lands via a PID-UNIQUE tmp + `os.replace` (the review demonstrated two concurrent serves cross-truncating a shared fixed `.tmp` into a 0-byte topology — the exact wound the row names), no residue. 37 **+7** — `shutil.which("polar")` when the vendored venv binary is absent, taken ONLY when the found binary sits beside `sys.executable` (the co-installed estate-image shape, F-77: bare runnable pair, no PYTHONPATH, no `<checkout>`, no NOTE); a FOREIGN PATH polar falls through to the F-45/REVENDOR hints (the review demonstrated a stub polar hijacking the printout and suppressing the actionable hint); `import shutil` counted. Total **+16**. **The budget decision**: bank was unavailable (the lift confines it to `cli.py`, banked to pointer form since CP-33 — what remains is the register-cited F-21/F-20 and F-45 comments), closing 37 again would re-litigate its own fired reopen condition, and "take only what fits" takes nothing at headroom 0 — so the law moved, ADR-0021's way: **ADR-0028**, 2,016 exactly, zero headroom by design, `tests/test_cli.py::test_size_law_census_is_machine_checked` asserting the census as an equality in both directions (growth is a stop-and-justify on every push; a shrink lowers the law in the same change; the glob is `[!.]*.py` — `wc -l`'s shell universe, so an editor's dot-lockfile cannot desync the check from the law's own command). Census: 18 + 159 builder + 528 checks + 257 cli + 123 client + 414 config + 322 pi_harness + 195 receiver = **2,016**. **One citation moved, disclosed**: the examples register's `cli.py:43` (the F-21/F-20 comment) now sits at `cli.py:51` — insertions ABOVE it; the comment is byte-untouched and no cited line was banked (the CP-50 footnote clause covers the stale number). Each change carries a test that fails with it removed — the full-suite counter-proof: `git stash push -- gsj_rollout/cli.py` → `pytest tests/test_cli.py` **7 red** (the 5 new tests fail, and the two re-pinned shape tests error on the stashed file's missing `cli.shutil`) / restored → 23 pass, the root suite 169. Rule-9 scan (the token spelled colon-free here, per the CP-64 precedent): fired — **37** and **51** (both waiting-on a cli.py allowance — the allowance is ADR-0028; both closed); rows 22 (no production bring-up), 47 (no mcp cut) did not fire; row 26 per the push's run in the report. Push: this repo's `main` at this CP's commit — the report carries the hash and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.


**[CP-66] The consumer residue — no wishlist row moves (40 was already closed; its recorded residue is taken and annotated in place); both consumer registers brought current and F-54's arc closed consumer-side. Touched here: `docs/VERDICT.md` (row 40's [CP-66] postscript), `docs/guide/trainer-guide.md` (the wheel-contents alt text — the drift-confession clause out, the six crossings in), `docs/guide/img/wheel-contents.png` (re-rendered at 0.1.4 from the outside-the-repo deck: six crossings — the G2 capture and `bringup.py` join 0.1.2's four — lane header `0.1.4 · py3-none-any · 18 entries`, never-ships now "the rest of estate/"), `docs/guide/img/two-roles.png` (the same deck visit's one other SHIPPED 0.1.2 residue: the pip tile now `wheel-only 0.1.4` — a named extent drift, same class as the mandate), this file (this paragraph). NOT touched: `gsj_rollout/` (2,016/2,016), `vendor/`, `estate/`, `pins/`, `tests/`, `.github/` — the DoD diff on the frozen list EMPTY; the root suite 169.** **The examples repo** (its own CP-66 commit): the sweep found fourteen drifted current-state claims, all fixed — `README.md:5` "PyPI 0.1.2" → 0.1.4 (CP-60's flag, three releases stale), the FINDINGS trailer F-54–F-69 / next-F-70 → F-54–F-78 / next-F-79 (and the README's range echo), seven "0.1.2 as of library CP-34" parentheticals (README, RUNBOOK ×2, install.sh, all three requirements headers) → "0.1.4 as of library CP-63", the RUNBOOK's library-suite counts 161/58/89 → 169/67/107 (the vendored-Polar 175/3 stands — A-8's CP-22 re-measurement), its dist/-pair "today" example reworked dated-historical (the checkout's `dist/` holds one wheel, 0.1.4), and slime_bridge's "# 14 tests" → 19 (measured: 19 passed, 0.20 s). Classified and left, CP-49's footnote clause: the bridge ADRs' `staging/serving/` citations (that repo's CP-50 commit says they keep their historical citations), every ">=0.1.x" floor line (they resolve, not lie), the pins README, `config.yaml`'s harness tag — and no wheel-entry-count or image-platform claim exists anywhere in that repo. **The demo repo** (its own CP-66 commit): row 40's residue executed — `ensure_image` loses `amd64_only` and the `--platform linux/amd64` fallback, and `daemon_arch()` + `import platform` go with it (the fallback was their only caller); the die() advisory tail ("a `no matching manifest` error would mean the registry lost this image's variant for your platform — report it") is now unconditional, so the one scenario the dead cure could still have caught — a registry serving the index but not a child, F-78's own shape at codeberg — now reports loudly instead of silently emulating, which is the better behaviour and the reason retirement beats repurposing; the README's Platform fact 1 rewritten — all four images native, `gsj-pi-harness` two-platform since CP-64, the refusal-then-explicit-pull story kept as history "for anyone reading an old trace" (CP-36's measurement stays; F-54's arc closes) — and the quickstart's ARM line follows; FINDINGS: the header and F-54's status cell record the sandbox half CLOSED at CP-64 and the cure retired, F-74's cell records 51 (d) cured at CP-62 and row 51 closed in full at CP-65, F-77's cell records wishlist 37 re-closed at CP-65 (rides the next release — 0.1.4 predates it), F-78's expired "until then" tail reworked (0.1.4 shipped at CP-63; the mirror recipe is history). The timings bullet stays byte-untouched — anchored to the CP-61 run. **Measured before claimed**: a fresh venv on PyPI's own 0.1.4 wheel (the demo REFUSES a source-checkout library — the stranger shape is the only shape), the local harness image removed first so the pull path had to fire, then `./bootstrap.py up` on this arm64 daemon — the plain pull with no `--platform` and no "arm64 —" line anywhere in the log resolved `pi0.83.0-3` native arm64 (id `1fc083d4…`, the CP-64 index), the estate stood in 40.0 s, `down` clean after. **The deck** (outside every repo; not a git repo — no push exists for it): the wheel-contents slide redrawn, and the visit's in-deck residue fixed — install-paths' pip tile and home's wheel tile 0.1.2 → 0.1.4, release-gate's "five must-ship paths" → seven (CP-60's assertion tuple), repo-map's subs 1,999 lines / 161 tests → 2,016 / 169; repo-map's `spike/` tile is PREMATURE, not wrong — `spike/` is still on disk, no `spike-cp06` tag exists, the off-tree proposal never ran, and repo-map renders into nothing today. Rule-9 scan (the token spelled colon-free here, the CP-64 precedent): 74 lines by the DoD's grep over `docs/` on disk; fired — NONE (row 40 closed at CP-64 — taking its recorded residue is an annotation, not a token event; rows 22, 47, 50, 53 wait on events this CP is not; row 26 per the push's run in the report). Push: all three repos' `main` at their CP-66 commits — the report carries the hashes and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-67] Release 0.1.5 — CP-65's three `cli.py` fixes reach the wire; wishlist 53 CLOSED (all echoes moved, four of them beyond the row's named two). What ships: the same 18 entries — no packaging change; what moves is `cli.py`'s content, checkout-only since CP-65: the 409 hint naming `--task-id` (51 f), the topology render guard (51 g — bytes-compare under EAFP, pid-unique tmp + `os.replace`), the third-shape serve printout (37 — `polar` beside `sys.executable`). All three read from the BUILT artifact before the tag: a scratch-venv install of the 0.1.5 wheel carries them, its `cli.py` byte-identical to HEAD's at 257 lines. Touched here: `pyproject.toml`/`gsj_rollout/__init__.py`/`tests/test_scaffold.py` (0.1.4 → 0.1.5 — the version literal is `gsj_rollout/`'s ONLY change; census 2,016/2,016, ADR-0028's equality green before and after), `README.md` (`:6` "2,000-line shell" → 2,016 — verified `wc -l` first; `:43`'s install literal → 0.1.5; `:96` "(164 tests" → 169 — the CP-67 sweep's find), `.github/workflows/ci.yml` (the labels and the comments only: `:4`'s "(164)" and the root job's display name → 169, verified by collection; `:27`'s "2,000-line budget" → 2,016), `docs/README.md:3` (1,999 → 2,016 — a pre-2,000-era echo that escaped the CP-56 AND CP-65 sweeps), `docs/guide/README.md:23` + `docs/guide/trainer-guide.md:9` (the wheel-version literals → 0.1.5), `CLAUDE.md` (`:5`/`:51`'s 0.1.4 tokens → 0.1.5 — outside the lift, taken as the CP-63/CP-65 precedents' declared excursion: the process file must not misstate the published version), `docs/VERDICT.md` (row 53's [CP-67] closure), this file. NOT touched: `gsj_rollout/` source beyond the version literal (the DoD diff on the frozen list EMPTY, 0 lines), `vendor/`, `estate/`, `pins/`, `tests/fixtures/`, both consumer repos — the demo's floor stays `>=0.1.4` by the stated default (a floor 0.1.5 satisfies; nothing in 0.1.5 is required by the demo, so a bump would be a claim without a need), and the examples repo's `README.md:5` "PyPI 0.1.4" (unanchored, CP-66's edit) goes stale at publication — that repo is not lifted; recorded for its next sitting, the CP-63 pattern. The version sweep, refereed (four sweepers, 220 hits classified across the three repos): the library's six current-state literals moved (the addresses above — CP-63 §2's exact list plus CLAUDE.md's pair), every "since 0.1.x"/"[CP-NN]"/"as of" anchor stays dated-historical, the trainer-guide alt text stays (the PNG is genuinely rendered at 0.1.4 — its self-dating convention since CP-60), the demo's 45 hits all stand (floors resolve, POLAR_IMAGE tags are true of the published image — A-28). Rule-9 scan (the token spelled colon-free here, the CP-64 precedent): fired — **53** (its token names "the next release CP", which this is; closed above); rows 22, 47, 50 wait on events this CP is not; row 26 per the push's runs in the report. Push: this repo's `main` at the release commit, tag `v0.1.5` on it — the record commit beneath this paragraph carries the run ids, colours and both install proofs. **The record (the second commit — the CP-34/CP-60/CP-63 shape)**: release commit `a769771`, tag `v0.1.5` at it. Push `a769771` → CI run **33390791817**: root suite (169) green — the relabelled job's first run — · corpus suite (67) green · mcp-service suite (107) green · wheel + packaged-pins install proof green; no red job, row 26 did not fire. Rehearsal (`workflow_dispatch` at `a769771`) → **33390819656**: build green · TestPyPI green · PyPI **skipped** (tag gate). Tag `v0.1.5` → **33391335001**: tag-matches-version, build green · TestPyPI green · **PyPI green**. **Both install proofs, seven checks each** (scratch venvs under the session scratchpad, outside every repo — the CP-63 cwd trap; the proof script asserts its own cwd is no repo): TestPyPI (`==0.1.5` + the extra-index for deps) 0.1.5 on attempt 1; PyPI (no index flags) 0.1.5 on attempt 3, ~40 s lag — CP-63's pattern, and `pip show -f` lists `bringup.py`, `ingest_corpus.py`, both pins sets, the G2 capture. The checks, green from both indexes: `[1]` the CP-09′ body (`sk-polar-44620742…`) validates to `[]` from the packaged pins; `[2]` both pins sets present; `[3]` the G2 capture's sha `f56e8a6e…` ∈ `pins.system_prompt_hash`; `[4]` `python -m gsj_rollout.ingest_corpus validate --corpus …/estate/corpus/staging` → PASS (12/12); `[5]` `gsj_rollout.bringup` on the wheel layout — `CHECKOUT False`, `INGEST` the packaged sibling, `RUNS` under cwd, the three verbs; `[6]` `FORGEJO_IMAGE == …:16.0.3`; `[7]` **the CP-65 fixes exercised on the packaged artifact** — `gsj-rollout serve --render-only` from the installed wheel with no `polar` on PATH prints the F-45 wheel NOTE with `<checkout>` placeholders, with a `polar` beside `sys.executable` prints the bare runnable pair (no PYTHONPATH, no NOTE — row 37's third shape, live from PyPI), and between the two renders 51 (g)'s no-op path held: byte-identical topology untouched (same mtime_ns + inode), no tmp residue. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-68] The spike shelved at its tag — ADR-0027's residual closed (":1741's `spike/` still sits at the root", today at `:1771`); no wishlist row moves (the residual lived in this file, never in the wishlist).** `spike/` — 25 files, 673,492 B, tree `2082a24f765c8c1839f6f2ec1aec4f1f395c4509`, byte-unchanged since CP-54 (`220da20`) — left `main` and is frozen at annotated tag `spike-cp06` on `a769771` (CP-67, the last commit containing it; the proposal was drafted against `96b309ce` and the tree id is the predicate that carried — re-certified equal today), pushed and proven resolving BEFORE any doc edit landed (contents API at the tag → 13 entries) and protected the same sitting: repository ruleset `21927030` (`refs/tags/spike-*`, deletion + update, zero bypass actors), verified empirically — a deletion push came back `GH013` rejected. `git archive spike-cp06 spike | shasum -a 256` = `6380b8af77506ebe9e72b3704bb580234dfdad2539dabeaa8064fbce48051fbb` is ADR-0029's byte-level freeze predicate; restore is `git checkout spike-cp06 -- spike` (rehearsed: 25 files back, tree id equal). **0 B reclaimed by design** — every blob stays reachable through the four spike-bearing commits (~103 KB packed), and main is NEVER rewritten: every permalink depends on `a769771` staying reachable. Top level 14 → 13 entries by `git ls-tree`. The 31-file commit: 25 deletions + 6 edits — `README.md:96` (the row split to `tests/` alone, the forwarding sentence with tag + SHA), `CLAUDE.md` (the tree line out, `estate/` the last entry, the tag pointer under the tree), `docs/checks-spec.md:891/:900` (the captures and `p1_verdict.py` re-pointed to the tag with the SHA beside — and the half-dead half made honest: `docs/polar/pi/` named as private record, untracked since CP-48, which the spec had cited as if tracked), `.gitignore:12-16` (the spike scratch block out; the estate comment is the successor), `docs/README.md` (the off-the-tree shelf row after `polar/`), this file. **The CP-68 amendment to the proposal's default**: the six §4/register citations — the numbering note, A-2, A-12, A-15, rows 11/31 — each annotated *(at `spike-cp06`)* rather than left stale; three are live assumption rows a reader may follow, and the annotation is the register's own convention. Kept deliberately: `release.yml`'s `spike/` wheel-ban token (a tripwire against the directory returning) with its four mirrors — `docs/guide/README.md:52`, `docs/guide/trainer-guide.md:24`, the alt text, `wheel-contents.png` — one coupled future decision, named in ADR-0029; `pi_harness.py:3`'s wheel-shipped docstring and `pyproject.toml:123`'s sdist comment resolve at the tag. Disk-only scratch preserved FIRST: `spike/rollout_results/` (6 raw Polar outputs, in no git history — `wire_diff.py`'s bodies) copied `diff -r`-identical to `docs/polar/spike-scratch/` (private record, ignored); `node_modules` (383 MB)/`workspace`/`__pycache__` deleted, regenerable by `npm ci` from the tagged lockfile. The deck's repo-map `spike/` tile (outside every repo — CP-66 flagged it going wrong when this landed) re-labelled off-tree in the same sitting; repo-map still renders into nothing. Census note: the proposal's 31-hits-in-11-files was measured at CP-58; today's tree gave 24 in 10 before the edits, every hit dispositioned. Root suite 169; `gsj_rollout/` not opened (2,016/2,016). Push: the tag first, then `main`; the report carries the CI run id and colours. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-69] The verl repo, minimal and running — the examples repo becomes one bridge + one loop, the slime path frozen at its tag, and the engine-ownership question answered from verl's source.** The tag-and-remove mechanism's second occupant (CP-68's shape): annotated tag `slime-cp17` on `73e63f0e` (the last examples-repo commit containing `slime_bridge/`; tagged tree `slime-cp17:slime_bridge` = `5f28d0f5`), pushed and resolving BEFORE any edit landed, protected the same sitting by examples-repo ruleset `21930459` (`refs/tags/slime-*`, deletion + update, zero bypass actors); then `git rm -r slime_bridge` (18 files) with three moved to main first because the verl path uses them — `reward_cited_pages.py` + its 5 tests → `verl_bridge/`, `cp17_loop/probe_sync.py` → `verl_bridge/probe_sync.py` (model/URL parameterized, stats returned; wire mechanism verbatim). **The ownership finding (examples F-79, the Step-2 answer, read at verl `1ae94559` — a fresh clone, cited to file:line): verl cannot push weights into an engine it did not spawn** — every in-place path is a Ray `collective_rpc` into a verl-launched `AsyncLLM` in a verl-named Ray actor whose workers carry verl's injected `worker_extension_cls`, over node-local CUDA-IPC/ZMQ; "standalone" mode still means verl creates the resource pool and launches the server; no reload-from-checkpoint HTTP endpoint exists anywhere at that SHA; middle paths are (A) surrender serving to verl's standalone replica (a real OpenAI endpoint verl updates in place — the engine then lives and dies with the trainer's Ray job, the ownership inversion this estate refuses) or (B) a LoRA-only `/v1/load_lora_adapter` shim verl does not ship. Restart sync is the boundary's honest shape, so **the loop scripts it**: `example_project/train_loop.py` (collect → grade → batch → train → sync → collect → train, N steps, one persisting worker, everything estate-specific a flag; refusals in words per CP-27 — no sync-cmd on multi-step, zero-reward batch before GPU spend, noisy probe floor, zero-movement probe = "engine serves the OLD weights", failed sync-cmd = "state unknown, restore by hand") with `sync_engine_local.sh` as the H200's `--sync-cmd` (serve-updated's two remote bodies, run on the serving host — F-29's other side) and the F-08 guard DEFAULT-ON (`norm_adv_by_std=False`, Dr.GRPO — the comment cites F-09's structural immunity AND CP-21's +10.39/2.32-clipped measurement; opting back in is an explicit warning flag). **The two-step proof ran on the H200 (off-mode, row 0, 2026-08-31)**: step 1 — 64 attempts → 0 rewarded → REFUSED at the grade gate (the guard working), extended loudly to +128 into the same group → 191/192 qualified (1 LP6 client-reject = the receiver's own quarantine verdict, law 6's legs agreeing at 319 archived + 1 quarantined = 320), reward 1/191, batch 191×(P 2952/R 25170), replay 0.013781 vs floor 0.008, Dr.GRPO advantages −0.0052/+0.9948, pg_loss 7.36e-05, grad_norm 0.0332 unclipped; sync 1 = noise floor 0.000000 (0/5976) then mean|Δ| 0.040133, 5793/5976 moved, 165 s downtime. Step 2 (post-sync policy, worker state continued) — 128/128 qualified, **reward 78/128 (mean 0.6094) vs step 1's 1/191**: near-verbatim format-copying of the seed trajectory's deliverable (`Parties: [page:1] …` in a file literally named `<task_id>.md` — the bank's skill card declares the placeholder unrendered; declared==written, so grading held), response width collapsed 25,170 → 8,192 — CP-17's mode-collapse onset measured at scale, reported as measured, not as success; recompute 0.004108 BELOW the floor = the loop's cross-check re-verifying sync 1 end-to-end; step-2 pg_loss 0.1969, grad_norm 0.4710 unclipped; sync 2 = 0.074026, 5849/5976 moved, 185 s. Library-side: five citations re-pointed under the docs/** lift (trainer-guide.md:296 reworked, guide/README.md:69, this file :536/:637, VERDICT :548/:613 — *(at `slime-cp17` since the examples repo's CP-69)*, the CP-68 register convention); **residual: `estate/README.md:105`** still cites `slime_bridge/cp17_loop/train_one_step.sh` as "the recipe that ran" — the one live `cp17_loop` path in tracked files, outside this CP's freeze-lift; the next estate-lift CP re-points it (the examples README's forwarding pointer carries the reader meanwhile). F-03/F-05/F-06/F-07 stay as history, each annotated to the tag (none closes — frozen, not fixed); F-79 minted, next fresh id F-80. `gsj_rollout/` not opened (2,016/2,016); root suite 169; examples suites 26 + 5.


**[CP-71] The corpus contract, for a stranger who writes one — CP-70's five manifest findings taken (items 2, 5, 11, 12, 3 — the walkthrough's report never landed on this disk; the items are as the CP-71 prompt states them), ADR-0030; wishlist 54–56 NEW.** The through-line closed: `corpus.yaml` is now three fields — `name`, `owner`, `git:` — each commented in the contract with what it is, what it affects, and whether the author must change it; the three estate fields are deprecated with warnings naming the new source, **never a failure** (item 2). The migration shape is DEPRECATE, argued from measurement: the lock's sixteen SHAs are commit refs (content + `git:` identity — no config field reaches them), nothing anywhere hashes `corpus.yaml`'s own bytes, the frozen `cli.py` requires the `sandbox_image` column, and the demo's `bootstrap.py` (pinned to released wheels) dies on a manifest without it — a hard removal breaks every existing corpus at the next release for zero SHA benefit. **The operator's mid-CP ruling, applied in full: `sandbox_image` is IGNORED when present, not honored — a corpus is not bound to a runtime.** The rows take the estate's value (`--sandbox-image` on the pipeline, default = `config.py`'s `runtime.image` default; `bringup.py` answers it, records it in `run.json`, passes it to every phase and writes it into `rollout.yaml`'s `runtime.image`), so CP-24's row-vs-config guard is intact and now genuinely config-sourced; `forgejo.base_url`/`mcp.url_base` stay honored-when-present (the lock keeps the canonical URL), and a corpus without them takes `--base-url` (required for scaffold/verify/all, refusal names the flag and the tool that answers it) / `--mcp-url`. **The owner allowlist became a shape check** (item 5): Forgejo v16's own rule read from source (`modules/validation/helpers.go:96-126` positive/negative patterns, the 33-name reserved list at `models/user/user.go:639-684`, MaxSize(40)) restricted to dot-free names because `token_env_name` maps only `-`→`_`; the check covers `--owner-override` too — closing the bypass the audit found (`load_corpus` checked the YAML value only) — and each refusal names the violated clause, not the fact of failure; Forgejo 16.0.3 measured LIVE agreeing this CP (`POST /api/v1/admin/users`: 422 `[Username]: invalid username` for `double--dash`/`trailing-`/`has.dots-and--runs`, 422 `name is reserved [name: admin]`). `gsj-elsewhere` — the very name the allowlist refused — validates, and stood an estate. **Prompt ids are optional** (item 11): skill → `skill:<name>` (the value the contract always forced — generating it changes nothing observable), free → `free:<12 hex of sha256(text)>` (stable under reorder/insert, moved only by a text edit — the audit established `prompt_id` appears NOWHERE in `gsj_rollout/`, `--from-bank` selects by row number, and the one true consumer is the examples trainer's `row_uid`); explicit ids stay legal for stability across edits, per-timestep uniqueness unchanged, a generated-id collision says it was generated. **`scaffold` landed in `bringup.py`** (item 12): `scaffold --out <dir>` writes splits, one case, one timestep, one page, both prompt forms, a corpus.yaml with every field commented and the must-change ones marked, a skill card and an AGENTS.md whose own text explains what they are — and it reads NOTHING from the installed library (item 3 decided: no packaged G2 capture, no pins, so no editable-install refusal; the files state the pins consequence instead), self-checks `validate` before returning, and `up` on a directory with no corpus.yaml names `scaffold` in its refusal (the CP-59 refusal class). The contract gained **"Bringing your own corpus"** (CP-70 item 4): pins re-derivation named honestly (the library ships no one-command walk for a foreign corpus — the demo's `bootstrap.py` is the worked example, `GSJ_PINS_PATH` the seam), timestep construction named as upstream, the retrieval defaults named as synthetic-sized, and the bring-your-own path stated as NOT walked end to end. **Proven on this Mac (no GPU)**: the tracked staging tree through `up` in 51.4 s — validate 12/12 with the three deprecation warnings verbatim, 4/4 repos converged at the frozen SHAs, index fingerprint `ea063721…` (the H200 store's), bank sha `ae9e0bbd…` unchanged, verify PASS 30/30, tree clean afterwards EXCEPT a pre-existing lock `_comment` drift (the frozen lock predates the current `write_lock` wording — restored, not committed as a passing fixture edit; wishlist 56); a scaffolded corpus through `up` in 21.8 s under owner `my-owner` — verify PASS 7/7, 2 bank rows (`skill:example` + the generated `free:<hash>`), the pins phase honestly warning the example card quarantines until re-derivation. Suites: corpus 67 → 82 (the allowlist test flipped to the shape rule with 7 named-clause cases, deprecation/id-generation/ignored-image/scaffold suites new), root 169 (frozen `tests/` green — the `{up,status,down}` help assertion kept literally true by the subparser metavar `scaffold | {up,status,down}`, noted for CP-72's rename, which also inherits the name collision with the pipeline's own `scaffold` phase). The demo's generator template annotated (still writes the three fields — its wheels require them; wishlist 54 carries the drop). Out-of-lift residuals parked in wishlist 55 (`estate/README.md:79`, `estate/estate.sh:57`, `create_owner.sh:19` — the allowlist's prose echoes). Rule-9 scan (the token spelled colon-free here, the CP-64 precedent): fired — NONE (rows 22, 47, 50 wait on events this CP is not; 54–56 open tokened; row 26 per the push's run in the report). Push: this repo's `main` and the demo's `main` at their CP-71 commits — the report carries the hashes and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-72] One tool for the estate — the bring-up renamed (`estate/bringup.py` → `estate/estate.py`, packaged `gsj_rollout.bringup` → `gsj_rollout.estate`) and the pipeline's standalone entry points folded into it as verbs.** The reference count came first (CP-50's discipline: 7 finders + 2 adversarial verifiers over the four repos): **303 classified tracked rows — 140 must-edit, 108 historical-stays, 29 predecessor, 13 frozen-side, 6 outside-lift, 5 wheel-bytes, 2 untracked-record — plus ~430 aggregated record/generated lines**, and the explicit relative-climb sweep (`parents[`, `.parent`, `find_spec`) found what greps miss: `test_bringup_scaffold.py:14`'s `parents[2]/"bringup.py"` join (moved with the rename), the demo `bootstrap.py:151-152` wheel climb probing `find_spec("gsj_rollout.bringup")`, and — the verifier's catch, the CP-50 class again — **demo `bootstrap.py:749-750` parses the tool's stdout by the literal prefixes `== run <name> ==` and `next — `**, a cross-repo output contract no finder listed; CP-72 keeps both prefixes byte-identical (wishlist 59 carries the demo-side re-verify). The verb set, printed by `--help`: **scaffold · validate · up · ingest · status · down** (`update` is CP-70's item 10, does not exist, and is not named); `validate` and `ingest` run the pipeline's phases in-process (the `cmd_scaffold` pattern) with the pipeline's exit codes, and CP-71's `{up,status,down}` metavar workaround retires. **The deprecation**: `python -m gsj_rollout.ingest_corpus <verb>` (and the script path) keeps working and prints a NOTICE on stderr naming `python -m gsj_rollout.estate validate|ingest` (checkout: `estate/estate.py`) — suppressed via `GSJ_PIPELINE_DRIVER` when the estate tool is the caller — documented as removed no earlier than 0.1.7, never in 0.1.6 (the release that ships the replacement); `gsj_rollout.ingest_corpus` stays a packaged module, its force-include keys byte-identical. Proven: root 169, corpus 90 (88 + the two folded-verb tests), mcp-service untouched; the wheel builds at 18 entries with `gsj_rollout/estate.py` and imports from a scratch venv in both shapes (CHECKOUT False, INGEST the packaged sibling, RUNS under cwd); **a scaffolded corpus stood a full estate up on the Mac under the renamed tool** (scaffold → validate → up → ingest → status → down --wipe). Register: row 55 DONE (the estate/ lift took its three allowlist echoes), row 54 appended (the rename rides the same next release), rows **57** (`release.yml:103`'s frozen tuple still requires `gsj_rollout/bringup.py` — the release path hard-fails until the next `.github/` lift moves it; ci.yml's corpus label 67 vs 90 actual), **58** (README.md/CLAUDE.md/two PNGs echo the old name outside the lift — recorded, the CP-60 class), **59** (the demo repo deferred whole: every installable wheel ≤ 0.1.5 ships only `gsj_rollout.bringup`, so its rewrite rides the release + floor bump) all NEW. The examples repo needed nothing: its only executable reader invokes the pipeline's `taskbank` phase by script path (still the supported form — the notice lands on stderr, its parsed stdout clean), and the RUNBOOK's `python -m gsj_rollout.ingest_corpus validate` claim from the CP-72 prompt no longer exists in that tree (removed with the CP-69 slimming). ADR-0031.

**[CP-73] The bring-up's surface — CP-70's items 7, 9 and 10 (as the CP-73 prompt states them; CP-70's report never landed on this disk, the CP-71 posture): the tool now shows what it decides before it spends, and a changed corpus has a verb.** Item 9, one sentence grown into a classification: the inference-endpoint prompt now says the answer is NOT binding — written to `rollout.yaml`'s `estate.serving_base_url`, the probe records rather than refuses, changed by editing that file or re-running `up` — and the same honesty ran through the interactive: the served model is not binding (rollout.yaml's `estate.model`), the corpus path is not (`update` syncs edits), while the owner, the run name and the embedding identity say they BIND (the last in CP-57's specific way: refused against a built store until `--rebuild`), and the adopt URLs say they are recorded behind `--retarget`. Item 7: on every `--mcp create` run the effective retrieval config — embedding identity, chunk window, `respect_page_boundaries`, decisions params, search defaults — is printed BEFORE the index is built under it, each setting priced by what a later change costs (model: refusal until `--rebuild`; chunking/decisions: fingerprint components, a corpus-wide re-embed; search: serving-only, a config edit + restart); interactively a confirm fires only when an embed is about to be spent (cold store, `--rebuild`, changed window), under `-y`/`--answers` the block prints and never stops (proven both modes on the cp73 estate); `--mcp-config <yaml>` is the scripted half — operator sections (`embedding`/`chunking`/`search`/`decisions`) merged onto the generated config, estate sections (`source`/`auth`/`index`/`server`) refused by name (proven: a `source:` key refused; a `search.default_k: 8` + `batch_size: 64` file merged, reviewed, and did NOT re-embed — `index_reused=True`, the pricing's own claim). Item 10: **`update --name <run>`** — pure orchestration over phases the pipeline already had (`scaffold --only`, `taskbank`, `ingest`, `verify`; `ingest_corpus.py` untouched, the prompt's one conditional lift not needed) — diffs the tree against the RUN's lock, reports the plan (report-then-act; `--dry-run` kept for scripted runs since `-y` removes the pause), then pushes only the changed repos, rebuilds the corpus-wide bank, triggers ONE if-stale reindex and verifies. The five change kinds each proven separately on the standing cp73 estate, verify PASS after each, the run lock's SHAs moving only where the corpus moved: an edited page (one case's refs moved, bank byte-identical), a new timestep (one case, bank 12→13, the re-derived-branches attribution named structurally), a new case (the live find of the CP: a running service's `source.repos` is start-time only, so reindex alone cannot admit a case — first proven failing loudly at verify, then built: a created service's config is the run's own artifact, rewritten + `--force-recreate` + wait-ready, 5/5 embedded; an ADOPTED service refuses naming its operator's fix), an edited skill card (every case moves, the card attributed by live-vs-tree bytes through the Forgejo raw API, the pins consequence OUT LOUD twice — the G1/G2 quarantine warning and the post-verify approved-set check naming `summarize`), and the unchanged corpus (`nothing moved — nothing to do`, before any network). What it refuses, each proven live or hermetically: a changed `git:` identity (read off a recorded commit's author via the API, both identities named — a new corpus is not an update), out-of-band branch drift (a stray API commit on `case_0003` → refused naming `up --overwrite-repos`, CP-59's posture kept; the cure re-converged it), a removed case (verify would fail on the stray lock entry; the manual path named), a new case on an adopted service. Never `--rebuild`, never `--overwrite-repos`. The qemu segfault refusal (wishlist 49) fired on the first `up` — the amd64 local tag under emulation — and named its own fix; the estate stood on the published multi-arch index. Frozen-side collision, decided not worked around dishonestly: the root suite (not lifted) asserts the six-verb metavar substring-exactly, so `estate.py` pins the brace line while `--help` lists `update` with its own help line — row 60; the corpus-wide re-embed granularity is row 61. The pre-push adversarial review (the CP-59/65/71/72 practice: 5 finders → 28 findings → 2 refuters each, several executing their scenarios) confirmed 14 + 2 splits and landed ~20 fixes in-CP, the largest: the embed-spend confirm re-keyed on the FULL fingerprint-component set (a `--mcp-config` `decisions.seed` used to rebuild silently under a false "no embed now" line — re-proven live, the confirm now fires), a resumed update adopting a repo that already holds exactly this corpus's build (an interrupted update no longer bricks its own recovery into the drift refusal), the run's baseline lock SEEDED into the tree before acting (a fresh checkout of the corpus source used to push first and wedge at taskbank — the review reproduced it on the file rail; re-proven live: a lock-less fresh copy synced clean), a wrong `--corpus` refused by NAME (every scaffolded corpus shares the template git identity, so the identity check cannot discriminate — executed by a refuter: corpus B pushed over run A's estate silently; now a CP-27 refusal), a free-prompt TEXT edit under an explicit id caught against the run's bank copy (the one channel that moves neither SHAs nor prompt ids — the docs' "a prompt change" promise made true), `--mcp-config` per-key/per-type validation (a typo'd or mistyped key used to surface as a 30-minute unreachable-wait), attribution that never reads a failed fetch as absence (and skips cards when the reference repo itself is gone), and EOF at the two spending confirms now declining (a closed stdin is not consent). Suites: root 169, corpus 109 (90 + 19), mcp-service untouched. Register: rows 60, 61 NEW; row 57 confirmed still open (the release CP's first edit). ADR-0032.

**[CP-74] Release 0.1.6 — three checkpoints of estate work reach a consumer (CP-71's slimmed manifest and deprecations, CP-72's renamed tool with its folded verbs and the pipeline's deprecation notice, CP-73's `update`, config review and binding-prompt wording); the release path repaired first — wishlist 57 CLOSED, 58 CLOSED, 54's wheel half fired.** Row 57 was the first hunk: `release.yml`'s required tuple named `gsj_rollout/bringup.py`, which no wheel since CP-72 contains, so any tag or dispatch would have failed at the build job — the row moved to `gsj_rollout/estate.py`, the whole tuple verified against the built artifact (18 entries, seven required present, six banned prefixes + CP-19's nine names absent, no `bringup.py` alias, `twine check` PASSED), and the rehearsal dispatch is the run that proves it; `ci.yml`'s corpus label 67 → 109 by collection (169/109/107), nothing else in `.github/`. The version literal is `gsj_rollout/`'s only change (census 2,016/2,016, ADR-0028's equality green before and after; the packaged `gsj_rollout/*.py` byte-identical to HEAD except `__init__.py`'s one line, measured from the installed artifact). What ships is content, not packaging: the packaged `estate.py` (sha256-equal to the checkout's, 3,327 lines) carries `update`, `--mcp-config` and the config review; `python -m gsj_rollout.ingest_corpus validate` still works and prints its NOTICE on stderr naming `python -m gsj_rollout.estate validate|ingest`, 0.1.6 as the release it keeps working in and 0.1.7 as the earliest removal — nothing claims removal in this release (`pyproject.toml:97`, `corpus-contract.md:347`, the notice itself; silent under `GSJ_PIPELINE_DRIVER`). Row 54's wheel half, from the built artifact: `scaffold` writes the three-field `corpus.yaml` and `validate` passes it unmodified; with the three estate fields added it warns three times and passes. Touched here: `pyproject.toml`/`gsj_rollout/__init__.py`/`tests/test_scaffold.py` (0.1.5 → 0.1.6), `.github/workflows/release.yml` (the tuple and its comment) + `ci.yml` (the two corpus labels), `README.md` (`:43` → 0.1.6/`estate.py`; `:92`, `:94` enumerate `estate.py`; `:102` 26 → 32 ADRs; `:106` the Licence sentence), `CLAUDE.md` (`:5` the version, the wheel list and the F-register claim — F-79 was minted in the examples register at CP-69, next fresh id F-80; `:10`; `:51`; `:59` ADRs 0001–0032; `:73`/`:85` corpus 109; `:79` the `estate.py` tree line with its seven verbs; `:80`), `docs/README.md:35` (ADR-0027–0032), `docs/guide/README.md:23`, `docs/guide/trainer-guide.md` (`:9` 0.1.6; `:11` the alt text at 0.1.6; `:13`; `:20` the estate verb as the current validate form, the module's own entry 0.1.2–0.1.5 and deprecated; `:22` the `gsj_rollout/estate.py` row with the seven verbs and the 0.1.3–0.1.5 history), `docs/guide/server-guide.md` (`:172` seven of eight bank columns — `prompt_id`, a bank column since CP-24, rides unread; `:276`/`:279` the validate command is the estate verb, the pipeline's own entry 0.1.2–0.1.5 and deprecated), the four re-rendered PNGs (`wheel-contents`, `estate-bringup`, `two-roles`, `api-surface` — the diagrams dir was reachable, PowerPoint render), `docs/VERDICT.md` (rows 57, 58 closed; 54's wheel-half postscript), this file. NOT touched: `gsj_rollout/` source beyond the version literal (the DoD diff on the frozen list EMPTY), `vendor/`, `estate/`, `pins/`, `tests/` beyond the scaffold assertion, the examples repo — whose `README.md:5` "PyPI 0.1.5" (unanchored) and `RUNBOOK.md:476` "corpus 67" go stale at publication and are recorded for its next sitting (the CP-63/CP-67 pattern); `tests/test_wheel_pipeline.py:57`'s docstring ("must move at its next lift") becomes history at the next `tests/` lift. The sweep, refereed (eight finders — literals in every form incl. tuples, the old name, the two consumer repos, CLAUDE.md/README claims, guide stories and numbers — then two referee lenses per file group, 38 referees): 449 raw hits, 341 unique, 27 MOVE (all applied above), 3 OUT_OF_LIFT (the three recorded), 36 DEMO_AFTER_RELEASE (the demo commit's inventory), the rest dated-historical; the referees refuted four finder edits (the old-name range is 0.1.3–0.1.5, the pipeline entry's 0.1.2–0.1.5, `prompt_id`'s age, and the demo's `POLAR_IMAGE`/`polar.Dockerfile` `gsj0.1.3`, which names a real published image — A-28, unchanged since CP-63/CP-67) and upheld every class. Rule-9 scan: fired — **57**, **58** (closed above), **54** (its first event; the demo half after publication), **59** (its first event — the demo commit follows publication, Step 6). Push: this repo's `main` at the release commit, tag `v0.1.6` on it once CI is green — the record commit beneath this paragraph carries the run ids, the colours, both nine-check proofs and the demo's outcome. **The record (the second commit — the CP-34/CP-60/CP-63/CP-67 shape)**: release commit `31d51e1`, tag `v0.1.6` at it. Push `31d51e1` → CI run **33615657302**: root suite (169) green · corpus suite (109) green — the relabelled job's first run · mcp-service suite (107) green · wheel + packaged-pins install proof green; no red job, row 26 did not fire. Rehearsal (`workflow_dispatch` at `31d51e1`) → **33615689639**: build green — the repaired tuple visible in its log; the run that would have failed at the tuple on any tag since CP-72 · TestPyPI green · PyPI **skipped** (tag gate). Tag `v0.1.6` → **33616088475**: `tag v0.1.6 matches version 0.1.6`, build green · TestPyPI green · **PyPI green**. **Both install proofs, nine checks each** (scratch venvs under the session scratchpad, outside every repo; the proof script asserts its own cwd is no repo — the CP-63 cwd trap, mechanised): TestPyPI (`==0.1.6` + the extra-index for deps) 0.1.6 on attempt 1; PyPI (no index flags) 0.1.6 on attempt 2 (~25 s lag — CP-63/CP-67's pattern), and an unpinned `pip install gsj-harness-rollout-server` resolves 0.1.6; `pip show -f` lists `estate.py`, `ingest_corpus.py`, both pins sets, the G2 capture — no `bringup.py`. The checks, green from both indexes: `[1]` the CP-09′ body (`sk-polar-44620742…`) validates to `[]` from the packaged pins; `[2]` both pins sets present; `[3]` the G2 capture's sha `f56e8a6e…` ∈ `pins.system_prompt_hash`; `[4]` `python -m gsj_rollout.ingest_corpus validate --corpus …/estate/corpus/staging` → PASS (12/12); `[5]` `gsj_rollout.estate` on the wheel layout — `CHECKOUT False`, `INGEST` the packaged sibling, `RUNS` under cwd, `--help` lists the seven verbs; `[6]` `FORGEJO_IMAGE == …:16.0.3`; `[7]` the CP-65 fixes exercised on the packaged `cli.py` (the F-45 NOTE with no `polar`, the bare pair with one beside `sys.executable`, the no-op re-render — mtime_ns + inode equal, no tmp); **`[8]` `scaffold` from the wheel** — `python -m gsj_rollout.estate scaffold --out <tmp>` writes five files whose `corpus.yaml` is `name`/`owner`/`git:`, and `validate` passes it unmodified with no warning — CP-71's deliverable reaching a consumer; **`[9]` the deprecated entry** — `python -m gsj_rollout.ingest_corpus validate` works (rc 0, PASS) and its stderr NOTICE names `python -m gsj_rollout.estate validate|ingest`, 0.1.6 as the release it keeps working in and 0.1.7 as the earliest removal, silent under `GSJ_PIPELINE_DRIVER`. **Step 6, the demo (wishlist 59, and 54's second event) — taken, a clean pass, AFTER the PyPI proof**: demo commit `672bab5` (pushed; that repo has no CI): `LIB_MIN` → `(0, 1, 6)`, `find_spec("gsj_rollout.estate")`, the `-m gsj_rollout.estate` Popen/say/hint/answers-header, `validate` through the estate verb, every remedy floor `>=0.1.6`, README + compose comments, `make_corpus.py`'s template the three-field manifest, `corpus_sandbox_image` retired (the sandbox image is the demo's `sandbox_image` answer to the tool — `SANDBOX_IMAGE`, pre-pulled as before), `read.py`'s G3 hint, next fresh id F-80. Proven from a FRESH CLONE of that commit against PyPI's 0.1.6 (a venv from `pip install 'gsj-harness-rollout-server>=0.1.6' pyarrow` — the README's own recipe): `make_corpus.py` → `validate` PASS with an EMPTY stderr (no notice leaks) → `up` rc 0 in 38 s from nothing — **the stdout mute held**: `== run demo == runs/demo/` at stdout line 96 of 171, zero `next — ` lines, zero Polar-block markers after it; the sandbox image is the estate's answer in `bringup-answers.yaml`, `rollout.yaml`'s `runtime.image`, `run.json` and all four bank rows; `status` lists the five containers; one episode through the demo's own printed recipe (row 1, `case_orchard@t2`, `--task-id gsj-cp74`) → **accepted** (`sk-polar-f1b18784…`, one turn, stop) in 7 s; `down --wipe` left no container, network or `work/`. The demo's `POLAR_IMAGE` stays `gsj0.1.3` (A-28 — a real published image; the referees refuted the finder's rebuild proposal, the CP-63/CP-67 posture). Rows **54** and **59** DONE. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-75] The `.env`, read not exported — CP-70's item 1 taken (as the CP-75 prompt states it; CP-70's report never landed on this disk, the CP-71 posture): `gsj-rollout submit` reads the `.env` beside its config for a variable the config names and the environment lacks; the size law re-set to the landed size, 2,034, under ADR-0033; wishlist 53 REOPENED (the same class, six echoes), 60 fired in part and re-parked, 62–64 NEW (the gateway leg the mechanism cannot reach; the refusal's traceback shape in the frozen `cli.py`; the writer's grammar vs compose).** The semantics, decided before pricing: **strictly beside the config** (`Path(os.path.abspath(config)).parent / ".env"`, bound at load — `cli.py`'s topology precedent — so a relative config path and a later cwd change cannot re-aim the read; `rollout.yaml` and `.env` are the siblings `estate.py up` writes; a `.env` in the cwd is never consulted, by test; a config built in memory, which nothing does, reads the cwd's — the dotenv convention — and refuses naming the real file); **the environment wins** — an operator who exported something meant it, a file silently overriding an export is the surprise this project avoids, and the refusal says so (`… not set in <dir>/.env (an export wins over it)`); with the export present the file is not even opened; an EMPTY export is absence, `estate.py`'s own rule (`Answers.secret`) and the CP-56 message's "unset or empty", kept; **the grammar is the writer's, and only the writer's** — `KEY='value'`, an inner `'` as `'\''`, blank and `#` lines, `KEY=` as absence (what `.` reads too); a bare or `"`-quoted value is REFUSED — the writer never emits one, it is the hand-edit (dotenv) shape, and the three readers disagree on it (`KEY="tok"` would splice the quotes into the clone URL, `KEY=tok # c` the comment, `KEY=$HOME` the literal, and the 401 would arrive inside the sandbox clone — the CP's review measured all three, and the second cut's "read bare as `estate.py`'s own reader does" was overturned: that reader only ever reads its own writer's output); no dotenv library (R1's candidate named and declined — the whole spec is one writer function in this repo); **a malformed line refuses** naming the real file and the line and saying what to do (CP-27; no `=`, a keyless `=value`, a non-name key such as `export KEY=…`, an unterminated or bare inner quote, a bare value) — never a skip; **no opt-in key** — the trigger is already explicit (the config names the variable), the file is consulted only for that variable and only when the environment lacks it, which is the case that REFUSES today, so it can only turn a refusal into a resolution, and a key would cost a config line, a generated line and one more thing a stranger must know; **lazy, at the seam** — `load_config` records the sibling path and reads nothing, so the receiver never opens the secrets file and a malformed `.env` beside a config naming no variable refuses nothing. **The finding (law 7), found not assumed**: `config.py` resolves ONE named variable. `mcp_token_secret_env` is a NAME it passes through the TaskRequest; the VALUE is read by `pi_harness.py:242` inside Polar's `serve_gateway` process — a different process, a frozen module, a process `config.py` never runs in — so the two seams cannot share the mechanism and the gateway terminal still sources the file (in a subshell). And the old closing block's "three terminals; each sources .env first" was over-broad on two of three: `serve` reads no secret (`receiver.py`/`cli.py` have no `os.environ`), `serve_rollout` never did. The honest cure for the gateway leg — an `estate.py` launcher injecting the run's `.env` into Polar's child environment, the pattern its pipeline phases already use (`estate.py:1594`, `:2980`: `{**os.environ, …}` with the three named secrets spread from `run_.env`) — is outside the size law and is row 62. **Priced at the file: +18** (§3's [CP-75] paragraph carries the per-line account and the budget argument; the ADR carries the "do not take it" case and its answer; the price moved twice under measurement — a quote-parity first cut refused the writer's own escape, a read-bare second cut was overturned by the review, the landed grammar refuses bare at one more line). Each behaviour has a test that fails with it removed (seven tests, root suite 169 → 176; every one killed by an implementation mutant in the review's scratch copies): resolved from the file and NOT exported — the whole environment byte-equal before and after; strictly beside the config, a relative path bound at load, a hand-built config's cwd read pinned as the convention; the environment wins, an empty export is absence, and a malformed file beside a winning export is never opened; absent from both — the CP-56 refusal naming the key, the variable, the real file and the rule; a malformed line refused naming the real file and the line, fourteen shapes; the quoting round-trip through `estate.py`'s writer (`Run.write_env`, imported) for a value with a quote, a space, a `$` and the rest of the shell's metacharacters, byte-for-byte, `estate.py`'s own reader agreeing; lazy. **Proven end to end on this Mac (no GPU)**: `estate.py up --name cp75` from nothing in 36 s (Forgejo :3001, MCP :8791, sign-in ON, the read token named by `estate.clone_credential_env`, gateway host measured dialable from a container), the receiver and `serve_rollout` started with NO environment, `serve_gateway` with `.env` sourced in its own child shell only, then `gsj-rollout submit … --row 0` from a shell with `env | grep -c '^GSJ_'` → **0** before and **0** after → `collected 1/1 episodes` (`case_0001@5`; twice — once on the second cut, once on the landed code after the review — both accepted, `validate_session_result` → `[]`, quarantine empty); the negative: every `.env` value (five secrets, 12–64 chars) grepped across the archived traces, the artifacts directory, `run.json`, both rendered configs and the three process logs — **zero hits**, the echoed clone URL carrying no userinfo (CP-56's strip). **The review** (two refereed workflows, 164 agents: six code lenses with two refuters per finding, six doc finders with two referees per hit; both resumed once after a session limit cut their second phases): 38 code findings reproduced, 2 survived both refuters and nine more were taken on judgment over the refuters' "preference, not defect" verdicts (the bare-value gap, the keyless skip, the relative-path binding, the hand-built config's real-file naming, the hermeticity defect — a shell carrying `GSJ_MCP_TOKEN_SECRET` turned the suite red — the two test regexes that pinned neither path nor line, the ADR's citation arithmetic, the compose-parity claim); the doc sweep's 33 upheld hits are all applied or recorded here; its two "FALSE" verdicts on pre-existing lines (charter row 29's eleven presets, the mcp README's eight modules) were checked and are true. **What the docs say now**: `estate.py`'s closing block prints the gateway line as the one that sources (in a subshell) and says `submit` reads the file — the `next — ` and `== run <name> ==` prefixes the demo parses byte-identical; its container-leg block says which of the three processes needs a value and that a container's `submit` needs the `.env` mounted beside its config; its `.env` header, the generated `rollout.yaml` header and the tool's `--help` docstring say the same; `_env_quote`'s docstring no longer claims compose parity (row 64); `estate/README.md`'s run-directory paragraph, the server guide's `serve` printout paragraph, its `clone_credential_env` row, its by-hand run book (whose tokens live in `forgejo/.token*` files, not a `.env` — its exports stay) and its troubleshooting row, the trainer guide's two credential mentions — each stating the rule and that **wheels through 0.1.6 read the environment only**, so on those the subshell line stays. The demo's recipe — twice, `README.md:344-350` and the `up`/`status` printout at `bootstrap.py:1005-1011` — stays correct and is not lifted: its `submit` runs inside the pinned `gsj-polar:f0e8343a-gsj0.1.3` image (library 0.1.3, no seam), so a floor bump retires nothing; it retires at a `gsj-polar` cut on ≥ 0.1.7 with the run's `.env` mounted beside `/estate/rollout.yaml` (row 62 names both). `estate/rollout.h200.yaml:37`'s "the var MUST be exported" is over-strong now and outside the lift — row 62 carries it for the H200 by-hand path. Touched here: `gsj_rollout/config.py` (the CP's only source change), `tests/test_config.py` (+7), `tests/test_cli.py` (the census literal and its docstring — the declared excursion under ADR-0028's clause), `estate/estate.py` (four strings and one docstring — Step 6's named target plus the false compose claim; outside the size law), `estate/README.md`, `docs/guide/{server-guide,trainer-guide,troubleshooting,how-it-works,README}.md`, `docs/README.md` (`:3` and the ADR range), `docs/CHARTER.md` (§1, §3 preamble + [CP-75], §8 rule 2, §9, this paragraph), `docs/VERDICT.md` (rows 53, 60, 62–64), `CLAUDE.md` (law 2's echo, the layout and suite counts — ADR-0012's echo duty, the CP-65 precedent, declared). NOT touched: `checks.py` (528/528, its tripwire green), every other `gsj_rollout/` module, `vendor/`, `pins/`, `.github/`, `estate/` beyond `estate.py`'s strings and the README, the consumer repos — the DoD diff on the frozen list EMPTY. The six tracked echoes outside both the lift and the mandatory list — `README.md:6` "2,016-line shell", `.github/workflows/ci.yml:27` "2,016-line budget", `README.md:102`'s "32 ADRs", and the root-suite count at `README.md:96`, `ci.yml:4` and `ci.yml:40` ("169"; the suite collects 176) — are row 53's class, stale again, re-parked there with a token. Rule-9 scan (the token spelled colon-free here, the CP-64 precedent): fired — **60** in part (its token named "the first tests/ lift", and this CP's one-file `tests/test_config.py` lift is that by the token's own words; NOT taken — the row's fix pairs `tests/test_wheel_pipeline.py:154` with `estate.py`'s metavar pin in one change and neither was lifted — annotated and re-parked on the sharper event); rows 22, 41, 47, 50, 61 wait on events this CP is not; rows 53, 62–64 open and tokened; row 26 per the push's run in the report. Push: this repo's `main` at this CP's commit — the report carries the hash and the CI run. Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-77] The indexer's two defects — wishlist 66, both halves, one image.** CP-76's item 10 taken: `chromadb==1.5.9` refuses a single `collection.add` above **5,461** items and both of the service's builders added the whole corpus in one call; `_recreate_collection` orphaned the previous HNSW directory on every rebuild. Reproduced before fixing, with the shape settled: the ceiling is `32766 // 6` — the SQLite statically linked into the wheel's Rust bindings (`RustBindingsAPI` is the persistent client's whole path in 1.5.9; the interpreter's own `sqlite3` reports 250,000 on both hosts and does not enter it; CP-76's Python-side derivation shares the formula, not the number) over six variables per record — and **a count of items, not items × metadata keys** (5,461 passes with 0/1/12/40/120 keys, 5,462 fails with any, one message, venv and Linux image alike); the orphans are chroma's, not ours — `delete_collection` drops every row and never the directory, in every case measured (same process, fresh process, opened first, a later start, `reset()`; the 1.5.9 Rust sources have no `remove_dir` on the path) — 39 under `estate/runs/cp73`, seven rebuild waves. Landed in `estate/mcp-service/` only (`gsj_rollout/` 2,034/2,034 untouched, no config key, no tool, no result shape, no fingerprint moved): both builders encode and add in `ADD_BATCH_SIZE = 1000` batches (5.46× under the ceiling, clamped at run time to what the client reports; the margin is against the count moving, not width, which was measured not to matter) with progress per batch in the log and in `/health`'s `build` block (kept, showing the last batch, when a build fails); `corpus_size: 0` refused at config load (the batched builder would otherwise come up ready and fail at the first query, where the single add refused at startup); `sweep_orphans` removes, after every drop and once at every start that loads or rebuilds — on the reuse path only after the load's own checks pass, so a refused store stays byte-untouched — exactly the directories no `segments` row names — argued in ADR-0016's CP-77 amendment (a directory without a row is unreachable by any chroma path and is the graph half of a store whose other half is gone; an interrupted rebuild's orphan is never servable because CP-57's record, written before the first drop, has no fingerprint) and refusing everything else (a live or half-filled collection's directory, non-uuid names, symlinks, files, all of it when `chroma.sqlite3` cannot be read — and an entry it cannot remove is skipped with its reason, never a failed start: the CP's review caught the first cut letting `rmtree` raise, which errored a start under every posture over a store that had served with the orphan inert). Proven: a build above the ceiling in the suite (6,000 decisions) and at scale (19,215 chunks + 12,000 decisions); a real `SIGKILL` at 3,000 of 19,215 vectors → `never` refuses ("missing", tool calls 503), `if-stale` rebuilds from scratch, directories equal segment rows after; the cp73 store's copy 45 → 6 directories (39 swept, 6.56 MB, the six live collections serving); the same 6,000-decision config errors on the 0.4.0 image with chroma's message and builds in six batches on 0.4.1; a pre-CP-77 and a CP-77 build of the staging corpus bit-identical on every collection, sidecar and fingerprint, the old store reused; mcp-service 114 (107 + 7), the six 30-assertion tests untouched. **Findings (law 7):** (1) **A-25 departs in one of three legs at scale** — same-store and builder-vs-loader identical 7/7, two independent builds identical at tool level 6/6 but not at the chunk tail: the `where`-filtered full fetch is ≈0.1% short (9,571 of 9,581) and each build misses a different tail from rank ≈450; a bounded fetch of 100 or 1,000 differs between builds at the top; the cause is NOT established (the review rebuilt the same bit-identical vectors under `hnsw.num_threads: 1` and still got two graphs) — ADR-0016 Mechanics 4's exact-scan parity qualified in the ADR and in `CaseIndex.search`'s docstring, A-25's three cells updated, two suite tests named as asserting the parity at 213 chunks only, wishlist 68 for the CP-78 fetch design; (2) **the vectors' bits depend on which texts share an encode call** — the 30 decisions in sevens vs one call max\|Δ\| 9.7e-08, vs single 1.19e-07; full-window 220-token chunks 0 but **page-tail chunks move** (73 of the staging 213; at scale a whole-collection re-encode differs from the 1,000-batched store by 1.4e-07 on 67 of 19,215 rows, all page-tail — above the 4e-08 bound and the 1.155e-07 substitution floor) — so `ADD_BATCH_SIZE` shapes the bytes above 1,000 items (an `INDEX_FORMAT` bump on change, the chunker's rule), every existing store (≤62 chunks, 30 decisions) is bit-unchanged and reused, and **the identity oracle was wrong above 1,000 chunks** (a whole-collection re-encode, two of its three sampled rows page-tail; it would fail by sampling luck on a true store) — fixed: it re-encodes in the builder's slices (`batch_spans`), the CP-55 bound untouched where measured; what stays open is `embedding.batch_size`, a config key that shapes the same bits, is not in the fingerprint, and which `estate/estate.py` prints as "speed only, not identity" (frozen this CP) — wishlist 69. **Image `0.4.1` built in both halves on the workstation** (native arm64; amd64 through CP-58's emulated recipe, the pip layer cached), **neither published nor loaded**: the GHCR two-platform push, the H200 `save | load` (`compose.yml` now asks for `0.4.1`) and the `estate/estate.py` / `estate/README.md` tag bump are the residual (`estate/` beyond `mcp-service/` frozen this CP, no H200 hold; row 66 carries the token) — an `estate.py` estate today runs `0.4.0`, which fails any collection above 5,461 vectors. Rows 65–67 (CP-76's drafted text) appended verbatim; 66 amended DONE; 68–69 NEW. `ci.yml`'s job label still says 107 where the suite is 114 (`.github/` frozen; `CLAUDE.md` corrected).

**[CP-78] The decisions surface, specified — a document, not an implementation; `docs/**` only.** The operator's five settled points (k = 5; thirty *chosen* decisions per estate corpus; gsj-next's wire shape `{query, k, hits, index_commit}` adopted here, gsj-next unchanged; the Randnummer as the unit) written down as `docs/decisions-surface.md` v1 (ADR-0034), precisely enough for two systems to implement and be *proven* to agree, with the conformance fixture beside it at `docs/decisions-surface/` (six published BGH decisions, `expected.json` carrying its `surface_version`, and `reference_extractor.py` — the generator, standard library only, the fixture's provenance and not an implementation of anything served) and one line in the shelf map. **Where it lives**: one canonical copy here, versioned by a surface version in its title and referenced by permalink; the fixture is meant to be copied, the document is not — a copy in each repo drifts at the first edit, a third repo has no owner, the wheel versions by a cadence gsj-next does not consume (spec §0). **What it fixes**: the source format (rii-dok v1, the DTD's 26 elements with every element's measured cardinality); a text rule `text(e)` two implementations produce the same bytes from (dropped subtrees contribute nothing at all — `<table>`, `<img>`, and the 326 image-viewer `<a href>` links found by refutation; six inline elements; Unicode White_Space normalization; `itertext`, never `.text` — 1,441 Randnummern and 11 decisions vanish under `.text`); the unit (an anchored `<dl>` row plus the unanchored rows between it and the next anchor, headings and quotations alike; rows after a section's last anchor kept only if indented — the one attribute test, `margin-left`, chosen after classifying all 309,200 unanchored rows by position, style and length; a section without anchors one unit with `rn` null, which is how the 6.6% anchorless Beschlüsse are indexed); identity (`doknr`, 33,979/33,979; Aktenzeichen display-only, ambiguous even with the date; ECLI absent for 33%); the split (verbatim contiguous covering pieces, never across units, the window the implementation's); the hit (every field typed, **absent vs null** decided — `ecli` absent when the source has none, `rn` null for a section unit and absent only at a level-1 implementation; `page`/`file` reserved); `index_commit` optional, `""` conformant; best piece per unit, top-k whole units, `k` default 5 clamped below at 1 and capped by the implementation, the candidate fetch bounded by `k` never by the corpus (row 68's half); the citation grammar `dec:<doknr>[:rn:<N>]` with a bounded regex and **the degradation rule** — the suffix only from an integer `rn` the hit carried, the bare form for `rn` null or no `rn` key — which makes a model trained at level 2 safe *in grammar* against gsj-next's level-1 surface today (every gsj-next hit's `decision_id` is the `doknr` on this drop, a data property its fallbacks never disturb; resolvable there by the operator CLI only), while the policy's compliance stays empirical (row 70). **Proven, not asserted**: three independent implementers (a literal reader, a gsj-next-side engineer, a state-machine author) wrote extractors from the spec text alone, forbidden the fixture and every reference, and reproduced `expected.json` byte for byte — then converged on the same wording gaps (an anchored row with an empty body, a dropped element's word boundary, "contains", header stripping), all folded in; fourteen refuters over seven claims (roster/G2 with the return annotation rendered through the roster suite's own helper — G3 and G2 unmoved, the annotation change `-> dict` mandatory under mcp 2.0.0's output validation; the degradation rule's premise; the unit rule's completeness; the licence position; every figure; both cost tables) found one material defect — §3.1's first wording contradicted the reference extractor on exactly three corpus rows the fixture could not see — and a dozen figure and wording precisions; the fixture grew from three shape files to six, the last three each pinning one sentence (a glued image, the viewer link, an indented tail row inside a `<span>`), and on them two of the three blind implementers now fail the image and all three the link — the fixture discriminating what the text alone did not. Three reviewers (a gsj-next maintainer's seat, a completeness critic against the prompt, a consistency reader) added the level-1 field-contract reading (a `.text` parser empties two of the six files, so level 1 cannot be a text test), the §2.2 scoping against gsj-next's never-drop rule (both postures conformant; a non-`doknr` id never citable), the version key inside `expected.json`, gsj-next's release-and-operations cost, the `k` cap as a context matter, the German wording of the citation clause, and the `estate/`/docs rows CP-76's cost table had and the first draft dropped. The six files re-downloaded from rechtsprechung-im-internet.de at CP-78 and compared byte for byte: identical; licence position § 5 Abs. 1 UrhG plus the publisher's free-reuse statement, narrowed by refutation (the `titelzeile` is a documentation addition, not the court's; no `sonstosatz` in any file). **Register**: A-32/A-33/A-34 (CP-76's drafts) and A-39 (the indentation attribute) filed; rows 65, 67, 68, 69 — every token naming this CP — annotated and re-parked on the events that can perform them (65 the building CP; 67 the first declaration edit, the spec moving none; 68 the fetch bounded here, recall measured at the build; 69 misnamed: batching is left to the implementation by design, `estate/` frozen); rows 70 (the rule's empirical half), 71 (gsj-next's pointer), 72 (version-2 candidates: tail headings, 946 substantive tail rows, 69 bare-`<div>` files) NEW. **Cost, both sides** (spec §13): here — `estate/mcp-service/` bodies, one service test rewritten, an image cut, `gsj_rollout/` 2,034/2,034 and the pins untouched; gsj-next, if it adopts — level 1 ≈ 15 lines and two columns (plus a `k < 1` clamp it lacks today), level 2 a rewrite of its decisions half and a full re-ingest of ≈ 1.39 M pieces. Nothing built; `gsj_rollout/`, `vendor/`, `estate/`, `pins/`, `tests/`, `.github/` byte-untouched (the DoD diff empty).

**[CP-79] Decisions, built — the surface of CP-78 served at level 2; `estate/mcp-service/`, `estate/estate.py`, `estate/README.md` and `docs/**`; image `0.5.0`; `gsj_rollout/` 2,034/2,034 and every pin untouched.** Opened with the publish CP-77 owed: `ghcr.io/mhganainy/gsj-mcp-service:0.4.1` composed as a two-platform index from the two measured images (`buildx imagetools create`, no rebuild — CP-61's method; index `d27327a4…`), both children fetched with an anonymous registry token, the amd64 half loaded on the H200 through skopeo as uid 1000, `estate.py`'s pin and `estate/README.md` bumped — and then `0.5.0`, this CP's cut, published and loaded the same way (index `17704c06…`). **The parser first**: `decisions.py` gained the rii parser and unit walk (a second reading of spec §2.2/§3/§4/§5, the synthetic generator left byte-unchanged as the no-path fallback) and `tests/test_decisions.py`'s first test compares its serialized output with `docs/decisions-surface/expected.json` byte for byte — 62 units, six files, reproduced on the first run — with the three discriminator sentences pinned positively on their files and on synthetic rows (a dropped `<img>` leaves `Rn. 2). Da`, an `<a href>` vanishes caption and all, an indented `<span>`-wrapped tail row is kept and the judges' names are not); over the whole March 2026 drop the parser reproduces spec §4.7's census figure for figure (740,849 units — 667,099 Randnummern, 73,750 section units — 2,231 files without a Randnummer, 462,896,397 characters, 22,831 ECLIs; 3 s over eight processes). **The store**: `decisions.path` (additive; `estate.py up --decisions-dir`, a read-only mount at `/app/decisions`, the host path in `run.json` and in the pre-embed review — never silently) → units → pieces through the one splitter (`ingest.split_spans`, the page chunker's window factored out, its bytes unchanged) and `check_chunks_fit` (now in slices) → CP-77's batched add; the fingerprint gains `decisions_drop: {sha256, surface_version, files}` only when a drop is configured, so a store without one hashes the pre-CP-79 document byte for byte (reproduced by hand in the suite; the cp75 workstation store built by `0.4.0` reused whole in 5 s with its segments untouched; the H200 pre-production store's `4954c167…` reproduced from its record without touching the box); `fingerprint.json` records one fingerprint per collection and `if-stale` rebuilds only what moved — a drop added to a pre-CP-79 store re-embeds `decisions` alone (wishlist 61 closed as the drop's side effect); `embedding.batch_size` is identity, a component when it leaves the pinned 32 (row 69 (c) decided). **The tool**: `search_decisions` returns `{query, k, hits, index_commit}` — the effective `k`, level-2 hits (`ecli` absent when the source has none, `rn` null for a section unit, `excerpt` the best piece, no `page`/`file`), the synthetic 30 inside the same envelope with `index_commit ""` — and the `def` line's `-> list[dict]` became `-> dict`, the one byte outside every pin: the roster suite renders the served declarations byte-identical to the captured wire entries and the episode's trace carries the unchanged 11-tool roster. **The fetch**: `200·k` pieces, a function of `k` — measured against an exact scan over every stored vector of a 1,999-file drop (71,946 pieces, 60 queries): recall 1.000 at k = 5 and 0.998 at k = 20, the unbounded HNSW fetch exact, the loss at smaller bounds the graph's search beam (`ef_search` 100 widened by `n_results`); A-25 at that scale: same-store and builder-vs-loader identical 8/8 in two runs, two independent builds identical at tool level and sharing 999 of 1,000 piece ids at the shipped fetch — the CP-77 tail, located; the identity oracle's benign end on the real store 1.49e-08 over 4,000 vectors. **One episode** through a cp79 estate on this workstation (a 200-file drop, 7,219 pieces embedded in eight batches inside the container, 170 s to ready; the Mac's vllm-metal Qwen3-0.6B): the agent called `mcp_gsj_search_decisions` first, received three whole Randnummern of two decisions (one without `ecli`, one hit's `excerpt` shorter than its multi-piece unit), reported Aktenzeichen, date and Rn 2 with a quoted sentence — and never wrote `dec:KORE621142019:rn:2`, the token its hit carried: the receiver accepted the trace, the grammar was available, the policy did not use it (row 70's empirical half, observed once). **Findings (law 7)**: (1) the six-file fixture caught nothing in the build — the CP's six-lens review caught what it cannot see: the Randnummer numbering anomaly judged per section (every ordinary Urteil flagged, the cross-section duplicates invisible — fixed decision-global, the spec's 13 + 101 = 114 files reproduced), a §6 coverage gap at a unit's edge (a soft hyphen the tokenizer gives no offset; one real unit), a record gap when a whole-store load fails midway, and the drop-swap confirm; (2) **spec v1 disagrees with its own reference extractor** on header whitespace — §3.1 collapses inner runs, the extractor and §5.2 keep them, and two files of the drop carry a doubled space (row 75); (3) **chroma 1.5.9's read path has a ceiling too**: a `query` that includes metadatas or documents is refused above 32,763 results (`too many SQL variables`; ids and distances alone fetch the whole store) — the decisions fetch sits 8× under it, `CaseIndex.search`'s full-candidate fetch would be refused above 32,763 in-cutoff chunks (row 68, moved); (4) spec §13.1's `/health.decisions → {count, sha}` sketch would have retyped an integer every reader and five `== 30` assertions hold — the build keeps `decisions` an int and adds `decisions_drop` (absent, never null) and `rebuilt`. **Not this CP's, said so**: the corpus contract's `decisions/` entry, `validate` clauses and lock (`estate/corpus/` frozen — row 73); the thirty chosen decisions (proven at an arbitrary every-17th-file scale, curation owed — row 74); the AGENTS.md citation clause (a corpus author's). Rows 61, 65, 66, 69 closed; 68 moved; 73–75 NEW; A-25 a fourth cell, A-40 filed; ADR-0035. mcp-service 134 (114 + 20), root 176, corpus 109 untouched.

**[CP-80] Release 0.1.7 — four checkpoints reach a consumer (CP-75's `.env` read at the `submit` seam, the one `gsj_rollout/` change since 0.1.6, +18 under ADR-0033; CP-77's batched adds and orphan sweep and CP-79's decisions surface through the published images `0.4.1`/`0.5.0`; CP-78's specification and fixture under `docs/`; CP-79's `--decisions-dir` in the packaged tool); the deprecated entry KEPT, its earliest removal moved to 0.1.8; wishlist 53 fired whole, five of six moved; rows 76, 77 NEW.** **The deprecation (Step 1)**: `python -m gsj_rollout.ingest_corpus` stays. For removing it: no published consumer spells it (both consumer repos grep-clean — the demo moved to the estate verb at CP-74; the corpus suite calls the module, not the entry), so a removal breaks nobody known, and every kept deprecation teaches that the notice is noise. For keeping it, which won: CP-72's notice promised survival through 0.1.6 and a removal "no earlier than 0.1.7", and 0.1.6 was published on 2026-09-02 — one day before this release — so a pip consumer on 0.1.2–0.1.5 who scripted the form has had one day of notice; a removal in the first eligible release is the letter of a floor, not its spirit; nobody asked; and the entry costs nothing (the module was always staying importable, and the estate tool imports the same file). Every lifted statement of the bound now reads "kept at 0.1.7; removal no earlier than 0.1.8" (`pyproject.toml:97`, `corpus-contract.md:347`, `trainer-guide.md:13`/`:20`, `server-guide.md:281`); the notice's own string lives in `estate/corpus/ingest_corpus.py` (frozen) and still says 0.1.7 — a weaker bound that stays true, read from the artifact ([9]) and recorded as row 76 (b). **The version literal is `gsj_rollout/`'s only change** (2,034/2,034, ADR-0033's equality green before and after; the packaged `gsj_rollout/*.py` byte-identical to the release tree, the census 2,034 read from site-packages, `_named_value` in the packaged `config.py`). **The sweep (Step 2), classified**: every `0.1.6` in every form — the literal, `(0, 1, 6)`, `>=0.1.6`, `v0.1.6`, `gsj0.1.6`, the wheel filename — across the three repos' tracked trees; moved: the three literals, `README.md:43`, `CLAUDE.md:5`/`:51`, `docs/guide/README.md:23`, `trainer-guide.md:9`/`:11`; dated-historical, kept: every "since 0.1.6" / "from 0.1.6" / "wheels 0.1.3–0.1.5" clause (`CLAUDE.md:79`, `corpus-contract.md:17`, `how-it-works.md:22`, `server-guide.md:281`, `trainer-guide.md:13`/`:20`/`:22`, `docs/guide/README.md:23`'s two), the §7 paragraphs and register rows that name it, and `estate/`'s six strings (row 76); the demo's 15 hits are its floor and its floor's story, and **the floor stays `>=0.1.6`**: nothing the demo runs needs this release (its `submit` runs inside the pinned `gsj0.1.3` image — row 62; `scaffold`'s three-field manifest is 0.1.6's), and it moves to `>=0.1.7` at CP-81 with `--decisions-dir`; the examples repo has no `0.1.6` at all — its `README.md:5` "PyPI 0.1.5", `:279` and `RUNBOOK.md:477` "corpus 67, mcp-service 107" are now two releases stale (CP-74's carry-forward, for CP-82's sitting). Beyond the version: `README.md:6` 2,016 → 2,034, `:96` 169 → 176, `:102` 32 → 35 ADRs, `CLAUDE.md:59` ADRs 0001–0035, `server-guide.md:285` the service image `0.4.0` → `0.5.0` (CP-79's cut; the compose file's tag). **The labels (Step 3)**: `ci.yml:4`/`:40` (169 → 176) and `:6`/`:70` (107 → 134), each by collection (176 / 134; corpus 109 unchanged; the CP-79 CI run had already collected 176/134 under the old names), nothing else in `.github/` — `ci.yml:27`'s size-law comment left under the prompt's "labels only" and re-parked (row 53). **What ships, read from the built artifact in a scratch venv outside every repo (Step 4)**: 18 entries, the six banned prefixes and CP-19's nine names absent, the seven required present, no `bringup`, `twine check` PASSED, METADATA 0.1.7; `gsj_rollout.estate` on the wheel layout with its seven verbs, the packaged `estate.py` sha256-equal to the checkout's and carrying `--decisions-dir` and the decisions review line; the deprecated entry working, its notice as above. **Found on the artifact (law 7)**: the packaged tool's default retrieval image is `0.4.1` (`MCP_IMAGE_PUBLISHED`), whose service forbids the `decisions.path` key the tool writes — `--decisions-dir` serves a drop only with `--mcp-image …:0.5.0` (row 77; the trainer guide's `estate.py` row says so). **What the release retires (Step 6)**: an operator on 0.1.7 with an `estate.py` run directory no longer sources the run's `.env` before `gsj-rollout submit` — the seam reads it beside `rollout.yaml` for the one variable the config names, the environment winning when set, nothing exported ([10], both halves, from the published artifact); the gateway terminal still sources (row 62 — Polar's process); the `docs/**` half of CP-75's "wheels through 0.1.6" clauses moved to the dated form (`server-guide.md:90`, `troubleshooting.md:95`), the `estate/` half — four `estate.py` strings and `estate/README.md:99` — waits on the next `estate/` lift (row 76 (a)). **The review** (eight refereed lenses over the diff, the lifted files and the consumer repos — 26 findings, two adversarial referees each): 19 upheld in the lift and applied as 13 distinct edits — the stale current-state claims CP-79 left in `docs/**` (the spec's own "not implemented" status and its §7.6 who-column, the troubleshooting rows' `0.4.0` image defaults, the fixture counted at three) and this paragraph's and the register's own (three tokens worded "the next lift of X", rule 9 (c)'s rejected form, re-worded to name freeze-lifts and calendar events; row 77 without `estate/README.md:83`; the stamp count; the tally sentence; the server guide's `--decisions-dir` without its image caveat; `CLAUDE.md:79`); 7 record-only (the consumer repos' stale lines, `ci.yml:27` under the labels-only lift, and `ci.yml:8`'s "four carried-patch tests" — REVENDOR.md's four files hold 25 tests, a unit ambiguity both referees refused to call a defect). **A release is a pin-worthy commit** (spec §0): the tag's commit is the first release whose tree carries `docs/decisions-surface.md` v1, so the permalink `gsj-next` would pin is `https://github.com/MHGanainy/gsj-harness-rollout-server/blob/<the v0.1.7 commit>/docs/decisions-surface.md`. Touched: `pyproject.toml`/`gsj_rollout/__init__.py`/`tests/test_scaffold.py` (the three literals; `pyproject.toml:97`'s comment), `ci.yml` (four labels), `README.md` (`:6`, `:43`, `:96`, `:102`), `CLAUDE.md` (`:5`, `:51`, `:59`, `:79` — `up --decisions-dir` CP-79 on the tool's line), `docs/guide/README.md:23`, `trainer-guide.md` (`:9`, `:11`, `:13`, `:20`, `:22` — the 0.1.7 history clause with the `--mcp-image` caveat), `server-guide.md` (`:90`, `:281`, `:285`, `:302` — the `--mcp-image` caveat beside `--decisions-dir`), `troubleshooting.md` (`:95`; `:133`/`:144` — the image tags `0.4.0` → the tool's `0.4.1`, with the `0.5.0` caveat), `corpus-contract.md:347`, `docs/README.md:18` (the fixture is six decisions, not three), `docs/decisions-surface.md` (the status paragraph and §7.6's who-column — implemented at level 2 since CP-79; a wording change logged in §14, the version stays v1), three re-rendered PNGs (`wheel-contents`, `two-roles`, `api-surface` — three of the deck's four 0.1.6 stamps, the ones with a tracked render; the fourth, `install-paths`, untracked since CP-54, moved with them off-tree; the other 30 tracked renders came back byte-identical), `docs/VERDICT.md` (53, 76, 77), this file. NOT touched: `gsj_rollout/` beyond the literal (the DoD diff on the frozen list EMPTY), `vendor/`, `estate/`, `pins/`, `tests/` beyond the assertion, `.github/` beyond the labels, both consumer repos. Push: `main` at the release commit, tag `v0.1.7` on it once CI is green — the record commit beneath this paragraph carries the run ids, the colours and both eleven-check proofs. **The record (the second commit — the CP-34/CP-60/CP-63/CP-67/CP-74 shape)**: release commit `14b88f7`, tag `v0.1.7` at it. Push `14b88f7` → CI run **33749709831**: root suite (176) green · corpus suite (109) green · mcp-service suite (134) green — the two relabelled jobs' first runs, 176 and 134 collected · wheel + packaged-pins install proof green; no red job, row 26 did not fire. Rehearsal (`workflow_dispatch` at `14b88f7`) → **33749739817**: build green (the tuple's `gsj_rollout/estate.py` row and the runner's PROOF OK in its log) · TestPyPI green · PyPI **skipped** (tag gate). Tag `v0.1.7` → **33750559346**: `tag v0.1.7 matches version 0.1.7`, build green · TestPyPI green · **PyPI green**. **Both install proofs, eleven checks each** (scratch venvs under the session scratchpad, outside every repo; the proof script asserts no `.git` above its cwd — the CP-63 trap, mechanised — and reads `gsj_rollout` from site-packages): TestPyPI (`==0.1.7` + the extra index for deps) 0.1.7 on attempt 1; PyPI (no index flags) on attempt 2 (~15 s lag — the CP-63/CP-67/CP-74 pattern), and an unpinned `pip install gsj-harness-rollout-server` from a neutral cwd resolves 0.1.7; `pip show -f` lists `estate.py`, `ingest_corpus.py`, both pins sets, the G2 capture — no `bringup.py`. From both indexes: the packaged `gsj_rollout/*.py` byte-identical to `14b88f7`'s (all eight), census 2,034 from site-packages, `_named_value` in the packaged `config.py`, `estate.py` and `ingest_corpus.py` sha256-equal to the checkout's; `[1]` the CP-09′ body (`sk-polar-44620742…`) validates to `[]` from the packaged pins; `[2]` both pins sets; `[3]` the G2 capture's sha `f56e8a6e…` ∈ `pins.system_prompt_hash`; `[4]` `python -m gsj_rollout.estate validate --corpus …/staging` → PASS (12/12), no notice; `[5]` `gsj_rollout.estate` on the wheel layout — `CHECKOUT False`, `INGEST` the packaged sibling, `RUNS` under cwd, `--help` the seven verbs; `[6]` `FORGEJO_IMAGE …:16.0.3`, and `MCP_IMAGE_PUBLISHED …:0.4.1` read and recorded (row 77); `[7]` the CP-65 fixes on the packaged `cli.py` (the F-45 NOTE with no `polar`, the bare pair with a stub beside `sys.executable`, the no-op re-render — mtime_ns + inode equal, no tmp); `[8]` `scaffold` from the wheel writes five files whose `corpus.yaml` is `name`/`owner`/`git:` and `validate` passes it unmodified, no warning; `[9]` the deprecated entry works (rc 0, PASS) and its NOTICE names `python -m gsj_rollout.estate validate|ingest`, 0.1.6 and "no earlier than 0.1.7", silent under `GSJ_PIPELINE_DRIVER`; **`[10]` the `.env` from the published wheel, both halves** — a config naming `clone_credential_env`, a `.env` beside it, nothing exported: the rendered clone URL carries `tok-from-file` and the process environment holds no `GSJ_*` before or after (read, not exported); the same with the variable exported as `tok-from-env`: the export wins, and still wins with a garbage `.env` beside it (not opened); a malformed `.env` with nothing exported refuses naming the file and `line 1`; **`[11]` `scaffold` on the CP-79-touched tool** — the packaged `estate.py` (sha256 `6bbadc89…`, the checkout's, carrying `--decisions-dir`) writes the three-field manifest, `validate` passes it unmodified with no warning, and with the three legacy estate fields added warns exactly three times and passes. Push: `origin/main` at the record commit; the demo and examples repos untouched (nothing to push there). Tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-81] The demo, with decisions — the surface reaches a consumer, and the citation clause meets a policy for the first time; the demo repo and `docs/**` only, `gsj_rollout/` 2,034/2,034 and every other frozen path byte-untouched.** CP-79 built the decisions surface at level 2 and recorded two things owed: a corpus arriving with the thirty decisions its author chose (row 74), and an empirical answer to whether a policy TOLD the citation grammar uses it (row 70's second half). The demo can do what the staging corpus cannot — its cases are ours to write, so decisions can be written to bear on them. **The thirty**: `synthetic/decisions.json` (tracked data) plus a renderer in `make_corpus.py` produce thirty fictional decisions of two invented courts of an invented district (Landgericht and Oberlandesgericht Grevenau, 2009–2024) as rii-dok v1 — the DTD's 26 elements in order, `<dl class="RspDL">` rows, `<a name="rd_N">` anchors, the publisher's two paragraph renderings (plain and the post-2018 styled `<span>`), signature tables and signature rows, indented quotations with the plain paragraph that resumes after them, two tables inside a Randnummer, one `Rechtsmittelbelehrung` tail row, one tenor-only order with no reasoning section at all, three files with no `titelzeile`, and an `ecli` on the sixteen dated 2016 or later. They are **chosen by construction**: each is written about what the demo's own cases turn on — the register against a long-standing fence, prescriptive possession, accession of a ditch, the scope and survival of a registered right of way; termination of a commercial lease for arrears, rent reduction for a flooded annex, notice through the caretaker, a landlord's deferred repair — so a stranger's search returns precedent a lawyer on these cases would want (measured: the deferred-repair query returns the deferred-repair decision's Leitsatz at 0.65, the easement query its Randnummer 9). Each was drafted, then reviewed on two independent adversarial lenses (bearing-and-law, format-and-shape) with a correction round: **26 blockers found and fixed across thirteen of the thirty**, among them four inverted geometries (a decision whose stated compass direction entailed the opposite of its own holding), three costs orders the reasons never supported, a § 485 Abs. 2 ZPO vehicle reasoned as if § 286 ZPO applied, and a demo-party initial that had leaked into an invented note. **Conformance, proved through the packaged parser rather than asserted**: `load_drop` over the generated drop reads 30 decisions, 0 refused, **313 units = 244 Randnummern + 69 section units**, 181,325 characters of unit text, drop sha256 `b414c670…`; the unit list matches the generator's own expectation for all thirty files; the parser reports **no anomalies** (numbering contiguous 1..K decision-global in every file); `ecli` present on 16 of 30 and absent — not null — on the rest. **The clause (spec §9.5)**: the corpus's `AGENTS.md` is the packaged reference text with one `## Decisions` section inserted before `## Deliverables`, the rest byte-identical (asserted in the generator, the reference span read from the installed wheel's G2 capture) — the format AND the degradation rule, stated as a rule the agent follows: *when the hit carries no `rn` … drop the suffix … never invent an `rn`*. It moves this corpus's G2 by design: `up` re-derives the pin (4,989 chars, sha `ebfa5e5f…`, against the reference's 4,466 / `f56e8a6e…`) and the receiver accepted every episode against it. **The seam**: `bootstrap.py` finds the drop BESIDE the corpus (`<corpus>-decisions/`, because the corpus contract admits no `decisions/` entry — row 73, and `validate` refuses one with the `mv` named) and passes `--decisions-dir`; no fourth input, and the bring-up's pre-embed review names the drop before anything is spent. **The floor moves to 0.1.7** for two reasons, and `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.7` was cut two-platform to carry them (A-28's rebuild duty, annotated): `--decisions-dir`, and CP-75's `.env` seam, which retires the demo's submit subshell — the run's `.env` is mounted read-only beside the config the container reads, and an episode submitted from a shell with **zero** exported `GSJ_` variables was collected and accepted (**row 62 (b) closed**). The retrieval image the demo answers moves `0.4.0` → `0.5.0`, which is row 77's workaround exercised by a consumer; **row 77's derived failure was also measured** — `0.4.1` refuses the `decisions.path` key the tool writes (`extra_forbidden`, the container exits at startup), `0.5.0` accepts the same file. **The reader**: `read.py` renders a decisions hit as what it is (court, docket, date, type, Randnummer or section, score, the citation the hit admits) instead of the raw clip CP-76 measured, and checks every `dec:` token the agent writes against that session's own hits — grounded or ungrounded, per token, beside the turn that wrote it — with a header line that says NONE when hits were available and nothing was cited, counts doknr written without the prefix separately, and reports whether the episode's own prompt carried the clause. **THE OBSERVATION (law 7), and it is a negative with a sting**: across four episodes on two estates with the clause in the pinned prompt and a natural precedent task, the 0.6B reference model searched, received level-2 hits carrying `rn`, named the decisions by **bare doknr in prose** — and wrote **no `dec:` token at all** (the §9.1 regex finds none in any of the four traces). Told the exact token form in the task prompt, it wrote one and **fabricated the Randnummer**: both hits in that episode were section units carrying `rn: null`, whose only valid citation is the bare `dec:GREV000082013`, and it emitted `dec:GREV000082013:rn:7` — exactly the failure the degradation rule exists to prevent, caught unprompted by the reader as `UNGROUNDED rn — the decision was retrieved (turn 1) but no hit carried rn 7`. So the clause alone does not produce the citation, and an instruction to produce it produces an ungrounded one: evidence for precisely what row 70 says is missing, which is the grammar exercised **under reward** rather than merely instructed. **A finding in the demo's own fixture (law 7 again)**: writing decisions against `case_orchard` surfaced that the case file's boundary geometry had been inverted since the corpus was written — page 2 put the fence west of the registered line and concluded the strip was the respondent's, which the geometry contradicts, as it contradicts page 1's "western side of the fence". One compass word; nothing in the estate could have caught it (pages are content, not schema, and no gate reads a page's prose); fixed, and minted as the consumer register's **F-80** (next fresh id F-81). **The stranger's path, timed**: fresh clone of the committed repo 0.1 s, venv + `pip install 'gsj-harness-rollout-server>=0.1.7' pyarrow tokenizers` from PyPI 40 s, `make_corpus.py` 0.05 s (corpus + drop), `validate` 1.4 s, `up` 38 s — **80 s to a running estate with the thirty embedded** (317 pieces in ~5 s inside the container, store 1.8 MB, drop 444 KB, `work/` 10 MB after the episodes). Rows 62 (b) closed, 70 and 74 annotated, 77 measured; A-28 a new cell; F-80 minted in the demo. Demo commits `6e84d81` + `09490fc`, pushed.

**[CP-83] The audit's phase 1 — source obligations complete; public delivery remains open.** B01/B02/B03/B06/B16 were reproduced, fixed and proven at the estate boundary. The operator chose immediate busy refusal for a second mutating command; phase 1 needed no H200 and consumed none of the booked window. Run names and resolved paths are confined, ordinary record reads validate shape/version/identity, mutations hold per-run exclusion, record publication uses unique temporary files, and failed or unknown cleanup preserves data and exits nonzero. Legitimate partial-run recovery and created/adopted ownership remain. ADR-0036 records the stdlib `fcntl.flock`/`tempfile`/`ExitStack` choice and custom domain checks under R1; the core stays exactly **2,034**, `checks.py` **528**, with no size-law movement. Both source MCP defaults select the already published 0.5.0; known incompatible images with a drop refuse early, and terminal startup/config failures no longer recommend more embedding time. CP-83 freshly measured public 0.1.7's bad default-drop failure at **32.784 s**; the corrected wait against that actual restarting container refused in **0.299 s**, naming 0.5.0. Genuine indexing progress and the recorded SIGSEGV diagnosis keep their explanations.

**The current proofs:** root **176 passed** (17.75 s), corpus **196 passed** (48.02 s; 109 + 87 phase-1 tests), MCP **134 passed** (137.53 s), examples **31 passed** (4.17 s). The startup counterproof gives 18 failures / 2 passes on HEAD versus 20 passes on the corrected source. The fresh four-process × 100 record-write probe gives HEAD **155 successes / 245 incidental FileNotFoundError** versus final source **29 successes / 371 intentional busy refusals**, all 400 accounted for and no temporary-file residue. With an actual `cmd_update` paused, competing up/update/down refused before changing run bytes while status remained available; no unobserved whole-command lost-update effect is claimed. Destructive probes used disposable absolute-name, parent-component, symlink-escape and half-created-run canaries. Two actual Alpine partial estates exercised missing-record normal cleanup and missing-`.env` fallback; an unavailable-daemon wipe refusal preserved their running resources and data, and successful downs took **1.424 / 1.408 s**. An active-endpoint network-removal refusal preserved that endpoint. These canary resources were released. A fresh locally built and installed **18-entry wheel**, still version 0.1.7 but distinct from PyPI (SHA256 prefix `20d94a11f67f6c`), reached default no-drop **verify 7/7 in 23.051 s** and default-drop **verify 7/7 in 21.324 s** (30 files, 313 units, 317 pieces). Its submit accepted in **5.021 s**; the archive was read: one turn, zero tools, 57 trainable tokens, invented pages 2/3 against cutoff 1. The fresh-clone demo against public 0.1.7 accepted the corrected row-2 task in **7.157 s** (up 45.493 s, warm up 12.926 s, down 4.453 s): two turns, one search, 166 trainable tokens, no write, answer errors recorded. Accepted traces establish provenance, not task or citation quality.

The six row-76 source strings now date automatic submit reading from wheel 0.1.7, retain older-wheel guidance and the deprecated entry's earliest 0.1.8 removal bound; gateway environment input remains separate (row 62). CP-82 had already corrected row 76's inference: the recipe said nothing exported, with a conditional old-wheel caveat. Examples/demo docs now agree on release/counts, the demo walkthrough selects row 2, public evidence links use tracked charter/checks authority, F-73 records its existing cure, and all living next-id notices agree on **F-83**. The first implementing phase records CP-82's measurements in wishlist 60/62/64/70/73–77, adds 78 for B04, and annotates fired parks 19/47/50 without taking their source work; B07 stays in existing row 50. **No wheel or image is published here:** B01/B02/B03/B06/B16 remain in public 0.1.7 until phase 3 delivers the source repairs; especially B03/row 77 and the packaged part of row 76 are not closed by a local wheel. Phase 2 inherits B04/B05 and the unanswered credential grammar; phase 4 inherits the consumer evidence/execution findings (F-81/F-82); phase 5 inherits B18's frozen-192-row diagnosis and Mohamed's booked **5 September 23:00–7 September 09:00, GPUs 0 and 7** window; phase 6 awaits the citation-reward decision and truthful fixtures; phase 7 inherits corpus handover and the versioned whitespace decision. Real curation remains owed. The paired metavar/root-test debt, all 24 CP-82 §7 keep decisions and the archived predecessor remain untouched. Push outcomes and final resource/census verification are recorded in the printed, untracked CP-83 report; this paragraph makes no publication or push claim. Capability tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.

**[CP-84] The audit's phase 2 — B04/B05 closed in source and proven with an unpublished installed wheel; public delivery and the frozen root-test expectation remain open.** Phase 1's name/containment, busy-refusal, record and checked-teardown boundaries stay intact. All nine B04 host/service disagreements re-reproduced on CP-83: exact search, false normalization, zero embedding batch/default search count, false page boundaries, a 15-token window, zero synthetic decisions, an unpinned revision and an invalid HF id. `corpus_size >= 1` was CP-77's service constraint, not a host fix. One `MCP_FIELDS` descriptor now drives allowed keys, types, ranges, supported values, fingerprint classification and review text; existing derived compatibility names remain. Actual `ServiceConfig` schema and semantic contract tests run in the service's environment, while the estate command keeps its light dependency boundary. The final local wheel has 18 entries, SHA256 `ddc83b5aacc80c84305e0bdbcc7a67cb8dacbae1e0f45272a470bcc38ecb2237`; its estate payload matches source and its fresh venv has neither torch nor Chroma. No core or service source/image changed; core remains **2,034**, checks **528**.

**The credential decision and proof:** the operator chose an explicit shared grammar. The apostrophe/Compose disagreement and vertical-tab/U+2028 loader truncation re-reproduced. Real Compose 2.40.2 additionally refused odd terminal backslash runs, so the accepted grammar is nonempty printable ASCII U+0020–U+007E without apostrophes or an odd run of trailing backslashes. Controls, DEL, non-ASCII and value-level newline forms refuse. Spaces, internal backslashes and even terminal runs stay literal; generic empty env entries remain absence. Secret-file input preserves one optional terminal LF as framing, but CRLF/multiple LF/embedded separators refuse and spaces are never trimmed. Acquired and minted credentials, writes and legacy loading validate before values can be used or truncated; refusals name the character class and advise rotating or choosing a compatible token without exposing the value. The package reader already refused malformed quoted lines, so no core change was needed. ADR-0037 records this operator-visible contract and the R1 descriptor decision, including the Pydantic/JSON-Schema alternatives and why actual-model tests are still required. Grammar pricing used **389 synthetic contexts**: all passed the two Python readers and shell; Compose rejected exactly three odd-terminal-backslash cases. The **56-case credential suite** includes **384 supported contexts through real Compose** and actual CLI-submit HTTP transport preserving the synthetic credential byte for byte. That local sink deliberately replies 503 and is not represented as an accepted episode.

**Effective config and store compatibility:** nine probes from the installed local wheel now exit 1 with the keyed cure, before a run directory exists, and leave container inventory unchanged. Existing integer/bool restrictions remain; missing model/revision/device/method string checks are newly enforced against service rules. Broader service coercions are an explicit unsupported host-input subset. Additional discriminating regressions cover YAML root/section shapes, valid `on`/`null` model strings and numeric revision strings losing their type in generated YAML, fractional/bool chunk-answer truncation, and malformed recorded residuals overriding dedicated binding fields. Ambiguous strings are quoted only when required; ordinary/default template bytes stay exact. A live overrides file selecting chunk window 212 with explicit CLI 220 produced 220; search 7/9 overrode the template. A plain rerun in **7.456 s** retained exact generated config bytes and recorded residual values and reused the indexes. The retained CP-83 store restarted in **16.923 s**, `index_reused: true`, with fingerprint, bank and refs unchanged; a separate fresh store built by a CP-83 wheel then upgraded to the CP-84 wheel reused in **23.443 s**, with generated config and fingerprint bytes identical. The default batch-32 omission, per-collection identity and every printed consequence class remain.

**Final execution:** corpus **291 passed** (54.60 s; 196 + 95), MCP **164 passed** (140.61 s; 134 + 30). The full isolated root suite is **175 passed / 1 failed** (18.39 s): frozen `test_env_file_grammar_round_trips_estate_py_writer` requires apostrophe emission, which contradicts the operator's new refusal contract. It remains unchanged and its failure is registered as wishlist **80**; no skip, xfail, boundary exception or unapproved root-test edit hides it. An earlier concurrent suite run also timed out in unchanged `test_serve_instructions_survive_a_pipe`; the isolated full run did not reproduce that timeout, and no cause is established. A fresh local-engine episode, session `2ead1db2…`, was accepted in **4.487 s**, then read: one assistant turn, zero tools, 26 trainable tokens, stop termination, no deliverable. It listed pages 1/2/3 instead of parties despite cutoff 1. This is consumer/provenance proof, not answer quality. The initial submit omitted the client's independently derived foreign-corpus pins and failed local G2; the same pins were supplied on both verification legs before submitting the fresh accepted task. No gate was relaxed.

**Scope and inheritance:** phase 2 needed no H200 and consumed none of Mohamed's booked **5 September 23:00–7 September 09:00, GPUs 0 and 7** window; the remote archive was not contacted. Final down took **2.339 s**; all five test ports closed, owned host processes released, and container/network inventories matched the baseline. The three pre-existing GSJ services and workstation engine endpoint remained. Examples/demo/archive code, registers and HEADs stayed unchanged; next fresh consumer id remains **F-83**. Wishlist **64/78** carry source closure and observable public-release proofs; **79** records frozen CI/README/CLAUDE count echoes, and **80** the unavoidable frozen root-test conflict. The full root-green proof is therefore incomplete. Public PyPI **0.1.7** was verified still to lack both fixes: phase 3 must publish phases 1/2, re-prove the installed defaults/config/credentials and then satisfy the image-dependent consumer's rebuild/proof duty. No public wheel/image was released here. All 24 CP-82 §7 keep decisions remain, including canonical-versus-dialable URLs, default fingerprint bytes, the Forgejo tag/digest posture and layout shims. Other audit phases and the archived predecessor were left untouched; no next-phase implementation was drafted. Push outcomes and final scope evidence are in the printed, untracked CP-84 report. Capability tally unchanged: **21 PARITY · 7 DROPPED · 2 GAP · 1 BETTER · 1 TBD**.


**[CP-85] The audit’s phase 3 — library 0.1.8 published and proven.** Release/tag commit `effd658` ships CP-83’s B01/B02/B03/B06/B16 and CP-84’s B04/B05. All seven are now closed for public-wheel consumers: local, TestPyPI and PyPI artifacts are SHA256 `e41023855a323dd879c9ee9554ef2bb1462c75a938b624e8dca490cbd446bc64`; installed estate payload `ddbb661c…` equals phase-2 source. Both public indexes passed the same fourteen checks from fresh external venvs with site-packages/cwd assertions. Check 12: nine keyed early refusals, no run directory/container and equal actual inventories. Check 13: synthetic writer/load/core/shell/real-Compose/submit transport plus class-naming mint/adopt refusals, 28 cases with no skips. Check 14: default published MCP 0.5.0 with a 30-file drop succeeds (313 units/317 pieces), retains `== run <name> ==` / `next — ` and cleans up checked resources. Both installed estates additionally reused config, bank, lock and fingerprint bytes unchanged, then accepted fresh episodes that were read and independently validated. No task-quality inference: the small model’s accepted answers still fail to identify the requested parties.

Row 80’s named assertion now cites ADR-0037: supported values round-trip; apostrophes refuse naming the class before file replacement. Root 176 passed locally (18.71 s); corpus 291 (54.64 s); MCP 164 (141.28 s); collection confirms 176/291/164. Row 79’s four labels now match actual CI. CI **33970588545**: root GREEN (176), corpus GREEN (291), MCP GREEN (164), wheel GREEN. Rehearsal **33970592544**: build GREEN, TestPyPI GREEN, PyPI SKIPPED. Tag release **33971054236**: build GREEN, TestPyPI GREEN, PyPI GREEN; release has three jobs, CI four. PyPI indexing needed four install attempts; the final install used no index flags, and a separate unpinned plain install resolves 0.1.8.

The deprecated entry remains functional in 0.1.8. CP-82 §7.4 protects unknown callers; “no earlier than 0.1.8” permits retirement but does not schedule it. The frozen notice already carries that truthful bound after CP-83, so it stays; docs explicitly retain the entry without rolling the floor again. Rows 64/76/78/79/80 are closed, their publication/Actions events fired. Row 81 records the frozen `estate/README.md` publication-pending sentence and the root helper’s legacy-encoding description. The version sweep classifies current-state changes versus dated history, including the demo tuple. Core 2,034/checks 528, all frozen source byte-unchanged. No H200, archive mutation, vendor change or later-phase work. The image-dependent demo is also delivered at `3286271`: its floor `(0, 1, 8)` and `gsj-polar:f0e8343a-gsj0.1.8` follow publication, with A-28’s two-platform proof above. A fresh GitHub clone plus the exact proposed floor/image patch used an unpinned PyPI host install resolving 0.1.8; up 42.682 s, preflight passed, row-2 submit 8.955 s, read/export/empty quarantine, down 3.550 s. Session `sk-polar-7fb2e7b0-6d5a-4cf3-8c83-b11ac0438fdb`: two turns, one case search, 170 trainable tokens, no deliverable, independent findings []. The extra validation script initially used the wrong trace directory; rerunning that read-only check against documented `work/traces` passed. No product correction or scope expansion was needed. A fresh post-push clone matches all 13 published files; exercised runtime/README bytes match, with only measured evidence added to the ADR after execution. Row 77’s composite publication/default-drop/accepted-read/image event is now closed. Original container inventory restored; no CP-85 processes or estate networks remain. Phase 4 inherits B08–B15/B17 unchanged; B18 stays phase 5, reward phase 6, corpus contract phase 7; B07 remains row 50.


| # | capability | gsj-envloader | here | status | notes |
| --- | --- | --- | --- | --- | --- |
| 1 | corpus contract | `docs/corpus-contract.md` — the normative corpus document | moved at CP-01, byte-identical (zero library references, measured); **v2 since CP-14** | PARITY | landed CP-01 (ADR-0002). **[CP-14] The first deliberate divergence from the predecessor's document (ADR-0015)**: contract v2 makes the train/eval split a directory property (`train/cases/`, `eval/cases/`), retires `eval_case_ids` with a validator rejection naming the migration, and adds the one-case-one-split invariant (rule 5) plus root strictness. The predecessor's corpus stays readable by ITS pipeline (law 3); this repo's pipeline reads only v2 trees, and a v1 tree fails validate with the migration spelled out. PARITY stands on the capability — a normative contract with a strict validator — now with this repo as the document's owner rather than its custodian |
| 2 | retrieval cutoff | timestep T = page cutoff: checkout pinned to `timestep-{T}` branch; MCP per-session cutoff clamp; G5 enforces at collection | injected per episode via `run_steps()` (A-4); the MCP clamp carries over | PARITY | CP-01: the clamp's owner (`mcp-service/`) and the timestep-branch tooling (`corpus/`, `forgejo/`) are here — component-level parity; end-to-end enforcement proven at CP-10; not injectable at all → abandon (§9). **CP-07: proven end to end, the first time an actual episode exercises it** — the harness clones `case_0001` at `timestep-12`, mints the per-episode token in `run_steps()`, renders `.pi/mcp.json`; the MCP service enforced the cutoff from the token's verified claims (every `search_case` result page ≤ 12; census-boundary page 12 itself visible in other samples), the authority logged per call (`docs/polar/pi-corpus/mcp_authority_log.jsonl`), and the adversarial tamper (timestep 12→18, original signature, called from inside the sandbox) rejected 401. The remaining GAP-to-PARITY gap is only G5's trace-side backstop as a `checks.py` validator (CP-10/CP-11) — the enforcement itself is at parity. **CP-10: the backstop landed** (`checks.check_page_cutoff`, row 13) — the page census reconstructs from the trace's own `mcp_gsj_search_case` results and every page > T fails `G5:search_page_gt_timestep`; the residual is where T comes from (row 13(b)). **CP-10 also found a cutoff channel no trace-side check can see, and it is inherited rather than introduced**: `corpus/ingest_corpus.py:601-612` builds each `timestep-{T}` branch as one truncation commit ON TOP OF `main`'s full-document commit, `pi_harness.py:127` clones `--branch … --single-branch` with **no `--depth`**, and `bash` is on the measured wire roster — so `git show HEAD~1:md/page_0018.md` returns a post-cutoff page from inside the sandbox, offline, with no MCP call involved (reproduced end to end with the exact recipe and clone flags; `git log` alone leaks the document's page count). The predecessor is WIDER — it clones the whole repository, every branch (`task.py:826-839`) — so this row's PARITY claim survives, but §5's "nothing past page T visible through any channel" does not, on either stack. G5 is blind to it by construction (the leak is `bash` output, not an `mcp_gsj_*` result). **Fix: `--depth 1` on the harness clone plus dropping the `origin` remote**, at the next `pi_harness.py` freeze-lift (frozen this CP). **[CP-11] FIXED and verified**: the clone step is `--depth 1 --branch timestep-{T} --single-branch` + `git remote remove origin` + `rm -rf .git/logs` (the reflog retained `clone: from <url>` after the remote drop — a CP-11 measurement, so the remote drop alone did not deny re-fetch); reproduction and cure ran in a scratch clone of a recipe-exact `case_0001` (estate torn down on this host): `git show HEAD~1:md/page_0018.md` went from returning the post-cutoff page to `fatal: invalid object name`, `git log` from 2 commits (subject leaking the 18-page total) to 1, `git cat-file -e` proves commit and blob absent, `git remote` empty, no URL under `.git/`, worktree byte-identical (`diff -r`), `read`/`grep`/`find`/`rg` unbroken; regression-tested on the rendered command (`tests/test_pi_harness.py`). **Residual, estate-owned**: anonymous Forgejo read (CP-04: 4 refs/repo anonymous-clonable) lets a URL-guessing agent re-clone over the network — cure is credentialed clone URLs or sandbox egress policy at estate bring-up (CP-04′); shared with the predecessor's estate. The predecessor's wider in-sandbox exposure (whole-repo clone, every branch) stays inherited and unfixed (law 3). **[CP-15] The MCP clamp's MECHANISM changed, the property did not (ADR-0016)**: the service-side filter is now a ChromaDB metadata pre-filter (`where: page ≤ T`, one collection per case) instead of the numpy candidate mask — verified empirically to constrain candidates BEFORE ranking (a post-filter would return fewer than requested and move the recall boundary; the discriminating test aims a query at a fact beyond the cutoff and still receives the whole in-cutoff candidate set), T still sourced from verified token claims only, the SN-serial probes and G5's shape contract green and unchanged (`mcp-service` suite 89 vs the 73 baseline — corrected from 83 at CP-18). **[CP-40] The estate residual DECIDED: production-prep, not permanently accepted** — it lost its owner at CP-09′ and sat unmentioned across ~8 bring-ups (audit O4) because every one was an evaluation estate: synthetic corpus, nothing measured whose value depended on adversarial cutoff evasion. That stops being true at the first bring-up someone intends to train from, so the decision is: the credential/egress choice (credentialed clone URLs or sandbox egress policy — the cure as named since CP-11) is the first production bring-up's, made before episodes run, not a gap to absorb. The demo estate WIDENS the exposure and now carries its own register row (demo F-69): its compose sets no sign-in requirement and its per-episode clone URLs embed no credentials — anonymous read is load-bearing there — mitigated only by nothing being host-published, a mitigation the sandboxed agent is inside of. **[CP-51]** sized: zero library lines — `pi_harness.py:67-74` already strips userinfo from the echoed clone URL and `:137` formats `clone_url_for` as given; the cure is estate-side (a `REQUIRE_SIGNIN_VIEW` compose line, a read-scoped token minted at `up`, the token in `clone_url_for` — ~17 lines) or an egress policy. **[CP-56] The cure is built and the network channel is proven refusable — mechanism (a), credentialed clone URLs + `REQUIRE_SIGNIN_VIEW`.** (a) over egress-policy (b) because (b) must also allowlist the MCP and the engine the agent legitimately needs — it defends everything but breaks the episode unless per-host; (a) defends the *repository*, which is where the leak is, and does NOT defend the model/MCP reachability (they stay open by necessity). The token is env-sourced (the repo's secret-in-env pattern, not a YAML value): `config.py` gained `clone_credential_env` — the field + splice at render, net **+0 lines** (paid for by comment recovery; `gsj_rollout/` holds at 2,000/2,000, no ADR-0012 raise). `pi_harness._strip_credentials` already removes userinfo from the echoed workspace URL (verified with a credentialed URL), so the token never reaches a trace — the checkout's `.git/` holds 0 files naming it. `create_owner.sh` mints a `read:repository,read:user` token beside the push token (idempotent; it clones at 200, is denied push at 403). **Probes, container-faithful** (fresh git container, no credential helper — the sandbox's posture): with sign-in ON, guessing `case_0002.git` and re-cloning own `case_0001@timestep-18` both return 401/auth-required (both succeeded under anonymous read); the harness's own credentialed `--depth 1` clone still checks out `timestep-12` with the CP-11 hardening intact. Probe 3 (a forged later-timestep MCP token) was already refused — `mcp-service` `test_tampered_timestep_reencoded_rejected`/`test_timestep_out_of_range_rejected`, 14/14 green. **The freeze bit (a finding):** flipping sign-in ON breaks two H200 consumers that are FROZEN this CP — the MCP index build (`estate/mcp-service/config.yaml auth_token_env: null`) and the pipeline's scaffold/verify re-clone (`estate/corpus/ingest_corpus.py`: `phase_scaffold`'s `ls_remote_heads` reads anonymously AND `push_repo` re-splices, so no single `--base-url` authenticates both). Both are bring-up-time, not episode-time. The H200 compose therefore ships `REQUIRE_SIGNIN_VIEW` **commented** with the two-phase recipe (build corpus+index anonymous, then flip); the DEMO estate (all consumers lifted) does the flip in `bootstrap.py` as the last bring-up step and closes it there. **Status at CP-56: CLOSED where every consumer is lifted (the demo), mechanism-complete on the H200 pending the frozen-consumer lift.** **[CP-58] CLOSED on the H200 — the parked event fired and the flip is one shot now.** Both frozen consumers lifted to present the one read token `create_owner.sh` mints: `estate/mcp-service/config.yaml` `source.auth_token_env: GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING` (the compose passes the variable, `estate.sh mcp-up` refuses without it, image `gsj-mcp-service:0.4.0` bakes the config — its cold-start fetch of all four cases ran through the token on the closed estate), and `ingest_corpus.py` verify's clone-back reads the same variable (`resolve_read_auth` → `credentialed_url` on the clone and the `ls-remote`; the token redacted from every finding; unset it clones anonymously and a refusal names the variable — measured on the closed estate: FAIL `… terminal prompts disabled (anonymous read — an estate requiring sign-in needs GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING exported)` without it, `verify: PASS (30 pass / 0 fail)` with it). `estate/forgejo/docker-compose.yml` ships `REQUIRE_SIGNIN_VIEW: "true"`, `rollout.h200.yaml` ships `clone_credential_env` set. **Measured across the recreate**: anonymous `info/refs?service=git-upload-pack` 200 → **401**, the read token 200, anonymous API 403. **The three probes, container-faithful on the H200** (the pi-harness image on `gsj-staging-net`, `GIT_TERMINAL_PROMPT=0`, global/system git config nulled — no helper can exist): (1) guess `case_0002.git` anonymously → `fatal: could not read Username for 'http://172.28.9.10:3000': terminal prompts disabled` (rc 128); (2) own `case_0001` at `timestep-18` anonymously → the same refusal; (3) the per-episode MCP token re-encoded 12→18 under its original signature → `HTTP 401 … unauthorized: token invalid: Signature verification failed`, while the untampered T=12 control initialized the session (200) — the channel closed since CP-07, confirmed live. The legitimate harness clone unaffected: `--depth 1 --branch timestep-12 --single-branch` with the token → 12 pages, `HEAD~1` → `invalid object name`, 0 files under `.git/` naming the token. **One episode collected on the closed estate**: `sk-polar-8f3275b6…thinking-off.json` (case_0001@12, `COMPLETED`, `finish_reason: stop`, `gsj_validation.findings: []`), quarantine unchanged at 5, the read/push/admin tokens 0 occurrences in the trace, `gsj_workspace.clone_url` stripped to `http://172.28.9.10:3000/gsj-staging/case_0001.git`, the MCP's request log naming the episode. **Not defended, by design**: the model endpoint and the MCP stay reachable from the sandbox — the agent needs both; a repository defense, not an egress lockdown. **One anonymous reader remains, outside CP-58's lift ("the verify credential only")**: `phase_scaffold`'s post-push `ls_remote_heads` convergence check — a re-*scaffold* of the closed estate fails loudly at its first case; the four staging repos were scaffolded before the flip and need none, and the helper already takes the token. **Status: CLOSED on both estates.** **[CP-59] The one argument landed and the park is resolved**: `phase_scaffold` reads back with `resolve_read_auth(...)` and a refusal is a `PipelineError` naming the variable ("the push itself succeeded"; `scaffold` prints which credential it reads back with), test-pinned (the test fails with the argument removed) and measured on a closed estate `bringup.py` created with sign-in ON from its first start — 4/4 cases converged, no flip, no anonymous phase. The H200's first re-scaffold needs nothing but the two exports. No reader is anonymous. **[CP-64] Re-measured on the H200's own instance under Forgejo 16.0.3** (the CP-62 re-pin applied on the box: 16.0.3 skopeo-loaded, `down`, checkout pulled to CP-63, `up` on the migrated forgejo-data — the admin token survived the migration): anonymous `/api/v1/version` **403**, anonymous `info/refs?service=git-upload-pack` **401**, the read token's `info/refs` **200** and its `ls-remote` listing the four refs; the four repos with their 16 deterministic branch SHAs intact (case_0001 main `29515d3dfc`, the CP-59/CP-62 values). The closed posture is image-move-invariant |
| 3 | git host | Forgejo estate: case repos with timestep branches; compose + bring-up/teardown scripts | moved at CP-01: `forgejo/` (data dir re-rooted inside the component; live H200 estate keeps its compose-project identity) | PARITY | tooling parity — no bring-up ran at CP-01 (out of scope); the H200 networking archaeology (static container IP, `host.docker.internal`) is documented in-file, inherit deliberately or not at all; CP-04: **first live bring-up of the moved components** — Forgejo + `corpus/ingest_corpus.py` scaffold converged on macOS (frozen SHAs reproduced, taskbank byte-identical `9eb8e3c2…`, corpus verify PASS 25/25, MCP census 18/22/15/20); Mac networking needs published ports (host→container-IP is dead on Docker Desktop) while container→container static-IP routing works unchanged — scratch-copy deltas only, both repos untouched |
| 4 | taskbank | `taskbank.py` builds the §3.1 parquet: skill rows resolve at rollout, free rows verbatim | tasks arrive as `(case, timestep, prompt)` via `client.submit`; **[CP-24]** `corpus/ingest_corpus.py`'s `taskbank` phase builds the ADR-0022 bank — flat rows shaped for `render_task_request`, skill cards resolved at build, free rows verbatim | PARITY | CP-01: builder NOT moved — deferred to CP-07 (ADR-0003); the phase raises, verify's row checks deferred with it; the frozen bank + lock carried as data (ADR-0002), still sha256-verified; CP-08: the arrival path is real — `render_task_request` turns the triple into a Polar `TaskRequest` (validated against Polar's own model) and `gsj-rollout submit --case --timestep --prompt` submits it; skill-row resolution stays deferred. **[CP-12] FINAL: GAP, deliberate (ADR-0003)** — the arrival path is real and at parity (CP-08), but the builder and skill-row resolution never landed anywhere: a skill row cannot resolve here, and without `prompt_source` no trace states what the task was (row 9's measured blocker). Deferred with a named owner at CP-01 and still owned; the fix is the `TaskRequest`-shaped builder in `client.py`'s orbit plus `prompt_source` at `config.py`'s next freeze-lift (`docs/VERDICT.md` §wishlist). **[CP-13] Half of that fix landed** — `render_task_request` now takes `prompt_source`/`skill_card_text` and states both in task metadata, so a resolved skill row has a place to declare itself and G1 verifies it (row 9 → PARITY). The row stays **GAP**: nothing here still RESOLVES a skill row — the builder and the resolution step remain ADR-0003's, and until they land every submitted task is definitionally `free` (the frozen `cli.py`'s only truth). What CP-13 removed is the blocker, not the deferral. **[CP-14] The split half is now fully specified even though the builder stays deferred (ADR-0015)**: each bank row carries a `split` field, value `train` \| `eval`, case-level — every row of a case takes the case's directory split as recorded in `corpus.lock.json` `cases.<case_id>.split` — and the builder passes it to `render_task_request(split=…)`, which states it in `TaskRequest.metadata` beside `case_id`/`timestep`/`prompt_source` (landed and test-proven this CP; absent = unstated, never defaulted to train). The deferred implementation has no split decisions left; the row stays GAP on the builder and skill-row resolution only. **[CP-24] GAP → PARITY — the builder lands (ADR-0022; ADR-0003's deferral resolves)**: `phase_taskbank` builds `taskbank.parquet` — one flat row per `(case, timestep, prompt)` carrying the triple, `split` (lock-sourced, ADR-0015's row-spec), `prompt_source`, the free row's verbatim `prompt_text` / the skill row's **resolved** `skill_card_text`, and `sandbox_image` — deterministic (byte-identical rebuilds; sorted rows, fixed schema), sha256 in the lock, `verify` running the row-level half deferred since CP-01 (counts, triples-exactly-once, set-equality with the tree, split/text/image re-derived). A row submits with zero translation (every column is the triple or a `render_task_request` argument — no `config.py` change needed, the CP-13/CP-14 result), and G1's story closes end to end: card bytes → bank text → render-computed hash → task metadata → trace metadata → `check_skill_card` ∈ the pinned set (proven on both real callback bodies, stamped per the CP-13 pattern). The frozen staging bank's 12 triples + splits reproduced exactly; its bytes did not (§3.1 nesting dropped by decision) — lock sha `9eb8e3c2…` → `ae9e0bbd…`. Skill-row resolution is build-time and corpus-level by decision: the sandbox-side instrument stays wishlist 9 |
| 5 | episode isolation | fresh per-episode checkout + ephemeral `docker run --rm` + per-episode gateway actor | Polar sandbox: start/stop/exec/upload/download | PARITY | CP-06/CP-07; CP-02: a fork (yichuan-w) works around two reported Docker-runtime defects — event-loop starvation in `DockerRuntime.start()` and task timeout not killing containers — UNVERIFIED here, check live at CP-06; CP-03: DockerRuntime ran live on macOS (4 parallel sandboxes via docker CLI create/exec/cp/rm, clean teardown observed; the two reported defects stay UNVERIFIED — nothing timed out); macOS networking fact for CP-06: task `network: "host"` does NOT reach the macOS host loopback unless Docker Desktop host networking is enabled — set `node.public_url` to the host LAN IP, which works from bridge and host-net containers *and* from the host-side rollout dispatch (the same URL serves both); CP-06: the LAN-IP topology confirmed again live (sanity + pi runs); `import_path` harness loading verified in the gateway process (PYTHONPATH-provided module, zero vendored edits) — note the module is CACHED after first import, so harness edits need a gateway restart; **operational trap found**: `runtime.workdir` applies to EVERY exec including the harness `setup()` that would create that workdir — `docker exec -w <nonexistent>` fails before setup can run, and because the presets discard exec results the failure surfaces only as "step 0 exited with code 127" with zero records; rule for CP-07: never point `runtime.workdir` at a directory the harness itself creates, and check `setup()` exec return codes loudly; the two reported Docker-runtime defects (event-loop starvation, timeout-not-killing) remain UNVERIFIED (nothing timed out); CP-04 (predecessor-side but platform-relevant): the linux/amd64 pi image runs fine under Docker Desktop emulation on arm64 (13.7 s episode wall), and `--add-host host.docker.internal:host-gateway` reaches host-loopback services on macOS unchanged; **CP-07: the harness ran our pi under DockerRuntime end to end on the real corpus** — clone at `timestep-{T}`, render config, run, download — all as `exec`/`download` against `BaseRuntime` (law 5, image needs only `node`+`git`); two new traps found and cured in `pi_harness.py`: (a) pi's managed-binary installer (ripgrep/fd into `<agent dir>/bin`) renames across filesystems, so a session-bind-mount agent dir silently breaks the built-in `grep`/`find` on every episode (the golden run hit the same class via its ro `/agent`) — the agent dir must be **container-local** (`/tmp/pi-agent`, also non-root-safe: the pinned image is uid 1000); (b) `PI_OFFLINE=1` (the spike's carry-over) gates that download unconditionally regardless of the `--offline` flag, so it is NOT set — pi fetches rg once per episode from GitHub (reachable from the bridge; a per-episode network dependency the golden run also carried). **[CP-12] FINAL: PARITY** — the lifecycle ran live at CP-03 (4 parallel sandboxes, clean teardown observed), CP-06 (`import_path` in the gateway process), CP-07 (our pi under DockerRuntime end to end, fresh per-episode clone), and CP-09 (seven submissions); per-episode isolation held every time. The two fork-reported Docker-runtime defects (event-loop starvation, timeout-not-killing) remain UNVERIFIED — nothing here ever timed out, and unverified is not false (§4) |
| 6 | harvest-before-reset | type-level guarantee: `_reset` requires a `HarvestResult`; artifacts copied out before any git command | Polar's problem — its lifecycle must give an equivalent guarantee | PARITY | CP-05 source audit checks for it; CP-05: the ordering EXISTS but as control flow, not types — `_handle_postrun` runs `_build_session_result` (build+eval, `node.py:505`) before teardown starts (`node.py:513-531`); trace data itself is proxy-time capture into the in-memory `SessionStore`, so trajectory construction never depends on the sandbox at harvest time; **CP-06 live confirmation**: the spike harness's `postprocess()` downloaded pi's in-sandbox transcript and the build produced a full trajectory, both before runtime stop — ordering held; caveat stands: control-flow parity, not the predecessor's type-level guarantee, and the gateway's temp session dir is REMOVED after the session, so anything not downloaded in `postprocess()` (or persisted by the CompletionWriter) is gone; **CP-07: the production `postprocess()` exit works on a real episode** — it downloaded pi's transcript AND the `out/` deliverable into `<artifacts_dir>/<session_id>/` before teardown, keyed by the Polar session id so the trace joins to them; loud-but-non-fatal on a missing `out/` (normal) |
| 7 | token/logprob capture | gateway codec renders the pinned template; token-level loss mask; sampling-time `rollout_log_probs`; capture-once | Polar's proxy + trace reconstruction | PARITY | **CP-09 (Mac pair): capture fidelity verified against the golden** — on identical-context positions (the two traces' 20-token common response prefix, same engine) Polar's captured logprobs agree with the predecessor's at mean |Δ| = 0.000114 / max 0.0018, well inside the contract bounds; discipline clean (finite, ≤ 0, no sentinel, `0.0` only at mask==0); captured values are RAW model logprobs, not sampling-renormalized (measured: raw replay hypothesis fits at the numerics floor, the renormalized hypothesis fits ~6× worse). Three CP-09 caveats: (a) **vllm-metal cannot teacher-force** — `prompt_logprobs_dict={}` is hardcoded (`vllm_metal/v1/model_runner.py:2235`) and the `echo` path 500s (`KeyError` in `_create_completion_logprobs`), so replay-style validation on Mac estates must run beside the serving engine (CP-09 used mlx_lm on the served snapshot; the H200 pair can replay through vLLM proper); (b) **turn≥2 `response_logprobs` are computed under the engine's wire context**, which differs from the merged stream by the ADR-0007 stitched glue ids (4 tokens/prior turn) — verified causally at CP-09 (replay vs wire ctx mean 0.0133 vs 0.0676 against the stream ctx); (c) the row-27 MLX exact-`0.0` artifact recurs on the Polar side (15/363). fidelity was CP-09; CP-02: at the pin nothing value-validates logprobs (the slime adapter checks presence and length only) — vLLM's `-9999.0` sentinel flows to the trainer; our guard supplies a missing check, not a duplicate (row 27); CP-03 live run: with no engine token ids the trace ships empty `prompt_ids`/`response_ids` and null logprobs (mlx-lm's `{"id",logprob}` entries are a dialect the pin's normalizers don't read) — value-level capture genuinely requires vLLM/SGLang (CP-09); also upstream's own sglang meta_info-recovery test FAILS at the pin (engine.py stamping skips on length mismatch → `KeyError: token_id`) — pre-existing test-vs-src drift, verified not introduced by our patches; CP-05: the capture surface line-verified — `prompt_ids` from `choice.input_token_ids`/`choice.prompt_token_ids`/`response.prompt_token_ids` (`record_utils.py:136-140`, NOT int-coerced), `response_ids` from `choice.token_ids`/`response.token_ids` else `logprobs.content` pairing (requires the `token_id` key — mlx's `id` fails at `:38`) else sglang `meta_info` (`:82-107`); NO value-level logprob validation exists anywhere in the vendored tree (grep isfinite/isnan/isinf/9999: zero hits), and the missing-logprob rejection at the pin is STATUS-derived, not config-gated (`adapter.py:120,274-278`; `require_trainable_logprobs` is a kwarg, not a config surface) — checks-spec corrected; `choices[0]` is the only choice ever consumed (`record_utils.py:131-134`) — `n>1` sampling loses every other choice silently; **CP-06**: with a token-id-bearing dialect (the stub: `prompt_token_ids` + `token_ids` + `logprobs.content[].token_id`) the whole capture path works end to end — `prompt_ids`/`response_ids`/`response_logprobs` fully populated in the callback, `0.0` placeholders only at mask-0 interstitials; the engine-prepare additions (`logprobs`, vllm `return_token_ids`, `top_logprobs: 0`) confirmed on the actual wire (stub dump); **the true wire request/response are not persisted or loggable anywhere at the pin** (CP-03 finding 4 sharpened at source: `proxy.py:118-136` builds and posts the outbound body without storing it, sglang `meta_info` is popped before save) — the engine-side dump is the only wire observation point, fine for a stub, GONE on a real vLLM (CP-09 must plan its own capture); pi never asks for `n>1` (wire-verified) so `choices[0]`-only capture is safe for pi traffic, enforced by the subclass `len(choices) == 1` check; **CP-04 platform fact for CP-09**: vllm-metal (vLLM 0.26.0+cpu arm64, MLX backend) speaks the full token-id dialect on `/v1/completions` — token-id prompts accepted, `return_token_ids` honored (`choices[0].token_ids`), `logprobs.token_logprobs` aligned, `choices[0].prompt_token_ids` echoed — so the Mac CP-09 pair has a real engine for the capture path; caveat: MLX/bf16 sampled logprobs round near-delta distributions to exactly `0.0` (20/292 mask-1 positions on the golden episode — row 27); **[CP-09′] H200-confirmed — the final M4-entry status**: capture fidelity holds on the governing platform with the replay run AS WRITTEN (vLLM proper teacher-forces; bit-deterministic, rerun Δ exactly 0.000000); caveat (a) is Mac-only by measurement, caveat (b) is GONE on symmetric-template estates (glue_stitched 0 — the merged stream teacher-forced directly with no F2-shaped excess: collected turn-2 drift 0.0121 vs F2's 0.0676, worse-span direction reversing across traces), caveat (c) recurs (37/510 = 7.3%). NEW and load-bearing for M4: the CUDA cross-request capture-noise floor — capture-vs-replay mean |Δ| 0.005246 (golden, Polar-free) / 0.007141 (collected) against the 0.005 bound, capture-vs-capture 0.003672 on identical contexts (the Mac's 0.000114 was MLX-sequential); invisible trace-side, every discipline rule passes — recorded in checks-spec §CP-09′ |
| 8 | multi-turn stitching | chains over the rendered stream; call offsets cross-checked against mask transitions | Polar `prefix_merging` (A-1 — line-verified at CP-05; **resolved empirically at CP-09, Mac pair**) | PARITY | **the central bet of the whole repo — CP-09 answers it for the Mac pair: PASS WITH FINDINGS** (`docs/reports/CP-09.md`): masks exact per the zero-tolerance row, `prompt_ids` byte-identical, decode-fidelity exact at mask==1 on both traces, glue template constants identical across stacks; nothing attributable to Polar. The one stitching-semantics finding is OURS (ADR-0007): the merged stream carries the stitched generation-prompt glue that the engine's turn≥2 prefill never saw, so turn≥2 logprobs are conditioned on a context 4 tokens away from what the trace implies (row 7(b); the golden's token-in dialect has no analogue). H200 confirmation pending (CP-04′/CP-09′); CP-02: the pin emits `reconstruction_stats` (chains_total, truncated, merged counts) into trajectory metadata — the G7 snapshot is readable receiver-side with zero patches, BUT silent chain truncation still returns COMPLETED, and `trajectory/registry.py` resolves builder strategies by import path — a validating `PrefixMergingBuilder` subclass in `gsj_rollout` is a zero-patch insertion seam; CP-03: real artifacts dumped (`docs/polar/`), live `reconstruction_stats` shape confirmed incl. P1's `raw_completions_total`; DEGENERATION PROVEN LIVE: with empty `prompt_ids` every completion starts its own chain — 10 length-1 chains reported as `full=10, truncated=0`, a clean-looking snapshot with zero actual merging — so G7 must require `chains_total == 1`, never just `truncated == 0`; CP-05 LINE-VERIFIED (A-1): retokenization guarantee + §3.4.2 interstitial split confirmed in code; degenerate-case mechanism confirmed at `prefix_merging.py:399` (`0 < n` guard; each length-1 chain counts `chains_reconstructed_full`); the finalize-loop prefix break (`:212-221`) is defensive dead code (grouping guarantees the pair property — adversarially re-verified); the builder README's "message-level grouping key" does NOT exist at the pin (grouping is token-prefix only — README-vs-code divergence, likely the unlanded `polar`-branch refactor); seven silent-degradation modes catalogued in `docs/checks-spec.md` §silent-degradation, ALL presenting as COMPLETED (CP-12 erratum, surfaced by the verification pass: the catalogue as landed at CP-05 holds NINE modes, S1–S9 — "seven" here and in the CP-05 report is the error; S4′ joined at CP-07); **CP-06: first live MERGED multi-turn chain** — pi 0.83.0, 2 completions, explicit EOT 260: `chains_total == 1`, `full == 1`, `truncated == 0`, merged stream = 119 sampled (mask 1) + 30 interstitial (mask 0) tokens with logprobs aligned and `0.0` only at mask-0 — the stitching layer does the right thing when fed a token-id dialect; token *fidelity* against a real engine stays CP-09's question; **CP-07: first MERGED chain on a real corpus episode + a real defect found** — the vendored grouping FAILS on pi's Qwen3 no-think template (the empty think block `[151667, 271, 151668, 271]` is appended to every generation prompt but not the history re-render, so consecutive pi prompts are never prefix-stable → 2 chains, silently COMPLETED, the S4 shape). Fixed in the subclass with a config-pinned generation-prompt glue stitch before grouping (A-21, ADR-0007, strict-extension only so S3 retries still don't merge); the same episode then merged `chains_total == 1` (441 sampled + 6755 interstitial, logprobs aligned, `0.0` only at mask-0). A stitching-layer defect the CP-06 stub could not surface (byte tokenizer, no template) — exactly the end-to-end-only class this row exists to catch. **[CP-04′] The defect's root cause is CURED at the estate**: under the served symmetric template (`qwen3_training.jinja`, Direction A) the vendored grouping merges natively with `generation_prompt_glue_ids` UNSET — two fresh H200 episodes, `chains_total == 1`, full G7 conjunction, `glue_stitched: 0` (`docs/polar/h200-stitch/`). The CP-09 stitching-semantics finding (F2 — turn≥2 logprobs conditioned 4 tokens away from the merged stream) dissolves at the root on this estate: the merged stream now IS the wire context. The stitch code stays dormant (A-21's fallback); the Mac-pair evidence stands unchanged for its estate; **[CP-09′] The central bet answered on BOTH pairs — the governing one included**: masks exact (zero-tolerance row satisfied on the H200 pair: 2 spans == 2 assistant turns per trace, r=0 open, stream-end close), prompt_ids byte-identical 2965/2965, decode-fidelity EXACT-BYTES at mask==1 both traces, glue framing byte-identical with the pinned G6 tail; native merge held live end-to-end (glue ids unset, glue_stitched 0, full G7 conjunction) and at REPLAY (the merged stream IS the wire context — teacher-forced directly, no de-stitch, nothing F2-shaped). Nothing attributable to Polar; verdict PASS WITH FINDINGS (docs/reports/CP-09prime.md). **[CP-22] The registry seam re-verified at the re-vendored tree** (`ValidatingPrefixMergingBuilder` resolves, MRO `→ PrefixMergingBuilder → BaseTrajectoryBuilder`) — with the finding that the recipe-verbatim venv rebuild BREAKS it (`gsj_rollout` never installed; REVENDOR.md corrected). **And the unlanded refactor this row has tracked since CP-02 is now priced**: simulated as landed, the refactored `build()` keeps a single `status="COMPLETED"` site and the stats dict, so P1/P2's source hunks apply clean against it — the message-level grouping the pin's README promises would arrive with it, which is what would retire the ADR-0007 stitch (dormant since CP-04′) |
| 9 | gate G1 skill_card | sha256 of the rollout-resolved skill-card text ∈ approved set; free prompts pass — **the predecessor read the card from the episode's own checkout** (`gsj-envloader task.py:878-885`) and hashed those bytes itself | `checks.check_skill_card` (CP-13) over the **submit-stated** `prompt_source`/`skill_card_hash` in trace metadata — the same contract on evidence gathered one hop earlier | PARITY | CP-11 decides survival; **[CP-11] approved set derived** (row 23): both staging cards, predecessor values reproduced; "as resolved" == card bytes while skill-row resolution stays ADR-0003-deferred — CP-11b's open question is the trace-side evidence for WHICH card a task resolved. **[CP-11b] DECIDED: unimplementable as specced, blocker named** — nothing on the trace states which card resolved (measured: both real episodes' first user message, 626 chars, neither equals nor contains the 616-byte card), and without `prompt_source` a hash test cannot distinguish a skill row from a free row that must pass n/a. Fix recorded in the spec: state `prompt_source` (+ card hash) in `TaskRequest.metadata` — one line in `config.render_task_request` at its next freeze-lift, natural landing with the taskbank (ADR-0003); the approved set is ready and waiting. **[CP-13] LANDED — GAP → PARITY**: `config.render_task_request` states `prompt_source` (`free` \| `skill:<name>`) in `TaskRequest.metadata` — arriving through the render parameters since `cli.py` stays frozen (its path is definitionally `free`: resolution never happens there) — and, for skill sources, `skill_card_hash` computed at render from the resolved card bytes (convention 1; the real summarize card reproduces the pinned value, test-proven); the taskbank (ADR-0003) passes `skill:<name>` + card text when it lands. `checks.check_skill_card` reads the hoisted statement (the CP-11 channel): `free` passes n/a finding-free, a skill source verifies the stated hash ∈ `skill_card_hash`, anything else — absent, bare `skill:`, unrecognized — fails closed `G1:missing_evidence:prompt_source`, a skill source without its hash fails `G1:missing_evidence:skill_card_hash`. Clean on both real episodes in the post-CP-13 stamped shape; fixture-era bodies (no statement) earn the missing-evidence finding honestly, the golden-mapping precedent. **The delta from the predecessor, named rather than implied**: it hashed the card file read from the episode's own checkout, so a case repo whose `skills/<name>/SKILL.md` had drifted was caught; this hashes a statement made before the sandbox exists, so it catches a wrong or unpinned card but not a drifted checkout. Two residuals, both owned: (i) **the card hash computed sandbox-side** — the instrument the predecessor had — is a wishlist item owned by `pi_harness.py`, not row 4; (ii) tying the *instruction text* to the card (the `<task_id>` substitution semantics) is genuinely skill-row resolution, ADR-0003's, row 4. The API deliberately keeps (i) open: `render_task_request` accepts `skill:<name>` with no card text, states no hash, and G1 fails closed `G1:missing_evidence:skill_card_hash` until whoever reads the checkout supplies it — so ADR-0003 is not forced into submit-side resolution. **[CP-51]** residual (i)'s owner moved at CP-40 and this row never said so: the sandbox-side instrument is production-prep (wishlist 9's [CP-40] note — the first bring-up wanting G1 tamper-evident), not "a `pi_harness.py` lift" nothing schedules |
| 10 | gate G2 system_prompt | sha256 of the wire system prompt ∈ approved set; path-sensitive, collapsed to a singleton by constant container paths | `checks.check_system_prompt` (CP-11b), the `/workspace` singleton set; different sandbox mount paths still change every hash — re-derive walk then | PARITY | expect a re-derive walk when Polar's mounts differ. **CP-10 finding (b), binding on G2 and G6 both — the one genuinely silent hazard the template investigation found**: both pinned chat templates coerce a non-string `message.content` to `''`, and pi sends `user` content as a content-part list, so an OFFLINE re-render of a message log through the pinned template silently produces **empty user turns** — a prompt that never existed, hashed and compared as though it did. Live serving is safe (vLLM flattens content parts before templating), which is exactly why an episode would never surface it. **Rule: any check that re-renders prompts from message logs, or reads message content at all, normalizes content parts first.** Landed as `checks._content_text` (used by the G5 census, tested across four content envelopes); G2/G6 must use it at CP-11 rather than reading `message["content"]`. **[CP-11] approved set derived** (row 23): the `/workspace` singleton property HOLDS on this stack — both real episodes' wire system prompts byte-identical to the derived singleton (4,466 chars, 4,476 UTF-8 bytes), hash reproducing the predecessor's pin; G2 is landable at CP-11b. **[CP-11b] LANDED and validated — GAP-class TBD → PARITY**: `checks.check_system_prompt` hashes every wire `system` message through `_content_text` (finding (b) honored — the typed-parts re-envelope of the same prompt passes, a one-byte edit fails `G2:system_prompt_hash_not_approved`, zero system messages fail closed `G2:missing_evidence:system_prompt`); clean on both real episodes, doctored failures verbatim in the CP-11b report |
| 11 | gate G3 tool_roster | sha256 over canonical JSON of the tools array **as sent on the wire** | `checks.check_tool_roster` (CP-11b) over `trace.tools` — persisted == wire for tools (CP-06) | PARITY | inseparable from row 31; CP-03: the wire tools array IS captured — persisted completion records carry it in both `original_request` and `transformed_request` (`docs/polar/completion_record.json`); caveat: the persisted `transformed_request` is pre-engine-shaping (the `logprobs`/`return_token_ids` fields sent on the wire are absent from disk); CP-05: the MERGED trace's `tools` field is the FIRST completion's transformed-request tools only (`record_utils.py:117-122,150` via `prefix_merging.py:276`) — a mid-session roster change is invisible in the merged trace, so receiver-side G3 must be complemented by a builder-subclass per-completion roster check; **CP-06 ANSWERS the wire question**: three-way diff on live pi traffic (`spike/wire_diff.py` *(at `spike-cp06`)*) shows `tools` byte-identical across `original_request` == `transformed_request` == the engine wire body (neither the transformer nor engine-prepare touches `tools` or `messages`; the wire-only deltas are exactly `logprobs`/`return_token_ids`/`top_logprobs`/`stream`/`stream_options`) — **the persisted `transformed_request` IS the wire form for everything G3 hashes**, so G3 is implementable from captured requests (per-completion, builder-side) and from `trace.tools` (receiver-side, first-completion caveat standing). **[CP-11] approved set derived** (row 23): both real episodes' `trace.tools` canonical-hash to the predecessor's pin exactly — pi 0.83.0 + mcp==2.0.0 generate byte-identical wire schemas under Polar's proxy; G3 is landable at CP-11b. **[CP-11b] LANDED and validated — TBD → PARITY**: `checks.check_tool_roster` canonical-JSON-hashes `trace.tools` against the approved set (predecessor's `store.py` convention byte-exact, `allow_nan=False` with unhashable content a finding rather than a raise); clean on both real episodes, one renamed tool fails `G3:tool_roster_hash_not_approved:<hash>`, an absent roster fails closed; the CP-05 first-completion caveat stands in the docstring, complemented by the builder's `R11` |
| 12 | gate G4 codec | tokenizer.json git-blob OID + chat-template sha256 ∈ approved sets | not landed receiver-side — no codec evidence rides the callback; verified estate-side by the pins walk at bring-up (ADR-0011) | GAP | four distinct hashing conventions across the gates — reproduce exactly. **CP-10 finding (a), the G4 blind spot**: G4 as specced pins the CODEC snapshot's chat template (`Qwen/Qwen3-0.6B` @ `c1899de…`, sha256 `a55ee1b1…`, 4168 chars) while the engine renders with the SERVED snapshot's (`mlx-community/Qwen3-0.6B-bf16` @ `42096995…`, sha256 `87a2728c…`, 4116 chars) — two different files, so the gate would pass without ever having measured the artifact that actually built the prompt. Harmless today and measured to be so (the diffs are confined to `content`/`reasoning_content` type guards; the `add_generation_prompt` tail is byte-identical; both render byte-identically on pi's normalized shapes) — but the binding rule is now recorded in `docs/checks-spec.md`: **G4's chat-template input is the template the engine actually renders with**. CP-04′ fixes it incidentally by adopting a template via `--chat-template <file>`, making the served template an explicitly pinned file. **[CP-11] approved sets derived per the binding rule** (row 23): `tokenizer_hash` = the git-blob OID, measured IDENTICAL across codec and served snapshots (the mlx conversion carries `tokenizer.json` byte-for-byte) and equal to the predecessor's pin; `chat_template_hash` pinned to the SERVED snapshot's `87a2728c…` (4116 chars) with the codec's `a55ee1b1…` (4168) recorded in provenance and deliberately NOT approved (a dead entry weakens the gate). Mac-estate-specific: the served template re-derives at CP-04′ by design. CP-11b's residual is mechanism, not values: where the receiver gets codec evidence to hash. **[CP-11b] The mechanism is DECIDED — ADR-0011: measure-at-serve, at the pins walk — and the gate stays GAP receiver-side with the blocker measured, not assumed**: zero codec evidence rides the callback (both real bodies probed — no fingerprint/tokenizer/template keys anywhere), and the only fingerprint that exists at the pin (`response.system_fingerprint` on the persisted per-completion record, an engine platform string) is not a codec identity and never rides the callback (CP-05). Trust-provenance rejected — the CP-09 F1 shape: it verifies the claim, not the artifact. G4 is verified estate-side by `pins/derive_pins.py` against the served snapshot at bring-up (CP-04′ DoD items 3–5); residual named: per-episode binding (row 22, estate-owned). **[CP-04′] The measure-at-serve walk EXECUTED on the H200, and finding (a)'s fix landed as designed**: the engine serves an explicit template file (`--chat-template staging/serving/qwen3_training.jinja`), so `chat_template_hash` now pins the file's own bytes (`1d944ff8…` — the CP-11 known-expiry note resolves); BOTH snapshot-embedded templates are recorded-not-approved (on the H200 the codec and served snapshots are the same `c1899de…`, so the split that created the blind spot does not exist, and the served file is the one artifact that builds wire prompts); `tokenizer_hash` re-verified unchanged from the H200 served snapshot. Status stays GAP receiver-side by decision (ADR-0011), exactly as before. **[CP-51] Owner named**: the receiver-side half has none by design — no available Polar pin carries codec evidence on the callback (upstream `stable` is one evaluator-only commit past `f0e8343a`), and trust-provenance stays rejected; the actionable residual, per-episode codec identity, is row 22's and is now recorded estate-side by the pins walk's `provenance.engine` block (tokenizer git-blob, served chat-template sha — row 22 [CP-51]). `waiting-on: a Polar pin whose callback carries codec evidence — then a checks.py rule under an ADR-0021 allowance` |
| 13 | gate G5 page_cutoff | pin-free: max checkout page == T, pages contiguous from 1, every search-result page ≤ T | `checks.py`; needs a page census reconstructable from the trace | PARITY | unreconstructable from the trace → abandon (§9) — **not triggered: CP-10 landed the backstop and the census IS reconstructable**. `checks.check_page_cutoff` rebuilds the page census from the trace's own tool-result texts with the two spec regexes, filtered to `mcp_gsj_search_case` (decisions are exempt; a built-in `read` of `md/page_0007.md` cites the already-clamped checkout), and fails `G5:search_page_gt_timestep:{page}>{T}`. Verified on both real episodes (CP-07: pages [1,5,7,9,11] ≤ 12; CP-09: same) and on doctored copies (page 18 at T=12 fails; the same page cited by a decisions result does not). **Two reasons this is GAP, not PARITY**: (a) the predecessor's other two clauses — max checkout page == T and contiguity from 1 — need the CHECKOUT census, a property of the sandbox filesystem that appears nowhere in the trace and is backstopped instead by the `timestep-{T}` clone itself; (b) T currently reaches the check only through the `mcp_gsj_case_status` result's own statement, because nothing puts the timestep into trace metadata — the structural home is `TaskRequest.metadata` via `config.py` (frozen this CP), a one-line CP-11 change, and until then an episode that never calls `case_status` is rejected `G5:missing_evidence:timestep` (fail-closed, loud, and a live rejection risk). **[CP-11] Both reasons resolved — GAP → PARITY.** (b) landed structurally: `render_task_request` puts `{case_id, timestep}` into `TaskRequest.metadata`, verified hop-by-hop by executing the vendored code (dispatch copy `pipeline.py:189`, proxy stamp `server.py:371-377`, trace-top-level hoist `prefix_merging.py:371-375`, `checks._episode_timestep` reads it first); the `case_status` fallback stays as redundancy for fixture-era traces; fail-closed unchanged; reserved metadata keys (`session_id`/`task_id`/`evaluation`/`policy_version`) documented and test-guarded. (a) is **DECIDED: the checkout-census clauses are DROPPED, owner this row** — the checkout census is a sandbox-filesystem property no trace carries; its enforcement is the `timestep-{T}` clone itself (proven live at CP-07) now hardened to `--depth 1`/no-remote/no-reflog (row 2), which closes the only checkout-side bypass ever found; a harness-recorded probe was rejected because the harness attesting its own checkout is the same self-reporting class as the `case_status` circularity, bought with budget lines the law does not have. The trace-side census guards what the agent actually SAW (search results), which is the clause that matters for training data. **[CP-13a] The dropped clauses RETURN — the reason they were dropped no longer holds.** They were dropped because the checkout census is "a sandbox-filesystem property no trace carries"; the workspace echo now carries it (`gsj_workspace`: branch, commit, tree, shallow posture, surviving remotes, page census), captured after the clone and before pi launches, riding the same A-23 channel as the settings echo — hops executed. `checks.check_workspace` enforces **max checkout page == T** and **pages contiguous from 1**, plus the CP-11 clone cure attested per-episode (`shallow=true`, zero remotes) instead of assumed. CP-11's objection — that a harness-recorded probe is "the same self-reporting class as the `case_status` circularity" — is answered rather than waved away, and the answer is scoped: the branch and max-page clauses cross-check the harness's echo against the TRAINER's independently-sourced `timestep`, so those two compare two sources; contiguity and clone posture are single-source and detect an honest misconfiguration (wrong branch, missing `--depth 1`, a truncated or mis-built checkout), not a hostile harness. What it is not: proof against a harness that lies about its own sandbox — that would need an attestation channel this repo does not have, and the row says so rather than implying otherwise. A missing echo fails closed (`G5:missing_evidence:workspace`) |
| 14 | gate G6 thinking_off | every assistant-turn opening ends with a pinned verbatim tail; zero turns fails closed | `checks.check_thinking_tail` (CP-23): tokenizer-free ids-`endswith` against `g6_expected_tail_ids` over the turn-1 `prompt_ids` suffix and each pre-turn mask-0 interstitial; zero mask-1 spans fail closed | PARITY | **[CP-11b] blocker named and the tokenizer-free mechanism designed (ADR-0011)**: neither this package (pydantic/httpx/pyyaml) nor Polar's venv (A-14's five) carries a tokenizer, so the builder subclass is not a home either. The landing design: pin `g6_expected_tail_ids` — the 41-byte tail as token ids under the served tokenizer — on the next pins walk (tokenizer needed at PIN time only, estate-side by construction), then G6 lands receiver-side as an ids-`endswith` over the mask-0 interstitial span preceding each mask-1 span of `response_ids` AND, for the first turn, over the suffix of `prompt_ids` (measured on both real traces: the first mask-1 span starts at `response_ids[0]` and the turn-1 tail sits at the end of `prompt_ids` — a response_ids-only rule would check zero turns on a single-turn episode; per the standing rule G6 reads token ids, never `response_messages`). Blocked this CP by the no-re-pin wall; CP-04′ re-derives the tail anyway (the Direction-A template changes it by design). **[CP-04′] The pin EXISTS — wishlist item 5 done**: `g6_expected_tail_ids = [151644, 77091, 198, 151667, 271, 151668, 271]`, derived and verified by the served tokenizer estate-side (`pins/derive_pins.py` re-verifies whenever transformers is importable). Measured correction to the anticipation above: the Direction-A template does NOT change the tail bytes — the TRL template's generation-prompt branch under `enable_thinking: false` is byte-identical to the pinned template's (turn-1 renders byte-identical across the two) — what changes is G6's SUBJECT: the tail now also appears in history re-renders, so every assistant-turn opening in the merged stream carries it, which is exactly the shape the CP-11b rule design (prompt_ids suffix + per-mask-1-span interstitial endswith) already covers. The rule itself stays blocked on a `checks.py` freeze-lift (CP-11c or later); status GAP unchanged. **[CP-23] LANDED — GAP → PARITY**: the freeze lifted, the budget resolved first (banking 520 → 497, then ADR-0021's raise to a machine-checked 528 — the ADR-0014 earmark lesson answered), and `check_thinking_tail` landed exactly per the ADR-0011 design pins provenance records: ids-`endswith` of `g6_expected_tail_ids` over the turn-1 `prompt_ids` suffix (plus any leading mask-0 run) and the mask-0 interstitial preceding each later mask-1 span; zero spans fail `G6:missing_evidence:turns`; token ids only, no tokenizer, never raises on content. What it asserts under the symmetric template: thinking stayed OFF at **every** turn opening of the merged stream, history re-renders included. Clean on all four real bodies (CP-07, CP-09, the CP-04′ stitch-retirement episode, the CP-09′ H200 fidelity body — the last two being the history-render subject itself); one doctored failure per clause and the single-turn case proven actually-checked (`docs/reports/CP-23.md`). Thinking-on note for Phase C recorded in the spec §G6: as pinned, a thinking-on estate fails every episode loudly — C-2 re-pins, re-conceives, or retires before the first thinking-on episode reaches a receiver. **[CP-28] The evidence half exists (M9a, `docs/polar/thinking/`)**: on a real 15-episode thinking-on collection the gate failed every episode exactly as designed (G6-only findings, fail-closed, quarantined with forensics, gate unweakened), and every one of the 41 turn openings ends `[151644, 77091, 198]` — the empty-think tail appeared zero times. The measurement favours **re-pin as per-mode pin data**: the 3-id tail is not an `endswith`-suffix of the 7-id tail, so a thinking-on estate pinning it ALONE keeps the gate mode-asserting (thinking-off openings fail it); `pins/` data plus a walk, zero `checks.py` lines, 528/528 untouched. Decision and landing stay C-2's. **[CP-30] C-2 LANDED — re-pin as per-mode pins data (ADR-0024), and the gate is now MODE-DEPENDENT, recorded here**: `pins/thinking-on/pins.gsj.json` is a complete pins document — six non-G6 approved sets byte-equal to the primary's (drift-guarded by `derive_pins.py`), G6 keys carrying the 3-id tail — and the mode reaches the check as the pins FILE the estate selects via `GSJ_PINS_PATH` on both law-6 legs; `checks.py` reads the same key through the same `approved_set` call, byte-unchanged at 528/528. What the gate proves, per mode: **off** — every assistant-turn opening carries the pinned empty-think block, i.e. thinking was OFF at every position the template could have shown it; **on** — every opening ends at the pinned bare generation prompt, i.e. template integrity plus the assertion that the estate genuinely ran thinking-on (no opening carries the off signature) — it no longer proves thinking-suppression, because thinking is on and rides mask-1 sampled content outside any opening. Mode-asserting in BOTH directions by the non-suffix geometry, test-proven both ways (the CP-28 quarantined exemplar passes the full seam under the on-pins and reproduces its recorded quarantine findings byte-stable under the off-pins; a real off trace fails the on-pins). Proven live at CP-30: one thinking-on and one thinking-off episode through the real receiver, both accepted clean, `chains_total == 1` (`docs/polar/thinking-on/`). The estate owns `harness.thinking`/pins agreement — a mismatch fails every episode loudly, the correct failure. Status stays PARITY with the mode-dependence stated: in on mode the gate is deliberately the weaker template-integrity + mode assertion |
| 15 | gate G7 no_compaction | settings canonical-JSON hash + `compaction.enabled == false` + chain snapshot exactly (1 chain, 0 rollbacks, 0 dropped tokens, 1 finalized) | `checks.check_chain_snapshot` (CP-11b) + `checks.check_settings_echo` (CP-13): the CP-05 stats conjunction on `reconstruction_stats` ∧ the settings-hash clause over the harness's echoed rendered settings | PARITY | CP-02: abort→ERROR defect (D3) CONFIRMED at the pin — a mid-chain abort presents a *clean* snapshot, so the snapshot alone cannot satisfy G7's premise; carried patch P2 (abort→session ERROR) is the guard, and `checks.py` adds a `finish_reason` allowlist that catches tail aborts for free; CP-03: P2 landed, adversarially verified faithful, abort tests green, and the propagation chain (builder ERROR → node → SessionResult → slime FAILED → zero loss mask) re-verified link-by-link at the vendored tree; the live run adds the second G7 requirement — a token-id-less backend produces a CLEAN snapshot of N length-1 chains, so require `chains_total == 1` too (row 8); CP-05 tightens the equalities again: require `chains_total == 1` ∧ `chains_reconstructed_truncated == 0` ∧ `completions_merged == completions_total` ∧ (with A-12 verified) `raw_completions_total == completions_total` — filter amputation of a chain TAIL still counts `chains_reconstructed_full` (the `kept == len(chain)` test runs against the post-filter chain, `prefix_merging.py:261-262`) and is invisible to the first two conditions alone; CP-06: the full conjunction observed holding on a real pi multi-turn session (2/2/2/1/0) — the rule is satisfiable in practice, not merely specifiable. **[CP-11] approved set derived** (row 23): `settings_hash` reproduces from the harness's own rendered constant (`{compaction:{enabled:false}}` — the same parsed document, canonical-hashed); G7 is landable at CP-11b. **[CP-11b] The stats conjunction LANDED and validated — TBD → PARITY, with the settings clause a named in-row residual**: `checks.check_chain_snapshot` (session-level — the stats ride `trajectory.metadata.reconstruction_stats`) enforces the CP-05 conjunction verbatim, one byte-stable finding per violated clause, any missing/non-int stat failing closed; clean on both real episodes, all four doctored clauses fire each for its own reason. The residual, honest: **the settings-hash clause has no callback evidence** (measured: zero `settings`/`compaction` occurrences on both real bodies) — compaction-off is enforced at source by the harness's `settings_json` constant (the exact document `settings_hash` pins), but the receiver cannot verify what it never receives; fix is a one-line harness echo into trace-reachable metadata at `pi_harness.py`'s next freeze-lift. PARITY claimed on the degeneration-catching half (the conjunction — the clause CP-03 proved `truncated == 0` alone is blind to), not on the unverifiable clause. **[CP-13] The settings residual is CLOSED**: `PiHarness.setup` echoes the rendered settings document — the object written into the sandbox settings.json, not a template — into the session's gateway-registry metadata (`SessionRegistry.register` on the existing id merges under the lock with status preserved, `session.py:87-88`; A-23: harness and proxy share the gateway process by the `import_path` architecture), from where the CP-11-proven channel carries it: proxy stamp onto every completion (`server.py:371-377`) → builder hoist into trace top-level metadata (`prefix_merging.py:371-375`) — all four hops EXECUTED against the real vendored classes in the component venv, not read. `checks.check_settings_echo` canonical-hashes the echoed document (convention 2) against `settings_hash`; a missing echo fails closed `G7:missing_evidence:settings`, a compaction-ON echo fails `G7:settings_hash_not_approved:<hash>`. The registry-absent case raises loudly at `setup()` (the unechoed episode would be rejected fail-closed at the receiver anyway; earlier is cheaper). Honest limit unchanged: the echo is the harness's own statement — self-reported evidence, law 6's declared class. **[CP-22] P2 re-applied byte-faithful at the re-vendor rehearsal** (clean by script, reverse-apply exact, abort tests green), and the named refactor risk is priced: P2's anchor — the single `status="COMPLETED"` finalize site — SURVIVES today's `polar`-branch refactor (dry-run applied clean in the scratch simulation, `session_had_abort` landing immediately at the finalize site); no upstream abort→ERROR path exists anywhere (zero `abort` occurrences in the refactored builder), so P2 stays ours |
| 16 | quarantine | two layers: hygiene (any gate failure ⇒ never served, kept for forensics) + row-level cap-quarantine | receiver drops failing traces at the source; no store to quarantine into | DROPPED | dropped with the store (§3); the at-source rejection half survives by law 6 — forensic retention is the trainer's problem; CP-02: `node._push_result` → callback → our receiver confirmed as the natural zero-patch checks home; upstream's own failed experiment (a `had_abort` metadata flag dropped in Polar→slime serialization) says validation-critical signals must ride status/structural fields, never metadata flags; CP-03: one real callback payload dumped (`docs/polar/callback_session_result.json` — the exact `node._push_result` body); NOTE the rollout server's persisted `ses_*.json` is NOT that body — `_storage_payload` strips `trajectory.status`/`trajectory.error` before writing — the receiver must validate the POSTed payload, never reconstruct it from rollout disk; CP-05: strip confirmed disk-only at `pipeline.py:423-436`; the callback endpoint validates pydantic shape only (`rollout/server.py:170-173`); and the rejection seam is REAL — a builder-subclass `status=ERROR` survives the whole path because the node only escalates, never clears (`node.py:579-587,602-610,615-624`; eval merge preserves status, `:700-738`); **CP-08: the at-source half LANDED** — the receiver validates the POSTed body through `checks.validate_session_result` and quarantines rejects to `<quarantine_dir>/<session_id>.json` (CP-08's shape; since CP-33 the filename stamps the pins mode — `<session_id>.<pins-mode>.json`, F-48 — [CP-41], audit S13) carrying the findings AND the full body (forensics beat counters, ADR-0008 §2), answering Polar 200 either way (rejection is our decision, not a delivery failure); fixture + doctored bodies tested; the trainer-side retention story stays the trainer's |
| 17 | store | append-only content-addressed Parquet `TrajectoryStore` | — | DROPPED | trainer's problem |
| 18 | ready/mix | pinned predicate grammar + composition planner | — | DROPPED | trainer's problem |
| 19 | staleness | `policy_lag` vs the shared version counter; teacher tapes null-lag by definition | — | DROPPED | trainer's problem |
| 20 | serve accounting | lease-based serve/commit in one transaction; `serve_count`; SPI thermostat | — | DROPPED | trainer's problem |
| 21 | collation | four shipped collators (`Default`/`SFT`/`OPD`/`RLVR`); no truncation anywhere by design | — | DROPPED | trainer's problem |
| 22 | provenance | `env.provenance`: the four evidence hashes, codec fingerprint, applied sampling block, exact invocation argv | trace metadata must carry an equivalent | GAP | CP-08/CP-09; CP-02: pin bug — anything a hook adds to `record.metadata` in memory never reaches the persisted completion files (the writer enqueues `dict(metadata or {})`, not `dict(record.metadata)`); P3 carries the fix; provenance must not rely on in-memory metadata mutation; CP-03: P3 landed and verified — the persisted record's metadata is now record-truthful, so provenance MAY ride `record.metadata` and reach disk; inertness confirmed on a real persisted record (no `policy_version` key with no declared version); CP-05: builder-subclass metadata keys survive to the callback verbatim and into slime `Sample.metadata["polar"]` (`adapter.py:141-160` deep-copies both trajectory and trace metadata); the key `evaluation` is RESERVED (overwritten by the eval merge, `node.py:737`); chain-level trace metadata presents the FIRST completion's values as the chain's (`prefix_merging.py:371-375`) with no homogeneity check — per-turn truth lives only in the `completion_metadata[]` list, so the receiver's "all per-turn stamps equal" rule must iterate that list, and the `prefix_merging cross-version fallback` referenced by a `storage.py:150` comment does NOT exist in the vendored builder (fork half, deliberately not carried); **CP-07: the builder-subclass metadata channel used for real** — `gsj_validation` (builder id, `findings`, `glue_stitched`) rides the callback verbatim (`docs/polar/pi-corpus/callback_session_result.json`), never touching the reserved `evaluation` key; the harness's `postprocess()` artifact directory is joined to the trace by the session id, the provenance seam CP-08/CP-09 build on; CP-08: the receiver persists the full callback body verbatim (status/error intact) at `<traces_dir>/<session_id>.json` (CP-08's shape; `<session_id>.<pins-mode>.json` since CP-33 — F-48; [CP-41], audit S13) — same join key as the artifact dir; provenance *content* (the evidence hashes) stays CP-09+. **CP-09 sampling-provenance finding**: pi sends no sampling parameters, the wire is not persisted (row 7), and nothing on the trace records what sampling the engine applied — the applied block is knowable only from engine-side evidence (the serve argv + the engine request log) and is therefore ESTATE provenance, not trace provenance. The served mlx-community conversion ships no `generation_config.json`, so an unpinned engine silently samples pi's parameterless requests at vLLM neutral defaults (T=1.0 — CP-07's episode did exactly this); CP-09 pins `--generation-config <dir>` with the codec snapshot's file (sha256 `2325da0f…`) and verifies application from the request log. Any future provenance surface must carry the engine's generation-config pin. **[CP-12] FINAL: GAP, half deliberate** — the CHANNEL is proven end to end (builder metadata → callback → slime, CP-05/CP-07; `{case_id, timestep}` structural since CP-11; artifacts joined by session id), but the predecessor's provenance CONTENT does not ride the trace: the applied sampling block is estate provenance (CP-09 F1 — knowable only from the serve argv + request log), the codec identity is estate-verified at the pins walk rather than stamped (ADR-0011 — zero codec evidence on the callback, measured), and no image tag or argv is stamped anywhere. The deliberate half: trust-provenance was REJECTED for cause (ADR-0011 — verifying a claim instead of the artifact is the F1 shape). The open residual: per-episode binding — nothing ties episode N's traces to the bring-up measurement; the cure is an estate provenance surface at CP-04′ bring-up, outside this repo by the scope law. **[CP-13a] The CORPUS half of the residual closes**: the workspace echo binds each episode to the exact commit and tree it ran against (`gsj_workspace.commit`/`.tree`, plus the credential-stripped clone URL and the page census), so "nothing ties episode N to what it actually read" is no longer true for the corpus. The CODEC and SAMPLING halves are untouched and stay estate-owned (ADR-0011, F1) — the echo is the harness's view of the sandbox filesystem, and the engine's identity is not visible from there. **[CP-40] The binding residual DECIDED: production-prep, not permanently accepted** — the cure was named "at CP-04′ bring-up" and CP-04′ ran without it (audit O5); no evaluation CP owns an estate to build it on, and pretending a future lift will is the decayed park §8 rule 9 now forbids. The decision: per-episode binding (tying episode N's traces to the bring-up measurement — serve argv, generation-config, codec identity) is REAL work the first production bring-up must do; accepting it permanently would leave trained-on traces unattributable to engine identity, the exact F1 lesson. The sampling half's rebirth as wishlist row 38 (CP-35, the demo's attestation residual) is cross-referenced both ways as of this CP — one residual, recorded twice, now owned once: by production bring-up. **[CP-51] NARROWED, estate-side, zero library lines**: `pins/derive_pins.py` now states the ENGINE beside the values it measured — served model name (asked of `GSJ_SERVED_ENDPOINT`'s `/v1/models`; its revision if reported, else a named absence), the snapshot revision, and the sha256 of the generation config (the file `--generation-config` points at), the tokenizer (git-blob) and the served `--chat-template` file — and `--record` writes that block into BOTH pins documents' `provenance.engine`, refusing if any approved value would move (CP-41's standard). The receiver names every archive for the pins file its process resolved (`<session_id>.<mode>.json`, CP-33), so an archived trace is attributable to the engine of the walk that produced its pins. Recorded THIS CP: the mechanism only — no estate ran; on this host the block prints with the served-model line a named absence and the snapshot hashes matching the pins (`2325da0f…` generation config, `1d944ff8…` template), and no pins document was written (the H200 walk with `--record` writes it). NOT covered, named: an engine restarted mid-run without a re-derive, and the serve argv itself (the walk reads the generation-config FILE, not the engine's applied defaults — wishlist 38's attestation half). **[CP-58] RECORDED for real — the H200 walk with `--record`, before the CP's episode.** The walk reproduced every approved value on the box (including the tokenizer leg, ADR-0011's estate-side verification: `g6_expected_tail_ids` re-derived through the served tokenizer) and wrote `provenance.engine` into both pins documents with the `pins` objects byte-identical after parse. Field by field: `served_model.id`/`.root` `Qwen/Qwen3-0.6B` ← `GET http://127.0.0.1:8000/v1/models` (the live engine, GPU 4); `served_model.revision` a named absence (vLLM's `/v1/models` carries none — CP-51's prediction); `snapshot_revision` `c1899de2…` ← the served snapshot's path, and the engine's own argv says `--revision c1899de2…`; `generation_config_sha256` `2325da0f…` ← the snapshot's file, byte-equal to `~/gsj-vllm/genconfig/generation_config.json` that `--generation-config` points at; `tokenizer_git_blob_oid` `949e1ec8…` = the approved `tokenizer_hash`; `chat_template_sha256` `1d944ff8…` ← `estate/serving/qwen3_training.jinja`, byte-equal to `~/gsj-vllm/qwen3_training.jinja` that `--chat-template` renders with = the approved `chat_template_hash`. Every value names its source, every absence its reason, and the two cross-checks the prompt feared (a foreign snapshot, a template that isn't the served one) were measured false by sha256 on the box. One cosmetic: the writer's `json.dumps(indent=2)` re-serialized the hand-formatted one-line `g6_expected_tail_ids` array one id per line (same value). The residuals are unchanged and still owned by production bring-up: an engine restarted mid-run without a re-derive, and the applied-sampling attestation (the walk reads the FILE). This record is the **evaluation** estate's engine — a production bring-up owes its own. `waiting-on: the first production bring-up — its own --record at its serve (CP-58's record is the eval estate's); the mid-run-restart residual and the applied-sampling attestation stay its` |
| 23 | pins | `gsj-pin`: approved-set JSON, generated data, zero hash literals in code | `derive_g2.py` + captured evidence carried (`pins/`); the pinned VALUES did not move — stale by construction under Polar's mounts (ADR-0002); the `gsj-pin` generator is predecessor library code and stayed frozen there | PARITY | deliberate: no valid approved sets exist here until the derive → re-pin → first-episode-validate walk under Polar's mount scheme (CP-07/CP-10/CP-11); the format `checks.py` consumes is specified in `docs/checks-spec.md`. **[CP-11] The walk ran — GAP → PARITY**: `pins/pins.gsj.json` (format `gsj-pins/1`, one provenance block per key: episode, artifact, host, Mac-specific flag) holds this repo's first valid approved sets, every value derived from repo-owned or estate-resident evidence — G3 from both real episodes' wire `tools` (convention anchored on `pins/tools.captured.json`), G2 from both episodes' wire system prompts (the `/workspace` singleton holds here, byte-identical across episodes), G7 from the harness's rendered constant, G1 from the staging cards, G4's tokenizer OID from both snapshots (identical) and its template pinned to the SERVED snapshot per finding (a), codec hash recorded-not-approved. Every derivable value reproduced the predecessor's pin — "stale by construction" measured out as value-stable under docker mounts, with provenance now this repo's own. `pins/derive_pins.py` re-runs the whole walk and fails loud on divergence (CP-04′ reruns it; served template diverges there by design). Residual: the first-episode-VALIDATE leg needs a consuming gate + a fresh episode — CP-11b, STOP-walled here. Only `chat_template_hash` is Mac-estate-specific. **[CP-11b] The validate leg is DONE — the row CLOSES**: gates G2/G3/G7 consume `pins/pins.gsj.json` at check time (`checks.approved_set`, repo-relative `PINS_PATH`, missing file/key raises — never fail-open, and a snapshot test proves no pinned value appears as a literal in `checks.py`); both real episodes pass the full seam clean and every landed gate fails on one doctored input for its own reason (verbatim lines in the CP-11b report). "Fresh episode" was STOP-walled again (no estate), so "first episode" = the two real episodes this repo owns — the same two the sets were derived from; a genuinely fresh episode first passes these gates at CP-04′/CP-09′. **[CP-16] The seam grew the resolver leg (ADR-0017)**: `PINS_PATH` = `GSJ_PINS_PATH` override → checkout → the wheel's packaged copy (`pins/pins.gsj.json` force-included at build, single source) — the trainer leg works from a wheel, and a foreign estate that skips the override fails loudly as `*_not_approved` (set membership), never silently. **[CP-19] And now it SAYS so (ADR-0019)**: on the third resolution case only — an installed wheel with no `GSJ_PINS_PATH` and no checkout, which is exactly the PyPI stranger — `checks` emits one `UserWarning` at import naming the packaged path, stating that these are the reference estate's approved sets rather than defaults, and naming the cure. Silent under an explicit override (the operator has chosen) and under a checkout (a developer is in-tree); a warning and never a raise, so the fail-closed posture and every rule body are untouched. The packaged copy cannot drift from `pins/` (force-included from it, never duplicated), so a re-pin costs a checkout consumer nothing and costs a published artifact a rebuild — a wheel is a snapshot of the approved sets as of its build |
| 24 | deterministic env pinning | uni-agent by SHA; sglang exact-pinned; generated `collector-requirements.txt`; image tag in provenance | Polar vendored by SHA (law 4) + pinned pi 0.83.0 | PARITY | CP-03: the Polar half landed — `/POLAR_SHA`, patched tree committed, component venv per upstream's own recipe. **[CP-12] FINAL: PARITY** — Polar pinned by SHA with recorded recipe and carried patches (CP-03, `vendor/REVENDOR.md`), pi 0.83.0 restored from the predecessor's byte-exact lockfile via `npm ci` (CP-06 image), upstream's own `uv.lock` kept, component venvs recreated per recipe (never moved — CP-01's rule), the sandbox image a pinned config value (law 5). The one predecessor clause not reproduced — identity stamps riding TRACE provenance — is row 22's GAP, not a pinning gap. **[CP-22] The pin is now proven REPRODUCIBLE, not just recorded**: the re-vendor rehearsal re-fetched `f0e8343a`, re-extracted, re-applied the patch set by script, and produced a tree byte-identical to the committed one (`git diff HEAD -- vendor/` empty; reverse-apply walks back to the pristine pin exactly) — A-8 resolved, mechanical cost ~2 minutes, `vendor/REVENDOR.md` corrected where execution proved it wrong (the A-14 venv install, the byte-fidelity tripwire, the conditional smoke) |
| 25 | one-YAML config | one YAML is the complete construction surface for both sides | `config.py`: seven sections + reserved free-form `user:`; renders Polar's `topology.yaml` and `TaskRequest` bodies | PARITY | CP-08 (ADR-0008 §1): GENERATE, not sit-beside — the server renders the topology, the trainer renders task requests, from the same file; both renders golden-tested AND validated against Polar's own `TopologyConfig`/`TaskRequest` models; unknown keys raise naming section+key; `user:` is validated as a mapping and never read (the predecessor's §9 pattern) |
| 26 | bounded collection | `gsj-collect`: bounded rounds, graceful drain, stated exit codes | `gsj-rollout submit`: bounded wait (`--timeout` + `--grace`), one progress line per state change, stated exit codes (0/1/2/3), SIGINT-clean `serve` | PARITY | H-34's table stakes landed at CP-08. **The row's question, ANSWERED** (stated in `config.py` and `submit --help`, ADR-0008 §5): a COLLECTED episode = status `COMPLETED` ∧ `gsj_validation.findings == []` ∧ zero `checks` findings — ERROR/TIMEOUT never count; `--episodes N` targets **N attempts** (`num_samples=N`), NOT collect-until-N-accepted (Polar's scheduler owns episode counts); a rejected trace counts as a consumed attempt, is quarantined, and is never retried automatically — exit 1 says collected < attempted. The predecessor's `truncated`-counts ambiguity has no analogue by construction: our builder flips truncation-class defects to ERROR (CP-07) |
| 27 | logprob sentinel guard | validators require `rollout_log_probs` finite and ≤ 0 everywhere — written to admit the `0.0` that record semantics place at mask==0 positions | `checks.py` guards the `-9999.0` sentinel with an **explicit threshold rule** — the finite-and-≤0 rule alone passes it (A-7 audit, spec corrected) | **PARITY** | **RESOLVED at CP-10 — landed and platform-conditioned.** `checks.check_logprob_discipline` implements the whole spec section: `LP3` sentinel (≤ −9000.0 at `mask==1`, `CheckPolicy.sentinel_threshold`), `LP1` absent array on a trainable trace, `LP2`/`LP8` length rules, `LP4` NaN/±inf (Python's `json` really does accept those literals off the wire), `LP5` positive, `LP7` the empty-mask validator escape, plus `TR1` the `finish_reason` allowlist and `TR2` the reasoning-mask re-vendor canary. **The row-27 question itself — the suspicious zero — is answered as an allowance, not a hard fail**: `CheckPolicy.zero_at_mask1_max_rate`, default 0.25 of `mask==1` positions, against CP-09's measurements on BOTH stacks (golden 20/292 = 6.8%, collected 15/363 = 4.1%, both otherwise discipline-clean, both bf16 rounding of genuinely-near-zero RAW logprobs — the raw replay hypothesis fits at the numerics floor, the renormalized one ~6× worse). 0.25 is ~3.6× the higher measurement: no measured trace trips it, a degenerate mostly-zero array still does, and a CUDA estate restores the original strictness with `0.0`. A knob rather than an engine sniff because the trace carries no engine identity (row 22). Fixture-verified: the CP-09 trace, the CP-07 trace, and the predecessor's golden tokens all pass clean; one doctored trace per rule fails with its exact finding string. Replay-style validation deliberately NOT built (CP-09 F2–F4; reasons recorded in `docs/checks-spec.md` §Replay). Earlier notes: CP-02: upstream has no value-level guard at all, so ours is load-bearing; also make absent/None `response_logprobs` a hard failure; CP-05 corrections: (a) the pin's missing-logprob rejection is STATUS-derived, not config-gated — `require_trainable_logprobs` is only a kwarg fed from `trainable = status not in (ABORTED, FAILED)` (`adapter.py:120,268`); a trainable trace with any `mask==1` and no logprobs RAISES trainer-side — our receiver rule stays because it fires earlier and on both sides; (b) zero value-level checks tree-wide re-confirmed by grep; (c) `models.py:116` lets an EMPTY `loss_mask` bypass the length validator — `checks.py` must hard-fail an empty mask on a trainable trace, never inherit that escape; (d) the builder's `0.0` placeholders can never land at `mask==1` (`prefix_merging.py:364,368` — any missing trainable slot nulls the WHOLE array first), so a `0.0` observed at `mask==1` is engine-reported and our suspicious-zero rule stands; **CP-04 measured a false-positive surface**: on vllm-metal (MLX bf16) 20/292 mask-1 sampled logprobs are engine-reported as exactly `0.0` (near-delta renormalized distributions under top_k 20 round to p=1.0) — the golden episode is otherwise clean, so the rule as specced would reject genuine Mac-pair traces; CP-10 must decide platform-conditioning (e.g. rule active on CUDA engines, demoted to counter/warn on MLX) instead of silently inheriting either behavior. **CP-09 confirms the artifact recurs on the Polar side** (15/363 mask-1 logprobs exactly `0.0` on the collected trace, 20/292 on the golden — same engine, both otherwise discipline-clean), so the platform-conditioning question is now symmetric across both stacks, and CP-09 additionally measured that captured values are RAW model logprobs (row 7), so the near-delta `0.0`s are bf16 rounding of genuinely-near-zero raw logprobs, not renormalization semantics. **[CP-04′] The conditioning premise "a CUDA estate restores the original strictness with `0.0`" is MEASURED FALSE**: on the H200 (CUDA vLLM 0.26.0, bf16, native) exact-`0.0` at `mask==1` recurs on every episode both stacks produced — golden 16/258 (6.2%), our stack 34/237 (14.3%), and 2119/8506 (24.9%) on a repetitive-loop episode that came within 0.1pp of the 0.25 allowance. The artifact is bf16-near-delta rounding, not an MLX platform quirk; the strict-0.0 policy rejected a clean H200 episode live (the receiver did its job — fail-closed, loud) before the estate config moved to the 0.25 default. Two consequences, recorded: (a) the H200 estate runs `zero_at_mask1_max_rate: 0.25` (`staging/rollout.h200.yaml`), not 0.0; (b) repetitive-loop episodes push the rate toward the boundary — the allowance is doing real work on CUDA, and CP-09′ should treat the zero-rate as a measured platform property, not a defect signal **[CP-09′] corroborated live, twice**: the qualifying clean episode measured 37/510 = 7.3% (golden 16/258 = 6.2% — the pair's 3rd/4th in-allowance CUDA measurements), and the receiver REJECTED a repetitive-loop episode at 2181/8192 = 26.6% > 0.25 during collection (attempt 2) — the allowance is load-bearing on CUDA, fail-closed and loud, exactly as this row predicted |
| 28 | async staging | no capability by this name; nearest referents: per-episode asyncio gateway loop, collector streaming rounds | the receiver is a callback endpoint — asynchronous by construction | PARITY | pinned down at CP-08: at our layer this means only that results arrive by push (the threaded receiver accepts callbacks without the trainer blocking) while the client polls independently — nothing more survives from the predecessor referents. Finding recorded en route: the node's per-session callback is pinned to Polar's own rollout server (`pipeline.py:184` overwrites the dispatch `callback_url`), so the zero-patch push channel to us is the manager's **task-terminal** `TaskResult` envelope (`TaskRequest.callback_url`, `manager.py:164-179`) — per-session push immediacy would need a vendored patch; the client's poll path is unaffected |
| 29 | multi-provider harness support | deliberately single-harness: pi via pinned uni-agent; "provider" meant only the pi models.json id and the tool-call parser | Polar's `import_path` runs arbitrary harnesses; we need only pi | BETTER | **[CP-12] FINAL: BETTER** — the predecessor is single-harness by design; Polar's `import_path` loaded OUR non-preset harness into the gateway process with zero vendored edits (CP-06) and ran it end to end on real corpus episodes (CP-07/CP-09), and the pin ships eleven preset harness modules (`src/polar/agent/presets/`, counted at CP-12 — the prompt's "nine" is the only correction; pi's own preset pins 0.67.68, which is why we bring our harness). BETTER claimed on the mechanism, exercised by construction — our harness IS an arbitrary harness; only pi was ever run here, deliberately |
| 30 | HPC runtime | none — Docker-only, single H200 host, SSH-tunnel topology | Polar supports Apptainer natively; deferred by A-11 | TBD | potential BETTER; law 5 keeps it free; CP-02: two forks (leeyykk, skzhang1) independently rework `runtime/apptainer.py` on real clusters (direct-exec instead of instance start/stop, dropped resource limits, proot wrapper) — field evidence the pin's Apptainer runtime needs work before A-11 is exercised. **[CP-12] FINAL: TBD, with the reason it was never reachable** — A-11 deliberately kept Docker as the Mac pair's single controlled variable, and no daemon-less cluster exists in this project's estate (the H200 estate is Docker too), so no checkpoint could exercise Apptainer without inventing a platform to run it on. Potential BETTER, genuinely unassessed; the field evidence stands (two forks independently rework `runtime/apptainer.py` before using it at scale), and law 5 keeps `gsj_rollout/` runtime-agnostic so nothing here blocks the attempt when a cluster demands it. `waiting-on: a daemon-less cluster in the estate (A-11) — no owner until then` |
| 31 | tool roster visible in config | `tools_allowlist` is a required, pinned `TaskConfig` field rendered to `--tools` argv; G3 hashes the wire-rendered roster | `tools_allowlist` is a required `AgentSpec.settings` list, rendered 1:1 to `--tools` (CP-07); config == argv == wire, byte-identical | PARITY | keep the roster a hashed field in `config.py`; close at CP-07/CP-08. **CP-06 answer to the row's question**: the chain config-field → `--tools` argv → wire `tools` array is fully observable — pi renders exactly the `--tools` allowlist as the request's `tools` (7 requested, 7 on the wire, schemas pi-generated), and the wire array survives byte-identical into the persisted `transformed_request` and the trace's `tools` (row 11) — so a pinned config field gives G3 a pinned input with zero extra capture machinery; the spike's argv-literal roster (`spike/pi_harness_spike.py:_TOOLS` *(at `spike-cp06`)*) is exactly the anti-pattern the row names, acceptable only because the spike is not the harness; CP-07 must make it an `AgentSpec.settings`/config field. **CP-07 CLOSES the row**: `tools_allowlist` is now a required `AgentSpec.settings` list; the harness renders it 1:1 into `--tools`, and the full chain was verified live — the configured 11-name allowlist == the rendered `--tools` argv == the wire `tools` array on the persisted trace (`docs/polar/pi-corpus/trace.json`), all byte-identical. G3 has a pinned input with zero extra capture machinery. CP-08: the roster's one home is now `harness.tools_allowlist` in the one YAML, rendered 1:1 into `AgentSpec.settings` (golden-tested: config == rendered settings) |
| 32 | train/eval split enforcement | three layers: `eval_case_ids` in the manifest → the taskbank's per-row `split` → **the loader's role lock** (serving eval rows for training refused at the source) | the split is a **directory property of the corpus tree** (ADR-0015, CP-14), carried end to end — tree → `corpus.lock.json` `cases.<id>.split` → the (deferred) bank row → `TaskRequest.metadata.split` → trace metadata — and verified for reality by the pipeline (`verify`'s split-vs-lock clause) and for vocabulary at the receiver (`TR3:split_not_train_or_eval`; both legs of law 6). **Nothing here enforces the split's meaning**: the loader was dropped at CP-00 (§3, trainer's problem), so no component refuses to train on a correctly-labeled eval trace | DROPPED | added at CP-14 — the enforcement half is deliberate, decided at CP-00 with the loader and made explicit here rather than left implied by row 18's `ready/mix` drop. The carry half is real and improved over the predecessor's manifest key (the split is now un-missable in the tree, exactly-one-membership is a hard validation failure, and a moved case that skips re-scaffold fails `verify`), but a label is not a lock: the trainer owns not training on eval, stated in ADR-0015, the contract's "what the split means downstream", and the spec's §The split label. Nothing to cross-source trace-side, measured: case repos are split-agnostic (ADR-0006 — no branch, file, or ref differs by split), deliberately, so the sandbox cannot reveal held-out status to the agent |

## 8. Standing rules

The seven scope laws as operating rules:

1. Own task → sandbox → agent → trace and refuse everything else: no
   storing, scheduling, scoring, weighting, versioning, or training.
2. Count our own lines every checkpoint; crossing 2,034 (ADR-0033;
   2,016 until CP-75, 2,000 until CP-65, 1,500 until CP-12) stops the
   work until justified
   in an ADR — and since CP-65 the suite enforces the number as an
   equality (`test_size_law_census_is_machine_checked`), so the count
   and the law move together or every push goes red.
3. Never touch `gsj-envloader` — read it, compare against it, but no
   checkpoint modifies it. **Historical since CP-45 (2026-08-25,
   ADR-0026).** The rule bound CP-00–CP-44 and did its job: the
   predecessor reached the archive byte-untouched (every porcelain
   check empty; v0.8.0 is the archive commit's parent). What it
   protected — the goldens' collecting stack staying exactly the
   artifact the goldens were collected on — is protected archivally
   rather than operationally from here: CP-45 made the single permitted
   write (the README archive header) and set the GitHub repo to
   archived, so the platform enforces read-only. The "fall back to it"
   half of the old wording is retired with the fallback role (the
   VERDICT's frozen-alive term, expired at CP-17's conversion); the
   read/compare half stands.
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
8. **Push both repos at the end of every CP** — the commit protocol ends
   at the remote, not the working tree. F-52 (CP-32) measured the cost of
   the alternative: both repos' CP-31 commits sat unpushed when the
   stranger test began, so "public" lagged "landed" by a checkpoint and
   the fresh-environment proof nearly measured the wrong artifact. A CP's
   report may state "pushed" only after `git status -sb` shows no ahead
   count in either repo. (Added at CP-33; the CLAUDE.md workflow section
   is outside this CP's freeze-lift, so the rule lives here — §8 is where
   operating rules bind.) **[CP-39] Ignored three CPs running, and
   widened.** CP-36, CP-37 and CP-38 each ended with the library
   unpushed — the mirror sat 3 commits behind while the stranger-test
   record, the model-surface derivation, `serve-llama31.sh` and register
   rows F-54–F-68 existed only locally (audit O1) — while the demo repo,
   which "both repos" does not even name, WAS pushed each time. The
   evidence clause above was satisfied vacuously: none of the three
   reports *claimed* the library pushed, and silence passed. Amended:
   the rule covers **every repo the CP touched** (three since CP-34);
   the report must state the push outcome either way — silence is
   non-compliance; and the rule now also lives in CLAUDE.md's workflow
   section (CP-33's obstacle, CLAUDE.md being outside that lift, fell
   with CP-39's), so every session reads it without opening this
   charter.
9. **Parks name observable events, and every CP's register pass checks
   them** — no row may wait on "the next lift of X" or on a cadence
   nothing schedules; a parked row whose named event has occurred moves
   in the CP that finds it (annotate, close, or re-park on a new event)
   — added at CP-40, the audit's decay mode 2: C-3, F-44 and wishlist
   rows 19/10/24/26 all sat parked on events that had already fired.
   **[CP-51] Teeth.** The 2026-08-27 sweep found five parks whose named
   events had fired — wishlist 26 six times, on the very push that wrote
   the park and five more — while five rule-9 passes (CP-42, 47, 48, 49,
   50) recorded "no parked row's named event fired", and five more parks
   written at CP-41 in a shape no scan can see. From this CP the rule has
   a mechanism, not a sentence: **(a)** every park carries a literal
   **`waiting-on: <observable event>`** token and lives in a register row
   — the VERDICT wishlist, this §7 table, §4, or an F row — never only in
   a §7 paragraph or a report; the per-CP scan is
   `grep -rn 'waiting-on:' docs/` read against what happened, and the
   report states its count. **(b)** A red job on the CP's own push **is**
   a fired trigger until proven otherwise: the report's `tests:` line
   carries the push's run id and every job's colour, and any red job
   names the register row it matches — "runner-side, cause unverified"
   is a verdict that must name the row, never an exemption (CP-48 wrote
   exactly that sentence about row 26 and did not name it). **(c)** "the
   next lift of X" and "the next register pass" are rejected wordings —
   which answers CP-42's unruled question: no CP is *the* register pass;
   every CP scans, and a park must name something a scan can observe.
   Retrofit at CP-51: every open park tokened; the prose-only parks
   (CP-41's W3/W8/S4/S10/M3/M4, its three "recorded, not fixed" items,
   CP-47's test coupling, CP-50's `mv` and sdist notes) taken, closed, or
   moved into wishlist rows 44–45.

## 9. What would make us abandon this

Stated in advance so the decision isn't made under sunk cost. Any of:

- `prefix_merging` output does not match the golden reference and the
  mismatch has no fix in **our** code.
- The proxy needs a forked translation layer to speak to pi 0.83.0.
- The cutoff cannot be injected per-episode through any sanctioned channel.
- G5 (the page cutoff) is unreconstructable from the trace.
- Our own code exceeds ~2,034 lines (ADR-0033; ~2,016 until CP-75,
  ~2,000 until CP-65, ~1,500 until CP-12) — the "thin shell" premise is
  false.
