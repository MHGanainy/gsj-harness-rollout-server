#!/usr/bin/env python3
"""Deterministic synthetic decisions corpus — carried over at CP-29.

Byte-identical generation to the retired stdio stub's ``decisions.py`` (CP-03,
ADR-0007): same seed, same templates, same rng stream => the same 30
decisions the pinned episodes saw. The only change is the optional ``n``
parameter (defaulting to the same ``N_DECISIONS``) so the service's
``decisions.corpus_size`` config field is honest; ``n == N_DECISIONS``
reproduces the historical corpus exactly.

Each decision's opening sentence embeds a docket reference
`AZ-<year>-<court>-<k>` that is unique to it by construction, so exact-hit
verification needs no fuzzy matching.
"""

from __future__ import annotations

import random

DEFAULT_SEED = 20260204
N_DECISIONS = 30
YEARS = list(range(2019, 2026))
COURTS = ["LG-A", "OLG-B", "BGH-C"]

SUBJECTS = ["freight contract", "warehouse lease", "insurance claim",
            "customs bond", "charter agreement", "salvage award",
            "storage liability", "carriage dispute"]
CHAMBERS = ["first civil", "second civil", "commercial", "maritime",
            "appellate"]
PARTIES = ["claimant", "defendant", "intervener", "guarantor"]
OUTCOMES = ["allowed in part", "dismissed as unfounded",
            "remitted for retrial", "settled by consent", "upheld on appeal"]

OPENING = ("Decision {docket}: the {chamber} chamber of {court} ruled on a "
           "{subject} in {year}.")
BODY_TEMPLATES = [
    "The {party} prevailed on the principal head of claim, with costs "
    "divided {a}:{b}.",
    "An expert opinion on the {subject} was commissioned and adopted in "
    "full.",
    "The court held that notice under the {subject} had been served out of "
    "time.",
    "Security of {amount} marks was ordered pending enforcement.",
    "The counterclaim brought by the {party} was {outcome}.",
    "Interest was awarded at {rate} percent from the date of filing.",
    "The appeal against the interlocutory order was {outcome}.",
    "Witness testimony on the {subject} was found only partially credible.",
]


def decisions_corpus(seed: int = DEFAULT_SEED, n: int = N_DECISIONS) -> list[dict]:
    """The full corpus: [{decision_id, court, year, text}], generation order."""
    rng = random.Random(f"{seed}/decisions")
    counters: dict[tuple[int, str], int] = {}
    corpus: list[dict] = []
    for _ in range(n):
        year = rng.choice(YEARS)
        court = rng.choice(COURTS)
        k = counters[(year, court)] = counters.get((year, court), 0) + 1
        docket = f"AZ-{year}-{court}-{k}"
        subject = rng.choice(SUBJECTS)
        sentences = [OPENING.format(docket=docket, chamber=rng.choice(CHAMBERS),
                                    court=court, subject=subject, year=year)]
        for _ in range(rng.randint(1, 3)):
            sentences.append(rng.choice(BODY_TEMPLATES).format(
                party=rng.choice(PARTIES), subject=subject,
                outcome=rng.choice(OUTCOMES), a=rng.randint(1, 3),
                b=rng.randint(1, 3), amount=rng.randint(2, 80) * 500,
                rate=rng.randint(2, 9)))
        corpus.append({"decision_id": f"D-{year}-{court}-{k}", "court": court,
                       "year": year, "text": " ".join(sentences)})
    return corpus


# ---------------------------------------------------------------------------
# The rii parser and the unit walk (CP-79) — docs/decisions-surface.md v1:
# §2.2 (a conforming source file), §3 (text extraction), §4 (the unit),
# §5 (identity). Standard library only, no store and no embedding here —
# the generator above stays the no-path fallback, byte-unchanged. The
# conformance fixture (docs/decisions-surface/expected.json, 62 units over
# six published decisions) is the acceptance test of everything below
# (tests/test_decisions.py); a rule change here that moves the fixture is a
# surface-version bump, never a quiet edit.

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SURFACE_VERSION = 1
# the nine ANY body sections, in DTD order (spec §4.1) — `vorinstanz` is
# ANY too but a header field, not text
SECTIONS = ("titelzeile", "leitsatz", "sonstosatz", "tenor", "tatbestand",
            "entscheidungsgruende", "gruende", "abwmeinung", "sonstlt")
