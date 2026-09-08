"""CP-97 (ADR-0042): `up` writes the pins SKELETON, never pins — the carried
sets from the pins in force, the G6 tail and the end-of-turn id measured from
the endpoint's own render (bring-your-own.md#your-model's measurement,
performed by `up`), the two derived sets and G4's empty, `not_measured` and
`coverage` stated. Two guards: the file is unusable as pins (the library
refuses the first empty approved set naming it; `up`/`update` refuse an
override that names a skeleton before anything runs), and the page's
derive_my_pins.py reads it so the walk starts from measured values.

Hermetic — no Docker daemon, no engine: the `http` seam is faked with
Qwen-, Llama-3- and Llama-2-shaped renders."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"
REPO = ESTATE_DIR.parent
STAGING = ESTATE_DIR / "corpus" / "staging"
PAGE = REPO / "docs" / "guide" / "bring-your-own.md"
FIDELITY_BODY = REPO / "docs" / "polar" / "h200-fidelity" / "callback_session_result.json"
THINKING_ON_BODY = REPO / "docs" / "polar" / "thinking" / "episode-on.quarantined.json"   # a receiver wrapper, G6 findings
HARNESS = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
ANCHOR = "a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56"

# the reference model's renders, as the CP-94 FakeEngine spells them
BASE = [151644, 872, 198, 9707, 13, 151645, 198]                 # <|im_start|>user\nHello.<|im_end|>\n
TAIL_OFF = [151644, 77091, 198, 151667, 271, 151668, 271]        # thinking off: the empty think block
TAIL_ON = [151644, 77091, 198]                                   # thinking on: <|im_start|>assistant\n
MARKER = [38, 50, 41, 2158, 51, 9660, 2523]                      # GSJPROBEMARKERXYZ
TEXT = {151645: "<|im_end|>", 198: "\n", 151644: "<|im_start|>", 77091: "assistant",
        151667: "<think>", 271: "\n\n", 151668: "</think>", 128009: "<|eot_id|>", 2: "</s>", 220: " "}


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp97", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "PH", module.Phases())
    return module


def fake_endpoint(monkeypatch, est, *, closer=(151645, 198), tail=None, detokenize=True,
                  messages_form=True, marker_in_render=True, extend=True):
    """A vLLM-shaped /tokenize + /detokenize: the one-turn render, the
    generation-prompt delta (`tail`, per the request's enable_thinking), the
    closed assistant turn `render + marker + closer`, and the marker alone."""
    calls = []

    def http(method, url, body=None, **kw):
        calls.append((url.rsplit("/", 1)[1], body))
        if url.endswith("/tokenize"):
            if "prompt" in body:
                return 200, {"tokens": list(MARKER)}
            if not messages_form:
                return 400, {"object": "error", "message": "messages is not a valid field"}
            on = body["chat_template_kwargs"]["enable_thinking"]
            t = tail if tail is not None else (TAIL_ON if on else TAIL_OFF)
            ids = list(BASE)
            if body["add_generation_prompt"]:
                ids += t
            elif len(body["messages"]) > 1:
                ids += (t if extend else [151644, 77091, 198, 9]) + (list(MARKER) if marker_in_render else [9, 9]) + list(closer)
            return 200, {"tokens": ids}
        if url.endswith("/detokenize"):
            if not detokenize:
                return 404, {"detail": "Not Found"}
            return 200, {"prompt": "".join(TEXT.get(t, "?") for t in body["tokens"])}
        return 404, {"detail": "Not Found"}

    monkeypatch.setattr(est, "http", http)
    return calls


# ------------------------------------------------------- the measurement

def test_measure_tail_reads_the_tail_and_the_terminator_from_the_endpoints_own_render(est, monkeypatch):
    """The page's #your-model measurement, performed by `up`: the ids
    add_generation_prompt adds under pi's kwargs, and the first
    non-whitespace token after assistant content in a closed turn."""
    calls = fake_endpoint(monkeypatch, est)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert m["measured"] and m["why"] is None
    assert m["g6_expected_tail_ids"] == TAIL_OFF
    assert m["g6_expected_tail_text"] == "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    assert m["end_of_turn_token_id"] == 151645 and m["end_of_turn_text"] == "<|im_end|>"
    assert m["history_extends_generation_prompt"] is True
    assert m["detokenize"] == "available"
    assert m["chat_template_kwargs"] == {"enable_thinking": False, "preserve_thinking": True}
    assert set(m["requests"]) == {"history_only", "with_generation_prompt", "assistant_closed", "marker"}
    for label in ("history_only", "with_generation_prompt", "assistant_closed"):
        req = m["requests"][label]["request"]
        assert req["chat_template_kwargs"] == {"enable_thinking": False, "preserve_thinking": True}
        assert req["add_special_tokens"] is False and req["model"] == "some/model"
        assert req["messages"][0] == {"role": "user", "content": [{"type": "text", "text": "Hello."}]}
    assert m["requests"]["marker"]["request"]["prompt"] == est.PROBE_MARKER
    assert [c for c, _ in calls].count("tokenize") == 4


def test_measure_tail_sends_pis_kwargs_for_the_thinking_level(est, monkeypatch):
    calls = fake_endpoint(monkeypatch, est)
    m = est.measure_tail("http://engine:8100", "some/model", "medium")
    assert m["measured"] and m["g6_expected_tail_ids"] == TAIL_ON
    assert m["chat_template_kwargs"] == {"enable_thinking": True, "preserve_thinking": True}
    assert all(body["chat_template_kwargs"]["enable_thinking"] is True
               for path, body in calls if path == "tokenize" and "messages" in body)
    assert est.pi_chat_template_kwargs("off") == {"enable_thinking": False, "preserve_thinking": True}


def test_measure_tail_without_detokenize_measures_the_tail_but_not_the_id_and_says_so(est, monkeypatch):
    """The demo's rule needs /detokenize to skip whitespace; without it the
    id would be a guess — a guess labelled measured is worse than the
    library default (the review's finding), so the tail is measured and the
    id is not, with the unverified token named."""
    fake_endpoint(monkeypatch, est, detokenize=False)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert m["measured"] and m["g6_expected_tail_ids"] == TAIL_OFF
    assert m["end_of_turn_token_id"] is None and m["end_of_turn_text"] is None and m["g6_expected_tail_text"] is None
    assert m["detokenize"] == "not available (POST /detokenize -> 404)"
    assert "the end-of-turn id was NOT measured (the tail was; the token after the content is 151645, unverified)" in m["why"]
    assert m["why"].endswith("bring-your-own.md#your-model")
    assert est.choose_end_of_turn(None, m, None, None) == (None, "default")
    assert est.choose_end_of_turn(None, m, 9, "measured") == (9, "record")


def test_measure_tail_reads_a_family_whose_closer_has_no_trailing_newline(est, monkeypatch):
    """Llama-3: `content<|eot_id|>` — the terminator is the last token."""
    fake_endpoint(monkeypatch, est, closer=(128009,), tail=[128006, 78191, 128007, 271])
    m = est.measure_tail("http://engine:8100", "meta-llama/Llama-3.1-8B-Instruct", "off")
    assert m["measured"] and m["end_of_turn_token_id"] == 128009 and m["end_of_turn_text"] == "<|eot_id|>"
    assert m["g6_expected_tail_ids"] == [128006, 78191, 128007, 271]


def test_measure_tail_skips_whitespace_before_the_terminator(est, monkeypatch):
    """Llama-2's ` </s>`: a space token precedes the closer — the demo's rule
    (the first NON-whitespace token) needs /detokenize to see it."""
    fake_endpoint(monkeypatch, est, closer=(220, 2), tail=[518, 29914, 25580, 29962])
    m = est.measure_tail("http://engine:8100", "llama-2", "off")
    assert m["measured"] and m["end_of_turn_token_id"] == 2 and m["end_of_turn_text"] == "</s>"


def test_measure_tail_names_an_endpoint_that_cannot_render_its_template(est, monkeypatch):
    fake_endpoint(monkeypatch, est, messages_form=False)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert not m["measured"] and m["g6_expected_tail_ids"] is None and m["end_of_turn_token_id"] is None
    assert "POST /tokenize (history_only) answered 400" in m["why"]
    assert "does not render its own chat template over the API" in m["why"]
    assert m["why"].endswith("bring-your-own.md#your-model")


def test_measure_tail_refuses_a_template_without_a_generation_prompt_delta(est, monkeypatch):
    fake_endpoint(monkeypatch, est, tail=[])
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert not m["measured"]
    assert "no clean, non-empty generation-prompt delta" in m["why"]


def test_measure_tail_names_a_render_that_hides_the_marker(est, monkeypatch):
    fake_endpoint(monkeypatch, est, marker_in_render=False)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert not m["measured"] and "were not found in the closed assistant render" in m["why"]


def test_measure_tail_flags_a_template_that_rewrites_history(est, monkeypatch):
    fake_endpoint(monkeypatch, est, extend=False)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert m["measured"] and m["history_extends_generation_prompt"] is False
    assert m["end_of_turn_token_id"] == 151645


def test_probe_engine_records_max_model_len(est, monkeypatch):
    monkeypatch.setattr(est, "http", lambda method, url, body=None, **kw:
                        (200, {"data": [{"id": "m", "max_model_len": 4096}]}) if url.endswith("/v1/models")
                        else (200, {"tokens": [1]}))
    p = est.probe_engine("http://engine:8100", "m")
    assert p["model_served"] and p["max_model_len"] == 4096 and p["tokenize"] == "available"


# ------------------------------------------------------- the id in force

def test_choose_end_of_turn_precedence(est):
    """flag > a recorded flag (an explicit answer persists) > the endpoint's
    own render > the record > nothing (the library default, said so)."""
    measured = {"measured": True, "end_of_turn_token_id": 248046}
    unmeasured = {"measured": False}
    assert est.choose_end_of_turn(7, measured, None, None) == (7, "flag")
    assert est.choose_end_of_turn("7", measured, 9, "measured") == (7, "flag")
    assert est.choose_end_of_turn(None, measured, 9, "flag") == (9, "flag")
    assert est.choose_end_of_turn(None, measured, 9, None) == (9, "flag")        # a 0.1.11 record: told, unlabelled
    assert est.choose_end_of_turn(None, measured, 9, "measured") == (248046, "measured")
    assert est.choose_end_of_turn(None, measured, None, None) == (248046, "measured")
    assert est.choose_end_of_turn(None, unmeasured, 9, "measured") == (9, "record")
    assert est.choose_end_of_turn(None, unmeasured, 9, "record") == (9, "record")
    assert est.choose_end_of_turn(None, unmeasured, 9, None) == (9, "flag")
    assert est.choose_end_of_turn(None, unmeasured, None, None) == (None, "default")
    assert est.choose_end_of_turn(None, {"measured": True, "end_of_turn_token_id": None}, None, None) == (None, "default")


def test_reuse_measurement_keeps_the_records_measurement_of_the_same_endpoint(est):
    """A re-run whose engine did not answer must not overwrite a measured
    skeleton with an unmeasured stub (the review's finding)."""
    prior = {"tail": {"measured": True, "engine": "http://e", "model": "m", "thinking": "off",
                      "g6_expected_tail_ids": TAIL_OFF, "end_of_turn_token_id": 151645}}
    stub = {"measured": False, "why": "http://e is not reachable — nothing was rendered"}
    reused = est.reuse_measurement(prior, stub, "http://e", "m", "off")
    assert reused["measured"] and reused["reused_from_record"] and reused["g6_expected_tail_ids"] == TAIL_OFF
    assert reused["requests"] == {} and reused["why"].startswith("this run: http://e is not reachable")
    assert est.reuse_measurement(prior, stub, "http://other", "m", "off") is stub          # another endpoint
    assert est.reuse_measurement(prior, stub, "http://e", "m", "medium") is stub           # another level
    assert est.reuse_measurement({}, stub, "http://e", "m", "off") is stub                 # nothing recorded
    fresh = {"measured": True, "end_of_turn_token_id": 1}
    assert est.reuse_measurement(prior, fresh, "http://e", "m", "off") is fresh            # this run measured


def test_pi_thinking_level_normalises_yamls_bool_and_refuses_a_non_level(est, capsys):
    """`thinking: off` in an --answers file arrives as False (YAML 1.1); a
    non-level is refused before the skeleton is measured under the wrong kwargs."""
    assert est.pi_thinking_level(False) == "off" and est.pi_thinking_level("off") == "off"
    assert est.pi_thinking_level("medium") == "medium"
    for raw in (True, "on", "bogus"):
        with pytest.raises(SystemExit) as exc:
            est.pi_thinking_level(raw)
        assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "--thinking is not a pi level." in err and "off|minimal|low|medium|high|xhigh|max" in err
    assert "YAML 1.1 reads a bare off/on as a boolean" in err


# -------------------------------------------------------- the skeleton

def staging_inputs(est, monkeypatch, *, thinking="off", measured=True):
    if not STAGING.is_dir():
        pytest.skip("the checkout's staging corpus")
    corpus = est.load_corpus(STAGING, None, HARNESS)
    g1 = est.pins_g1_check(corpus)
    assert g1["checked"]
    if measured:
        fake_endpoint(monkeypatch, est)
        m = est.measure_tail("http://engine:8100", "Qwen/Qwen3-0.6B", thinking)
    else:
        m = {"measured": False, "why": "http://engine:8100 is not reachable — nothing was rendered",
             "engine": "http://engine:8100", "model": "Qwen/Qwen3-0.6B", "thinking": thinking,
             "chat_template_kwargs": est.pi_chat_template_kwargs(thinking),
             "g6_expected_tail_ids": None, "g6_expected_tail_text": None,
             "end_of_turn_token_id": None, "end_of_turn_text": None,
             "history_extends_generation_prompt": None, "detokenize": None, "requests": {}}
    probe = {"url": "http://engine:8100", "model": "Qwen/Qwen3-0.6B", "reachable": measured,
             "models": ["Qwen/Qwen3-0.6B"] if measured else [], "model_served": measured,
             "tokenize": "available" if measured else None, "max_model_len": 32768 if measured else None,
             "probed_at": "2026-09-08T00:00:00Z"}
    return corpus, g1, probe, m


def test_pins_skeleton_has_the_pins_shape_under_its_own_format(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    doc = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, 151645, "measured", "off")
    path = est.write_pins_skeleton(tmp_path, doc)
    assert path == tmp_path / "pins.skeleton.json"
    on_disk = json.loads(path.read_text())
    assert on_disk["format"] == "gsj-pins-skeleton/1" and on_disk["format"] != "gsj-pins/1"
    in_force = json.loads(Path(g1["pins_path"]).read_text())["pins"]
    sets = on_disk["pins"]
    assert set(sets) == {"skill_card_hash", "system_prompt_hash", "tool_roster_hash", "settings_hash",
                         "g6_expected_tail_ids", "tokenizer_hash", "chat_template_hash"}
    assert sets["tool_roster_hash"] == in_force["tool_roster_hash"] == [ANCHOR]
    assert sets["settings_hash"] == in_force["settings_hash"]
    assert sets["g6_expected_tail_ids"] == [TAIL_OFF]
    assert sets["skill_card_hash"] == [] and sets["system_prompt_hash"] == []
    assert sets["tokenizer_hash"] == [] and sets["chat_template_hash"] == []
    assert "mode" not in on_disk
    assert on_disk["in_force"] == {"end_of_turn_token_id": 151645, "source": "measured",
                                   "note": on_disk["in_force"]["note"]}
    assert on_disk["measured"]["end_of_turn_token_id"] == 151645
    assert on_disk["measured"]["requests"]["with_generation_prompt"]["response"]["tokens"] == BASE + TAIL_OFF
    # what only an inspected episode supplies is NAMED, never filled
    supplied = on_disk["supplied_by_an_inspected_episode"]
    assert supplied["system_prompt_hash"].startswith("G2 — sha256 of the wire system prompt")
    assert "2 card(s)" in supplied["skill_card_hash"]
    for name, card in corpus.skills.items():
        assert hashlib.sha256(card.read_bytes()).hexdigest() in supplied["skill_card_hash"]
    # the page's blocks
    # CP-99: the two derived rows say whose emptiness this is — the FILE's, not
    # the estate's. Here the fixture's pins in force cover every card, so both
    # rows say so (a1 asked why a demo with usable pins is handed a skeleton
    # announcing an undone walk; the file answers now instead of restating it).
    assert on_disk["coverage"]["skill_card_hash"].startswith("NOT DERIVED YET in THIS file — empty")
    assert on_disk["coverage"]["system_prompt_hash"].startswith("NOT DERIVED YET in THIS file — empty")
    assert "already carry it and cover every skill card in this corpus" in on_disk["coverage"]["skill_card_hash"]
    assert on_disk["walk_status"]["derive"].startswith("NOT NEEDED on this estate")
    assert on_disk["coverage"]["tool_roster_hash"].startswith("carried from the pins in force")
    assert on_disk["coverage"]["g6_expected_tail_ids"].startswith("measured here from the endpoint's own render")
    assert on_disk["coverage"]["tokenizer_hash"].startswith("NOT MEASURED")
    assert on_disk["coverage"]["sampling_policy"].startswith("UNKNOWN")
    assert any(n.startswith("tokenizer_hash (G4") for n in on_disk["not_measured"])
    assert any("tool-call parser" in n for n in on_disk["not_measured"])
    prov = on_disk["provenance"]
    assert prov["engine"]["served_model"]["id"] == "Qwen/Qwen3-0.6B" and prov["engine"]["max_model_len"] == 32768
    assert prov["engine"]["carried_from"]["path"] == g1["pins_path"]
    assert prov["engine"]["carried_from"]["block"]["served_model"]["id"] == "Qwen/Qwen3-0.6B"
    assert "http://engine:8100/tokenize" in prov["g6_expected_tail_ids"]["artifacts"]
    assert "derive_my_pins.py" in on_disk["walk_status"]["derive"]
    assert "NOT A PINS FILE" in on_disk["skeleton"] and "GSJ_PINS_PATH must never name this file" in on_disk["skeleton"]


def test_pins_skeleton_for_a_thinking_level_carries_the_mode_and_the_on_tail(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch, thinking="medium")
    doc = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, 151645, "measured", "medium")
    assert doc["mode"] == "thinking-on" and doc["pins"]["g6_expected_tail_ids"] == [TAIL_ON]
    assert doc["measured"]["chat_template_kwargs"] == {"enable_thinking": True, "preserve_thinking": True}


def test_pins_skeleton_says_when_only_the_id_is_unmeasured(est, monkeypatch, tmp_path):
    corpus, g1, probe, _ = staging_inputs(est, monkeypatch)
    fake_endpoint(monkeypatch, est, detokenize=False)
    m = est.measure_tail("http://engine:8100", "Qwen/Qwen3-0.6B", "off")
    doc = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, None, "default", "off")
    assert doc["pins"]["g6_expected_tail_ids"] == [TAIL_OFF]
    assert "(NOT the end-of-turn id — see measured.why)" in doc["host"] and "measured from" in doc["host"]
    assert doc["not_measured"][-1].startswith("end_of_turn_token_id — see measured.why (the tail was measured)")
    assert doc["in_force"]["source"] == "default"


def test_pins_skeleton_carries_the_in_force_engine_block_without_its_own_carried_from(est, monkeypatch, tmp_path):
    """A pins.gsj.json the page's script derived from an earlier skeleton
    carries provenance.engine with a carried_from inside; the next `up`
    under it must not nest one level per re-pin (the review's finding)."""
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    first = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, 151645, "measured", "off")
    derived = json.loads(Path(g1["pins_path"]).read_text())
    derived["provenance"]["engine"] = first["provenance"]["engine"]      # what the page's script copies
    derived_path = tmp_path / "pins.gsj.json"
    derived_path.write_text(json.dumps(derived))
    g1_derived = {**g1, "pins_path": str(derived_path), "pins_source": "GSJ_PINS_PATH"}
    second = est.pins_skeleton(tmp_path, "canary", corpus, g1_derived, probe, m, 151645, "measured", "off")
    block = second["provenance"]["engine"]["carried_from"]["block"]
    assert "carried_from" not in block and block["served_model"]["id"] == "Qwen/Qwen3-0.6B"
    assert second["provenance"]["engine"]["carried_from"]["what"].startswith("this endpoint as an earlier `up` probed it")
    assert first["provenance"]["engine"]["carried_from"]["what"].startswith("the pins in force's provenance.engine")


