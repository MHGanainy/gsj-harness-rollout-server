# gsj-mcp-service — the retrieval service

The retrieval service is the estate component the timestep cutoff depends on: it is the only thing the agent can search, and it decides — server-side, from a signed token — which pages exist for an episode. One long-running process serves the four `gsj` tools over **streamable-http** MCP to any number of concurrent episodes.

- **Four tools** — `search_case`, `search_decisions`, `case_status`, `decision_stats` — registered on an MCP server named `gsj`; pi renders them as `mcp_gsj_*`.
- **Per-episode JWT in the URL path** — every request is `POST /mcp/<token>`; the service verifies the HMAC-SHA256 signature before the MCP layer sees anything.
- **ChromaDB** — the frozen case dataset is ingested from the git host, embedded with a pinned MiniLM, and stored as one collection per case plus one for decisions.
- **Cutoff as a pre-filter** — the full document is indexed once per case; a query is constrained to `page ≤ T` *before* ranking, with T taken from the verified token claims only.

The package is `gsj_mcp_service`. It is not part of the `gsj-harness-rollout-server` wheel and imports nothing from the library (test-enforced); the coupling is the HTTP contract and the token format documented here. The server side of the library reaches it through one configuration value, `estate.mcp_url_base` — see [Configuration](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/configuration.md). The reader-facing guide for the same component is [The retrieval service](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/retrieval-service.md).

## Run it

### Locally

Any host with a venv and a reachable Forgejo serving the frozen dataset:

```bash
cd estate/mcp-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
export GSJ_MCP_TOKEN_SECRET=<secret>     # required; the value never lands in a file
python -m gsj_mcp_service --config config.yaml
curl -s localhost:8790/health            # poll until "state": "ready"
```

Startup fails fast — exit code 2 with a `ConfigError` naming the file and field — on a bad config, on a missing token secret, or when `source.auth_token_env` names an environment variable that is unset. The committed `config.yaml` carries the staging deployment values: `source.base_url: http://172.28.9.10:3000` is the staging Forgejo's static container IP on the H200. On any other host, point `source.base_url` at a Forgejo serving the frozen dataset — from the workstation that is `http://localhost:3941` through the staging tunnel.

### On the H200 (Docker)

The image bakes the pinned MiniLM snapshot at build time (`MINILM_REVISION` build argument, `HF_HOME=/opt/hf-cache`) and runs fully offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`; Chroma telemetry is disabled in code). It ships by `docker save | docker load` because the H200 daemon cannot pull:

```bash
# workstation
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.3.0 estate/mcp-service/
docker save gsj-mcp-service:0.3.0 | ssh h200-admin docker load
# H200
cd estate/mcp-service && GSJ_MCP_TOKEN_SECRET=<secret> docker compose up -d
```

The image tag `0.3.0` is the ChromaDB backend; its dependency set adds roughly 310 MB installed over the previous image (a measured venv delta, dominated by transitive onnxruntime, kubernetes and grpcio — none on the service's runtime path), so expect a similar image-size delta.

`compose.yml` is shaped by the H200's uid-scoped firewall:

| setting | value | why |
|---|---|---|
| `network_mode` | `host`, binding `0.0.0.0:8790` | published ports do not work there — docker-proxy's root-originated forward leg is dropped |
| `user` | `"1000:1000"` | root egress is dropped, so the ingesting process must run as uid 1000 to clone from the Forgejo container |
| `environment` | `GSJ_MCP_TOKEN_SECRET: ${GSJ_MCP_TOKEN_SECRET:?…}` | compose refuses to start without the secret in the invoking environment; it passes the name through and the value never lands in a file |
| `volumes` | `./data:/app/data` | clone cache and index survive restarts |
| `restart` | `unless-stopped` | |

Episode containers reach the service at `http://host.docker.internal:8790`. The wider estate recipe is [`estate/README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/estate/README.md).

### Environment variables

| variable | required | meaning |
|---|---|---|
| `GSJ_MCP_TOKEN_SECRET` | yes | the HMAC secret both sides sign and verify with; the *name* is configurable (`auth.token_secret_env`), the value appears in no config file, log, error body or trace |
| the variable named by `source.auth_token_env` | only if set | a Forgejo token for authenticated pulls; unset = anonymous read (the staging answer — the repos are public) |

### Health and readiness

Liveness is that the process answers `/health` at all; readiness is `state: "ready"`. The index is built or loaded by a background thread after the process starts listening, so poll:

```bash
curl -s localhost:8790/health | python -m json.tool
```

Tool traffic before ready gets a clear 503, never empty results.

