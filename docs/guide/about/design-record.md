[Documentation](../README.md) › About

# The design record

This page tells you where the library came from, which documents hold its reasoning and what each one is for, what happened to the predecessor it replaced, which repositories sit beside it, what licence covers what, and why some citations in the tracked documents cannot be followed from a clone.

## Where the library came from

The library is the product of an evaluation, not a greenfield build. Its predecessor, `gsj-envloader`, ran the same corpus episodes with roughly 1,800 lines of its own episode execution and capture: a checkout → run → harvest → reset lifecycle with Docker bolted inside, per-episode gateway sessions, and a finalize pipeline. That layer worked and was externally verified, but it was expensive to keep: approved sets re-derived at nearly every image or mount change, and a capture transport that changed three times.

The question the evaluation asked was whether NVIDIA's Polar ([`NVIDIA-NeMo/ProRL-Agent-Server`](https://github.com/NVIDIA-NeMo/ProRL-Agent-Server)) could own that layer, leaving a thin shell: the corpus, the temporally-scoped retrieval service, a harness for the pinned agent (pi 0.83.0), and the validation. The success criterion was stated in advance:

> One real episode against our corpus, through our MCP service, with the cutoff enforced, producing a trace whose token ids, `loss_mask`, and logprobs verifiably match the golden reference the predecessor produced for the same task.

The verdict is **ADOPT**. It was provisional on 2026-08-09 and converted on 2026-08-11, when both converting conditions held: the golden pair collected on the production hardware (H200) passed with the replay run as written, and a trainer took one real optimizer step on traces collected through this path. The conditions that would reverse it — a mask or retokenization divergence attributable to Polar with no fix in our code, a trainer bridge that proves unusable, or a re-vendor that breaks the patch posture — are kept on record in [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md), together with the five abandon conditions written down before the work began so the decision would not be made under sunk cost.

What the evaluation left behind is the shape described in [Architecture](../concepts/architecture.md): Polar, vendored by commit into `vendor/polar/` with three carried patches (`POLAR_SHA` records the pin and the patch list), driven by 1,999 lines of our own code.

## The documents and what each is for

Everything normative is tracked in the repository and readable from a clone. The reading order depends on what you are trying to do: run the library, trust it, or change it.

![The document map: three numbered shelves. Shelf 1, run it: this site, the README, the examples repo and the demo repo. Shelf 2, trust it: VERDICT.md alone. Shelf 3, change it: CHARTER.md, checks-spec.md and corpus-contract.md.](../img/document-map.png)

