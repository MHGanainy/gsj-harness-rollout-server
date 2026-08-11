"""Post-verification: green on an intact estate; catches injected reality
mismatches (a page mutated AFTER scaffold, ref drift, a doctored parquet) —
naming the specific delta. Pre-validation checks the input; THIS is the half
that checks reality."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import ingest_corpus as ic


def run_all_local(root: Path, estate: str) -> None:
    # scaffold only since CP-01: the taskbank phase is deferred (ADR-0003)
    assert ic.main(["scaffold", "--corpus", str(root),
                    "--base-url", estate]) == 0


def verify(root: Path, estate: str) -> int:
    return ic.main(["verify", "--corpus", str(root), "--base-url", estate,
                    "--skip-ingest"])


def test_intact_estate_passes(corpus_root, estate, capsys):
    run_all_local(corpus_root, estate)
    assert verify(corpus_root, estate) == 0
    out = capsys.readouterr().out
    assert "== verify: PASS" in out
    assert "SKIPPED (--skip-ingest)" in out
    assert "deferred to CP-07" in out  # the bank row reports the deferral


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


def _record_bank(root: Path, payload: bytes) -> None:
    """A lock entry for a hand-written bank file — the CP-01 stand-in for
    the deferred taskbank phase (ADR-0003): verify's surviving bank check
    is sha256-vs-lock, so a recorded bank is bytes + a lock row."""
    (root / "taskbank.parquet").write_bytes(payload)
    lock = ic.load_lock(root, required=True)
    lock["taskbank"] = {"path": "taskbank.parquet", "rows": 5, "train": 3,
                        "eval": 2,
                        "sha256": hashlib.sha256(payload).hexdigest()}
    ic.write_lock(root, lock)


def test_doctored_parquet_fails_sha(corpus_root, estate, capsys):
    """The surviving byte-level half of the bank check (the row-set half —
    'row count != lock', the missing triple named — is deferred to CP-07
    with the phase, ADR-0003)."""
    run_all_local(corpus_root, estate)
    _record_bank(corpus_root, b"the recorded bank bytes")
    assert verify(corpus_root, estate) == 0
    capsys.readouterr()

    (corpus_root / "taskbank.parquet").write_bytes(b"doctored bytes")
    assert verify(corpus_root, estate) == 1
    out = capsys.readouterr().out
    assert "sha256" in out and "!= lock" in out


def test_missing_taskbank_is_deferred_not_an_error(corpus_root, estate,
                                                   capsys):
    """Pre-CP-01 an absent bank failed verify; with the phase deferred
    (ADR-0003) a lock without a bank entry is a loud SKIP, not a FAIL —
    verify must stay green on a freshly scaffolded estate."""
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    assert verify(corpus_root, estate) == 0
    out = capsys.readouterr().out
    assert "deferred to CP-07" in out


def test_taskbank_phase_is_deferred(corpus_root, estate, capsys):
    """The ADR-0003 surface: an explicit `taskbank` run raises the deferral
    as a usage error naming the ADR."""
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    rc = ic.main(["taskbank", "--corpus", str(corpus_root)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "deferred to CP-07" in err and "ADR-0003" in err


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
    """`all` with --skip-ingest: validate → scaffold → (taskbank deferred,
    ADR-0003) → verify — the deferral must not abort the run."""
    rc = ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate,
                  "--skip-ingest"])
    assert rc == 0
    out = capsys.readouterr().out
    for marker in ("== validate: PASS", "== scaffold", "== ingest == SKIPPED",
                   "== taskbank == DEFERRED to CP-07", "== verify: PASS"):
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
    """`all --only` must not abort after pushing, and a recorded bank + its
    lock entry are left untouched (the ADR-0047(e) footgun stays closed —
    under the ADR-0003 deferral no path writes a bank at all)."""
    run_all_local(corpus_root, estate)
    _record_bank(corpus_root, b"the recorded bank bytes")
    bank_before = (corpus_root / "taskbank.parquet").read_bytes()
    lock_before = ic.load_lock(corpus_root)["taskbank"]
    capsys.readouterr()

    rc = ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate,
                  "--skip-ingest", "--only", "case_a"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "== taskbank == DEFERRED to CP-07" in out
    assert "== verify: PASS" in out
    assert (corpus_root / "taskbank.parquet").read_bytes() == bank_before
    assert ic.load_lock(corpus_root)["taskbank"] == lock_before
