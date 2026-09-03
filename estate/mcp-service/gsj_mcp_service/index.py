"""Per-case vector index — ChromaDB collections, cutoff-filter-first.

One collection per case over the FULL document (never per timestep); the
cutoff is applied as a metadata PRE-filter (``where: page <= T``) **before**
similarity ranking — a post-filter would change result counts and is the
classic leak shape (ADR-0040(d)); the pre-filter behavior is test-verified,
not assumed (ADR-0016). T comes from the verified token claims only.

Storage: ``<index.path>/chroma/`` (the Chroma persistent store — one
collection per case plus ``decisions``, cosine space) + the sidecars the
tools need regardless of the vector store: ``<case_id>/chunks.json``
(chunk metadata, page texts, refs, timesteps) and ``decisions/corpus.json``.
``<index.path>/fingerprint.json`` holds the corpus fingerprint that gates
reuse-vs-rebuild on restart (ADR-0040(c)); since CP-15 it carries the
Chroma version, so a Chroma upgrade rebuilds loudly instead of failing
silently (ADR-0016); since CP-57 it also carries the STORE'S IDENTITY —
``embedding: {model, revision, dimension}``, which model built these
vectors — read back at every startup and compared with the configured
model before anything loads (``state.py``): a mismatch is refused, not
rebuilt over. The same shape as the pins document recording the engine:
identity written next to the artifact it produced.

Embeddings are ALWAYS supplied explicitly by the configured encoder
(``embedding.py``; MiniLM by default, any model since CP-57); Chroma's own
embedding machinery is disabled by a raising embedding function on every
collection handle. With the model configurable there are two ways to be
wrong — Chroma's default EF (an fp32 ONNX export of the default MiniLM
checkpoint, 384 dims) substituted for the configured model, or a store
built by one configured model served under another — and both are
guarded: the first structurally (below) plus the oracle's bound, the
second by the identity record — written to ``fingerprint.json`` AND
stamped into every collection's metadata, so it travels with the vectors
themselves — and, as the belt under those braces, a load-time check that
each collection's stamp and its stored vectors' width are the loaded
model's (``_check_collection_identity``) — Chroma would otherwise accept
the collection and fail at the first query, or not at all.

Since CP-77 the builders never hand Chroma the whole corpus in one call:
``chromadb==1.5.9`` refuses a single ``add`` above 5,461 items (its Rust
bindings' bundled SQLite binds at most 32,766 variables and the write path
spends 6 per record — a COUNT, measured independent of the metadata width),
so both builders encode and add in ``ADD_BATCH_SIZE`` batches with a
progress callback per batch, and every rebuild sweeps the HNSW directories
Chroma leaves behind — ``delete_collection`` drops the segment rows and
never the directory (measured: same process, fresh process, opened first)
— by the one rule the store's own system database supports: a directory
no segment row names is unreachable by any Chroma code path and is removed
(``sweep_orphans``); everything else under ``chroma/`` is left alone.

Since CP-79 the ``decisions`` collection has two sources: a rii-dok v1
drop at ``decisions.path`` — parsed and cut into units by ``decisions.py``
per docs/decisions-surface.md (the Randnummer as the retrieval unit), each
unit split into pieces through the same token-window splitter the pages use
(``ingest.split_spans``; spec §6), best piece per unit at query time with a
fetch bounded by ``k`` (spec §8; ``DECISIONS_FETCH_PER_K``) — or, with no
path, the 30 synthetic decisions the pinned episodes saw, byte-unchanged.
The fingerprint gains a ``decisions_drop`` component only when a drop is
configured (a key present with None would move the hash — measured at
CP-76), and ``fingerprint.json`` records one fingerprint per collection so
a start rebuilds only the collections whose inputs moved: a decisions drop
never re-embeds the cases (wishlist 61).

Result shape (the compatibility requirement any future backend must keep —
G5's transcript backstop parses it via the library's
``extract_case_search_pages``): every ``search_case`` hit carries
``"page"`` (int) and ``"file"`` (``md/page_NNNN.md``). Ranking policy
stays ours — Chroma supplies candidate scoring only: ``score = 1 −
cosine_distance``, chunk scores aggregated to page level (max), top-k
pages score-descending, ties by page ascending, non-positive scores
dropped, full page text attached.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from .config import ChunkingConfig, EmbeddingConfig
from .decisions import SECTION_ORDER, SURFACE_VERSION, Drop
from .embedding import Encoder
from .ingest import CaseSource, Chunk, split_spans

INDEX_FORMAT = 2  # 1 = vectors.npy + numpy scan, retired at CP-15 (ADR-0016)
CHROMA_VERSION = chromadb.__version__

logger = logging.getLogger("gsj_mcp_service")

# The add batch (CP-77, wishlist 66a). chromadb 1.5.9 refuses one ``add``
# above 5,461 items: ``32766 // 6`` — the Rust bindings' bundled SQLite
# variable limit over the six variables its write path binds per record —
# reported by ``client.get_max_batch_size()`` and measured at CP-77 to be a
# count of items and nothing else (5,461 passes with 0, 1, 12 or 40
# metadata keys; 5,462 fails with 0, 1 or 40; identical in the venv and in
# the Linux image). 1,000 sits 5.46× under that: the margin is against the
# count MOVING — a chroma bump rebuilds the store loudly through the
# fingerprint but runs this same code — not against width, which was
# measured not to matter; and the batch is clamped at run time to what the
# client reports, so it can never exceed the ceiling of the host it runs
# on. Throughput is indifferent above ~100 (the embed dominates: ~91
# chunks/s single-threaded at 220 tokens), and one progress line per 1,000
# vectors is a readable cadence for a million-vector build. Every
# collection any estate has recorded fits in one batch (max 62 chunks, 30
# decisions), so their bytes are exactly what the single call wrote. Above
# it the batch decides which texts share an encode call, and the vectors'
# last bits depend on that (sentence-transformers length-sorts a call and
# pads per mini-batch): a change here owes an INDEX_FORMAT bump, the
# chunker's rule (ADR-0016 as amended at CP-57 and CP-77).
ADD_BATCH_SIZE = 1000

# The candidate fetch of the decisions surface (CP-79, spec §8.4): a
# function of ``k``, never of the corpus size — ``DECISIONS_FETCH_PER_K × k``
# pieces are fetched, aggregated best-piece-per-unit, and the top ``k``
# units returned. Why a multiple of k: a unit contributes as many pieces
# as its split produced (the longest Randnummer, 2,814 tokens, cuts into
# 16 at 220/40), so k units can hide behind many more pieces; gsj-next
# fetches 5·k. Why 200 and not 20: the number is a measurement, not a
# taste. Against an exact numpy scan over every stored vector of a
# 1,999-decision drop (43,760 units, 71,946 pieces; 60 queries, 52 of
# them sentence-sized slices of the drop's own units) the unbounded HNSW
# fetch is exact (recall 1.000 at k=5 and k=20), so what a bounded fetch
# loses is the graph's search beam — chroma's ``hnsw:ef_search`` is 100
# and ``n_results`` widens it — not the aggregation: 20·k gave recall
# 0.953 at k=5 (one query 0 of 5) and 0.984 at k=20; 100·k 0.993/0.998;
# 200·k 1.000 (60/60 queries, the exact order) at k=5 and 0.998 (min
# 0.95) at k=20; 400·k 1.000/0.999. So 200·k: 1,000 pieces at the default
# k, 4,000 at ``max_k`` 20 — under 0.2 s with metadatas, and 8× under the
# 32,763-result ceiling chroma's read path enforces on a metadata fetch
# (the write path's SQLite variable limit again, measured at CP-79).
# Recorded in wishlist 68 and A-25; ``tests/measure_decisions_recall.py``
# re-runs the measurement for any drop (a full 34k-file drop owes its
# own run). Not a config key: nothing on the wire can test it, and a knob
# without a measurement behind it is a guess.
DECISIONS_FETCH_PER_K = 200

# A persisted HNSW segment lives at ``<persist>/<segment uuid>/``.
_SEGMENT_DIR_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# progress(collection, vectors_done, vectors_total, batch, batches)
ProgressFn = Callable[[str, int, int, int, int], None]

# The one pin any store written before CP-57 was built by: the model id was
# the config default in every deployment and the revision the shipped one
# (the H200 estate's store, the CI stores, every recorded build). A store
# with no identity record is assumed to be this — so a changed model is
# refused against it rather than rebuilt over (CP-57 review) — and gets the
# record backfilled on its first matching reuse.
PRE_CP57_STORE_IDENTITY = {
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "dimension": 384,
}

_HNSW_COSINE = {"hnsw": {"space": "cosine"}}  # normalized vecs: score = 1 - d


class StoreMismatchError(Exception):
    """The stored index was built by a model other than the configured one
    (CP-57): the identity record disagrees, or the vectors' width is not the
    loaded model's. Refused loudly — never rebuilt over, never served."""


