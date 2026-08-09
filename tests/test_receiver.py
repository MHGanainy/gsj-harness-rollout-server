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


def test_real_callback_body_round_trips(receiver, callback_body):
    response = httpx.post(receiver.url, json=callback_body)
    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": 0}

    persisted_path = receiver.tmp_path / "traces" / f"{callback_body['session_id']}.json"
    assert persisted_path.exists()
    persisted = json.loads(persisted_path.read_text())
    # CP-07 finding 5's property: unlike the rollout server's ses_*.json,
    # OUR persisted copy keeps status/error intact — it IS the POSTed body.
    assert persisted == callback_body
    assert persisted["status"] == "COMPLETED"
    trace = persisted["trajectory"]["traces"][0]
    assert len(trace["prompt_ids"]) == 2965
    assert len(trace["response_ids"]) == len(trace["loss_mask"]) == 7196


def test_builder_error_status_is_quarantined(receiver, callback_body):
    doctored = copy.deepcopy(callback_body)
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


def test_builder_findings_are_quarantined_even_when_completed(receiver, callback_body):
    doctored = copy.deepcopy(callback_body)
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


def test_task_result_envelope_is_unwrapped(receiver, callback_body):
    envelope = {"task_id": "t-1", "status": "completed",
                "results": [callback_body], "result_paths": []}
    response = httpx.post(receiver.url, json=envelope)
    assert response.json() == {"accepted": 1, "rejected": 0}
    assert (receiver.tmp_path / "traces" / f"{callback_body['session_id']}.json").exists()


def test_mixed_envelope_partitions_per_member(receiver, callback_body):
    errored = copy.deepcopy(callback_body)
    errored["session_id"] = "sk-polar-mixed-errored"
    errored["status"] = "ERROR"
    envelope = {"task_id": "t-1", "status": "completed",
                "results": [callback_body, errored], "result_paths": []}
    response = httpx.post(receiver.url, json=envelope)
    assert response.json() == {"accepted": 1, "rejected": 1}
    assert (receiver.tmp_path / "traces" / f"{callback_body['session_id']}.json").exists()
    assert not (receiver.tmp_path / "traces" / "sk-polar-mixed-errored.json").exists()
    assert (receiver.tmp_path / "quarantine" / "sk-polar-mixed-errored.json").exists()


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
