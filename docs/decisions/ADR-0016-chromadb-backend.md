# ADR-0016 — ChromaDB behind the MCP tools

## Context

CP-15 (M4c). The MCP service's retrieval backend is hand-rolled:
`vectors.npy` (float32, L2-normalized MiniLM chunk embeddings) plus an
exact brute-force cosine scan in numpy (`index.py`), one index per case,
the timestep cutoff applied as a candidate filter before ranking
(ADR-0040(d) posture, carried from the predecessor's ADR-0007). It is
correct, byte-reproducible (ADR-0040(f)), and 161 lines we maintain.
The operator directed the swap to ChromaDB. Everything above the backend
is a wire contract other components already consume: G3 hashes the tool
roster (`a7a7956b…48e56`), G5's two regexes parse the result shape,
`checks.py` and the pinned episodes depend on the cutoff's
filter-before-rank semantics.

R1 (do not reinvent) is the standing pressure: the hand-rolled index was
accepted at CP-29-predecessor scale precisely because it was trivial;
Chroma is the off-the-shelf candidate now named.

## Decision

Replace `vectors.npy` + the numpy cosine scan (case indexes AND the
decisions index) with ChromaDB collections. Everything else — tool
declarations, result shape, cutoff semantics, token verification,
ingestion, chunking, the pinned MiniLM encoder — stays byte-identical.

### The four invariants that may not move

1. **Tool names, signatures, docstrings** (`tools.py`) — the SDK
   generates wire schemas from them; G3 hashes the wire roster against
   the pinned `a7a7956b…48e56`. Any drift fails every episode until a
   deliberate `gsj-pin` re-pin. `tools.py` is untouched this CP, and the
   service's own suite now asserts the pin (`test_roster_pin.py`): the
   live `tools/list` declarations must reproduce the four `mcp_gsj_*`
   entries of `pins/tools.captured.json` byte-for-byte under pi's wire
   rendering, and that captured array must hash into
   `pins/pins.gsj.json`'s `tool_roster_hash`. This test should have
   existed before; it exists now.
2. **Result shape** — every `search_case` hit carries `"page"` (int) and
   `"file"` == `md/page_NNNN.md` (4 digits), parseable by G5's two
   regexes (`"page"\s*:\s*(\d+)`, `md/page_(\d{4})\.md`). A backend that
   renames the key or reformats the path blinds the gate. The shape is
   assembled in OUR code from chunk metadata, never by Chroma; the
   existing shape tests stand.
3. **Cutoff filter before ranking** — candidates are constrained to
   `page <= T` BEFORE similarity ranking. A post-filter returns fewer
   than `k` and moves the recall boundary — the classic leak shape.
   Chroma's `where={"page": {"$lte": T}}` is the primitive, and its
   pre-filter behavior is **verified empirically, not assumed**
   (test designed before the code, see Mechanics 4).
4. **T from verified token claims only** — the cutoff reaches `search`
   only via `claims.timestep` (`tools.py`, unchanged); no request field
   ever carries it.

### Mechanics

1. **Chroma pinned exact**: `chromadb==1.5.9` in `requirements.txt`
   (latest-then-freeze, resolved 2026-08-11). A new dependency with its
   own upgrade risk — assumption row A-24. `PersistentClient` at
   `<index.path>/chroma`, telemetry off
   (`Settings(anonymized_telemetry=False)` — the container runs offline).
2. **One collection per case**, named `<case_id>`, plus one `decisions`
   collection — closer to today's per-case shape, and the cutoff filter
   stays a single `page` clause instead of a compound
   `case_id AND page` on every query. **Chroma's name rules NARROW the
   valid case-id space** (measured, corrected by the CP-15 review: 3–512
   chars of `[a-zA-Z0-9._-]` with alphanumeric ends, so contract-valid ids
   like `c1`, `case_`, `x-` are rejected — the corpus contract admits
   1+ chars and trailing `_`/`-`). Decision: accept the narrowing and make
   it LOUD — `SourceConfig.repos` validates per element at config load
   with a message naming the constraint and this ADR, instead of failing
   at first index build with Chroma's generic error. The frozen roster
   (`case_0001`–`case_0004`) passes; the corpus contract itself is not
   touched (frozen this CP — a corpus-side tightening is a future
   corpus-CP decision).
3. **Cosine space** (`configuration={"hnsw": {"space": "cosine"}}`);
   vectors stay L2-normalized so `score = 1 − distance` reproduces
   today's cosine-similarity score semantics (positive = similar).
   Ranking policy stays OURS: chunk→page aggregation (max), sort by
   `(-score, page)`, non-positive scores dropped, top-k pages, full page
   text attached. Chroma supplies candidate scoring only.
4. **Full filtered-set fetch**: `n_results = |{chunks: page ≤ T}|`
   (known from the in-memory chunk metadata). Correct page-level max
   aggregation needs every candidate page's best chunk, and at 213
   chunks the full fetch is free — this keeps the tool's ranking at
   parity with the exact scan it replaces. At a corpus where that stops
   being true, the fetch becomes bounded (c·k chunks) and THAT is where
   real approximation enters `search_case` — a future decision, not
   this one. The pre-filter test locks the semantics: at a tight
   timestep, a query aimed at out-of-cutoff content must return ALL
   in-cutoff chunks — a post-filter cannot (the global top-n is
   dominated by out-of-cutoff chunks, so filtering after ranking
   returns fewer). Measured at the probe: global top-5 entirely beyond
   the cutoff, `where`-filtered query returned exactly the full
   in-cutoff set.
5. **Decisions move too** — same backend for both indexes (R3: one
   backend, not two). `n_results = 30` (the full corpus), tie-break
   `(-score, decision_id)` and the positive-score drop stay ours;
   `search_decisions`/`decision_stats` remain cutoff-exempt
   (ADR-0007(e)) and `decision_stats` never touches Chroma (it is a
   pure recount over the in-memory corpus).
6. **Sidecars survive**: `chunks.json` (chunk metadata + page texts +
   refs + timesteps) and `decisions/corpus.json` are unchanged — the
   tools need page texts and the census regardless of the vector store.
   Only `vectors.npy`'s role moved into Chroma.
7. **The default-EF hazard, guarded structurally.** Measured at the
   probe: `create_collection(embedding_function=None)` records a
   `legacy` EF config, but `get_collection`'s *default parameter* is
   `DefaultEmbeddingFunction()` — Chroma's bundled ONNX MiniLM, which it
   downloads on first text op and which embeds at **384 dimensions,
   exactly ours**, so an accidental `query_texts`/text-only `add` would
   silently mix two different MiniLM implementations (ONNX-quantized vs
   the pinned `sentence-transformers` revision) and produce
   plausible-but-wrong scores. Guard: every `create_collection`/
   `get_collection` passes a raising embedding function
   (`_NoTextOps` — any text op raises naming `embedding.py` as the one
   encoder), embeddings are always passed explicitly, and the identity
   test asserts a stored Chroma vector is **bit-exact** equal to the
   pinned encoder's output for the same chunk text (round-trip measured
   exact at the probe).