class _NoTextOps:
    """Refuses Chroma's text-side embedding paths. Without an explicit
    embedding function, ``get_collection``'s DEFAULT parameter attaches
    Chroma's bundled ONNX MiniLM — 384 dims, the default model's own width,
    so under the default model a stray text op would silently mix two
    implementations of the same checkpoint (ADR-0016); under any other
    configured model it would mix two unrelated models. Embeddings come
    only from the configured, revision-pinned encoder."""

    _MESSAGE = ("text ops are disabled on this collection — embeddings are "
                "supplied explicitly by the pinned encoder configured at "
                "embedding.model (embedding.py; ADR-0016)")

    def name(self) -> str:
        return "gsj-no-text-ops"

    def is_legacy(self) -> bool:
        return True  # persisted as legacy config — never rehydrated by chroma

    def __call__(self, input):  # noqa: A002 — chroma validates this signature
        raise RuntimeError(self._MESSAGE)

    def embed_query(self, input):  # noqa: A002
        raise RuntimeError(self._MESSAGE)

    def embed_documents(self, input):  # noqa: A002
        raise RuntimeError(self._MESSAGE)


def chroma_client(root: Path):
    """The persistent Chroma client at ``<index.path>/chroma``; telemetry
    off — the staging deployment runs fully offline."""
    return chromadb.PersistentClient(
        path=str(root / "chroma"),
        settings=Settings(anonymized_telemetry=False))


