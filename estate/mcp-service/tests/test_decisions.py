"""The decisions surface (CP-79, docs/decisions-surface.md v1): the parser
reproduces the conformance fixture byte for byte and handles — rather than
accidentally passes — the three rules the fixture's discriminator files
pin; a drop ingests through the batched builder into level-2 hits whose
shape, absent-vs-null discipline and order follow §7 and §8; the wrapper's
``k`` is clamped and echoed; a level-1 response is accepted by a level-2
consumer (§9.3); an existing store rebuilds nothing on upgrade, and a drop
re-embeds only the decisions collection (wishlist 61)."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET

import pytest
import yaml

from helpers import (
    REPO_ROOT,
    call_tool,
    canonical,
    free_port,
    make_state,
    mcp_roundtrip,
    mint_token,
    spawn_server,
    stop_server,
    write_config,
)

import gsj_mcp_service.index as index_module
import gsj_mcp_service.state as state_module
from gsj_mcp_service import decisions as D
from gsj_mcp_service.config import ConfigError, load_config
from gsj_mcp_service.index import (DECISIONS_FETCH_PER_K, RiiDecisionsIndex,
                                   corpus_fingerprint,
                                   read_collection_fingerprints, rii_pieces)

# The fixture is read where it lives (spec §0 says "copy it into the test
# tree"; inside the one repository that holds the canonical copy, reading
# it in place is the copy with zero drift — the roster suite reads pins/
# the same way).
FIXTURE = REPO_ROOT / "docs" / "decisions-surface"
EXPECTED = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
FILES = [entry["file"] for entry in EXPECTED["documents"]]
WITH_ECLI = {"jb-KORE303672022.xml", "jb-KORE202300077.xml", "jb-JURE160019189.xml"}
WITHOUT_ECLI = {"jb-KORE613012010.xml", "jb-KORE308052015.xml", "jb-JURE130006754.xml"}
# spec §9.1's one regular expression
CITATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])dec:([A-Z]{4}[0-9]{9})(?::rn:([1-9][0-9]*))?(?![A-Za-z0-9_]|:rn)")

REQUIRED_L2 = {"decision_id", "aktenzeichen", "court", "date", "doktyp",
               "rn", "section", "score", "text"}
REQUIRED_L1 = {"decision_id", "aktenzeichen", "court", "date", "doktyp",
               "score", "text"}


def _section(xml: str, name: str = "gruende"):
    """A body section element from an XHTML snippet."""
    return ET.fromstring(f"<{name}>{xml}</{name}>")


def _units(xml: str, name: str = "gruende") -> list[tuple[int | None, str]]:
    return [(u.rn, u.text) for u in D.units_of_section(name, _section(xml, name))]


# -- §10: the fixture, byte for byte ------------------------------------------

def test_expected_json_reproduced_byte_for_byte():
    """The acceptance test of the parser (spec §10.2): the six files →
    exactly the 62 units and header fields of expected.json — the same
    count, order, section, rn and text, byte for byte — serialized the
    way the reference extractor wrote it (the surface version and the
    generator line are the fixture's own header)."""
    documents = [D.parse_decision(FIXTURE / name).as_fixture_document()
                 for name in FILES]
    ours = {"surface_version": D.SURFACE_VERSION,
            "generated_by": EXPECTED["generated_by"], "documents": documents}
    rendered = (json.dumps(ours, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    assert EXPECTED["surface_version"] == D.SURFACE_VERSION
    assert rendered == (FIXTURE / "expected.json").read_bytes()
    assert sum(len(d["units"]) for d in documents) == 62
    assert [len(d["units"]) for d in documents] == [12, 1, 4, 29, 10, 6]
    for doc in documents:
        assert ("ecli" in doc["metadata"]) == (doc["file"] in WITH_ECLI)


# -- the three sentences the discriminator files pin ------------------------

def test_a_dropped_element_contributes_nothing_not_even_a_boundary():
    """§3.1 rule 1 on the fourth file: Rn 22 reads `§ 23 Rn. 2)<img/>. Da
    für` in the source and `Rn. 2). Da für` in the unit — no space where
    the image was. An implementation that treats the dropped element as
    a block boundary writes `Rn. 2) . Da` and fails here; one that keeps
    its alt text fails too. The synthetic cases spell the rule out."""
    decision = D.parse_decision(FIXTURE / "jb-KORE308052015.xml")
    rn22 = next(u for u in decision.units if u.rn == 22)
    assert "§ 23 Rn. 2). Da für" in rn22.text
    assert "Rn. 2) . Da" not in rn22.text
    assert D.text_of(ET.fromstring('<dd><p>x<img src="b.jpg"/>y</p></dd>')) == "xy"
    assert D.text_of(ET.fromstring(
        '<dd><p>before<table><tr><td>Judge</td></tr></table>after</p></dd>')) == "beforeafter"
    # the boundary rules the same flow must keep: a block separates words,
    # the six inline elements do not, White_Space (U+00A0 included) collapses
    assert D.text_of(ET.fromstring("<dd><p>a<br/>b</p></dd>")) == "a b"
    assert D.text_of(ET.fromstring("<dd><p>Abs. 1<sup>a</sup></p></dd>")) == "Abs. 1a"
    assert D.text_of(ET.fromstring("<dd><p>a</p><p>b</p></dd>")) == "a b"
    assert D.text_of(ET.fromstring("<dd><p>a  b\n c­</p></dd>")) == "a b c­"


def test_an_image_viewer_link_is_dropped_whole():
    """§3.1 rule 1 on the fifth file: Rn 1 ends at `Widerrufsinformation
    eingefügt:` — the `<a href="bild1_0.jpg">` that follows, caption and
    all, contributes nothing; an implementation that keeps the caption
    (`Abbildung in Originalgröße in neuem Fenster öffnen`) fails here. An
    `<a>` WITHOUT href (an anchor) stays inline."""
    decision = D.parse_decision(FIXTURE / "jb-JURE160019189.xml")
    rn1 = next(u for u in decision.units if u.rn == 1)
    assert rn1.text.endswith("Widerrufsinformation eingefügt:")
    assert all("Abbildung" not in u.text for u in decision.units)
    snippet = ('<dd><p>ende:</p><img src="bild1_0.jpg"/><a href="bild1_0.jpg">'
               '<br/><span>Abbildung in Originalgröße in neuem Fenster öffnen'
               '</span></a><p>weiter</p></dd>')
    assert D.text_of(ET.fromstring(snippet)) == "ende: weiter"
    assert D.text_of(ET.fromstring('<dd><p>x <a name="rd_3">3</a>y</p></dd>')) == "x 3y"


def test_a_tail_row_is_kept_only_when_indented_by_its_whole_subtree():
    """§4.1/§4.2 on the sixth file: after the last anchor a
    `<p style="margin-left:36pt"><span>Rechtsmittelbelehrung:</span></p>`
    row is kept (indented — `text(p)` reads the whole subtree, so the
    `<span>`'s text counts) and the plain rows after it (the judges'
    names) are dropped. A `.text`-only reading of `p` sees an empty
    paragraph, drops the row, and fails here."""
    decision = D.parse_decision(FIXTURE / "jb-JURE130006754.xml")
    last = decision.units[-1]
    assert last.rn == 4
    # the two indented tail rows ride at the end of Rn 4; the three plain
    # rows after them (the judges' names) do not appear anywhere
    assert "\nRechtsmittelbelehrung:\nDie Berufung ist innerhalb" in last.text
    assert last.text.endswith("(§ 112e Satz 2 BRAO, § 124a Abs. 6 VwGO).")
    assert not any("Kayser" in u.text or "Martini" in u.text for u in decision.units)
    p = ET.fromstring('<p style="margin-left:36pt"><span>Rechtsmittelbelehrung:</span></p>')
    assert (p.text or "").strip() == ""          # what .text alone would see
    assert D.text_of(p) == "Rechtsmittelbelehrung:"
    section = ('<dl><dt><a name="rd_1">1</a></dt><dd><p>A</p></dd></dl>'
               '<dl><dt/><dd><p style="margin-left:36pt"><span>Q</span></p></dd></dl>'
               '<dl><dt/><dd><p>Richter</p></dd></dl>'
               '<dl><dt/><dd><p style="margin-left:54pt">Z</p></dd></dl>')
    assert _units(section) == [(1, "A\nQ\nZ")]
    # an indented row whose only content is a dropped table is not indented
    table_only = ('<dl><dt><a name="rd_1">1</a></dt><dd><p>A</p></dd></dl>'
                  '<dl><dt/><dd><p style="margin-left:36pt"><table><tr><td>x</td></tr></table></p></dd></dl>')
    assert _units(table_only) == [(1, "A")]
    # inside the anchors every non-empty row joins the open unit, indented or not
    between = ('<dl><dt/><dd><p>I.</p></dd></dl>'
               '<dl><dt><a name="rd_1">1</a></dt><dd><p>A</p></dd></dl>'
               '<dl><dt/><dd><p style="margin-left:36pt">quote</p></dd></dl>'
               '<dl><dt/><dd><p>resumes.</p></dd></dl>'
               '<dl><dt/><dd><p>II.</p></dd></dl>'
               '<dl><dt><a name="rd_2">2</a></dt><dd><p>B</p></dd></dl>')
    assert _units(between) == [(1, "I.\nA\nquote\nresumes.\nII."), (2, "B")]


def test_anchors_and_empty_rows_per_the_unit_rule():
    """§4.1/§4.2: an anchored row with an empty body still opens its unit
    (a continuation row fills it, or it is not produced); rd_0 and a
    digitless rd_ are not anchors; the match is the whole attribute; a
    section without anchors is one unit with rn None; empty rows vanish."""
    filled = ('<dl><dt><a name="rd_1">1</a></dt><dd><p/></dd></dl>'
              '<dl><dt/><dd><p>filled</p></dd></dl>'
              '<dl><dt><a name="rd_2">2</a></dt><dd/></dl>'
              '<dl><dt><a name="rd_3">3</a></dt><dd><p>C</p></dd></dl>')
    assert _units(filled) == [(1, "filled"), (3, "C")]
    # a literal LF in an attribute is normalized to a space by the XML
    # parser; the character reference &#10; is what reaches the regex as a
    # newline (the trap the spec's "re.fullmatch, not re.match" names)
    not_anchors = ('<dl><dt><a name="rd_0">0</a></dt><dd><p>zero</p></dd></dl>'
                   '<dl><dt><a name="rd_"/></dt><dd><p>digitless</p></dd></dl>'
                   '<dl><dt><a name="rd_7&#10;"/></dt><dd><p>newline</p></dd></dl>'
                   '<dl><dt><a name="rd_7 "/></dt><dd><p>space</p></dd></dl>'
                   '<dl><dt><a name="rd_007">7</a></dt><dd><p>seven</p></dd></dl>')
    section = _section(not_anchors)
    assert [a.get("name") for a in section.iter("a")][2] == "rd_7\n"
    assert _units(not_anchors) == [(7, "zero\ndigitless\nnewline\nspace\nseven")]
    anomalies: list[str] = []
    D.units_of_section("gruende", section, anomalies)
    assert sorted(a.split("<a name=")[1].split(">")[0] for a in anomalies
                  if "not an anchor" in a) == ["'rd_'", "'rd_0'", "'rd_7 '", "'rd_7\\n'"]
    assert _units('<dl><dt/><dd><p>a</p></dd></dl><dl><dt/><dd><p/></dd></dl>'
                  '<dl><dt/><dd><p>b</p></dd></dl>', "tenor") == [(None, "a\nb")]
    assert _units('<dl><dt/><dd><p/></dd></dl>', "tenor") == []
    assert _units("") == []
    # duplicate numbers: both units produced (§5.4)
    dup = ('<dl><dt><a name="rd_1">1</a></dt><dd><p>A</p></dd></dl>'
           '<dl><dt><a name="rd_1">1</a></dt><dd><p>B</p></dd></dl>')
    assert _units(dup) == [(1, "A"), (1, "B")]


def test_numbering_anomalies_are_judged_across_the_whole_decision(tmp_path):
    """§2.3 read with §5.4: Randnummer numbering runs from tatbestand into
    entscheidungsgruende, so contiguity is the decision's property — an
    ordinary Urteil (1–3 then 4–9, the first fixture file) reports nothing,
    a restart inside sonstlt is a duplicate, a gap is non-contiguous. The
    review of CP-79 caught the first cut judging it per section (every
    Urteil flagged, the cross-section duplicates invisible)."""
    ordinary = D.parse_decision(FIXTURE / "jb-KORE303672022.xml")
    assert [u.rn for u in ordinary.units if u.rn] == list(range(1, 10))
    assert ordinary.anomalies == ()
    for name in FILES:
        assert not any("Randnummer numbering" in a or "duplicate" in a
                       for a in D.parse_decision(FIXTURE / name).anomalies), name

    def decision(body: str, doknr: str = "KORE000000001") -> D.Decision:
        path = tmp_path / f"jb-{doknr}.xml"
        path.write_text(_conforming(doknr).replace(
            "<tenor><dl><dt/><dd><p>Tenor.</p></dd></dl></tenor>"
            "<gruende><dl><dt><a name=\"rd_1\">1</a></dt><dd><p>Grund.</p></dd></dl></gruende>",
            body))
        return D.parse_decision(path)

    def row(n, text):
        return f'<dl><dt><a name="rd_{n}">{n}</a></dt><dd><p>{text}</p></dd></dl>'
    restart = decision(f"<tatbestand>{row(1, 'a')}{row(2, 'b')}</tatbestand>"
                       f"<entscheidungsgruende>{row(3, 'c')}</entscheidungsgruende>"
                       f"<sonstlt>{row(1, 'd')}</sonstlt>")
    assert [u.rn for u in restart.units] == [1, 2, 3, 1]
    assert [a for a in restart.anomalies if "duplicate" in a] == \
        ["duplicate Randnummer numbers [1] (a citation to one of them is ambiguous)"]
    gap = decision(f"<gruende>{row(1, 'a')}{row(3, 'c')}</gruende>")
    assert [a for a in gap.anomalies if "not contiguous" in a] == \
        ["Randnummer numbering not contiguous 1..K: 2 anchors from 1 to 3"]
    late = decision(f"<gruende>{row(2, 'a')}{row(3, 'c')}</gruende>")
    assert any("not contiguous" in a for a in late.anomalies)
    empty = decision(f"<gruende>{row(1, 'a')}"
                     f'<dl><dt><a name="rd_2">2</a></dt><dd><p/></dd></dl></gruende>')
    assert [u.rn for u in empty.units] == [1]
    assert empty.anomalies == ("gruende: Randnummer 2 has no text — not produced",)
    digitless = decision('<gruende><dl><dt><a name="rd_"/></dt><dd><p>x</p></dd></dl></gruende>')
    assert digitless.units == (D.Unit("gruende", None, "x"),)
    assert digitless.anomalies == ("gruende: <a name='rd_'> is not an anchor — the row is unanchored",)


def test_header_values_keep_inner_whitespace(tmp_path):
    """The reference extractor's reading (and gsj-next's): leading and
    trailing White_Space removed, inner runs kept — two files of the March
    2026 drop carry a doubled space inside their Aktenzeichen, and spec
    §3.1's last paragraph (collapse) contradicts §5.2 (verbatim) on them;
    the build follows the fixture's generator (wishlist 75)."""
    path = tmp_path / "jb-KORE000000002.xml"
    path.write_text(_conforming("KORE000000002", aktenzeichen="  VI  ZR 114/23\n", ecli=" "))
    decision = D.parse_decision(path)
    assert decision.aktenzeichen == "VI  ZR 114/23"
    assert decision.ecli is None and "ecli" not in decision.header()


# -- §2.2: conforming files, the drop loader ---------------------------------

def _conforming(doknr: str = "KORE000000001", **fields) -> str:
    values = {"doknr": doknr, "ecli": "", "gertyp": "BGH", "gerort": "",
              "spruchkoerper": "1. Zivilsenat", "entsch-datum": "20240102",
              "aktenzeichen": "I ZR 1/24", "doktyp": "Urteil"}
    values.update(fields)
    body = "".join(f"<{k}>{v}</{k}>" for k, v in values.items())
    return (f"<dokument>{body}<tenor><dl><dt/><dd><p>Tenor.</p></dd></dl></tenor>"
            f"<gruende><dl><dt><a name=\"rd_1\">1</a></dt><dd><p>Grund.</p></dd></dl>"
            f"</gruende></dokument>")


def test_nonconforming_files_are_refused_with_reasons(tmp_path):
    """The training estate's posture (spec §2.2): a file that does not
    conform is skipped WITH its reason, the drop goes on; the drop's hash
    covers the kept files' names and bytes, in order."""
    drop = tmp_path / "drop"
    drop.mkdir()
    for name in FILES:
        shutil.copy(FIXTURE / name, drop / name)
    (drop / "jb-KORE000000001.xml").write_text(_conforming())
    (drop / "jb-KORE000000002.xml").write_text(_conforming("KORE000000009"))
    (drop / "jb-KORE000000003.xml").write_text(_conforming("KORE000000003", **{"entsch-datum": "2024-01-02"}))
    (drop / "jb-KORE000000004.xml").write_text(_conforming("KORE000000004", doktyp=""))
    (drop / "jb-KORE000000005.xml").write_text("<dokument><doknr>KORE000000005</doknr>")
    (drop / "jb-KORE000000006.xml").write_text("<urteil><doknr>KORE000000006</doknr></urteil>")
    (drop / "notes.txt").write_text("not a decision")
    loaded = D.load_drop(drop)
    by_name = {e["file"]: e["metadata"]["decision_id"] for e in EXPECTED["documents"]}
    by_name["jb-KORE000000001.xml"] = "KORE000000001"
    assert [d.decision_id for d in loaded.decisions] == [
        by_name[name] for name in sorted(by_name)]      # ascending filename order
    reasons = dict(loaded.skipped)
    assert set(reasons) == {f"jb-KORE00000000{i}.xml" for i in (2, 3, 4, 5, 6)}
    assert "jb-KORE000000009.xml" in reasons["jb-KORE000000002.xml"]
    assert "eight ASCII digits" in reasons["jb-KORE000000003.xml"]
    assert "doktyp" in reasons["jb-KORE000000004.xml"]
    assert "well-formed" in reasons["jb-KORE000000005.xml"]
    assert "<dokument>" in reasons["jb-KORE000000006.xml"]
    assert loaded.units == 62 + 2
    # the hash: the kept files only, and it moves with their bytes
    before = loaded.sha256
    (drop / "jb-KORE000000004.xml").unlink()
    assert D.load_drop(drop).sha256 == before
    (drop / "jb-KORE000000001.xml").write_text(_conforming(aktenzeichen="I ZR 2/24"))
    assert D.load_drop(drop).sha256 != before
    with pytest.raises(D.DecisionError, match="not a directory"):
        D.load_drop(drop / "missing")


def test_decisions_path_resolves_against_the_config_dir(tmp_path):
    cfg = write_config(tmp_path, repos=["case_0003"], clone_cache_dir=tmp_path / "c",
                       index_path=tmp_path / "i", decisions_path="./my-drop")
    config = load_config(cfg)
    assert config.decisions.path == tmp_path / "my-drop"
    assert config.decisions.path.is_absolute()
    cfg2 = write_config(tmp_path, repos=["case_0003"], clone_cache_dir=tmp_path / "c",
                        index_path=tmp_path / "i", name="nopath.yaml")
    assert load_config(cfg2).decisions.path is None
    doc = yaml.safe_load(cfg.read_text())
    doc["decisions"]["pathh"] = "typo"
    (tmp_path / "typo.yaml").write_text(yaml.safe_dump(doc))
    with pytest.raises(ConfigError, match="pathh"):
        load_config(tmp_path / "typo.yaml")


# -- the store: a drop, batched, into level-2 hits ---------------------------

@pytest.fixture(scope="module")
def drop_dir(tmp_path_factory):
    drop = tmp_path_factory.mktemp("drop")
    for name in FILES:
        shutil.copy(FIXTURE / name, drop / name)
    (drop / "jb-KORE000000005.xml").write_text("<dokument><doknr>KORE000000005</doknr>")
    return drop


@pytest.fixture(scope="module")
def drop_state(tmp_path_factory, built_state, shared_dirs, drop_dir):
    """case_0003 + the six-file drop, built with ADD_BATCH_SIZE forced to 7
    so the 99 pieces land in 15 adds — the batched path a real drop takes
    (CP-77's above-the-ceiling shape at suite cost)."""
    root = tmp_path_factory.mktemp("drop-store")
    config_path = write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", decisions_path=str(drop_dir))
    previous = index_module.ADD_BATCH_SIZE
    index_module.ADD_BATCH_SIZE = 7
    state = state_module.AppState(load_config(config_path))
    state.encoder = built_state.encoder
    batches: list[tuple] = []
    report = state._on_batch
    state._on_batch = lambda *args: (batches.append(args), report(*args))
    try:
        state.initialize()
    finally:
        index_module.ADD_BATCH_SIZE = previous
    assert state.status == "ready", state.error
    return {"root": root, "config": config_path, "state": state, "batches": batches}


def test_a_drop_builds_batched_and_health_names_it(drop_state):
    state = drop_state["state"]
    assert state.decisions.kind == "rii"
    import math
    walked = [b for b in drop_state["batches"] if b[0] == "decisions"]
    n = math.ceil(state.decisions.n_pieces / 7)
    assert n >= 10
    assert [b[3] for b in walked] == list(range(1, n + 1))
    assert walked[-1] == ("decisions", state.decisions.n_pieces,
                          state.decisions.n_pieces, n, n)
    assert state.reused_index is False and state.rebuilt == ["case_0003", "decisions"]
    assert state.decisions.n_units == 62
    assert state.decisions.collection.count() == state.decisions.n_pieces > 62
    health = state.health()
    assert health["decisions"] == 6
    assert health["decisions_drop"] == {
        "sha256": state.decisions.index_commit, "files": 6, "units": 62,
        "pieces": state.decisions.n_pieces, "skipped": 1,
        "surface_version": D.SURFACE_VERSION}
    assert health["rebuilt"] == ["case_0003", "decisions"]
    assert re.fullmatch(r"[0-9a-f]{64}", state.decisions.index_commit)
    sidecar = json.loads((drop_state["root"] / "index" / "decisions" / "corpus.json").read_text())
    assert sidecar["source"] == "rii" and sidecar["surface_version"] == 1
    assert len(sidecar["drop"]["skipped"]) == 1
    assert sidecar["drop"]["skipped"][0][0] == "jb-KORE000000005.xml"
    assert "not well-formed XML" in sidecar["drop"]["skipped"][0][1]
    # index_commit is the drop's content hash — recomputed here from the
    # kept files' names and bytes, independently of the loader
    import hashlib
    digest = hashlib.sha256()
    for name in sorted(FILES):
        digest.update(f"{name}\n{hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest()}\n".encode())
    assert state.decisions.index_commit == digest.hexdigest()
    assert state.decisions.n_pieces == sum(len(u["pieces"]) for e in sidecar["decisions"]
                                           for u in e["units"])
    # every unit's text is the fixture's, byte for byte, in the fixture's order
    by_id = {e["metadata"]["decision_id"]: e for e in EXPECTED["documents"]}
    for entry in sidecar["decisions"]:
        expected = by_id[entry["decision_id"]]
        assert [(u["section"], u["rn"], u["text"]) for u in entry["units"]] == \
            [(u["section"], u["rn"], u["text"]) for u in expected["units"]]
        assert {k: v for k, v in entry.items() if k not in ("units", "anomalies")} \
            == expected["metadata"]
        # spec §6: pieces are verbatim contiguous slices that cover the unit
        for unit in entry["units"]:
            spans = unit["pieces"]
            assert spans[0][0] == 0 and spans[-1][1] == len(unit["text"])
            for (b0, e0), (b1, e1) in zip(spans, spans[1:]):
                assert b0 < b1 <= e0 < e1, (unit["section"], unit["rn"], spans)
    # the piece ids follow the reference scheme; the metadata resolves them
    got = state.decisions.collection.get(include=["metadatas"])
    assert len(got["ids"]) == state.decisions.n_pieces
    for pid, meta in zip(got["ids"], got["metadatas"]):
        doknr, rest = pid.split(":", 1)
        assert meta["doknr"] == doknr and rest.endswith(f":p{meta['piece']}")
        unit = state.decisions._by_id[doknr]["units"][meta["unit"]]
        assert meta["section"] == unit["section"]
        assert meta.get("rn") == unit["rn"] if unit["rn"] is not None else "rn" not in meta
        assert rest.startswith(f"rn:{unit['rn']}" if unit["rn"] is not None else unit["section"])


def check_level2_hit(hit: dict, expected_ecli: bool | None = None) -> None:
    """Spec §7.3 field by field, §7.4 absent-vs-null."""
    assert REQUIRED_L2 <= set(hit), hit.keys()
    assert set(hit) <= REQUIRED_L2 | {"ecli", "excerpt"}, hit.keys()
    assert "page" not in hit and "file" not in hit
    assert re.fullmatch(r"[A-Z]{4}[0-9]{9}", hit["decision_id"])
    assert isinstance(hit["aktenzeichen"], str)
    assert hit["court"] == "BGH"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", hit["date"])
    assert hit["doktyp"] in ("Urteil", "Beschluss")
    assert hit["rn"] is None or (isinstance(hit["rn"], int) and hit["rn"] >= 1)
    assert hit["section"] in D.SECTIONS
    assert isinstance(hit["score"], float) and hit["score"] > 0
    assert isinstance(hit["text"], str) and hit["text"]
    if "ecli" in hit:
        assert isinstance(hit["ecli"], str) and hit["ecli"].startswith("ECLI:DE:BGH:")
    if expected_ecli is not None:
        assert ("ecli" in hit) is expected_ecli, hit["decision_id"]
    if "excerpt" in hit:
        assert hit["excerpt"] and hit["excerpt"] in hit["text"]


def test_hits_carry_the_level2_shape_absent_vs_null_and_the_order(drop_state):
    """§7.3/§7.4 on real hits: ecli present exactly for the three files
    that have one, absent (never null, never "") for the other three; rn
    an integer for a Randnummer and null for a section unit; text the
    whole unit, byte-exact against the fixture; no page/file; §8.2's
    order; §8.1's best piece as the excerpt; §8.3's clamp."""
    state = drop_state["state"]
    by_id = {e["metadata"]["decision_id"]: e for e in EXPECTED["documents"]}
    seen_ids, seen_null, seen_rn = set(), False, False
    for query in ("Sittenwidrigkeit Dieselfall Schädiger Gesamtcharakter",
                  "Widerrufsinformation Verbraucherdarlehen",
                  "Rechtsmittelbelehrung Anwaltsgerichtshof",
                  "Kosten des Rechtsstreits", "Nichtzulassungsbeschwerde"):
        vec, _ = state.encoder.encode_query(query)
        hits = state.decisions.search(vec, k=20)
        assert hits
        for hit in hits:
            entry = by_id[hit["decision_id"]]
            check_level2_hit(hit, expected_ecli=entry["file"] in WITH_ECLI)
            unit = next(u for u in entry["units"]
                        if u["section"] == hit["section"] and u["rn"] == hit["rn"])
            assert hit["text"] == unit["text"]
            seen_ids.add(hit["decision_id"])
            seen_null |= hit["rn"] is None
            seen_rn |= hit["rn"] is not None
        keys = [(-h["score"], h["decision_id"], D.SECTION_ORDER[h["section"]],
                 h["rn"] is not None, h["rn"] or 0) for h in hits]
        assert keys == sorted(keys)
        assert len({(h["decision_id"], h["section"], h["rn"]) for h in hits}) == len(hits)
        assert len(hits) <= 20
        assert [(h["decision_id"], h["section"], h["rn"]) for h in state.decisions.search(vec, k=3)] == \
            [(h["decision_id"], h["section"], h["rn"]) for h in hits[:3]]
    assert seen_ids == set(by_id)          # every decision surfaced, with and without ecli
    assert seen_null and seen_rn
    # the bounded fetch (§8.4): what search asks chroma for is a function of
    # k alone — never of the piece count
    asked: list[int] = []
    real = state.decisions.collection.query

    def spy(**kwargs):
        asked.append(kwargs["n_results"])
        return real(**kwargs)
    state.decisions.collection.query = spy
    try:
        vec, _ = state.encoder.encode_query("Kosten des Rechtsstreits")
        state.decisions.search(vec, k=3)
        state.decisions.search(vec, k=20)
        state.decisions.search(vec, k=1)
    finally:
        del state.decisions.collection.query
    assert asked == [min(state.decisions.n_pieces, DECISIONS_FETCH_PER_K * k)
                     for k in (3, 20, 1)]
    assert state.decisions.n_pieces < DECISIONS_FETCH_PER_K * 20   # (the fake-collection test shows the scaling)


def test_the_wrapper_over_real_mcp_and_the_synthetic_default(
        drop_state, tmp_path_factory, server):
    """§7.2 over streamable-http: `{query, k, hits, index_commit}` as one
    JSON text block (a `-> dict` tool carries no structured content under
    mcp 2.0.0), the EFFECTIVE k echoed (k=0 → 1, k=999 → max_k 20), at
    most k hits, index_commit the drop's hash. And the no-path default —
    the session server over the synthetic 30 — returns the same envelope
    around level-0 hits with index_commit ""."""
    run_dir = tmp_path_factory.mktemp("drop-srv")
    port = free_port()
    config_path = write_config(
        run_dir, repos=["case_0003"], clone_cache_dir=drop_state["state"].config.source.clone_cache_dir,
        index_path=drop_state["root"] / "index", port=port,
        decisions_path=str(drop_state["state"].config.decisions.path))
    proc, log_file = spawn_server(run_dir, config_path, port)
    try:
        assert proc.final_health["index_reused"] is True
        assert proc.final_health["decisions_drop"]["files"] == 6
        token = mint_token("case_0003", 4)
        _, replies = mcp_roundtrip(proc.base_url, token, [
            ("search_decisions", {"query": "Widerrufsinformation", "k": 3}),
            ("search_decisions", {"query": "Widerrufsinformation", "k": 0}),
            ("search_decisions", {"query": "Widerrufsinformation", "k": 999}),
            ("search_decisions", {"query": "Widerrufsinformation"}),
            ("decision_stats", {})])
        for reply in replies[:4]:
            assert not reply.is_error and reply.structured is None
            assert len(reply.texts) == 1
        three, zero, huge, default, stats = [json.loads(r.texts[0]) for r in replies]
        for response, k in ((three, 3), (zero, 1), (huge, 20), (default, 5)):
            assert set(response) == {"query", "k", "hits", "index_commit"}
            assert response["query"] == "Widerrufsinformation"
            assert response["k"] == k and len(response["hits"]) <= k
            assert response["index_commit"] == drop_state["state"].decisions.index_commit
            for hit in response["hits"]:
                check_level2_hit(hit)
        assert len(zero["hits"]) == 1 and canonical(zero["hits"][0]) == canonical(three["hits"][0])
        assert len(huge["hits"]) == 20
        assert stats == {"total": 6, "by_year": {"2010": 1, "2013": 1, "2015": 1,
                                                  "2016": 1, "2022": 1, "2023": 1},
                         "by_court": {"BGH": 6}}
    finally:
        stop_server(proc, log_file)
    # the synthetic default, unchanged inside the same envelope
    response = call_tool(server.base_url, mint_token("case_0001", 5),
                         "search_decisions", {"query": "warehouse lease", "k": 5})
    assert set(response) == {"query", "k", "hits", "index_commit"}
    assert response["k"] == 5 and response["index_commit"] == ""
    assert len(response["hits"]) == 5
    for hit in response["hits"]:
        assert set(hit) == {"decision_id", "court", "year", "score", "text"}


# -- §9: a level-2 consumer accepts level-1 responses ------------------------

def cite(hit: dict) -> str | None:
    """A level-2 consumer's citation rule (spec §9.2): the suffix only from
    an integer rn the hit carries; the bare form for rn null or no rn key;
    a decision_id that is not a doknr is not a citation source."""
    if not re.fullmatch(r"[A-Z]{4}[0-9]{9}", str(hit.get("decision_id", ""))):
        return None
    rn = hit.get("rn")
    if isinstance(rn, int) and not isinstance(rn, bool) and rn >= 1:
        return f"dec:{hit['decision_id']}:rn:{rn}"
    return f"dec:{hit['decision_id']}"


def read_response(response: dict) -> list[str]:
    """What the consumer reads off any conformant response, either level:
    the envelope, the required level-1 fields, then a citation per hit."""
    assert {"query", "k", "hits"} <= set(response)
    assert isinstance(response.get("index_commit", ""), str)
    citations = []
    for hit in response["hits"]:
        assert REQUIRED_L1 <= set(hit)
        assert "page" not in hit and "file" not in hit
        assert "ecli" not in hit or (isinstance(hit["ecli"], str) and hit["ecli"])
        token = cite(hit)
        assert token is not None
        match = CITATION_RE.fullmatch(token)
        assert match and match.group(1) == hit["decision_id"]
        citations.append(token)
    return citations


def test_a_level1_response_is_accepted_by_a_level2_consumer(drop_state):
    state = drop_state["state"]
    vec, _ = state.encoder.encode_query("Sittenwidrigkeit Dieselfall")
    level2 = {"query": "Sittenwidrigkeit Dieselfall", "k": 5,
              "hits": state.decisions.search(vec, k=5),
              "index_commit": state.decisions.index_commit}
    cited = read_response(level2)
    assert cited and any(":rn:" in c for c in cited)
    for hit, token in zip(level2["hits"], cited):
        match = CITATION_RE.fullmatch(token)
        assert match.group(1) == hit["decision_id"]
        assert (match.group(2) is None) == (hit["rn"] is None)
        if hit["rn"] is not None:
            assert int(match.group(2)) == hit["rn"] and hit["rn"] >= 1
    # the same hits as a level-1 implementation would return them: rn and
    # section absent (never null) — the bare form for every one (§9.2 rule 4)
    level1 = {"query": level2["query"], "k": 5, "hits": [
        {k: v for k, v in hit.items() if k not in ("rn", "section", "excerpt")}
        for hit in level2["hits"]]}
    assert read_response(level1) == [f"dec:{h['decision_id']}" for h in level1["hits"]]
    # rn null (a section unit) is the bare form too (rule 3)
    assert cite({"decision_id": "KORE613012010", "rn": None}) == "dec:KORE613012010"
    # and what is NOT a citation: a non-doknr id, a suffixed non-conforming id
    assert cite({"decision_id": "D-2021-OLG-B-1", "rn": 3}) is None
    assert cite({"decision_id": "KORE303672022__2"}) is None
    for bad in ("dec:KORE303672022:rn:08", "dec:KORE303672022:rn:0",
                "codec:KORE303672022", "dec:KORE303672022__2"):
        assert not CITATION_RE.search(bad), bad
    assert CITATION_RE.search("[Rn. 8](dec:KORE303672022:rn:8)").group(2) == "8"


# -- upgrade: nothing rebuilds; a drop re-embeds only the decisions ---------

def test_no_path_fingerprint_document_is_byte_identical_to_pre_cp79(built_state):
    """The hashed document without a drop is exactly the pre-CP-79 layout
    — the component is ADDED only when a drop is configured, never a key
    with None — so every existing store's fingerprint is reproduced and
    reused on upgrade. Reproduced here from the old layout by hand."""
    import hashlib
    from types import SimpleNamespace
    config = built_state.config
    sources = {cid: SimpleNamespace(main_sha=idx.refs["main"])
               for cid, idx in built_state.cases.items()}
    old_layout = {
        "index_format": index_module.INDEX_FORMAT,
        "cases": {cid: src.main_sha for cid, src in sorted(sources.items())},
        "embedding": {"model": config.embedding.model,
                      "revision": config.embedding.revision,
                      "normalize": config.embedding.normalize},
        "chunking": {"max_tokens": config.chunking.max_tokens,
                     "overlap": config.chunking.overlap,
                     "respect_page_boundaries": config.chunking.respect_page_boundaries},
        "decisions": {"seed": config.decisions.seed, "size": config.decisions.corpus_size},
        "chroma": {"version": index_module.CHROMA_VERSION},
    }
    by_hand = hashlib.sha256(json.dumps(old_layout, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    args = (sources, config.embedding, config.chunking,
            config.decisions.seed, config.decisions.corpus_size)
    assert corpus_fingerprint(*args) == by_hand == built_state.fingerprint
    assert corpus_fingerprint(*args, decisions_drop=None) == by_hand
    assert corpus_fingerprint(*args, decisions_drop={"sha256": "0" * 64,
                                                     "surface_version": 1,
                                                     "files": 1}) != by_hand
    # wishlist 69 (c): embedding.batch_size is identity above the smaller
    # batch size — a component only when it leaves the pinned 32, so the
    # stores every estate built at 32 keep their bytes and a moved value
    # re-embeds
    assert config.embedding.batch_size == index_module.PINNED_ENCODE_BATCH_SIZE == 32
    moved = config.embedding.model_copy(update={"batch_size": 64})
    assert corpus_fingerprint(sources, moved, config.chunking,
                              config.decisions.seed, config.decisions.corpus_size) != by_hand
    per = index_module.collection_fingerprints(sources, moved, config.chunking,
                                               config.decisions.seed,
                                               config.decisions.corpus_size)
    same = index_module.collection_fingerprints(sources, config.embedding, config.chunking,
                                                config.decisions.seed,
                                                config.decisions.corpus_size)
    assert set(per) == set(same) and all(per[k] != same[k] for k in per)


def _segment_dirs(index_root) -> set[str]:
    with sqlite3.connect(index_root / "chroma" / "chroma.sqlite3") as con:
        return {row[0] for row in con.execute("SELECT id FROM segments")}


def test_a_pre_cp79_store_is_reused_and_a_drop_re_embeds_only_the_decisions(
        built_state, shared_dirs, drop_dir, tmp_path_factory):
    """A copy of the session store with its record cut back to the pre-
    CP-79 shape (no per-collection map): (1) the same config reuses it
    whole (`index_reused: true`) and backfills the record; (2) the config
    plus a drop rebuilds the decisions collection ALONE — every case
    collection loaded, its segment untouched (wishlist 61); (3) the drop
    removed again: the synthetic 30 rebuilt, the cases still untouched."""
    root = tmp_path_factory.mktemp("upgrade")
    shutil.copytree(shared_dirs["index"], root / "index")
    record = root / "index" / "fingerprint.json"
    doc = json.loads(record.read_text())
    assert "collections" in doc
    del doc["collections"]
    record.write_text(json.dumps(doc))
    repos = sorted(built_state.cases)

    def config(name, **overrides):
        return write_config(root, repos=repos, clone_cache_dir=shared_dirs["clones"],
                            index_path=root / "index", name=name, **overrides)
    reused = make_state(config("same.yaml"), encoder=built_state.encoder)
    assert reused.status == "ready", reused.error
    assert reused.reused_index is True and reused.rebuilt == []
    assert reused.fingerprint == built_state.fingerprint
    assert set(read_collection_fingerprints(root / "index")) == set(repos) | {"decisions"}
    segments_before = _segment_dirs(root / "index")

    record.write_text(json.dumps(doc))          # back to the pre-CP-79 shape
    with_drop = make_state(config("drop.yaml", decisions_path=str(drop_dir)),
                           encoder=built_state.encoder)
    assert with_drop.status == "ready", with_drop.error
    assert with_drop.reused_index is False
    assert with_drop.rebuilt == ["decisions"]
    assert with_drop.decisions.kind == "rii" and with_drop.health()["decisions"] == 6
    assert with_drop.fingerprint != built_state.fingerprint
    assert all(with_drop.progress[r].get("reused") for r in repos)
    segments_after = _segment_dirs(root / "index")
    assert len(segments_after) == len(segments_before)
    # chroma keeps two segment rows per collection (metadata + vector):
    # exactly the decisions collection's two were replaced
    assert len(segments_before & segments_after) == len(segments_before) - 2
    vec, _ = built_state.encoder.encode_query("deposition slip concerning the sealed ledgers")
    assert canonical(with_drop.cases["case_0003"].search(vec, k=5, timestep=9)) == \
        canonical(built_state.cases["case_0003"].search(vec, k=5, timestep=9))

    back = make_state(config("back.yaml"), encoder=built_state.encoder)
    assert back.status == "ready", back.error
    assert back.rebuilt == ["decisions"] and back.decisions.kind == "synthetic"
    assert back.fingerprint == built_state.fingerprint
    assert back.health()["decisions"] == 30 and "decisions_drop" not in back.health()
    assert len(_segment_dirs(root / "index") & segments_after) == len(segments_before) - 2
    # rebuild: always still re-embeds everything
    always = make_state(config("always.yaml", rebuild="always"), encoder=built_state.encoder)
    assert always.status == "ready" and always.rebuilt == repos + ["decisions"]


def test_a_drop_with_no_conforming_file_is_a_startup_error(built_state, shared_dirs,
                                                          tmp_path_factory):
    root = tmp_path_factory.mktemp("empty-drop")
    (root / "drop").mkdir()
    (root / "drop" / "jb-KORE000000005.xml").write_text("<dokument>")
    state = make_state(write_config(
        root, repos=["case_0003"], clone_cache_dir=shared_dirs["clones"],
        index_path=root / "index", decisions_path=str(root / "drop")),
        encoder=built_state.encoder)
    assert state.status == "error"
    assert "no conforming rii-dok v1 decision" in state.error
    assert "jb-KORE000000005.xml" in state.error


# -- §8.2's total order and §8.2's positive-score rule, on crafted ties -------

class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows            # [(id, metadata, distance)]
        self.asked: list[int] = []

    def query(self, **kwargs):
        self.asked.append(kwargs["n_results"])
        rows = self.rows[:kwargs["n_results"]]
        return {"ids": [[r[0] for r in rows]],
                "metadatas": [[r[1] for r in rows]],
                "distances": [[r[2] for r in rows]]}


def test_the_total_order_on_ties_and_non_positive_scores():
    """Two units at the same internal score are ordered by decision_id,
    then section in DTD order, then rn with null first, then document
    order; a unit whose best piece scores ≤ 0 is never returned; a unit
    with several pieces in the fetch scores by its best (§8.1) and the
    excerpt is that piece."""
    def unit(section, rn, text):
        return {"section": section, "rn": rn, "text": text,
                "pieces": [[0, len(text) // 2], [len(text) // 2 - 1, len(text)]]}
    doc = {"drop": {"sha256": "f" * 64, "files": 2, "skipped": []},
           "surface_version": 1, "decisions": [
               {"decision_id": "KORE000000002", "aktenzeichen": "II", "court": "BGH",
                "date": "2020-01-02", "doktyp": "Urteil", "units": [
                    unit("gruende", 1, "b-gruende-one"), unit("gruende", 1, "b-gruende-one-dup"),
                    unit("gruende", None, "b-gruende-null"), unit("tenor", None, "b-tenor")]},
               {"decision_id": "KORE000000001", "aktenzeichen": "I", "court": "BGH",
                "date": "2020-01-01", "doktyp": "Beschluss", "units": [
                    unit("leitsatz", None, "a-leitsatz"), unit("gruende", 2, "a-gruende-two")]}]}
    rows = [("KORE000000002:gruende:p0", {"doknr": "KORE000000002", "unit": 2, "piece": 0}, 0.5),
            ("KORE000000002:rn:1:d2:p1", {"doknr": "KORE000000002", "unit": 1, "piece": 1}, 0.5),
            ("KORE000000002:rn:1:p0", {"doknr": "KORE000000002", "unit": 0, "piece": 0}, 0.5),
            ("KORE000000002:tenor:p0", {"doknr": "KORE000000002", "unit": 3, "piece": 0}, 0.5),
            ("KORE000000001:rn:2:p1", {"doknr": "KORE000000001", "unit": 1, "piece": 1}, 0.5),
            ("KORE000000001:rn:2:p0", {"doknr": "KORE000000001", "unit": 1, "piece": 0}, 0.7),
            ("KORE000000001:leitsatz:p0", {"doknr": "KORE000000001", "unit": 0, "piece": 0}, 0.5),
            ("KORE000000002:tenor:p1", {"doknr": "KORE000000002", "unit": 3, "piece": 1}, 1.0),
            ("KORE000000001:leitsatz:p1", {"doknr": "KORE000000001", "unit": 0, "piece": 1}, 1.2)]
    index = RiiDecisionsIndex(_FakeCollection(rows), doc)
    hits = index.search([0.0], k=20)
    assert [(h["decision_id"], h["section"], h["rn"], h["score"]) for h in hits] == [
        ("KORE000000001", "leitsatz", None, 0.5),
        ("KORE000000001", "gruende", 2, 0.5),
        ("KORE000000002", "tenor", None, 0.5),
        ("KORE000000002", "gruende", None, 0.5),
        ("KORE000000002", "gruende", 1, 0.5),
        ("KORE000000002", "gruende", 1, 0.5)]
    assert [h["text"] for h in hits[4:]] == ["b-gruende-one", "b-gruende-one-dup"]
    # the unit's best piece is its second (distance 0.5 beats 0.7): the excerpt
    assert hits[1]["excerpt"] == "a-gruende-two"[len("a-gruende-two") // 2 - 1:] == "ende-two"
    assert hits[1]["score"] == 0.5 and hits[1]["excerpt"] != hits[1]["text"]
    # §8.4: the fetch is DECISIONS_FETCH_PER_K × k, capped by the piece count
    big = dict(doc, decisions=[dict(doc["decisions"][0], units=[
        {"section": "gruende", "rn": 1, "text": "x" * 9000,
         "pieces": [[i, i + 2] for i in range(0, 8998)]}])])
    fake = _FakeCollection([("KORE000000002:rn:1:p0",
                             {"doknr": "KORE000000002", "unit": 0, "piece": 0}, 0.5)])
    RiiDecisionsIndex(fake, big).search([0.0], k=1)
    RiiDecisionsIndex(fake, big).search([0.0], k=20)
    RiiDecisionsIndex(fake, big).search([0.0], k=100)
    assert fake.asked == [DECISIONS_FETCH_PER_K, DECISIONS_FETCH_PER_K * 20, 8998]
    # the whole fetch scores ≤ 0: nothing comes back, no error
    zero = RiiDecisionsIndex(_FakeCollection([
        ("KORE000000001:leitsatz:p0", {"doknr": "KORE000000001", "unit": 0, "piece": 0}, 1.0),
        ("KORE000000001:rn:2:p0", {"doknr": "KORE000000001", "unit": 1, "piece": 0}, 1.4)]), doc)
    assert zero.search([0.0], k=5) == []
    assert index.search([0.0], k=2) == hits[:2]


def test_piece_ids_follow_the_reference_scheme_with_d2_for_a_repeated_number(built_state):
    """§6's reference identifiers: `<doknr>:rn:<N>:p<i>` / `<doknr>:<section>:p<i>`,
    a repeated (doknr, number) taking :d2, :d3 before :p<i>; pieces cover
    every unit, the first from 0 and the last to the unit's end even when
    the unit ends with a format character the tokenizer gives no offset."""
    soft = "Ende mit weichem Trennstrich.\n\u00ad"
    decision = D.Decision(
        file="jb-KORE000000009.xml", sha256="0" * 64, decision_id="KORE000000009",
        aktenzeichen="I ZR 9/24", ecli=None, court="BGH", date="2024-01-01",
        doktyp="Urteil", units=(
            D.Unit("tenor", None, "Tenor."), D.Unit("gruende", 1, "Eins."),
            D.Unit("gruende", 1, "Eins noch einmal."), D.Unit("sonstlt", 1, "Drittes."),
            D.Unit("gruende", 2, soft)))
    drop = D.Drop(path="/x", decisions=(decision,), skipped=(), sha256="1" * 64)
    entries, texts, ids, metadatas = rii_pieces(
        drop, built_state.encoder.tokenizer, built_state.config.chunking)
    assert ids == ["KORE000000009:tenor:p0", "KORE000000009:rn:1:p0",
                   "KORE000000009:rn:1:d2:p0", "KORE000000009:rn:1:d3:p0",
                   "KORE000000009:rn:2:p0"]
    assert [m["unit"] for m in metadatas] == [0, 1, 2, 3, 4]
    assert "rn" not in metadatas[0] and metadatas[3] == {
        "doknr": "KORE000000009", "unit": 3, "piece": 0, "section": "sonstlt", "rn": 1}
    assert texts[-1] == soft and entries[0]["units"][-1]["pieces"] == [[0, len(soft)]]


def test_a_failed_whole_store_load_keeps_the_healthy_collections(
        built_state, shared_dirs, tmp_path_factory):
    """A whole-fingerprint match whose load fails on ONE collection (a
    corrupt decisions sidecar) rebuilds that collection alone and records
    every healthy one — the review's catch: the first cut left the loaded
    cases out of the record, so the next drop would have re-embedded
    them. And a start that keeps everything reports index_reused true."""
    root = tmp_path_factory.mktemp("half-corrupt")
    shutil.copytree(shared_dirs["index"], root / "index")
    record = root / "index" / "fingerprint.json"
    doc = json.loads(record.read_text())
    del doc["collections"]                     # the pre-CP-79 shape
    record.write_text(json.dumps(doc))
    corpus = json.loads((root / "index" / "decisions" / "corpus.json").read_text())
    (root / "index" / "decisions" / "corpus.json").write_text(json.dumps(corpus[:-1]))
    repos = sorted(built_state.cases)
    state = make_state(write_config(root, repos=repos, clone_cache_dir=shared_dirs["clones"],
                                    index_path=root / "index"), encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.rebuilt == ["decisions"] and state.reused_index is False
    assert set(read_collection_fingerprints(root / "index")) == set(repos) | {"decisions"}
    assert all(state.progress[r].get("reused") for r in repos)
    # a removed case: the whole fingerprint moves, nothing is embedded
    fewer = make_state(write_config(root, repos=repos[:-1], clone_cache_dir=shared_dirs["clones"],
                                    index_path=root / "index", name="fewer.yaml"),
                       encoder=built_state.encoder)
    assert fewer.status == "ready" and fewer.rebuilt == [] and fewer.reused_index is True
    assert "rebuilt" not in fewer.health() and fewer.health()["index_reused"] is True


def test_a_sidecar_of_the_other_kind_is_rebuilt_not_served(built_state, shared_dirs,
                                                           drop_dir, tmp_path_factory):
    """A forged per-collection record cannot make the synthetic sidecar
    serve under a drop config: the kind is checked at load and the
    decisions collection rebuilt from the drop."""
    root = tmp_path_factory.mktemp("kind")
    shutil.copytree(shared_dirs["index"], root / "index")
    record = root / "index" / "fingerprint.json"
    config_path = write_config(root, repos=sorted(built_state.cases),
                               clone_cache_dir=shared_dirs["clones"],
                               index_path=root / "index", decisions_path=str(drop_dir))
    probe = state_module.AppState(load_config(config_path))
    probe.encoder = built_state.encoder
    drop, component = probe._load_drop()
    from types import SimpleNamespace
    sources = {cid: SimpleNamespace(main_sha=idx.refs["main"]) for cid, idx in built_state.cases.items()}
    wanted = index_module.collection_fingerprints(
        sources, probe.config.embedding, probe.config.chunking,
        probe.config.decisions.seed, probe.config.decisions.corpus_size,
        decisions_drop=component)
    doc = json.loads(record.read_text())
    doc["collections"]["decisions"] = wanted["decisions"]     # the forgery
    record.write_text(json.dumps(doc))
    state = make_state(config_path, encoder=built_state.encoder)
    assert state.status == "ready", state.error
    assert state.decisions.kind == "rii" and state.rebuilt == ["decisions"]
