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
    del doc["receiver"]["traces_dir"]  # required, no default (CP-25: a /tmp
    # default would lose the training data silently — honest-defaults rule)
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match="traces_dir"):
        load_config(bad)


# --- CP-25: the consumer surface — endpoints required, the rest defaulted --


def test_a_stranger_config_of_endpoints_only_loads(tmp_path):
    """The CP-25 claim, machine-checked: the six values a consumer must
    supply — four estate endpoints, the gateway public_url, the traces
    dir — are a COMPLETE config; everything else has a working default."""
    minimal = {
        "estate": {
            "clone_url_for": "http://git.example:3000/gsj/{case_id}.git",
            "mcp_url_base": "http://mcp.example:8790",
            "serving_base_url": "http://127.0.0.1:8000",
            "model": "Qwen/Qwen3-0.6B",
        },
        "polar": {"gateway": {"public_url": "http://192.0.2.1:8100"}},
        "receiver": {"traces_dir": "/data/traces"},
    }
    path = tmp_path / "minimal.yaml"
    path.write_text(yaml.safe_dump(minimal))
    cfg = load_config(path)
    # The defaults are the measured estate values, stated at their source:
    assert cfg.runtime.image == "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
    assert len(cfg.harness.tools_allowlist) == 11  # the G3-pinned roster
    assert cfg.harness.artifacts_dir == "/tmp/gsj-artifacts"
    assert cfg.builder.end_of_turn_token_id == 151645  # A-15: still an
    # explicit pin on every render — the default is the pin, not detection
    rendered = render_task_request(cfg, task_id="t", instruction="i",
                                   case_id="c", timestep=1)
    assert rendered["builder"]["config"]["end_of_turn_token_id"] == 151645
    assert rendered["agent"]["settings"]["tools_allowlist"][0] == "read"
    assert render_topology(cfg)["gateway"]["nodes"][0]["public_url"] == "http://192.0.2.1:8100"


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
    """G5's structural timestep (CP-11) + G1's prompt_source (CP-13):
    `TaskRequest.metadata` rides the callback verbatim and is hoisted into
    every trace's top-level metadata (`prefix_merging.py:371-375`), so T
    and the task's origin stop depending on in-trace heuristics. Polar
    setdefault-shadows `session_id`/`task_id` and overwrites
    `evaluation`/`policy_version` — reserved, never ours."""
    cfg = load_config(FIXTURE)
    rendered = render_task_request(cfg, task_id="t", instruction="i",
                                   case_id="case_0001", timestep=12)
    assert rendered["metadata"] == {
        "case_id": "case_0001", "timestep": 12, "prompt_source": "free"}
    assert not {"session_id", "task_id", "evaluation", "policy_version"} & rendered["metadata"].keys()


# --- CP-13: prompt_source + the complete CheckPolicy mirror ---------------


def test_skill_prompt_source_states_the_card_bytes_hash():
    """G1's evidence (row 9): a skill source carries the sha256 of the
    RESOLVED card bytes (convention 1), computed at render from the text
    the submit path held — for the real staging summarize card, that is
    the pinned approved value."""
    import hashlib
    import json as json_mod

    cfg = load_config(FIXTURE)
    card = (Path(__file__).parent.parent
            / "corpus" / "staging" / "skills" / "summarize" / "SKILL.md").read_text()
    rendered = render_task_request(
        cfg, task_id="t", instruction=card, case_id="case_0001", timestep=12,
        prompt_source="skill:summarize", skill_card_text=card)
    stated = rendered["metadata"]["skill_card_hash"]
    assert stated == hashlib.sha256(card.encode("utf-8")).hexdigest()
    import gsj_rollout.checks as checks
    pins = json_mod.loads(checks.PINS_PATH.read_text())["pins"]
    assert stated in pins["skill_card_hash"]
    assert rendered["metadata"]["prompt_source"] == "skill:summarize"


def test_prompt_source_shapes_are_validated_at_render():
    cfg = load_config(FIXTURE)
    render = lambda **kw: render_task_request(  # noqa: E731
        cfg, task_id="t", instruction="i", case_id="c", timestep=1, **kw)
    with pytest.raises(ValueError, match="only valid with a skill"):
        render(prompt_source="free", skill_card_text="CARD")
    # every rejected shape raises the DOCUMENTED ValueError — including the
    # non-string ones, which reached `.startswith` and raised AttributeError
    # until the CP-13 adversarial pass measured it
    for bad in ("taskbank", "skill:", "", "skill: ", "skill:\n", None, 0, True,
                ["free"], {"free": 1}, b"free"):
        with pytest.raises(ValueError, match="prompt_source"):
            render(prompt_source=bad)
    with pytest.raises(ValueError, match="non-empty text"):
        render(prompt_source="skill:summarize", skill_card_text=7)
    # free rows never state a card hash
    assert "skill_card_hash" not in render()["metadata"]


