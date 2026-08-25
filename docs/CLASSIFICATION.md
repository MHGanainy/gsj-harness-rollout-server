# CLASSIFICATION — every tracked file, on two axes

Written at CP-47 (2026-08-25). A read-only census: nothing moved,
nothing hidden, nothing deleted. The operator's question — *what should
a consumer's repository contain?* — is answered here as a table, so the
decision can be taken with the couplings in hand rather than by
directory-name feel. The evidence base: a seven-region sweep of this
repo, both workflows, the build, all three test suites, the pins
scripts, and both consumer checkouts (`gsj-harness-rollout-server-examples`,
`gsj-rollout-demo`), every claim carried by a file:line or a committed
value. CP-46's runtime-read census was the starting point; this
document finds the rest.

**701 tracked files.** Every one is classified below; directories are
classified as a unit only where every file in them shares both axes.

## §1 The two axes

**Axis 1 — audience.** Who is this for?
- **CONSUMER** — someone who installs and uses the library.
- **OPERATOR** — someone standing an estate up.
- **CONTRIBUTOR** — someone changing the code.
- **INTERNAL** — the development record; serves the project, not a user.

**Axis 2 — coupling.** What breaks if it is not in the repository?
- **RUNTIME** — code reads it when something runs (CI, the pins walk, a
  test, the build).
- **DERIVED-FROM** — its bytes determine a value committed elsewhere (a
  lock SHA, a pin, a wheel hash).
- **CITED** — referenced by path from material that must keep resolving.
- **FREE** — nothing reads it, nothing depends on it; removing it costs
  only the information in it.

A file often carries more than one coupling; the table records the
**strongest** (RUNTIME > DERIVED-FROM > CITED > FREE) and names the
others in the evidence column. The cells that matter are the
contradictions — INTERNAL files with RUNTIME or DERIVED-FROM coupling:
files that look like process and behave like dependencies. They are
listed exhaustively in §4, and they are the reason this document exists
instead of a `.gitignore`.

## §2 The table

Directories split because their files disagree on an axis: **root** (6
files, six different rows), **`pins/`** (approved sets vs derivation
scripts vs captured artifacts), **`docs/`** (normative top level vs the
record vs runtime-read evidence — `golden/` and `polar/` each split
again file-by-file), **`corpus/`** (pipeline vs staging tree),
**`staging/`** (two code-read files vs seven operator recipes),
**`vendor/`** (Polar tree vs vendor meta), **`spike/`** (the CP-46
framing header vs the frozen evidence).

