"""CP-34 (Step 3): the corpus pipeline rides the wheel.

The contract says validate before ingesting, but `corpus/ingest_corpus.py`
lived only in the checkout — a pip-install consumer had no path to the PASS
table without cloning the repo (the F-45 shape, one seam over). The cure is
the pins precedent applied to a module: a build-time force-include mapping
`corpus/ingest_corpus.py` -> `gsj_rollout/ingest_corpus.py`, single source,
zero `gsj_rollout/*.py` change. These tests hold the two legs of that:
the mapping in pyproject (drift kills the packaged leg silently), and the
wheel layout actually answering `python -m gsj_rollout.ingest_corpus`.
"""

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
    assert include["corpus/ingest_corpus.py"] == "gsj_rollout/ingest_corpus.py"
    # The sdist root set must carry it too: `python -m build` builds the
    # wheel FROM the sdist, so omission there silently drops it (CP-19).
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    assert "corpus/ingest_corpus.py" in sdist


def test_packaged_pipeline_validate_reaches_the_pass_table(tmp_path):
    """The wheel layout (`site/gsj_rollout/` + the force-included module)
    answers `python -m gsj_rollout.ingest_corpus validate` with the per-case
    PASS table, against the staging corpus, with the checkout NOT on the
    path — a pip-install consumer's exact invocation."""
    site = tmp_path / "site"
    pkg = site / "gsj_rollout"
    pkg.mkdir(parents=True)
    for src in (REPO / "gsj_rollout").glob("*.py"):
        shutil.copy(src, pkg / src.name)
    (pkg / "pins").mkdir()
    shutil.copy(REPO / "pins" / "pins.gsj.json", pkg / "pins" / "pins.gsj.json")
    shutil.copy(REPO / "corpus" / "ingest_corpus.py", pkg / "ingest_corpus.py")

    result = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.ingest_corpus",
         "validate", "--corpus", str(REPO / "corpus" / "staging")],
        capture_output=True, text=True, cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site)},
    )
    assert result.returncode == 0, result.stderr
    assert "== validate ==" in result.stdout
    assert "== validate: PASS" in result.stdout
    # per-case rows, not just the footer — the table a stranger reads
    assert "case_0001" in result.stdout