def test_a_skill_row_may_leave_the_card_hash_to_the_checkout():
    """The taskbank keeps the predecessor's architecture available: it
    resolved the card from the episode's own checkout (`gsj-envloader
    task.py:878-885`), not at submit. Stating `skill:<name>` without card
    text is legal and G1 fails closed until someone supplies the hash —
    so ADR-0003 can still choose sandbox-side resolution."""
    import gsj_rollout.checks as checks

    cfg = load_config(FIXTURE)
    rendered = render_task_request(cfg, task_id="t", instruction="i", case_id="c",
                                   timestep=1, prompt_source="skill:summarize")
    assert rendered["metadata"]["prompt_source"] == "skill:summarize"
    assert "skill_card_hash" not in rendered["metadata"]
    assert checks.check_skill_card({"metadata": rendered["metadata"]}) == [
        "G1:missing_evidence:skill_card_hash"]


# --- CP-14 (ADR-0015): the split into TaskRequest.metadata ----------------


def test_split_rides_task_metadata_when_stated():
    """The CP-11-proven channel: `metadata.split` is hoisted into every
    trace's top-level metadata, beside case_id/timestep/prompt_source.
    A parameter like `prompt_source` — the config surface grows no corpus
    dependency; the taskbank supplies the value from the lock (ADR-0003)."""
    cfg = load_config(FIXTURE)
    rendered = render_task_request(cfg, task_id="t", instruction="i",
                                   case_id="case_0004", timestep=13,
                                   split="eval")
    assert rendered["metadata"] == {
        "case_id": "case_0004", "timestep": 13,
        "prompt_source": "free", "split": "eval"}


def test_absent_split_means_unstated_never_train():
    """The frozen cli path cannot know the split; omitting the key states
    that honestly — a silent `train` default would be a false label."""
    cfg = load_config(FIXTURE)
    rendered = render_task_request(cfg, task_id="t", instruction="i",
                                   case_id="c", timestep=1)
    assert "split" not in rendered["metadata"]


def test_split_vocabulary_is_validated_at_render():
    cfg = load_config(FIXTURE)
    for bad in ("test", "TRAIN", "", 0, True, ["train"], b"eval"):
        with pytest.raises(ValueError, match="split must be 'train' or 'eval'"):
            render_task_request(cfg, task_id="t", instruction="i",
                                case_id="c", timestep=1, split=bad)


# --- CP-27: the strangerward validators (wishlist 21, 23; F-25, F-23) -----