| path | files | audience | coupling | what reads it / depends on it |
| --- | --- | --- | --- | --- |
| `README.md` | 1 | CONSUMER | RUNTIME | hatchling reads it at every build/install (`pyproject.toml:9`; ci.yml:47,117, release.yml:74); its bytes are the published PyPI long description (0.1.2 METADATA — also DERIVED-FROM) |
| `LICENSE` | 1 | CONSUMER | RUNTIME | build reads `license-files` (`pyproject.toml:16`); ships verbatim in every wheel (`dist-info/licenses/LICENSE`, verified in the 0.1.2 artifact) |
| `pyproject.toml` | 1 | CONTRIBUTOR | RUNTIME | every install, build, and CI job (ci.yml:47,65,117; release.yml:68-74 asserts tag == `v{version}`); read as data by tests/test_checks.py:972 and tests/test_wheel_pipeline.py:25 |
| `POLAR_SHA` | 1 | OPERATOR | RUNTIME | the demo's image build clones this repo and copies it in (`gsj-rollout-demo/estate/polar.Dockerfile:39-42`); the demo's committed tag `gsj-polar:f0e8343a-gsj0.1.2` embeds its value (`bootstrap.py:47` — DERIVED-FROM). In-repo: prose citations only, zero code readers (grep-verified) |
| `CLAUDE.md` | 1 | INTERNAL | RUNTIME | injected into every working session by the Claude Code harness (AUDIT S1: "it's injected into every session"); no repo code, test, or workflow opens it — see §4's caveat |
| `.gitignore` | 1 | CONTRIBUTOR | RUNTIME | git, on every status/add; its `spike/`, `forgejo/`, `staging/serving/run/` rows keep regenerable scratch untracked (.gitignore:10-20) |
| `.github/workflows/` | 2 | CONTRIBUTOR | RUNTIME | GitHub Actions executes both on every push/tag; ci.yml:150 and release.yml:133 read the h200-fidelity fixture; release.yml:86-99 asserts wheel contents by path prefix |
| `gsj_rollout/` | 8 | CONSUMER | RUNTIME | the product — packaged by every build (`pyproject.toml:78`), exercised by the root suite; `checks.py` bytes ↔ ADR-0021's committed 528 (test_checks.py:784) and `__init__.py:16` ↔ the version literal in three places (also DERIVED-FROM) |
| `tests/` | 13 | CONTRIBUTOR | RUNTIME | ci.yml:48 runs the suite on every push; its 3 fixture files are self-referenced only (nothing outside `tests/` reads them) |
| `pins/pins.gsj.json`, `pins/thinking-on/pins.gsj.json` | 2 | CONSUMER | RUNTIME | `checks.py:116-137` reads the checkout copy at import (ADR-0017); `receiver.py:73` reads the mode key; force-included into every wheel (`pyproject.toml:85,91`; release.yml:96-97 asserts — also DERIVED-FROM); the demo reads the wheel copies at bring-up (`bootstrap.py:664-670`) |
| `pins/derive_pins.py` | 1 | CONTRIBUTOR | RUNTIME | executed by the root suite in CI (test_checks.py:1050 subprocess, asserts rc 0) — every path it reads is thereby CI-load-bearing |
| `pins/derive_g2.py` | 1 | CONTRIBUTOR | CITED | operator-run only (no test or CI invokes it — verified); cited from charter row 23 and VERDICT; its default paths make two files below RUNTIME |
| pins captured artifacts (6: `system_prompt.captured.txt`, `tools.captured.json`, `settings.rendered.json`, `g6_tail.captured.txt`, `thinking-on/g6_tail.captured.txt`, `container/system_prompt.container.derived.txt`) | 6 | INTERNAL | RUNTIME | all six are read by the derive walks or the root suite, and four are the byte-source of committed pin values — the full proof is §4 rows 9-14 |
| `docs/README.md` | 1 | CONSUMER | CITED | the record's shelf map (CP-46); renders under the `docs/` listing; names the load-bearing paths |
| `docs/VERDICT.md` | 1 | CONSUMER | CITED | README:176; **published PyPI 0.1.2 metadata URL** (`pyproject.toml:50`); examples ADR-0003 quotes it by path |
| `docs/CHARTER.md` | 1 | CONTRIBUTOR | CITED | the normative document; **published PyPI metadata URL** (`pyproject.toml:51`); CLAUDE.md:5 |
| `docs/checks-spec.md` | 1 | CONSUMER | CITED | **published PyPI metadata URL** (`pyproject.toml:52`); cited from wheel-shipped docstrings (`checks.py:1`, `builder.py:5`) and the demo README:168 |
| `docs/corpus-contract.md` | 1 | CONSUMER | CITED | cited from wheel-shipped CLI help (`ingest_corpus.py:8,65,1421`); the demo prints its GitHub URL in a runtime error (`bootstrap.py:255`) and templates it into every user's config (`config.yaml.example:9`) |
| `docs/AUDIT-2026-08-24.md` | 1 | CONSUMER | CITED | the trust document (docs/README: read it and stop); README:179; spike/README.md:4 |
| `docs/reports/` | 51 | INTERNAL | CITED | README:178 ("every claim's primary evidence"); **two are cited from the wheel-shipped pins provenance** — `CP-04prime.md` and `CP-11b.md` in `pins.gsj.json` `walk_status`, on PyPI immutably (§5); consumer repos cite CP-16/20/36/43 by path; staging/README:36,71 |
| `docs/prompts/` | 51 | INTERNAL | CITED | the workflow contract (CLAUDE.md:19); each report's companion; docs/README shelf table. No runtime reader (verified) |
| `docs/decisions/` | 26 | CONTRIBUTOR | CITED | "decisions about the code" (CP-46); README:180; the demo deep-links ADR-0025 (`README.md:304`); examples cite ADR-0019/0020 by id (id-citations survive moves; path-citations do not) |
| `docs/golden/mac/tokens.npz` | 1 | INTERNAL | RUNTIME | tests/conftest.py:22 (`golden_trace` fixture); the committed tuple (20, 292, 3747) at test_checks.py:141 is computed from its bytes (also DERIVED-FROM) |
| `docs/golden/mac/MANIFEST.md`, `record.json` | 2 | INTERNAL | DERIVED-FROM | the golden fixture's transcribed constants — `timestep: 12`, `finish_reason: "stop"` — come from these files (conftest.py:110-125 docstring); never opened by code |
| `docs/golden/` remainder (COMPARISON.md, mac/transcript.txt, mac/artifact/NOTE, h200/ ×5) | 8 | INTERNAL | CITED | COMPARISON.md is the README evidence table's first citation (:129) and the conftest field-mapping's source (:107); the h200 pair is CP-09′'s comparison target (docs/polar/README.md) |
| `docs/polar/README.md` | 1 | CONSUMER | CITED | the shelf's own index (CP-41 mechanism, S14); cited by docs/README |
| `docs/polar/` runtime-read evidence (7: `pi-corpus/callback_session_result.json`, `pi-corpus/trace.json`, `fidelity/callback_session_result.json`, `fidelity/trace.json`, `h200-fidelity/callback_session_result.json`, `h200-stitch/attempt5.accepted.json`, `thinking/episode-on.quarantined.json`) | 7 | INTERNAL | RUNTIME | read by tests/conftest.py:19-21, test_checks.py:707-721,935,1007-1018, ci.yml:150, release.yml:133, and pins/derive_pins.py:76 — the full proof is §4 rows 1-7 |
| `docs/polar/` remaining evidence (thinking 14, thinking-on 8, h200-loop 8, h200-fidelity 7, h200-verl-loop 6, pi-corpus 3, pi 4, fidelity 2, h200-stitch 1, 3 loose CP-03 artifacts) | 56 | INTERNAL | CITED | indexed by `docs/polar/README.md`; `thinking/` as a directory is the measurement basis named in the wheel-shipped on-pins provenance ("all 41 turn openings of 15 real thinking-on episodes"); examples RUNBOOK:322 cites `docs/polar/thinking/` |
| `corpus/ingest_corpus.py` | 1 | CONSUMER | RUNTIME | force-included into every wheel as `gsj_rollout/ingest_corpus.py` (`pyproject.toml:100`; release.yml:98 asserts — also DERIVED-FROM); imported at pytest import time by mcp-service/tests/helpers.py:79; run from the checkout by examples `rebuild_taskbank.sh:11` |
| `corpus/` pipeline (tests ×5, pytest.ini, requirements.txt) | 7 | CONTRIBUTOR | RUNTIME | ci.yml:65-67 installs and runs the corpus suite (58) on every push |
| `corpus/staging/` | 163 | OPERATOR | RUNTIME | dual-natured: the estate's corpus source **and** the freeze record — see §4's closing note. Read by tests/test_config.py:153, test_wheel_pipeline.py:50, corpus/tests/test_taskbank.py:27,237, mcp-service/tests/helpers.py:36 (at module import — every mcp test run), pins/derive_pins.py:94, derive_g2.py:59. Its bytes determine the lock's 16 ref SHAs, the taskbank sha, the pins `skill_card_hash` (→ every wheel), both golden manifests' "converged" claims, and the demo's byte-identical `AGENTS.reference.md` (all DERIVED-FROM) |
| `mcp-service/` | 29 | OPERATOR | RUNTIME | ci.yml:104-106 runs its suite (89) on every push; ci.yml:91's cache key is a literal copy of `config.yaml:25`'s model revision; `checks.py:92` cites its README as the binding contract |
| `forgejo/` | 4 | OPERATOR | CITED | human-run only — no test, CI step, or code reads it (verified); cited by .gitignore:10, mcp-service/config.yaml:7, and its compose carries the live H200 estate's identity ("Do not rename it out from under the running instance") |
| `staging/serving/serve-updated.sh` | 1 | OPERATOR | RUNTIME | tests/test_staging_scripts.py:6 — content tripwire + `bash -n`, on every CI push; cited by examples ADR-0002:30, ADR-0004:57, both loop READMEs, FINDINGS rows, and train.py:527 prints it as the operator's sync instruction |
| `staging/serving/qwen3_training.jinja` | 1 | OPERATOR | RUNTIME | pins/derive_pins.py:109 hashes it on every walk (CI via test_checks.py:1050); the committed `chat_template_hash` in both pins sets is its sha256 (also DERIVED-FROM); the h200 golden manifest pins the same bytes |
| `staging/` remainder (README, rollout.h200.yaml, serve.sh, serve-llama31.sh, healthcheck.sh, 2 model envs) | 7 | OPERATOR | CITED | operator recipes, human-run; cited by checks-spec:620, charter §7, both golden manifests (serve.sh argv, :57), consumer loop READMEs (`--config staging/rollout.h200.yaml` commands run from this checkout), demo MODEL-SURFACE:25 (audit M2); serve.sh reads its sibling env files when run |
| `vendor/polar/` | 210 | OPERATOR | RUNTIME | `cli.py:44-51` probes it on every `serve`; **the root suite fails if the directory is absent** (test_cli.py:232 monkeypatches `exists` but not `isdir` — see §3); `pi_harness.py:48` / `builder.py:18` import `polar`, resolved in the operator-run Polar processes (A-14); the demo's image build pip-installs it from a fresh clone (`polar.Dockerfile:43`); examples `train_one_step.sh:44` reads `src/slime_bridge/reward_post_process.py` from it; checks-spec's rule citations resolve into it by file:line |
| `vendor/patches/` (3) + `apply_patches.sh` | 4 | CONTRIBUTOR | DERIVED-FROM | the committed post-patch tree is upstream@`POLAR_SHA` + P1-P3 (ADR-0005); `apply_patches.sh --verify` asserts the patch symbols in named vendored files (:33-44); reverse-apply walks back to the pristine pin (charter) |
| `vendor/REVENDOR.md` | 1 | CONTRIBUTOR | CITED | `cli.py:52` prints it as the operator's hint at serve time, test-locked (test_cli.py:232 asserts the string); the re-vendor recipe; POLAR_SHA:15, examples RUNBOOK:217 |
| `spike/README.md` | 1 | CONSUMER | CITED | the CP-46 directory header — converts the shelf into a labeled exhibit |
| `spike/` evidence | 24 | INTERNAL | CITED | zero runtime readers outside itself (exhaustive grep — the only non-prose hits are release.yml:87's banned-prefix tuple, a pyproject comment, and .gitignore rows, all name-keyed); cited by path from checks-spec:891,900, charter A-2/A-12/A-15/row 31, ADR-0006, `pi_harness.py:3`'s wheel-shipped docstring, AUDIT:144 |

## §3 Summary counts, by cell

| | RUNTIME | DERIVED-FROM | CITED | FREE | total |
| --- | ---: | ---: | ---: | ---: | ---: |
| CONSUMER | 13 | 0 | 7 | 0 | **20** |
| OPERATOR | 405 | 0 | 11 | 0 | **416** |
| CONTRIBUTOR | 25 | 4 | 29 | 0 | **58** |
| INTERNAL | 15 | 2 | 190 | 0 | **207** |
| **total** | **458** | **6** | **237** | **0** | **701** |

Three measurements decide everything downstream:

1. **The FREE column is zero.** Nothing tracked is free to leave. The
   record is deliberately cross-woven — every evidence directory is
   cited by path from at least one document that must keep resolving
   (the normative spec, the charter's assumption register, a consumer
   repo, or a published artifact). "Nothing reads it" was checked, not
   assumed, and it is true of nothing.
2. **458 of 701 files are RUNTIME.** Most of that is the operator
   estate (vendor 210, staging tree 163) — but 15 are INTERNAL: §4.
3. **The one avoidable-by-accident coupling found:** the root suite
   requires `vendor/polar/` to *exist as a directory* —
   test_cli.py:227-229 monkeypatches `os.path.exists` for the venv
   probe but leaves `cli.py:51`'s `os.path.isdir` unpatched, so
   deleting or renaming `vendor/polar` fails
   `test_serve_printout_hints_the_unbuilt_venv`. A few-line test edit
   removes it. Every other RUNTIME read of record material is
   *designed* (the suite validates the real evidence bodies; the walk
   re-derives the real pins), and the avoidable-copy option is priced
   per row in §4.

## §4 The contradictions — INTERNAL files that are dependencies

Seventeen files are classified INTERNAL on axis 1 and RUNTIME or
DERIVED-FROM on axis 2. Every hide/move option in §6 pays for this
list. Proof per row:

**INTERNAL + RUNTIME (15):**

1. `docs/polar/pi-corpus/callback_session_result.json` — tests/conftest.py:19
   (the session `callback_body` fixture behind most of the suite). Also
   DERIVED-FROM: test_checks.py:114's tuple (27, 441) and
   test_client.py:29's literal 2965 are computed from its bytes.
   *Copyable into tests/fixtures/ (~418 KB) — at the cost of forking
   the CP-07 evidence; the suite's design is that pass-clean assertions
   run against the real accepted bodies.*
2. `docs/polar/pi-corpus/trace.json` — pins/derive_pins.py:76 hashes its
   `tools[]` and `prompt_messages[0].content` on every walk (CI-run via
   test_checks.py:1050). Also DERIVED-FROM: `pins.gsj.json`'s
   `tool_roster_hash`/`system_prompt_hash` provenance names it — strings
   that ship in every wheel. *Not movable without editing derive_pins.py
   and re-releasing the pins provenance; PyPI 0.1.2 names the path forever.*
3. `docs/polar/fidelity/callback_session_result.json` — tests/conftest.py:20
   (`fidelity_callback`). *Copyable (~103 KB), same evidence-fork cost.*
4. `docs/polar/fidelity/trace.json` — tests/conftest.py:21 **and**
   pins/derive_pins.py:76; DERIVED-FROM: pins provenance +
   test_checks.py:107's (15, 363). *Three couplings, one path.*
5. `docs/polar/h200-fidelity/callback_session_result.json` — ci.yml:150
   **and** release.yml:133 (the install proof on both the push and the
   release path) **and** test_checks.py:721, :935. *Three independent
   readers; also the byte-source of both bridge repos' committed
   fixture copies (sha 467fc2db…, provenance READMEs).*
6. `docs/polar/h200-stitch/attempt5.accepted.json` — test_checks.py:720
   via `_polar_body`. *Copyable (~453 KB), same objection.*
7. `docs/polar/thinking/episode-on.quarantined.json` — test_checks.py:1007
   and :1018 (which asserts the recorded quarantine verdict reproduces —
   the file must stay byte-identical to the wrapper's findings).
8. `docs/golden/mac/tokens.npz` — tests/conftest.py:22; DERIVED-FROM:
   test_checks.py:141's (20, 292, 3747). *Copyable (~184 KB) — but it
   is the archived predecessor's golden reference; a copy severs the
   suite from the A-1 provenance chain.*
9. `pins/tools.captured.json` — derive_pins.py:72, the canonical-JSON
   convention anchor ("if this fails, nothing below is trustworthy");
   DERIVED-FROM: its canonical hash IS the approved `tool_roster_hash`.
10. `pins/settings.rendered.json` — tests/conftest.py:23→:51 stamps
    every fixture trace; test_pi_harness.py:154 asserts the harness
    constant renders exactly this document; derive_pins.py:88;
    DERIVED-FROM: `settings_hash`. *47 bytes, inlineable — but the
    pi_harness test's point is the file.*
11. `pins/g6_tail.captured.txt` — derive_pins.py:111-112; DERIVED-FROM:
    the approved `g6_expected_tail` IS this file's text (algo
    `verbatim_text`), and `g6_expected_tail_ids` is it tokenized.
12. `pins/thinking-on/g6_tail.captured.txt` — derive_pins.py:122, with
    the exact-identity prefix check (:126-128) binding it byte-wise to
    row 11's file; DERIVED-FROM: the on-set tail pin.
13. `pins/container/system_prompt.container.derived.txt` —
    derive_pins.py:85; DERIVED-FROM: `system_prompt_hash` (f56e8a6e…),
    and the demo carries a byte-identical copy with a *runtime
    tripwire* — `bootstrap.py:677-681` dies if its copy drifts from the
    wheel's pinned value.
14. `pins/system_prompt.captured.txt` — derive_g2.py:56/:123's default
    input (operator-run, not CI); the G2 derivation source —
    checks-spec:1424: "embeds the predecessor's host paths —
    byte-load-bearing, never rewrite."
15. `CLAUDE.md` — read programmatically by exactly one runtime: the
    session harness injects it at the start of every CP (AUDIT S1).
    Caveat stated plainly: this is not axis 2's parenthetical list (CI,
    pins walk, test, build) — but removing it changes what every future
    checkpoint session knows, which is a break, not a cost-of-information.

