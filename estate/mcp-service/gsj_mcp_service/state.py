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
from .decisions import DecisionError, Drop, decisions_corpus, load_drop
from .embedding import Encoder
from .index import (CHROMA_VERSION, PRE_CP57_STORE_IDENTITY, CaseIndex,
                    DecisionsIndex, RiiDecisionsIndex, StoreMismatchError,
                    build_case_index, build_decisions_index,
                    build_rii_decisions_index, chroma_client,
                    collection_fingerprints, corpus_fingerprint,
                    drop_component, evict_chroma_client_cache,
                    load_case_index, load_decisions_index,
                    read_collection_fingerprints, read_fingerprint,
                    read_store_identity, save_case_index,
                    save_decisions_index, sweep_orphans, write_fingerprint)
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
        self.decisions: DecisionsIndex | RiiDecisionsIndex | None = None
        self.fingerprint: str | None = None
        self.reused_index = False
        # CP-79: which collections this start (re)built, by name — [] on a
        # whole-store reuse; /health "rebuilt" once ready
        self.rebuilt: list[str] = []
        # The build in flight (CP-77): which collection, how many of its
        # vectors are embedded and added, which batch — /health "build"
        # while indexing, kept as the last batch that landed when a build
        # fails (the failure names where it stopped), absent once ready.
        self.build_progress: dict | None = None
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

        drop, component = self._load_drop()
        args = (sources, config.embedding, config.chunking,
                config.decisions.seed, config.decisions.corpus_size)
        fingerprint = corpus_fingerprint(*args, decisions_drop=component)
        wanted = collection_fingerprints(*args, decisions_drop=component)
        stored = read_fingerprint(config.index.path)

        if config.index.rebuild == "never":
            if stored != fingerprint:
                raise IngestError(
                    f"index.rebuild=never but the stored index is "
                    f"{'missing' if stored is None else 'STALE'} "
                    f"(stored={stored!r}, computed={fingerprint!r})")
            self._load_all(fingerprint)
            self._backfill_identity(fingerprint, wanted)
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
                self._backfill_identity(fingerprint, wanted)
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

        client = self._client()
        self._sweep(client)
        identity = self.encoder.identity()
        # a whole-store load that failed midway may have filled some of
        # these; every kept collection is re-loaded and re-checked below
        self.cases = {}
        self.decisions = None
        # CP-79 (wishlist 61): the collections whose inputs did not move are
        # loaded, not re-embedded — never under `always`, the explicit ask
        # to re-embed everything
        keep = (self._reusable(stored, fingerprint, wanted, args)
                if config.index.rebuild != "always" else set())
        kept: dict[str, str] = {}
        for repo in config.source.repos:
            if repo in keep:
                try:
                    self.cases[repo] = load_case_index(
                        client, config.index.path, repo, identity)
                except StoreMismatchError:
                    raise
                except Exception as error:  # noqa: BLE001 — a corrupt collection rebuilds
                    logger.warning("%s: stored collection unreadable (%s) — "
                                   "rebuilding it", repo, error)
                else:
                    kept[repo] = wanted[repo]
                    self.progress[repo]["reused"] = True
        if "decisions" in keep:
            try:
                self.decisions = load_decisions_index(client, config.index.path,
                                                      identity)
                expected_kind = "rii" if drop is not None else "synthetic"
                if self.decisions.kind != expected_kind:
                    raise ValueError(
                        f"the stored decisions sidecar is {self.decisions.kind}, "
                        f"the config wants {expected_kind}")
            except StoreMismatchError:
                raise
            except Exception as error:  # noqa: BLE001
                logger.warning("decisions: stored collection unreadable (%s) "
                               "— rebuilding it", error)
                self.decisions = None
            else:
                kept["decisions"] = wanted["decisions"]
        if kept:
            logger.info("collections reused by their own fingerprint: %s "
                        "(CP-79); rebuilding %s", sorted(kept),
                        sorted(set(wanted) - set(kept)))
        # The record FIRST, before anything is destroyed: the identity of
        # the model about to fill the store and no reusable fingerprint. A
        # rebuild interrupted anywhere below leaves a store the next start
        # refuses under the old model (the record names the new one) and
        # rebuilds under the new (no fingerprint) — never one it serves
        # (CP-57 review: the interrupted same-width re-pin; CP-77: the
        # same holds for a kill between two add batches). Since CP-79 the
        # record also names the collections complete under this identity,
        # updated as each lands, so a kill keeps them reusable.
        write_fingerprint(config.index.path, None, identity, collections=kept)
        for repo, source in sources.items():
            if repo in self.cases:
                continue
            index = build_case_index(client, self.encoder, source,
                                     progress=self._on_batch)
            save_case_index(config.index.path, index)
            self.cases[repo] = index
            self.progress[repo]["embedded"] = True
            self.rebuilt.append(repo)
            kept[repo] = wanted[repo]
            write_fingerprint(config.index.path, None, identity, collections=kept)
        if self.decisions is None:
            if drop is not None:
                self.decisions = build_rii_decisions_index(
                    client, self.encoder, drop, config.chunking,
                    progress=self._on_batch)
            else:
                corpus = decisions_corpus(config.decisions.seed,
                                          config.decisions.corpus_size)
                self.decisions = build_decisions_index(
                    client, self.encoder, corpus, progress=self._on_batch)
            save_decisions_index(config.index.path, self.decisions)
            self.rebuilt.append("decisions")
            kept["decisions"] = wanted["decisions"]
        write_fingerprint(config.index.path, fingerprint, identity,
                          collections=kept)
        self.fingerprint = fingerprint
        # reused = nothing embedded: a whole-store mismatch that kept every
        # collection (a case removed; a generator key edited under a drop)
        # is a reuse, and says so
        self.reused_index = not self.rebuilt
        self.build_progress = None
        self.status = "ready"
        self.ready_at = time.time()
        logger.info("index built: fingerprint %s — READY (embedded by %s @ %s, "
                    "%d dims; rebuilt %s)", fingerprint, config.embedding.model,
                    config.embedding.revision, self.encoder.dimension,
                    sorted(self.rebuilt))

    def _load_drop(self) -> tuple[Drop | None, dict | None]:
        """The rii drop at ``decisions.path`` (CP-79), or (None, None) with
        no path — the synthetic 30. Every refused file is logged with its
        reason; a drop with no conforming decision is a startup error."""
        path = self.config.decisions.path
        if path is None:
            return None, None
        try:
            drop = load_drop(path)
        except DecisionError as error:
            raise IngestError(str(error)) from None
        for name, reason in drop.skipped[:20]:
            logger.warning("decisions: %s refused — %s", name, reason)
        if len(drop.skipped) > 20:
            logger.warning("decisions: … and %d more files refused",
                           len(drop.skipped) - 20)
        if not drop.decisions:
            raise IngestError(
                f"decisions.path {path}: no conforming rii-dok v1 decision "
                f"({len(drop.skipped)} file(s) refused — the first: "
                f"{drop.skipped[0] if drop.skipped else 'no .xml files at all'})")
        anomalies = sum(len(d.anomalies) for d in drop.decisions)
        logger.info("decisions: %d decisions read from %s — %d units, %d "
                    "file(s) refused, %d anomalies reported; drop sha256 %s",
                    len(drop.decisions), path, drop.units, len(drop.skipped),
                    anomalies, drop.sha256)
        return drop, drop_component(drop)

    def _reusable(self, stored: str | None, fingerprint: str,
                  wanted: dict[str, str], args: tuple) -> set[str]:
        """Which collections of the stored index are current (CP-79): those
        whose recorded per-collection fingerprint equals the wanted one —
        or every one, when the whole-store fingerprint matches and only a
        failed load brought us here (each is re-loaded and re-checked; the
        corrupt one fails and is rebuilt). A store written before the
        record existed has none; if its whole fingerprint equals this
        config's WITHOUT the decisions drop, its cases (and its synthetic
        decisions) are current and the drop is the only thing that moved —
        every pre-CP-79 store that gains a drop lands here and keeps its
        cases."""
        if stored == fingerprint:
            return set(wanted)
        recorded = read_collection_fingerprints(self.config.index.path)
        if recorded:
            return {name for name, value in wanted.items()
                    if recorded.get(name) == value}
        if stored is not None and self.config.decisions.path is not None \
                and stored == corpus_fingerprint(*args):
            return {name for name in wanted if name != "decisions"}
        return set()

    def _on_batch(self, collection: str, done: int, total: int,
                  batch: int, batches: int) -> None:
        """One add batch landed (CP-77): the operator watching a long build
        sees it move — in the log and in /health — instead of a silent
        hour-long embed (the demo's F-46 shape)."""
        self.build_progress = {"collection": collection, "vectors": done,
                               "total": total, "batch": batch,
                               "batches": batches}
        logger.info("%s: %d/%d vectors embedded and added (batch %d/%d)",
                    collection, done, total, batch, batches)

    def _sweep(self, client) -> None:
        """Remove the HNSW directories earlier rebuilds left behind (CP-77,
        wishlist 66b) — only those no segment row names; see
        ``index.sweep_orphans`` for what is refused and why."""
        removed = sweep_orphans(client)
        if removed:
            logger.warning(
                "swept %d orphaned HNSW director%s (%d bytes) left under "
                "%s/chroma by earlier rebuilds — chromadb 1.5.9 never "
                "removes a dropped collection's directory (CP-77)",
                len(removed), "y" if len(removed) == 1 else "ies",
                sum(size for _, size in removed), self.config.index.path)

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
        # The sweep AFTER the load's own checks (CP-77 review): a store the
        # load refuses — another model's stamp, a count off its sidecar —
        # stays byte-untouched, as the refusal promises; a store that loads
        # sheds what earlier rebuilds left.
        self._sweep(client)
        self.fingerprint = fingerprint
        self.reused_index = True
        self.status = "ready"
        self.ready_at = time.time()

    def _backfill_identity(self, fingerprint: str,
                           collections: dict[str, str]) -> None:
        """A pre-CP-57 store, proven this model's by the fingerprint match
        and the load-time checks: give it the record it lacked — and, since
        CP-79, a store without the per-collection record gets that too (the
        whole-store match proves every collection current). Outside the
        reuse path's corrupt-rebuild catch — a record that cannot be
        written is a warning, never a reason to re-embed a good store
        (CP-57 review)."""
        had_identity = read_store_identity(self.config.index.path) is not None
        if had_identity and read_collection_fingerprints(self.config.index.path):
            return
        identity = self.encoder.identity()
        try:
            write_fingerprint(self.config.index.path, fingerprint, identity,
                              collections=collections)
        except OSError as error:
            logger.warning("stored index predates the %s record and the "
                           "record could not be written (%s) — serving it "
                           "anyway%s", "per-collection" if had_identity
                           else "identity", error,
                           "" if had_identity else "; it is assumed the "
                           "pre-CP-57 pin until the record lands")
            return
        logger.info("stored index predates the %s record — backfilled "
                    "(embedding %s; collections %s)",
                    "per-collection" if had_identity else "identity",
                    identity, sorted(collections))

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
            self.rebuilt = []
            self.build_progress = None
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
        build = self.build_progress  # read once: the init thread clears it
        if build is not None:
            doc["build"] = dict(build)
        if self.status == "ready":
            doc["backend"]["collections"] = (
                len(self.cases) + (1 if self.decisions is not None else 0))
            doc["cases"] = {
                cid: {"pages": idx.n_pages, "chunks": len(idx.chunks),
                      "timesteps": idx.timesteps}
                for cid, idx in sorted(self.cases.items())}
            doc["decisions"] = self.decisions.n_decisions
            if self.decisions.kind == "rii":
                # CP-79: a drop names itself — absent for the synthetic 30
                doc["decisions_drop"] = {
                    "sha256": self.decisions.drop["sha256"],
                    "files": self.decisions.drop["files"],
                    "units": self.decisions.n_units,
                    "pieces": self.decisions.n_pieces,
                    "skipped": len(self.decisions.drop["skipped"]),
                    "surface_version": self.decisions.doc["surface_version"]}
            doc["fingerprint"] = self.fingerprint
            doc["index_reused"] = self.reused_index
            if self.rebuilt:
                doc["rebuilt"] = list(self.rebuilt)
        return doc


def request_log(state: AppState, **fields) -> None:
    """One structured JSON line per tool call (the F-17 lesson, ADR-0040(h)).
    Only the configured fields are emitted, in the configured order."""
    wanted = state.config.server.request_log_fields
    record = {"event": "tool_call"}
    record.update({key: fields.get(key) for key in wanted})
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)
