"""CP-84 B05: synthetic credentials only; producer boundaries agree with readers."""

from __future__ import annotations

import argparse
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest

ESTATE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ESTATE_DIR))
import estate as est  # noqa: E402
from gsj_rollout.config import _named_value  # noqa: E402
from gsj_rollout import cli  # noqa: E402

SYNTHETIC_ENV = "CP84_SYNTHETIC_CREDENTIAL"
UNSUPPORTED = [
    ("apostrophe", "synthetic'only", "apostrophe"),
    ("vertical-tab", "synthetic\vonly", "control"),
    ("line-separator", "synthetic\u2028only", "non-ASCII"),
    ("paragraph-separator", "synthetic\u2029only", "non-ASCII"),
    ("carriage-return", "synthetic\ronly", "control"),
    ("newline", "synthetic\nonly", "control"),
    ("tab", "synthetic\tonly", "control"),
    ("nul", "synthetic\0only", "control"),
    ("del", "synthetic\x7fonly", "control"),
    ("non-ascii", "synthetic\u00e9only", "non-ASCII"),
    ("odd-backslash", "synthetic\\", "trailing backslash"),
    ("three-backslashes", "synthetic\\\\\\", "trailing backslash"),
]
SUPPORTED = ["".join(chr(i) for i in range(32, 127) if i != 39),
             " leading and trailing ", " ", r"synthetic\n\t\$HOME", "synthetic\\\\",
             '$HOME ${CP84_DO_NOT_EXPAND:-no} `uname` "double" #hash = ; %',
             "synthetic\\ "]


def refusal(capsys, expected_class):
    output = capsys.readouterr().err
    assert "REFUSED" in output and expected_class in output
    assert "found:" in output and "expected:" in output and "what to do:" in output
    assert "rotate" in output and "token" in output
    assert "synthetic" not in output  # the refusal names the class, never the value


@pytest.mark.parametrize("label,value,expected_class", UNSUPPORTED, ids=[v[0] for v in UNSUPPORTED])
def test_writer_refuses_before_replacing_env(tmp_path, monkeypatch, capsys,
                                            label, value, expected_class):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("credential-canary")
    run.env = {SYNTHETIC_ENV: "safe-before-probe"}
    run.write_env()
    env_file = run.dir / ".env"
    before = env_file.read_bytes()
    run.env[SYNTHETIC_ENV] = value
    with pytest.raises(SystemExit) as exc:
        run.write_env()
    assert exc.value.code == 1
    refusal(capsys, expected_class)
    assert env_file.read_bytes() == before


@pytest.mark.parametrize("source", ["env", "file", "prompt", "fallback"])
@pytest.mark.parametrize("value,expected_class", [
    ("synthetic'only", "apostrophe"), ("synthetic\v", "control"),
    ("synthetic\u2028", "non-ASCII"), ("synthetic\\", "trailing backslash")])
def test_adopt_refuses_before_returning_secret(tmp_path, monkeypatch, capsys,
                                              source, value, expected_class):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    args = argparse.Namespace(answers=None, defaults=source != "prompt", credential_file=None)
    answers = est.Answers(args)
    fallback = None
    if source == "env":
        monkeypatch.setenv(SYNTHETIC_ENV, value)
    elif source == "file":
        path = tmp_path / "credential.txt"
        path.write_text(value)
        path.chmod(0o600)
        args.credential_file = str(path)
    elif source == "prompt":
        answers.interactive = True
        monkeypatch.setattr(est.getpass, "getpass", lambda _: value)
    else:
        fallback = value
    with pytest.raises(SystemExit) as exc:
        answers.secret("synthetic credential", env=SYNTHETIC_ENV,
                       file_key="credential_file", fallback=fallback)
    assert exc.value.code == 1
    refusal(capsys, expected_class)


@pytest.mark.parametrize("source", ["env", "file", "prompt", "fallback"])
def test_adopt_preserves_significant_spaces(tmp_path, monkeypatch, source):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    value = " synthetic credential " + "\\" + " "
    args = argparse.Namespace(answers=None, defaults=source != "prompt", credential_file=None)
    answers = est.Answers(args)
    fallback = None
    if source == "env":
        monkeypatch.setenv(SYNTHETIC_ENV, value)
    elif source == "file":
        path = tmp_path / "credential.txt"
        path.write_text(value)
        args.credential_file = str(path)
    elif source == "prompt":
        answers.interactive = True
        monkeypatch.setattr(est.getpass, "getpass", lambda _: value)
    else:
        fallback = value
    assert answers.secret("synthetic credential", env=SYNTHETIC_ENV,
                          file_key="credential_file", fallback=fallback) == value


