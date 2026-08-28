"""The Chroma backend's own contract (CP-15, ADR-0016): the cutoff is a
PRE-filter (invariant 3, verified empirically — designed before the code),
the stored vectors are the pinned encoder's and Chroma's own embedding
machinery is unreachable (the silent-substitution hazard: Chroma's default
EF is a DIFFERENT MiniLM at the same 384 dims), the corpus fingerprint
carries the Chroma version so an upgrade rebuilds loudly, and the service
knows the corpus only through Forgejo clone URLs — never the corpus tree's
paths (the CP-14 split re-shape is invisible here by construction,
asserted rather than assumed — CP-15 Step 3)."""

from __future__ import annotations

import json
import shutil
import time
from types import SimpleNamespace

import numpy as np
import pytest

from helpers import (
    ALL_REPOS,
    SERIAL_RE,
    SERVICE_DIR,
    get_health,
    make_state,
    write_config,
)

from gsj_mcp_service.index import CHROMA_VERSION, corpus_fingerprint


def chunk_ids_within(index, timestep: int) -> set[str]:
    return {f"p{c.page:04d}c{c.chunk_idx:04d}"
            for c in index.chunks if c.page <= timestep}


# -- invariant 3: pre-filter, not post-filter --------------------------------

def test_cutoff_prefilters_candidates_not_postfilters(built_state, facts):
    """THE empirical check, designed before the code: aim a query at a fact
    far BEYOND the cutoff so the global (unfiltered) top ranks are
    dominated by out-of-cutoff chunks, then ask the where-filtered query
    for the whole in-cutoff candidate set. A pre-filter returns ALL of it
    (the candidate set was constrained before ranking); a post-filter
    (rank globally, drop out-of-cutoff afterwards) returns fewer than
    requested and moves the recall boundary — the leak shape ADR-0040(d)
    forbids."""
    index = built_state.cases["case_0002"]          # 22 pages
    timestep = 2
    in_cutoff = chunk_ids_within(index, timestep)
    assert 0 < len(in_cutoff) < len(index.chunks)

    fact = next(f for f in facts
                if f["case_id"] == "case_0002" and f["page"] > 15)
    query_vec, _ = built_state.encoder.encode_query(fact["line"])

    unfiltered = index.collection.query(
        query_embeddings=[query_vec], n_results=len(in_cutoff),
        include=["metadatas"])
    global_pages = [m["page"] for m in unfiltered["metadatas"][0]]
    assert any(page > timestep for page in global_pages), (
        "probe mis-aimed: the global ranking must be dominated by "
        "out-of-cutoff chunks for this test to discriminate")

    filtered = index.collection.query(
        query_embeddings=[query_vec], n_results=len(in_cutoff),
        where={"page": {"$lte": timestep}}, include=["metadatas"])
    assert len(filtered["ids"][0]) == len(in_cutoff), (
        "fewer results than in-cutoff candidates — where= post-filters")
    assert set(filtered["ids"][0]) == in_cutoff
    assert all(m["page"] <= timestep for m in filtered["metadatas"][0])


def test_tool_level_tight_timestep_serves_every_visible_page(built_state,
                                                             facts):
    """The same property one layer up: search_case at T=2 with a query
    aimed beyond the cutoff still ranks BOTH visible pages — never fewer
    results because the true top ranks were filtered away."""
    fact = next(f for f in facts
                if f["case_id"] == "case_0002" and f["page"] > 15)
    query_vec, _ = built_state.encoder.encode_query(fact["line"])
    results = built_state.cases["case_0002"].search(query_vec, k=20,
                                                    timestep=2)
    assert {hit["page"] for hit in results} == {1, 2}
    serial = SERIAL_RE.search(fact["line"]).group(0)
    assert serial not in json.dumps(results)


# -- embedding identity (ADR-0016 guard; bounded since CP-55) ----------------

