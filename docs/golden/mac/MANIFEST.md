# MANIFEST — the CP-04 Mac golden reference

One episode collected by the **predecessor's** stack (`gsj-envloader`
v0.8.0, frozen — run, never modified) on the operator's Mac, frozen as the
yardstick CP-09 measures Polar's trace against. Any CP-09 difference that
cannot be attributed to Polar must be attributable to something written
down here. The H200 pair (CP-04′/CP-09′) re-establishes the production
numbers later; **nothing mixes across `docs/golden/mac/` and
`docs/golden/h200/`.**

## The episode

| | |
|---|---|
| task triple | **`case_0001`, `timestep-12`, `skill:summarize`** (taskbank row 1) |
| episode uid / session | `ep-b4124a5aa0a8468d` |
| collected | 2026-08-09, macOS arm64 (Darwin 24.6.0), `collector_run_id: cp04-mac-golden` |
| outcome | `finish_state=completed`, `gate_failures=[]`, exit 0, wall 13.7 s (pi 13.4 s), not timed out |
| turns / tools | 4 turns; **9 tool executions, in order**: `mcp_gsj_search_case`, `mcp_gsj_search_decisions`, `mcp_gsj_case_status`, `read`, `grep`, `read`, `read`, `read`, `read` — the H-41 assertion (≥1 `mcp_gsj_*` ∧ ≥1 built-in) holds |
| token record | `prompts` 2965 + `responses` 3747 = `input_ids` 6712; `loss_mask == response_mask`, 292 × mask-1 (sampled) + 3455 × mask-0 (interstitial); `rollout_log_probs` aligned 3747, finite, ≤ 0, min −3.1457, `0.0` at every mask-0 position |
| logprob caveat | **20 of 292 mask-1 logprobs are exactly `0.0`** — MLX/bf16 renormalized sampling logprobs round near-delta distributions to `0.0`. Not in the CP-04 assertion list (present/finite/≤0 all hold); recorded because the checks-spec suspicious-zero rule would fire on it (row-27 finding, CP-04 report) |
| artifact | none produced — `env.artifact.path = null`; the model answered in-chat without writing `out/ep-b4124a5aa0a8468d.md` (see `artifact/NOTE`) |
| config hash | `9c7e7af473aa6b8fbaba611fba129b902051c8c9f0777eb78f4b7253f44d4295` (`config.mac.yaml` as loaded) |

## Sampling (applied per call, provenance-recorded)

`temperature 0.6, top_p 0.95, top_k 20, max_tokens 8192, seed 756095467
(= derive_seed(traj_id)), logprobs true` — the predecessor's frozen
reference block plus the `max_tokens` mirror of pi's
`max_completion_tokens`. **Not greedy**: greedy was measured uncollectible
for this model on this task family (turn-1 `<tool_call>` emission loop,
twice live — `docs/golden/COMPARISON.md` §sampling carries the evidence
and the comparison consequences).

## Model & serving

| | |
|---|---|
| policy model id | `Qwen/Qwen3-0.6B` (the A-01/ADR-0029 student pin) |
| codec snapshot | `Qwen/Qwen3-0.6B` @ `c1899de289a04d12100db370d81485cdf75e47ca` (HF cache; G4 hashes measured from it) |
| served weights | `mlx-community/Qwen3-0.6B-bf16` (bf16 MLX conversion) @ HF snapshot `42096995f6402fde107068cf530136fe64b604f8`, under `--served-model-name Qwen/Qwen3-0.6B` |
| engine | **vllm-metal `0.3.0.dev20260809035703`** (plugin) on **vLLM `0.26.0+cpu`** (macOS arm64 wheel), mlx 0.32.0 — same vLLM version as the H200 reference stack (`0.26.0+cu129`), different build/backend |
| serve argv | `vllm serve mlx-community/Qwen3-0.6B-bf16 --served-model-name Qwen/Qwen3-0.6B --host 127.0.0.1 --port 8100 --max-model-len 32768 --max-num-seqs 8 --gpu-memory-utilization 0.6` |
| capture dialect | `/v1/completions`, token-id prompt, `return_token_ids: true`, `logprobs: 1`, `add_special_tokens: false` → `choices[0].token_ids` + `choices[0].logprobs.token_logprobs` (verified in the CP-04 gate; `choices[0].prompt_token_ids` is also echoed) |

