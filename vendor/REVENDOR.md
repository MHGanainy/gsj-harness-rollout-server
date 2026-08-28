# REVENDOR — moving the Polar pin

`vendor/polar` is upstream Polar ([`NVIDIA-NeMo/ProRL-Agent-Server`](https://github.com/NVIDIA-NeMo/ProRL-Agent-Server)) at the `stable`-branch commit recorded in `/POLAR_SHA`, with three carried patches applied on top. **The committed tree is the *patched* tree**; `vendor/patches/` exists so the next pin can be rebuilt from upstream, and `vendor/apply_patches.sh` applies (or verifies) the set. This page is the recipe for moving the pin — it has run twice (the first vendor on 2026-08-09, and a same-SHA rehearsal on 2026-08-12 that reproduced the committed tree byte-for-byte; `/POLAR_SHA` records both).

> [!NOTE]
> **Time budget, measured.** The mechanical loop — fetch → extract → patch → verify → venv rebuild → vendored suite — is **~2 minutes** on a warm `uv` cache (a cold cache adds dependency-download minutes); the full verification (all four suites + the pins walk + the registry seam) about **15 minutes**. The half-day figure is the *contingency* budget for re-anchoring patches when upstream moves under them — none of it is mechanism.

## Why vendor at all

Upstream has **no tags and no releases** — there is nothing to depend on. So the dependency is a pin: the `stable` branch's HEAD at a recorded SHA (development lands there via squash-merged PRs), vendored as a tree with no history — 4,387 of upstream's 4,406 commits are inherited OpenHands, so the history carries almost nothing of Polar's own.

## The pin record: `/POLAR_SHA`

One flat file at the repository root is the whole record of what is vendored:

| Line | What it records |
| --- | --- |
| `POLAR_SHA=<sha>` | the pinned commit — `f0e8343a7870abf6ec2366890f685881ceab92cb` today |
| `repo:` · `branch:` | where it came from — the `stable` branch of `NVIDIA-NeMo/ProRL-Agent-Server` |
| `commit:` | the pinned commit's subject, date, and author |
| `vendored:` · `re-vendored:` | each execution of this recipe: date and outcome |
| `excluded:` | the exclusion list — currently exactly one entry, an 8.3 MB training-data JSONL |
| `patches` | the three carried patch files, in apply order |
| `verify:` · `re-vendor:` | the verify command and the pointer to this recipe |

## The three carried patches

`vendor/patches/`, applied in order by `vendor/apply_patches.sh`. Each patch file opens with a header documenting its origin commits, its semantic anchors, and every adaptation already made — read it before touching that patch.

| Patch | What it does |
| --- | --- |
| `P1-non-agent-filter.patch` | Adds `record_filters.py` — a shape-only non-agent-completion filter plus truncated-marker and empty-choices filters — and wires `filter_trainable_completions()` into both trajectory builders; all-filtered sessions become trajectory `ERROR`, and the `prefix_merging` stats gain `raw_completions_total`. |
| `P2-abort-to-error.patch` | Any completion with `finish_reason == "abort"` anywhere in a session makes the trajectory `status="ERROR"` (`"aborted generation (weight-update cutoff)"`) in `PrefixMergingBuilder.build()` — without it a mid-chain abort merges cleanly and trains. |
| `P3-policy-version-storage.patch` | `SessionStore` stamps a live `policy_version` onto each turn's record metadata (`set_policy_version` / `get_policy_version` / `session_would_span`) and fixes metadata persistence (the writer payload is built from `dict(record.metadata)`); inert until a trainer declares versions. |

## The recipe

![The re-vendor recipe as five numbered steps: fetch upstream stable at a SHA, replace vendor/polar wholesale, apply the three carried patches in order, prove the tree, record the pin — with a rejected hunk looping back to a fresh extract](../docs/guide/img/revendor-recipe.png)

<sub>Moving the pin: upstream at a recorded SHA, a wholesale tree replacement, the three patches in order, proof before record. A rejected hunk means re-anchoring that one patch and restarting from a fresh extract.</sub>

### 1. Pick the new SHA

Pin the `stable` HEAD. Record the SHA, the date, and the reason for moving *before* touching the tree. If `stable` has **not** moved, re-vendoring to the same SHA is still a valid (and occasionally worthwhile) run of this recipe — it proves the pin reproduces.

Survey with `gh api` (the upstream web pages are robots-blocked): `stable`'s HEAD, the `polar` dev branch, tags, and whether any carried patch's subject landed upstream.

### 2. Fetch and verify the tree

No history — the tree at the SHA is all that is vendored:

```bash
git init /tmp/polar-new && cd /tmp/polar-new
git remote add origin https://github.com/NVIDIA-NeMo/ProRL-Agent-Server
git fetch --depth 1 origin <NEW_SHA>
git checkout FETCH_HEAD
git rev-parse HEAD          # MUST print <NEW_SHA> exactly
```

### 3. Replace the vendored tree

Delete `vendor/polar` entirely — keep nothing, stale files are how vendored trees rot — then re-extract and re-apply the exclusion list (currently exactly one entry, also listed in `/POLAR_SHA`):

```bash
rm -rf vendor/polar && mkdir -p vendor/polar
git -C /tmp/polar-new archive <NEW_SHA> | tar -x -C vendor/polar
rm vendor/polar/examples/swegym_slime_grpo/swegym_train_293.jsonl
```

### 4. Re-apply the patches, in order

```bash
bash vendor/apply_patches.sh
```

`git apply` is atomic per patch: a single rejected hunk fails that whole patch, loudly, with a non-zero exit — never a silently half-applied tree. On a reject, hand-re-adapt the failing patch against the new tree — each patch header documents its origin commits, its semantic anchors, and every adaptation already made — then regenerate that patch file (edit the diff, keep the header current) and re-run from a freshly extracted tree so the final patch set applies clean end-to-end.

> [!IMPORTANT]
> **The byte-fidelity tripwire** — run it immediately after the patches, before anything else:
>
> ```bash
> git status --porcelain -- vendor/     # same-SHA re-vendor: MUST be empty
> git diff HEAD --stat -- vendor/       # moved pin: exactly the upstream delta
> ```
>
> On a same-SHA re-vendor a single line of output means the recipe did not reproduce the committed tree (mode flip, stale exclusion, patch drift) — stop and find out why. On a moved pin, the diff must contain nothing but the upstream delta. The stronger per-patch check is the reverse-apply walk: `git apply -R` P3 → P2 → P1 walks the tree back to the pristine pin.

### 5. Verify the patched tree

```bash
bash vendor/apply_patches.sh --verify     # 10 symbol checks, all OK
cd vendor/polar
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . pytest pytest-asyncio
uv pip install -p .venv/bin/python -e ../..    # gsj_rollout — NOT optional, see below
.venv/bin/pytest -q
.venv/bin/python -c "from gsj_rollout.builder import ValidatingPrefixMergingBuilder as V; \
  from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder as P; \
  assert issubclass(V, P)"                     # the registry seam
```

> [!IMPORTANT]
> **The `-e ../..` line is not optional.** The polar venv hosts `gsj_rollout` (charter assumption A-14): Polar's `import_path` loads our harness and our `ValidatingPrefixMergingBuilder` into Polar's process. Without that install the venv builds fine but the registry seam fails (`ModuleNotFoundError: gsj_rollout`) — the server would not start against our config. The seam check above is the tripwire.

The carried-patch tests must be green — 25 tests across `test_record_filters.py`, `test_builder_filter_wiring.py`, `test_prefix_merging_abort.py`, and `test_storage_policy_version.py`. Compare upstream failures against the pre-existing set at `f0e8343a` — three (the sglang-router proxy 500, the dashboard templates route, the sglang meta_info `KeyError: 'token_id'`), a suite split of 175 passed / 3 failed. Do not chase those as regressions, but do record any new ones.

### 6. Record the pin

Update `/POLAR_SHA` (SHA, dates, the patch list if it changed) and the gap register in [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) §7 for the rows the re-vendor touched.

## What to re-run afterwards

Once the vendored tree passes, widen out — from the repository root:

```bash
pytest -q                                    # the root suite: 161
(cd estate/corpus && python -m pytest -q)    # the corpus suite: 58
(cd estate/mcp-service && .venv/bin/python -m pytest -q)   # the retrieval-service suite: 89 (venv per its README)
python pins/derive_pins.py                   # the pins walk: every approved value must reproduce
```

A moved pin in the pins walk means the re-vendor changed the wire — that is a finding, not a formality.

Then two checks that only matter when the tree actually changed:

- **The smoke test.** Drive Polar's calculator example (`vendor/polar/examples/calculator`) end-to-end, and re-dump the run artifacts under `docs/polar/` if their shapes changed — downstream code was built against those shapes. Conditional: if step 4's tripwire showed the re-vendored tree byte-identical to the previously committed one, the smoke cannot produce different shapes — skip it and say so.
- **The re-vendor canary.** Confirm no reasoning-masking support arrived upstream: per [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md), a trace whose metadata carries a `reasoning_loss_mask` key with `masked_tokens > 0` must still fail (the rule is deliberately not type-narrowed). The feature that would produce that key is fork-only today.

## Known divergences

- **The `polar` dev branch carries a pending `prefix_merging` refactor** (+49/−156, ~80 unlanded commits, including a new `gateway/engine.py`). Priced against a scratch tree with the refactor simulated as landed: the three patches' source hunks all apply clean — the refactored `build()` keeps a single `status="COMPLETED"` site (P2's block dry-ran onto it exactly) and the stats dict keeps its shape (P1's `raw_completions_total` landed). The only rejects are P1's two fixture-marker hunks in `test_engine_trajectory_equivalence.py` / `test_per_request_builder.py`, which the refactor rewrote — mechanical re-anchoring, not re-porting. If a future landing does reject wholesale, re-anchor on (a) the single `status="COMPLETED"` return in `build()` — P2's check must sit immediately before whatever finalizes a non-empty session — and (b) the reconstruction-stats dict for P1's `raw_completions_total`. Never pin the `polar` branch itself: at `98ec8fa2` it is frozen since 2026-06-06 and three commits *behind* `stable` (it lacks #37/#43/#45). Either way the vendored suite at the new pin is the real gate — a textual apply is not a behavioral proof.
- **The refactor grew a `policy_version` consumer**: `_top_level_scheduler_metadata` promotes `{group_id, policy_version, rollout_step}` to trajectory-level metadata — still no producer (`gateway/storage.py` untouched; P3 stays ours), but if it lands, P3's stamp becomes a key upstream's own scheduler layer reads. Check this first at the next survey.
- **File mode**: the fork carries `prefix_merging.py` as 100755; upstream is 100644. Keep 100644 — never let a patch flip it.
- **P3's storage anchors** (`_SessionState`, `save_message`'s lock block, the writer-enqueue payload) sat unchanged between the fork base and the pin except for fork-only metrics lines; the same string `dict(metadata or {})` appears TWICE in `save_message` — the fix targets only the writer-payload site (20-space indent), never the record-construction site (16-space indent).
- **Upstream is Anthropic-shape-drift-prone for P1**: the filter's SDK-only key list (`context_management` / `thinking` / `output_config` / `stream`) and the pi wire dialect must be re-validated (charter assumption A-12) whenever either side moves.

## Provenance

Citations the body used to carry inline, kept here verbatim so nothing is lost; they resolve in the operator's private record.

- The pin and the vendoring mechanism — "ADR-0004 the pin, ADR-0005 the mechanism".
- The measured time budget — "Budget, measured (CP-22)"; the half-day contingency figure — "ADR-0004's estimate; CP-03's first-vendor actual is in `docs/reports/CP-03.md`".
- The recipe's two executions — "CP-03 (first vendor, `f0e8343a`, wrote it); CP-22 (rehearsal, same SHA — `stable` had not moved — reproduced the committed tree byte-for-byte and corrected the steps marked [CP-22] below)".
- Recording a moved pin's SHA, date, and reason before touching the tree — originally "in a new ADR"; the same-SHA case — "no new ADR then, record the decision in the CP report instead" [CP-22].
- The no-history fetch's commit count — "4,387 of 4,406 commits are inherited OpenHands, CP-02".
- The byte-fidelity tripwire — added "[CP-22]"; the reverse-apply walk — "CP-03's reverse-apply standard (`git apply -R` P3→P2→P1 walks the tree back to the pristine pin) is the stronger per-patch check; CP-22 ran both".
- The venv defect the registry-seam check guards — "The recipe as first written omitted it; followed verbatim at CP-22 it produced a venv where the registry seam fails" (A-14).
- The pre-existing upstream failures — "recorded in `docs/reports/CP-03.md` (3 at `f0e8343a` …); [CP-22] confirmed the same three, byte-for-byte the same suite split 175 passed / 3 failed".
- The smoke test's reference transcript — "the calculator example per the CP-03 Step-5 transcript in `docs/reports/CP-03.md`"; the artifact consumers — "CP-06/CP-08 build against them"; the byte-identical skip condition — "[CP-22] Conditional".
- The reasoning-masking feature the canary watches for — "D4 is fork-only today" (the predecessor-fork defect table, CP-02).
- The refactor pricing — "[CP-22] **Priced, no longer just named**"; the `policy_version`-consumer note — "[CP-22]".
