"""Service configuration — the owned surface (ADR-0040(b)).

One ``config.yaml``, validated at startup with pydantic (``extra="forbid"``
everywhere: an unknown key is a startup error, never silently ignored).
Every field is documented in the service README's config reference.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .decisions import DEFAULT_SEED, N_DECISIONS

_FORBID = ConfigDict(extra="forbid", frozen=True)


class SourceConfig(BaseModel):
    """Where the frozen dataset lives (staging Forgejo)."""
    model_config = _FORBID

    base_url: str  # e.g. http://172.28.9.10:3000 — no trailing slash needed
    owner: str | None = "gsj-admin"  # None for ownerless URL trees (file:// bares)
    repos: list[str] = Field(min_length=1)  # explicit list: the dataset is frozen
    ref_main: str = "main"
    ref_pattern: str = "timestep-{T}"  # discovery of the recorded timestep refs
    auth_token_env: str | None = None  # env var NAME; unset = anonymous read
    clone_cache_dir: Path

    @field_validator("base_url")
    @classmethod
    def _no_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("ref_pattern")
    @classmethod
    def _pattern_has_t(cls, value: str) -> str:
        if "{T}" not in value:
            raise ValueError("ref_pattern must contain the literal '{T}'")
        return value

    @field_validator("repos")
    @classmethod
    def _repos_can_name_chroma_collections(cls, value: list[str]) -> list[str]:
        # The backend names one collection per case (ADR-0016), and chroma
        # enforces names of 3-512 chars from [a-zA-Z0-9._-] starting and
        # ending alphanumeric — NARROWER than the corpus contract's case_id
        # rule (1+ chars, trailing _/- legal). Rejected here with the
        # constraint named, instead of at first index build with chroma's
        # generic error.
        for repo in value:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]",
                                repo):
                raise ValueError(
                    f"repo {repo!r} cannot name a chroma collection "
                    f"(ADR-0016): 3-512 characters from [a-zA-Z0-9._-], "
                    f"starting and ending alphanumeric")
        return value

    def clone_url(self, repo: str) -> str:
        """Anonymous clone URL; the auth token (if any) is injected by the
        ingester and never logged."""
        if self.owner is None:
            return f"{self.base_url}/{repo}.git"
        return f"{self.base_url}/{self.owner}/{repo}.git"


class EmbeddingConfig(BaseModel):
    model_config = _FORBID

    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    revision: str  # required: the model pin is part of the corpus fingerprint
    device: str = "cpu"
    batch_size: int = Field(default=32, ge=1)
    normalize: bool = True

    @field_validator("normalize")
    @classmethod
    def _normalize_is_true(cls, value: bool) -> bool:
        # false had defined raw-dot-product ranking semantics under the numpy
        # scan; the chroma cosine space normalizes internally and cannot
        # reproduce them, so the mode is retired loudly (ADR-0016), the
        # search.method pattern.
        if value is not True:
            raise ValueError(
                "embedding.normalize: false is retired (ADR-0016) — the "
                "chroma cosine backend normalizes internally, so raw "
                "dot-product ranking is no longer a supported mode")
        return value


class ChunkingConfig(BaseModel):
    model_config = _FORBID

    max_tokens: int = Field(default=220, ge=16)
    overlap: int = Field(default=40, ge=0)
    # Chunks never span pages: every chunk has exactly one `page`, which makes
    # the straddling question trivially satisfied (ADR-0040(e)). False is not
    # a supported mode — a future backend that wants cross-page chunks must
    # revisit G5's transcript backstop first.
    respect_page_boundaries: Literal[True] = True

    @field_validator("overlap")
    @classmethod
    def _overlap_lt_max(cls, value: int, info) -> int:
        max_tokens = info.data.get("max_tokens")
        if max_tokens is not None and value >= max_tokens:
            raise ValueError("overlap must be smaller than max_tokens")
        return value


class IndexConfig(BaseModel):
    model_config = _FORBID

    path: Path
    # if-stale: rebuild when the corpus fingerprint mismatches (the normal
    # mode); always: rebuild on every start; never: refuse to rebuild — a
    # missing/stale index is a startup error (frozen prod deployments).
    rebuild: Literal["if-stale", "always", "never"] = "if-stale"


class SearchConfig(BaseModel):
    model_config = _FORBID

    default_k: int = Field(default=5, ge=1)
    max_k: int = Field(default=20, ge=1)
    # chroma: ChromaDB/HNSW over the cutoff-filtered candidate set
    # (ADR-0016; determinism is a measured assumption, A-25, not a
    # guarantee). "exact" — the retired numpy brute-force scan — is
    # rejected BY NAME so a stale config fails loudly instead of promising
    # byte-reproducibility the backend no longer keeps.
    method: str = "chroma"

    @field_validator("method")
    @classmethod
    def _method_is_chroma(cls, value: str) -> str:
        if value == "exact":
            raise ValueError(
                "search.method 'exact' is retired (ADR-0016) — the backend "
                "is ChromaDB; set method: chroma")
        if value != "chroma":
            raise ValueError("search.method must be 'chroma' (ADR-0016)")
        return value


class DecisionsConfig(BaseModel):
    model_config = _FORBID

    seed: int = DEFAULT_SEED
    corpus_size: int = N_DECISIONS  # 30 reproduces the pinned corpus exactly


class AuthConfig(BaseModel):
    model_config = _FORBID

    token_secret_env: str = "GSJ_MCP_TOKEN_SECRET"  # env var NAME, never a value
    leeway_s: int = Field(default=30, ge=0)  # clock-skew allowance for exp


class ServerConfig(BaseModel):
    model_config = _FORBID

    host: str = "127.0.0.1"
    port: int = 8790
    log_level: str = "info"
    # The SDK's DNS-rebinding protection validates the HTTP Host header and
    # 421s anything not allowlisted. OFF by default here: the per-request
    # token is this service's security boundary, clients are not browsers,
    # and the legitimate Host varies by channel (127.0.0.1 on-host,
    # host.docker.internal:PORT from episode containers, tunnel hosts from
    # the workstation) — the CP-29 episode outage was exactly this check
    # rejecting host.docker.internal. Turn it on with an explicit
    # allowed_hosts list ("host" or "host:*" patterns) if a deployment
    # wants it.
    dns_rebinding_protection: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)
    request_log_fields: list[str] = Field(default_factory=lambda: [
        "episode_id", "case_id", "timestep", "tool", "k", "n_results",
        "latency_ms", "cache_hit"])


class ServiceConfig(BaseModel):
    model_config = _FORBID

    source: SourceConfig
    embedding: EmbeddingConfig
    chunking: ChunkingConfig
    index: IndexConfig
    search: SearchConfig
    decisions: DecisionsConfig = DecisionsConfig()
    auth: AuthConfig = AuthConfig()
    server: ServerConfig = ServerConfig()

    def token_secret(self) -> str:
        """Resolve the signing secret from the configured env var — the value
        never appears in config, logs, or errors."""
        secret = os.environ.get(self.auth.token_secret_env)
        if not secret:
            raise ConfigError(
                f"auth.token_secret_env: environment variable "
                f"{self.auth.token_secret_env!r} is unset or empty — the "
                f"service cannot verify tokens without it")
        return secret

    def source_token(self) -> str | None:
        if self.source.auth_token_env is None:
            return None
        token = os.environ.get(self.source.auth_token_env)
        if not token:
            raise ConfigError(
                f"source.auth_token_env: environment variable "
                f"{self.source.auth_token_env!r} is unset or empty")
        return token


class ConfigError(Exception):
    """Startup-time configuration failure with a human-readable message."""


def load_config(path: Path) -> ServiceConfig:
    """Load + validate ``config.yaml``; every failure is a ConfigError that
    names the offending file and field."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: invalid YAML — {error}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    try:
        config = ServiceConfig(**raw)
    except Exception as error:  # pydantic ValidationError, rendered readably
        raise ConfigError(f"{path}: {error}") from None
    # Paths resolve against the config file's directory, not the cwd.
    base = path.resolve().parent
    resolved = config.model_copy(update={
        "source": config.source.model_copy(update={
            "clone_cache_dir": _resolve(base, config.source.clone_cache_dir)}),
        "index": config.index.model_copy(update={
            "path": _resolve(base, config.index.path)}),
    })
    return resolved


def _resolve(base: Path, p: Path) -> Path:
    return p if p.is_absolute() else (base / p)
