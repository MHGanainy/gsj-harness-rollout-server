"""CP-84 B04: keyed refusals precede Docker and preserve config precedence.

The subprocess canary's `docker` executable only records argv and exits.
Every corpus, override, run path, and call log belongs to pytest's tmp_path;
no real container, daemon, model, or credential is used by these tests.
"""

from __future__ import annotations

import argparse
import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import make_corpus

ESTATE_PY = Path(__file__).resolve().parents[2] / "estate.py"
sys.path.insert(0, str(ESTATE_PY.parent))
import estate as est  # noqa: E402


B04 = (
    ("search", "method", "exact", "chroma"),
    ("embedding", "normalize", False, "true"),
    ("embedding", "batch_size", 0, "at least 1"),
    ("search", "default_k", 0, "at least 1"),
    ("chunking", "respect_page_boundaries", False, "true"),
    ("chunking", "max_tokens", 15, "at least 16"),
    ("decisions", "corpus_size", 0, "at least 1"),
    ("embedding", "revision", "main", "commit"),
    ("embedding", "model", "not a model id", "HF model id"),
)


def run_without_docker(tmp_path, *flags):
    corpus = make_corpus(tmp_path / "corpus", estate_fields=False)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CP84_DOCKER_CALLS"\nexit 97\n')
    docker.chmod(0o700)
    calls = tmp_path / "docker-calls"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GSJ_") and not key.startswith("CP84_")}
    env.update(PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
               CP84_DOCKER_CALLS=str(calls), PYTHONDONTWRITEBYTECODE="1")
    runs = tmp_path / "runs"
    proc = subprocess.run(
        [sys.executable, str(ESTATE_PY), "up", "-y", "--corpus", str(corpus),
         "--runs-dir", str(runs), "--name", "mcp-boundary", *flags],
        env=env, text=True, capture_output=True, timeout=20)
    return proc, calls, runs / "mcp-boundary"


def assert_early_refusal(proc, calls, run_dir, key, cure):
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "REFUSED" in proc.stderr and key in proc.stderr, proc.stderr
    for label in ("found:", "expected:", "what to do:", cure):
        assert label in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr
    assert not calls.exists(), calls.read_text() if calls.exists() else ""
    assert not run_dir.exists(), list(run_dir.iterdir()) if run_dir.exists() else []


@pytest.mark.parametrize("section,key,value,cure", B04,
                         ids=[f"{section}.{key}" for section, key, *_ in B04])
def test_nine_audit_probes_refuse_before_any_docker_call(tmp_path, section, key, value, cure):
    config = tmp_path / "override.yaml"
    config.write_text(yaml.safe_dump({section: {key: value}}))
    proc, calls, run_dir = run_without_docker(tmp_path, "--mcp-config", str(config))
    assert_early_refusal(proc, calls, run_dir, f"{section}.{key}", cure)
    assert str(config) in proc.stderr


@pytest.mark.parametrize("body", ["false\n", "0\n", "[]\n", "''\n"])
def test_false_yaml_roots_are_refused_instead_of_clearing_overrides(tmp_path, body):
    config = tmp_path / "override.yaml"
    config.write_text(body)
    proc, calls, run_dir = run_without_docker(tmp_path, "--mcp-config", str(config))
    assert_early_refusal(proc, calls, run_dir, str(config), "mapping")


@pytest.mark.parametrize("body", ["", "# deliberately clear residuals\n", "{}\n"])
def test_empty_override_document_still_clears_residuals(tmp_path, body):
    config = tmp_path / "empty.yaml"
    config.write_text(body)
    assert est.load_mcp_overrides(str(config)) == {}
    assert est.load_mcp_overrides(None) is None


