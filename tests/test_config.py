"""CP-08 config tests: round-trip, loud unknown keys, free-form user, golden renders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from gsj_rollout.config import load_config, render_task_request, render_topology

FIXTURE = Path(__file__).parent / "fixtures" / "rollout.yaml"
GOLDEN = Path(__file__).parent / "golden"


def test_full_file_round_trip():
    cfg = load_config(FIXTURE)
    assert cfg.estate.model == "Qwen/Qwen3-0.6B"
    assert cfg.estate.mcp_token_secret_env == "GSJ_MCP_TOKEN_SECRET"  # default
    assert cfg.runtime.backend == "docker"  # a value, not an assumption (law 5)
    assert cfg.harness.tools_allowlist[0] == "read"
    assert len(cfg.harness.tools_allowlist) == 11
    assert cfg.builder.end_of_turn_token_id == 151645
    assert cfg.builder.generation_prompt_glue_ids == [151667, 271, 151668, 271]
    assert cfg.polar.rollout.base_url == "http://127.0.0.1:8080"
    assert cfg.receiver.resolved_quarantine_dir == "/tmp/gsj-traces/quarantine"


def test_unknown_key_names_section_and_key(tmp_path):
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["estate"]["clone_pattern"] = "oops"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match=r"section 'estate': unknown key 'clone_pattern'"):
        load_config(bad)


def test_missing_required_key_is_loud(tmp_path):
    doc = yaml.safe_load(FIXTURE.read_text())
    del doc["builder"]["end_of_turn_token_id"]  # A-15: required, never defaulted
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match="end_of_turn_token_id"):
        load_config(bad)


def test_user_section_is_free_form_and_never_read(tmp_path):
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["user"] = {"whatever": {"deeply": ["nested", 1]}, "keys": True}
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(doc))
    cfg = load_config(path)
    assert cfg.user["whatever"]["deeply"] == ["nested", 1]
    rendered = json.dumps(render_topology(cfg)) + json.dumps(
        render_task_request(cfg, task_id="t", instruction="i", case_id="c", timestep=1)
    )
    assert "whatever" not in rendered and "deeply" not in rendered

    doc["user"] = ["not", "a", "mapping"]
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError):
        load_config(path)


def test_topology_render_matches_golden():
    cfg = load_config(FIXTURE)
    golden = yaml.safe_load((GOLDEN / "topology.yaml").read_text())
    assert render_topology(cfg) == golden


def test_task_request_render_matches_golden():
    cfg = load_config(FIXTURE)
    rendered = render_task_request(
        cfg,
        task_id="golden-task",
        instruction="Summarize the case.",
        case_id="case_0001",
        timestep=12,
        episodes=1,
        timeout_seconds=900.0,
    )
    golden = json.loads((GOLDEN / "task_request.json").read_text())
    assert rendered == golden
    # The roster chain's pinned input (row 31): config == rendered settings.
    assert rendered["agent"]["settings"]["tools_allowlist"] == cfg.harness.tools_allowlist


# --- CP-11: the structural timestep + the CheckPolicy operator surface ----


def test_task_request_metadata_carries_the_task_identity():
    """G5's structural timestep: `TaskRequest.metadata` rides the callback
    verbatim and is hoisted into every trace's top-level metadata
    (`prefix_merging.py:371-375`), so T stops depending on the agent having
    called `case_status`. Polar setdefault-shadows `session_id`/`task_id`
    and overwrites `evaluation`/`policy_version` — reserved, never ours."""
    cfg = load_config(FIXTURE)
    rendered = render_task_request(cfg, task_id="t", instruction="i",
                                   case_id="case_0001", timestep=12)
    assert rendered["metadata"] == {"case_id": "case_0001", "timestep": 12}
    assert not {"session_id", "task_id", "evaluation", "policy_version"} & rendered["metadata"].keys()


def test_checks_section_reaches_the_frozen_call_sites(tmp_path, callback_body, monkeypatch):
    """Step 5's point: the knob must turn WITHOUT touching receiver/client.
    Loading a YAML with `checks:` rebinds the process-default policy, and
    the frozen call shape `validate_session_result(result)` picks it up."""
    import gsj_rollout.checks as checks

    monkeypatch.setattr(checks, "DEFAULT_POLICY", checks.DEFAULT_POLICY)  # register restore
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["checks"] = {"zero_at_mask1_max_rate": 0.0}  # the CUDA-estate strictness (row 27)
    path = tmp_path / "cuda.yaml"
    path.write_text(yaml.safe_dump(doc))
    cfg = load_config(path)
    assert cfg.checks.zero_at_mask1_max_rate == 0.0
    assert cfg.checks.sentinel_threshold == -9000.0  # untouched fields keep CheckPolicy defaults
    assert checks.DEFAULT_POLICY == checks.CheckPolicy(zero_at_mask1_max_rate=0.0)
    # The CP-07 trace carries 27/441 exact-0.0 at mask==1: clean under the
    # default allowance, rejected under the configured strictness.
    assert "LP6:zero_logprob_rate_at_mask1:27/441>0.0" in checks.validate_session_result(callback_body)
