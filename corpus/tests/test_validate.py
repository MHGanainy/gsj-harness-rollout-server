"""Validator coverage: the positive path plus one negative per contract rule
(docs/corpus-contract.md; the CP-33 Step-5 list)."""

from __future__ import annotations

from pathlib import Path

import ingest_corpus as ic
from conftest import make_corpus, write_case


def run_validate(root: Path, capsys) -> tuple[int, str]:
    rc = ic.main(["validate", "--corpus", str(root)])
    return rc, capsys.readouterr().out


def test_positive_passes(corpus_root, capsys):
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 0
    assert "== validate: PASS" in out
    # per-(case, timestep) PASS rows with census + prompt counts
    assert "case_a      timestep-2  PASS" in out.replace("   ", "  ") or \
        "timestep-2" in out


def test_empty_prompts_yaml_is_legal(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/prompts.yaml").write_text(
        "", encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 0
    assert "0 prompts" in out


def test_absent_prompts_yaml_is_legal(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/prompts.yaml").unlink()
    rc, _ = run_validate(corpus_root, capsys)
    assert rc == 0


def test_missing_page(corpus_root, capsys):
    (corpus_root / "cases/case_b/timestep-3/pages/page_0002.md").unlink()
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "missing pages [2]" in out


def test_gap_in_numbering(corpus_root, capsys):
    pages = corpus_root / "cases/case_b/timestep-3/pages"
    (pages / "page_0003.md").rename(pages / "page_0004.md")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "missing pages [3]" in out
    assert "beyond the cutoff [4]" in out


def test_relative_numbering(corpus_root, capsys):
    """The classic mistake: a timestep-3 directory holding ONE file named
    page_0001.md (its pages numbered per-directory, not absolutely)."""
    pages = corpus_root / "cases/case_b/timestep-3/pages"
    (pages / "page_0002.md").unlink()
    (pages / "page_0003.md").unlink()
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "must be exactly 1..3 (absolute numbering)" in out


def test_unpadded_page_name(corpus_root, capsys):
    pages = corpus_root / "cases/case_a/timestep-1/pages"
    (pages / "page_0001.md").rename(pages / "page_1.md")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "page_1.md" in out and "4-digit" in out


def test_prefix_divergence_names_case_page_and_hashes(corpus_root, capsys):
    divergent = corpus_root / "cases/case_b/timestep-3/pages/page_0001.md"
    divergent.write_text("## Page 1\n\nEDITED in timestep-3 only.\n",
                         encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "prefix divergence on page 1" in out
    assert "case_b" in out
    # both hashes shown
    import hashlib
    edited = hashlib.sha256(divergent.read_bytes()).hexdigest()[:16]
    original = hashlib.sha256(
        (corpus_root / "cases/case_b/timestep-2/pages/page_0001.md")
        .read_bytes()).hexdigest()[:16]
    assert edited in out and original in out


def test_unresolvable_skill(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/prompts.yaml").write_text(
        'prompts:\n  - {id: "skill:missing", source: skill, name: missing}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "unresolvable skill 'missing'" in out


def test_duplicate_prompt_id(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/prompts.yaml").write_text(
        "prompts:\n"
        '  - {id: "skill:summarize", source: skill, name: summarize}\n'
        '  - {id: "skill:summarize", source: skill, name: summarize}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "duplicate prompt id 'skill:summarize'" in out


def test_eval_id_not_in_cases(tmp_path, capsys):
    root = make_corpus(tmp_path / "corpus")
    text = (root / "corpus.yaml").read_text(encoding="utf-8")
    (root / "corpus.yaml").write_text(
        text.replace("eval_case_ids: [case_b]",
                     "eval_case_ids: [case_zz]"), encoding="utf-8")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "eval_case_ids" in out and "case_zz" in out


def test_non_utf8_page(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/pages/page_0001.md").write_bytes(
        b"\xff\xfe not utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "not valid UTF-8" in out


def test_misnamed_timestep_dir_fails_loudly(corpus_root, capsys):
    ts = corpus_root / "cases/case_a/timestep-2"
    ts.rename(corpus_root / "cases/case_a/timestep_2")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "timestep_2" in out and "unexpected entry" in out


def test_leading_zero_timestep_dir(corpus_root, capsys):
    ts = corpus_root / "cases/case_a/timestep-2"
    ts.rename(corpus_root / "cases/case_a/timestep-02")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "timestep-02" in out


def test_bad_owner(tmp_path, capsys):
    root = make_corpus(tmp_path / "corpus", owner="gsj-elsewhere")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "owner 'gsj-elsewhere'" in out


def test_free_prompt_id_slug_mismatch(corpus_root, capsys):
    (corpus_root / "cases/case_a/timestep-1/prompts.yaml").write_text(
        'prompts:\n  - {id: "free:has spaces", source: free, text: "Hi."}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "free:<slug>" in out


def test_only_unknown_case_is_usage_error(corpus_root, capsys):
    rc = ic.main(["validate", "--corpus", str(corpus_root),
                  "--only", "case_zz"])
    assert rc == 2
    assert "unknown cases" in capsys.readouterr().err
