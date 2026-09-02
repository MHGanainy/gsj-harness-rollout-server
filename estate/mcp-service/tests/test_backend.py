"""The Chroma backend's own contract (CP-15, ADR-0016): the cutoff is a
PRE-filter (invariant 3, verified empirically — designed before the code),
the stored vectors are the CONFIGURED encoder's and Chroma's own embedding
machinery is unreachable (the silent-substitution hazard: Chroma's default
EF is an fp32 ONNX export of the default MiniLM at the same 384 dims), the
corpus fingerprint carries the Chroma version so an upgrade rebuilds
loudly, and the service knows the corpus only through Forgejo clone URLs —
never the corpus tree's paths (the CP-14 split re-shape is invisible here
by construction, asserted rather than assumed — CP-15 Step 3). Since CP-57
the model is configuration: the store records which model built it, a
change is refused until an explicit rebuild, the vectors' width is
cross-checked at load, the chunk window is checked against the model, and
the oracle's bound follows the configured model's scale."""

from __future__ import annotations

import json
import logging
import math
import shutil
import time
from types import SimpleNamespace

import numpy as np
import pytest

from helpers import (
    ALL_REPOS,
    DEFAULT_MODEL,
    REVISION,
    SECOND_DIMENSION,
    SECOND_MAX_TOKENS,
    SECOND_MODEL,
    SECOND_OVERLAP,
    SECOND_REVISION,
    SERIAL_RE,
    SERVICE_DIR,
    canonical,
    get_health,
    make_state,
    write_config,
)

import gsj_mcp_service.index as index_module
import gsj_mcp_service.state as state_module
from gsj_mcp_service.config import load_config
from gsj_mcp_service.index import (ADD_BATCH_SIZE, CHROMA_VERSION,
                                   PRE_CP57_STORE_IDENTITY, batch_spans,
                                   corpus_fingerprint, read_fingerprint,
                                   read_store_identity, sweep_orphans,
                                   write_fingerprint)


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


# -- embedding identity (ADR-0016 guard; bounded since CP-55; the model
#    configurable since CP-57) ----------------------------------------------

# The CP-55 bound (ADR-0016 amendment), MEASURED against the default
# model — all-MiniLM-L6-v2 at 384 dims — and both ends of its margin are
# properties of that exact checkpoint. The margin is thin — 7.75x end to
# end, not the six orders the record used to claim: benign same-encoder
# drift reaches max|Δ| 1.490e-08 (arm64, CP-18) / 7.451e-09 (the CI
# runner image — CP-53 attempts 1+2 and CP-54, identical), while the
# nearest real hazard — Chroma's default EF, an fp32 ONNX export of the
# SAME checkpoint, not the quantized model ADR-0016 assumed — sits at
# max|Δ| 1.155e-07..2.719e-07 across all 51 case_0001 rows (CP-55; the
# three rows this oracle samples: 1.6e-07..1.9e-07). 4e-08 is the
# geometric midpoint: 2.7x above the worst measured drift, 2.9x below
# the hazard floor, ~11 float32 ULP at MiniLM's typical component
# magnitude. The cosine floor guards only the genuinely-different-model
# class: cosine cannot resolve the drift OR the fp32-ONNX substitution —
# every measured row of both classes lands within 1 ULP of 1.0 (CP-51's
# forced run printed 1.000000000; the firings and the substitution both
# print 1.000000119, float32's 1+1ULP) — so it exists to keep the
# wrong-model class caught if the |Δ| bound is ever loosened.
#
# CP-57, the model configurable — how the bound survives a model change.
# The |Δ| end is SCALE-relative: a unit vector's rms component is 1/√d
# (measured: 0.0510 at 384, 0.0361 at 768), and float32 drift is
# relative to component magnitude, so the measured 4e-08 at 384 dims
# transposes to 4e-08·√(384/d) — exactly the CP-55 constant under the
# default model (the default path's assertions are numerically
# unchanged), a reasoned EXTRAPOLATION elsewhere (A-31: unmeasured until
# a production re-pin measures its own two ends — ADR-0016 (c) still
# owes that). The hazard end does not transfer and does not need to:
# for any configured model that is not the default, Chroma's default EF
# is a COMPLETELY different model, and the substitution class is the
# cross-model class — measured at CP-57 on the same texts, MiniLM vs
# another 384-dim encoder (bge-small): cosine 0.23..0.31, max|Δ| ≥ 0.31
# — which the cosine floor fails by ~0.7, while at any other dimension
# the store refuses the vector outright (Chroma fixes a collection's
# width at the first add; test-asserted below).
MEASURED_MODEL = DEFAULT_MODEL
MEASURED_DIMENSION = 384
ENCODER_MAX_ABS_DELTA = 4e-08      # measured at MEASURED_DIMENSION
ENCODER_MIN_COSINE = 0.999


def encoder_max_abs_delta(dimension: int) -> float:
    """The |Δ| bound at a model's dimension: the measured constant under the
    default model, transposed by component scale elsewhere (CP-57)."""
    return ENCODER_MAX_ABS_DELTA * math.sqrt(MEASURED_DIMENSION / dimension)


