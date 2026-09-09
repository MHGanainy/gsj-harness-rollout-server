"""CP-101 (row 102): the `== run <name> ==` footer, made conditional.

Round six's `stranger-a1` read `up`'s pins line carrying CP-99's new
conditional clause —

    … skill_card_hash, system_prompt_hash EMPTY in it — and NOT NEEDED here
    as far as this script can check: <pins> already carries them …

— and, **twenty lines later on the same screen**, the `== run demo ==`
block's skeleton row still saying the opposite, unconditionally:

    pins.skeleton.json NOT pins — … ;
                       G1/G2 EMPTY until an inspected quarantined episode
                       supplies them (#your-pins reads it)

It filed the contradiction as F6 and ranked it second of seven. That footer
is the unconditional site CP-99's amendment did not reach: one screen, two
claims, and the reader arbitrates. CP-101 makes it conditional on exactly
the fact the pins line already tests — `skeleton_covered`, i.e. whether the
pins in force carry both derived sets AND cover every skill card in this
corpus.

The row it belongs to is 102, whose own question ("will a reader who did
not write the skeleton use it?") round six ANSWERED from a direction CP-99
did not expect: nobody opened a skeleton by hand, and both library-door
strangers consumed one through `derive_my_pins.py` — the walk's step 4
performed. The artifact is an input to a script, not a page to be read.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"

SKELETON = "/runs/demo/pins.skeleton.json"
PINS = "/runs/demo/pins.gsj.json"
ENGINE = "http://131.159.30.148:40035"


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp101", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "PH", module.Phases())
    return module


def measured(**over) -> dict:
    doc = {"measured": True, "end_of_turn_token_id": 248046}
    doc.update(over)
    return doc


# --------------------------------------------------------------- the two ways

def test_the_footer_says_not_needed_when_the_pins_in_force_cover_this_corpus(est):
    """a1's estate: the demo door, where `bootstrap.py` has already derived
    real G1/G2 and every episode is accepted. The footer must not tell that
    reader the walk is still owed."""
    row = est.skeleton_footer_row(SKELETON, measured(), ENGINE,
                                  {"pins_path": PINS}, True)
    assert "NOT NEEDED on this estate" in row
    assert PINS in row and "already carries them" in row
    # the sentence a1 read as contradicting the line above it is GONE here
    assert "until an inspected quarantined episode" not in row
    # and it still says what the file is and is not
    assert "NOT pins" in row and "#your-pins" in row


def test_the_footer_still_names_the_walk_when_the_pins_do_not_cover_it(est):
    """b1's estate: its own corpus, a foreign model, pins that cover neither.
    This reader IS owed the walk, and the line is unchanged for them."""
    row = est.skeleton_footer_row(SKELETON, measured(), ENGINE,
                                  {"pins_path": PINS}, False)
    assert "G1/G2 EMPTY until an inspected quarantined episode supplies them" in row
    assert "(#your-pins reads it)" in row
    assert "NOT NEEDED" not in row


def test_the_footer_reports_a_skeleton_that_could_not_be_written(est):
    """The third state is untouched: no skeleton, because the pins in force
    could not be read at all."""
    row = est.skeleton_footer_row(None, measured(), ENGINE, {"pins_path": PINS}, False)
    assert row.startswith(f"  (no {est.SKELETON_NAME}:")
    assert "the pins in force could not be read" in row
    assert "G1/G2" not in row


# ------------------------------------------------- the head, in both branches

@pytest.mark.parametrize("covered", [True, False])
def test_the_footer_head_carries_the_measurement_either_way(est, covered):
    row = est.skeleton_footer_row(SKELETON, measured(), ENGINE, {"pins_path": PINS}, covered)
    assert "the G6 tail measured (the end-of-turn id too)" in row
    assert ENGINE in row


@pytest.mark.parametrize("covered", [True, False])
def test_an_unmeasured_tail_says_so_in_both_branches(est, covered):
    row = est.skeleton_footer_row(
        SKELETON, measured(measured=False, end_of_turn_token_id=None), ENGINE,
        {"pins_path": PINS}, covered)
    assert "the G6 tail NOT measured" in row
    assert "the end-of-turn id NOT — see the skeleton measured.why" in row


@pytest.mark.parametrize("covered", [True, False])
def test_a_reused_measurement_is_labelled_in_both_branches(est, covered):
    """CP-99's audit: a measurement REUSED from the record is never printed as
    one taken this run. That label must survive the conditional."""
    row = est.skeleton_footer_row(
        SKELETON, measured(reused_from_record=True), ENGINE, {"pins_path": PINS}, covered)
    assert "reused from this run's record — the engine did not answer this time" in row


# ------------------------------------------------------ the screen, as a whole

def test_the_footer_and_the_pins_line_cannot_disagree_on_one_screen(est):
    """a1's finding as a property, not an anecdote: on a covered estate NEITHER
    line may claim the walk is owed; on an uncovered one BOTH may."""
    covered_row = est.skeleton_footer_row(SKELETON, measured(), ENGINE, {"pins_path": PINS}, True)
    owed = "until an inspected quarantined episode"
    assert owed not in covered_row
    uncovered_row = est.skeleton_footer_row(SKELETON, measured(), ENGINE, {"pins_path": PINS}, False)
    assert owed in uncovered_row


def test_the_demo_stdout_contract_prefixes_are_untouched(est):
    """The demo parses `== run <name> ==` and `next — `; this change moves a
    line inside that block and must not move the block's own markers."""
    source = ESTATE_PY.read_text(encoding="utf-8")
    assert '== run {name} == {rel}/' in source
    # the skeleton row is still indented as a run-block row, not a bare line
    row = est.skeleton_footer_row(SKELETON, measured(), ENGINE, {"pins_path": PINS}, True)
    assert row.startswith("  pins.skeleton.json") and row.endswith("\n")
