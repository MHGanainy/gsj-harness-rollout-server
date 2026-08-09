"""Ingestion + index lifecycle (ADR-0040(c)/(e)): full document from main via
git plumbing, contiguous pages, single-page chunks that are verbatim page
slices, timesteps parsed from refs; fingerprint-gated reuse/rebuild and the
rebuild: never frozen-prod mode. All against the LOCAL deterministic bares."""

from __future__ import annotations

import shutil

import pytest

from helpers import (
    ALL_REPOS,
    CASE_PAGES,
    CASE_TIMESTEPS,
    canonical,
    make_state,
    write_config,
)


def test_pages_ingested_contiguous(built_state):
    """Every case ingests its FULL main-branch page set, contiguous 1..N,
    with the expected N (18/22/15/20)."""
    assert sorted(built_state.cases) == ALL_REPOS
    for case_id, expected_n in CASE_PAGES.items():
        index = built_state.cases[case_id]
        assert sorted(index.pages) == list(range(1, expected_n + 1))
        assert index.n_pages == expected_n


def test_chunks_carry_one_page_and_never_span(built_state):
    """Each chunk carries exactly one page, file == md/page_NNNN.md for that
    page, and its text is a verbatim substring of that single page's text —
    chunks never span page boundaries (ADR-0040(e))."""
    for case_id, index in built_state.cases.items():
        assert index.chunks, case_id
        covered = set()
        for chunk in index.chunks:
            assert chunk.case_id == case_id
            assert isinstance(chunk.page, int)
            assert chunk.page in index.pages
            assert chunk.file == f"md/page_{chunk.page:04d}.md"
            assert chunk.text in index.pages[chunk.page], (
                f"{case_id} p{chunk.page} chunk {chunk.chunk_idx} "
                f"is not a substring of its page")
            covered.add(chunk.page)
        assert covered == set(index.pages), f"{case_id}: uncovered pages"


def test_timesteps_parsed_from_refs(built_state):
    """timestep-{T} branches parse to the recorded per-case timestep lists;
    the raw refs include main plus each timestep branch."""
    for case_id, expected in CASE_TIMESTEPS.items():
        index = built_state.cases[case_id]
        assert index.timesteps == expected
        assert "main" in index.refs
        for timestep in expected:
            assert f"timestep-{timestep}" in index.refs


def test_second_appstate_reuses_index_and_serves_identical_results(
        built_state, shared_dirs):
    """Idempotent re-init: a SECOND AppState over the same index dir matches
    the stored fingerprint, reports index_reused True via the /health payload,
    and serves byte-identical search results from the loaded vectors."""
    config_path = write_config(
        shared_dirs["root"], repos=ALL_REPOS,
        clone_cache_dir=shared_dirs["clones"], index_path=shared_dirs["index"],
        name="config-reinit.yaml")
    state2 = make_state(config_path, encoder=built_state.encoder)
    assert state2.status == "ready", state2.error
    assert state2.reused_index is True
    health = state2.health()
    assert health["state"] == "ready"
    assert health["index_reused"] is True
    assert health["fingerprint"] == built_state.fingerprint
    assert health["decisions"] == 30

    query_vec, _ = built_state.encoder.encode_query(
        "deposition slip concerning the sealed ledgers")
    for case_id, timestep in [("case_0001", 12), ("case_0003", 9)]:
        first = built_state.cases[case_id].search(query_vec, k=10,
                                                 timestep=timestep)
        second = state2.cases[case_id].search(query_vec, k=10,
                                              timestep=timestep)
        assert canonical(first) == canonical(second)
        assert first, "expected non-empty results for the identity check"


@pytest.fixture(scope="module")
def mini(tmp_path_factory, built_state):
    """A small single-case (case_0003) index built once for the
    rebuild-lifecycle tests; the loaded MiniLM is shared for speed."""
    root = tmp_path_factory.mktemp("mini")
    config_path = write_config(root, repos=["case_0003"],
                               clone_cache_dir=root / "clones",
                               index_path=root / "index")
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "ready", state.error
    return {"root": root, "state": state}


def test_fingerprint_mismatch_rebuilds(mini, built_state, tmp_path_factory):
    """Changing a chunking param changes the corpus fingerprint: a fresh
    AppState over a copy of the stored index detects the mismatch and
    REBUILDS (index_reused False, new fingerprint)."""
    root = tmp_path_factory.mktemp("mismatch")
    shutil.copytree(mini["root"] / "index", root / "index")
    config_path = write_config(root, repos=["case_0003"],
                               clone_cache_dir=mini["root"] / "clones",
                               index_path=root / "index", max_tokens=200)
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.reused_index is False
    assert state.fingerprint != mini["state"].fingerprint
    assert state.health()["index_reused"] is False


def test_rebuild_never_with_missing_index_errors(mini, built_state,
                                                 tmp_path_factory):
    """index.rebuild: never + no stored index => state "error" with a message
    naming the mode and the missing index — frozen prod refuses to rebuild."""
    root = tmp_path_factory.mktemp("never-missing")
    config_path = write_config(root, repos=["case_0003"],
                               clone_cache_dir=mini["root"] / "clones",
                               index_path=root / "index", rebuild="never")
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "error"
    assert state.error is not None
    assert "rebuild=never" in state.error
    assert "missing" in state.error
    assert state.health()["state"] == "error"
    assert "error" in state.health()


def test_rebuild_never_with_stale_index_errors(mini, built_state,
                                               tmp_path_factory):
    """index.rebuild: never + a stored index whose fingerprint mismatches the
    computed corpus (chunking param changed) => state "error" calling the
    index STALE, never a silent rebuild."""
    root = tmp_path_factory.mktemp("never-stale")
    shutil.copytree(mini["root"] / "index", root / "index")
    config_path = write_config(root, repos=["case_0003"],
                               clone_cache_dir=mini["root"] / "clones",
                               index_path=root / "index", rebuild="never",
                               max_tokens=200)
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "error"
    assert "rebuild=never" in state.error
    assert "STALE" in state.error
