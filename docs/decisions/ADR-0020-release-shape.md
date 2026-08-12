# ADR-0020 — the release shape: Apache-2.0, wheel-only, trusted publishing

Date: 2026-08-12 (CP-19). Status: accepted.

## Context

CP-18 named the metadata gap: no `readme`, no `license`, no classifiers,
no URLs, and a `requires-python` claim (`>=3.11`) that nothing tested.
Filling it requires three decisions that outlive the checkpoint — what
licence the code is under, what artifacts a release consists of, and how
a release is authorised — plus one that CP-19 was asked to make and
could not complete alone (whether to actually publish).

The licence question is not a formality here. The tree vendors NVIDIA's
Polar (Apache-2.0, `vendor/polar/LICENSE`, Copyright 2026 NVIDIA), carries
three patches against it (`vendor/patches/P1..P3`), and the whole premise
of the repo (charter §2) is that Polar owns the episode-execution layer.
A consumer needs to know which terms apply to what.

## Decision

**1. Apache-2.0 for our code** (`LICENSE`, root; `license = "Apache-2.0"`
as a PEP 639 SPDX expression with `license-files = ["LICENSE"]`).

Chosen over MIT for two reasons specific to this tree. First, Polar is
Apache-2.0, so matching it means the repository holds **one** set of
terms rather than two a reader must reconcile — and the question "is
`pi_harness.py` a derivative of Polar?" stops changing what anyone's
obligations are. Second, Apache-2.0 §4(b) makes "state that you changed
it" an obligation rather than a courtesy, which is the discipline this
repo already practices for the carried patches (`vendor/REVENDOR.md`);
picking a licence that does not ask for it would be picking against our
own habit. MIT's simplicity buys nothing we need and drops the patent
grant.

The `LICENSE` file's terms body is byte-identical to `vendor/polar/LICENSE`
(verified by diff — it is the canonical Apache-2.0 text); only the
appendix copyright line differs.

**Polar's licence is kept distinct structurally, not textually.**
`vendor/polar/` keeps its own `LICENSE` in place and is covered by it. No
notice was appended to our `LICENSE` and no NOTICE file was invented,
because the two never meet in a released artifact: `vendor/` is in
**neither** the wheel nor the sdist, so nothing NVIDIA-authored ships
under this project's name. That is asserted at build time in
`release.yml` rather than asserted in prose.

**2. Wheel-only publication.** The package is pure Python
(`py3-none-any`); no consumer needs to build from source, and the actual
source is a public git repository named in the metadata. Against that,
the sdist was measured as a live hazard rather than a theoretical one:
the build backend's default root set is "every tracked path", producing
**4.6 MB / 835 files** including `vendor/polar/` (215 entries),
`corpus/`, `mcp-service/`, `forgejo/`, `spike/`, `staging/`, `docs/` and
`tests/`. One `twine upload dist/*` publishes all of it.

Two guards, because wheel-only alone protects the index and not the
operator: `release.yml` builds `--wheel` and uploads only that, **and**
`[tool.hatch.build.targets.sdist]` states an explicit root set so a local
`python -m build` cannot produce the 4.6 MB tarball at all. The stanza is
`only-include`, not `include`, and the distinction was measured: with
`include`, hatchling still applied its default file selection on top,
which globs README/LICENSE/pyproject **recursively** — the sdist retained
`vendor/polar/LICENSE`, `vendor/polar/pyproject.toml` and 20 vendored
`README.md` files. `only-include` narrows the root set instead of
extending it.

**3. Trusted publishing (OIDC), tag-triggered, TestPyPI first.**
No API token is stored in this repository and none has to be rotated.
`release.yml` is default-deny (`permissions: {}`) with `contents: read`
on the build job and `id-token: write` on the two publish jobs and
nowhere else; the publish jobs do not check the repository out at all.
The PyPI job is gated on both `needs: testpypi` and the ref being a
`v*` tag, so `workflow_dispatch` rehearses the entire path with no
possibility of reaching PyPI. The release does **not** re-run CI — it
re-runs the wheel job only, because that is the job whose subject is the
artifact being published; `corpus/` and `mcp-service/` are in no
artifact.

**4. `requires-python` narrowed `>=3.11` → `>=3.12`.** Nothing ever ran
3.11: CI is 3.12, every deployment target is 3.12, and the operator's
workstation venv is 3.13. Narrowing the claim was chosen over widening
CI, per the CP-19 prompt's own steer — a floor that nothing tests is a
promise, not a fact.

**5. CP-19 does not publish.** The operator was asked and chose to stop
at the path. Publication requires a pending publisher configured in the
PyPI and TestPyPI web UIs under the owning account — an action this
repository cannot perform — and a PyPI upload of a version is
irrevocable: PyPI refuses re-upload of `0.1.0` even after a yank, so the
only cure for a bad first release is `0.1.1`. Building the path and
rehearsing it locally is reversible; publishing is not.

## Consequence

`pip install gsj-harness-rollout-server` does not work today, and the
name is unclaimed on both indexes (verified: the PyPI JSON API returns
404 for it, while `httpx` returns 200 — the HTML project pages sit behind
a bot challenge that returns 200 for names that do not exist, so the JSON
API is the only reliable oracle). **The name is therefore not reserved,
and that is the standing risk of this decision**: anyone may claim
`gsj-harness-rollout-server` before we do. It is accepted because the
alternative is an irrevocable upload made to win a race.

What a release now costs, once the publishers exist: configure them once,
push a `v0.1.0` tag, and the workflow does the rest — build, assert the
exclusions, `twine check`, re-run CP-16's install proof against the exact
artifact, TestPyPI, then PyPI. The tag-vs-version check fails the run
before anything is built if they disagree.

Wishlist row 17 stays **OPEN** and records the two prerequisites, so the
path is not mistaken for a completed publication.