def assert_vector_is_the_pinned_encoders(chunk_id: str, stored, ours) -> None:
    dimension = int(np.asarray(ours).shape[0])
    bound = encoder_max_abs_delta(dimension)
    delta = float(np.abs(stored - ours).max())
    cosine = float(stored @ ours / (np.linalg.norm(stored) * np.linalg.norm(ours)))
    assert delta <= bound and cosine >= ENCODER_MIN_COSINE, (
        f"chunk {chunk_id} vector is not "
        f"the pinned encoder's: max|Δ| {delta:.3e}, cosine {cosine:.9f} "
        f"(bound at {dimension} dims: max|Δ| ≤ {bound:.3e}, "
        f"cosine ≥ {ENCODER_MIN_COSINE} — ADR-0016 as amended at "
        f"CP-55 and CP-57)")


def test_bound_is_the_measured_constant_at_the_default_model():
    """The default path is unchanged by CP-57: at 384 dims the transposed
    bound IS the CP-55 constant, bit for bit — and elsewhere it scales as
    the component magnitude does."""
    assert encoder_max_abs_delta(MEASURED_DIMENSION) == ENCODER_MAX_ABS_DELTA
    assert encoder_max_abs_delta(4 * MEASURED_DIMENSION) == pytest.approx(
        ENCODER_MAX_ABS_DELTA / 2)


