"""Activation contracts recorded from independent, unchanged 482b041 source.

The observer runs real cmd_up/Run/file publication through the activation
boundary; only external service observations are substituted. Docker CLI
answers come from the measured disposable Compose fixture, not invented
exit/stream shapes. The corpus scaffold child uses the real file:// rail.
Run this file as a script to characterize another independent source tree.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "activation"
SCENARIOS = (
    "cold", "warm", "changed_config", "rebuild", "resume_build", "drop_summary",
    "adopt", "adopt_after_create", "compose_written", "checkpoint_before",
    "checkpoint_after", "activation_after", "wait_oserror", "wait_interrupt",
    "reset_after", "hook_mutation", "late_timeout", "missing_timeout",
)


class ObservedBoundary(Exception):
    """The next unchanged corpus phase is outside the selected operation."""


def observe(source: Path, work: Path, scenario: str) -> dict:
    source, work = source.resolve(), work.resolve()
    sys.path.insert(0, str(source))
    path = source / "estate" / "estate.py"
    spec = importlib.util.spec_from_file_location("activation_subject", path)
    est = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = est
    spec.loader.exec_module(est)
    assert Path(est.__file__).resolve() == path
    assert Path(est.ic.__file__).resolve() == source / "estate/corpus/ingest_corpus.py"
    import gsj_rollout
    assert Path(gsj_rollout.__file__).resolve() == source / "gsj_rollout/__init__.py"
    fixture_spec = importlib.util.spec_from_file_location("activation_corpus_fixture",
                                                       HERE / "conftest.py")
    fixtures = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixtures)
    work.mkdir(parents=True)
    corpus = fixtures.make_corpus(work / "corpus", estate_fields=False)
    bare = work / "bare"
    bare.mkdir()
    est.RUNS = work / "runs"
    est.RUNS.mkdir()
    events, outcomes = [], []
    state = {"running": False, "fault": None, "building": False, "mutation": False}
    est._T0 = 100.0
    est._TTY = False
    est.time = SimpleNamespace(monotonic=lambda: 100.0, time=lambda: 100.0)
    est.now_iso = lambda: "2026-09-11T00:00:00+00:00"
    est.script_version = lambda: {"script": "estate/estate.py", "commit": "482b041",
                                  "dirty": False, "library": "0.1.16"}
    est.shutil = SimpleNamespace(**{key: getattr(shutil, key) for key in dir(shutil)})
    est.shutil.which = lambda cmd: "/usr/bin/git" if cmd == "git" else None
    est.check_docker = lambda: events.append(["check_docker"])
    est.daemon_arch = lambda: "arm64"
    # This fixture characterizes the measured macOS/ARM contract even when
    # pytest runs on Linux; installed Linux paths have separate deployment proof.
    est.platform = SimpleNamespace(system=lambda: "Darwin")
    est.image_present = lambda image: True
    est.pick_port = lambda want, default, *args, **kwargs: default
    est.secrets = SimpleNamespace(token_hex=lambda size: "c" * (size * 2))
    for key in list(os.environ):
        if key.startswith("GSJ_"):
            del os.environ[key]
    os.environ[est.ADMIN_PASSWORD_ENV] = "fixture-admin-password"
    os.environ[est.MCP_SECRET_ENV] = "c" * 64
    health = {"state": "ready", "fingerprint": "f" * 64, "index_reused": True,
              "embedding": {"model": est.DEFAULT_EMBEDDING_MODEL,
                            "revision": est.DEFAULT_EMBEDDING_REVISION, "dimension": 384},
              "cases": {"case_a": {}, "case_b": {}}, "decisions": 30,
              "progress": {}, "backend": {"kind": "chroma"}}
    if scenario == "drop_summary":
        health.update(rebuilt=["decisions"], decisions_drop={"files": 2, "units": 3,
                      "pieces": 4, "sha256": "d" * 64})
    est.http = lambda *args, **kwargs: (200, health)
    est.Forgejo.probe = lambda self: setattr(self, "signin", True)
    est.Forgejo.owner_exists = lambda self, owner: True
    est.Forgejo.owner_repos = lambda self, owner: []
    est.Forgejo.token_valid = lambda self, token, owner: True
    est.Forgejo.mint_token = lambda self, owner, label, scopes: "fixture-" + label + "-token"
    est.Mcp.health = lambda self: health
    est.Mcp.reindex = lambda self: (events.append(["reindex", self.url, self.secret])
                                   or (202, {"reindex": "started"}))
    original_wait = est.Mcp.wait_ready

    def wait(self, timeout, what, container=None):
        events.append(["wait_ready", self.url, self.container_url, self.secret, timeout, what, container])
        if state["fault"] == "wait_oserror":
            raise OSError("injected readiness transport boundary")
        if state["fault"] == "wait_interrupt":
            raise KeyboardInterrupt("injected readiness cancellation")
        return original_wait(self, timeout, what, container)

    est.Mcp.wait_ready = wait

    def building(url, container):
        events.append(["rebuild_in_progress", url, container])
        return state["building"]

    est.rebuild_in_progress = building

    def compose(root, *args, **kwargs):
        events.append(["compose", str(root), list(args), kwargs])
        if args[0] == "up":
            key = ("docker compose up -d --force-recreate mcp <running>" if "--force-recreate" in args
                   else "docker compose up -d mcp <running>" if state["running"]
                   else "docker compose up -d mcp <absent>")
            state["running"] = True
            if state["fault"] == "activation_after":
                raise OSError("injected after external activation")
        elif args[0] == "ps":
            key = "docker compose ps <running>" if state["running"] else "docker compose ps <absent>"
        elif args[0] == "down":
            state["running"] = False
            key = "docker compose down --remove-orphans <running>"
        else:
            raise AssertionError(args)
        # cli_shape already owns response construction and substitutions. Its
        # stdout argument carries the recorded sample for a host-variable row.
        sample = fixtures.CLI_SHAPES["shapes"][key].get("sample_stdout", "")
        return fixtures.cli_shape(key, list(args), name="gsj-activation-mcp", network="external-net",
                                  stdout=sample.replace("{name}", "gsj-activation-mcp"))

    est.compose = compose
    original_run = est.run

    def run(cmd, **kwargs):
        if cmd[0] != "docker":
            return original_run(cmd, **kwargs)
        events.append(["docker", cmd, kwargs])
        assert cmd[1:3] == ["ps", "-a"]
        return fixtures.cli_shape(
            "docker ps -a --filter label=com.docker.compose.project=<absent> --format {{.Names}}",
            cmd, name="gsj-activation")

    est.run = run
    original_compose = est.write_compose

    def write_compose(root, run_, network, external):
        events.append(["write_compose.before", network, external])
        original_compose(root, run_, network, external)
        events.append(["write_compose.after"])
        if state["fault"] == "compose_written":
            raise OSError("injected after Compose file publication")
        if scenario == "late_timeout":
            args.ingest_timeout = 7.25
        if state["mutation"]:
            # Original cmd_up locals do not change when these persisted mappings
            # are mutated by a hook. Snapshot before this hook, not after it.
            run_.record["compose"]["mcp"].update(image="mutated/image", port=9999,
                                                container="mutated-container",
                                                config=str(root / "mutated.yaml"))
            run_.record["network"].update(name="mutated-network", external=False)
            run_.env[est.MCP_SECRET_ENV] = "mutated-secret"

    est.write_compose = write_compose
    original_record = est.Run._write_record

    def write_record(self):
        target = bool(self.record.get("compose", {}).get("mcp"))
        events.append(["record.before", target])
        if target and state["fault"] == "checkpoint_before":
            raise OSError("injected before run checkpoint")
        original_record(self)
        events.append(["record.after", target])
        if target and state["fault"] == "checkpoint_after":
            raise OSError("injected after run checkpoint")
        if target and state["mutation"]:
            previous_mcp = est.Mcp
            def late_mcp(*args):
                events.append(["late_Mcp", list(args)])
                return previous_mcp(*args)
            est.Mcp = late_mcp

    est.Run._write_record = write_record
    original_write_text = Path.write_text

    def write_text(self, data, *write_args, **kwargs):
        answer = original_write_text(self, data, *write_args, **kwargs)
        if self.name == "mcp-config.yaml":
            if scenario == "missing_timeout" and hasattr(args, "ingest_timeout"):
                del args.ingest_timeout
            events.append(["config.write", "always" if "rebuild: always" in data else "if-stale"])
            if state["fault"] == "reset_after" and "rebuild: if-stale" in data:
                raise OSError("injected after rebuild reset publication")
        return answer

    Path.write_text = write_text

    def pipeline(phase, *extra, **kwargs):
        events.append(["pipeline", phase, list(extra), {key: str(value) if isinstance(value, Path) else value
                       for key, value in kwargs.items() if key != "run_env"}])
        if phase == "ingest":
            raise ObservedBoundary("next corpus ingest reached")
        assert phase == "scaffold"
        child = subprocess.run([sys.executable, str(est.INGEST), "scaffold", "--corpus", str(corpus),
                                "--base-url", bare.as_uri()], text=True, capture_output=True,
                               env={**os.environ, "GSJ_PIPELINE_DRIVER": "estate"})
        assert child.returncode == 0, child.stderr + child.stdout
        os.utime(corpus / est.ic.LOCK_NAME, (100, 100))
        return child

    est._run_corpus_phase = pipeline
    args = argparse.Namespace(answers=None, defaults=True, corpus=str(corpus), name="activation",
                              forgejo="adopt", forgejo_url="http://forgejo.fixture:3000",
                              forgejo_sandbox_url="http://forgejo.fixture:3000", network="external-net",
                              skip_sandbox_image=True, ingest_timeout=19.5,
                              mcp="adopt" if scenario == "adopt" else "create",
                              mcp_url="http://mcp.fixture:8790", mcp_sandbox_url="http://mcp.fixture:8790")

    def files():
        return {str(p.relative_to(est.RUNS)): {"body": p.read_text(), "mode": oct(p.stat().st_mode & 0o777)}
                for p in sorted(est.RUNS.rglob("*")) if p.is_file()}

    def invoke(label, callback):
        before = len(events)
        out, err = io.StringIO(), io.StringIO()
        error = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                callback()
            except BaseException as exc:
                error = [type(exc).__name__, str(exc)]
        outcomes.append({"label": label, "error": error, "stdout": out.getvalue(), "stderr": err.getvalue(),
                         "events": events[before:], "files": files(), "running": state["running"]})

    repeated = scenario in ("warm", "changed_config", "rebuild", "resume_build", "adopt_after_create", "reset_after")
    if repeated:
        invoke("initial", lambda: est.cmd_up(args))
        assert outcomes[-1]["error"][0] == "ObservedBoundary", outcomes[-1]
        index = est.RUNS / "activation/mcp-data/index"
        index.mkdir()
        (index / "fingerprint.json").write_text(json.dumps({"embedding": health["embedding"]}))
        if scenario == "changed_config":
            args.chunk_max_tokens = 240
        if scenario in ("rebuild", "resume_build", "reset_after"):
            args.rebuild = True
        if scenario == "resume_build":
            state["building"] = True
        if scenario == "adopt_after_create":
            args.mcp = "adopt"
    state["fault"] = scenario if scenario in SCENARIOS[8:15] else None
    state["mutation"] = scenario == "hook_mutation"
    if scenario == "missing_timeout":
        state["fault"] = "activation_after"
    invoke("subject", lambda: est.cmd_up(args))
    # Use real status/Run readers and actual kernel-lock observation. CLI ps
    # bytes are the measured shape; no health/query implementation is changed.
    invoke("status", lambda: est.cmd_status(argparse.Namespace(name=args.name)))
    if state["fault"]:
        state["fault"] = None
        state["building"] = state["running"] and bool(getattr(args, "rebuild", False))
        invoke("resume", lambda: est.cmd_up(args))
    est.shutil.which = lambda cmd: "/usr/bin/" + cmd
    invoke("down", lambda: est.cmd_down(argparse.Namespace(name=args.name, wipe=False)))
    Path.write_text = original_write_text
    encoded = json.dumps(outcomes, sort_keys=True).replace(str(work), "<WORK>").replace(str(source), "<SOURCE>")
    return json.loads(encoded)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_activation_matches_unchanged_source_observations(tmp_path, scenario):
    source = HERE.parents[2]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source), str(tmp_path / "work"),
                           scenario], env=environment, text=True, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    actual = json.loads(proc.stdout)
    # Keep full diagnostics beside a failed test without adding repeated run
    # files/diagnostic text to the repository's maintained fixture surface.
    (tmp_path / "actual.json").write_text(json.dumps(actual, indent=2))
    expected = json.loads((FIXTURES / "baseline.json").read_text())[scenario]
    assert observation_digests(actual) == expected
    subject = next(item for item in actual if item["label"] == "subject")
    calls = [row for row in subject["events"] if row[0] == "compose" and row[2][0] == "up"]
    if scenario in ("adopt", "adopt_after_create"):
        assert not calls
        assert any(row[0] == "reindex" for row in subject["events"])
    elif scenario in ("compose_written", "checkpoint_before", "checkpoint_after"):
        assert not calls  # failed checkpoint must not start a container
    else:
        assert len(calls) == 1
        forced = "--force-recreate" in calls[0][2]
        assert forced == (scenario in ("changed_config", "rebuild", "reset_after"))
    assert actual[-1]["label"] == "down" and actual[-1]["error"] is None
    assert "activation/.estate-run" in actual[-1]["files"]  # down without wipe


def observation_digests(rows):
    """A recorded independent oracle, split by outcome for useful failures."""
    return [{"label": row["label"], "error": row["error"], "running": row["running"],
             "sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()}
            for row in rows]


if __name__ == "__main__":
    print(json.dumps(observe(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]), indent=2))