**INTERNAL + DERIVED-FROM (2):**

16. `docs/golden/mac/MANIFEST.md` — the golden fixture's committed
    `timestep: 12` is transcribed from it (conftest.py:110-125).
17. `docs/golden/mac/record.json` — same mechanism, `finish_reason:
    "stop"` from `env.steps[*].stop_reason`.

**The near-contradiction, named:** `corpus/staging/` (163 files) is
classified OPERATOR because the estate scaffolds from it — but it is
equally the freeze record, and it carries the densest coupling in the
repo: six runtime readers across all three suites and both derive
scripts, and five derivation chains ending in the lock's 16 ref SHAs,
the taskbank sha, the wheel's `skill_card_hash`, both golden manifests,
and the demo's tripwired copies. CP-46 §7 already recorded why it
cannot regenerate: its collector is archived, so byte-identical
regeneration is unprovable in principle. Whatever the operator decides
for INTERNAL files, this directory is not movable on the same terms.

**Citation with teeth, distinct from ordinary CITED:** two report files
— `docs/reports/CP-04prime.md` and `docs/reports/CP-11b.md` — plus the
`docs/polar/` episode paths and `docs/polar/thinking/` are named inside
`pins.gsj.json`'s provenance and `walk_status`, which ship in every
wheel; and `docs/VERDICT.md`, `docs/CHARTER.md`, `docs/checks-spec.md`
are the published PyPI 0.1.2 project URLs (`pyproject.toml:50-52`).
PyPI artifacts are immutable: these paths are pinned by releases that
cannot be edited, only superseded.

