"""Config validation (ADR-0040(b)): one config.yaml, pydantic-validated with
extra="forbid" everywhere — unknown keys and type errors are startup failures
naming the offending file and field; paths resolve against the config file's
directory; secrets are env-var NAMES resolved at use, never values."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from helpers import BARES_URL, REVISION

from gsj_mcp_service.config import ConfigError, load_config


def base_doc() -> dict:
    return {
        "source": {"base_url": BARES_URL, "owner": None,
                   "repos": ["case_0001"], "clone_cache_dir": "./data/clones"},
        "embedding": {"revision": REVISION},
        "chunking": {"max_tokens": 220, "overlap": 40,
                     "respect_page_boundaries": True},
        "index": {"path": "./data/index"},
        "search": {"default_k": 5, "max_k": 20},
        "decisions": {"seed": 20260204, "corpus_size": 30},
        "auth": {"token_secret_env": "GSJ_MCP_TOKEN_SECRET", "leeway_s": 30},
        "server": {"host": "127.0.0.1", "port": 8790},
    }


def dump(tmp_path: Path, doc: dict, name: str = "config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def test_good_config_loads(tmp_path):
    """A complete valid config loads; defaults fill the omitted fields and
    the base_url trailing slash is normalized away."""
    doc = base_doc()
    doc["source"]["base_url"] = BARES_URL + "/"
    config = load_config(dump(tmp_path, doc))
    assert config.source.base_url == BARES_URL          # trailing slash stripped
    assert config.source.owner is None
    assert config.source.repos == ["case_0001"]
    assert config.embedding.revision == REVISION
    assert config.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.chunking.max_tokens == 220
    assert config.index.rebuild == "if-stale"           # default
    assert config.search.max_k == 20
    assert config.decisions.seed == 20260204
    assert config.decisions.corpus_size == 30
    assert config.auth.leeway_s == 30
    assert config.source.clone_url("case_0001") == f"{BARES_URL}/case_0001.git"


@pytest.mark.parametrize("section", [None, "source", "embedding", "chunking",
                                     "index", "search", "auth", "server"])
def test_unknown_key_anywhere_fails(tmp_path, section):
    """extra="forbid" at every level: an unknown key — top-level or nested in
    any section — is a ConfigError naming the stray key, never silently
    ignored."""
    doc = base_doc()
    if section is None:
        doc["flux_capacitor"] = 1
    else:
        doc[section]["flux_capacitor"] = 1
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert "flux_capacitor" in str(excinfo.value)
    assert "config.yaml" in str(excinfo.value)          # names the file


@pytest.mark.parametrize("drop", [("embedding", "revision"),
                                  ("source", "repos"),
                                  ("source", "base_url"),
                                  ("index", "path")])
def test_missing_required_field_fails(tmp_path, drop):
    """Required fields (embedding.revision, source.repos/base_url,
    index.path) have no defaults — omitting one is a named ConfigError."""
    section, field = drop
    doc = base_doc()
    del doc[section][field]
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert field in str(excinfo.value)


def test_missing_section_fails(tmp_path):
    """A whole missing required section (embedding) fails loudly."""
    doc = base_doc()
    del doc["embedding"]
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert "embedding" in str(excinfo.value)


def test_respect_page_boundaries_false_fails(tmp_path):
    """respect_page_boundaries: false is NOT a supported mode (ADR-0040(e) —
    cross-page chunks would need G5's transcript backstop revisited first)."""
    doc = base_doc()
    doc["chunking"]["respect_page_boundaries"] = False
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert "respect_page_boundaries" in str(excinfo.value)


@pytest.mark.parametrize("overlap", [220, 300])
def test_overlap_ge_max_tokens_fails(tmp_path, overlap):
    """overlap >= max_tokens would make the chunk window stride <= 0."""
    doc = base_doc()
    doc["chunking"]["overlap"] = overlap
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert "overlap" in str(excinfo.value)


def test_relative_paths_resolve_against_config_dir(tmp_path):
    """clone_cache_dir and index.path given relative resolve against the
    config FILE's directory, not the process cwd; absolute paths pass
    through untouched."""
    nested = tmp_path / "deploy" / "conf"
    nested.mkdir(parents=True)
    doc = base_doc()
    doc["source"]["clone_cache_dir"] = "./cache/clones"
    doc["index"]["path"] = "../idx"
    config = load_config(dump(nested, doc))
    assert config.source.clone_cache_dir == nested / "cache/clones"
    assert config.index.path == nested / ".." / "idx"
    assert config.source.clone_cache_dir.is_absolute()
    assert config.index.path.is_absolute()

    doc2 = copy.deepcopy(doc)
    doc2["source"]["clone_cache_dir"] = str(tmp_path / "abs-clones")
    doc2["index"]["path"] = str(tmp_path / "abs-index")
    config2 = load_config(dump(nested, doc2, name="config2.yaml"))
    assert config2.source.clone_cache_dir == tmp_path / "abs-clones"
    assert config2.index.path == tmp_path / "abs-index"


def test_token_secret_env_unset_raises(tmp_path, monkeypatch):
    """token_secret() is resolved from the NAMED env var at call time; unset
    (or empty) is a ConfigError naming the variable — the value itself never
    appears anywhere."""
    doc = base_doc()
    doc["auth"]["token_secret_env"] = "GSJ_TEST_SECRET_THAT_IS_UNSET"
    config = load_config(dump(tmp_path, doc))
    monkeypatch.delenv("GSJ_TEST_SECRET_THAT_IS_UNSET", raising=False)
    with pytest.raises(ConfigError) as excinfo:
        config.token_secret()
    assert "GSJ_TEST_SECRET_THAT_IS_UNSET" in str(excinfo.value)

    monkeypatch.setenv("GSJ_TEST_SECRET_THAT_IS_UNSET", "")
    with pytest.raises(ConfigError):
        config.token_secret()

    monkeypatch.setenv("GSJ_TEST_SECRET_THAT_IS_UNSET", "s3cret-value")
    assert config.token_secret() == "s3cret-value"


def test_ref_pattern_must_contain_T(tmp_path):
    """ref_pattern without the literal '{T}' cannot discover timestep refs."""
    doc = base_doc()
    doc["source"]["ref_pattern"] = "timestep-x"
    with pytest.raises(ConfigError) as excinfo:
        load_config(dump(tmp_path, doc))
    assert "{T}" in str(excinfo.value)


def test_missing_config_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path / "nope.yaml")
    assert "not found" in str(excinfo.value)
