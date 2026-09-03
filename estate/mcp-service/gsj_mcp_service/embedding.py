"""The configured encoder — eval mode, pinned revision, deterministic
(ADR-0040(f)).

WHICH model is configuration, not code (CP-57): ``embedding.model`` is a
HuggingFace model id and ``embedding.revision`` the full commit SHA that
pins it — MiniLM by default, any sentence-transformers-loadable checkpoint
on a real corpus. Nothing in this module assumes a family or a dimension:
the dimension, the token window and the special-token count are read off
the loaded model and exposed for the store (its identity record, ADR-0016
as amended at CP-57), the chunker (the window check) and the oracle (the
bound's scale). An unloadable id fails at startup with the id named —
never at the first query (CP-27's standard).

Determinism posture: torch grad off, single-threaded CPU math, exact float32
arithmetic, no dropout (eval mode is sentence-transformers' default at
inference). Two fresh processes embedding the same text on the same host
produce byte-identical vectors; the determinism test asserts exactly that.
This covers the EMBEDDING half only: since CP-15 the ranking half is
Chroma/HNSW, where cross-process reproducibility is a measured assumption
(A-25, ADR-0016), not a guarantee.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

import numpy as np

from .config import EmbeddingConfig

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class EmbeddingModelError(Exception):
    """The configured model cannot serve this deployment — unloadable id or
    revision, or a chunk window it cannot hold. A STARTUP failure naming
    the config key and what to check, never a first-query surprise."""


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
        self._dimension: int | None = None
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
        model, revision = self._config.model, self._config.revision
        try:
            loaded = SentenceTransformer(
                model, revision=revision, device=self._config.device)
        except Exception as error:  # noqa: BLE001 — every loader failure is named here
            raise EmbeddingModelError(
                f"embedding.model {model!r} @ embedding.revision {revision!r} "
                f"could not be loaded ({type(error).__name__}: {error}) — "
                f"check that the id exists on HuggingFace and loads as a "
                f"sentence-transformers model, that the revision is a "
                f"commit of that repo, and, when the deployment runs "
                f"offline (HF_HUB_OFFLINE=1), that this exact snapshot is "
                f"in the HF cache") from None
        loaded.eval()
        dimension = loaded.get_embedding_dimension()
        if dimension is None:  # a checkpoint without a declared width
            dimension = int(np.asarray(loaded.encode(
                ["gsj"], convert_to_numpy=True)).shape[-1])
        self._model = loaded
        self._dimension = int(dimension)

    @property
    def tokenizer(self):
        self.load()
        return self._model.tokenizer

    @property
    def dimension(self) -> int:
        """The loaded model's vector width — the store's dimension."""
        self.load()
        return self._dimension

    @property
    def loaded_dimension(self) -> int | None:
        """The dimension if the model is loaded, else None — never loads
        (``/health`` reads it while the init thread may still be loading)."""
        return self._dimension

    @property
    def max_seq_length(self) -> int:
        """The window the model truncates at, special tokens included."""
        self.load()
        return int(self._model.max_seq_length)

    @property
    def special_tokens(self) -> int:
        """Specials the tokenizer adds around one sequence ([CLS]/[SEP] and
        kin) — what a chunk's content tokens must leave room for."""
        return int(self.tokenizer.num_special_tokens_to_add(pair=False))

    def identity(self) -> dict:
        """What the store records about the model that built it (CP-57):
        id, revision and dimension — compared at every startup."""
        return {"model": self._config.model,
                "revision": self._config.revision,
                "dimension": self.dimension}

    def check_chunk_window(self, max_tokens: int) -> None:
        """Chunking is model-dependent: a chunk of ``max_tokens`` content
        tokens plus the model's specials must fit its window, or the model
        silently truncates every chunk and the tails become unsearchable —
        a recall hole nothing downstream would report. This is the static,
        NECESSARY half, refused before any corpus is fetched; it is not
        sufficient — a chunk is a character slice that re-tokenizes a few
        tokens longer than the window it was cut from — so
        ``check_chunks_fit`` measures the real chunks after ingest
        (CP-57)."""
        room = self.max_seq_length - self.special_tokens
        if max_tokens > room:
            raise EmbeddingModelError(
                f"chunking.max_tokens {max_tokens} does not fit "
                f"embedding.model {self._config.model!r}: its window is "
                f"{self.max_seq_length} tokens including "
                f"{self.special_tokens} specials, so chunks may hold at "
                f"most {room} tokens — and less in practice, since a chunk "
                f"re-tokenizes a few tokens longer than its window (the "
                f"shipped 220 leaves 34 under MiniLM's 256). Lower "
                f"chunking.max_tokens well below {room}, or configure a "
                f"model with a larger window")

    def check_chunks_fit(self, label: str, texts: list[str]) -> None:
        """The exact half of the window check, on the real corpus: every
        chunk's full token count (specials included, no truncation) against
        the model's window. A slice that starts mid-word gains a word-start
        piece on re-tokenization, so the static bound admits overflow at
        its boundary — measured at CP-57's review: at the boundary value
        127 of 814 staging chunks overflowed a 100-token window by one and
        were truncated silently at encode time. Refused at startup naming
        the count and the worst chunk."""
        window = self.max_seq_length
        # in slices (CP-79): a drop is a million pieces, and one tokenizer
        # call over all of them materialises every id list at once
        over: list[tuple[int, int]] = []
        step = 4096
        for lo in range(0, len(texts), step):
            encoded = self.tokenizer(texts[lo:lo + step], add_special_tokens=True,
                                     truncation=False,
                                     return_attention_mask=False)
            over.extend((len(ids), lo + i)
                        for i, ids in enumerate(encoded["input_ids"])
                        if len(ids) > window)
        if over:
            worst, index = max(over)
            raise EmbeddingModelError(
                f"{label}: {len(over)} of {len(texts)} chunks re-tokenize "
                f"past embedding.model {self._config.model!r}'s "
                f"{window}-token window (worst: chunk {index}, {worst} "
                f"tokens with specials) and would be truncated silently at "
                f"encode time — lower chunking.max_tokens: a chunk is cut "
                f"on one tokenization and re-tokenized at encode, so it "
                f"needs headroom under the window (the shipped 220 leaves "
                f"34 under MiniLM's 256)")

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
