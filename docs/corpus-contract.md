# The corpus source-directory contract (v3, CP-88 / ADR-0038 — court decisions as corpus data; v2: CP-14 / ADR-0015; taskbank as built: CP-24 / ADR-0022; manifest slimmed + `scaffold`: CP-71; v1: the predecessor's CP-33 / ADR-0046)

**Audience: the data-prep team.** This document is self-contained — you do
not need to know anything else about this repository. You produce one
directory tree in the shape below; the ingestion pipeline
(`estate/corpus/ingest_corpus.py`) turns it into git case repositories, a search
index (the case pages and, since v3, the court decisions the corpus may
carry), and a task table. You never edit the pipeline, and the pipeline
never edits your tree.

The pipeline is strict on purpose: **everything it can check, it checks
before anything is uploaded**, and every failure names the exact file and
rule. A tree that passes `validate` will scaffold, index, and verify
without surprises.

**You do not have to start from a blank directory.**
`estate/estate.py scaffold --out <dir>` (from an installed wheel:
`python -m gsj_rollout.estate scaffold --out <dir>`, wheels from 0.1.6 —
published wheels ≤ 0.1.5 predate the `scaffold` verb, so there run it
from a checkout) writes an annotated
starting tree in exactly the shape below — one example case, one timestep,
one page, both prompt forms — that passes `validate` unmodified; every
file it writes says what it is and what to change. Edit, `validate`, `up`.

```
<corpus-root>/
  corpus.yaml                     # corpus-level configuration (reference below)
  AGENTS.md                       # the agent instructions, corpus-level
  skills/<name>/SKILL.md          # skill cards, corpus-level (copied into every repo)
  decisions/                      # OPTIONAL (v3): court decisions, one rii-dok v1 XML file each,
    jb-<doknr>.xml                #   named exactly as rechtsprechung-im-internet.de publishes them
    README.md                     #   optional (the scaffold's); ignored — "Decisions" below
  train/                          # the training split
    cases/
      <case_id>/                  # e.g. case_0007 — becomes the repo name
        case.yaml                 # OPTIONAL per-case metadata (title, notes)
        timestep-<T>/             # T = integer page cutoff, unpadded (timestep-12)
          pages/page_<NNNN>.md    # ABSOLUTE page numbering, 4-digit, exactly 1..T
          prompts.yaml            # THIS timestep's prompts (reference below)
  eval/                           # the held-out split — same shape inside
    cases/
      <case_id>/…
```

**Where a case sits IS its split.** A case under `train/cases/` trains; a
case under `eval/cases/` is held out for evaluation — all of its
timesteps and prompts. The split is per case, never per timestep, and
there is no manifest key for it: the directory is the single source of
truth (v1's `eval_case_ids` is retired; see the migration note at the
end). The corpus-level files stay at the root, above the split — they are
shared by both. Either split directory may be absent, or present with an
empty `cases/` — both mean "this split has no cases", and an
everything-trains corpus is valid either way (the migration recipe below
produces the empty-`eval/cases/` form; you may `rmdir` it if you prefer).
At least one case must exist somewhere, and a split, when present, must
be a *directory* — a stray file named `train` or `eval` is a validation
error, not an empty split.

There are exactly two splits, named `train` and `eval`. A third directory
(say `test/`) is a validation error, not a feature — adding a split is a
contract change that needs its own ADR.

Generated files the pipeline writes into `<corpus-root>` (never write these
yourself): `corpus.lock.json`, `taskbank.parquet`, and — only when
`decisions/` holds decisions — `decisions.lock.json`.

## The five hard invariants

These are the rules a folder tree cannot enforce by shape alone. The
validator enforces all five; violating any one is a hard failure and
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
  - {source: skill, name: tatbestand}
  - {source: free,
     text: "Which parties are named so far? Cite pages."}
```

- `source: skill` — a reference to a skill card. `name` must resolve to
  `<corpus-root>/skills/<name>/SKILL.md`. The card's *text* is resolved into the generated task
  table at build time (the `taskbank` phase copies the corpus-level
  card's bytes into every row that references it — ADR-0022; v1 deferred
  this resolution to episode runtime). Practical consequences for you:
  **after editing a card, re-run `taskbank`** — `verify` fails a table
  whose card text no longer matches the tree — and tell the
  rollout-server operator: an edited or new card also changes the hash
  the rollout side verifies episodes against, and until *their* approved
  set is re-derived, every episode on the new card will be rejected at
  trace validation. The pipeline cannot do that step for you; it is
  deliberately unaware of the rollout side's pins.
- `source: free` — a verbatim prompt. `text` is the exact user message
  (stored byte-for-byte).
- **`id` is optional bookkeeping** (since CP-71 — the pipeline generates
  what it can generate). Absent, a skill entry's id is `skill:<name>` and
  a free entry's is `free:<first 12 hex of the text's sha256>` — stable
  under reordering and insertion, moved only by an edit to the text
  itself. The id is the third element of the task table's row key and its
  sort key, so an id-less free row *moves* when its text is edited;
  supply `id: "free:<slug>"` (slug: letters, digits, `._-`) when you want
  an id that survives text edits. A skill entry's explicit id must be
  exactly `skill:<name>` (anything else is an error, not an alias).