## The HTTP surface

![Three actors — the operator, the corpus pipeline and pi — each reach one door of the retrieval service: the open health endpoint, the admin-guarded reindex endpoint and the token-guarded MCP endpoint; behind them sit the health JSON, the reindex thread and the four tools, backed by the ChromaDB store and its sidecar files](../../docs/guide/img/mcp-surface.png)

<sub>One process, three doors. One secret signs two claim sets: an episode token opens only the MCP door, an admin token only the reindex door, and the health door has no lock.</sub>

The process is `python -m gsj_mcp_service --config config.yaml`, listening on `server.host:server.port` (the shipped file binds `0.0.0.0:8790`). The ASGI wrapper in `app.py` owns the URL surface; the MCP endpoint underneath it is the MCP SDK's own streamable-http Starlette app.

| route | methods | auth | purpose |
|---|---|---|---|
| `/health` | GET | none | liveness and readiness JSON |
| `/admin/reindex` | POST | admin JWT in `Authorization: Bearer` | re-ingest, then reuse or rebuild the index |
| `/mcp/<token>` | POST (JSON-RPC) | per-episode JWT as the last path segment | the MCP endpoint |
| anything else | — | — | `404 not found` (plain text) |

### Status codes

| response | route | when |
|---|---|---|
| **200** | `/health` | always — the body says whether the service is ready |
| **202** `{"reindex": "started", "state": "indexing"}` | `/admin/reindex` | a reindex was started; the state flipped *before* the response |
| **202** `{"reindex": "already-indexing", "state": "indexing"}` | `/admin/reindex` | one is already running — idempotent, exactly one init thread at a time |
| **401** `{"error": …}` | `/admin/reindex` | missing, malformed, expired, wrong-key, or non-admin token |
| **405** `{"error": …}` | `/admin/reindex` | any method but POST |
| **401** JSON-RPC error `-32001` | `/mcp` or `/mcp/` | no token in the path |
| **503** JSON-RPC error `-32001` | `/mcp/<token>` | `/health` reports `indexing` or `error` — checked *before* the token is examined; the body names the state |
| **401** JSON-RPC error `-32001` | `/mcp/<token>` | tampered payload, wrong-key signature, expired `exp`, malformed JWT, a non-HS256 `alg`, unknown `case_id`, `timestep` outside `1..n_pages` |
| **405** | `/mcp/<token>` | GET — the SSE stream is not served |
| `ToolError` (MCP result, not HTTP) | `/mcp/<token>` | in-band failures after transport succeeds, e.g. `case_status` at a timestep leaving no visible pages |

A JSON-RPC rejection echoes the request's `id` when one can be read from the body, so well-behaved clients correlate the failure.

### MCP protocol

The endpoint runs **stateless** (`stateless_http=True`): every request stands alone, which is what per-request token verification needs. Only POST JSON-RPC is served; pi 0.83.0 with pi-mcp-extension 1.5.0 is a POST-only client and works against it. The token travels in the URL path because that is the one channel the rendered `.pi/mcp.json` carries — the harness writes `url: <mcp_url_base>/mcp/<token>` and the extension uses it verbatim. Because the endpoint is stateless, a single `tools/call` POST is a complete request, no `initialize` handshake needed:

```python
import json, urllib.request

def call_search_case(mcp_url_base: str, token: str, query: str, k: int = 5):
    envelope = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "search_case",
                                      "arguments": {"query": query, "k": k}}}).encode()
    request = urllib.request.Request(
        f"{mcp_url_base}/mcp/{token}", data=envelope, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode()
```

### `/health` fields

| field | present | content |
|---|---|---|
| `state` | always | `indexing` \| `ready` \| `error` |
| `uptime_s` | always | seconds since start |
| `progress` | always | per-repo `{done, pages, chunks}`, plus `embedded: true` once a repo has been embedded on a rebuild |
| `embedding` | always | `{model, revision}` |
| `backend` | always | `{name: "chromadb", version}`, plus `collections` (cases + decisions) when ready |
| `error` | on error | the failure message |
| `cases` | ready | per-case `{pages, chunks, timesteps}` |
| `decisions` | ready | decisions corpus size |
| `fingerprint` | ready | the active corpus fingerprint |
| `index_reused` | ready | whether the stored index was reused rather than rebuilt |

### Request logs

One structured JSON line per tool call goes to stderr, `{"event": "tool_call", …}` with the fields — and the order — of `server.request_log_fields`: `episode_id, case_id, timestep, tool, k, n_results, latency_ms, cache_hit` by default (`cache_hit` is the query-embedding LRU). Every call is attributable to its episode, and `episode_id` is the Polar session id, so the log joins to the trace.

