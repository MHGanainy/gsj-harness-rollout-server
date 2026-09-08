"""Fixtures for the corpus-pipeline suite: a tiny contract-conformant corpus
built in tmp_path, scaffolded against a local ``file://`` bare estate — the
pipeline's first-class hermetic rail (ADR-0047). No network, no Forgejo."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

CORPUS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORPUS_DIR))

# The real CLI's shapes, measured — CHARTER §8 rule 10 (CP-98): a fake's exit
# code and streams come from this file, never from the test author's memory;
# test_estate_cp98_reaper.py re-measures every entry against the CLI on PATH.
CLI_SHAPES_PATH = Path(__file__).resolve().parent / "cli_shapes.json"
CLI_SHAPES = json.loads(CLI_SHAPES_PATH.read_text(encoding="utf-8"))


def cli_shape(key: str, cmd: list | None = None, **subs) -> subprocess.CompletedProcess:
    """A faked CLI answer with the REAL CLI's shape: exit code, stdout and
    stderr from cli_shapes.json, `{name}` filled from `subs`. `cmd` is the
    argv the code under test ran (recorded on the CompletedProcess)."""
    shape = CLI_SHAPES["shapes"][key]

    def fill(text: str) -> str:     # `{name}` only — never str.format: a stream may hold braces
        for k, v in subs.items():
            text = text.replace("{" + k + "}", v)
        return text

    stdout = shape.get("stdout")
    if stdout is None:      # the value is the host's, not the CLI's (`stdout_re`): the caller's literal
        return subprocess.CompletedProcess(cmd or shape["argv"], shape["returncode"],
                                           subs.get("stdout", ""), fill(shape["stderr"]))
    return subprocess.CompletedProcess(cmd or shape["argv"], shape["returncode"],
                                       fill(stdout), fill(shape["stderr"]))

AGENTS_MD = "# AGENTS.md\n\nCite pages as `page:N` (file `md/page_NNNN.md`).\n"
SKILL_MD = "# Skill: summarize\n\nSummarize; cite pages as `page:N`.\n"

PROMPT_SKILL = '  - {id: "skill:summarize", source: skill, name: summarize}\n'
PROMPT_FREE = ('  - {id: "free:parties", source: free,\n'
               '     text: "Which parties are named so far? Cite pages."}\n')


def corpus_yaml(*, owner: str = "gsj-staging", mcp: str | None = None,
                estate_fields: bool = True) -> str:
    """estate_fields=False writes the CP-71 shape — name/owner/git only,
    none of the three deprecated estate fields."""
    mcp_block = f"mcp:\n  url_base: {mcp}\n" if mcp else ""
    return (
        "name: test-corpus\n"
        f"owner: {owner}\n"
        + ("forgejo:\n"
           "  base_url: http://forgejo.invalid:3000\n"
           f"{mcp_block}" if estate_fields else "")
        + "git:\n"
          "  name: gsj-fixtures\n"
          "  email: fixtures@gsj.invalid\n"
          '  date: "2026-01-01T00:00:00 +0000"\n'
        + ("sandbox_image: example.invalid/harness:1\n" if estate_fields
           else ""))


def page_text(case_id: str, page: int) -> str:
    return f"## Page {page}\n\nProse of {case_id} page {page}.\n"


def write_case(root: Path, split: str, case_id: str, timesteps: list[int],
               prompts: dict[int, str] | None = None) -> None:
    """One case with absolute-numbered, prefix-consistent timesteps under
    its split directory (ADR-0015). The per-timestep prompts default to
    the skill prompt everywhere."""
    for t in timesteps:
        pages = root / split / "cases" / case_id / f"timestep-{t}" / "pages"
        pages.mkdir(parents=True)
        for page in range(1, t + 1):
            (pages / f"page_{page:04d}.md").write_text(
                page_text(case_id, page), encoding="utf-8")
        body = (prompts or {}).get(t, PROMPT_SKILL)
        (pages.parent / "prompts.yaml").write_text(
            "prompts:\n" + body if body else "", encoding="utf-8")


def make_corpus(root: Path, **yaml_kwargs) -> Path:
    """The worked minimal shape of docs/corpus-contract.md (v2, ADR-0015):
    case_a under train/, case_b held out under eval/; case_a's timestep 2
    adds a free prompt (the per-timestep-prompts path)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.yaml").write_text(
        corpus_yaml(**yaml_kwargs), encoding="utf-8")
    (root / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    skill = root / "skills" / "summarize"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    write_case(root, "train", "case_a", [1, 2],
               prompts={2: PROMPT_SKILL + PROMPT_FREE})
    write_case(root, "eval", "case_b", [2, 3])
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


class FakePull:
    """A fake for estate.py's `popen` seam (CP-96): `docker pull`'s stdout
    lines delivered live to the drainer, a delay before the process exits,
    its stderr text and its return code — so image_pull's heartbeat, phase
    tally and verdict can be exercised without a daemon."""

    def __init__(self, cmd, returncode=0, lines=(), stderr="", delay=0.0):
        self.args = cmd
        self._final, self._deadline = returncode, time.monotonic() + delay
        self.returncode = None
        self.stdout = iter(list(lines))
        self.stderr = io.StringIO(stderr)

    def wait(self, timeout=None):
        remaining = self._deadline - time.monotonic()
        if timeout is not None and remaining > timeout:
            time.sleep(timeout)
            raise subprocess.TimeoutExpired(self.args, timeout)
        if remaining > 0:
            time.sleep(remaining)
        self.returncode = self._final
        return self.returncode