def test_stored_vectors_are_the_pinned_encoders(built_state):
    """Stored Chroma vectors are the configured encoder's output for the
    same chunk texts, to within the CP-55 bound — Chroma never embedded
    anything. The hazard is silent: Chroma's default EF (attached by
    get_collection's default parameter) is a MiniLM at the default model's
    384 dims, so under the default model a substitution would produce
    plausible scores, not errors; the bound is set so every measured row
    of that substitution fails it. The shape is the MODEL's dimension —
    384 only because the configured model is the default one. The
    re-encode is cut into the builder's own batches (CP-77): which texts
    share an encode call moves a short chunk's last bits by up to
    1.4e-07 — above the bound, at the substitution floor — so a
    whole-collection re-encode is the wrong reference above
    ADD_BATCH_SIZE; at case_0001's 51 chunks the two are one call."""
    index = built_state.cases["case_0001"]
    assert built_state.config.embedding.model == MEASURED_MODEL
    assert built_state.encoder.dimension == MEASURED_DIMENSION
    texts = [c.text for c in index.chunks]
    ours = np.concatenate([
        built_state.encoder.encode_corpus(texts[lo:hi])
        for lo, hi in batch_spans(built_state._client(), len(texts))])
    for row in (0, len(index.chunks) // 2, len(index.chunks) - 1):
        chunk = index.chunks[row]
        got = index.collection.get(
            ids=[f"p{chunk.page:04d}c{chunk.chunk_idx:04d}"],
            include=["embeddings"])
        stored = np.asarray(got["embeddings"][0], dtype=np.float32)
        assert stored.shape == (built_state.encoder.dimension,)
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
    with pytest.raises(Exception, match="pinned encoder configured at"):
        collection.query(query_texts=["probe"], n_results=1)


# -- CP-57: the model follows the config; the store knows who built it ------

def test_store_records_the_embedder_identity(built_state, shared_dirs):
    """fingerprint.json carries the store's identity — model, revision and
    the dimension the model turned out to have — next to the fingerprint
    (the pins-document shape: identity beside the artifact); /health says
    the same once the model is loaded."""
    doc = json.loads((shared_dirs["index"] / "fingerprint.json").read_text())
    assert doc["embedding"] == {"model": DEFAULT_MODEL, "revision": REVISION,
                                "dimension": MEASURED_DIMENSION}
    assert read_store_identity(shared_dirs["index"]) == doc["embedding"]
    assert built_state.encoder.identity() == doc["embedding"]
    assert built_state.health()["embedding"] == doc["embedding"]


@pytest.mark.parametrize("rebuild", ["if-stale", "never"])
def test_model_change_against_existing_store_is_refused(
        built_state, shared_dirs, tmp_path_factory, rebuild):
    """A store built by one model, served under another, is CP-15's phantom
    store in a different hat — plausible scores, nothing saying so. The
    service REFUSES (it does not rebuild over the store: a model change is
    a re-pin, and re-embedding a production corpus is asked for
    explicitly), before the new model is even loaded, naming both models
    and the fix."""
    root = tmp_path_factory.mktemp(f"model-change-{rebuild}")
    shutil.copytree(shared_dirs["index"], root / "index")
    config_path = write_config(
        root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", rebuild=rebuild,
        model=SECOND_MODEL, revision=SECOND_REVISION,
        max_tokens=SECOND_MAX_TOKENS, overlap=SECOND_OVERLAP)
    state = make_state(config_path)
    assert state.status == "error"
    assert state.error.startswith("StoreMismatchError: EMBEDDING MODEL "
                                  "MISMATCH — refusing to serve"), state.error
    for needle in (DEFAULT_MODEL, REVISION, "384 dims", SECOND_MODEL,
                   SECOND_REVISION, "index.rebuild: always", "CP-57"):
        assert needle in state.error, (needle, state.error)
    assert state.encoder.loaded_dimension is None, (
        "the refusal must land before the model loads")
    assert state.cases == {} and state.decisions is None
    # The store is untouched: still the default model's, still loadable.
    assert read_store_identity(root / "index")["model"] == DEFAULT_MODEL
    restored = make_state(write_config(
        root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", rebuild=rebuild, name="restored.yaml"),
        encoder=built_state.encoder)
    assert restored.status == "ready", restored.error
    assert restored.reused_index is True


def test_rebuild_always_is_the_explicit_re_embed(built_state, shared_dirs,
                                                 tmp_path_factory):
    """index.rebuild: always is the operator's stated ask to re-embed under
    the configured model — it skips the identity gate, rebuilds, and the
    store's identity becomes the new model's. (case_0003 only: the second
    model is real and this re-embeds.)"""
    root = tmp_path_factory.mktemp("rebuild-always")
    seed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index"), encoder=built_state.encoder)
    assert seed.status == "ready", seed.error
    assert read_store_identity(root / "index")["model"] == DEFAULT_MODEL
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", rebuild="always", model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP, name="second.yaml"))
    assert state.status == "ready", state.error
    assert state.reused_index is False
    assert read_store_identity(root / "index") == {
        "model": SECOND_MODEL, "revision": SECOND_REVISION,
        "dimension": SECOND_DIMENSION}


@pytest.fixture(scope="module")
def second_model_state(tmp_path_factory, shared_dirs):
    """A fresh store under the second model over case_0001 — 768 dims, a
    100-token window, chunking fitted to it. The CP-57 proof that the
    service starts, indexes and serves under a model that is not MiniLM."""
    root = tmp_path_factory.mktemp("second-model")
    config_path = write_config(
        root, repos=["case_0001"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP)
    state = make_state(config_path)
    assert state.status == "ready", state.error
    assert state.reused_index is False
    return state, root


def test_second_model_indexes_and_the_oracle_passes(second_model_state):
    """Under the second model: the dimension is the MODEL's (768, read off
    the model — nowhere is 384 assumed), the store records that model, the
    oracle holds at the transposed bound, Chroma's text ops stay refused,
    a 384-dim vector (the shape of MiniLM and of Chroma's default EF)
    cannot even enter the store, and the tools serve."""
    state, root = second_model_state
    assert state.encoder.dimension == SECOND_DIMENSION != MEASURED_DIMENSION
    assert read_store_identity(root / "index") == {
        "model": SECOND_MODEL, "revision": SECOND_REVISION,
        "dimension": SECOND_DIMENSION}
    assert state.health()["embedding"]["dimension"] == SECOND_DIMENSION

    index = state.cases["case_0001"]
    ours = state.encoder.encode_corpus([c.text for c in index.chunks])
    assert ours.shape == (len(index.chunks), SECOND_DIMENSION)
    for row in (0, len(index.chunks) // 2, len(index.chunks) - 1):
        chunk = index.chunks[row]
        cid = f"p{chunk.page:04d}c{chunk.chunk_idx:04d}"
        got = index.collection.get(ids=[cid], include=["embeddings"])
        stored = np.asarray(got["embeddings"][0], dtype=np.float32)
        assert stored.shape == (SECOND_DIMENSION,)
        assert_vector_is_the_pinned_encoders(cid, stored, ours[row])

    with pytest.raises(Exception, match="pinned encoder configured at"):
        index.collection.query(query_texts=["probe"], n_results=1)
    with pytest.raises(Exception, match=r"(?i)dimension"):
        index.collection.add(ids=["gsj-cp57-probe"],
                             embeddings=[np.zeros(MEASURED_DIMENSION,
                                                  dtype=np.float32)])
    assert index.collection.count() == len(index.chunks)

    vec, _ = state.encoder.encode_query("the sealed ledgers deposition")
    hits = index.search(vec, k=3, timestep=index.n_pages)
    assert hits and all(hit["file"] == f"md/page_{hit['page']:04d}.md"
                        for hit in hits)


def test_chunk_window_is_checked_against_the_model(built_state, shared_dirs,
                                                   second_model_state,
                                                   tmp_path_factory):
    """Chunking is model-dependent — the shipped 220 was sized for MiniLM's
    256-token window. A max_tokens the model cannot hold would be silently
    truncated at encode time (chunk tails unsearchable, nothing reporting
    it); it is refused at startup with both numbers named — under the
    default model at 255, and under the second model at the shipped 220
    against its 100-token window."""
    root = tmp_path_factory.mktemp("window")
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index-a", max_tokens=255, overlap=40),
        encoder=built_state.encoder)
    assert state.status == "error"
    assert state.error.startswith("EmbeddingModelError: chunking.max_tokens "
                                  "255 does not fit"), state.error
    for needle in (DEFAULT_MODEL, "256 tokens", "2 specials", "most 254"):
        assert needle in state.error, (needle, state.error)

    second, _ = second_model_state
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index-b", model=SECOND_MODEL,
        revision=SECOND_REVISION, name="second.yaml"),   # shipped 220/40
        encoder=second.encoder)
    assert state.status == "error"
    assert "chunking.max_tokens 220 does not fit" in state.error
    for needle in (SECOND_MODEL, "100 tokens", "most 98"):
        assert needle in state.error, (needle, state.error)


def test_forged_identity_is_caught_at_the_collection(
        built_state, second_model_state, shared_dirs, tmp_path_factory):
    """The belt under the braces: fingerprint.json forged to claim the
    default model (identity AND the fingerprint that model would compute)
    over a store whose vectors are the second model's 768-dim ones. The
    identity gate passes by construction; the collection's own stamp
    refuses at load naming the model that filled it — and with the stamp
    stripped, the width check refuses on its own. Chroma alone would have
    handed back the collection and failed at the first query."""
    second, root = second_model_state
    forged = tmp_path_factory.mktemp("forged")
    shutil.copytree(root / "index", forged / "index")
    # A refused store stays byte-untouched, orphans included (CP-77): the
    # reuse-path sweep runs only after the load's own checks pass.
    orphan = forged / "index" / "chroma" / "0f0f0f0f-0000-4000-8000-c0ffee000080"
    orphan.mkdir()
    (orphan / "header.bin").write_bytes(b"\0" * 100)
    config_path = write_config(
        forged, repos=["case_0001"], clone_cache_dir=shared_dirs["clones"],
        index_path=forged / "index", max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP)  # the default model; chunking as the store's
    config = load_config(config_path)
    sources = {"case_0001": SimpleNamespace(
        main_sha=second.cases["case_0001"].refs["main"])}
    expected = corpus_fingerprint(
        sources, config.embedding, config.chunking, config.decisions.seed,
        config.decisions.corpus_size)
    write_fingerprint(forged / "index", expected,
                      built_state.encoder.identity())   # the forgery
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "error"
    assert state.error.startswith("StoreMismatchError: case_0001: chroma "
                                  "collection was filled by "
                                  f"{SECOND_MODEL!r}"), state.error
    assert "index.rebuild: always" in state.error
    assert (orphan / "header.bin").exists(), "a refused store was swept"

    # Strip the stamp (an out-of-band store with none): the width alone.
    state._client().get_collection("case_0001").modify(
        metadata={"gsj_stripped": True})
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "error"
    assert state.error.startswith("StoreMismatchError: case_0001: chroma "
                                  "collection holds 768-dim vectors"), state.error
    assert "embeds at 384 dims" in state.error


def test_unresolvable_model_id_fails_at_startup_named(shared_dirs,
                                                      tmp_path_factory):
    """An id HuggingFace cannot resolve fails at STARTUP — the init thread,
    before any ingest — with the config key, the id, the revision and
    what to check named (CP-27's standard), never at the first query."""
    root = tmp_path_factory.mktemp("unresolvable")
    bogus = "sentence-transformers/no-such-model-gsj-cp57"
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", model=bogus, revision="0" * 40))
    assert state.status == "error"
    assert state.error.startswith(
        f"EmbeddingModelError: embedding.model {bogus!r} @ "
        f"embedding.revision {'0' * 40!r} could not be loaded"), state.error
    assert "HuggingFace" in state.error and "HF cache" in state.error
    assert state.progress == {"case_0003": {"done": False}}, (
        "nothing was ingested — the failure is at the model, first")


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


# -- CP-57 review: the four ways the gate could still be bypassed ------------

def test_collections_carry_the_identity_stamp(built_state, second_model_state):
    """The identity travels with the vectors, not only in the sidecar:
    every collection is created with the model that filled it as metadata,
    so a chroma/ directory copied out-of-band next to an unchanged
    fingerprint.json is still refused at load (test above)."""
    for state, model, revision, dimension in (
            (built_state, DEFAULT_MODEL, REVISION, MEASURED_DIMENSION),
            (second_model_state[0], SECOND_MODEL, SECOND_REVISION,
             SECOND_DIMENSION)):
        for collection in [c.collection for c in state.cases.values()] + [
                state.decisions.collection]:
            assert collection.metadata["gsj_model"] == model
            assert collection.metadata["gsj_revision"] == revision
            assert collection.metadata["gsj_dimension"] == dimension


def _strip_to_pre_cp57(index_root, chroma_client_state=None):
    """Rewrite fingerprint.json in the shape every pre-CP-57 store has —
    no `embedding` block — and, when a state is given, drop the collection
    stamps too (pre-CP-57 collections carried no metadata)."""
    doc = json.loads((index_root / "fingerprint.json").read_text())
    del doc["embedding"]
    (index_root / "fingerprint.json").write_text(json.dumps(doc))
    if chroma_client_state is not None:
        client = chroma_client_state._client()
        for collection in client.list_collections():
            collection.modify(metadata={"pre_cp57": True})


@pytest.mark.parametrize("rebuild", ["if-stale", "never"])
def test_pre_cp57_store_under_a_changed_model_is_refused(
        built_state, shared_dirs, tmp_path_factory, rebuild):
    """Every store that exists today (the H200's) has no identity record.
    Exactly one pin built those, so an absent record on an existing store
    is assumed to be that pin — and a changed model is REFUSED against it
    (the review's finding: without this it rebuilt over the store with a
    log line saying the opposite)."""
    root = tmp_path_factory.mktemp(f"pre-cp57-{rebuild}")
    seed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index"), encoder=built_state.encoder)
    assert seed.status == "ready", seed.error
    _strip_to_pre_cp57(root / "index", seed)
    assert read_store_identity(root / "index") is None
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", rebuild=rebuild, model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP, name="second.yaml"))
    assert state.status == "error"
    assert state.error.startswith("StoreMismatchError: EMBEDDING MODEL "
                                  "MISMATCH — refusing to serve"), state.error
    assert "assumed the pre-CP-57 pin" in state.error
    assert PRE_CP57_STORE_IDENTITY["model"] in state.error
    assert state.encoder.loaded_dimension is None
    # untouched: still the default model's 384-dim vectors
    peek = seed._client().get_collection("case_0003").get(
        limit=1, include=["embeddings"])
    assert len(peek["embeddings"][0]) == MEASURED_DIMENSION


def test_pre_cp57_store_under_its_own_model_is_reused_and_backfilled(
        built_state, shared_dirs, tmp_path_factory):
    """The same store under the pin that built it: fingerprint match, reused
    (never re-embedded), and the record it lacked is written. If the record
    CANNOT be written (a read-only fingerprint.json — a file another uid
    wrote), the store is still served with a warning: a good store is
    never re-embedded over a sidecar write (the review's finding)."""
    root = tmp_path_factory.mktemp("pre-cp57-same")
    seed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index"), encoder=built_state.encoder)
    assert seed.status == "ready", seed.error
    _strip_to_pre_cp57(root / "index", seed)

    record = root / "index" / "fingerprint.json"
    record.chmod(0o444)
    try:
        state = make_state(write_config(
            root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
            index_path=root / "index", name="ro.yaml"),
            encoder=built_state.encoder)
        assert state.status == "ready", state.error
        assert state.reused_index is True, "a good store was re-embedded"
        assert read_store_identity(root / "index") is None
    finally:
        record.chmod(0o644)

    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", name="rw.yaml"),
        encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.reused_index is True
    assert read_store_identity(root / "index") == built_state.encoder.identity()


def test_interrupted_rebuild_is_never_served(built_state, second_model_state,
                                             shared_dirs, tmp_path_factory,
                                             monkeypatch):
    """A `rebuild: always` re-pin killed after the collections are
    re-embedded but before the final record: the record was written FIRST
    (the new model's identity, no fingerprint), so a rollback to the old
    model is refused by name and a restart under the new model rebuilds —
    never `ready` over another model's vectors (the review's reproduction:
    without this, a same-width re-pin rolled back served model B's vectors
    under model A with `index_reused: true`)."""
    root = tmp_path_factory.mktemp("interrupted")
    seed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index"), encoder=built_state.encoder)
    assert seed.status == "ready", seed.error

    def die(*args, **kwargs):
        raise RuntimeError("simulated kill after the case collections")
    monkeypatch.setattr(state_module, "save_decisions_index", die)
    killed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", rebuild="always", model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP, name="repin.yaml"),
        encoder=second_model_state[0].encoder)
    assert killed.status == "error" and "simulated kill" in killed.error
    monkeypatch.undo()
    assert read_fingerprint(root / "index") is None
    assert read_store_identity(root / "index")["model"] == SECOND_MODEL

    rollback = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", name="rollback.yaml"),
        encoder=built_state.encoder)
    assert rollback.status == "error"
    assert rollback.error.startswith("StoreMismatchError: EMBEDDING MODEL "
                                     "MISMATCH"), rollback.error
    assert SECOND_MODEL in rollback.error

    resumed = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=SECOND_MAX_TOKENS,
        overlap=SECOND_OVERLAP, name="resume.yaml"),
        encoder=second_model_state[0].encoder)
    assert resumed.status == "ready", resumed.error
    assert resumed.reused_index is False
    assert read_store_identity(root / "index") == {
        "model": SECOND_MODEL, "revision": SECOND_REVISION,
        "dimension": SECOND_DIMENSION}