- Duplicate ids **within one timestep** = error — and two id-less entries
  with identical content collide at the generated id (the failure says
  the id was generated, so you are not hunting for an `id:` key the file
  does not contain). The same id at different timesteps is normal (the
  same question asked as the case grows).
- An empty or absent `prompts.yaml` is **legal**: that timestep produces
  no task rows. The case branch is still built and indexed — it just
  isn't asked anything (yet).
- No other keys are allowed in an entry; unknown keys are errors.

Every `(case, timestep, prompt)` triple becomes exactly one row of the
generated task table.

### 5. One case, one split

A `case_id` may appear under `train/cases/` **or** `eval/cases/`, never
both. Two directories with the same name in different splits are two
claims about the same case, and the validator refuses to pick one:

> `case '<case_id>' present under both train/cases/ and eval/cases/ — a
> case belongs to exactly one split (ADR-0015); remove one`

Moving a case between splits is legal at any time *before* upload; after
an upload it additionally requires re-running `scaffold` so the freeze
record (`corpus.lock.json`) states the new split — `verify` fails on a
tree whose splits disagree with the lock.

## Decisions — court decisions as corpus data (v3, CP-88 / ADR-0038)

*Published in library 0.1.9 (CP-91), from CP-88. `scaffold` writes
`decisions/` and its README; `validate` admits the drop and `up` locks and
mounts it by default. On historical wheel 0.1.8, `validate` refuses that
root entry: keep the drop beside the corpus and use `--decisions-dir`, or
upgrade. A corpus without `decisions/` behaves as before.*

A corpus may carry the court decisions its retrieval service serves
beside the case pages: `<corpus-root>/decisions/`, one file per decision
in the rii-dok v1 XML that rechtsprechung-im-internet.de publishes, named
`jb-<doknr>.xml`. The format and every rule are the library's
`docs/decisions-surface.md` (surface version 1): §2 the file, §3–§4 the
unit rule (a decision is served by Randnummer — its numbered paragraphs —
or, for a section without numbering, as one section unit; the service
calls that "level 2"), §9 the citation grammar your `AGENTS.md` may teach
(`dec:<doknr>:rn:<N>`, beside `page:N`; the clause is §9.5). The
directory is OPTIONAL, and the split is not involved: decisions are
corpus-level, above `train/` and `eval/`, and every episode's retrieval
service serves them whole — a page cutoff scopes the case, never the
precedent (the `search_decisions` tool is cutoff-exempt by design).

**What `validate` refuses** — every failure names the file and the rule
(spec §2.2, plus §2.1's element sequence):

- the file does not parse as XML;
- the root element is not `dokument`;
- the root does not carry the DTD's 26 elements, in order (`doknr` …
  `accessRights`) — stricter than the retrieval service's own parser,
  which reads a file with a missing or misplaced element; the lock claims
  the drop is rii-dok v1 as measured, so the tree is held to the measured
  shape;
- `doknr` does not match `[A-Z]{4}[0-9]{9}` (`KORE…` / `JURE…`) or is not
  the filename stem after `jb-` (uniqueness follows: two files cannot
  share one stem in a flat directory — the validator keeps a duplicate
  check as defence in depth);
- `entsch-datum` is not eight ASCII digits;
- `gertyp` or `doktyp` is empty;
- anything in `decisions/` that is not a `jb-<doknr>.xml` file or the
  optional `README.md`: a subdirectory, a misnamed `.xml`, a backup file,
  a dot-entry such as a Finder's `.DS_Store` — the directory is flat and
  strict, like everything below the root (dot-entries are ignored at the
  root only), so clean a folder that was handled in a file manager before
  moving it in; an unreadable directory, or a file nested deeper than the
  parser walks, is refused the same way, never a traceback.

One bad file refuses the tree and nothing is uploaded, the way one bad
page does: a training corpus must be exactly what its lock says. The
retrieval service's own posture is the other one (spec §2.2: it skips a
non-conforming file and serves the rest), so on a tree that passes
`validate` the two keep the same files and compute the same hash.