## §5 The consumer's repository, hypothetically

**The strict listing** — CONSUMER-audience or FREE-coupled files only.
FREE contributes nothing (the column is zero), so the repo is the
20 CONSUMER files:

```
README.md  LICENSE
gsj_rollout/            (8 — the library)
pins/pins.gsj.json  pins/thinking-on/pins.gsj.json
corpus/ingest_corpus.py
docs/README.md  docs/VERDICT.md  docs/checks-spec.md
docs/corpus-contract.md  docs/AUDIT-2026-08-24.md
docs/polar/README.md  spike/README.md
```

It is not a working repository. It has no `pyproject.toml` (nothing
installs or builds), no tests, no CI — those are CONTRIBUTOR. Add the
CONTRIBUTOR skeleton (58 files) and it builds — **and the moment
`tests/` arrives, the record is required again**: the suite reads seven
`docs/polar/` bodies, `tokens.npz`, all six pins captures, the 163-file
staging tree, `staging/serving/serve-updated.sh`, and requires
`vendor/polar/` to exist. The test suite is the record's anchor; a
consumer repo that keeps the tests keeps the evidence.

**What the consumer loses** (every INTERNAL/OPERATOR/CONTRIBUTOR shelf):
the 26 ADRs ("why is it built this way" — including ADR-0021's
checks.py tripwire rationale and ADR-0017's pins resolution order); all
51 reports and 51 prompts — the primary evidence behind every number in
the README's proven-claims table; the golden pair (the A-1 fidelity
proof against the predecessor); the `docs/polar/` run artifacts (the
cutoff tamper transcript, both training loops, the thinking evidence);
`docs/CHARTER.md` (a published PyPI URL — it 404s); the spike; the
estate (`vendor/`, `staging/`, `mcp-service/`, `forgejo/`,
`corpus/staging/`) — which means the demo's image build breaks too.

