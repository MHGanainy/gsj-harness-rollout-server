"""CP-104: what the last stranger round (round seven, 2026-09-09, against
0.1.14) found in estate.py, and the ordering nobody had written down.

- b1's finding 1: `up`'s closing block said "the published gsj-polar image"
  and spelled nothing pullable — `polar_image_ref()` names the tag A-28 cuts
  for this library version, and the wheel's NOTE carries it with the page.
- b1's finding 2: `submit --row N` indexes a parquet nothing shipped could
  print — `bank_rows_lines()` lists the rows in the closing block and in
  every `status` that has a bank.
- b1's finding 3: the heartbeat's verdict was binary — the tally's age rides
  on the line, and past a floor `the pipe is moving` says whose bytes.
- b2's finding 2: a transfer cut by `unexpected EOF` was refused with tag,
  mirror and digest advice — it is its own kind now, and the cure leads with
  the same command again.
- b2's finding 3: an `up` that died before run.json left a marker, and
  `status` said `no run named` — it names the first phase and the resume.
- b2's finding 4: the closing `status`/`down` pair and the generated
  rollout.yaml header dropped `--runs-dir` and `--corpus` — spelled, always.
- the row-102 near miss (b1's step 16): "refused on first use" — the
  admission gates run before any pins are read, measured on the real
  checks.py in a separate process, exactly as b1 tested it.

Hermetic — no Docker daemon, no estate; the pull is the CP-96 FakePull on the
`popen` seam, the CLI runs behind the CP-94 docker canary."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import FakePull
from test_estate_cp94_round3 import fake_docker, invoke, partial_run
from test_estate_cp97_skeleton import staging_inputs

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"
REPO = ESTATE_DIR.parent
STAGING_BANK = ESTATE_DIR / "corpus" / "staging" / "taskbank.parquet"
FIDELITY_BODY = REPO / "docs" / "polar" / "h200-fidelity" / "callback_session_result.json"


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp104", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    return module


# ------------------------------------------------ b1 (1): the image, spelled

def test_polar_image_ref_is_the_tag_a28_cuts_for_this_version(est):
    import gsj_rollout
    ref = est.polar_image_ref()
    sha = (REPO / "POLAR_SHA").read_text().splitlines()[0].split("=", 1)[1].strip()
    assert ref == f"ghcr.io/mhganainy/gsj-polar:{sha[:8]}-gsj{gsj_rollout.__version__}"
    assert ref.startswith("ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj")


def test_polar_image_ref_from_a_wheel_uses_the_recorded_short_sha(est, monkeypatch):
    monkeypatch.setattr(est, "CHECKOUT", False)
    import gsj_rollout
    assert est.polar_image_ref() == f"ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj{gsj_rollout.__version__}"


def test_the_wheels_closing_note_names_the_pullable_image_and_the_page(est, monkeypatch):
    monkeypatch.setattr(est, "CHECKOUT", False)
    note = est.polar_route_note()
    assert est.polar_image_ref() in note
    assert "anonymously pullable" in note and "one clause per flag" in note
    assert note.index("bring-your-own.md#polars-two-processes") > note.index(est.polar_image_ref())
    assert "git clone https://github.com/MHGanainy/gsj-harness-rollout-server" in note
    assert "gsj-rollout-demo's shape" not in note        # the old pointer at a second repo


def test_a_checkout_prints_no_note(est, monkeypatch):
    monkeypatch.setattr(est, "CHECKOUT", True)
    assert est.polar_route_note() == ""


# ------------------------------------------------ b1 (2): the bank has a reader

def test_bank_rows_lines_list_index_case_timestep_prompt_id_and_split(est):
    lines = est.bank_rows_lines(STAGING_BANK, limit=100)
    rows = est.ic.read_taskbank_rows(STAGING_BANK)
    assert len(lines) == len(rows) >= 2
    for i, (line, row) in enumerate(zip(lines, rows)):
        assert line == (f"    --row {i:<3} {row['case_id']}@{row['timestep']}  "
                        f"{row['prompt_id']}  [{row['split']}]")
    # the bank's own order: (case_id, timestep, prompt_id) — `free:` before `skill:`
    keys = [(r["case_id"], r["timestep"], r["prompt_id"]) for r in rows]
    assert keys == sorted(keys)


def test_bank_rows_lines_cap_a_long_bank_and_say_how_it_is_sorted(est):
    rows = est.ic.read_taskbank_rows(STAGING_BANK)
    lines = est.bank_rows_lines(STAGING_BANK, limit=2)
    assert len(lines) == 3 and lines[0].startswith("    --row 0  ")
    assert lines[-1] == f"    … {len(rows) - 2} more row(s); the bank is sorted by (case_id, timestep, prompt_id)"


def test_bank_rows_lines_name_an_unreadable_bank_instead_of_raising(est, tmp_path):
    bad = tmp_path / "taskbank.parquet"
    bad.write_bytes(b"not parquet")
    (line,) = est.bank_rows_lines(bad)
    assert line.startswith("    (rows not listed — PipelineError: ")


def test_status_lists_the_rows_when_the_run_has_a_bank(tmp_path):
    """The incomplete report (CP-92's path, the lock free) — the bank was
    copied into the run before the record stopped, so the rows are there."""
    rd = partial_run(tmp_path)
    (rd / "taskbank.parquet").write_bytes(STAGING_BANK.read_bytes())
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1, proc.stderr
    assert "taskbank  ? rows — what `submit --row N` addresses:" in proc.stdout
    assert "    --row 0   case_0001@" in proc.stdout
    assert "--runs-dir" in proc.stderr and "to resume" in proc.stderr


def test_status_without_a_bank_lists_nothing(tmp_path):
    partial_run(tmp_path)
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert "submit --row N" not in proc.stdout


# ------------------------------------------------ b2 (3): died before the record

def test_status_on_a_marker_only_run_dir_names_the_first_phase_and_the_resume(tmp_path):
    """b2's `up` was cut by `unexpected EOF` in the Forgejo pull, before
    run.json existed; `status` then said `no run named codex` for a directory
    it had called ACTIVE minutes earlier."""
    rd = tmp_path / "codex"
    rd.mkdir()
    (rd / ".estate-run").write_text("estate run codex\n")
    proc = invoke(tmp_path, "status", "--name", "codex")
    assert proc.returncode == 1
    assert "no run named" not in proc.stderr
    assert "started and stopped before its record was written" in proc.stderr
    assert "ownership marker and no run.json" in proc.stderr
    assert "Forgejo image pull or its health wait" in proc.stderr
    assert f"up --name codex --corpus <the corpus root you gave up> --runs-dir {tmp_path}" in proc.stderr
    assert "docker ps -a --filter name=gsj-codex-" in proc.stderr


def test_status_on_a_directory_that_is_not_ours_still_says_no_run_named(tmp_path):
    (tmp_path / "stray").mkdir()
    (tmp_path / "stray" / "notes.txt").write_text("somebody else's")
    proc = invoke(tmp_path, "status", "--name", "stray")
    assert proc.returncode == 1 and "no run named 'stray'" in proc.stderr
    assert "started and stopped" not in proc.stderr


# ------------------------------------------------ b2 (4): every printed command is complete

def test_manage_hint_spells_the_runs_root_on_both_commands(est, tmp_path):
    hint = est.manage_hint("codex", tmp_path)
    assert hint == (f"{est.PROG} status --name codex --runs-dir {tmp_path}    |    "
                    f"{est.PROG} down --name codex --runs-dir {tmp_path} [--wipe]")


def test_the_printed_commands_name_the_interpreter_from_a_wheel(est, tmp_path, monkeypatch):
    """b2's finding 4, second half: a bare `python` is whichever is first on
    PATH; from a wheel the printed command names the interpreter that ran up."""
    monkeypatch.setattr(est, "CHECKOUT", False)
    prog = f"{sys.executable} -m gsj_rollout.estate"
    assert est.runnable_prog() == prog
    assert est.manage_hint("codex", tmp_path).startswith(f"{prog} status --name codex --runs-dir {tmp_path}")
    assert est.rerun_hint("codex", "--corpus /c", tmp_path) == f"{prog} up --name codex --corpus /c --runs-dir {tmp_path}"


def test_the_tools_help_names_the_documentation_and_why_32768(est):
    proc = subprocess.run([sys.executable, str(ESTATE_PY), "--help"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "https://github.com/MHGanainy/gsj-harness-rollout-server/tree/main/docs/guide" in proc.stdout
    up = subprocess.run([sys.executable, str(ESTATE_PY), "up", "--help"], capture_output=True, text=True, timeout=60)
    # argparse wraps help at hyphens too (`--max-` / `model-len`): compare with all whitespace removed
    assert "thereferenceestate'sserved--max-model-len" in "".join(up.stdout.split())


def test_rerun_hint_carries_the_corpus_and_the_runs_root(est, tmp_path):
    assert est.rerun_hint("codex", "--corpus /c", tmp_path) == f"{est.PROG} up --name codex --corpus /c --runs-dir {tmp_path}"


def test_the_incomplete_reports_resume_cure_is_the_complete_up(tmp_path):
    partial_run(tmp_path)
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert f"up --name canary --corpus {tmp_path / 'corpus'} --runs-dir {tmp_path}` to resume" in proc.stderr


# ------------------------------------------------ b2 (2): a cut transfer, its own kind

@pytest.mark.parametrize("stderr", ["unexpected EOF",
                                    "read tcp 10.0.0.2:5555->1.2.3.4:443: i/o timeout",
                                    "read: connection reset by peer"])
def test_a_cut_transfer_is_its_own_kind(est, stderr):
    assert est.pull_failure_kind(stderr) == "transfer"


@pytest.mark.parametrize("stderr", ["manifest unknown", "dial tcp: lookup ghcr.io: no such host",
                                    "dial tcp 1.2.3.4:443: connect: connection refused",
                                    "dial tcp 1.2.3.4:443: i/o timeout",        # the registry never answered
                                    "net/http: TLS handshake timeout"])
def test_a_registry_that_did_not_answer_stays_a_download_failure(est, stderr):
    assert est.pull_failure_kind(stderr) == "download"


def test_an_extraction_failure_outranks_a_transfer_mark(est):
    assert est.pull_failure_kind("unexpected EOF … failed to extract layer") == "extract"


def test_the_transfer_cure_leads_with_the_same_command_and_keeps_the_registry_advice_second(est):
    advice = "pass --forgejo-image <ref> naming a live one"
    fix = est.pull_failure_fix("transfer", "codeberg.org/forgejo/forgejo:16.0.3", advice)
    assert fix.startswith("re-run the same command first")
    assert "the daemon keeps every layer that completed" in fix
    assert "`Retrying in N seconds` on its own is the pull recovering" in fix
    assert "troubleshooting.md, the pull row" in fix
    assert fix.index("fails the same way twice") < fix.index(advice)
    # the other kinds are what they were
    assert est.pull_failure_fix("download", "x", advice) == advice
    assert "docker run --rm alpine true" in est.pull_failure_fix("extract", "x", advice)


def test_the_transfer_expectation_names_the_cut_and_the_others_are_unchanged(est):
    registry = "a pullable image (both platform manifests served)"
    assert "connection was cut" in est.pull_failure_expected("transfer", registry)
    assert "unexpected EOF" in est.pull_failure_expected("transfer", registry)
    assert est.pull_failure_expected("download", registry) == registry
    assert est.pull_failure_expected("extract", registry) == "a daemon whose storage can extract and mount OCI layers"


# ------------------------------------------------ b1 (3): the tally's age on the heartbeat

PULL_LINES = ["pi0.83.0-3: Pulling from mhganainy/gsj-pi-harness\n",
              "a1b2c3d4e5f6: Pulling fs layer\n", "0f1e2d3c4b5a: Pulling fs layer\n",
              "a1b2c3d4e5f6: Downloading\n", "0f1e2d3c4b5a: Downloading\n"]


def test_pull_tally_age_and_caveat_are_empty_while_the_tally_moves(est, monkeypatch):
    monkeypatch.setattr(est, "PULL_HEARTBEAT_S", 60.0)
    assert est.pull_tally_age(0) == "" and est.pull_moving_caveat(0) == ""
    assert est.pull_tally_age(1) == ", unchanged for 1m"
    assert est.pull_tally_age(17) == ", unchanged for 17m"
    assert est.pull_moving_caveat(est.PULL_TALLY_STALL_BEATS - 1) == ""
    caveat = est.pull_moving_caveat(17)
    assert caveat.startswith(" — but no layer changed state in 17m")
    assert "can move bytes for minutes without finishing" in caveat and "the byte count is only the host's" in caveat
    assert "from zero" not in caveat          # b1's reading of the display, not a measured mechanism


def test_image_pull_heartbeat_carries_the_tally_age_and_qualifies_the_verdict_past_the_floor(
        est, monkeypatch, capsys):
    """b1's seventeen beats at `7/12 layers complete`, every one ending `the
    pipe is moving`: the fake delivers its layer lines at once and then
    nothing changes while the host keeps receiving bytes."""
    monkeypatch.setattr(est, "PULL_HEARTBEAT_S", 0.12)
    counter = {"rx": 0}

    def rx():
        counter["rx"] += 665 * 1024
        return counter["rx"]

    monkeypatch.setattr(est, "host_rx_bytes", rx)
    monkeypatch.setattr(est, "popen", lambda cmd, **kw: FakePull(cmd, 0, lines=PULL_LINES, delay=0.9))
    proc = est.image_pull("example.invalid/big:1", "mcp")
    assert proc.returncode == 0
    beats = [ln for ln in capsys.readouterr().out.splitlines() if "still pulling" in ln]
    assert len(beats) >= est.PULL_TALLY_STALL_BEATS + 2, beats
    assert "0/2 layers complete, 2 downloading" in beats[0] and "unchanged for" not in beats[0]
    assert all("the pipe is moving" in b for b in beats)
    aged = [b for b in beats if ", unchanged for " in b]
    assert len(aged) == len(beats) - 1, beats
    qualified = [b for b in beats if "but no layer changed state in" in b]
    assert beats[est.PULL_TALLY_STALL_BEATS] in qualified
    assert not any(b in qualified for b in beats[:est.PULL_TALLY_STALL_BEATS]), beats
    assert all("can move bytes for minutes without finishing" in b for b in qualified)


class PacedPull(FakePull):
    """A pull whose layer lines land one per heartbeat, so the tally keeps moving."""

    def __init__(self, cmd, lines, every: float, delay: float):
        super().__init__(cmd, 0, delay=delay)

        def paced():
            for line in lines:
                yield line
                time.sleep(every)

        self.stdout = paced()


def test_image_pull_heartbeat_does_not_age_a_tally_that_keeps_moving(est, monkeypatch, capsys):
    monkeypatch.setattr(est, "PULL_HEARTBEAT_S", 0.12)
    monkeypatch.setattr(est, "host_rx_bytes", lambda: 1)
    lines = [f"layer{i:08d}: Pulling fs layer\n" for i in range(8)]
    monkeypatch.setattr(est, "popen", lambda cmd, **kw: PacedPull(cmd, lines, every=0.12, delay=0.8))
    est.image_pull("example.invalid/big:1", "mcp")
    beats = [ln for ln in capsys.readouterr().out.splitlines() if "still pulling" in ln]
    assert beats
    assert not any("but no layer changed state" in b for b in beats), beats


# ------------------------------------------------ the row-102 near miss, measured on checks.py

def test_the_skeletons_own_prose_says_what_first_use_means(est, tmp_path, monkeypatch):
    corpus, g1, probe, m = staging_inputs(est, monkeypatch)
    doc = est.pins_skeleton(tmp_path, "canary", corpus, g1, probe, m, 151645, "measured", "off")
    text = doc["skeleton"]
    assert "on first use (PinsConfigurationError — first use being the first hash gate a COMPLETED body reaches" in text
    assert "admission gates ADM1-ADM4 run before any pins are read" in text


def test_admission_gates_run_before_the_pins_are_read_on_the_real_checks(est, tmp_path):
    """b1's step 16, both halves, in a separate process against the library
    on this interpreter: `{}` under a skeleton comes back as ADM1/ADM3 (no
    refusal — nothing read the pins), a COMPLETED body under the same file
    raises PinsConfigurationError naming the first empty key."""
    skeleton = tmp_path / "pins.skeleton.json"
    skeleton.write_text(json.dumps({"format": est.SKELETON_FORMAT, "pins": {
        "tool_roster_hash": ["a" * 64], "settings_hash": ["b" * 64],
        "g6_expected_tail_ids": [[1, 2, 3]], "skill_card_hash": [], "system_prompt_hash": [],
        "tokenizer_hash": [], "chat_template_hash": []}}))
    code = ("import json, sys\n"
            "from gsj_rollout import checks\n"
            "print('EMPTY', checks.validate_session_result({}))\n"
            "try:\n"
            "    print('BODY', checks.validate_session_result(json.loads(open(sys.argv[1]).read())))\n"
            "except checks.PinsConfigurationError as exc:\n"
            "    print('REFUSED', exc)\n")
    env = dict(os.environ, GSJ_PINS_PATH=str(skeleton), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-c", code, str(FIDELITY_BODY)], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    empty, body = proc.stdout.strip().splitlines()
    assert empty == "EMPTY ['ADM1:status_not_completed:None', 'ADM3:trajectory_missing']"
    assert body.startswith("REFUSED pins key 'system_prompt_hash' missing, empty, or not a list in ")
    assert body.endswith(str(skeleton))


# ------------------------------------------------ a2's finding 3, the library's twin: measure_tail

from test_estate_cp97_skeleton import TAIL_OFF, fake_endpoint


def flaky_tokenize(est, monkeypatch, misses: int):
    """The cp97 endpoint, with its first `misses` /tokenize requests getting
    no answer — what `http()` returns on a read timeout."""
    real = est.http
    left = {"n": misses}

    def http(method, url, body=None, **kw):
        if url.endswith("/tokenize") and left["n"] > 0:
            left["n"] -= 1
            return None, "TimeoutError: timed out"
        return real(method, url, body, **kw)

    monkeypatch.setattr(est, "http", http)
    monkeypatch.setattr(est, "TOKENIZE_RETRY_S", 0.0)


def test_a_tokenize_request_that_gets_no_answer_once_is_retried_and_the_tail_is_measured(est, monkeypatch):
    fake_endpoint(monkeypatch, est)
    flaky_tokenize(est, monkeypatch, misses=1)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert m["measured"] and m["why"] is None and m["g6_expected_tail_ids"] == TAIL_OFF
    assert m["requests"]["history_only"]["attempts"] == 2
    assert m["requests"]["with_generation_prompt"]["attempts"] == 1


def test_two_missed_requests_report_the_measurement_not_an_inference_about_the_endpoint(est, monkeypatch):
    """a2's endpoint was vLLM and answered the same request in 0.25 s either
    side of the one the demo lost — the old sentence called that endpoint
    unable to render its own template."""
    fake_endpoint(monkeypatch, est)
    flaky_tokenize(est, monkeypatch, misses=2)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert not m["measured"] and m["g6_expected_tail_ids"] is None
    assert m["why"].startswith("POST /tokenize (history_only) got no answer — 2 attempts, each under a 30 s "
                               "timeout, the last: TimeoutError: timed out.")
    assert "says nothing about whether this endpoint renders its chat template" in m["why"]
    assert "does not render its own chat template" not in m["why"]
    assert "Re-run `up` to measure again" in m["why"] and m["why"].endswith("bring-your-own.md#your-model")


def test_an_endpoint_that_answers_and_refuses_is_still_named_and_not_retried(est, monkeypatch):
    calls = fake_endpoint(monkeypatch, est, messages_form=False)
    monkeypatch.setattr(est, "TOKENIZE_RETRY_S", 0.0)
    m = est.measure_tail("http://engine:8100", "some/model", "off")
    assert "POST /tokenize (history_only) answered 400" in m["why"]
    assert "does not render its own chat template over the API" in m["why"]
    assert m["requests"]["history_only"]["attempts"] == 1
    assert [c for c, _ in calls].count("tokenize") == 1