# The CP-55 bound (ADR-0016 amendment). Both ends of the margin are
# MEASURED, and it is thin — 7.75x end to end, not the six orders the
# record used to claim: benign same-encoder drift reaches max|Δ|
# 1.490e-08 (arm64, CP-18) / 7.451e-09 (the CI runner image — CP-53
# attempts 1+2 and CP-54, identical), while the nearest real hazard —
# Chroma's default EF, an fp32 ONNX export of the SAME checkpoint, not
# the quantized model ADR-0016 assumed — sits at max|Δ|
# 1.155e-07..2.719e-07 across all 51 case_0001 rows (CP-55; the three
# rows this oracle samples: 1.6e-07..1.9e-07). 4e-08 is the geometric
# midpoint: 2.7x above the worst measured drift, 2.9x below the hazard
# floor, ~11 float32 ULP at MiniLM's typical component magnitude. The
# cosine floor guards only the genuinely-different-model class
# (unrelated vectors sit near 0.80, CP-18): cosine cannot resolve the
# drift OR the fp32-ONNX substitution — every measured row of both
# classes lands within 1 ULP of 1.0 (CP-51's forced run printed
# 1.000000000; the firings and the substitution both print
# 1.000000119, float32's 1+1ULP) — so it exists to keep the wrong-model
# class caught if the |Δ| bound is ever loosened.
ENCODER_MAX_ABS_DELTA = 4e-08
ENCODER_MIN_COSINE = 0.999


def assert_vector_is_the_pinned_encoders(chunk_id: str, stored, ours) -> None:
    delta = float(np.abs(stored - ours).max())
    cosine = float(stored @ ours / (np.linalg.norm(stored) * np.linalg.norm(ours)))
    assert delta <= ENCODER_MAX_ABS_DELTA and cosine >= ENCODER_MIN_COSINE, (
        f"chunk {chunk_id} vector is not "
        f"the pinned encoder's: max|Δ| {delta:.3e}, cosine {cosine:.9f} "
        f"(bound: max|Δ| ≤ {ENCODER_MAX_ABS_DELTA:.0e}, "
        f"cosine ≥ {ENCODER_MIN_COSINE} — ADR-0016 as amended at CP-55)")