**What `validate` reports without refusing** — spec §2.3's anomalies,
one PASS row per occurrence naming the file: a duplicated Randnummer
number — a restart of the numbering included (two units then share an
`rn`, and a citation to it is ambiguous); numbering that is not
contiguous `1..K` without any duplicate (a gap, a start at 2 or 3) — the
two numbering kinds are exclusive per file and count once per file; an
anchored paragraph with no text (the unit is not produced); an
`<a name="rd_">` with no digits (not an anchor); text outside any row
(not indexed); a reasoning section with text and no anchors (one section
unit); a title and nothing else — these five count once per occurrence.
Read those rows: they do not fail the tree, but a duplicated Randnummer
is a citation your graders cannot ground. The counts per kind go into
the lock.

**Empty is legal.** A `decisions/` holding no `.xml` file (the scaffold
writes one, with a README saying what goes in it) means "this corpus
carries no decisions": no lock is written and the estate serves the
library's built-in placeholder set of 30 synthetic decisions. A corpus
with no `decisions/` at all behaves exactly as under v2 (its `verify`
table gains no row).

**`decisions.lock.json`** — written by the `scaffold` phase beside
`corpus.lock.json` when the directory holds decisions, removed by
`scaffold` when they are gone. A corpus without decisions keeps its
`corpus.lock.json` byte-identical to v2's: no key is added there, and
the case repos' commit SHAs do not depend on the drop. The file as written (keys sorted, two-space indent), for the demo
repo's thirty synthetic decisions:

```json
{
  "_comment": ["Generated by ingest_corpus.py (corpus-contract v3, CP-88 / ADR-0038) — …"],
  "anomalies": {},
  "dates": {"max": "2024-11-19", "min": "2009-05-19"},
  "ecli": 16,
  "files": 30,
  "files_with_anomalies": 0,
  "randnummer_units": 244,
  "section_units": 69,
  "sha256": "b414c6709a5b7d0daf4505d2ed5bdd5fcadf325e5401e0dd34ae9b76d13eaaa4",
  "surface_version": 1,
  "units": 313
}
```

`_comment` is informational and ignored by `verify`. `sha256` is the
drop's content hash: for each `jb-<doknr>.xml` in ascending filename
order, feed the line `<filename>` + newline + `<sha256 of the file's
bytes, lowercase hex>` + newline into one sha256 — the value the retrieval
service computes for the same directory and serves as `index_commit` on
every decisions hit and as `/health.decisions_drop.sha256`; lock and
service agree by construction. `units` / `randnummer_units` /
`section_units` are the unit rule's census (spec §3–§4): the pipeline
carries a port of the service's parser, pinned by its suite to the
conformance fixture unit for unit and to the service's own module, so
the number the lock records is the number the service serves. `ecli`
counts the files carrying an ECLI (absent on decisions before 2016);
`dates` is the range of `entsch-datum`; `anomalies` maps a §2.3 kind
(`duplicate_randnummer`, `non_contiguous_randnummer`,
`randnummer_without_text`, `non_anchor_rd_name`, `text_outside_rows`,
`anchorless_reasoning_section`, `title_only`) to its occurrences.
**No per-file rows**: the lock is a fixity record and a census, not an
index — CP-76 priced per-file rows at about 1 MB for the published drop,
and nothing downstream reads them. Commit it with the corpus, like
`corpus.lock.json`.

