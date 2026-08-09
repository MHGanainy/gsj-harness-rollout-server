"""Fixtures for the corpus-pipeline suite: a tiny contract-conformant corpus
built in tmp_path, scaffolded against a local ``file://`` bare estate — the
pipeline's first-class hermetic rail (ADR-0047). No network, no Forgejo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CORPUS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORPUS_DIR))

AGENTS_MD = "# AGENTS.md\n\nCite pages as `page:N` (file `md/page_NNNN.md`).\n"
SKILL_MD = "# Skill: summarize\n\nSummarize; cite pages as `page:N`.\n"

PROMPT_SKILL = '  - {id: "skill:summarize", source: skill, name: summarize}\n'
PROMPT_FREE = ('  - {id: "free:parties", source: free,\n'
               '     text: "Which parties are named so far? Cite pages."}\n')


def corpus_yaml(*, owner: str = "gsj-staging", eval_ids: str = "[]",
                mcp: str | None = None) -> str:
    mcp_block = f"mcp:\n  url_base: {mcp}\n" if mcp else ""
    return (
        "name: test-corpus\n"
        f"owner: {owner}\n"
        "forgejo:\n"
        "  base_url: http://forgejo.invalid:3000\n"
        f"{mcp_block}"
        "git:\n"
        "  name: gsj-fixtures\n"
        "  email: fixtures@gsj.invalid\n"
        '  date: "2026-01-01T00:00:00 +0000"\n'
        "sandbox_image: example.invalid/harness:1\n"
        f"eval_case_ids: {eval_ids}\n")


def page_text(case_id: str, page: int) -> str:
    return f"## Page {page}\n\nProse of {case_id} page {page}.\n"


def write_case(root: Path, case_id: str, timesteps: list[int],
               prompts: dict[int, str] | None = None) -> None:
    """One case with absolute-numbered, prefix-consistent timesteps. The
    per-timestep prompts default to the skill prompt everywhere."""
    for t in timesteps:
        pages = root / "cases" / case_id / f"timestep-{t}" / "pages"
        pages.mkdir(parents=True)
        for page in range(1, t + 1):
            (pages / f"page_{page:04d}.md").write_text(
                page_text(case_id, page), encoding="utf-8")
        body = (prompts or {}).get(t, PROMPT_SKILL)
        (pages.parent / "prompts.yaml").write_text(
            "prompts:\n" + body if body else "", encoding="utf-8")


def make_corpus(root: Path, **yaml_kwargs) -> Path:
    """The worked minimal shape of docs/corpus-contract.md: two cases, the
    second held out for eval; case_a's timestep 2 adds a free prompt (the
    per-timestep-prompts path)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.yaml").write_text(
        corpus_yaml(eval_ids="[case_b]", **yaml_kwargs), encoding="utf-8")
    (root / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    skill = root / "skills" / "summarize"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    write_case(root, "case_a", [1, 2],
               prompts={2: PROMPT_SKILL + PROMPT_FREE})
    write_case(root, "case_b", [2, 3])
    return root


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    return make_corpus(tmp_path / "corpus")


@pytest.fixture
def estate(tmp_path: Path) -> str:
    """A local bare estate the scaffolder pushes into (file:// rail)."""
    root = tmp_path / "estate"
    root.mkdir()
    return f"file://{root}"
