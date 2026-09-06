"""CP-90: disposable canaries at the run/credential refusal seam."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "estate_refusal_repairs", Path(__file__).resolve().parents[2] / "estate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "run", Mock(side_effect=AssertionError("unexpected Docker call")))
    return module


def owned(est, name="rory"):
    r = est.Run(name)
    r.prepare()
    (r.dir / "precious.txt").write_text("disposable CP-90 canary")
    return r


def clean_refusal(capsys):
    err = capsys.readouterr().err
    assert all(word in err for word in ("REFUSED", "found:", "expected:", "what to do:"))
    assert "Traceback" not in err
    return err


@pytest.mark.skipif(os.geteuid() == 0, reason="0500 must deny directory creation")
@pytest.mark.parametrize("verb", ["up", "update", "down"])
def test_unwritable_runs_root_refuses_before_work(est, tmp_path, capsys, verb):
    r = owned(est)
    (r.dir / "compose.yaml").write_text(est.COMPOSE_HEAD.format(
        prog=est.PROG, run=r.name, project="gsj-rory"))
    (r.dir / "run.json").write_text(json.dumps({"schema": 1, "run": r.name}))
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(SystemExit) as exc:
            getattr(est, "cmd_" + verb)(argparse.Namespace(name=r.name, wipe=False))
        assert exc.value.code == 1
        err = clean_refusal(capsys)
        assert str(tmp_path) in err and "writable runs directory" in err and ".locks" in err
        est.run.assert_not_called()
        assert (r.dir / "precious.txt").is_file()
    finally:
        tmp_path.chmod(0o700)


@pytest.mark.parametrize("kind", ["file", "missing"])
def test_lock_setup_reports_runs_root_without_creating_parents(est, tmp_path, monkeypatch, capsys, kind):
    root = tmp_path / "root-canary"
    if kind == "file":
        root.write_text("disposable file")
    else:
        root = root / "missing-runs"
    monkeypatch.setattr(est, "RUNS", root)
    with pytest.raises(SystemExit):
        est.cmd_up(argparse.Namespace(name="root-canary"))
    assert str(root) in clean_refusal(capsys)
    assert not (root / ".locks").exists()
    assert kind == "file" or not root.parent.exists()
    est.run.assert_not_called()


@pytest.mark.skipif(os.geteuid() == 0, reason="0000 must deny directory access")
@pytest.mark.parametrize("blocked", ["directory", "file"])
def test_lock_permission_cure_distinguishes_directory_from_file(est, tmp_path, capsys, blocked):
    r = owned(est, "lock-permissions-canary")
    locks = tmp_path / ".locks"
    locks.mkdir()
    target = locks if blocked == "directory" else locks / (r.name + ".lock")
    if blocked == "file":
        target.touch()
    target.chmod(0)
    try:
        with pytest.raises(SystemExit):
            est.cmd_down(argparse.Namespace(name=r.name, wipe=False))
        err = clean_refusal(capsys)
        if blocked == "directory":
            assert str(locks) in err
            assert f"owner uid {locks.stat().st_uid}" in err
            assert f"caller uid {os.geteuid()}" in err
            assert "run as the user that owns" in err and "do not delete" in err
            assert "restore the lock file and its permissions" not in err
        else:
            assert "restore the lock file and its permissions" in err
        est.run.assert_not_called()
    finally:
        target.chmod(0o700 if blocked == "directory" else 0o600)


@pytest.mark.parametrize("verb", ["down", "update"])
@pytest.mark.parametrize("root_exists", [False, True])
def test_absent_run_refuses_without_leaving_a_lock(est, tmp_path, monkeypatch, capsys, verb, root_exists):
    root = tmp_path if root_exists else tmp_path / "typo-canary" / "runs"
    monkeypatch.setattr(est, "RUNS", root)
    with pytest.raises(SystemExit):
        getattr(est, "cmd_" + verb)(argparse.Namespace(name="absent-canary", wipe=False))
    assert "no run named 'absent-canary'" in clean_refusal(capsys)
    assert not (root / ".locks").exists()
    assert root_exists or not root.parent.exists()
    est.run.assert_not_called()


def test_update_missing_record_refuses_before_lock(est, tmp_path, capsys):
    r = owned(est, "missing-record-canary")
    with pytest.raises(SystemExit):
        est.cmd_update(argparse.Namespace(name=r.name))
    assert "has no run.json" in clean_refusal(capsys)
    assert not (tmp_path / ".locks").exists()


@pytest.mark.parametrize("field", ["backend", "embedding"])
def test_null_optional_health_mapping_remains_loadable(est, field):
    r = owned(est, "null-health-canary")
    r.record = {"schema": 1, "run": r.name, "mcp": {
        "mode": "adopted", "url": "http://localhost:9", field: None}}
    r.write_env()
    r.write_record()
    loaded = est.Run(r.name)
    loaded.load()
    assert loaded.record["mcp"][field] is None
    assert est.record_problem(loaded.record, r.name) is None
    inputs = est.mcp_config_inputs(est.Answers(argparse.Namespace(answers=None, defaults=True)),
                                   loaded.record)
    assert inputs["model"] == est.DEFAULT_EMBEDDING_MODEL
    loaded.record["mcp"][field] = []
    assert est.record_problem(loaded.record, r.name) == f"mcp.{field} is not an object"


@pytest.mark.parametrize("record", ["absent", "broken", "unreadable"])
def test_adopted_only_unknown_network_preserves_wipe_canary(est, monkeypatch, capsys, record):
    r = owned(est, "adopted-network-canary")
    rec = r.dir / "run.json"
    if record != "absent":
        rec.write_text("{not JSON")
    if record == "unreadable":
        original = Path.read_text

        def read_text(path, *args, **kwargs):
            if path == rec:
                raise PermissionError("disposable record canary")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(SystemExit):
        est.cmd_down(argparse.Namespace(name=r.name, wipe=True))
    err = clean_refusal(capsys)
    assert "network" in err and "unverified" in err and "gsj-adopted-network-canary-net" in err
    assert "restore run.json from backup" in err
    assert (r.dir / "precious.txt").is_file()
    est.run.assert_not_called()
    est.cmd_down(argparse.Namespace(name=r.name, wipe=False))
    assert "unverified" in capsys.readouterr().out


@pytest.mark.parametrize("channel", ["env", "file"])
@pytest.mark.parametrize("line_kind", ["legacy-apostrophe", "malformed"])
def test_follow_printed_load_cure_to_working_credential(est, tmp_path, monkeypatch, capsys, channel, line_kind):
    r = owned(est, "credential-cure-canary")
    key = est.ADMIN_PASSWORD_ENV
    raw = est._env_quote("old'pw") if line_kind == "legacy-apostrophe" else "unquoted"
    path = r.dir / ".env"
    path.write_text(f"{key}={raw}\n")
    before = path.read_bytes()
    replacement = "rotated-synthetic-password"
    file = tmp_path / "synthetic-password"
    file.write_text(replacement)
    file.chmod(0o600)
    monkeypatch.delenv(key, raising=False)
    if channel == "env":
        monkeypatch.setenv(key, replacement)
    args = argparse.Namespace(name=r.name, answers=None, defaults=True,
                              corpus=str(Path(est.__file__).parent / "corpus/staging"),
                              forgejo="adopt", forgejo_admin_password_file=str(file) if channel == "file" else None)
    secret = est.Answers.secret
    spy = Mock(side_effect=AssertionError("load must precede Answers.secret"))
    monkeypatch.setattr(est.Answers, "secret", spy)
    with pytest.raises(SystemExit):
        est.cmd_up(args)
    err = clean_refusal(capsys)
    spy.assert_not_called()
    est.run.assert_not_called()
    assert path.read_bytes() == before
    assert str(path) in err and "line 1" in err
    assert "edit" in err and "by hand" in err and f"{key}='value'" in err
    assert "up" in err and "down" in err and "--wipe" in err
    assert f"--runs-dir {r.root}" in err
    assert "old'pw" not in err and replacement not in err
    # Follow the printed repair exactly, then exercise the real adoption reader
    # and persistence boundary. A different valid placeholder proves re-adoption.
    path.write_text(f"{key}='valid-placeholder'\n")
    monkeypatch.setattr(est.Answers, "secret", secret)
    # Re-enter the advertised verb and observe the actual adopted-service
    # authentication boundary. Stop at the test service, before any network I/O.
    class Authenticated(Exception):
        pass

    def probe(forgejo):
        assert forgejo.admin[1] == replacement
        raise Authenticated

    monkeypatch.setattr(est.Forgejo, "probe", probe)
    monkeypatch.setattr(est, "script_version", lambda: {"test": "CP-90"})
    args.forgejo_url = "http://127.0.0.1:9"
    with pytest.raises(Authenticated):
        est.cmd_up(args)
    est.run.assert_not_called()
    loaded = est.Run(r.name)
    loaded.load()
    loaded.env[key] = replacement
    loaded.write_env()
    reloaded = est.Run(r.name)
    reloaded.load()
    assert reloaded.env[key] == replacement


@pytest.mark.parametrize("raw", [b"KEY='abc'\r\n", b"KEY='ab\rc'\n"])
def test_cr_in_env_is_refused_without_normalization(est, capsys, raw):
    r = owned(est, "crlf-credential-canary")
    (r.dir / ".env").write_bytes(raw)
    with pytest.raises(SystemExit):
        r.load()
    err = clean_refusal(capsys)
    assert "control character" in err and "by hand" in err
    assert r.env == {}
    assert (r.dir / ".env").read_bytes() == raw
