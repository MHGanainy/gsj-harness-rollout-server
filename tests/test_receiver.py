"""CP-08 receiver tests: the real callback body round-trips; doctored bodies quarantine."""

from __future__ import annotations

import copy
import json
import threading

import httpx
import pytest

from gsj_rollout.receiver import Receiver


@pytest.fixture
def receiver(tmp_path):
    server = Receiver("127.0.0.1", 0, str(tmp_path / "traces"), str(tmp_path / "quarantine"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.port}/callbacks/session_result"
    server.tmp_path = tmp_path
    yield server
    server.shutdown()


def test_real_callback_body_round_trips(receiver, body13):
    response = httpx.post(receiver.url, json=body13)
    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": 0}

    persisted_path = receiver.tmp_path / "traces" / f"{body13['session_id']}.json"
    assert persisted_path.exists()
    persisted = json.loads(persisted_path.read_text())
    # CP-07 finding 5's property: unlike the rollout server's ses_*.json,
    # OUR persisted copy keeps status/error intact — it IS the POSTed body.
    assert persisted == body13
    assert persisted["status"] == "COMPLETED"
    trace = persisted["trajectory"]["traces"][0]
    assert len(trace["prompt_ids"]) == 2965
    assert len(trace["response_ids"]) == len(trace["loss_mask"]) == 7196


def test_builder_error_status_is_quarantined(receiver, body13):
    doctored = copy.deepcopy(body13)
    doctored["status"] = "ERROR"
    response = httpx.post(receiver.url, json=doctored)
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "rejected": 1}

    session_id = doctored["session_id"]
    assert not (receiver.tmp_path / "traces" / f"{session_id}.json").exists()
    quarantined = json.loads(
        (receiver.tmp_path / "quarantine" / f"{session_id}.json").read_text()
    )
    assert "ADM1:status_not_completed:ERROR" in quarantined["findings"]
    assert quarantined["session_result"] == doctored  # forensics beat counters


def test_builder_findings_are_quarantined_even_when_completed(receiver, body13):
    doctored = copy.deepcopy(body13)
    doctored["trajectory"]["metadata"]["gsj_validation"]["findings"] = [
        "S1:empty_prompt_ids:c-0001"
    ]
    response = httpx.post(receiver.url, json=doctored)
    assert response.json() == {"accepted": 0, "rejected": 1}
    quarantined = json.loads(
        (receiver.tmp_path / "quarantine" / f"{doctored['session_id']}.json").read_text()
    )
    assert "ADM2:builder_findings_present:1" in quarantined["findings"]
    assert "S1:empty_prompt_ids:c-0001" in quarantined["findings"]


def test_task_result_envelope_is_unwrapped(receiver, body13):
    envelope = {"task_id": "t-1", "status": "completed",
                "results": [body13], "result_paths": []}
    response = httpx.post(receiver.url, json=envelope)
    assert response.json() == {"accepted": 1, "rejected": 0}
    assert (receiver.tmp_path / "traces" / f"{body13['session_id']}.json").exists()


def test_mixed_envelope_partitions_per_member(receiver, body13):
    errored = copy.deepcopy(body13)
    errored["session_id"] = "sk-polar-mixed-errored"
    errored["status"] = "ERROR"
    envelope = {"task_id": "t-1", "status": "completed",
                "results": [body13, errored], "result_paths": []}
    response = httpx.post(receiver.url, json=envelope)
    assert response.json() == {"accepted": 1, "rejected": 1}
    assert (receiver.tmp_path / "traces" / f"{body13['session_id']}.json").exists()
    assert not (receiver.tmp_path / "traces" / "sk-polar-mixed-errored.json").exists()
    assert (receiver.tmp_path / "quarantine" / "sk-polar-mixed-errored.json").exists()


# --- CP-13: the pins-failure seam, over HTTP (the CP-11b shapes cured) ----


def _no_pins_needed_result():
    """A member the receiver would quarantine WITHOUT touching pins
    (traces=[] → ADM4/G7 findings only) — the member that used to get
    half-persisted before the batch went atomic."""
    return {"session_id": "s-atomic-1", "status": "COMPLETED",
            "trajectory": {"metadata": {}, "traces": []}}


def test_missing_pins_file_is_a_500_and_the_batch_is_atomic(receiver, body13, monkeypatch):
    """CP-11b measured: a missing pins FILE dropped the connection with no
    HTTP response and left earlier members of the batch written. Cured: a
    500 naming the path, the whole envelope undispositioned."""
    import gsj_rollout.checks as checks

    monkeypatch.setattr(checks, "_pins_cache", None)
    monkeypatch.setattr(checks, "PINS_PATH", receiver.tmp_path / "no-such-pins.gsj.json")
    envelope = {"task_id": "t-1", "status": "completed", "result_paths": [],
                "results": [_no_pins_needed_result(), body13]}
    response = httpx.post(receiver.url, json=envelope)
    assert response.status_code == 500
    assert "pins configuration" in response.json()["error"]
    assert "no-such-pins.gsj.json" in response.json()["error"]
    # atomic: not even the first (pins-free) member was dispositioned
    assert list((receiver.tmp_path / "traces").iterdir()) == []
    assert list((receiver.tmp_path / "quarantine").iterdir()) == []
    assert (receiver.accepted, receiver.rejected) == (0, 0)