**What `verify` checks**: the tree against the lock (a decision edited
since `scaffold` fails, naming the changed hash and the phase to re-run;
a missing or a stale lock fails naming `scaffold`), and the lock against
what the service serves (`/health.decisions_drop`'s sha256, file count
and unit count must equal the lock's; a service serving the synthetic 30
beside a corpus that carries decisions fails). A corpus without
decisions skips both and says so; a service serving a drop from outside
such a corpus (the estate's `--decisions-dir`, below) passes with a row
saying whose drop it is.

**The estate.** `estate.py up` mounts `<corpus>/decisions` read-only into
the retrieval service by default when it holds decisions — no flag — and
the bring-up's retrieval-config review names the source.
`--decisions-dir <dir>` remains the override for a drop kept outside a
corpus (the CP-79 route: recorded by the run, kept on a re-run, cleared
with `--decisions-dir ''`). A corpus `decisions/` AND a `--decisions-dir`
— given now, or recorded by an earlier `up` of the same run — is a
refusal that names both, says which wins (the corpus's, under this
contract) and how to resolve it; never a silent precedence. A drop that
arrives by the flag is not the corpus's data: it is not locked here and a
hand-over of the corpus does not carry it — move it inside
(`mv <corpus>-decisions <corpus>/decisions`, then `validate`) to make it
corpus data.

**Editing the decisions of a standing estate.** Re-run `estate.py up`:
its scaffold phase re-locks the changed drop, its ingest phase asks the
service to re-index and the service — whose fingerprint sees the drop's
bytes — re-embeds the decisions collection alone, keeping every case
collection, and `verify` then passes with the new hash (measured at
CP-88 on the workstation estate: one edited file → `rebuilt
['decisions']` in 22 s, verify PASS; the file restored → the lock back
to its old hash, verify PASS). `up --rebuild` re-embeds everything.
`estate.py update` does not see a drop-only change: it diffs the cases
against the run's lock and reports "nothing to do" when no case moved
(row 73's residue, recorded at CP-88) — use `up` for the drop.

## `corpus.yaml` reference

Three fields. The file describes the CORPUS — its name, who owns its
repos, and the commit identity that makes it reproducible. Everything
about where it runs (the git host, the retrieval service, the harness
image) is the **estate's**, answered at bring-up, and does not belong
here — this file was shaped by a project that only ever had one corpus,
and CP-71 unpicked that.

```yaml
# The corpus's name (letters, digits, . _ -). It becomes the DEFAULT RUN
# NAME when it fits one (a run name is lowercase letters, digits, - and
# _; a name with capitals or dots needs --name at `up`), and the run
# name prefixes everything the bring-up creates: the containers
# gsj-<name>-forgejo / gsj-<name>-mcp, the docker network gsj-<name>-net,
# and the run directory runs/<name>/ — name: my-corpus yields a container
# called gsj-my-corpus-forgejo. Yours to choose; you will read it in
# `docker ps` for as long as the estate stands.
name: my-corpus

# The git-host account that owns one repository per case — any USABLE
# Forgejo username (the rule is below; the old gsj-staging|gsj-prod
# allowlist is gone since CP-71). The credential environment variables
# are NAMED after it (GSJ_FORGEJO_TOKEN_<OWNER>, uppercased, '-' -> '_'),
# and it appears in the clone URL every episode's sandbox receives:
# <base_url>/<owner>/<case_id>.git. Change it and the variables change
# with it.
owner: my-owner

# DO NOT CHANGE these three, and do not update the date when you edit the
# corpus. A commit SHA is a function of content plus author plus date, so
# pinning all three makes the case repos byte-reproducible: re-running
# the pipeline on an unchanged tree converges to identical commit SHAs on
# every branch — which is what makes the lock's sixteen recorded SHAs
# mean anything (any SHA change is a real content change, never noise).
git:
  name: gsj-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"
```

Three fields older corpora carry here are **deprecated** (warned, never a
failure) — each was the estate's all along:

- `forgejo.base_url` — the git host is where the corpus is *served*, not
  what it *is*. `estate.py up` answers it (and always overrode this
  field with a transport override anyway); the standalone pipeline takes
  `--base-url`. Still honored when present, as the canonical URL the lock
  records.
- `mcp.url_base` — the retrieval service, likewise: `up` creates or
  adopts one; the standalone pipeline takes `--mcp-url`. Still honored;
  a corpus naming neither simply skips the `ingest` phase.
- `sandbox_image` — **ignored** when present: a corpus is not bound to a
  runtime. The task rows take the estate's value — `up`'s
  `--sandbox-image` answer, which is also what it writes into
  `rollout.yaml`'s `runtime.image` (standalone: the pipeline's
  `--sandbox-image`, default the published harness image) — so
  `submit --from-bank`'s row-vs-config guard keeps meaning what it meant:
  the image the bank was *built for*.

**There is no split key.** v1's `eval_case_ids` is retired and the
validator *rejects* a manifest that still carries it (migration note
below) — the split lives in the tree, nowhere else.

## The owner — what it is, and what a valid one looks like

The owner is the git-host account under which one repository per case
lives; two estates differ by exactly this value plus one credential in
the environment. Until CP-71 the validator allowlisted two names —
`gsj-staging` and `gsj-prod`, the reference estates' pair, still the
values our own estates use:

| | staging | prod |
|---|---|---|
| `owner` in corpus.yaml | `gsj-staging` | `gsj-prod` |
| push credential (env var) | `GSJ_FORGEJO_TOKEN_GSJ_STAGING` | `GSJ_FORGEJO_TOKEN_GSJ_PROD` |
| read credential (env var, optional — verify's clone-back) | `GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING` | `GSJ_FORGEJO_READ_TOKEN_GSJ_PROD` |

**Any usable Forgejo username is now a valid owner.** The check is
Forgejo v16's own rule (`modules/validation/helpers.go`,
`models/user/user.go`), restricted to dot-free names because of the
derivation below — a refusal names the exact clause broken:

- starts with a letter or digit; then only letters, digits, `-`, `_`
  (Forgejo would also accept `.`, but see the derivation);
- no consecutive and no trailing `-`/`_`;
- at most 40 characters;
- not a name Forgejo reserves for its own routes (`admin`, `api`,
  `user`, `org`, `repo`, `ghost`, … — case-insensitively).

Forgejo's API answers HTTP 422 for the same values (`invalid username`,
`name is reserved [name: …]`); the validator refuses them at `validate`,
before anything is pushed.

