"""CP-84: the lightweight host descriptor agrees with the actual service.

Import the owned ServiceConfig here, inside its test environment. The estate
command must not acquire the service's encoder/vector-runtime dependencies.
The host deliberately keeps its existing strict YAML scalar contract; tests
separate that contract from Pydantic's permissive, unadvertised coercions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gsj_mcp_service.config import ServiceConfig


_ESTATE_PATH = Path(__file__).resolve().parents[2] / "estate.py"
_spec = importlib.util.spec_from_file_location("cp84_estate_contract", _ESTATE_PATH)
est = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(est)


def template_values():
    return dict(
        prog="schema-contract", run="synthetic", forgejo_url="http://localhost:1",
        owner="synthetic", repos="case_synthetic", read_env="CP84_READ",
        model=est.DEFAULT_EMBEDDING_MODEL, revision=est.DEFAULT_EMBEDDING_REVISION,
        chunk_max=220, chunk_overlap=40, rebuild="if-stale", secret_env="CP84_SECRET")


def base_doc():
    return yaml.safe_load(est.render_mcp_template(**template_values()))


def service_problems(doc):
    try:
        ServiceConfig(**doc)
    except ValidationError as error:
        return [".".join(str(part) for part in row["loc"])
                for row in error.errors()]
    return []


B04 = (
    ("search", "method", "exact"),
    ("embedding", "normalize", False),
    ("embedding", "batch_size", 0),
    ("search", "default_k", 0),
    ("chunking", "respect_page_boundaries", False),
    ("chunking", "max_tokens", 15),
    ("decisions", "corpus_size", 0),
    ("embedding", "revision", "main"),
    ("embedding", "model", "not a model id"),
)


@pytest.mark.parametrize("section,key,value", B04,
                         ids=[f"{section}.{key}" for section, key, _ in B04])
def test_audited_bad_value_is_refused_by_host_and_actual_service(section, key, value):
    doc = base_doc()
    assert service_problems(doc) == []
    doc[section][key] = value
    dotted = f"{section}.{key}"
    assert dotted in service_problems(doc)
    problems = est.mcp_override_problems({section: {key: value}})
    assert any(problem.startswith(dotted + ":") for problem in problems), problems


# Native YAML scalars exercise every public field's boundaries and custom
# service validators. Values are synthetic: no model is downloaded or secret
# read. The complete operator mapping keeps cross-field comparisons honest.
NATIVE_VALUES = {
    "embedding": {
        "model": ("x", "BAAI/bge-small-en-v1.5", "a/b", "a..b", "a--b", "x_",
                  "", "not a model id", "/leading", "a/b/c", "a/", "_x", "ä/x"),
        "revision": ("0" * 40, "abcdef0123456789" * 2 + "abcdef01",
                     "main", "v1", "a" * 39, "a" * 41, "A" * 40, "g" * 40),
        "device": ("cpu", "cuda:0", "mps", "", "not-a-device"),
        "batch_size": (-1, 0, 1, 2, 32, 64, 10**12),
        "normalize": (False, True),
    },
    "chunking": {
        "max_tokens": (-1, 0, 15, 16, 39, 40, 41, 220, 1000),
        "overlap": (-1, 0, 1, 40, 219, 220, 221),
        "respect_page_boundaries": (False, True),
    },
    "search": {
        "default_k": (-1, 0, 1, 5, 20, 21, 10**12),
        "max_k": (-1, 0, 1, 5, 20, 10**12),
        "method": ("chroma", "exact", "faiss", "CHROMA", ""),
    },
    "decisions": {
        "seed": (-10**12, -1, 0, 1, 20260204),
        "corpus_size": (-1, 0, 1, 30, 10**12),
    },
}


@pytest.mark.parametrize("section", NATIVE_VALUES)
def test_host_native_scalar_semantics_match_actual_service(section):
    for key, values in NATIVE_VALUES[section].items():
        for value in values:
            doc = base_doc()
            doc[section][key] = value
            host = est.mcp_config_problems(doc)
            service = service_problems(doc)
            assert bool(host) == bool(service), (section, key, value, host, service)
            if host:
                assert any(problem.startswith(f"{section}.{key}:")
                           or (key == "max_tokens"
                               and problem.startswith("chunking.overlap:"))
                           for problem in host), host


def test_chunk_window_relationship_uses_the_complete_effective_values():
    for maximum, overlap in ((16, 15), (16, 16), (16, 17), (220, 219),
                             (220, 220), (1000, 999), (1000, 1000)):
        doc = base_doc()
        doc["chunking"].update(max_tokens=maximum, overlap=overlap)
        host = est.mcp_config_problems(doc)
        service = service_problems(doc)
        assert bool(host) == bool(service), (maximum, overlap, host, service)


def test_existing_host_type_contract_is_explicitly_stricter_than_service_coercion():
    # Pydantic accepts these spellings, but the host has always required a
    # native YAML integer or boolean. Descriptor consolidation must not
    # silently broaden that contract or falsely claim these are service errors.
    for section, key, value in (
        ("embedding", "batch_size", "32"), ("embedding", "batch_size", 32.0),
        ("embedding", "batch_size", True), ("search", "default_k", "5"),
        ("decisions", "seed", "20260204"), ("decisions", "corpus_size", True),
        ("embedding", "normalize", "true"), ("embedding", "normalize", 1),
        ("chunking", "respect_page_boundaries", 1),
    ):
        doc = base_doc()
        doc[section][key] = value
        assert service_problems(doc) == []
        host = est.mcp_override_problems({section: {key: value}})
        assert host, (section, key, value)
        assert "service would refuse" not in " ".join(host), host


def test_wrong_yaml_shapes_are_never_admitted_to_the_service():
    for section, model_field in ServiceConfig.model_fields.items():
        if section not in est.MCP_OPERATOR_SECTIONS:
            continue
        for key in model_field.annotation.model_fields:
            for value in (None, [], {}):
                if key == "path" and value is None:
                    continue
                doc = base_doc()
                doc[section][key] = value
                assert service_problems(doc), (section, key, value)
                problems = est.mcp_config_problems(doc)
                assert any(problem.startswith(f"{section}.{key}:")
                           for problem in problems), (section, key, value, problems)


def test_default_template_matches_service_defaults_without_adding_path():
    values = template_values()
    assert est.render_mcp_template(**values) == est.MCP_CONFIG.format(**values)
    doc = base_doc()
    effective = ServiceConfig(**doc)
    for section in est.MCP_OPERATOR_SECTIONS:
        model = ServiceConfig.model_fields[section].annotation
        for key, field in model.model_fields.items():
            if not field.is_required() and key != "path":
                assert doc[section][key] == field.default, (section, key)
            if key in doc[section]:
                assert doc[section][key] == getattr(getattr(effective, section), key)
    assert "path" not in doc["decisions"]
    assert effective.decisions.path is None
    assert effective.embedding.batch_size == 32


@pytest.mark.parametrize("key,value", [
    ("model", "on"), ("model", "null"), ("model", "123"),
    ("model", "true"), ("model", "False"), ("model", "0xFF"),
    ("revision", "0" * 40), ("revision", "1" * 40),
])
def test_production_rendering_preserves_ambiguous_yaml_strings_for_actual_service(key, value):
    values = template_values()
    values[key] = value
    doc = yaml.safe_load(est.render_mcp_template(**values))
    assert type(doc["embedding"][key]) is str
    assert doc["embedding"][key] == value
    actual = ServiceConfig(**doc)
    assert getattr(actual.embedding, key) == value


@pytest.mark.parametrize("section", ("embedding", "chunking", "search", "decisions"))
def test_descriptor_keys_types_bounds_and_literals_match_actual_schema(section):
    model = ServiceConfig.model_fields[section].annotation
    schema = model.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(est.MCP_FIELDS[section]) == set(model.model_fields)
    for key, actual in schema["properties"].items():
        spec = est.MCP_FIELDS[section][key]
        nullable = "anyOf" in actual
        shape = next(item for item in actual["anyOf"] if item["type"] != "null") \
            if nullable else actual
        assert spec["type"] is {"integer": int, "string": str,
                                "boolean": bool}[shape["type"]], (section, key)
        assert spec.get("minimum") == shape.get("minimum"), (section, key)
        assert bool(spec.get("nullable")) == nullable, (section, key)
        if "const" in shape:
            assert spec["literal"] == shape["const"], (section, key)
        assert spec["consequence"] and spec["review"], (section, key)
        assert isinstance(spec["fingerprint"], bool), (section, key)
    # This one key is the complete service shape but remains behind the host
    # mount flag. A new service key must first be accounted for, never dropped.
    flag_only = {key for key, spec in est.MCP_FIELDS[section].items()
                 if spec.get("flag_only")}
    assert flag_only == ({"path"} if section == "decisions" else set())


def test_decisions_path_is_recognized_but_owned_by_the_mount_flag():
    for value in (None, "./decisions", "/app/decisions"):
        doc = base_doc()
        doc["decisions"]["path"] = value
        assert service_problems(doc) == []
        assert est.mcp_config_problems(doc) == []
        host = est.mcp_override_problems({"decisions": {"path": value}})
        assert any(problem.startswith("decisions.path:") and "--decisions-dir" in problem
                   for problem in host), host
