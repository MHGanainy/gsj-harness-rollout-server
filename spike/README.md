# spike/ — the first end-to-end probe

Frozen evidence from the first end-to-end probe of running **pi** (the coding
agent, `@earendil-works/pi-coding-agent` 0.83.0) inside **Polar**'s runtime:
sandbox → gateway proxy → wire capture → trajectory builder, against a stub
inference backend. Three runs are captured — a scripted two-turn sanity gate,
pi driven locally against the stub, and pi through Polar end to end. Nothing
here is maintained or part of the library; the permanent harness is
`gsj_rollout/pi_harness.py`.

![Episode dataflow](../docs/guide/img/episode-dataflow.png)

<sub>One episode end to end — the agent in its sandbox, the gateway proxy,
the wire capture, the trajectory builder. This spike walked that path
first.</sub>

## Contents

| Path | What it is |
| --- | --- |
| `stub_backend.py` | Minimal OpenAI-compatible `/v1/chat/completions` server speaking a dialect Polar's capture actually works against |
| `pi_harness_spike.py` | The minimum harness that runs pi in Polar's runtime, loaded via `agent.import_path` — superseded by `gsj_rollout/pi_harness.py` |
| `two_turn_probe.py` | Scripted two-turn OpenAI client (stdlib only) that runs inside the sandbox as the sanity-gate agent |
| `preflight_builder_check.py` | Feeds a simulated two-turn exchange straight into the vendored `PrefixMergingBuilder` (no servers) and asserts one chain |
| `p1_verdict.py` | Runs the carried non-agent-completion-filter patch's shape test against the captured pi wire bodies: does its drop arm ever fire on pi traffic? |
| `wire_diff.py` | Three-way diff of each completion's request forms — original, post-transformer, and the wire the engine received |
| `task_sanity.yaml` / `task_pi.yaml` | The two Polar task specs: the scripted probe, and pi end to end |
| `topology.spike.yaml` | One-node topology with the stub backend in the inference engine's slot |
| `captures/` | The evidence: stub-side wire captures (JSONL), pi transcripts, task status |
| `pi-image/` | Dockerfile + npm lockfile for the sandbox image (node 22 + pi 0.83.0, restored with `npm ci`) |
| `pi-local/` | Frozen local pi install (lockfile + agent config) for the local-run captures; never imported by the library |

Scratch outputs are gitignored (`rollout_results/`, `pi-local/node_modules/`,
`pi-local/workspace/`): the tree keeps curated evidence only.

## How the captures relate to the checks

The stub emits the exact wire dialect the trace validators key on: response
ids as `choices[0].token_ids`, mirrored one-for-one in `logprobs.content`
entries carrying `token_id` + `logprob`; `prompt_token_ids` on the response
top level; logprobs finite and negative. The files in `captures/` are real
bodies in that dialect from pi traffic. The rule reasoning the validators
enforce over it is documented in
[docs/checks-spec.md](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

## Status

Frozen. No CI job touches `spike/`, and neither built artifact includes it —
the wheel packages `gsj_rollout/` only, and the sdist's explicit root set
excludes it. It stays readable as provenance for the harness, the stub
dialect, and the checks.

## Provenance

- The probe this directory freezes, and the tag its scripts and task ids
  carry: **CP-06** (the previous heading read "spike/ — frozen CP-06
  evidence").
- The catalogue entry for this directory: "catalogued in
  `docs/AUDIT-2026-08-24.md` §RESIDUE" (the audit is part of the untracked
  development record).
