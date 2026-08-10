"""CP-11: the leak-closing clone flags, asserted on the rendered command.

`polar` lives in `vendor/polar/.venv`, not the test venv, so the four
imported names are stubbed just enough to import the module and drive
`setup()` — the assertion targets the exact shell string the sandbox
executes (the same string the CP-11 scratch reproduction ran verbatim).
The stubs are monkeypatch-scoped and the module import is unwound after,
so `test_scaffold`'s "`polar` never in `sys.modules`" surface law holds.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
import types

from conftest import REPO_ROOT


def _stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class _FakeRuntime:
    session_id = "sk-polar-test"

    def __init__(self):
        self.commands: list[str] = []

    async def exec(self, command: str):
        self.commands.append(command)
        return types.SimpleNamespace(return_code=0, stderr="")


class _FakeRegistry:
    """The two vendored `SessionRegistry` methods the echo touches, with
    the merge semantics the CP-13 hop execution proved on the real class
    (`session.py:87-88`): register() on a known id merges metadata."""

    def __init__(self, known: dict[str, dict]):
        self.known = known
        self.register_calls: list[tuple] = []

    def get(self, session_id):
        return types.SimpleNamespace(session_id=session_id, metadata=self.known[session_id]) \
            if session_id in self.known else None

    def register(self, session_id, *, metadata=None, status="REGISTERED", **kwargs):
        self.register_calls.append((session_id, metadata, status))
        if metadata:
            self.known[session_id] = {**self.known[session_id], **metadata}


def _stubbed_pi_harness(monkeypatch, registry):
    stubs = {
        "polar": _stub("polar"),
        "polar.agent": _stub("polar.agent"),
        "polar.agent.base": _stub("polar.agent.base", BaseHarness=type("BaseHarness", (), {})),
        "polar.agent.models": _stub("polar.agent.models", AgentRunResult=type("AgentRunResult", (), {})),
        "polar.gateway": _stub("polar.gateway"),
        "polar.gateway.server": _stub(
            "polar.gateway.server",
            get_state=lambda: types.SimpleNamespace(session_registry=registry)),
        "polar.runtime": _stub("polar.runtime"),
        "polar.runtime.base": _stub("polar.runtime.base", BaseRuntime=type("BaseRuntime", (), {}),
                                    RUNTIME_AGENT_LOG_DIR="/polar/agent-logs"),
        "polar.runtime.models": _stub("polar.runtime.models", ExecInput=type("ExecInput", (), {})),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules.pop("gsj_rollout.pi_harness", None)
    from gsj_rollout import pi_harness
    return pi_harness


def _harness_under_test(pi_harness):
    harness = pi_harness.PiHarness.__new__(pi_harness.PiHarness)
    harness.settings = {
        "case_id": "case_0001",
        "timestep": 12,
        "clone_url_for": "http://host.docker.internal:3000/gsj-staging/{case_id}.git",
        "mcp_url_base": "http://host.docker.internal:8790",
        "tools_allowlist": ["read"],
        "artifacts_dir": "/tmp/gsj-artifacts",
    }
    harness.model_name = "gsj/Qwen/Qwen3-0.6B"
    return harness


def test_clone_is_shallow_single_branch_and_remoteless(monkeypatch):
    """Row 2's git-history cutoff channel: `--depth 1` keeps only the
    truncation commit (no `HEAD~1`, no full-document blobs); dropping
    `origin` removes the configured re-fetch path; scrubbing `.git/logs`
    removes the clone URL the reflog would otherwise hand back (CP-11
    measured `clone: from <url>` surviving the remote drop)."""
    registry = _FakeRegistry({"sk-polar-test": {"case_id": "case_0001"}})
    pi_harness = _stubbed_pi_harness(monkeypatch, registry)
    try:
        harness = _harness_under_test(pi_harness)
        runtime = _FakeRuntime()
        asyncio.run(pi_harness.PiHarness.setup(harness, runtime))
        clone_steps = [c for c in runtime.commands if "git clone" in c]
        assert clone_steps == [
            "git clone --depth 1 --branch timestep-12 --single-branch "
            "http://host.docker.internal:3000/gsj-staging/case_0001.git /workspace "
            "&& git -C /workspace remote remove origin "
            "&& rm -rf /workspace/.git/logs"
        ]
    finally:
        sys.modules.pop("gsj_rollout.pi_harness", None)


def test_settings_echo_merges_the_rendered_document(monkeypatch):
    """G7's settings echo (CP-13, row 15): setup() merges the settings
    document AS WRITTEN into the session's registry metadata — the same
    document the sandbox write step carries — with the status-preserving
    empty-status merge, before any completion exists. The vendored-hop
    chain from there (registry → proxy stamp → builder hoist) is executed
    against the real Polar classes in the CP-13 hop run (report §notes)."""
    registry = _FakeRegistry({"sk-polar-test": {"case_id": "case_0001", "timestep": 12}})
    pi_harness = _stubbed_pi_harness(monkeypatch, registry)
    try:
        harness = _harness_under_test(pi_harness)
        runtime = _FakeRuntime()
        asyncio.run(pi_harness.PiHarness.setup(harness, runtime))
        echoed = registry.register_calls[0][1]["gsj_settings"]
        assert registry.register_calls == [("sk-polar-test", {"gsj_settings": echoed}, "")]
        assert registry.known["sk-polar-test"]["gsj_settings"] == echoed
        # The chain that must not drift, asserted rather than eyeballed:
        # the harness's echoed document IS the pinned rendered document IS
        # what `settings_hash` approves. Without this, editing the harness
        # constant leaves the suite green while every real episode fails
        # G7 (measured by the CP-13 adversarial pass, in a scratch copy).
        import gsj_rollout.checks as checks
        pinned = json.loads((REPO_ROOT / "pins" / "settings.rendered.json").read_text())
        assert echoed == pinned
        assert checks._sha256_canonical_json(echoed) in checks.approved_set("settings_hash")
        # and the same document is what the sandbox write step renders
        write_step = runtime.commands[0]
        assert f"printf '%s' {shlex.quote(json.dumps(pinned))}" in write_step
        assert "settings.json" in write_step
    finally:
        sys.modules.pop("gsj_rollout.pi_harness", None)


def test_settings_echo_fails_loudly_outside_the_gateway_registry(monkeypatch):
    """A-23's loud path: a session id the process's registry does not know
    means the echo cannot reach the trace — setup() raises rather than
    letting the episode run unechoed (it would be rejected fail-closed at
    the receiver anyway; earlier is cheaper)."""
    import pytest

    registry = _FakeRegistry({})  # a disconnected/foreign registry
    pi_harness = _stubbed_pi_harness(monkeypatch, registry)
    try:
        harness = _harness_under_test(pi_harness)
        with pytest.raises(RuntimeError, match="settings echo"):
            asyncio.run(pi_harness.PiHarness.setup(harness, _FakeRuntime()))
    finally:
        sys.modules.pop("gsj_rollout.pi_harness", None)