def evict_chroma_client_cache(root: Path) -> None:
    """Evict (and stop) the process-cached Chroma system for THIS store path,
    so the next client observes the real on-disk store. Chroma caches one
    System per path per process, which makes an out-of-band store
    replacement (``rm -rf <index.path>/chroma`` before ``/admin/reindex``)
    otherwise invisible — the running process would keep serving the
    unlinked inode and ``reindex`` would not be restart-equivalent
    (ADR-0016, the CP-15 review's phantom-store finding). Private API of
    the pinned ``chromadb==1.5.9``: the cache dict and the path-string
    identifier are ``SharedSystemClient``'s; eviction is scoped to this
    path only, never a global cache clear."""
    from chromadb.api.shared_system_client import SharedSystemClient
    identifier = str(root / "chroma")
    system = SharedSystemClient._identifier_to_system.pop(identifier, None)
    if system is not None:
        system.stop()


def drop_component(drop: Drop) -> dict:
    """The decisions drop's fingerprint component (CP-79): the drop's
    content hash (every kept file's name and bytes, in order), the surface
    version whose unit rule cut it, and the file count. It enters the
    fingerprint document only when ``decisions.path`` is set — a key
    present with ``None`` still moves the hash (measured at CP-76) — so
    every store built without a drop keeps its fingerprint byte-identical
    and nothing rebuilds on upgrade."""
    return {"sha256": drop.sha256, "surface_version": SURFACE_VERSION,
            "files": len(drop.decisions)}


def _digest(doc: dict) -> str:
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


# The encode composition every recorded store was built under (wishlist 69
# (c), decided at CP-79): ``embedding.batch_size`` shapes a collection's
# last bits above the smaller batch size (sentence-transformers pads per
# mini-batch — measured at CP-77), so it IS identity — but every store any
# estate holds was built at 32, so the component enters the hashed
# document only when the configured value differs: a store built at 32
# keeps its fingerprint byte for byte, a config that moves the value
# re-embeds (the bytes would differ), and the one estate that ever merged
# ``batch_size: 64`` over a 32-built store (cp73, CP-73) rebuilds once —
# correctly, its config and its bytes never agreed.
PINNED_ENCODE_BATCH_SIZE = 32


def _embedding_component(embedding: EmbeddingConfig) -> dict:
    doc = {"model": embedding.model, "revision": embedding.revision,
           "normalize": embedding.normalize}
    if embedding.batch_size != PINNED_ENCODE_BATCH_SIZE:
        doc["batch_size"] = embedding.batch_size
    return doc


def corpus_fingerprint(sources: dict[str, CaseSource],
                       embedding: EmbeddingConfig,
                       chunking: ChunkingConfig,
                       decisions_seed: int, decisions_size: int,
                       chroma_version: str = CHROMA_VERSION,
                       decisions_drop: dict | None = None) -> str:
    """sha256 over everything that determines index bytes: repo main SHAs,
    model + revision, chunking params, decisions corpus params, index
    format, and (since CP-15) the Chroma version — an upgrade that changes
    the on-disk format must rebuild loudly, never fail silently. Since
    CP-79 also the decisions drop's component (``drop_component``) and a
    non-default ``embedding.batch_size`` — each an ADDITIONAL key, present
    only when set, so the document a store built without a drop at the
    pinned batch size hashes is byte-identical to before."""
    doc = {
        "index_format": INDEX_FORMAT,
        "cases": {cid: src.main_sha for cid, src in sorted(sources.items())},
        "embedding": _embedding_component(embedding),
        "chunking": {"max_tokens": chunking.max_tokens,
                     "overlap": chunking.overlap,
                     "respect_page_boundaries": chunking.respect_page_boundaries},
        "decisions": {"seed": decisions_seed, "size": decisions_size},
        "chroma": {"version": chroma_version},
    }
    if decisions_drop is not None:
        doc["decisions_drop"] = decisions_drop
    return _digest(doc)


