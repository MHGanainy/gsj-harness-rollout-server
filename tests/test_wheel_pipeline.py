"""CP-34 (Step 3): the corpus pipeline rides the wheel.

The contract says validate before ingesting, but `corpus/ingest_corpus.py`
lived only in the checkout — a pip-install consumer had no path to the PASS
table without cloning the repo (the F-45 shape, one seam over). The cure is
the pins precedent applied to a module: a build-time force-include mapping
`estate/corpus/ingest_corpus.py` -> `gsj_rollout/ingest_corpus.py`, single source,
zero `gsj_rollout/*.py` change. These tests hold the two legs of that:
the mapping in pyproject (drift kills the packaged leg silently), and the
wheel layout actually answering `python -m gsj_rollout.ingest_corpus`.

CP-60 (wishlist 36, 48) applied the same mechanism twice more — the G2
reference capture (data: the singleton whose sha256 IS the packaged
`system_prompt_hash`, so a bring-your-own estate derives its prompt from
the wheel, not from a tripwired copy) and `estate/bringup.py` (a module,
`python -m gsj_rollout.bringup`). The bring-up was NOT standalone by
construction: measured on the 0.1.3 pre-shim artifact, `import
gsj_rollout.bringup` died at its checkout-relative `import ingest_corpus`.
The layout test below is that measurement, kept.

CP-72 renamed the tool — `estate/estate.py`, packaged `gsj_rollout.estate`
(wheels <= 0.1.5 carry the old name) — and folded the pipeline's standalone
entry points into it as the `validate` and `ingest` verbs. The pipeline's
own command-line entry keeps working with a deprecation notice on stderr
(suppressed for the estate tool's own subprocess calls via
GSJ_PIPELINE_DRIVER); the validate test below pins both.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_the_wheel_ships_the_corpus_pipeline_by_config():
    """Same arbitration as the pins mapping test: `tomllib`, fast and
    hermetic — the built artifact itself is proven once below."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text())
    include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert include["estate/corpus/ingest_corpus.py"] == "gsj_rollout/ingest_corpus.py"
    # The sdist root set must carry it too: `python -m build` builds the
    # wheel FROM the sdist, so omission there silently drops it (CP-19).
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    assert "estate/corpus/ingest_corpus.py" in sdist


def test_the_wheel_ships_the_g2_capture_and_the_estate_tool_by_config():
    """CP-60: the two later force-includes, both legs each (wishlist 36/48).
    `release.yml`'s required tuple (seven entries since CP-60) asserts both on
    the built artifact; this is the CI-side half (the tag path re-runs no test).
    CP-72: the estate tool's pair is the renamed one — the frozen release.yml
    still names `gsj_rollout/bringup.py` and must move at its next lift
    (wishlist 57) or the tag build fails."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text())
    include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    for src, dst in (("pins/container/system_prompt.container.derived.txt",
                      "gsj_rollout/pins/container/system_prompt.container.derived.txt"),
                     ("estate/estate.py", "gsj_rollout/estate.py")):
        assert include[src] == dst
        assert src in sdist
        assert (REPO / src).is_file()


def test_the_shipped_g2_capture_is_the_packaged_singleton():
    """The demo's sha tripwire (bootstrap.py, CP-34), moved in-suite: the
    file the wheel ships must hash to the packaged reference pins'
    `system_prompt_hash` — otherwise a consumer derives G2 from the wrong
    bytes and every episode quarantines G2-only."""
    capture = (REPO / "pins" / "container" / "system_prompt.container.derived.txt").read_bytes()
    pins = json.loads((REPO / "pins" / "pins.gsj.json").read_text())
    assert hashlib.sha256(capture).hexdigest() in pins["pins"]["system_prompt_hash"]


def test_packaged_pipeline_validate_reaches_the_pass_table(tmp_path):
    """The wheel layout (`site/gsj_rollout/` + the force-included module)
    answers `python -m gsj_rollout.ingest_corpus validate` with the per-case
    PASS table, against the staging corpus, with the checkout NOT on the
    path. CP-72: the invocation is a deprecated alias of the estate tool's
    `validate` verb — it still works, the notice names the replacement on
    stderr (never stdout: rebuild scripts parse the table), and the estate
    tool's own subprocess calls suppress it via GSJ_PIPELINE_DRIVER."""
    site = tmp_path / "site"
    pkg = site / "gsj_rollout"
    pkg.mkdir(parents=True)
    for src in (REPO / "gsj_rollout").glob("*.py"):
        shutil.copy(src, pkg / src.name)
    (pkg / "pins").mkdir()
    shutil.copy(REPO / "pins" / "pins.gsj.json", pkg / "pins" / "pins.gsj.json")
    shutil.copy(REPO / "estate" / "corpus" / "ingest_corpus.py", pkg / "ingest_corpus.py")

    result = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.ingest_corpus",
         "validate", "--corpus", str(REPO / "estate" / "corpus" / "staging")],
        capture_output=True, text=True, cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site)},
    )
    assert result.returncode == 0, result.stderr
    assert "== validate ==" in result.stdout
    assert "== validate: PASS" in result.stdout
    # per-case rows, not just the footer — the table a stranger reads
    assert "case_0001" in result.stdout
    # the deprecation (CP-72): notice on stderr, naming the folded verb
    assert "NOTICE: this entry point is deprecated" in result.stderr
    assert "python -m gsj_rollout.estate validate|ingest" in result.stderr
    assert "NOTICE" not in result.stdout
    # and the estate tool's own subprocess calls run notice-free
    driven = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.ingest_corpus",
         "validate", "--corpus", str(REPO / "estate" / "corpus" / "staging")],
        capture_output=True, text=True, cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site),
             "GSJ_PIPELINE_DRIVER": "estate"},
    )
    assert driven.returncode == 0, driven.stderr
    assert "NOTICE" not in driven.stderr


def test_packaged_estate_tool_imports_from_the_wheel_layout(tmp_path):
    """The wheel layout answers `import gsj_rollout.estate` with the
    checkout NOT on the path, binds the pipeline to the force-included
    sibling (not `estate/corpus/`), keeps the runs directory out of
    site-packages, and `python -m gsj_rollout.estate --help` prints the
    full verb set — the pre-shim 0.1.3 artifact failed the first assertion
    (as `gsj_rollout.bringup`, the tool's pre-CP-72 name)."""
    site = tmp_path / "site"
    pkg = site / "gsj_rollout"
    pkg.mkdir(parents=True)
    for src in (REPO / "gsj_rollout").glob("*.py"):
        shutil.copy(src, pkg / src.name)
    shutil.copy(REPO / "estate" / "corpus" / "ingest_corpus.py", pkg / "ingest_corpus.py")
    shutil.copy(REPO / "estate" / "estate.py", pkg / "estate.py")
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site)}

    probe = subprocess.run(
        [sys.executable, "-c",
         "import gsj_rollout.estate as e; print(e.CHECKOUT); print(e.INGEST); print(e.RUNS)"],
        capture_output=True, text=True, cwd=tmp_path, env=env)
    assert probe.returncode == 0, probe.stderr
    checkout, ingest, runs = probe.stdout.splitlines()
    assert checkout == "False"
    assert Path(ingest) == pkg / "ingest_corpus.py"
    assert Path(runs) == tmp_path / "runs"

    helped = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.estate", "--help"],
        capture_output=True, text=True, cwd=tmp_path, env=env)
    assert helped.returncode == 0, helped.stderr
    assert "{scaffold,validate,up,ingest,status,down}" in helped.stdout
