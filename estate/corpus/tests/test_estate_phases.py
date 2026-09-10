"""The shared phase boundary, measured through the real file:// pipeline.

The invocation seam tests return an opaque sentinel or raise; they do not
invent external CLI exit codes/streams (CHARTER section 8 rule 10).
"""

from __future__ import annotations

import importlib.util
from dataclasses import asdict, fields
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ingest_corpus as ic
from test_decisions import copy_fixture
from test_verify import run_all_local


@pytest.fixture
def est():
    path = Path(__file__).resolve().parents[2] / "estate.py"
    spec = importlib.util.spec_from_file_location("estate_phases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_invocation_keeps_credentials_local_and_reads_them_each_time(
        est, monkeypatch, tmp_path):
    monkeypatch.setenv("GSJ_FORGEJO_TOKEN_OWNER", "ambient")
    monkeypatch.setenv("AMBIENT_OTHER", "inherited")
    before, cwd = dict(os.environ), Path.cwd()
    run_env = {"GSJ_FORGEJO_TOKEN_OWNER": "first",
               "GSJ_FORGEJO_READ_TOKEN_OWNER": "reader",
               est.MCP_SECRET_ENV: "secret", "RUN_ONLY_OTHER": "excluded"}
    seen, result = [], object()

    def record(cmd, env, phase, **kw):
        seen.append((cmd, env, phase, kw))
        return result

    monkeypatch.setattr(est, "run_phase", record)
    args = dict(corpus_path=tmp_path, base_url="file:///bare",
                sandbox_image="example.invalid/harness:1", ingest_timeout=37.5,
                owner_override="owner", run_env=run_env,
                credential_names=("GSJ_FORGEJO_TOKEN_OWNER",
                                  "GSJ_FORGEJO_READ_TOKEN_OWNER"))
    assert est._run_corpus_phase("scaffold", "--only", "case_a", **args) is result
    run_env["GSJ_FORGEJO_TOKEN_OWNER"] = "second"
    assert est._run_corpus_phase("verify", **args, mcp_url="http://mcp.invalid") is result
    assert seen[0][0] == [sys.executable, str(est.INGEST), "scaffold", "--corpus",
                          str(tmp_path), "--base-url", "file:///bare", "--sandbox-image",
                          "example.invalid/harness:1", "--ingest-timeout", "37.5",
                          "--owner-override", "owner", "--only", "case_a"]
    assert seen[1][0][-4:] == ["--mcp-url", "http://mcp.invalid", "--owner-override", "owner"]
    assert [call[1]["GSJ_FORGEJO_TOKEN_OWNER"] for call in seen] == ["first", "second"]
    for cmd, env, phase, kw in seen:
        assert env["GSJ_FORGEJO_READ_TOKEN_OWNER"] == "reader"
        assert env[est.MCP_SECRET_ENV] == "secret"
        assert env["AMBIENT_OTHER"] == "inherited" and "RUN_ONLY_OTHER" not in env
        assert env["GSJ_PIPELINE_DRIVER"] == "estate" and kw == {}
        assert all(value not in cmd for value in ("first", "second", "reader", "secret"))
    assert dict(os.environ) == before and Path.cwd() == cwd


@pytest.mark.parametrize("error", [OSError("cannot start"), KeyboardInterrupt(),
                                    subprocess.TimeoutExpired("phase", 1)])
def test_shared_invocation_does_not_catch_child_boundary_exceptions(est, monkeypatch, error):
    def fail(*args, **kw):
        raise error

    monkeypatch.setattr(est, "run_phase", fail)
    with pytest.raises(type(error)) as caught:
        est._run_corpus_phase("verify", corpus_path=Path.cwd(), base_url="file:///bare",
                              sandbox_image="example.invalid/harness:1", ingest_timeout=1,
                              owner_override=None, run_env={}, credential_names=("PUSH", "READ"))
    assert caught.value is error


@pytest.mark.parametrize("shape", ["skip", "unnamed", "only", "missing_bank", "missing_lock",
                                    "marker_path"])
def test_real_child_retains_raw_result_and_the_established_estate_display(
        est, corpus_root, estate, monkeypatch, capsys, shape):
    if shape == "marker_path":
        corpus_root = corpus_root.rename(corpus_root.with_name("corpus  SKIPPED (compat)"))
    copy_fixture(corpus_root)
    run_all_local(corpus_root, estate)
    capsys.readouterr()
    cmd = [sys.executable, str(est.INGEST), "verify", "--corpus", str(corpus_root),
           "--base-url", estate]
    if shape != "unnamed":
        cmd += ["--skip-ingest"]
    if shape == "only":
        cmd += ["--only", "case_a"]
    if shape in ("missing_bank", "missing_lock", "marker_path"):
        (corpus_root / (ic.LOCK_NAME if shape == "missing_lock" else ic.TASKBANK_NAME)).unlink()
    standalone_env = {key: value for key, value in os.environ.items()
                      if key != "GSJ_PIPELINE_DRIVER"}
    standalone = subprocess.run(cmd, env=standalone_env, text=True, capture_output=True)
    expected = est.verify_headline(standalone.stdout)
    # Measure the real CLI's notice: ordinary standalone emits it, while
    # GSJ_PIPELINE_DRIVER has suppressed it since CP-72. Other stderr stays.
    notice = subprocess.run([sys.executable, str(est.INGEST), "--help"],
                            env=standalone_env, text=True, capture_output=True)
    assert notice.returncode == 0
    assert notice.stderr.startswith("NOTICE: this entry point is deprecated (CP-72)")
    assert standalone.stderr.startswith(notice.stderr)

    child = est.run_phase(cmd, {**standalone_env, "GSJ_PIPELINE_DRIVER": "estate"},
                          "verify")
    out, err = capsys.readouterr()
    assert child.returncode == standalone.returncode == {
        "missing_bank": 1, "missing_lock": 2, "marker_path": 1}.get(shape, 0)
    assert child.stdout == standalone.stdout and out == expected
    if shape == "marker_path":
        # Retain the legacy display oddity: the path adds a third displayed
        # skip beside the two actual MCP skips (corpus and decisions).
        assert " / 3 skipped / 1 fail) ==" in out
    assert child.stderr == err == standalone.stderr[len(notice.stderr):]


def test_private_verification_result_keeps_the_public_finding_shape():
    findings = [
        ic.Finding("case", "check", True, "  SKIPPED (ordinary prose)"),
        ic.Finding("case", "check", False, "failed")]
    result = ic._VerificationResult(findings)
    assert result.findings is findings and result.exit_code == 1
    assert [field.name for field in fields(findings[0])] == ["scope", "where", "ok", "detail", "split"]
    assert asdict(findings[1]) == {"scope": "case", "where": "check", "ok": False,
                                  "detail": "failed", "split": "-"}
    assert repr(findings[1]) == "Finding(scope='case', where='check', ok=False, detail='failed', split='-')"