def test_pins_skeleton_says_what_it_could_not_measure(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch, measured=False)
    doc = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, None, "default", "off")
    assert doc["pins"]["g6_expected_tail_ids"] == []
    assert doc["coverage"]["g6_expected_tail_ids"].startswith("NOT MEASURED — empty")
    assert doc["provenance"]["g6_expected_tail_ids"]["algo"].startswith("NOT MEASURED — http://engine:8100 is not reachable")
    assert any(n.startswith("g6_expected_tail_ids and end_of_turn_token_id") for n in doc["not_measured"])
    assert "NOT measured" in doc["host"]
    assert doc["in_force"] == {"end_of_turn_token_id": None, "source": "default", "note": doc["in_force"]["note"]}


# ------------------------------------------- unusable as pins, two ways

def test_the_library_refuses_a_skeleton_named_by_gsj_pins_path(est, monkeypatch, tmp_path):
    """A consumer who points GSJ_PINS_PATH at the skeleton gets a refusal
    naming the empty set and the file — the receiver's 500, the trainer's
    raise — never a silent partial validation. A fresh process: the library
    resolves GSJ_PINS_PATH once, at import."""
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    path = est.write_pins_skeleton(tmp_path, est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m,
                                                               151645, "measured", "off"))
    code = ("import json, sys\nfrom gsj_rollout import checks\n"
            "body = json.load(open(sys.argv[1]))\n"
            "try:\n    print('FINDINGS', checks.validate_session_result(body)); sys.exit(3)\n"
            "except checks.PinsConfigurationError as exc:\n    print('REFUSED', exc)\n")
    env = {**os.environ, "GSJ_PINS_PATH": str(path)}
    proc = subprocess.run([sys.executable, "-c", code, str(FIDELITY_BODY)], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("REFUSED pins key ")
    assert "missing, empty, or not a list" in proc.stdout and str(path) in proc.stdout
    key = re.search(r"pins key '([a-z_0-9]+)'", proc.stdout).group(1)
    assert key in ("system_prompt_hash", "skill_card_hash"), key
    assert "FINDINGS" not in proc.stdout


def test_refuse_skeleton_pins_stops_before_anything_runs(est, monkeypatch, capsys, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    path = est.write_pins_skeleton(tmp_path, est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m,
                                                               151645, "measured", "off"))
    monkeypatch.setenv("GSJ_PINS_PATH", str(path))
    with pytest.raises(SystemExit) as exc:
        est.refuse_skeleton_pins()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "GSJ_PINS_PATH names a pins SKELETON, not pins." in err
    assert str(path) in err and "format 'gsj-pins-skeleton/1'" in err
    assert "empty approved sets: ['chat_template_hash', 'skill_card_hash', 'system_prompt_hash', 'tokenizer_hash']" in err
    # CP-99 (a2, F9): the anchor no longer runs into the prose — a terminal
    # linkifies `…#your-pins's` and the reader gets a 404 on the one file the
    # refusal is about. The URL ends at a space now, on all three sites.
    assert "#your-pins — its derive_my_pins.py reads the skeleton — and" in err
    assert "#your-pins's" not in err
    assert "never at pins.skeleton.json" in err
    assert "found:" in err and "expected:" in err and "what to do:" in err


def test_refuse_skeleton_pins_lets_real_pins_and_an_unset_override_through(est, monkeypatch, tmp_path):
    import gsj_rollout.checks as checks
    monkeypatch.delenv("GSJ_PINS_PATH", raising=False)
    est.refuse_skeleton_pins()
    monkeypatch.setenv("GSJ_PINS_PATH", str(checks.PINS_PATH))
    est.refuse_skeleton_pins()
    monkeypatch.setenv("GSJ_PINS_PATH", str(tmp_path / "absent.json"))
    est.refuse_skeleton_pins()          # the library's own refusal names it, on first use
    (tmp_path / "broken.json").write_text("{not json")
    monkeypatch.setenv("GSJ_PINS_PATH", str(tmp_path / "broken.json"))
    est.refuse_skeleton_pins()


def test_up_refuses_a_skeleton_in_force_before_the_corpus_is_read(est, monkeypatch, capsys, tmp_path):
    """The refusal sits with the interpreter checks — before the corpus, the
    run directory, the .env, any container."""
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    path = est.write_pins_skeleton(tmp_path, est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m,
                                                               151645, "measured", "off"))
    monkeypatch.setenv("GSJ_PINS_PATH", str(path))
    monkeypatch.setattr(est, "load_corpus", lambda *a, **k: pytest.fail("the corpus was read"))
    args = argparse.Namespace(answers=None, defaults=True, corpus=str(tmp_path / "no-such-corpus"),
                              name="skeleton-canary")
    with pytest.raises(SystemExit) as exc:
        est.cmd_up(args)
    assert exc.value.code == 1
    assert "GSJ_PINS_PATH names a pins SKELETON" in capsys.readouterr().err
    assert not (tmp_path / "skeleton-canary").exists()


