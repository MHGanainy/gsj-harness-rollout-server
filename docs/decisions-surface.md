# The decisions surface — specification, version 1 (CP-78, 2026-09-03)

**Status: specified (CP-78); implemented at level 2 by this repository's
service since CP-79.** `gsj-mcp-service:0.5.0` (`estate/mcp-service/`,
published as `ghcr.io/mhganainy/gsj-mcp-service:0.5.0`) serves a rii-dok v1
drop named by `decisions.path` (since CP-88 the corpus's own `decisions/`
by default — corpus-contract v3, ADR-0038 — or `estate.py up
--decisions-dir` as the override) at level 2
— its parser reproduces the conformance fixture byte for byte and its hits
carry every §7.3 field (`estate/mcp-service/tests/test_decisions.py`, the
§10.2 test); with no drop it serves the synthetic 30 inside the §7
envelope, the hits at level 0 (§7.6). `gsj-next` returns document-level
hits without Randnummern (level 1 once it adopts the field rules; it is not
changed by this document). The conformance fixture in
[`decisions-surface/`](decisions-surface/README.md) is what makes "two
implementations agree" a test rather than a claim.

**Audience.** Two implementers — this repository's MCP service
(`estate/mcp-service/`, the training-time surface) and `gsj-next`'s
(`services/mcp/server.py` + `gsj/search.py`, the production surface the
trained model ships to) — plus the consumers that read hits and citations:
the trainer-side grader, the demo's transcript reader, and the authors of a
corpus's `AGENTS.md`. It is self-contained: nothing here requires reading
the rest of this repository.

**Why a specification.** The model trained in this repository is deployed
against `gsj-next`. Whatever it learns to call, and whatever citation it
learns to write, it will call and write there. A hit shape or a citation
grammar that exists only in training is a hallucination generator in
production. So the surface is written down once, precisely enough that two
independent systems can implement it and be *proven* to agree — and where
one side cannot yet provide a field, the document says what the agent does
instead (§9.3, the degradation rule).

The words MUST, MUST NOT, SHOULD, MAY, REQUIRED and OPTIONAL are RFC
2119's. Numbers in this
document were measured over the 33,979-file rii drop this repository
trains against (the CP-76 census, re-run under this document's rules at
CP-78); they describe that corpus, not a guarantee about future drops.

---

## 0. Where this document lives, and how it is referenced

**One canonical copy, here — `docs/decisions-surface.md` in
`gsj-harness-rollout-server` — with the fixture beside it, versioned by the
`version` in this title and referenced by permalink.** Not a copy in each
repository, not a third repository, not the wheel.

