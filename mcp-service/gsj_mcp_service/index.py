"""Per-case vector index — exact brute-force cosine, cutoff-filter-first.

One index per case over the FULL document (never per timestep); the cutoff
is applied as a candidate FILTER (chunk.page <= T) **before** ranking — a
post-filter would change result counts and is the classic leak shape
(ADR-0040(d)). T comes from the verified token claims only.

Storage: ``<index.path>/<case_id>/vectors.npy`` (float32 [n_chunks, dim],
L2-normalized when embedding.normalize) + ``chunks.json`` (metadata
``{case_id, page, file, chunk_idx, text}`` per row, page texts, refs).
``<index.path>/fingerprint.json`` holds the corpus fingerprint that gates
reuse-vs-rebuild on restart (ADR-0040(c)).

Result shape (the compatibility requirement any future backend must keep —
G5's transcript backstop parses it via the library's
``extract_case_search_pages``): every ``search_case`` hit carries
``"page"`` (int) and ``"file"`` (``md/page_NNNN.md``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .config import ChunkingConfig, EmbeddingConfig
from .embedding import Encoder
from .ingest import CaseSource, Chunk

INDEX_FORMAT = 1


def corpus_fingerprint(sources: dict[str, CaseSource],
                       embedding: EmbeddingConfig,
                       chunking: ChunkingConfig,
                       decisions_seed: int, decisions_size: int) -> str:
    """sha256 over everything that determines index bytes: repo main SHAs,
    model + revision, chunking params, decisions corpus params, format."""
    doc = {
        "index_format": INDEX_FORMAT,
        "cases": {cid: src.main_sha for cid, src in sorted(sources.items())},
        "embedding": {"model": embedding.model, "revision": embedding.revision,
                      "normalize": embedding.normalize},
        "chunking": {"max_tokens": chunking.max_tokens,
                     "overlap": chunking.overlap,
                     "respect_page_boundaries": chunking.respect_page_boundaries},
        "decisions": {"seed": decisions_seed, "size": decisions_size},
    }
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


class CaseIndex:
    def __init__(self, case_id: str, vectors: np.ndarray, chunks: list[Chunk],
                 pages: dict[int, str], refs: dict[str, str],
                 timesteps: list[int]) -> None:
        self.case_id = case_id
        self.vectors = vectors  # float32 [n_chunks, dim]
        self.chunks = chunks
        self.pages = pages
        self.refs = refs
        self.timesteps = timesteps
        self.n_pages = max(pages)
        self._pages_by_chunk = np.array([c.page for c in chunks], dtype=np.int64)

    def search(self, query_vec: np.ndarray, k: int, timestep: int) -> list[dict]:
        """Filter to page <= timestep FIRST, then rank the filtered set by
        cosine; aggregate chunk scores to page level (max), return top-k pages
        as ``{"page", "file", "score", "text"}`` with full page text —
        score-descending, ties by page ascending, non-positive scores dropped.
        """
        visible = np.flatnonzero(self._pages_by_chunk <= timestep)
        if visible.size == 0:
            return []
        scores = self.vectors[visible] @ query_vec  # exact cosine (normalized)
        best_by_page: dict[int, float] = {}
        for idx, score in zip(visible, scores):
            page = int(self._pages_by_chunk[idx])
            value = float(score)
            if page not in best_by_page or value > best_by_page[page]:
                best_by_page[page] = value
        ranked = sorted(best_by_page.items(),
                        key=lambda item: (-item[1], item[0]))
        return [{"page": page, "file": f"md/page_{page:04d}.md",
                 "score": score, "text": self.pages[page]}
                for page, score in ranked[:k] if score > 0]


class DecisionsIndex:
    """Cutoff-exempt (ADR-0007(e)): ranks the full deterministic corpus."""

    def __init__(self, vectors: np.ndarray, corpus: list[dict]) -> None:
        self.vectors = vectors
        self.corpus = corpus

    def search(self, query_vec: np.ndarray, k: int) -> list[dict]:
        scores = self.vectors @ query_vec
        ranked = sorted(zip(scores, self.corpus),
                        key=lambda item: (-float(item[0]), item[1]["decision_id"]))
        return [{"decision_id": d["decision_id"], "court": d["court"],
                 "year": d["year"], "score": float(score), "text": d["text"]}
                for score, d in ranked[:k] if float(score) > 0]


def build_case_index(encoder: Encoder, source: CaseSource) -> CaseIndex:
    vectors = encoder.encode_corpus([c.text for c in source.chunks])
    return CaseIndex(source.case_id, vectors, source.chunks, source.pages,
                     source.refs, source.timesteps)


def save_case_index(root: Path, index: CaseIndex) -> None:
    case_dir = root / index.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    np.save(case_dir / "vectors.npy", index.vectors)
    (case_dir / "chunks.json").write_text(json.dumps({
        "case_id": index.case_id,
        "refs": index.refs,
        "timesteps": index.timesteps,
        "chunks": [asdict(c) for c in index.chunks],
        "pages": {str(p): t for p, t in sorted(index.pages.items())},
    }, ensure_ascii=False))


def load_case_index(root: Path, case_id: str) -> CaseIndex:
    case_dir = root / case_id
    vectors = np.load(case_dir / "vectors.npy")
    doc = json.loads((case_dir / "chunks.json").read_text())
    chunks = [Chunk(**c) for c in doc["chunks"]]
    pages = {int(p): t for p, t in doc["pages"].items()}
    return CaseIndex(case_id, vectors, chunks, pages, doc["refs"],
                     doc["timesteps"])


def save_decisions_index(root: Path, index: DecisionsIndex) -> None:
    dec_dir = root / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    np.save(dec_dir / "vectors.npy", index.vectors)
    (dec_dir / "corpus.json").write_text(
        json.dumps(index.corpus, ensure_ascii=False))


def load_decisions_index(root: Path) -> DecisionsIndex:
    dec_dir = root / "decisions"
    return DecisionsIndex(np.load(dec_dir / "vectors.npy"),
                          json.loads((dec_dir / "corpus.json").read_text()))


def read_fingerprint(root: Path) -> str | None:
    try:
        return json.loads((root / "fingerprint.json").read_text())["fingerprint"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def write_fingerprint(root: Path, fingerprint: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "fingerprint.json").write_text(
        json.dumps({"fingerprint": fingerprint, "index_format": INDEX_FORMAT}))
