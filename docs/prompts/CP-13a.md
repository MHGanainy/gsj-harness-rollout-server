# CP-13 addendum — echo the workspace identity into the trace

Run immediately after `docs/prompts/CP-13.md`, as an extension of the same
checkpoint: **one additional commit**, `CP-13a: workspace identity echo`.
Everything CP-13's STOP wall forbids still holds — no GPU, no estate, no
template change, no re-pin, no taskbank, no `g6_expected_tail_ids`.

**Freeze-lift: `gsj_rollout/pi_harness.py` (the echo), plus `checks.py`
only if a check lands. NOT lifted: anything CP-13 did not lift.**

## Why

CP-13 Step 3 established (or refuted) a channel from the harness's runtime
into `trajectory.metadata`, for the rendered settings. **If that channel
works, the same channel should carry the environment the agent actually
saw** — and that is currently unrecorded anywhere.

Today a trace tells you which case and timestep were *requested*
(`TaskRequest.metadata`, CP-11). It does not tell you what the sandbox
*contained*. Those are the same thing only if the clone did what it was
told, and CP-11 already founday it silently doesn't — the full-depth
clone that leaked post-cutoff pages through `git show HEAD~1`. A requested
timestep is an intention; the checked-out tree is the fact.

**This is squarely inside the scope law** (task → sandbox → agent →
trace): it records what the sandbox was, at the moment the agent ran.

## What to echo

Captured in `setup()` or early `run_steps()` — after the clone, before pi
launches — and carried through the same channel Step 3 proved:

- **repo identity**: the clone URL as rendered (credential-stripped — the
  CP-11 reflog lesson: a URL in an artifact is a re-fetch path), the
  resolved `case_id`
- **branch and commit**: `git rev-parse --abbrev-ref HEAD` and
  `git rev-parse HEAD` — the branch the agent worked on and the exact
  commit, which is the corpus lock's own key
- **shallow posture**: `git rev-parse --is-shallow-repository`, the commit
  count, and whether any remote survives — the CP-11 cure, now attested
  per-episode rather than assumed from the cle page census**: the sorted `md/page_NNNN.md` filenames present, or
  their count plus min/max — **this is the load-bearing one**, because it
  is the checkout census CP-11 dropped from G5 as unreconstructable
- **a tree digest**: a stable hash over the workspace's tracked paths (or
  `git rev-parse HEAD^{tree}`), so a modified checkout is detectable

Keep it small and structured — a dict, not a shell dump. And **capture it
before the agent runs**, so what you record is the environment as
provisioned, not as the agent left it.

## What this unblocks

CP-11 dropped G5's checkout-census clauses (max page == T, contiguity from
1) because they need a sandbox-filesystem property no trace carries. If
this echo lands, that property *is* in the trace.

**But CP-11's rejection reasoning applies and must be answered, not
ignored**: it called a harness-recorded probe "the same self-reporting
class as the `case_status` circularity the structural timestep just
removed." That objection is real and this addendum does dissolve it —
what it changes is that a *deviating* echo is now visible, where before
there was no evidence at all.

So: land the echo, then decide explicitly whether to land the census
clauses as a check.

- **If yes** — state plainly that it detects an honest misconfiguration
  (wrong branch, wrong depth, truncated clone), not a hostile harness, and
  cross-check the echoed branch against `TaskRequest.metadata.timestep` so
  the check compares *two independently-sourced* facts rather than one
  self-report.
- **If no** — record the echo as forensic evidence with the reasoning, and
  say what would make it check-worthy.

Either answer is fine. An unexamined "we have data now, so let's gate on
it" is not.

## Verification

- The echo reaches `trajectory.metadata` — proven by executing the
  vendored hops, the CP-11 method, not by reading them.
- No credential appears in any echoed value (assert it, don't assume it —
  the clone URL is the obvious carrier).
- The echoed branch matches the requestedon both real fixtures,
  and a doctored mismatch is detectable (whether or not you gate on it).
- If the census clauses land: clean pass on both real traces, one doctored
  failure each, the CP-10 pattern.

## Definition of Done — run and show output
```
git diff HEAD -- vendor/ corpus/ forgejo/ pins/ spike/ \
  gsj_rollout/builder.py gsj_rollout/client.py gsj_rollout/cli.py   # → empty
pytest -q                                          # green, counts
wc -l gsj_rollout/*.py                             # against 2,000
# the echoed dict's shape, verbatim
# the vendored-hop trace proving it reaches trajectory.metadata
# the credential-absence assertion
# the census-clause decision, stated
test -f docs/reports/CP-13a.md && echo OK
git status --porcelain                             # → empty after commit
```
One commit: `CP-13a: workspace identity echo`.

## Report
`docs/reports/CP-13a.md`, brief — this is an addendum, not a checkpoint.
Under notes: the echoed fields and where they are captured in the
l; the proven path to trace metadata; the credential check; the
census decision with its reasoning; row 13's status if it changed; and
whether the echo makes any other dropped or blocked check reachable —
a re-read of the "not checked" list with this new evidence in hand is
worth the five minutes.