## The four tools

The tools are registered unprefixed on a server named `gsj`; pi renders them `mcp_gsj_search_case` and so on. That server key is load-bearing — the approved tool roster (gate G3) was pinned against those names.

| tool | arguments | returns | cutoff |
|---|---|---|---|
| `search_case` | `query: str`, `k: int = 5` | list of `{"page": int, "file": "md/page_NNNN.md", "score": float, "text": <full page text>}`, ranked over pages `≤ T` only | **scoped** |
| `search_decisions` | `query: str`, `k: int = 5` | list of `{"decision_id", "court", "year", "score", "text"}` | exempt |
| `case_status` | — | `{"case_id", "timestep", "pages_visible", "max_visible_page", "source": "service"}` — the **token's** scope | reports T |
| `decision_stats` | `from_year`, `to_year`, `court` (all optional) | `{"total", "by_year", "by_court"}` | exempt |

`k` is clamped into `[1, search.max_k]`. `search_case` aggregates chunk scores to page level (max), returns the top-k pages score-descending with ties by page ascending, drops non-positive scores, and attaches the **full page text** (`index.py`). The decisions corpus is a separate deterministic collection with no page structure — seeded generation, 30 decisions by default, each opening with a docket reference `AZ-<year>-<court>-<k>` unique to it — and is never clamped by the case timestep.