SECTION_ORDER = {name: rank for rank, name in enumerate(SECTIONS)}
# the six inline elements that do not separate words (spec §3.1 rule 2)
INLINE = frozenset({"a", "em", "strong", "span", "sub", "sup"})
# subtrees that contribute nothing at all — not even a boundary (rule 1);
# an <a> is dropped only when it carries an href (the image-viewer link)
DROPPED = frozenset({"table", "img"})
ANCHOR_RE = re.compile(r"rd_([0-9]+)")          # fullmatch, spec §4.1
DOKNR_RE = re.compile(r"[A-Z]{4}[0-9]{9}")      # spec §2.2 / §9.1
DATE_RE = re.compile(r"[0-9]{8}")               # eight ASCII digits
FILENAME_RE = re.compile(r"jb-(.+)\.xml")


class DecisionError(Exception):
    """A source file that does not conform (spec §2.2) — the training estate
    refuses it, with the reason, and never aborts the drop for it."""


@dataclass(frozen=True)
class Unit:
    """What one hit is a hit of: a Randnummer (``rn`` ≥ 1) or a whole
    section (``rn`` None), with its text exactly as spec §4 produces it."""
    section: str
    rn: int | None
    text: str


@dataclass(frozen=True)
class Decision:
    file: str
    sha256: str                 # of the file's bytes
    decision_id: str            # the doknr, verbatim (spec §5.1)
    aktenzeichen: str
    ecli: str | None            # None = the source has none (absent on the hit)
    court: str
    date: str                   # ISO 8601 YYYY-MM-DD
    doktyp: str
    units: tuple[Unit, ...]     # document order: sections in DTD order, rows in order
    anomalies: tuple[str, ...] = ()

    @property
    def year(self) -> int:
        return int(self.date[:4])

    def header(self) -> dict:
        """The hit's header fields (spec §7.3): ``ecli`` present only when the
        source has a non-empty value — absent, never null or empty."""
        doc = {"decision_id": self.decision_id,
               "aktenzeichen": self.aktenzeichen, "court": self.court,
               "date": self.date, "doktyp": self.doktyp}
        if self.ecli:
            doc["ecli"] = self.ecli
        return doc

    def as_fixture_document(self) -> dict:
        """The shape of one entry of ``expected.json``'s ``documents``."""
        return {"file": self.file, "metadata": self.header(),
                "units": [{"section": u.section, "rn": u.rn, "text": u.text}
                          for u in self.units]}


@dataclass(frozen=True)
class Drop:
    """A directory of ``jb-<doknr>.xml`` files, read in ascending filename
    order: the conforming decisions, the files refused with their reasons,
    and one content hash over the conforming files (the fingerprint
    component and ``index_commit``)."""
    path: str
    decisions: tuple[Decision, ...]
    skipped: tuple[tuple[str, str], ...]
    sha256: str

    @property
    def units(self) -> int:
        return sum(len(d.units) for d in self.decisions)


# -- §3 text ------------------------------------------------------------------

def _dropped(el) -> bool:
    return el.tag in DROPPED or (el.tag == "a" and el.get("href") is not None)


def _flow(el, out: list) -> None:
    """Every text node under ``el`` in document order (spec §3.1): a dropped
    subtree contributes nothing — not its text, not its descendants', not
    rule 2's boundary spaces — while its tail still joins the parent's
    flow; every element outside INLINE puts one space before and after
    its content."""
    if _dropped(el):
        return
    block = el.tag not in INLINE
    if block:
        out.append(" ")
    if el.text:
        out.append(el.text)
    for child in el:
        _flow(child, out)
        if child.tail:
            out.append(child.tail)
    if block:
        out.append(" ")


def normalize(text: str) -> str:
    """Rule 3: runs of Unicode White_Space collapsed to one U+0020, none
    leading or trailing. ``str.split()`` is the conforming implementation
    here (its extra code points cannot occur in well-formed XML 1.0)."""
    return " ".join(text.split())


def text_of(el) -> str:
    if el is None:
        return ""
    out: list = []
    _flow(el, out)
    return normalize("".join(out))


def header_value(root, name: str) -> str:
    """A ``#PCDATA`` header element's text with leading and trailing
    White_Space removed; missing, empty or whitespace-only reads as ``""``.
    Inner runs are KEPT — the reading of the reference extractor that
    generated the fixture and of gsj-next's parser; spec §3.1's last
    paragraph says inner runs collapse too, which contradicts §5.2/§7.3's
    "verbatim" on exactly two files of the March 2026 drop (a doubled
    space inside an Aktenzeichen — CP-79 finding, wishlist 75): the
    implementation follows the executable reading until the spec picks."""
    return (root.findtext(name) or "").strip()


