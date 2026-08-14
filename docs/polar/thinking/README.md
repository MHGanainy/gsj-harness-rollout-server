# docs/polar/thinking — CP-28 (M9a): does thinking earn its cost?

The Phase-C go/no-go measurement: two 15-episode collections on the golden
triple (`case_0001`, timestep 12, the golden `skill:summarize` instruction,
626 bytes), same estate, same engine **process** (never restarted between
legs), all four legs pinned and verified — the only config delta is
`harness.thinking: "off"` → `"medium"` (plus per-leg artifacts/traces
dirs). Thinking-on episodes were collected **through the receiver**: all 15
were quarantined with G6 findings recorded — the gate was not weakened, not
bypassed. Verdict and full analysis: `docs/reports/CP-28.md`.

## The wire mechanism (measured, not assumed)

pi 0.83.0 with `thinkingFormat: "qwen-chat-template"` sends
`chat_template_kwargs: {enable_thinking: !!reasoningEffort,
preserve_thinking: true}` on **every** request; Polar's openai-chat proxy
path forwards it untouched (CP-06's `pi_request.transformed.json` shows it
verbatim); vLLM lets the per-request value override the serve argv's
`--default-chat-template-kwargs '{"enable_thinking": false}'`
(`probe_override.txt`). So the flag travels config → TaskRequest
`settings.thinking` → pi `--thinking <level>` → per-request kwarg → the
served symmetric template's generation-prompt conditional. **Trap:** pi
clamps unknown `--thinking` values to `"off"` silently — `thinking: "on"`
would have measured nothing; the scratch config uses `"medium"` (any
non-off pi level is wire-equivalent under `qwen-chat-template`).

## Files

| file | what |
|---|---|
| `rollout.cp28.{off,on}.yaml` | the scratch configs (CP-04 pattern — lived at `~/cp28/` on the H200, outside both repos; committed here as evidence) |
| `collect.sh`, `analyze.py` | the collection driver and the measurement script (ran on-box) |
| `timing-{off,on}.csv` | per-attempt submit wall clock |
| `analysis-{off,on}.json` | per-episode measurements + distributions; `analysis-on.json` carries every decoded `<think>` text |
| `collection_comparison.txt` | the two legs side by side + per-episode tables + G6 accounting |
| `reasoning_excerpts.txt` | decoded think spans, shortest/median/longest episodes |
| `episode-off.accepted.json` | exemplar control episode (receiver-accepted; the one OFF episode that wrote a deliverable) |
| `episode-on.quarantined.json` | exemplar measurement episode (quarantine wrapper: `{"findings": [G6:…], "session_result": …}` — the findings-recorded collection path) |
| `probe_override.txt` | pre-collection engine probes: kwarg override + reasoning round-trip field mapping |
| `g4_engine_evidence.txt` | served template sha + live engine argv (same process, both legs) |

## Headline numbers (n=15 per leg)

|  | off | on |
|---|---|---|
| receiver | 15 accepted | 15 quarantined, findings G6-only |
| chains_total==1 | 15/15 | **15/15** (A-22 exercised: symmetric template holds) |
| think tokens (med / p25–p75 / max) | 0 | 1100 / 713–1430 / 2523 |
| think fraction of sampled tokens | 0 | median 0.67 (0.44–0.95) |
| response ids (med / max) | 3705 / 10319 | 7136 / 23533 |
| total ids %32k (med / max) | 20% / 41% | 31% / 81% |
| finish `length` | 0 | 0 (one `tool_calls`-final at 81%) |
| episode wall (med) | 7.7 s | 21.1 s (~2.7×) |
| MCP tool successes (mean) | 2.5 | 4.1 |
| deliverable written | 1/15 | **8/15** |
| deliverable with `page:N` citations | 1/15 | 3/15 |
| turn openings ending `[151644, 77091, 198]` | 0/30 | **41/41** (the CP-23 re-pin candidate; empty-think tail appeared 0 times) |
