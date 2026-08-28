[Documentation](../README.md) › Guides

# The retrieval service

The retrieval service — an MCP server, which is why the config key is `mcp_url_base` and the agent's tools are `mcp_gsj_*` — is the estate component that the [timestep cutoff](../concepts/timestep-cutoff.md) depends on: it is the only thing the agent can search, and it decides — server-side, from a signed token — which pages exist for this episode. This page covers what the service serves, how it authenticates each request, how the cutoff is applied to a query, how the index is built and rebuilt, the `config.yaml` and `compose.yml` surface you operate it with, the compatibility contract any replacement backend must honour, and what it does and does not promise about determinism.

The service lives in the repository under `estate/mcp-service/` as the package `gsj_mcp_service`. It is not part of the `gsj-harness-rollout-server` wheel and it imports nothing from `gsj_rollout`; the coupling to the library is the HTTP contract and the token format described here. The server side of the library reaches it through one configuration value, `estate.mcp_url_base` (see [Configuration](configuration.md)).

## What it serves

One long-running process ingests the frozen case dataset from the git host, embeds every page with a pinned MiniLM, stores the vectors in ChromaDB (one collection per case plus one for decisions), and answers token-scoped queries over streamable-http MCP to any number of concurrent episodes.

![Three actors on the left (operator, corpus pipeline, pi) each reach one door of the retrieval service: GET /health with no auth, POST /admin/reindex behind a padlock opened by an admin token, and POST /mcp/token behind a padlock opened by an episode token. Behind the doors sit the health JSON, the reindex thread and the four MCP tools; the tools and the reindex thread point at a ChromaDB store and its sidecar files in a persistent storage lane](../img/mcp-surface.png)

<sub>One process, three doors: the health probe needs no key, the reindex door takes an admin token, the MCP door takes an episode token. Behind them: the readiness JSON, the reuse-or-rebuild thread, and the four tools reading the store.</sub>

Reading the picture row by row:

