"""CP-83: a teardown refusal must preserve the disposable run's data."""
import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def estate(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "estate_down_test", Path(__file__).resolve().parents[2] / "estate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/docker")
    return module


def canary(estate, *, env=True, compose=True, record=None):
    r = estate.Run("canary")
    r.dir.mkdir()
    (r.dir / "precious.txt").write_text("disposable CP-83 canary")
    if compose:
        (r.dir / "compose.yaml").write_text(estate.COMPOSE_HEAD.format(
            prog=estate.PROG, run=r.name, project="gsj-canary")
            + "  mcp:\n    image: example.invalid/canary\n")
    if env:
        (r.dir / ".env").write_text("")
    if record is not None:
        (r.dir / "run.json").write_text(json.dumps(record))
    return r


def docker_stub(*, stop=0, network_rm=0, unavailable=False,
                survivors=False, network=True):
    calls = []
    state = {"network": network}

    def run(cmd, **kw):
        calls.append(cmd)
        code, out, err = 0, "", ""
        if unavailable:
            code, err = 1, "Cannot connect to the Docker daemon"
        elif cmd[1] == "compose":
            code, err = stop, "stop failed" if stop else ""
        elif cmd[1] == "ps":
            out = "owned-container\n" if survivors else ""
        elif cmd[1:3] == ["network", "ls"]:
            out = "gsj-canary-net\n" if state["network"] else ""
        elif cmd[1:3] == ["network", "inspect"]:
            code = 0 if state["network"] else 1
        elif cmd[1:3] == ["network", "rm"]:
            code, err = network_rm, "network has active endpoints" if network_rm else ""
            if not code:
                state["network"] = False
        return subprocess.CompletedProcess(cmd, code, out, err)

    return run, calls


@pytest.mark.parametrize("env", [True, False])
@pytest.mark.parametrize("failure", ["unavailable", "stop", "network", "survivors"])
def test_failed_cleanup_refuses_before_wipe(estate, monkeypatch, capsys, env, failure):
    r = canary(estate, env=env)
    run, calls = docker_stub(unavailable=failure == "unavailable",
                             stop=int(failure == "stop"),
                             network_rm=int(failure == "network"),
                             survivors=failure == "survivors")
    monkeypatch.setattr(estate, "run", run)
    with pytest.raises(SystemExit) as exc:
        estate.cmd_down(argparse.Namespace(name=r.name, wipe=True))
    assert exc.value.code != 0
    captured = capsys.readouterr()
    assert "created services stopped" not in captured.out
    assert "what to do:" in captured.err
    assert "Docker" in captured.err or "docker" in captured.err
    assert (r.dir / "precious.txt").read_text() == "disposable CP-83 canary"
    assert not any(cmd[1] == "run" for cmd in calls)


@pytest.mark.parametrize("record", [None, [], {"network": []}])
def test_missing_or_damaged_record_can_stop_created_services(estate, monkeypatch, record):
    r = canary(estate, env=False, record=record)
    run, calls = docker_stub()
    monkeypatch.setattr(estate, "run", run)
    estate.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert ["docker", "compose", "-p", "gsj-canary", "down", "--remove-orphans"] in calls
    assert any(cmd[1] == "ps" for cmd in calls)
    assert ["docker", "network", "rm", "gsj-canary-net"] in calls
    assert (r.dir / "precious.txt").is_file()


@pytest.mark.parametrize("record", [
    {"network": {"name": "other-tenant", "external": True}},
    {"schema": 1, "run": "other-run", "network": {"external": True}},
    {"schema": 1, "run": "canary", "network": {"external": "false"}},
])
def test_damaged_record_cannot_hide_generated_compose_owned_network(estate, monkeypatch, record):
    r = canary(estate, env=False, record=record)
    run, calls = docker_stub()
    monkeypatch.setattr(estate, "run", run)
    estate.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert ["docker", "network", "rm", "gsj-canary-net"] in calls
    assert (r.dir / "precious.txt").is_file()


def test_positive_absence_is_idempotent_and_data_survives(estate, monkeypatch):
    r = canary(estate)
    run, calls = docker_stub(network=False)
    monkeypatch.setattr(estate, "run", run)
    estate.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert not any(cmd[1:3] == ["network", "rm"] for cmd in calls)
    assert (r.dir / "precious.txt").is_file()


@pytest.mark.parametrize("record", [None, {"network": {"name": "external", "external": True}},
                                  {"compose": "damaged"}])
def test_no_owned_docker_resources_needs_no_daemon_or_valid_record(estate, monkeypatch, record):
    r = canary(estate, compose=False, record=record)
    monkeypatch.setattr(estate.shutil, "which", lambda _: None)
    monkeypatch.setattr(estate, "run", lambda *a, **kw: pytest.fail("Docker was not needed"))
    estate.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert (r.dir / "precious.txt").is_file()


def test_adopted_external_network_is_never_removed(estate, monkeypatch):
    r = canary(estate, record={"schema": 1, "run": "canary",
                              "network": {"name": "other-tenant", "external": True}})
    run, calls = docker_stub(network=False)
    monkeypatch.setattr(estate, "run", run)
    estate.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert not any(cmd[1:3] == ["network", "rm"] for cmd in calls)


def test_root_owned_wipe_failure_is_not_reported_done(estate, monkeypatch, capsys):
    r = canary(estate)
    run, calls = docker_stub(network=False)

    def failing_wipe(cmd, **kw):
        if cmd[1] == "run":
            return subprocess.CompletedProcess(cmd, 1, "", "read-only filesystem")
        return run(cmd, **kw)

    def permission_error(*args, **kw):
        raise PermissionError("root-owned test canary")

    monkeypatch.setattr(estate, "run", failing_wipe)
    monkeypatch.setattr(estate.shutil, "rmtree", permission_error)
    with pytest.raises(SystemExit) as exc:
        estate.cmd_down(argparse.Namespace(name=r.name, wipe=True))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "wipe did not finish" in captured.err
    assert "read-only filesystem" in captured.err
    assert "done; the next" not in captured.out
    assert (r.dir / "precious.txt").is_file()
