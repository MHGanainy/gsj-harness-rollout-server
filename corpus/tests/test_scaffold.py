"""Scaffold: determinism (two runs, identical SHAs), idempotent re-push,
the ADR-0006 repo shape, and the lock — all against the local file:// rail."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ingest_corpus as ic


def scaffold(root: Path, estate: str) -> int:
    return ic.main(["scaffold", "--corpus", str(root), "--base-url", estate])


def heads(estate: str, owner: str, case_id: str) -> dict[str, str]:
    return ic.ls_remote_heads(estate, owner, case_id)


def read_lock(root: Path) -> dict:
    return json.loads((root / "corpus.lock.json").read_text(encoding="utf-8"))


def test_two_runs_identical_shas(corpus_root, estate, tmp_path):
    assert scaffold(corpus_root, estate) == 0
    first = {case: heads(estate, "gsj-staging", case)
             for case in ("case_a", "case_b")}
    first_lock = (corpus_root / "corpus.lock.json").read_bytes()

    estate2 = f"file://{tmp_path / 'estate2'}"
    (tmp_path / "estate2").mkdir()
    assert scaffold(corpus_root, estate2) == 0
    second = {case: heads(estate2, "gsj-staging", case)
              for case in ("case_a", "case_b")}

    assert first == second, "same tree must scaffold to identical SHAs"
    assert (corpus_root / "corpus.lock.json").read_bytes() == first_lock, \
        "the lock is deterministic (no timestamps by design)"


def test_repush_is_idempotent_and_converges(corpus_root, estate):
    assert scaffold(corpus_root, estate) == 0
    before = heads(estate, "gsj-staging", "case_a")

    # Move a remote branch away (an agent-like stray push) …
    bare = estate[len("file://"):] + "/gsj-staging/case_a.git"
    subprocess.run(["git", "--git-dir", bare, "update-ref",
                    "refs/heads/stray", before["main"]], check=True)
    # … re-run: refs converge back to exactly the built set (--prune).
    assert scaffold(corpus_root, estate) == 0
    after = heads(estate, "gsj-staging", "case_a")
    assert after == before
    assert "stray" not in after


def test_repo_shape_adr_0006(corpus_root, estate, tmp_path):
    assert scaffold(corpus_root, estate) == 0
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", f"{estate}/gsj-staging/case_b.git",
                    str(clone)], check=True, capture_output=True)

    def files(ref: str) -> set[str]:
        out = subprocess.run(
            ["git", "-C", str(clone), "ls-tree", "-r", "--name-only", ref],
            check=True, capture_output=True, text=True).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}

    main = files("origin/main")
    # main = the LARGEST timestep's pages (case_b has timesteps 2, 3)
    assert {"md/page_0001.md", "md/page_0002.md", "md/page_0003.md"} <= main
    assert {"AGENTS.md", ".gitignore", "out/.gitkeep",
            "skills/summarize/SKILL.md"} <= main
    t2 = files("origin/timestep-2")
    assert "md/page_0003.md" not in t2 and "md/page_0002.md" in t2
    assert {"AGENTS.md", ".gitignore", "out/.gitkeep",
            "skills/summarize/SKILL.md"} <= t2
    gitignore = subprocess.run(
        ["git", "-C", str(clone), "show", "origin/main:.gitignore"],
        check=True, capture_output=True, text=True).stdout
    assert gitignore == ic.CASE_GITIGNORE


def test_lock_records_refs_census_and_prompt_ids(corpus_root, estate):
    assert scaffold(corpus_root, estate) == 0
    lock = read_lock(corpus_root)
    assert lock["corpus"]["owner"] == "gsj-staging"
    # ADR-0015: the split rides the lock per case; the manifest key is gone
    assert "eval_case_ids" not in lock["corpus"]
    assert lock["cases"]["case_a"]["split"] == "train"
    assert lock["cases"]["case_b"]["split"] == "eval"
    case_a = lock["cases"]["case_a"]
    assert set(case_a["refs"]) == {"main", "timestep-1", "timestep-2"}
    assert case_a["timesteps"]["1"] == {"pages": 1,
                                        "prompt_ids": ["skill:summarize"]}
    assert case_a["timesteps"]["2"]["prompt_ids"] == ["skill:summarize",
                                                      "free:parties"]
    # canonical clone URL from corpus.yaml, not the --base-url override
    assert case_a["clone_url"] == \
        "http://forgejo.invalid:3000/gsj-staging/case_a.git"


def test_dry_run_pushes_and_writes_nothing(corpus_root, estate):
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate, "--dry-run"]) == 0
    assert not (corpus_root / "corpus.lock.json").exists()
    estate_dir = Path(estate[len("file://"):])
    assert not any(estate_dir.iterdir())


def test_missing_token_env_is_a_usage_error(corpus_root, capsys, monkeypatch):
    monkeypatch.delenv("GSJ_FORGEJO_TOKEN_GSJ_STAGING", raising=False)
    rc = ic.main(["scaffold", "--corpus", str(corpus_root),
                  "--base-url", "http://forgejo.invalid:3000"])
    assert rc == 2
    assert "GSJ_FORGEJO_TOKEN_GSJ_STAGING" in capsys.readouterr().err


def test_owner_override_changes_owner_and_token_env(corpus_root, estate,
                                                    capsys, monkeypatch):
    monkeypatch.delenv("GSJ_FORGEJO_TOKEN_GSJ_PROD", raising=False)
    rc = ic.main(["scaffold", "--corpus", str(corpus_root),
                  "--base-url", "http://forgejo.invalid:3000",
                  "--owner-override", "gsj-prod"])
    assert rc == 2
    assert "GSJ_FORGEJO_TOKEN_GSJ_PROD" in capsys.readouterr().err
    # on the file:// rail (no token needed) the override lands in the estate
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate,
                    "--owner-override", "gsj-prod"]) == 0
    assert heads(estate, "gsj-prod", "case_a")
