"""CP-83: disposable containment canaries, record recovery, and real-process exclusion."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import pytest

ESTATE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ESTATE_DIR))
import estate as est  # noqa: E402

ESTATE_PY = ESTATE_DIR / "estate.py"


def invoke(runs, verb, name, *args):
    # A boundary regression must never reach the host Docker daemon.
    with tempfile.TemporaryDirectory(prefix="cp90-boundary-docker-canary-") as scratch:
        fake_bin = Path(scratch)
        calls = fake_bin / "docker-calls"
        docker = fake_bin / "docker"
        docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CP90_DOCKER_CALLS"\nexit 97\n')
        docker.chmod(0o700)
        env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                   CP90_DOCKER_CALLS=str(calls), PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, str(ESTATE_PY), verb, "--runs-dir", str(runs),
                               "--name", name, *args], env=env, capture_output=True,
                              text=True, timeout=15)
        assert not calls.exists(), "Docker canary intercepted: " + calls.read_text()
        return proc


def record(name="canary"):
    return {"schema": 1, "run": name,
            "forgejo": {"mode": "adopted", "url": "http://127.0.0.1:9"},
            "mcp": {"mode": "adopted", "url": "http://127.0.0.1:9"}}


def test_invoke_intercepts_docker_before_host_path(tmp_path, monkeypatch):
    # The second shim also makes this safety test harmless with invoke's fix removed.
    host_bin = tmp_path / "disposable-host-bin"
    host_bin.mkdir()
    host_call = tmp_path / "disposable-host-docker-call"
    host_docker = host_bin / "docker"
    host_docker.write_text('#!/bin/sh\nprintf called > "$CP90_HOST_DOCKER_CALL"\nexit 98\n')
    host_docker.chmod(0o700)
    monkeypatch.setenv("PATH", str(host_bin))
    monkeypatch.setenv("CP90_HOST_DOCKER_CALL", str(host_call))
    surrogate = tmp_path / "disposable-estate.py"
    surrogate.write_text("import subprocess, sys\nsys.exit(subprocess.run(['docker', 'info']).returncode)\n")
    monkeypatch.setitem(invoke.__globals__, "ESTATE_PY", surrogate)
    with pytest.raises(AssertionError, match="Docker canary intercepted: info"):
        invoke(tmp_path / "runs", "up", "canary")
    assert not host_call.exists()


@pytest.mark.parametrize("verb", ["up", "update", "status", "down"])
@pytest.mark.parametrize("bad_name", ["../outside", "absolute", "escape", "loop", "trailing\n"])
def test_every_named_verb_refuses_uncontained_names_before_work(tmp_path, verb, bad_name):
    runs = tmp_path / "runs"
    runs.mkdir()
    canary = tmp_path / "outside"
    canary.mkdir()
    evidence = canary / "disposable.txt"
    evidence.write_text("Made only for this test; never real user data.\n")
    expected = f"run name {bad_name!r} is not a token."
    if bad_name == "absolute":
        bad_name = str(canary)
        expected = f"run name {bad_name!r} is not a token."
    elif bad_name == "escape":
        # Valid outside state makes status/update exercise the containment guard,
        # rather than accidentally passing on an unrelated missing-record refusal.
        (canary / "run.json").write_text(json.dumps(record("escape")))
        (canary / ".env").write_text("")
        (canary / "compose.yaml").write_text(est.COMPOSE_HEAD.format(
            prog="estate/estate.py", run="escape", project="gsj-escape"))
        (runs / "escape").symlink_to(canary, target_is_directory=True)
        expected = "run 'escape' escapes its named directory."
    elif bad_name == "loop":
        (runs / "loop").symlink_to("loop", target_is_directory=True)
        expected = "run 'loop' escapes its named directory."
    proc = invoke(runs, verb, bad_name, *(["--wipe"] if verb == "down" else []))
    assert proc.returncode == 1
    assert "REFUSED" in proc.stderr and "Traceback" not in proc.stderr
    assert expected in proc.stderr, proc.stderr
    assert evidence.read_text().startswith("Made only for this test")
    assert not (runs / ".locks").exists()  # rejected before even a lock is created


def test_wipe_refuses_unowned_directory_and_keeps_disposable_contents(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.dir.mkdir()
    canary = r.dir / "disposable.txt"
    canary.write_text("not an estate")
    monkeypatch.setattr(est.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        est.cmd_down(argparse.Namespace(name=r.name, wipe=True))
    assert exc.value.code == 1
    assert "ownership" in capsys.readouterr().err
    assert canary.read_text() == "not an estate"


@pytest.mark.parametrize("loop_name", ["canary", ".locks"])
def test_symlink_loop_refusal_survives_python312_resolution_error(tmp_path, monkeypatch, capsys,
                                                                 loop_name):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    root = tmp_path.resolve()
    loop = root / loop_name
    loop.symlink_to(loop_name, target_is_directory=True)
    original_resolve = Path.resolve

    def python312_resolve(path, *args, **kwargs):
        if path == loop:
            raise RuntimeError(f"Symlink loop from {path}")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", python312_resolve)
    with pytest.raises(SystemExit) as exc:
        run = est.Run("canary")
        with run.mutation():
            pytest.fail("a looping run or lock path must refuse before mutation")
    refusal = capsys.readouterr().err
    assert exc.value.code == 1 and "REFUSED" in refusal
    assert "found:" in refusal and "expected:" in refusal and "what to do:" in refusal
    assert loop.is_symlink()


def test_marker_proves_ownership_but_unknown_network_blocks_partial_wipe(tmp_path, monkeypatch,
                                                                      capsys):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.prepare()
    (r.dir / "disposable.txt").write_text("owned partial run, no Docker work yet")
    r.require_wipe_owned()
    monkeypatch.setattr(est.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit):
        est.cmd_down(argparse.Namespace(name=r.name, wipe=True))
    assert "network gsj-canary-net is unverified; refusing --wipe" in capsys.readouterr().err
    assert (r.dir / "disposable.txt").read_text() == "owned partial run, no Docker work yet"


@pytest.mark.parametrize("legacy", ["record", "compose", "env"])
def test_legacy_run_ownership_needs_matching_identity(tmp_path, monkeypatch, legacy):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.dir.mkdir()
    if legacy == "record":
        path = r.dir / "run.json"
        path.write_text(json.dumps(record()))
    elif legacy == "compose":
        path = r.dir / "compose.yaml"
        path.write_text(est.COMPOSE_HEAD.format(prog="estate/bringup.py", run=r.name,
                                                project="gsj-canary"))
    else:
        path = r.dir / ".env"
        r.write_env()
    assert r.owned()
    path.write_text(path.read_text().replace("canary", "someone-else"))
    assert not r.owned()


@pytest.mark.parametrize("bad", [None, [], {}, {"schema": 2, "run": "canary"},
                                 {"schema": True, "run": "canary"},
                                 {"schema": 1, "run": "someone-else"},
                                 {**record(), "network": []},
                                 {**record(), "network": {"external": "false"}},
                                 {**record(), "secrets": {"names": "secret"}},
                                 {**record(), "ports": {"receiver": "8300"}},
                                 {**record(), "forgejo": {"mode": "created", "url": "broken"}},
                                 {**record(), "engine": {"url": "http://[invalid"}},
                                 {**record(), "compose": {"mcp": {"image": "some-image"}}},
                                 {**record(), "last_run": []}])
def test_invalid_record_shape_names_file_and_recovery_without_traceback(tmp_path, bad):
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps(bad))
    (rd / ".env").write_text("")
    proc = invoke(tmp_path, "status", "canary")
    assert proc.returncode == 1
    assert "run.json" in proc.stderr and "restore" in proc.stderr
    assert "REFUSED" in proc.stderr and "Traceback" not in proc.stderr


def test_historical_and_partial_schema_one_records_remain_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.dir.mkdir()
    (r.dir / ".env").write_text("")
    historical = {**record(), "corpus": {"sandbox_image": "historical-sandbox"}}
    for body in (historical, {"schema": 1, "run": "canary", "forgejo": historical["forgejo"]}):
        (r.dir / "run.json").write_text(json.dumps(body))
        r.load()
        assert r.record == body
    proc = invoke(tmp_path, "status", "canary")
    assert proc.returncode == 1 and "incomplete" in proc.stderr
    assert "up --name canary" in proc.stderr and "Traceback" not in proc.stderr


def test_up_refuses_arbitrary_nonempty_run_directory_before_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.dir.mkdir()
    canary = r.dir / "disposable.txt"
    canary.write_text("unknown directory")
    with pytest.raises(SystemExit):
        r.prepare()
    refusal = capsys.readouterr().err
    assert "refusing to use" in refusal and "choose another --name" in refusal
    assert canary.read_text() == "unknown directory"
    assert not (r.dir / ".estate-run").exists()


def test_missing_env_preserves_restore_backup_cure(tmp_path):
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps(record()))
    proc = invoke(tmp_path, "status", "canary")
    assert proc.returncode == 1 and ".env is missing" in proc.stderr
    assert "restore .env from your backup" in proc.stderr


def test_record_replacement_uses_unique_tempfiles_and_cleans_failed_replace(tmp_path, monkeypatch):
    monkeypatch.setattr(est, "RUNS", tmp_path)
    r = est.Run("canary")
    r.dir.mkdir()
    r.record = record()
    paths = []
    real_replace = est.os.replace

    def replace(src, dst):
        paths.append(src)
        real_replace(src, dst)

    monkeypatch.setattr(est.os, "replace", replace)
    r.write_record()
    r.write_record()
    assert len(set(paths)) == 2
    assert all(path.name != "run.json.tmp" for path in paths)

    def failed_replace(src, dst):
        raise OSError("synthetic rename failure")

    before = (r.dir / "run.json").read_bytes()
    monkeypatch.setattr(est.os, "replace", failed_replace)
    with pytest.raises(OSError, match="synthetic rename failure"):
        r.write_record()
    assert (r.dir / "run.json").read_bytes() == before
    assert not list(r.dir.glob("run.json.*.tmp"))


def test_four_processes_each_write_100_records_only_succeed_or_refuse_busy(tmp_path):
    (tmp_path / "canary").mkdir()
    gate = tmp_path / "go"
    code = """
