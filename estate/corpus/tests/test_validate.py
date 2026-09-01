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
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        "", encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 0
    assert "0 prompts" in out


def test_absent_prompts_yaml_is_legal(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").unlink()
    rc, _ = run_validate(corpus_root, capsys)
    assert rc == 0


def test_missing_page(corpus_root, capsys):
    (corpus_root / "eval/cases/case_b/timestep-3/pages/page_0002.md").unlink()
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "missing pages [2]" in out


def test_gap_in_numbering(corpus_root, capsys):
    pages = corpus_root / "eval/cases/case_b/timestep-3/pages"
    (pages / "page_0003.md").rename(pages / "page_0004.md")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "missing pages [3]" in out
    assert "beyond the cutoff [4]" in out


def test_relative_numbering(corpus_root, capsys):
    """The classic mistake: a timestep-3 directory holding ONE file named
    page_0001.md (its pages numbered per-directory, not absolutely)."""
    pages = corpus_root / "eval/cases/case_b/timestep-3/pages"
    (pages / "page_0002.md").unlink()
    (pages / "page_0003.md").unlink()
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "must be exactly 1..3 (absolute numbering)" in out


def test_unpadded_page_name(corpus_root, capsys):
    pages = corpus_root / "train/cases/case_a/timestep-1/pages"
    (pages / "page_0001.md").rename(pages / "page_1.md")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "page_1.md" in out and "4-digit" in out


def test_prefix_divergence_names_case_page_and_hashes(corpus_root, capsys):
    divergent = corpus_root / "eval/cases/case_b/timestep-3/pages/page_0001.md"
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
        (corpus_root / "eval/cases/case_b/timestep-2/pages/page_0001.md")
        .read_bytes()).hexdigest()[:16]
    assert edited in out and original in out


