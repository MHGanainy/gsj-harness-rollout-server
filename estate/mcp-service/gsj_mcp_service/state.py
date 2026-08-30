"""Runtime state: readiness distinct from liveness (ADR-0040(c)/(h)).

Liveness = the process answers ``/health`` at all. Readiness = ``state ==
"ready"`` — indexes loaded/built and tools serving. Tool traffic before
ready gets a clear MCP error, never empty results.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from typing import Literal

from .config import ServiceConfig
from .decisions import decisions_corpus
from .embedding import Encoder
from .index import (CHROMA_VERSION, PRE_CP57_STORE_IDENTITY, CaseIndex,
                    DecisionsIndex, StoreMismatchError, build_case_index,
                    build_decisions_index, chroma_client, corpus_fingerprint,
                    evict_chroma_client_cache, load_case_index,
                    load_decisions_index, read_fingerprint,
                    read_store_identity, save_case_index,
                    save_decisions_index, write_fingerprint)
from .ingest import IngestError, ingest_case

logger = logging.getLogger("gsj_mcp_service")


class NotReadyError(Exception):
    """Raised by tool bodies when the service is not (yet) ready."""


class AppState:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.encoder = Encoder(config.embedding)
        self.status: Literal["indexing", "ready", "error"] = "indexing"
        self.error: str | None = None
        self.progress: dict[str, dict] = {
            repo: {"done": False} for repo in config.source.repos}
        self.cases: dict[str, CaseIndex] = {}
        self.decisions: DecisionsIndex | None = None
        self.fingerprint: str | None = None
        self.reused_index = False
        self.started_at = time.time()
        self.ready_at: float | None = None
        self._reindex_lock = threading.Lock()
        self._chroma = None  # one persistent client per process, lazy

    def _client(self):
        if self._chroma is None:
            self._chroma = chroma_client(self.config.index.path)
        return self._chroma

    # -- initialization -----------------------------------------------------

    def initialize(self) -> None:
        """Ingest → fingerprint → reuse-or-(re)build. Runs in a background
        thread; any failure lands in status="error" with the message."""
        try:
            self._initialize()
        except (IngestError, Exception) as error:  # noqa: BLE001 — /health surface
            self.status = "error"
            self.error = f"{type(error).__name__}: {error}"
            logger.error("initialization failed: %s", self.error)

    def _initialize(self) -> None:
        config = self.config
        source_token = config.source_token()
        # The store's identity gate runs FIRST — before the model loads, so
        # a re-pinned config is refused in milliseconds, not after a model
        # download and a corpus fetch (CP-57).
        self._check_store_identity()
        self.encoder.load()
        self.encoder.check_chunk_window(config.chunking.max_tokens)
        tokenizer = self.encoder.tokenizer

        sources = {}
        for repo in config.source.repos:
            sources[repo] = ingest_case(
                config.source, config.chunking, tokenizer, repo, source_token)
            self.encoder.check_chunks_fit(
                repo, [c.text for c in sources[repo].chunks])
            self.progress[repo] = {
                "done": True,
                "pages": len(sources[repo].pages),
                "chunks": len(sources[repo].chunks),
            }
            logger.info("ingested %s: %d pages, %d chunks", repo,
                        len(sources[repo].pages), len(sources[repo].chunks))

        fingerprint = corpus_fingerprint(
            sources, config.embedding, config.chunking,
            config.decisions.seed, config.decisions.corpus_size)
        stored = read_fingerprint(config.index.path)

        if config.index.rebuild == "never":
            if stored != fingerprint:
                raise IngestError(
                    f"index.rebuild=never but the stored index is "
                    f"{'missing' if stored is None else 'STALE'} "
                    f"(stored={stored!r}, computed={fingerprint!r})")
            self._load_all(fingerprint)
            self._backfill_identity(fingerprint)
            return

        if config.index.rebuild == "if-stale" and stored == fingerprint:
            try:
                self._load_all(fingerprint)
            except StoreMismatchError:
                raise  # another model's vectors are not corruption — refuse
            except Exception as error:  # corrupt files ⇒ loud rebuild
                logger.warning("stored index unreadable (%s) — REBUILDING", error)
            else:
                logger.info("index reused: fingerprint match %s", fingerprint)
                self._backfill_identity(fingerprint)
                return
        elif stored is not None and stored != fingerprint:
            logger.warning(
                "CORPUS FINGERPRINT MISMATCH — stored %s != computed %s; "
                "REBUILDING the index (repo SHAs, chunking params, or the "
                "Chroma version changed; a model change lands here only "
                "under index.rebuild: always — against a store it is "
                "refused before this point; with the dataset frozen this "
                "should only happen on a deliberate re-pin)",
                stored, fingerprint)
        else:
            logger.info("no stored index — building fresh")

        corpus = decisions_corpus(config.decisions.seed,
                                  config.decisions.corpus_size)
        client = self._client()
        # The record FIRST, before anything is destroyed: the identity of
        # the model about to fill the store and no reusable fingerprint. A
        # rebuild interrupted anywhere below leaves a store the next start
        # refuses under the old model (the record names the new one) and
        # rebuilds under the new (no fingerprint) — never one it serves
        # (CP-57 review: the interrupted same-width re-pin).
        write_fingerprint(config.index.path, None, self.encoder.identity())
        for repo, source in sources.items():
            index = build_case_index(client, self.encoder, source)
            save_case_index(config.index.path, index)
            self.cases[repo] = index
            self.progress[repo]["embedded"] = True
        self.decisions = build_decisions_index(client, self.encoder, corpus)
        save_decisions_index(config.index.path, self.decisions)
        write_fingerprint(config.index.path, fingerprint,
                          self.encoder.identity())
        self.fingerprint = fingerprint
        self.reused_index = False
        self.status = "ready"
        self.ready_at = time.time()
        logger.info("index built: fingerprint %s — READY (embedded by %s @ %s, "
                    "%d dims)", fingerprint, config.embedding.model,
                    config.embedding.revision, self.encoder.dimension)

    def _check_store_identity(self) -> None:
        """CP-57's gate: a store built by one model and served under another
        is CP-15's phantom store in a different hat — plausible scores,
        nothing saying so. The stored ``embedding`` block is compared with
        the configured model + revision and any difference REFUSES to
        serve: a model change is a re-pin, not staleness, and re-embedding
        a production corpus (destroying the old store on the way) must be
        asked for explicitly — ``index.rebuild: always`` is that ask, and
        skips this gate. Absent block (no store, or pre-CP-57) passes to
        the fingerprint, which hashes the same identity."""
        if self.config.index.rebuild == "always":
            return
        stored = read_store_identity(self.config.index.path)
        assumed = ""
        if stored is None:
            if read_fingerprint(self.config.index.path) is None:
                return  # no store at all (or one mid-rebuild: no fingerprint)
            # An existing store with no record predates CP-57, and exactly
            # one pin built those — assume it rather than rebuild over it.
            stored = PRE_CP57_STORE_IDENTITY
            assumed = (" (a store written before CP-57 carries no identity "
                       "record; assumed the pre-CP-57 pin)")
        configured = self.config.embedding
        if (stored.get("model") == configured.model
                and stored.get("revision") == configured.revision):
            return
        raise StoreMismatchError(
            f"EMBEDDING MODEL MISMATCH — refusing to serve. The stored index "
            f"at {self.config.index.path} was built by "
            f"{stored.get('model')!r} @ {stored.get('revision')!r} "
            f"({stored.get('dimension')} dims){assumed}, but the config names "
            f"embedding.model {configured.model!r} @ embedding.revision "
            f"{configured.revision!r}. Vectors from one model are "
            f"meaningless under another and nothing downstream would say "
            f"so (ADR-0016 as amended at CP-57). This is a model re-pin, "
            f"not staleness: to re-embed the corpus with the configured "
            f"model, start once with index.rebuild: always (or delete "
            f"{self.config.index.path}); to keep the stored index, restore "
            f"the model and revision that built it.")

    def _load_all(self, fingerprint: str) -> None:
        client = self._client()
        identity = self.encoder.identity()
        for repo in self.config.source.repos:
            self.cases[repo] = load_case_index(client, self.config.index.path,
                                               repo, identity)
        self.decisions = load_decisions_index(client, self.config.index.path,
                                              identity)
        self.fingerprint = fingerprint
        self.reused_index = True
        self.status = "ready"
        self.ready_at = time.time()

    def _backfill_identity(self, fingerprint: str) -> None:
        """A pre-CP-57 store, proven this model's by the fingerprint match
        and the load-time checks: give it the record it lacked. Outside the
        reuse path's corrupt-rebuild catch — a record that cannot be
        written is a warning, never a reason to re-embed a good store
        (CP-57 review)."""
        if read_store_identity(self.config.index.path) is not None:
            return
        identity = self.encoder.identity()
        try:
            write_fingerprint(self.config.index.path, fingerprint, identity)
        except OSError as error:
            logger.warning("stored index predates the identity record and "
                           "the record could not be written (%s) — serving "
                           "it anyway; it is assumed the pre-CP-57 pin "
                           "until the record lands", error)
            return
        logger.info("stored index predates the identity record — "
                    "backfilled embedding %s", identity)

    def start_background_init(self) -> threading.Thread:
        thread = threading.Thread(target=self.initialize,
                                  name="gsj-mcp-init", daemon=True)
        thread.start()
        return thread

    def request_reindex(self) -> str:
        """The CP-33 re-index trigger (ADR-0047(d)): re-run ingest →
        fingerprint → reuse-or-rebuild in a background thread. The service is
        unready (503 on tool traffic) until it completes — the same contract
        a restart gives, without a process manager. Returns "started" or
        "already-indexing" (idempotent under concurrent triggers: exactly one
        init thread runs at a time). An unchanged corpus is cheap: fetch +
        fingerprint match ⇒ the stored index is reused, not re-embedded."""
        with self._reindex_lock:
            if self.status == "indexing":
                return "already-indexing"
            self.status = "indexing"
            self.error = None
            self.progress = {repo: {"done": False}
                             for repo in self.config.source.repos}
            self.cases = {}
            self.decisions = None
            self.fingerprint = None
            self.reused_index = False
            # Restart-equivalence (ADR-0016): drop the cached chroma system
            # so the init thread observes the REAL on-disk store — without
            # this, a store replaced out-of-band stays a served phantom.
            evict_chroma_client_cache(self.config.index.path)
            self._chroma = None
            thread = threading.Thread(target=self.initialize,
                                      name="gsj-mcp-reindex", daemon=True)
            thread.start()
            logger.info("admin reindex started (previous state discarded; "
                        "unready until re-init completes)")
            return "started"

    # -- request-side accessors --------------------------------------------

    def require_ready(self) -> None:
        if self.status != "ready":
            detail = self.error if self.status == "error" else "still indexing"
            raise NotReadyError(
                f"service not ready (state: {self.status} — {detail}); "
                f"retry after /health reports state=ready")

    def case(self, case_id: str) -> CaseIndex:
        index = self.cases.get(case_id)
        if index is None:
            raise KeyError(case_id)
        return index

    # -- observability ------------------------------------------------------

    def health(self) -> dict:
        doc: dict = {
            "state": self.status,
            "uptime_s": round(time.time() - self.started_at, 1),
            "progress": self.progress,
            "embedding": {"model": self.config.embedding.model,
                          "revision": self.config.embedding.revision,
                          "dimension": self.encoder.loaded_dimension},
            "backend": {"name": "chromadb", "version": CHROMA_VERSION},
        }
        if self.error:
            doc["error"] = self.error
        if self.status == "ready":
            doc["backend"]["collections"] = (
                len(self.cases) + (1 if self.decisions is not None else 0))
            doc["cases"] = {
                cid: {"pages": idx.n_pages, "chunks": len(idx.chunks),
                      "timesteps": idx.timesteps}
                for cid, idx in sorted(self.cases.items())}
            doc["decisions"] = len(self.decisions.corpus)
            doc["fingerprint"] = self.fingerprint
            doc["index_reused"] = self.reused_index
        return doc


def request_log(state: AppState, **fields) -> None:
    """One structured JSON line per tool call (the F-17 lesson, ADR-0040(h)).
    Only the configured fields are emitted, in the configured order."""
    wanted = state.config.server.request_log_fields
    record = {"event": "tool_call"}
    record.update({key: fields.get(key) for key in wanted})
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)