<sub>One shelf per intent: shelf 1 to run the library, shelf 2 to decide whether to trust it (the verdict is standalone — read it, then stop), shelf 3 to change it. Auditing has its own map, [further down this page](#the-development-record-is-private).</sub>

| Document | What it is | Open it when |
| --- | --- | --- |
| This site (`docs/guide/`) | The user documentation: installation, the two quickstarts, concepts, configuration, the Python API. Written for consumers; not part of the evaluation record. | You are adopting the library. |
| [`README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/README.md) | The repository's front door: the shape, the cutoff, the two roles, what has been measured, the licence. | First contact with the repository. |
| [`docs/VERDICT.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/VERDICT.md) | The adoption verdict: what Polar gave, what it cost, what we still own, whether it works, the conditions that would reverse the verdict, and the consolidated list of open wants. Standalone. | You are deciding whether to trust the server. |
| [`docs/CHARTER.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md) | The normative document: the scope laws, the assumption register (§4 — every assumption with its basis and its if-false consequence), the capability and gap register (§7 — the table the repository is judged by), and the standing rules (§8). | You are changing the library, or asking why a capability is present, absent, or dropped. |
| [`docs/checks-spec.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md) | Why each validator rule exists: the pins and approved-set format, the hashing conventions, the gates, admission, the failure vocabulary, the logprob discipline. | A finding came back and you need the reasoning behind it. See [Validation](../concepts/validation.md) and [Finding vocabulary](../reference/findings.md) for the consumer view. |
| [`docs/corpus-contract.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md) | The corpus source-tree contract: the directory shape `ingest_corpus.py validate` enforces, written for the data-prep team and self-contained. | You are preparing a corpus. See [The corpus](../guides/corpus.md). |
| [`docs/README.md`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/README.md) | The shelf map of `docs/`. It describes the operator's full copy of the record, not what a clone contains — see [the private record](#the-development-record-is-private) below. | You want to know what a citation was pointing at. |
| [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE) | Apache-2.0, covering our code. `vendor/polar/LICENSE` covers the vendored tree. | See [Licence](#licence). |

> [!TIP]
> **The short path to a trust decision**
>
> Read the `README.md`, then `docs/VERDICT.md`, and stop. The verdict is written to be standalone: it names its evidence but does not require reading it. The charter is for people who change the library; the two specifications are for people who hit a finding or prepare a corpus.

## The predecessor

`gsj-envloader` at tag `v0.8.0` is the stack this library replaced, and its status is settled:

| | |
| --- | --- |
| Status | **Archived.** The GitHub repository is set to archived and is read-only. The only write the evaluation ever made to it was the archive header in its README, one commit past `v0.8.0`; by design no other checkpoint of the work touched it. |
| Role | **The golden reference.** It is the collecting stack for both golden pairs — one on a Mac estate, one on the production H200 estate — that this library's fidelity claims are measured against: `loss_mask` exact at zero tolerance and `prompt_ids` byte-identical on the same task triple. `v0.8.0` stays readable and cloneable so those comparisons remain reproducible. |
| Not a role | **The fallback.** Keeping the predecessor alive as a fallback was a term of the *provisional* adopt and expired when the verdict converted. Nothing in this library depends on it at runtime. |

Two things carried over rather than being rebuilt: the corpus pipeline and the retrieval service, which now live under `estate/` and are outside the library's line budget, and the golden traces themselves, whose Mac-side fixtures are tracked under `tests/fixtures/golden-mac/` and exercised by the test suite.

## The consumer repos

Two public repositories sit beside the library, one per role. Neither is needed to install the wheel; each is the fastest route to a working setup for its role.

| Repository | Role | Start at |
| --- | --- | --- |
| [`gsj-harness-rollout-server-examples`](https://github.com/MHGanainy/gsj-harness-rollout-server-examples) | Trainer side: a training loop against an existing server, including the slime and verl bridges. The bridges install from there — each is a requirements file plus one documented command — because neither can be a pip extra of this package (verl must install `--no-deps` from a pinned git SHA; slime is a container image). | Its `RUNBOOK.md`, then [Running a training loop](../guides/training-loop.md). |
| [`gsj-rollout-demo`](https://github.com/MHGanainy/gsj-rollout-demo) | Bring-your-own estate: from a fresh machine to the first accepted episode, with the demo README as the only input. | Its README, then [The estate](../guides/estate.md). |

Both repositories are consumers in the strict sense: their loops and bring-ups were run against the server without changing anything in `gsj_rollout/`, which is what the scope law asks of a rollout server.

## Licence

| What | Licence | Where it is stated |
| --- | --- | --- |
| Our code (`gsj_rollout/`, `estate/`, `pins/`, the docs) | Apache-2.0 | [`LICENSE`](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/LICENSE) at the repository root; `pyproject.toml` declares `license = "Apache-2.0"` with `license-files = ["LICENSE"]`. |
| `vendor/polar/` | Apache-2.0, **NVIDIA's** (Copyright 2026 NVIDIA) | `vendor/polar/LICENSE`, carried with the vendored tree. The same licence was chosen for our code deliberately, so one tree holds one set of terms; the distinction is kept structural rather than textual. |

The vendored tree ships in no released artifact. Publication is wheel-only, and the wheel contains `gsj_rollout/`, the two pins sets, and `ingest_corpus.py` — nothing else. The release workflow asserts this on the built artifact: any path under `vendor/`, `estate/`, `spike/`, `tests/`, `docs/` or `.github/` in the wheel fails the release. So nothing NVIDIA-authored is published under this project's name, and installing the wheel gives you our code under our licence only. See [Installation](../getting-started/installation.md) for what the wheel does and does not contain.

The package metadata points at the documents above, so they are one click from the PyPI page:

| PyPI project URL | Target |
| --- | --- |
| Repository | <https://github.com/MHGanainy/gsj-harness-rollout-server> |
| Verdict | `docs/VERDICT.md` |
| Charter | `docs/CHARTER.md` |
| Checks specification | `docs/checks-spec.md` |

## The development record is private

The library was built in numbered checkpoints, each with a prompt, a report, and where a decision was taken, a decision record. That per-checkpoint record — the prompts, the reports, the decision records, the audit of the record, and the raw golden-pair and run evidence — **is maintained privately by the operator and is not tracked in the repository**. It exists, unchanged, in the operator's working tree; a clone does not contain it.

> [!WARNING]
> **`CP-NN` and ADR citations do not resolve from a clone**
>
> The tracked documents — the README, the charter, the verdict, the checks specification, and the provenance blocks inside the wheel-shipped `pins.gsj.json` — cite checkpoint reports (`docs/reports/CP-NN.md`) and decision records (`ADR-NNNN`) as their evidence. Those citations were left as written rather than rewritten: they are true of the private record, and rewriting settled documents is not something this project does. From a clone they are footnotes you cannot follow. Treat a claim that rests only on such a citation as *asserted*, not as checkable at the cited path.

![The evidence map: a public region anyone can check — the code and its three test suites, the pins walk, the tracked documents, the release gate's wheel assertions, the evidence bodies, and the archived gsj-envloader v0.8.0 — beside a private region holding the operator's prompts and reports, decision records, and the audit and raw run evidence. An arrow from the tracked documents toward the private record is barred at the boundary: it cites, but does not resolve. A five-step strip below shows the check sequence a clone runs.](../img/evidence-map.png)

<sub>What a clone can check (left) and what it cannot reach (right): the tracked documents cite the private record, but the citation stops at the boundary. The strip along the bottom is the audit sequence, spelled out below.</sub>

What remains checkable from a clone is the code and what it executes against:

```bash
git clone https://github.com/MHGanainy/gsj-harness-rollout-server
cd gsj-harness-rollout-server
pip install -e ".[dev]"
pytest -q                               # the root suite (the corpus and mcp-service suites live under estate/)
bash vendor/apply_patches.sh --verify   # asserts all three carried patches are applied to vendor/polar/
cat POLAR_SHA                           # the pin: upstream repo, branch, commit, and the patch list
```

Beyond the suites: the pins walk (`pins/derive_pins.py`) re-derives every approved-set hash from the evidence bodies it names, the release workflow's assertions run against every built wheel, and the handful of evidence bodies under `docs/polar/` that CI, the test suites, and the pins walk actually read stay tracked for exactly that reason. This page and the rest of the site are written from the code as it is, so nothing here depends on the private record to be verified — where a page states a number, the number comes from a document or an artifact you can open.