# -- §4 rows and units -------------------------------------------------------

def rows_of(section) -> list:
    """The section's rows: its ``<dl>`` descendants with no ``<dl>`` ancestor
    inside the section, in document order."""
    rows: list = []
    stack = [(child, False) for child in reversed(list(section))]
    while stack:
        el, inside = stack.pop()
        if el.tag == "dl":
            if not inside:
                rows.append(el)
            inside = True
        stack.extend((child, inside) for child in reversed(list(el)))
    return rows


def _live_paragraphs(el):
    """``<p>`` descendants of ``el`` outside every dropped subtree."""
    if _dropped(el):
        return
    if el.tag == "p":
        yield el
    for child in el:
        yield from _live_paragraphs(child)


def parse_row(dl) -> tuple[int | None, str, bool]:
    """(number or None, text, indented) for one row (spec §4.1)."""
    dt = next((c for c in dl if c.tag == "dt"), None)
    dd = next((c for c in dl if c.tag == "dd"), None)
    number = None
    if dt is not None:
        for a in dt.iter("a"):
            match = ANCHOR_RE.fullmatch(a.get("name") or "")
            if match and int(match.group(1)) >= 1:
                number = int(match.group(1))
                break
    text = text_of(dd)
    indented = dd is not None and any(
        "margin-left" in (p.get("style") or "") and text_of(p)
        for p in _live_paragraphs(dd))
    return number, text, indented


def units_of_section(name: str, section, anomalies: list | None = None,
                     numbers: list | None = None) -> list[Unit]:
    """Spec §4.2 (anchored rows) and §4.4 (a section without anchors).
    ``anomalies`` collects this section's reportable oddities (§2.3);
    ``numbers`` collects every anchored row's number, in order, for the
    decision-global numbering check ``parse_decision`` runs (§5.4:
    numbering runs across sections, so contiguity is a decision's
    property, not a section's)."""
    dls = rows_of(section)
    rows = [parse_row(dl) for dl in dls]
    if anomalies is not None:
        for dl in dls:
            dt = next((c for c in dl if c.tag == "dt"), None)
            for a in (dt.iter("a") if dt is not None else ()):
                value = a.get("name") or ""
                match = ANCHOR_RE.fullmatch(value)
                if value.startswith("rd_") and not (match and int(match.group(1)) >= 1):
                    anomalies.append(f"{name}: <a name={value!r}> is not an "
                                     f"anchor — the row is unanchored")
    if numbers is not None:
        numbers.extend(number for number, _, _ in rows if number is not None)
    anchored = [i for i, (number, _, _) in enumerate(rows) if number is not None]
    if not anchored:
        texts = [text for _, text, _ in rows if text]
        return [Unit(name, None, "\n".join(texts))] if texts else []
    last = anchored[-1]
    prefix: list[str] = []
    open_unit: list | None = None       # [rn, parts]
    walked: list[list] = []
    for i, (number, text, indented) in enumerate(rows):
        if number is not None:
            open_unit = [number, prefix + ([text] if text else [])]
            prefix = []
            walked.append(open_unit)
        elif not text:
            continue                    # spacer rows, dropped-only rows
        elif open_unit is None:
            prefix.append(text)         # before the first anchor: prefixed
        elif i > last and not indented:
            continue                    # after the last anchor, plain: dropped
        else:
            open_unit[1].append(text)   # between anchors, or an indented tail
    units: list[Unit] = []
    for number, parts in walked:
        text = "\n".join(parts)
        if text:
            units.append(Unit(name, number, text))
        elif anomalies is not None:
            anomalies.append(f"{name}: Randnummer {number} has no text — not produced")
    return units


def numbering_anomaly(numbers: list[int]) -> str | None:
    """Spec §2.3's first row, decision-global (§5.4): the anchored rows'
    numbers in document order across every section must be exactly
    ``1..K``; a duplicate (two units share an ``rn`` — the citation
    ``dec:<doknr>:rn:<N>`` is then ambiguous, §5.4) is named as such, any
    other departure (a gap, a restart, a start at 2 or 3) as
    non-contiguous."""
    if not numbers:
        return None
    seen: set[int] = set()
    duplicates = sorted({n for n in numbers if n in seen or seen.add(n)})
    if duplicates:
        return f"duplicate Randnummer numbers {duplicates} (a citation to one of them is ambiguous)"
    if numbers != list(range(1, len(numbers) + 1)):
        return (f"Randnummer numbering not contiguous 1..K: {len(numbers)} anchors "
                f"from {numbers[0]} to {max(numbers)}")
    return None