def collection_fingerprints(sources: dict[str, CaseSource],
                            embedding: EmbeddingConfig,
                            chunking: ChunkingConfig,
                            decisions_seed: int, decisions_size: int,
                            chroma_version: str = CHROMA_VERSION,
                            decisions_drop: dict | None = None) -> dict[str, str]:
    """One fingerprint per collection (CP-79, wishlist 61): each hashes
    only what determines THAT collection's bytes — a case's its own main
    SHA, the chunking, the model and the store format; the decisions
    collection's the drop component and the chunking (a drop is split),
    or the generator's seed and size (the 30 are not). Recorded beside
    the whole-store fingerprint so a start under ``if-stale`` rebuilds the
    collections whose inputs moved and loads the rest: a decisions drop
    never re-embeds the cases, a one-case edit never re-embeds the others.
    The whole-store fingerprint stays the reuse gate (a match means every
    collection matches and the case SET is the same)."""
    common = {
        "index_format": INDEX_FORMAT,
        "embedding": _embedding_component(embedding),
        "chroma": {"version": chroma_version},
    }
    chunk = {"max_tokens": chunking.max_tokens, "overlap": chunking.overlap,
             "respect_page_boundaries": chunking.respect_page_boundaries}
    out = {cid: _digest({**common, "chunking": chunk, "case": {cid: src.main_sha}})
           for cid, src in sorted(sources.items())}
    if decisions_drop is not None:
        out["decisions"] = _digest({**common, "chunking": chunk,
                                    "decisions_drop": decisions_drop})
    else:
        out["decisions"] = _digest({**common, "decisions": {
            "seed": decisions_seed, "size": decisions_size}})
    return out


def _chunk_id(chunk: Chunk) -> str:
    return f"p{chunk.page:04d}c{chunk.chunk_idx:04d}"


def _collection_stamp(identity: dict) -> dict:
    """The identity as collection metadata — next to the vectors themselves,
    so it survives an out-of-band copy of ``chroma/`` that the sidecar's
    record would not know about (CP-57 review)."""
    return {"gsj_model": identity["model"],
            "gsj_revision": identity["revision"],
            "gsj_dimension": int(identity["dimension"])}


def _persist_dir(client) -> Path:
    return Path(client.get_settings().persist_directory)


def _known_segments(client) -> set[str] | None:
    """Every segment id the store's system database records — read straight
    from ``chroma.sqlite3``'s ``segments`` table (``id, type, scope,
    collection``; the pinned 1.5.9 layout, the same private-format
    dependency ``evict_chroma_client_cache`` already takes), the one place
    Chroma writes which directories under the persist dir are its. None
    when the table cannot be read: then nothing is deleted."""
    path = _persist_dir(client) / "chroma.sqlite3"
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                                     uri=True)
    except sqlite3.Error as error:
        logger.warning("orphan sweep skipped — %s unreadable (%s)", path, error)
        return None
    try:
        return {row[0] for row in connection.execute("SELECT id FROM segments")}
    except sqlite3.Error as error:
        logger.warning("orphan sweep skipped — %s unreadable (%s)", path, error)
        return None
    finally:
        connection.close()


def sweep_orphans(client) -> list[tuple[str, int]]:
    """Remove every HNSW directory no segment row references (CP-77,
    wishlist 66b) and return ``[(directory, bytes)]``.

    What is safe to delete, argued: Chroma reaches a persisted HNSW index
    only through its segment row — the directory is named by the segment
    id and nothing else records the name — so a directory without a row
    cannot be opened, queried, or recovered by any Chroma path; it is
    dead weight the size of a collection. ``delete_collection`` (1.5.9,
    the Rust bindings) drops the rows and leaves the directory in every
    case measured. An interrupted rebuild is no exception in this store:
    CP-57's order writes the identity record with NO fingerprint before
    the first ``delete_collection``, so the old collection's rows are
    gone before its directory is orphaned and the store as a whole is
    refused-or-rebuilt on the next start, never served — the corpus in
    git is the source the rebuild regenerates it from, the orphan is not
    a copy anything can serve. What is refused: any directory a segment
    row names (live, or the half-filled one an interrupted add left —
    that collection's row exists and the next rebuild drops it properly),
    any name that is not a segment uuid, a symlink, every file, an entry
    the process cannot remove, and everything when the system database
    cannot be read. Two things it assumes, both the service's already:
    one writer per store (the known set is read once, before the loop —
    a second process filling a collection meanwhile is not a supported
    state; ``request_reindex`` serialises in-process), and that
    ``chroma.sqlite3`` and the directories beside it are one snapshot (a
    database restored alone over a newer tree names the newer directories
    as orphans; that restore is a re-embed, the corpus in git being the
    source — not a recoverable store)."""
    persist = _persist_dir(client)
    known = _known_segments(client)
    if known is None or not persist.is_dir():
        return []
    removed: list[tuple[str, int]] = []
    for entry in sorted(persist.iterdir()):
        if (entry.is_symlink() or not entry.is_dir() or entry.name in known
                or not _SEGMENT_DIR_RE.match(entry.name)):
            continue
        # One entry that cannot be removed (another uid's directory under
        # a bind mount, a file the process may not stat) is skipped with
        # its reason — an orphan is inert, and a sweep that cannot finish
        # must never stop a store that served before it existed.
        try:
            size = sum(f.stat().st_size for f in entry.rglob("*")
                       if f.is_file())
            shutil.rmtree(entry)
        except OSError as error:
            logger.warning("orphan sweep: %s left in place (%s)", entry.name,
                           error)
            continue
        removed.append((entry.name, size))
    return removed