def test_every_unusable_pins_shape_is_a_500_over_http(receiver, body13, monkeypatch, tmp_path):
    """Five reachable pins-configuration faults, not two: the CP-13
    adversarial pass measured a corrupt file answering 400 (the masquerade
    again) and unreadable / directory / wrong-shape files dropping the
    connection. Classified by origin now, so all five answer 500."""
    import gsj_rollout.checks as checks

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text('{"pins": {"skill_card_hash": ["a"]}')
    unreadable = tmp_path / "noperm.json"
    unreadable.write_text("{}")
    unreadable.chmod(0o000)
    a_directory = tmp_path / "pinsdir"
    a_directory.mkdir()
    wrong_shape = tmp_path / "wrong.json"
    wrong_shape.write_text('["not", "a", "mapping"]')

    for path in (corrupt, unreadable, a_directory, wrong_shape, tmp_path / "absent.json"):
        monkeypatch.setattr(checks, "_pins_cache", None)
        monkeypatch.setattr(checks, "PINS_PATH", path)
        response = httpx.post(receiver.url, json=body13)
        assert response.status_code == 500, path.name
        assert "pins configuration" in response.json()["error"], path.name
        assert list((receiver.tmp_path / "traces").iterdir()) == []
    unreadable.chmod(0o600)  # so tmp_path cleanup can remove it


def test_an_unserializable_member_lands_nothing_and_answers(receiver, body13, monkeypatch):
    """The atomicity hole the CP-13 pass found: a member whose payload
    defeats `json.dump` (it reproduced it with legal-JSON nesting deep
    enough to exhaust the stack inside the old write loop) wrote member 1,
    orphaned a `.tmp` for member 2, and dropped the connection.
    Serialization now happens in the validation phase — the guarantee is
    tested directly rather than through a recursion-depth coincidence."""
    import gsj_rollout.receiver as receiver_mod

    real_dumps = json.dumps

    def failing_dumps(payload, *args, **kwargs):
        # only the receiver's own whole-result serialization, never the
        # canonical hashing `checks` does on sub-objects with kwargs
        if isinstance(payload, dict) and payload.get("session_id") == "sk-polar-second":
            raise RecursionError("maximum recursion depth exceeded")
        return real_dumps(payload, *args, **kwargs)

    monkeypatch.setattr(receiver_mod.json, "dumps", failing_dumps)
    second = copy.deepcopy(body13)
    second["session_id"] = "sk-polar-second"
    envelope = {"task_id": "t-1", "status": "completed", "result_paths": [],
                "results": [body13, second]}
    response = httpx.post(receiver.url, json=envelope)
    assert response.status_code == 400
    assert "not serializable" in response.json()["error"]
    for directory in ("traces", "quarantine"):
        assert list((receiver.tmp_path / directory).iterdir()) == [], directory
    assert (receiver.accepted, receiver.rejected) == (0, 0)


def test_a_staging_failure_leaves_no_partial_batch_and_no_orphan_tmp(receiver, body13):
    """Phase 2's guarantee: if any `.tmp` cannot be staged, every staged
    `.tmp` is unlinked and nothing is committed — the batch is atomic
    against write faults, not only against validation faults."""
    errored = copy.deepcopy(body13)
    errored["session_id"] = "sk-polar-quarantined"
    errored["status"] = "ERROR"                       # → quarantine (writable)
    (receiver.tmp_path / "traces").chmod(0o500)       # → body13's stage fails
    try:
        response = httpx.post(receiver.url, json={
            "task_id": "t-1", "status": "completed", "result_paths": [],
            "results": [errored, body13]})
        assert response.status_code == 500
        assert "receiver: PermissionError" in response.json()["error"]
        assert list((receiver.tmp_path / "quarantine").iterdir()) == []
        assert (receiver.accepted, receiver.rejected) == (0, 0)
    finally:
        (receiver.tmp_path / "traces").chmod(0o700)


def test_an_endless_session_id_is_refused_at_the_shape_screen(receiver):
    """A session id is a filename: Polar caps its own at 128 chars
    (`session.py:16`), and so do we — otherwise a legal-per-regex id
    reaches the write and fails there, which is the wrong layer."""
    endless = {"session_id": "s" * 300, "trajectory": {"metadata": {}, "traces": []}}
    assert httpx.post(receiver.url, json=endless).status_code == 400
    assert list((receiver.tmp_path / "quarantine").iterdir()) == []


def test_missing_pins_key_is_a_500_not_a_400_masquerade(receiver, body13, monkeypatch):
    """CP-11b measured: a missing pins KEY answered 400 — a client-error
    status for a server-configuration fault. Cured: 500, key named,
    nothing written."""
    import gsj_rollout.checks as checks

    monkeypatch.setattr(checks, "_pins_cache", {"system_prompt_hash": ["x"]})
    envelope = {"task_id": "t-1", "status": "completed", "result_paths": [],
                "results": [_no_pins_needed_result(), body13]}
    response = httpx.post(receiver.url, json=envelope)
    assert response.status_code == 500
    assert "tool_roster_hash" in response.json()["error"]
    assert list((receiver.tmp_path / "traces").iterdir()) == []
    assert list((receiver.tmp_path / "quarantine").iterdir()) == []


def test_malformed_body_gets_400(receiver):
    assert httpx.post(receiver.url, json={"nonsense": True}).status_code == 400
    assert httpx.post(receiver.url, content=b"not json").status_code == 400
    # Malformed CONTENT past the shape screen still answers (findings, not a
    # crashed handler): the never-raises contract, exercised over HTTP.
    response = httpx.post(receiver.url, json={"session_id": "s-1", "trajectory": "oops"})
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "rejected": 1}
    # session_id becomes a filename — traversal-shaped ids are refused.
    assert httpx.post(receiver.url, json={"session_id": "../evil", "trajectory": {}}).status_code == 400
    assert (
        httpx.post(f"http://127.0.0.1:{receiver.port}/elsewhere", json={}).status_code == 404
    )
