"""Per-turn policy_version stamping in SessionStore (carried patch P3, storage half).

Inert until ``set_policy_version()`` is called: with no version declared, the
store's in-memory records and persisted payloads are identical to the unpatched
pin's. The persistence half (writer payload built from ``record.metadata``, not
the raw ``metadata`` parameter) is what makes the per-turn stamp reach disk.
"""

from __future__ import annotations

from typing import Any

from polar.gateway.storage import SessionStore

_REQUEST = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
_RESPONSE = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


class _CapturingWriter:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def enqueue(self, *, task_id, session_id, completion_id, record) -> None:
        self.records.append(record)


def test_save_message_stamps_live_policy_version_and_persists_it() -> None:
    writer = _CapturingWriter()
    store = SessionStore(completion_writer=writer)
    store.set_policy_version(3)

    store.save_message("s1", _REQUEST, _RESPONSE, metadata={"submitted_version": 1})

    [completion] = store.get_completions("s1")
    assert completion["metadata"]["policy_version"] == 3
    assert completion["metadata"]["submitted_version"] == 1
    # The persistence fix: the stamp reaches the writer payload (disk), not just memory.
    [persisted] = writer.records
    assert persisted["metadata"]["policy_version"] == 3
    assert persisted["metadata"]["submitted_version"] == 1


def test_session_would_span_only_after_a_version_bump() -> None:
    store = SessionStore()
    store.set_policy_version(3)
    store.save_message("s1", _REQUEST, _RESPONSE)

    assert store.session_gen_version("s1") == 3
    assert store.session_would_span("s1") is False

    store.set_policy_version(4)

    assert store.session_would_span("s1") is True
    # A fresh session has no gen_version yet and never spans.
    assert store.session_would_span("s2") is False


def test_inert_without_a_declared_version() -> None:
    writer = _CapturingWriter()
    store = SessionStore(completion_writer=writer)

    store.save_message("s1", _REQUEST, _RESPONSE, metadata={"submitted_version": 1})

    [completion] = store.get_completions("s1")
    assert "policy_version" not in completion["metadata"]
    [persisted] = writer.records
    assert persisted["metadata"] == {"submitted_version": 1}
    assert store.get_policy_version() is None
    assert store.session_gen_version("s1") is None
    assert store.session_would_span("s1") is False