def _recreate_collection(client, name: str, identity: dict):
    """The rebuild path: drop any existing collection, sweep the HNSW
    directory Chroma leaves behind it, create fresh — stamped with the
    model that is about to fill it."""
    try:
        client.delete_collection(name)
    except NotFoundError:
        pass
    else:
        removed = sweep_orphans(client)
        logger.info("%s: dropped for rebuild — %d HNSW director%s removed "
                    "(%d bytes)", name, len(removed),
                    "y" if len(removed) == 1 else "ies",
                    sum(size for _, size in removed))
    return client.create_collection(
        name, configuration=dict(_HNSW_COSINE),
        metadata=_collection_stamp(identity),
        embedding_function=_NoTextOps())


def batch_spans(client, total: int) -> list[tuple[int, int]]:
    """The ``[lo, hi)`` slices a build of ``total`` items encodes and adds,
    in order — ``ADD_BATCH_SIZE`` clamped to the ceiling the client
    reports. Exposed because the slices decide the vectors' last bits
    (which texts share an encode call), so anything that re-encodes a
    collection to compare against the store must cut the same way."""
    size = min(ADD_BATCH_SIZE, client.get_max_batch_size())
    return [(lo, min(lo + size, total)) for lo in range(0, total, size)]


def _add_batched(client, collection, encoder: Encoder, name: str,
                 texts: list[str], ids: list[str], metadatas: list[dict],
                 progress: ProgressFn | None) -> None:
    """Encode then add, one ``ADD_BATCH_SIZE`` batch at a time (clamped to
    the ceiling the client reports), calling ``progress`` after each —
    so a long build is visible while it runs and the corpus's vectors are
    never all in memory at once."""
    total = len(texts)
    spans = batch_spans(client, total)
    for number, (lo, hi) in enumerate(spans, 1):
        vectors = encoder.encode_corpus(texts[lo:hi])
        collection.add(ids=ids[lo:hi], embeddings=vectors,
                       metadatas=metadatas[lo:hi])
        if progress is not None:
            progress(name, hi, total, number, len(spans))


class CaseIndex:
    def __init__(self, case_id: str, collection, chunks: list[Chunk],
                 pages: dict[int, str], refs: dict[str, str],
                 timesteps: list[int]) -> None:
        self.case_id = case_id
        self.collection = collection
        self.chunks = chunks
        self.pages = pages
        self.refs = refs
        self.timesteps = timesteps
        self.n_pages = max(pages)
        self._pages_by_chunk = [c.page for c in chunks]

    def search(self, query_vec, k: int, timestep: int) -> list[dict]:
        """Constrain candidates to page <= timestep FIRST (Chroma ``where``
        pre-filter — test-verified), rank the filtered set by cosine;
        aggregate chunk scores to page level (max), return top-k pages as
        ``{"page", "file", "score", "text"}`` with full page text —
        score-descending, ties by page ascending, non-positive scores
        dropped. ``n_results`` is the WHOLE filtered candidate set, so the
        page aggregation sees every candidate's best chunk — parity with
        the exact scan this replaced at the frozen estate's scale (213
        chunks); measured ≈0.1% short at 19,215, a different tail per
        build (CP-77, wishlist 68); a larger corpus that needs a bounded
        fetch moves the approximation boundary and re-opens A-25
        (ADR-0016)."""
        candidates = sum(1 for page in self._pages_by_chunk
                         if page <= timestep)
        if candidates == 0:
            return []
        result = self.collection.query(
            query_embeddings=[query_vec], n_results=candidates,
            where={"page": {"$lte": timestep}},
            include=["metadatas", "distances"])
        best_by_page: dict[int, float] = {}
        for meta, distance in zip(result["metadatas"][0],
                                  result["distances"][0]):
            page = int(meta["page"])
            score = 1.0 - float(distance)
            if page not in best_by_page or score > best_by_page[page]:
                best_by_page[page] = score
        ranked = sorted(best_by_page.items(),
                        key=lambda item: (-item[1], item[0]))
        return [{"page": page, "file": f"md/page_{page:04d}.md",
                 "score": score, "text": self.pages[page]}
                for page, score in ranked[:k] if score > 0]


class DecisionsIndex:
    """Cutoff-exempt (ADR-0007(e)): ranks the full deterministic corpus —
    ``n_results`` is the whole corpus, tie-break by decision_id is ours.
    The no-path fallback since CP-79: its hits keep their level-0 shape
    (``{decision_id, court, year, score, text}`` — spec §7.6) inside the
    wrapper ``tools.py`` puts around both sources; ``index_commit`` is
    ``""`` (a synthetic corpus names no drop)."""

    kind = "synthetic"
    index_commit = ""

    def __init__(self, collection, corpus: list[dict]) -> None:
        self.collection = collection
        self.corpus = corpus
        self._by_id = {d["decision_id"]: d for d in corpus}
        self.n_decisions = len(corpus)

    def search(self, query_vec, k: int) -> list[dict]:
        result = self.collection.query(
            query_embeddings=[query_vec], n_results=len(self.corpus),
            include=["distances"])
        scored = [(1.0 - float(distance), self._by_id[decision_id])
                  for decision_id, distance in zip(result["ids"][0],
                                                   result["distances"][0])]
        ranked = sorted(scored,
                        key=lambda item: (-item[0], item[1]["decision_id"]))
        return [{"decision_id": d["decision_id"], "court": d["court"],
                 "year": d["year"], "score": float(score), "text": d["text"]}
                for score, d in ranked[:k] if score > 0]


