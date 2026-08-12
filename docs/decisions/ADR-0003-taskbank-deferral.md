# ADR-0003 — Defer the taskbank phase to CP-07

## Context

`corpus/ingest_corpus.py`'s `taskbank` phase builds the §3.1 parquet
through the predecessor's public library API — `CaseSpec`, `PromptSpec`,
`build_taskbank`, `write_taskbank`, `read_taskbank`, `TASKBANK_SCHEMA` —
imported lazily in exactly three places (`build_corpus_table`,
`phase_taskbank`, and `phase_verify`'s row-level bank check). That library
is not in this repo. The options: (a) depend on `gsj-envloader` as a
pinned dependency for the taskbank phase only, (b) inline the ~200 lines
of taskbank building into `corpus/`, or (c) defer the phase until CP-07
tells us what shape Polar wants tasks in.

## Decision

**(c) — defer.** Polar takes `TaskRequest`s, not §3.1 parquet rows
(charter §3: the loader and its parquet-consuming stack are deliberately
dropped, and gap row 4 already records that tasks arrive as
`(case, timestep, prompt)` via `client.submit`). Building a parquet we may
never serve is speculative work; (a) would make the frozen predecessor a
live dependency of this repo's pipeline, and (b) would inline ~200 lines
against a size discipline that exists to prevent exactly that accretion —
both to produce an artifact with no consumer here.

Applied to the pipeline (the only CP-01 edits to its logic):

- `phase_taskbank` raises a `PipelineError`: *"the taskbank phase is
  deferred to CP-07 (ADR-0003) — Polar takes TaskRequests, not §3.1
  parquet rows"*. `all` prints the same deferral loudly and continues to
  `verify` (the `--only` skip precedent).
- `build_corpus_table` and `expected_triples` — the code that imported the
  library — are deleted, recoverable from the predecessor @ v0.8.0.
- `phase_verify` keeps every check it can run with the stdlib: the bank
  file's existence and its sha256 against the lock (the carried parquet is
  frozen reference data, ADR-0002). The row-level semantics checks
  (triples-exactly-once, split, sandbox_image), which need
  `read_taskbank`, are reported as SKIPPED with the deferral named.
- validate / scaffold / ingest are untouched and never imported the
  library.
- `corpus/tests/test_taskbank.py` (5 tests) cannot run without the library
  and is skipped module-level with the deferral as the stated reason.
  `test_verify.py`'s one library-dependent test
  (`test_doctored_parquet_fails_sha_and_rowset`) is rewritten library-free
  against the surviving sha256 check, and the two tests that asserted the
  old must-have-a-bank behavior are rewritten to assert the deferral
  (counts in the CP-01 report).

## Consequence

The pipeline stands alone: validate → scaffold → ingest → verify run with
stdlib + PyYAML + git. The frozen `taskbank.parquet` + `corpus.lock.json`
remain byte-verifiable here (sha256), but no new bank can be built in this
repo until CP-07 decides the task shape — at which point either a
`TaskRequest`-shaped builder lands in `client.py`'s orbit (the likely
outcome) or, if Polar turns out to want §3.1 rows after all, this ADR is
revisited against options (a)/(b). Gap row 4 carries the deferral; the
predecessor remains able to rebuild the parquet at any time (it is frozen,
not retired).

---

**[CP-24] The deferral resolves — ADR-0022.** The grounds above still
hold (Polar takes `TaskRequest`s; the predecessor's library never became
a dependency): what landed is not the §3.1 bank this ADR declined to
build, but a consumer-facing enumeration shaped for
`render_task_request`, built by `corpus/ingest_corpus.py` itself with
pyarrow (`corpus/requirements.txt`). Option (c)'s exit condition fired
in the direction the Consequence paragraph predicted, with one precision
the paragraph's wording lacked: the builder is `TaskRequest`-shaped in
its *surface* (every row column is the triple or a `render_task_request`
argument) but it landed in `corpus/`'s pipeline, not `client.py`'s
orbit — the bank enumerates rows a consumer renders; it does not render
them itself (ADR-0022 §1). Not options (a)/(b) in any part.
`phase_taskbank` builds, `phase_verify` runs the deferred row-level
checks, gap row 4 → PARITY.
