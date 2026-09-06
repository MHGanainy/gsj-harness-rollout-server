"""CP-88 (corpus-contract v3, ADR-0038): `decisions/` as corpus data — the
root entry, `validate`'s §2.2 refusals and §2.3 anomaly reports, the
census-only `decisions.lock.json`, `verify`'s tree-vs-lock and lock-vs-served
comparisons, the scaffold's empty directory, and the estate tool's default
mount with `--decisions-dir` as the override (both present = a refusal).

The unit rule the pipeline carries is a port of the service's parser; the
first tests pin it to the conformance fixture (docs/decisions-surface/,
spec §10.2: unit for unit, byte for byte) and to the service's own module,
so the two implementations cannot drift apart silently."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_corpus

import ingest_corpus as ic

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "docs" / "decisions-surface"
SERVICE_PARSER = REPO / "estate" / "mcp-service" / "gsj_mcp_service" / "decisions.py"
ESTATE = REPO / "estate" / "estate.py"
# the demo repo's thirty synthetic rii decisions (CP-81): a sibling
# checkout, present on the operator's workstation, absent in CI — the
# tracked six-file fixture carries the same proof
THIRTY = Path.home() / "mg" / "workspace" / "gsj-rollout-demo" / "corpus-synthetic-decisions"

sys.path.insert(0, str(REPO / "estate"))
import estate as est  # noqa: E402


# ----------------------------------------------------------- fixtures

def row(number: int | None, text: str, *, name: str | None = None,
        indented: bool = False) -> str:
    anchor = (f'<a name="{name}"/>' if name is not None
              else f'<a name="rd_{number}"/>' if number is not None else "")
    style = ' style="margin-left:36pt"' if indented else ""
    return f"<dl><dt>{anchor}</dt><dd><p{style}>{text}</p></dd></dl>"


def decision_xml(doknr: str = "KORE000000001", *, date: str = "20200102",
                 gertyp: str = "BGH", doktyp: str = "Beschluss", ecli: str = "",
                 sections: dict[str, str] | None = None, root: str = "dokument",
                 elements: tuple[str, ...] | None = None) -> str:
    """A minimal rii-dok v1 file: the 26 elements in DTD order (or the
    sequence given), the body sections as given (default: a tenor row)."""
    sections = {"tenor": row(None, "Die Beschwerde wird verworfen.")} \
        if sections is None else sections
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', f"<{root}>"]
    for name in (ic.DECISION_DTD_ELEMENTS if elements is None else elements):
        body = {"doknr": doknr, "ecli": ecli, "gertyp": gertyp, "doktyp": doktyp,
                "entsch-datum": date, "aktenzeichen": "I ZR 1/20",
                "region": "<abk>DEU</abk><long>Bundesrepublik Deutschland</long>",
                "identifier": f"https://example.invalid/?docid=jb-{doknr}",
                "coverage": "Deutschland", "language": "deutsch",
                "publisher": "BMJV", "accessRights": "public"}.get(name, "")
        body = sections.get(name, body)
        parts.append(f"<{name}>{body}</{name}>")
    parts.append(f"</{root}>")
    return "\n".join(parts) + "\n"


def write_drop(corpus: Path, files: dict[str, str]) -> Path:
    ddir = corpus / ic.DECISIONS_DIR
    ddir.mkdir(exist_ok=True)
    for name, text in files.items():
        (ddir / name).write_text(text, encoding="utf-8")
    return ddir


def copy_fixture(corpus: Path) -> Path:
    ddir = corpus / ic.DECISIONS_DIR
    ddir.mkdir(exist_ok=True)
    for path in sorted(FIXTURE.glob("jb-*.xml")):
        shutil.copyfile(path, ddir / path.name)
    return ddir


def rows_of(out: str, scope: str = "(decisions)") -> list[str]:
    return [line for line in out.splitlines() if line.startswith(scope)]


def drop_sha256(ddir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(ddir.iterdir()):
        if path.suffix == ".xml":
            digest.update(f"{path.name}\n{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    return digest.hexdigest()


_SERVICE = None


def service_parser():
    """The frozen service parser, loaded by path once — without writing
    bytecode under estate/mcp-service/ (a cold CI checkout has no cache)."""
    global _SERVICE
    if _SERVICE is None:
        spec = importlib.util.spec_from_file_location("svc_decisions", SERVICE_PARSER)
        module = importlib.util.module_from_spec(spec)
        sys.modules["svc_decisions"] = module
        was = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = was
        _SERVICE = module
    return _SERVICE


# ------------------------------------------- the port, pinned two ways

def test_port_reproduces_the_conformance_fixture_unit_for_unit():
    """Spec §10.2 at level 2: the same units, in order, with the same
    section, rn and text byte for byte; ecli present for three files and
    absent for three; 62 units = 50 Randnummern + 12 section units."""
    expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    assert expected["surface_version"] == ic.DECISION_SURFACE_VERSION
    records = []
    for document in expected["documents"]:
        record = ic.parse_decision_file(FIXTURE / document["file"])
        assert [list(u) for u in record.units] == \
            [[u["section"], u["rn"], u["text"]] for u in document["units"]], document["file"]
        assert record.doknr == document["metadata"]["decision_id"]
        assert record.date == document["metadata"]["date"]
        assert (record.ecli is not None) == ("ecli" in document["metadata"])
        assert record.anomalies == ()
        records.append(record)
    census = ic.decisions_census(records, "x")
    assert (census.files, census.units, census.randnummer_units,
            census.section_units, census.ecli) == (6, 62, 50, 12, 3)
    assert (census.date_min, census.date_max) == ("2010-06-01", "2023-11-09")


def test_port_agrees_with_the_service_parser_over_the_fixture():
    """The two implementations of spec §3–§4 — the service's (the level-2
    one CP-79 proved) and this port — produce the same units, header
    fields, anomaly messages and drop hash for the same files."""
    svc = service_parser()
    for path in sorted(FIXTURE.glob("jb-*.xml")):
        ours, theirs = ic.parse_decision_file(path), svc.parse_decision(path)
        assert [list(u) for u in ours.units] == \
            [[u.section, u.rn, u.text] for u in theirs.units], path.name
        assert (ours.doknr, ours.date, ours.ecli, ours.sha256) == \
            (theirs.decision_id, theirs.date, theirs.ecli, theirs.sha256)
        assert [m for _, m in ours.anomalies] == list(theirs.anomalies)
    assert svc.load_drop(FIXTURE).sha256 == drop_sha256(FIXTURE)


def test_port_and_service_report_the_same_anomalies(tmp_path):
    """Spec §2.3's tolerated shapes, one file each: the port's messages for
    the kinds the service names are the service's, verbatim."""
    svc = service_parser()
    ddir = write_drop(tmp_path, {
        "jb-KORE000000001.xml": decision_xml("KORE000000001", sections={
            "gruende": row(1, "Eins.") + row(3, "Drei.") + row(3, "Nochmal drei.")}),
        "jb-KORE000000002.xml": decision_xml("KORE000000002", sections={
            "gruende": row(1, "Eins.") + row(None, "Unverankert.", name="rd_")}),
        "jb-KORE000000003.xml": decision_xml("KORE000000003", sections={
            "gruende": "<div>Bare text outside any row.</div>" + row(1, "Eins.")}),
        "jb-KORE000000004.xml": decision_xml("KORE000000004", sections={
            "gruende": row(1, "Eins.") + row(2, "")}),
        "jb-KORE000000005.xml": decision_xml("KORE000000005", sections={
            "gruende": row(2, "Zwei.") + row(4, "Vier.")}),
        # spec §3.1 rule 2 (the inline set glues, a block separates) and
        # §4.1 (rd_0 is not an anchor): shapes the six-file fixture does
        # not contain — the service module is the oracle
        "jb-KORE000000006.xml": decision_xml("KORE000000006", sections={
            "gruende": row(None, "", name="rd_0") + row(1, "Abs. 1<sup>a</sup> und <em>x</em>y"
                                                        "<strong>z</strong><sub>2</sub>, <span>s</span>"
                                                        "<div>block</div>t<table><tr><td>gone</td></tr></table>")
            + row(2, 'vor<img src="b.jpg"/>bild <a href="bild1.jpg"><br/><span>Abbildung</span></a> nach')}),
    })
    for path in sorted(ddir.glob("jb-*.xml")):
        ours = ic.parse_decision_file(path)
        theirs = svc.parse_decision(path)
        assert [m for k, m in ours.anomalies
                if k not in ("anchorless_reasoning_section", "title_only")] == \
            list(theirs.anomalies), path.name
        assert [list(u) for u in ours.units] == \
            [[u.section, u.rn, u.text] for u in theirs.units], path.name
    six = ic.parse_decision_file(ddir / "jb-KORE000000006.xml")
    assert [u[1] for u in six.units] == [1, 2]          # rd_0 opened no unit
    assert six.units[0][2] == "Abs. 1a und xyz2, s block t"
    assert six.units[1][2] == "vorbild nach"