class RiiDecisionsIndex:
    """The decisions surface at level 2 (CP-79, docs/decisions-surface.md):
    the unit of spec §4 is what a hit returns, the pieces of spec §6 are
    what is embedded, a unit's score is its best piece's (§8.1), hits are
    ordered by the total order of §8.2, the fetch is bounded by ``k``
    (§8.4). Cutoff-exempt like the synthetic corpus it replaces. The
    sidecar document holds every unit's text and its pieces' character
    spans, so a hit carries the whole unit (never a piece) and ``excerpt``
    is the best piece without re-splitting."""

    kind = "rii"

    def __init__(self, collection, doc: dict) -> None:
        self.collection = collection
        self.doc = doc
        self.decisions: list[dict] = doc["decisions"]
        self.drop: dict = doc["drop"]
        self._by_id = {d["decision_id"]: d for d in self.decisions}
        self.n_decisions = len(self.decisions)
        self.n_units = sum(len(d["units"]) for d in self.decisions)
        self.n_pieces = sum(len(u["pieces"]) for d in self.decisions
                            for u in d["units"])
        # what decision_stats aggregates: year and court per decision
        self.corpus = [{"decision_id": d["decision_id"], "court": d["court"],
                        "year": int(d["date"][:4])} for d in self.decisions]

    @property
    def index_commit(self) -> str:
        """The drop's content hash (spec §7.5) — the value the decisions
        lock will record once corpus-contract v3 lands."""
        return self.drop["sha256"]

    def search(self, query_vec, k: int, fetch: int | None = None) -> list[dict]:
        """Top-``k`` units for the query: fetch ``DECISIONS_FETCH_PER_K × k``
        pieces (``fetch`` overrides the bound — for the recall measurement
        only), keep each unit's best piece (§8.1), order per §8.2 — score
        descending, then ``decision_id``, section in DTD order, ``rn`` with
        null first, document order — drop non-positive scores, return the
        whole unit's text with the best piece as ``excerpt``."""
        if self.n_pieces == 0:
            return []
        wanted = DECISIONS_FETCH_PER_K * k if fetch is None else fetch
        result = self.collection.query(
            query_embeddings=[query_vec],
            n_results=max(1, min(self.n_pieces, wanted)),
            include=["metadatas", "distances"])
        best: dict[tuple[str, int], tuple[float, int]] = {}
        for meta, distance in zip(result["metadatas"][0],
                                  result["distances"][0]):
            key = (str(meta["doknr"]), int(meta["unit"]))
            score = 1.0 - float(distance)
            if key not in best or score > best[key][0]:
                best[key] = (score, int(meta["piece"]))

        def order(item):
            (doknr, ordinal), (score, _) = item
            unit = self._by_id[doknr]["units"][ordinal]
            return (-score, doknr, SECTION_ORDER[unit["section"]],
                    unit["rn"] is not None, unit["rn"] or 0, ordinal)

        hits: list[dict] = []
        for (doknr, ordinal), (score, piece) in sorted(best.items(), key=order)[:k]:
            if score <= 0:
                break
            decision = self._by_id[doknr]
            unit = decision["units"][ordinal]
            hit = {"decision_id": decision["decision_id"],
                   "aktenzeichen": decision["aktenzeichen"]}
            if decision.get("ecli"):
                hit["ecli"] = decision["ecli"]
            begin, end = unit["pieces"][piece]
            hit.update({"court": decision["court"], "date": decision["date"],
                        "doktyp": decision["doktyp"], "rn": unit["rn"],
                        "section": unit["section"], "score": float(score),
                        "text": unit["text"],
                        "excerpt": unit["text"][begin:end]})
            hits.append(hit)
        return hits


