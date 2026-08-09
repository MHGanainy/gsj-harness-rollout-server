### CP-11b REPORT
status: done
scope_drift: none — the DoD's frozen surface diffs empty (`vendor/`, `corpus/`, `mcp-service/`, `forgejo/`, `spike/`, `receiver.py`, `client.py`, and `pi_harness.py` untouched beyond the DoD's own list), the predecessor untouched, no template change, and no re-pin (`pins/pins.gsj.json` values byte-identical — the diff is exactly the `walk_status.first_episode_validate` prose line; `derive_pins.py` reproduces every approved value). The `cli.py`/`config.py`/`builder.py` edits are the ADR-0009 recovery and were verified prose-only by AST comparison (builder identical after docstring strip; cli/config differences confined to string constants in prints/help — the sanctioned "operator prints"). One declared logic change beyond the four gates, inside the lifted file and forced by this CP's own adversarial pass: three pre-existing never-raise breaches fixed in `checks.py` (under `questions:`)
files: 12 files changed — new: `docs/prompts/CP-11b.md`, `docs/reports/CP-11b.md` (this), `docs/decisions/ADR-0011-codec-evidence.md`; modified: `gsj_rollout/checks.py` (the gates G2/G3/G7 + H-41, pins loading, two hashing conventions, the never-raise fixes; 285 → 407), `gsj_rollout/cli.py`/`gsj_rollout/config.py`/`gsj_rollout/builder.py` (prose-only budget recovery), `tests/test_checks.py` (+14 gate tests, the crash-shape corpus, the vocabulary snapshot), `tests/conftest.py` (the CP-09 callback fixture), `docs/checks-spec.md` (§The gates as landed, the pins-seam facts, dispositions), `docs/CHARTER.md` (rows 9–15, 23, §3, §6), `pins/pins.gsj.json` (walk_status prose only)
tests: `.venv/bin/pytest -q` → **76 passed** (62 pre-existing — two updated deliberately: the vocabulary snapshot gained the 10 new entries, the golden-mapping test now asserts the fail-closed findings its evidence-less shape earns — plus 14 new gate tests) | additionally verified by a 6-agent adversarial workflow — see §Verification
adrs: ADR-0011 (G4/G6 codec evidence: measure-at-serve; trust-provenance rejected on measured absence + the F1 precedent)        assumptions: none
gap_register: rows 10/11/15 TBD→**PARITY** (G2, G3, G7's stats conjunction — landed and validated on both real episodes); row 9 TBD→**GAP** (G1 unimplementable as specced, blocker measured, fix recorded); rows 12/14 TBD→**GAP** (G4/G6 deferred by ADR-0011 with mechanisms named, G6's design corrected for the first turn); row 23 **CLOSES** (first-episode-validate done); §3 gains the [CP-11b] budget status (1,496/1,500, three measured movements); §6's CP-11 row records the CP-11b outcome
questions:
  - Corrupted span, Step 2 intro: "each using the byetail]` vocabulary" → "each using the byte-stable `{id}:{slug}[:detail]` vocabulary" (the CP-07/CP-10 findings form).
  - Corrupted span, Step 2 G2 bullet: "finding (b) i: a raw read" → "finding (b) is binding: a raw read" (the spec's own phrasing).
  - Corrupted span, Step 3: "Decoding needs the tokenizer atime" → "…the tokenizer at check time" (the pins provenance wording).
  - Corrupted span, Step 3: "the builder subclass (which rue Polar's process)" → "…which runs in Polar's process".
  - Corrupted span, Step 6 heading: "## Step 6 — C, spec" → "## Step 6 — Charter, spec" (its own bullet list).
  - Corrupted span, DoD: "git stacelain" → "git status --porcelain" (CP-10/CP-11's DoD form).
  - Applied default, **G7's settings clause**: the CP asks where the settings evidence lives in a trace — measured answer: nowhere (zero `settings`/`compaction` occurrences on both real callback bodies), so the stats conjunction landed alone with the gap recorded in row 15 and the fix named (a one-line harness echo of the rendered settings into trace-reachable metadata, `pi_harness.py`'s next freeze-lift).
  - Applied default, **G1 not landed** (the CP's own contingency): measured that the trace cannot identify the card — both episodes' first user message (626 chars) neither equals nor contains the 616-byte summarize card, and without `prompt_source` no hash test can distinguish a skill row from a free row that must pass n/a. Fix recorded: `prompt_source` (+ card hash) in `TaskRequest.metadata`, one line in `config.render_task_request` at its next freeze-lift, landing naturally with the taskbank (ADR-0003).
  - Applied default, **H-41 as a policy-gated check, not a warning finding**, default OFF: the receiver treats any finding as a rejection (frozen), so a warning that rides the findings list would reject legitimate zero-tool episodes — the CP says it is not a gate. The knob is `CheckPolicy.reject_toolless_roster`; the YAML mirror cannot gain the field this CP (`config.py` logic frozen), so it is library-level until the next freeze-lift — the one-field mirror drift is declared in `ChecksConfig`'s docstring.
  - Applied default, **rows 10/11/15 land on PARITY, row 15 with an in-row residual**: PARITY claimed on the degeneration-catching conjunction (the clause CP-03 proved `truncated == 0` alone is blind to), not on the settings clause the receiver cannot verify — the residual is named in the row rather than flipping the row to GAP, mirroring row 13's precedent (landed core + named residual).
  - Applied default, **`builder.py`'s freeze-lift judged genuinely needed**: cli+config banking alone recovered −34 against ADR-0009's 120–140 gate estimate (1,438 − 34 + 140 > 1,500), so the arithmetic did not close without it. All three candidates were used; the gates then cost exactly 135.
  - Applied default, **a second and third recovery movement mid-CP**: the gates' landing put the tree at 1,518 (measured) — cured immediately by compressing gate docstrings to spec pointers (−21), not deferred to the end; the adversarial pass then forced +4 guard lines, paid by −5 further prose (net −1). The charter's budget paragraph records all three movements with reproducible endpoints (its first draft misattributed the per-pass endpoints; the verification caught it — §Verification).
  - Applied default, **`pins/pins.gsj.json` walk_status prose updated**: not a re-pin — zero approved values changed (`derive_pins.py` exits 0, "all approved values reproduced"; the git diff is one prose line) — the walk-status ledger simply records its own validate leg closing.
  - Applied default, **three pre-existing never-raise breaches fixed in `checks.py`**: the adversarial pass proved `validate_session_result` RAISED on JSON-legal wire content (OverflowError on a `10**400` logprob at `math.isfinite`; TypeError on an unhashable `tool_call` id/`tool_call_id`; TypeError on a non-string `finish_reason`) — all three reproduce against HEAD, so they are inherited, but the never-raise contract is re-asserted by this CP's own prose and `checks.py` was the file under lift. Fixed (each shape now yields its owning finding — LP4 / census-skip / TR1), regression-locked in the malformed-content corpus. Rule semantics on well-formed traces unchanged; the 62 pre-existing tests pass.
next: CP-12 (the verdict) — not drafted, per the STOP wall. It inherits: the complete checks/does-not-check picture (§notes below); the freeze-lift wishlist accumulated across CPs (receiver: pins-failure seam cleanup; pi_harness: settings echo; config: `prompt_source` + the H-41 mirror field; mcp-service: the CP-10 README one-liner, frozen three CPs running); and CP-04′'s standing obligations (derive_pins at bring-up = G4's measure-at-serve, the `g6_expected_tail_ids` pin with the first-turn clause, the template flip re-derives)

---

#### Step 1 — the budget, measured (before → after, per movement)

```
                 HEAD   bank(−55)   gates(+135)   prose(−21)   verify(−1)   final
cli.py            175         163           163          163          163     163
config.py         268         249           249          246          246     246
builder.py        189         165           165          159          159     159
checks.py         285         285           420          408          407     407
everything else   521         521           521          521          521     521
total           1,438       1,383         1,518        1,497        1,496   1,496
```

The banking ran FIRST, per Step 1 — and was still not enough: the gates
cost 135 (the top of ADR-0009's estimate; the four hashing-convention
sketch it budgeted for six gates roughly matches four gates plus pins
loading plus the hostile-content guards), and the tree stood at 1,518
mid-CP. The cure was applied at that moment, not at the last gate: gate
docstrings compressed to one-line spec pointers (the ADR-0009 migration
pattern, applied to the new code itself). The adversarial pass then
bought its three guard lines with five more lines of prose. Final:
**1,496/1,500**, `checks.py` **407/420**. Four lines of headroom is the
honest number CP-12 inherits.

#### Step 2 — per gate: landed or not, evidence source, the verbatim lines

Clean pass, both real episodes, full seam (the first-episode-validate leg):

```
CP-07 sk-polar-c4eef751: validate_session_result -> []
CP-09 sk-polar-180dd057: validate_session_result -> []
```

Doctored failures, each firing for its own reason (equality-asserted in
the suite; controls prove the filter is doing the work):

```
G3 one tool renamed        -> ['G3:tool_roster_hash_not_approved:1d1208b116d1…b74b43d7d']
G3 roster absent           -> ['G3:missing_evidence:tools']
G2 one byte appended       -> ['G2:system_prompt_hash_not_approved:40617ed8e310…8bad447adf6e']
G2 system message absent   -> ['G2:missing_evidence:system_prompt']
G2 control: typed parts, same prompt -> []          (finding (b) honored)
G7 chains_total=2          -> ['G7:chains_total_ne_1:2']
G7 truncated=1             -> ['G7:chains_truncated:1']
G7 completions_merged=1    -> ['G7:completions_merged_ne_total:1!=2']
G7 raw_completions_total=3 -> ['G7:raw_completions_ne_total:3!=2']
G7 stats absent            -> ['G7:missing_evidence:reconstruction_stats']
H41 toolless, default off  -> []
H41 toolless, armed        -> ['H41:roster_offered_zero_tool_calls']
H41 armed, real episode    -> []
```

- **G3 — landed** (`check_tool_roster`). Evidence: `trace.tools`, the
  wire array as persisted (CP-06: persisted == wire for tools);
  canonical-JSON convention byte-exact to the predecessor's
  (independently re-derived by the verification against
  `gsj-envloader/store.py` executed verbatim, plus the
  `pins/tools.captured.json` anchor). CP-05 first-completion caveat in
  the docstring; `R11` complements builder-side.
- **G2 — landed** (`check_system_prompt`). Evidence: every `system`-role
  message in `prompt_messages`, flattened through `_content_text`
  (finding (b)); the `/workspace` singleton set. An injected second
  system message fails (it cannot match the singleton); unencodable
  content is a finding, not a raise.
- **G7 — the stats conjunction landed** (`check_chain_snapshot`,
  session-level: the stats ride `trajectory.metadata`, not a trace).
  All four CP-05 clauses, fail-closed per missing/non-int stat (bools
  rejected before ints, so `True` does not pass as `1`). **The settings
  clause did not land** — no settings evidence rides the callback
  (measured); recorded in row 15 with the harness-echo fix named.
- **G1 — not landed**, unimplementable as specced; measured blocker and
  recorded fix under `questions:`.
- **H-41 — landed policy-gated** (shape below).

#### Step 3 — the G4/G6 decision (ADR-0011), and what the weaker option would have cost

**Measure-at-serve, executed at the pins walk on the serving estate.**
The deciding facts were measured, not argued: zero codec evidence rides
the callback (no `fingerprint`/`tokenizer`/`chat_template` key anywhere
on either real body); the only fingerprint that exists at the pin —
`response.system_fingerprint` on the persisted per-completion record,
`0.31.3-0.32.0-macOS-15.6.1-arm64-…` — is an engine platform string,
not a codec identity, on a record that never rides the callback (CP-05).
So **trust-provenance was not merely weaker, it was unimplementable**:
there is no claim on the wire to verify. What it would have cost had the
evidence existed: a gate that green-lights any trace whose estate SAYS
the right thing — the exact CP-09 F1 shape (wrong sampling defaults,
every gate green) — bought with a vendored patch to stamp the claim into
forwarded metadata. The strong option costs machinery this CP could not
build (estate recording + a channel), but half of it already exists:
`pins/derive_pins.py` IS the measure-at-serve instrument, run against
the served snapshot at bring-up (CP-04′ DoD items 3–5). The residual
that stays open either way, named: per-episode binding — a snapshot swap
after bring-up is invisible to every trace-side check (row 22, estate
provenance). **G6** additionally cannot decode receiver-side (no
tokenizer in this package's deps or Polar's — A-14 — so the builder
subclass is not a home either); the tokenizer-free landing design is
recorded: pin `g6_expected_tail_ids` on the next walk, then ids-
`endswith` over each pre-turn interstitial **and the `prompt_ids` suffix
for turn 1** — the first-turn clause added after the verification
measured that the first mask-1 span starts at `response_ids[0]` on both
real traces (a `response_ids`-only rule checks zero turns on a
single-turn episode).

#### Step 4 — the H-41 flag's shape

A trace whose `tools` roster is present and non-empty but whose message
stream carries zero parsed `tool_calls` — the predecessor's
gates-green-but-tool-free H-41 shape. Landed as a **policy-gated check**
(`H41:roster_offered_zero_tool_calls`), not a warning finding, because
the frozen receiver drops on any finding and the CP is explicit that a
legitimate episode can call no tools: default OFF, armed by
`CheckPolicy.reject_toolless_roster`. Roster absent is G3's
missing-evidence shape, deliberately not H41's. Visibility as landed:
the string is in the snapshot-tested vocabulary, the rule runs on both
law-6 legs when armed, and arming is one YAML line away once the
`ChecksConfig` mirror gains the field (declared drift, next config
freeze-lift). The primary H-41 defense remains loud at the engine (a
parser-less vLLM 400s pi's `tool_choice: auto` → zero completions →
builder ERROR, measured CP-07); this is the trace-side backstop for the
subtler parser-present-but-broken class.

#### Step 5 — the validate leg (row 23 closes)

The two real episodes are exactly what "first episode" means here (the
estate stayed down; no re-collection). Both pass the full seam clean —
admission, discipline, tripwires, G5, G2, G3, G7 — and each landed gate
fails on one doctored input for its own reason (the verbatim lines
above; equality asserts in the suite, so a co-firing rule would break
the test). No doctored input passed, so no pin and no convention needed
re-derivation. The golden structural mapping earns its own honest
treatment: it carries no wire evidence by construction, so as of this CP
the hash gates fail closed on it (`G3:missing_evidence:tools`,
`G2:missing_evidence:system_prompt`) while the discipline stays clean —
asserted as such, the fail-closed posture proven on a real artifact.

#### What this repo now checks, and what it does not — CP-12's inheritance

**Checked, both law-6 legs (`checks.py`, receiver + client identically):**
admission (`ADM1`–`ADM5`); the logprob discipline (`LP1`–`LP9`,
sentinel −9000, zero-rate allowance 0.25, RAW semantics); the tripwires
(`TR1` finish-reason allowlist — tail aborts; `TR2` re-vendor canary);
**G5** search-page census vs the structural timestep (fail-closed);
**G2** wire system prompt vs the `/workspace` singleton; **G3** wire
tool roster vs the pinned hash; **G7** the four-clause reconstruction
conjunction (fail-closed); **H-41** toolless-roster (armed by policy).
All hash gates consume `pins/pins.gsj.json` at check time; missing pins
raise (never fail open); hostile content (NaN, surrogates, big ints,
unhashable ids, non-string enums) yields findings, never exceptions.

**Checked builder-side, in Polar's process (CP-07 subclass):** explicit
EOT present (`A15`), per-completion token presence (`S1`/`S6`), choices
arity (`S8`), duplicate-prompt retries (`S3`), mid-chain length
(`S7`), roster stability (`R11`), version homogeneity (`S9`), agent
shape + filter drops (`A12`), plus the ADR-0007 glue stitch.

**Enforced at source rather than checked:** the page cutoff's clamp
(MCP service, verified-claims JWT) and checkout (`--depth 1` clone, no
remote, no reflog); compaction-off (the harness settings constant);
the engine pins (generation-config, tool parser — serve argv).

**Not checked, each with its owner and blocker:** G1 skill card (no
trace-side card identity; `prompt_source` in task metadata, config
freeze-lift + taskbank); G4 codec receiver-side (no evidence on the
callback; estate-side `derive_pins.py` at bring-up, CP-04′; per-episode
binding open, row 22); G6 thinking-off (needs `g6_expected_tail_ids` on
the next walk; then receiver-side ids rule incl. the first-turn
`prompt_ids` clause); G7's settings-hash clause (no callback evidence;
harness echo, next `pi_harness.py` lift); sampling provenance (row 22,
estate); replay (deliberately absent, F2–F4); mid-chain aborts (carried
patch P2's job, D3); per-completion records (never ride the callback,
A-5 — builder's domain); a fabricated-but-consistent stats block
(self-reported evidence — the wire admits it by construction, law 6's
declared limit, incl. the all-zero shape the verification measured);
zero-tool episodes when H-41 is unarmed (the default).

#### Verification

Six adversarial agents (five refutation lenses — gate fail-open/false-
rejection hunting with executed hostile payloads, hashing-convention
re-derivation, scope/prose-only compliance via AST comparison, budget
arithmetic, documentation fidelity — plus a fresh-eyes critic over
their raw findings), every claim settled by an executed command or a
file:line citation. Verdicts: 2 CONFIRMED_SOUND, 3 DEFECT_FOUND, critic
DEFECT_FOUND. Dispositions:

**Blocking, fixed here.** (1) Three never-raise breaches on JSON-legal
wire content — big-int logprob (OverflowError at `math.isfinite`),
unhashable `tool_call` id (TypeError in the G5 census), non-string
`finish_reason` (TypeError at the frozenset) — each reproduced against
HEAD too (inherited, not introduced), each escaping the frozen
receiver's `(ValueError, KeyError)` handler (connection drop, no
response) and the guardless client leg. Fixed in `checks.py` (the file
under lift): each shape now yields its owning finding; regression-locked
in the malformed-content corpus; net −1 line. (2) The charter budget
paragraph's per-pass endpoint attributions did not reproduce (each pass
TOTAL was a real measurement; the parentheticals mixed final endpoints
into the first pass) — rewritten with per-movement endpoints that
reproduce from `git show HEAD:` vs the tree, the same defect class CP-11's
verification caught in ITS budget paragraph, caught again.

