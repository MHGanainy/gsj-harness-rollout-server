"""TRAINER — submit + collect (ADR-0008 §3).

Polls `GET /rollout/task/{id}`, never the receiver's disk: the poll
returns the callback-validated `SessionResult` objects verbatim with
status/error intact (`manager.py:214` — the same in-memory source the
CP-07 fixture was captured from), the trainer need not share a disk with
the receiver, and law 6 wants this side's verdict independent — every
fetched result re-runs the same `checks.validate_session_result` the
receiver ran, so nothing upstream can launder a bad trace into the
trainer. Installs light: pydantic + httpx only (ADR-0001); `polar` is
never imported here.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, Mapping

import httpx
from pydantic import BaseModel, ConfigDict, Field

from . import checks

logger = logging.getLogger("gsj_rollout.client")

_TERMINAL_TASK_STATUSES = ("completed", "failed")


class Trace(BaseModel):
    """Our mirror of the callback trace fields (Polar isn't importable trainer-side)."""

    model_config = ConfigDict(extra="allow")

    prompt_ids: list[int] = Field(default_factory=list)
    response_ids: list[int] = Field(default_factory=list)
    loss_mask: list[int] = Field(default_factory=list)
    prompt_messages: list[dict[str, Any]] = Field(default_factory=list)
    response_messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str | None = None
    response_logprobs: list[float] | None = None
    reward: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def partition_session_results(
    session_results: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], list[str]]]]:
    """(accepted, rejected-with-findings) — law 6's client-side leg."""
    accepted: list[dict[str, Any]] = []
    rejected: list[tuple[dict[str, Any], list[str]]] = []
    for result in session_results:
        findings = checks.validate_session_result(result)
        if findings:
            rejected.append((dict(result), findings))
        else:
            accepted.append(dict(result))
    return accepted, rejected


def traces_of(session_result: Mapping[str, Any]) -> list[Trace]:
    return [
        Trace.model_validate(trace)
        for trace in (session_result.get("trajectory") or {}).get("traces") or []
    ]


class RolloutClient:
    """The trainer's whole surface: submit, wait, collect validated traces."""

    def __init__(self, base_url: str, *, poll_interval_s: float = 2.0,
                 http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.poll_interval_s = poll_interval_s
        self._http = http or httpx.Client(timeout=30.0)

    def submit(self, task_request: Mapping[str, Any]) -> str:
        response = self._http.post(
            f"{self.base_url}/rollout/task/submit", json=dict(task_request)
        )
        response.raise_for_status()
        return response.json()["task_id"]

    def wait(
        self,
        task_id: str,
        *,
        timeout_s: float,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Poll until the task is terminal; the SessionResult bodies, verbatim."""
        deadline = time.monotonic() + timeout_s
        while True:
            response = self._http.get(f"{self.base_url}/rollout/task/{task_id}")
            response.raise_for_status()
            status = response.json()
            if on_poll is not None:
                on_poll(status)
            if status["status"] in _TERMINAL_TASK_STATUSES:
                return status["results"]
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"task {task_id} not terminal after {timeout_s}s "
                    f"({status['completed_sessions']}/{status['total_sessions']} sessions)"
                )
            time.sleep(min(self.poll_interval_s, max(deadline - time.monotonic(), 0.0)))

    def collect(
        self,
        task_requests: Iterable[Mapping[str, Any]],
        *,
        timeout_s: float = 1020.0,  # default task timeout 900 + callback grace 120
    ) -> list[Trace]:
        """Submit everything, wait, return the traces of checks-clean sessions."""
        task_ids = [self.submit(request) for request in task_requests]
        results: list[dict[str, Any]] = []
        for task_id in task_ids:
            results.extend(self.wait(task_id, timeout_s=timeout_s))
        accepted, rejected = partition_session_results(results)
        for result, findings in rejected:  # reported, never returned (ADR-0008 §3)
            logger.warning("rejected %s: %s", result.get("session_id"), findings)
        return [trace for result in accepted for trace in traces_of(result)]
