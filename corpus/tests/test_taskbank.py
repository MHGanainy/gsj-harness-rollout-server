"""Taskbank generation (ADR-0022; the ADR-0003 deferral resolved at CP-24):
row count, split sourcing from the lock, triple uniqueness, the
resolved-card and verbatim-free columns, byte-determinism, the --only
refusal, the row → ``render_task_request`` submit path, and G1's
end-to-end story on the real callback bodies.

CP-01 skipped this module while bank building lived on the predecessor's
library API; CP-24 re-lands the five deferred specifications against this
repo's own builder — the predecessor's library is still not a dependency
(ADR-0002). One deliberate substitution: the predecessor-API parity test
(``test_uniform_corpus_matches_single_api_call``, ADR-0042(b)'s sha-parity
guard) cannot run library-free and is superseded by
``test_two_builds_are_byte_identical`` — the property it protected (an
unchanged tree reproducing identical bank bytes) is asserted directly."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import ingest_corpus as ic
from conftest import SKILL_MD

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING = REPO_ROOT / "corpus" / "staging"
FREE_TEXT = "Which parties are named so far? Cite pages."

# The smallest RunConfig the render surface accepts — inline, so this
# suite never reads the server's fixtures; invalid hosts on purpose
# (nothing here talks to a network).
MINIMAL_CFG = {
    "estate": {
        "clone_url_for": "http://forgejo.invalid:3000/gsj-staging/{case_id}.git",
        "mcp_url_base": "http://mcp.invalid:8790",
        "serving_base_url": "http://serve.invalid:8000",
        "model": "qwen3-0p6b",
    },
    "runtime": {"image": "example.invalid/harness:1"},
    "harness": {"tools_allowlist": ["search_pages"],
                "artifacts_dir": "/workspace/out"},
    "builder": {"end_of_turn_token_id": 151645},
    "polar": {"gateway": {"public_url": "http://gw.invalid:8100"}},
    "receiver": {"traces_dir": "/tmp/traces"},
}


def build(root: Path, estate: str) -> None:
    assert ic.main(["scaffold", "--corpus", str(root),
                    "--base-url", estate]) == 0
    assert ic.main(["taskbank", "--corpus", str(root)]) == 0


def read_rows(root: Path) -> list[dict]:
    return ic.read_taskbank_rows(root / "taskbank.parquet")


def test_rows_split_and_uniqueness(corpus_root, estate):
    build(corpus_root, estate)
    rows = read_rows(corpus_root)
    triples = [(r["case_id"], r["timestep"], r["prompt_id"]) for r in rows]
    # case_a: t1 skill; t2 skill + free. case_b (eval): t2, t3 skill each.
    assert triples == [
        ("case_a", 1, "skill:summarize"),
        ("case_a", 2, "free:parties"),
        ("case_a", 2, "skill:summarize"),
        ("case_b", 2, "skill:summarize"),
        ("case_b", 3, "skill:summarize"),
    ]
    assert triples == sorted(triples)  # the ADR-0022 canonical order
    assert len(set(triples)) == len(triples)
    for row in rows:
        assert row["split"] == ("eval" if row["case_id"] == "case_b"
                                else "train")
        assert row["sandbox_image"] == "example.invalid/harness:1"
    lock = json.loads((corpus_root / "corpus.lock.json").read_text())
    # exactly the frozen key set (ADR-0022 §4: no new lock keys)
    assert set(lock["taskbank"]) == {"path", "rows", "train", "eval",
                                     "sha256"}
    assert lock["taskbank"]["rows"] == 5
    assert lock["taskbank"]["train"] == 3 and lock["taskbank"]["eval"] == 2
    digest = hashlib.sha256(
        (corpus_root / "taskbank.parquet").read_bytes()).hexdigest()
    assert lock["taskbank"]["sha256"] == digest


def test_prompt_storage_is_the_render_surface(corpus_root, estate):
    """ADR-0022 §1–§3: a skill row carries the RESOLVED corpus-level card
    (and no prompt text), a free row the contract's verbatim text (and no
    card) — each column exactly what `render_task_request` takes."""
    build(corpus_root, estate)
    rows = {(r["case_id"], r["timestep"], r["prompt_id"]): r
            for r in read_rows(corpus_root)}
    skill = rows[("case_a", 1, "skill:summarize")]
    assert skill["prompt_source"] == "skill:summarize"
    assert skill["prompt_text"] is None
    assert skill["skill_card_text"] == SKILL_MD
    free = rows[("case_a", 2, "free:parties")]
    assert free["prompt_source"] == "free"
    assert free["skill_card_text"] is None
    assert free["prompt_text"] == FREE_TEXT


def test_two_builds_are_byte_identical(corpus_root, estate):
    """ADR-0022 §4 (supersedes the predecessor-API sha-parity test: the
    property it protected is asserted directly, bank AND lock)."""
    build(corpus_root, estate)
    first_bank = (corpus_root / "taskbank.parquet").read_bytes()
    first_lock = (corpus_root / "corpus.lock.json").read_bytes()
    assert ic.main(["taskbank", "--corpus", str(corpus_root)]) == 0
    assert (corpus_root / "taskbank.parquet").read_bytes() == first_bank
    assert (corpus_root / "corpus.lock.json").read_bytes() == first_lock


def test_only_is_refused(corpus_root, estate, capsys):
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    rc = ic.main(["taskbank", "--corpus", str(corpus_root),
                  "--only", "case_a"])
    assert rc == 2
    assert "corpus-wide" in capsys.readouterr().err


def test_promptless_timestep_produces_no_rows(corpus_root, estate):
    (corpus_root / "eval/cases/case_b/timestep-2/prompts.yaml").write_text(
        "", encoding="utf-8")
    build(corpus_root, estate)
    triples = {(r["case_id"], r["timestep"]) for r in read_rows(corpus_root)}
    assert ("case_b", 2) not in triples
    assert ("case_b", 3) in triples


def test_a_crlf_card_rides_byte_faithful(tmp_path, estate):
    """CP-13's binding constraint, armed: the row carries the card's raw
    FILE bytes decoded (`read_bytes().decode("utf-8")`), so a CRLF card
    keeps its \\r\\n — a `read_text()` resolution would silently translate
    the newlines and move the downstream G1 hash."""
    from conftest import make_corpus
    root = make_corpus(tmp_path / "crlf")
    card = root / "skills" / "summarize" / "SKILL.md"
    card.write_bytes(b"# Skill: summarize\r\n\r\nCRLF card.\r\n")
    build(root, estate)
    rows = {(r["case_id"], r["timestep"], r["prompt_id"]): r
            for r in read_rows(root)}
    text = rows[("case_a", 1, "skill:summarize")]["skill_card_text"]
    assert text == card.read_bytes().decode("utf-8")
    assert "\r\n" in text


def test_taskbank_without_lock_is_a_usage_error(corpus_root, capsys):
    """The split is sourced from the lock (ADR-0015's row-spec) — no
    scaffold, no bank."""
    rc = ic.main(["taskbank", "--corpus", str(corpus_root)])
    assert rc == 2
    assert "run the scaffold phase first" in capsys.readouterr().err


def test_split_move_without_rescaffold_refuses_to_build(corpus_root, estate,
                                                        capsys):
    """A case moved between splits after scaffold: the tree and the lock
    disagree, and the bank must refuse to state either value until a
    re-scaffold (the ADR-0015 freeze-record discipline, applied at build
    time, not just at verify)."""
    assert ic.main(["scaffold", "--corpus", str(corpus_root),
                    "--base-url", estate]) == 0
    shutil.move(str(corpus_root / "eval" / "cases" / "case_b"),
                str(corpus_root / "train" / "cases" / "case_b"))
    rc = ic.main(["taskbank", "--corpus", str(corpus_root)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "split as sourced 'train' != lock 'eval'" in err
    assert "re-scaffolded" in err


def test_dry_run_previews_and_writes_nothing(corpus_root, capsys):
    """`taskbank --dry-run` needs no lock (a fresh tree previews from the
    tree's own split) and writes neither bank nor lock."""
    rc = ic.main(["taskbank", "--corpus", str(corpus_root), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN — nothing written" in out
    assert "5 rows (train 3 / eval 2)" in out
    assert not (corpus_root / "taskbank.parquet").exists()
    assert not (corpus_root / "corpus.lock.json").exists()


def test_a_row_submits_without_translation(corpus_root, estate):
    """CP-24 Step 3, the whole path: read a row → `render_task_request`
    → a TaskRequest — every argument straight off the row, no
    `config.py` change (the CP-13/CP-14 result)."""
    from gsj_rollout.config import RunConfig, render_task_request
    build(corpus_root, estate)
    rows = {(r["case_id"], r["timestep"], r["prompt_id"]): r
            for r in read_rows(corpus_root)}
    cfg = RunConfig.model_validate(MINIMAL_CFG)

    row = rows[("case_b", 3, "skill:summarize")]
    body = render_task_request(
        cfg, task_id="t-skill-row",
        instruction=row["prompt_text"] or row["skill_card_text"],
        case_id=row["case_id"], timestep=row["timestep"],
        prompt_source=row["prompt_source"],
        skill_card_text=row["skill_card_text"], split=row["split"])
    assert body["instruction"] == SKILL_MD  # the resolved card IS the ask
    assert body["metadata"] == {
        "case_id": "case_b", "timestep": 3,
        "prompt_source": "skill:summarize",
        "skill_card_hash": hashlib.sha256(
            SKILL_MD.encode("utf-8")).hexdigest(),
        "split": "eval"}

    row = rows[("case_a", 2, "free:parties")]
    body = render_task_request(
        cfg, task_id="t-free-row",
        instruction=row["prompt_text"] or row["skill_card_text"],
        case_id=row["case_id"], timestep=row["timestep"],
        prompt_source=row["prompt_source"],
        skill_card_text=row["skill_card_text"], split=row["split"])
    assert body["instruction"] == FREE_TEXT
    assert body["metadata"] == {"case_id": "case_a", "timestep": 2,
                                "prompt_source": "free", "split": "train"}


def test_g1_end_to_end_on_the_staging_bank(tmp_path):
    """CP-24 Step 3's proof, fixture-driven: a STAGING skill row's card,
    through `render_task_request`'s render-computed hash, into task
    metadata, into a real callback body's trace metadata (the CP-11 hoist
    channel, stamped the way CP-13's fixtures stamp it), past
    `check_skill_card` against the real pins — clean. The raw bodies
    (which predate `prompt_source`) fail closed honestly, and an UNPINNED
    card (this suite's fixture card) is named `not_approved`."""
    from gsj_rollout import checks
    from gsj_rollout.config import RunConfig, render_task_request

    root = tmp_path / "staging"
    shutil.copytree(STAGING, root)
    # the committed lock ships with the tree: the bank builds estate-free
    assert ic.main(["taskbank", "--corpus", str(root)]) == 0
    rows = {(r["case_id"], r["timestep"], r["prompt_id"]): r
            for r in ic.read_taskbank_rows(root / "taskbank.parquet")}
    row = rows[("case_0001", 12, "skill:summarize")]  # the golden triple

    cfg = RunConfig.model_validate(MINIMAL_CFG)
    body = render_task_request(
        cfg, task_id="t-g1",
        instruction=row["prompt_text"] or row["skill_card_text"],
        case_id=row["case_id"], timestep=row["timestep"],
        prompt_source=row["prompt_source"],
        skill_card_text=row["skill_card_text"], split=row["split"])
    # the render-computed hash IS the pinned staging-card value
    assert body["metadata"]["skill_card_hash"] in \
        checks.approved_set("skill_card_hash")

    for fixture in ("pi-corpus", "fidelity"):  # both real callback bodies
        callback = json.loads(
            (REPO_ROOT / "docs" / "polar" / fixture /
             "callback_session_result.json").read_text(encoding="utf-8"))
        trace = callback["trajectory"]["traces"][0]
        # raw, verbatim: no statement — the honest fail-closed path
        assert checks.check_skill_card(trace) == \
            ["G1:missing_evidence:prompt_source"]
        # stamped with exactly what the row rendered (task metadata rides
        # into trace metadata top-level — the CP-11-proven hoist)
        stamped = {**trace, "metadata": {**trace.get("metadata", {}),
                                         **body["metadata"]}}
        assert checks.check_skill_card(stamped) == []

    # a card the pins do NOT approve states its hash and is refused by it
    doctored_body = render_task_request(
        cfg, task_id="t-g1-doctored", instruction=SKILL_MD,
        case_id="case_0001", timestep=12,
        prompt_source="skill:summarize", skill_card_text=SKILL_MD,
        split="train")
    doctored = {**trace, "metadata": {**trace.get("metadata", {}),
                                      **doctored_body["metadata"]}}
    (finding,) = checks.check_skill_card(doctored)
    assert finding.startswith("G1:skill_card_hash_not_approved:")
