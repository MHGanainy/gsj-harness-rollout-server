# The decisions-surface conformance fixture (surface version 1)

Six real decisions of the Bundesgerichtshof, byte-identical to their
published rii-dok v1 XML, and `expected.json` — the units and the hit
metadata that [`../decisions-surface.md`](../decisions-surface.md) §3–§5
produce for each. Three files reproduce the corpus's three shapes; three
more each pin one sentence of the unit rule that the first three cannot
tell apart (found at CP-78 by having three independent implementers write
the rule from the specification alone and diffing their outputs). An
implementation of the surface at level 2 is conformant iff it reproduces
`expected.json` exactly (spec §10.2). This directory is meant to be
**copied** into an implementation's test tree; the specification is not
(spec §0).

## The files

| file | sha256 | bytes | shape (spec §10.1) |
|---|---|---|---|
| `jb-KORE303672022.xml` | `995b9147812967385eb8f0ecaa275ccbb31cf82bdf3a6998f81e5050005dccbf` | 15,035 | ordinary: Urteil, VI ZR 543/20, 2022-02-08; nine Randnummern across `tatbestand` and `entscheidungsgruende`, headings between anchors, an indented quotation inside Rn 8, a signature table, an ECLI |
| `jb-KORE613012010.xml` | `4f957a81359ea12045836880c380c44504d4e7c9a2b1902edd5e57b168d7c948` | 1,908 | anchorless: Beschluss, XI ZR 63/10, 2010-06-01; tenor only, no ECLI — one section unit, `rn: null`, no `ecli` key |
| `jb-KORE202300077.xml` | `d9cb95c3037d41438d3c5c2c3055a5e1574e66735c9dd3172a7158b18345a1b6` | 4,314 | the post-2018 `<span>` export: Beschluss, I ZB 62/23, 2023-11-09; every paragraph inside a styled `<span>`, so a `.text`-only parser yields an empty decision; three Randnummern; signatures as plain rows after the last anchor |
| `jb-KORE308052015.xml` | `a0a2443d1784c9eac3a7d21f6317d323137e3c1d60de8c98e1c49b99b615d560` | 31,134 | the glued image (spec §3.1 rule 1): Beschluss, XII ZB 608/13, 2015-02-25; Rn 22 reads `§ 23 Rn. 2)<img/>. Da für` — a dropped element between two non-space characters, one of three such rows in the drop; an implementation that emits a word boundary for the dropped element fails here; no ECLI, 26 Randnummern |
| `jb-JURE160019189.xml` | `7baef778fb3428816b683309cac6a75b27ba78ab0bb182b6db249328b6e6572f` | 10,555 | the image-viewer link (spec §3.1 rule 1): Beschluss, XI ZR 6/16, 2016-10-25; Rn 1 ends `Widerrufsinformation eingefügt:` followed by an `<img>` and an `<a href="bild1_0.jpg">…Abbildung in Originalgröße in neuem Fenster öffnen…</a>` that the rule drops; an implementation that keeps the caption fails here; an ECLI |
| `jb-JURE130006754.xml` | `72cd8138cdf76b7240308efc5ca6beab7c26739deee0d88a98be3b86e0edcd66` | 7,972 | the indented tail row inside a `<span>` (spec §4.1, §4.2): Beschluss, AnwZ (Brfg) 60/12, 2013-03-21; after the last anchor a `<p style="margin-left:36pt"><span>Rechtsmittelbelehrung:</span></p>` row that the tail rule keeps only when `text(p)` reads the whole subtree; no ECLI |
| `expected.json` | `742330813246ecb91c9c325f7e5b6e07c7ae6bd02b6f29e86da9956e3b61c70c` | 43,073 | generated at CP-78 by `reference_extractor.py` from the six files above; carries `surface_version: 1` |
| `reference_extractor.py` | `5f405e24f84347a8447399e46d20d1f74baf762fbf545ffbd5c63022b8c72db3` | 7,829 | the generator: spec §2.2, §3, §4, §5 as one literal reading, standard library only — the fixture's provenance, **not** an implementation of the surface and not part of any service |

62 units in all (12 + 1 + 4 + 29 + 10 + 6): 50 Randnummern and 12 section
units; `ecli` present on three files, absent on three.

## `expected.json`

One JSON object: the surface version, the generator, and one entry per
file in the order of the table above:

```
{
  "surface_version": 1,
  "generated_by":    "reference_extractor.py (CP-78)",
  "documents": [
    {
      "file":     "jb-KORE303672022.xml",
      "metadata": {"decision_id", "aktenzeichen", "court", "date", "doktyp", "ecli"?},
      "units":    [{"section", "rn", "text"}, …]      // document order; rn null for a section unit
    }, …
  ]
}
```

