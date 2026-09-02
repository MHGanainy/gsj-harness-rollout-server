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
from .embedding import Encoder
from .ingest import CaseSource, Chunk

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


def corpus_fingerprint(sources: dict[str, CaseSource],
                       embedding: EmbeddingConfig,
                       chunking: ChunkingConfig,
                       decisions_seed: int, decisions_size: int,
                       chroma_version: str = CHROMA_VERSION) -> str:
    """sha256 over everything that determines index bytes: repo main SHAs,
    model + revision, chunking params, decisions corpus params, index
    format, and (since CP-15) the Chroma version — an upgrade that changes
    the on-disk format must rebuild loudly, never fail silently."""
    doc = {
        "index_format": INDEX_FORMAT,
        "cases": {cid: src.main_sha for cid, src in sorted(sources.items())},
        "embedding": {"model": embedding.model, "revision": embedding.revision,
                      "normalize": embedding.normalize},
        "chunking": {"max_tokens": chunking.max_tokens,
                     "overlap": chunking.overlap,
                     "respect_page_boundaries": chunking.respect_page_boundaries},
        "decisions": {"seed": decisions_seed, "size": decisions_size},
        "chroma": {"version": chroma_version},
    }
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


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
    ``n_results`` is the whole corpus, tie-break by decision_id is ours."""

    def __init__(self, collection, corpus: list[dict]) -> None:
        self.collection = collection
        self.corpus = corpus
        self._by_id = {d["decision_id"]: d for d in corpus}

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


def save_decisions_index(root: Path, index: DecisionsIndex) -> None:
    dec_dir = root / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    (dec_dir / "corpus.json").write_text(
        json.dumps(index.corpus, ensure_ascii=False))


def load_decisions_index(client, root: Path,
                         identity: dict) -> DecisionsIndex:
    corpus = json.loads((root / "decisions" / "corpus.json").read_text())
    collection = client.get_collection("decisions",
                                       embedding_function=_NoTextOps())
    if collection.count() != len(corpus):
        raise ValueError(
            f"decisions: chroma collection holds {collection.count()} "
            f"vectors, sidecar records {len(corpus)} — stored index corrupt")
    _check_collection_identity(collection, "decisions", identity)
    return DecisionsIndex(collection, corpus)


def _read_fingerprint_doc(root: Path) -> dict:
    try:
        doc = json.loads((root / "fingerprint.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def read_fingerprint(root: Path) -> str | None:
    return _read_fingerprint_doc(root).get("fingerprint")


def read_store_identity(root: Path) -> dict | None:
    """The ``embedding`` block — which model built this store (CP-57).
    None for no store, and for a store written before CP-57 (its
    fingerprint still hashes model + revision, so a reuse under the same
    model backfills the block; a different model mismatches the
    fingerprint exactly as before)."""
    identity = _read_fingerprint_doc(root).get("embedding")
    return identity if isinstance(identity, dict) else None


def write_fingerprint(root: Path, fingerprint: str | None,
                      embedding: dict) -> None:
    """The fingerprint plus the store's identity: the model, revision and
    dimension that produced these vectors, next to the artifact (CP-57).
    ``fingerprint=None`` is the record a rebuild writes BEFORE it destroys
    anything: identity of the model about to fill the store, no reusable
    fingerprint — an interrupted rebuild is then refused under the old
    model and rebuilt under the new, never served."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "fingerprint.json").write_text(
        json.dumps({"fingerprint": fingerprint, "index_format": INDEX_FORMAT,
                    "chroma_version": CHROMA_VERSION,
                    "embedding": dict(embedding)}))
