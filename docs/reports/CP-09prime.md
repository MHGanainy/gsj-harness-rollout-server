### CP-09′ REPORT
status: done
scope_drift: none — no `gsj_rollout/` code touched; no `checks.py` change (G6 included, STOP wall held); no vendored edits; protected-path diff `git diff HEAD -- vendor/ corpus/ mcp-service/ forgejo/ pins/ spike/ docs/golden/h200/ gsj_rollout/checks.py` empty (DoD, run below); the predecessor read and RUN never written (its stack was not used this CP — the golden was frozen at CP-04′; this CP collected through OUR path only); no freeze-lift was needed — the comparison exposed nothing ours to fix; no capability written (the comparison drivers are estate-side scratch scripts, not repo code)
files: 13 files changed — new: `docs/polar/h200-fidelity/{callback_session_result.json, trace.json, pi_transcript.jsonl, mcp_authority_log.jsonl, comparison_results.json, replay_rerun.txt, sampling_evidence.txt, artifact/ep-3ba9d4a1498f89fc.md}` (the collected episode + its evidence + the measured numbers; the last two added because the adversarial pass flagged that the replay-vs-replay figure and the applied sampling block otherwise lived only in estate-side logs — the row-22 class, now deposited), `docs/prompts/CP-09prime.md`, `docs/reports/CP-09prime.md` (this); modified: `docs/CHARTER.md` (A-1 governing-platform resolution; A-16 counterpart closed; §5 MET on both pairs; rows 7, 8, 27 final M4-entry statuses), `docs/checks-spec.md` (§CP-09′ — the platform capture-noise floor, a clean-presenting class), `docs/golden/COMPARISON.md` (H200 results section), `docs/VERDICT.md` (dated converting-condition-1 section), `docs/polar/README.md` (h200-fidelity section)
tests: `.venv/bin/pytest -q` → **125 passed** (no code touched); the comparison itself verified by a 4-agent adversarial workflow — all four legs CONFIRMED: structure (every number independently recomputed from the raw arrays, zero discrepancies), decode/glue (all four mask-1 spans re-decoded **byte-exact** with an independent pure-python BPE decoder over the pinned snapshot; glue framing and G6 tail ids re-confirmed; both prompts' full id sequences re-proven identical), replay-indexing (the offset proven by measured ±1-shift: aligned mean |Δ| 0.005936 vs 0.138431/0.138718 shifted — 23× worse, 5 positions > 1 nat, max 2.18 nats, zero such positions aligned; the F2 hypothesis refuted by injection), and verdict-classification (the contract's "beyond it on both" branch, the PASS WITH FINDINGS box, and condition-1 MET each confirmed against the contract's own text)
adrs: none        assumptions: A-1 (RESOLVED on the governing platform — the H200 pair; the Mac pair resolved it for its estate at CP-09); A-16 (counterpart CLOSED — the H200 verdict exists and governs the numerics; both pairs' verdicts agree in kind: PASS WITH FINDINGS, nothing attributable to Polar on either)
gap_register: rows 7 (capture — final M4-entry status PARITY, H200-confirmed; the CUDA cross-request capture-noise floor annotated in-row), 8 (reconstruction/masks — final M4-entry status PARITY, the central bet answered on BOTH pairs; masks exact zero-tolerance on the H200, native merge live at replay), 27 (logprobs — PARITY stands; this pair's zero-rates 6.2% golden / 7.3% collected recorded, third and fourth in-allowance CUDA measurements); §5 gains the MET-on-both-pairs note; §4 A-1/A-16 updated
questions:
  - Corrupted span, Read-first list: "`docs/golden/h200/MANIFEST.md` (the mparison rests on)" → "…(the provenance the comparison rests on)".
  - Corrupted span, Step 1: "`--enable-auto-tool-choicparser hermes`" → "`--enable-auto-tool-choice --tool-call-parser hermes`" (the serve argv's two flags, per serve.sh and the MANIFEST).
  - Corrupted span, Step 2: "Glue ids unset — CP-he template makes them unnecessary" → "…CP-04′'s symmetric template makes them unnecessary".
  - Corrupted span, Step 3 item 2: "`prompt_ids` and the inteNote what changed since CP-09**" → "`prompt_ids` and the interstitial glue. **Note what changed since CP-09**".
  - Corrupted span, Step 3 item 3: "the merged stream is the wire context underic template" → "…under the symmetric template".
  - Corrupted span, heading "## Stepict" → "## Step 4 — Verdict".
  - Corrupted span, Step 5: "Gap rows on tonstruction, capture, logprobs, and masks" → "Gap rows on token reconstruction, capture, logprobs, and masks" (rows 8, 7, 27; masks live in rows 7/8).
  - Corrupted span, DoD: "# → emptmmit" → "# → empty after commit".
  - Applied default, attempt cap: CP-09's cap-of-10 default produced no qualifier (all refusals on the H-41 successful-built-in leg); extended to 26 and qualified at **attempt 19** — the CP itself sets no cap and says "collect another and report the attempt count".
  - Applied default, "≥1 successful built-in": read per the CP-07/CP-09 standard (a *successful* built-in), same as both prior collections.
  - Applied default, replay mechanism: `/v1/completions` with token-id prompt, `max_tokens: 0, echo: true, logprobs: 1, add_special_tokens: false` — vLLM returns per-position teacher-forced prompt logprobs through the engine (the as-written form; probed before use).
  - Applied default, replay-vs-replay diagnostic: added per the contract's own "rerun to bound it" branch — it decomposes the drift (replay path bit-deterministic; the drift is capture-path).
  - Applied default, capture-vs-capture span: the FULL common response prefix (105 ids here vs the Mac pair's 20) — more positions, same instrument.
  - Applied default, deposit set: CP-09's four files + `comparison_results.json` (the measured numbers) + the collected artifact under `artifact/` — deposited because this pair's artifact row has a real subject; the file is named `ep-3ba9d4a1498f89fc.md` (the GOLDEN's uid) because the instruction bytes embed it — the uid-substitution implication, stated: our episode wrote the deliverable to the path the golden's instruction names.
  - Applied default, MCP authority log: extracted from the service container's stdout (`docker logs`), the three `tool_call` events for the qualifying session — the 0.3.0 service logs authority events there, not to a file.
next: M4 — the slime bridge and one OPD loop (converting condition 2, the last before the provisional adopt converts). Replay-style trainer checks on this platform must use the measured floor (checks-spec §CP-09′), not the CP-18 anchor as written. Row 2's estate residual (anonymous Forgejo read) remains OPEN, unchanged by this CP.

---

#### The estate as brought back (Step 1), and the three legs verbatim

Fast path, exactly as CP-04′ left it: Forgejo up from its intact data dir
(refs **4 / 4 / 1**; taskbank sha `9eb8e3c2…`, pins.staging.json
`bfa66b26…` — both frozen values reproduced); mcp-service 0.3.0 up from
its intact user-owned data dir (warm index, ready in ~10 s):

```
state: ready — census 18/22/15/20 pages, 51/62/43/57 chunks
backend: {"name": "chromadb", "version": "1.5.9", "collections": 5}
```

Corpus verify against the live estate: **PASS 29/29**. GPU discovered
free at run time: **GPU 3, 4 MiB used** (same tenant layout as CP-04′);
serving healthcheck verbatim: `OK /health · OK /v1/models lists
Qwen/Qwen3-0.6B · OK tool call parsed: get_utc_time
(finish_reason=tool_calls) · OK tool round trip: 'The current UTC time is
2026-08-04T12:00:00Z.' · healthcheck OK`. Episode networking preflighted
from a `gsj-staging-net` container before any submission: Forgejo 200,
MCP 200, gateway 200 (the CP-04′ attempt-1 failure class ruled out
before it could cost an episode). `serving_base_url` without `/v1`, MCP
HMAC secret from the CP-04′ 0600 scratch file, `zero_at_mask1_max_rate:
0.25` — all per the committed `staging/rollout.h200.yaml`.

The three engine legs, re-verified rather than assumed:

1. **`--generation-config`** — startup log, verbatim: `WARNING …
   [config/model.py:1546] Default vLLM sampling parameters have been
   overridden by /home/sysadmin/gsj-vllm/genconfig: {'temperature': 0.6,
   'top_k': 20, 'top_p': 0.95}`; genconfig sha `2325da0f…` (== the codec
   pin). Applied block from the request log on the qualifying session's
   own two turns (gateway-log session-bound to engine requests
   `chatcmpl-843bbced7905a18e` 10:19:14.501 and `chatcmpl-b0728e6e4f8a0bbe`
   10:19:17.305): `SamplingParams(… temperature=0.6, top_p=0.95,
   top_k=20, … seed=None, stop=[], … max_tokens=8192, … logprobs=0, …)`
   — no unexpected sampling params on the wire; pi sent none; the F1
   recurrence window closed.
2. **`--enable-auto-tool-choice --tool-call-parser hermes`** — in the
   live argv (read from `/proc/<pid>/cmdline`); the healthcheck's parsed
   tool_call and every episode's `tool_choice: auto` traffic prove them.
3. **`--max-model-len 32768`** — in the live argv; the collected episode
   ran a 6,715-token turn-2 prefill without a 400.

Plus the template leg: `--chat-template
/home/sysadmin/gsj-vllm/qwen3_training.jinja`, sha256 verified **on the
serving host** = `1d944ff8…` == the committed
`staging/serving/qwen3_training.jinja` byte-for-byte.

#### The collection (Step 2): assertions verbatim, attempt count honest

Submission per attempt, all on the golden's triple with **the golden's
own instruction bytes** (626 bytes, sha `361a885d…`, extracted from the
frozen `docs/golden/h200/transcript.txt` user message and byte-verified
on the H200 before use — the uid `ep-3ba9d4a1498f89fc` rides in the
text, so `prompt_ids` exact-equality is reachable at all):

```
gsj-rollout submit --config staging/rollout.h200.yaml --case case_0001 --timestep 12 \
  --prompt-file ~/cp09prime/instruction.golden.txt --task-id cp09prime-fidelity-aN \
  --timeout 900 --grace 120 --out ~/cp09prime/attemptN.json
```

**Nineteen attempts; attempt 19 qualified** (vs 7 at CP-04′ and 7 at
CP-09 — same refusal class, worse rate this run). Honest ledger:
attempt 2 was **rejected by the receiver** on
`LP6:zero_logprob_rate_at_mask1:2181/8192>0.25` — a repetitive-loop
episode over the allowance, the fail-closed seam doing its job live
(the CP-04′ attempt-4 shape recurring); attempts 1, 3–18 all returned
exit 0, `COMPLETED`, gates green, full G7 conjunction — refused by the
H-41 assertion alone (zero *successful* built-ins; grep/read error
loops, the golden's own collection history class). The qualifying
episode `sk-polar-44620742-9323-4202-9b58-474b4ed45f26`, asserted
verbatim:

```
ASSERT session COMPLETED, no builder ERROR: PASS — status=COMPLETED findings=[]
ASSERT chains_total==1 with full G7 conjunction: PASS — {"chains_total": 1,
  "chains_reconstructed_full": 1, "chains_reconstructed_truncated": 0,
  "raw_completions_total": 2, "completions_total": 2, "completions_merged": 2}
ASSERT completion_filter.excluded == []: PASS
ASSERT glue ids unset stayed dormant (glue_stitched==0): PASS — glue_stitched=0
trace: prompt_ids=2965 response_ids=3990 mask1=510 mask0=3480 logprobs=3990 finish=stop
    logprobs: positive=0 sentinel@mask1=0 0.0@mask1=37/510 (7.3%) all-0.0@mask0=True
ASSERT checks.validate_session_result == [] (estate policy 0.25): PASS
ASSERT roster on the wire == configured allowlist: PASS — 11 names, byte-identical
ASSERT completions == pi agent turns: PASS — 2 records vs 2 assistant turns
ASSERT >= 1 mcp_gsj_* executed ok: PASS — [mcp_gsj_case_status, mcp_gsj_search_decisions, mcp_gsj_search_case]
ASSERT >= 1 successful built-in executed: PASS — [write]
    tools in order: [(grep,ERR),(grep,ERR),(grep,ERR),(grep,ERR),(read,ERR),
      (write,ok),(mcp_gsj_case_status,ok),(mcp_gsj_search_decisions,ok),(mcp_gsj_search_case,ok)]
ASSERT cutoff held — every cited search page <= 12: PASS — pages [1, 5, 7, 9, 11]
```

The MCP authority log carries the session's three `tool_call` events,
each under the token's verified claims (`case_0001`, `timestep 12`). The
episode wrote the deliverable to `out/ep-3ba9d4a1498f89fc.md` — the path
the golden's instruction names (the uid substitution implication). Deposit:
`docs/polar/h200-fidelity/`.

#### Step 3 — the comparison table

Golden = `docs/golden/h200/` (`ep-3ba9d4a1498f89fc`); collected =
`docs/polar/h200-fidelity/` (`sk-polar-44620742…`). COMPARISON.md
severity order; structural mapping `prompts↔prompt_ids`,
`responses↔response_ids`, `loss_mask↔loss_mask`.

| field | golden | collected | verdict | attribution |
|---|---|---|---|---|
| G7 stats conjunction (disqualifier) | n/a (freeze-asserted) | 1/1/0; raw=total=merged=2; excluded []; `glue_stitched: 0` | PASS | — |
| tools executed (disqualifier, H-41) | 6 execs: 3 `mcp_gsj_*` ok + `write` ok (grep/read ERR) | 9 execs: 3 `mcp_gsj_*` ok + `write` ok (grep×4, read ERR) | PASS | — |
| sampling confirmed (disqualifier) | driver-sent 0.6/0.95/20 + seed 1500772333 (provenance + request log, CP-04′) | engine-applied 0.6/0.95/20, seed None, both turns (request log, session-bound) | PASS | — |
| `prompt_ids` vs `prompts` | 2965 ids | 2965 ids | **EXACT — byte-identical** (the golden's instruction bytes made the uid row reachable; the A-1 retokenization class clean on the governing platform) | — |
| `loss_mask` semantics (zero tolerance) | 2 spans [0,207)+[3631,3682), == `response_mask`, 258×1/3424×0 | 2 spans [0,270)+[3750,3990), 510×1/3480×0 | **EXACT** — 1 exactly on engine-sampled spans, 0 on glue; span count == own assistant turns (2 each); opens at r=0, closes at stream end; both traces | — |
| `response_ids` @ mask==1, decode-fidelity per trace | both spans decode **EXACT-BYTES** to own transcript (tool_call blocks + `<|im_end|>`; final text turn + `<|im_end|>`) | same, both spans | PASS (re-verified independently by the adversarial workflow) | — |
| `response_ids` @ mask==0, glue per trace | every glue span opens `\n<|im_start|>user\n`, closes `<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n`; glue-span AND `prompt_ids` tails == pinned `g6_expected_tail_ids` | same, byte-identical framing | PASS — cross-trace framing constants identical; the symmetric template's history-borne think block present exactly as CP-04′ measured | — |
| logprob discipline | finite ≤0, no sentinel, `0.0` only @mask0; 16/258 = **6.2%** exact-`0.0` @mask1 | same; 37/510 = **7.3%** | PASS (0.25 allowance, row 27 posture; the pair adds the 3rd and 4th in-allowance CUDA measurements) | platform (CUDA bf16) |
| logprob replay **as written** (through the engine, one echo request per trace) | mean&#124;Δ&#124; **0.005246** (bound 0.005), 8/258 > 0.05 (max 0.0949); per-span 0.0060/0.0023 | mean&#124;Δ&#124; **0.007141** (bound 0.005), 23/510 > 0.05 (max 0.2107); per-span 0.0027/0.0121; **NO de-stitch** — the merged stream teacher-forced directly | **beyond the stated bounds on BOTH traces, symmetrically** → the contract's own rule ("beyond it on both") + the decomposition below | platform (capture-path decode-vs-prefill numerics; the replay path itself is bit-deterministic — measured) |
| — replay-vs-replay (the contract's "rerun to bound it") | mean&#124;Δ&#124; = **0.000000**, max 0.000000 | same, exactly | the engine's teacher-force path does NOT drift run-to-run — the capture-vs-replay delta is entirely the capture-time compute path (decode steps + batch composition) vs the replay's one prefill | — |
| **capture-vs-capture on identical contexts** (105-token common response prefix — same engine, same 2965-token context, masks agree) | e.g. r=0: −0.105473 | r=0: −0.114390 | **mean&#124;Δ&#124; = 0.003672, max 0.0614; 2/105 positions > 0.05** (r=20: 0.0546, r=102: 0.0614) — capture agreement at the platform's cross-request floor; within the contract's mean bound but not spotless per-position, and the Mac pair's 0.000114 margin is gone (CUDA cross-request numerics ≈ 30× MLX's) | platform floor |
| `finish_reason` | `stop` (freeze-asserted; per-turn tool_calls → stop) | `stop` (per-turn tool_calls → stop) | PASS — allowlist, no `length` | — |
| reward / artifact (informational) | reward n/a; artifact exists (112 B, 4 sections, zero `page:N` citations) | reward None; artifact exists (85 B, 4 section labels, cites pages [1,2,3,4] ≤ 12) | both episodes delivered to the instructed path; the collected one's citations respect the cutoff census; at 0.6B the row proves existence + cutoff discipline, nothing about quality (scoring stays out — law 1) | — |

Replay per-position bound failures, individually listed (r: captured/replay):

```
golden (8/258):    r=24:-0.166/-0.227  r=49:-0.252/-0.313  r=76:-0.394/-0.338  r=102:-0.313/-0.252
                   r=106:-0.599/-0.659 r=122:-1.690/-1.781 r=164:-0.974/-0.879 r=175:-0.604/-0.550
collected (23/510): r=24:-0.167/-0.227  r=76:-0.393/-0.338  r=123:-0.987/-1.046 r=196:-0.387/-0.313
  r=240:-1.975/-1.890 r=3750:-2.883/-3.094 r=3762:-1.871/-1.794 r=3768:-1.489/-1.430
  r=3781:-1.159/-1.244 r=3783:-0.611/-0.677 r=3822:-0.477/-0.415 r=3823:-1.497/-1.574
  r=3835:-2.470/-2.335 r=3849:-0.791/-0.858 r=3852:-0.633/-0.576 r=3883:-0.982/-1.144
  r=3889:-0.523/-0.576 r=3902:-2.859/-3.050 r=3912:-1.532/-1.444 r=3916:-1.331/-1.402
  r=3918:-0.383/-0.316 r=3960:-1.325/-1.244 r=3975:-0.773/-0.844
```

All sub-nat disagreements on moderately-uncertain tokens; note r=24 and
r=76 fail on BOTH traces with near-identical values — the same context
positions drifting the same way under two different captures, the
platform signature, not a capture defect on either side.

#### The three CP-09 findings, on this pair

- **F3 (vllm-metal cannot teacher-force) — GONE, as predicted.** The
  replay ran as written through the serving engine: one
  `/v1/completions` echo request per trace, all 6,647/6,955 positions
  returned. And it is *bit-deterministic* (replay-vs-replay exactly
  0.000000) — the H200 replay leg is a real instrument, not a floor.
- **F2 (de-stitch before replay) — GONE, as CP-04′ predicted, now
  proven at replay.** `glue_stitched: 0`, chains merged natively, and
  the merged stream teacher-forced directly with no glue removal shows
  no F2-shaped excess: the collected turn-2 drift is 0.0121 vs F2's
  0.0676 at CP-09, and the worse-span direction REVERSES across traces
  (golden's worse span is turn-1 at 0.0060, its turn-2 is 0.0023) — no
  systematic turn≥2 context delta exists. Nothing contradicts CP-04′.
- **F4 (the tolerance anchor) — applies as written for the first time,
  and the bounds fail on their own terms.** Same engine, engine-path
  replay, and still: golden 0.005246 > 0.005 (a 4.9% exceedance — and
  its turn-2 span is fully WITHIN both bounds at 0.0023 with zero
  positions over; the magnitude is marginal, the bound still fails as
  written), collected 0.007141, with per-position failures on both. The decomposition (replay-vs-replay
  = 0.000000 exactly) pins the entire delta on the capture-time compute
  path — decode-step kernels and batch composition vs the replay's
  single prefill — i.e. the same prefill-vs-decode class the CP-18
  anchor (0.0036) was derived from, at a larger magnitude on this
  estate. The exceedance exists identically on the Polar-free golden,
  so it attributes to platform, not capture stamping.

#### Step 4 — the verdict

**Does Polar's trajectory reconstruction match the predecessor's, on
production hardware, with the replay run as written?**

**PASS WITH FINDINGS.** Where the contract demands exactness, the match
is exact on the governing platform: `loss_mask` semantics (the
zero-tolerance row — the comparison that matters most) exact on both
traces; `prompt_ids` byte-identical (2965/2965); per-trace
decode-fidelity exact to the byte at mask==1; glue framing constants
byte-identical across traces with the pinned G6 tail; structure and
discipline sound; cutoff held. **Not plain PASS** for one reason,
stated without softening: the replay-as-written exceeded the contract's
stated bounds — on both traces (golden mean |Δ| 0.005246 vs the 0.005
bound; collected 0.007141; per-position failures 8/258 and 23/510
against a zero allowance). The contract's own logprob row classifies a
both-sides exceedance as platform, and this CP measured the mechanism
rather than assuming it: the engine's replay path is bit-deterministic
(rerun delta exactly 0.000000), so the drift is entirely capture-time
decode-path/batching numerics against replay-time prefill numerics —
present identically on the predecessor's Polar-free capture, at the
same positions, in the same sub-nat magnitudes. **Not FAIL** because
FAIL requires a mask or retokenization divergence attributable to
Polar, and there is none — the A-1 classes are exactly clean.
**Nothing in this comparison is attributable to Polar's code.** No §9
condition fires; Path C is not costed because it is not triggered.

**Converting condition 1 is MET**: the H200 golden pair passes with the
replay run as written (this CP) and the template flip per the inherited
DoD (CP-04′). A-1 resolves on the governing platform; §5's criterion is
met on the pair that counts. What remains before the provisional adopt
converts: **condition 2 — M4's training loop** (the slime bridge running
one OPD step consuming these masks and logprobs). Consequence of the
one finding for M4: any replay-style validation must use this estate's
measured floor (mean ≈ 0.005–0.008, per-position tail to ≈ 0.21), not
the CP-18 anchor as written; trainers consuming `response_logprobs` as
behavior-policy values inherit a sub-nat capture-path noise floor that
no trace-side check can see (checks-spec §CP-09′).

#### What the H200 pair showed that the Mac pair could not

1. **The as-written replay is bit-deterministic — and the contract's
   bounds still fail.** Only an engine-path replay could show this: the
   0.005/0.05 bounds anchor a prefill-vs-decode measurement (CP-18,
   0.0036) that this estate exceeds on the predecessor's own capture.
   The bounds were never conservative enough for CUDA
   continuous-batching capture; the Mac's beside-the-engine substitute
   could not separate replay noise from capture noise. Measured here:
   replay noise = 0, capture-path noise = the whole delta.
2. **The identical-context instrument dulls on production hardware.**
   Capture-vs-capture: 0.000114 (Mac, sequential MLX) → 0.003672 (H200,
   interleaved CUDA) — ≈ 30×. It still discriminates capture semantics,
   but its two-orders-of-margin days are Mac-only. This is invisible
   trace-side: every discipline rule passes on both estates — a
   clean-presenting class, now recorded in the spec.
3. **No de-stitch, live, at replay** — CP-04′ predicted it from
   structure (native merge); this CP teacher-forced the merged stream
   directly and found no F2-shaped excess. The symmetric template's
   cure is confirmed at the numerics level, not just the grouping level.
4. **The qualification rate is platform-dependent**: 19 attempts vs 7
   on both prior collections, same H-41 refusal class (every refusal
   `completed`/gates-green), plus one live LP6 rejection at 26.6%
   zero-rate — the allowance is doing real work on CUDA exactly as
   row 27 predicted.
5. **The artifact row had a real subject for the first time** — both
   episodes delivered to the instructed path; the collected episode's
   citations ([1,2,3,4]) respect the cutoff census. At 0.6B it proves
   existence and discipline, not quality.

#### DoD, run and shown

```
$ git diff HEAD -- vendor/ corpus/ mcp-service/ forgejo/ pins/ spike/ \
    docs/golden/h200/ gsj_rollout/checks.py
(empty)
$ .venv/bin/pytest -q
125 passed in 12.74s
# the three engine legs, verbatim                (Step-1 section above)
# the collection assertions + attempt count      (Step-2 section above, 19 attempts)
# the comparison table                           (Step-3 section above)
# the replay result as written, both traces      (table + failure list above)
# the verdict, unsoftened                        (Step-4 section above)
$ ls docs/polar/h200-fidelity/
artifact  callback_session_result.json  comparison_results.json
mcp_authority_log.jsonl  pi_transcript.jsonl  replay_rerun.txt
sampling_evidence.txt  trace.json
$ grep -n 'A-1\b' docs/CHARTER.md
193:| A-1 | … | **RESOLVED — empirically on BOTH pairs; the H200 (governing) at CP-09′** …
$ test -f docs/reports/CP-09prime.md && echo OK
OK
$ git status --porcelain      # after commit
(empty)
```

Estate torn down after the comparison per the standing rule (CP-34/
ADR-0048 discipline): receiver, gateway, rollout server stopped; vLLM
stopped and the workstation tunnel closed; MCP and Forgejo containers
down and `gsj-staging-net` removed; estate ports closed; GPU 3 back to
4 MiB. Fast-path artifacts left in place: Forgejo/MCP data dirs, the
serving venv + snapshot + genconfig + template under `~/gsj-vllm`, both
collector venvs, `~/cp04prime` and `~/cp09prime` scratch (attempt
bodies, logs, the comparison scripts and results).
