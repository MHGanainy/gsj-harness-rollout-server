"""CP-08 client tests: collect() returns traces and runs `checks` client-side (law 6)."""

from __future__ import annotations

import copy

from conftest import task_status

import gsj_rollout.checks as checks
from gsj_rollout.client import RolloutClient, partition_session_results, traces_of


def test_collect_returns_traces_and_calls_checks(fake_rollout_factory, callback_body, monkeypatch):
    server = fake_rollout_factory([task_status([callback_body])])
    calls: list[str] = []
    real = checks.validate_session_result
    monkeypatch.setattr(
        checks, "validate_session_result",
        lambda body: calls.append(body["session_id"]) or real(body),
    )

    client = RolloutClient(server.base_url, poll_interval_s=0.01)
    traces = client.collect([{"task_id": "t-1"}], timeout_s=5.0)

    # Law 6's teeth: the client ran the same checks on what IT fetched.
    assert calls == [callback_body["session_id"]]
    assert len(traces) == 1
    assert len(traces[0].prompt_ids) == 2965
    assert traces[0].finish_reason == "stop"
    assert traces[0].metadata["session_id"] == callback_body["session_id"]


def test_collect_excludes_rejected_sessions(fake_rollout_factory, callback_body):
    errored = copy.deepcopy(callback_body)
    errored["session_id"] = "sk-polar-errored"
    errored["status"] = "ERROR"
    server = fake_rollout_factory([task_status([callback_body, errored])])

    traces = RolloutClient(server.base_url, poll_interval_s=0.01).collect(
        [{"task_id": "t-1"}], timeout_s=5.0
    )
    assert len(traces) == 1  # the ERROR session's trace is not returned

    accepted, rejected = partition_session_results([callback_body, errored])
    assert [r["session_id"] for r in accepted] == [callback_body["session_id"]]
    assert rejected[0][0]["session_id"] == "sk-polar-errored"
    assert "ADM1:status_not_completed:ERROR" in rejected[0][1]


def test_collect_logs_rejections(fake_rollout_factory, callback_body, caplog):
    errored = copy.deepcopy(callback_body)
    errored["session_id"] = "sk-polar-errored"
    errored["status"] = "ERROR"
    server = fake_rollout_factory([task_status([errored])])
    with caplog.at_level("WARNING", logger="gsj_rollout.client"):
        traces = RolloutClient(server.base_url, poll_interval_s=0.01).collect(
            [{"task_id": "t-1"}], timeout_s=5.0
        )
    assert traces == []  # reported, never returned (ADR-0008 §3)
    assert "sk-polar-errored" in caplog.text and "ADM1:status_not_completed" in caplog.text


def test_wait_raises_timeout_when_never_terminal(fake_rollout_factory):
    import pytest

    running = task_status([], status="running")
    running["total_sessions"] = 1
    server = fake_rollout_factory([running])
    client = RolloutClient(server.base_url, poll_interval_s=0.01)
    with pytest.raises(TimeoutError, match="not terminal"):
        client.wait("t-1", timeout_s=0.15)


def test_wait_polls_until_terminal(fake_rollout_factory, callback_body):
    running = task_status([], status="running")
    running["total_sessions"] = 1
    server = fake_rollout_factory([running, running, task_status([callback_body])])

    client = RolloutClient(server.base_url, poll_interval_s=0.01)
    results = client.wait(client.submit({"task_id": "t-1"}), timeout_s=5.0)
    assert server.polls == 3
    assert results[0]["session_id"] == callback_body["session_id"]
    assert traces_of(results[0])[0].finish_reason == "stop"