**What breaks, by name** — every RUNTIME/DERIVED-FROM row that would
have to move with it or be re-homed:

- tests/conftest.py:19-22 → 3 polar bodies + `tokens.npz` (§4 rows 1,3,4,8)
- test_checks.py:707-721, :935, :1007-1018 → h200-stitch, h200-fidelity,
  thinking (§4 rows 5-7)
- ci.yml:150 + release.yml:133 → the h200-fidelity fixture (§4 row 5)
- pins/derive_pins.py:72-122 → both trace.json files + five pins
  captures + `qwen3_training.jinja` (§4 rows 2,4,9-13) — and
  test_checks.py:1050 runs the walk in CI
- conftest.py:23 + test_pi_harness.py:154 → `settings.rendered.json`
- test_config.py:153-163 → the staging skill card ↔ pins linkage
- test_wheel_pipeline.py:50 + corpus/tests/test_taskbank.py:27,237 +
  mcp-service/tests/helpers.py:36,79,131 → `corpus/staging/` and
  `ingest_corpus.py` (helpers reads at module import — the mcp suite
  cannot even collect without the staging tree)
- test_staging_scripts.py:6 → `serve-updated.sh`
- test_cli.py:232 (via cli.py:51) → the `vendor/polar/` directory
- the wheel force-includes (`pyproject.toml:85,91,100`) → both pins
  sets + `ingest_corpus.py`, release-asserted at release.yml:95-99
