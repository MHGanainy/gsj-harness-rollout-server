"""SERVER — the one YAML, two audiences (ADR-0008 §1).

One file is the complete construction surface for both sides (gap row
25): the server loads it to start the receiver and to render Polar's
`topology.yaml`; the trainer loads the same file to render `TaskRequest`
bodies and find the endpoints. Library sections reject unknown keys
loudly; the reserved `user:` section is validated as a mapping and never
read — the trainer's knobs live in the same file without touching our
schema. Nothing here assumes Docker: `runtime.backend` is a value
(law 5), and `runtime.workdir` is deliberately unrepresentable (the
CP-06 trap — the harness run step carries its own cwd).

Collect-N semantics (gap row 26 — stated here and in `submit --help`,
inherited nowhere):
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

COLLECT_SEMANTICS = """\
Collect-N semantics (gap row 26):
- A COLLECTED episode is a SessionResult that is (a) status COMPLETED,
  (b) free of builder findings (gsj_validation.findings == []), and
  (c) free of `checks` findings. ERROR and TIMEOUT never count.
- `submit --episodes N` targets N ATTEMPTS (num_samples=N on one
  TaskRequest) — Polar's scheduler owns episode counts. It is NOT
  collect-until-N-accepted.
- A rejected trace counts as a consumed attempt, is quarantined with its
  findings, and is never retried automatically; exit code 1 says
  collected < attempted, and resubmission is the operator's call."""

__doc__ = (__doc__ or "") + COLLECT_SEMANTICS  # `or ""`: -OO strips docstrings


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EstateConfig(_Section):
    clone_url_for: str  # Forgejo clone URL pattern with {case_id}
    mcp_url_base: str
    mcp_token_secret_env: str = "GSJ_MCP_TOKEN_SECRET"
    serving_base_url: str  # the engine the gateway proxies to
    provider: str = "gsj"  # pi provider key; model_name = "<provider>/<model>"
    model: str


class RuntimeConfig(_Section):
    backend: str = "docker"
    image: str
    network: str = "bridge"  # CP-07's proven Mac leg; host on the H200 estate


class HarnessConfig(_Section):
    import_path: str = "gsj_rollout.pi_harness:PiHarness"
    tools_allowlist: list[str] = Field(min_length=1)  # the G3 pinned input (row 31)
    artifacts_dir: str
    workdir: str = "/workspace"
    context_window: int = 32768
    max_tokens: int = 8192
    thinking: str = "off"
    pi_entry: str | None = None
    pi_mcp_extension: str | None = None
    mcp_token_ttl_s: int = 3600


class BuilderConfig(_Section):
    strategy: str = "gsj_rollout.builder:ValidatingPrefixMergingBuilder"
    end_of_turn_token_id: int  # required, never auto-detected (A-15)
    generation_prompt_glue_ids: list[int] | None = None  # template-specific (A-21)


class RolloutConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8080
    public_url: str | None = None
    save_dir: str | None = None

    @property
    def base_url(self) -> str:
        return self.public_url or _default_url(self.host, self.port)


class GatewayNodeConfig(_Section):
    id: str = "gsj-node-01"
    host: str = "0.0.0.0"
    port: int = 8100
    public_url: str  # required: must serve host dispatch AND the sandbox (CP-03 finding 2)
    engine: str = "vllm"
    max_init_workers: int = 4
    max_run_workers: int = 2
    max_postrun_workers: int = 4


class PolarConfig(_Section):
    rollout: RolloutConfig = Field(default_factory=RolloutConfig)
    gateway: GatewayNodeConfig
    heartbeat_interval_seconds: int = 30


class ReceiverConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8300
    public_url: str | None = None
    traces_dir: str
    quarantine_dir: str | None = None  # default: <traces_dir>/quarantine

    @property
    def base_url(self) -> str:
        return self.public_url or _default_url(self.host, self.port)

    @property
    def resolved_quarantine_dir(self) -> str:
        return self.quarantine_dir or str(Path(self.traces_dir) / "quarantine")


class RunConfig(_Section):
    estate: EstateConfig
    runtime: RuntimeConfig
    harness: HarnessConfig
    builder: BuilderConfig
    polar: PolarConfig
    receiver: ReceiverConfig
    user: dict[str, Any] = Field(default_factory=dict)  # reserved, never read


