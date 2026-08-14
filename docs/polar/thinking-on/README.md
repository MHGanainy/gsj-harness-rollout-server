# thinking-on — the CP-30 live pair (C-2 landed, ADR-0024)

One thinking-on and one thinking-off episode, both through the REAL
receiver on the H200 estate (CP-09′ fast path), both **accepted clean —
no G6 findings, no quarantine, attempt 1 of 1 each**. The thing CP-28
could not have: at CP-28 every thinking-on episode was correctly
quarantined because the off-tail was the only pin; CP-30's per-mode pins
(`pins/thinking-on/pins.gsj.json`, selected via `GSJ_PINS_PATH` on both
law-6 legs) let the same unweakened gate accept the mode the estate
declares.

| | thinking-off | thinking-on |
|---|---|---|
| session | `sk-polar-1c2bd6f2…` | `sk-polar-61eaa850…` |
| receiver verdict | accepted, findings `[]` | accepted, findings `[]` |
| quarantine dir | empty | empty |
| attempts | 1 | 1 |
| wall (submit) | 10.4 s | 26.5 s |
| `chains_total` / full / truncated | 1 / 1 / 0 | 1 / 1 / 0 |
| completions merged/total/raw | 2/2/2 | 3/3/3 |
| `glue_stitched` | 0 | 0 |
| turns (mask-1 spans) | 2 | 3 |
| think ids (151667/151668) @ mask==1 | 0 | 6 (a `<think>` pair opens every turn) |
| think ids @ mask==0 | 2 (the empty-think interstitial — the off signature) | 0 (history re-renders keep the reasoning) |
| `prompt_ids` tail | the 7-id empty-think tail | the 3-id `<|im_start|>assistant\n` tail |
| finish_reason | stop | stop |
| logprobs | positive=0, zero@mask1 13/334 (3.9%) | positive=0, zero@mask1 62/1630 (3.8%) |

Files: `episode-{off,on}.accepted.json` — the receiver's stored
envelopes, verbatim; `rollout.cp30.{off,on}.yaml` — the scratch configs
(evidence, never config; identical to CP-28's but for the cp30 paths;
the on config's `thinking: "medium"` now passes the ADR-0024 validator);
`derive_pins.estate.txt` — the pins walk on the estate with the served
tokenizer importable: both tails reproduced (`[151644, 77091, 198,
151667, 271, 151668, 271]` and `[151644, 77091, 198]`), non-G6 set
equality and the byte-prefix relation ok, exit 0; `verify.py` /
`verify.txt` — the table above, recomputed from the envelopes.

Process facts: the ON leg's receiver AND submit both ran with
`GSJ_PINS_PATH=<checkout>/pins/thinking-on/pins.gsj.json` (the ADR-0024
estate discipline — both law-6 legs); the OFF leg used default checkout
resolution. Same engine process served both legs (the flag rides
requests, not the argv — CP-28). Polar rollout + gateway stayed up
across the receiver swap; the receiver restarts because pins load once
per process (the CP-11b operational fact).
