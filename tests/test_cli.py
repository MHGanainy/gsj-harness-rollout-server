"""CP-08 CLI tests: help, stated exit codes, bounded exit, embeddability."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, task_status

from gsj_rollout import cli

FIXTURE = Path(__file__).parent / "fixtures" / "rollout.yaml"


def _config_for(tmp_path, base_url: str) -> Path:
    doc = yaml.safe_load(FIXTURE.read_text())
    host, port = base_url.removeprefix("http://").split(":")
    doc["polar"]["rollout"] = {"host": host, "port": int(port)}
    doc["receiver"]["traces_dir"] = str(tmp_path / "traces")
    doc["receiver"]["port"] = 0  # never collide with a real port in tests
    path = tmp_path / "rollout.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_help_exits_zero(capsys):
    for argv in (["--help"], ["serve", "--help"], ["submit", "--help"]):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(argv)
        assert excinfo.value.code == 0
    assert "Collect-N semantics" in capsys.readouterr().out  # row 26, stated


def test_bad_config_exits_2(tmp_path, capsys):
    submit = ["submit", "--case", "case_0001", "--timestep", "12", "--prompt", "p"]
    assert cli.main(submit + ["--config", str(tmp_path / "missing.yaml")]) == 2
    bad = tmp_path / "bad.yaml"
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["estate"]["unknown_knob"] = 1
    bad.write_text(yaml.safe_dump(doc))
    assert cli.main(submit + ["--config", str(bad)]) == 2
    assert cli.main(["serve", "--config", str(bad), "--render-only"]) == 2
    assert "unknown key 'unknown_knob'" in capsys.readouterr().err
    broken = tmp_path / "broken.yaml"
    broken.write_text("estate: [unclosed")  # yaml.YAMLError, not ValueError
    assert cli.main(submit + ["--config", str(broken)]) == 2
    assert "invalid YAML" in capsys.readouterr().err


def test_unreachable_server_exits_3(tmp_path):
    config = _config_for(tmp_path, "http://127.0.0.1:1")  # nothing listens on port 1
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p"])
    assert code == 3


def test_reachable_but_erroring_server_exits_3(tmp_path, fake_rollout_factory):
    server = fake_rollout_factory([], submit_status=500)
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p"])
    assert code == 3  # an HTTP error is never conflated with exit 1's meaning


def test_rejected_episode_exits_1(tmp_path, fake_rollout_factory, callback_body, capsys):
    import copy

    errored = copy.deepcopy(callback_body)
    errored["session_id"] = "sk-polar-cli-errored"
    errored["status"] = "ERROR"
    server = fake_rollout_factory([task_status([errored])])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p", "--poll-interval", "0.02"])
    assert code == 1  # a consumed attempt that was not collected
    out = capsys.readouterr().out
    assert "rejected sk-polar-cli-errored" in out and "collected 0/1" in out


def test_bounded_exit_on_never_terminal_task(tmp_path, fake_rollout_factory):
    server = fake_rollout_factory([task_status([], status="running")])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p",
                     "--timeout", "0.3", "--grace", "0", "--poll-interval", "0.02"])
    assert code == 1  # terminal for us, not collected — never hangs


def test_submit_collects_and_writes_out(tmp_path, fake_rollout_factory, body13):
    server = fake_rollout_factory([task_status([body13])])
    config = _config_for(tmp_path, server.base_url)
    out = tmp_path / "collected"
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p", "--out", str(out),
                     "--poll-interval", "0.02"])
    assert code == 0
    assert (out / f"{body13['session_id']}.json").exists()


def test_serve_render_only(tmp_path, capsys):
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    rendered = tmp_path / "topology.rendered.yaml"
    assert rendered.exists()
    assert yaml.safe_load(rendered.read_text())["gateway"]["nodes"][0]["model_served"] == "Qwen/Qwen3-0.6B"
    out = capsys.readouterr().out
    assert "serve_rollout" in out and "serve_gateway" in out


# --- CP-27: the strangerward lift (wishlist 19, 22; F-20, F-21) -----------


def test_module_form_help_exits_zero_and_prints():
    """Wishlist 19's other half: the module form must behave like the
    console script, not like an import."""
    result = subprocess.run([sys.executable, "-m", "gsj_rollout.cli", "--help"],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0
    assert "gsj-rollout" in result.stdout


def test_module_form_serve_bad_config_exits_2_not_silently_0(tmp_path):
    """Hypothesis (f), measured at CP-26: `python -m gsj_rollout.cli serve`
    exited 0 with zero bytes of output having started nothing. With the
    __main__ guard it takes the CP-08 contract: stated exit code, says why."""
    result = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.cli", "serve",
         "--config", str(tmp_path / "missing.yaml")],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2  # EXIT_CONFIG, not the silent 0
    assert result.stderr.strip()   # and it says why


def test_serve_instructions_survive_a_pipe(tmp_path):
    """F-20: the topology + the two Polar commands are the session's only
    instructions, and block-buffered stdout lost them under `nohup … > log`.
    Through a pipe (not a tty), they must arrive WHILE the server runs."""
    import queue
    import threading
    import time

    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gsj_rollout.cli", "serve", "--config", str(config)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO_ROOT,
        # a parent env with PYTHONUNBUFFERED set would make this test pass
        # without the flush — pin it off so the coverage is unconditional
        env={**os.environ, "PYTHONUNBUFFERED": ""})
    channel: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=lambda: [channel.put(line) for line in proc.stdout],
                     daemon=True).start()
    lines: list[str] = []
    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and len(lines) < 5:
            try:
                lines.append(channel.get(timeout=0.2))
            except queue.Empty:
                pass
        assert proc.poll() is None, (proc.returncode, proc.stderr.read())
        joined = "".join(lines)
        assert "serve_rollout" in joined and "serve_gateway" in joined
        assert "receiver listening" in joined
        # F-21: the printed Polar path is absolute, not cwd-relative
        assert str(REPO_ROOT / "vendor" / "polar" / ".venv") in joined
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_no_signal_handler_installed_at_import():
    # The predecessor's embeddability property, checked in a clean interpreter.
    probe = (
        "import signal, gsj_rollout.cli, gsj_rollout.receiver;"
        "assert signal.getsignal(signal.SIGINT) is signal.default_int_handler;"
        "assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL;"
        "print('clean')"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                            text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"
