"""MiniLM embedding — eval mode, pinned revision, deterministic (ADR-0040(f)).

Determinism posture: torch grad off, single-threaded CPU math, exact float32
arithmetic, no dropout (eval mode is sentence-transformers' default at
inference). Two fresh processes embedding the same text on the same host
produce byte-identical vectors; the determinism test asserts exactly that.
An ANN index or multi-threaded BLAS would forfeit this — assumption row
required before either is introduced.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

import numpy as np

from .config import EmbeddingConfig

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class Encoder:
    """Lazy-loading wrapper around SentenceTransformer.

    Query encoding is serialized by a lock (queries are single, tiny texts —
    the lock guarantees deterministic math under concurrent tool calls) and
    memoized in a small LRU (`cache_hit` in the request log).
    """

    _QUERY_CACHE_SIZE = 256

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model = None
        self._lock = threading.Lock()
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()

    @property
    def config(self) -> EmbeddingConfig:
        return self._config

    def load(self) -> None:
        """Load the pinned model; import cost is paid here, not at module
        import (tests that never embed stay torch-free)."""
        if self._model is not None:
            return
        import torch
        torch.set_grad_enabled(False)
        torch.set_num_threads(1)
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(
            self._config.model,
            revision=self._config.revision,
            device=self._config.device,
        )
        self._model.eval()

    @property
    def tokenizer(self):
        self.load()
        return self._model.tokenizer

    def encode_corpus(self, texts: list[str]) -> np.ndarray:
        """Batch-encode chunk texts at ingest time -> float32 [n, dim]."""
        self.load()
        with self._lock:
            vectors = self._model.encode(
                texts,
                batch_size=self._config.batch_size,
                normalize_embeddings=self._config.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str) -> tuple[np.ndarray, bool]:
        """Encode one query -> (float32 [dim], cache_hit)."""
        self.load()
        with self._lock:
            cached = self._query_cache.get(text)
            if cached is not None:
                self._query_cache.move_to_end(text)
                return cached, True
            vector = self._model.encode(
                [text],
                batch_size=1,
                normalize_embeddings=self._config.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
            vector = np.asarray(vector, dtype=np.float32)
            self._query_cache[text] = vector
            if len(self._query_cache) > self._QUERY_CACHE_SIZE:
                self._query_cache.popitem(last=False)
            return vector, False
