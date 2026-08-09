"""Taskbank generation: row count, split, triple uniqueness, the public-API
parity of the uniform path, and the --only refusal.

CP-01: the whole module is skipped — these tests exercise bank building
through the predecessor's library API (``build_taskbank`` et al.), and the
taskbank phase is deferred to CP-07 (ADR-0003; the library is not a
dependency of this repo, ADR-0002). The deferral behavior itself is tested
in test_verify.py. Kept verbatim below as the specification of what a
CP-07 builder must reproduce."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.skip("taskbank phase deferred to CP-07 (ADR-0003) — bank building "
            "needs the predecessor's library, which is not a dependency "
            "here (ADR-0002)", allow_module_level=True)

import ingest_corpus as ic
from conftest import make_corpus


def build(root: Path, estate: str) -> None:
    assert ic.main(["scaffold", "--corpus", str(root),
                    "--base-url", estate]) == 0
    assert ic.main(["taskbank", "--corpus", str(root)]) == 0


def test_rows_split_and_uniqueness(corpus_root, estate):
    from gsj.envloader import read_taskbank
    build(corpus_root, estate)
    rows = read_taskbank(corpus_root / "taskbank.parquet")
    triples = [(r.metadata.case_repo_id, r.metadata.timestep,
                r.metadata.prompt_id) for r in rows]
    # case_a: t1 skill; t2 skill + free. case_b (eval): t2, t3 skill each.
    assert sorted(triples) == [
        ("case_a", 1, "skill:summarize"),
        ("case_a", 2, "free:parties"),
        ("case_a", 2, "skill:summarize"),
        ("case_b", 2, "skill:summarize"),
        ("case_b", 3, "skill:summarize"),
    ]
    assert len(set(triples)) == len(triples)
    for row in rows:
        assert row.split == ("eval" if row.metadata.case_repo_id == "case_b"
                             else "train")
        assert row.extra_info.tools_kwargs.task.sandbox.image == \
            "example.invalid/harness:1"
    lock = json.loads((corpus_root / "corpus.lock.json").read_text())
    assert lock["taskbank"]["rows"] == 5
    assert lock["taskbank"]["train"] == 3 and lock["taskbank"]["eval"] == 2
    digest = hashlib.sha256(
        (corpus_root / "taskbank.parquet").read_bytes()).hexdigest()
    assert lock["taskbank"]["sha256"] == digest


def test_prompt_storage_follows_adr_0016(corpus_root, estate):
    from gsj.envloader import read_taskbank
    build(corpus_root, estate)
    rows = {(r.metadata.case_repo_id, r.metadata.timestep,
             r.metadata.prompt_id): r
            for r in read_taskbank(corpus_root / "taskbank.parquet")}
    skill = rows[("case_a", 1, "skill:summarize")]
    assert skill.prompt == [] and skill.metadata.prompt_source == "skill"
    free = rows[("case_a", 2, "free:parties")]
    assert free.metadata.prompt_source == "free"
    assert [m.role for m in free.prompt] == ["user"]
    assert free.prompt[0].content == \
        "Which parties are named so far? Cite pages."


def test_uniform_corpus_matches_single_api_call(tmp_path, estate):
    """A corpus whose cases each carry ONE uniform prompt list must produce
    byte-identical parquet to the direct single build_taskbank call — the
    ADR-0042(b) parity that kept the hosted staging bank's sha unchanged."""
    from gsj.envloader import CaseSpec, PromptSpec, build_taskbank
    from gsj.envloader.taskbank import write_taskbank

    root = make_corpus(tmp_path / "uniform")
    # strip the per-timestep extra prompt: make case_a uniform too
    (root / "cases/case_a/timestep-2/prompts.yaml").write_text(
        'prompts:\n  - {id: "skill:summarize", source: skill, name: summarize}\n',
        encoding="utf-8")
    build(root, estate)

    direct = tmp_path / "direct.parquet"
    table = build_taskbank(
        {"case_a": CaseSpec(timesteps=[1, 2],
                            prompts=[PromptSpec.skill("summarize")]),
         "case_b": CaseSpec(timesteps=[2, 3],
                            prompts=[PromptSpec.skill("summarize")])},
        ["case_b"], sandbox_image="example.invalid/harness:1")
    write_taskbank(table, direct)
    assert direct.read_bytes() == (root / "taskbank.parquet").read_bytes()


def test_only_is_refused(corpus_root, estate, capsys):
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    rc = ic.main(["taskbank", "--corpus", str(corpus_root),
                  "--only", "case_a"])
    assert rc == 2
    assert "corpus-wide" in capsys.readouterr().err


def test_promptless_timestep_produces_no_rows(corpus_root, estate):
    from gsj.envloader import read_taskbank
    (corpus_root / "cases/case_b/timestep-2/prompts.yaml").write_text(
        "", encoding="utf-8")
    build(corpus_root, estate)
    rows = read_taskbank(corpus_root / "taskbank.parquet")
    triples = {(r.metadata.case_repo_id, r.metadata.timestep)
               for r in rows}
    assert ("case_b", 2) not in triples
    assert ("case_b", 3) in triples
