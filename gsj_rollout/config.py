"""SERVER — the one YAML, two audiences (ADR-0008 §1, gap row 25): the
server renders the receiver + Polar's `topology.yaml`, the trainer renders
`TaskRequest` bodies, from the same file. Unknown keys reject loudly;
`user:` is reserved and never read. Nothing assumes Docker (law 5);
`runtime.workdir` is deliberately unrepresentable (the CP-06 trap).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_origin
from urllib.parse import urlsplit

import yaml
from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)

from . import checks

COLLECT_SEMANTICS = """\
Collect-N semantics (gap row 26):
- COLLECTED = status COMPLETED + gsj_validation.findings == [] + zero
  `checks` findings; ERROR and TIMEOUT never count.
- `submit --episodes N` targets N ATTEMPTS (num_samples=N) — Polar's
  scheduler owns episode counts; NOT collect-until-N-accepted.
- A rejected trace is a consumed attempt, quarantined with its findings,
  never auto-retried; exit 1 says collected < attempted."""

__doc__ = (__doc__ or "") + COLLECT_SEMANTICS  # `or ""`: -OO strips docstrings


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EstateConfig(_Section):
    """Six values a consumer must supply: the four here, plus
    `GatewayNodeConfig.public_url` and `ReceiverConfig.traces_dir` —
    everything else in this file has a working default (CP-25)."""

    clone_url_for: str  # Forgejo clone URL pattern with {case_id}; episode
    # containers clone it THEMSELVES (CP-11), so it must resolve from inside
    # the sandbox network, not just from the host
    mcp_url_base: str  # the MCP retrieval service, again sandbox-reachable
    mcp_token_secret_env: str = "GSJ_MCP_TOKEN_SECRET"  # env var holding the
    # HMAC secret; must equal the mcp-service's own secret
    serving_base_url: str  # the engine the gateway proxies to — NO /v1 suffix
    # (Polar's proxy appends /v1/chat/completions itself; CP-04′)
    provider: str = "gsj"  # pi provider key; model_name = "<provider>/<model>"
    model: str  # must equal the engine's --served-model-name byte-for-byte
    model_revision: str | None = None  # optional in-band pin: the engine's
    # served snapshot revision (the HF commit sha) — the server never reads
    # it; a trainer's `--snapshot` can verify against it BEFORE the GPU
    # instead of matching the engine by luck (CP-26 F-23, wishlist 23)

    @field_validator("serving_base_url")
    @classmethod
    def _reject_v1_suffix(cls, value: str) -> str:
        # Wishlist 21(b): the suffixed form is schema-plausible and fails at
        # run time as a bare 404 on /v1/v1/… that reads as a wrong host.
        if value.rstrip("/").endswith("/v1"):
            raise ValueError(
                "must not end in /v1 — Polar's proxy appends /v1/chat/completions "
                "itself (CP-04′), so this URL would request /v1/v1/…; drop the "
                "suffix and point at the engine root, e.g. http://127.0.0.1:8000")
        return value


class RuntimeConfig(_Section):
    backend: str = "docker"
    # The published pinned harness image (node + git + pi 0.83.0, CP-06);
    # an estate that builds its own overrides — the default is the image
    # every measured episode ran.
    image: str = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
    network: str = "bridge"  # CP-07's proven Mac leg; the estate's compose
    # network wherever services are addressed container-to-container (CP-04′)


class HarnessConfig(_Section):
    import_path: str = "gsj_rollout.pi_harness:PiHarness"
    # The G3-pinned roster (row 31): the wire `tools` array hashes into the
    # shipped approved set, so any OTHER roster fails
    # `G3:tool_roster_hash_not_approved` until the estate re-pins.
    tools_allowlist: list[str] = Field(
        default=["read", "ls", "grep", "find", "write", "edit", "bash",
                 "mcp_gsj_search_case", "mcp_gsj_search_decisions",
                 "mcp_gsj_case_status", "mcp_gsj_decision_stats"],
        min_length=1)
    artifacts_dir: str = "/tmp/gsj-artifacts"  # host-side, written by the
    # gateway process; the reward grader reads deliverables here — point it
    # somewhere durable for real runs (/tmp is ephemeral, honestly so)
    workdir: str = "/workspace"  # in-image; G2's approved hash is the
    # /workspace singleton — changing it means a re-pin walk
    context_window: int = 32768
    max_tokens: int = 8192
    thinking: str = "off"  # flipping it needs a symmetric served template
    # AND re-conceiving G6 (A-22, CP-23) — not a knob today
    pi_entry: str | None = None
    pi_mcp_extension: str | None = None
    mcp_token_ttl_s: int = 3600


class BuilderConfig(_Section):
    strategy: str = "gsj_rollout.builder:ValidatingPrefixMergingBuilder"
    # Pinned, never auto-detected (A-15) — a default is still an explicit pin
    # on every rendered TaskRequest, and 151645 is <|im_end|> under the Qwen3
    # tokenizer the default model serves. Re-derive when `estate.model`
    # changes: tokenizer.convert_tokens_to_ids("<|im_end|>") — or your
    # template's end-of-turn token — against the SERVED tokenizer.
    end_of_turn_token_id: int = 151645
    generation_prompt_glue_ids: list[int] | None = None  # template-specific
    # (A-21); dormant since CP-04′ — set only under an asymmetric template


class ChecksConfig(_Section):
    """`CheckPolicy` mirror, defaults read from it (CP-11, spec §operator
    surface); a CUDA estate sets `zero_at_mask1_max_rate: 0.0` (row 27).
    CP-13 closed the declared mirror drift: complete by test."""

    sentinel_threshold: float = checks.CheckPolicy.sentinel_threshold
    zero_at_mask1_max_rate: float = checks.CheckPolicy.zero_at_mask1_max_rate
    reject_toolless_roster: bool = checks.CheckPolicy.reject_toolless_roster  # H-41


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
    public_url: str  # required: ONE URL reachable from host dispatch AND
    # from inside episode containers (CP-03 finding 2) — a LAN IP or the
    # estate network's gateway IP, never localhost
    engine: str = "vllm"
    max_init_workers: int = 4
    max_run_workers: int = 2
    max_postrun_workers: int = 4

    @model_validator(mode="after")
    def _port_agrees_with_public_url(self) -> "GatewayNodeConfig":
        # Wishlist 21(a): one fact, two keys — a mismatch dispatches to a URL
        # nothing listens on (measured: connection refused, CP-26). Reject
        # rather than derive: public_url is the consumer's statement of
        # reachability and silently rewriting either key would hide the typo.
        parsed = urlsplit(self.public_url)
        if parsed.scheme not in ("http", "https"):
            # A scheme-less "IP:8100" parses as path (or host-as-scheme), so
            # the port check below would misread it as "port 80" and suggest
            # a fix that validates yet stays undialable. Name the real gap.
            raise ValueError(
                f"public_url {self.public_url!r} needs an explicit http:// or "
                f"https:// scheme — without one the URL cannot be dialed and "
                f"its port cannot be read")
        advertised = parsed.port if parsed.port is not None else (
            443 if parsed.scheme == "https" else 80)
        if advertised != self.port:
            raise ValueError(
                f"public_url advertises port {advertised} but the gateway "
                f"listens on port {self.port} — one fact, two keys; set "
                f"public_url's port to :{self.port} or set gateway.port "
                f"to {advertised} (a mismatch means connection-refused on "
                f"the advertised URL at the first dispatch)")
        return self


class PolarConfig(_Section):
    rollout: RolloutConfig = Field(default_factory=RolloutConfig)
    gateway: GatewayNodeConfig
    heartbeat_interval_seconds: int = 30


class ReceiverConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8300
    public_url: str | None = None
    traces_dir: str  # required, no default on purpose: this is where the
    # training data lands, and a /tmp default would lose it silently (the
    # CP-19 honest-defaults rule) — choose durable storage
    quarantine_dir: str | None = None  # default: <traces_dir>/quarantine

    @property
    def base_url(self) -> str:
        return self.public_url or _default_url(self.host, self.port)

    @property
    def resolved_quarantine_dir(self) -> str:
        return self.quarantine_dir or str(Path(self.traces_dir) / "quarantine")


class RunConfig(_Section):
    estate: EstateConfig
    # runtime/harness/builder/checks may be omitted wholesale (CP-25): every
    # field of theirs has a working default, so absence means "the measured
    # reference values", stated per-field at each default.
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    builder: BuilderConfig = Field(default_factory=BuilderConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    polar: PolarConfig
    receiver: ReceiverConfig
    user: dict[str, Any] = Field(default_factory=dict)  # reserved, never read


def _default_url(host: str, port: int) -> str:
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"


def _null_sections_to_empty(data: dict[str, Any], model: type[BaseModel]) -> None:
    """F-25 (wishlist 23): a section whose every key is deleted or commented
    out parses as YAML null, and pydantic reports 'Input should be a valid
    dictionary' naming no field. Normalize null to {} wherever the model
    expects a section, so the field-level errors fire instead — the message
    then names the section AND its missing keys ('polar.gateway.public_url:
    Field required'). Model-driven, not a hardcoded section list. Dict-typed
    sections (`user:`) normalize too — gutting the free section down to its
    header must not reject the config."""
    for name, field in model.model_fields.items():
        sub = field.annotation
        if name not in data:
            continue
        if isinstance(sub, type) and issubclass(sub, BaseModel):
            if data[name] is None:
                data[name] = {}
            elif isinstance(data[name], dict):
                _null_sections_to_empty(data[name], sub)
        elif get_origin(sub) is dict and data[name] is None:
            data[name] = {}


def load_config(path: str | Path) -> RunConfig:
    """Load and validate the one YAML; unknown keys name section and key."""
    with open(path) as handle:
        try:
            loaded = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"config {path}: invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"config {path} must contain a top-level mapping")
    _null_sections_to_empty(loaded, RunConfig)
    try:
        cfg = RunConfig.model_validate(loaded)
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
    # ADR-0010: rebind the process default; last `load_config` wins.
    checks.DEFAULT_POLICY = checks.CheckPolicy(**cfg.checks.model_dump())
    return cfg


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
    prompt_source: str = "free",
    skill_card_text: str | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    """One Polar `TaskRequest` body for the triple `(case, timestep, prompt)`;
    `callback_url` is the zero-patch push channel (ADR-0008 §2).

    `prompt_source` states the task's origin for G1 (row 9): `free` for
    verbatim text (the frozen `cli.py` path — resolution never happens
    there), `skill:<name>` for taskbank skill rows (ADR-0003). Passing the
    resolved card text states its bytes-hash (convention 1) at
    `metadata.skill_card_hash`; omitting it leaves the hash to whoever
    reads the card from the checkout, and G1 fails closed until one of
    them supplies it — the taskbank keeps the choice.

    `split` (ADR-0015) states the case's train/eval placement — a render
    parameter like `prompt_source`, never a lock lookup: the config
    surface grows no corpus dependency, and the taskbank supplies the
    value from `corpus.lock.json` when ADR-0003 lands. None (the frozen
    `cli.py` path, which cannot know it) omits the key: absent means
    UNSTATED, never `train` — a false label is worse than a missing one.
    Carried and visible, not enforced: the trainer owns not training on
    eval (row 32); `checks.py` rejects only a value outside the ADR-0015
    vocabulary (TR3)."""
    skill_card_hash = None
    if not isinstance(prompt_source, str):
        raise ValueError(f"prompt_source must be 'free' or 'skill:<name>', got {prompt_source!r}")
    if prompt_source == "free":
        if skill_card_text is not None:
            raise ValueError("skill_card_text is only valid with a skill: prompt_source")
    elif prompt_source.startswith("skill:") and prompt_source[len("skill:"):].strip():
        if skill_card_text is not None:
            if not isinstance(skill_card_text, str) or not skill_card_text:
                raise ValueError("skill_card_text must be non-empty text")
            # UTF-8 bytes, the pins convention: read the card with
            # `read_bytes().decode('utf-8')`, never `read_text()` (locale
            # + universal-newline translation would change the hash).
            skill_card_hash = checks._sha256_text(skill_card_text)
            if skill_card_hash is None:
                raise ValueError("skill_card_text is not UTF-8-encodable")
    else:
        raise ValueError(f"prompt_source must be 'free' or 'skill:<name>', got {prompt_source!r}")
    if split is not None and split not in ("train", "eval"):
        raise ValueError(f"split must be 'train' or 'eval' (ADR-0015), got {split!r}")
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
    metadata: dict[str, Any] = {
        "case_id": case_id, "timestep": int(timestep), "prompt_source": prompt_source,
    }
    if skill_card_hash is not None:
        metadata["skill_card_hash"] = skill_card_hash
    if split is not None:
        metadata["split"] = split
    return {
        "task_id": task_id,
        "instruction": instruction,
        "num_samples": int(episodes),
        "timeout_seconds": float(timeout_seconds),
        # G5's structural timestep (CP-11) + G1's prompt_source (CP-13):
        # hoisted into every trace's top-level metadata
        # (`prefix_merging.py:371-375`). Polar's reserved keys
        # (`session_id`/`task_id`/`evaluation`/`policy_version`) never here.
        "metadata": metadata,
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
