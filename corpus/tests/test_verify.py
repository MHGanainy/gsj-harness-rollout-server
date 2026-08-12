"""Post-verification: green on an intact estate; catches injected reality
mismatches (a page mutated AFTER scaffold, ref drift, a doctored parquet —
by sha AND, since CP-24, by rows against the tree) — naming the specific
delta. Pre-validation checks the input; THIS is the half that checks
reality."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import ingest_corpus as ic


def run_all_local(root: Path, estate: str) -> None:
    # the full local pipeline: since CP-24 the bank is part of what a
    # complete run leaves behind (ADR-0022), so verify expects one
    assert ic.main(["scaffold", "--corpus", str(root),
                    "--base-url", estate]) == 0
    assert ic.main(["taskbank", "--corpus", str(root)]) == 0


def verify(root: Path, estate: str) -> int:
    return ic.main(["verify", "--corpus", str(root), "--base-url", estate,
                    "--skip-ingest"])


def test_intact_estate_passes(corpus_root, estate, capsys):
    run_all_local(corpus_root, estate)
    assert verify(corpus_root, estate) == 0
    out = capsys.readouterr().out
    assert "== verify: PASS" in out
    assert "SKIPPED (--skip-ingest)" in out
    assert "sha matches the lock" in out          # the byte half
    assert "triples set-equal the tree" in out    # the row half (CP-24)


def test_mutated_page_after_scaffold_fails_naming_it(corpus_root, estate,
                                                     tmp_path, capsys):
    run_all_local(corpus_root, estate)

    # Mutate page 2 of case_b's timestep-3 branch IN THE REMOTE (the estate),
    # leaving the source tree and the lock untouched — a reality drift.
    work = tmp_path / "mutate"
    url = f"{estate}/gsj-staging/case_b.git"
    subprocess.run(["git", "clone", "-q", "-b", "timestep-3", url, str(work)],
                   check=True, capture_output=True)
    (work / "md" / "page_0002.md").write_text("## Page 2\n\nTAMPERED.\n",
                                              encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "intruder", "GIT_AUTHOR_EMAIL": "x@x",
           "GIT_COMMITTER_NAME": "intruder", "GIT_COMMITTER_EMAIL": "x@x",
           "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["git", "-C", str(work), "commit", "-aqm", "tamper"],
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin",
                    "timestep-3"], check=True, capture_output=True, env=env)

    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "case_b" in out
    # the ref no longer matches the lock, and the page bytes differ
    assert "live refs != lock" in out
    assert ("page 2 bytes differ from the source" in out
            or "prefix divergence AS CLONED" in out)


def test_doctored_parquet_fails_sha(corpus_root, estate, capsys):
    """The byte half of the bank check: bytes that differ from the
    recorded sha256 are named — and garbage bytes additionally fail the
    row half as unreadable (CP-24)."""
    run_all_local(corpus_root, estate)
    assert verify(corpus_root, estate) == 0
    capsys.readouterr()

    (corpus_root / "taskbank.parquet").write_bytes(b"doctored bytes")
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "sha256" in out and "!= lock" in out
    assert "not readable as parquet" in out


def test_verify_rows_catch_a_missing_triple(corpus_root, estate, capsys):
    """CP-24: the row-level half, on the CP-14 injected-mismatch pattern.
    The doctored bank drops one triple and RE-RECORDS itself in the lock
    (sha and counts consistent with the doctored bytes), so the sha and
    count clauses all pass — only set-equality with the TREE can catch
    it, and it must, naming the triple."""
    run_all_local(corpus_root, estate)
    bank_path = corpus_root / "taskbank.parquet"
    rows = [r for r in ic.read_taskbank_rows(bank_path)
            if not (r["case_id"] == "case_b" and r["timestep"] == 3)]
    pa = ic._pyarrow()
    pa.parquet.write_table(
        pa.Table.from_pylist(rows, schema=ic._taskbank_schema(pa)), bank_path)
    lock = ic.load_lock(corpus_root, required=True)
    lock["taskbank"] = {"path": "taskbank.parquet", "rows": 4, "train": 3,
                        "eval": 1,
                        "sha256": hashlib.sha256(
                            bank_path.read_bytes()).hexdigest()}
    ic.write_lock(corpus_root, lock)

    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "sha matches the lock" in out  # the byte half is blind to this
    assert "missing from the bank" in out
    assert "('case_b', 3, 'skill:summarize')" in out


def _rewrite_bank(root: Path, rows: list[dict], schema=None) -> None:
    """Rewrite the bank from doctored rows and RE-RECORD the lock so the
    sha and count clauses pass — only the tree-derived clauses can catch
    the doctoring."""
    bank_path = root / "taskbank.parquet"
    pa = ic._pyarrow()
    pa.parquet.write_table(
        pa.Table.from_pylist(rows, schema=schema or ic._taskbank_schema(pa)),
        bank_path)
    lock = ic.load_lock(root, required=True)
    train = sum(1 for r in rows if r.get("split") == "train")
    lock["taskbank"] = {"path": "taskbank.parquet", "rows": len(rows),
                        "train": train, "eval": len(rows) - train,
                        "sha256": hashlib.sha256(
                            bank_path.read_bytes()).hexdigest()}
    ic.write_lock(root, lock)


def test_verify_rows_catch_a_tampered_text_column(corpus_root, estate,
                                                  capsys):
    """CP-24's adversarial pass: the per-row text comparison must bite. A
    bank whose skill_card_text was tampered — triples, counts and sha all
    consistent — fails on exactly the column, named."""
    run_all_local(corpus_root, estate)
    rows = ic.read_taskbank_rows(corpus_root / "taskbank.parquet")
    for row in rows:
        if row["prompt_id"] == "skill:summarize":
            row["skill_card_text"] = "# a card the tree never held\n"
    _rewrite_bank(corpus_root, rows)
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "skill_card_text != the tree's bytes" in out


def test_verify_refuses_a_bank_with_wrong_column_types(corpus_root, estate,
                                                       capsys):
    """A float64 timestep column reads back as 1.0 == 1 in every
    comparison, so a name-only column check would verify it clean while
    handing consumers the wrong types — the reader must refuse the whole
    schema (CP-24's adversarial pass)."""
    run_all_local(corpus_root, estate)
    pa = ic._pyarrow()
    schema = pa.schema([
        (name, pa.float64() if name == "timestep" else pa.string())
        for name in ic.TASKBANK_COLUMNS])
    rows = ic.read_taskbank_rows(corpus_root / "taskbank.parquet")
    for row in rows:
        row["timestep"] = float(row["timestep"])
    _rewrite_bank(corpus_root, rows, schema=schema)
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "schema != the ADR-0022 row shape" in out


def test_verify_reports_a_null_triple_value_as_a_finding(corpus_root,
                                                         estate, capsys):
    """A null case_id is legal parquet (nullable string) — the row half
    must FAIL on it with the findings table intact, never die in a raw
    TypeError sort (CP-24's adversarial pass)."""
    run_all_local(corpus_root, estate)
    rows = ic.read_taskbank_rows(corpus_root / "taskbank.parquet")
    rows[0]["case_id"] = None
    _rewrite_bank(corpus_root, rows)
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "== verify: FAIL" in out          # the table printed
    assert "not in the tree" in out          # the null triple is extra…
    assert "missing from the bank" in out    # …and the real one missing


def test_corrupt_lock_is_a_usage_error_not_a_traceback(corpus_root, estate,
                                                       capsys):
    """A truncated or merge-conflicted lock is a realistic state and
    verify is the tool one reaches for — it must answer with a
    PipelineError naming the file, not a JSONDecodeError traceback."""
    run_all_local(corpus_root, estate)
    (corpus_root / "corpus.lock.json").write_text("{broken", encoding="utf-8")
    assert verify(corpus_root, estate) == 2
    err = capsys.readouterr().err
    assert "unreadable as JSON" in err and "corpus.lock.json" in err


def test_scaffold_without_taskbank_fails_verify_naming_the_phase(
        corpus_root, estate, capsys):
    """CP-01's loud SKIP for a bankless lock retired with the deferral
    (ADR-0022): the bank is part of what a complete run leaves behind, so
    a freshly scaffolded estate with no bank is a FAIL naming the phase —
    the pre-CP-01 posture restored."""
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "no bank recorded in the lock" in out
    assert "taskbank phase" in out


def test_split_move_without_rescaffold_fails_verify(corpus_root, estate,
                                                    capsys):
    """ADR-0015: the split checks back from the lock. Moving a case between
    splits leaves the repo content identical (split-agnostic, ADR-0006) —
    only the lock clause can catch the move, and it must."""
    import shutil
    run_all_local(corpus_root, estate)
    assert verify(corpus_root, estate) == 0
    capsys.readouterr()

    shutil.move(str(corpus_root / "eval" / "cases" / "case_b"),
                str(corpus_root / "train" / "cases" / "case_b"))
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "split as sourced 'train' != lock 'eval'" in out
    assert "re-scaffolded" in out
    # the refs still match — the mismatch is the split, nothing else
    assert "live refs != lock" not in out


def test_verify_without_lock_is_usage_error(corpus_root, estate, capsys):
    rc = verify(corpus_root, estate)
    assert rc == 2
    assert "run the scaffold phase first" in capsys.readouterr().err


def test_all_on_file_rail(corpus_root, estate, capsys):
    """`all` with --skip-ingest: validate → scaffold → taskbank (built,
    CP-24) → verify — one run leaves a verified estate AND a verified
    bank."""
    rc = ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate,
                  "--skip-ingest"])
    assert rc == 0
    out = capsys.readouterr().out
    for marker in ("== validate: PASS", "== scaffold", "== ingest == SKIPPED",
                   "== taskbank == 5 rows (train 3 / eval 2)",
                   "== verify: PASS"):
        assert marker in out


