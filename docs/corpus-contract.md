# The corpus source-directory contract (v1, CP-33 / ADR-0046)

**Audience: the data-prep team.** This document is self-contained — you do
not need to know anything else about this repository. You produce one
directory tree in the shape below; the ingestion pipeline
(`corpus/ingest_corpus.py`) turns it into git case repositories, a search
index, and a task table. You never edit the pipeline, and the pipeline
never edits your tree.

The pipeline is strict on purpose: **everything it can check, it checks
before anything is uploaded**, and every failure names the exact file and
rule. A tree that passes `validate` will scaffold, index, and verify
without surprises.

```
<corpus-root>/
  corpus.yaml                     # corpus-level configuration (reference below)
  AGENTS.md                       # the agent instructions, corpus-level
  skills/<name>/SKILL.md          # skill cards, corpus-level (copied into every repo)
  cases/
    <case_id>/                    # e.g. case_0007 — becomes the repo name
      case.yaml                   # OPTIONAL per-case metadata (title, notes)
      timestep-<T>/               # T = integer page cutoff, unpadded (timestep-12)
        pages/page_<NNNN>.md      # ABSOLUTE page numbering, 4-digit, exactly 1..T
        prompts.yaml              # THIS timestep's prompts (reference below)
```

Generated files the pipeline writes into `<corpus-root>` (never write these
yourself): `corpus.lock.json`, `taskbank.parquet`.

## The four hard invariants

These are the rules a folder tree cannot enforce by shape alone. The
validator enforces all four; violating any one is a hard failure and
nothing gets uploaded.

### 1. Timesteps are directories, not a filter

A timestep directory contains the **complete case as it stands at that
cutoff**: `timestep-12/pages/` contains exactly `page_0001.md` …
`page_0012.md` — all twelve files, physically present. The pipeline
*copies* your timestep directories; it never truncates a larger set down
for you. If `timestep-12` is missing `page_0003.md`, that is an error, not
an instruction.

### 2. Absolute page numbering — non-negotiable

`page_0007.md` is **page 7 of the case**, in every timestep directory that
contains it. Numbering never restarts per timestep. Pages are cited
downstream as `page:N`, audited against a page census, and served through
a retrieval service that filters on `page ≤ T` — all three break silently
if a file called `page_0001.md` is ever anything but page 1 of the case.
File names are 4-digit zero-padded (`page_0007.md`, never `page_7.md`),
and a `timestep-<T>` directory holds exactly pages 1..T — no gaps, no
extras, no padding variants.

### 3. Prefix consistency — the invariant you will break first

For any two timesteps T1 < T2 of the same case:

- every page present in both directories must be **byte-identical**, and
- `timestep-<T2>/pages/` must contain exactly `timestep-<T1>`'s pages plus
  pages T1+1..T2.

A timestep is a *cutoff of one growing document*, never a re-edit. If you
fix a typo on page 3, fix it in **every** timestep directory that contains
page 3 — the validator compares hashes across timesteps and a divergence
is a hard failure naming the case, the page, and both sha256s. (This is
the rule most likely to be broken by hand-editing; run `validate` after
every edit.)

### 4. `prompts.yaml` — what gets asked at this timestep

Each timestep directory carries its own `prompts.yaml`:

```yaml
prompts:
  - {id: "skill:tatbestand", source: skill, name: tatbestand}
  - {id: "free:entity-question", source: free,
     text: "Which parties are named so far? Cite pages."}
```

- `source: skill` — a reference to a skill card. `name` must resolve to
  `<corpus-root>/skills/<name>/SKILL.md`, and `id` must be exactly
  `skill:<name>`. The card's *text* is not baked anywhere at build time —
  it is resolved inside the checkout when an episode runs, so per-case
  card variation stays possible.
- `source: free` — a verbatim prompt. `text` is the exact user message
  (stored byte-for-byte); `id` must be `free:<slug>` with a slug of your
  choosing (letters, digits, `._-`).
- Duplicate `id`s **within one timestep** = error. The same `id` at
  different timesteps is normal (the same question asked as the case
  grows).
- An empty or absent `prompts.yaml` is **legal**: that timestep produces
  no task rows. The case branch is still built and indexed — it just
  isn't asked anything (yet).
- No other keys are allowed in an entry; unknown keys are errors.