def rii_pieces(drop: Drop, tokenizer, chunking: ChunkingConfig):
    """Every unit of the drop split into pieces (spec §6): verbatim
    contiguous slices that cover the unit and never span two, each
    carrying its unit's identity and ordinal. Yields the sidecar's per-
    decision entries and, flat, the piece texts, ids and metadatas.
    Piece ids follow the spec's reference scheme —
    ``<doknr>:rn:<N>:p<i>`` / ``<doknr>:<section>:p<i>``, a repeated
    (doknr, number) taking ``:d2``, ``:d3`` … before ``:p<i>`` — and the
    metadata's ``unit`` ordinal is what a hit resolves through."""
    entries: list[dict] = []
    texts: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []
    for decision in drop.decisions:
        seen: dict[str, int] = {}
        units: list[dict] = []
        for ordinal, unit in enumerate(decision.units):
            spans = split_spans(tokenizer, unit.text, chunking)
            # spec §6 constraint 2, at the edges: the tokenizer's normalizer
            # gives no offset to a format character (U+00AD, U+200B) that
            # opens or closes a unit, so the first and last piece are
            # widened to the unit's bounds — still verbatim, still
            # contiguous; one unit of the March 2026 drop ends with a soft
            # hyphen (CP-79 review)
            spans[0] = (0, spans[0][1])
            spans[-1] = (spans[-1][0], len(unit.text))
            prefix = (f"{decision.decision_id}:rn:{unit.rn}" if unit.rn is not None
                      else f"{decision.decision_id}:{unit.section}")
            seen[prefix] = seen.get(prefix, 0) + 1
            if seen[prefix] > 1:
                prefix += f":d{seen[prefix]}"
            for piece, (begin, end) in enumerate(spans):
                texts.append(unit.text[begin:end])
                ids.append(f"{prefix}:p{piece}")
                meta = {"doknr": decision.decision_id, "unit": ordinal,
                        "piece": piece, "section": unit.section}
                if unit.rn is not None:
                    meta["rn"] = unit.rn
                metadatas.append(meta)
            units.append({"section": unit.section, "rn": unit.rn,
                          "text": unit.text,
                          "pieces": [[begin, end] for begin, end in spans]})
        entry = decision.header()
        entry["units"] = units
        entry["anomalies"] = list(decision.anomalies)
        entries.append(entry)
    return entries, texts, ids, metadatas


def build_rii_decisions_index(client, encoder: Encoder, drop: Drop,
                              chunking: ChunkingConfig,
                              progress: ProgressFn | None = None) -> RiiDecisionsIndex:
    """The drop → units → pieces → the ``decisions`` collection, batched
    (CP-77's path — a real drop is far above chroma's single-add ceiling),
    every piece window-checked against the model first (the refusal that
    stops a silently truncated store, CP-57)."""
    entries, texts, ids, metadatas = rii_pieces(drop, encoder.tokenizer,
                                                chunking)
    encoder.check_chunks_fit("decisions", texts)
    collection = _recreate_collection(client, "decisions", encoder.identity())
    _add_batched(client, collection, encoder, "decisions", texts=texts,
                 ids=ids, metadatas=metadatas, progress=progress)
    doc = {"source": "rii", "surface_version": SURFACE_VERSION,
           "drop": {"path": drop.path, "sha256": drop.sha256,
                    "files": len(drop.decisions),
                    "skipped": [list(item) for item in drop.skipped]},
           "decisions": entries}
    return RiiDecisionsIndex(collection, doc)


def build_case_index(client, encoder: Encoder, source: CaseSource,
                     progress: ProgressFn | None = None) -> CaseIndex:
    collection = _recreate_collection(client, source.case_id,
                                      encoder.identity())
    _add_batched(
        client, collection, encoder, source.case_id,
        texts=[c.text for c in source.chunks],
        ids=[_chunk_id(c) for c in source.chunks],
        metadatas=[{"case_id": c.case_id, "page": c.page, "file": c.file,
                    "chunk_idx": c.chunk_idx} for c in source.chunks],
        progress=progress)
    return CaseIndex(source.case_id, collection, source.chunks, source.pages,
                     source.refs, source.timesteps)


def save_case_index(root: Path, index: CaseIndex) -> None:
    """The sidecar the tools need regardless of the vector store; the
    vectors themselves live in the Chroma store (ADR-0016)."""
    case_dir = root / index.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "chunks.json").write_text(json.dumps({
        "case_id": index.case_id,
        "refs": index.refs,
        "timesteps": index.timesteps,
        "chunks": [asdict(c) for c in index.chunks],
        "pages": {str(p): t for p, t in sorted(index.pages.items())},
    }, ensure_ascii=False))


def _check_collection_identity(collection, name: str, identity: dict) -> None:
    """The collection against the loaded model (CP-57): its stamp — which
    model filled it; absent only on a collection written before CP-57,
    whose fingerprint match stands in — and one stored vector's width.
    Chroma fixes a collection's dimension at the first add and would accept
    the handle, then raise at the first query; both checks move that to
    startup and name it as what it is: a store built by another model."""
    stamp = collection.metadata or {}
    if "gsj_model" in stamp and (
            stamp.get("gsj_model") != identity["model"]
            or stamp.get("gsj_revision") != identity["revision"]):
        raise StoreMismatchError(
            f"{name}: chroma collection was filled by "
            f"{stamp.get('gsj_model')!r} @ {stamp.get('gsj_revision')!r} "
            f"({stamp.get('gsj_dimension')} dims) but the config names "
            f"embedding.model {identity['model']!r} @ embedding.revision "
            f"{identity['revision']!r} — a store built by a different "
            f"model (ADR-0016 as amended at CP-57); refusing to serve it. "
            f"Re-embed with index.rebuild: always, or restore the model "
            f"that built it")
    peek = collection.get(limit=1, include=["embeddings"])
    if not peek["ids"]:
        return
    stored = len(peek["embeddings"][0])
    if stored != identity["dimension"]:
        raise StoreMismatchError(
            f"{name}: chroma collection holds {stored}-dim vectors but the "
            f"configured embedding.model embeds at {identity['dimension']} "
            f"dims — the store was built by a different model (ADR-0016 as "
            f"amended at CP-57); refusing to serve it. Re-embed with "
            f"index.rebuild: always, or restore the model that built it")