@pytest.mark.parametrize("terminator", ["", "\n"])
def test_secret_file_allows_one_lf_framing_without_trimming_spaces(tmp_path, monkeypatch, terminator):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    path = tmp_path / "credential.txt"
    path.write_bytes((" synthetic " + terminator).encode())
    args = argparse.Namespace(answers=None, defaults=True, credential_file=str(path))
    assert est.Answers(args).secret("credential", env=SYNTHETIC_ENV,
                                   file_key="credential_file") == " synthetic "


@pytest.mark.parametrize("terminator", ["\r\n", "\n\n", "\r", "\v", "\u2028"])
def test_secret_file_rejects_other_framing(tmp_path, monkeypatch, capsys, terminator):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    path = tmp_path / "credential.txt"
    path.write_bytes(("synthetic" + terminator).encode())
    args = argparse.Namespace(answers=None, defaults=True, credential_file=str(path))
    with pytest.raises(SystemExit) as exc:
        est.Answers(args).secret("credential", env=SYNTHETIC_ENV, file_key="credential_file")
    assert exc.value.code == 1
    refusal(capsys, "non-ASCII" if terminator == "\u2028" else "control")


def test_secret_file_refuses_undecodable_bytes_without_exposing_them(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    path = tmp_path / "credential.txt"
    path.write_bytes(b"synthetic\xffonly")
    args = argparse.Namespace(answers=None, defaults=True, credential_file=str(path))
    with pytest.raises(SystemExit) as exc:
        est.Answers(args).secret("credential", env=SYNTHETIC_ENV, file_key="credential_file")
    assert exc.value.code == 1
    refusal(capsys, "non-ASCII")


@pytest.mark.parametrize("value,expected_class", [("synthetic'only", "apostrophe"),
                                                  ("synthetic\vonly", "control"),
                                                  ("synthetic\u2028only", "non-ASCII")])
def test_minted_token_refused_before_authentication(monkeypatch, capsys, value, expected_class):
    forgejo = est.Forgejo("http://127.0.0.1:9", "http://127.0.0.1:9",
                          ("synthetic-admin", "synthetic-password"), "adopted")
    monkeypatch.setattr(forgejo, "api", lambda *a, **k: (201, {"sha1": value}))
    with pytest.raises(SystemExit) as exc:
        forgejo.mint_token("synthetic-owner", "read", ["read:repository"])
    assert exc.value.code == 1
    refusal(capsys, expected_class)


@pytest.mark.parametrize("value,expected_class", [("synthetic'only", "apostrophe"),
                                                  ("synthetic\vonly", "control"),
                                                  ("synthetic\u2028only", "non-ASCII")])
def test_legacy_env_refuses_before_truncating(tmp_path, monkeypatch, capsys, value, expected_class):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("credential-canary")
    run.dir.mkdir()
    env_file = run.dir / ".env"
    # The old writer's exact encoding is a legacy-input fixture, never new output.
    env_file.write_text(f"{SYNTHETIC_ENV}=" + "'" + value.replace("'", "'\\''") + "'\n")
    before = env_file.read_bytes()
    with pytest.raises(SystemExit) as exc:
        run.load()
    assert exc.value.code == 1
    refusal(capsys, expected_class)
    assert run.env == {} and env_file.read_bytes() == before


@pytest.mark.parametrize("value", SUPPORTED)
def test_supported_writer_loader_core_and_shell_agree(tmp_path, monkeypatch, value):
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("credential-canary")
    run.env[SYNTHETIC_ENV] = value
    run.write_env()
    loaded = est.Run(run.name)
    loaded.load()
    assert loaded.env == run.env
    assert (run.dir / ".env").stat().st_mode & 0o777 == 0o600
    cfg = argparse.Namespace(_env_file=run.dir / ".env")
    assert _named_value(cfg, "synthetic credential", SYNTHETIC_ENV) == value
    shell = subprocess.run(["/bin/sh", "-c", "set -a; . \"$1\"; \"$2\" -c "
                            "'import json,os; print(json.dumps(os.environ[\"CP84_SYNTHETIC_CREDENTIAL\"]))'",
                            "credential-probe", str(run.dir / ".env"), sys.executable],
                           capture_output=True, text=True, timeout=10)
    assert shell.returncode == 0, shell.stderr
    assert json.loads(shell.stdout) == value


def test_empty_unrelated_env_entries_remain_absence(tmp_path, monkeypatch):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("credential-canary")
    run.dir.mkdir()
    (run.dir / ".env").write_text("EMPTY=\nQUOTED_EMPTY=''\nCP84_SYNTHETIC_CREDENTIAL='valid'\n")
    run.load()
    assert run.env == {"EMPTY": "", "QUOTED_EMPTY": "", SYNTHETIC_ENV: "valid"}
    run.write_env()
    reloaded = est.Run(run.name)
    reloaded.load()
    assert reloaded.env == run.env


def test_supported_credential_reaches_real_submit_transport(tmp_path, monkeypatch):
    """An HTTP sink observes exact request bytes; its 503 is not an accepted episode."""
    monkeypatch.delenv(SYNTHETIC_ENV, raising=False)
    monkeypatch.setattr(est, "RUNS", tmp_path)
    value = SUPPORTED[0] + " \\\\"
    run = est.Run("credential-submit")
    run.env = {SYNTHETIC_ENV: value}
    run.write_env()
    observed = []

    class Sink(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            observed.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(503)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Sink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = run.dir / "rollout.yaml"
    path.write_text(est.yaml.safe_dump({
        "estate": {"clone_url_for": "http://git.invalid/synthetic/{case_id}.git",
                   "clone_credential_env": SYNTHETIC_ENV, "mcp_url_base": "http://mcp.invalid:8790",
                   "serving_base_url": "http://127.0.0.1:9", "model": "synthetic"},
        "polar": {"gateway": {"public_url": "http://127.0.0.1:8100"},
                  "rollout": {"port": server.server_port}},
        "receiver": {"traces_dir": str(run.dir / "traces")}}))
    args = argparse.Namespace(config=str(path), from_bank=None, case="synthetic-case", timestep=1,
                              prompt="synthetic input", prompt_file=None, task_id="credential-probe",
                              episodes=1, timeout=1, grace=0, poll_interval=0.01, out=None)
    try:
        assert cli.submit(args) == cli.EXIT_UNREACHABLE
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(observed) == 1
    assert observed[0]["agent"]["settings"]["clone_url_for"] == (
        "http://" + value + "@git.invalid/synthetic/{case_id}.git")


def test_real_compose_parses_supported_character_contexts(tmp_path, monkeypatch):
    """No daemon/image/container needed; actual Go dotenv parser, not a Python mirror."""
    if not shutil.which("docker"):
        pytest.skip("real Docker Compose CLI unavailable")
    env = {"PATH": os.environ["PATH"]}  # never capture the operator's secret environment
    version = subprocess.run(["docker", "compose", "version"], capture_output=True,
                             text=True, env=env, timeout=10)
    if version.returncode:
        pytest.skip("real Docker Compose plugin unavailable")
    monkeypatch.setattr(est, "RUNS", tmp_path)
    run = est.Run("credential-compose")
    samples = list(SUPPORTED)
    for i in range(32, 127):
        if i != 39:
            char = chr(i)
            samples.extend([char + "synthetic", "synthetic" + char + "end"])
            if i != 92:
                samples.extend(["synthetic" + char, "synthetic\\" + char])
    samples.extend("synthetic" + "\\" * count for count in (2, 4, 6))
    run.env = {f"CP84_{i}": value for i, value in enumerate(samples)}
    run.write_env()
    compose_file = run.dir / "compose.yaml"
    compose_file.write_text(est.yaml.safe_dump({"services": {"probe": {
        "image": "alpine:3.20", "environment": {
            key: "${" + key + ":?required}" for key in run.env}}}}))
    argv = ["docker", "compose", "--env-file", str(run.dir / ".env"), "-f",
            str(compose_file), "config"]
    quiet = subprocess.run(argv + ["-q"], capture_output=True, text=True, env=env, timeout=10)
    assert quiet.returncode == 0, quiet.stderr
    rendered = subprocess.run(argv + ["--environment"], capture_output=True,
                              text=True, env=env, timeout=10)
    assert rendered.returncode == 0, rendered.stderr
    composed = dict(line.partition("=")[::2] for line in rendered.stdout.split("\n")
                    if line.startswith("CP84_"))
    assert composed == run.env
