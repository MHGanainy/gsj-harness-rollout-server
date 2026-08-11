# docs/polar — real Polar artifacts

**`h200-stitch/` is the CP-04′ stitch-retirement evidence** (the H200
estate under the symmetric served template, `generation_prompt_glue_ids`
UNSET — Polar's grouping merging natively). **`fidelity/` is the CP-09
comparison episode** (collected through `gsj-rollout submit`, measured
against `docs/golden/mac/` — verdict in `docs/reports/CP-09.md`).
**`pi-corpus/` is the authoritative record of *our* traffic** (CP-07:
pi 0.83.0 against the real corpus, real MCP service, cutoff live). `pi/`
(CP-06 stub) and the top-level CP-03 mlx files stay as the record of the
build-up: `pi/` for the wire dialect proved against a stub, CP-03 for the
first smoke run and the S1 degeneration proof.

## h200-stitch/ — the CP-04′ stitch retirement (glue ids unset, chains merge natively)

Captured 2026-08-11 on the H200 estate (vLLM 0.26.0+cu129 serving
`Qwen/Qwen3-0.6B` @ `c1899de…` under `--chat-template
staging/serving/qwen3_training.jinja` — the Direction-A symmetric
template), both episodes collected through `gsj-rollout submit` off
`staging/rollout.h200.yaml` with **`generation_prompt_glue_ids` unset**.
Both merged natively: `chains_total == 1`, the full G7 conjunction
(1/1/0, raw == total == merged == 2), `glue_stitched: 0` — ADR-0007's
stitch stopped being load-bearing exactly as its amendment predicted, and
F2 dissolves at the root (the merged stream IS the wire context).

- `attempt4.quarantined.json` — the receiver's quarantine record for
  session `sk-polar-688d8dc3-aa74-4b8d-803b-4b969b129487`: COMPLETED,
  clean everywhere except `LP6:zero_logprob_rate_at_mask1:34/237>0.0`
  under the then-configured strict CUDA policy — the live measurement
  that falsified row 27's "a CUDA estate sets `0.0`" premise (14.3%
  exact-`0.0` at mask==1 on native CUDA bf16). The receiver's fail-closed
  seam shown doing its job on a real wire, findings + full body together.
- `attempt5.accepted.json` — the accepted collected body for session
  `sk-polar-dae2b26a-c62d-4b43-96d5-4a2a98eff4e0` (policy at the CP-10
  default 0.25): `prompt_ids` 2965, `response_ids` 15803 (8506 mask-1 +
  7297 mask-0), zero-rate 24.9% — a repetitive failed-`read` loop episode
  that still completed, merged, and passed every gate; also the fresh
  H200 wire evidence behind the pins re-verification (G2's `/workspace`
  singleton and G3's roster hash reproduce from this trace — provenance
  notes in `pins/pins.gsj.json`).

## h200-fidelity/ — the CP-09′ comparison episode (the governing pair's collected half)

Captured 2026-08-11 on the H200 estate (the CP-04′ recipe brought back
per `staging/README.md`; vLLM 0.26.0+cu129 under the symmetric template,
all three engine legs re-verified — see the CP-09′ report's Step 1).
Session `sk-polar-44620742-9323-4202-9b58-474b4ed45f26`, task
`cp09prime-fidelity-a19` (**attempt 19** — 17 refused on the H-41
successful-built-in leg, attempt 2 rejected live by the receiver's LP6
at 26.6% zero-rate), the golden triple with **the golden's own
instruction bytes** (the uid `ep-3ba9d4a1498f89fc` rides in the text —
COMPARISON.md §H200 half). 2 completions, `chains_total == 1`,
`glue_stitched: 0` (ids unset — native merge), `finish: stop`, 510
mask-1 / 3480 mask-0. Measured against `docs/golden/h200/` per
COMPARISON.md executed in full, replay **as written** through the
engine: verdict **PASS WITH FINDINGS**, converting condition 1 met
(`docs/reports/CP-09prime.md`).

- `callback_session_result.json` — the receiver-accepted callback body,
  byte-verbatim; `trace.json` — its extracted trace.
- `pi_transcript.jsonl` — pi's `--mode json` event stream (harness
  postprocess download).
