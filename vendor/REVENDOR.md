# REVENDOR — moving the Polar pin

The vendored tree is upstream `stable` at the SHA in `/POLAR_SHA`, with the
three carried patches applied (ADR-0004 the pin, ADR-0005 the mechanism).
The committed tree is the *patched* tree; `vendor/patches/` exists so the
next pin can be rebuilt. Budget a half day (ADR-0004's estimate; CP-03's
actual first-vendor cost is in `docs/reports/CP-03.md`).

## Recipe

1. **Pick the new SHA.** Upstream has no tags or releases — pin the
   `stable` HEAD (development lands there via squash-merged PRs). Record
   the SHA, date, and reason for moving in a new ADR before touching the
   tree.

2. **Fetch and verify the tree** (no history — 4,387 of 4,406 commits are
   inherited OpenHands, CP-02):

   ```bash
   git init /tmp/polar-new && cd /tmp/polar-new
   git remote add origin https://github.com/NVIDIA-NeMo/ProRL-Agent-Server
   git fetch --depth 1 origin <NEW_SHA>
   git checkout FETCH_HEAD
   git rev-parse HEAD          # MUST print <NEW_SHA> exactly
   ```

3. **Replace the vendored tree.** Delete `vendor/polar` entirely (keep
   nothing — stale files are how vendored trees rot), re-extract, re-apply
   the exclusion list (currently exactly one entry, also listed in
   `/POLAR_SHA`):

   ```bash
   rm -rf vendor/polar && mkdir -p vendor/polar
   git -C /tmp/polar-new archive <NEW_SHA> | tar -x -C vendor/polar
   rm vendor/polar/examples/swegym_slime_grpo/swegym_train_293.jsonl
   ```

4. **Re-apply the patches, in order:**

   ```bash
   bash vendor/apply_patches.sh
   ```

   On a rejected hunk the script stops loudly. Resolve by hand-re-adapting
   the failing patch against the new tree — each patch header documents its
   origin SHA, its semantic anchors, and every adaptation already made —
   then regenerate that patch file (edit the diff, keep the header current)
   and re-run from a freshly extracted tree so the final patch set applies
   clean end-to-end.

5. **Verify:**

   ```bash
   bash vendor/apply_patches.sh --verify     # 10 symbol checks, all OK
   cd vendor/polar
   uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . pytest pytest-asyncio
   .venv/bin/pytest -q
   ```

   The carried-patch tests (`test_record_filters.py`,
   `test_builder_filter_wiring.py`, `test_prefix_merging_abort.py`,
   `test_storage_policy_version.py`) must be green. Compare upstream
   failures against the pre-existing set recorded in
   `docs/reports/CP-03.md` (3 at `f0e8343a`: sglang-router proxy 500,
   dashboard templates route, sglang meta_info `KeyError: 'token_id'`) —
   do not chase those as regressions, but do record any new ones.

6. **Re-run the smoke test** — the calculator example per the CP-03 Step-5
   transcript in `docs/reports/CP-03.md`, and re-dump the artifacts in
   `docs/polar/` if their shapes changed (CP-06/CP-08 build against them).

7. **Update `/POLAR_SHA`** (SHA, dates, patch list if it changed) and the
   gap register rows the re-vendor touched. Check the `checks-spec`
   re-vendor canary still holds (no reasoning-masking arrived: a
   `reasoning_loss_mask` metadata key with `masked_tokens > 0` must fail —
   D4 is fork-only today).

## Known risks, named

- **The `polar` dev branch carries a pending `prefix_merging` refactor
  (+49/−156)** (~80 unlanded commits, incl. a new `gateway/engine.py`).
  When it squash-lands on `stable`, expect P2 (and P1's prefix_merging
  wiring) to reject wholesale: re-anchor on (a) the single
  `status="COMPLETED"` return in `build()` — P2's check must sit
  immediately before whatever finalizes a non-empty session — and (b) the
  reconstruction-stats dict for P1's `raw_completions_total`.
- **File mode:** the fork carries `prefix_merging.py` as 100755; upstream
  is 100644. Keep 100644 — never let a patch flip it.
- **P3's storage anchors** (`_SessionState`, `save_message`'s lock block,
  the writer-enqueue payload) sat unchanged between the fork base and the
  pin except for fork-only metrics lines; the same string
  `dict(metadata or {})` appears TWICE in `save_message` — the fix targets
  only the writer-payload site (20-space indent), never the
  record-construction site (16-space indent).
- **Upstream is Anthropic-shape-drift-prone for P1:** the filter's
  SDK-only key list (`context_management`/`thinking`/`output_config`/
  `stream`) and the pi wire dialect must be re-validated (A-12) whenever
  either side moves.
