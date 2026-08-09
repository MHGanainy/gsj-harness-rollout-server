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
from .index import (CaseIndex, DecisionsIndex, build_case_index,
                    corpus_fingerprint, load_case_index, load_decisions_index,
                    read_fingerprint, save_case_index, save_decisions_index,
                    write_fingerprint)
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
        self.encoder.load()
        tokenizer = self.encoder.tokenizer

        sources = {}
        for repo in config.source.repos:
            sources[repo] = ingest_case(
                config.source, config.chunking, tokenizer, repo, source_token)
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
            return

        if config.index.rebuild == "if-stale" and stored == fingerprint:
            try:
                self._load_all(fingerprint)
                logger.info("index reused: fingerprint match %s", fingerprint)
                return
            except Exception as error:  # corrupt files ⇒ loud rebuild
                logger.warning("stored index unreadable (%s) — REBUILDING", error)
        elif stored is not None and stored != fingerprint:
            logger.warning(
                "CORPUS FINGERPRINT MISMATCH — stored %s != computed %s; "
                "REBUILDING the index (repo SHAs, model revision, or chunking "
                "params changed — with the dataset frozen this should only "
                "happen on a deliberate re-pin)", stored, fingerprint)
        else:
            logger.info("no stored index — building fresh")

        corpus = decisions_corpus(config.decisions.seed,
                                  config.decisions.corpus_size)
        for repo, source in sources.items():
            index = build_case_index(self.encoder, source)
            save_case_index(config.index.path, index)
            self.cases[repo] = index
            self.progress[repo]["embedded"] = True
        decisions_vectors = self.encoder.encode_corpus(
            [f"{d['decision_id']} {d['court']} {d['year']} {d['text']}"
             for d in corpus])
        self.decisions = DecisionsIndex(decisions_vectors, corpus)
        save_decisions_index(config.index.path, self.decisions)
        write_fingerprint(config.index.path, fingerprint)
        self.fingerprint = fingerprint
        self.reused_index = False
        self.status = "ready"
        self.ready_at = time.time()
        logger.info("index built: fingerprint %s — READY", fingerprint)

    def _load_all(self, fingerprint: str) -> None:
        for repo in self.config.source.repos:
            self.cases[repo] = load_case_index(self.config.index.path, repo)
        self.decisions = load_decisions_index(self.config.index.path)
        self.fingerprint = fingerprint
        self.reused_index = True
        self.status = "ready"
        self.ready_at = time.time()

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
                          "revision": self.config.embedding.revision},
        }
        if self.error:
            doc["error"] = self.error
        if self.status == "ready":
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
