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
import sys
import types


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


def test_clone_is_shallow_single_branch_and_remoteless(monkeypatch):
    """Row 2's git-history cutoff channel: `--depth 1` keeps only the
    truncation commit (no `HEAD~1`, no full-document blobs); dropping
    `origin` removes the configured re-fetch path; scrubbing `.git/logs`
    removes the clone URL the reflog would otherwise hand back (CP-11
    measured `clone: from <url>` surviving the remote drop)."""
    stubs = {
        "polar": _stub("polar"),
        "polar.agent": _stub("polar.agent"),
        "polar.agent.base": _stub("polar.agent.base", BaseHarness=type("BaseHarness", (), {})),
        "polar.agent.models": _stub("polar.agent.models", AgentRunResult=type("AgentRunResult", (), {})),
        "polar.runtime": _stub("polar.runtime"),
        "polar.runtime.base": _stub("polar.runtime.base", BaseRuntime=type("BaseRuntime", (), {}),
                                    RUNTIME_AGENT_LOG_DIR="/polar/agent-logs"),
        "polar.runtime.models": _stub("polar.runtime.models", ExecInput=type("ExecInput", (), {})),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules.pop("gsj_rollout.pi_harness", None)
    from gsj_rollout import pi_harness
    try:
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