@pytest.mark.skipif(not THIRTY.is_dir(), reason="the demo checkout's thirty are not beside this repo")
def test_the_demos_thirty_census_is_cp79s_313_244_69():
    """CP-79/CP-81 measured the demo's thirty at 313 units = 244 Randnummern
    + 69 section units under the service; the lock's census must be the
    parser's, and the drop hash the one both estates served at CP-82."""
    records = [ic.parse_decision_file(p) for p in sorted(THIRTY.glob("jb-*.xml"))]
    census = ic.decisions_census(records, drop_sha256(THIRTY))
    assert (census.files, census.units, census.randnummer_units, census.section_units) == \
        (30, 313, 244, 69)
    assert census.sha256 == "b414c6709a5b7d0daf4505d2ed5bdd5fcadf325e5401e0dd34ae9b76d13eaaa4"
    assert census.anomalies == {} and census.files_with_anomalies == 0


# ------------------------------------------------------------ validate

def test_a_corpus_without_decisions_is_the_v2_corpus(corpus_root, capsys):
    """No decisions/ — no row, no lock, nothing new: the contract's v2
    behaviour is what a corpus gets by default."""
    corpus = ic.phase_validate(corpus_root)
    assert corpus is not None and corpus.decisions is None
    assert rows_of(capsys.readouterr().out) == []


