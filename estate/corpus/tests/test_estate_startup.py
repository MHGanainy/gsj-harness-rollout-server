"""CP-83 phase 1: startup failures are distinct from a slow live index.

Only disposable corpus/run fixtures and simulated Docker observations are
used here; the installed-wheel/live-estate proof is recorded separately.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_corpus

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import estate as est  # noqa: E402


def test_checkout_and_published_defaults_support_decisions():
    assert est.MCP_IMAGE == "gsj-mcp-service:0.5.0"
    assert est.MCP_IMAGE_PUBLISHED == "ghcr.io/mhganainy/gsj-mcp-service:0.5.0"


@pytest.mark.parametrize("answers_file", [False, True])
def test_known_incompatible_drop_refuses_before_estate_work(tmp_path, monkeypatch, capsys,
                                                          answers_file):
    corpus = make_corpus(tmp_path / "corpus", estate_fields=False)
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "jb-fixture.xml").write_text("<fixture/>")
    monkeypatch.setattr(est, "RUNS", tmp_path / "runs")

    def spent_work():
        pytest.fail("incompatible image reached Docker setup")

    monkeypatch.setattr(est, "check_docker", spent_work)
    values = {"corpus": str(corpus), "name": "startup-canary", "mcp": "create",
              "mcp_image": "ghcr.io/mhganainy/gsj-mcp-service:0.4.1",
              "decisions_dir": str(drop)}
    if answers_file:
        answers = tmp_path / "answers.json"
        answers.write_text(json.dumps(values))
        args = argparse.Namespace(answers=str(answers), defaults=True)
    else:
        args = argparse.Namespace(answers=None, defaults=True, **values)
    with pytest.raises(SystemExit) as exc:
        est.cmd_up(args)
    assert exc.value.code == 1
    refusal = capsys.readouterr().err
    assert "0.4.1" in refusal and "0.5.0" in refusal
    assert "found:" in refusal and "expected:" in refusal and "what to do:" in refusal
    assert "--mcp-image" in refusal
    assert not (tmp_path / "runs" / "startup-canary" / ".env").exists()


@pytest.mark.parametrize("image", ["gsj-mcp-service:0.4.1-arm64",
                                    "ghcr.io/mhganainy/gsj-mcp-service:0.4.0"])
def test_known_local_and_registry_pre_decisions_tags_refuse(image, capsys):
    with pytest.raises(SystemExit):
        est.require_decisions_image(image, "/disposable/drop")
    assert "--mcp-image" in capsys.readouterr().err


@pytest.mark.parametrize("image,drop", [
    ("gsj-mcp-service:0.4.1", None),
    ("gsj-mcp-service:0.5.0", "/drop"),
    ("gsj-mcp-service:custom", "/drop"),
    ("registry.invalid/gsj-mcp-service:0.4.1", "/drop"),
    ("ghcr.io/mhganainy/gsj-mcp-service@sha256:" + "a" * 64, "/drop"),
])
def test_unidentified_custom_images_and_no_drop_remain_supported(image, drop):
    est.require_decisions_image(image, drop)


def waiting(monkeypatch, health, state=None, logs=""):
    clock = [100.0]
    monkeypatch.setattr(est.time, "time", lambda: clock[0])
    monkeypatch.setattr(est.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    mcp = est.Mcp("http://127.0.0.1:9", "http://mcp:8790", "fixture-secret", "created")
    readings = iter(health)
    monkeypatch.setattr(mcp, "health", lambda: next(readings, None))
    commands = []

    def docker(cmd, **kwargs):
        commands.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(state or {"Status": "running", "ExitCode": 0}), "")
        assert cmd[:2] == ["docker", "logs"]
        return subprocess.CompletedProcess(cmd, 0, logs, "")

    monkeypatch.setattr(est, "run", docker)
    return mcp, clock, commands


@pytest.mark.parametrize("status,exit_code", [("exited", 1), ("restarting", 1), ("dead", 137), ("exited", 0)])
def test_terminal_startup_refuses_without_indexing_cure(monkeypatch, capsys, status, exit_code):
    mcp, clock, commands = waiting(monkeypatch, [], {"Status": status, "ExitCode": exit_code},
                                   "ValidationError: ServiceConfig\ndecisions.path\nExtra inputs are not permitted")
    with pytest.raises(SystemExit) as exc:
        mcp.wait_ready(1800, "cold start", container="gsj-startup-canary-mcp")
    assert exc.value.code == 1
    assert clock[0] < 110  # a terminal process is not given the indexing budget
    refusal = capsys.readouterr().err
    assert "0.5.0" in refusal and "--mcp-image" in refusal
    assert "cpu" not in refusal.lower() and "keep waiting" not in refusal
    assert any(cmd[:2] == ["docker", "logs"] for cmd in commands)


def test_unknown_startup_exit_names_logs_and_config_not_cpu(monkeypatch, capsys):
    mcp, _, _ = waiting(monkeypatch, [], {"Status": "exited", "ExitCode": 2}, "permission denied")
    with pytest.raises(SystemExit):
        mcp.wait_ready(30, "start", container="gsj-startup-canary-mcp")
    refusal = capsys.readouterr().err
    assert "docker logs" in refusal and "mcp-config.yaml" in refusal
    assert "cpu" not in refusal.lower()


def test_running_emulated_sigsegv_keeps_cp59_cure(monkeypatch, capsys):
    mcp, clock, _ = waiting(monkeypatch, [], logs="fatal: signal 11")
    monkeypatch.setattr(est, "daemon_arch", lambda: "arm64")
    with pytest.raises(SystemExit):
        mcp.wait_ready(1800, "cold start", container="gsj-startup-canary-mcp")
    refusal = capsys.readouterr().err
    assert "signal 11" in refusal and "build the service natively" in refusal
    assert "--mcp-image" in refusal and clock[0] < 130


def test_real_index_progress_can_take_longer_than_silence_probe(monkeypatch, capsys):
    fetching = {"state": "indexing", "progress": {"case_a": {"done": True}}}
    embedded = {"state": "indexing", "progress": {"case_a": {"done": True, "embedded": True}}}
    ready = {"state": "ready", "progress": embedded["progress"]}
    mcp, clock, commands = waiting(monkeypatch, [fetching] * 12 + [embedded, ready])
    assert mcp.wait_ready(1800, "cold start", container="gsj-startup-canary-mcp") == ready
    assert clock[0] > 130 and not commands
    progress = capsys.readouterr().out
    assert "0/1 embedded" in progress and "1/1 embedded" in progress


def test_no_health_timeout_does_not_call_it_indexing(monkeypatch, capsys):
    mcp, _, _ = waiting(monkeypatch, [])
    with pytest.raises(SystemExit):
        mcp.wait_ready(6, "adopted service")
    refusal = capsys.readouterr().err
    assert "unreachable" in refusal and "cpu" not in refusal.lower()


def test_env_instructions_date_fallback_and_preserve_gateway_requirement(tmp_path, monkeypatch):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("instructions-canary")
    run.write_env()
    text = (run.dir / ".env").read_text()
    assert "since 0.1.7" in text
    assert "environment wins" in text
    assert "0.1.6" in text and "Historical" in text
    assert "serve_gateway" in text and "source it there" in text


def test_deprecated_alias_notice_keeps_its_documented_bound():
    proc = subprocess.run([sys.executable, str(est.INGEST), "--help"],
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "no earlier than 0.1.8" in proc.stderr
    assert "stays importable" in proc.stderr
