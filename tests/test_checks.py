"""CP-08 checks-seam tests: never-raises contract; the run_trace_checks wiring."""

from __future__ import annotations

import copy

import gsj_rollout.checks as checks


def test_never_raises_on_malformed_content():
    # ADR-0008 §6: findings, not exceptions — whatever the wire delivers.
    malformed = [
        {},
        {"session_id": "s"},
        {"session_id": "s", "trajectory": "oops"},
        {"session_id": "s", "trajectory": ["not", "a", "mapping"]},
        {"session_id": "s", "trajectory": {"metadata": "junk", "traces": [{}]}},
        {"session_id": "s", "trajectory": {"metadata": {"gsj_validation": "junk"}, "traces": [{}]}},
        {"session_id": "s", "trajectory": {"metadata": {"gsj_validation": {"findings": "F1"}}, "traces": [{}]}},
        {"session_id": "s", "trajectory": {"traces": "oops"}},
        {"session_id": "s", "trajectory": {"traces": [None, "junk"]}},
        {"status": "COMPLETED", "trajectory": {"traces": [{}, 42]}},
    ]
    for body in malformed:
        findings = checks.validate_session_result(body)
        assert isinstance(findings, list) and findings, f"must reject, not accept: {body!r}"


def test_admission_vocabulary(callback_body):
    assert checks.validate_session_result(callback_body) == []

    errored = copy.deepcopy(callback_body)
    errored["status"] = "TIMEOUT"
    assert "ADM1:status_not_completed:TIMEOUT" in checks.validate_session_result(errored)

    no_traces = copy.deepcopy(callback_body)
    no_traces["trajectory"]["traces"] = []
    assert "ADM4:no_traces" in checks.validate_session_result(no_traces)

    non_list_findings = copy.deepcopy(callback_body)
    non_list_findings["trajectory"]["metadata"]["gsj_validation"]["findings"] = "S1:oops"
    result = checks.validate_session_result(non_list_findings)
    assert "ADM2:builder_findings_present:1" in result and "S1:oops" in result


def test_run_trace_checks_seam_is_wired(callback_body, monkeypatch):
    # The CP-10/CP-11 rules land in run_trace_checks; prove findings surface.
    monkeypatch.setattr(checks, "run_trace_checks", lambda trace: ["G7:stub_finding"])
    assert checks.validate_session_result(callback_body) == ["G7:stub_finding"]
    assert checks.run_trace_checks.__doc__ is None  # the monkeypatched stand-in


def test_stub_returns_no_findings_unconditionally():
    # The STOP wall: no trace rules this CP.
    assert checks.run_trace_checks({}) == []
    assert checks.run_trace_checks({"loss_mask": [], "response_logprobs": [1.0]}) == []
