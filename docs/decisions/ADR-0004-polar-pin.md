# ADR-0004 — Polar pin: upstream `stable` HEAD `f0e8343a` + a named carry-patch set

## Context

CP-02 audited `NVIDIA-NeMo/ProRL-Agent-Server` via the authenticated REST
API (the prior research was robots-blocked off every GitHub page).
Findings that bear on the pin:

- **Upstream is slow, not dead.** Default branch `stable` HEAD is
  `f0e8343a7870abf6ec2366890f685881ceab92cb` ("Harbor evaluator and TMAX
  example (#45)", 2026-06-26) — unchanged for ~6 weeks, but feature
  branches were pushed 2026-07-15 (`rubric-prm`) and 2026-08-04
  (`binfeng/skill2env`), and the `polar` branch carries 80 unlanded dev
  commits, including a `prefix_merging` refactor (+49/−156). Development
  lands on `stable` via squash-merged PRs (zero open PRs is normal here,
  not abandonment). No tags, no releases — vendoring by SHA is the only
  option, as assumed (A-8).
- **The four A-7 defects resolved** (CP-02 report, per-defect detail):
  D1 confirmed and worse than reported (no non-agent completion filter
  exists at the pin at all), D2 partially confirmed (the vLLM `-9999.0`
  sentinel is unvalidated at the pin; the rest of the claim was fork-only
  code), D3 confirmed end-to-end (`finish_reason=="abort"` handled
  nowhere), D4 refuted for upstream (reasoning masking is fork-only).
  D5's "integrity template" is really a version-span (mixed-weight)
  exclusion feature revealing a further confirmed pin defect: sessions
  spanning a weight sync are recorded as clean and are retroactively
  unauditable.
- **Every fix lives in one personal fork** (`BryanChen408`), on feature
  branches that (a) sit on a base two commits *behind* the pin — missing
  #43's Slime/SGL migration, which independently closed two logprob holes
  we need closed — and (b) carry 98–203 commits of Ascend-NPU/math/t2a
  workload code we absolutely do not want. No maintainer fork exists:
  `billxbf` (the primary author) keeps a staging fork byte-identical to
  upstream `stable`.

## Decision

CP-03 vendors **upstream `stable` at
`f0e8343a7870abf6ec2366890f685881ceab92cb`**, plus a named, hand-adapted
carry-patch set (scope law 4). The patches are adaptations, **not
cherry-picks** — none of the source commits apply verbatim to the pin
because their fork base predates it:

- **P1 — non-agent completion filter** (from `cb6132824ad4` +
  `d764ecce0d0b`): a `record_filters.py` with the *shape-only*
  `_is_non_agent_side_completion` (post-fix form; never the content
  whitelist), wired into both builders. Blocks auxiliary harness LLM
  calls from becoming `chain_length=1` trainable traces with session
  reward (D1; measured density up to 27% of a batch on the fork).
  **Lands at CP-03.**
- **P2 — abort → session ERROR** (from `3c930e6da34d`, hunks 1–2 only;
  hunk 3 deletes fork-only code): any completion with
  `finish_reason=="abort"` marks the trajectory `status=ERROR` in
  `prefix_merging.build()`. Mid-chain aborts are otherwise invisible on
  the wire — no downstream check can compensate (D3). **Lands at CP-03.**
- **P3 — per-turn `policy_version` stamping** (from `08e59e75f679`,
  storage half only, ~45 adapted lines incl. the `dict(record.metadata)`
  persistence fix): makes mixed-weight sessions auditable; the receiver
  then enforces "all per-turn stamps equal". The admin-endpoint and
  entry-interception halves are efficiency, not integrity — not carried.
  **Lands at CP-03 as a carried patch; inert until the trainer declares
  versions (A-13 covers the interim).**

Not carried: the fork's reasoning masking (D4 — absent upstream, and we
run thinking-off with G6 failing closed; a one-line canary in `checks.py`
tripwires its return), and the fork's `_logprob_integrity` (doesn't apply
to the pin's rewritten `record_utils.py`; value-level guarding is
`checks.py`'s job on both sides of the wire, law 6).

## Consequence

- The pin is the newest curated upstream state and contains #43's
  logprob-extraction hardening; the three patches are small, localized
  (one new file + builder wiring; two hunks in `prefix_merging.build`;
  ~45 lines in `gateway/storage.py`), and documented here by source SHA.
- Re-vendor cost: moderate. Expect roughly a half-day per re-vendor:
  re-pin, re-apply P1–P3, re-run upstream's tests plus ours. The known
  rebase risk is the unlanded `polar`-branch `prefix_merging` refactor
  (+49/−156) — when it squash-lands on `stable`, P2 (and the builder
  wiring of P1) will need manual re-porting. The re-vendor recipe is
  recorded at CP-03.
- P1's shape criteria are Anthropic-API-shaped; A-12 requires
  re-validating them against pi 0.83.0's actual wire dialect at CP-06.
- Pinning a personal fork was rejected: wrong base (missing #43),
  ~200 commits of unrelated workload code, and single-maintainer risk.
  Waiting for upstream to land the fixes was rejected: no upstream PR
  proposes any of them.