def test_chunks_that_retokenize_past_the_window_are_refused(
        second_model_state, shared_dirs, tmp_path_factory):
    """The static window check is necessary, not sufficient: a chunk is a
    character slice that re-tokenizes a few tokens longer than the window
    it was cut from. At the boundary the static check admits (98 under a
    100-token window) real staging chunks overflow by one and would be
    truncated silently at encode time — measured after ingest, refused
    naming the count and the worst chunk (the review's finding). 96 fits."""
    second, _ = second_model_state
    room = second.encoder.max_seq_length - second.encoder.special_tokens
    assert room == 98
    root = tmp_path_factory.mktemp("retokenize")
    state = make_state(write_config(
        root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", model=SECOND_MODEL,
        revision=SECOND_REVISION, max_tokens=room, overlap=SECOND_OVERLAP),
        encoder=second.encoder)
    assert state.status == "error"
    assert state.error.startswith("EmbeddingModelError: case_000"), state.error
    assert "re-tokenize past" in state.error and "100-token window" in state.error
    assert "truncated silently" in state.error


# -- CP-77: the add ceiling, the batch, the orphans (wishlist 66) -----------

def _hnsw_dirs(index_root) -> set[str]:
    return {p.name for p in (index_root / "chroma").iterdir() if p.is_dir()}