`metadata` carries exactly the hit fields of spec §7.3 that come from the
header — `ecli` present for the three files that have one, **absent**
(not null) for `jb-KORE613012010.xml`, `jb-KORE308052015.xml` and
`jb-JURE130006754.xml`. `units` are in the order spec §4
produces them: sections in DTD order, rows in document order. Each
`text` is the whole unit, rows joined with U+000A, whitespace normalized
per spec §3.1. Every string is UTF-8 without escaping of non-ASCII
characters.

## Running a conformance check

There is no harness here by design — the check is a comparison any
implementation can write in a dozen lines:

1. parse each XML file, extract its units and header fields per spec
   §2–§5;
2. serialize as above;
3. compare with `expected.json`'s `documents`: same number of units per
   file, same order, and for every unit the same `section`, `rn` and
   `text` (byte equality of the UTF-8 string); the same `metadata` keys
   and values, `ecli` absent where absent.

A difference is either a bug in the implementation or a defect in the
specification's wording. In the second case the specification moves and
the surface version with it; `reference_extractor.py` is edited to the
new reading and `expected.json` regenerated from it:

```
python3 reference_extractor.py fixture expected.json jb-KORE303672022.xml jb-KORE613012010.xml jb-KORE202300077.xml jb-KORE308052015.xml jb-JURE160019189.xml jb-JURE130006754.xml
```

How well the prose alone pins the rule was measured once, at CP-78: three
implementers who had read only the specification (never this directory,
never the extractor) reproduced the first three files byte for byte, and
on the last three — added for that reason — two of them diverged on the
glued image and all three on the image-viewer link, until the wording
was tightened.

## Provenance and licence

The six files were taken unmodified from the 33,979-file rii drop this
repository measures against (files dated 2026-03-23, the drop of March
2026), themselves downloaded from Rechtsprechung im Internet,
`https://www.rechtsprechung-im-internet.de/` — the Federal Ministry of
Justice and Consumer Protection (`publisher: BMJV` in every file) with the
Federal Office of Justice; technical provision by juris GmbH. Each file
names its own source page in its `identifier` element:
`http://www.rechtsprechung-im-internet.de/jportal/?quelle=jlink&docid=jb-<doknr>&psml=bsjrsprod.psml&max=true`.

Their licence position:

- Under **§ 5 Abs. 1 UrhG**, court decisions and officially authored
  headnotes (*Entscheidungen und amtlich verfaßte Leitsätze zu
  Entscheidungen*) enjoy no copyright protection.
- The publisher states on the site's front page (read 2026-09-02): *„Die
  Entscheidungen stehen in allen angebotenen Formaten zur freien Nutzung
  und Weiterverwendung zur Verfügung.“* — and its *Hinweise* page lists
  the XML, with this DTD, as one of the offered formats. The site names
  no licence instrument; GovData registers the dataset, by the Bundesamt
  für Justiz, under "other open licence". Every file carries
  `accessRights: public` — a metadata field, not a licence.
- The copies are byte-identical to the published XML (the hashes above;
  re-downloaded from the site at CP-78 through the `jb-<doknr>.zip` links
  of its `rii-toc.xml` and compared — identical), so nothing has been
  altered, and the source is named. § 5 Abs. 1 works carry no duty at
  all; the no-alteration and source-naming duties of § 62 Abs. 1–3 and
  § 63 Abs. 1–2 attach to § 5 Abs. 2 works, and both are met anyway.
- What is the court's own text: the Tenor and the reasons of all six,
  and the Leitsätze (two files carry one; that of `jb-KORE303672022.xml`
  matches the Senate's headnote in the BGH's own publication of the
  judgment verbatim). The `titelzeile` (four files) and the `norm` line
  (five) are documentation additions absent from the court's own
  publication; the
  site does not say whether the BGH's Dokumentationsstelle or the
  technical provider wrote them, and case law settles the "officially
  authored" question only for a court documentation office's
  *Orientierungssätze* (VGH Baden-Württemberg, 10 S 281/12) — they ride
  here unmodified under the publisher's free-use statement, which names
  every offered format. None of the six files contains a `sonstosatz`
  (in this drop, 39 of the 45 are explicit notes of the BGH's
  Dokumentationsstelle). No text of a private publisher is present.
- The decisions are published anonymized by the court; the only personal
  names they carry are the judges' signatures, which are part of the
  published decision and which the surface drops from indexed text (spec
  §3.1 rule 1 for the signature tables, §4.2 for signatures as plain
  rows) — the files keep them, unmodified.

The repository's Apache-2.0 licence covers `expected.json`,
`reference_extractor.py` and this README; it does not cover the six XML
files, which are not this repository's work and need no licence from it.