- `gsj-rollout-demo/estate/polar.Dockerfile:39-43` → clones this repo
  for `vendor/polar` + `POLAR_SHA` at image-build time

**README/PyPI citations that stop resolving:** the evidence table's
`docs/golden/COMPARISON.md` (:129) and its per-row CP report citations;
"Where the record lives" (:176-182 — reports/, prompts/, decisions/,
golden/, polar/, CHARTER); the PyPI 0.1.2 Charter URL; the wheel-shipped
provenance strings naming `docs/polar/*` and `docs/reports/CP-04prime.md`
/ `CP-11b.md` — immutable on PyPI, danglable but not fixable.

## §6 The options, priced against the classification

**(a) Split — internal files to a second repository (public or private).**
Moving the 207 INTERNAL files costs: re-homing or re-pointing the 17
contradiction files — roughly 25 reader edits across `tests/` (5
files), both workflows, `pins/derive_pins.py`, and `conftest.py`, plus
a pins re-derivation and a **0.1.3 release** (the provenance strings
that name `docs/polar/*` paths ship inside every wheel; 0.1.2's are
immutable and dangle forever); the citation rewrites — CP-46's census:
**740 move-breaking occurrences across the three repos** (725 here,
mostly inside verbatim prompts, append-only ADRs, and frozen reports
this project forbids rewriting; this CP's per-file recount in the
consumer repos found the library-tree references are a superset of
CP-46's 15: ~49 citation lines in examples, ~15 in the demo); history
extraction if commit anchors must keep resolving (CP-45's archive
paragraph anchors the goldens to `4037bc2` by hash — SHAs do not
survive extraction); and every future CP becomes a two-repo,
non-atomic commit. **Against the requirement:** it genuinely removes
~190 INTERNAL-CITED files from the consumer's view — but the 17
runtime-coupled ones either stay (and the record is still visible) or
force the full re-homing bill; and the listing the consumer actually
confronts barely changes, because the bulk of it is the OPERATOR
estate (416 files: vendor, staging tree, mcp-service), which is not
internal and cannot leave a repo whose server role requires it.

**(b) Untrack — internal files removed from `HEAD`, kept locally.**
The same 17-file re-homing bill and the same 740 citations break —
plus the record stops being checkable by anyone but the operator: the
audit's premise ("citable at its current paths by design"), the README
evidence table, and the PyPI-shipped provenance all point at paths
that 404 publicly; and the only copy sits one disk failure from gone.
**Against the requirement:** it hides the material, at the price of
converting an evaluation whose product is a checkable record into an
uncheckable one. The strict-listing analysis above shows the CI badge
dies too (the suite cannot run without the evidence files).

**(c) Frame harder — CP-46's approach extended.** Publish this
classification (done — this document is committed); extend the shelf-
README mechanism to the remaining unframed interiors (`corpus/` has no
README over its 163-file staging tree; `vendor/` fronts 210 files with
only REVENDOR.md; `forgejo/` and `staging/` have none); optionally add
per-row labels to docs/README's shelf table pointing here. Cost: near
zero — a few index files, no reader edits, no re-release, zero of the
740 citations touched. **Against the requirement:** it does not remove
anything from the consumer's view; it labels it. The listing stays 16
entries and the clone stays 5.9 MB. What it fixes is the only part the
classification shows to be fixable at this price: that a consumer
cannot currently tell which files are for them (20 of 701) without
reading forty reports — the table makes skipping cheap and deliberate.

## §7 Recommendation

**(c), extended as described — and publish this table as the map.**
The grounds are §3's three measurements: FREE is zero, so there is no
free hide list; the INTERNAL files a consumer might resent are 207 of
701, and the 17 that are load-bearing pin the rest in place through
740 citations, two CI gates, the pins walk, and PyPI-immutable
provenance; and the bulk of the listing is the operator estate, which
no internal/consumer split touches at all. Options (a) and (b) spend a
re-release plus a mass edit of frozen records to remove material that
§5 shows the test suite would immediately re-require, and (b)
additionally un-checks the record this evaluation exists to produce.
If the operator's requirement is strictly that a consumer must not
*see* the development record, only (a) executed in full achieves it —
at the counted price above, and the operator should decide that with
this table in hand. The residual (c) honestly does not fix: the
listing's length. The one cheap correctness fix found either way:
test_cli.py's unpatched `isdir` (§3.3), a few-line edit at the next
test freeze-lift.

*Method note: seven parallel evidence agents swept CI/build, pins,
the root suite and library, the moved components, vendor/spike/root,
both consumer checkouts, and docs/ — every RUNTIME and DERIVED-FROM
claim above carries its file:line; negatives ("nothing reads it") were
grep-verified, not assumed. Counts reconcile: 701 = root 6 + .github 2
+ gsj_rollout 8 + tests 13 + pins 10 + docs 209 + corpus 171 +
mcp-service 29 + forgejo 4 + staging 9 + vendor 215 + spike 25.*