def _segment_rows(index_root) -> set[str]:
    import sqlite3
    with sqlite3.connect(index_root / "chroma" / "chroma.sqlite3") as con:
        return {row[0] for row in con.execute("SELECT id FROM segments")}


def test_chromas_add_ceiling_is_a_count_and_the_batch_sits_under_it(tmp_path):
    """The pinned chroma refuses one add above 5,461 items, and the ceiling
    is a COUNT: 5,461 passes with 12 metadata keys per record, 5,462 fails
    with none — the shape CP-77 measured (0/1/12/40/120 keys, venv and
    Linux image alike; wishlist 66). The number is 32766 // 6 — the Rust
    bindings' SQLite variable limit over six variables per record.
    ADD_BATCH_SIZE sits at least 5x under it, so a chroma bump that moves
    the ceiling fails here by design; batch_spans cuts 0, 51 and 2,500
    items into no span, one, and 1000/1000/500."""
    client = index_module.chroma_client(tmp_path)
    ceiling = client.get_max_batch_size()
    assert ceiling == 5461 == 32766 // 6, (
        "the pinned chroma's ceiling moved — re-argue ADD_BATCH_SIZE")
    assert ADD_BATCH_SIZE * 5 <= ceiling
    assert batch_spans(client, 0) == []
    assert batch_spans(client, 51) == [(0, 51)]
    assert batch_spans(client, 2500) == [(0, 1000), (1000, 2000), (2000, 2500)]
    collection = client.create_collection(
        "ceiling", configuration={"hnsw": {"space": "cosine"}},
        embedding_function=index_module._NoTextOps())
    unit = [1.0] + [0.0] * 7
    collection.add(ids=[f"i{n}" for n in range(ceiling)],
                   embeddings=[unit] * ceiling,
                   metadatas=[{f"k{k:02d}": (f"v{k}" if k % 2 else n + k)
                               for k in range(12)} for n in range(ceiling)])
    assert collection.count() == ceiling
    with pytest.raises(Exception) as excinfo:
        collection.add(ids=[f"j{n}" for n in range(ceiling + 1)],
                       embeddings=[unit] * (ceiling + 1))
    assert (f"Batch size of {ceiling + 1} is greater than max batch size "
            f"of {ceiling}") in str(excinfo.value)
    assert collection.count() == ceiling


