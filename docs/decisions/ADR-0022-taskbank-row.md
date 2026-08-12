# ADR-0022 — the taskbank row: an enumeration for consumers, shaped for `render_task_request`

## Context

ADR-0003 deferred the taskbank phase because Polar takes `TaskRequest`s,
not §3.1 parquet rows — and that reasoning still holds. What changed is
the *consumer*: Phase D's story ships a parquet per project, and today a
consumer holding this repo enumerates `(case, timestep, prompt)` triples
by hand from the tree. The bank this ADR lands is therefore **not** what
the predecessor's was:

- **Not** an input Polar consumes. Polar takes a `TaskRequest`; the
  arrival path (`render_task_request` → `client.submit`) has been real
  since CP-08 and is untouched here.
- **Is** the enumeration a consumer needs: which triples exist, which
  split each belongs to, and — verbatim — what a submitter passes to
  `render_task_request`. A row submits without translation.

Everything the row must carry was specified before this CP: the split's
path is ADR-0015's row-spec (per-row `split` ∈ {train, eval}, case-level,
sourced from `lock.cases.<id>.split`, passed to
`render_task_request(split=…)`; the lock's `taskbank` block keeps the
train/eval counts), and the prompt-origin statement is CP-13's
(`prompt_source`, `skill_card_text`, hash computed at render).

## Decision

### 1. The row shape — the render surface, flat, eight columns

One row per `(case, timestep, prompt)` triple. Schema, in column order:

| column | type | why it is there / what a consumer does with it |
| --- | --- | --- |
| `case_id` | string | the triple; names the case repo (`clone_url_for.format(case_id=…)`) and `render_task_request(case_id=…)` |
| `timestep` | int64 | the triple; selects branch `timestep-<T>` and the retrieval cutoff; `render_task_request(timestep=…)` |
| `prompt_id` | string | the triple; `skill:<name>` \| `free:<slug>` — the contract's id, unique per `(case, timestep)`; names the ask in run books and joins back to the tree |
| `split` | string | `train` \| `eval`, case-level from `lock.cases.<id>.split` (ADR-0015 row-spec, binding); `render_task_request(split=…)` — the trainer's routing label |
| `prompt_source` | string | `free` \| `skill:<name>` — the exact `render_task_request(prompt_source=…)` value (G1's statement), carried verbatim so no consumer re-derives it from `prompt_id` |
| `prompt_text` | string, null on skill rows | free rows: the contract's verbatim text, byte-for-byte from `prompts.yaml` — the instruction a consumer submits |
| `skill_card_text` | string, null on free rows | skill rows: the resolved card (§2) — `render_task_request(skill_card_text=…)`, and the instruction |
| `sandbox_image` | string | corpus-level constant carried per row (contract v2 already promises it; predecessor parity) — the image an estate must serve for the row to mean what it meant |

**Deliberately dropped from the predecessor's §3.1 shape**, each with the
reason: `data_source` (a constant `"gsj_cases"` keying the predecessor's
loader registry — the loader was dropped at CP-00, charter §3);
the chat-message `prompt` list (the loader's chat shape; our submit
surface takes an instruction string); the `extra_info.tools_kwargs.task…`
nesting (the loader's tool-wiring envelope; here runtime/agent settings
come from the one YAML, never from a row). The predecessor's
`metadata.{case_repo_id, timestep, prompt_id, prompt_source}` survives as
the flat triple + `prompt_source`, with `prompt_source` upgraded from
`skill`/`free` to the render-ready `skill:<name>`/`free`. Flat columns,
no struct nesting: the consumers are dataframe readers, and the row's
contract is "pass these fields on", not "reproduce the loader's object
model".

The submit path a row implies, whole:

```python
row = taskbank.to_pylist()[i]
body = render_task_request(
    cfg, task_id=…, instruction=row["prompt_text"] or row["skill_card_text"],
    case_id=row["case_id"], timestep=row["timestep"],
    prompt_source=row["prompt_source"], skill_card_text=row["skill_card_text"],
    split=row["split"])
```

No `config.py` change: CP-13 and CP-14 built these parameters for exactly
this, and the row fitting them unmodified is the result those checkpoints
were aiming at.

### 2. Skill resolution — the bank carries the resolved text

A skill row carries the card's **resolved text**: the corpus-level
`skills/<name>/SKILL.md` read as `read_bytes().decode("utf-8")` (CP-13's
binding constraint — never `read_text()`, whose locale/newline
translation would silently change the downstream hash). Not the hash, not
a bare reference, not nothing:

- **Text, because the hash is computed at render.**
  `render_task_request(skill_card_text=…)` computes `skill_card_hash`
  itself (convention 1) so nothing downstream trusts a caller's
  arithmetic — a bank carrying only a hash would leave the consumer
  nothing to pass, G1 fail-closed (`G1:missing_evidence:skill_card_hash`)
  and the statement's provenance unimproved. Carrying both text and a
  hash invites the two to disagree.
- **This is where G1's statement comes from honestly.** The chain lands
  whole: corpus card bytes → bank `skill_card_text` → render-computed
  hash → `TaskRequest.metadata` → trace metadata (the CP-11 hoist) →
  `check_skill_card` vs the pinned set. The pins' own provenance note
  ("'as resolved at rollout' == these bytes") stays true: the bank
  resolves the same corpus-level bytes the scaffolder writes into every
  case repo, and `verify`'s row half re-checks the equality.
- **The limit, named.** This is *build-time* resolution of the
  corpus-level card. It cannot see a drifted checkout — that remains
  wishlist 9 (sandbox-side hashing, `pi_harness.py`), unchanged in kind:
  what the bank adds is an honest statement to verify, not the
  predecessor's instrument that read the episode's own checkout. And a
  card edited after a bank build makes the bank stale — `verify`'s row
  half compares every row's `skill_card_text` (and free `prompt_text`)
  back to the tree, so staleness is a named FAIL, not a drift.

The contract's v1 sentence "the card's text is not baked anywhere at
build time" is superseded for the bank (contract updated this CP): the
card *is* baked into the bank row at build time, from the corpus level —
which is also exactly what every case repo carries, per verify.

### 3. Free rows — verbatim text, confirmed

`prompt_text` is the `prompts.yaml` string byte-for-byte (the contract
stores it; the bank carries it; verify compares it back). `skill_card_text`
is null; `prompt_source` is `free`; G1 passes n/a by CP-13's contract.

### 4. Determinism

Byte-identical rebuilds from an unchanged tree, by construction: rows
sorted by `(case_id, timestep, prompt_id)`; a fixed explicit schema
(types above, one row group, the writer's defaults otherwise); no
timestamps, no environment values, no absolute paths anywhere in the
artifact. The lock's `taskbank` block keeps exactly its frozen key set
(`path`, `rows`, `train`, `eval`, `sha256`) — no new keys, so the lock
stays byte-reproducible too. One honest caveat, recorded rather than
implied: the parquet footer embeds the writer's own version string
(`created_by: parquet-cpp-arrow …`), so byte-identity is guaranteed *per
environment* — a pyarrow upgrade changes bytes without changing rows.
The lock's sha256 pins the artifact; `verify`'s row-level half checks the
semantics bytes-independently, so a writer-version rebuild is a
re-derive (new sha in the lock), never a silent divergence.

### 5. The writer — pyarrow, corpus-side only (R1)

The off-the-shelf candidate is **pyarrow** (the parquet reference
implementation; already in this project's orbit — mcp-service's venv
carries it, and the frozen bank was written by it). Rejected: a
hand-rolled stdlib parquet writer (R1 — hundreds of lines of format
code to avoid a standard dependency); depending on the frozen
predecessor for its `write_taskbank` (ADR-0003's original grounds stand:
the frozen repo must not become a live dependency). pyarrow is imported
**lazily** inside the taskbank build/read paths and recorded in
`corpus/requirements.txt`; a missing install is a `PipelineError` naming
it. The root package's dependencies are untouched (`pyproject.toml` is
not lifted this CP, and the trainer-side wheel has no reason to carry a
parquet writer): the dependency belongs to the moved component that
writes the artifact, exactly like mcp-service's belong to it.

### 6. The frozen bank

The staging bank (`9eb8e3c2…`, 12 rows, train 9 / eval 3) is superseded
by a rebuild under this schema. The triple set and split assignment are
expected to reproduce exactly (the staging tree's prompts are unchanged);
the bytes are not (§3.1 nesting dropped, columns added, writer version).
The lock records the new sha; the diff is reported precisely in
`docs/reports/CP-24.md`. ADR-0002's "carried as frozen reference data"
clause retires for the bank: from this CP the bank is a *generated*
artifact of this pipeline, like the lock.

## Consequence

- `phase_taskbank` builds; ADR-0003's deferral resolves (marked there,
  not rewritten). Gap row 4 → PARITY; G1 has its end-to-end story.
- `verify` gains the deferred row-level half: count and split totals vs
  the lock, triples exactly-once and set-equal to the tree, per-row
  split vs the lock's case split, `sandbox_image` vs the corpus, and
  text columns byte-equal to the tree.
- `--only` never builds or half-builds a bank (usage error on
  `taskbank`, loud skip under `all` — ADR-0047(e) upheld).
- A consumer reads the parquet and submits rows without translation;
  what it cannot get from the bank remains deliberate: no scheduling, no
  scoring, no storage (law 1).