The env var names are derived from the owner: `GSJ_FORGEJO_TOKEN_` /
`GSJ_FORGEJO_READ_TOKEN_` + the owner uppercased with `-` → `_` — which
is why the owner may not contain `.`: only `-` is mapped, and a dotted
owner would name an invalid environment variable.
Credentials are **never** written into `corpus.yaml` or any other file —
the pipeline reads the named environment variables and refuses to run
scaffold without the push one. The push token authorizes *pushes*.
**[CP-56] An estate may close anonymous read** (Forgejo
`REQUIRE_SIGNIN_VIEW`) to stop a sandbox agent re-cloning past its cutoff;
the rollout side then presents a read-scoped token
(`estate.clone_credential_env`). **[CP-58]** `verify`'s clone-back presents
the same read token when its variable is exported and reads anonymously
when it is not (an estate requiring sign-in then fails the clone with a
finding naming the variable); the MCP index build presents it through
`source.auth_token_env`. **[CP-59]** `scaffold`'s post-push read-back
(the `ls-remote` convergence check) presents the same read token, so a
fresh or wiped closed estate scaffolds as is; anonymous against an estate
requiring sign-in, it fails with a message naming the variable (the push
itself succeeded, the lock is not written). No reader is anonymous.

If `mcp.url_base` is set, re-indexing additionally requires
`GSJ_MCP_TOKEN_SECRET` in the environment (the retrieval service's shared
admin secret — ask the estate operator).

## What the pipeline produces from your tree

You do not have to act on this section; it is here so the transformation
is never a surprise.

Per case, one git repository named `<case_id>` under `owner` — **the repo
is split-agnostic**: its name is `<case_id>`, never `train/<case_id>`,
and nothing inside it differs by split (an episode's checkout must not
reveal whether its case is held out). Only `corpus.lock.json` records the
split. Each repo contains:

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
Because the repo is split-agnostic, moving a case between splits changes
**no** commit SHA — only the lock.

The pipeline also writes, into `<corpus-root>`:

- `corpus.lock.json` — the record of what is live: per case the **split**
  (`train` | `eval`), and per branch the commit SHA, the page census, and
  the prompt ids; plus the task table's row count and sha256. Commit it
  with the corpus; it is the freeze record downstream consumers pin
  against.
- `decisions.lock.json` (v3, only when `decisions/` holds decisions) —
  the drop's content hash and census, no per-file rows ("Decisions"
  above). Commit it with the corpus.
- `taskbank.parquet` — the task table (ADR-0022): one row per (case,
  timestep, prompt), flat columns `case_id`, `timestep`, `prompt_id`,
  `split` (`train` | `eval`, taken from the case's directory —
  case-level, so every row of a case shares it), `prompt_source`
  (`free` | `skill:<name>`), `prompt_text` (free rows: your verbatim
  text; null on skill rows), `skill_card_text` (skill rows: the resolved
  `skills/<name>/SKILL.md` bytes; null on free rows), and
  `sandbox_image` — the harness image of the estate that built the bank
  (the `--sandbox-image` value, not the corpus's; `submit --from-bank`
  compares it against the running config's `runtime.image` and refuses a
  mismatch). Rows are sorted by `(case_id, timestep, prompt_id)`
  and the file rebuilds byte-identically from an unchanged tree. A
  consumer submits a row as-is — every column is either the triple or a
  submit-path argument.

## Running the pipeline

The estate operator's one-command bring-up, `estate/estate.py up`, runs
the five phases below for you against a git host and retrieval service it
creates or adopts, and writes the rollout server's config beside the
table — this section is the pipeline on its own.

```bash
estate/estate.py validate --corpus <corpus-root>                        # check the tree
python estate/corpus/ingest_corpus.py all      --corpus <corpus-root>   # the full run
```

(`validate` and `ingest` are estate-tool verbs since CP-72 — from a wheel,
`python -m gsj_rollout.estate validate|ingest`. The other phases keep the
pipeline's own command line, which still works for every phase but prints
a deprecation notice; retained through 0.1.11; removal remains eligible from 0.1.8, not scheduled.)

`all` runs the five phases in order and stops at the first failure:

| phase | what it does | what it guarantees |
|---|---|---|
| `validate` | checks this contract against your tree — the cases and, since v3, `decisions/` (refusals named per file; anomalies reported) | nothing is uploaded unless the whole tree passes |
| `scaffold` | creates/updates the repos, pushes all branches | idempotent; deterministic SHAs; writes `corpus.lock.json` (incl. each case's split) and, since v3, `decisions.lock.json` (the drop's hash and census) |
| `ingest` | tells the retrieval service to (re)index; waits for ready | search serves exactly the pushed corpus |
| `taskbank` | writes `taskbank.parquet`; records its sha in the lock | one row per (case, timestep, prompt), split from the directory (via the lock — a case moved between splits must be re-scaffolded first); needs `pyarrow` (`estate/corpus/requirements.txt`) |
| `verify` | clones everything **back from the git host**, re-reads the parquet **row by row**, queries the service | what is *live* matches your tree and the lock, byte-for-byte — including each case's split, and the task table's rows: counts, every triple exactly once and set-equal to your tree, split/text/image columns re-derived from the tree; since v3 the decisions: the tree against `decisions.lock.json`, and the lock against the drop the service serves |

`validate` checks the input; `verify` checks reality — the second half is
what tells you an upload actually landed as intended, so never skip it.
Both print a findings table with one line per case and timestep — `case`,
`split`, `where`, `result`, and the specific rule broken with the file
named. The exit code is non-zero if anything failed, and no later phase
runs.

The estate's three values ride flags, not the manifest (CP-71):
`--base-url <url>` names the git host — required for
`scaffold`/`verify`/`all` on a corpus without the deprecated
`forgejo.base_url` (`--dry-run` excepted: it pushes nothing; on a corpus
that carries the key, a transport override — the lock keeps the
canonical URL); `--mcp-url <url>` names the retrieval
service; `--sandbox-image <ref>` stamps the task rows (default: the
published harness image — pass the SAME value to `taskbank` and `verify`,
which re-derives it). `estate.py up` supplies all three for you.

Useful flags: `--only <case_id> ...` (limit validate/scaffold/verify's
repo work to some cases — the task table is corpus-wide, so the
`taskbank` phase is skipped and your committed table is left alone;
refresh it afterwards with a plain `taskbank` run), `--dry-run` (validate
+ build everything locally, push nothing, write nothing), `--skip-ingest`
(no retrieval service in reach), `--owner-override <owner>` (push the same
tree under a different account — e.g. a rehearsal under `gsj-staging` of a
tree whose `corpus.yaml` says `gsj-prod`).

A corpus that names no retrieval service (no `--mcp-url`, no deprecated
`mcp.url_base`) skips the `ingest` phase (and `verify`'s search-service
check) with a printed note — that is the supported "no retrieval
service" configuration; `--skip-ingest` is the same skip when one *is*
named.

## What the split means downstream (and what it does not)

Honesty over comfort: the split is a **label, carried end to end and
enforced nowhere in this pipeline**. It travels tree →
`corpus.lock.json` → the task table row → the task request's metadata →
the collected trace, so every consumer can see it — and the *trainer*
owns not training on eval-split traces. The rollout side rejects only a
malformed label (a split value other than `train`/`eval` on a trace
fails validation); it does not, and cannot, stop anyone from training on
a correctly-labeled eval trace. If you need a wall rather than a label,
build it trainer-side.

## Worked minimal example

A complete, valid corpus with two cases — one training, one held out —
one skill and one free prompt:

```
minimal-corpus/
  corpus.yaml
  AGENTS.md
  skills/
    summarize/
      SKILL.md
  train/
    cases/
      case_demo/
        timestep-1/
          pages/
            page_0001.md
          prompts.yaml
        timestep-2/
          pages/
            page_0001.md          # byte-identical to timestep-1's page_0001.md
            page_0002.md
          prompts.yaml
  eval/
    cases/
      case_holdout/
        timestep-2/
          pages/
            page_0001.md
            page_0002.md
          prompts.yaml
```

`corpus.yaml`:

```yaml
name: minimal-corpus
owner: gsj-staging
git:
  name: gsj-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"
```

`train/cases/case_demo/timestep-1/prompts.yaml`:

```yaml
prompts:
  - {source: skill, name: summarize}
```

`train/cases/case_demo/timestep-2/prompts.yaml` (the free prompt keeps an
explicit id here so its row key survives edits to the text — id-less
would work too, as `free:<text-hash>`):

```yaml
prompts:
  - {source: skill, name: summarize}
  - {id: "free:parties", source: free,
     text: "Which parties are named so far? Cite pages."}
```

`eval/cases/case_holdout/timestep-2/prompts.yaml`:

```yaml
prompts:
  - {source: skill, name: summarize}
```

This produces two repos and a four-row task table:
`(case_demo, 1, skill:summarize)`, `(case_demo, 2, skill:summarize)`,
`(case_demo, 2, free:parties)` — all `train` — and
`(case_holdout, 2, skill:summarize)` — `eval`.

## Bringing your own corpus

Everything above holds for any corpus. What this section adds is what
*changes* when the corpus is yours rather than the reference one — in
one place, honestly (CP-70 item 4).