8. **Fingerprint gains the backend**: `INDEX_FORMAT` 1 → 2 (the on-disk
   layout changed) and a new `chroma_version` component in
   `corpus_fingerprint` — a Chroma upgrade that changes the on-disk
   format forces a loud rebuild under `if-stale` (or a startup error
   under `never`) instead of failing silently. Existing `vectors.npy`
   files from a format-1 deployment are ignored (the mismatch rebuild
   overwrites the sidecars; stale `.npy` files are inert leftovers an
   operator may delete).
9. **`search.method: "exact"` is retired loudly**, the `eval_case_ids`
   pattern: the value was a promise ("brute-force cosine —
   byte-reproducible") that the backend no longer keeps, so keeping it
   would be false advertising. The one supported value is `"chroma"`;
   a config carrying `exact` fails startup with a message naming this
   ADR and the fix. **`embedding.normalize: false` joins it** (CP-15
   review): under the numpy scan `false` had defined raw-dot-product
   ranking semantics; Chroma's cosine space normalizes internally and
   cannot reproduce them, so the mode is rejected by the same
   loud-retirement pattern rather than silently re-ranked. Both
   retirements are test-enforced (`test_config.py`).
10. **Reindex is restart-equivalent** (CP-15 review's phantom-store
   finding, reproduced and fixed): Chroma caches one `System` per store
   path per process with open sqlite handles, so after an out-of-band
   store replacement (`rm -rf <index.path>/chroma`, the operator move
   this ADR itself invites) a running service kept serving the unlinked
   inode and `/admin/reindex` "reused" a phantom while a restart rebuilt.
   `request_reindex` now evicts the process-cached system for its own
   store path (scoped, never a global cache clear — pinned-version
   private API, documented at `index.evict_chroma_client_cache`) before
   re-initializing, so the init thread observes the real disk; regression-
   tested (`test_backend.py: test_reindex_after_out_of_band_store_
   replacement_rebuilds`).

### What is accepted as changed

**Byte-reproducible retrieval stops being a guarantee.** ADR-0040(f)'s
posture ("exact brute-force — deterministic; an ANN backend forfeits
this and needs an assumption row first") is exercised exactly as
written: HNSW is what Chroma gives, this is a RAG system, and the
operator declined exact search by choosing the swap. CP-15 Step 4
**measures** cross-process determinism at this scale rather than
asserting either way; the result is assumption row A-25. Chroma is NOT
tuned to force determinism — that would be exact search by the back
door.

**Scores change in the last float digits.** Chroma computes cosine
distance internally (Rust, float32); `1 − distance` differs from the
numpy dot product at ~1e-7 (measured at the probe). Scores were never
pinned bytes — the shape contract requires positive floats sorted by
`(-score, page)` — but any future comparison against CP-14-era stored
scores is a diff, not a bug.

### What Chroma is for — stated plainly

At 213 chunks it buys little: the numpy scan was exact, deterministic,
and already written. What the swap buys is (a) a query API and a
persistence layer this repo no longer maintains (the deleted scan +
save/load code is the R1 payment), and (b) substrate that keeps working
when the corpus grows past where brute-force is free — metadata
pre-filtering plus ANN is the shape a real corpus needs, and moving to
it while the corpus is small means the wire contract is proven ported
before scale forces a hurried port. That is the honest whole of it.

## Consequences

- `mcp-service` gains a heavyweight pinned dependency (chromadb + its
  transitive set: onnxruntime, opentelemetry, grpcio, kubernetes,
  tokenizers, …) — image size delta recorded in the CP-15 report; the
  H200 `save | load` recipe is unchanged in kind.
- The determinism section of the README is rewritten: embedding
  determinism (ours) survives; ranking determinism is A-25's measured
  claim, not a guarantee.
- `rebuild: never` deployments must re-key on any Chroma bump — the
  fingerprint's `chroma_version` component makes the stale index loud.
- The G3/G5/cutoff invariants are now test-enforced inside the service's
  own suite, so a future backend swap (prod included) inherits
  executable compatibility requirements, not just README prose.
- If a later CP needs bounded fetch (corpus growth), the approximation
  boundary moves inside `search_case` and A-25 must be re-measured —
  that CP owns the recall story.
- **Accepted, not fixed** (CP-15 review, recorded): an in-flight tool call
  that passed the readiness check just before a REBUILD reindex flips the
  state can observe `delete_collection` mid-query and gets a loud (if
  generic) tool error; its retry lands on the clean 503. The window
  exists only on deliberate re-pin reindexes of a live service (an
  unchanged corpus reindex reuses and deletes nothing), the numpy
  backend's analogue served retired in-memory data silently rather than
  failing loudly, and closing it (versioned collection names with an
  atomic swap) buys a rare cosmetic improvement at real complexity.
  Revisit only if live re-pin reindexes become routine.