def test_stored_vectors_are_the_pinned_encoders(built_state):
    """Stored Chroma vectors are the pinned MiniLM encoder's output for the
    same chunk texts, to within the CP-55 bound — Chroma never embedded
    anything. The hazard is silent: Chroma's default EF (attached by
    get_collection's default parameter) is a MiniLM at the same 384 dims,
    so a substitution would produce plausible scores, not errors; the
    bound is set so every measured row of that substitution fails it."""
    index = built_state.cases["case_0001"]
    ours = built_state.encoder.encode_corpus([c.text for c in index.chunks])
    for row in (0, len(index.chunks) // 2, len(index.chunks) - 1):
        chunk = index.chunks[row]
        got = index.collection.get(
            ids=[f"p{chunk.page:04d}c{chunk.chunk_idx:04d}"],
            include=["embeddings"])
        stored = np.asarray(got["embeddings"][0], dtype=np.float32)
        assert stored.shape == (384,)
        # np.array_equal until CP-55; the message keeps printing the
        # measured numbers — they are what made the bound decidable, and
        # the next drift must print its own.
        assert_vector_is_the_pinned_encoders(
            f"p{chunk.page:04d}c{chunk.chunk_idx:04d}", stored, ours[row])


def test_identity_bound_fails_wrong_in_either_direction(built_state):
    """The bound proven at both measured ends (ADR-0016, CP-55): the benign
    drift classes pass (the CI runner's 7.451e-09 on every component,
    arm64's worst 1.490e-08 on one), the measured hazard class fails (one
    component moved by 1.937e-07 — the fp32-ONNX substitution's delta on
    this very chunk), and a wrong-model vector fails the cosine floor on
    its own. The failing halves are what stop a future loosening from
    going unnoticed."""
    index = built_state.cases["case_0001"]
    chunk = index.chunks[0]
    cid = f"p{chunk.page:04d}c{chunk.chunk_idx:04d}"
    got = index.collection.get(ids=[cid], include=["embeddings"])
    stored = np.asarray(got["embeddings"][0], dtype=np.float32)

    within_ci = stored + np.float32(7.451e-09)
    assert_vector_is_the_pinned_encoders(cid, within_ci, stored)
    within_arm64 = stored.copy()
    within_arm64[0] += np.float32(1.490e-08)
    assert_vector_is_the_pinned_encoders(cid, within_arm64, stored)

    beyond = stored.copy()
    beyond[0] += np.float32(1.937e-07)
    with pytest.raises(AssertionError, match="not the pinned encoder's"):
        assert_vector_is_the_pinned_encoders(cid, beyond, stored)

    wrong_model = np.roll(stored, 7)
    cosine = float(wrong_model @ stored /
                   (np.linalg.norm(wrong_model) * np.linalg.norm(stored)))
    assert cosine < ENCODER_MIN_COSINE
    with pytest.raises(AssertionError, match="not the pinned encoder's"):
        assert_vector_is_the_pinned_encoders(cid, wrong_model, stored)


def test_chroma_text_ops_are_refused(built_state):
    """The structural half of the guard: every collection handle carries
    the raising EF, so a stray text op fails loudly instead of silently
    embedding with Chroma's bundled model."""
    collection = built_state.cases["case_0001"].collection
    with pytest.raises(Exception, match="pinned MiniLM encoder"):
        collection.query(query_texts=["probe"], n_results=1)


# -- the fingerprint's Chroma component (ADR-0016) ---------------------------

def test_fingerprint_carries_the_chroma_version(built_state):
    config = built_state.config
    sources = {cid: SimpleNamespace(main_sha=idx.refs["main"])
               for cid, idx in built_state.cases.items()}
    args = (sources, config.embedding, config.chunking,
            config.decisions.seed, config.decisions.corpus_size)
    assert corpus_fingerprint(*args) == built_state.fingerprint
    assert corpus_fingerprint(*args, chroma_version="0.0.0-previous") \
        != built_state.fingerprint


def test_chroma_version_change_rebuilds_loudly(built_state, shared_dirs,
                                               tmp_path_factory):
    """Simulate a Chroma upgrade: the stored fingerprint was written under
    a different chroma version => if-stale detects the mismatch and
    REBUILDS (index_reused False), landing back on the current version's
    fingerprint — never a silent reuse of an old-format store."""
    root = tmp_path_factory.mktemp("chroma-bump")
    shutil.copytree(shared_dirs["index"], root / "index")
    config = built_state.config
    sources = {cid: SimpleNamespace(main_sha=idx.refs["main"])
               for cid, idx in built_state.cases.items()}
    previous = corpus_fingerprint(
        sources, config.embedding, config.chunking, config.decisions.seed,
        config.decisions.corpus_size, chroma_version="0.0.0-previous")
    (root / "index" / "fingerprint.json").write_text(json.dumps(
        {"fingerprint": previous, "index_format": 2,
         "chroma_version": "0.0.0-previous"}))

    config_path = write_config(
        root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index")
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.reused_index is False
    assert state.fingerprint == built_state.fingerprint


def test_reindex_after_out_of_band_store_replacement_rebuilds(
        built_state, tmp_path_factory):
    """The CP-15 review's phantom-store finding, pinned: chroma caches one
    system per path per process, so after `rm -rf <index.path>/chroma` a
    running service would keep serving the unlinked inode and a reindex
    would 'reuse' a phantom. request_reindex must be restart-equivalent
    (ADR-0016): it evicts the cached system, observes the real (now empty)
    disk, and REBUILDS loudly."""
    root = tmp_path_factory.mktemp("phantom")
    config_path = write_config(
        root, repos=["case_0003"], clone_cache_dir=root / "clones",
        index_path=root / "index")
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.reused_index is False

    shutil.rmtree(root / "index" / "chroma")
    assert state.request_reindex() == "started"
    deadline = time.monotonic() + 300
    while state.status == "indexing" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert state.status == "ready", state.error
    assert state.reused_index is False, (
        "reindex reused a store that no longer exists on disk — the phantom")
    vec, _ = built_state.encoder.encode_query(
        "deposition slip concerning the sealed ledgers")
    assert state.cases["case_0003"].search(vec, k=3, timestep=9)


# -- /health names the live backend (CP-15) ----------------------------------

def test_health_reports_backend_identity(server):
    health = get_health(server.base_url)
    assert health["backend"]["name"] == "chromadb"
    assert health["backend"]["version"] == CHROMA_VERSION
    assert health["backend"]["collections"] == len(ALL_REPOS) + 1  # +decisions


# -- CP-15 Step 3: the split-shaped tree is invisible here -------------------

def test_no_corpus_tree_path_literal_in_service_source():
    """CP-14 measured that the service consumes the corpus through the
    pipeline API and Forgejo clone URLs; assert it rather than assume it:
    no service module names the corpus tree's paths. (The census half of
    the assertion is test_pages_ingested_contiguous — 18/22/15/20 off the
    current staging tree via the pipeline-built bares.)"""
    for path in sorted((SERVICE_DIR / "gsj_mcp_service").glob("*.py")):
        text = path.read_text()
        for needle in ("cases/", "train/", "eval/", "corpus/staging"):
            assert needle not in text, (
                f"{path.name} names the corpus tree: {needle!r}")