- `mcp_authority_log.jsonl` — the session's three `tool_call` events
  under verified claims (from the 0.3.0 service's stdout).
- `comparison_results.json` — every number in the CP-09′ comparison
  table, as computed estate-side.
- `replay_rerun.txt` — the replay-vs-replay determinism measurement
  (exactly 0.000000 on both traces; the attribution's load-bearing leg).
- `sampling_evidence.txt` — the gateway-log session binding + the two
  engine request-log `SamplingParams` lines + the startup override
  warning (the F1 window closed, deposited because the trace cannot
  carry it — row 22).
- `artifact/ep-3ba9d4a1498f89fc.md` — the episode's deliverable, named
  by the GOLDEN's uid because the instruction bytes embed it (the uid
  substitution implication, stated).

## fidelity/ — the CP-09 comparison episode (our submit path, end to end)

Captured 2026-08-09 from CP-09: the same stack as `pi-corpus/` but
submitted through **our** four surfaces — `gsj-rollout submit` rendered
the `TaskRequest` from the one YAML, the manager's terminal callback
landed on our receiver (accepted, persisted verbatim), and the engine ran
under the CP-09 pinned configuration (CP-04 argv + CP-07 flags +
`--generation-config` holding the codec snapshot's
`generation_config.json` + `--enable-log-requests`; see the CP-09 report's
Step 1 — without that pin, pi's parameterless requests sample at vLLM
neutral defaults, silently). Session
`sk-polar-180dd057-3b69-49d2-b834-6b67cf1ccba4`, task `cp09-fidelity-a7`
(attempt 7 of 7 — 1–6 refused on the H-41 successful-built-in leg), the
golden triple `(case_0001, timestep-12, skill:summarize)`; 2 completions,
`chains_total == 1`, `glue_stitched == 1`, `finish: stop`.

- `callback_session_result.json` — the receiver-persisted callback body,
  byte-verbatim (status/error intact): the merged trace,
  `reconstruction_stats` (the full G7 conjunction), `completion_filter`,
  `gsj_validation` (`findings: []`).
- `trace.json` — the merged trace: `prompt_ids` 2965 (**byte-identical to
  the golden's `prompts`**), `response_ids` 3790 (363 sampled mask-1 +
  3427 interstitial mask-0), aligned `response_logprobs` (`0.0` only at
  mask-0 plus 15 MLX-bf16 mask-1 zeros — row 27), the 11-tool roster.
- `pi_transcript.jsonl` — pi's `--mode json` stream: 2 assistant turns
  (== 2 completions), tools `mcp_gsj_search_case/search_decisions/
  case_status` ok, `write` ok (read/grep ERR — directory reads).
- `mcp_authority_log.jsonl` — the session's `tool_call` events, each
  authorized from the token's verified claims
  (`case_id: case_0001, timestep: 12, episode_id: sk-polar-180dd057…`).

## pi-corpus/ — the CP-07 real episode (pi 0.83.0, our corpus, cutoff live)

Captured 2026-08-09 from CP-07: pi 0.83.0 (image
`ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3`) driven by
`gsj_rollout/pi_harness.py` via `agent.import_path`, through the gateway
proxy against vllm-metal (vLLM 0.26.0+cpu / MLX bf16, `Qwen/Qwen3-0.6B`,
`--max-model-len 32768`), with `pi-mcp-extension` loaded and the live
`mcp-service` clamp. Builder
`gsj_rollout.builder:ValidatingPrefixMergingBuilder` with
`end_of_turn_token_id: 151645` and `generation_prompt_glue_ids:
[151667, 271, 151668, 271]` (A-15 + ADR-0007). All files come from the
same session `sk-polar-c4eef751-0539-4066-aadc-f599a936f1c5` of task
`cp07-pi-corpus`, triple `(case_0001, timestep-12, skill:summarize)` —
2 completions, `chains_total == 1`, `glue_stitched == 1`.

- `callback_session_result.json` — the full `SessionResult` callback body
  with `status`/`error` intact (fetched from the rollout manager's
  in-memory results via `GET /rollout/task/{id}`; the on-disk `ses_*.json`
  strips `trajectory.status`/`error`, `pipeline.py:423-436`). Carries the
  merged trace, `reconstruction_stats`, `completion_filter`, and the
  builder's `gsj_validation` metadata (`findings: []`).
- `trace.json` — the merged multi-turn `Trace`: `prompt_ids` 2965,
  `response_ids` 7196 (441 sampled mask-1 + 6755 interstitial mask-0),
  aligned `response_logprobs` (no positive, no sentinel, `0.0` only at
  mask-0 plus 27 MLX-bf16 mask-1 zeros — row 27), the 11-tool roster,
  `finish_reason: "stop"`.
- `pi_transcript.jsonl` — pi's `--mode json` event stream, downloaded by
  `postprocess()` before teardown: 2 assistant `message_end`, `agent_end`
  present, tool executions incl. `write`/`read` (ok) and the four
  `mcp_gsj_*` (ok) — the completions-vs-turns evidence (2 records == 2
  turns).
- `mcp_authority_log.jsonl` — the `mcp-service` `tool_call` stderr lines
  for this session: every one carries `case_id: case_0001, timestep: 12,
  episode_id: sk-polar-c4eef751…` — **proof the cutoff came from the
  token's verified claims**, and that `episode_id` = the Polar session id
  joins the two logs (ADR-0006).
- `adversarial_probe.txt` — the security evidence, run inside the pi
  sandbox image: the valid token authorizes (HTTP 200); the same token
  with `timestep` mutated 12→18 (original signature kept) is rejected
  HTTP 401 `-32001` "Signature verification failed". The agent can read
  the token but cannot forge its scope.

Not captured here (same as `pi/`): the true post-engine-prepare wire body
is not persisted by Polar; per-completion records do not ride the callback
(session-level checks therefore live builder-side — CP-05). The MLX-bf16
`0.0`-at-mask-1 logprobs are a platform property of this Mac pair (row 27,
A-16); the H200 pair re-establishes production numerics.

## pi/ — the CP-06 spike artifacts (pi 0.83.0 through Polar)

Captured 2026-08-09 from the CP-06 spike: pi 0.83.0 (the predecessor's
byte-exact npm pins) driven by `spike/pi_harness_spike.py` via
`agent.import_path`, docker sandbox (`gsj-spike-pi:0.83.0`), through the
gateway proxy against the CP-06 stub backend (`spike/stub_backend.py`,
engine `vllm`, `end_of_turn_token_id: 260` explicit per A-15). All four
files come from the same session `sk-polar-3e3d7ce4-ea6f-4690-958a-3db2f51300bf`
of task `cp06-pi-hello` (2 completions, `chains_total == 1`).

- `pi_request.raw.json` — `original_request` of the second completion
  (richest shape: system string + user content-part list + assistant
  `tool_calls` echo + tool result): **exactly what pi sent**. Note the
  always-present `stream: true`, `stream_options`, `store: false`,
  `max_completion_tokens`, `chat_template_kwargs.enable_thinking: false`.
- `pi_request.transformed.json` — the same completion's persisted
  `transformed_request`. Sole transformer delta on pi traffic:
  `max_tokens` added (copied from `max_completion_tokens`, original key
  retained). `messages`/`tools` byte-equal to the raw form.
- `trace.json` — the merged multi-turn `Trace`: `prompt_ids` (2734),
  `response_ids` (149 = 119 sampled mask-1 + 30 interstitial mask-0),
  aligned `response_logprobs`, `tools` (the 7-tool roster),
  `finish_reason: "stop"`.
- `callback_session_result.json` — the full `SessionResult` callback body
  (same provenance as the CP-03 artifact: `GET /rollout/task/{id}`, the
  manager appends the callback-validated objects verbatim).

The **true wire request** (post-engine-prepare: `+logprobs`,
`+return_token_ids`, `+top_logprobs: 0`, `stream` forced `false`,
`stream_options` removed) is not persisted by Polar anywhere; the stub's
own dump is the only observation point — committed at
`spike/captures/pi_polar_stub.jsonl`. Measured against the persisted
`transformed_request`: the deltas are exactly those five keys —
`messages` and `tools` ride unchanged, so the persisted form IS the wire
form for everything the gates hash.

---

# The CP-03 smoke-run artifacts (mlx, mini_swe_agent)

Captured 2026-08-09 from the calculator example running end-to-end on the
patched vendored pin (`f0e8343a` + P1–P3): 1 gateway node, docker sandboxes,
`mini_swe_agent` harness, mlx-lm serving `Qwen2.5-Coder-3B-Instruct-4bit`
(no GPU). All three files come from the **same session**
`sk-polar-bfffd5b9-ffda-42e6-8670-6688e46d48e3` of task
`calculator-mini_swe_agent-20260809T102409Z`. CP-06 (harness) and CP-08
(receiver) build against these shapes. Full transcript: CP-03 report.

## callback_session_result.json — the callback payload

The `SessionResult` the gateway node POSTs to
`{rollout.public_url}/callbacks/session_result` (`node._push_result`,
`node.py:855-861`, body = `result.model_dump(mode="json")`). Provenance:
fetched from `GET /rollout/task/{task_id}` — the manager appends the
callback-validated `SessionResult` objects verbatim (`manager.py:214`), so
this content equals the POSTed body (pretty-printed here; whitespace/key
order is presentation). NOTE: the rollout server's *persisted*
`ses_*.json` files are NOT this payload — `pipeline._storage_payload`
strips `trajectory.status` and `trajectory.error` from the on-disk copy.

Shape: `session_id`, `task_id`, `status` ("COMPLETED"), `trajectory`
(below), `timing` (`register_to_init_queue_ms`, `init_ms`, `run_ms`,
`postrun_ms`), `node_id`, `error` (null), `metadata`.

Trajectory metadata: `builder` ("prefix_merging"), `session_id`,
`task_id`, `api_type` ("openai_chat"), `model_requested` ("gpt-5.4" — what
the harness sent), `model_used` (the served model), `record_count`,
`task_metadata`, `trace_count`, `reconstruction_stats`,
`completion_filter` (**patch P1's bookkeeping, live in the real path**),
`evaluation`. `reconstruction_stats` actually contains: `chains_total`,
`chains_reconstructed_full`, `chains_reconstructed_truncated`,
`raw_completions_total` (**added by P1**), `completions_total`,
`completions_merged`.

## trace.json — one real `Trace`

`trajectory.traces[0]` of the same session. Fields: `prompt_ids`,
`response_ids`, `loss_mask`, `prompt_messages`, `response_messages`,
`tools`, `finish_reason`, `response_logprobs`, `reward`, `metadata`.

**Honest degradations of this no-GPU capture** (all expected; none are
Polar defects):

- `prompt_ids`/`response_ids`/`loss_mask` are **empty** and
  `response_logprobs` is null: mlx-lm returns no `token_ids`/
  `prompt_token_ids`, and its logprob entries use `{"id": ..., "logprob"}`
  — a dialect the pin's VLLMEngine normalizer doesn't read. Token-level
  capture needs real vLLM/SGLang (CP-09, GPU).
- Because `prompt_ids` were empty, **every completion started its own
  chain**: 10 completions → `chains_total: 10`, each chain length 1, yet
  `chains_reconstructed_full: 10, truncated: 0` — a *clean-looking*
  snapshot while no merging actually happened. The receiver-side G7 rule
  must require `chains_total == 1` (as specced), not just
  `truncated == 0`; this run is live proof of why.
- `finish_reason: "length"` on every turn — mlx-lm's default 512-token
  completion cap, not a harness property.

## completion_record.json — one persisted gateway completion

The CompletionWriter file
`rollout_results/task_<id>/sessions/<sid>/completions/0001-<cid>.json`
(first turn of the same session), byte-verbatim. Fields: `completion_id`,
`timestamp`, `session_id`, `task_id`, `api_type`, `model_requested`,
`model_used`, `original_request` (**exactly what the harness sent**,
`model: "gpt-5.4"`), `transformed_request` (gateway-rewritten model),
`response` (mlx dialect incl. 512 `{"id", "logprob"}` entries),
`metadata` (`session_id`, `task_id` — **no `policy_version` key: patch P3
confirmed inert with no declared version**), `__written_at`.

Notes that bear on our gates:

- The persisted request carries the **wire tools array** (mini-swe-agent
  sends a `bash` function tool) in both `original_request` and
  `transformed_request` — the G3 wire-roster capture surface exists under
  Polar's proxy (gap rows 11/31).
- The persisted `transformed_request` is **pre-engine-shaping**: it lacks
  the `logprobs`/`top_logprobs`/`return_token_ids` fields the engine
  strategy adds at proxy time (the response proves they were sent). What
  is on disk is the transformer output, not the final engine wire request.
- The proxy logs only uvicorn access lines; these files are the only
  capture record.
