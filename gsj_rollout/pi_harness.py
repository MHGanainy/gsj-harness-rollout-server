"""SERVER — our pi as a Polar harness, via `agent.import_path` (CP-07).

Promoted from `spike/pi_harness_spike.py` (CP-06) per ADR-0006, which is
the contract this module implements: `AgentSpec.settings` is the input
channel (roster, clone URL, MCP base, token parameters — never argv
literals, row 31); the per-episode cutoff token is minted host-side in
`run_steps()` with stdlib HS256 (the `corpus/ingest_corpus.py` ADR-0041
recipe; claims `{case_id, timestep, episode_id, exp}`, `episode_id` = the
Polar session id) and enforced server-side by the MCP service from
verified claims only; `postprocess()` is the only artifact exit.

ADR-0008 (predecessor) fidelity carried from the spike: the package entry
is invoked directly (never the `.bin/pi` shim — pi-mcp-extension's peer
dep overwrites it with legacy 0.73.x); the hermetic flag set; stdin
`< /dev/null`; `PI_CODING_AGENT_DIR` at a session-local agent dir;
models.json with `baseUrl` AND `apiKey` substituted at exec time from the
proxy env — the apiKey IS the Polar session id, which is how the gateway
maps captures to the session. The MCP extension loads via
`--no-extensions --extension <path>` (discovery off, explicit path on);
`.pi/mcp.json` must exist under pi's cwd at launch, with server key `gsj`
and `lifecycle: eager` (both load-bearing: the `mcp_gsj_*` tool names G3
hashes, and print mode has no `/mcp:start`).

Runtime-agnostic by law 5: everything here is exec/download against
`BaseRuntime`. The image must provide `node` and `git`. Never set
`runtime.workdir` to a harness-created path (CP-06 trap); the run step
carries its own `cwd`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shlex
import time

from polar.agent.base import BaseHarness
from polar.agent.models import AgentRunResult
from polar.runtime.base import BaseRuntime, RUNTIME_AGENT_LOG_DIR
from polar.runtime.models import ExecInput

# Container-local, NOT under /polar/session: the session dir is a bind
# mount, and pi's managed-binary installer (rg/fd into <agent dir>/bin)
# renames from the container tmpdir across filesystems — the download
# silently fails and the built-in grep/find die on every episode (CP-07,
# measured; the golden run shows the same failure via its ro /agent).
# /tmp because the image may run non-root (pi0.83.0-3 is uid 1000).
_AGENT_DIR = "/tmp/pi-agent"
_DEFAULT_WORKDIR = "/workspace"  # the predecessor's docker-mode path: keeps the G2 singleton
_DEFAULT_PI_ENTRY = "/opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
_DEFAULT_EXTENSION = "/opt/pi/node_modules/pi-mcp-extension/src/index.ts"
_DEFAULT_SECRET_ENV = "GSJ_MCP_TOKEN_SECRET"
_REQUIRED_SETTINGS = ("case_id", "timestep", "clone_url_for", "mcp_url_base", "tools_allowlist", "artifacts_dir")


def _mint_episode_token(case_id: str, timestep: int, episode_id: str, ttl_s: int, secret: str) -> str:
    """Stdlib HS256 JWT — the ADR-0041 mint recipe (`corpus/ingest_corpus.py:797-810`),
    episode claim set. PyJWT deliberately not added to Polar's venv (ADR-0006, A-14)."""

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64(
        json.dumps(
            {"case_id": case_id, "timestep": timestep, "episode_id": episode_id,
             "exp": int(time.time()) + ttl_s},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = header + b"." + payload
    signature = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


class PiHarness(BaseHarness):
    """pi 0.83.0 + pi-mcp-extension against our corpus, per ADR-0006."""

    async def setup(self, runtime: BaseRuntime) -> None:
        missing = [key for key in _REQUIRED_SETTINGS if not self.settings.get(key)]
        if missing:
            raise ValueError(f"PiHarness settings missing required keys: {missing}")
        if not self.model_name or "/" not in self.model_name:
            raise ValueError(
                f"PiHarness requires model_name as 'provider/model' (got {self.model_name!r})"
            )
        provider, model_id = self.model_name.split("/", 1)
        # The session id doubles as the token's episode_id claim (ADR-0006):
        # the MCP request log becomes joinable to the Polar session.
        self._session_id = runtime.session_id

        settings_json = {"compaction": {"enabled": False}}
        models_template = {
            "providers": {
                provider: {
                    "baseUrl": "__POLAR_GATEWAY_BASE_URL__",
                    "api": "openai-completions",
                    "apiKey": "__POLAR_SESSION_KEY__",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                        "thinkingFormat": "qwen-chat-template",
                    },
                    "models": [
                        {
                            "id": model_id,
                            "reasoning": True,
                            "contextWindow": int(self.settings.get("context_window", 32768)),
                            "maxTokens": int(self.settings.get("max_tokens", 8192)),
                        }
                    ],
                }
            }
        }
        workdir = self.settings.get("workdir", _DEFAULT_WORKDIR)
        clone_url = str(self.settings["clone_url_for"]).format(case_id=self.settings["case_id"])
        branch = f"timestep-{int(self.settings['timestep'])}"
        steps = (
            (
                f"mkdir -p {_AGENT_DIR} && "
                f"printf '%s' {shlex.quote(json.dumps(settings_json))} > {_AGENT_DIR}/settings.json && "
                f"printf '%s' {shlex.quote(json.dumps(models_template))} > {_AGENT_DIR}/models.json.tmpl"
            ),
            f"git clone --branch {shlex.quote(branch)} --single-branch {shlex.quote(clone_url)} {shlex.quote(workdir)}",
        )
        # Fail loudly (H-41 / CP-06 trap): the presets discard exec results,
        # which is how the workdir chicken-and-egg failure stayed silent.
        for step in steps:
            result = await runtime.exec(step)
            if result.return_code != 0:
                raise RuntimeError(
                    f"PiHarness setup failed (rc={result.return_code}) on {step.split()[0]!r}: "
                    f"{result.stderr!r}"
                )

    def run_steps(self, instruction: str) -> list[ExecInput]:
        provider, model_id = self.model_name.split("/", 1)
        workdir = self.settings.get("workdir", _DEFAULT_WORKDIR)

        secret_env = str(self.settings.get("mcp_token_secret_env", _DEFAULT_SECRET_ENV))
        secret = os.environ.get(secret_env)
        if not secret:
            raise RuntimeError(f"PiHarness: token secret env var {secret_env!r} is unset in the gateway process")
        token = _mint_episode_token(
            case_id=str(self.settings["case_id"]),
            timestep=int(self.settings["timestep"]),
            episode_id=self._session_id,
            ttl_s=int(self.settings.get("mcp_token_ttl_s", 3600)),
            secret=secret,
        )
        mcp_url = f"{str(self.settings['mcp_url_base']).rstrip('/')}/mcp/{token}"
        mcp_json = {
            "settings": {"toolPrefix": "mcp"},
            "mcpServers": {
                "gsj": {"transport": "streamable-http", "lifecycle": "eager", "url": mcp_url}
            },
        }

        roster = self.settings["tools_allowlist"]
        tools_argv = ",".join(roster) if isinstance(roster, (list, tuple)) else str(roster)
        pi_entry = self.settings.get("pi_entry", _DEFAULT_PI_ENTRY)
        extension = self.settings.get("pi_mcp_extension", _DEFAULT_EXTENSION)
        thinking = str(self.settings.get("thinking", "off"))

        return [
            ExecInput(
                command=(
                    # .pi/mcp.json must exist at pi launch (the extension reads
                    # cwd at module load and bails silently if it is absent).
                    f"mkdir -p {workdir}/.pi && "
                    f"printf '%s' {shlex.quote(json.dumps(mcp_json))} > {workdir}/.pi/mcp.json && "
                    # models.json from the template, substituting the proxy env
                    # (available only now, not at setup): baseUrl <- the
                    # gateway /v1 endpoint, apiKey <- the session id.
                    f'sed -e "s|__POLAR_GATEWAY_BASE_URL__|$OPENAI_BASE_URL|g" '
                    f'-e "s|__POLAR_SESSION_KEY__|$OPENAI_API_KEY|g" '
                    f"{_AGENT_DIR}/models.json.tmpl > {_AGENT_DIR}/models.json && "
                    f"node {pi_entry} "
                    f"--print --mode json --no-session --no-prompt-templates "
                    f"--no-themes --no-extensions --extension {shlex.quote(extension)} "
                    f"--no-skills --approve --offline "
                    f"--tools {shlex.quote(tools_argv)} "
                    f"--provider {shlex.quote(provider)} "
                    f"--model {shlex.quote(model_id)} "
                    f"--thinking {shlex.quote(thinking)} "
                    f"{shlex.quote(instruction)} "
                    f"< /dev/null "
                    f"2>&1 | tee {RUNTIME_AGENT_LOG_DIR}/pi.txt"
                ),
                cwd=workdir,
                # Exactly the predecessor's env (its ADR-0008): PI_CODING_AGENT_DIR
                # only. PI_OFFLINE=1 (Polar's preset habit, carried by the spike)
                # gates pi's runtime ripgrep download (tools-manager.js reads the
                # ENV, not the --offline flag) and the image ships no rg — set, it
                # silently breaks the built-in grep/find on every episode (CP-07,
                # measured). Unset, pi downloads rg into <agent dir>/bin once per
                # episode — a per-episode network dependency the golden run also had.
                env={**self.env, "PI_CODING_AGENT_DIR": _AGENT_DIR},
            )
        ]

    async def postprocess(self, runtime: BaseRuntime, result: AgentRunResult) -> None:
        """The only artifact exit (ADR-0006): the session dir is destroyed
        after the session. Lands pi's transcript and the deliverable under
        `<artifacts_dir>/<session_id>/`; the trace references them via
        `trajectory.metadata.session_id`. Loud but non-fatal — evidence
        collection must not fail the run."""
        dest = os.path.join(str(self.settings["artifacts_dir"]), self._session_id)
        workdir = self.settings.get("workdir", _DEFAULT_WORKDIR)
        try:
            await runtime.download_file(
                f"{RUNTIME_AGENT_LOG_DIR}/pi.txt", os.path.join(dest, "pi_transcript.jsonl")
            )
        except Exception as exc:
            print(f"PiHarness postprocess: transcript download failed: {exc}")
        try:
            probe = await runtime.exec(f"test -d {workdir}/out")
            if probe.return_code == 0:
                await runtime.download_dir(f"{workdir}/out", os.path.join(dest, "out"))
        except Exception as exc:
            print(f"PiHarness postprocess: deliverable download failed: {exc}")