Every `(case, timestep, prompt)` triple becomes exactly one row of the
generated task table.

## `corpus.yaml` reference

```yaml
name: my-corpus                  # corpus name (letters, digits, ._-)
owner: gsj-staging               # gsj-staging | gsj-prod — THE environment switch
forgejo:
  base_url: http://172.28.9.10:3000    # the git host serving this corpus
mcp:
  url_base: http://127.0.0.1:8790      # OPTIONAL: the retrieval service to
                                       #   (re)index after upload; omit to skip
git:                             # fixed commit identity => deterministic SHAs
  name: gsj-fixtures             #   (re-running the pipeline on an unchanged
  email: fixtures@gsj.invalid    #   tree reproduces identical commits)
  date: "2026-01-01T00:00:00 +0000"
sandbox_image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3   # rides every task row
eval_case_ids: [case_0004]       # subset of cases/; these cases are held out
                                 #   for evaluation (ALL their timesteps and
                                 #   prompts) — the split is per case, never
                                 #   per timestep
```

- `owner` selects the Forgejo account the repos live under; clone URLs
  become `<base_url>/<owner>/<case_id>.git`.
- `eval_case_ids` may be empty (everything trains); every listed id must
  exist under `cases/`.
- `git.date` is any fixed git-parseable date with offset. Do not update it
  when you edit the corpus — it exists so that identical trees produce
  identical commits, not to record wall-clock time.

## The owner switch — staging vs prod

**Staging and prod differ by exactly one value in this file plus one
credential in the environment. That is the whole point of the switch.**

| | staging | prod |
|---|---|---|
| `owner` in corpus.yaml | `gsj-staging` | `gsj-prod` |
| push credential (env var) | `GSJ_FORGEJO_TOKEN_GSJ_STAGING` | `GSJ_FORGEJO_TOKEN_GSJ_PROD` |

The env var name is derived from the owner: `GSJ_FORGEJO_TOKEN_` + the
owner uppercased with `-` → `_`. Credentials are **never** written into
`corpus.yaml` or any other file — the pipeline reads the named environment
variable at push time and refuses to run scaffold without it. Anonymous
*read* access to the pushed repos is expected (episodes clone without
credentials); the token authorizes *pushes* only.

If `mcp.url_base` is set, re-indexing additionally requires
`GSJ_MCP_TOKEN_SECRET` in the environment (the retrieval service's shared
admin secret — ask the estate operator).

## What the pipeline produces from your tree

You do not have to act on this section; it is here so the transformation
is never a surprise.

Per case, one git repository named `<case_id>` under `owner`:

- branch `main` = the **largest** timestep's pages (the fullest state of
  the document you provided);
- one branch `timestep-<T>` per timestep directory, containing exactly
  that directory's pages;
- in every branch: your corpus-level `AGENTS.md` and `skills/` verbatim,
  an `out/.gitkeep` working directory, and a fixed `.gitignore`;
- **pages land in the repo as `md/page_<NNNN>.md`** — the source tree's
  `pages/` directory maps to `md/` in the repo (the `page:N ↔
  md/page_NNNN.md` citation convention the agent instructions rely on).
  Bytes are copied unchanged; only the directory name differs.

Commits use the fixed identity and date from `corpus.yaml`, so re-running
the pipeline over an unchanged tree converges to identical commit SHAs —
uploads are idempotent, and any SHA change is a real content change.

The pipeline also writes, into `<corpus-root>`:

- `corpus.lock.json` — the record of what is live: per case and per
  branch the commit SHA, the page census, and the prompt ids; plus the
  task table's row count and sha256. Commit it with the corpus; it is the
  freeze record downstream consumers pin against.
- `taskbank.parquet` — the task table: one row per (case, timestep,
  prompt), split `train`/`eval` per `eval_case_ids`, carrying
  `sandbox_image`.

## Running the pipeline

```bash
python corpus/ingest_corpus.py validate --corpus <corpus-root>   # check the tree
python corpus/ingest_corpus.py all      --corpus <corpus-root>   # the full run
```

`all` runs the five phases in order and stops at the first failure:

| phase | what it does | what it guarantees |
|---|---|---|
| `validate` | checks this contract against your tree | nothing is uploaded unless the whole tree passes |
| `scaffold` | creates/updates the repos, pushes all branches | idempotent; deterministic SHAs; writes `corpus.lock.json` |
| `ingest` | tells the retrieval service to (re)index; waits for ready | search serves exactly the pushed corpus |
| `taskbank` | writes `taskbank.parquet`; records its sha in the lock | one row per (case, timestep, prompt), split applied |
| `verify` | clones everything **back from the git host**, re-reads the parquet, queries the service | what is *live* matches your tree and the lock, byte-for-byte |

`validate` checks the input; `verify` checks reality — the second half is
what tells you an upload actually landed as intended, so never skip it.

Useful flags: `--only <case_id> ...` (limit validate/scaffold/verify's
repo work to some cases — the task table is corpus-wide, so the
`taskbank` phase is skipped and your committed table is left alone;
refresh it afterwards with a plain `taskbank` run), `--dry-run` (validate
+ build everything locally, push nothing, write nothing), `--skip-ingest`
(no retrieval service in reach), `--owner-override <owner>` (push the same
tree under a different account — e.g. a rehearsal under `gsj-staging` of a
tree whose `corpus.yaml` says `gsj-prod`).

Omitting `mcp.url_base` from `corpus.yaml` skips the `ingest` phase (and
`verify`'s search-service check) with a printed note — that is the
supported "no retrieval service" configuration; `--skip-ingest` is the
same skip on a corpus that *does* name one.

Validation output is a table — one line per case and timestep, `PASS` or
`FAIL` with the specific rule broken and file named. The exit code is
non-zero if anything failed, and no later phase runs.

## Worked minimal example

A complete, valid corpus with one case, two timesteps, one skill and one
free prompt:

```
minimal-corpus/
  corpus.yaml
  AGENTS.md
  skills/
    summarize/
      SKILL.md
  cases/
    case_demo/
      timestep-1/
        pages/
          page_0001.md
        prompts.yaml
      timestep-2/
        pages/
          page_0001.md            # byte-identical to timestep-1's page_0001.md
          page_0002.md
        prompts.yaml
```

`corpus.yaml`:

```yaml
name: minimal-corpus
owner: gsj-staging
forgejo:
  base_url: http://172.28.9.10:3000
git:
  name: gsj-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"
sandbox_image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3
eval_case_ids: []
```

`cases/case_demo/timestep-1/prompts.yaml`:

```yaml
prompts:
  - {id: "skill:summarize", source: skill, name: summarize}
```

`cases/case_demo/timestep-2/prompts.yaml`:

```yaml
prompts:
  - {id: "skill:summarize", source: skill, name: summarize}
  - {id: "free:parties", source: free,
     text: "Which parties are named so far? Cite pages."}
```

This produces one repo `case_demo` (branches `main` == `timestep-2`
content, `timestep-1`, `timestep-2`) and a three-row task table:
`(case_demo, 1, skill:summarize)`, `(case_demo, 2, skill:summarize)`,
`(case_demo, 2, free:parties)` — all `train`.

## Naming rules (reference)

| thing | rule |
|---|---|
| `<case_id>` | `^[a-z0-9][a-z0-9_-]*$` (it becomes a repo name) |
| timestep directory | `timestep-<T>`, T a positive integer, no leading zeros |
| page file | `page_<NNNN>.md`, 4-digit zero-padded, `.md` |
| skill name / free slug | letters, digits, `._-`; must start alphanumeric |
| every text file | UTF-8, no exceptions |

Strictness of the tree: under `cases/<case_id>/` only `case.yaml` and
`timestep-<T>/` directories are allowed; under a timestep directory only
`pages/` and `prompts.yaml`; under `pages/` only page files. Anything else
is a validation error — a misspelled `timestep_12/` must fail loudly, not
be silently skipped.

## Checklist before you hand a corpus over

- [ ] `validate` passes with zero FAILs.
- [ ] Every timestep directory is the complete case at that cutoff (rule 1).
- [ ] Page numbers are absolute and 4-digit (rule 2).
- [ ] After any page edit: the edit is applied to every timestep that
      contains the page (rule 3), and `validate` was re-run.
- [ ] Every skill referenced by any `prompts.yaml` has its card under
      `skills/` (rule 4).
- [ ] `eval_case_ids` lists exactly the held-out cases.
- [ ] No credentials anywhere in the tree.
