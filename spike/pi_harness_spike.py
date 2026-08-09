"""CP-06 spike harness — the minimum harness that runs pi in Polar's runtime.

NOT the permanent module (that is CP-07's `gsj_rollout/pi_harness.py`); this
exists to answer A-2/A-12/A-15 wire questions. Loaded by the gateway process
via `agent.import_path: "pi_harness_spike:PiSpikeHarness"` with
PYTHONPATH=spike (the registry seam — `agent/factory.py:39-56`,
`_imports.py:11-30`; zero vendored edits).

Deltas from Polar's own `pi` preset, all ADR-0008 (predecessor) fidelity:
- the package entry `/opt/pi/node_modules/@earendil-works/pi-coding-agent/
  dist/cli.js` baked into the image at the predecessor's byte-exact pins,
  invoked directly — NEVER the `.bin/pi` shim (pi-mcp-extension's peer dep
  overwrites it with legacy 0.73.x);
- the full hermetic flag set (`--no-session --no-prompt-templates
  --no-themes --no-extensions --no-skills --approve --offline`), stdin
  `< /dev/null` (print mode reads stdin until EOF), `--thinking off`;
- `PI_CODING_AGENT_DIR` pointed at a session-local agent dir instead of
  `$HOME/.pi/agent`;
- `models.json` carries our production shape (provider `gsj`,
  `api: openai-completions`, qwen-chat-template compat) with `baseUrl` AND
  `apiKey` substituted at exec time from the proxy env — the apiKey IS the
  Polar session id, which is how the gateway maps captures to the session
  (`gateway/session.py:215-244`); the preset's `openai`-provider env
  fallback is replaced by an explicit substitution.

`setup()` writes pi's static config (settings.json, the models.json
template, the workspace); `run_steps()` performs the env substitution and
emits the argv — the proxy env does not exist yet at setup time
(`agent/README.md:96-99`).
"""

from __future__ import annotations

import json
import shlex

import os

from polar.agent.base import BaseHarness
from polar.agent.models import AgentRunResult
from polar.runtime.base import BaseRuntime, RUNTIME_AGENT_LOG_DIR
from polar.runtime.models import ExecInput

_AGENT_DIR = "/polar/session/pi-agent"
_WORKSPACE = "/polar/session/workspace"
_PI_ENTRY = "/opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
_TOOLS = "read,ls,grep,find,write,edit,bash"


class PiSpikeHarness(BaseHarness):
    async def setup(self, runtime: BaseRuntime) -> None:
        if not self.model_name or "/" not in self.model_name:
            raise ValueError(
                "PiSpikeHarness requires model_name as 'provider/model' "
                f"(got {self.model_name!r})"
            )
        provider, model_id = self.model_name.split("/", 1)

        settings = {"compaction": {"enabled": False}}
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
                            "contextWindow": int(self.settings.get("context_window", 262144)),
                            "maxTokens": int(self.settings.get("max_tokens", 8192)),
                        }
                    ],
                }
            }
        }
        result = await runtime.exec(
            f"mkdir -p {_AGENT_DIR} {_WORKSPACE} && "
            f"printf '%s' {shlex.quote(json.dumps(settings))} > {_AGENT_DIR}/settings.json && "
            f"printf '%s' {shlex.quote(json.dumps(models_template))} > {_AGENT_DIR}/models.json.tmpl"
        )
        # Fail loudly (H-41): the presets discard exec results, which is how
        # the workdir chicken-and-egg failure above stayed silent.
        if result.return_code != 0:
            raise RuntimeError(
                f"pi spike setup failed (rc={result.return_code}): {result.stderr!r}"
            )

    def run_steps(self, instruction: str) -> list[ExecInput]:
        provider, model_id = self.model_name.split("/", 1)
        thinking = str(self.settings.get("thinking", "off"))
        return [
            ExecInput(
                command=(
                    # models.json from the template, substituting the proxy env
                    # (available only now, not at setup): baseUrl <- the
                    # gateway /v1 endpoint, apiKey <- the session id.
                    f'sed -e "s|__POLAR_GATEWAY_BASE_URL__|$OPENAI_BASE_URL|g" '
                    f'-e "s|__POLAR_SESSION_KEY__|$OPENAI_API_KEY|g" '
                    f"{_AGENT_DIR}/models.json.tmpl > {_AGENT_DIR}/models.json && "
                    f"node {_PI_ENTRY} "
                    f"--print --mode json --no-session --no-prompt-templates "
                    f"--no-themes --no-extensions --no-skills --approve --offline "
                    f"--tools {_TOOLS} "
                    f"--provider {shlex.quote(provider)} "
                    f"--model {shlex.quote(model_id)} "
                    f"--thinking {shlex.quote(thinking)} "
                    f"{shlex.quote(instruction)} "
                    f"< /dev/null "
                    f"2>&1 | tee {RUNTIME_AGENT_LOG_DIR}/pi.txt"
                ),
                cwd=_WORKSPACE,
                env={
                    **self.env,
                    "PI_CODING_AGENT_DIR": _AGENT_DIR,
                    "PI_OFFLINE": "1",
                },
            )
        ]

    async def postprocess(self, runtime: BaseRuntime, result: AgentRunResult) -> None:
        """Copy pi's --mode json transcript out of the sandbox before the
        session dir is torn down — the completions-vs-turns count (issue-#39
        / H-41 check) needs it. Destination comes from the env so the spike
        task file controls it; default lands next to the other captures."""
        dest = self.env.get(
            "SPIKE_TRANSCRIPT_DEST",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures", "pi_polar_transcript.jsonl"),
        )
        try:
            await runtime.download_file(f"{RUNTIME_AGENT_LOG_DIR}/pi.txt", dest)
        except Exception as exc:  # evidence collection must not fail the run
            print(f"pi spike postprocess: transcript download failed: {exc}")