@pytest.mark.parametrize("flags,key,cure", [
    (("--chunk-max-tokens", "15"), "chunking.max_tokens", "at least 16"),
    (("--chunk-overlap", "-1"), "chunking.overlap", "at least 0"),
    (("--chunk-max-tokens", "16"), "chunking.overlap", "lower chunking.overlap"),
    (("--chunk-overlap", "220"), "chunking.overlap", "lower chunking.overlap"),
    (("--embedding-revision", "main"), "embedding.revision", "commit"),
    (("--embedding-model", "bad model", "--embedding-revision", "a" * 40),
     "embedding.model", "HF model id"),
])
def test_effective_flag_values_refuse_before_any_docker_call(tmp_path, flags, key, cure):
    proc, calls, run_dir = run_without_docker(tmp_path, *flags)
    assert_early_refusal(proc, calls, run_dir, key, cure)


@pytest.mark.parametrize("key,value", [("chunk_max_tokens", 220.75),
                                      ("chunk_overlap", 40.75),
                                      ("chunk_overlap", False)])
def test_answers_do_not_silently_truncate_float_or_boolean_chunk_values(tmp_path, key, value):
    answers = tmp_path / "answers.yaml"
    answers.write_text(yaml.safe_dump({key: value}))
    proc, calls, run_dir = run_without_docker(tmp_path, "--answers", str(answers))
    dotted = "chunking.max_tokens" if key == "chunk_max_tokens" else "chunking.overlap"
    assert_early_refusal(proc, calls, run_dir, dotted, "int")


def answers(**values):
    return est.Answers(argparse.Namespace(answers=None, defaults=True, **values))


def previous_run(residual=None):
    return {
        "mcp": {"mode": "created", "embedding": {
            "model": "previous/model", "revision": "1" * 40}},
        "compose": {"mcp": {"chunking": {"max_tokens": 200, "overlap": 20},
                              "config_overrides": residual or {}}},
    }


def test_override_file_beats_record_and_flags_beat_override_file(tmp_path):
    config = tmp_path / "overrides.yaml"
    config.write_text(yaml.safe_dump({
        "embedding": {"model": "file/model", "revision": "2" * 40, "batch_size": 64},
        "chunking": {"max_tokens": 100, "overlap": 10}, "search": {"default_k": 8}}))
    previous = previous_run({"search": {"max_k": 99}})
    from_file = est.mcp_config_inputs(answers(mcp_config=str(config)), previous)
    assert (from_file["model"], from_file["revision"], from_file["chunk_max"],
            from_file["chunk_overlap"]) == ("file/model", "2" * 40, 100, 10)
    assert from_file["residual"] == {"embedding": {"batch_size": 64},
                                    "search": {"default_k": 8}}
    from_flags = est.mcp_config_inputs(answers(mcp_config=str(config),
        embedding_model="flag/model", embedding_revision="3" * 40,
        chunk_max_tokens=96, chunk_overlap=8), previous)
    assert (from_flags["model"], from_flags["revision"], from_flags["chunk_max"],
            from_flags["chunk_overlap"]) == ("flag/model", "3" * 40, 96, 8)
    assert from_flags["residual"] == from_file["residual"]


def test_plain_rerun_keeps_recorded_residuals_but_empty_file_clears_them(tmp_path):
    residual = {"embedding": {"device": "cpu", "batch_size": 64},
                "search": {"default_k": 8, "max_k": 17},
                "decisions": {"seed": 20260205, "corpus_size": 37}}
    previous = previous_run(residual)
    before = copy.deepcopy(previous)
    kept = est.mcp_config_inputs(answers(), previous)
    assert (kept["model"], kept["revision"], kept["chunk_max"], kept["chunk_overlap"]) \
        == ("previous/model", "1" * 40, 200, 20)
    assert kept["residual"] == residual
    empty = tmp_path / "empty.yaml"
    empty.write_text("{}\n")
    cleared = est.mcp_config_inputs(answers(mcp_config=str(empty)), previous)
    assert cleared["residual"] == {}
    assert (cleared["model"], cleared["revision"], cleared["chunk_max"],
            cleared["chunk_overlap"]) == ("previous/model", "1" * 40, 200, 20)
    assert previous == before


