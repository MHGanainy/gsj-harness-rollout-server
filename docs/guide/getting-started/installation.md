[Documentation](../README.md) › Getting started

# Installation

This page installs the library for whichever of the two roles you play, explains the one trap that bites on the first `import` (the pins), lists the extras and why some extras you might expect do not exist (there is no `[docs]` extra either — this documentation is plain Markdown, read on GitHub), and describes how the vendored Polar gets its own virtual environment. By the end you will have a working install and know how to check it.

## Which role you are installing for

The package serves two roles that are easy to confuse on first contact.

| role | what you need | what you get |
| --- | --- | --- |
| **Trainer** — a training loop that submits tasks and collects traces | `pip install gsj-harness-rollout-server`, any Python ≥ 3.12, anywhere | `RolloutClient` (submit + collect), `checks` (re-verify every trace), `load_config`; the wheel weighs pydantic + httpx + pyyaml and runs no episodes |
| **Server** — the machine that runs episodes against an estate | a git checkout, an editable install, and Polar's own venv under `vendor/polar/.venv` | `gsj-rollout serve` (the receiver), the harness and builder that Polar loads, the test suite |

The published wheel is for the trainer role. If you only ever call a server that somebody else operates, stop after the [trainer section](#trainer-role-pip-install) and continue with the [trainer quickstart](trainer-quickstart.md). Everything on the server side additionally needs an estate — an inference engine, a Forgejo git host, the retrieval service and an ingested corpus — which no `pip install` provides; see [the estate](../guides/estate.md) and the [server quickstart](server-quickstart.md).

![Two lanes. Trainer: one pip install of gsj-harness-rollout-server 0.1.2 giving RolloutClient and checks — no Polar, no estate. Server: a numbered strip git clone, pip install -e .[dev], uv venv for Polar; the checkout feeds your venv (which runs gsj-rollout serve and submit) and Polar's venv (which runs polar serve_rollout and serve_gateway and hosts gsj_rollout too); a note reads Python 3.12 or newer everywhere](../img/install-paths.png)

<sub>Two roles, three installs. The trainer is one `pip install` and talks to a server over HTTP. The server is a clone plus two virtual environments: yours at the checkout root, and Polar's under `vendor/polar/.venv`, which is also where `gsj_rollout` must be importable — Polar's process loads the harness and the builder from the checkout by import path. Python 3.12 or newer on every path.</sub>

What each of the three installs pulls in, in one line each:

- `pip install gsj-harness-rollout-server` — the PyPI wheel, `0.1.2`, with `pydantic`, `httpx` and `pyyaml`; what lands in `site-packages/gsj_rollout/` is the eight modules, both pins sets and `ingest_corpus.py` (the [wheel section](#what-the-wheel-contains) below).
- `pip install -e ".[dev]"` in your own venv at the checkout root — the same package plus `pytest` and `pyarrow`, and the checkout's `vendor/polar/` at the pinned `POLAR_SHA` with its three carried patches.
- `uv venv --python 3.12` under `vendor/polar/`, then `uv pip install -e .` (Polar) and `uv pip install -e ../..` (`gsj_rollout`) into it — the environment the two Polar processes run from.

## Python version

`requires-python = ">=3.12"`. The floor is 3.12 because 3.12 is what is tested in CI and what the project deploys into: the retrieval service image, Polar's uv venv, and the reference collector all run 3.12. 3.13 runs the root suite on a workstation but is not in CI, and the wheel is `py3-none-any`, so any 3.12+ interpreter works for the trainer role. Nothing below 3.12 has ever run the code.

## Trainer role: pip install

```bash
python -m venv .venv && . .venv/bin/activate
pip install gsj-harness-rollout-server
python -c "import gsj_rollout; print(gsj_rollout.__version__)"   # 0.1.2
```

The core dependencies are exactly three: `pydantic`, `httpx`, `pyyaml`. No Polar, no pyarrow, no GPU stack. `import gsj_rollout` never imports `polar`; the two modules that do (`pi_harness`, `builder`) are deliberately not exported from the package root and are only ever loaded by Polar's own process.

```python
from gsj_rollout import RolloutClient, Trace, checks, load_config, RunConfig
```

The `gsj-rollout` console script is installed too. `gsj-rollout submit` works from the wheel against a running server; `gsj-rollout serve` needs the checkout (from a wheel it still renders the topology and prints the commands, but with a `NOTE:` line saying "this is an installed wheel — no wheel ships vendor/polar" and `<checkout>` placeholders, rather than failing on a missing file). See [the command line](../guides/cli.md).

> [!WARNING]
> **Read the pins section before your first `import gsj_rollout.checks`**
>
> The wheel ships the reference estate's approved sets, not neutral defaults. On any other estate every hash gate fails unless `GSJ_PINS_PATH` is set first. Details in [the pins trap](#the-pins-trap-on-first-import) below.

## Server role: a checkout

The server side runs from a clone of the repository, because it needs `vendor/polar/` — the vendored Polar tree that ships in no wheel.

```bash
git clone https://github.com/MHGanainy/gsj-harness-rollout-server
cd gsj-harness-rollout-server
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q          # the root suite; 161 tests, no estate needed
```

The editable install puts `gsj_rollout` on your venv's path and gives you the `gsj-rollout` console script; `[dev]` adds `pytest` and `pyarrow` (the latter for `submit --from-bank`, which the CLI imports lazily behind a named error so the core stays pyarrow-free).

### Polar's own venv

Polar does not run in your venv. It runs from its own uv-managed environment under `vendor/polar/.venv`, built with upstream's install recipe, and **that** environment is the one that hosts `gsj_rollout` at episode time: Polar loads our harness and our trajectory builder by import path (`gsj_rollout.pi_harness:PiHarness` is the config default), so `gsj_rollout` must be importable from inside Polar's process. The dependency points from Polar to us, not the other way round — which works because our three core dependencies are a subset of Polar's five (`fastapi`, `uvicorn`, `httpx`, `pydantic`, `pyyaml`).

```bash
cd vendor/polar
uv venv --python 3.12 .venv
uv pip install -p .venv/bin/python -e . pytest pytest-asyncio   # Polar itself
uv pip install -p .venv/bin/python -e ../..                     # gsj_rollout, into Polar's venv
.venv/bin/python -c "from gsj_rollout.builder import ValidatingPrefixMergingBuilder as V; \
  from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder as P; \
  assert issubclass(V, P)"                                      # the seam: our builder subclasses Polar's
cd ../..
```

> [!WARNING]
> **The `-e ../..` line is not optional**
>
> A Polar venv without `gsj_rollout` installed starts, renders nothing wrong, and then fails with `ModuleNotFoundError: gsj_rollout` the moment it tries to load the harness from the topology. The one-line `issubclass` check above is the tripwire; run it after any rebuild of the venv.

`gsj-rollout serve --config <yaml>` renders `topology.rendered.yaml` next to your config, prints the two Polar commands (`serve_rollout` and `serve_gateway`, both invoked as `<checkout>/vendor/polar/.venv/bin/polar … -c topology.rendered.yaml` with `PYTHONPATH=<checkout>`), and then runs our receiver. You run the two Polar processes yourself, from that venv. If the venv is missing, `serve` prints a NOTE pointing at `vendor/REVENDOR.md` instead of an `ENOENT`.

### How Polar is vendored

Polar (NVIDIA's `ProRL-Agent-Server`) publishes no tags or releases, so it is pinned by commit rather than by version: `POLAR_SHA` at the repository root records the SHA, the branch (`stable`), the vendor date, the one excluded file, and the three patches the tree carries (`P1-non-agent-filter`, `P2-abort-to-error`, `P3-policy-version-storage`, under `vendor/patches/`). The committed `vendor/polar/` tree is the *patched* tree — history is not vendored, only the files. `vendor/polar/` keeps NVIDIA's own Apache-2.0 `LICENSE` and ships in no released artifact.

```bash
bash vendor/apply_patches.sh --verify     # asserts all three patches are present; changes nothing
```

Moving the pin — fetch, extract, re-apply the patches, rebuild the venv, re-run the suites — is the recipe in `vendor/REVENDOR.md` in the checkout. You do not need it to install; you need it the day upstream `stable` moves and you want to follow.

## Extras

| extra | installs | for whom |
| --- | --- | --- |
| *(none)* | `pydantic`, `httpx`, `pyyaml` | the trainer role — submit, collect, re-verify |
| `dev` | `pytest`, `pyarrow` | anyone running the root suite; `pyarrow` backs `submit --from-bank` |
| `server` | *(empty)* | see below |

### Why `[server]` is empty

`[server]` exists and is deliberately empty. Polar runs from `vendor/polar/.venv` with upstream's own install, and — as described above — it is Polar's venv that imports `gsj_rollout`, not our venv that imports Polar. There is nothing for a `[server]` extra to pull in; the server-side install is "clone, `pip install -e .`, build Polar's venv", not a dependency set.

### Why there is no `[verl]` or `[slime]` extra

Two trainers have been driven end to end from this library, and neither can be expressed as a pip extra:

- **verl** must be installed `--no-deps` from git at a pinned SHA — its declared dependency closure drags in a GPU stack that a trainer host must not resolve through pip. Extras cannot say `--no-deps`, and PyPI rejects direct git URLs in published metadata anyway.
- **slime** is a 24.4 GB container image, not a pip target at all.

Each bridge's install is therefore a requirements file plus one documented command in the examples repository, under [`example_project/`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples). See [running a training loop](../guides/training-loop.md).

## The pins trap on first import

`gsj_rollout.checks` validates every trace against *approved sets* read from a pins file, and the wheel ships the reference estate's pins — so on **any other estate** every hash gate fails `*_not_approved` until `GSJ_PINS_PATH` points at your own file, set before the first import of `gsj_rollout.checks` and on both legs (receiver and trainer). A wrong path raises `PinsConfigurationError` on first use rather than falling through, and the file is read once per process, so a change needs a restart. The resolution order, the import-time `UserWarning`, the thinking-on set the wheel also carries, and how to derive a file for your estate are all on [Pins and approved sets](../concepts/pins.md#resolution-order).

```bash
export GSJ_PINS_PATH=/srv/my-estate/pins.gsj.json      # before the process starts, on BOTH legs
```

## What the wheel contains

Publication is wheel-only. Four source paths are copied into the wheel at build time and nothing else in the checkout is: the `pins/` and `estate/corpus/` files stay the single source in the tree and are force-included by the build backend, never duplicated.

![Two lanes, the checkout and the wheel 0.1.2 py3-none-any. Four rows cross from left to right: gsj_rollout/ (8 modules) via hatch packages; pins/pins.gsj.json, pins/thinking-on/pins.gsj.json and estate/corpus/ingest_corpus.py via force-include, landing under gsj_rollout/. A red never-ships row — vendor/, estate/, spike/, tests/, docs/, .github/ — points at a cross: nothing crosses](../img/wheel-contents.png)

<sub>Four paths cross from the checkout into the wheel — the package by hatchling's `packages`, the three data files by `force-include` — and nothing else does. The wheel is `0.1.2`, `py3-none-any`, and the only artifact published.</sub>

| in the wheel | copied from | why it rides along |
| --- | --- | --- |
| `gsj_rollout/` — `__init__`, `builder`, `checks`, `cli`, `client`, `config`, `pi_harness`, `receiver` | `gsj_rollout/` | the package; `gsj-rollout = gsj_rollout.cli:main` is the console script |
| `gsj_rollout/pins/pins.gsj.json` | `pins/pins.gsj.json` | the reference (thinking-off) approved sets, so the trainer leg validates on install |
| `gsj_rollout/pins/thinking-on/pins.gsj.json` | `pins/thinking-on/pins.gsj.json` | the thinking-on set, data only — something for `GSJ_PINS_PATH` to point at on a pip-only estate |
| `gsj_rollout/ingest_corpus.py` | `estate/corpus/ingest_corpus.py` | the corpus pipeline, standalone (stdlib + PyYAML; pyarrow lazily), so a pip consumer can validate a corpus tree without a clone |

Deliberately **not** in the wheel: `vendor/polar/` (NVIDIA-authored, under its own licence — nothing of it ships under this project's name), `estate/` (the corpus pipeline's tests, the retrieval service, the Forgejo and serving recipes), `tests/`, `docs/`, `spike/`, `.github/`. To see for yourself what a published wheel holds, without installing it:

```bash
pip download gsj-harness-rollout-server --no-deps && unzip -l gsj_harness_rollout_server-*.whl
```

With the wheel alone you can validate a corpus tree:

```bash
python -m gsj_rollout.ingest_corpus validate --corpus /path/to/corpus
```

See [the corpus](../guides/corpus.md) for the tree contract this checks.

### How a release proves the wheel

![A five-step strip — tag = version, build --wheel, assert what ships, install proof, TestPyPI then PyPI — over a row of tiles: the wheel, three green assertions (nothing leaked in; five must-ship paths; install proof in a fresh venv outside the checkout), and PyPI. A red rail from the three assertions leads to a tile reading nothing published — any assertion fails](../img/release-gate.png)

<sub>The release workflow builds the wheel and then proves it is the right wheel before anything is uploaded; any failed assertion stops the release with nothing published.</sub>

The release workflow runs on a `v*` tag (a manual run rehearses the same path but stops at TestPyPI). In order:

1. **Tag matches version** — the tag must equal `v` + the `version` in `pyproject.toml`; a mismatch would publish the wrong number under the right name and nothing downstream would ever say so.
2. **`python -m build --wheel`** — the wheel only; no sdist is published.
3. **Assert what ships** — on the built artifact, that no entry starts with `vendor/`, `estate/`, `spike/`, `tests/`, `docs/` or `.github/`, and that the five must-ship paths are present: `gsj_rollout/checks.py`, `gsj_rollout/client.py`, both pins files and `gsj_rollout/ingest_corpus.py`. `twine check` runs on the artifact too.
4. **Install proof, from outside the checkout** — the wheel is installed into a fresh venv and, with the working directory moved *away* from the repository, `checks.PINS_PATH` is asserted to be the packaged copy under `site-packages` and a real callback body is validated with zero findings. With the repository as the working directory, `import gsj_rollout` would bind to the source tree and prove nothing about the wheel.
5. **TestPyPI, then PyPI** — trusted publishing (an OIDC exchange, no stored token); the PyPI job is tag-gated as well as chained, so a rehearsal can never reach it.

The workflow does not re-run CI's suites — those guard components that are not in the artifact — and expects the tag to point at a commit CI has already validated.

## Checking the install

**Trainer**

```bash
python -c "from gsj_rollout import checks; print(checks.PINS_PATH)"
```

Expect the warning above if you have not set `GSJ_PINS_PATH` — that is the resolver telling you which pins you are about to validate against. Then continue with the [trainer quickstart](trainer-quickstart.md).

**Server**

```bash
pytest -q                                   # 161 passed
bash vendor/apply_patches.sh --verify       # every carried patch present
vendor/polar/.venv/bin/python -c "import gsj_rollout, polar; print('seam ok')"
gsj-rollout serve --config rollout.yaml --render-only
```

`--render-only` writes `topology.rendered.yaml` and prints the two Polar commands without starting the receiver, which is a cheap way to confirm the config parses and the Polar venv is found. Then continue with the [server quickstart](server-quickstart.md) and [configuration](../guides/configuration.md).

If something fails at this stage, [troubleshooting](../guides/troubleshooting.md) collects the known first-contact failures.

## See also

- [Trainer quickstart](trainer-quickstart.md) — from `pip install` to a first validated `Trace`.
- [Server quickstart](server-quickstart.md) — `serve`, the two Polar processes, and the first accepted episode.
- [Pins and approved sets](../concepts/pins.md) — the resolution order and the trap this page names.
- [Command line](../guides/cli.md) — the `gsj-rollout` console script the install provides.
- [Troubleshooting](../guides/troubleshooting.md) — the known first-contact failures.
