# CHARTER — gsj-harness-rollout-server

The normative document. `CLAUDE.md` governs process; this file governs
content. Predecessor: `gsj-envloader` @ v0.8.0 — alive, frozen, not
retired; the fallback and the golden reference.

## 1. What we are building

A **rollout server for our corpus**. Given a task `(case, timestep,
prompt)` it runs our agent in an isolated sandbox with temporally-scoped
retrieval and emits a training-ready trajectory. Trainer-agnostic,
algorithm-agnostic, parameterization-agnostic. Episode execution and
trajectory reconstruction are NVIDIA Polar's, vendored by SHA; our code is
the thin shell that points Polar at our corpus, our MCP service, our pinned
pi, and our checks.

**The scope law**: "The rollout server owns: task → sandbox → agent →
trace. Nothing else. If it stores, schedules, scores, weights, versions,
or trains — it's out."

**Size budget**: our own code stays under **1,500 lines**, excluding
vendored Polar, tests, and the moved components (`corpus/`,
`mcp-service/`, `forgejo/`). A checkpoint that pushes past it must stop
and justify.

## 2. Why this repo exists

The predecessor works and is externally verified — the zero-CLI proof and
the recorded runs in `gsj-envloader-examples` are real evidence. But
roughly **1,800 of its lines are episode execution and capture**
(`task.py`'s checkout→run→harvest→reset lifecycle with docker bolted
inside it, `uniagent_driver.py`'s per-episode gateway sessions,
`collector.py`'s finalize pipeline), and that layer was expensive to
maintain: the G2 approved set had to be re-derived at nearly every image,
rename, or mount change; the capture transport changed three times; a
silently load-bearing parser dependency (sglang, H-41) once produced
gates-green but tool-free episodes; and dismantling the dev harness around
it took two dedicated checkpoints. This repo tests whether Polar can own
that layer. **We are not migrating; the predecessor stays alive.** If the
answer is no, we say so and stop (§9).

## 3. What we start with

**Carried over** (moved, not rewritten — landed at CP-01; measured own-code
lines, ADR-0002 is the boundary):

| component | lines (measured, CP-01) | what it is |
| --- | --- | --- |
| `corpus/` | 1,195 pipeline + 662 tests + 163 staging data files | the corpus source of truth + five-phase ingestion pipeline (taskbank phase deferred to CP-07, ADR-0003) |
| `mcp-service/` | 1,390 package + 1,615 tests + ~480 config/docs | the hosted streamable-http MCP service: per-episode JWTs, per-session cutoff clamp |
| `forgejo/` | 191 | git-host bring-up: case repos with `timestep-{T}` branches |
| pins / G2 tooling | 174 + 5 captured-evidence files | `derive_g2.py` byte-substitution derivation + the captured G2/G3/G6/G7 evidence; the `gsj-pin` generator turned out to be predecessor *library* code and stayed frozen there (ADR-0002) — the approved-set format is specified in `docs/checks-spec.md` |
| the corpus contract | 309 | `corpus-contract.md`, the normative corpus document — byte-identical copy |

**Adopted**:

| component | how | what it owns |
| --- | --- | --- |
| Polar (NVIDIA) | vendored by SHA at CP-03; no releases, so pinned commit + recorded re-vendor recipe + carried patches | episode execution, sandbox lifecycle (start/stop/exec/upload/download), the model proxy, trajectory reconstruction (`prefix_merging`), the slime bridge |

**Written here** (the budget per module):

| module | budget (lines) |
| --- | --- |
| `pi_harness.py` | 50–150 |
| `receiver.py` | 50–100 |
| `checks.py` | 150–250 |
| `config.py` | ~100 |
| `client.py` | ~80 |
| `cli.py` | ~60 |

Sum 490–740 — the 1,500 ceiling is headroom, not a target.

**Deliberately dropped** (and whose problem each becomes):

- the store — trainer's problem
- the loader (`ready`/`mix`/leases/serve accounting/SPI) — trainer's problem
- staleness tracking — trainer's problem
- collation — trainer's problem
- `GsjCaseTask` — Polar's problem
- `uniagent_driver` — Polar's problem
- `collector` — Polar's problem

## 4. What we assume

Every new assumption gets a row here immediately. **Unverified is not
false** — a reported defect stays UNVERIFIED until a checkpoint verifies
it.

| # | assumption | basis | if false |
| --- | --- | --- | --- |
| A-1 | Polar's `prefix_merging` reconstructs multi-turn token streams correctly | **LINE-VERIFIED at CP-05** (algorithm; token fidelity stays CP-09's question): the retokenization guarantee holds in code — assistant tokens come only from engine-sampled ids, never from a prompt re-rendering (`record_utils.py:82-107`, `prefix_merging.py:337-353`; no tokenizer anywhere in the builder); grouping is a strict token-id prefix test (`prefix_merging.py:399`); the interstitial split implements the paper's §3.4.2 exactly (`prefix_merging.py:326-334`). Adversarially re-verified (6-agent pass, 17/18 claims confirmed, 1 scope-corrected). **But every discovered failure mode degrades silently to `status=COMPLETED`** — truncation, chain degeneration, EOT misdetection, filter amputation, `choices[0]`-only capture, discard-and-reprompt — catalogued in `docs/checks-spec.md` §silent-degradation; verdict: **GO WITH CONDITIONS** (CP-05 report) | CP-09 fidelity fails against the golden reference with no fix in our code → abandon (§9) |
| A-2 | Polar's proxy handles pi 0.83.0's traffic unmodified | the proxy is provider-generic by design; untested against 0.83.0 | a forked translation layer would be needed → abandon (§9) |
| A-3 | pi package identity: **RESOLVED** — same tool; `@mariozechner` deprecated → `@earendil-works`; Polar's preset pins 0.67.68, we run 0.83.0 | npm deprecation trail traced | n/a (resolved); if the rename hid a fork, the CP-05 source audit catches it |
| A-4 | the per-episode cutoff token is injectable via `run_steps()` | Polar's episode API takes per-episode parameters | the cutoff must ride another channel (env, MCP session claim); CP-10 decides — no channel at all → abandon (§9) |
| A-5 | the callback payload is sufficient for `checks.py` (token ids, `loss_mask`, logprobs, metadata) | Polar emits training-ready traces for its slime bridge; **CP-05, verified at source**: the callback body is `SessionResult.model_dump(mode="json")` (`node.py:860`) carrying full traces (token ids, `loss_mask`, logprobs, messages, tools, `finish_reason`), `reconstruction_stats`, and a writable metadata channel — builder-subclass keys survive to the callback verbatim and on into slime `Sample.metadata["polar"]` (`adapter.py:141-160`); the endpoint revalidates pydantic shape only (`rollout/server.py:170-173`). **Caveat**: per-completion records do NOT ride the callback (only the `completion_metadata` extracts in trace metadata), so session-level checks must run builder-side — the receiver alone cannot see them | receiver must re-fetch or reconstruct; re-scope at CP-08 |
| A-6 | slime can run OPD against Polar traces | Polar ships a slime bridge | trainer needs an adapter — trainer's problem, but it weakens the CP-12 verdict |
| A-7 | **RESOLVED at CP-02 — partially confirmed**, per defect: **D1 leak CONFIRMED, worse than reported** — upstream at the pin has *no* non-agent completion filter at all (the whitelist was fork code; every auxiliary harness call becomes a trainable trace carrying session reward); **D2 PARTIAL** — vLLM `-9999.0` flows to the trainer unvalidated at the pin (confirmed; zero value-level logprob checks upstream), but `_logprob_integrity` is fork-only and the interstitial `0.0` is mask==0-only (benign, matches our rule); **D3 CONFIRMED end-to-end** — statuses are {COMPLETED, TIMEOUT, ERROR}, `finish_reason=="abort"` is handled nowhere, a mid-chain abort presents a *clean* chain snapshot; **D4 REFUTED for upstream** — reasoning masking is fork-only, the pin emits all-ones `loss_mask` unconditionally | commit patches read + upstream line-verified at `f0e8343a` (CP-02 report, ADR-0004) | D1/D3 become carried patches P1/P2 at CP-03; the sentinel guard lands in `checks.py` as an **explicit threshold rule** — the finite-and-≤0 rule does NOT auto-reject `-9999.0` (spec corrected at CP-02) |
| A-8 | vendoring a release-less branch is sustainable | pinned SHA + recorded re-vendor recipe + carried patches; **CP-03 evidence**: first vendor executed at moderate cost (~one working day incl. patch adaptation, component venv, smoke run; all three patches apply clean from `vendor/apply_patches.sh`; upstream suite 175 passed / 3 pre-existing failures); re-vendor estimated ~half day, the `prefix_merging` refactor is the named risk (`vendor/REVENDOR.md`) | maintenance cost balloons; re-decide the dependency posture in an ADR |
| A-9 | the carried components transfer unmodified | they were built host-portable behind the corpus contract; predecessor law forbade host-layout dependence in library code | fixes happen here (the predecessor is frozen) and the touched row flips to GAP until cured |
| A-10 | reward sparsity at demo scale is a method/scale property, not infrastructure | the predecessor's recorded runs show the same | still not a rollout-server defect — out of scope by the scope law |
| A-11 | **Apptainer deferred** — Polar supports it natively; we stay on Docker so the CP-09 comparison has one variable | Polar's README lists the Apptainer runtime; the predecessor was Docker-only, so Docker is the controlled variable | revisit on a cluster without a daemon; law 5 keeps `gsj_rollout/` runtime-agnostic so nothing needs rewriting |
| A-12 | our pi harness makes no auxiliary (non-agent-loop) LLM calls through Polar's gateway | unverified — agentic harnesses routinely do (D1's measured leaked body was a verbatim Read-tool-result echo from an auxiliary call) | every auxiliary call becomes a well-formed `chain_length=1` trainable trace carrying full session reward (measured density up to 27% of a batch on the fork); carried patch P1 is the only defense (landed at CP-03, adversarially verified faithful) — verify at CP-06 by counting captured completions against agent turns, and re-validate P1's Anthropic-shaped criteria against pi's actual wire dialect; CP-03 smoke datapoint (not pi evidence): mini_swe_agent made 40/40 agent-shaped calls, filter excluded none |
| A-13 | until carried patch P3 (per-turn `policy_version` stamping) is active, the trainer drains all in-flight sessions before every weight sync | D5 audit: at the pin a session spanning a weight sync is assembled as COMPLETED with a clean chain snapshot and only the stale submission-time version — invisible on the wire and retroactively unauditable; CP-03: P3 landed inert (stamping + persistence fix present and verified; nothing declares versions yet — confirmed no `policy_version` key on a real persisted record) | mixed-weight traces train silently; the receiver cannot catch what the capture layer never records (the declared limit of law 6) |
| A-14 | `vendor/polar/.venv` (Python 3.12) can host `gsj_rollout` when CP-06 wires the `import_path` harness — the dependency points Polar→us, and our core deps (pydantic/httpx/pyyaml) are a strict subset of Polar's five (fastapi/uvicorn/httpx/pydantic/pyyaml) | ADR-0005; both dependency sets read from the two pyprojects at CP-03 | a version conflict forces re-deciding the environment split (dedicated harness venv, or loosening root pins); the root package never grows Polar deps either way |
| A-15 | gsj rollouts always pin `end_of_turn_token_id` in the builder config — EOT auto-detection is never relied on | CP-05: auto-detect takes the last sampled token of the FIRST natural-stop completion in the chain (`prefix_merging.py:286-302`, natural = `{stop, tool_calls, stop_sequence}`); a stop-parameter/stop-sequence finish makes that an arbitrary token (a newline, a `</tool_call>`), and a wrong EOT mis-splits every interstitial — duplicated assistant-body fragments ride in as mask-0 tokens, corrupted-but-COMPLETED; with no natural stop in a chain at all (every turn `length`), every merge silently truncates instead; detection is per-chain, so two chains in one trajectory can even resolve different ids | an unconfigured EOT on a real run degrades every multi-turn chain to silent truncation or silent corruption; the builder-subclass check (explicit eot config present, else reject) fails closed |

