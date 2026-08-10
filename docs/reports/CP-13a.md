### CP-13a REPORT
status: done
scope_drift: **one declared, named rather than folded in.** The addendum lifts `pi_harness.py` and `checks.py` (the latter "only if a check lands" — one did). `gsj_rollout/receiver.py` was also touched, for three lines: CP-13's own fresh-eyes critic, which returned after CP-13 was committed, reproduced a **regression CP-13 introduced** — two members of one envelope sharing a `session_id` shared a `.tmp`, so the first commit consumed it and the second raised `FileNotFoundError` *after* one file had landed, with the counters saying nothing was accepted. Leaving a known half-persisting regression in a file this addendum's sibling had just lifted was the worse option; it is fixed here (one disposition per `session_id`, last-wins; indexed stage paths) with its own regression test. Everything else holds: the DoD's frozen surface diffs empty, `pins/pins.gsj.json` is byte-identical (`derive_pins.py` still reports "all approved values reproduced"), the predecessor is untouched, and no GPU, estate, template change, re-pin, taskbank work, or `g6_expected_tail_ids` appears
files: 9 files changed — new: `docs/prompts/CP-13a.md`, `docs/reports/CP-13a.md` (this), `docs/decisions/ADR-0014-census-allowances.md`; modified: `gsj_rollout/pi_harness.py` (the workspace probe, credential stripping, the shared echo, 258 → 322), `gsj_rollout/checks.py` (`check_workspace` + 5 vocabulary constants, 460 → 497), `gsj_rollout/receiver.py` (the duplicate-`session_id` fix, 181 → 184), `tests/` (conftest's workspace stamp + `test_pi_harness.py` + `test_checks.py` + `test_receiver.py`, +18 tests), `docs/CHARTER.md` (rows 13 and 22, §3's module table + budget, §4 unchanged), `docs/checks-spec.md` (§The checkout census, returned; the G5 landing note; the vocabulary)
tests: `.venv/bin/pytest -q` → **121 passed** (103 at CP-13, +18)
adrs: ADR-0014 (`checks.py` 480 → 520; `pi_harness.py`'s CP-00 estimate 50–150 → 350, settled rather than left as silent drift)        assumptions: none added — the echo stands on **A-23**, added at CP-13
gap_register: **row 13's dropped clauses RETURN** — max checkout page == T and contiguity from 1 land as `checks.check_workspace`, with the CP-11 clone cure now attested per-episode; the row keeps PARITY and records what the check does and does not detect. **Row 22's corpus half closes** — each episode is now bound to the exact commit and tree it ran against; the codec and sampling halves stay estate-owned (ADR-0011, F1). §3 gains the [CP-13a] budget paragraph (1,746/2,000) and the module table carries its ADR-set allowances
questions:
  - Corrupted span, §Why: "CP-11 already founday it silently doesn't" → "CP-11 already **found that** it silently doesn't" (the sentence's referent is the full-depth clone that leaked post-cutoff pages — CP-10 found it, CP-11 cured it).
  - Corrupted span, §What to echo, third bullet: "assumed from the cle page census**: the sorted `md/page_NNNN.md` filenames" → "assumed from the **clone flags**\n- **the page census**: the sorted `md/page_NNNN.md` filenames…" (the run-on swallowed the end of the shallow-posture bullet and the start of the page-census bullet; the list's five items are repo identity / branch and commit / shallow posture / page census / tree digest).
  - Corrupted span, §Verification: "The echoed branch matches the requestedon both real fixtures" → "matches the requested **timestep** on both real fixtures".
  - Corrupted span, §Report: "where they are captured in the l;" → "where they are captured in the **lifecycle**;".
  - Applied default, **the page census is `{count, min, max}`, not the filename list**. The addendum offers either; the prompt also says "keep it small and structured". Count/min/max is sufficient for both predecessor clauses (max == T directly; contiguity from 1 as `min == 1 ∧ count == max`) and stays a fixed three integers whatever the document's length, where the filename list grows with it and rides every completion record.
  - Applied default, **the tree digest is `git rev-parse HEAD^{tree}`**, the addendum's own parenthetical, rather than a hash computed over tracked paths: it is the git object that already means "the content of this checkout", costs one probe line, and needs no convention of ours to be reproducible.
  - Applied default, **the census fails closed on a missing echo** (`G5:missing_evidence:workspace`), consistent with every other gate and with the spec's stated posture, which is why the two real fixtures gain a third stamped statement (§the census decision).
  - Applied default, **the probe runs as one exec at the end of `setup()`**, not in `run_steps()`: `setup()` is after the clone and before pi launches (the addendum's window), and putting it in `run_steps()` would either mix probe output into pi's transcript or cost a second exec in the run path.
next: advisory — unchanged from CP-13. CP-04′/CP-09′ when the H200 frees, or M4. Wishlist item 9 (G1's card hash computed sandbox-side) now has a concrete vehicle: this probe already reads the checkout, so hashing `skills/<name>/SKILL.md` there is a few lines in the same exec — deliberately NOT done here, being outside this addendum's stated echo list. Nothing drafted.

---

#### The echoed dict, verbatim

Captured by `PiHarness._probe_workspace` in one exec at the end of
`setup()` — after the clone, before pi launches, so it records the
environment **as provisioned** rather than as the agent left it:

```json
{
  "branch": "timestep-12",
  "case_id": "case_0001",
  "clone_url": "http://host.docker.internal:3000/gsj-staging/case_0001.git",
  "commit": "0000000000000000000000000000000000000000",
  "commits": 1,
  "pages": {"count": 12, "max": 12, "min": 1},
  "remotes": 0,
  "shallow": true,
  "tree": "1111111111111111111111111111111111111111"
}
```

(the `commit`/`tree` values above are the test fixture's placeholders; the
hop run below shows real-shaped ones). Each field answers a question the
trace could not previously answer: **what repo** (credential-stripped URL,
case id), **what the agent worked on** (branch, commit, tree — a modified
checkout is detectable), **whether the CP-11 cure actually applied**
(`shallow`, `commits`, `remotes` — attested per episode instead of assumed
from the clone flags), and **what pages existed** (the checkout census G5
dropped as unreconstructable).

#### The proven path to trace metadata

Executed against the real vendored classes in the component venv, the
CP-11 method — and deliberately driven with a **credentialed** clone URL so
the credential check is exercised on the real path rather than in a unit
test:

```
$ PYTHONPATH=<repo> vendor/polar/.venv/bin/python hops_13a.py
hop1 dispatch-register: {'case_id': 'case_0001', 'timestep': 12, 'prompt_source': 'free'}
hop2 harness echo (real register(), session.py:87-88):
     gsj_workspace = {"branch": "timestep-12", "case_id": "case_0001", "clone_url":
       "http://forgejo:3000/gsj-staging/case_0001.git", "commit": "6d4e0f6a…f900",
       "commits": 1, "pages": {"count": 12, "max": 12, "min": 1}, "remotes": 0,
       "shallow": true, "tree": "aabbccdd…ccdd"}
     status preserved: RUNNING | registered: True | task_id: t-13a
     probed after the clone, before pi: True / no pi launch in setup
hop3 _completion_metadata keys: ['case_id', 'gsj_settings', 'gsj_workspace',
       'prompt_source', 'session_id', 'task_id', 'timestep']
hop4 _chain_metadata → trace top-level keys: [same seven]
gate: check_workspace(echoed)=[] | doctored branch ->
       ['G5:workspace_branch_ne_timestep:timestep-18!=timestep-12']
ALL HOPS EXECUTED — the workspace echo reaches trace metadata
```

The ordering assertion in that run is load-bearing and is also a unit
test: the probe is the last `setup()` exec and no pi launch appears in
`setup()` at all, so the echo lands before any completion exists — which
is what makes the builder's first-completion hoist carry it.

#### The credential check

Asserted, not assumed. The hop run above fed
`http://gsj-bot:s3cr3t@forgejo:3000/gsj-staging/{case_id}.git` and then
searched the *whole serialized trace metadata*:

```
credential check: echoed clone_url = http://forgejo:3000/gsj-staging/case_0001.git
                  no credential anywhere in trace metadata ✓
                  the clone command still uses it: True
```

Only the echo is stripped — the clone the sandbox runs still uses the
credentialed URL, so nothing about fetching changes. `_strip_credentials`
is separately table-tested across six shapes, including the one that
matters for not over-stripping: an `@` in the *path* stays
(`http://h/a@b.git`).

#### The probe, run against a real repository

The hop run drives a fake runtime, so the shell itself was proven
separately — the rendered probe executed against a recipe-shaped clone
(an 18-page `main`, a `timestep-12` truncation commit on top, cloned with
the CP-11 flags):

```
rc: 0
branch=timestep-12
commit=08c0287a2466e4d67ae9f6887ddefcc52e78cbd5
tree=45238c0bad29f87fc3f2deed723636a47e71fd9c
shallow=false
commits=2
remotes=       0
pages=0001 0002 0003 0004 0005 0006 0007 0008 0009 0010 0011 0012
parsed pages -> {'count': 12, 'min': 1, 'max': 12}
```

The census is exactly right — 12 contiguous pages for `timestep-12`,
proving the parse against real `ls` output rather than a canned string.
And `shallow=false, commits=2` is not a bug in the probe: **git ignores
`--depth` for local-path clones** ("warning: --depth is ignored in local
clones; use file:// instead"), so this checkout genuinely did not get the
CP-11 cure — and `check_workspace` fires
`G5:checkout_history_posture:shallow=False,remotes=0` on it. That is the
posture clause catching a real misconfiguration on its first contact with
a real repository, which is a better argument for the clause than any
doctored fixture.

One parse note the run surfaced: BSD `wc -l` pads (`remotes=       0`).
`int()` strips it, and the echo carries the parsed integer, so nothing
ragged rides the trace. A probe whose inner `git` fails is loud rather
than quiet — `echo "k=$(git …)"` exits 0 regardless, so an empty required
field raises instead of echoing an empty census as fact (tested).

#### The census decision: land it, scoped

**Landed.** CP-11's objection — a harness-recorded probe is "the same
self-reporting class as the `case_status` circularity the structural
timestep just removed" — is answered per clause rather than waved away:

| finding | clause | sourcing |
|---|---|---|
| `G5:workspace_branch_ne_timestep:timestep-18!=timestep-12` | branch == `timestep-{T}` | **cross-sourced** — the harness's git vs the trainer's `TaskRequest.metadata.timestep` |
| `G5:checkout_max_page_ne_timestep:18!=12` | max checkout page == T | **cross-sourced**, same two independent origins |
| `G5:checkout_pages_not_contiguous:2-12/11` | contiguous from 1 | single-source |
| `G5:checkout_history_posture:shallow=False,remotes=0` | the CP-11 clone cure, per episode | single-source |
| `G5:missing_evidence:workspace` | no echo / a non-integer census | fail-closed |

Clean on both real episodes in the post-CP-13a stamped shape (`CP-07
stamped: []`, `CP-09 stamped: []`), one doctored failure per clause above,
verbatim — the CP-10 pattern.

**What it detects, said plainly: an honest misconfiguration** — a wrong
branch, a clone that lost `--depth 1`, a surviving remote, a truncated or
mis-built checkout. **What it does not detect: a harness that lies about
its own sandbox.** No arrangement of these clauses fixes that; it needs an
attestation channel this repo does not have. What the two cross-sourced
clauses buy is real but bounded: they raise the cost of a lie from "say
nothing" to "say something consistent with the trainer's independently
supplied timestep". That is exactly the improvement CP-11's objection
asked for, and the spec and row 13 both say it is no more than that.

The two fixture-era bodies gain a third stamped statement, on the same
terms as CP-13's two: the raw fixtures on disk stay verbatim and are
asserted to earn `G5:missing_evidence:workspace` honestly, while the
stamped shape — exactly what a CP-13a collection produces for
`case_0001`/`timestep-12`, pages 1–12 because every `timestep-{T}` branch
holds pages 1..T (`corpus/ingest_corpus.py:601-612`) — passes clean.

#### What else the echo makes reachable — the "not checked" re-read

Two things, one of them cheap:

- **Wishlist item 9 (G1's card hash computed sandbox-side) now has a
  vehicle.** The predecessor hashed `skills/<name>/SKILL.md` read from the
  episode's own checkout; this probe already reads that checkout, so the
  hash is a few lines in the same exec. Not done here — it is outside the
  addendum's stated echo list — but the item stops being architectural and
  becomes small.
- **Row 22's corpus half closes.** Its open residual was per-episode
  binding: nothing tied episode N to what it actually ran against. The
  commit and tree do exactly that for the corpus. The codec and sampling
  halves are untouched and stay estate-owned (ADR-0011, F1) — the echo is
  the harness's view of a filesystem, and the engine's identity is not
  visible from there.

Everything else on the list is unmoved and for the same reasons as before:
G4 and G6 need codec and tokenizer facts the sandbox cannot see; replay
needs an engine; mid-chain aborts are carried patch P2's; per-completion
records never ride the callback. Row 2's residual (an agent guessing the
Forgejo endpoint and re-cloning over the network) is *partly* strengthened
— `remotes=0` is now attested per episode rather than assumed — but the
network-guess half remains estate posture, unchanged.

#### The budget

```
                CP-13    CP-13a   delta   what
checks.py         460       497     +37   check_workspace + 5 vocabulary constants
pi_harness.py     258       322     +64   the probe, credential stripping, the shared echo
receiver.py       181       184      +3   the duplicate-session_id fix
everything else   743       743       0
total           1,642     1,746    +104
```

**1,746 / 2,000.** `checks.py` passed ADR-0013's 480, and `pi_harness.py`
had stood above its CP-00 estimate of 50–150 since CP-07 with no ADR ever
saying so. **ADR-0014** settles both (520 and 350) rather than leaving one
module's overshoot formal and the other's silent, and §3's module table now
carries the ADR-set numbers instead of the CP-00 guess. The law is
untouched.

#### DoD, run and shown

```
$ git diff HEAD -- vendor/ corpus/ forgejo/ pins/ spike/ \
    gsj_rollout/builder.py gsj_rollout/client.py gsj_rollout/cli.py
(empty)
$ .venv/bin/pytest -q
121 passed in 12.72s
$ wc -l gsj_rollout/*.py
  18 __init__.py  159 builder.py  497 checks.py  163 cli.py  123 client.py
  280 config.py   322 pi_harness.py  184 receiver.py  → 1746 total (/2000)
# the echoed dict's shape:                    §The echoed dict, verbatim
# the vendored-hop trace:                     §The proven path, executed
# the credential-absence assertion:           §The credential check
# the census-clause decision:                 §The census decision: land it, scoped
$ .venv/bin/python pins/derive_pins.py | tail -1
all approved values reproduced          # no re-pin
$ git -C /Users/elganayni/mg/workspace/gsj-envloader status --porcelain
(empty — the predecessor untouched)
$ test -f docs/reports/CP-13a.md && echo OK
OK
$ git status --porcelain      # after commit
(empty)
```
