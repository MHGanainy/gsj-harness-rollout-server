#!/usr/bin/env python3
"""The reference extractor for the decisions-surface conformance fixture.

This script GENERATES ``expected.json`` from the fixture's source files by
applying the unit rule of ``docs/decisions-surface.md`` (§2.2, §3, §4, §5)
literally; it is the fixture's provenance, not an implementation of the
surface (no store, no embedding, no tool) and not part of the served
service. Standard library only. It lives beside the fixture so that a
later surface version can regenerate ``expected.json`` reproducibly and
so that a reader can check the spec's prose against one executable
reading of it. Written at CP-78; surface version 1.

Usage:
  reference_extractor.py fixture <out.json> <file.xml>...   # regenerate expected.json
  reference_extractor.py stats <out.json> [<dir>]           # unit census over a drop
"""
SURFACE_VERSION = 1
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from multiprocessing import Pool

ROOT = "decisions"  # the drop directory for `stats`; override with the third argument
SECTIONS = ("titelzeile", "leitsatz", "sonstosatz", "tenor", "tatbestand",
            "entscheidungsgruende", "gruende", "abwmeinung", "sonstlt")
INLINE = {"a", "em", "strong", "span", "sub", "sup"}
DROPPED = {"table", "img"}
ANCHOR = re.compile(r"rd_([0-9]+)")


def _dropped(el):
    """A dropped subtree: <table>, <img>, or an <a> carrying an href (the
    publisher's image-viewer link — UI chrome beside the dropped <img>)."""
    return el.tag in DROPPED or (el.tag == "a" and el.get("href") is not None)


def _flow(el, out):
    """Text nodes in document order; a dropped subtree contributes nothing
    at all — neither its content nor rule 2's boundary spaces (its tail
    still belongs to the parent); every other element outside INLINE is a
    block boundary — a space before and after its content."""
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


def text_of(el):
    """Whitespace-normalized text: runs of Unicode White_Space collapsed to
    one U+0020, none leading or trailing (Python's str.split())."""
    if el is None:
        return ""
    out = []
    _flow(el, out)
    return " ".join("".join(out).split())


def rows_of(section):
    """The section's rows: every <dl> that is not inside another <dl>, in
    document order."""
    rows = []

    def walk(el, inside):
        for child in el:
            if child.tag == "dl":
                if not inside:
                    rows.append(child)
                walk(child, True)
            else:
                walk(child, inside)
    walk(section, False)
    return rows


def _live_ps(el):
    """The <p> descendants of el that are not inside a dropped subtree."""
    if _dropped(el):
        return
    if el.tag == "p":
        yield el
    for ch in el:
        yield from _live_ps(ch)


def parse_row(dl):
    dt = next((c for c in dl if c.tag == "dt"), None)
    dd = next((c for c in dl if c.tag == "dd"), None)
    rn = None
    if dt is not None:
        for a in dt.iter("a"):
            m = ANCHOR.fullmatch(a.get("name") or "")
            if m and int(m.group(1)) >= 1:      # rd_0 is not an anchor (spec §4.1)
                rn = int(m.group(1))
                break
    text = text_of(dd)
    indented = dd is not None and any(
        "margin-left" in (p.get("style") or "") and text_of(p)
        for p in _live_ps(dd))
    return rn, text, indented


def units_of_section(name, section, stats=None):
    rows = [parse_row(dl) for dl in rows_of(section)]
    anchored = [i for i, (rn, _, _) in enumerate(rows) if rn is not None]
    units = []
    if not anchored:
        texts = [t for _, t, _ in rows if t]
        if texts:
            units.append({"section": name, "rn": None, "text": "\n".join(texts)})
            if stats is not None:
                stats["section_units"] += 1
        return units
    last = anchored[-1]
    prefix = []
    current = None
    for i, (rn, text, indented) in enumerate(rows):
        if rn is not None:
            current = {"section": name, "rn": rn, "_parts": prefix + ([text] if text else [])}
            prefix = []
            units.append(current)
            if stats is not None:
                stats["rn_units"] += 1
            continue
        if not text:
            continue
        if current is None:
            prefix.append(text)
            if stats is not None:
                stats["prefix_rows"] += 1
        elif i > last:
            if indented:
                current["_parts"].append(text)
                if stats is not None:
                    stats["tail_rows_kept"] += 1
            elif stats is not None:
                stats["tail_rows_dropped"] += 1
        else:
            current["_parts"].append(text)
            if stats is not None:
                stats["continuation_rows"] += 1
    out = []
    for u in units:
        text = "\n".join(u.pop("_parts"))
        if text:
            u["text"] = text
            out.append(u)
        elif stats is not None:
            stats["empty_rn_units_dropped"] += 1
    return out


def extract(path, stats=None):
    root = ET.parse(path).getroot()
    doknr = (root.findtext("doknr") or "").strip()
    date = (root.findtext("entsch-datum") or "").strip()
    meta = {"decision_id": doknr,
            "aktenzeichen": (root.findtext("aktenzeichen") or "").strip(),
            "court": (root.findtext("gertyp") or "").strip(),
            "date": f"{date[0:4]}-{date[4:6]}-{date[6:8]}",
            "doktyp": (root.findtext("doktyp") or "").strip()}
    ecli = (root.findtext("ecli") or "").strip()
    if ecli:
        meta["ecli"] = ecli
    units = []
    for name in SECTIONS:
        section = root.find(name)
        if section is not None:
            units.extend(units_of_section(name, section, stats))
    return {"file": os.path.basename(path), "metadata": meta, "units": units}


def _stats_one(name):
    stats = Counter()
    doc = extract(os.path.join(ROOT, name), stats)
    stats["docs"] += 1
    stats["units"] += len(doc["units"])
    if not doc["units"]:
        stats["docs_without_units"] += 1
    if all(u["rn"] is None for u in doc["units"]):
        stats["docs_without_rn_units"] += 1
    stats["unit_chars"] += sum(len(u["text"]) for u in doc["units"])
    for u in doc["units"]:
        stats[f"units_in_{u['section']}"] += 1
    return stats


def main():
    mode, out = sys.argv[1], sys.argv[2]
    if mode == "fixture":
        docs = [extract(p) for p in sys.argv[3:]]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"surface_version": SURFACE_VERSION,
                       "generated_by": "reference_extractor.py (CP-78)",
                       "documents": docs}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        for d in docs:
            print(d["file"], d["metadata"], len(d["units"]), "units")
            for u in d["units"]:
                print(f"   {u['section']:22s} rn={u['rn']!s:5s} {len(u['text']):5d} chars  {u['text'][:70]!r}")
    else:
        global ROOT
        if len(sys.argv) > 3:
            ROOT = sys.argv[3]
        total = Counter()
        names = sorted(f for f in os.listdir(ROOT) if f.endswith(".xml"))
        with Pool(10) as pool:
            for s in pool.imap_unordered(_stats_one, names, chunksize=64):
                total.update(s)
        json.dump(dict(total), open(out, "w"), indent=1, sort_keys=True)
        print(json.dumps(dict(total), indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