def test_batched_build_serves_what_a_single_add_served(
        built_state, shared_dirs, tmp_path_factory, monkeypatch, caplog):
    """ADD_BATCH_SIZE forced to 7, so every collection is filled by several
    adds: the store must be the one a single add built — the same counts,
    byte-identical results at tool level AND raw chunk level (the A-25
    canary's shape, applied to insertion order; a two-builds comparison,
    which A-25 measured to hold at 213 chunks and not at the chunk tail
    of 19,215 — this test is pinned to the staging scale) — and the build
    progress must have walked every batch of every collection, visible in
    /health (with state "indexing") and as one INFO line per batch while
    it ran, and gone from /health once ready. The encoder is pinned to
    one text per call for BOTH builds, because the vectors' last bits
    depend on which texts share an encode call (measured at CP-77: the
    30 decisions encoded in sevens differ from one call by max|Δ|
    9.7e-08, full-window 220-token chunks by 0, page-tail chunks by up to
    1.4e-07) — that is the encode's property, ADD_BATCH_SIZE joins
    embedding.batch_size in it, and this test isolates the ADD."""
    real = built_state.encoder.encode_corpus
    monkeypatch.setattr(built_state.encoder, "encode_corpus",
                        lambda texts: np.stack([real([t])[0] for t in texts]))
    single_root = tmp_path_factory.mktemp("single-add")
    single = make_state(write_config(
        single_root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=single_root / "index"), encoder=built_state.encoder)
    assert single.status == "ready", single.error

    monkeypatch.setattr(index_module, "ADD_BATCH_SIZE", 7)
    root = tmp_path_factory.mktemp("batched")
    state = state_module.AppState(load_config(write_config(
        root, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index")))
    state.encoder = built_state.encoder
    seen: list = []
    report = state._on_batch

    def spy(*args):
        report(*args)
        health = state.health()
        seen.append((args, health.get("build"), health["state"]))
    state._on_batch = spy
    caplog.set_level(logging.INFO, logger="gsj_mcp_service")
    state.initialize()
    assert state.status == "ready", state.error
    assert state.reused_index is False
    assert "build" not in state.health()

    walked: dict[str, list] = {}
    for (name, done, total, batch, batches), snapshot, status in seen:
        walked.setdefault(name, []).append((done, total, batch, batches))
        assert status == "indexing"
        assert snapshot == {"collection": name, "vectors": done,
                            "total": total, "batch": batch,
                            "batches": batches}
        assert (f"{name}: {done}/{total} vectors embedded and added "
                f"(batch {batch}/{batches})") in caplog.messages
    assert set(walked) == set(ALL_REPOS) | {"decisions"}
    for name, rows in walked.items():
        total = rows[0][1]
        n = math.ceil(total / 7)
        assert n >= 5, (name, total)
        assert [r[2] for r in rows] == list(range(1, n + 1))
        assert rows[-1] == (total, total, n, n)
    for case_id in ALL_REPOS:
        assert (state.cases[case_id].collection.count()
                == len(built_state.cases[case_id].chunks)
                == single.cases[case_id].collection.count())
    assert state.decisions.collection.count() == 30

    probes = [("case_0001", 12, "the sealed ledgers were moved to the antechamber"),
              ("case_0002", 22, "the warehouse ledger and invoices"),
              ("case_0003", 9, "deposition slip concerning the sealed ledgers")]
    for case_id, timestep, query in probes:
        vec, _ = built_state.encoder.encode_query(query)
        ours = state.cases[case_id].search(vec, k=10, timestep=timestep)
        theirs = single.cases[case_id].search(vec, k=10, timestep=timestep)
        assert ours and canonical(ours) == canonical(theirs)
        candidates = len(chunk_ids_within(built_state.cases[case_id], timestep))
        raw = [index.collection.query(
            query_embeddings=[vec], n_results=candidates,
            where={"page": {"$lte": timestep}}, include=["distances"])
            for index in (state.cases[case_id], single.cases[case_id])]
        assert raw[0]["ids"] == raw[1]["ids"]
        assert [repr(d) for d in raw[0]["distances"][0]] == \
            [repr(d) for d in raw[1]["distances"][0]]
    vec, _ = built_state.encoder.encode_query(
        "warehouse lease counterclaim dismissed")
    assert canonical(state.decisions.search(vec, k=10)) == \
        canonical(single.decisions.search(vec, k=10))


def test_a_build_above_the_ceiling(built_state, shared_dirs, tmp_path_factory):
    """The decisions builder past 5,461 items — 6,000, above the ceiling
    the pre-CP-77 single add hit (the test above): it builds, records,
    serves 20 sorted distinct hits, and a fresh start reuses the store and
    serves the same bytes."""
    root = tmp_path_factory.mktemp("above-ceiling")
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", decisions_size=6000),
        encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.reused_index is False
    assert (state.decisions.collection.count() == 6000
            == len(state.decisions.corpus))
    assert state.health()["decisions"] == 6000
    vec, _ = built_state.encoder.encode_query(
        "AZ-2021-OLG-B-1 salvage award appeal")
    hits = state.decisions.search(vec, k=20)
    assert len(hits) == 20
    assert hits == sorted(hits, key=lambda h: (-h["score"], h["decision_id"]))
    assert len({h["decision_id"] for h in hits}) == 20

    again = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", decisions_size=6000, name="again.yaml"),
        encoder=built_state.encoder)
    assert again.status == "ready", again.error
    assert again.reused_index is True
    assert canonical(again.decisions.search(vec, k=20)) == canonical(hits)


def test_a_kill_between_batches_is_never_served(
        built_state, shared_dirs, tmp_path_factory, monkeypatch):
    """A build killed between two add batches (ADD_BATCH_SIZE forced to 7,
    the encoder dying on its third call — the store then holds a
    half-filled collection and no sidecar): CP-57's record, written before
    the first drop, has no fingerprint, so the next start under rebuild:
    never refuses (missing) and under if-stale REBUILDS — the partial
    store is never ready, and /health keeps the last batch that landed
    (2/7, 14 of 43) so the failure names where it stopped. Batching makes
    this kill likelier, not the outcome different."""
    monkeypatch.setattr(index_module, "ADD_BATCH_SIZE", 7)
    root = tmp_path_factory.mktemp("killed-batch")
    real = built_state.encoder.encode_corpus
    calls = {"n": 0}

    def dying(texts):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated kill between add batches")
        return real(texts)
    monkeypatch.setattr(built_state.encoder, "encode_corpus", dying)

    def config(name, **overrides):
        return write_config(root, repos=["case_0003"],
                            clone_cache_dir=shared_dirs["clones"],
                            index_path=root / "index", name=name, **overrides)
    killed = make_state(config("kill.yaml"), encoder=built_state.encoder)
    assert killed.status == "error" and "simulated kill" in killed.error
    assert killed.build_progress == {"collection": "case_0003", "vectors": 14,
                                     "total": 43, "batch": 2, "batches": 7}
    assert killed.health()["build"] == killed.build_progress
    monkeypatch.undo()
    assert read_fingerprint(root / "index") is None
    assert read_store_identity(root / "index") == built_state.encoder.identity()
    assert not (root / "index" / "case_0003" / "chunks.json").exists()
    assert killed._client().get_collection("case_0003").count() == 14

    refused = make_state(config("never.yaml", rebuild="never"),
                         encoder=built_state.encoder)
    assert refused.status == "error"
    assert refused.error.startswith(
        "IngestError: index.rebuild=never but the stored index is missing")
    assert refused.cases == {} and refused.decisions is None

    rebuilt = make_state(config("stale.yaml"), encoder=built_state.encoder)
    assert rebuilt.status == "ready", rebuilt.error
    assert rebuilt.reused_index is False
    assert rebuilt.cases["case_0003"].collection.count() == 43
    vec, _ = built_state.encoder.encode_query(
        "deposition slip concerning the sealed ledgers")
    assert canonical(rebuilt.cases["case_0003"].search(vec, k=10, timestep=9)) \
        == canonical(built_state.cases["case_0003"].search(vec, k=10, timestep=9))
    assert _hnsw_dirs(root / "index") <= _segment_rows(root / "index")
    assert len(_hnsw_dirs(root / "index")) == 2


def test_orphaned_hnsw_directories_are_swept(built_state, shared_dirs,
                                             tmp_path_factory):
    """chroma 1.5.9 leaves a dropped collection's HNSW directory behind in
    every case measured (same process, fresh process, opened first), so
    every rebuild used to leak one directory per collection — 39 in
    estate/runs/cp73 (wishlist 66b). Now a rebuild removes the dropped
    collection's directory and a start sweeps what earlier rebuilds left,
    by the one rule the store supports: a directory no segment row names.
    What the sweep refuses: a live directory, a directory that is not a
    segment uuid, a stray file, a symlink wearing a segment's name, an
    entry it cannot remove (skipped with its reason, the start still
    ready; the read-only leg holds for a non-root uid — CI's runner, the
    image's 1000) — and everything when the system database cannot be
    read."""
    root = tmp_path_factory.mktemp("orphans")

    def config(name, **overrides):
        return write_config(root, repos=["case_0003"],
                            clone_cache_dir=shared_dirs["clones"],
                            index_path=root / "index", name=name, **overrides)
    seed = make_state(config("seed.yaml"), encoder=built_state.encoder)
    assert seed.status == "ready", seed.error
    first = _hnsw_dirs(root / "index")
    assert len(first) == 2 and first <= _segment_rows(root / "index")

    # a rebuild: the two dropped directories go, the two new ones stay
    rebuilt = make_state(config("always.yaml", rebuild="always"),
                         encoder=built_state.encoder)
    assert rebuilt.status == "ready", rebuilt.error
    second = _hnsw_dirs(root / "index")
    assert len(second) == 2 and second.isdisjoint(first)
    assert second <= _segment_rows(root / "index")

    # planted: an orphan (a segment-shaped name no row names), a directory
    # that is not a segment, a stray file
    chroma = root / "index" / "chroma"
    orphan = chroma / "0f0f0f0f-0000-4000-8000-c0ffee000077"
    orphan.mkdir()
    (orphan / "header.bin").write_bytes(b"\0" * 100)
    (chroma / "not-a-segment").mkdir()
    (chroma / "not-a-segment" / "keep").write_text("x")
    (chroma / "stray.txt").write_text("x")

    # and two the sweep must leave alone without stopping the start: an
    # orphan the process cannot remove (another uid's directory under a
    # bind mount, here a read-only one holding a file) and a symlink that
    # wears a segment's name (rmtree refuses symlinks; nothing of chroma's
    # is one)
    stuck = chroma / "0f0f0f0f-0000-4000-8000-c0ffee000078"
    stuck.mkdir()
    (stuck / "header.bin").write_bytes(b"\0" * 100)
    stuck.chmod(0o555)
    link = chroma / "0f0f0f0f-0000-4000-8000-c0ffee000079"
    link.symlink_to(chroma / "not-a-segment")

    try:
        reused = make_state(config("reuse.yaml"), encoder=built_state.encoder)
        assert reused.status == "ready", reused.error
        assert reused.reused_index is True
        assert not orphan.exists()
        assert stuck.is_dir() and (stuck / "header.bin").exists()
        assert link.is_symlink() and (chroma / "not-a-segment" / "keep").exists()
        assert (chroma / "stray.txt").exists()
        assert _hnsw_dirs(root / "index") == second | {
            "not-a-segment", stuck.name, link.name}
    finally:
        stuck.chmod(0o755)
    vec, _ = built_state.encoder.encode_query(
        "deposition slip concerning the sealed ledgers")
    assert reused.cases["case_0003"].search(vec, k=3, timestep=9)

    # the refusal: no readable system database ⇒ nothing is deleted
    blind = tmp_path_factory.mktemp("blind")
    planted = blind / "0f0f0f0f-0000-4000-8000-c0ffee000078"
    planted.mkdir()
    fake_client = SimpleNamespace(get_settings=lambda: SimpleNamespace(
        persist_directory=str(blind)))
    assert sweep_orphans(fake_client) == []
    assert planted.exists()