def load_case_index(client, root: Path, case_id: str,
                    identity: dict) -> CaseIndex:
    doc = json.loads((root / case_id / "chunks.json").read_text())
    chunks = [Chunk(**c) for c in doc["chunks"]]
    pages = {int(p): t for p, t in doc["pages"].items()}
    collection = client.get_collection(case_id,
                                       embedding_function=_NoTextOps())
    if collection.count() != len(chunks):
        raise ValueError(
            f"{case_id}: chroma collection holds {collection.count()} "
            f"vectors, sidecar records {len(chunks)} chunks — stored index "
            f"corrupt")
    _check_collection_identity(collection, case_id, identity)
    return CaseIndex(case_id, collection, chunks, pages, doc["refs"],
                     doc["timesteps"])


def build_decisions_index(client, encoder: Encoder, corpus: list[dict],
                          progress: ProgressFn | None = None) -> DecisionsIndex:
    collection = _recreate_collection(client, "decisions", encoder.identity())
    _add_batched(
        client, collection, encoder, "decisions",
        texts=[f"{d['decision_id']} {d['court']} {d['year']} {d['text']}"
               for d in corpus],
        ids=[d["decision_id"] for d in corpus],
        metadatas=[{"court": d["court"], "year": d["year"]} for d in corpus],
        progress=progress)
    return DecisionsIndex(collection, corpus)


def save_decisions_index(root: Path, index) -> None:
    """The sidecar: the synthetic corpus as the list it always was (bytes
    unchanged), a drop as the document ``build_rii_decisions_index``
    assembled (``source: rii``)."""
    dec_dir = root / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    payload = index.doc if index.kind == "rii" else index.corpus
    (dec_dir / "corpus.json").write_text(
        json.dumps(payload, ensure_ascii=False))


def load_decisions_index(client, root: Path, identity: dict):
    """Either kind, told apart by the sidecar's shape; the count check is
    against pieces for a drop and decisions for the synthetic corpus."""
    doc = json.loads((root / "decisions" / "corpus.json").read_text())
    collection = client.get_collection("decisions",
                                       embedding_function=_NoTextOps())
    if isinstance(doc, dict) and doc.get("source") == "rii":
        index = RiiDecisionsIndex(collection, doc)
        expected = index.n_pieces
        what = "pieces"
    else:
        index = DecisionsIndex(collection, doc)
        expected = len(doc)
        what = "decisions"
    if collection.count() != expected:
        raise ValueError(
            f"decisions: chroma collection holds {collection.count()} "
            f"vectors, sidecar records {expected} {what} — stored index "
            f"corrupt")
    _check_collection_identity(collection, "decisions", identity)
    return index


def _read_fingerprint_doc(root: Path) -> dict:
    try:
        doc = json.loads((root / "fingerprint.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def read_fingerprint(root: Path) -> str | None:
    return _read_fingerprint_doc(root).get("fingerprint")


def read_collection_fingerprints(root: Path) -> dict[str, str]:
    """The per-collection record (CP-79); ``{}`` for a store written before
    it existed — such a store is reused whole on a fingerprint match and
    gets the record backfilled then (``state._backfill_identity``)."""
    doc = _read_fingerprint_doc(root).get("collections")
    return {str(k): str(v) for k, v in doc.items()} if isinstance(doc, dict) else {}


def read_store_identity(root: Path) -> dict | None:
    """The ``embedding`` block — which model built this store (CP-57).
    None for no store, and for a store written before CP-57 (its
    fingerprint still hashes model + revision, so a reuse under the same
    model backfills the block; a different model mismatches the
    fingerprint exactly as before)."""
    identity = _read_fingerprint_doc(root).get("embedding")
    return identity if isinstance(identity, dict) else None


def write_fingerprint(root: Path, fingerprint: str | None,
                      embedding: dict,
                      collections: dict[str, str] | None = None) -> None:
    """The fingerprint plus the store's identity: the model, revision and
    dimension that produced these vectors, next to the artifact (CP-57).
    ``fingerprint=None`` is the record a rebuild writes BEFORE it destroys
    anything: identity of the model about to fill the store, no reusable
    fingerprint — an interrupted rebuild is then refused under the old
    model and rebuilt under the new, never served. ``collections`` (CP-79)
    is the per-collection record — during a rebuild, the collections that
    are complete under this identity, so a kill keeps them reusable."""
    root.mkdir(parents=True, exist_ok=True)
    doc = {"fingerprint": fingerprint, "index_format": INDEX_FORMAT,
           "chroma_version": CHROMA_VERSION, "embedding": dict(embedding)}
    if collections is not None:
        doc["collections"] = dict(sorted(collections.items()))
    (root / "fingerprint.json").write_text(json.dumps(doc))
