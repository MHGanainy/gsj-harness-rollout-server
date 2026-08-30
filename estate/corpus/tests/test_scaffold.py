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


# -- CP-59: scaffold's post-push read-back credential (gap row 2's last
#    anonymous reader) ---------------------------------------------------

READ_VAR = "GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING"
HTTP_ESTATE = "http://forgejo.invalid:3000"


def _http_scaffold_with_refused_ls_remote(monkeypatch, seen: list[list[str]]):
    """An http estate whose push side is faked away (no Forgejo here) and
    whose `git ls-remote` is refused the way a sign-in-required Forgejo
    refuses under GIT_TERMINAL_PROMPT=0 — every other git call is real, so
    the repo build and the splice run for real."""
    real_run = ic.subprocess.run
    monkeypatch.setattr(ic, "resolve_push_auth", lambda corpus, base_url: "push-tok")
    monkeypatch.setattr(ic, "ensure_remote_repo", lambda *a, **k: None)
    monkeypatch.setattr(ic, "push_repo", lambda *a, **k: None)

    def fake_run(args, **kwargs):
        if list(args[:2]) == ["git", "ls-remote"]:
            seen.append(list(args))
            raise subprocess.CalledProcessError(
                128, args, output="",
                stderr=f"fatal: unable to access '{args[-1]}': could not read "
                       f"Username for '{HTTP_ESTATE}': terminal prompts disabled")
        return real_run(args, **kwargs)
    monkeypatch.setattr(ic.subprocess, "run", fake_run)


def test_scaffold_read_back_carries_the_read_token_and_refusal_is_a_named_error(
        corpus_root, monkeypatch, capsys):
    """Fails if phase_scaffold stops passing resolve_read_auth(...) to
    ls_remote_heads: the argv would carry no userinfo."""
    monkeypatch.setenv(READ_VAR, "s3cret-read-token")
    seen: list[list[str]] = []
    _http_scaffold_with_refused_ls_remote(monkeypatch, seen)
    rc = ic.main(["scaffold", "--corpus", str(corpus_root),
                  "--base-url", HTTP_ESTATE])
    assert rc == 2                                      # a PipelineError, not a traceback
    assert seen and "://gsj-staging:s3cret-read-token@forgejo.invalid:3000/" in seen[0][-1]
    out, err = capsys.readouterr()
    assert f"reading back with {READ_VAR}" in out       # says which credential
    assert "s3cret-read-token" not in out + err         # redacted everywhere
    assert ("case_a: post-push read-back `git ls-remote "
            f"{HTTP_ESTATE}/gsj-staging/case_a.git` failed") in err
    assert "'http://gsj-staging:***@forgejo.invalid:3000/" in err
    assert "needs GSJ_FORGEJO_READ_TOKEN" not in err    # no hint: a token WAS given
    assert not (corpus_root / "corpus.lock.json").exists()  # nothing recorded


def test_scaffold_anonymous_read_back_refusal_names_the_variable(
        corpus_root, monkeypatch, capsys):
    monkeypatch.delenv(READ_VAR, raising=False)
    seen: list[list[str]] = []
    _http_scaffold_with_refused_ls_remote(monkeypatch, seen)
    rc = ic.main(["scaffold", "--corpus", str(corpus_root),
                  "--base-url", HTTP_ESTATE])
    assert rc == 2
    assert seen and "@" not in seen[0][-1]              # anonymous, as configured
    out, err = capsys.readouterr()
    assert "reading back anonymously" in out
    assert "terminal prompts disabled" in err
    assert f"needs {READ_VAR} exported" in err          # the cure, named
    assert "the push itself succeeded" in err


def test_scaffold_read_back_with_the_token_converges_and_writes_the_lock(
        corpus_root, monkeypatch, capsys):
    """The success path: the credentialed read-back returns the built heads,
    the case converges, the lock is written and names the credential used."""
    monkeypatch.setenv(READ_VAR, "s3cret-read-token")
    built: dict[str, dict[str, str]] = {}
    real_build = ic.build_case_repo

    def build_and_remember(corpus, case, dest, env):
        heads = real_build(corpus, case, dest, env)
        built[case.case_id] = heads
        return heads
    monkeypatch.setattr(ic, "build_case_repo", build_and_remember)
    monkeypatch.setattr(ic, "resolve_push_auth", lambda corpus, base_url: "push-tok")
    monkeypatch.setattr(ic, "ensure_remote_repo", lambda *a, **k: None)
    monkeypatch.setattr(ic, "push_repo", lambda *a, **k: None)
    real_run = ic.subprocess.run
    seen: list[list[str]] = []

    def fake_run(args, **kwargs):
        if list(args[:2]) == ["git", "ls-remote"]:          # the remote answers with
            seen.append(list(args))                          # exactly what was built
            case_id = args[-1].rsplit("/", 1)[-1][:-len(".git")]
            out = "".join(f"{sha}\trefs/heads/{branch}\n"
                          for branch, sha in built[case_id].items())
            return subprocess.CompletedProcess(args, 0, out, "")
        return real_run(args, **kwargs)
    monkeypatch.setattr(ic.subprocess, "run", fake_run)
    rc = ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", HTTP_ESTATE])
    assert rc == 0
    assert len(seen) == 2 and all(
        "://gsj-staging:s3cret-read-token@forgejo.invalid:3000/" in a[-1] for a in seen)
    out = capsys.readouterr().out
    assert f"reading back with {READ_VAR}" in out
    assert out.count("[pushed, converged]") == 2
    assert "s3cret-read-token" not in out
    lock = read_lock(corpus_root)
    assert set(lock["cases"]) == {"case_a", "case_b"}
    assert lock["cases"]["case_a"]["refs"] == built["case_a"]