**Start with `scaffold`** (`estate/estate.py scaffold --out <dir>`;
wheel: `python -m gsj_rollout.estate scaffold`) rather than a blank
directory — the tree it writes validates as written and each file says
what to change.

**Your `AGENTS.md` and skill cards change what the rollout side pins.**
The trace validators verify every episode against an approved set: G1 is
the sha256 of the resolved skill-card bytes, G2 the sha256 of the system
prompt your `AGENTS.md` becomes. The shipped pins approve the REFERENCE
corpus's values, so on your corpus **every episode will quarantine until
the estate's pins are re-derived and named**:

- `estate.py up` already tells you: its pins phase warns with the exact
  cards the in-force approved set lacks. It deliberately does not write
  pins.
- The library owns the walk, as a page a stranger can follow:
  [`docs/guide/bring-your-own.md#your-pins`](guide/bring-your-own.md#your-pins)
  — one episode against the reference pins, **inspect** the quarantined
  body, derive every approved value from what actually ran (G1 = sha256
  of each of your `skills/<name>/SKILL.md` files' raw bytes; G2 = the
  wire system prompt as UTF-8 bytes, your `AGENTS.md` found in it exactly
  once), `GSJ_PINS_PATH` pointed at the file for the receiver and the
  trainer both (law 6: same document, both legs), restart, one accepted
  episode. Still no one-command form in the library, deliberately: the
  inspection step is the point. The demo repo's `bootstrap.py`
  (`derive_pins`) is the one-command form for the reference-model case
  (G2 by `AGENTS.md` byte-substitution on the wheel's packaged capture).
  `pins/derive_pins.py` in the checkout re-**verifies** the reference
  estate's own set; it does not derive yours and does not ship on the
  wheel.

**Your decisions are corpus data too (v3).** A `decisions/` of rii-dok v1
files travels with the corpus, is locked with it and is what the estate
serves — see "Decisions" above. Teaching the agent to cite them is your
`AGENTS.md`'s job (the §9.5 clause of `docs/decisions-surface.md`), and,
like any `AGENTS.md` edit, it moves G2 — re-derive the pins as described
above. What no measurement yet shows is a policy USING the citation
grammar under a reward (the library's wishlist row 70): the clause alone
produced no citation from the reference model at CP-81.

**Your timesteps must correspond to something real.** A timestep is a
cutoff of one growing document — the contract checks the *shape* of that
claim (prefix consistency, absolute numbering) but cannot check that
page 7 truly precedes page 8 in the world. Constructing honest cutoffs
from your source material is upstream of this system, and it is where
the value of the corpus is decided.

**The retrieval defaults were sized for the synthetic corpus.** The
embedder (`sentence-transformers/all-MiniLM-L6-v2`) and the chunk window
(220 tokens, overlap 40) are `up`'s defaults because they fit the
reference pages; nothing re-derives them for your material. `up` takes
`--embedding-model`/`--embedding-revision` (a non-default model is
mounted from your HF cache) and `--chunk-max-tokens`/`--chunk-overlap`
— re-embedding an existing store is an explicit `--rebuild`. Since
CP-73 the effective retrieval config is printed for review **before**
your corpus is embedded under it, each setting priced by what a later
change costs (the model: a refusal until `--rebuild`; the chunk window:
a corpus-wide re-embed; the search defaults: a config edit), and
`--mcp-config <yaml>` supplies the operator sections (`embedding`,
`chunking`, `search`, `decisions`) from a file for scripted runs.

**Editing a corpus that is already standing.** `estate.py update
--name <run>` (CP-73) syncs edits: it diffs your tree against the run's
lock, reports per case what moved — an edited page (edit it in *every*
timestep that holds it, invariant 3), a new timestep, a new case, a
prompt change — and what each costs downstream, then pushes only the
changed repos, rebuilds the bank, triggers one if-stale reindex and
re-verifies. An edited `AGENTS.md` or skill card is attributed against
the live repo's bytes and the pins consequence said out loud: G1/G2
move, episodes on the affected cards quarantine until the pins are
re-derived. It refuses a changed `git:` identity (every SHA moves —
that is a new corpus, stand it up as its own run) and never re-embeds
by force.

**What is proven, and what is not.** Proven (CP-71, a Mac estate): a
scaffolded corpus validates unmodified, ingests, banks and verifies
end-to-end through `up`. Proven since (2026-09-06, a stranger from
`pip install` alone, no demo, no examples): the bring-your-own path
end to end — this library's own scaffold as the foreign corpus,
`qwen3.6-27b` as the foreign model, the pins re-derived from one
quarantined episode, one accepted episode, findings `[]`, re-verified
in a separate process; it caught exactly at the pins step, as this
paragraph predicted, and the walk the stranger assembled is now the
page above (re-walked at CP-92 on a workstation estate). NOT proven
still: a training run consuming such episodes. Expect to be the first
there.

## Naming rules (reference)

| thing | rule |
|---|---|
| split directory | exactly `train` or `eval`, at the corpus root; no third |
| `owner` | a usable Forgejo username, dot-free (the rule, with reasons: "The owner" above) |
| `<case_id>` | `^[a-z0-9][a-z0-9_-]*$` (it becomes a repo name) |
| timestep directory | `timestep-<T>`, T a positive integer, no leading zeros |
| page file | `page_<NNNN>.md`, 4-digit zero-padded, `.md` |
| skill name / free slug | letters, digits, `._-`; must start alphanumeric |
| decision file (v3) | `jb-<doknr>.xml`, doknr `[A-Z]{4}[0-9]{9}` equal to the stem; `decisions/` is flat, plus an optional `README.md` |
| every text file | UTF-8, no exceptions |

Strictness of the tree: at the corpus root only `corpus.yaml`,
`AGENTS.md`, `skills/`, `train/`, `eval/`, `decisions/` (v3) and the three
generated files are allowed (dot-prefixed entries like `.git` are ignored
**at the root only** — a corpus source tree may itself be a git
repository); under `train/` or `eval/` only `cases/`; under `cases/` only
case directories; under `cases/<case_id>/` only `case.yaml` and
`timestep-<T>/` directories; under a timestep directory only `pages/` and
`prompts.yaml`; under `pages/` only page files; under `decisions/` only
`jb-<doknr>.xml` files and an optional `README.md`. Anything else is a
validation error — a misspelled `timestep_12/`, a stray `test/` split or
a `decisions/2024/` subdirectory must fail loudly, not be silently
skipped.

`AGENTS.md` and `skills/` are **required** at the root even for a corpus
that uses only free prompts (`skills/` may then be empty). Under
`skills/` only `<name>/` directories are allowed, and each must contain a
non-empty `SKILL.md`. One honest exception to the strictness doctrine:
files *beside* `SKILL.md` inside a `skills/<name>/` directory are neither
validated nor copied — **only `SKILL.md` travels into the case repos** —
so do not keep supporting material there expecting it to ship.

## Migrating a v1 corpus (pre-CP-14 shape)

A v1 tree keeps `cases/` at the corpus root and names its held-out cases
in `corpus.yaml`'s `eval_case_ids`. The validator **rejects** both — a v1
corpus fails `validate` until migrated; nothing is silently reinterpreted.
What you will see:

- for the root `cases/` directory:
  > `cases/ at the corpus root is the retired pre-split shape (ADR-0015)
  > — move each case under train/cases/ or eval/cases/`
- for the manifest key:
  > `'eval_case_ids' is retired (ADR-0015) — the split is now the
  > directory layout: move each listed case under
  > <corpus-root>/eval/cases/, every other case under
  > <corpus-root>/train/cases/, then delete this key`

The migration is exactly those two messages, performed:

1. `mkdir -p train eval/cases && mv cases train/cases`
2. for each case named in `eval_case_ids`:
   `mv train/cases/<case_id> eval/cases/<case_id>`
3. delete the `eval_case_ids` key from `corpus.yaml`
4. `validate`, then re-run `scaffold` (the lock gains each case's split;
   **no commit SHA changes** — the move touches no page bytes, and the
   repos are split-agnostic), then `verify`.

The split's meaning is unchanged from v1: the same cases are held out,
per case, all their timesteps and prompts. Only where the fact is written
moved.

## Checklist before you hand a corpus over

- [ ] `validate` passes with zero FAILs.
- [ ] Every case sits under exactly one of `train/cases/` or
      `eval/cases/`, and the held-out cases are exactly the ones you mean
      to hold out (rule 5 — the tree is the only place this is written).
- [ ] Every timestep directory is the complete case at that cutoff (rule 1).
- [ ] Page numbers are absolute and 4-digit (rule 2).
- [ ] After any page edit: the edit is applied to every timestep that
      contains the page (rule 3), and `validate` was re-run.
- [ ] Every skill referenced by any `prompts.yaml` has its card under
      `skills/` (rule 4).
- [ ] No `eval_case_ids` key in `corpus.yaml` (retired — the validator
      rejects it).
- [ ] No estate values in `corpus.yaml` — `forgejo:`, `mcp:` and
      `sandbox_image:` are the estate's (deprecated; a corpus still
      carrying them warns, and `sandbox_image` is ignored outright).
- [ ] `decisions/`, if present, holds only `jb-<doknr>.xml` files (and
      the README), every file passes `validate`, and its anomaly rows
      were read (a duplicated Randnummer makes a citation ambiguous).
- [ ] No credentials anywhere in the tree.