## Stack pins

| component | pin |
|---|---|
| gsj-envloader | v0.8.0 — wheel `dist/gsj_envloader-0.8.0-py3-none-any.whl`, sha256 `a6921de620a6f4a399b20b7efb65f01c7893761f17840d17eb7428bf899d441c`; checkout `4037bc250e937e386ecf54fa38f170ca80b167bb` (predecessor tree clean before and after) |
| pi | 0.83.0 (`@earendil-works/pi-coding-agent`), `--thinking off`, ADR-0008 argv (full argv verbatim in `record.json` → `env.provenance.invocation.argv`) |
| pi-mcp-extension | as baked in the harness image (loaded via `--extension`) |
| harness image | `ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3`, id `sha256:6d5f1dc6f18349b6ddf68962a0ef2fcb6fa723cade6f2cfbb8ba32479b4c48c0` — **linux/amd64, executed under Docker Desktop emulation** |
| uni-agent | `73b0f41efa88b311fd69129c6f835c012e925e73` (git direct reference) |
| tool parser | `hermes (sglang FunctionCallParser, sglang==0.5.10.post1)` — the H-41 guard passed at driver build |
| collector env | python 3.12.7 arm64; `staging/collector/install_collector_env.sh` + the `--no-deps` line, verbatim, no CUDA extra index |
| estate | Forgejo `codeberg.org/forgejo/forgejo:16.0.2`; `gsj-mcp-service:0.2.0` built arm64 from this repo's `mcp-service/`; corpus scaffolded from this repo's `corpus/staging` (scratch copy, one-line `base_url` delta); MCP census 18/22/15/20, corpus verify PASS 25/25 |
| hosted inputs | `taskbank.parquet` sha256 `9eb8e3c2d3760b9b74c4cda20394fd54bd12f95e78d397dbd40631f801eb19da`; `pins.staging.json` sha256 `bfa66b262765c57f5c662d9845860d003c7b0cf72e596b47a6005a537e12598b` — **both byte-identical to the frozen H200 contract**; the pin values were additionally regenerated on this Mac with `gsj-pin` and matched value-for-value (only `provenance.artifacts` path strings differ in the committed file — they predate the predecessor's devharness→staging relocation) |

## G-hashes (episode provenance == the pinned approved sets, every one a singleton hit)

| gate | pin | value on this episode |
|---|---|---|
| G1 `skill_card_hash` | summarize card | `d41ec6eaffbb940ec48191b50513ddfa44a3669c242a8df519f94127a20f449a` |
| G2 `system_prompt_hash` | the docker-mode `/workspace` singleton — **estate-invariant, NOT Mac-path-specific** (docker execution keeps host paths out of the prompt) | `f56e8a6e9ea9dd1c19be89c6754a4e8d3d1c0f89e04bb21f60237aa2e8837df4` |
| G3 `tool_roster_hash` | the 11-tool wire array | `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56` |
| G4 `tokenizer_hash` | git-blob OID of tokenizer.json | `949e1ec83f61520a25c75426edc4a43acc36f29a` |
| G4 `chat_template_hash` | sha256 of the template string | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| G6 `g6_expected_tail` | 41-byte verbatim tail (`staging/pins/g6_tail.captured.txt`) | matched (gates green) |
| G7 `settings_hash` | canonical-JSON of settings | `dae8948524be8253e04c4174632477e0333adc0323e791a6e54ace3b31004d20` |

## Frozen files

| file | sha256 |
|---|---|
| `record.json` | `8d39b48ce7fb8da764ed9a5161f62e6f595aa9e136a26b285520380055bb6db1` |
| `tokens.npz` | `4188e604281cd06e8b4e8450468aaae317338c4c37a8bddc68bee7cae018bf91` |
| `transcript.txt` (pi's `--mode json` event stream, verbatim) | `c9ba2303acf2d392aa1304e3eaa94405ad175345d617b0a909abe16dcc876340` |
| `artifact/NOTE` (no deliverable — see above) | `d579480439670473b36ac3afd101b9f08edcf7284c76a9789add2ab263cea4f4` |

## Every Mac adaptation (CP-04′ on the H200 will need none of these)

1. **Collector env**: no CUDA extra index (BRINGUP's cu129 hint is
   CUDA-host-only). Everything else verbatim; sglang installed from its
   plain wheel on python 3.12 arm64 (the "source-build, 3.11-only" doubt
   did not materialize).
2. **Serving**: vllm-metal (fresh install via upstream `install.sh` —
   no prior setup existed on this Mac) in place of vLLM cu129; weights are
   the mlx-community bf16 conversion served under the pinned model name;
   no SSH tunnels or self-forwards (one-host estate, direct
   `127.0.0.1:8100`).
3. **`--max-model-len 32768`, not the CP-prompt-suggested 16384**: the
   config pins `context_window: 32768` and the session sizes per-turn
   `max_tokens` from remaining capacity; at 16384 every episode call was
   rejected 400 (`max_tokens cannot be greater than max_model_len`) and pi
   turns errored empty — nine gates-green-looking but empty attempts
   before diagnosis.
4. **Networking** (CP-03 finding 2 class): published ports
   `127.0.0.1:3000` (Forgejo) and `127.0.0.1:8790` (MCP) for host
   processes; the MCP container joined `gsj-staging-net` (so its baked
   `source.base_url http://172.28.9.10:3000` needed no change) instead of
   the H200's `network_mode: host`; episode containers reached the
   host-side gateway and MCP via the predecessor's own
   `host.docker.internal` rewrite + `--add-host host.docker.internal:host-gateway`,
   which works under Docker Desktop unchanged.
5. **Scratch copies, outside both repos** (law 3): forgejo
   compose/up.sh/create_owner.sh (HOST → `127.0.0.1:3000`, data dir
   re-rooted to scratch), mcp compose (delta 4), and `corpus-staging`
   (one line: `forgejo.base_url → http://127.0.0.1:3000`).
6. **New estate config `config.mac.yaml`** (the predecessor's delta law —
   values, never code): scratch store/work paths; `clone_url_for` owner
   `gsj-staging` (the pipeline-scaffolded estate, canonical since the
   predecessor's CP-33; the H200 config's `gsj-admin` clones are its
   byte-identical CP-29 freeze); `wall_timeout_s` 480 → 900
   (amd64-emulation headroom); `concurrency` 2 → 1; `rollout.seed` 5
   (lands the deficit draw on `timestep-12`); `sampling_student` gains
   `max_tokens: 8192` (pi's own per-turn cap; converts a greedy/rambling
   loop into a fast honest failure); `collector_run_id: cp04-mac-golden`.
   Frozen-contract values carried unchanged: taskbank/pins sha256s, image
   tag, `pi_version`, `uniagent_sha`, model/revision pins,
   `tools_allowlist`, eval sampling.
7. **The pi image runs emulated** (linux/amd64 on arm64 — Docker Desktop
   warning recorded in episode stderr; worked throughout).
8. **The MCP HMAC secret** lived in a 0600 scratch file for cross-process
   reuse during the CP (ADR-0037(b) wants env-only; session-scoped
   deviation, never in a repo file, log, or provenance).

## Collection history (what it took, honestly)

Nine empty-turn attempts against the 16384 serving (adaptation 3), one
uncapped-greedy wall-timeout (`infra_error`, 558 s, >25k-token turn-1
loop), one capped-greedy `truncated` (exactly 8192 tokens, zero tool
executions — greedy abandoned, COMPARISON.md §sampling), one
reference-sampling episode refused at freeze (no built-in tool executed,
no artifact — the H-41 assertion did its job), then the frozen episode on
the next attempt. Also observed: a `truncated` episode counts toward
`collect_episodes(episodes=1)`'s "new trainable" target — the trainer-side
`ready: finish_state == completed` predicate is what excludes it, not the
collector (recorded in the CP-04 report, gap row 26).