def _text_outside_rows(section) -> bool:
    """Spec §4.6: bare text in a section that no ``<dl>`` contains."""
    def walk(el) -> bool:
        if el.tag == "dl" or _dropped(el):
            return False
        if (el.text or "").strip():
            return True
        for child in el:
            if walk(child) or (child.tail or "").strip():
                return True
        return False
    return walk(section)


# -- §2.2 a conforming file, §5 identity ------------------------------------

def parse_decision(path: str | os.PathLike) -> Decision:
    """One file → one Decision; ``DecisionError`` names why a file does not
    conform (spec §2.2)."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise DecisionError(f"not well-formed XML ({error})") from None
    if root.tag != "dokument":
        raise DecisionError(f"root element is <{root.tag}>, not <dokument>")
    doknr = header_value(root, "doknr")
    if not DOKNR_RE.fullmatch(doknr):
        raise DecisionError(f"doknr {doknr!r} is not [A-Z]{{4}}[0-9]{{9}}")
    match = FILENAME_RE.fullmatch(path.name)
    if match is None or match.group(1) != doknr:
        raise DecisionError(f"filename {path.name!r} is not jb-{doknr}.xml")
    date = header_value(root, "entsch-datum")
    if not DATE_RE.fullmatch(date) or not date.isascii():
        raise DecisionError(f"entsch-datum {date!r} is not eight ASCII digits")
    court = header_value(root, "gertyp")
    doktyp = header_value(root, "doktyp")
    if not court:
        raise DecisionError("gertyp is empty")
    if not doktyp:
        raise DecisionError("doktyp is empty")
    anomalies: list[str] = []
    numbers: list[int] = []
    units: list[Unit] = []
    for name in SECTIONS:
        section = root.find(name)
        if section is None:
            continue
        units.extend(units_of_section(name, section, anomalies, numbers))
        if _text_outside_rows(section):
            anomalies.append(f"{name}: text outside any row (not indexed)")
    if (anomaly := numbering_anomaly(numbers)) is not None:
        anomalies.append(anomaly)
    return Decision(
        file=path.name, sha256=hashlib.sha256(raw).hexdigest(),
        decision_id=doknr, aktenzeichen=header_value(root, "aktenzeichen"),
        ecli=header_value(root, "ecli") or None, court=court,
        date=f"{date[0:4]}-{date[4:6]}-{date[6:8]}", doktyp=doktyp,
        units=tuple(units), anomalies=tuple(anomalies))


def load_drop(directory: str | os.PathLike) -> Drop:
    """Every ``*.xml`` file of the directory in ascending filename order; a
    non-conforming file is skipped with its reason (the drop is never
    aborted for one bad file); of a duplicate ``doknr`` the first file is
    kept. The drop's sha256 covers the kept files' names and bytes."""
    directory = Path(directory)
    if not directory.is_dir():
        raise DecisionError(f"decisions.path {directory} is not a directory")
    decisions: list[Decision] = []
    skipped: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    digest = hashlib.sha256()
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".xml"):
            continue
        try:
            decision = parse_decision(directory / name)
        except DecisionError as error:
            skipped.append((name, str(error)))
            continue
        except OSError as error:
            skipped.append((name, f"unreadable ({error})"))
            continue
        if decision.decision_id in seen:
            skipped.append((name, f"duplicate doknr {decision.decision_id} "
                                  f"(kept {seen[decision.decision_id]})"))
            continue
        seen[decision.decision_id] = name
        decisions.append(decision)
        digest.update(f"{name}\n{decision.sha256}\n".encode())
    return Drop(path=str(directory), decisions=tuple(decisions),
                skipped=tuple(skipped), sha256=digest.hexdigest())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:               # a drop directory, or one file
        target = Path(sys.argv[1])
        if target.is_file():
            docs = [parse_decision(target)]
        else:
            drop = load_drop(target)
            docs = list(drop.decisions)
            for name, reason in drop.skipped:
                print(f"REFUSED {name}: {reason}")
            print(f"{len(docs)} decisions, {len(drop.skipped)} refused, "
                  f"{drop.units} units, sha256 {drop.sha256}")
        for d in docs:
            print(d.file, d.header(), len(d.units), "units", list(d.anomalies))
            for u in d.units:
                print(f"   {u.section:22s} rn={u.rn!s:5s} {len(u.text):6d} chars  {u.text[:70]!r}")
    else:
        for d in decisions_corpus():
            print(f"{d['decision_id']}  [{d['court']} {d['year']}]  {d['text']}")
