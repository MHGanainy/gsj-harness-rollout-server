# docs/polar — real Polar artifacts

**`pi/` supersedes the top-level mlx-derived files for every question
about *our* traffic** (CP-06). The top-level CP-03 artifacts stay as the
record of the first smoke run and of the S1 degeneration proof.

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