def _write(tmp_path, doc, name="cfg.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc))
    return path


def test_serving_base_url_v1_suffix_rejected_at_load(tmp_path):
    """Wishlist 21(b): the suffixed form used to be accepted and fail at run
    time as a bare 404 on /v1/v1/… reading as a wrong host (CP-26 §3)."""
    doc = yaml.safe_load(FIXTURE.read_text())
    for trap in ("http://127.0.0.1:8021/v1", "http://127.0.0.1:8021/v1/"):
        doc["estate"]["serving_base_url"] = trap
        with pytest.raises(ValueError, match=r"serving_base_url.*must not end in /v1"):
            load_config(_write(tmp_path, doc))
    doc["estate"]["serving_base_url"] = "http://127.0.0.1:8021"  # the engine root
    assert load_config(_write(tmp_path, doc)).estate.serving_base_url == "http://127.0.0.1:8021"


def test_gateway_port_public_url_mismatch_rejected_at_load(tmp_path):
    """Wishlist 21(a): one fact, two keys — the mismatch used to surface as
    connection-refused on the advertised URL at the first dead submit."""
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["polar"]["gateway"]["public_url"] = "http://192.168.0.158:9100"  # port default: 8100
    with pytest.raises(ValueError, match=r"advertises port 9100 but the gateway "
                                         r"listens on port 8100"):
        load_config(_write(tmp_path, doc))
    # no explicit port advertises the scheme default — the same dead URL
    doc["polar"]["gateway"]["public_url"] = "http://192.168.0.158"
    with pytest.raises(ValueError, match=r"advertises port 80 but the gateway"):
        load_config(_write(tmp_path, doc))
    # agreement in BOTH keys is the accepted form, at any port
    doc["polar"]["gateway"]["public_url"] = "http://192.168.0.158:9100"
    doc["polar"]["gateway"]["port"] = 9100
    cfg = load_config(_write(tmp_path, doc))
    assert cfg.polar.gateway.port == 9100
    # a scheme-less URL parses port-less ("IP:8100" reads as path or as a
    # host-named scheme) — reject naming the REAL gap, never "port 80"
    doc["polar"]["gateway"]["public_url"] = "192.168.0.158:9100"
    with pytest.raises(ValueError, match=r"needs an explicit http:// or https://"):
        load_config(_write(tmp_path, doc))


def test_null_section_error_names_the_missing_fields(tmp_path):
    """F-25: a required line deleted whole leaves a comment-only section →
    YAML null → the old error was 'Input should be a valid dictionary'
    naming no field. It must name the section and what it needs."""
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["polar"]["gateway"] = None  # what `gateway:` + only comments parses to
    with pytest.raises(ValueError, match=r"'polar\.gateway\.public_url': Field required"):
        load_config(_write(tmp_path, doc))
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["estate"] = None  # a whole top-level section commented out
    with pytest.raises(ValueError, match=r"'estate\.clone_url_for': Field required"):
        load_config(_write(tmp_path, doc))
    # the dict-typed free section takes the same F-25 mutation shape: a
    # serve-only consumer gutting `user:` to its header must still load
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["user"] = None
    assert load_config(_write(tmp_path, doc)).user == {}


def test_model_revision_is_an_optional_in_band_pin(tmp_path):
    """F-23's config half (wishlist 23): the served snapshot's revision may
    travel with the config; absent means unpinned — stated, never guessed."""
    assert load_config(FIXTURE).estate.model_revision is None
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["estate"]["model_revision"] = "c1899de289a04d12100db370d81485cdf75e47ca"
    cfg = load_config(_write(tmp_path, doc))
    assert cfg.estate.model_revision == "c1899de289a04d12100db370d81485cdf75e47ca"


def test_checks_config_mirrors_check_policy_completely():
    """Step 2's teeth: every `CheckPolicy` field has a `ChecksConfig`
    counterpart with the same default (and nothing extra), so the CP-11b
    H-41 mirror drift cannot recur silently."""
    import dataclasses

    import gsj_rollout.checks as checks
    from gsj_rollout.config import ChecksConfig

    policy = {field.name: field.default for field in dataclasses.fields(checks.CheckPolicy)}
    mirror = {name: field.default for name, field in ChecksConfig.model_fields.items()}
    assert mirror == policy


def test_h41_knob_is_reachable_from_the_one_yaml(tmp_path, monkeypatch):
    """CP-11b's declared drift, closed: arming H-41 is one YAML line."""
    import gsj_rollout.checks as checks

    monkeypatch.setattr(checks, "DEFAULT_POLICY", checks.DEFAULT_POLICY)  # register restore
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["checks"] = {"reject_toolless_roster": True}
    path = tmp_path / "armed.yaml"
    path.write_text(yaml.safe_dump(doc))
    cfg = load_config(path)
    assert cfg.checks.reject_toolless_roster is True
    assert checks.DEFAULT_POLICY == checks.CheckPolicy(reject_toolless_roster=True)


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


# --- CP-30 (ADR-0024): the thinking knob --------------------------------


def test_thinking_accepts_every_pi_level(tmp_path):
    """ADR-0024: the knob's whole domain — pi's own levels — loads and
    rides the rendered TaskRequest verbatim (`pi_harness` forwards it as
    `--thinking <level>` unchanged; CP-28 measured the full path)."""
    doc = yaml.safe_load(FIXTURE.read_text())
    for level in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
        doc["harness"]["thinking"] = level
        cfg = load_config(_write(tmp_path, doc))
        assert cfg.harness.thinking == level
        rendered = render_task_request(cfg, task_id="t", instruction="i",
                                       case_id="c", timestep=1)
        assert rendered["agent"]["settings"]["thinking"] == level


def test_thinking_pi_clamped_values_rejected_at_load(tmp_path):
    """The CP-28 silent clamp: pi maps anything off its level list to
    "off" with no error, so a typo collects a control run wearing the
    measurement's label. Reject at load, naming the levels and the
    hazard (CP-27's message standard)."""
    doc = yaml.safe_load(FIXTURE.read_text())
    for trap in ("on", "true", "enabled", "OFF", "Medium", ""):
        doc["harness"]["thinking"] = trap
        with pytest.raises(ValueError,
                           match=r"'harness\.thinking'.*not a pi thinking level"
                                 r".*off\|minimal\|low\|medium\|high\|xhigh\|max"
                                 r".*silently clamps"):
            load_config(_write(tmp_path, doc))


def test_thinking_yaml11_bare_spellings(tmp_path):
    """pyyaml is YAML 1.1: bare `off`/`on` parse as booleans before pydantic
    ever sees them. The natural spelling `thinking: off` must keep meaning
    off, and bare `on` — exactly the clamp typo — must get the clamp
    rejection, not a bare 'Input should be a valid string' naming no level."""
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["harness"]["thinking"] = False   # what bare `off`/`no` parse to
    assert load_config(_write(tmp_path, doc)).harness.thinking == "off"
    doc["harness"]["thinking"] = True    # what bare `on`/`yes`/`true` parse to
    with pytest.raises(ValueError, match=r"'harness\.thinking'.*silently clamps"):
        load_config(_write(tmp_path, doc))