## 5. What we are testing

Four questions:

1. **Does Polar run our pi?** Our pinned pi 0.83.0, launched by an
   `import_path` harness, through Polar's proxy, inside a Polar-managed
   sandbox.
2. **Does our cutoff survive?** The timestep's page cutoff enforced
   per-episode, end to end, through our MCP service — nothing past page T
   visible through any channel.
3. **Are the traces trustworthy?** Token ids, `loss_mask`, and logprobs
   that pass `checks.py` — the gates' evidence reconstructable from what
   Polar captures.
4. **Can a trainer consume them?** Submit with `client.py`, receive
   validated traces, feed slime.

The success criterion, verbatim: *one real episode against our corpus,
through our MCP service, with the cutoff enforced, producing a trace whose
token ids, `loss_mask`, and logprobs verifiably match the golden reference
the predecessor produced for the same task.*

## 6. The plan

GPU needed only at CP-04 and CP-09. Decision points — where the plan may
legitimately stop — are **CP-05**, **CP-09**, and **CP-12**.

| CP | what | notes |
| --- | --- | --- |
| CP-00 | scaffold | this checkpoint |
| CP-01 | moves | `corpus/`, `mcp-service/`, `forgejo/`, pins tooling, corpus contract |
| CP-02 | fork audit | the four reported defects (A-7): verify or refute each |
| CP-03 | vendor Polar | pinned SHA, re-vendor recipe, `[server]` deps become real |
| CP-04 | golden reference | predecessor produces the reference trace (GPU) |
| CP-05 | source audit | Polar line-read against A-1/A-4/A-5 — **decision point** |
| CP-06 | harness spike + stub | smallest pi-under-Polar episode |
| CP-07 | the harness | `pi_harness.py` + first `checks.py` validators |
| CP-08 | receiver / config / CLI | `receiver.py`, `config.py`, `client.py`, `cli.py` |
| CP-09 | fidelity | trace vs golden reference (GPU) — **decision point** |
| CP-10 | sentinels + cutoff | logprob sentinel guard; cutoff enforcement proven |
| CP-11 | surviving gates | which of G1–G7 survive as `checks.py` validators |
| CP-12 | the verdict | the gap register closes the argument — **decision point** |

