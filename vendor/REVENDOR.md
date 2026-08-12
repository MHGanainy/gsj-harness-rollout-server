# REVENDOR — moving the Polar pin

The vendored tree is upstream `stable` at the SHA in `/POLAR_SHA`, with the
three carried patches applied (ADR-0004 the pin, ADR-0005 the mechanism).
The committed tree is the *patched* tree; `vendor/patches/` exists so the
next pin can be rebuilt.

**Budget, measured (CP-22)**: the mechanical loop — fetch → extract →
patch → verify → venv rebuild → vendored suite — is **~2 minutes** on a
warm uv cache (cold adds dependency-download minutes); the full
verification (all four suites + pins + the registry seam) ~15 minutes.
The half-day figure (ADR-0004's estimate; CP-03's first-vendor actual is
in `docs/reports/CP-03.md`) is the *contingency* budget for re-anchoring
patches when upstream moves under them — none of it is mechanism.

**Executions of this recipe**: CP-03 (first vendor, `f0e8343a`, wrote it);
CP-22 (rehearsal, same SHA — `stable` had not moved — reproduced the
committed tree byte-for-byte and corrected the steps marked [CP-22]
below).

## Recipe

1. **Pick the new SHA.** Upstream has no tags or releases — pin the
   `stable` HEAD (development lands there via squash-merged PRs). Record
   the SHA, date, and reason for moving in a new ADR before touching the
   tree. [CP-22] If `stable` has NOT moved, re-vendoring to the same SHA
   is still a valid (and occasionally worthwhile) run of this recipe — it
   proves the pin reproduces; no new ADR then, record the decision in the
   CP report instead. Survey with `gh api` (the web pages are
   robots-blocked): `stable`'s HEAD, the `polar` dev branch, tags, and
   whether any carried patch's subject landed upstream.

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

   [CP-22] **The byte-fidelity tripwire** — run it immediately after the
   patches, before anything else:

   ```bash
   git status --porcelain -- vendor/     # same-SHA re-vendor: MUST be empty
   git diff HEAD --stat -- vendor/       # moved pin: exactly the upstream delta
   ```

   On a same-SHA re-vendor a single line of output means the recipe did
   not reproduce the committed tree (mode flip, stale exclusion, patch
   drift) — stop and find out why. On a moved pin, the diff must contain
   nothing but the upstream delta. CP-03's reverse-apply standard
   (`git apply -R` P3→P2→P1 walks the tree back to the pristine pin) is
   the stronger per-patch check; CP-22 ran both.

5. **Verify:**

   ```bash
   bash vendor/apply_patches.sh --verify     # 10 symbol checks, all OK
   cd vendor/polar
   uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e . pytest pytest-asyncio
   uv pip install -p .venv/bin/python -e ../..    # [CP-22] gsj_rollout — see below
   .venv/bin/pytest -q
   .venv/bin/python -c "from gsj_rollout.builder import ValidatingPrefixMergingBuilder as V; \
     from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder as P; \
     assert issubclass(V, P)"                     # [CP-22] the registry seam
   ```

   [CP-22] **The `-e ../..` line is not optional.** The polar venv hosts
   `gsj_rollout` (A-14): Polar's `import_path` loads our harness and our
   `ValidatingPrefixMergingBuilder` into Polar's process. The recipe as
   first written omitted it; followed verbatim at CP-22 it produced a venv
   where the registry seam fails (`ModuleNotFoundError: gsj_rollout`) —
   the server would not start against our config. The seam check above is
   the tripwire.

   The carried-patch tests (`test_record_filters.py`,
   `test_builder_filter_wiring.py`, `test_prefix_merging_abort.py`,
   `test_storage_policy_version.py`) must be green — 25 tests between
   them. Compare upstream failures against the pre-existing set recorded
   in `docs/reports/CP-03.md` (3 at `f0e8343a`: sglang-router proxy 500,
   dashboard templates route, sglang meta_info `KeyError: 'token_id'`;
   [CP-22] confirmed the same three, byte-for-byte the same suite split
   175 passed / 3 failed) — do not chase those as regressions, but do
   record any new ones. Then the other suites and the pins walk from the
   repo root (`pytest -q`; corpus; mcp-service; `python
   pins/derive_pins.py` → every approved value must reproduce — a moved
   pin means the re-vendor changed the wire).

6. **Re-run the smoke test** — the calculator example per the CP-03 Step-5
   transcript in `docs/reports/CP-03.md`, and re-dump the artifacts in
   `docs/polar/` if their shapes changed (CP-06/CP-08 build against them).
   [CP-22] Conditional: if step 4's tripwire showed the re-vendored tree
   byte-identical to the previously committed one, the smoke cannot
   produce different shapes — skip it and say so. It earns its cost only
   when the tree actually changed.

7. **Update `/POLAR_SHA`** (SHA, dates, patch list if it changed) and the
   gap register rows the re-vendor touched. Check the `checks-spec`
   re-vendor canary still holds (no reasoning-masking arrived: a
   `reasoning_loss_mask` metadata key with `masked_tokens > 0` must fail —
   D4 is fork-only today).

## Known risks, named

- **The `polar` dev branch carries a pending `prefix_merging` refactor
  (+49/−156)** (~80 unlanded commits, incl. a new `gateway/engine.py`).
  [CP-22] **Priced, no longer just named**: with the refactor simulated as
  landed (scratch tree = pristine pin + the `polar`-branch versions of the
  files it touches, at `polar` @ `98ec8fa2`, frozen since 2026-06-06 and 3
  commits BEHIND `stable` — it lacks #37/#43/#45, so never pin it), the
  three patches' **source hunks all apply clean**: both anchors named
  below survived — the refactored `build()` keeps a single
  `status="COMPLETED"` site (P2's block dry-ran onto it exactly) and the
  stats dict keeps its shape (P1's `raw_completions_total` landed). The
  only rejects are P1's two fixture-marker hunks in
  `test_engine_trajectory_equivalence.py` / `test_per_request_builder.py`,
  which the refactor rewrote — mechanical re-anchoring, not re-porting.
  If a future landing does reject wholesale, re-anchor on (a) the single
  `status="COMPLETED"` return in `build()` — P2's check must sit
  immediately before whatever finalizes a non-empty session — and (b) the
  reconstruction-stats dict for P1's `raw_completions_total`. Either way
  the vendored suite at the new pin is the real gate — a textual apply is
  not a behavioral proof.
- [CP-22] **The refactor grew a `policy_version` consumer**:
  `_top_level_scheduler_metadata` promotes `{group_id, policy_version,
  rollout_step}` to trajectory-level metadata — still no producer
  (`gateway/storage.py` untouched; P3 stays ours), but if it lands, P3's
  stamp becomes a key upstream's own scheduler layer reads. Check this
  first at the next survey.
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