def _default_url(host: str, port: int) -> str:
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"


def load_config(path: str | Path) -> RunConfig:
    """Load and validate the one YAML; unknown keys name section and key."""
    with open(path) as handle:
        try:
            loaded = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"config {path}: invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"config {path} must contain a top-level mapping")
    try:
        return RunConfig.model_validate(loaded)
    except ValidationError as exc:
        details = []
        for err in exc.errors():
            loc = [str(part) for part in err["loc"]]
            if err["type"] == "extra_forbidden":
                section, key = ".".join(loc[:-1]) or "<root>", loc[-1]
                details.append(f"section '{section}': unknown key '{key}'")
            else:
                details.append(f"'{'.'.join(loc)}': {err['msg']}")
        raise ValueError(f"config {path} invalid — " + "; ".join(details)) from exc


def render_topology(cfg: RunConfig) -> dict[str, Any]:
    """Polar's `topology.yaml` content, generated — never hand-maintained."""
    rollout: dict[str, Any] = {"host": cfg.polar.rollout.host, "port": cfg.polar.rollout.port}
    if cfg.polar.rollout.public_url:
        rollout["public_url"] = cfg.polar.rollout.public_url
    if cfg.polar.rollout.save_dir:
        rollout["save_dir"] = cfg.polar.rollout.save_dir
    node = cfg.polar.gateway
    return {
        "rollout": rollout,
        "gateway": {
            "heartbeat_interval_seconds": cfg.polar.heartbeat_interval_seconds,
            "nodes": [
                {
                    "id": node.id,
                    "host": node.host,
                    "port": node.port,
                    "public_url": node.public_url,
                    "model_served": cfg.estate.model,
                    "inference": {"engine": node.engine, "base_url": cfg.estate.serving_base_url},
                    "max_init_workers": node.max_init_workers,
                    "max_run_workers": node.max_run_workers,
                    "max_postrun_workers": node.max_postrun_workers,
                }
            ],
        },
    }


def render_task_request(
    cfg: RunConfig,
    *,
    task_id: str,
    instruction: str,
    case_id: str,
    timestep: int,
    episodes: int = 1,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    """One Polar `TaskRequest` body for the task triple `(case, timestep, prompt)`.

    `callback_url` points at our receiver: the manager POSTs the terminal
    TaskResult envelope there (`manager.py:164-179`) — the zero-patch push
    channel (ADR-0008 §2)."""
    settings: dict[str, Any] = {
        "case_id": case_id,
        "timestep": int(timestep),
        "clone_url_for": cfg.estate.clone_url_for,
        "mcp_url_base": cfg.estate.mcp_url_base,
        "mcp_token_secret_env": cfg.estate.mcp_token_secret_env,
        "mcp_token_ttl_s": cfg.harness.mcp_token_ttl_s,
        "tools_allowlist": list(cfg.harness.tools_allowlist),
        "artifacts_dir": cfg.harness.artifacts_dir,
        "workdir": cfg.harness.workdir,
        "context_window": cfg.harness.context_window,
        "max_tokens": cfg.harness.max_tokens,
        "thinking": cfg.harness.thinking,
    }
    if cfg.harness.pi_entry:
        settings["pi_entry"] = cfg.harness.pi_entry
    if cfg.harness.pi_mcp_extension:
        settings["pi_mcp_extension"] = cfg.harness.pi_mcp_extension
    builder_config: dict[str, Any] = {"end_of_turn_token_id": cfg.builder.end_of_turn_token_id}
    if cfg.builder.generation_prompt_glue_ids is not None:
        builder_config["generation_prompt_glue_ids"] = list(cfg.builder.generation_prompt_glue_ids)
    return {
        "task_id": task_id,
        "instruction": instruction,
        "num_samples": int(episodes),
        "timeout_seconds": float(timeout_seconds),
        "runtime": {
            "backend": cfg.runtime.backend,
            "image": cfg.runtime.image,
            "network": cfg.runtime.network,
        },
        "agent": {
            "import_path": cfg.harness.import_path,
            "model_name": f"{cfg.estate.provider}/{cfg.estate.model}",
            "settings": settings,
        },
        "builder": {"strategy": cfg.builder.strategy, "config": builder_config},
        "callback_url": f"{cfg.receiver.base_url}/callbacks/session_result",
    }
