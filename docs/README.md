# docs/ — the shelf map

`docs/` holds two different things: the **user guide** (`guide/`, written for people adopting the library) and the **evaluation record** (everything else, written while the library was built). The product itself is [`gsj_rollout/`](https://github.com/MHGanainy/gsj-harness-rollout-server/tree/main/gsj_rollout) — 1,999 lines, eight files; `pip install gsj-harness-rollout-server` for the trainer role. Nothing here is required to *run* the server, but one shelf (`polar/`) holds files that code reads, so it stays where it is (see [Load-bearing paths](#load-bearing-paths)).

This page is the shelf map: what each shelf is, who opens it, and what to read first.

> [!IMPORTANT]
> **Most of this directory is maintained privately since CP-48.** The operator removed the development record from tracking: `reports/`, `prompts/` (all of them since CP-49a; `CP-48.md` was the last prompt tracked), `decisions/`, `AUDIT-2026-08-24.md`, `CLASSIFICATION.md` (the CP-47 classification), the shelf README under `polar/`, and every `golden/` and `polar/` file except the seven bodies that CI, the release gate, the test suites, and the pins walk read — ten until CP-49, when the three Mac-golden files moved, still tracked, to `../tests/fixtures/golden-mac/` and `golden/` became entirely untracked. Those seven stay by proof; they head the [Load-bearing paths](#load-bearing-paths) table below.
>
> The record still exists, unchanged, in the operator's working tree. The shelf table below describes **that** copy, not what a clone of this repository contains. Reading this from a clone: the `reports/`, `prompts/` and `decisions/` shelves are gone, and every `CP-NN` and ADR citation in the surviving documents — this repository's, the charter's, the spec's, the consumer repos', and the two report paths inside the wheel-shipped `pins.gsj.json` provenance — is a footnote you cannot follow: it resolves only in the operator's private record. That is the cost of the decision, recorded here rather than papered over: the evaluation's product was a checkable record, and from a clone the checkable part now ends at the code, the suites, and the evidence bodies they execute against.

## Read this first

1. [`VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) — the adoption verdict, its reversing conditions, and the consolidated wishlist. Standalone: read it, then stop.
2. [`CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) — the normative document: scope laws, the assumption register (§4), the capability/gap register (§7), the standing rules (§8).
3. [`checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) — why each validator rule exists: the gates, admission, the logprob discipline.
4. [`corpus-contract.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md) — the corpus tree contract, the input `ingest_corpus.py validate` checks.
5. `AUDIT-2026-08-24.md` — *private, operator's copy only*: the 24-agent adversarial audit of the whole record against the working trees, executed suites, and published artifacts; zero of 91 findings refuted, the drift itemized with owners.

![The reading order as three numbered shelves: run it (this guide, the README, the two consumer repositories), trust it (the verdict, standalone), change it (the charter, the checks specification, the corpus contract)](guide/img/document-map.png)

<sub>Three shelves, read top-down: what you open to run the library, the one document that settles whether to trust it, and the three that bind anyone changing it.</sub>

## The shelves

| Shelf | What it is | Who opens it | In a clone |
| --- | --- | --- | --- |
| [`guide/`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/README.md) | **The user documentation**: plain Markdown, `guide/README.md` is the index — installation, the two quickstarts, concepts, the how-to guides, the reference (Python API, finding vocabulary, wire formats), troubleshooting — with diagrams as PNGs under `guide/img/`. The diagram sources are PowerPoint decks kept outside this repository. Written for consumers; not part of the evaluation record | anyone adopting the library | tracked |
| `VERDICT.md`, `CHARTER.md`, `checks-spec.md`, `corpus-contract.md` | The four normative documents, described under [Read this first](#read-this-first) | see above | tracked |
| `polar/` | Real Polar run artifacts — fidelity, the training loops, thinking, the adversarial probe — indexed by its own shelf README | anyone re-verifying an episode claim | seven bodies tracked, the rest private |
| `golden/` | The golden-pair evidence — `mac/`, `h200/`, `COMPARISON.md` — the A-1 fidelity proof against the archived predecessor's reference traces | anyone re-verifying the `loss_mask`/`prompt_ids` claims | private; the Mac fixtures are tracked at `../tests/fixtures/golden-mac/` |
| `reports/` | One report per checkpoint (CP-00 through the present, plus the prime/letter checkpoints CP-04′, CP-09′, CP-11b, CP-13a), in the fixed template — the primary evidence behind every number in the root README and the verdict | an auditor chasing a claim to its source | private |
| `prompts/` | Every checkpoint's instructions, saved verbatim — read beside the same-numbered report to compare what was asked with what was delivered | an auditor verifying process | private |
| `decisions/` | The ADRs, append-only, one decision each, Context → Decision → Consequence (ADR-0001 through ADR-0026 at CP-46; ADR-0027 since) | anyone asking "why is it built this way" | private |
| `AUDIT-2026-08-24.md`, `CLASSIFICATION.md` | The adversarial audit of the record, and the CP-47 census that classified every tracked file by audience and coupling — the basis of the CP-48 untracking | an auditor; anyone asking what a clone should contain | private |

## Who needs what

- **Training against a server** (the pip consumer): [`guide/README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/README.md) and the pages it indexes — start at [Installation](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/installation.md) and the [Trainer quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/trainer-quickstart.md) — then `checks-spec.md` when you need the reasoning behind a finding.
- **Operating an estate**: the [Server quickstart](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/getting-started/server-quickstart.md) and [The estate](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/guides/estate.md) in the guide; otherwise nothing here — [`../estate/`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/estate/README.md) (its README is the recipe, `estate.sh` the front door) and [`../pins/`](https://github.com/MHGanainy/gsj-harness-rollout-server/tree/main/pins) are the operator's directories.
- **Deciding whether to trust this server**: the [root README](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/README.md), then `VERDICT.md`, then the audit if you hold the private copy — and stop. The audit read all the reports adversarially so you don't have to.
- **Changing the library**: `CHARTER.md` binds you, and so do the decision records (`decisions/`, private); [`../CLAUDE.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/CLAUDE.md) is the process contract.
- **Auditing a claim**: everything, at these paths — the record is citable at its current paths by design, and stays put. From a clone: the code, the suites, the pins walk, and the evidence bodies below.

## Load-bearing paths

The record is not passive text. These paths are read by code, and moving them breaks the build. The seven `polar/` bodies are exactly the negated rows of the repository's `.gitignore`; the Mac fixtures are ordinary tracked files under `../tests/fixtures/`.

| Path | Read by |
| --- | --- |
| `polar/h200-fidelity/callback_session_result.json` | The install proof in [`.github/workflows/ci.yml`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/.github/workflows/ci.yml) and [`release.yml`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/.github/workflows/release.yml) — the built wheel validates this real callback body from outside the checkout — and the root suite (`tests/test_checks.py`) |
| `polar/pi-corpus/callback_session_result.json`, `polar/fidelity/callback_session_result.json` | The root suite's fixtures (`tests/conftest.py`) and the corpus suite (`estate/corpus/tests/test_taskbank.py`) |
| `polar/pi-corpus/trace.json`, `polar/fidelity/trace.json` | [`pins/derive_pins.py`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/pins/derive_pins.py), which re-derives the approved tool-roster and system-prompt hashes from each trace's `tools[]` and `prompt_messages[0]`; the wheel-shipped `pins.gsj.json` names these paths in its provenance blocks. The root suite's fixtures also load `fidelity/trace.json` |
| `polar/h200-stitch/attempt5.accepted.json`, `polar/thinking/episode-on.quarantined.json` | The root suite (`tests/test_checks.py`) |
| `../tests/fixtures/golden-mac/` — `tokens.npz`, `record.json`, `MANIFEST.md` | The root suite's fixtures (`tests/conftest.py`). The Mac golden fixtures, the A-1 provenance chain, lived under `golden/` until they moved here |

Nothing in this directory is dead: every suspicion of a stale file was catalogued and disproved. This index shelves; it does not prune.

## Provenance

Citations that the body above used to carry inline, kept here so nothing is lost:

- This shelf map was added at CP-46; its mechanism is `polar/README.md`'s (CP-41), one level up.
- The Mac golden fixtures moved from `golden/` to `../tests/fixtures/golden-mac/` at CP-49.
- "The record is citable at its current paths by design, and stays put" — CP-46.
- "Nothing in this directory is dead" — `AUDIT-2026-08-24.md` §RESIDUE catalogued every suspicion and disproved each one.
