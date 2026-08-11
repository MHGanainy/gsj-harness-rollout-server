# MANIFEST — the CP-04′ H200 golden reference

One episode collected by the **predecessor's** stack (`gsj-envloader`
v0.8.0, frozen — run, never modified) on the H200 estate, frozen as the
yardstick CP-09′ measures Polar's trace against — the same two-capture-layer
comparison design as the Mac pair, on the production platform (the Step-5
provenance decision, recorded in `docs/reports/CP-04prime.md`). Any CP-09′
difference that cannot be attributed to Polar must be attributable to
something written down here. Per A-16 the H200 pair's verdict **governs the
production numerics**; **nothing mixes across `docs/golden/mac/` and
`docs/golden/h200/`.**

## The episode

| | |
|---|---|
| task triple | **`case_0001`, `timestep-12`, `skill:summarize`** (seed-5 deficit draw, verified by simulation before the run and by the episode's own branch/claims after) |
| episode uid / session | `ep-3ba9d4a1498f89fc`; one uninterrupted pi session `019ff02c-54dd-7ff6-bbab-ece010e197af` (exactly one `type:session` event in the transcript) |
| collected | 2026-08-11, H200 host `gpu-compute-legal-tech` (Linux, docker episodes, native amd64 — no emulation), `collector_run_id: cp04prime-h200-golden` |
| outcome | `finish_state=completed`, `gate_failures=[]`, exit 0, wall 8.4 s (pi 8.2 s), not timed out |
| turns / tools | 4 turns; **6 tool executions, in order**: `grep`(err), `read`(err), **`write`(ok)**, `mcp_gsj_case_status`(ok), `mcp_gsj_search_decisions`(ok), `mcp_gsj_search_case`(ok) — the H-41 assertion (≥1 `mcp_gsj_*` ∧ ≥1 *successful* built-in) holds |
| token record | `prompts` 2965 + `responses` 3682 = `input_ids` 6647; `loss_mask == response_mask`, 258 × mask-1 (sampled) + 3424 × mask-0 (interstitial); `rollout_log_probs` aligned 3682, finite, ≤ 0, min −2.2529, `0.0` at every mask-0 position |
| logprob caveat | **16 of 258 mask-1 logprobs are exactly `0.0` (6.2%)** — the row-27 exact-`0.0` artifact **recurs on CUDA vLLM bf16**; it is NOT MLX-specific. Same-estate corroboration (our stack, this CP): 34/237 (14.3%) and 2119/8506 (24.9%, a repetitive-loop episode that nearly reached the 0.25 allowance). Row 27's "a CUDA estate restores strictness with `0.0`" is measured false on this platform |
| instruction | the resolved skill row, 626 bytes — **it embeds the episode uid** (`Write the summary to out/ep-3ba9d4a1498f89fc.md`), so turn-1 prompt LENGTH varies ±1–2 tokens per episode uid (measured across this CP's 8 attempts: 2964–2966). CP-09′ must collect its counterpart with THIS golden's instruction bytes verbatim (the CP-09 procedure) or `prompt_ids` exact-equality fails on the uid alone |
| artifact | **produced** (unlike the Mac golden): `out/ep-3ba9d4a1498f89fc.md`, sha256 `eaabe127497c2c9cc62fcdc0a4cda540018e646974f8dfcf594bfcee74fb0c2b`, harvested pre-reset, frozen at `artifact/` |
| config hash | `2c4ae77a21c20adad980d07cda9848e0558aed66864c5c995ab38933c62bf5ae` (`config.cp04prime.yaml` as loaded) |

## Sampling (applied per call, provenance-recorded AND engine-verified)

`temperature 0.6, top_p 0.95, top_k 20, max_tokens 8192, seed 1500772333
(= derive_seed(traj_id)), logprobs true` — the predecessor's frozen
reference block plus the `max_tokens` mirror. **Engine-side confirmation,
from the request log (`--enable-log-requests`, both turns, seed-matched)**:

```
SamplingParams(n=1, …, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
  seed=1500772333, stop=[], …, max_tokens=8192, …, logprobs=1, …)
```

Not greedy — the Mac pair measured greedy uncollectible for this model on
this task family; the contract (`docs/golden/COMPARISON.md` §sampling)
carries the evidence and stands unchanged for the H200 pair.

## Model & serving

| | |
|---|---|
| policy model id | `Qwen/Qwen3-0.6B` — served weights == codec snapshot == `Qwen/Qwen3-0.6B` @ `c1899de289a04d12100db370d81485cdf75e47ca` (**one snapshot for everything** — the Mac's served/codec split does not exist here) |
| dtype | `torch.bfloat16` (native CUDA, engine-reported) |
| engine | **vLLM `0.26.0+cu129`** on torch `2.11.0+cu129`, python 3.12.13 (uv), NVIDIA H200 (GPU 3, `CUDA_VISIBLE_DEVICES=3`), `VLLM_ATTENTION_BACKEND=FLASH_ATTN`, `--enforce-eager` |
| serve argv | `vllm serve Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca --host 127.0.0.1 --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.30 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' --chat-template /home/sysadmin/gsj-vllm/qwen3_training.jinja --generation-config /home/sysadmin/gsj-vllm/genconfig --enable-log-requests --enforce-eager` (recipe: this repo's `staging/serving/serve.sh`) |
| **served chat template** | **`qwen3_training.jinja` (TRL, byte-verbatim), sha256 `1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`** — the CP-04′ Direction-A symmetric template, pinned in the serve argv and committed at `staging/serving/qwen3_training.jinja`. Honest scope note: this golden's own prompts were rendered by the predecessor's **codec** (token-in `/v1/completions` — the server-side chat template is never invoked for it); the served template is the estate's serving identity and the surface our stack's episodes render through |
| generation-config pin | `--generation-config` → byte-copy of the snapshot's own `generation_config.json`, sha256 `2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2` (== the codec pin CP-09 used); startup log: `Default vLLM sampling parameters have been overridden by /home/sysadmin/gsj-vllm/genconfig: {'temperature': 0.6, 'top_k': 20, 'top_p': 0.95}` — on this CUDA snapshot the file EXISTS upstream (verified, not assumed); the explicit flag makes the pin auditable from the argv |
| capture dialect | `/v1/completions`, token-id prompt, `return_token_ids: true`, `logprobs: 1`, `add_special_tokens: false` → `choices[0].token_ids` + `choices[0].logprobs.token_logprobs` (the predecessor's uni-agent gateway codec) |

## Stack pins

| component | pin |
|---|---|
| gsj-envloader | v0.8.0 — wheel `gsj_envloader-0.8.0-py3-none-any.whl`, sha256 `a6921de620a6f4a399b20b7efb65f01c7893761f17840d17eb7428bf899d441c` (byte-identical to the Mac collection's wheel); fresh collector venv `.venv-cp04prime` (python 3.12.13 via uv) — the H200's pre-existing `.venv` held a stale 0.5.0 without uni_agent/verl/sglang and was left untouched |
| pi | 0.83.0 (`@earendil-works/pi-coding-agent`), `--thinking off`, ADR-0008 argv (verbatim in `record.json` → `env.provenance.invocation.argv`) |
| pi-mcp-extension | as baked in the harness image (loaded via `--extension`) |
| harness image | `ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3`, id `sha256:f7a6d63a5f0a86bda5e1fab6f3cb6fa6177b20f4a3f9c6b97b33b4cc1dfe37f0` — **the H200 daemon's CP-30 frozen load** (native linux/amd64; note the workstation's current build of the same tag has a different image id — the daemon's load is the estate's frozen artifact and is what both stacks ran this CP) |
| uni-agent | `73b0f41efa88b311fd69129c6f835c012e925e73` (git direct reference) |
| tool parser | `hermes (sglang FunctionCallParser, sglang==0.5.10.post1)` — the H-41 guard passed at driver build (verified in the fresh venv before any collection) |
| collector env | `staging/collector/install_collector_env.sh` + the `--no-deps` line, verbatim, `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu129` (torch 2.13.0+cu129 in the collector venv; the SERVING venv is torch 2.11.0+cu129) |
| estate | Forgejo `codeberg.org/forgejo/forgejo:16.0.2` at `172.28.9.10:3000` (BRINGUP §1 verbatim; refs 4/4/1, taskbank sha reproduced); **`gsj-mcp-service:0.3.0`** (the CP-15 ChromaDB backend) built linux/amd64 from this repo's `mcp-service/`, shipped `docker save \| ssh docker load`; `/health` ready with census 18/22/15/20 pages, 51/62/43/57 chunks, backend `{chromadb, 1.5.9, collections: 5}`; corpus scaffolded from this repo's **split-shaped** `corpus/staging` (converged on the frozen SHAs); corpus verify **PASS 29/29** |
| hosted inputs | `taskbank.parquet` sha256 `9eb8e3c2d3760b9b74c4cda20394fd54bd12f95e78d397dbd40631f801eb19da`; `pins.staging.json` sha256 `bfa66b262765c57f5c662d9845860d003c7b0cf72e596b47a6005a537e12598b` — the frozen H200 contract, consumed in place |

## G-hashes (episode provenance == the pinned approved sets, every one a singleton hit)

| gate | pin | value on this episode |
|---|---|---|
| G1 `skill_card_hash` | summarize card | `d41ec6eaffbb940ec48191b50513ddfa44a3669c242a8df519f94127a20f449a` |
| G2 `system_prompt_hash` | the docker-mode `/workspace` singleton — holds on the H200 exactly as CP-04 finding 5 predicted | `f56e8a6e9ea9dd1c19be89c6754a4e8d3d1c0f89e04bb21f60237aa2e8837df4` |
| G3 `tool_roster_hash` | the 11-tool wire array (mcp-service 0.3.0 — the CP-15 unchanged-roster assertion, now also proven on a live H200 wire) | `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56` |
| G4 `tokenizer_hash` | git-blob OID of tokenizer.json | `949e1ec83f61520a25c75426edc4a43acc36f29a` |
| G4 codec `chat_template_hash` | the CODEC's template (what rendered THIS golden's prompts — recorded-not-approved in `pins/pins.gsj.json`; the approved serving-side value is the TRL file's `1d944ff8…` above) | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| G6 `g6_expected_tail` | 41-byte verbatim tail; ids under the served tokenizer pinned this CP as `g6_expected_tail_ids` `[151644, 77091, 198, 151667, 271, 151668, 271]` | matched (gates green) |
| G7 `settings_hash` | canonical-JSON of settings | `dae8948524be8253e04c4174632477e0333adc0323e791a6e54ace3b31004d20` |

## Frozen files

| file | sha256 |
|---|---|
| `record.json` | `87aa31f3c3c6e8fe7710e67260fd260ccf2bbf3f4d7cad80573e109541ef5775` |
| `tokens.npz` | `895ed87ca9d6c0099cdd43b7e69cc0507cf2d4e9924c2c51b4341658dae48f72` |
| `transcript.txt` (pi's `--mode json` event stream, verbatim) | `12c14a371ac01e07be6049d99709e1bc1dd2d9e8722ba1309edf35230a05ce04` |
| `artifact/ep-3ba9d4a1498f89fc.md` (the produced deliverable) | `eaabe127497c2c9cc62fcdc0a4cda540018e646974f8dfcf594bfcee74fb0c2b` |

## H200-specific facts (the estate as it actually was)

1. **No Mac adaptation was needed — as A-16 predicted.** Native amd64 pi
   image (no emulation), no published ports, no vllm-metal, no
   `wall_timeout_s` raise (480 stood; episodes ran 7.5–24 s).
2. **GPU 3, not BRINGUP's default 7**: GPUs 0/1/2/6/7 were occupied by
   other tenants; 3 and 5 were free. `GSJ_VLLM_GPU=3`, frac 0.30.
3. **Serving venv + snapshot reused** (BRINGUP §0's survive-teardown
   design); the serve recipe is this repo's `staging/serving/serve.sh`
   (deltas from the predecessor's enumerated in its header — template,
   explicit genconfig, GPU default, no LoRA flags).
4. **Config deltas from `config.staging.yaml`** (the delta law — values,
   never code): scratch store/work roots, `collector_run_id`,
   `sampling_student.max_tokens: 8192` (the CP-04 mirror),
   `rollout.seed: 5` (lands the deficit draw on `timestep-12`),
   `concurrency` 2 → 1 (a concurrency-2 run draws a SECOND row —
   measured: its second episode ran `timestep-18`), fresh store per
   attempt (completed episodes shift the deficit off the target row).
5. **The MCP HMAC secret** lived in a 0600 scratch file for cross-process
   reuse during the CP (the CP-04 session-scoped deviation, same terms).
6. **The collection ran against the estate while the symmetric template
   was being served** — the two stacks' episodes interleaved on the same
   engine; the golden's codec dialect bypasses the server-side template by
   construction (see Model & serving).

## Collection history (what it took, honestly)

Eight episodes total; **seven on-triple attempts; attempt 7 qualified**
(the same count CP-09's Mac collection took, on the same leg). Run A
(concurrency 2): one `timestep-12` episode refused at freeze — grep + 4
reads all errored, zero successful built-ins, the exact H-41 class — plus
one off-triple `timestep-18` episode (the concurrency draw, adaptation 4).
Loop runs 1–5 (concurrency 1, fresh store each): all `completed`,
gates green, all refused on the successful-built-in leg (grep/read error
loops; run 5 rambled to 25,189 response tokens under the 8192 per-turn
cap across turns — `completed`, not truncated). Run 6 qualified: `write`
succeeded, artifact produced, frozen above. Every refused episode was
`completed`/gates-green — the H-41 assertion, not the gates, did the
refusing, which is exactly why it exists.