import contextlib, io, json, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
import estate as est
est.RUNS = pathlib.Path(sys.argv[2])
run = est.Run('canary')
run.record = {'run': 'canary'}
pathlib.Path(sys.argv[3]).touch()
while not pathlib.Path(sys.argv[4]).exists():
    time.sleep(.001)
counts = {}
for _ in range(100):
    try:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            run.write_record()
        result = 'success'
    except SystemExit as exc:
        result = 'busy' if exc.code == 1 and 'is busy' in err.getvalue() else 'wrong_refusal'
    except Exception as exc:
        result = type(exc).__name__
    counts[result] = counts.get(result, 0) + 1
print(json.dumps(counts))
"""
    workers = [subprocess.Popen([sys.executable, "-c", code, str(ESTATE_DIR), str(tmp_path),
                                 str(tmp_path / f"ready-{n}"), str(gate)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for n in range(4)]
    try:
        deadline = time.monotonic() + 10
        while len(list(tmp_path.glob("ready-*"))) != 4 and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(list(tmp_path.glob("ready-*"))) == 4
    finally:
        gate.touch()
    totals = {}
    for worker in workers:
        stdout, stderr = worker.communicate(timeout=10)
        assert worker.returncode == 0, stderr
        for result, count in json.loads(stdout).items():
            totals[result] = totals.get(result, 0) + count
    assert set(totals) <= {"success", "busy"}, totals
    assert sum(totals.values()) == 400 and totals.get("success", 0) > 0
    assert json.loads((tmp_path / "canary/run.json").read_text())["schema"] == 1
    assert not list((tmp_path / "canary").glob("*.tmp"))


def test_whole_mutating_command_excludes_other_verbs_but_status_can_read(tmp_path):
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps(record()))
    (rd / ".env").write_text("")
    entered, release = tmp_path / "entered", tmp_path / "release"
    code = """