def test_unresolvable_skill(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        'prompts:\n  - {id: "skill:missing", source: skill, name: missing}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "unresolvable skill 'missing'" in out


def test_duplicate_prompt_id(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        "prompts:\n"
        '  - {id: "skill:summarize", source: skill, name: summarize}\n'
        '  - {id: "skill:summarize", source: skill, name: summarize}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "duplicate prompt id 'skill:summarize'" in out


# --- CP-14 (ADR-0015): the split is the directory layout ------------------


def test_split_column_in_the_table(corpus_root, capsys):
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 0
    header = next(line for line in out.splitlines() if "result" in line)
    assert "split" in header
    rows = [line for line in out.splitlines() if "PASS" in line]
    assert any("case_a" in row and "train" in row for row in rows)
    assert any("case_b" in row and "eval" in row for row in rows)


def test_retired_eval_case_ids_is_rejected_naming_the_migration(
        corpus_root, capsys):
    """A v1 manifest key must FAIL with the migration named — silently
    ignoring it ships a corpus whose split means nothing (ADR-0015)."""
    with open(corpus_root / "corpus.yaml", "a", encoding="utf-8") as handle:
        handle.write("eval_case_ids: [case_b]\n")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "'eval_case_ids' is retired (ADR-0015)" in out
    assert "eval/cases/" in out and "delete this key" in out


def test_root_cases_dir_is_rejected_as_the_pre_split_shape(tmp_path, capsys):
    """A whole v1 tree (cases/ at the root) fails with its own migration
    message, not a generic stray-entry error."""
    root = make_corpus(tmp_path / "corpus")
    (root / "train" / "cases").rename(root / "cases")
    (root / "train").rmdir()
    import shutil
    shutil.rmtree(root / "eval")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "retired pre-split shape (ADR-0015)" in out
    assert "train/cases/ or eval/cases/" in out


def test_case_under_both_splits_is_a_hard_failure(corpus_root, capsys):
    import shutil
    shutil.copytree(corpus_root / "train" / "cases" / "case_a",
                    corpus_root / "eval" / "cases" / "case_a")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert ("present under both train/cases/ and eval/cases/" in out
            and "exactly one split" in out)


def test_third_split_dir_fails_loudly(corpus_root, capsys):
    """ADR-0015: two splits, no third — a `test/` tree must never be
    silently skipped; it needs an ADR, and the message says so."""
    pages = corpus_root / "test" / "cases" / "case_c" / "timestep-1" / "pages"
    pages.mkdir(parents=True)
    (pages / "page_0001.md").write_text("## Page 1\n", encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "unexpected entry 'test'" in out and "ADR (ADR-0015)" in out


def test_a_file_squatting_a_split_name_fails(corpus_root, capsys):
    """A regular file named `train` must not silently vanish the split —
    the root walk type-checks reserved names (CP-14 adversarial pass)."""
    import shutil
    shutil.rmtree(corpus_root / "train")
    (corpus_root / "train").write_text("not a split\n", encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "'train' at the corpus root must be a directory" in out


def test_only_on_a_pre_split_tree_still_prints_the_migration(tmp_path,
                                                             capsys):
    """--only must not turn the migration diagnostics into exit 2: with
    tree-level findings pending, the table prints (CP-14 adversarial
    pass — the unknown-cases usage error is for sound trees only)."""
    import shutil
    root = make_corpus(tmp_path / "corpus")
    (root / "train" / "cases").rename(root / "cases")
    (root / "train").rmdir()
    shutil.rmtree(root / "eval")
    rc = ic.main(["validate", "--corpus", str(root), "--only", "case_a"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "retired pre-split shape (ADR-0015)" in out


def test_v1_tree_shows_both_migration_messages_in_one_run(tmp_path, capsys):
    """The retired-key and pre-split-shape rejections must arrive
    together — the root walk is independent of corpus.yaml parsing."""
    import shutil
    root = make_corpus(tmp_path / "corpus")
    (root / "train" / "cases").rename(root / "cases")
    (root / "train").rmdir()
    shutil.rmtree(root / "eval")
    with open(root / "corpus.yaml", "a", encoding="utf-8") as handle:
        handle.write("eval_case_ids: [case_b]\n")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "'eval_case_ids' is retired (ADR-0015)" in out
    assert "retired pre-split shape (ADR-0015)" in out


def test_missing_split_dirs_fail(tmp_path, capsys):
    import shutil
    root = make_corpus(tmp_path / "corpus")
    shutil.rmtree(root / "train")
    shutil.rmtree(root / "eval")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "at least one of train/cases/ or eval/cases/" in out


def test_eval_only_corpus_is_legal(tmp_path, capsys):
    """One split may be absent: everything-evals (and, symmetrically,
    everything-trains) is a valid corpus."""
    import shutil
    root = make_corpus(tmp_path / "corpus")
    shutil.rmtree(root / "train")
    rc, out = run_validate(root, capsys)
    assert rc == 0
    assert "case_b" in out


def test_non_utf8_page(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/pages/page_0001.md").write_bytes(
        b"\xff\xfe not utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "not valid UTF-8" in out


def test_misnamed_timestep_dir_fails_loudly(corpus_root, capsys):
    ts = corpus_root / "train/cases/case_a/timestep-2"
    ts.rename(corpus_root / "train/cases/case_a/timestep_2")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "timestep_2" in out and "unexpected entry" in out


def test_leading_zero_timestep_dir(corpus_root, capsys):
    ts = corpus_root / "train/cases/case_a/timestep-2"
    ts.rename(corpus_root / "train/cases/case_a/timestep-02")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "timestep-02" in out


# --- CP-71: the owner allowlist became a shape check ----------------------


def test_owner_is_a_shape_not_a_membership(tmp_path, capsys):
    """'gsj-elsewhere' — the very name the old two-value allowlist
    refused — is a usable Forgejo username and now validates."""
    root = make_corpus(tmp_path / "corpus", owner="gsj-elsewhere")
    rc, _ = run_validate(root, capsys)
    assert rc == 0


def test_bad_owner_refusal_names_the_rule(tmp_path, capsys):
    """Each refusal states the clause of Forgejo's own username rule the
    value breaks (v16: modules/validation/helpers.go + the reserved list),
    not just the fact of failure."""
    cases = [
        ("-leading", "start with a letter or digit"),
        ("dotted.owner", "mapping only '-' to '_'"),   # the env-var reason
        ("double--dash", "consecutive or trailing"),
        ("trailing-", "consecutive or trailing"),
        ("admin", "reserves 'admin'"),
        ("Ghost", "reserves 'ghost'"),                 # case-insensitive
        ("x" * 41, "caps usernames at 40"),
    ]
    for i, (owner, clause) in enumerate(cases):
        root = make_corpus(tmp_path / f"corpus-{i}", owner=owner)
        rc, out = run_validate(root, capsys)
        assert rc == 1, owner
        assert f"owner {owner!r} is not a usable Forgejo username" in out
        assert clause in out, (owner, out)


def test_owner_with_trailing_newline_is_refused(tmp_path, capsys):
    """The CP-71 review's find: a YAML block scalar (`owner: |` + name)
    yields 'my-owner\\n', which a '$'-anchored regex accepts — and which
    would mint an unexportable env-var name and a Forgejo 422. \\Z holds
    the line."""
    root = make_corpus(tmp_path / "corpus")
    text = (root / "corpus.yaml").read_text(encoding="utf-8")
    (root / "corpus.yaml").write_text(
        text.replace("owner: gsj-staging", "owner: |\n  my-owner"),
        encoding="utf-8")
    rc, out = run_validate(root, capsys)
    assert rc == 1
    assert "is not a usable Forgejo username" in out


def test_explicit_skill_id_mismatch_still_refused(corpus_root, capsys):
    """An explicit id on a skill entry must be exactly skill:<name> —
    optional never became alias-able."""
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        'prompts:\n  - {id: "skill:wrong", source: skill, name: summarize}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "id must be 'skill:summarize', got 'skill:wrong'" in out


def test_owner_override_is_shape_checked_too(corpus_root, capsys):
    """--owner-override used to bypass the allowlist entirely; the shape
    check covers it, so a malformed owner fails at validate instead of as
    a Forgejo 422 mid-scaffold."""
    rc = ic.main(["validate", "--corpus", str(corpus_root),
                  "--owner-override", "bad-"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "owner 'bad-' is not a usable Forgejo username" in out


# --- CP-71: the three estate fields are deprecated, honored, warned -------


def test_deprecated_estate_fields_warn_and_pass(tmp_path, capsys):
    root = make_corpus(tmp_path / "corpus", mcp="http://mcp.invalid:8790")
    rc, out = run_validate(root, capsys)
    assert rc == 0
    assert "WARNING: corpus.yaml: DEPRECATED 'forgejo.base_url'" in out
    assert "WARNING: corpus.yaml: DEPRECATED 'mcp.url_base'" in out
    # the URL fields are honored; the image is IGNORED (a corpus is not
    # bound to a runtime) — each warning says which and names the source
    assert "Still honored as the canonical URL" in out
    assert "DEPRECATED 'sandbox_image' — IGNORED" in out
    assert "the estate's" in out


def test_deprecation_warnings_survive_quiet_phases(corpus_root, capsys):
    """The CP-71 review's find: the quiet re-validations are exactly the
    invocations that change data — a standalone `taskbank` on a corpus
    still pinning sandbox_image must not silently write default-image
    rows. The warnings print on EVERY phase."""
    rc = ic.main(["taskbank", "--corpus", str(corpus_root), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DEPRECATED 'sandbox_image' — IGNORED" in out


def test_estate_field_free_corpus_validates_without_warnings(tmp_path,
                                                             capsys):
    """The CP-71 shape — name, owner, git: and nothing else — is the
    documented form (what `estate.py scaffold` writes)."""
    root = make_corpus(tmp_path / "corpus", estate_fields=False)
    rc, out = run_validate(root, capsys)
    assert rc == 0
    assert "DEPRECATED" not in out


def test_scaffold_without_any_base_url_is_a_usage_error(tmp_path, capsys):
    """No forgejo.base_url and no --base-url: the refusal names the flag
    (and the tool that answers it), before anything runs."""
    root = make_corpus(tmp_path / "corpus", estate_fields=False)
    rc = ic.main(["scaffold", "--corpus", str(root)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no git host to talk to" in err
    assert "--base-url" in err and "estate.py up" in err


# --- CP-71: prompt ids are optional, generated when absent ----------------


def test_idless_prompts_are_legal(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        "prompts:\n"
        "  - {source: skill, name: summarize}\n"
        '  - {source: free, text: "Who signed the deed? Cite pages."}\n',
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 0
    assert "1 pages, 2 prompts" in out


def test_duplicate_generated_ids_say_they_were_generated(corpus_root,
                                                         capsys):
    """Two id-less entries with the same content collide at the generated
    id — the message says where the id came from, or the reader hunts for
    an `id:` key that is not in the file."""
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
        "prompts:\n"
        "  - {source: skill, name: summarize}\n"
        "  - {source: skill, name: summarize}\n",
        encoding="utf-8")
    rc, out = run_validate(corpus_root, capsys)
    assert rc == 1
    assert "duplicate prompt id 'skill:summarize'" in out
    assert "the id was generated from the entry" in out


def test_free_prompt_id_slug_mismatch(corpus_root, capsys):
    (corpus_root / "train/cases/case_a/timestep-1/prompts.yaml").write_text(
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