> [!WARNING]
> **The tool declarations are pinned.** The tool names, signatures (type hints and defaults — the SDK generates the JSON schemas from them) and docstrings in `gsj_mcp_service/tools.py` are byte-identical to the retired stdio stub's (the predecessor's, at commit `bbd4830`), and serving them over streamable-http through real pi reproduces the pinned `tool_roster_hash` `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56` exactly (the wire `tools` array captured from pi's request, hashed as canonical JSON — the value in `pins/pins.gsj.json`). Any edit to names, signatures or docstrings — or a bump of the `mcp==2.0.0` SDK pin — changes the wire roster and G3 fails until the approved sets are deliberately re-pinned. The tool *bodies* differ from the stub by design (MiniLM cosine retrieval instead of token overlap); the declarations may not. `tests/test_roster_pin.py` asserts all of this without collecting an episode.

## Authentication and the cutoff

![pi posts to the MCP endpoint and a five-step strip runs: ready, verify the token, take T from the claims, filter to pages at or below T then rank, return the hits and log the call; the first two steps have early exits to 503 and 401, and the result text lands in the trace where gate G5 re-reads every page against T](../../docs/guide/img/mcp-request-path.png)

<sub>One `search_case` call end to end: two early exits, then T from the verified claims, a pre-filter to pages ≤ T before ranking, and hits whose `page` fields are exactly what gate G5 re-reads from the trace — on the receiver, and again in the trainer.</sub>

### The episode token

A JWT, HMAC-SHA256, claims `{case_id, timestep, episode_id, exp}`:

| claim | type | meaning |
|---|---|---|
| `case_id` | str | the one case this episode may query |
| `timestep` | int | T — the page cutoff, taken from these verified claims **only** |
| `episode_id` | str | the Polar session id; request-log correlation |
| `exp` | int | mint time + TTL (the harness's `harness.mcp_token_ttl_s`, default 3600 s), verified with `auth.leeway_s` clock-skew allowance (default 30 s) |

**Mint/verify split.** The harness mints one token per episode on the host with a stdlib HMAC implementation (`gsj_rollout/pi_harness.py` — sign-only by design); the service verifies with PyJWT (`tokens.py`), `algorithms=["HS256"]` and `exp` required, and the two have been cross-verified byte-identical. The secret is shared by name, never by value: the harness reads the variable named by `estate.mcp_token_secret_env`, the service the one named by `auth.token_secret_env`; both default to `GSJ_MCP_TOKEN_SECRET`. The value never enters the sandbox.

**The agent may read its own token** from the rendered `.pi/mcp.json`. This is accepted and documented: every call the token enables is already scoped to its own episode's case and timestep, the cutoff is decided from the verified claims rather than any request field, and mutating a claim breaks the signature.

### The admin token

`POST /admin/reindex` is guarded by a JWT signed with the **same** secret but the claim set `{"admin": "reindex", "exp": …}`. An episode token never authorizes a reindex (no `admin` claim) and an admin token never authorizes a tool call (no `case_id`). The corpus pipeline's `ingest_corpus.py ingest` mints one with a 300 s TTL using plain stdlib, and the suite cross-verifies that mint against the real service:

```python
import base64, hashlib, hmac, json, os, time

def mint_admin_token(secret: str, ttl_s: int = 300) -> str:
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=")
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64(json.dumps({"admin": "reindex", "exp": int(time.time()) + ttl_s},
                             separators=(",", ":")).encode())
    signing_input = header + b"." + payload
    signature = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()

token = mint_admin_token(os.environ["GSJ_MCP_TOKEN_SECRET"])
```

### How the cutoff is applied

Verification happens per request in the ASGI wrapper, before the SDK app is reached; the verified claims ride a `contextvar` into the tool body (the SDK's tool worker threads inherit it, which the concurrency test asserts end to end). One `search_case` call, step by step (`app.py`, `tokens.py`, `tools.py`, `index.py`):

1. **Readiness.** If the state is not `ready`, the request is answered 503 before the token is examined.
2. **Verification.** Signature, `exp` and claim types are checked; the case must be in the frozen dataset and `1 ≤ timestep ≤ n_pages`. Any failure is a 401.
3. **Claims → T.** The tool never reads a timestep from its arguments — `search_case(query, k)` has no such parameter.
4. **Pre-filter.** The case's collection is queried with `where={"page": {"$lte": T}}` and `n_results` equal to the whole filtered candidate set, so the filter constrains candidates **before** similarity ranking and the page aggregation sees every candidate's best chunk.
5. **Embed and rank.** The query is embedded by the pinned MiniLM (single-threaded, serialized by a lock, memoized in a 256-entry LRU); `score = 1 − cosine_distance`; chunk scores aggregate to page max; pages sort by `(−score, page)`; non-positive scores are dropped; the top-k pages come back with full page text.
6. **Result and log.** Each hit is `{"page", "file", "score", "text"}` and one request-log line goes to stderr.

> [!WARNING]
> **Filter before rank, never after.** A post-filter — rank the whole document, then drop pages past T — changes result counts and is the classic leak shape. `tests/test_backend.py` verifies the pre-filter behaviour against the backend rather than assuming it.

## Configuration reference

One `config.yaml`, validated at startup with pydantic: `extra="forbid"` everywhere, so an unknown key is a startup error naming file and field, never silently ignored; all models are frozen. Relative paths resolve against the config file's directory, not the cwd. Source of truth: `gsj_mcp_service/config.py`.

### `source:` — where the frozen dataset lives

| field | type | default | meaning |
|---|---|---|---|
| `base_url` | `str` | **required** | Forgejo base URL (a trailing slash is stripped) — deployment topology, so the git host is configuration, never code |
| `owner` | `str \| None` | `"gsj-admin"` | owner segment of clone URLs; `None` for ownerless URL trees (`file://` bares, as the test suite uses). The shipped `config.yaml` sets `gsj-staging` — the pipeline-scaffolded estate |
| `repos` | `list[str]` | **required** (≥ 1) | explicit case-repo list — the dataset is frozen, there is no discovery. Each name must be able to name a Chroma collection: 3–512 characters from `[a-zA-Z0-9._-]`, starting and ending alphanumeric — narrower than the corpus contract's `case_id` rule, rejected here with the constraint named |
| `ref_main` | `str` | `"main"` | the full-document ref pages are read from |
| `ref_pattern` | `str` | `"timestep-{T}"` | discovery pattern for the recorded timestep refs; must contain the literal `{T}` |
| `auth_token_env` | `str \| None` | `None` | env var **name** holding a Forgejo token for authenticated pulls; unset = anonymous read |
| `clone_cache_dir` | `Path` | **required** | bare-mirror clone cache; survives restarts |

### `embedding:`

| field | type | default | meaning |
|---|---|---|---|
| `model` | `str` | `"sentence-transformers/all-MiniLM-L6-v2"` | the embedding model |
| `revision` | `str` | **required** | HF revision pin — part of the corpus fingerprint; the shipped value is `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, kept in sync with the Dockerfile's `MINILM_REVISION` bake |
| `device` | `str` | `"cpu"` | torch device |
| `batch_size` | `int` (≥ 1) | `32` | corpus-encoding batch size |
| `normalize` | `bool`, `true` only | `true` | L2-normalize embeddings (dot product = cosine). `false` is retired and rejected at startup: the Chroma cosine space normalizes internally and cannot reproduce raw dot-product ranking |

### `chunking:`

| field | type | default | meaning |
|---|---|---|---|
| `max_tokens` | `int` (≥ 16) | `220` | tokenizer-token window per chunk (below MiniLM's 256 including specials) |
| `overlap` | `int` (≥ 0, < `max_tokens`) | `40` | window overlap in tokens |
| `respect_page_boundaries` | `Literal[true]` | `true` | **contract** — chunks never span pages, so every chunk has exactly one `page`; `false` is not a supported mode (a backend wanting cross-page chunks must revisit G5's transcript backstop first) |

### `index:`

| field | type | default | meaning |
|---|---|---|---|
| `path` | `Path` | **required** | index storage root: `<path>/chroma/` (the ChromaDB persistent store — one collection per case plus `decisions`) and the sidecars `<path>/<case_id>/chunks.json`, `<path>/decisions/corpus.json`, `<path>/fingerprint.json` |
| `rebuild` | `"if-stale" \| "always" \| "never"` | `"if-stale"` | rebuild policy — see [the rebuild policy](#the-corpus-fingerprint-and-the-rebuild-policy) |

### `search:`

| field | type | default | meaning |
|---|---|---|---|
| `default_k` | `int` (≥ 1) | `5` | default result count (the tool signatures' `k = 5` — G3-pinned) |
| `max_k` | `int` (≥ 1) | `20` | hard clamp: a requested `k` is clamped into `[1, max_k]` |
| `method` | `"chroma"` only | `"chroma"` | ChromaDB/HNSW over the cutoff-pre-filtered candidate set. The retired `"exact"` (a numpy brute-force scan) is rejected **by name** at startup — it promised byte-reproducibility the backend no longer guarantees; any other value is rejected too |

### `decisions:`

| field | type | default | meaning |
|---|---|---|---|
| `seed` | `int` | `20260204` | the deterministic decisions-corpus seed (`decisions.py`, byte-identical generation to the retired stub's) |
| `corpus_size` | `int` | `30` | corpus size; `30` reproduces the pinned historical corpus exactly |

### `auth:`

| field | type | default | meaning |
|---|---|---|---|
| `token_secret_env` | `str` | `"GSJ_MCP_TOKEN_SECRET"` | env var **name** holding the HMAC secret — the name, never a value |
| `leeway_s` | `int` (≥ 0) | `30` | clock-skew allowance on `exp` verification |

### `server:`

| field | type | default | meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | bind address. The staging file sets `0.0.0.0`: on the H200, containers reach host services via `host.docker.internal` only when the service binds beyond loopback |
| `port` | `int` | `8790` | bind port |
| `log_level` | `str` | `"info"` | uvicorn/logging level |
| `request_log_fields` | `list[str]` | `[episode_id, case_id, timestep, tool, k, n_results, latency_ms, cache_hit]` | fields (and order) of the per-call JSON log line |
| `dns_rebinding_protection` | `bool` | `false` | the SDK's Host-header check (421 on unlisted hosts). OFF by default: the token is the security boundary, clients are not browsers, and the legitimate Host varies by channel (`127.0.0.1`, `host.docker.internal:<port>`, tunnel hosts) — switched on, it rejected every containerized episode |
| `allowed_hosts` | `list[str]` | `[]` | Host allowlist (`"host"` or `"host:*"` patterns), consumed only when `dns_rebinding_protection: true` |

## Indexing, fingerprints and reindex

### Ingestion

At startup a background thread runs **ingest → fingerprint → reuse-or-rebuild** (`state.py`, `ingest.py`) while `/health` reports progress; any failure lands in `state: "error"` with the message. For each repository in `source.repos` the ingester:

- clones a **bare mirror** into `source.clone_cache_dir` on first start, or `fetch --prune`s it on later starts, through the git CLI (each command has a 120 s timeout; a configured source token is injected into the URL at call time and redacted from any error);
- reads the **full page set from `source.ref_main`** with git plumbing (`ls-tree`, `show`) — never a working-tree checkout — and requires the pages to be contiguous `1..N`;
- records every branch's SHA and parses the recorded timesteps from branches matching `source.ref_pattern`;
- chunks each page with the pinned MiniLM tokenizer into windows of `chunking.max_tokens` tokens with `chunking.overlap` overlap, mapped back to character offsets so each chunk is a verbatim slice of the page, **never across a page boundary** — every chunk carries exactly one `page` and one `file`.

**One index per case over the full document — not per timestep.** The cutoff is a query-time filter.

### The store

One ChromaDB collection per case (named after the case id, cosine space) plus one `decisions` collection, in a persistent store at `<index.path>/chroma/`. Chunk metadata is `{case_id, page, file, chunk_idx}`; chunk ids are `p<page>c<chunk_idx>` (four digits each). Beside the store sit the sidecars the tools need regardless of the vector backend: `<case_id>/chunks.json` (chunk metadata, page texts, refs, timesteps), `decisions/corpus.json`, and `fingerprint.json`. Loading a stored index cross-checks each collection's count against its sidecar and refuses a mismatch as corrupt.

> [!NOTE]
> **Chroma's own embedder is disabled on purpose.** Chroma's default embedding function is a *different* MiniLM (ONNX) at the same 384 dimensions, so a stray text-side operation would silently mix two implementations. Every collection handle is opened with an embedding function that raises; vectors are always supplied explicitly by the pinned encoder, and the suite asserts that stored vectors are bit-exact the pinned encoder's output.

### The corpus fingerprint and the rebuild policy

Restart idempotence hangs on a sha256 over everything that determines index bytes: each repository's `main` SHA, the embedding model, revision and `normalize` flag, the chunking parameters, the decisions corpus parameters, the index format (`INDEX_FORMAT = 2`), and the **ChromaDB version** (`index.py: corpus_fingerprint`). A Chroma upgrade that changes the on-disk format therefore rebuilds loudly under `if-stale` and errors under `never` — never a silent failure.

| `index.rebuild` | behaviour |
|---|---|
| `if-stale` (default) | fingerprint match ⇒ reuse the stored index (unreadable files ⇒ loud rebuild); mismatch ⇒ rebuild with a warning naming both fingerprints |
| `always` | rebuild on every start |
| `never` | a missing or stale index is a startup **error** — the posture for a frozen production deployment |

With the dataset frozen (`estate/corpus/staging/corpus.lock.json` is the pipeline's freeze record), a fingerprint mismatch should only ever follow a deliberate re-pin: a model revision, a chunking parameter, or the `chromadb` pin. The fingerprint is the only re-index trigger.

### `POST /admin/reindex`

The corpus pipeline calls this after pushing a new estate (`ingest_corpus.py ingest` — mint, POST, poll `/health` to `ready`); you can call it by hand with the admin token above. It re-runs ingest → fingerprint → reuse-or-rebuild in a background thread and gives the same contract a restart would, without a process manager: the state flips to `indexing` before the `202` is sent, `/mcp/*` answers 503 until `/health` is `ready` again, and a second trigger while one runs returns `already-indexing` and spawns no second thread. An unchanged corpus is cheap — fetch, fingerprint match, and the stored index is reused rather than re-embedded (`index_reused: true`). Under `rebuild: never` a stale corpus lands the service in `state: "error"`; refusing loudly is the intended behaviour for a frozen deployment.

Restart-equivalence is real: the trigger evicts the process-cached Chroma system for this store path (a private API of the pinned `chromadb==1.5.9`, scoped to this path only), so a store replaced out-of-band — `rm -rf <index.path>/chroma` before the POST — is observed by the re-init instead of being served as a phantom from the unlinked inode.

## Determinism

Two halves. **Embedding — guaranteed by construction**: MiniLM in eval mode, torch grad off, `torch.set_num_threads(1)`, exact float32 arithmetic, query encoding serialized by a lock — two fresh processes embedding the same text on the same host produce byte-identical vectors (`embedding.py`; the suite asserts exactly this). **Ranking — measured, not guaranteed**: retrieval is Chroma/HNSW, which forfeits the exact-scan byte-reproducibility promise by construction. `tests/measure_determinism.py` (run directly, not a pytest module) compares two fresh processes over the same store, builder versus loader, and two independent builds — ids, order and scores at tool level and at raw chunk level — and came back **identical on every probe** at this scale (213 chunks, full-candidate-set fetch). `test_identical_results_across_fresh_processes` is the regression canary. A larger corpus, a bounded fetch, or a Chroma bump reopens the question: do not build anything new on byte-reproducible retrieval.

## The compatibility contract

Binding on **any** backend behind these four tools — a production replacement included:

1. **The G5 result shape.** Every `search_case` hit carries `"page"` (int, key exactly `page`) and `"file"` exactly `md/page_NNNN.md` (4 digits). Gate G5's backstop parses the transcript's tool-result texts with two regexes — `"page"\s*:\s*(\d+)` and `md/page_(\d{4})\.md` (`gsj_rollout/checks.py`, inlined in `tests/helpers.py`) — and a backend that renames the key or reformats the path blinds the gate. Rule reasoning: [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).
2. **The cutoff, filter-before-rank.** No text with a page reference > T may appear in any returned content. The structural clamp is server-side: one index per case, candidates filtered to `page ≤ T` **then** ranked — a post-filter changes result counts and is the classic leak shape. T comes from the verified token claims only, never from a request field.
3. **Exemptions and scope.** `search_decisions` and `decision_stats` are cutoff-exempt; `case_status` reports the token's scope.
4. **The pinned embedder, never the backend's own.** Whatever the backend bundles for embedding is disabled or unreachable; vectors come from the pinned MiniLM revision only, and the suite asserts stored-vector == pinned-encoder-output identity. Chroma's default embedding function is a different MiniLM at the *same* 384 dimensions — a substitution would be silent by construction, so it must be structurally impossible.

The load-bearing requirements are test-enforced in this suite — the wire roster against the pinned `tool_roster_hash` plus the source-level signature pin (`test_roster_pin.py`), the G5 result shape (`test_tools.py`), the cutoff pre-filter and the embedder identity (`test_backend.py`) — so a replacement backend inherits executable requirements, not just this prose.

### Replacing the backend

A real retrieval backend goes behind the same four tools, the same token format, and the same result shape. The consumer-side delta is **one endpoint value** — `estate.mcp_url_base` in the server configuration — configuration, never code. `gsj_mcp_service` imports nothing from `gsj_rollout` at runtime and the library imports nothing from it; the directory can be extracted to its own repository as-is.

## Tests

89 tests across eight modules, plus the determinism measurement:

| module | covers |
|---|---|
| `test_config.py` | validation: unknown keys anywhere, missing fields and sections, `respect_page_boundaries: false`, `overlap ≥ max_tokens`, relative-path resolution, unset secret, the retired `exact` and `normalize: false`, Chroma-unsafe repo names, `ref_pattern` without `{T}` |
| `test_ingest.py` | contiguous pages, one page per chunk, timesteps from refs, second-process index reuse, fingerprint mismatch rebuilds, `rebuild: never` with a missing or stale index |
| `test_backend.py` | the pre-filter (chunk and tool level), stored vectors bit-exact the pinned encoder's, text ops refused, the Chroma version in the fingerprint, a Chroma-version change rebuilds loudly, reindex after out-of-band store replacement, backend identity in `/health`, no corpus-tree path literal in the source |
| `test_tools.py` | listing and calling the tools, beyond-cutoff facts stay hidden, page = T is visible, positive sorted scores, decisions ignore the cutoff, `decision_stats` totals and filters, `k` clamps, result texts parse with the G5 extractor, no library import at runtime |
| `test_auth_http.py` | tampered payloads, expiry, wrong key, missing token, unknown case, timestep out of range, garbage tokens, `id` echo, foreign `Host` accepted by default |
| `test_admin.py` | every rejection of `/admin/reindex`, the round trip through `indexing` back to `ready` with the same fingerprint, the pipeline's stdlib mint verifying, concurrent triggers idempotent |
| `test_processes.py` | `indexing` observed before `ready`, the ready `/health` shape, 503 before ready, the error state on a bad source, identical results across fresh processes, 12 concurrent sessions with zero cross-talk |
| `test_roster_pin.py` | the captured wire roster hashes into the pin, live declarations reproduce the captured entries byte for byte, the source-level input schemas, `k = 5` served by default |
| `measure_determinism.py` | not a test — the ranking-determinism measurement, run directly |

The suite spawns real server subprocesses through `.venv/bin/python`, so the venv must live exactly at `estate/mcp-service/.venv`; `pytest` is installed on top of `requirements.txt`. The git source is built on demand from `estate/corpus/staging` through the corpus pipeline's own `file://` rail (cached in `tests/.corpus-bares/`, rebuilt when `corpus.lock.json` changes), and the four-case index is embedded once per session and reused by every server afterwards. The pinned MiniLM is fetched from Hugging Face on the first embed and cached under `~/.cache/huggingface`.

```bash
cd estate/mcp-service
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q                 # 89 passed
.venv/bin/python tests/measure_determinism.py # the ranking measurement
```

### Pins

`requirements.txt` is pinned exact:

| package | version | note |
|---|---|---|
| `mcp` | 2.0.0 | **contract** — the SDK generates the four tool schemas; the roster hash was reproduced with exactly this version |
| `sentence-transformers` | 5.7.0 | |
| `torch` | 2.13.0 | CPU wheels via `--extra-index-url https://download.pytorch.org/whl/cpu` |
| `numpy` | 2.5.1 | |
| `chromadb` | 1.5.9 | the version is a fingerprint component — a bump forces a loud re-index |
| `pydantic` | 2.13.4 | |
| `PyJWT` | 2.13.0 | |
| `PyYAML` | 6.0.3 | |
| `uvicorn` | 0.52.1 | |

The embedding revision pin is `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (`config.yaml`, the Dockerfile, and the test suite agree).

## Provenance

The checkpoint and decision records behind the facts above are private; the citations the previous text carried are kept here, verbatim, so nothing is lost.

- The service's origin: "the external gsj MCP service (CP-29, ADR-0040)" — built in the predecessor, `gsj-envloader` @ v0.8.0; "the four `gsj` tools (Spec §2.2)".
- The retired per-session stdio stub it replaced: "ADR-0007 — retired at CP-32, last-known-good commit `bbd4830`".
- Which records belong to which repository: "the ADR-0007/0034/0040/0041/0047, CP-29/32/33 and A-08 cites are the predecessor's, `gsj-envloader` @ v0.8.0, where the service was built; CP-10/14/15, ADR-0016 and A-25 are this repo's, which has maintained it since its CP-01, ADR-0002 — scoped at CP-51, audit C1".
- The ChromaDB backend, one collection per case with the cutoff as a metadata pre-filter: "CP-15, ADR-0016"; image tag "0.3.0 = CP-15: the ChromaDB backend"; the ≈310 MB installed delta is CP-15's measurement.
- The consumer side in the predecessor: "`mcp_launch.transport: streamable-http` (ADR-0041, `docs/config-reference.md`)", with the TTL as `mcp_launch.token_ttl_s` and the endpoint as `mcp_launch.url_base`; in this repository the keys are `estate.mcp_url_base`, `estate.mcp_token_secret_env` and `harness.mcp_token_ttl_s`.
- The estate scaffolded from `estate/corpus/staging` by `estate/corpus/ingest_corpus.py`, owner `gsj-staging`: "since CP-33 … (ADR-0047)".
- The H200 topology (host networking, uid 1000, `host.docker.internal`, the `localhost:3941` tunnel) and the `save | load` recipe: "measured at CP-29 — the predecessor's `staging/README.md`"; "the same recipe as the sandbox image, the predecessor's `docs/publishing.md`".
- `/admin/reindex`: "CP-33, ADR-0047(d)".
- pi 0.83.0 + pi-mcp-extension 1.5.0 as a POST-only client: "proven live, CP-29".
- The server key `gsj` being load-bearing for the `mcp_gsj_*` names: "ADR-0007(c)".
- The decisions tools being cutoff-exempt: "ADR-0007(e)"; the decisions corpus seed "carried over byte-identical (ADR-0007)".
- The roster proof: "CP-29 Step 1 proved that serving them over streamable-http through real pi reproduces the pinned `tool_roster_hash` … exactly (wire tools array captured from pi's request, hashed with the pin layer's `sha256_canonical_json`)"; "until a deliberate `gsj-pin` re-pin".
- Token minting: "in the predecessor, `gsj.envloader.task.mint_episode_token`, a stdlib-HMAC implementation — sign-only by design; this repo's harness takes over minting when episodes run under Polar, CP-07/CP-10"; "cross-verified byte-identical at CP-29".
- The git host as configuration: "the A-08 'git host = CONFIG' posture".
- `respect_page_boundaries` as a contract: "ADR-0040(e)"; git via the CLI: "the official client, ADR-0034 prior-art"; one index per case with a query-time cutoff: "ADR-0040(d), the ADR-0007 leaky-server posture carried over".
- The retired `"exact"` search method: "numpy brute-force, ≤ CP-14"; reproducibility as a measured assumption: "the ADR-0040(f) assumption row is A-25: reproducibility is measured, not promised".
- DNS-rebinding protection off by default: "ON it rejected every containerized episode at CP-29".
- Determinism in two halves and the measurement: "since CP-15 (ADR-0016)"; "the CP-15 measurement (`tests/measure_determinism.py` …) came back IDENTICAL on every probe … recorded as assumption row A-25".
- Readiness distinct from liveness: "ADR-0040(h)"; the `backend` health field: "CP-15"; attributable request logs: "the F-17 lesson (silent collection) applied pre-emptively".
- The G5 backstop in this repository: "this repo's `checks.py` reimplements them at CP-10, `docs/checks-spec.md`"; the predecessor's `gsj.envloader.gates.extract_case_search_pages`, "inlined in this repo's `tests/helpers.py`".
- Chroma's default embedding function as the silent-substitution hazard: "the CP-15 lesson"; the requirements becoming test-enforced: "since CP-15".
- The production swap and the delta law: "ADR-0040(i)"; "the delta law (CLAUDE.md law 7) holding at the service boundary: CONFIG, never CODE".
- The directory moving from the predecessor into this repository as-is: "at CP-01 (ADR-0002)".