def test_update_refuses_a_skeleton_in_force_before_the_record_is_read(est, monkeypatch, capsys, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    path = est.write_pins_skeleton(tmp_path, est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m,
                                                               151645, "measured", "off"))
    monkeypatch.setenv("GSJ_PINS_PATH", str(path))
    (tmp_path / "canary").mkdir()
    (tmp_path / "canary" / "run.json").write_text("{}")   # the wrapper's own existence check passes
    monkeypatch.setattr(est, "_load_run", lambda *a, **k: pytest.fail("the record was read"))
    with pytest.raises(SystemExit) as exc:
        est.cmd_update(argparse.Namespace(name="canary", corpus=None, dry_run=False))
    assert exc.value.code == 1
    assert "GSJ_PINS_PATH names a pins SKELETON" in capsys.readouterr().err


# ------------------------------------------- the page's script reads it

def page_scripts() -> list[str]:
    if not PAGE.is_file():
        pytest.skip("docs/guide/bring-your-own.md is not in this tree")
    blocks = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.S)
    assert "bring-your-own.md#your-model" in blocks[0]
    assert "bring-your-own.md#your-pins" in blocks[1]
    return blocks


def quarantined_run(est, tmp_path, doc, body_path: Path = FIDELITY_BODY) -> Path:
    """A run directory after the walk's step 2: the skeleton `up` wrote and
    one quarantined body — the tracked fidelity episode (the reference
    model, the staging corpus) wrapped as the receiver writes it, or a
    tracked receiver wrapper as is."""
    run = tmp_path / "run"
    (run / "traces" / "quarantine").mkdir(parents=True)
    if doc is not None:
        est.write_pins_skeleton(run, doc)
    raw = json.loads(body_path.read_bytes())
    if "session_result" in raw:
        wrapper, body = raw, raw["session_result"]
    else:
        body = raw
        wrapper = {"findings": ["G2:system_prompt_hash_not_approved:0000", "G6:prompt_suffix_ne_tail_ids"],
                   "session_result": body}
    (run / "traces" / "quarantine" / f"{body['session_id']}.json").write_text(json.dumps(wrapper))
    return run


