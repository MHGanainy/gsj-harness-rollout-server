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
silently (ADR-0016).

Embeddings are ALWAYS supplied explicitly by the pinned MiniLM encoder
(``embedding.py``); Chroma's own embedding machinery is disabled by a
raising embedding function on every collection handle — Chroma's default
EF is a DIFFERENT MiniLM (ONNX) at the same 384 dims, so a silent
substitution would be plausible-but-wrong (ADR-0016, test-asserted).

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
from dataclasses import asdict
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from .config import ChunkingConfig, EmbeddingConfig
from .embedding import Encoder
from .ingest import CaseSource, Chunk

INDEX_FORMAT = 2  # 1 = vectors.npy + numpy scan, retired at CP-15 (ADR-0016)
CHROMA_VERSION = chromadb.__version__

_HNSW_COSINE = {"hnsw": {"space": "cosine"}}  # normalized vecs: score = 1 - d


class _NoTextOps:
    """Refuses Chroma's text-side embedding paths. Without an explicit
    embedding function, ``get_collection``'s DEFAULT parameter attaches
    Chroma's bundled ONNX MiniLM — 384 dims, same as ours — and a stray
    text op would silently mix two different MiniLM implementations
    (ADR-0016). Embeddings come only from the pinned encoder."""

    _MESSAGE = ("text ops are disabled on this collection — embeddings are "
                "supplied explicitly by the pinned MiniLM encoder "
                "(embedding.py; ADR-0016)")

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


def _recreate_collection(client, name: str):
    """The rebuild path: drop any existing collection, create fresh."""
    try:
        client.delete_collection(name)
    except NotFoundError:
        pass
    return client.create_collection(
        name, configuration=dict(_HNSW_COSINE),
        embedding_function=_NoTextOps())


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
        the exact scan this replaced; a larger corpus that needs a bounded
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


def build_case_index(client, encoder: Encoder, source: CaseSource) -> CaseIndex:
    vectors = encoder.encode_corpus([c.text for c in source.chunks])
    collection = _recreate_collection(client, source.case_id)
    collection.add(
        ids=[_chunk_id(c) for c in source.chunks],
        embeddings=vectors,
        metadatas=[{"case_id": c.case_id, "page": c.page, "file": c.file,
                    "chunk_idx": c.chunk_idx} for c in source.chunks])
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


def load_case_index(client, root: Path, case_id: str) -> CaseIndex:
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
    return CaseIndex(case_id, collection, chunks, pages, doc["refs"],
                     doc["timesteps"])


def build_decisions_index(client, encoder: Encoder,
                          corpus: list[dict]) -> DecisionsIndex:
    vectors = encoder.encode_corpus(
        [f"{d['decision_id']} {d['court']} {d['year']} {d['text']}"
         for d in corpus])
    collection = _recreate_collection(client, "decisions")
    collection.add(
        ids=[d["decision_id"] for d in corpus],
        embeddings=vectors,
        metadatas=[{"court": d["court"], "year": d["year"]} for d in corpus])
    return DecisionsIndex(collection, corpus)


def save_decisions_index(root: Path, index: DecisionsIndex) -> None:
    dec_dir = root / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    (dec_dir / "corpus.json").write_text(
        json.dumps(index.corpus, ensure_ascii=False))


def load_decisions_index(client, root: Path) -> DecisionsIndex:
    corpus = json.loads((root / "decisions" / "corpus.json").read_text())
    collection = client.get_collection("decisions",
                                       embedding_function=_NoTextOps())
    if collection.count() != len(corpus):
        raise ValueError(
            f"decisions: chroma collection holds {collection.count()} "
            f"vectors, sidecar records {len(corpus)} — stored index corrupt")
    return DecisionsIndex(collection, corpus)


def read_fingerprint(root: Path) -> str | None:
    try:
        return json.loads((root / "fingerprint.json").read_text())["fingerprint"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def write_fingerprint(root: Path, fingerprint: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "fingerprint.json").write_text(
        json.dumps({"fingerprint": fingerprint, "index_format": INDEX_FORMAT,
                    "chroma_version": CHROMA_VERSION}))