- **The operator** polls `GET /health` (no auth) until the JSON says `state: "ready"`; the fields are tabulated below.
- **The corpus pipeline** (`ingest_corpus.py ingest`) mints an admin token from the shared secret and calls `POST /admin/reindex`, which starts one background thread — fetch, fingerprint, then reuse the stored index or rebuild it — and answers `202` while `/mcp/*` returns 503 until `/health` is `ready` again (see [`POST /admin/reindex`](#post-adminreindex)).
- **pi, in the sandbox**, reads `url: <mcp_url_base>/mcp/<token>` from `.pi/mcp.json` — the token was minted host-side by the harness — and calls the MCP endpoint, whose four tools pi renders as `mcp_gsj_*`.
- **Storage** is `<index.path>/`, a volume that survives restarts: the ChromaDB store under `chroma/` (one collection per case plus `decisions`) and the sidecar files beside it (`<case_id>/chunks.json`, `decisions/corpus.json`, `fingerprint.json`), described under [Indexing and reindex](#indexing-and-reindex).

The process is `python -m gsj_mcp_service --config config.yaml`, listening on `server.host:server.port`; the shipped file binds `0.0.0.0:8790`.

### The HTTP surface

| route | methods | auth | purpose |
|---|---|---|---|
| `/health` | GET | none | liveness and readiness JSON (fields below) |
| `/admin/reindex` | POST | admin JWT in `Authorization: Bearer` | re-ingest, then reuse or rebuild the index |
| `/mcp/<token>` | POST | per-episode JWT as the last path segment | the MCP endpoint |

The MCP endpoint is the MCP SDK's own streamable-http app, run **stateless** (`stateless_http=True`): every request stands alone, which is what per-request token verification needs. Only POST JSON-RPC is served; a GET (the SSE stream) returns 405. pi's MCP extension is a POST-only client, so this is enough. The token travels in the URL path because that is the one channel the rendered `.pi/mcp.json` carries — the harness writes `url: <mcp_url_base>/mcp/<token>` and the extension uses it verbatim.

`/health` distinguishes liveness from readiness. Liveness is that the process answers at all; readiness is `state: "ready"`. Tool traffic before ready gets a clear error, never empty results.

| field | present | content |
|---|---|---|
| `state` | always | `indexing` \| `ready` \| `error` |
| `uptime_s` | always | seconds since start |
| `progress` | always | per-repo `{done, pages, chunks}`, plus `embedded: true` once a repo has been embedded on a rebuild (absent when the stored index is reused) |
| `embedding` | always | `{model, revision}` |
| `backend` | always | `{name: "chromadb", version}`, plus `collections` (cases + decisions) when ready |
| `error` | on error | the failure message |
| `cases` | ready | per-case `{pages, chunks, timesteps}` |
| `decisions` | ready | decisions corpus size |
| `fingerprint` | ready | the active corpus fingerprint |
| `index_reused` | ready | whether the stored index was reused rather than rebuilt |

```bash
curl -s localhost:8790/health | python -m json.tool     # poll until "state": "ready"
```

### The four tools

The tools are registered unprefixed on an MCP server named `gsj`; pi renders them as `mcp_gsj_search_case` and so on. That server key is load-bearing — it is what the approved tool roster (gate G3) was pinned against, and `checks.py` names the cutoff-scoped tool as `mcp_gsj_search_case`.

![pi on the left calls into two lanes. Inside the cutoff: search_case passes through a funnel labelled filter ≤ T then rank into one collection per case, and case_status reads the same case index to report T. Outside the cutoff: search_decisions ranks the whole decisions collection and decision_stats counts over it](../img/mcp-tools.png)

<sub>Two of the four tools live inside the cutoff — `search_case` is filtered to pages ≤ T before it is ranked, `case_status` reports T — and two are exempt because the decisions corpus has no page structure. Chunks never cross a page, so every hit carries exactly one `page` and one `file`.</sub>

| tool | arguments | returns | cutoff |
|---|---|---|---|
| `search_case` | `query: str`, `k: int = 5` | list of `{"page": int, "file": "md/page_NNNN.md", "score": float, "text": <full page text>}`, ranked over pages `≤ T` only | **scoped** |
| `search_decisions` | `query: str`, `k: int = 5` | list of `{"decision_id", "court", "year", "score", "text"}` | exempt |
| `case_status` | — | `{"case_id", "timestep", "pages_visible", "max_visible_page", "source": "service"}` — the **token's** scope | reports T |
| `decision_stats` | `from_year`, `to_year`, `court` (all optional) | `{"total", "by_year", "by_court"}` | exempt |

`k` is clamped into `[1, search.max_k]`. The decisions corpus is a separate, deterministic collection with no page structure (seeded generation, 30 decisions by default); it is never clamped by the case timestep. Which tools are inside the cutoff and why is discussed in [The timestep cutoff](../concepts/timestep-cutoff.md#what-the-cutoff-does-not-cover).

> [!WARNING]
> **The tool declarations are pinned**
>
> The tool names, signatures (type hints and defaults — the SDK generates the JSON schemas from them) and docstrings in `gsj_mcp_service/tools.py` produce the wire roster that gate G3 hashes. Editing any of them, or bumping the `mcp==2.0.0` SDK pin, changes the roster and every trace fails G3 until the approved sets are deliberately re-pinned. The tool *bodies* are free to change; the declarations are not. See [Pins and approved sets](../concepts/pins.md).

## Authentication

Every `/mcp/<token>` request carries a JWT signed with HMAC-SHA256. The service verifies it with PyJWT (`tokens.py`) on every request, before the SDK app sees anything; the harness mints it with a stdlib implementation (`gsj_rollout/pi_harness.py`), one per episode, on the host.

| claim | type | meaning |
|---|---|---|
| `case_id` | str | the one case this episode may query |
| `timestep` | int | T — the page cutoff, taken from these verified claims **only** |
| `episode_id` | str | the Polar session id; request-log correlation |
| `exp` | int | mint time + TTL (`harness.mcp_token_ttl_s`, default 3600 s), verified with `auth.leeway_s` clock-skew allowance (default 30 s) |

The secret is shared by name, never by value: the harness reads it from the environment variable named by `estate.mcp_token_secret_env` in the gateway process, the service from the variable named by `auth.token_secret_env`. Both default to `GSJ_MCP_TOKEN_SECRET`. The value appears in no config file, no log, no error body and no trace, and it never enters the sandbox.

The agent can read its own token from `.pi/mcp.json`. This is accepted by design: every call the token enables is already scoped to the agent's own case and timestep, the cutoff is decided from the verified claims rather than from any request field, and editing a claim invalidates the signature. The argument is laid out in [The timestep cutoff](../concepts/timestep-cutoff.md#why-the-agent-may-read-its-token-but-cannot-widen-it).

### The admin token

`POST /admin/reindex` is guarded by a JWT signed with the **same** secret but a different claim set: `{"admin": "reindex", "exp": …}`. An episode token never authorizes a reindex (no `admin` claim) and an admin token never authorizes a tool call (no `case_id`). The corpus pipeline's `ingest_corpus.py ingest` mints one with a 300 s TTL; the recipe is plain stdlib:

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

### Error semantics

Verification happens per request in the ASGI wrapper (`app.py`), so a bad request never reaches the MCP layer. The order matters: readiness is checked first, then the token.

| response | when | body |
|---|---|---|
| **503** | `/health` reports `indexing` or `error` — checked before the token | JSON-RPC error naming the state and suggesting a retry after `/health` is `ready` |
| **401** | `/mcp` with no token; tampered payload; wrong-key signature; expired `exp`; malformed JWT; a non-HS256 `alg`; unknown `case_id`; `timestep` outside `1..n_pages` | JSON-RPC error, `code -32001`, echoing the request's `id` when one can be read |
| `ToolError` | in-band failures after transport succeeds, e.g. `case_status` at a timestep leaving no visible pages | an MCP tool-error result, not an HTTP error |
| **405** / **401** on `/admin/reindex` | non-POST / missing or invalid admin token | plain JSON `{"error": …}` |

## How the cutoff is applied

The service indexes the **full** document of every case once and applies the cutoff at query time. This is the crucial design choice: there is no per-timestep index to get out of sync, and the cutoff cannot be widened by the client because the client never states it.

![pi posts to /mcp/token and a five-step strip runs: ready?, verify token, claims → T, filter ≤ T then rank, hits + log. Under the first two steps hang the early exits 503 not ready and 401 bad token; under the rest, the key that carries T, the case collection, and the top-k hits. The hits' result text travels back into the trace, where checks.py gate G5 re-reads it and lands on every page ≤ T or on a page > T](../img/mcp-request-path.png)

<sub>Two early exits, then T from the verified claims, a pre-filter to pages ≤ T before ranking, and hits whose `page` fields are exactly what gate G5 re-reads from the trace — on the receiver, and again in the trainer.</sub>

The result text of every `search_case` call lands verbatim in the trace as the tool result; that is the text `check_page_cutoff` parses. The strip's fourth chevron covers steps 4 and 5 below. One `search_case` call, step by step (`app.py`, `tokens.py`, `tools.py`, `index.py`):

1. **Readiness.** If the state is not `ready`, the request is answered 503 before the token is examined.
2. **Verification.** The token is decoded with `algorithms=["HS256"]` and `exp` required; the claims are type-checked; the case must be in the frozen dataset and `1 ≤ timestep ≤ n_pages`. Any failure is a 401.
3. **Claims.** The verified `TokenClaims` ride a `contextvar` into the tool body. The tool never reads a timestep from its arguments — `search_case(query, k)` has no such parameter.
4. **Pre-filter.** The case's ChromaDB collection is queried with `where={"page": {"$lte": T}}` and `n_results` equal to the whole filtered candidate set, so the filter constrains candidates **before** similarity ranking and the page aggregation sees every candidate's best chunk.
5. **Embed and rank.** The query is embedded by the pinned MiniLM (single-threaded, serialized by a lock, memoized in a small LRU); `score = 1 − cosine_distance`; chunk scores are aggregated to page level by max; pages are sorted by `(−score, page)`; non-positive scores are dropped; the top-k pages are returned with the **full page text**.
6. **Result and log.** Each hit is `{"page", "file", "score", "text"}`, and one structured JSON line goes to stderr: `{"event": "tool_call", "episode_id", "case_id", "timestep", "tool", "k", "n_results", "latency_ms", "cache_hit"}`. Every call is attributable to its episode.

> [!WARNING]
> **Filter before rank, never after**
>
> A post-filter — rank the whole document, then drop pages past T — changes result counts and is the classic leak shape: the ranking already saw the future, and a top-k that was filled with post-cutoff pages comes back short. The service's test suite verifies the pre-filter behaviour against the backend rather than assuming it. Keep this property if you replace the backend.

Because the endpoint is stateless, a single JSON-RPC `tools/call` POST is a complete request — no `initialize` handshake is needed. The service's own tests probe it this way:

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

## Indexing and reindex

### Ingestion

At startup a background thread runs **ingest → fingerprint → reuse-or-rebuild** (`state.py`, `ingest.py`) while `/health` reports progress; any failure lands in `state: "error"` with the message. For each repository in `source.repos` the ingester:

- clones a **bare mirror** into `source.clone_cache_dir` on first start, or `fetch --prune`s it on later starts, using the git CLI (a configured source token is injected into the URL at call time and redacted from any error);
- reads the **full page set from `source.ref_main`** with git plumbing (`ls-tree`, `show`) — never a working-tree checkout — and requires the pages to be contiguous `1..N`;
- records every branch's SHA and parses the recorded timesteps from branches matching `source.ref_pattern` (`timestep-{T}`);
- chunks each page with the pinned MiniLM tokenizer into windows of `chunking.max_tokens` tokens with `chunking.overlap` overlap, mapped back to character offsets so each chunk is a verbatim slice of the page, and **never across a page boundary** — every chunk carries exactly one `page` and one `file`.

The index is one ChromaDB collection per case (named after the case id, cosine space) plus one `decisions` collection, in a persistent store at `<index.path>/chroma/`. Chunk metadata is `{case_id, page, file, chunk_idx}`. Beside the store sit the sidecars the tools need regardless of the vector backend: `<index.path>/<case_id>/chunks.json` (chunk metadata, page texts, refs, timesteps), `<index.path>/decisions/corpus.json`, and `<index.path>/fingerprint.json`.

> [!NOTE]
> **Chroma's own embedder is disabled on purpose**
>
> Chroma's default embedding function is a *different* MiniLM (ONNX) at the same 384 dimensions, so a stray text-side operation would silently mix two implementations. Every collection handle is opened with an embedding function that raises; vectors are always supplied explicitly by the pinned encoder, and the suite asserts that stored vectors are bit-exact the pinned encoder's output.

### The corpus fingerprint and the rebuild policy

Restart idempotence hangs on a sha256 over everything that determines index bytes: each repository's `main` SHA, the embedding model, revision and `normalize` flag, the chunking parameters, the decisions corpus parameters, the index format, and the **ChromaDB version**. A Chroma upgrade that changes the on-disk format therefore rebuilds loudly under `if-stale` and errors under `never` — it never fails silently.

| `index.rebuild` | behaviour |
|---|---|
| `if-stale` (default) | fingerprint matches ⇒ reuse the stored index (unreadable files ⇒ loud rebuild); mismatch ⇒ rebuild with a warning naming both fingerprints |
| `always` | rebuild on every start |
| `never` | a missing or stale index is a startup **error** — the posture for a frozen production deployment |

With the dataset frozen (the corpus pipeline's lock file records it), a fingerprint mismatch should only ever follow a deliberate re-pin: a model revision, a chunking parameter, or the `chromadb` pin. The fingerprint is the only re-index trigger.

### `POST /admin/reindex`

The corpus pipeline calls this after pushing a new estate (`ingest_corpus.py ingest`); you can call it by hand. It re-runs ingest → fingerprint → reuse-or-rebuild in a background thread and gives the same contract a restart would, without a process manager:

| response | meaning |
|---|---|
| `202 {"reindex": "started", "state": "indexing"}` | the state flipped to `indexing` **before** the response; `/mcp/*` answers 503 until `/health` is `ready` again |
| `202 {"reindex": "already-indexing", …}` | one is already running — idempotent, exactly one init thread at a time |
| `401` | missing or invalid admin token |
| `405` | not a POST |

An unchanged corpus is cheap: fetch, fingerprint match, and the stored index is reused rather than re-embedded (`index_reused: true` in `/health`). Under `rebuild: never` a stale corpus lands the service in `state: "error"` — refusing loudly is the intended behaviour for a frozen deployment.

Triggering it by hand is the same three steps the pipeline's `ingest` phase performs — mint, POST, poll:

```python
import json, os, time, urllib.request

base = "http://localhost:8790"
token = mint_admin_token(os.environ["GSJ_MCP_TOKEN_SECRET"])      # the function above
request = urllib.request.Request(f"{base}/admin/reindex", method="POST", data=b"",
                                 headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.status, json.loads(response.read()))          # 202 {'reindex': 'started', 'state': 'indexing'}

while True:
    with urllib.request.urlopen(f"{base}/health", timeout=10) as response:
        health = json.loads(response.read())
    if health["state"] == "ready":
        print("fingerprint", health["fingerprint"], "index_reused", health["index_reused"])
        break
    if health["state"] == "error":
        raise SystemExit(health["error"])
    time.sleep(2)
```

> [!TIP]
> **Replacing the store out of band**
>
> If you delete `<index.path>/chroma/` while the service is running and then trigger a reindex, the service evicts its process-cached Chroma client for that path first, so the rebuild observes the real on-disk store rather than the unlinked one. This keeps `reindex` restart-equivalent.

## Running it: `config.yaml` and `compose.yml`

### Local

```bash
cd estate/mcp-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
export GSJ_MCP_TOKEN_SECRET=<secret>        # required; the value never lands in a file
python -m gsj_mcp_service --config config.yaml
curl -s localhost:8790/health               # poll until "state": "ready"
```

Startup fails fast, exit code 2, with a `ConfigError` naming the file and field on a bad config, and on a missing secret variable. The committed `config.yaml` carries the reference estate's deployment values; on any other host, point `source.base_url` at a git host serving the frozen dataset.

### `config.yaml`

One file, validated at startup with pydantic. Every model is `extra="forbid"` and frozen: an unknown key is a startup error naming the field, never silently ignored. Relative paths resolve against the config file's directory, not the working directory. The schema is `gsj_mcp_service/config.py`.

| section | field | default | notes |
|---|---|---|---|
| `source` | `base_url` | required | git host base URL; a trailing slash is stripped |
| | `owner` | `"gsj-admin"` | owner segment of clone URLs (`<base_url>/<owner>/<repo>.git`); `null` for ownerless trees such as `file://` bares. The shipped file sets `gsj-staging` |
| | `repos` | required, ≥ 1 | the explicit case list — the dataset is frozen, there is no discovery. Each name must be a legal Chroma collection name (3–512 chars of `[a-zA-Z0-9._-]`, alphanumeric at both ends), checked at startup |
| | `ref_main` | `"main"` | the full-document ref pages are read from |
| | `ref_pattern` | `"timestep-{T}"` | must contain the literal `{T}` |
| | `auth_token_env` | `null` | env var **name** holding a git-host token; unset = anonymous read |
| | `clone_cache_dir` | required | the bare-mirror cache |
| `embedding` | `model` | `sentence-transformers/all-MiniLM-L6-v2` | |
| | `revision` | required | the HF revision pin — part of the fingerprint; keep in sync with the Dockerfile's `MINILM_REVISION` bake |
| | `device` | `"cpu"` | |
| | `batch_size` | `32` | corpus-encoding batch size |
| | `normalize` | `true` | `false` is rejected — the cosine backend normalizes internally |
| `chunking` | `max_tokens` | `220` | ≥ 16; below MiniLM's 256-token window including specials |
| | `overlap` | `40` | must be smaller than `max_tokens` |
| | `respect_page_boundaries` | `true` | the only accepted value |
| `index` | `path` | required | the store root: `chroma/` plus the sidecars |
| | `rebuild` | `"if-stale"` | `if-stale` \| `always` \| `never` |
| `search` | `default_k` | `5` | matches the pinned tool signature's `k = 5` |
| | `max_k` | `20` | hard clamp on requested `k` |
| | `method` | `"chroma"` | the only accepted value; the retired `exact` scan is rejected by name |
| `decisions` | `seed` | `20260204` | the deterministic decisions-corpus seed |
| | `corpus_size` | `30` | `30` reproduces the pinned corpus exactly |
| `auth` | `token_secret_env` | `"GSJ_MCP_TOKEN_SECRET"` | env var **name** of the HMAC secret |
| | `leeway_s` | `30` | clock-skew allowance on `exp` |
| `server` | `host` | `"127.0.0.1"` | the shipped file binds `0.0.0.0` so episode containers can reach the host service |
| | `port` | `8790` | |
| | `log_level` | `"info"` | |
| | `request_log_fields` | the eight fields above | fields and order of the per-call log line |
| | `dns_rebinding_protection` | `false` | the SDK's Host-header check (421 on unlisted hosts) |
| | `allowed_hosts` | `[]` | consumed only when the check is on |

> [!NOTE]
> **Why DNS-rebinding protection is off by default**
>
> The per-request token is the security boundary and the clients are not browsers. The legitimate `Host` header varies by channel — `127.0.0.1` on the host, `host.docker.internal:8790` from an episode container, a tunnel host from a workstation — and with the check on, every containerized episode was rejected with 421. Turn it on only with an explicit `allowed_hosts` list.

### `compose.yml` and the image

```yaml
name: gsj-mcp-service
services:
  mcp:
    image: gsj-mcp-service:0.3.0
    container_name: gsj-mcp-service
    network_mode: host
    user: "1000:1000"
    environment:
      GSJ_MCP_TOKEN_SECRET: ${GSJ_MCP_TOKEN_SECRET:?set GSJ_MCP_TOKEN_SECRET in the environment}
    volumes:
      - ./data:/app/data          # clone cache + index survive restarts
    restart: unless-stopped
```

- The `:?` guard refuses to start without `GSJ_MCP_TOKEN_SECRET` in the invoking environment; compose passes the name through and the value never lands in a file.
- `network_mode: host` and `user: "1000:1000"` are the reference estate's answer to a host whose uid-scoped firewall drops published ports and root egress; on such a host the service binds `0.0.0.0:8790` directly and episode containers reach it at `http://host.docker.internal:8790`. Adjust both for your own host — nothing in the service assumes them.
- `./data` holds the clone cache and the index; it is the volume that makes restarts cheap.
- The image bakes the pinned MiniLM snapshot at build time (`MINILM_REVISION`, kept equal to `embedding.revision`) and runs fully offline: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, Chroma telemetry disabled in code.

```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.3.0 estate/mcp-service/
docker save gsj-mcp-service:0.3.0 | ssh <host> docker load     # for a host whose daemon cannot pull
cd estate/mcp-service && GSJ_MCP_TOKEN_SECRET=<secret> docker compose up -d
```

The runtime pins in `requirements.txt` are exact. Two of them are contract: `mcp==2.0.0` (the tool schemas, hence the G3 roster) and `chromadb==1.5.9` (a component of the corpus fingerprint, so a bump forces a loud re-index). See [The estate](estate.md) for where the service sits among the other operator-run components.

## The compatibility contract

Any backend placed behind these four tools — including a production retrieval system — must honour four requirements. The first two are what `gsj_rollout/checks.py` and the cutoff rest on; all four are enforced by the service's test suite (`test_tools.py`, `test_backend.py`, `test_roster_pin.py`), so a replacement inherits executable requirements rather than prose.

1. **The G5 result shape.** Every `search_case` hit carries `"page"` as an integer under the key exactly `page`, and `"file"` exactly `md/page_NNNN.md` with four digits. Gate G5's transcript backstop in `checks.py` re-reads every `mcp_gsj_search_case` result text from the trace with exactly two regexes:

    ```python
    _PAGE_MEMBER = re.compile(r'"page"\s*:\s*(\d+)')
    _PAGE_FILE = re.compile(r"md/page_(\d{4})\.md")
    ```

    Any parsed page greater than T is the finding `G5:search_page_gt_timestep:{page}>{T}`. A backend that renames the key or reformats the path **blinds the gate without failing it** — the regexes match nothing, and a leak goes unreported. This is why the shape is binding.

2. **The cutoff, filter-before-rank.** No text with a page reference greater than T may appear in any returned content. The clamp is structural and server-side: one index per case over the full document, candidates filtered to `page ≤ T` and *then* ranked. T comes from the verified token claims only, never from a request field.

3. **The exemptions are fixed.** `search_decisions` and `decision_stats` are cutoff-exempt; `case_status` reports the token's scope (`checks.py` falls back to its `"timestep"` member when a trace carries no metadata timestep).

4. **The pinned embedder, never the backend's own.** Whatever the backend bundles for embedding is disabled or unreachable; vectors come from the pinned MiniLM revision only, and stored vectors must equal the pinned encoder's output.

The consumer-side delta for a backend swap is one configuration value, `estate.mcp_url_base`. The four tools, the token format and the result shape stay; the rule reasoning behind G5 is in [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md), and the validators themselves in [Validation](../concepts/validation.md).

## Determinism posture

The promise has two halves, and only one is a guarantee.

**Embedding — guaranteed.** MiniLM runs in eval mode with gradients off, single-threaded CPU math (`torch.set_num_threads(1)`), exact float32 arithmetic, and query encoding serialized by a lock. Two fresh processes embedding the same text on the same host produce byte-identical vectors; the suite asserts exactly this.

**Ranking — measured, not guaranteed.** Retrieval is ChromaDB's HNSW index, which by construction forfeits the byte-reproducibility an exact scan would give. Measured across two fresh processes over the same store, a builder against a loader, and two independent builds — ids, order and scores at both tool and chunk level — the results were identical on every probe at the reference corpus's scale (about two hundred chunks, full-candidate-set fetch). A larger corpus, a bounded `n_results`, or a Chroma bump reopens the question. `search.method: exact` is rejected by name at startup precisely so a stale config cannot promise what the backend no longer keeps.

> [!WARNING]
> **Build on the cutoff, not on reproducible ranking**
>
> Do not build anything new on byte-reproducible retrieval. Build on the cutoff, which is structural, and on gate G5, which audits it from the trace.

## See also

- [The timestep cutoff](../concepts/timestep-cutoff.md) — the two walls and the G5 audit this service is one half of
- [The corpus](corpus.md) — the frozen dataset the service ingests, and the pipeline that triggers its reindex
- [The estate](estate.md) — the git host, the inference engine, and where this service sits among them
- [Configuration](configuration.md) — `estate.mcp_url_base`, `estate.mcp_token_secret_env`, `harness.mcp_token_ttl_s`
- [Troubleshooting](troubleshooting.md) — 503 while indexing, 401 on every call, 421 from the Host check
