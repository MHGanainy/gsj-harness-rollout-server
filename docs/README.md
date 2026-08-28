# docs/ — the record

This directory is the evaluation record, not the product. The product
is [`../gsj_rollout/`](../gsj_rollout/) — 1,999 lines, eight files;
`pip install gsj-harness-rollout-server` for the trainer role. Nothing
here is required to *run* the server, but one shelf (`polar/`) is a
runtime input (see "Load-bearing paths" below), so it stays put — two
shelves, until CP-49 moved the Mac fixtures to
`../tests/fixtures/golden-mac/`. This
file is the shelf map: what each shelf is, who needs it, and what to
read first. Added at CP-46; the mechanism is `polar/README.md`'s
(CP-41), one level up.

> **Since CP-48 most of this directory is maintained privately.** The
> operator removed the development record from tracking: `reports/`,
> `prompts/` (all of them since CP-49a; CP-48's own prompt was the
> last one tracked),
> `decisions/`, `AUDIT-2026-08-24.md`, the CP-47 classification, the
> shelf README under `polar/`, and every `golden/` and `polar/` file
> except the ten that CI, the release gate, the test suites, and the
> pins walk read (the "Load-bearing paths" below — those stay, by
> proof; seven since CP-49, when the three Mac-golden files moved,
> still tracked, to `../tests/fixtures/golden-mac/` and `golden/`
> became entirely untracked). The record still exists, unchanged, in the operator's working
> tree; the shelf map below is kept as written and describes **that**
> copy, not what a clone of this repository contains. Reading this from
> a clone: the `reports/`, `prompts/` and `decisions/` shelves are
> gone, and every `CP-NN` and ADR citation in the surviving documents —
> this repo's, the charter's, the spec's, the consumer repos', and the
> two report paths inside the wheel-shipped `pins.gsj.json` provenance
> — is a footnote you cannot follow: it resolves only in the operator's
> private record. That is the cost of this decision, recorded here
> rather than papered over: the evaluation's product was a checkable
> record, and from a clone the checkable part now ends at the code, the
> suites, and the evidence bodies they execute against.

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
| `guide/` | the **user documentation**: plain Markdown (`guide/README.md` is the index) — installation, quickstarts, concepts, configuration, CLI and API reference — with diagrams as PNGs under `guide/img/`; the diagram sources are PowerPoint decks kept outside this repository. Not part of the evaluation record; written for consumers | anyone adopting the library |

## Who needs what

- **Deciding whether to trust this server**: the root README, then
  `VERDICT.md`, then `AUDIT-2026-08-24.md` — and stop. The audit read
  all the reports adversarially so you don't have to.
- **Training against a server** (the pip consumer): `guide/README.md` and
  the pages it indexes, then `checks-spec.md` when you need the reasoning
  behind a finding.
- **Operating an estate**: nothing here — `../estate/` (its README is
  the recipe; `estate.sh` the front door) and `../pins/` are the operator's
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
- the Mac golden fixtures — `tokens.npz` and its manifests, the A-1
  provenance chain — lived here until CP-49; they are tracked at
  `../tests/fixtures/golden-mac/` now.

Nothing in this directory is dead: `AUDIT-2026-08-24.md` §RESIDUE
catalogued every suspicion and disproved each one. This index shelves;
it does not prune.