def test_an_empty_decisions_dir_is_legal_and_means_no_decisions(corpus_root, capsys):
    """The scaffold's README-only directory: legal, said out loud, no lock."""
    ddir = corpus_root / ic.DECISIONS_DIR
    ddir.mkdir()
    (ddir / ic.DECISIONS_README).write_text("# decisions/\n", encoding="utf-8")
    corpus = ic.phase_validate(corpus_root)
    assert corpus is not None and corpus.decisions is None
    (line,) = rows_of(capsys.readouterr().out)
    assert "PASS" in line and "empty" in line and "synthetic 30" in line


def test_a_corpus_with_decisions_validates_and_reports_the_census(corpus_root, capsys):
    copy_fixture(corpus_root)
    corpus = ic.phase_validate(corpus_root)
    out = capsys.readouterr().out
    assert corpus is not None and corpus.decisions is not None
    assert "== validate: PASS" in out
    (line,) = rows_of(out)
    assert "6 files, 62 units (50 Randnummern + 12 section units)" in line
    assert "3 with an ECLI" in line and "2010-06-01..2023-11-09" in line
    assert "anomalies 0 in 0 file(s)" in line
    assert corpus.decisions.sha256 == drop_sha256(corpus_root / ic.DECISIONS_DIR)


def test_the_root_entry_is_admitted_and_its_type_checked(corpus_root, capsys):
    """CP-71's root strictness admits the eighth name; a FILE called
    decisions is refused naming the contract."""
    (corpus_root / ic.DECISIONS_DIR).write_text("not a directory", encoding="utf-8")
    assert ic.phase_validate(corpus_root) is None
    out = capsys.readouterr().out
    assert "'decisions' at the corpus root must be a directory" in out
    assert "corpus-contract v3" in out
    (corpus_root / ic.DECISIONS_DIR).unlink()
    # the generated lock's name, as a directory, is refused like the others
    (corpus_root / ic.DECISIONS_LOCK_NAME).mkdir()
    assert ic.phase_validate(corpus_root) is None
    assert f"'{ic.DECISIONS_LOCK_NAME}' must be a generated file" in capsys.readouterr().out


@pytest.mark.parametrize("name, text, rule", [
    ("jb-KORE000000001.xml", "<dokument><doknr>KORE000000001</doknr>",
     "not well-formed XML"),
    ("jb-KORE000000001.xml", decision_xml(root="urteil"),
     "root element is <urteil>, not <dokument> (spec §2.2)"),
    ("jb-KORE000000001.xml",
     decision_xml(elements=tuple(e for e in ic.DECISION_DTD_ELEMENTS if e != "sonstlt")),
     "26 DTD elements in order (spec §2.1: doknr … accessRights); found 25 — missing ['sonstlt']"),
    ("jb-KORE000000001.xml",
     decision_xml(elements=("ecli", "doknr") + ic.DECISION_DTD_ELEMENTS[2:]),
     "out of order at position 1: found 'ecli', expected 'doknr'"),
    ("jb-KORE000000001.xml",
     decision_xml(elements=ic.DECISION_DTD_ELEMENTS + ("norm",)),
     "found 27 — the 26 in order, then unexpected ['norm']"),
    ("jb-KORE000000001.xml",
     decision_xml(elements=("doknr",) + ic.DECISION_DTD_ELEMENTS),
     "found 27 — duplicated element 'doknr'"),
    ("jb-KORE000000001.xml", decision_xml(doknr="KORE1"),
     "doknr 'KORE1' is not [A-Z]{4}[0-9]{9} (spec §2.2)"),
    ("jb-KORE000000001.xml", decision_xml(doknr="KORE000000002"),
     "filename 'jb-KORE000000001.xml' is not jb-KORE000000002.xml — the doknr must equal the filename stem"),
    ("jb-KORE000000001.xml", decision_xml(date="2020-01-02"),
     "entsch-datum '2020-01-02' is not eight ASCII digits (spec §2.2)"),
    ("jb-KORE000000001.xml", decision_xml(gertyp=""), "gertyp is empty (spec §2.2)"),
    ("jb-KORE000000001.xml", decision_xml(doktyp=" "), "doktyp is empty (spec §2.2)"),
])
def test_a_malformed_drop_is_refused_naming_the_file_and_the_rule(
        corpus_root, capsys, name, text, rule):
    write_drop(corpus_root, {name: text})
    assert ic.phase_validate(corpus_root) is None
    out = capsys.readouterr().out
    (line,) = [l for l in rows_of(out) if "FAIL" in l]
    assert f"decisions/{name}" in line and rule in line
    assert "== validate: FAIL" in out


