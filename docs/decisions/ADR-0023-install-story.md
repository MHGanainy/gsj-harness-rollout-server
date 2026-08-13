# ADR-0023 — the install story: no trainer extras, a requirements file per bridge

Date: 2026-08-13 (CP-25). Status: accepted.

## Context

The target consumer experience is `pip install gsj-harness-rollout-server`,
edit one config, `python train.py`. The wheel's own closure is honest —
pydantic + httpx + pyyaml (ADR-0001) — but a training loop needs a trainer,
and neither measured trainer is pip-expressible:

- **verl** must be installed `--no-deps` from git at the pinned SHA
  `1ae945592754cbeb1350cbe092fe6117070fd4c7` (uni-agent's own submodule pin,
  A-27). Installing it *with* deps drags verl's declared GPU-stack closure
  (vllm-class pins, flash-attn expectations) onto a trainer host that must
  not resolve it — CP-21 ran flash-free by measurement (F-12). `--no-deps`
  then leaves the real import closure unstated: CP-21's measured
  `ModuleNotFoundError` chain was torchdata, datasets, pillow, cachetools,
  tqdm, and the torch wheel itself needed the cu126 variant chosen against
  the box's driver. This is F-18 of the predecessor, returned.
- **slime** is not an install at all: the loop runs inside the
  `slimerl/slime:v0.3.0` image (24.4 GB) because the training leg needs the
  Megatron that image ships — Polar's documented Megatron pin lacks the
  module slime v0.3.0 imports (F-06).

Three candidate mechanisms were on the table: extras in `pyproject.toml`
(`[verl]`, `[slime]`), a constraints/requirements file per bridge in the
examples repo, or a documented two-step.

## Decision

**No `[verl]` or `[slime]` extras — ever, at this pin.** Two independent
hard blockers, either sufficient:

1. pip extras cannot express `--no-deps`; an extra listing
   `verl @ git+…@SHA` would install verl's full declared closure, which is
   exactly the failure the pin avoids.
2. PyPI rejects packages whose metadata carries direct URL requirements, so
   a wheel with such an extra is unpublishable — it would re-open wishlist
   17 as a hard error.

**What ships instead: a requirements file per bridge in the examples repo,
wrapped in one readable command.** `example_project/requirements.txt` states
the verl import closure explicitly (the five unstated packages included,
with the cu126 torch note), and `example_project/install.sh` is the one
command a consumer reads and runs — venv, wheel, closure, then the one
`--no-deps` git line, in that order, each step commented with its reason.
The slime leg stays what it measurably is: an image pull plus mounted
checkouts, documented in `slime_bridge/cp17_loop/`, named in the run book as
the alternative rather than dressed up as an install.

The honest boundary, restated: the **server** leg needs an estate — a served
engine, Forgejo, the MCP service, Polar's two processes — and no packaging
decision changes that. The README's two-roles split governs; the install
instructions inherit it.

## Consequence

- `pyproject.toml` records the absence as a decision (comment in
  `[project.optional-dependencies]` citing this ADR), so the next reader
  does not "fix" it by adding the extra PyPI will refuse.
- The examples repo owns install truth per bridge; a closure change at a
  verl re-pin edits one requirements file, not published metadata.
- A consumer on a flash-attn-equipped host may install verl's real closure
  instead; the requirements file says so rather than forbidding it.
