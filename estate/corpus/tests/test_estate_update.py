"""estate.py's CP-73 surface: the `update` verb's diff/plan semantics and
the retrieval-config review machinery (CP-70 items 7/9/10).

Two rails, the suite's own split: the pure halves (update_plan,
same_git_identity, the --mcp-config merge and review) import the tool as a
module; the verb-level halves run it as a consumer does (a subprocess) on
the hermetic paths that never dial an estate — the unchanged corpus, the
--dry-run report, and the refusals that fire before any network. The live
halves (drift, identity, attribution, the acted update) are the CP-73
report's estate proof, not unit-testable without a Forgejo."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from conftest import make_corpus, page_text, write_case, PROMPT_SKILL

CORPUS_DIR = Path(__file__).resolve().parent.parent
ESTATE_DIR = CORPUS_DIR.parent
sys.path.insert(0, str(ESTATE_DIR))

import estate as est  # noqa: E402  — the tool, as a module (pure halves only)
import ingest_corpus as ic  # noqa: E402

ESTATE_PY = ESTATE_DIR / "estate.py"
OWNER = "gsj-staging"


def run_estate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ESTATE_PY), *args],
                          capture_output=True, text=True)


def scaffolded(tmp_path: Path) -> tuple[Path, dict]:
    """A corpus scaffolded and banked on the file:// rail; (root, lock)."""
    root = make_corpus(tmp_path / "corpus", estate_fields=False)
    bare = tmp_path / "bare"
    bare.mkdir()
    assert ic.main(["scaffold", "--corpus", str(root),
                    "--base-url", f"file://{bare}"]) == 0
    assert ic.main(["taskbank", "--corpus", str(root)]) == 0
    return root, json.loads((root / ic.LOCK_NAME).read_text())


def make_run(tmp_path: Path, root: Path, name: str = "r1") -> Path:
    """A run directory shaped like `up` leaves it — record, .env, and the
    run's lock copy — pointing at an estate nothing in these tests dials
    (the hermetic paths return before any network)."""
    runs = tmp_path / "runs"
    rd = runs / name
    rd.mkdir(parents=True)
    shutil.copyfile(root / ic.LOCK_NAME, rd / ic.LOCK_NAME)
    if (root / ic.TASKBANK_NAME).is_file():
        shutil.copyfile(root / ic.TASKBANK_NAME, rd / ic.TASKBANK_NAME)
    (rd / "run.json").write_text(json.dumps({
        "schema": 1, "run": name,
        "corpus": {"path": str(root), "owner": OWNER},
        "forgejo": {"mode": "created", "url": "http://127.0.0.1:9",
                    "owner": OWNER,
                    "push_token_env": ic.token_env_name(OWNER),
                    "read_token_env": ic.read_token_env_name(OWNER)},
        "mcp": {"mode": "created", "url": "http://127.0.0.1:9"},
    }, indent=2))
    (rd / ".env").write_text(
        f"{ic.token_env_name(OWNER)}='push-token'\n"
        f"{ic.read_token_env_name(OWNER)}='read-token'\n")
    return runs


def plan_for(root: Path, lock: dict, built=None) -> dict:
    corpus = ic.phase_validate(root, quiet=True)
    assert corpus is not None
    cases = lock.get("cases", {})
    if built is None:
        built = {cid: dict(cases[cid]["refs"]) for cid in cases
                 if cid in corpus.cases}
        for cid in corpus.cases:
            built.setdefault(cid, {"main": "0" * 40})
    return est.update_plan(corpus, cases, built)


# ---------------------------------------------------------- update_plan

def test_plan_unchanged_corpus_is_all_unchanged(tmp_path):
    root, lock = scaffolded(tmp_path)
    plan = plan_for(root, lock)
    assert plan["unchanged"] == ["case_a", "case_b"]
    assert plan["push"] == {} and not plan["removed"] and not plan["new"]


def test_plan_content_move_names_the_branches_and_the_census(tmp_path):
    root, lock = scaffolded(tmp_path)
    built = {cid: dict(lock["cases"][cid]["refs"]) for cid in lock["cases"]}
    built["case_a"]["timestep-2"] = "f" * 40   # an edited page: same census
    built["case_a"]["main"] = "e" * 40
    plan = plan_for(root, lock, built)
    [reason] = [r for r in plan["push"]["case_a"] if "content moved" in r]
    assert "'main'" in reason and "'timestep-2'" in reason
    assert "page census unchanged" in reason
    assert plan["unchanged"] == ["case_b"]
    assert plan["bank_moves"] and plan["repos_move"]


def test_plan_new_branch_reads_as_a_new_timestep(tmp_path):
    root, lock = scaffolded(tmp_path)
    built = {cid: dict(lock["cases"][cid]["refs"]) for cid in lock["cases"]}
    built["case_a"]["timestep-3"] = "a" * 40
    built["case_a"]["main"] = "b" * 40
    plan = plan_for(root, lock, built)
    assert any("new branch(es) ['timestep-3']" in r
               for r in plan["push"]["case_a"])


