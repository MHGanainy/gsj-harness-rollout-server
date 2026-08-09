"""BOTH — trace validators (interface at CP-08; rules at CP-10/CP-11).

The same code runs on both sides of the wire (scope law 6): the receiver
drops bad traces at the source, the trainer re-verifies what it fetched.
One entry point, `validate_session_result`, takes the callback-shaped
`SessionResult` mapping (never the rollout server's on-disk `ses_*.json`,
which strips `trajectory.status`/`error` — CP-07 finding 5) and returns
findings as byte-stable ``{id}:{slug}[:detail]`` strings. An empty list
means accepted; it never raises on content (ADR-0008 §6).

Two layers:

- **Admission** (live now): honor what the builder already decided — the
  CP-05/CP-07 escalation contract. Status must be COMPLETED (`ADM1`), the
  builder's `gsj_validation.findings` must be empty (`ADM2`), a
  trajectory with at least one trace must be present (`ADM3`/`ADM4`),
  and every trace must at least be a mapping (`ADM5`).
- **Trace rules** (`run_trace_checks`): the CP-10/CP-11 stub below. Gates
  G1–G7, the logprob discipline, and the G7 stats conjunction land there
  per `docs/checks-spec.md`; until then it returns no findings
  unconditionally.
"""

from __future__ import annotations

from typing import Any, Mapping

ACCEPTED_STATUS = "COMPLETED"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_session_result(session_result: Mapping[str, Any]) -> list[str]:
    """Validate one callback-shaped `SessionResult`; [] means accepted."""
    findings = _admission_findings(session_result)
    traces = _as_mapping(session_result.get("trajectory")).get("traces")
    for trace in traces if isinstance(traces, list) else []:
        if isinstance(trace, Mapping):
            findings.extend(run_trace_checks(trace))
        else:
            findings.append("ADM5:malformed_trace")
    return findings


def _admission_findings(session_result: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    status = session_result.get("status")
    if status != ACCEPTED_STATUS:
        findings.append(f"ADM1:status_not_completed:{status}")
    trajectory = session_result.get("trajectory")
    if not isinstance(trajectory, Mapping):
        findings.append("ADM3:trajectory_missing")
        return findings
    builder_findings = _as_mapping(
        _as_mapping(trajectory.get("metadata")).get("gsj_validation")
    ).get("findings") or []
    if not isinstance(builder_findings, list):
        builder_findings = [builder_findings]
    if builder_findings:
        findings.append(f"ADM2:builder_findings_present:{len(builder_findings)}")
        findings.extend(str(finding) for finding in builder_findings)
    traces = trajectory.get("traces")
    if not (isinstance(traces, list) and traces):
        findings.append("ADM4:no_traces")
    return findings


def run_trace_checks(trace: Mapping[str, Any]) -> list[str]:
    """CP-10/CP-11 fill this — returns no findings unconditionally.

    The rules specified in `docs/checks-spec.md` land here: the logprob
    discipline (finite ≤ 0, the explicit ≤ −9000 sentinel threshold, no
    0.0 at mask==1, empty-mask hard failure), the `finish_reason`
    allowlist, the G7 stats conjunction, and gates G1–G7 against the
    pins. The seam is fixed at CP-08 so both sides already call it.
    """
    return []