## 7. Gap register

The table this repo is judged by. **Every CP updates this table.** A
capability silently disappearing is exactly the failure this table exists
to prevent — DROPPED is a decision with a named owner, never an accident.
Status ∈ `PARITY | DROPPED | GAP | BETTER | TBD`.

| # | capability | gsj-envloader | here | status | notes |
| --- | --- | --- | --- | --- | --- |
| 1 | corpus contract | `docs/corpus-contract.md` — the normative corpus document | moved at CP-01, byte-identical (zero library references, measured) | PARITY | landed CP-01 (ADR-0002) |
| 2 | retrieval cutoff | timestep T = page cutoff: checkout pinned to `timestep-{T}` branch; MCP per-session cutoff clamp; G5 enforces at collection | injected per episode via `run_steps()` (A-4); the MCP clamp carries over | TBD | CP-01: the clamp's owner (`mcp-service/`) and the timestep-branch tooling (`corpus/`, `forgejo/`) are here — component-level parity; end-to-end enforcement proven at CP-10; not injectable at all → abandon (§9) |
| 3 | git host | Forgejo estate: case repos with timestep branches; compose + bring-up/teardown scripts | moved at CP-01: `forgejo/` (data dir re-rooted inside the component; live H200 estate keeps its compose-project identity) | PARITY | tooling parity — no bring-up ran at CP-01 (out of scope); the H200 networking archaeology (static container IP, `host.docker.internal`) is documented in-file, inherit deliberately or not at all |
| 4 | taskbank | `taskbank.py` builds the §3.1 parquet: skill rows resolve at rollout, free rows verbatim | tasks arrive as `(case, timestep, prompt)` via `client.submit` | TBD | CP-01: builder NOT moved — deferred to CP-07 (ADR-0003); the phase raises, verify's row checks deferred with it; the frozen bank + lock carried as data (ADR-0002), still sha256-verified |
| 5 | episode isolation | fresh per-episode checkout + ephemeral `docker run --rm` + per-episode gateway actor | Polar sandbox: start/stop/exec/upload/download | TBD | CP-06/CP-07; CP-02: a fork (yichuan-w) works around two reported Docker-runtime defects — event-loop starvation in `DockerRuntime.start()` and task timeout not killing containers — UNVERIFIED here, check live at CP-06; CP-03: DockerRuntime ran live on macOS (4 parallel sandboxes via docker CLI create/exec/cp/rm, clean teardown observed; the two reported defects stay UNVERIFIED — nothing timed out); macOS networking fact for CP-06: task `network: "host"` does NOT reach the macOS host loopback unless Docker Desktop host networking is enabled — set `node.public_url` to the host LAN IP, which works from bridge and host-net containers *and* from the host-side rollout dispatch (the same URL serves both) |
| 6 | harvest-before-reset | type-level guarantee: `_reset` requires a `HarvestResult`; artifacts copied out before any git command | Polar's problem — its lifecycle must give an equivalent guarantee | TBD | CP-05 source audit checks for it; CP-05: the ordering EXISTS but as control flow, not types — `_handle_postrun` runs `_build_session_result` (build+eval, `node.py:505`) before teardown starts (`node.py:513-531`); trace data itself is proxy-time capture into the in-memory `SessionStore`, so trajectory construction never depends on the sandbox at harvest time; live confirmation at CP-06 |
| 7 | token/logprob capture | gateway codec renders the pinned template; token-level loss mask; sampling-time `rollout_log_probs`; capture-once | Polar's proxy + trace reconstruction | TBD | fidelity is CP-09; CP-02: at the pin nothing value-validates logprobs (the slime adapter checks presence and length only) — vLLM's `-9999.0` sentinel flows to the trainer; our guard supplies a missing check, not a duplicate (row 27); CP-03 live run: with no engine token ids the trace ships empty `prompt_ids`/`response_ids` and null logprobs (mlx-lm's `{"id",logprob}` entries are a dialect the pin's normalizers don't read) — value-level capture genuinely requires vLLM/SGLang (CP-09); also upstream's own sglang meta_info-recovery test FAILS at the pin (engine.py stamping skips on length mismatch → `KeyError: token_id`) — pre-existing test-vs-src drift, verified not introduced by our patches; CP-05: the capture surface line-verified — `prompt_ids` from `choice.input_token_ids`/`choice.prompt_token_ids`/`response.prompt_token_ids` (`record_utils.py:136-140`, NOT int-coerced), `response_ids` from `choice.token_ids`/`response.token_ids` else `logprobs.content` pairing (requires the `token_id` key — mlx's `id` fails at `:38`) else sglang `meta_info` (`:82-107`); NO value-level logprob validation exists anywhere in the vendored tree (grep isfinite/isnan/isinf/9999: zero hits), and the missing-logprob rejection at the pin is STATUS-derived, not config-gated (`adapter.py:120,274-278`; `require_trainable_logprobs` is a kwarg, not a config surface) — checks-spec corrected; `choices[0]` is the only choice ever consumed (`record_utils.py:131-134`) — `n>1` sampling loses every other choice silently |
| 8 | multi-turn stitching | chains over the rendered stream; call offsets cross-checked against mask transitions | Polar `prefix_merging` (A-1 — line-verified at CP-05; fidelity pending CP-09) | TBD | the central bet of the whole repo; CP-02: the pin emits `reconstruction_stats` (chains_total, truncated, merged counts) into trajectory metadata — the G7 snapshot is readable receiver-side with zero patches, BUT silent chain truncation still returns COMPLETED, and `trajectory/registry.py` resolves builder strategies by import path — a validating `PrefixMergingBuilder` subclass in `gsj_rollout` is a zero-patch insertion seam; CP-03: real artifacts dumped (`docs/polar/`), live `reconstruction_stats` shape confirmed incl. P1's `raw_completions_total`; DEGENERATION PROVEN LIVE: with empty `prompt_ids` every completion starts its own chain — 10 length-1 chains reported as `full=10, truncated=0`, a clean-looking snapshot with zero actual merging — so G7 must require `chains_total == 1`, never just `truncated == 0`; CP-05 LINE-VERIFIED (A-1): retokenization guarantee + §3.4.2 interstitial split confirmed in code; degenerate-case mechanism confirmed at `prefix_merging.py:399` (`0 < n` guard; each length-1 chain counts `chains_reconstructed_full`); the finalize-loop prefix break (`:212-221`) is defensive dead code (grouping guarantees the pair property — adversarially re-verified); the builder README's "message-level grouping key" does NOT exist at the pin (grouping is token-prefix only — README-vs-code divergence, likely the unlanded `polar`-branch refactor); seven silent-degradation modes catalogued in `docs/checks-spec.md` §silent-degradation, ALL presenting as COMPLETED |
| 9 | gate G1 skill_card | sha256 of the rollout-resolved skill-card text ∈ approved set; free prompts pass | `checks.py` validator | TBD | CP-11 decides survival |
| 10 | gate G2 system_prompt | sha256 of the wire system prompt ∈ approved set; path-sensitive, collapsed to a singleton by constant container paths | `checks.py`; different sandbox mount paths silently change every hash | TBD | expect a re-derive walk when Polar's mounts differ |
| 11 | gate G3 tool_roster | sha256 over canonical JSON of the tools array **as sent on the wire** | `checks.py`; needs wire-roster capture from Polar's proxy | TBD | inseparable from row 31; CP-03: the wire tools array IS captured — persisted completion records carry it in both `original_request` and `transformed_request` (`docs/polar/completion_record.json`); caveat: the persisted `transformed_request` is pre-engine-shaping (the `logprobs`/`return_token_ids` fields sent on the wire are absent from disk); CP-05: the MERGED trace's `tools` field is the FIRST completion's transformed-request tools only (`record_utils.py:117-122,150` via `prefix_merging.py:276`) — a mid-session roster change is invisible in the merged trace, so receiver-side G3 must be complemented by a builder-subclass per-completion roster check |
| 12 | gate G4 codec | tokenizer.json git-blob OID + chat-template sha256 ∈ approved sets | `checks.py` | TBD | four distinct hashing conventions across the gates — reproduce exactly |
| 13 | gate G5 page_cutoff | pin-free: max checkout page == T, pages contiguous from 1, every search-result page ≤ T | `checks.py`; needs a page census reconstructable from the trace | TBD | unreconstructable from the trace → abandon (§9) |
| 14 | gate G6 thinking_off | every assistant-turn opening ends with a pinned verbatim tail; zero turns fails closed | `checks.py`; needs decoded turn openings | TBD | |
| 15 | gate G7 no_compaction | settings canonical-JSON hash + `compaction.enabled == false` + chain snapshot exactly (1 chain, 0 rollbacks, 0 dropped tokens, 1 finalized) | `checks.py`; Polar must surface a chain-state equivalent | TBD | CP-02: abort→ERROR defect (D3) CONFIRMED at the pin — a mid-chain abort presents a *clean* snapshot, so the snapshot alone cannot satisfy G7's premise; carried patch P2 (abort→session ERROR) is the guard, and `checks.py` adds a `finish_reason` allowlist that catches tail aborts for free; CP-03: P2 landed, adversarially verified faithful, abort tests green, and the propagation chain (builder ERROR → node → SessionResult → slime FAILED → zero loss mask) re-verified link-by-link at the vendored tree; the live run adds the second G7 requirement — a token-id-less backend produces a CLEAN snapshot of N length-1 chains, so require `chains_total == 1` too (row 8); CP-05 tightens the equalities again: require `chains_total == 1` ∧ `chains_reconstructed_truncated == 0` ∧ `completions_merged == completions_total` ∧ (with A-12 verified) `raw_completions_total == completions_total` — filter amputation of a chain TAIL still counts `chains_reconstructed_full` (the `kept == len(chain)` test runs against the post-filter chain, `prefix_merging.py:261-262`) and is invisible to the first two conditions alone |
| 16 | quarantine | two layers: hygiene (any gate failure ⇒ never served, kept for forensics) + row-level cap-quarantine | receiver drops failing traces at the source; no store to quarantine into | DROPPED | dropped with the store (§3); the at-source rejection half survives by law 6 — forensic retention is the trainer's problem; CP-02: `node._push_result` → callback → our receiver confirmed as the natural zero-patch checks home; upstream's own failed experiment (a `had_abort` metadata flag dropped in Polar→slime serialization) says validation-critical signals must ride status/structural fields, never metadata flags; CP-03: one real callback payload dumped (`docs/polar/callback_session_result.json` — the exact `node._push_result` body); NOTE the rollout server's persisted `ses_*.json` is NOT that body — `_storage_payload` strips `trajectory.status`/`trajectory.error` before writing — the receiver must validate the POSTed payload, never reconstruct it from rollout disk; CP-05: strip confirmed disk-only at `pipeline.py:423-436`; the callback endpoint validates pydantic shape only (`rollout/server.py:170-173`); and the rejection seam is REAL — a builder-subclass `status=ERROR` survives the whole path because the node only escalates, never clears (`node.py:579-587,602-610,615-624`; eval merge preserves status, `:700-738`) |
| 17 | store | append-only content-addressed Parquet `TrajectoryStore` | — | DROPPED | trainer's problem |
| 18 | ready/mix | pinned predicate grammar + composition planner | — | DROPPED | trainer's problem |
| 19 | staleness | `policy_lag` vs the shared version counter; teacher tapes null-lag by definition | — | DROPPED | trainer's problem |
| 20 | serve accounting | lease-based serve/commit in one transaction; `serve_count`; SPI thermostat | — | DROPPED | trainer's problem |
| 21 | collation | four shipped collators (`Default`/`SFT`/`OPD`/`RLVR`); no truncation anywhere by design | — | DROPPED | trainer's problem |
| 22 | provenance | `env.provenance`: the four evidence hashes, codec fingerprint, applied sampling block, exact invocation argv | trace metadata must carry an equivalent | TBD | CP-08/CP-09; CP-02: pin bug — anything a hook adds to `record.metadata` in memory never reaches the persisted completion files (the writer enqueues `dict(metadata or {})`, not `dict(record.metadata)`); P3 carries the fix; provenance must not rely on in-memory metadata mutation; CP-03: P3 landed and verified — the persisted record's metadata is now record-truthful, so provenance MAY ride `record.metadata` and reach disk; inertness confirmed on a real persisted record (no `policy_version` key with no declared version); CP-05: builder-subclass metadata keys survive to the callback verbatim and into slime `Sample.metadata["polar"]` (`adapter.py:141-160` deep-copies both trajectory and trace metadata); the key `evaluation` is RESERVED (overwritten by the eval merge, `node.py:737`); chain-level trace metadata presents the FIRST completion's values as the chain's (`prefix_merging.py:371-375`) with no homogeneity check — per-turn truth lives only in the `completion_metadata[]` list, so the receiver's "all per-turn stamps equal" rule must iterate that list, and the `prefix_merging cross-version fallback` referenced by a `storage.py:150` comment does NOT exist in the vendored builder (fork half, deliberately not carried) |
| 23 | pins | `gsj-pin`: approved-set JSON, generated data, zero hash literals in code | `derive_g2.py` + captured evidence carried (`pins/`); the pinned VALUES did not move — stale by construction under Polar's mounts (ADR-0002); the `gsj-pin` generator is predecessor library code and stayed frozen there | GAP | deliberate: no valid approved sets exist here until the derive → re-pin → first-episode-validate walk under Polar's mount scheme (CP-07/CP-10/CP-11); the format `checks.py` consumes is specified in `docs/checks-spec.md` |
| 24 | deterministic env pinning | uni-agent by SHA; sglang exact-pinned; generated `collector-requirements.txt`; image tag in provenance | Polar vendored by SHA (law 4) + pinned pi 0.83.0 | TBD | CP-03: the Polar half landed — `/POLAR_SHA`, patched tree committed, component venv per upstream's own recipe |
| 25 | one-YAML config | one YAML is the complete construction surface for both sides | `config.py` (~100 lines) | TBD | CP-08 |
| 26 | bounded collection | `gsj-collect`: bounded rounds, graceful drain, stated exit codes | Polar's scheduler owns episode counts | TBD | H-34's lesson stands: bounded exit, signal handling, progress output are table stakes |
| 27 | logprob sentinel guard | validators require `rollout_log_probs` finite and ≤ 0 everywhere — written to admit the `0.0` that record semantics place at mask==0 positions | `checks.py` guards the `-9999.0` sentinel with an **explicit threshold rule** — the finite-and-≤0 rule alone passes it (A-7 audit, spec corrected) | TBD | CP-10; CP-02: upstream has no value-level guard at all, so ours is load-bearing; also make absent/None `response_logprobs` a hard failure; CP-05 corrections: (a) the pin's missing-logprob rejection is STATUS-derived, not config-gated — `require_trainable_logprobs` is only a kwarg fed from `trainable = status not in (ABORTED, FAILED)` (`adapter.py:120,268`); a trainable trace with any `mask==1` and no logprobs RAISES trainer-side — our receiver rule stays because it fires earlier and on both sides; (b) zero value-level checks tree-wide re-confirmed by grep; (c) `models.py:116` lets an EMPTY `loss_mask` bypass the length validator — `checks.py` must hard-fail an empty mask on a trainable trace, never inherit that escape; (d) the builder's `0.0` placeholders can never land at `mask==1` (`prefix_merging.py:364,368` — any missing trainable slot nulls the WHOLE array first), so a `0.0` observed at `mask==1` is engine-reported and our suspicious-zero rule stands |
| 28 | async staging | no capability by this name; nearest referents: per-episode asyncio gateway loop, collector streaming rounds | the receiver is a callback endpoint — asynchronous by construction | TBD | pin down what this must mean at CP-08 |
| 29 | multi-provider harness support | deliberately single-harness: pi via pinned uni-agent; "provider" meant only the pi models.json id and the tool-call parser | Polar's `import_path` runs arbitrary harnesses; we need only pi | TBD | potential BETTER, unverified |
| 30 | HPC runtime | none — Docker-only, single H200 host, SSH-tunnel topology | Polar supports Apptainer natively; deferred by A-11 | TBD | potential BETTER; law 5 keeps it free; CP-02: two forks (leeyykk, skzhang1) independently rework `runtime/apptainer.py` on real clusters (direct-exec instead of instance start/stop, dropped resource limits, proot wrapper) — field evidence the pin's Apptainer runtime needs work before A-11 is exercised |
| 31 | tool roster visible in config | `tools_allowlist` is a required, pinned `TaskConfig` field rendered to `--tools` argv; G3 hashes the wire-rendered roster | **if `pi_harness.py` bakes the roster into argv literals, G3 has no pinned input** | GAP | keep the roster a hashed field in `config.py`; close at CP-07/CP-08 |

## 8. Standing rules

The seven scope laws as operating rules:

1. Own task → sandbox → agent → trace and refuse everything else: no
   storing, scheduling, scoring, weighting, versioning, or training.
2. Count our own lines every checkpoint; crossing 1,500 stops the work
   until justified in an ADR.
3. Never touch `gsj-envloader` — read it, compare against it, fall back to
   it, but no checkpoint modifies it.
4. Vendor Polar by pinned SHA with a recorded re-vendor recipe; carry
   patches as first-class, documented artifacts.
5. Keep `gsj_rollout/` runtime-agnostic: the runtime is a config value and
   Polar's sandbox interface (start/stop/exec/upload/download) is the only
   contract assumed.
6. Ship one `checks.py` and run it on both sides of the wire — the
   receiver drops bad traces at the source, the trainer re-verifies on
   arrival.
7. Treat findings as deliverables: a checkpoint that proves Polar cannot
   do something is a success, recorded in the gap register, not a failure
   to route around.

## 9. What would make us abandon this

Stated in advance so the decision isn't made under sunk cost. Any of:

- `prefix_merging` output does not match the golden reference and the
  mismatch has no fix in **our** code.
- The proxy needs a forked translation layer to speak to pi 0.83.0.
- The cutoff cannot be injected per-episode through any sanctioned channel.
- G5 (the page cutoff) is unreconstructable from the trace.
- Our own code exceeds ~1,500 lines — the "thin shell" premise is false.