def test_plan_new_case_and_removed_case(tmp_path):
    root, lock = scaffolded(tmp_path)
    write_case(root, "train", "case_c", [1])
    shutil.rmtree(root / "eval" / "cases" / "case_b")
    plan = plan_for(root, lock)
    assert plan["removed"] == ["case_b"]
    assert plan["new"] == ["case_c"]
    assert "NEW" in plan["push"]["case_c"][0]


def test_plan_prompt_only_change_says_the_repo_is_unchanged(tmp_path):
    root, lock = scaffolded(tmp_path)
    (root / "train" / "cases" / "case_a" / "timestep-2" /
     "prompts.yaml").write_text("prompts:\n" + PROMPT_SKILL, encoding="utf-8")
    plan = plan_for(root, lock)     # refs identical: prompts never enter SHAs
    [reason] = plan["push"]["case_a"]
    assert "prompts at timestep-2" in reason
    assert "the repo itself is unchanged" in reason
    assert plan["bank_moves"] and not plan["repos_move"]


def test_plan_split_move_names_the_bank(tmp_path):
    root, lock = scaffolded(tmp_path)
    lock["cases"]["case_b"]["split"] = "train"   # the lock remembers train
    plan = plan_for(root, lock)
    [reason] = plan["push"]["case_b"]
    assert "split 'train' -> 'eval'" in reason and "bank" in reason


# ---------------------------------------------------- same_git_identity

TREE_IDENT = {"name": "gsj-fixtures", "email": "fixtures@gsj.invalid",
              "date": "2026-01-01T00:00:00 +0000"}


def test_identity_same_instant_same_offset_matches():
    live = {"name": "gsj-fixtures", "email": "fixtures@gsj.invalid",
            "date": "2026-01-01T00:00:00Z"}
    assert est.same_git_identity(TREE_IDENT, live) is True


def test_identity_changed_email_or_date_refuse_and_offset_counts():
    assert est.same_git_identity(
        TREE_IDENT, {**TREE_IDENT, "email": "other@gsj.invalid",
                     "date": "2026-01-01T00:00:00Z"}) is False
    assert est.same_git_identity(
        TREE_IDENT, {**TREE_IDENT, "date": "2026-01-02T00:00:00Z"}) is False
    # the same instant at another offset is a DIFFERENT author line (the
    # offset enters the SHA), so it is a different identity
    assert est.same_git_identity(
        TREE_IDENT, {**TREE_IDENT, "date": "2026-01-01T01:00:00+01:00"}) is False


def test_identity_unparseable_date_is_unknown_never_a_guess():
    assert est.same_git_identity(
        TREE_IDENT, {**TREE_IDENT, "date": "yesterday"}) is None


# ------------------------------------------------- the --mcp-config half

def test_mcp_overrides_refuse_the_estate_sections_by_name():
    problems = est.mcp_override_problems(
        {"embedding": {"model": "x"}, "source": {"owner": "evil"},
         "server": {"port": 1}, "typo": {}})
    assert any(p.startswith("source:") for p in problems)
    assert any(p.startswith("server:") for p in problems)
    assert any(p.startswith("typo:") for p in problems)
    assert est.mcp_override_problems({"search": {"default_k": 8}}) == []
    assert est.mcp_override_problems(["not", "a", "mapping"])
    # a typo'd per-section key is refused HERE, not as a container that
    # never comes ready (the service refuses unknown keys at its start)
    [p] = est.mcp_override_problems({"search": {"defualt_k": 8}})
    assert p.startswith("search.defualt_k:")
    # None = flag not given; {} = an explicitly empty file (clears the record)
    assert est.load_mcp_overrides(None) is None


def test_render_mcp_config_is_verbatim_without_overrides_and_merges_with():
    base = est.MCP_CONFIG.format(
        prog="estate/estate.py", run="r", forgejo_url="http://c:3000",
        owner=OWNER, repos="case_a", read_env="R", model="m", revision="v",
        chunk_max=220, chunk_overlap=40, rebuild="if-stale", secret_env="S")
    assert est.render_mcp_config(base, {}) == base
    merged = est.render_mcp_config(
        base, {"search": {"default_k": 8}, "embedding": {"batch_size": 64}})
    doc = yaml.safe_load(merged)
    assert doc["search"] == {"default_k": 8, "max_k": 20, "method": "chroma"}
    assert doc["embedding"]["batch_size"] == 64
    assert doc["embedding"]["model"] == "m"          # untouched keys survive
    assert doc["source"]["owner"] == OWNER           # estate sections intact
    assert merged.startswith("# GENERATED")          # the header survives


def test_config_review_prices_every_class_of_change():
    doc = {"embedding": {"model": "m", "revision": "v"},
           "chunking": {"max_tokens": 220, "overlap": 40},
           "search": {"default_k": 5, "max_k": 20},
           "decisions": {"seed": 1, "corpus_size": 30}}
    review = est.mcp_config_review(doc, Path("/run/mcp-config.yaml"))
    assert "REFUSED against the built store until --rebuild" in review
    assert "re-embed of the WHOLE corpus" in review
    assert "serving-only" in review and "restart" in review
    assert "speed only, not identity" in review


