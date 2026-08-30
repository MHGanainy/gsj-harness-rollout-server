# gsj-mcp-service — the retrieval service

The estate component the timestep cutoff depends on: the only thing the agent can search, deciding server-side — from a signed token — which pages exist for an episode; one long-running process serves the four `gsj` tools over **streamable-http** MCP to any number of concurrent episodes.

The package is `gsj_mcp_service` — not part of the `gsj-harness-rollout-server` wheel, importing nothing from the library (test-enforced); the coupling is the HTTP contract and token format below, reached from the server side through one config value, `estate.mcp_url_base`. Reader-facing guide: [server guide](../../docs/guide/server-guide.md).

## Run it

Locally — any host with a venv and a reachable Forgejo serving the frozen dataset. Startup fails fast — exit code 2, a `ConfigError` naming file and field — on a bad config (unknown keys included: pydantic `extra="forbid"`, all models frozen, relative paths resolved against the config file's directory; source of truth `gsj_mcp_service/config.py`), a missing token secret, or an unset variable named by `source.auth_token_env`. The committed `config.yaml` carries the staging values: `source.base_url: http://172.28.9.10:3000` is the staging Forgejo's static container IP on the H200; from the workstation use `http://localhost:3941` through the staging tunnel.

```bash
cd estate/mcp-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
export GSJ_MCP_TOKEN_SECRET=<secret>     # required; the value never lands in a file
python -m gsj_mcp_service --config config.yaml
curl -s localhost:8790/health            # poll until "state": "ready"
```

On the H200 (Docker) — the image bakes the configured embedding model at build time (`EMBEDDING_MODEL` / `EMBEDDING_REVISION` build args, defaulting to `config.yaml`'s pair; `HF_HOME=/opt/hf-cache`), runs fully offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, Chroma telemetry disabled in code), and ships by `save | load` because the H200 daemon cannot pull:

```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.3.0 estate/mcp-service/   # workstation
docker save gsj-mcp-service:0.3.0 | ssh h200-admin docker load
cd estate/mcp-service && GSJ_MCP_TOKEN_SECRET=<secret> docker compose up -d                     # H200
```

Tag `0.3.0` is the ChromaDB backend (≈310 MB installed over the previous image — transitive onnxruntime, kubernetes, grpcio, none on the runtime path). `compose.yml` is shaped by the H200's uid-scoped firewall: `network_mode: host` binding `0.0.0.0:8790` (published ports do not work — docker-proxy's root-originated forward leg is dropped), `user: "1000:1000"` (root egress is dropped; ingest must clone as uid 1000), `GSJ_MCP_TOKEN_SECRET: ${GSJ_MCP_TOKEN_SECRET:?…}` (compose refuses to start without the secret in the invoking environment), `./data:/app/data` (clone cache and index survive restarts), `restart: unless-stopped`. Episode containers reach the service at `http://host.docker.internal:8790`; the wider estate recipe is [`estate/README.md`](../README.md). Environment: `GSJ_MCP_TOKEN_SECRET` (required — the HMAC secret both sides sign and verify with; the *name* is configurable via `auth.token_secret_env`, the value appears in no config file, log, error body or trace) and, only if set, the variable named by `source.auth_token_env` (a Forgejo token for authenticated pulls; unset = anonymous read).

## The HTTP surface

![Three actors — the operator, the corpus pipeline and pi — each reach one door of the retrieval service: the open health endpoint, the admin-guarded reindex endpoint and the token-guarded MCP endpoint; behind them sit the health JSON, the reindex thread and the four tools, backed by the ChromaDB store and its sidecar files](../../docs/guide/img/mcp-surface.png)

<sub>One process, three doors. One secret signs two claim sets: an episode token opens only the MCP door, an admin token only the reindex door, and the health door has no lock.</sub>

| route | auth | codes |
|---|---|---|
| `GET /health` | none | **200** always — the body says whether the service is ready |
| `POST /admin/reindex` | admin JWT in `Authorization: Bearer` | **202** `{"reindex": "started", "state": "indexing"}` (state flips *before* the response) · **202** `{"reindex": "already-indexing", "state": "indexing"}` (idempotent, one init thread) · **401** `{"error": …}` missing/malformed/expired/wrong-key/non-admin token · **405** any method but POST |
| `POST /mcp/<token>` | per-episode JWT as the last path segment | JSON-RPC error `-32001` as: **503** while `/health` reports `indexing` or `error` (checked *before* the token; the body names the state) · **401** no token, tampered payload, wrong-key signature, expired `exp`, malformed JWT, non-HS256 `alg`, unknown `case_id`, `timestep` outside `1..n_pages` · **405** GET (the SSE stream is not served) · `ToolError` (MCP result, not HTTP) for in-band failures after transport succeeds |
| anything else | — | **404** `not found` (plain text) |

The service listens on `server.host:server.port` (shipped: `0.0.0.0:8790`); the ASGI wrapper in `app.py` owns the URL surface. The MCP endpoint is the SDK's own streamable-http Starlette app run **stateless** (`stateless_http=True`), only POST JSON-RPC served (pi 0.83.0 with pi-mcp-extension 1.5.0 is a POST-only client); the token travels in the URL path because that is the one channel the rendered `.pi/mcp.json` carries — the harness writes `url: <mcp_url_base>/mcp/<token>`. A single `tools/call` POST with `Content-Type: application/json` and `Accept: application/json, text/event-stream` is a complete request, no `initialize` handshake; a rejection echoes the request's `id` when one can be read from the body. `/health` fields — always: `state` (`indexing` | `ready` | `error`), `uptime_s`, `progress` (per-repo `{done, pages, chunks}`, plus `embedded: true` once a repo is embedded on a rebuild), `embedding` `{model, revision, dimension}` (`dimension` is `null` until the model is loaded), `backend` (`{name: "chromadb", version}` plus `collections` when ready); on error: `error` (the failure message); when ready: `cases` (per-case `{pages, chunks, timesteps}`), `decisions` (corpus size), `fingerprint`, `index_reused`. Liveness is answering at all; readiness is `state: "ready"` — the index is built or loaded by a background thread after listening starts, so poll; tool traffic before ready gets a clear 503, never empty results. Request logs: one structured JSON line per tool call to stderr, `{"event": "tool_call", …}` with the fields — and order — of `server.request_log_fields` (`episode_id, case_id, timestep, tool, k, n_results, latency_ms, cache_hit` by default; `cache_hit` is the query-embedding LRU); `episode_id` is the Polar session id, so the log joins to the trace.

## The four tools

Registered unprefixed on an MCP server named `gsj` — the server key is load-bearing, the approved tool roster (gate G3) was pinned against these names; pi renders them `mcp_gsj_search_case` and so on. `k` is clamped into `[1, search.max_k]`; `search_case` aggregates chunk scores to page level (max), sorts by `(−score, page)`, drops non-positive scores and attaches the full page text (`index.py`); the decisions corpus is a separate deterministic collection with no page structure — seeded, 30 decisions by default, each opening with a unique docket reference `AZ-<year>-<court>-<k>` — never clamped by the case timestep.

| tool | arguments | returns | cutoff |
|---|---|---|---|
| `search_case` | `query: str`, `k: int = 5` | list of `{"page": int, "file": "md/page_NNNN.md", "score": float, "text": <full page text>}`, ranked over pages ≤ T only | **scoped** |
| `search_decisions` | `query: str`, `k: int = 5` | list of `{"decision_id", "court", "year", "score", "text"}` | exempt |
| `case_status` | — | `{"case_id", "timestep", "pages_visible", "max_visible_page", "source": "service"}` — the **token's** scope | reports T |
| `decision_stats` | `from_year`, `to_year`, `court` (all optional) | `{"total", "by_year", "by_court"}` | exempt |

> [!WARNING]
> **The tool declarations are pinned.** Names, signatures (type hints and defaults — the SDK generates the JSON schemas from them) and docstrings in `gsj_mcp_service/tools.py` are byte-identical to the retired stdio stub's (commit `bbd4830`), and serving them over streamable-http through real pi reproduces the pinned `tool_roster_hash` `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56` exactly (the wire `tools` array hashed as canonical JSON — the value in `pins/pins.gsj.json`). Any edit — or a bump of the `mcp==2.0.0` pin — changes the wire roster and G3 fails until the approved sets are deliberately re-pinned; the tool *bodies* differ by design (cosine retrieval over the configured encoder, not token overlap), the declarations may not. `tests/test_roster_pin.py` asserts all of this without collecting an episode.

## Authentication and the cutoff

![pi posts to the MCP endpoint and a five-step strip runs: ready, verify the token, take T from the claims, filter to pages at or below T then rank, return the hits and log the call; the first two steps have early exits to 503 and 401, and the result text lands in the trace where gate G5 re-reads every page against T](../../docs/guide/img/mcp-request-path.png)

<sub>One `search_case` call end to end: two early exits, then T from the verified claims, a pre-filter to pages ≤ T before ranking, and hits whose `page` fields are exactly what gate G5 re-reads from the trace — on the receiver, and again in the trainer.</sub>

- **Episode token**: a JWT, HMAC-SHA256, claims `{case_id, timestep, episode_id, exp}` — `case_id` the one case this episode may query, `timestep` is T (taken from these verified claims **only**), `episode_id` the Polar session id (request-log correlation), `exp` = mint time + TTL (`harness.mcp_token_ttl_s`, default 3600 s), verified with `auth.leeway_s` clock-skew allowance (default 30 s). The agent may read its own token in the rendered `.pi/mcp.json` — accepted: every call it enables is already scoped to its own case and timestep, and mutating a claim breaks the signature.
- **Mint/verify split**: the harness mints one token per episode on the host with stdlib HMAC (`gsj_rollout/pi_harness.py` — sign-only by design); the service verifies with PyJWT (`tokens.py`), `algorithms=["HS256"]`, `exp` required — cross-verified byte-identical. The secret is shared by *name*, never by value (`estate.mcp_token_secret_env` / `auth.token_secret_env`, both default `GSJ_MCP_TOKEN_SECRET`); the value never enters the sandbox.
- **Admin token**: the **same** secret, claim set `{"admin": "reindex", "exp": …}` — an episode token never authorizes a reindex (no `admin` claim), an admin token never authorizes a tool call (no `case_id`). `ingest_corpus.py ingest` mints one with plain stdlib at a 300 s TTL; the suite cross-verifies that mint against the real service.
- **Request path** (`app.py`, `tokens.py`, `tools.py`, `index.py`): not `ready` ⇒ 503 before the token is examined; then signature, `exp` and claim types, the case must be in the frozen dataset and `1 ≤ timestep ≤ n_pages` (any failure a 401); the verified claims ride a `contextvar` into the tool body (inherited by the SDK's worker threads, asserted end to end) — `search_case(query, k)` has no timestep parameter.
- **Filter before rank**: the case's collection is queried with `where={"page": {"$lte": T}}` and `n_results` equal to the whole filtered candidate set, so the cutoff constrains candidates **before** similarity ranking and page aggregation sees every candidate's best chunk; queries are embedded by the configured encoder (MiniLM by default; single-threaded, lock-serialized, 256-entry LRU), `score = 1 − cosine_distance`. A post-filter — rank the whole document, then drop pages past T — changes result counts and is the classic leak shape; `tests/test_backend.py` verifies the pre-filter against the backend rather than assuming it. Rule reasoning: [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

## Configuration reference

| key | type | default | meaning |
|---|---|---|---|
| `source.base_url` | `str` | **required** | Forgejo base URL (trailing slash stripped) — the git host is configuration, never code |
| `source.owner` | `str \| None` | `"gsj-admin"` | owner segment of clone URLs; `None` for ownerless URL trees (`file://` bares, as the tests use). Shipped value: `gsj-staging` |
| `source.repos` | `list[str]` | **required** (≥ 1) | explicit case-repo list — the dataset is frozen, no discovery. Each name must name a Chroma collection: 3–512 chars of `[a-zA-Z0-9._-]`, alphanumeric ends — narrower than the corpus contract's `case_id` rule, rejected with the constraint named |
| `source.ref_main` | `str` | `"main"` | the full-document ref pages are read from |
| `source.ref_pattern` | `str` | `"timestep-{T}"` | recorded-timestep ref pattern; must contain the literal `{T}` |
| `source.auth_token_env` | `str \| None` | `None` | env var **name** holding a Forgejo token; unset = anonymous read |
| `source.clone_cache_dir` | `Path` | **required** | bare-mirror clone cache; survives restarts |
| `embedding.model` | `str` | `"sentence-transformers/all-MiniLM-L6-v2"` | the embedding model — a HuggingFace id, any sentence-transformers-loadable checkpoint (shape validated at load: `namespace/name`); the store records which model built it and **refuses to serve under another** until an explicit re-embed (`index.rebuild: always`) — a change is a re-pin, never a silent swap. The dimension is read off the model, assumed nowhere. The default is the model every oracle bound was measured against; a production re-pin owes its own measurement (A-31, wishlist 46) |
| `embedding.revision` | `str` | **required** | the model repo's **full 40-hex commit SHA** — a branch or tag is refused at load (it can move under the index); a corpus-fingerprint component and part of the store's recorded identity; shipped `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, kept in sync with the Dockerfile's `EMBEDDING_REVISION` bake |
| `embedding.device` | `str` | `"cpu"` | torch device |
| `embedding.batch_size` | `int` ≥ 1 | `32` | corpus-encoding batch size |
| `embedding.normalize` | `true` only | `true` | L2-normalize (dot product = cosine); `false` is retired and rejected at startup — Chroma's cosine space normalizes internally and cannot reproduce raw dot-product ranking |
| `chunking.max_tokens` | `int` ≥ 16 | `220` | tokenizer-token window per chunk; must fit the configured model's window minus its special tokens — **checked at startup** with both numbers named, and the real chunks re-checked after ingest (a chunk re-tokenizes a few tokens longer than its window, so leave headroom: 220 leaves 34 under MiniLM's 256; a 100-token-window model needs ≈ 96, not the 98 the static bound admits) |
| `chunking.overlap` | `int` ≥ 0, < `max_tokens` | `40` | window overlap in tokens |
| `chunking.respect_page_boundaries` | `true` only | `true` | **contract** — chunks never span pages, every chunk has exactly one `page`; `false` is not a supported mode (revisit G5's transcript backstop first) |
| `index.path` | `Path` | **required** | index root: `<path>/chroma/` (the persistent store) plus the sidecars `<path>/<case_id>/chunks.json`, `<path>/decisions/corpus.json`, `<path>/fingerprint.json` (the fingerprint **and the store's identity** — `embedding: {model, revision, dimension}`, which model built these vectors) |
| `index.rebuild` | `"if-stale" \| "always" \| "never"` | `"if-stale"` | rebuild policy — below; `always` is also the one sanctioned way to re-embed under a changed `embedding.model` |
| `search.default_k` | `int` ≥ 1 | `5` | default result count (the tool signatures' G3-pinned `k = 5`) |
| `search.max_k` | `int` ≥ 1 | `20` | hard clamp: a requested `k` is clamped into `[1, max_k]` |
| `search.method` | `"chroma"` only | `"chroma"` | ChromaDB/HNSW over the pre-filtered candidate set; the retired `"exact"` (numpy brute-force) is rejected **by name** at startup — it promised byte-reproducibility the backend no longer guarantees |
| `decisions.seed` | `int` | `20260204` | deterministic decisions-corpus seed (`decisions.py`, byte-identical generation to the retired stub's) |
| `decisions.corpus_size` | `int` | `30` | corpus size; `30` reproduces the pinned historical corpus exactly |
| `auth.token_secret_env` | `str` | `"GSJ_MCP_TOKEN_SECRET"` | env var **name** holding the HMAC secret — the name, never a value |
| `auth.leeway_s` | `int` ≥ 0 | `30` | clock-skew allowance on `exp` verification |
| `server.host` | `str` | `"127.0.0.1"` | bind address; staging sets `0.0.0.0` — containers reach host services via `host.docker.internal` only when the bind goes beyond loopback |
| `server.port` | `int` | `8790` | bind port |
| `server.log_level` | `str` | `"info"` | uvicorn/logging level |
| `server.request_log_fields` | `list[str]` | the eight fields above | fields (and order) of the per-call JSON log line |
| `server.dns_rebinding_protection` | `bool` | `false` | the SDK's Host-header check (421 on unlisted hosts). OFF by default: the token is the security boundary, clients are not browsers, the legitimate Host varies by channel — switched on, it rejected every containerized episode |
| `server.allowed_hosts` | `list[str]` | `[]` | Host allowlist (`"host"` or `"host:*"` patterns), consumed only when protection is on |

## Indexing, fingerprints and reindex

- Startup runs **ingest → fingerprint → reuse-or-rebuild** in a background thread while `/health` reports progress (`state.py`, `ingest.py`); any failure lands in `state: "error"` with the message. Per repository: a bare-mirror clone into `source.clone_cache_dir` on first start, `fetch --prune` after (git CLI, 120 s timeout per command; a source token is injected at call time and redacted from errors); pages read from `source.ref_main` with `ls-tree`/`show` — never a checkout — and required contiguous `1..N`; every branch SHA recorded, timesteps parsed from branches matching `source.ref_pattern`; pages chunked with the configured model's tokenizer into verbatim character slices, never across a page boundary (the chunk window is checked against that model's window first). **One index per case over the full document — the cutoff is a query-time filter.**
- The store: one cosine ChromaDB collection per case (named after the case id) plus `decisions`, at `<index.path>/chroma/`; chunk metadata `{case_id, page, file, chunk_idx}`, chunk ids `p<page>c<chunk_idx>` (four digits each); the sidecars sit beside it, and loading cross-checks each collection's count against its sidecar — a mismatch is refused as corrupt. Chroma's own embedder is disabled on purpose (its default embedding function is an fp32 ONNX export of the default MiniLM at the same 384 dimensions — under the default model a near-identical substitute, under any other model an unrelated one): every collection handle opens with an embedding function that raises, vectors always come from the configured encoder, and the suite asserts stored vectors are its output to within the measured bound (max\|Δ\| ≤ 4e-08·√(384/d), cosine ≥ 0.999 — ADR-0016 as amended at CP-55 and CP-57).
- The corpus fingerprint is a sha256 over everything that determines index bytes: each repository's `main` SHA, the embedding model/revision/`normalize`, the chunking parameters, the decisions parameters, `INDEX_FORMAT = 2`, and the **ChromaDB version** (`index.py: corpus_fingerprint`) — a Chroma format change rebuilds loudly under `if-stale` and errors under `never`. Policies: `if-stale` (default) reuses on match (unreadable files ⇒ loud rebuild) and rebuilds on mismatch with a warning naming both fingerprints; `always` rebuilds every start; `never` makes a missing or stale index a startup **error** — the frozen-production posture. With the dataset frozen (`estate/corpus/staging/corpus.lock.json` is the freeze record), a mismatch should only follow a deliberate re-pin; the fingerprint is the only *rebuild* trigger.
- **A model change is refused, not rebuilt over** (CP-57): before the model loads, the store's recorded `embedding {model, revision}` is compared with the config, and any difference lands in `state: "error"` — `EMBEDDING MODEL MISMATCH — refusing to serve …` naming both models, both revisions, the stored dimension and the fix — with the store untouched (under `if-stale` and `never` alike; `/admin/reindex` takes the same path). A model change is a re-pin: re-embedding a production corpus destroys the old store and must be asked for — `index.rebuild: always` for one start (or delete `index.path`). A store written before CP-57 carries no record; exactly one pin built those (the default MiniLM @ `1110a243…`), so it is assumed to be that pin — refused under any other model, and under its own pin proven by the fingerprint and backfilled on first reuse (a record that cannot be written is a warning, never a re-embed). The identity is also stamped into every collection's metadata and compared at load, and one stored vector's width is cross-checked against the loaded model's dimension — so a store whose record was forged or lost, or a `chroma/` directory restored from elsewhere, is refused at startup rather than failing at the first query. A rebuild writes the new model's identity (with no fingerprint) *before* it drops anything, so a rebuild killed midway is refused under the old model and rebuilt under the new, never served. An `embedding.model` HuggingFace cannot resolve, a `chunking.max_tokens` the model cannot hold, or real chunks that re-tokenize past the model's window (a chunk is a character slice that re-tokenizes a few tokens longer than the window it was cut from — measured after each case's ingest) are likewise named startup errors (`EmbeddingModelError: …`).
- `POST /admin/reindex` — called by `ingest_corpus.py ingest` after pushing a new estate (mint, POST, poll `/health` to `ready`), or by hand with an admin token — re-runs the same pipeline in a background thread with restart semantics and no process manager: the state flips to `indexing` before the 202, `/mcp/*` answers 503 until `ready`, a second trigger returns `already-indexing` with no second thread, and an unchanged corpus is cheap — fetch, fingerprint match, stored index reused (`index_reused: true`). Under `rebuild: never` a stale corpus lands in `state: "error"` — refusing loudly is intended.
- Restart-equivalence is real: the trigger evicts the process-cached Chroma system for this store path (a private API of the pinned `chromadb==1.5.9`, scoped to this path only), so a store replaced out-of-band — `rm -rf <index.path>/chroma` before the POST — is observed by the re-init, never served as a phantom from the unlinked inode.

## Determinism

- **Embedding — guaranteed by construction**: the configured model in eval mode, torch grad off, `torch.set_num_threads(1)`, exact float32, query encoding serialized by a lock — two fresh processes embedding the same text on the same host produce byte-identical vectors (`embedding.py`; the suite asserts exactly this).
- **Ranking — measured, not guaranteed**: Chroma/HNSW forfeits exact-scan byte-reproducibility by construction. `tests/measure_determinism.py` (run directly, not a pytest module) compares two fresh processes over the same store, builder vs loader, and two independent builds — ids, order and scores at tool and raw chunk level — and came back **identical on every probe** at this scale (213 chunks, full-candidate-set fetch); `test_identical_results_across_fresh_processes` is the regression canary. A larger corpus, a bounded fetch, or a Chroma bump reopens the question — do not build anything new on byte-reproducible retrieval.

## The compatibility contract

Binding on **any** backend behind these four tools — a production replacement included — and all test-enforced (the wire roster and signature pin `test_roster_pin.py`, the G5 shape `test_tools.py`, the pre-filter and embedder identity `test_backend.py`), so a replacement inherits executable requirements. The consumer-side delta of a swap is **one endpoint value**, `estate.mcp_url_base` — configuration, never code; `gsj_mcp_service` and `gsj_rollout` import nothing from each other at runtime, and the directory can be extracted to its own repository as-is.

- **The G5 result shape**: every `search_case` hit carries `"page"` (int, key exactly `page`) and `"file"` exactly `md/page_NNNN.md` (4 digits). G5's backstop parses the transcript's tool-result texts with two regexes — `"page"\s*:\s*(\d+)` and `md/page_(\d{4})\.md` (`gsj_rollout/checks.py`, inlined in `tests/helpers.py`) — a backend that renames the key or reformats the path blinds the gate.
- **The cutoff, filter-before-rank**: no text with a page reference > T in any returned content; one index per case, candidates filtered to `page ≤ T` **then** ranked; T from the verified token claims only, never a request field.
- **Exemptions and scope**: `search_decisions` and `decision_stats` are cutoff-exempt; `case_status` reports the token's scope.
- **The configured, pinned embedder, never the backend's own**: whatever the backend bundles is disabled or unreachable; vectors come from the configured model at its pinned revision only (stored-vector ≈ encoder-output is asserted to the measured bound), the store records which model built it and refuses to serve under another. A substitution would be silent by construction, so it must be structurally impossible.

## Tests and pins

107 tests across eight modules — config validation (`test_config.py`), ingestion and the rebuild policy (`test_ingest.py`), the pre-filter, embedder identity, the store's identity record, the model-change refusal, the second-model proof and fingerprint (`test_backend.py`), tool behaviour, cutoff visibility and G5 parseability (`test_tools.py`), token rejections and default-`Host` acceptance (`test_auth_http.py`), every `/admin/reindex` path (`test_admin.py`), process lifecycle, 503-before-ready and 12 concurrent sessions with zero cross-talk (`test_processes.py`), the roster pin (`test_roster_pin.py`) — plus the `measure_determinism.py` measurement. The suite spawns real server subprocesses through `.venv/bin/python`, so the venv must live exactly at `estate/mcp-service/.venv`; the git source is built on demand from `estate/corpus/staging` via the pipeline's `file://` rail (cached in `tests/.corpus-bares/`, rebuilt when `corpus.lock.json` changes); the pinned MiniLM is fetched on first embed and the second proof model (`sentence-transformers/paraphrase-albert-small-v2`, ~45 MB, 768 dims) once at suite import, both cached under `~/.cache/huggingface` — with both cached the suite runs `HF_HUB_OFFLINE=1`, so no model load touches the hub.

```bash
cd estate/mcp-service && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q                 # 107 passed
.venv/bin/python tests/measure_determinism.py # the ranking measurement
```

`requirements.txt` is pinned exact: `mcp==2.0.0` (**contract** — the SDK generates the four tool schemas; the roster hash was reproduced with exactly this version), `chromadb==1.5.9` (a fingerprint component — a bump forces a loud re-index), `sentence-transformers==5.7.0`, `torch==2.13.0` (CPU wheels via `--extra-index-url https://download.pytorch.org/whl/cpu`), `numpy==2.5.1`, `pydantic==2.13.4`, `PyJWT==2.13.0`, `PyYAML==6.0.3`, `uvicorn==0.52.1`. The embedding revision pin is `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (`config.yaml`, the Dockerfile's `EMBEDDING_REVISION` and the suite agree).

## Provenance

- Origin and backend: the external gsj MCP service, the predecessor's CP-29/ADR-0040 (the four tools, Spec §2.2); in this repo since CP-01 (ADR-0002), record split scoped at CP-51, audit C1; the stdio stub ADR-0007, retired at CP-32, last-known-good `bbd4830`, server key `gsj` ADR-0007(c), decisions exemption and seed ADR-0007(e); the ChromaDB backend, image `0.3.0`, the ≈310 MB delta, the determinism halves and A-25: CP-15, ADR-0016, ADR-0040(f); the oracle's bound: CP-55; the model as configuration, the store's identity and the refusal: CP-57 (ADR-0016 amendments); the retired `"exact"` method ≤ CP-14; the Chroma default-embedder hazard and test-enforced requirements: the CP-15 lesson; attributable request logs: the F-17 lesson.
- Keys and estate: the predecessor's `mcp_launch.transport/url_base/token_ttl_s` (ADR-0041) → `estate.mcp_url_base`, `estate.mcp_token_secret_env`, `harness.mcp_token_ttl_s`; token minting from `gsj.envloader.task.mint_episode_token`, taken over under Polar (CP-07/CP-10), cross-verified byte-identical at CP-29; the pipeline-scaffolded estate, owner `gsj-staging`, and `/admin/reindex`: CP-33, ADR-0047(d); H200 topology and the `save | load` recipe: CP-29; the roster proof through real pi (POST-only pi 0.83.0 + pi-mcp-extension 1.5.0) and DNS-rebinding protection rejecting every containerized episode: CP-29.
- Laws: git host = config A-08; git via the official CLI ADR-0034; one index per case, query-time cutoff ADR-0040(d); the page-boundary contract ADR-0040(e); readiness vs liveness ADR-0040(h); the production swap and the config-never-code delta law ADR-0040(i); G5 reimplemented in `checks.py` at CP-10 (`docs/checks-spec.md`), the predecessor's `gsj.envloader.gates.extract_case_search_pages` inlined in `tests/helpers.py`.

## See also

- [Server guide](../../docs/guide/server-guide.md) — serve, the one YAML, the estate and this service from the consumer side
- [Validation and pins](../../docs/guide/validation-and-pins.md) — gates G3 and G5, the approved sets, the finding vocabulary
- [Troubleshooting](../../docs/guide/troubleshooting.md) — symptom → cause → fix
