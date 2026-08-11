# ADR-0015 — split-by-directory: the train/eval split becomes a property of the corpus tree

## Context

The train/eval split has lived in `corpus.yaml` as `eval_case_ids` — a
manifest key naming the held-out cases, applied at taskbank-build time as
a per-row `split` column (contract v1; the frozen staging bank carries
`train: 9 / eval: 3`). Everything else about a case is expressed by where
its files sit in the tree; the split alone was expressed by an entry in a
list a directory away from the case it governs. A case could be added
without anyone touching the manifest, silently defaulting to train; the
tree could be read completely without learning the split at all. CP-14's
scope is to make the split a property of the corpus tree and carry it
through the taskbank row into the trace. The taskbank builder itself
stays deferred (ADR-0003) — this ADR specifies the split's path into a
row so the deferred implementation has no decisions left.

## Decision

1. **The shape.** Confirmed as proposed:

   ```
   <corpus-root>/
     corpus.yaml  AGENTS.md  skills/          # corpus-level, shared, ABOVE the split
     train/cases/<case_id>/timestep-<T>/…
     eval/cases/<case_id>/timestep-<T>/…
   ```

   Corpus-level files stay at the root: they are shared by both splits,
   and putting them above the split states that a split changes *which
   cases* are held out, never *what the corpus is*. The alternative
   `cases/{train,eval}/<case_id>/` (one `cases/` roof, split one level
   down) was considered and rejected: the split is the fact this CP
   exists to make un-missable, and `ls <corpus-root>` showing `train/`
   and `eval/` is exactly that; the proposed shape also preserves the
   `cases/<case_id>/timestep-<T>` path suffix, so every per-case rule,
   message, and habit from contract v1 keeps its shape one level deeper.

2. **`eval_case_ids` retires — and is rejected, not ignored.** The
   validator fails a `corpus.yaml` still carrying the key, with a message
   naming the migration:

   > `'eval_case_ids' is retired (ADR-0015) — the split is now the
   > directory layout: move each listed case under
   > <corpus-root>/eval/cases/, every other case under
   > <corpus-root>/train/cases/, then delete this key`

   Likewise a root-level `cases/` directory (the v1 shape) is rejected
   with its own migration message rather than reported as a generic
   stray. Silently ignoring either is how a data-prep team ships a corpus
   whose split means nothing.

3. **Exactly one split per case.** A `case_id` present under both
   `train/cases/` and `eval/cases/` is a hard validation failure:

   > `case '<case_id>' present under both train/cases/ and eval/cases/ —
   > a case belongs to exactly one split (ADR-0015); remove one`

4. **Two splits, named `train` and `eval`, no third.** The corpus root is
   now strict: besides the corpus-level files and the two generated
   artifacts, only `train/` and `eval/` are allowed, so a `test/` tree
   fails loudly instead of silently vanishing (dot-prefixed entries are
   ignored at the root only — a corpus source tree may be a git repo).
   The door to a third split is deliberately left open, but only through
   an ADR of its own: if `test` ever earns its keep, that ADR decides its
   semantics; nothing lands by directory creation alone.

5. **What the split means downstream — carried and visible, not
   enforced.** The split rides: tree → `corpus.lock.json`
   (`cases.<case_id>.split`) → the taskbank row (deferred, §row-spec
   below) → `TaskRequest.metadata.split` → trace metadata (the
   CP-11-proven hoist). Nothing in this repo *enforces* it: the
   predecessor's loader had a role lock and this repo dropped the loader
   at CP-00 (charter §3, "deliberately dropped"), so **the trainer owns
   not training on eval**. The one thing enforced here is the
   *vocabulary*: a trace whose metadata states a split outside
   `{train, eval}` is rejected at the receiver
   (`TR3:split_not_train_or_eval`) — so no de facto third split can
   arrive through the metadata channel unnoticed. That is a check on the
   submitter's own statement, named as such in `docs/checks-spec.md`; an
   unenforceable guarantee stated as a guarantee would be worse than this
   honest label. Gap-register row 32 records the dropped enforcement.

6. **Clarification, not new capability.** `eval_case_ids` already
   expressed a case-level split; this ADR moves the same fact into the
   tree and retires the key. One mechanism, not two: contract v2
   describes only the directory form, and the per-case granularity is
   unchanged — the split is per case, never per timestep.

**The row-spec (binding on the deferred ADR-0003 builder).** Each taskbank
row carries a `split` field, value `train` or `eval`, case-level: every
row of a case takes the case's directory split as recorded in
`corpus.lock.json` `cases.<case_id>.split`. The lock's `taskbank` block
keeps its `train`/`eval` row counts. The builder passes the row's `split`
to `config.render_task_request(split=…)`, which states it in
`TaskRequest.metadata` beside `case_id`/`timestep`/`prompt_source`.
`split` is a render *parameter*, not a config key or a lock lookup — the
config surface must not grow a corpus dependency, and the taskbank is the
component that reads the lock. Absent means **unstated** (the frozen
`cli.py` submit path cannot know it); it is never defaulted to `train`,
because a false label is worse than a missing one.

**The lock re-derives; nothing re-pins.** `corpus.lock.json` gains
`split` per case and drops `corpus.eval_case_ids`, so its bytes and
sha256 change — a re-derive of a generated record, not a re-pin of
evidence. What moves: `corpus.yaml` (key deleted), the lock (split
fields), the directory layout. What must not move: every page's bytes,
`AGENTS.md`, `skills/`, `prompts.yaml` files, every ref SHA in the lock
(a case repo is split-agnostic, ADR-0006 — scaffold output is
byte-identical), and the frozen `taskbank.parquet` with its recorded
sha `9eb8e3c2…`. Any ref SHA that changes under the move means content
was touched, and the CP stops.

## Consequence

- Contract v2 (`docs/corpus-contract.md`) describes one split mechanism;
  a v1 corpus fails validation with messages that name the migration
  (move cases under `train/cases/`/`eval/cases/`, delete
  `eval_case_ids`). The corpus root becomes strict for visible entries.
- The staging tree re-shapes (`case_0004` → eval per the manifest, the
  rest → train); its lock re-derives with identical refs; the frozen
  parquet is carried unchanged and still sha-verifies.
- `phase_verify` gains a split clause: a case whose tree split disagrees
  with the lock's is a mismatch — moving a case between splits requires a
  re-scaffold, so the freeze record always states the live split.
- `checks.py` gains one tripwire (`TR3`) and `config.py` one render
  parameter; both sides of law 6 see the same label. Enforcement of the
  split's *meaning* is explicitly the trainer's (row 32).
- The predecessor's corpus and contract v1 are untouched (law 3); this is
  the first deliberate divergence of the carried contract from the
  predecessor's (row 1 annotated).