# ------------------------------------------------ the verb, hermetically

def test_help_keeps_the_pinned_metavar_and_lists_update():
    proc = run_estate("--help")
    assert proc.returncode == 0
    # the frozen root test (test_wheel_pipeline.py:154) asserts this exact
    # brace line; the pin retires at the first tests/ lift (wishlist 60)
    assert "{scaffold,validate,up,ingest,status,down}" in proc.stdout
    assert re.search(r"^\s+update\s", proc.stdout, re.M)
    assert "update --name RUN" in proc.stdout            # the docstring line


def test_update_unknown_run_refuses(tmp_path):
    proc = run_estate("update", "--runs-dir", str(tmp_path), "--name", "nope")
    assert proc.returncode == 1
    assert "no run named 'nope'" in proc.stderr


def test_update_unchanged_corpus_says_so_and_does_nothing(tmp_path):
    root, _ = scaffolded(tmp_path)
    runs = make_run(tmp_path, root)
    proc = run_estate("update", "--runs-dir", str(runs), "--name", "r1")
    assert proc.returncode == 0, proc.stderr
    assert "nothing moved" in proc.stdout
    assert "nothing to do" in proc.stdout
    # and it never got to the live estate (which does not exist)
    assert "REFUSED" not in proc.stderr


def test_update_dry_run_reports_an_edited_page_and_touches_nothing(tmp_path):
    root, lock = scaffolded(tmp_path)
    runs = make_run(tmp_path, root)
    for t in (1, 2):        # the prefix rule: an edit lands in EVERY timestep
        (root / "train" / "cases" / "case_a" / f"timestep-{t}" / "pages" /
         "page_0001.md").write_text(page_text("case_a", 1) + "Edited.\n",
                                    encoding="utf-8")
    before = (root / ic.LOCK_NAME).read_bytes()
    proc = run_estate("update", "--runs-dir", str(runs), "--name", "r1",
                      "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "case_a" in proc.stdout and "content moved" in proc.stdout
    assert re.search(r"^\s+case_b\s+unchanged", proc.stdout, re.M)
    assert "--dry-run: the local diff only" in proc.stdout
    assert (root / ic.LOCK_NAME).read_bytes() == before   # nothing written


def test_update_refuses_a_removed_case_naming_the_manual_path(tmp_path):
    root, _ = scaffolded(tmp_path)
    runs = make_run(tmp_path, root)
    shutil.rmtree(root / "eval" / "cases" / "case_b")
    proc = run_estate("update", "--runs-dir", str(runs), "--name", "r1")
    assert proc.returncode == 1
    assert "case(s) ['case_b']" in proc.stderr
    assert "removing a case is not an update" in proc.stderr
    assert "down --wipe" in proc.stderr


def test_update_detects_a_free_prompt_text_edit_under_an_explicit_id(tmp_path):
    """The one silent channel: an explicit id survives text edits by design,
    and prompts never enter the repo SHAs — the run's bank copy is the
    record of the text last served, and update diffs against it."""
    root, _ = scaffolded(tmp_path)
    runs = make_run(tmp_path, root)
    (root / "train" / "cases" / "case_a" / "timestep-2" /
     "prompts.yaml").write_text(
        "prompts:\n" + PROMPT_SKILL
        + '  - {id: "free:parties", source: free,\n'
          '     text: "Which parties are named so far? Cite pages. EDITED."}\n',
        encoding="utf-8")
    proc = run_estate("update", "--runs-dir", str(runs), "--name", "r1",
                      "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "free-prompt TEXT edited at ['timestep-2']" in proc.stdout
    assert "the repo is unchanged" in proc.stdout


def test_update_dry_run_reports_a_new_case_and_a_new_timestep(tmp_path):
    root, _ = scaffolded(tmp_path)
    runs = make_run(tmp_path, root)
    write_case(root, "train", "case_c", [1])
    ts3 = root / "eval" / "cases" / "case_b" / "timestep-3"
    (ts3.parent / "timestep-4" / "pages").mkdir(parents=True)
    for page in range(1, 5):
        src = ts3 / "pages" / f"page_{page:04d}.md"
        text = (src.read_text(encoding="utf-8") if src.is_file()
                else page_text("case_b", page))
        (ts3.parent / "timestep-4" / "pages" /
         f"page_{page:04d}.md").write_text(text, encoding="utf-8")
    (ts3.parent / "timestep-4" / "prompts.yaml").write_text(
        "prompts:\n" + PROMPT_SKILL, encoding="utf-8")
    proc = run_estate("update", "--runs-dir", str(runs), "--name", "r1",
                      "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert re.search(r"^\s+case_c\s+NEW", proc.stdout, re.M)
    assert "new branch(es) ['timestep-4']" in proc.stdout
