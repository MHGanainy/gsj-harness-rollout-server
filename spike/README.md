# spike/ — the first end-to-end probe

Frozen evidence from the first end-to-end probe of pi (`@earendil-works/pi-coding-agent` 0.83.0) inside Polar's runtime — sandbox → gateway proxy → wire capture → trajectory builder — against a stub inference backend, in three runs: a scripted two-turn sanity gate, pi locally against the stub, pi through Polar end to end.
Nothing here is maintained or part of the library; the permanent harness is `gsj_rollout/pi_harness.py`, and the dataflow this spike first walked is drawn in [how-it-works](../docs/guide/how-it-works.md).

| Path | What it is |
| --- | --- |
| `stub_backend.py` | Minimal OpenAI-compatible `/v1/chat/completions` server speaking the dialect Polar's capture actually works against |
| `pi_harness_spike.py` | Minimum harness running pi in Polar's runtime via `agent.import_path` — superseded by `gsj_rollout/pi_harness.py` |
| `two_turn_probe.py` | Scripted two-turn OpenAI client (stdlib only); runs inside the sandbox as the sanity-gate agent |
| `preflight_builder_check.py` | Feeds a simulated two-turn exchange straight into the vendored `PrefixMergingBuilder` (no servers), asserts one chain |
| `p1_verdict.py` | Runs the carried non-agent-completion-filter patch's shape test on the captured pi wire bodies: does its drop arm ever fire? |
| `wire_diff.py` | Three-way diff of each completion's request forms — original, post-transformer, and the wire the engine received |
| `task_sanity.yaml` / `task_pi.yaml` | The two Polar task specs: the scripted probe and pi end to end |
| `topology.spike.yaml` | One-node topology with the stub backend in the inference engine's slot |
| `captures/` | The evidence: stub-side wire captures (JSONL), pi transcripts, task status |
| `pi-image/` | Dockerfile + npm lockfile for the sandbox image (node 22 + pi 0.83.0, restored with `npm ci`) |
| `pi-local/` | Frozen local pi install (lockfile + agent config) for the local-run captures; never imported by the library |

Scratch outputs are gitignored (`rollout_results/`, `pi-local/node_modules/`, `pi-local/workspace/`); the tree keeps curated evidence only.
The captures are real pi bodies in the exact dialect the trace validators key on — response ids as `choices[0].token_ids` mirrored one-for-one in `logprobs.content` entries carrying `token_id` + `logprob`, top-level `prompt_token_ids`, logprobs finite and negative — rule reasoning in [docs/checks-spec.md](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

> [!NOTE]
> Frozen: no CI job touches `spike/`, and neither built artifact includes it — the wheel packages `gsj_rollout/` only; the sdist's explicit root set excludes it.

Provenance: the probe this directory freezes — the tag its scripts and task ids carry — is CP-06.