@pytest.mark.parametrize("entry, kind, rule", [
    ("KORE000000001.xml", "file", "only jb-<doknr>.xml (doknr [A-Z]{4}[0-9]{9}, spec §2.1) and README.md are allowed"),
    ("jb-KORE000000001.xml.bak", "file", "unexpected entry 'jb-KORE000000001.xml.bak'"),
    ("notes.txt", "file", "unexpected entry 'notes.txt'"),
    ("2024", "dir", "unexpected directory '2024' — decisions/ is flat"),
])
def test_decisions_dir_is_flat_and_strict(corpus_root, capsys, entry, kind, rule):
    ddir = write_drop(corpus_root, {"jb-KORE000000001.xml": decision_xml()})
    if kind == "dir":
        (ddir / entry).mkdir()
    else:
        (ddir / entry).write_text("x", encoding="utf-8")
    assert ic.phase_validate(corpus_root) is None
    (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
    assert rule in line


def test_an_unreadable_decisions_dir_and_a_bottomless_file_are_refusals(corpus_root, capsys):
    """Neither escapes as a traceback: the directory listing and the walk
    are inside the refusal boundary (the review's P2/P3)."""
    import os
    if os.getuid() == 0:
        pytest.skip("root reads everything")
    ddir = write_drop(corpus_root, {"jb-KORE000000001.xml": decision_xml(sections={
        "tenor": row(None, "<span>" * 1500 + "x" + "</span>" * 1500)})})
    assert ic.phase_validate(corpus_root) is None
    (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
    assert "jb-KORE000000001.xml" in line and "nesting deeper than the walker" in line
    (ddir / "jb-KORE000000001.xml").unlink()
    ddir.chmod(0o000)
    try:
        assert ic.phase_validate(corpus_root) is None
        (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
        assert "decisions/" in line and "unreadable" in line
    finally:
        ddir.chmod(0o755)


def test_a_drop_with_one_bad_file_names_it_and_refuses_the_tree(corpus_root, capsys):
    """Every failure names the exact file; the good files are not a pass."""
    files = {p.name: p.read_text(encoding="utf-8") for p in FIXTURE.glob("jb-*.xml")}
    files["jb-KORE000000009.xml"] = decision_xml(doknr="KORE000000009", gertyp="")
    write_drop(corpus_root, files)
    assert ic.phase_validate(corpus_root) is None
    out = capsys.readouterr().out
    fails = [l for l in rows_of(out) if "FAIL" in l]
    assert len(fails) == 1 and "decisions/jb-KORE000000009.xml" in fails[0]
    assert "gertyp is empty" in fails[0]


def test_anomalies_are_reported_not_refused_and_counted(corpus_root, capsys):
    """Spec §2.3: none of these refuses a file; each is a PASS row naming
    the file and the anomaly, and the census counts them by kind."""
    write_drop(corpus_root, {
        "jb-KORE000000001.xml": decision_xml("KORE000000001", sections={
            "gruende": row(1, "Eins.") + row(3, "Drei.") + row(3, "Nochmal drei.")}),
        "jb-KORE000000002.xml": decision_xml("KORE000000002", sections={
            "gruende": row(1, "Eins.") + row(None, "Unverankert.", name="rd_")}),
        "jb-KORE000000003.xml": decision_xml("KORE000000003", sections={
            "gruende": "<div>Bare text outside any row.</div>" + row(1, "Eins.")}),
        "jb-KORE000000004.xml": decision_xml("KORE000000004", sections={
            "gruende": row(1, "Eins.") + row(2, "")}),
        "jb-KORE000000005.xml": decision_xml("KORE000000005", sections={
            "gruende": row(2, "Zwei.") + row(4, "Vier.")}),
        "jb-KORE000000006.xml": decision_xml("KORE000000006", sections={
            "gruende": row(None, "Gründe ohne Anker.")}),
        "jb-KORE000000007.xml": decision_xml("KORE000000007", sections={
            "titelzeile": row(None, "Nur ein Titel"), "tenor": ""}),
    })
    corpus = ic.phase_validate(corpus_root)
    out = capsys.readouterr().out
    assert corpus is not None and "== validate: PASS" in out
    anomaly_rows = [l for l in rows_of(out) if "anomaly (reported, not refused — spec §2.3)" in l]
    assert all("PASS" in l for l in anomaly_rows) and len(anomaly_rows) == 7
    assert any("jb-KORE000000001.xml" in l and "duplicate Randnummer numbers [3]" in l for l in anomaly_rows)
    assert any("jb-KORE000000002.xml" in l and "<a name='rd_'> is not an anchor" in l for l in anomaly_rows)
    assert any("jb-KORE000000003.xml" in l and "text outside any row" in l for l in anomaly_rows)
    assert any("jb-KORE000000004.xml" in l and "Randnummer 2 has no text" in l for l in anomaly_rows)
    assert any("jb-KORE000000005.xml" in l and "not contiguous 1..K: 2 anchors from 2 to 4" in l for l in anomaly_rows)
    assert any("jb-KORE000000006.xml" in l and "text and no anchors — one section unit, rn null" in l for l in anomaly_rows)
    assert any("jb-KORE000000007.xml" in l and "a title and nothing else" in l for l in anomaly_rows)
    census = corpus.decisions
    assert census.anomalies == {
        "duplicate_randnummer": 1, "non_anchor_rd_name": 1, "text_outside_rows": 1,
        "randnummer_without_text": 1, "non_contiguous_randnummer": 1,
        "anchorless_reasoning_section": 1, "title_only": 1}
    assert census.files_with_anomalies == 7 and census.files == 7
    # the units the rule produces for these shapes (spec §4): the duplicate
    # number yields two units, the empty body none, the anchorless section one
    assert (census.units, census.randnummer_units, census.section_units) == (10, 8, 2)


def test_only_and_quiet_phases_still_validate_the_decisions(corpus_root, capsys):
    """The drop is corpus-wide: --only limits the case work, never the
    decisions check, and a quiet phase still refuses a bad file."""
    write_drop(corpus_root, {"jb-KORE000000001.xml": decision_xml(doktyp="")})
    assert ic.phase_validate(corpus_root, only=["case_a"], quiet=True) is None
    assert "doktyp is empty" in capsys.readouterr().out


# --------------------------------------------------------------- lock

def test_scaffold_writes_the_census_lock_and_leaves_the_corpus_lock_alone(
        corpus_root, estate, tmp_path):
    """The lock: the drop's hash and census, no per-file rows, byte-
    deterministic; corpus.lock.json gains no key and its SHAs are the ones
    the same tree yields with no decisions/ at all."""
    twin = make_corpus(tmp_path / "twin")
    assert ic.main(["scaffold", "--corpus", str(twin), "--base-url", estate]) == 0
    twin_lock = (twin / ic.LOCK_NAME).read_bytes()
    assert not (twin / ic.DECISIONS_LOCK_NAME).exists()

    copy_fixture(corpus_root)
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert (corpus_root / ic.LOCK_NAME).read_bytes() == twin_lock
    lock = json.loads((corpus_root / ic.DECISIONS_LOCK_NAME).read_text(encoding="utf-8"))
    assert set(lock) == {"_comment", "surface_version", "sha256", "files", "units",
                         "randnummer_units", "section_units", "ecli", "dates",
                         "anomalies", "files_with_anomalies"}
    assert lock["surface_version"] == 1
    assert lock["sha256"] == drop_sha256(corpus_root / ic.DECISIONS_DIR)
    assert (lock["files"], lock["units"], lock["randnummer_units"], lock["section_units"],
            lock["ecli"]) == (6, 62, 50, 12, 3)
    assert lock["dates"] == {"min": "2010-06-01", "max": "2023-11-09"}
    assert lock["anomalies"] == {} and lock["files_with_anomalies"] == 0
    assert "jb-" not in json.dumps({k: v for k, v in lock.items() if k != "_comment"})
    first = (corpus_root / ic.DECISIONS_LOCK_NAME).read_bytes()
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert (corpus_root / ic.DECISIONS_LOCK_NAME).read_bytes() == first


def test_an_anomalous_drop_locks_its_counts_and_verifies(corpus_root, estate, capsys):
    write_drop(corpus_root, {
        "jb-KORE000000001.xml": decision_xml("KORE000000001", sections={
            "gruende": row(1, "Eins.") + row(3, "Drei.") + row(3, "Nochmal drei.")}),
        "jb-KORE000000002.xml": decision_xml("KORE000000002", sections={
            "gruende": row(2, "Zwei.") + row(3, "") + "<div>Bare text.</div>"}),
    })
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    lock = json.loads((corpus_root / ic.DECISIONS_LOCK_NAME).read_text(encoding="utf-8"))
    assert lock["anomalies"] == {"duplicate_randnummer": 1, "non_contiguous_randnummer": 1,
                                 "randnummer_without_text": 1, "text_outside_rows": 1}
    assert lock["files_with_anomalies"] == 2 and lock["files"] == 2
    assert (lock["units"], lock["randnummer_units"], lock["section_units"]) == (4, 4, 0)
    first = (corpus_root / ic.DECISIONS_LOCK_NAME).read_bytes()
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert (corpus_root / ic.DECISIONS_LOCK_NAME).read_bytes() == first
    assert ic.main(["taskbank", "--corpus", str(corpus_root)]) == 0
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 0
    assert "2 files, 4 units" in capsys.readouterr().out


def test_dry_run_writes_no_decisions_lock(corpus_root):
    copy_fixture(corpus_root)
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--dry-run"]) == 0
    assert not (corpus_root / ic.DECISIONS_LOCK_NAME).exists()


def test_scaffold_removes_a_stale_decisions_lock(corpus_root, estate, capsys):
    copy_fixture(corpus_root)
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    shutil.rmtree(corpus_root / ic.DECISIONS_DIR)
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert not (corpus_root / ic.DECISIONS_LOCK_NAME).exists()
    assert "decisions lock removed" in capsys.readouterr().out


# ------------------------------------------------------------- verify

def health_for(corpus_root: Path, **decisions) -> dict:
    doc = {"state": "ready", "fingerprint": "f" * 64, "index_reused": True,
           "cases": {"case_a": {"pages": 2, "timesteps": [1, 2]},
                     "case_b": {"pages": 3, "timesteps": [2, 3]}}}
    if decisions:
        doc["decisions_drop"] = decisions
    return doc


def scaffold_and_bank(corpus_root: Path, estate: str) -> None:
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert ic.main(["taskbank", "--corpus", str(corpus_root)]) == 0


def test_verify_passes_a_locked_drop_the_service_serves(corpus_root, estate, monkeypatch, capsys):
    copy_fixture(corpus_root)
    scaffold_and_bank(corpus_root, estate)
    sha = drop_sha256(corpus_root / ic.DECISIONS_DIR)
    monkeypatch.setattr(ic, "get_health", lambda url, timeout=10.0: health_for(
        corpus_root, sha256=sha, files=6, units=62, pieces=70, skipped=0, surface_version=1))
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--mcp-url", "http://mcp.invalid"]) == 0
    out = capsys.readouterr().out
    lines = rows_of(out)
    assert any("lock" in l and "6 files, 62 units" in l and "match the lock" in l for l in lines)
    assert any("mcp" in l and "served drop matches the lock: 6 files, 62 units" in l for l in lines)


def test_verify_catches_a_decision_changed_after_scaffold(corpus_root, estate, capsys):
    copy_fixture(corpus_root)
    scaffold_and_bank(corpus_root, estate)
    path = corpus_root / ic.DECISIONS_DIR / "jb-KORE613012010.xml"
    path.write_text(path.read_text(encoding="utf-8").replace("Beschluss", "Urteil"),
                    encoding="utf-8")
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 1
    (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
    assert "the tree's drop differs from the lock: sha256" in line
    assert "re-run scaffold" in line


def test_verify_names_a_missing_or_stale_decisions_lock(corpus_root, estate, capsys):
    copy_fixture(corpus_root)
    scaffold_and_bank(corpus_root, estate)
    (corpus_root / ic.DECISIONS_LOCK_NAME).unlink()
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 1
    assert f"{ic.DECISIONS_LOCK_NAME} missing — run the scaffold phase" in capsys.readouterr().out
    # the lock back, the drop gone: stale
    assert ic.main(["scaffold", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    shutil.rmtree(corpus_root / ic.DECISIONS_DIR)
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 1
    assert f"stale {ic.DECISIONS_LOCK_NAME}" in capsys.readouterr().out


def test_verify_fails_when_the_service_serves_another_drop_or_none(
        corpus_root, estate, monkeypatch, capsys):
    copy_fixture(corpus_root)
    scaffold_and_bank(corpus_root, estate)
    monkeypatch.setattr(ic, "get_health", lambda url, timeout=10.0: health_for(
        corpus_root, sha256="0" * 64, files=30, units=313, pieces=317, skipped=0,
        surface_version=1))
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--mcp-url", "http://mcp.invalid"]) == 1
    (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
    assert "served drop != the lock" in line
    assert "sha256 served 0000000000000000…" in line and "files served 30 != lock 6" in line
    monkeypatch.setattr(ic, "get_health", lambda url, timeout=10.0: health_for(corpus_root))
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--mcp-url", "http://mcp.invalid"]) == 1
    (line,) = [l for l in rows_of(capsys.readouterr().out) if "FAIL" in l]
    assert "serves the synthetic decisions, not the corpus's decisions/" in line


def test_verify_without_decisions_tolerates_a_flag_route_drop(corpus_root, estate, monkeypatch, capsys):
    """The CP-79 route: a corpus with no decisions/ served beside a
    --decisions-dir drop verifies, and says whose drop it is."""
    scaffold_and_bank(corpus_root, estate)
    monkeypatch.setattr(ic, "get_health", lambda url, timeout=10.0: health_for(
        corpus_root, sha256="b" * 64, files=30, units=313, pieces=317, skipped=0,
        surface_version=1))
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--mcp-url", "http://mcp.invalid"]) == 0
    lines = rows_of(capsys.readouterr().out)
    assert any("SKIPPED (no decisions/ in the corpus" in l for l in lines)
    assert any("a drop from outside the corpus (estate.py up --decisions-dir): 30 files" in l
               for l in lines)


def test_verify_prints_no_decisions_row_for_a_plain_v2_corpus(corpus_root, estate, monkeypatch, capsys):
    """No decisions/, no lock, a service serving the synthetic 30: the v2
    table, unchanged — the rows appear only when something decisions-
    related exists (a lock, a drop in the tree, or a served drop)."""
    scaffold_and_bank(corpus_root, estate)
    monkeypatch.setattr(ic, "get_health", lambda url, timeout=10.0: health_for(corpus_root))
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--mcp-url", "http://mcp.invalid"]) == 0
    assert rows_of(capsys.readouterr().out) == []
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 0
    assert rows_of(capsys.readouterr().out) == []


def test_verify_skips_the_served_check_with_the_reason(corpus_root, estate, capsys):
    copy_fixture(corpus_root)
    scaffold_and_bank(corpus_root, estate)
    assert ic.main(["verify", "--corpus", str(corpus_root), "--base-url", estate,
                    "--skip-ingest"]) == 0
    lines = rows_of(capsys.readouterr().out)
    assert any("match the lock" in l for l in lines)
    assert any("mcp" in l and "SKIPPED (--skip-ingest)" in l for l in lines)


def test_all_on_the_file_rail_with_decisions(corpus_root, estate, capsys):
    copy_fixture(corpus_root)
    assert ic.main(["all", "--corpus", str(corpus_root), "--base-url", estate]) == 0
    assert (corpus_root / ic.DECISIONS_LOCK_NAME).is_file()
    assert "== verify: PASS" in capsys.readouterr().out


# ------------------------------------------------- the staging corpus

def test_the_staging_corpus_carries_no_decisions_and_validates_unchanged(capsys):
    staging = REPO / "estate" / "corpus" / "staging"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (staging / ic.LOCK_NAME, staging / ic.TASKBANK_NAME)}
    corpus = ic.phase_validate(staging)
    assert corpus is not None and corpus.decisions is None
    assert rows_of(capsys.readouterr().out) == []
    assert not (staging / ic.DECISIONS_DIR).exists()
    assert not (staging / ic.DECISIONS_LOCK_NAME).exists()
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (staging / ic.LOCK_NAME, staging / ic.TASKBANK_NAME)}
    assert after == before


# ------------------------------------------------------ estate.py

def test_resolve_decisions_source_prefers_the_corpus_and_refuses_both(tmp_path):
    corpus_drop = tmp_path / "corpus" / "decisions"
    corpus_drop.mkdir(parents=True)
    (corpus_drop / "jb-KORE000000001.xml").write_text(decision_xml(), encoding="utf-8")
    beside = tmp_path / "corpus-decisions"
    beside.mkdir()
    (beside / "jb-KORE000000002.xml").write_text(decision_xml("KORE000000002"), encoding="utf-8")
    cd = est.corpus_decisions_dir(tmp_path / "corpus")
    assert cd == str(corpus_drop.resolve())
    assert est.resolve_decisions_source(cd, None) == (cd, "corpus")
    assert est.resolve_decisions_source(cd, "") == (cd, "corpus")
    assert est.resolve_decisions_source(None, None) == (None, "none")
    assert est.resolve_decisions_source(None, "") == (None, "none")
    assert est.resolve_decisions_source(None, str(beside)) == (str(beside.resolve()), "flag")
    # the corpus's own directory named by the flag is the corpus route, not two drops
    assert est.resolve_decisions_source(cd, cd) == (cd, "corpus")
    assert est.resolve_decisions_source(cd, str(corpus_drop)) == (cd, "corpus")
    with pytest.raises(est.DecisionsSourceConflict) as exc:
        est.resolve_decisions_source(cd, str(beside))
    text = str(exc.value)
    assert str(corpus_drop.resolve()) in text and str(beside) in text
    assert "WINS under corpus-contract v3" in text and "--decisions-dir ''" in text
    assert f"mv {corpus_drop.resolve()}" in text


def test_the_config_review_names_the_drops_source(tmp_path):
    drop = tmp_path / "decisions"
    drop.mkdir()
    (drop / "jb-KORE000000001.xml").write_text(decision_xml(), encoding="utf-8")
    doc = {"decisions": {"path": est.MCP_DECISIONS_MOUNT, "seed": 1, "corpus_size": 30}}
    corpus_route = est.mcp_config_review(doc, tmp_path / "c.yaml", str(drop), "corpus")
    flag_route = est.mcp_config_review(doc, tmp_path / "c.yaml", str(drop), "flag")
    assert "the corpus's own decisions/" in corpus_route and "1 .xml file(s)" in corpus_route
    assert "--decisions-dir, the override" in flag_route
    assert "--decisions-dir <host directory>" not in corpus_route   # the review's E8/D7
    synthetic = est.mcp_config_review({"decisions": {"seed": 1, "corpus_size": 30}}, tmp_path / "c.yaml")
    assert "synthetic" in synthetic


def test_corpus_decisions_dir_ignores_an_empty_or_readme_only_directory(tmp_path):
    corpus = tmp_path / "corpus"
    (corpus / "decisions").mkdir(parents=True)
    assert est.corpus_decisions_dir(corpus) is None
    (corpus / "decisions" / "README.md").write_text("# decisions/\n", encoding="utf-8")
    assert est.corpus_decisions_dir(corpus) is None
    (corpus / "decisions" / "jb-KORE000000001.xml").write_text(decision_xml(), encoding="utf-8")
    assert est.corpus_decisions_dir(corpus) == str((corpus / "decisions").resolve())
    assert est.corpus_decisions_dir(tmp_path / "nowhere") is None


def test_recorded_flag_replays_only_the_flag_route():
    """A pre-CP-88 record (no decisions_source) recorded the flag — replayed;
    a corpus-route record is re-resolved from the corpus, never replayed."""
    assert est.recorded_decisions_flag({}) is None
    assert est.recorded_decisions_flag({"decisions_dir": "/d"}) == "/d"
    assert est.recorded_decisions_flag({"decisions_dir": "/d", "decisions_source": "flag"}) == "/d"
    assert est.recorded_decisions_flag({"decisions_dir": "/c/decisions",
                                        "decisions_source": "corpus"}) is None
    assert est.recorded_decisions_flag({"decisions_dir": None, "decisions_source": "none"}) is None


def test_estate_scaffold_writes_an_empty_decisions_dir_that_validates(tmp_path, capsys):
    out = tmp_path / "my-corpus"
    proc = subprocess.run([sys.executable, str(ESTATE), "scaffold", "--out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "decisions/" in proc.stdout and "OPTIONAL" in proc.stdout
    readme = out / ic.DECISIONS_DIR / ic.DECISIONS_README
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "jb-<doknr>.xml" in text and "decisions.lock.json" in text and "synthetic 30" in text
    assert sorted(p.name for p in (out / ic.DECISIONS_DIR).iterdir()) == [ic.DECISIONS_README]
    assert ic.main(["validate", "--corpus", str(out)]) == 0
    out_text = capsys.readouterr().out
    assert "== validate: PASS" in out_text and "empty — no decisions" in out_text


def test_up_refuses_a_corpus_drop_and_a_flag_together_before_any_estate_work(
        tmp_path, monkeypatch, capsys):
    corpus = make_corpus(tmp_path / "corpus", estate_fields=False)
    write_drop(corpus, {"jb-KORE000000001.xml": decision_xml()})
    beside = tmp_path / "corpus-decisions"
    beside.mkdir()
    (beside / "jb-KORE000000002.xml").write_text(decision_xml("KORE000000002"), encoding="utf-8")
    monkeypatch.setattr(est, "RUNS", tmp_path / "runs")
    est.RUNS.mkdir()  # CP-90: reach the decisions check through a valid runs root

    def spent_work():
        pytest.fail("two drops reached Docker setup")

    monkeypatch.setattr(est, "check_docker", spent_work)
    args = argparse.Namespace(answers=None, defaults=True, corpus=str(corpus),
                              name="two-drops", mcp="create", decisions_dir=str(beside))
    with pytest.raises(SystemExit) as exc:
        est.cmd_up(args)
    assert exc.value.code == 1
    refusal = capsys.readouterr().err
    assert "two decisions drops for one estate" in refusal
    assert str((corpus / "decisions").resolve()) in refusal and str(beside) in refusal
    assert "WINS under corpus-contract v3" in refusal and "--decisions-dir ''" in refusal
    assert "found:" in refusal and "expected:" in refusal and "what to do:" in refusal
    assert not (tmp_path / "runs" / "two-drops").exists()


def test_up_refuses_a_recorded_flag_when_the_corpus_gains_decisions(tmp_path, monkeypatch, capsys):
    """The re-run shape: a run that recorded --decisions-dir, re-run after
    the operator moved the drop inside the corpus — refused, naming the
    '' that adopts the corpus's."""
    corpus = make_corpus(tmp_path / "corpus", estate_fields=False)
    write_drop(corpus, {"jb-KORE000000001.xml": decision_xml()})
    beside = tmp_path / "corpus-decisions"
    beside.mkdir()
    (beside / "jb-KORE000000002.xml").write_text(decision_xml("KORE000000002"), encoding="utf-8")
    monkeypatch.setattr(est, "RUNS", tmp_path / "runs")
    run = est.Run("rerun")
    run.dir.mkdir(parents=True)
    run.write_env()                      # an empty .env: the record's companion
    (run.dir / "run.json").write_text(json.dumps({
        "schema": 1, "run": "rerun", "created_at": "2026-09-01T00:00:00Z",
        "corpus": {"owner": "gsj-staging"},
        "forgejo": {"mode": "created", "url": "http://127.0.0.1:9"},
        "mcp": {"mode": "created", "url": "http://127.0.0.1:9"},
        "compose": {"mcp": {"image": est.MCP_IMAGE, "container": "x", "port": 9,
                            "data": "d", "config": "c", "read_env": "R",
                            "decisions_dir": str(beside)}}}), encoding="utf-8")
    monkeypatch.setattr(est, "check_docker", lambda: pytest.fail("reached Docker"))
    args = argparse.Namespace(answers=None, defaults=True, corpus=str(corpus), name="rerun",
                              mcp="create")
    with pytest.raises(SystemExit) as exc:
        est.cmd_up(args)
    assert exc.value.code == 1
    refusal = capsys.readouterr().err
    assert "two decisions drops" in refusal and "recorded by this run's earlier `up`" in refusal