def run_derive(script: str, run: Path, tmp_path: Path, **env) -> subprocess.CompletedProcess:
    (tmp_path / "derive_my_pins.py").write_text(script)
    environ = {k: v for k, v in os.environ.items() if k != "GSJ_PINS_PATH"}
    environ.update({"RUN": str(run), "CORPUS": str(STAGING), **env})
    return subprocess.run([sys.executable, str(tmp_path / "derive_my_pins.py")], env=environ,
                          cwd=tmp_path, capture_output=True, text=True, timeout=180)


def test_the_pages_derive_script_starts_from_the_skeleton(est, monkeypatch, tmp_path):
    """#your-pins's derive_my_pins.py reads pins.skeleton.json where it
    exists: the tail `up` measured (no PROBE needed), the endpoint's
    provenance, the mode — and still derives the two, still asserts the
    carried ones against the reference."""
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    run = quarantined_run(est, tmp_path, est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m,
                                                           151645, "measured", "off"))
    proc = run_derive(page_scripts()[1], run, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"skeleton read {run / 'pins.skeleton.json'} (tail measured by up)" in proc.stdout
    out = json.loads((run / "pins.gsj.json").read_text())
    assert out["format"] == "gsj-pins/1"
    body = json.loads(FIDELITY_BODY.read_bytes())
    trace = body["trajectory"]["traces"][0]
    wire = next(mm["content"] for mm in trace["prompt_messages"] if mm["role"] == "system")
    assert out["pins"]["system_prompt_hash"] == [hashlib.sha256(wire.encode()).hexdigest()]
    assert sorted(out["pins"]["skill_card_hash"]) == sorted(
        hashlib.sha256(c.read_bytes()).hexdigest() for c in STAGING.glob("skills/*/SKILL.md"))
    assert out["pins"]["tool_roster_hash"] == [ANCHOR]
    assert out["pins"]["g6_expected_tail_ids"] == [TAIL_OFF]
    assert "as `up` measured it (pins.skeleton.json)" in out["provenance"]["g6_expected_tail_ids"]["algo"]
    assert str(run / "pins.skeleton.json") in out["provenance"]["g6_expected_tail_ids"]["artifacts"]
    assert out["provenance"]["engine"]["served_model"]["id"] == "Qwen/Qwen3-0.6B"
    assert out["coverage"]["g6_expected_tail_ids"].startswith("derived here from the endpoint's own render")
    assert "pins.skeleton.json" in out["host"]
    assert "mode" not in out
    assert any("tool-call parser IDENTITY (a serve flag) and its PRESENCE" in n for n in out["not_measured"])
    assert not any(n.startswith(("g6_expected_tail_ids", "end_of_turn_token_id")) for n in out["not_measured"])
    # the derived file is real pins: the library reads it
    monkeypatch.setenv("GSJ_PINS_PATH", str(run / "pins.gsj.json"))
    est.refuse_skeleton_pins()


def test_the_pages_derive_script_takes_the_skeletons_tail_not_the_references(est, monkeypatch, tmp_path):
    """The thinking-on body's turn openings end with the ON tail, which is
    not the reference file's; only a skeleton measured for a thinking level
    lets the walk approve it — and the mode rides from the skeleton."""
    corpus, g1, probe, m = staging_inputs(est, monkeypatch, thinking="medium")
    run = quarantined_run(est, tmp_path, est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m,
                                                           151645, "measured", "medium"), body_path=THINKING_ON_BODY)
    proc = run_derive(page_scripts()[1], run, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads((run / "pins.gsj.json").read_text())
    assert out["pins"]["g6_expected_tail_ids"] == [TAIL_ON] and out["mode"] == "thinking-on"
    assert "as `up` measured it (pins.skeleton.json)" in out["provenance"]["g6_expected_tail_ids"]["algo"]
    # the same body without a skeleton stops at the first turn opening: the reference tail is the OFF one
    run2 = quarantined_run(est, tmp_path / "second", None, body_path=THINKING_ON_BODY)
    proc2 = run_derive(page_scripts()[1], run2, tmp_path / "second")
    assert proc2.returncode == 1 and "turn 1's opening does not end with the tail" in proc2.stderr
    assert not (run2 / "pins.gsj.json").exists()


def test_the_pages_derive_script_refuses_an_explicit_skeleton_path_that_does_not_exist(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    run = quarantined_run(est, tmp_path, est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m,
                                                           151645, "measured", "off"))
    proc = run_derive(page_scripts()[1], run, tmp_path, SKELETON=str(tmp_path / "typo.json"))
    assert proc.returncode == 1 and "does not exist: name the pins.skeleton.json `up` wrote" in proc.stderr
    assert not (run / "pins.gsj.json").exists()


def test_the_pages_derive_script_does_not_carry_an_unserved_engines_block(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch, measured=False)
    run = quarantined_run(est, tmp_path, est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m,
                                                           None, "default", "off"))
    proc = run_derive(page_scripts()[1], run, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "engine block NOT carried: `up` probed 'Qwen/Qwen3-0.6B' before it was served" in proc.stdout
    assert "skeleton read" in proc.stdout and "(tail not measured by up)" in proc.stdout
    out = json.loads((run / "pins.gsj.json").read_text())
    assert "engine" not in out["provenance"] and out["pins"]["g6_expected_tail_ids"] == [TAIL_OFF]
    assert "the packaged reference tail" in out["provenance"]["g6_expected_tail_ids"]["algo"]


def test_the_pages_derive_script_refuses_a_skeleton_carried_from_another_set(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    doc = est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m, 151645, "measured", "off")
    doc["pins"]["settings_hash"] = ["0" * 64]
    run = quarantined_run(est, tmp_path, doc)
    proc = run_derive(page_scripts()[1], run, tmp_path)
    assert proc.returncode == 1
    assert "the skeleton's settings_hash is not the reference's" in proc.stderr
    assert not (run / "pins.gsj.json").exists()


def test_the_pages_derive_script_refuses_a_skeleton_and_a_probe_that_disagree(est, monkeypatch, tmp_path):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    run = quarantined_run(est, tmp_path, est.pins_skeleton(tmp_path / "run", "canary", corpus, g1, probe, m,
                                                           151645, "measured", "off"))
    (tmp_path / "model-probe.json").write_text(json.dumps(
        {"derived": {"g6_expected_tail_ids": [1, 2, 3], "end_of_turn_token_id": 5}}))
    proc = run_derive(page_scripts()[1], run, tmp_path, PROBE=str(tmp_path / "model-probe.json"))
    assert proc.returncode == 1
    assert "measured different tails" in proc.stderr


def test_the_pages_derive_script_still_works_without_a_skeleton(est, monkeypatch, tmp_path):
    """Older wheels wrote none: the reference tail on the reference model."""
    if not STAGING.is_dir():
        pytest.skip("the checkout's staging corpus")
    run = quarantined_run(est, tmp_path, None)
    proc = run_derive(page_scripts()[1], run, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "skeleton read" not in proc.stdout
    out = json.loads((run / "pins.gsj.json").read_text())
    assert out["pins"]["g6_expected_tail_ids"] == [TAIL_OFF]
    assert "the packaged reference tail" in out["provenance"]["g6_expected_tail_ids"]["algo"]


# ------------------------------------------------------------- the help

def test_up_help_says_the_end_of_turn_id_is_measured_and_the_flag_overrides():
    proc = subprocess.run([sys.executable, str(ESTATE_PY), "up", "--help"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    text = " ".join(proc.stdout.split())
    assert "`up` MEASURES it from the endpoint's own render" in text
    assert "recorded in pins.skeleton.json with the G6 tail" in text
    assert "this flag overrides the measurement" in text
    assert "stands only when nothing could be measured" in text
