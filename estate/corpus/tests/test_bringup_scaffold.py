"""CP-71 (CP-70 item 12): `bringup.py scaffold` — the annotated starting
tree. It must validate unmodified, ingest on the file:// rail, refuse a
non-empty target, and be named by `up`'s not-a-corpus refusal. The tool is
exercised as a consumer runs it (a subprocess), not imported."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import ingest_corpus as ic

BRINGUP = Path(__file__).resolve().parents[2] / "bringup.py"


def run_bringup(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BRINGUP), *args],
                          capture_output=True, text=True)


def test_scaffold_writes_a_tree_that_validates_unmodified(tmp_path, capsys):
    out = tmp_path / "my-corpus"
    proc = run_bringup("scaffold", "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert "validates as written" in proc.stdout
    assert "validate --corpus" in proc.stdout and "up --corpus" in proc.stdout
    # the tree, as promised: splits, one case, one timestep, pages/
    assert (out / "corpus.yaml").is_file()
    assert (out / "AGENTS.md").is_file()
    assert (out / "skills" / "example" / "SKILL.md").is_file()
    assert (out / "train" / "cases" / "case_example" / "timestep-1" /
            "pages" / "page_0001.md").is_file()
    assert (out / "eval" / "cases").is_dir()
    # none of the three deprecated estate fields, every field commented
    text = (out / "corpus.yaml").read_text(encoding="utf-8")
    for gone in ("forgejo:", "mcp:", "\nsandbox_image:"):
        assert gone not in text
    for marker in ("CHANGE THIS", "DO NOT CHANGE", "DEPRECATED"):
        assert marker in text
    assert ic.main(["validate", "--corpus", str(out)]) == 0
    assert "== validate: PASS" in capsys.readouterr().out


def test_scaffolded_corpus_ingests_on_the_file_rail(tmp_path):
    """The tree is not just shaped right — it scaffolds, banks, and its
    two prompt forms land as rows with generated ids (the free id a
    content hash of the example text)."""
    import hashlib
    out = tmp_path / "my-corpus"
    assert run_bringup("scaffold", "--out", str(out)).returncode == 0
    estate = tmp_path / "estate"
    estate.mkdir()
    assert ic.main(["scaffold", "--corpus", str(out),
                    "--base-url", f"file://{estate}"]) == 0
    assert ic.main(["taskbank", "--corpus", str(out)]) == 0
    rows = ic.read_taskbank_rows(out / "taskbank.parquet")
    free_text = "Which parties are named so far? Cite pages as (page:N)."
    want = {("case_example", 1, "skill:example"),
            ("case_example", 1,
             "free:" + hashlib.sha256(free_text.encode()).hexdigest()[:12])}
    assert {(r["case_id"], r["timestep"], r["prompt_id"])
            for r in rows} == want
    for row in rows:
        assert row["sandbox_image"] == ic.DEFAULT_SANDBOX_IMAGE


def test_scaffold_refuses_a_file_target_in_words(tmp_path):
    """The CP-71 review's find: --out naming an existing FILE crashed with
    a raw NotADirectoryError instead of the CP-27 refusal shape."""
    target = tmp_path / "afile"
    target.write_text("mine", encoding="utf-8")
    proc = run_bringup("scaffold", "--out", str(target))
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "is not a directory" in proc.stderr
    assert target.read_text(encoding="utf-8") == "mine"


def test_scaffold_refuses_a_nonempty_target(tmp_path):
    out = tmp_path / "occupied"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    proc = run_bringup("scaffold", "--out", str(out))
    assert proc.returncode == 1
    assert "never" in proc.stderr and "overwrites" in proc.stderr
    assert (out / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_up_on_a_missing_corpus_names_scaffold(tmp_path):
    """CP-70 item 12's other half: 'not a corpus root' tells a starting
    reader nothing — the refusal hands them the verb that writes one."""
    proc = run_bringup("up", "--corpus", str(tmp_path / "nothing-here"),
                       "-y", "--runs-dir", str(tmp_path / "runs"))
    assert proc.returncode == 1
    assert "scaffold --out" in proc.stderr
    assert "annotated starting tree" in proc.stderr
