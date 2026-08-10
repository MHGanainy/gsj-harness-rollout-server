# mcp-service — the external gsj MCP service (CP-29, ADR-0040)

The standalone retrieval service the Spec always assumed and dev never had:
the four `gsj` tools (Spec §2.2) served over **streamable-http** to any
number of concurrent episodes, replacing the per-session stdio stub
(ADR-0007 — retired at CP-32, last-known-good commit `bbd4830`; CP/ADR
numbers in this file are the predecessor's, `gsj-envloader` @ v0.8.0 —
maintained here since this repo's CP-01, ADR-0002) with one
long-running process. It
ingests the frozen case dataset from staging Forgejo (the estate scaffolded
from `corpus/staging` by `corpus/ingest_corpus.py`; freeze record
`corpus/staging/corpus.lock.json`), embeds it with a pinned MiniLM, and answers
token-scoped queries — the page cutoff enforced server-side from verified
per-episode JWT claims, never from anything the client says. It imports
nothing from `gsj.envloader`; the coupling to the library is the HTTP
contract and the token format only. Consumer side: `mcp_launch.transport:
streamable-http` (ADR-0041, `docs/config-reference.md`).

## Quick start

Local, any host (a venv and a reachable Forgejo):

```bash
cd mcp-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
export GSJ_MCP_TOKEN_SECRET=<secret>     # required; the value never lands in a file
python -m gsj_mcp_service --config config.yaml
curl -s localhost:8790/health            # poll until "state": "ready"
```

The committed `config.yaml` carries the **staging deployment values** (H200
— `source.base_url: http://172.28.9.10:3000` is the staging Forgejo's
static container IP). On any other host, point `source.base_url` at a
Forgejo serving the frozen dataset — from the workstation that is
`http://localhost:3941` through the staging tunnel (the predecessor's
`staging/README.md`).
Startup fails fast with a named-field `ConfigError` on a bad config or a
missing secret env var.

On the H200 (compose — the image ships by `save | load` because the H200
daemon cannot pull, same recipe as the sandbox image, the predecessor's
`docs/publishing.md`):

```bash
# workstation
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t gsj-mcp-service:0.2.0 mcp-service/
docker save gsj-mcp-service:0.2.0 | ssh h200-admin docker load
# H200
cd mcp-service && GSJ_MCP_TOKEN_SECRET=<secret> docker compose up -d
```

`compose.yml` refuses to start without `GSJ_MCP_TOKEN_SECRET` in the
invoking environment (`:?` guard — compose passes the name through, the
value never lands in a file). It runs `network_mode: host` + `user:
"1000:1000"`, binding `0.0.0.0:8790` — both forced by the H200's measured
uid-scoped firewall (published ports do not work there; root egress is
dropped, so the ingesting process must run as uid 1000 — the full topology
is the predecessor's `staging/README.md`). `./data` (clone cache + index) is a volume and
survives restarts. The image bakes the pinned MiniLM snapshot at build time
and runs fully offline (`HF_HUB_OFFLINE=1`).

## The HTTP contract

| endpoint | methods | auth | purpose |
|---|---|---|---|
| `/health` | GET | none | liveness + readiness JSON (states below) |
| `/admin/reindex` | POST | admin JWT, `Authorization: Bearer` | re-ingest + reuse-or-rebuild (CP-33, ADR-0047(d)) |
| `/mcp/<token>` | POST | per-episode JWT in the path | the MCP endpoint |

**`POST /admin/reindex`** — the corpus pipeline's ingest trigger
(`corpus/ingest_corpus.py ingest`). Auth is a JWT signed with the SAME
secret (`auth.token_secret_env`) but the admin claim set `{"admin":
"reindex", "exp": …}` — an episode token never authorizes admin (no
`admin` claim) and an admin token never authorizes tool calls (no
`case_id`). Responses: `401` unauthenticated/invalid; `405` non-POST;
`202 {"reindex": "started", "state": "indexing"}` — the state flips
*before* the response, the service is unready (503 on tool traffic) until
re-init completes, poll `/health` to `ready`; `202 {"reindex":
"already-indexing"}` while one runs (idempotent — exactly one init thread
ever). An unchanged corpus is cheap: fetch + fingerprint match ⇒ the
stored index is **reused**, never re-embedded (`index_reused: true` in
`/health`). Under `rebuild: never` a stale reindex lands in `state:
"error"` — the frozen-prod posture refuses rebuilds loudly, by design.

**MCP protocol**: streamable-http, **stateless** (`stateless_http=True` —
every request stands alone, matching per-request token verification), POST
JSON-RPC. GET (the SSE stream) returns **405** — a POST-only client works,
and pi 0.83.0 + pi-mcp-extension 1.5.0 is one (proven live, CP-29). The
token travels in the URL path because that is the channel the rendered
`.pi/mcp.json` carries (`url` is used verbatim by the pi-mcp-extension).

**Error semantics** (`app.py` — verification happens per request, BEFORE
the SDK app sees anything):

- **503 not-ready** — while `/health` reports `indexing` or `error`, every
  `/mcp/*` request gets a JSON-RPC error body naming the state; readiness
  is checked before token verification. Tool calls before ready are a clear
  MCP error, never empty results.
- **401 unauthorized** — missing token (`/mcp` bare), tampered payload,
  wrong-key signature, expired `exp`, malformed JWT, alg confusion (only
  HS256 accepted), unknown `case_id`, `timestep` outside `1..n_pages`. Body
  is a JSON-RPC error (`code -32001`) echoing the request's `id` when one
  can be read, so well-behaved clients correlate the failure.
- **`ToolError`** — in-band failures after transport succeeds (e.g.
  `case_status` at a timestep leaving no visible pages): an MCP tool-error
  result, not an HTTP error.

## The four tools

Registered unprefixed on server `gsj`; pi renders them `mcp_gsj_*`
(ADR-0007(c) — the server key `gsj` in the rendered `.pi/mcp.json` is
load-bearing for those names).

| tool | arguments | returns |
|---|---|---|
| `search_case` | `query: str`, `k: int = 5` | list of `{"page": int, "file": "md/page_NNNN.md", "score": float, "text": <full page text>}` — ranked over pages ≤ T only |
| `search_decisions` | `query: str`, `k: int = 5` | list of `{"decision_id", "court", "year", "score", "text"}` — **cutoff-exempt** (ADR-0007(e)) |
| `case_status` | — | `{"case_id", "timestep", "pages_visible", "max_visible_page", "source": "service"}` — reports the **token's** scope |
| `decision_stats` | `from_year`, `to_year`, `court` (all optional) | `{"total", "by_year", "by_court"}` — cutoff-exempt |

`k` is clamped into `[1, search.max_k]`. `search_case` aggregates chunk
scores to page level (max), returns top-k pages score-descending, ties by
page ascending, non-positive scores dropped, with the **full page text**
(`index.py`).

**G3 warning — the declarations are pinned.** The tool names, signatures
(type hints and defaults — the SDK generates the schemas from them) and
docstrings in `gsj_mcp_service/tools.py` are byte-identical to the
retired stub's (at commit `bbd4830`), and CP-29 Step 1 proved that serving them over
streamable-http through real pi reproduces the pinned `tool_roster_hash`
`a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56`
**exactly** (wire tools array captured from pi's request, hashed with the
pin layer's `sha256_canonical_json`). Any edit to names/signatures/
docstrings — or a bump of the `mcp==2.0.0` SDK pin (`requirements.txt`) —
changes the wire roster and G3 fails until a deliberate `gsj-pin` re-pin.
The bodies differ from the stub by design (MiniLM cosine retrieval instead
of token overlap); the declarations may not.

## The token format

JWT, HMAC-SHA256, claims `{case_id, timestep, episode_id, exp}`:

| claim | type | meaning |
|---|---|---|
| `case_id` | str | the one case this episode may query |
| `timestep` | int | T — the page cutoff, from these verified claims ONLY |
| `episode_id` | str | request-log correlation |
| `exp` | int | mint time + TTL (library `mcp_launch.token_ttl_s`, default 3600 s); verified with `auth.leeway_s` clock-skew allowance (default 30 s) |

**Mint/verify split**: the episode side mints (in the predecessor,
`gsj.envloader.task.mint_episode_token`, a stdlib-HMAC implementation —
sign-only by design; this repo's harness takes over minting when episodes
run under Polar, CP-07/CP-10); the service verifies with PyJWT
(`tokens.py`) — cross-verified byte-identical at CP-29. **The agent may read its own token**
from the rendered `.pi/mcp.json` — accepted and documented: every call it
enables is already scoped to its own episode's timestep, and mutating any
claim breaks the signature. **The secret** travels only as an env var
(`GSJ_MCP_TOKEN_SECRET` by default; both sides configure the NAME, never
the value) — it appears in no config file, no log, no error body, no
provenance.

## Configuration reference

One `config.yaml`, validated at startup with pydantic (`extra="forbid"`
everywhere — an unknown key is a startup error naming file and field, never
silently ignored; all models frozen). Relative paths resolve against the
config file's directory, not the cwd. Source of truth: `gsj_mcp_service/
config.py`.

### `source:` — where the frozen dataset lives

| field | type | default | meaning |
|---|---|---|---|
| `base_url` | `str` | **required** | Forgejo base URL (trailing slash stripped) — deployment topology, the A-08 "git host = CONFIG" posture |
| `owner` | `str \| None` | `"gsj-admin"` | owner segment of clone URLs; `None` for ownerless URL trees (`file://` bares). The shipped `config.yaml` sets `gsj-staging` since CP-33 — the service ingests the pipeline-scaffolded estate (`corpus/`, ADR-0047); the schema default is unchanged |
| `repos` | `list[str]` | **required** (≥ 1) | explicit case-repo list — the dataset is frozen, there is no discovery |
| `ref_main` | `str` | `"main"` | the full-document ref pages are read from |
| `ref_pattern` | `str` | `"timestep-{T}"` | discovery pattern for the recorded timestep refs; must contain the literal `{T}` |
| `auth_token_env` | `str \| None` | `None` | env var NAME holding a Forgejo token for authenticated pulls; unset = anonymous read (the staging answer — repos are public) |
| `clone_cache_dir` | `Path` | **required** | bare-mirror clone cache; survives restarts |

### `embedding:`

| field | type | default | meaning |
|---|---|---|---|
| `model` | `str` | `"sentence-transformers/all-MiniLM-L6-v2"` | the embedding model |
| `revision` | `str` | **required** | HF revision pin — part of the corpus fingerprint; keep in sync with the Dockerfile's `MINILM_REVISION` bake |
| `device` | `str` | `"cpu"` | torch device |
| `batch_size` | `int` (≥ 1) | `32` | corpus-encoding batch size |
| `normalize` | `bool` | `true` | L2-normalize embeddings (dot product = cosine) |

### `chunking:`

| field | type | default | meaning |
|---|---|---|---|
| `max_tokens` | `int` (≥ 16) | `220` | tokenizer-token window per chunk (< MiniLM's 256 incl. specials) |
| `overlap` | `int` (≥ 0, < max_tokens) | `40` | window overlap in tokens |
| `respect_page_boundaries` | `Literal[true]` | `true` | **contract** — chunks never span pages, so every chunk has exactly one `page`; `false` is not a supported mode (a backend wanting cross-page chunks must revisit G5's transcript backstop first, ADR-0040(e)) |

### `index:`

| field | type | default | meaning |
|---|---|---|---|
| `path` | `Path` | **required** | index storage root (`<path>/<case_id>/{vectors.npy,chunks.json}`, `<path>/decisions/`, `<path>/fingerprint.json`) |
| `rebuild` | `Literal["if-stale", "always", "never"]` | `"if-stale"` | rebuild policy (semantics below) |

### `search:`

| field | type | default | meaning |
|---|---|---|---|
| `default_k` | `int` (≥ 1) | `5` | default result count (the tool signatures' `k = 5` — G3-pinned) |
| `max_k` | `int` (≥ 1) | `20` | hard clamp: requested `k` is clamped into `[1, max_k]` |
| `method` | `Literal["exact"]` | `"exact"` | brute-force cosine over the full filtered candidate set — byte-reproducible at this corpus size; an ANN backend forfeits that and needs an assumption row first (ADR-0040(f)) |

### `decisions:`

| field | type | default | meaning |
|---|---|---|---|
| `seed` | `int` | `20260204` | the deterministic decisions-corpus seed (ADR-0007, carried over byte-identical in `decisions.py`) |
| `corpus_size` | `int` | `30` | corpus size; `30` reproduces the pinned historical corpus exactly |

### `auth:`

| field | type | default | meaning |
|---|---|---|---|
| `token_secret_env` | `str` | `"GSJ_MCP_TOKEN_SECRET"` | env var NAME holding the HMAC secret — the name, never a value |
| `leeway_s` | `int` (≥ 0) | `30` | clock-skew allowance on `exp` verification |

### `server:`

| field | type | default | meaning |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | bind address. The staging file sets `0.0.0.0`: on the H200, containers reach host services via `host.docker.internal` only when the service binds beyond loopback (measured — the predecessor's `staging/README.md`) |
| `port` | `int` | `8790` | bind port |
| `log_level` | `str` | `"info"` | uvicorn/logging level |
| `request_log_fields` | `list[str]` | `[episode_id, case_id, timestep, tool, k, n_results, latency_ms, cache_hit]` | fields (and order) of the per-call JSON log line |
| `dns_rebinding_protection` | `bool` | `false` | the SDK's Host-header check (421 on unlisted hosts). OFF by default: the token is the security boundary, clients are not browsers, and the legitimate Host varies by channel (`127.0.0.1`, `host.docker.internal:<port>`, tunnel hosts) — ON it rejected every containerized episode at CP-29 |
| `allowed_hosts` | `list[str]` | `[]` | Host allowlist (`"host"` or `"host:*"` patterns), consumed only when `dns_rebinding_protection: true` |

## Ingestion & the index

At startup a background thread runs ingest → fingerprint →
reuse-or-(re)build (`state.py`, `ingest.py`); `/health` reports progress
throughout, and any failure lands in `state: "error"` with the message.
Ingestion clones/fetches each case's **bare mirror** from Forgejo into the
clone cache (git CLI — the official client, ADR-0034 prior-art; a
configured source token is injected into the URL at call time and never
logged), reads the **full page set from `main`** via git plumbing (never a
working-tree checkout; contiguous `1..N` enforced), and chunks each page —
never across page boundaries. **One index per case over the full document —
NOT per timestep**; the cutoff is a query-time filter (ADR-0040(d), the
ADR-0007 leaky-server posture carried over).

Restart idempotence hangs on the **corpus fingerprint** — sha256 over
everything that determines index bytes: repo `main` SHAs + embedding model
& revision & normalize + chunking params + decisions params + index format
(`index.py: corpus_fingerprint`). Policy:

| `index.rebuild` | behavior |
|---|---|
| `if-stale` | fingerprint match ⇒ reuse the stored index (corrupt files ⇒ loud rebuild); mismatch ⇒ **loud** rebuild with a warning naming both fingerprints |
| `always` | rebuild on every start |
| `never` | a missing or stale index is a startup **error** — for frozen prod deployments |

With the dataset frozen (`corpus/staging/corpus.lock.json` — the pipeline's
freeze record), a fingerprint
mismatch should only ever happen on a deliberate re-pin (a model-revision or
chunking-param change) — the re-index trigger is the fingerprint, nothing
else.

## Determinism

MiniLM in eval mode, torch grad off, **single-threaded** CPU math, exact
float32 arithmetic, exact brute-force cosine in numpy, query encoding
serialized by a lock: two fresh processes embedding the same text on the
same host produce byte-identical vectors, hence identical rankings
(`embedding.py`; the determinism test asserts exactly this). An ANN index
or multi-threaded BLAS would forfeit this and needs an `ASSUMPTIONS.md` row
first (ADR-0040(f)).

## Operability

**Readiness is distinct from liveness** (ADR-0040(h)): liveness = the
process answers `/health` at all; readiness = `state: "ready"`. `/health`
fields:

| field | when | content |
|---|---|---|
| `state` | always | `indexing` \| `ready` \| `error` |
| `uptime_s` | always | seconds since start |
| `progress` | always | per-repo `{done, pages, chunks, embedded}` |
| `embedding` | always | `{model, revision}` |
| `error` | on error | the failure message |
| `cases` | ready | per-case `{pages, chunks, timesteps}` |
| `decisions` | ready | corpus size |
| `fingerprint` | ready | the active corpus fingerprint |
| `index_reused` | ready | whether the stored index was reused |

**Request logs**: one structured JSON line per tool call on stderr (`event:
"tool_call"`) — `episode_id, case_id, timestep, tool, k, n_results,
latency_ms, cache_hit` (`cache_hit` = the query-embedding LRU). The F-17
lesson (silent collection) applied pre-emptively: every call is attributable
to its episode.

## Compatibility requirements

Binding on **any** future backend behind these four tools — prod included:

1. **The G5 result shape.** Every `search_case` hit carries `"page"` (int,
   key exactly `page`) and `"file"` exactly `md/page_NNNN.md` (4 digits).
   The G5 backstop regexes
   (`"page"\s*:\s*(\d+)` and `md/page_(\d{4})\.md` — the predecessor's
   `gsj.envloader.gates.extract_case_search_pages`, inlined in this repo's
   `tests/helpers.py`; this repo's `checks.py` reimplements them at CP-10,
   `docs/checks-spec.md`) parse the transcript's
   tool-result texts as G5's backstop — a backend that renames the key or
   reformats the path blinds the gate.
2. **The cutoff, filter-before-rank.** No text with a page reference > T
   may appear in any returned content. The structural clamp is server-side:
   one index per case, candidates filtered to `page ≤ T` **then** ranked —
   a post-filter changes result counts and is the classic leak shape
   (ADR-0040(d)). T comes from the verified token claims ONLY, never from a
   request field.
3. `search_decisions`/`decision_stats` are cutoff-exempt (ADR-0007(e));
   `case_status` reports the token's scope.

## Prod swap

A real retrieval backend goes behind the same four tools, the same token
format, and the same result shape (ADR-0040(i)). The consumer-side delta is
**one endpoint value** — `mcp_launch.url_base` — which is the delta law
(CLAUDE.md law 7) holding at the service boundary: CONFIG, never CODE.

## Extractability

`gsj_mcp_service` imports nothing from `gsj.envloader` at runtime
(test-enforced); the library imports nothing from it. The coupling is the
HTTP contract and the token format documented above — which is how this
directory moved from the predecessor into this repo as-is at CP-01
(ADR-0002).