**Real, fixed as documentation.** The G6 first-turn blind spot in
ADR-0011's landing design (measured: both traces' first mask-1 span at
`response_ids[0]`, the 7-id tail at `prompt_ids[-7:]`) — the ADR and row
14 now carry the `prompt_ids`-suffix clause. The pins cache's
process-lifetime (an on-disk re-pin is masked until restart) — now on
the cache line and in the spec. The receiver's ugly-but-closed pins
failure modes (missing KEY → 400 masquerade; missing FILE → unanswered
connection, half-persisted batch) and the client leg's total-failure
shape — measured live against a running receiver, recorded in the spec
with the seam cleanup named for `receiver.py`'s next lift. The dangling
`docs/reports/CP-11b.md` references — resolved by this file.

**Recorded, deliberately not fixed.** G7 admits a fabricated all-zero/
equal-negative stats block (equality clauses, no floor): spec-conformant,
builder-unreachable at the pin, and a floor buys nothing against a
consistent forger — the self-reported-evidence limit law 6 already
declares; recorded in the spec for CP-12. **Dispositioned as noise**,
each checked: the `G7:missing_evidence:reconstruction_stats.<key>`
dot-path detail (the field IS a path; prefix-grep contract intact); the
cli print consolidation (string-only AST delta, the sanctioned recovery);
pins not shipping in the wheel (fails CLOSED via FileNotFoundError;
both legs run from the checkout by design); the H-41 knob being
YAML-unreachable and revertible by a later `load_config` (documented
intent — ADR-0010's "last load wins" + the declared mirror drift).

**What held under attack**: no fail-open and no false rejection in any
landed gate across the full hostile battery (typed-parts/bare-mapping/
list envelopes pass G2, reordered-key canonical equivalents pass G3,
float/bool/string stats fail G7 closed, H41 arms and disarms exactly as
specced); both hashing conventions byte-match the predecessor's
executed originals on 15 adversarial inputs; every pinned value
re-derives; no pinned literal in code; the frozen surface diffs empty;
all 18 pre-existing vocabulary entries byte-identical with 10 pure
additions; 76/76 green.

#### DoD, run and shown

```
$ git diff HEAD -- vendor/ corpus/ mcp-service/ forgejo/ spike/ \
    gsj_rollout/receiver.py gsj_rollout/client.py
(empty)
$ .venv/bin/pytest -q
76 passed in 8.74s
$ wc -l gsj_rollout/*.py
  18 __init__.py  159 builder.py  407 checks.py  163 cli.py  123 client.py
  246 config.py  237 pi_harness.py  143 receiver.py  → 1496 total (/1500)
# per gate: §Step 2 above, verbatim; budget recovery: §Step 1, measured
$ .venv/bin/python pins/derive_pins.py | tail -1
all approved values reproduced
$ grep -n 'row 9\|row 1[0-5]\|row 23' docs/CHARTER.md | head
(rows 9–15 and 23 at their earned statuses — §gap_register above)
$ test -f docs/reports/CP-11b.md && echo OK
OK
$ git status --porcelain      # after commit
(empty)
```
