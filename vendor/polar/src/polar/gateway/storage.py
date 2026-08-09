"""In-memory session storage for gateway completion records."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from polar.gateway.completion_writer import CompletionWriter
from polar.trajectory.models import CompletionRecord, CompletionSession


@dataclass(slots=True)
class _SessionState:
    session_id: str
    created_at: str | None = None
    completion_count: int = 0
    task_id: str | None = None
    model_requested: str | None = None
    model_used: str | None = None
    api_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    completions: list[CompletionRecord] = field(default_factory=list)
    # policy_version live when this session generated its FIRST turn.  The version-span
    # guard rejects the session's next request if current_version != gen_version.
    gen_version: int | None = None


class SessionStore:
    """Thread-safe in-memory storage for active gateway sessions."""

    def __init__(self, *, completion_writer: CompletionWriter | None = None) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionState] = {}
        self._completion_writer = completion_writer
        # Live policy_version, bumped by the trainer at each weight sync (during the
        # engine pause, before resume) via POST /admin/policy_version.  Stamped onto
        # each completion and used for the version-span guard.  None = never set yet.
        self._current_policy_version: int | None = None

    def set_policy_version(self, version: int) -> None:
        """Set the live policy_version (called at each weight sync, during pause)."""
        with self._lock:
            self._current_policy_version = int(version)

    def get_policy_version(self) -> int | None:
        with self._lock:
            return self._current_policy_version

    def session_gen_version(self, session_id: str) -> int | None:
        """O(1) read of a session's first-generation version (version-span guard)."""
        with self._lock:
            state = self._sessions.get(session_id)
            return state.gen_version if state is not None else None

    def session_would_span(self, session_id: str) -> bool:
        """True iff this session already generated under a version != current, so its
        NEXT turn would span a weight update (mixed-weight).  O(1); reject before
        generating.  False for fresh sessions (no gen_version) and when version unset."""
        with self._lock:
            cur = self._current_policy_version
            state = self._sessions.get(session_id)
            gen = state.gen_version if state is not None else None
            return cur is not None and gen is not None and cur != gen

    def close(self) -> None:
        with self._lock:
            self._sessions.clear()

    def list_active_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._metadata_payload_locked(state)
                for state in self._sessions.values()
            ]

    def get_completions(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return []
            return [c.model_dump(mode="json") for c in state.completions]

    def ensure_session(
        self,
        session_id: str,
        model_requested: str | None,
        model_used: str | None,
        api_type: str | None,
        *,
        task_id: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or refresh session metadata."""
        with self._lock:
            state = self._get_or_create_session_locked(session_id, created_at=created_at)
            self._merge_metadata_locked(
                state,
                task_id=task_id,
                model_requested=model_requested,
                model_used=model_used,
                api_type=api_type,
                metadata=metadata,
            )
            return self._metadata_payload_locked(state)

    def save_message(
        self,
        session_id: str,
        request: dict[str, Any],
        response: dict[str, Any],
        *,
        original_request: dict[str, Any] | None = None,
        model_requested: str | None = None,
        model_used: str | None = None,
        api_type: str | None = None,
        task_id: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append one completion record to the in-memory session."""
        effective_model_used = model_used or request.get("model", "unknown")
        record = CompletionRecord.model_validate(
            {
                "completion_id": f"msg_{uuid.uuid4().hex[:12]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request": request,
                "original_request": original_request or {},
                "response": response,
                "metadata": dict(metadata or {}),
            }
        )

        with self._lock:
            state = self._get_or_create_session_locked(session_id, created_at=created_at)
            self._merge_metadata_locked(
                state,
                task_id=task_id,
                model_requested=model_requested,
                model_used=effective_model_used,
                api_type=api_type,
                metadata=metadata,
            )
            # version-span guard: stamp the live policy_version onto this completion and
            # record the session's first-generation version.  Used by the gateway entry
            # interception (reject next turn if current != gen_version) and the
            # prefix_merging cross-version fallback.
            if self._current_policy_version is not None:
                record.metadata["policy_version"] = self._current_policy_version
                if state.gen_version is None:
                    state.gen_version = self._current_policy_version
            state.completions.append(record)
            state.completion_count = len(state.completions)
            effective_task_id = state.task_id

        # Off the hot path: best-effort persist to disk.
        if self._completion_writer is not None:
            self._completion_writer.enqueue(
                task_id=effective_task_id,
                session_id=session_id,
                completion_id=record.completion_id,
                record={
                    "completion_id": record.completion_id,
                    "timestamp": record.timestamp,
                    "session_id": session_id,
                    "task_id": effective_task_id,
                    "api_type": api_type,
                    "model_requested": model_requested,
                    "model_used": effective_model_used,
                    "original_request": original_request or {},
                    "transformed_request": request,
                    "response": response,
                    # version-span: persist record.metadata (carries the live per-turn
                    # policy_version stamped in save_message), NOT the raw session-level
                    # scheduler metadata param -- else disk shows the constant submission
                    # version and cross-version can't be audited from the persisted files.
                    "metadata": dict(record.metadata),
                },
            )
        return record.completion_id

    def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        """Return session metadata if present."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            return self._metadata_payload_locked(state)

    def load_completion_session(self, session_id: str) -> CompletionSession:
        """Load the typed completion session from in-memory state."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return CompletionSession.model_validate(
                    {
                        "session_id": session_id,
                        "completion_count": 0,
                        "completions": [],
                    }
                )

            payload = self._metadata_payload_locked(state)
            payload["completions"] = [
                completion.model_dump(mode="python")
                for completion in state.completions
            ]
            return CompletionSession.model_validate(payload)

    def delete_session(self, session_id: str) -> int:
        """Drop a session and return how many messages were removed."""
        with self._lock:
            state = self._sessions.pop(session_id, None)
            if state is None:
                return 0
            return len(state.completions)

    def _get_or_create_session_locked(
        self,
        session_id: str,
        *,
        created_at: str | None,
    ) -> _SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            state = _SessionState(
                session_id=session_id,
                created_at=created_at or datetime.now(timezone.utc).isoformat(),
            )
            self._sessions[session_id] = state
            return state

        if state.created_at is None:
            state.created_at = created_at or datetime.now(timezone.utc).isoformat()
        return state

    def _merge_metadata_locked(
        self,
        state: _SessionState,
        *,
        task_id: str | None,
        model_requested: str | None,
        model_used: str | None,
        api_type: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        state.task_id = self._merge_field(state.task_id, task_id)
        state.model_requested = self._merge_field(state.model_requested, model_requested)
        state.model_used = self._merge_field(state.model_used, model_used)
        state.api_type = self._merge_field(state.api_type, api_type)
        if metadata:
            state.metadata.update(metadata)

    def _metadata_payload_locked(self, state: _SessionState) -> dict[str, Any]:
        return {
            "session_id": state.session_id,
            "created_at": state.created_at,
            "completion_count": len(state.completions),
            "task_id": state.task_id,
            "model_requested": state.model_requested,
            "model_used": state.model_used,
            "api_type": state.api_type,
            "metadata": dict(state.metadata),
        }

    @staticmethod
    def _merge_field(existing: Any, incoming: Any) -> Any:
        if incoming in (None, "", "unknown"):
            return existing
        if existing in (None, "", "unknown"):
            return incoming
        return existing
