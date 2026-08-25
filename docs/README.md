# docs/ — the record

This directory is the evaluation record, not the product. The product
is [`../gsj_rollout/`](../gsj_rollout/) — 1,999 lines, eight files;
`pip install gsj-harness-rollout-server` for the trainer role. Nothing
here is required to *run* the server, but two shelves are runtime
inputs (see "Load-bearing paths" below), so nothing here moves. This
file is the shelf map: what each shelf is, who needs it, and what to
read first. Added at CP-46; the mechanism is `polar/README.md`'s
(CP-41), one level up.

## Read this first

1. [`VERDICT.md`](VERDICT.md) — the adoption verdict, its reversing
   conditions, and the consolidated wishlist. Standalone.
2. [`CHARTER.md`](CHARTER.md) — the normative document: scope laws,
   the assumption register (§4), the capability/gap register (§7),
   the standing rules (§8).
3. [`AUDIT-2026-08-24.md`](AUDIT-2026-08-24.md) — the 24-agent
   adversarial audit of the whole record against the working trees,
   executed suites, and published artifacts; zero of 91 findings
   refuted, the drift itemized with owners.
4. [`checks-spec.md`](checks-spec.md) — why each validator rule
   exists: the gates, admission, the logprob discipline.
5. [`corpus-contract.md`](corpus-contract.md) — the corpus tree
   contract (the input `ingest_corpus.py validate` checks).

## The shelves

| shelf | what it is | who opens it |
| --- | --- | --- |
| `reports/` | one report per checkpoint (CP-00 through the present, plus the prime/letter checkpoints CP-04′, CP-09′, CP-11b, CP-13a), in the fixed template — the primary evidence behind every number in the root README and the verdict | an auditor chasing a claim to its source |
| `prompts/` | every checkpoint's instructions, saved verbatim — read beside the same-numbered report to compare what was asked with what was delivered | an auditor verifying process |
| `decisions/` | the ADRs, append-only, one decision each, Context → Decision → Consequence (ADR-0001 through ADR-0026 at CP-46) | anyone asking "why is it built this way" |
| `golden/` | the golden-pair evidence — `mac/`, `h200/`, `COMPARISON.md` — the A-1 fidelity proof against the archived predecessor's reference traces | anyone re-verifying the `loss_mask`/`prompt_ids` claims |
| `polar/` | real Polar run artifacts (fidelity, the training loops, thinking, the adversarial probe); carries its own shelf README | anyone re-verifying an episode claim |

## Who needs what

- **Deciding whether to trust this server**: the root README, then
  `VERDICT.md`, then `AUDIT-2026-08-24.md` — and stop. The audit read
  all the reports adversarially so you don't have to.
- **Training against a server** (the pip consumer): `checks-spec.md`
  is the only file here you will open.
- **Operating an estate**: nothing here — `../staging/`, `../corpus/`,
  `../mcp-service/`, `../forgejo/`, `../pins/` are the operator's
  directories.
- **Changing the library**: `decisions/` and `CHARTER.md` bind you;
  `../CLAUDE.md` is the process contract.
- **Auditing a claim**: everything, at these paths — the record is
  citable at its current paths by design, and stays put (CP-46).

## Load-bearing paths

The record is not passive text; these paths are read by code, and
moving them breaks the build:

- `polar/h200-fidelity/callback_session_result.json` — a fixture for
  CI and the release gate (`.github/workflows/ci.yml`, `release.yml`)
  and for the root suite (`tests/`).
- `polar/<episode>/trace.json` — read at runtime by
  `pins/derive_pins.py`, which re-derives every approved value from
  the evidence named in its provenance blocks; the wheel-shipped
  `pins.gsj.json` names these paths.
- `golden/mac/tokens.npz` and the golden manifests — the A-1
  provenance chain.

Nothing in this directory is dead: `AUDIT-2026-08-24.md` §RESIDUE
catalogued every suspicion and disproved each one. This index shelves;
it does not prune.