def test_partial_window_override_is_checked_after_flag_merge(tmp_path):
    config = tmp_path / "window.yaml"
    config.write_text("chunking:\n  max_tokens: 16\n")
    selected = est.mcp_config_inputs(answers(mcp_config=str(config), chunk_overlap=15), {})
    assert (selected["chunk_max"], selected["chunk_overlap"]) == (16, 15)
    with pytest.raises(SystemExit):
        est.mcp_config_inputs(answers(mcp_config=str(config)), {})


def test_cli_can_repair_a_file_window_relationship_before_effective_validation(tmp_path):
    config = tmp_path / "window.yaml"
    config.write_text("chunking:\n  max_tokens: 16\n  overlap: 40\n")
    selected = est.mcp_config_inputs(answers(mcp_config=str(config), chunk_max_tokens=64), {})
    assert (selected["chunk_max"], selected["chunk_overlap"]) == (64, 40)


@pytest.mark.parametrize("maximum,overlap", [("220", "40"), ("+220", "+40"),
                                           ("220", "-0")])
def test_numeric_string_answers_keep_the_existing_integer_contract(maximum, overlap):
    selected = est.mcp_config_inputs(answers(chunk_max_tokens=maximum, chunk_overlap=overlap), {})
    assert selected["chunk_max"] == 220 and selected["chunk_overlap"] == int(overlap)


def test_bad_recorded_residuals_refuse_with_replacement_remedy(capsys):
    with pytest.raises(SystemExit):
        est.mcp_config_inputs(answers(), previous_run({"search": {"method": "exact"}}))
    error = capsys.readouterr().err
    assert "search.method" in error and "chroma" in error
    assert "--mcp-config" in error and "empty file clears" in error


@pytest.mark.parametrize("section,key,value", [
    ("embedding", "model", "other/model"),
    ("embedding", "revision", "2" * 40),
    ("chunking", "max_tokens", 64),
    ("chunking", "overlap", 10),
])
def test_corrupted_residual_cannot_override_separately_bound_answers(capsys, section, key, value):
    with pytest.raises(SystemExit):
        est.mcp_config_inputs(answers(), previous_run({section: {key: value}}))
    error = capsys.readouterr().err
    assert f"config_overrides.{section}.{key}" in error
    assert "--mcp-config" in error and "empty file clears" in error
    assert "found:" in error and "expected:" in error and "what to do:" in error


def test_review_names_every_setting_and_its_consequence(tmp_path):
    doc = yaml.safe_load(est.MCP_CONFIG.format(
        prog="test", run="review", forgejo_url="http://localhost:1", owner="owner",
        repos="case_one", read_env="READ", model=est.DEFAULT_EMBEDDING_MODEL,
        revision=est.DEFAULT_EMBEDDING_REVISION, chunk_max=220, chunk_overlap=40,
        rebuild="if-stale", secret_env="SECRET"))
    review = est.mcp_config_review(doc, tmp_path / "mcp-config.yaml")
    for section, fields in est.MCP_FIELDS.items():
        for key, field in fields.items():
            assert f"{section}.{key}" in review
            assert est.MCP_CONSEQUENCES[field["consequence"]].format(
                cfg_path=tmp_path / "mcp-config.yaml") in review
    for consequence in ("REFUSED against the built store until --rebuild",
                        "re-embed of the WHOLE corpus", "serving-only",
                        "speed only, not identity", "decisions collection alone"):
        assert consequence in review
    assert "32" in review and "absent when 32" in review


def test_review_keeps_unknown_drop_count_when_the_host_path_is_absent(tmp_path):
    review = est.mcp_config_review({"decisions": {"path": "/app/decisions"}},
                                   tmp_path / "config.yaml", str(tmp_path / "absent"))
    assert "?" in review and "rii-dok" in review