The argument. The document has one writer and two readers. The writer is
this repository: the surface exists because a model is trained here, and
every rule below is grounded in a measurement this repository made. Of the
two readers, one (this repository's service) must implement it now and the
other (`gsj-next`) may implement it later, on its own schedule. A document
copied into both repositories drifts the first time either side edits its
copy — and the drift is invisible exactly where it matters, at the boundary
between training and production. A third, neutral repository would have no
owner and no process (this repository's checkpoint protocol cannot bind a
repository it does not run), and would be one more thing for a reader to
find. Shipping it inside the PyPI wheel would version it by *this* library's
release cadence, which `gsj-next` does not consume, and would make every
wording fix a release.

What makes the pointer safe against drift:

- **A version number.** The `version` in the title is the surface version.
  It moves only on a change an implementation or a consumer can observe (a
  field, a rule, the citation grammar, the fixture's expected output).
  Wording changes do not move it. The change log is §14.
- **A permalink.** A referencing repository names the commit:
  `https://github.com/MHGanainy/gsj-harness-rollout-server/blob/<sha>/docs/decisions-surface.md`,
  and the version it implements. `main` is where the next version is
  drafted; a pin is a SHA.
- **The fixture is copied, the document is not.** `decisions-surface/`
  (six source files and their expected output) is *meant* to be copied
  into an implementation's test tree: the source files are published court
  documents whose bytes are fixed by their publisher, and `expected.json`
  carries the surface version it was generated under (its top-level
  `surface_version` key) beside the script that generated it. A copied
  fixture cannot drift silently — it either passes or it names the
  version it disagrees with.

What `gsj-next` would commit, if and when it adopts (it is not modified by
this checkpoint, and the decision is its operator's): one pointer line
(permalink + version) in its own record, and the fixture directory under
`tests/fixtures/`. Nothing else in this document asks anything of it.

---

## 1. Scope

This document specifies, for the tool `search_decisions` on an MCP server
named `gsj` (rendered `mcp_gsj_search_decisions` by pi):

1. the **source format** an implementation ingests (§2);
2. the **text extraction rule** — how markup becomes text (§3);
3. the **unit** — what one hit is a hit *of* (§4), and its identity (§5);
4. the **embedding split** — the constraints on how a unit becomes vectors,
   none of which reach the wire (§6);
5. the **wire shape** — the request, the response envelope, every hit
   field, its type, and whether it is required, null, or absent (§7);
6. **ranking and aggregation** — best piece per unit, top-k units, whole
   units returned, the default and the clamp on `k` (§8);
7. the **citation grammar** an agent writes from a hit, and the
   **degradation rule** that keeps a citation valid when an implementation
   cannot provide the Randnummer (§9);
8. the **conformance fixture** and what "agree" means (§10).

It does not specify (§11) whole-decision reading, lexical retrieval,
metadata filters, or the embedding model — and it deliberately leaves to
the implementation (§12) the store, the model, the window and the batching,
none of which change what an agent sees.

The four settled decisions this document is written against: **k defaults
to 5**; **the unit is the Randnummer**; **the wire shape is `gsj-next`'s**
(`{query, k, hits, index_commit}`) — this repository adopts it, `gsj-next`
is not changed; and — this repository's training estates only — **an
estate corpus carries a chosen slice of decisions** (thirty that bear on
the corpus's cases — a random thirty of thirty-four thousand would teach
the agent that searching decisions is useless; which thirty is the corpus
author's call and outside this document).

---

## 2. The source format: rii-dok v1

### 2.1 Files

One decision per file, named `jb-<doknr>.xml`, UTF-8, well-formed XML with
the document type declaration

```
<!DOCTYPE dokument SYSTEM "https://www.rechtsprechung-im-internet.de/dtd/v1/rii-dok.dtd">
```

published by Rechtsprechung im Internet (Bundesministerium der Justiz und
für Verbraucherschutz with the Bundesamt für Justiz; technical provision by
juris GmbH). The DTD (juris GmbH, version 1, 2015-11-19) declares the root
`dokument` as a fixed sequence of **26 elements, in this order**:

| # | element | DTD content | measured over 33,979 files |
|---|---|---|---|
| 1 | `doknr` | `#PCDATA` | non-empty 100%; **unique 33,979/33,979**; equals the filename stem after `jb-` 100%; shape `[A-Z]{4}[0-9]{9}` (`KORE` 27,814, `JURE` 6,165) |
| 2 | `ecli` | `#PCDATA` | non-empty **67.2%** (22,831): 0% for 2010–2014, 16% in 2015, ≥ 98% from 2016; all `ECLI:DE:BGH:YYYY:…`, all distinct |
| 3 | `gertyp` | `#PCDATA` | non-empty 100%; one value in this drop (`BGH`) |
| 4 | `gerort` | `#PCDATA` | empty 100% |
| 5 | `spruchkoerper` | `#PCDATA` | non-empty 99.99% (33 distinct non-empty values) |
| 6 | `entsch-datum` | `#PCDATA` | `YYYYMMDD`, valid 100%; 2010–2026 |
| 7 | `aktenzeichen` | `#PCDATA` | non-empty 100%; **not unique**: 1,464 values shared by 3,199 files (max 11); 132 files carry two (`5 StR 623/17 und 5 StR 624/17`) |
| 8 | `doktyp` | `#PCDATA` | non-empty 100%; 14 values (`Beschluss` 22,232, `Urteil` 11,222, `Versäumnisurteil` 262, `EuGH-Vorlage` 198, …) |
| 9 | `norm` | `#PCDATA` | non-empty 79.4%; comma-separated |
| 10 | `vorinstanz` | `ANY` | non-empty 98.2%; `<br/>`-separated lines |
| 11 | `region` | `(abk, long)` | `DEU` / `Bundesrepublik Deutschland` 100% |
| 12 | `mitwirkung` | `#PCDATA` | empty 100% |
| 13 | `titelzeile` | `ANY` | with text 78.9% |
| 14 | `leitsatz` | `ANY` | with text 37.8% |
| 15 | `sonstosatz` | `ANY` | with text 0.1% (45) |
| 16 | `tenor` | `ANY` | with text 99.96% (14 empty) |
| 17 | `tatbestand` | `ANY` | with text 27.6% (always together with 18: the Urteil shape) |
| 18 | `entscheidungsgruende` | `ANY` | with text 27.6% |
| 19 | `gruende` | `ANY` | with text 65.8%; **never non-empty together with 18** (0 files); **6.6% (2,237) have neither 18 nor 19** — their reasoning is in `tenor` |
| 20 | `abwmeinung` | `ANY` | empty 100% |
| 21 | `sonstlt` | `ANY` | with text 0.2% (75: Berichtigungs-/Ergänzungsbeschlüsse) |
| 22 | `identifier` | `#PCDATA` | the rii URL, `docid=jb-<doknr>` 100% |
| 23 | `coverage` | `#PCDATA` | `Deutschland` 100% |
| 24 | `language` | `#PCDATA` | `deutsch` 100% |
| 25 | `publisher` | `#PCDATA` | `BMJV` 100% |
| 26 | `accessRights` | `#PCDATA` | `public` 100% |

Every one of the 33,979 files carries exactly this sequence. The `ANY`
elements hold XHTML 1.0 Transitional; the tags seen in this drop are `a`,
`br`, `dd`, `div`, `dl`, `dt`, `p`, `table`/`tr`/`td`/`th`/`thead`/`tbody`/`tfoot`,
`span`, `strong`, `em`, `sub`, `sup`, `img`, `blockquote`, `ul`/`li`, and
one `nohlj`; 326 `<a href="bild….jpg">` image-viewer links in 188 files
(each wrapping `<br/><span>Abbildung in Originalgröße in neuem Fenster
öffnen</span>`, beside the `<img>` it enlarges). No `<ol>`, no nested
`<dl>` or `<p>`. The DTD
references the XHTML entity set but the corpus uses only three of the
five predefined entities (`&amp;`, `&lt;`, `&gt;`), so a non-validating
parser that does not resolve the external DTD reads every file (stdlib
`ElementTree`: 0 parse errors).

### 2.2 A conforming source file

A source file **conforms** iff: it parses as XML; the root element is
`dokument`; `doknr` matches `[A-Z]{4}[0-9]{9}` — the shape the citation
grammar (§9.1) is written for — and equals the filename stem after
`jb-`; no other file in the drop carries the same `doknr` (given the
stem rule, possible only across directories or on a case-folding
filesystem); `entsch-datum` is eight ASCII digits (`[0-9]{8}`, not a
locale's digit class); `gertyp` and `doktyp` are non-empty. Nothing else
is required: every body section, `ecli`, `norm`, `spruchkoerper` and
`vorinstanz` may be empty. Every rule in §3–§9 is stated for conforming
files, and every file of the drop this document measures conforms.

What an implementation does with a non-conforming file is its own
posture, and the two known implementations differ by design: this
repository's training estate **refuses** it (skipped with its reason
reported; a drop is not aborted for one bad file; of a duplicate pair, the
first in ascending filename order is the one kept), because a training
corpus must be exactly what its lock says; `gsj-next`'s production ingest
**never drops** a decision (its CF-1 rule — a colliding id is
disambiguated with a `__N` suffix, a missing `doknr` falls back to an
Aktenzeichen or file-stem slug, an unparseable date leaves the year
null), because an operator batch must survive one bad document. Both are
conformant, with one obligation on the ingesting side: a hit whose row
came from a non-conforming file MUST NOT carry a `doknr`-shaped
`decision_id` it does not own — a suffixed or slugged id is returned as
it is (§9.1 keeps it out of the citation grammar), and a `date` the file
does not carry is absent.

### 2.3 Anomalies the rule tolerates

The drop is not clean, and the unit rule (§4) is written so that none of
these refuses a file; a validator SHOULD report them:

| anomaly | count (files) | what §4 does |
|---|---|---|
| Randnummer numbering not contiguous `1..K` | 114 of the 31,748 anchored files (0.36%), in overlapping classes: 13 with duplicate numbers (3 of them a restart inside `sonstlt`), 74 with gaps or out-of-order numbers, 27 starting at 2 or 3 | numbers are taken as they stand; a duplicate number yields two units with the same `rn` (§5.4) |
| anchored block with an empty body | 218 blocks | the row opens its unit (§4.2); the unit is produced only if continuation rows give it text — 271 Randnummer units are not produced in this drop: 212 of these 218 (six gain text from a continuation row) plus 59 anchored rows whose only content is a signature table dropped by §3.1 |
| `<a name="rd_"/>` with no digits | 1 block (`jb-KORE202400018.xml`) | not an anchor: the row is unanchored |
| Randnummer text as bare `<div>` text outside any `<dl>` | 69 files (66 in a reasoning section; in 31 of them only a signature or a heading) | not a row: the text is not indexed (§4.6) |
| a reasoning section with text and no anchors | 2 files | one section unit, `rn` null (§4.4) |
| a title and nothing else | 1 file (`jb-KORE517722026.xml`) | one `titelzeile` unit |

---

## 3. Text extraction

Everything an agent reads comes through one function, **`text(e)`**, over
an element `e` of a body section. It is defined so that two implementations
produce the same bytes.

### 3.1 The flow

`text(e)` is the concatenation, in document order, of every text node
under `e` (the element's own text, each descendant's text, and every tail —
the text that follows a child element inside its parent; `e`'s own tail is
not under `e` and belongs to its parent's flow), with three adjustments:

1. **Dropped subtrees.** A `<table>`, an `<img>`, or an `<a>` element
   that carries an `href` attribute (the publisher's image-viewer link,
   UI chrome beside the `<img>` it enlarges) contributes **nothing at
   all** — not its text, not its descendants', and not the boundary
   spaces of rule 2: the element is treated as if it were not there,
   and its *tail* (text after it, inside its parent) joins the parent's
   flow directly. `x<img/>y` reads `xy`; `Rn. 2)<img/>. Da` reads
   `Rn. 2). Da`. Exactly three rows in the drop have an `<img>` glued to
   text on both sides (none a `<table>`), and this reading is the one
   that reads them right (§10.1's fourth file carries one).
2. **Block boundaries.** Every element that is not dropped and not in the
   inline set `{a, em, strong, span, sub, sup}` — `e` itself included —
   contributes one space (U+0020) before its content and one after it.
   So `<p>`, `<br>`, `<div>`, `<dd>`, `<blockquote>`, `<li>` and every
   other element separate words; the six inline elements do not
   (`Abs. 1<sup>a</sup>` reads `Abs. 1a`; `a<br/>b` reads `a b`).
3. **Whitespace normalization.** The result is split on runs of Unicode
   *White_Space* code points and re-joined with single U+0020; nothing
   leads or trails. (White_Space = U+0009–U+000D, U+0020, U+0085, U+00A0,
   U+1680, U+2000–U+200A, U+2028, U+2029, U+202F, U+205F, U+3000 — the
   normative list; an implementation in any language uses exactly these
   code points. Python's `str.split()` implements this set plus
   U+001C–U+001F, which cannot occur in a well-formed XML 1.0 document
   (nor can U+000B or U+000C), so it is a conforming implementation
   there; Java's `Character.isWhitespace` is not — it excludes the
   non-breaking spaces U+00A0, U+2007 and U+202F.) No
   other character is altered: U+00AD (soft hyphen,
   527 occurrences) and U+200B (zero-width space, 58) are kept.

The same normalization applies to every header value carried on a hit
(§7.3): the `#PCDATA` element's text (it has no children) with leading
and trailing White_Space removed and inner runs collapsed; an element that
is missing, empty, or whitespace-only reads as the empty string, which for
`ecli` means "absent" (§5.3). In this drop no header value carries
surrounding whitespace, so "verbatim" and "normalized" coincide.

Measured: the corpus holds 4.26 million U+00A0 (non-breaking spaces) and
6,650 `<br/>` inside a `<p>` with a non-space character on both sides (at
least 8,038 at any depth) — a rule that ignored either would glue words in
an implementation and split them in another.

### 3.2 Why `itertext`, not `.text`

An extraction that reads only an element's own `.text` (as `gsj-next`'s
`_paragraphs` does today) loses the text that follows an inline child and
yields nothing for a paragraph that *starts* with one. Measured over the
drop: 1.11% of characters corpus-wide, **23,212 whole paragraphs, 1,441
entire Randnummern, and 11 whole decisions** — and the loss is
series-dependent: 0.6–1.7% in 2010–2016 files, **5.3–10.5% in the
2018–2026 `KORE6`/`KORE7` files**, whose word-processor export wraps every
paragraph in `<span style="color: rgb(0, 0, 0)">`. The newest law is what
it loses. The third fixture file (§10) is one of the eleven: under `.text`
it ingests as an empty string.

---

## 4. The unit

A **unit** is what a hit returns: either one **Randnummer** (a numbered
paragraph of the reasoning, with the unanchored rows that belong to it) or
one **section** (a body section that carries no numbered paragraphs, whole).

### 4.1 Rows

The nine `ANY` body sections are walked in DTD order: `titelzeile`,
`leitsatz`, `sonstosatz`, `tenor`, `tatbestand`, `entscheidungsgruende`,
`gruende`, `abwmeinung`, `sonstlt`. (`vorinstanz` is also `ANY` but is a
header field, not text; it is not a section.)

A section is the first child element of `dokument` with that name; a
section that is missing (the DTD forbids it; §2.2 does not require it)
has no rows. Within a section, the **rows** are its `<dl>` descendants in
document order that have no `<dl>` ancestor inside the section (nested
`<dl>` do not occur in the drop; the rule is stated for completeness) —
"descendant" throughout §4 means at any depth, and "first" means first in
document order. A row's `<dt>` is its first `dt` child element and its
`<dd>` its first `dd` child (every `<dl>` in the drop has exactly one of
each: 1,768,022 of 1,768,022). The row's **text** is `text(dd)` (§3), or
the empty string when there is no `<dd>` (an anchored row without a
`<dd>` still opens its unit, with empty text); a row without a `<dt>` is
unanchored.

A row is **anchored** iff its `<dt>` has an `<a>` descendant whose `name`
attribute is, in full, `rd_` followed by one or more ASCII digits that
parse to a decimal integer **≥ 1** (the first such `<a>`, if several —
none has several); that integer is the row's **number**. An
implementation MUST match the whole attribute value (no trailing newline,
no surrounding whitespace — `re.fullmatch`, not `re.match`, in Python).
A `name` of `rd_` with no digits, or one whose digits parse to 0, is not
an anchor and the row is unanchored (§2.3's digitless `rd_` is the one
such value in the drop; no anchor carries a leading zero — one that did
would parse to its number, `rd_007` to 7). The drop holds 667,371 `rd_`
attributes, all in a `<dt>`, of which 667,370 are anchors; a `<p>` walk
never sees them, which is why no earlier generation of this pipeline ever
returned a Randnummer.

A row is **indented** iff its `<dd>` has a `<p>` descendant, not inside a
dropped subtree (§3.1; four such `<p>` sit inside tables in the drop and
do not count), whose `style` attribute contains the substring
`margin-left` — any value; the substring test is the whole rule — and
whose `text(p)` (§3: the whole subtree, never the element's own `.text`
alone — 57 tail rows in the drop, a `<span>`-wrapped
`Rechtsmittelbelehrung:` among them, flip between kept and dropped on
that distinction; §10.1's sixth file carries one) is non-empty.
Indentation is the publisher's rendering of quoted material (petitions,
contract clauses, cited passages): `margin-left:<N>pt` on 37,745 rows
between anchors (`36pt` on 28,228 of them; `54pt`, `18pt`, `90pt`, `72pt`,
`108pt`, `162pt` the rest), `margin-left:<N>px !important` on 2,573;
indented rows occur in
every position (168 before a section's first anchor, 480 after its last,
16,721 in anchorless sections). (Text directly inside a `<dd>`,
outside any `<p>` — 91 rows — is ordinary text under the `<dd>` and needs
no rule.)

### 4.2 A section with anchored rows: Randnummer units

Walk the rows in order.

- An **anchored row always opens a Randnummer unit**, whether or not its
  own text is empty: `section` = the section's name, `rn` = the row's
  number, text = the row's text (nothing, if empty). The 278 anchored
  rows whose text is empty (218 with an empty body, 60 whose only content
  is a dropped table) still open their unit, so the rows that follow them
  join *that* unit, not the previous one — 7 of the 278 are filled that
  way, 271 stay empty and are not produced.
- An **unanchored row with non-empty text** joins a unit by position:
  - **before the first anchored row** of the section: it is *prefixed* to
    the first Randnummer unit of the section, in document order, ahead of
    that row's own text (9,439 rows in the drop — almost all a heading
    such as `I.`, plus the handful of opening paragraphs whose anchor the
    publisher lost);
  - **between two anchored rows**: it is *appended* to the open unit (the
    preceding Randnummer) — **every** such row, whether it is an indented
    quotation, the plain paragraph text that resumes after the quotation,
    or a heading (`II.`, `a)`) that introduces the next Randnummer (80,709
    rows: 40,319 indented — one of them the digitless-anchor row of §2.3 —
    37,045 plain rows matching a heading pattern, 3,345 other plain rows);
  - **after the last anchored row** of the section: it is *appended* to the
    last Randnummer unit **only if it is indented** (480 rows: closing
    quotations); otherwise it is **dropped** (32,547 rows: the judges'
    signatures in the files that render them as plain rows, the
    documentation office's `<Anmerkung der Dokumentationsstelle …>`
    notes, `Hinweis:` lines). The rule applies in anchored sections only:
    in the anchorless `tenor` of an Urteil the closing `Von Rechts wegen`
    row is part of the section unit (§4.4 — the first fixture file keeps
    it).
- **Unanchored** rows with empty text are ignored wherever they stand
  (the 791,451 spacer rows `<dt/><dd><p/></dd>`, every row whose only
  content was a dropped table — 16,336 signature tables after the last
  anchor — and the 292 rows that held only a dropped image-viewer
  caption).

Under this rule 81,008 Randnummern — **12.1%** — receive at least one
appended row (CP-76's 4.57% counted only the indented quotation blocks;
the headings and resumed text of §4.2 make up the rest).

A unit's **text** is its non-empty rows' texts — prefixed, own and
appended rows alike — in document order, joined with U+000A (one newline
between rows, none leading or trailing). A Randnummer unit whose text is
empty after the walk is **not produced**
(271 in this drop: the empty-bodied anchors no continuation row fills,
counted with the duplicates).

Why no smarter rule for headings: the plain rows between anchors mix
one-word headings (median 1 word) with real paragraph text that resumes
after a quotation (1,071 rows of twelve words or more, e.g. `lässt sich
weder anhand des Akteninhalts noch anhand des Berufungsurteils
nachvollziehen.` — the second half of Randnummer 8 in the first fixture
file), and nothing structural separates them. A length or pattern
threshold would be one more thing two implementations could disagree on;
a heading riding at the tail of the Randnummer it follows costs nothing an
agent can see except the two characters. Version 2 may add a heading rule
if a measurement shows it matters.

### 4.3 The tail rule, argued

The rows after a section's last anchor are, in this drop, 16,336 signature
tables, 32,547 plain rows with a median of three words (judges' names, one
per row, in the files that do not use a table), and 480 indented rows with
a median of 40–41 words (a closing quotation). The first two are not the
court's reasoning and would otherwise sit at the end of the last
Randnummer of half the corpus (17,625 files carry a table; the rest mostly
carry plain rows). The one attribute test recovers the third class. What
the rule loses: 946 plain rows of twelve words or more after the last
anchor — statute text appended as an annex, notes of the BGH
documentation office (`<Anmerkung der Dokumentationsstelle …>`), a
closing paragraph the publisher left unanchored — 2.9% of the plain rows
in that position, 0.3% of the 309,200 non-empty unanchored rows in the
drop — named here so nobody re-measures it.

### 4.4 A section with no anchored rows: one section unit

All its non-empty rows, joined with U+000A, form **one unit** with
`section` = the section's name and **`rn` = null**. This is how
`titelzeile` (26,814 units), `leitsatz` (12,861), `tenor` (33,958),
`sonstosatz` (45) and `sonstlt` (70) are indexed in ordinary decisions —
and how the **6.6% of decisions with no anchors at all** (2,231 files —
almost all of them the 2,237 tenor-only Beschlüsse with neither reasoning
section, whose tenor has a median of 478 tokens and which skew to
2023–2025: eight of those 2,237 carry anchors after all — seven in
`tenor`, one in `sonstlt` — and two files have a reasoning section with no
anchor, so 2,237 − 8 + 2 = 2,231) are indexed: as their `tenor` unit (and
`titelzeile`/`leitsatz` if present).
They are cited by `doknr` alone (§9). A section whose rows are all empty
produces nothing. The rule is per section, not per section *name*: the 7
`tenor` and 5 `sonstlt` sections that do carry anchors yield Randnummer
units (51 with `section: "tenor"` in the drop), and every other `tenor` is
a section unit.

### 4.5 What is dropped, in one place

| dropped | measured | rule |
|---|---|---|
| spacer rows (`<dt/><dd><p/></dd>`) and every empty `<dt/>` | 791,451 rows; 1,100,651 empty `<dt/>` | §4.1: only a row's `<dd>` text counts; empty rows are ignored |
| `<table>` subtrees — almost all judges' signature blocks | 18,596 tables in 17,625 files (52%); 60 under an anchor | §3.1: dropped everywhere, tails kept |
| `<img>` | 3,206 in 889 files (`src="bild1_0.jpg"` / `.png`, the image files are not in the corpus) | §3.1 |
| `<a href>` image-viewer links (`Abbildung in Originalgröße in neuem Fenster öffnen`) | 326 in 188 files | §3.1 |
| plain rows after a section's last anchor (signatures as rows, notes, closings) | 32,547 rows | §4.2 |
| Randnummer text outside any `<dl>` | 69 files | §4.6 |
| header fields other than the six carried on the hit (`norm`, `vorinstanz`, `spruchkoerper`, `region`, `identifier`, …) | — | not text; not on the wire (§7) |

### 4.6 Text outside rows

Text that is not inside a row — bare text in a `<div>` or a `<p>` that no
`<dl>` contains — is not indexed. It occurs in 69 files, where the
publisher rendered the first one or two Randnummern without their `<dl>`
(in 31 of them the stray text is only a signature or a heading); a
validator SHOULD report it.

### 4.7 The drop under this rule

| | count |
|---|---|
| files | 33,979 |
| units | **740,849** |
| Randnummer units | 667,099 (667,370 anchors − 271 empty) |
| section units | 73,750 (`tenor` 33,958 · `titelzeile` 26,814 · `leitsatz` 12,861 · `sonstosatz` 45 · `sonstlt` 70 · the two anchorless reasoning sections) |
| files with no Randnummer unit | 2,231 (6.6%) |
| files with no unit at all | 0 |
| characters of unit text | 462,896,397 |
| Randnummer length (MiniLM tokens, CP-76) | p50 **188**, p75 327, p90 480, p99 810, max 2,814; **36.5% exceed 254**, 42.9% exceed 220 |

---

## 5. Identity

### 5.1 `decision_id` is the `doknr`

The key of a decision is its `doknr`, verbatim: the only field that is
present and unique in every file (33,979/33,979), and the filename minus
its `jb-` prefix and `.xml`. Its shape in this drop is `[A-Z]{4}[0-9]{9}`.
An implementation
MUST use it as `decision_id` and MUST NOT derive the id from anything else
for a conforming source. (`gsj-next` slugs the `doknr` — for an
alphanumeric value the slug is the value, so its ids already conform.)

### 5.2 `aktenzeichen` is a display field

The docket number is what a lawyer says and writes, and it rides every hit
for that reason — but it identifies nothing on its own: shared by 3,199
files (eleven carry `2 StR 156/24`), still ambiguous **together with the
full date** (256 pairs cover 553 files), and 132 files carry two of them.
Verbatim from the source; never parsed by a consumer.

### 5.3 `ecli` is display-only and often absent

The European Case Law Identifier exists for 67.2% of the drop and for
**none of 2010–2014** — a third of the corpus cannot be cited by ECLI.
Where present it is unique and rides the hit verbatim; where the source
has none, the hit has no `ecli` key (§7.4). It is never a citation target.

### 5.4 A unit's identity

A unit is identified by `(decision_id, section, rn)`: `rn` an integer for
a Randnummer unit, null for a section unit. Randnummer numbering is
decision-global (it runs from `tatbestand` into `entscheidungsgruende` in
9,370 of the 9,382 Urteil-shaped files of §2.1 rows 17–18), so
`(decision_id, rn)` alone names a Randnummer —
except in the 13 files with duplicate numbers, where two units share it.
An implementation MUST produce both and MUST NOT merge or drop either; the
citation `dec:<doknr>:rn:<N>` is then ambiguous between two paragraphs of
the same decision, a known and reported anomaly, not a defect of the
implementation.

---

## 6. The embedding split

A unit is the retrieval unit; it is not necessarily the embedding unit.
36.5% of Randnummern exceed the 254 content tokens MiniLM can hold, and
1.8% of whole decisions fit any 256-token model. So **a unit that exceeds
the implementation's window is split into pieces; a unit that fits stays
whole.** The split is invisible on the wire (§7 returns whole units), so
this document constrains it only where a bad split would change what an
agent sees:

1. Every piece is a **verbatim, contiguous substring** of the unit's text
   (§4.2's bytes). No paraphrase, no re-flow, no header prefix — the piece
   an embedding sees is text the agent can be shown.
2. The pieces **cover** the unit: every character of the unit's text lies
   in at least one piece. Adjacent pieces MAY overlap. Nothing is
   silently truncated — the failure that has shipped twice on this corpus
   (`gsj-next`'s predecessor: a 900-character window truncating 95.65% of
   chunks at embed time; a fourth codebase's store: 99.7% of its full
   chunks truncated), and that this repository's service refuses at
   startup (`check_chunks_fit`).
3. A piece **never spans two units**.
4. Every piece carries its unit's identity (§5.4) and its ordinal within
   the unit, so that a hit on any piece resolves to the whole unit.

The window, the tokenizer, the overlap and the boundary rule (token or
character, sentence-aware or not) are the implementation's (§12). Under
this repository's pinned tokenizer at its 220-token window with 40
overlap, the Randnummern become ≈ 1,063,964 pieces (1.59×, measured at
CP-76 over the 667,371 anchored blocks); with the section units, ≈ 1.16
million pieces for the whole drop.

**Reference piece identifier** (informative — never on the wire):
`<doknr>:rn:<N>:p<i>` for the *i*-th piece (0-based) of Randnummer *N*, and
`<doknr>:<section>:p<i>` for a section unit's pieces; a duplicate-number
unit takes the smallest unused suffix `:d2`, `:d3` … before `:p<i>`.

---

## 7. The tool and the wire shape

### 7.1 The tool

Name `search_decisions`, on an MCP server named `gsj`; two parameters:

| parameter | type | default | |
|---|---|---|---|
| `query` | string | required | free text; the implementation embeds it as it embeds pieces |
| `k` | integer | **5** | the number of units wanted; clamped per §8.3 |

The declaration's other bytes — the docstring, an `ctx` parameter a
framework injects, the return annotation — are each implementation's own.
(This repository's declaration is byte-pinned by its roster gate; the two
parameters above are the part both implementations already share.)

### 7.2 The response

One JSON object:

```
{
  "query":        string      – the query as received
  "k":            integer     – the effective k (§8.3)
  "hits":         [hit, …]    – at most k, ordered per §8.2
  "index_commit": string      – optional; "" when unknown (§7.5)
}
```

How the MCP SDK carries it (text content, structured content, or both) is
the implementation's. `hits: []` is a normal response (an empty corpus, or
no candidate with a positive score — §8.2), never an error. Transport and
authentication errors are outside this document.

### 7.3 The hit

| field | type | presence | value |
|---|---|---|---|
| `decision_id` | string | **required** | the `doknr` (§5.1) |
| `aktenzeichen` | string | **required** | the source value verbatim (§5.2); `""` only if the source has none |
| `ecli` | string | **required when the source has a non-empty value; absent otherwise** | the source value verbatim (§5.3) |
| `court` | string | **required** | `gertyp` verbatim (`BGH`) |
| `date` | string | **required** | `entsch-datum` as ISO 8601 `YYYY-MM-DD` |
| `doktyp` | string | **required** | the source value verbatim (`Urteil`, `Beschluss`, …) |
| `rn` | integer ≥ 1 **or null** | **required at level 2; absent at level 1** (§7.6) | the Randnummer of the unit; **null for a section unit** (§4.4) |
| `section` | string | **required at level 2; absent at level 1** | one of the nine section names (§4.1) |
| `score` | number | **required**, positive | higher is more similar; a rounding of the ordering key (§8.2); scale is the implementation's — cosine similarity in both known implementations, one of them rounded to four decimals — so scores are not comparable across responses or across implementations |
| `text` | string | **required** | level 2: the **whole unit's text**, byte-exact per §4; level 1: a contiguous substring of the decision's text as that implementation extracts it — its provenance is otherwise unconstrained (it MAY include a header line such as `norm`, and it MAY have been read by a `.text`-only parser) |
| `excerpt` | string | optional, level 2 | the best-scoring piece of the unit (§8.1), so a consumer can render a hit short without re-splitting `text`; never a substitute for `text` |

**Additional keys** MAY be present (`gsj-next` carries `title` and `year`
today); a consumer MUST ignore keys it does not know. **Two keys are
reserved and MUST NOT appear on a decisions hit: `page` and `file`.** They
are the case-search hit's, and a reader that keys on them rather than on
the tool's name (this repository's demo transcript reader does; its
trainer-side page gate does not — it scopes by tool name and ignores a
decision hit's `page`, proven by its suite) would misread a decision hit
as a page hit.

### 7.4 Absent and null are different

- A key is **absent** when the implementation has nothing to say: the
  source carries no ECLI (`ecli`), or the implementation does not resolve
  Randnummern at all (`rn`, `section` at level 1).
- A key is **null** when the implementation knows the answer is "none":
  `rn: null` says *this unit is a whole section, not a numbered paragraph*
  — a positive statement the citation grammar relies on (§9.2).

Storage that cannot hold null (chroma metadata) is the reason `ecli` is
absent rather than null: it can be carried as metadata and simply omitted.
`rn` is decided at the wrapper, which can say null.

One rule per field, so no two are read by analogy: `ecli` — required when
the source has a non-empty value, absent otherwise, never null or `""`;
`aktenzeichen` — always present, `""` if the source has none (it is a
display field the human form needs a slot for); `rn` — present at level
2, integer or null, absent at level 1; `section` — present at level 2,
absent at level 1; `index_commit` — optional, and an absent key reads as
`""` (§7.5).

### 7.5 `index_commit`

An opaque string identifying the corpus drop and index the response was
served from; `""` when unknown. `gsj-next` returns `""` for the global
decisions corpus today and is conformant. This repository has a natural
value — the content hash of the drop, as recorded in its decisions lock
(`decisions.lock.json: corpus_sha256`, the CP-76 proposal) — and SHOULD
fill it once that lock exists. A consumer treats two responses with equal
non-empty values as served from the same index and makes no other
inference. The key MAY be omitted; a consumer reads a missing key as `""`.

### 7.6 Conformance levels

| level | what the hit carries | who |
|---|---|---|
| **0** | anything else | this repository's service before CP-79 (a bare list of `{decision_id, court, year, score, text}` over synthetic decisions) — and still its default with no `decisions.path`: the synthetic 30, those same hit keys inside the §7.2 envelope (image `0.4.1` and earlier carry no other mode) |
| **1 — document** | every required field of §7.3 except `rn` and `section`, which are **absent**; `text` an excerpt of unconstrained provenance. Level 1 is a **field contract only**: it says nothing about how text is extracted, so a level-1 implementation MAY index no unit at all for a decision its extraction empties (a `.text` parser empties 11 of the drop, two of the six fixture files among them — §3.2) | `gsj-next` once its hits carry `ecli`/`date`/`doktyp` (today it carries `decision_id`, `aktenzeichen`, `title`, `court`, `year`, `score`, `text` — the envelope conforms, the hit is three fields short) |
| **2 — Randnummer** | every field of §7.3, with `rn` and `section` on every hit, `text` the whole unit | this repository's service since CP-79 (image `0.5.0`) when `decisions.path` names a drop; `gsj-next` if and when it adopts §4 |

A consumer written for level 2 MUST accept level 1 responses: that is the
degradation rule (§9.3), and it is what makes a model trained at level 2
safe against a level-1 production surface.

---

## 8. Ranking and aggregation

### 8.1 Best piece per unit

The query is embedded once; candidate pieces are retrieved by vector
similarity; **a unit's score is the best score among its retrieved
pieces**; units are ranked by that score; the top *k* units are returned,
each with its **whole** text (never the piece). Several units of the same
decision MAY appear in one response — the unit is the Randnummer, not the
decision.

### 8.2 Order

Hits are ordered by the implementation's internal similarity descending
(the unrounded value `score` is derived from — two units that round to the
same wire `score` are still ordered by the internal one). Ties at the
internal value are broken by `decision_id` ascending, then — where the
hit carries them — `section` in DTD order, then `rn` ascending with null
first, then the unit's document order within its decision (the key that
separates two units of one decision that share an `rn`, §5.4): a total
order, so two implementations over the same vectors and the same
candidate set return the same list. An implementation MUST NOT return a
hit whose score is not positive.

### 8.3 `k`

`k` defaults to **5**. An implementation MUST treat a request with `k < 1`
as `k = 1`, and SHOULD cap `k` at an implementation limit `k_max ≥ 5`
(this repository: `search.max_k`, 20 today; `gsj-next`: uncapped). The
response's `k` is the **effective** value after this clamp, and
`len(hits) ≤ k`. A response MAY carry fewer than `k` hits. The cap is a
context matter, not a taste: a level-2 hit is a whole Randnummer (p50
188 tokens, p99 810, the longest 2,814 — §4.7), so five hits cost about
twice what a case-page search costs today at the median and up to six
times at the 95th percentile, and an uncapped `k` lets one tool result run
to tens of thousands of characters; a policy trained under one cap meets
the deployment's, so the two SHOULD agree. `k_max = 20` is the
recommended ceiling at level 2.

### 8.4 The candidate fetch

How many pieces are fetched before aggregation is the implementation's,
with one strong recommendation: the fetch SHOULD be **bounded by a
function of `k`, not of the corpus size** (fetching every vector is not a
workable design at 740,849 units; it is what this repository's service
does today over thirty decisions) — a SHOULD because nothing on the wire
can test it. Because a unit may contribute many pieces to the candidate
set, an implementation SHOULD fetch well more than `k` pieces (`gsj-next`
fetches `5·k`; the longest Randnummer, 2,814 tokens, splits into 16 pieces
at 220/40). Recall against an exact scan is **not guaranteed** by this document;
an implementation's record SHOULD state its bound and its measured recall
at the corpus's size (this repository's: wishlist row 68).

---

## 9. Citations

### 9.1 The grammar

An agent cites a decision it retrieved with one token:

```
citation = "dec:" doknr [ ":rn:" number ]
doknr    = 4 uppercase ASCII letters, 9 ASCII digits        ; e.g. KORE303672022
number   = 1*DIGIT without leading zeros, ≥ 1                ; the hit's rn
```

`dec:KORE303672022:rn:8` names Randnummer 8 of the decision with `doknr`
`KORE303672022`; `dec:KORE613012010` names the decision as a whole. The
token contains no spaces or slashes, so it survives every wrapper an agent
writes — `[Rn. 8](dec:KORE303672022:rn:8)`, `(dec:KORE303672022:rn:8)`,
`` `dec:KORE303672022:rn:8` `` — and one regular expression finds it:

```
(?<![A-Za-z0-9_])dec:([A-Z]{4}[0-9]{9})(?::rn:([1-9][0-9]*))?(?![A-Za-z0-9_]|:rn)
```

The two boundaries are part of the grammar: a token is not preceded by an
identifier character (`codec:KORE…` is not a citation) and not followed by
one or by a further `:rn` (`dec:KORE303672022__2` — the disambiguation
suffix `gsj-next` would append if a non-conforming drop made two files
claim one id — and `dec:KORE303672022:rn:08`, `…:rn:0`, `…:rn:8a`,
`…:rn:` are all *outside* the grammar, not truncated to a valid-looking
bare citation). A `:rn:` suffix that fails the number rule invalidates
the whole token. A hit whose `decision_id` is not a `doknr` of the shape
above is not a citation source; a consumer MUST reject it, never cut it to
shape.

The human form — `BGH, Urteil vom 8. Februar 2022 – VI ZR 543/20, Rn. 8` —
is prose beside the token, built from the hit's `court`, `doktyp`, `date`,
`aktenzeichen` and `rn`, and only from fields the hit carries: at level 1
that is the court and the Aktenzeichen (and whatever else is present, such
as a year), never a composed date or type. It is for the reader; the token
is for the machine. Neither the Aktenzeichen (§5.2) nor the ECLI (§5.3) is
ever the machine handle.

### 9.2 The rules an agent follows

1. A citation is written **only from a hit** the agent received in the
   same session. The `doknr` is copied from `decision_id`; nothing is
   composed from memory.
2. The `:rn:<N>` suffix is written **only when the hit carries an integer
   `rn`**, and `N` is that integer.
3. A hit with `rn: null` (a section unit — the Leitsatz, the Tenor, a
   tenor-only Beschluss) is cited in the **bare form** `dec:<doknr>`.
4. A hit **without an `rn` key** (a level-1 implementation) is cited in
   the **bare form** as well.
5. The bare form is always valid for any retrieved decision; the suffixed
   form is valid only under rule 2.

### 9.3 The degradation rule, and why it matters

Rules 3 and 4 together are the degradation rule: **an implementation that
cannot return `rn` returns hits without it, and an agent citing from such
a hit uses the bare form.** It is what makes a model trained against
level 2 safe against `gsj-next` as it stands:

- Every hit `gsj-next` returns from the drop it stands on today carries
  `decision_id` = the `doknr`. That is a property of the *data*, not of
  its code: `gsj-next` falls back to an Aktenzeichen or file-stem slug
  when a file has no `doknr` and appends `__N` when two files claim one
  id, and neither path fires on this drop (33,979 of 33,979 files carry
  an alphanumeric, unique `doknr`, so the slug is the value — measured
  through `gsj-next`'s own parser at CP-78). So `dec:<doknr>` is available
  there without any change on that side — and resolvable today only by
  the operator's CLI (`gsj decisions show <id>`): `gsj-next` has no MCP
  lookup tool and no reader of the token, which survives in a note as
  text.
- The suffix can be written only from an integer the hit carried. Where
  the hit carries none, the grammar has no valid suffixed form — so a
  correctly behaving policy emits the bare token, and a grader (§9.4)
  scores a fabricated `:rn:` as ungrounded, which is what training
  penalizes.
- Nothing about the bare form depends on the unit rule (§4): it is
  identical at every level, and it is the *only* form for the 6.6% of
  decisions that have no Randnummern anyway.

What the rule guarantees is the **grammar**: no valid citation exists that
production cannot resolve. Whether a trained policy *follows* rule 4 when
it meets level-1 hits for the first time is an empirical question, on two
axes. A model that only ever saw level-2 responses may still write `:rn:`
from habit; and the deployment's own instructions may say nothing about
`dec:` at all — `gsj-next`'s `AGENTS.md` today mandates page links only,
its agent loop retries once for a `page:` link, and its push hook enforces
a size floor and never reads a citation — so a policy trained under a
corpus that carries the §9.5 clause meets a prompt that does not, and a
`dec:`-only note is neither rejected nor read there. So a training corpus SHOULD include level-1 responses (hits
without `rn`) so the policy exercises rule 4 under reward; an evaluation
SHOULD measure the grounded-citation rate on level-1 responses separately,
under a prompt without the clause as well as with it; and the §9.5 clause
belongs in the instructions of *any* deployment the trained model reaches,
whatever its level. All three are the building checkpoint's and the
deployment's, not this document's.

### 9.4 Grounding a citation (informative — for graders)

A consumer that scores citations can do better than a range check: a
citation is **grounded** iff its `doknr` appears as `decision_id` in a hit
of a `search_decisions` result in the same trajectory and, when suffixed,
that hit carries `rn` equal to the suffix. Tool results are resolvable by
call id in this repository's traces and nothing between the service and
the record truncates them, so no census of the corpus is needed. A
fabricated in-range page number scores like a grounded one under the
existing `page:N` regex; a fabricated `dec:` token cannot.

### 9.5 Beside `page:N`

The grammar sits beside the case citation `page:N` and shares its habits:
bare, wrapper-agnostic, machine-checkable. The corpus's agent instructions
(`AGENTS.md`) and skill cards need one clause — in English, *cite
decisions as `dec:<doknr>:rn:<N>`; the hit gives you both; without an
`rn`, cite `dec:<doknr>`*; in German, the language every deployed prompt
in this line is written in, *Zitiere Entscheidungen als
`dec:<doknr>:rn:<N>` — der Treffer liefert beides; ohne `rn` zitiere
`dec:<doknr>`* — and that clause is the corpus author's to add (in this
repository it moves a prompt-hash gate exactly as any `AGENTS.md` edit
does).

---

## 10. Conformance

### 10.1 The fixture

[`decisions-surface/`](decisions-surface/README.md) holds six real
decisions from the drop, byte-identical to their published form — three
chosen for the corpus's three shapes and three for the one rule each
discriminates — and `expected.json`, the units and metadata this
document's rules produce for each, generated by a reference extractor
(not typed by hand):

| file | shape | what it exercises |
|---|---|---|
| `jb-KORE303672022.xml` | Urteil, 2022, VI ZR 543/20 | the ordinary shape: `titelzeile`/`leitsatz`/`tenor` section units; Randnummern 1–3 in `tatbestand` running into 4–9 in `entscheidungsgruende`; headings `I.`/`II.`/`III.` between anchors; an indented quotation inside Rn 8 with the plain text that resumes after it; a signature table after the last anchor; an ECLI |
| `jb-KORE613012010.xml` | Beschluss, 2010, XI ZR 63/10 | the anchorless 6.6%: tenor-only, two rows, no `titelzeile`, no `leitsatz`, **no ECLI** (the `ecli` key is absent), one section unit with `rn: null` |
| `jb-KORE202300077.xml` | Beschluss, 2023, I ZB 62/23 | the post-2018 `<span>` pattern: every paragraph's text is inside `<span style="color: rgb(0, 0, 0)">`, so `.text` extraction yields an **empty decision** (one of the eleven); three Randnummern; the judges' signatures as plain rows after the last anchor (dropped) |
| `jb-KORE308052015.xml` | Beschluss, 2015, XII ZB 608/13 | **the glued image** (§3.1 rule 1): Rn 22 reads `§ 23 Rn. 2)<img/>. Da für` — one of the three rows in the drop where a dropped element sits between two non-space characters; an implementation that emits a boundary for it writes `Rn. 2) . Da` and fails. Also no ECLI, 26 Randnummern, no table |
| `jb-JURE160019189.xml` | Beschluss, 2016, XI ZR 6/16 | **the image-viewer link** (§3.1 rule 1): Rn 1 ends `Widerrufsinformation eingefügt:` followed by `<img>` and `<a href="bild1_0.jpg"><br/><span>Abbildung in Originalgröße in neuem Fenster öffnen</span></a>`; an implementation that keeps the caption fails. An ECLI |
| `jb-JURE130006754.xml` | Beschluss, 2013, AnwZ (Brfg) 60/12 | **the indented tail row inside a `<span>`** (§4.1, §4.2): after the last anchor a `<p style="margin-left:36pt"><span>Rechtsmittelbelehrung:</span></p>` row, kept by the tail rule only under the whole-subtree reading of `text(p)`, followed by the plain (dropped) rows; that row is one of the 23,212 `.text`-empty paragraphs of §3.2 (the decision as a whole is not one of the eleven); no ECLI |

Together: 62 units (12 + 1 + 4 + 29 + 10 + 6), of which 50 Randnummern
and 12 section units; three hits with `ecli`, three without; one
`Urteil`, five `Beschluss`. The first three reproduce the corpus's
shapes; the last three each pin one sentence of §3–§4 that the first
three cannot tell apart — found by having three independent implementers
write the rule from this text and diffing them (CP-78).

### 10.2 What "agree" means

An implementation **conforms at level 2** iff, for each fixture file, its
extraction produces exactly the units in `expected.json` — the same
count, the same order, and for each unit the same `section`, the same `rn`
and the same `text`, byte for byte — and a hit it returns for any of those
units carries the `decision_id`, `aktenzeichen`, `court`, `date`, `doktyp`
values recorded there, with `ecli` present for the three files that have
one and absent for the other three. The ranking rules (§8) are not testable by the
fixture (they need a model); they are testable between two implementations
that share one.

An implementation **conforms at level 1** iff its hits for the six files
carry the level-1 fields of §7.3 with these values and no `rn` or
`section` key.

### 10.3 Licence position of the fixture

The six files are court decisions of the Bundesgerichtshof as published
by the Federal Ministry of Justice and the Federal Office of Justice on
rechtsprechung-im-internet.de. Under § 5 Abs. 1 UrhG, court decisions and
officially authored headnotes enjoy no copyright protection; the publisher
states on its front page that the decisions are available in every
offered format — the XML included, per its *Hinweise* page — for free use
and reuse (*„Die Entscheidungen stehen in allen angebotenen Formaten zur
freien Nutzung und Weiterverwendung zur Verfügung“*, read 2026-09-02); the
dataset is registered on GovData by the Bundesamt für Justiz under "other
open licence"; every file carries `accessRights: public`. The copies are
byte-identical to the published XML — re-downloaded from the site at CP-78
(the `jb-<doknr>.zip` links of its `rii-toc.xml`) and compared: identical
— nothing altered, the source named inside each file's `identifier`
element and in the fixture's README. What in the files is the
court's own text: the Tenor, the reasons, and the `leitsatz` of
`jb-KORE303672022.xml`, which matches the Senate's headnote in the BGH's
own publication of that judgment verbatim. The `titelzeile` of that file
and the `norm` line of two are documentation additions absent from the
court's own publication; whether they count as officially authored under
§ 5 Abs. 1 is settled by case law only for a court documentation office's
*Orientierungssätze* (VGH Baden-Württemberg, 10 S 281/12, for the BVerfG's),
and the site does not say whether the BGH's Dokumentationsstelle or the
technical provider wrote them — they ride under the publisher's free-use
statement, unmodified. None of the six files contains a `sonstosatz`
(in this drop 39 of the 45 are explicit notes of the BGH's
Dokumentationsstelle). The repository's Apache-2.0 licence covers
`expected.json` and the README, not the six source files, which are not
this repository's work.

---

## 11. What this document does not cover

Stated so that nobody reads a promise into silence.

1. **Whole-decision reading.** An agent sees Randnummern and sections,
   never the judgment as one document. `gsj-next` has `get_decision` as a
   CLI verb and not as an MCP tool; this repository has nothing. Adding one
   is a roster change and, here, a release — a separate decision.
2. **Lexical retrieval.** No BM25, no exact-Aktenzeichen lookup is
   specified; a query that is a docket number is embedded like any other.
   (An implementation MAY answer such a query with that decision's units
   first, inside the same shape; nothing here requires it.)
3. **Metadata filters.** No `where` on year, court, senate or doktyp: the
   two parameters are `query` and `k`, and adding one moves this
   repository's declaration pin. `decision_stats` is not specified here.
4. **The embedding model's suitability for German.** Both known
   implementations pin `all-MiniLM-L6-v2`, an English-vocabulary model
   measuring 2.75 characters per token on this corpus; the split (§6)
   makes it *correct* (nothing truncated), not *good*. Retrieval quality is
   unmeasured and outside this document.
5. **Recall.** §8.4 bounds the fetch and asks for a measurement; it does
   not promise a number.
6. **Versioning of the corpus** beyond the opaque `index_commit`: no diff,
   no partial update, no history — a drop is replaced whole.
7. **Multi-court corpora.** Every number here is from a single-court drop
   (`BGH`); `court` is carried so that a wider drop needs no *hit*-shape
   change — but the citation grammar pins the `doknr` shape (§2.2, §9.1),
   so a drop whose document numbers look different is a surface version
   bump; nothing else about other courts' documents has been measured.
8. **Errors, authentication, transport**, and the tool's docstring.

## 12. What is deliberately left to the implementation

None of these changes what an agent sees, so none is specified:

- **the store** — chroma, SQLite, anything; whether piece text lives beside
  the vector or is read back from a units table;
- **the model, the tokenizer, the window, the overlap, the boundary rule**
  of the split (§6's four constraints hold for any choice);
- **batching, identity records, fingerprints, rebuild policy** — how an
  implementation knows its index matches its drop;
- **the candidate-fetch bound** (§8.4) and the ANN index;
- **the score's scale and precision**;
- **the internal identifiers** of units and pieces (§6 gives a reference
  scheme);
- **how the thirty decisions of an estate corpus are chosen**, and how a
  drop is validated, locked and mounted (this repository: the CP-76
  proposal, corpus-contract v3).

---

## 13. What it costs each side (informative)

Restated from the CP-76 cost table against the settled decisions, with
`gsj-next`'s side added. Nothing in this section is a commitment on
`gsj-next`'s behalf.

### 13.1 This repository (its own concerns — a `gsj-next` reader skips this table)

| surface | change | pin / law |
|---|---|---|
| `estate/` (outside the size law) | as CP-76's table: `ingest_corpus.py`'s root entry, `validate` clauses (§2.2 plus the anomaly report of §2.3), `decisions.lock.json` and the verify clause; `estate.py`'s `/app/decisions:ro` mount, `decisions.path` in the config template and its two hand-mirrored key lists, `update` semantics for a replaced folder, `scaffold` writing an empty `decisions/`; corpus-suite tests — **built at CP-88** (corpus-contract v3, ADR-0038): the root entry, the §2.2 refusals plus the §2.1 element sequence, §2.3 reported not refused, the census-only lock, verify's two comparisons, the default mount with `--decisions-dir` as the override; the unit rule ported into the pipeline and pinned to the fixture and to the service's parser (the full drop: 740,849 units, equal hashes); `update` does not see a drop-only change — a re-run of `up` re-locks it | corpus-contract v3 → ADR-0038 (CP-88) |
| `estate/mcp-service/` `decisions.py` | rii parser + the unit walk of §3–§4 (the synthetic generator kept as the no-path fallback) | — |
| `estate/mcp-service/` `index.py`, `state.py`, `config.py` | `decisions.path`; pieces per §6 through the existing token-window chunker and `check_chunks_fit`; best-piece-per-unit aggregation (§8.1) with a **bounded fetch** (§8.4); per-collection identity and fingerprint; `/health.decisions` → `{count, sha}` | image cut (`0.5.0`); ADR-0034/0035 as CP-76 named them |
| `tools.py` **body** | the wrapper `{query, k, hits, index_commit}` and the level-2 hit; the **name, parameters, defaults and docstring stay byte-identical** — `search_decisions(query: str, k: int = 5)` and its one-line docstring — while the `def` line's return annotation changes `-> list[dict]` → `-> dict`, and must: under mcp 2.0.0 a dict returned from a `-> list[dict]` tool fails the SDK's output validation with a tool error, and `-> dict` yields no output schema and no structured content, the shape `case_status` and `decision_stats` already use. The annotation is outside the roster hash — G3 hashes name + description + pi's rendering of the *input* schema + order; mcp 2.0.0 emits an output schema for `-> list[dict]` and none for `-> dict`, and pi-mcp-extension 1.5.0 reads neither — **re-verified at CP-78 by rendering both declarations through the roster suite's own wire-entry helper: identical bytes, the pinned hash reproduced**; so **G3 does not move and G2 does not move** (G2 carries the docstring's first 120 characters, unchanged). What does change on the wire: the tool result becomes one text block carrying the wrapper instead of N blocks (one per hit) plus structured content — the trace's tool message holds one JSON object. `tools.py`'s own CONTRACT docstring ("signatures (type hints and defaults) … byte-identical") must be amended to exclude the return annotation when the wrapper lands, or the file contradicts itself | none |
| service tests | `test_tools.py:128–146` rewritten for the wrapper (the whole test iterates the result as a list, not only its key-set line); the `== 30` assertions (`test_processes.py:55`, `test_config.py:55`, `test_ingest.py:85`, `test_tools.py:155–157`, `test_backend.py:867`) untouched while the generator stays the no-path default; the six fixture files as real-shaped fixtures and `expected.json` as the conformance test; the A-25 canary re-measured on the real store | — |
| `gsj_rollout/` (2,034/2,034, headroom 0) | **nothing** — no tool, no declaration, decisions stay cutoff-exempt (`checks.py`'s `CUTOFF_SCOPED_TOOLS`), the allowlist default unchanged | — |
| `pins/` | **nothing** for the wrapper and the hit; a corpus's `AGENTS.md` clause (§9.5) moves that corpus's G2, as any `AGENTS.md` edit does | — |
| consumers | examples: the `dec:` regex + trace-grounded validation (§9.4) — F-80; demo: `parse_hits` already returns `None` for a hit without `page` (today's decision hits render as a raw clip; the wrapper renders the same way — run at CP-78), so nothing breaks and one branch may render Randnummern later; its cutoff-violation line for a non-integer `page` prints only when the archived metadata carries an integer timestep, which is why §7.3 reserves the key | F-80 |
| corpus content (staging / BYO) | the `AGENTS.md` and skill-card clause; the staging corpus stays synthetic (no decisions folder), so its G2 does not move | G1/G2 per corpus |
| docs | corpus-contract v3 (the `decisions/` entry, the lock, the citation clause beside `page:N`), `checks-spec` (the G5 exemption stated, unchanged), the server guide, the mcp-service README, the two guide diagrams | — |

If the operator later wants `get_decision` as a tool or a `where` filter on
`search_decisions` (§11.1, §11.3): a declaration change — G3 and G2 re-pin,
one `config.py` allowlist line under the size law's equality test and an
ADR, a wheel release, re-collected root-suite fixtures — a separate
decision, as CP-76 priced it.

### 13.2 `gsj-next`, if and when it adopts

| what | change | size |
|---|---|---|
| level 1 (the hit's missing fields) | carry `ecli` (its parser never reads the element today, though its own rii fixtures carry one), `date` (ISO; today the date is read and sliced to a year), `doktyp` (already stored) on the row and the hit; keep `title`/`year` (additional keys are allowed); clamp `k < 1` to 1 and echo the effective `k` (§8.3 — today `k=0` and `k=-3` are echoed as they came and return no hits); drop the `ecli` key when the row's value is null (§7.4) | a guarded `ADD COLUMN` × 2 (the pattern its store already uses), ~15 lines in `search.py`, one test; no re-embedding — but the ingest verb re-embeds every decision it touches, so the back-fill is a new small `UPDATE` path over the files, not a re-run of ingest |
| level 2 (the unit) | replace `_paragraphs` with §3's flow (inline set, dropped subtrees, `<br>`, White_Space); the row walk of §4 instead of the joined-sections string; per-unit text storage — a units table, or the whole unit's text beside each piece, §12 leaves it open (the decisions row holds the joined decision text and chunk text lives only in chroma today); ids and metadata per piece (§6); best-piece-per-unit instead of best-chunk-per-decision (its `_OVERFETCH` already bounds the fetch) | a rewrite of the decisions half of `search.py` (~150 lines) and `ports.replace_decision`; a **full re-ingest** — ≈ 1.39 M pieces at its 500/80-character window over units (an approximate §4 walk at CP-78; the ≈ 1.16 M of §6 is this repository's 220/40-token geometry) vs 1,122,668 chunks today, roughly a quarter more vectors (≈ 7 GB vs 5.8 GB), hours of CPU; the six conformance files joined to its two `decisions_rii` fixtures (which pin CF-1's shared-Aktenzeichen pair and stay); the §8.2 order; its per-decision result view (`views.render_decisions_search`: a title column today, `rn`/`section` columns for unit hits), its test doubles' metadata and the shape assertion in its integration suite; `get_decision`/`decisions show` semantics once units exist beside the decision text |
| any level the trained model is deployed against | the `AGENTS.md` citation clause (§9.5) — the model meets the deployment's prompt, not the training corpus's | one clause |
| any level — release and operations | `gsj-next` is a deployed product with a pilot bound to its state (a chart pin, runbook counts of 33,979 decisions / 1,122,668 vectors): any level is an image and chart release, a runbook change in both languages, and a corpus operation on the pilot cluster — the level-1 back-fill an operator verb or ingest flag with its own test and doc line, level 2 a re-ingest of about five hours at today's rate plus a larger vector volume | the dominant cost on that side, and the operator's to schedule |
| not required | the envelope's shape and keys (already conformant for `k ≥ 1`; the `k < 1` clamp is the level-1 item), `index_commit` (`""` is conformant), the tool declaration, the CLI verbs, the case-side pipeline | — |

---

## 14. Change log

- **v1 — CP-78, 2026-09-03** (drafted 2026-09-02, verified and settled
  the next day). First version. Written against the
  CP-76 census (33,979 files) and the CP-78 re-measurement under §3–§4's
  rules (740,849 units). Three independent implementers reproduced the
  three-file fixture from the text alone; their divergences on rows the
  fixture did not contain (a dropped element's boundary, the image-viewer
  link, an indented row inside a `<span>`) settled §3.1 rule 1 and §4.1
  and added the fourth to sixth files. Fixture: `jb-KORE303672022.xml`,
  `jb-KORE613012010.xml`, `jb-KORE202300077.xml`, `jb-KORE308052015.xml`,
  `jb-JURE160019189.xml`, `jb-JURE130006754.xml`, `expected.json`
  generated by the reference extractor. No implementation conforms yet.
- **wording — CP-80, 2026-09-03** (version unchanged, §0): the status
  paragraph and §7.6's "who" column moved from "not implemented" to the
  level-2 implementation CP-79 built (`gsj-mcp-service:0.5.0`,
  `estate/mcp-service/`), proven against the fixture by
  `tests/test_decisions.py`. No field, rule, grammar or fixture output
  changed.
- **wording — CP-88, 2026-09-06** (version unchanged, §0): the status
  paragraph names the corpus's own `decisions/` as the drop's default
  source (corpus-contract v3, ADR-0038) with `--decisions-dir` as the
  override, and §13.1's `estate/` row records what was built. A second
  level-2 implementation of §3–§4 now exists — the pipeline's port in
  `estate/corpus/ingest_corpus.py`, for the lock's census — pinned to the
  fixture and to the service's parser (the two agree over the full
  33,979-file drop: 740,849 units, the same hash). No field, rule,
  grammar or fixture output changed.