def test_all_without_mcp_url_skips_ingest_not_errors(corpus_root, estate,
                                                     capsys):
    """corpus.yaml's mcp block is optional: omitting it SKIPS the reindex
    (the contract's "omit to skip"), it does not abort the run."""
    assert "mcp:" not in (corpus_root / "corpus.yaml").read_text()
    rc = ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate])
    assert rc == 0
    out = capsys.readouterr().out
    assert "== ingest == SKIPPED (no mcp.url_base configured" in out
    assert "== verify: PASS" in out
    assert "SKIPPED (no mcp.url_base configured)" in out  # verify's census row


def test_all_with_only_completes_and_leaves_the_bank_alone(corpus_root,
                                                           estate, capsys):
    """`all --only` must not abort after pushing, and the built bank + its
    lock entry are left byte-untouched (ADR-0047(e): a partial bank must
    never exist — under --only the phase is a loud skip, never a
    per-case rebuild)."""
    run_all_local(corpus_root, estate)
    bank_before = (corpus_root / "taskbank.parquet").read_bytes()
    lock_before = ic.load_lock(corpus_root)["taskbank"]
    capsys.readouterr()

    rc = ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate,
                  "--skip-ingest", "--only", "case_a"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "== taskbank == SKIPPED (--only" in out
    assert "== verify: PASS" in out
    assert (corpus_root / "taskbank.parquet").read_bytes() == bank_before
    assert ic.load_lock(corpus_root)["taskbank"] == lock_before
