# ADR-0005 — Vendoring mechanism: committed patched tree at `vendor/polar/`, patches as re-vendor artifacts, component venv

## Context

ADR-0004 pinned upstream `stable` @ `f0e8343a` plus carried patches P1–P3.
Law 4 says vendor, don't depend; upstream has no releases and its git
history is 99% inherited OpenHands (CP-02), so "vendor" must mean the tree
at the SHA, not a submodule, subtree, or fork. CP-01's mcp-service set the
precedent that components may own their environments. The measured pin
tree: 206 files, 14 MB (of which one 8.3 MB training-data JSONL), core
runtime deps exactly `fastapi, uvicorn, httpx, pydantic, pyyaml`,
`requires-python >= 3.11` (README installs with 3.12).

## Decision

1. **Where:** `vendor/polar/`, the full tree at the pinned SHA extracted
   via `git archive` (no `.git`, no history), **committed to this repo**.
   The pin is recorded in `/POLAR_SHA`; the fetch is SHA-verified
   (`git fetch --depth 1 <SHA> && git rev-parse HEAD` must echo the pin).
2. **Budget:** the 1,500-line budget counts `gsj_rollout/` only (charter
   §1 already excludes vendored Polar; restated here as binding).
   `vendor/` never counts.
3. **Exclusions — exactly one file:**
   `examples/swegym_slime_grpo/swegym_train_293.jsonl` (8.3 MB = 60% of
   the tree; training-task data for the one Slime-GRPO *training* example,
   out of scope by the scope law — its absence breaks only that example's
   task sampling). Everything else vendors: `web/` (208 KB, optional
   dashboard SPA — the platform degrades to a JSON placeholder without a
   built `web/dist`), `uv.lock` (476 KB, upstream's tested resolution),
   all of `assets/` (2.9 MB doc imagery, including 728 KB referenced by
   nothing — binaries never produce mergeable diffs, and keeping them
   keeps `diff --stat` against upstream at exactly one line),
   `scripts/patch/` (documents the token metadata Polar expects from
   SGLang/Slime — spec knowledge). Vendored size: **5.3 MB, 205 files**.
4. **Patch carriage:** `vendor/patches/{P1,P2,P3}-*.patch`, applied in
   order (P2's context assumes P1 — both touch `prefix_merging.py`). Each
   patch is a unified diff prefixed by a header naming its origin fork
   SHA(s), what it does, why it is carried, the CP-02 evidence, and every
   adaptation made against the fork's version. `vendor/apply_patches.sh`
   applies them to a clean tree via `git apply` (atomic per patch, loud
   non-zero failure on any rejected hunk) and `--verify` greps ten
   expected symbols. **The committed `vendor/polar` tree is the *patched*
   tree** — a checkout works with zero install-time steps; the patches are
   re-vendor artifacts and `--verify` is the drift tripwire. Recipe:
   `vendor/REVENDOR.md`.
5. **Environment:** `vendor/polar/.venv` built per upstream's own recipe
   (`uv venv --python 3.12 && uv pip install -e .` + pytest/pytest-asyncio)
   — the CP-01 component-venv pattern. The root package's `[server]` extra
   stays **empty**, and root `requires-python` stays `>=3.11`: nothing
   forces a bump because 3.12 is confined to the component venv.
   Deliberately so: at CP-06 the dependency points the *other way* —
   Polar's `import_path` mechanism imports `gsj_rollout.pi_harness` into
   Polar's process, so `vendor/polar/.venv` will host our package, which
   works because our core deps (`pydantic, httpx, pyyaml`) are a strict
   subset of Polar's five (A-14). sglang/vLLM are **not installed**: Polar
   never imports them (they are HTTP request-shaping strategies over
   `inference.base_url`), and real token-emitting inference is a CP-09/GPU
   concern.

Rejected alternatives: submodule/subtree (depends on a release-less
personal-history upstream; law 4), installing Polar into the root venv
(inverts the real CP-06 import direction and drags fastapi/uvicorn into
the trainer-side surface), committing the pristine tree + install-time
patching (every checkout would need a mutation step before running, and
the repo state would not be the code that runs).

## Consequence

- Checkout-and-run; re-vendor = re-extract + re-apply + re-verify, with
  the `prefix_merging` refactor named as the known rebase risk
  (REVENDOR.md).
- The repo grows ~5.3 MB of vendored code; our own-line budget is
  unaffected by construction.
- Upstream's suite at the pin has 3 pre-existing failures (recorded in the
  CP-03 report); re-vendors must not chase them as regressions. With
  patches: 175 passed / 3 failed — the patch set adds 25 green tests and
  breaks nothing.
- A-14 (polar venv hosts gsj_rollout at CP-06; dep subset holds) enters
  the charter's assumption register.
