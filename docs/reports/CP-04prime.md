### CP-04′ REPORT
status: done
scope_drift: none — the frozen six modules plus `corpus/`, `mcp-service/`, `vendor/`, `spike/` all diff empty against HEAD (DoD, run below); `pi_harness.py` untouched (its conditional lift was never triggered — the template adoption forced no config value through it); the predecessor read and RUN, never written (its H200 checkout's pre-existing dirty state — CP-22 tree + rsynced staging — predates this CP and was left exactly as found; collection used a NEW venv `.venv-cp04prime` beside its stale one); no fidelity comparison ran (STOP wall held — the golden froze on its OWN assertions only; the one cross-stack observation, the uid-in-instruction render-length fact, is recorded as a CP-09′ execution note, not compared); no `checks.py` change, no G6 rule, no training. One edit outside the named lift list, declared: `tests/test_checks.py` +4 (the pins snapshot test assumed all pins are strings; the new list-typed `g6_expected_tail_ids` broke it — tests are outside both the freeze list and the size law, and the assertion's intent now covers the new pin type)
files: 23 files changed, 38,841 insertions(+), 48 deletions(−) — new: `docs/golden/h200/{MANIFEST.md, record.json, tokens.npz, transcript.txt, artifact/ep-3ba9d4a1498f89fc.md}` (the frozen H200 golden), `docs/polar/h200-stitch/{attempt4.quarantined.json, attempt5.accepted.json}` (the stitch-retirement evidence), `staging/{README.md, rollout.h200.yaml, serving/{serve.sh, healthcheck.sh, model-0.6b.env, qwen3_training.jinja}}` (this repo's H200 estate recipe + the adopted template, byte-verbatim TRL), `docs/prompts/CP-04prime.md`, `docs/reports/CP-04prime.md` (this); modified: `pins/pins.gsj.json` + `pins/derive_pins.py` (the walk), `docs/CHARTER.md` (A-16 counterpart, A-21 note, §6 plan row + DoD marked done, rows 8/12/14/27), `docs/checks-spec.md` (the CUDA-strictness withdrawal), `docs/golden/COMPARISON.md` (§H200 half), `docs/VERDICT.md` (wishlist 5 done), `docs/decisions/ADR-0007…md` (dated amendment), `docs/polar/README.md` (h200-stitch section), `tests/test_checks.py` (declared above)
tests: `.venv/bin/pytest -q` → **125 passed** (the CP-15 count; the one snapshot-test accommodation declared under scope_drift)
adrs: ADR-0007 amended (append-only, dated 2026-08-11 — Direction A executed, the stitch dormant)        assumptions: A-16 gains its H200 counterpart (the H200 governs numerics — measured, not asserted); A-21 annotated (the pinned-glue condition no longer obtains on the H200 estate; the assumption stands for asymmetric templates)
gap_register: rows 8 (native merge under the symmetric template — F2 dissolves at the root on this estate), 12 (the measure-at-serve walk EXECUTED; the served template an explicit pinned file; the CP-11 expiry note resolved; GAP-by-decision unchanged), 14 (the `g6_expected_tail_ids` pin exists — wishlist 5; the rule still blocked on a `checks.py` freeze-lift; GAP unchanged), 27 (the CUDA-strictness premise measured false; PARITY unchanged); §6 gains the CP-04′ plan row and the inherited DoD marked done item-by-item; tally unchanged: 19 PARITY · 7 DROPPED · 4 GAP · 1 BETTER · 1 TBD
questions:
  - Corrupted span, Step 1: "the same model as the Mac pair, delib in numerics and not in model" → "…deliberately a pair in numerics and not in model" (A-16's design: vary the platform, hold the model).
  - Corrupted span, Step 2 heading: "The template: ddopt, prove" → "the template: choose, prove, adopt" (the body's own "Three parts, in order" are **Choose**/**Prove**/**Adopt**).
  - Corrupted span, Step 2: "diverging at index 2004 of 2008 on actly the four glue ids" → "…on exactly the four glue ids".
  - Corrupted span, Step 3: "the tail now appears inders too" → "the tail now appears in history renders too" (what the symmetric template changes).
  - Corrupted span, Step 4: "it is the fallback and A-22's ansa thinking-on estate" → "it is the fallback — and A-22's answer for a thinking-on estate stays the symmetric template, not the stitch".
  - Corrupted span, Step 5: "Assert before freezingdard" → "Assert before freezing, per the CP-04 standard".
  - Corrupted span, Step 6: "the rule is still blocked on a `checks.py` li`docs/golden/COMPARISON.md` gains…" → two merged lines: "…blocked on a `checks.py` lift." and a separate bullet "`docs/golden/COMPARISON.md` gains an H200 section, or a note that the contract holds unchanged…" (both executed: the note-plus-execution-facts form).
  - Corrupted span, DoD: "# → empty after come commit: `CP-04prime: …`" → "# → empty after commit" plus "One commit: `CP-04prime: the H200 golden pair`" (and the code fence was never closed).
  - Applied default, the "template investigation's findings document": no standalone document by that name exists in either repo (searched both). The findings record is ADR-0007's 2026-08-09 amendment + the CP-10 report §Step 4 — both read; the "three-line diff" was reconstructed by deriving TRL's file against the pinned template directly rather than located.
  - Applied default, the proof's absolute indices: measured **2018 of 2022**, not the prompt's "2004 of 2008" — same structure exactly (divergence at n−4, tail = precisely `[151667, 271, 151668, 271]`, symmetric variant diverging nowhere); the ±14 attributed to renderer/`tojson` formatting of the tools block in the investigation's environment. The load-bearing property reproduces exactly; the absolute lengths were never it.
  - Applied default, GPU: BRINGUP's default GPU 7 is occupied by another tenant (129 GiB); served on **GPU 3** (free), `GSJ_VLLM_GPU=3` — a value, recorded in `staging/serving/serve.sh`.
  - Applied default, the teacher instance: NOT brought up — no step needs it (it is the predecessor's M2/OPD capability) and the cluster is shared; BRINGUP's student-only subset suffices for the golden pair.
  - Applied default, `serving_base_url` without `/v1`: Polar's proxy appends `/v1/chat/completions` itself (`proxy.py:126`) — the suffixed form 404'd on `/v1/v1/…` (attempt 2, measured); recorded in `staging/rollout.h200.yaml`.
  - Applied default, episode networking: `runtime.network: gsj-staging-net` + host services at `172.28.9.1` — OUR harness clones INSIDE the sandbox (the CP-11 hardened clone) where the predecessor clones host-side and mounts, so our episode containers must reach Forgejo's container IP themselves; docker inter-network isolation blocks the default bridge (attempt 1 failed exactly there, measured); all three paths probed from a staging-net container before resubmitting. Config values only (law 5).
  - Applied default, `zero_at_mask1_max_rate`: STARTED at 0.0 per row 27's own "a CUDA estate restores strictness" note — which this estate then measured FALSE (the LP6 rejection below); moved to the CP-10 default 0.25 with the measurement recorded in the config comment, the spec, and row 27.
  - Applied default, the MCP data dir: recreated user-owned before compose-up (dockerd auto-created the bind-mount root-owned; the 0.3.0 container runs uid 1000 and failed loudly on `/app/data/clones`).
  - Applied default, the predecessor collector venv: the H200's existing `.venv` is stale (gsj.envloader 0.5.0, no uni_agent/verl/sglang — the H-41 guard fails); built a FRESH `.venv-cp04prime` per BRINGUP §5 + the 0.8.0 wheel (sha reproduced) and left the stale venv untouched. Collection runs from OUTSIDE `~/gsj-envloader` (the CP-22-era source tree shadows the installed wheel under `python -c` CWD precedence — measured ImportError).
  - Applied default, golden row-targeting: `concurrency` 2 → 1 (a concurrency-2 run draws a SECOND row — measured: its second episode ran `timestep-18`) and a FRESH store per attempt (completed episodes shift the deficit off the target row); seed-5 draw verified by simulation (`Random(5).random()*3 = 1.8687` → index 1 = timestep-12) and by every episode's own branch/claims.
  - Applied default, golden provenance: **the predecessor's stack** (the CP's own recommendation) — feasible on the H200, so CP-09′ keeps the Mac pair's exact comparison design on production hardware; nothing narrowed.
  - Applied default, stitch-evidence deposit: `docs/polar/h200-stitch/` (the `pi-corpus/`/`fidelity/` precedent — episode evidence lives under `docs/polar/`, the golden dir stays the predecessor-stack artifact only).
  - Applied default, estate teardown: executed per the estate's own standing rule (CP-34/ADR-0048 — torn down between CPs; not in this prompt's steps but the shared-GPU premise demands it); data dirs, venvs, snapshots and `~/cp04prime` scratch survive, so CP-09′'s bring-up is the fast path. Verified: all estate ports closed, GPU 3 back to 4 MiB, `forgejo-data` intact.
  - Applied default, the MCP HMAC secret: 0600 scratch file on the H200 for cross-process reuse (the CP-04 session-scoped deviation, same terms).
next: CP-09′ — execute `docs/golden/COMPARISON.md` verbatim against `docs/golden/h200/` (its new §H200-half carries the four execution facts: use THIS golden's instruction bytes — the uid rides in the text; no de-stitch step — the merged stream is the wire context; the 0.25 zero-allowance posture; the replay runs through the engine as written, same-engine tolerances applying for the first time). Row 2's estate residual (anonymous Forgejo read → an URL-guessing agent can re-clone) remains OPEN — named in the VERDICT's CP-04′ description but not in this prompt's steps; CP-09′ or an estate CP owns the credentialed-clone/egress decision.

---

#### The estate as brought up (Step 1), and every deviation from BRINGUP

Forgejo per BRINGUP §1 verbatim (its own `up.sh`; data dir intact from
the last teardown): refs `4 / 4 / 1`, taskbank sha
`9eb8e3c2…` — both expected values exactly. The **split-shaped corpus**
scaffolded from THIS repo's `corpus/staging` on the H200
(`ingest_corpus.py scaffold`): all four cases `[pushed, converged]` on the
frozen estate — the CP-14 measurement (bytes and refs unchanged by the
split) confirmed against the live estate. **mcp-service 0.3.0** (the
CP-15 ChromaDB backend) built linux/amd64 on the workstation and shipped
over the `docker save | gzip | ssh docker load` link — the transfer was
practical (the ~310 MB dependency delta rode a ~2.5 GB image; no slimmer
image needed). `/health` after a cold rebuild (INDEX_FORMAT 2 — expected,
~30 s):

```
state: ready — census 18/22/15/20 pages, 51/62/43/57 chunks
backend: {"name": "chromadb", "version": "1.5.9", "collections": 5}
```

Corpus verify against the live estate: **PASS 29/29** (the v2 pipeline's
count; BRINGUP's "25/25" is the predecessor pipeline's). Serving
healthcheck, verbatim: `OK /health · OK /v1/models lists Qwen/Qwen3-0.6B
· OK tool call parsed: get_utc_time (finish_reason=tool_calls) · OK tool
round trip: 'The current UTC time is 2026-08-04T12:00:00Z.' · healthcheck
OK`.

Deviations from BRINGUP, each recorded where it lives: GPU 3 not 7
(tenant occupancy); teacher not brought up; the serve recipe is this
repo's `staging/serving/serve.sh` (deltas in its header: the symmetric
template, the explicit generation-config pin, no LoRA flags, GPU
default); the MCP service runs from THIS repo's checkout with a fresh
data dir (cold re-index rather than the predecessor's cache — the old
index is the numpy format anyway); episode networking per the
`staging/rollout.h200.yaml` header (the one genuinely new fact: our
in-sandbox clone needs Forgejo reachable FROM the sandbox — the
predecessor never did).

#### The engine's three pinned legs (Step 1), with evidence

1. **`--generation-config`** → a byte-copy of the snapshot's own
   `generation_config.json` — which the CUDA snapshot CARRIES upstream
   (verified, not assumed: sha256 `2325da0f…`, byte-identical to the
   codec pin CP-09 used). Startup log, verbatim: `Default vLLM sampling
   parameters have been overridden by /home/sysadmin/gsj-vllm/genconfig:
   {'temperature': 0.6, 'top_k': 20, 'top_p': 0.95}`. Applied block from
   the request log on the golden's own two turns (seed-matched):
   `SamplingParams(… temperature=0.6, top_p=0.95, top_k=20,
   seed=1500772333, stop=[], max_tokens=8192, logprobs=1 …)`.
2. **`--enable-auto-tool-choice --tool-call-parser hermes`** — in the
   serve argv (verbatim in the MANIFEST); the healthcheck's parsed
   `tool_call` and every episode's `tool_choice: auto` traffic prove them
   live.
3. **`--max-model-len 32768`** — in the serve argv; episodes ran up to
   25k-token responses without a 400 (the CP-04 failure shape absent).

#### The template (Step 2): choice, reasoning, and the proof

**Choice: TRL's `qwen3_training.jinja`, byte-verbatim** (sha256
`1d944ff8…`, upstream `huggingface/trl` @ `63b7c3f5…`, 2026-07-16), over
the three-line diff and over any hybrid. Reasoning: (1) it is the
superset the CP said to prefer — the positional
`loop.index0 > ns.last_query_index` conditional is dropped entirely (the
history render is unconditional, so thinking-ON is covered — A-22's cure
held in reserve) and the `reasoning_content` fallback is handled (splits
`content` on `</think>`); (2) byte-verbatim adoption keeps the external
identity (the pin IS TRL's shipped artifact); (3) its
`{% generation %}`/`{% endgeneration %}` training markup is accepted by
the exact serving path — verified in the H200 venv before serving (vLLM
0.26.0's renderer registers the `generation` tag itself and delegates to
`tokenizer.apply_chat_template`, transformers 5.14.1 — and the live
warmup + every episode confirm it).

**The proof, before serving** (both templates rendered against the same
captured 4-message pi body, `docs/polar/pi/pi_request.raw.json`,
tokenized by the served tokenizer; typed content parts flattened the way
vLLM flattens — finding (b) honored):

```
== pinned (the served snapshot's own template, sha a55ee1b1) ==
turn-1 prompt_ids: 2022   turn-2 prompt_ids: 2066
DIVERGES at index 2018 of 2022
  turn-1 decoded from 2018: '<think>\n\n</think>\n\n'
  turn-2 decoded from 2018: '<tool_call>\n{"name": "'
  tail past divergence in turn-1: 4 ids = [151667, 271, 151668, 271]

== symmetric (TRL qwen3_training.jinja) ==
turn-1 prompt_ids: 2022   turn-2 prompt_ids: 2070
turn-2 is a STRICT PREFIX-EXTENSION of turn-1: True
```

Plus the identity that bounds the blast radius: **turn-1 renders
byte-identical across the two templates** — the only behavioral delta is
the think block re-appearing in history re-renders (19 chars/turn), so
G2's singleton and every fresh episode's first prompt are untouched by
the flip.

**Adoption**: `--chat-template /home/sysadmin/gsj-vllm/qwen3_training.jinja`
in the serve argv (sha-verified on the serving host against the committed
`staging/serving/qwen3_training.jinja`), the file committed, the recipe
committed. Per-request overrides were not used.

#### The pins walk (Step 3), run estate-side on the H200

`derive_pins.py` (updated: the served template is now an explicit file —
`GSJ_SERVED_TEMPLATE`; snapshot-embedded templates recorded-not-approved;
`g6_expected_tail_ids` verified by the served tokenizer wherever
transformers is importable) — full output in the walk run, every approved
value reproduced:

| pin | value | moved? | provenance |
|---|---|---|---|
| `tokenizer_hash` | `949e1ec8…` | no | H200 served snapshot's tokenizer.json (codec == served here — one snapshot) |
| `chat_template_hash` | `87a2728c…` → **`1d944ff8…`** | **YES — the whole point** | the served `--chat-template` file's bytes; Mac value retired, both snapshot-embedded templates (`a55ee1b1…`) recorded-not-approved |
| `settings_hash` | `dae89485…` | no | the harness constant + carried evidence |
| `tool_roster_hash` | `a7a7956b…` | no (CP-15's assertion held on a live wire) | carried evidence + the FRESH H200 episode's `trace.tools` |
| `system_prompt_hash` | `f56e8a6e…` | no — the `/workspace` singleton holds on the H200 | carried evidence + the fresh episode's wire system prompt |
| `skill_card_hash` | `d41ec6ea…`, `15ae463e…` | no | the corpus staging cards |
| `g6_expected_tail` | 41 bytes | no — **measured**: the TRL generation-prompt branch is byte-identical under `enable_thinking: false`; the flip changes G6's SUBJECT (the tail now rides history renders too), not the tail | `pins/g6_tail.captured.txt` |
| `g6_expected_tail_ids` | **`[151644, 77091, 198, 151667, 271, 151668, 271]`** | NEW (wishlist 5) | the tail tokenized by the served tokenizer, estate-side (ADR-0011) |

The G6 rule this feeds (recorded in the pin's provenance, NOT
implemented — `checks.py` frozen): ids-endswith over the suffix of
`prompt_ids` and over the mask-0 interstitial span preceding each mask-1
span of `response_ids`; zero turns checked fails closed; token ids only.

#### The stitch retirement (Step 4) — the single most consequential line

Two fresh episodes through `gsj-rollout submit`, `generation_prompt_glue_ids`
**unset**, verbatim from the callback bodies (`docs/polar/h200-stitch/`):

```
reconstruction_stats: {"chains_total": 1, "chains_reconstructed_full": 1,
  "chains_reconstructed_truncated": 0, "raw_completions_total": 2,
  "completions_total": 2, "completions_merged": 2}
gsj_validation: findings=[]  glue_stitched=0
```

**Polar's grouping merges natively under the symmetric template.** The
template did its job; F2 dissolves at the root on this estate — the
merged stream IS the wire context. The stitch code stays in place and
dormant (ADR-0007's amendment records the executed flip; A-21 keeps the
fallback). Submission history, honestly: 5 attempts — attempt 1 failed on
episode-container→Forgejo reachability (the inter-network isolation
finding, cured by config), attempts 2–3 on my own `serving_base_url`
`/v1` suffix (the proxy appends it; 404 measured, cured by config),
attempt 4 COMPLETED with the full conjunction and was **rejected by the
receiver on `LP6:zero_logprob_rate_at_mask1:34/237>0.0`** under the
strict CUDA policy — the row-27 finding below — and attempt 5 (policy at
the 0.25 default) was **accepted through the full receiver seam**:
`collected 1/1`, G1/G2/G3/G5/G7 + the logprob discipline all green,
cutoff held (search pages `[1, 5, 7, 9, 11]` ≤ 12), ≥1 `mcp_gsj_*` and a
successful `grep`. The accepted trace is also the fresh-episode
re-verification of G2/G3 (both hashes reproduce — pins provenance
updated), closing the "first genuinely fresh episode" note row 23 left
open.

#### The golden (Step 5): provenance decision, assertions, attempt count

**Decision: the predecessor's stack — the CP's recommendation, executed.**
The collector stack stood up on the H200 (a finding in itself: the
resident venv was stale 0.5.0 and unusable; BRINGUP §5 + the 0.8.0 wheel
rebuilt it, H-41 guard verbatim-green: `uni_agent OK · verl OK 0.9.0.dev
· sglang FunctionCallParser OK 0.5.10.post1 · gsj.envloader OK 0.8.0`),
so CP-09′ keeps CP-09's exact two-capture-layer design on production
hardware. **Eight episodes, seven on-triple attempts; attempt 7
qualified** — the same count CP-09 took, on the same H-41
successful-built-in leg (every refusal was `completed`/gates-green with
zero successful built-ins; the assertion, not the gates, did the
refusing). The frozen episode `ep-3ba9d4a1498f89fc`, asserted verbatim:

```
record uid=ep-3ba9d4a1498f89fc task triple=('case_0001', 12, 'skill:summarize') num_turns=4 tool_calls=6 wall=8.414s
ASSERT finish_state == completed: PASS — 'completed'
ASSERT gate_failures == []: PASS — []
ASSERT input_ids == prompts + responses: PASS — lens 6647 vs 2965+3682
ASSERT loss_mask == response_mask: PASS
ASSERT R-aligned lengths agree: PASS — responses=3682 loss_mask=3682 response_mask=3682 logprobs=3682
ASSERT rollout_log_probs present & finite: PASS
ASSERT logprobs <= 0 at mask==1: PASS — 258 mask-1 positions, max=0.000000
WARN suspicious-zero rule (checks-spec): 16 exact-0.0 logprob(s) at mask==1 of 258 — CUDA bf16, row 27
ASSERT no sentinel (<= -9000) at mask==1: PASS — min=-2.2529
ASSERT exactly 0.0 at mask==0 placeholders: PASS — 3424 mask-0 positions
ASSERT >= 1 mcp_gsj_* tool executed: PASS — [mcp_gsj_case_status, mcp_gsj_search_decisions, mcp_gsj_search_case]
ASSERT >= 1 successful built-in executed: PASS — [write]
tool executions, in order: [(grep,ERR),(read,ERR),(write,ok),(mcp_gsj_case_status,ok),(mcp_gsj_search_decisions,ok),(mcp_gsj_search_case,ok)]
```

One uninterrupted pi session; the provenance G-hashes hit every pinned
singleton (G1 `d41ec6ea…`, G2 `f56e8a6e…`, G3 `a7a7956b…`, G4
`949e1ec8…`/codec `a55ee1b1…`, G7 `dae89485…`); an **artifact was
produced** (`out/ep-3ba9d4a1498f89fc.md`, sha `eaabe127…` — the Mac
golden had none) and is frozen with the record, tokens, transcript, and
the 129-line MANIFEST under `docs/golden/h200/`. Nothing compares across
`mac/` and `h200/`.

#### What the H200 surfaced that the Mac could not

1. **Row 27's CUDA premise is false — measured, live, at the receiver.**
   Exact-`0.0` at `mask==1` is a bf16-near-delta property, not an MLX
   quirk: golden 16/258 (6.2%), our stack 34/237 (14.3%) and 2119/8506
   (24.9% — a repetitive-loop episode within 0.1pp of the allowance).
   The strict-`0.0` policy rejected a clean episode (fail-closed, loud —
   the seam worked); the estate now runs the 0.25 default and the spec's
   recommendation is withdrawn with the numbers attached.
2. **Our in-sandbox clone has an estate-networking requirement the
   predecessor never had**: episode containers must reach Forgejo's
   container IP themselves; docker inter-network isolation silently
   blackholes the default bridge. Cured by config
   (`runtime.network: gsj-staging-net`, host services at the network's
   own gateway IP), preflight-probed, recorded in the YAML header.
3. **The resolved skill instruction embeds the episode uid**, so turn-1
   renders vary ±1–2 tokens per uid (measured 2964–2966 across eight
   attempts). Invisible on the Mac pair (CP-09 reused the golden's fixed
   bytes); binding on CP-09′ (COMPARISON.md §H200 half).
4. **The predecessor's H200 resident state had rotted quietly** — stale
   0.5.0 venv without the H-41 stack, a CP-22-era source tree that
   shadows an installed wheel under `python -c` — both worked around
   without touching the predecessor (fresh venv, run from outside the
   tree), both worth knowing before anyone re-runs BRINGUP §5 as written.
5. **`docker save | load` image identity drift**: the H200 daemon's
   `pi0.83.0-3` is a different image id than the workstation's current
   build of the same tag; the estate's frozen load is what both stacks
   ran, recorded by id in the MANIFEST.

#### DoD, run and shown

```
$ git diff HEAD -- gsj_rollout/checks.py gsj_rollout/builder.py \
    gsj_rollout/config.py gsj_rollout/receiver.py gsj_rollout/client.py \
    gsj_rollout/cli.py corpus/ mcp-service/ vendor/ spike/
(empty)
$ .venv/bin/pytest -q
125 passed in 12.79s
# estate: /health census 18/22/15/20 + backend {chromadb, 1.5.9, collections: 5}; healthcheck OK incl. tool round trip   (Step-1 section, verbatim)
# template: prefix-extension before/after                                            (Step-2 section, verbatim)
# pins walk: all approved values reproduced; chat_template_hash re-derived by design (Step-3 table + walk output)
# stitch retirement: chains_total == 1, glue_stitched: 0, glue ids unset             (Step-4 section, verbatim)
# golden: assertions + 7-of-7-on-triple attempt count                                (Step-5 section, verbatim)
$ ls docs/golden/h200/
artifact  MANIFEST.md  record.json  tokens.npz  transcript.txt
$ grep -c '^' docs/golden/h200/MANIFEST.md
129
$ test -f docs/reports/CP-04prime.md && echo OK
OK
$ git status --porcelain      # after commit
(empty)
```