import argparse, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
import estate as est
est.RUNS = pathlib.Path(sys.argv[2])
def paused_load(*args):
    pathlib.Path(sys.argv[3]).touch()
    while not pathlib.Path(sys.argv[4]).exists():
        time.sleep(.01)
    raise SystemExit(0)
est._load_run = paused_load
est.cmd_update(argparse.Namespace(name='canary', dry_run=False))
"""
    proc = subprocess.Popen([sys.executable, "-c", code, str(ESTATE_DIR), str(tmp_path),
                             str(entered), str(release)], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not entered.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert entered.exists(), proc.communicate(timeout=1)
        for verb in ("up", "update", "down"):
            other = invoke(tmp_path, verb, "canary")
            assert other.returncode == 1 and "is busy" in other.stderr
            assert "wait for it to finish or check status" in other.stderr
            assert "Traceback" not in other.stderr
        other = invoke(tmp_path, "status", "canary")
        assert other.returncode == 0, other.stderr
        assert "== run canary" in other.stdout
    finally:
        release.touch()
        proc.communicate(timeout=5)
    assert proc.returncode == 0
    # A later writer acquires normally: no stale lock after the command exits.
    code = "import pathlib,sys;sys.path.insert(0,sys.argv[1]);import estate as e;e.RUNS=pathlib.Path(sys.argv[2]);r=e.Run('canary');r.load();r.write_record()"
    later = subprocess.run([sys.executable, "-c", code, str(ESTATE_DIR), str(tmp_path)],
                           capture_output=True, text=True, timeout=5)
    assert later.returncode == 0, later.stderr
