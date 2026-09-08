"""CP-98: the reaper's bound, and the fake that hid it (row 100).

CP-96 wrote `reap_container` to retry `docker rm -f <name>` for 30 s so that
a fallback probe killed mid-create on a copy-on-create daemon is removed when
the daemon's copy ends. The real CLI answers `docker rm -f` on a name that
does not exist with EXIT 0 and `No such container` on STDERR, so the loop
read exit 0 as removed and returned in 0.0 s on a container the daemon had
not produced yet; the hermetic test faked exit 1, which is why it shipped
green in 0.1.12. Now removed is read off stdout — the CLI names what it
removed — and every fake's shape is the measured one (cli_shapes.json).

The second half is the class, not the row (CHARTER §8 rule 10): the shapes
file is re-measured here against the CLI on PATH wherever a daemon answers,
and skipped, naming the reason, where none does."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import CLI_SHAPES, CLI_SHAPES_PATH, cli_shape

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"
TESTS_DIR = Path(__file__).resolve().parent
HARNESS = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
PRESENT_IMAGE = "alpine:3.20"
ABSENT_IMAGE = "example.invalid/absent:1"


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp98", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "PH", module.Phases())
    return module


# ------------------------------------------------------------ the reaper

def test_reap_container_reads_removed_off_stdout_not_the_exit_code(est, monkeypatch):
    """The two answers the CLI gives are BOTH exit 0: `<name>\\n` on stdout
    when it removed something, `No such container` on stderr when the name
    is not there (yet). Only the first is 'removed'."""
    monkeypatch.setattr(est.time, "sleep", lambda s: None)
    seen = []
    answers = iter(["docker rm -f <missing>"] * 4 + ["docker rm -f <present>"])
    monkeypatch.setattr(est, "run", lambda cmd, **kw: (seen.append(cmd),
                                                       cli_shape(next(answers), cmd, name=cmd[3]))[1])
    assert est.reap_container("gsj-probe-42", wait_s=60) is True
    assert seen == [["docker", "rm", "-f", "gsj-probe-42"]] * 5
    assert cli_shape("docker rm -f <missing>", name="gsj-probe-42").returncode == 0   # the shape that hid it


def test_reap_container_past_the_bound_says_not_produced(est, monkeypatch):
    monkeypatch.setattr(est.time, "sleep", lambda s: None)
    clock = iter([0.0, 0.0, 2.0, 4.0, 31.0])
    monkeypatch.setattr(est.time, "monotonic", lambda: next(clock))
    calls = []
    monkeypatch.setattr(est, "run", lambda cmd, **kw: (calls.append(cmd),
                                                       cli_shape("docker rm -f <missing>", cmd, name=cmd[3]))[1])
    assert est.reap_container("gsj-probe-7", wait_s=30) is False
    assert len(calls) == 4          # it kept asking until the bound, never earlier


def test_reap_container_does_not_mistake_another_name_for_removed(est, monkeypatch):
    """`docker rm -f a b` prints the names it removed one per line; the reaper
    asks for one name and accepts only that name on stdout."""
    monkeypatch.setattr(est.time, "sleep", lambda s: None)
    clock = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(est.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(est, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "some-other-name\n", ""))
    assert est.reap_container("gsj-probe-9", wait_s=30) is False


def test_probe_dial_past_the_bound_names_the_container_the_wait_and_the_command(est, monkeypatch, capsys):
    monkeypatch.setattr(est.time, "sleep", lambda s: None)
    monkeypatch.setattr(est, "PROBE_RUN_TIMEOUT_S", 20.0)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return cli_shape("docker rm -f <missing>", cmd, name=cmd[3])   # never produced within the bound

    clock = iter([0.0] + [float(t) for t in range(0, 40, 2)])
    monkeypatch.setattr(est.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(est, "run", fake_run)
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5"], 18299, None, HARNESS)
    name = calls[0][3]
    assert results == [] and name.startswith("gsj-probe-")
    assert failure.startswith("timed out after 20 s via a `docker run` of " + HARNESS)
    assert f"the daemon is still creating {name} (30 s of `docker rm -f` found nothing)" in failure
    assert f"`docker rm -f {name}` removes it" in failure
    rm_calls = [c for c in calls if c[:3] == ["docker", "rm", "-f"]]
    assert len(rm_calls) >= 2 and all(c[3] == name for c in rm_calls)   # the bound ran


def test_probe_dial_does_not_reap_when_the_client_never_started(est, monkeypatch):
    """An OSError from `docker run` means no client ran: the container was
    never created, and the reaper must not wait 30 s for one — 'never
    existed' is told apart from 'still being created' by the code path,
    because the CLI cannot tell them apart."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise OSError(13, "Permission denied")
        raise AssertionError(f"unexpected docker call {cmd}")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est.time, "sleep", lambda s: pytest.fail("the reaper waited"))
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5"], 18299, None, HARNESS)
    assert results == [] and failure.startswith("could not start via a `docker run` of " + HARNESS)
    assert "still creating" not in failure
    assert [c for c in calls if c[:3] == ["docker", "rm", "-f"]] == []


def test_probe_dial_removes_a_container_the_run_left_when_it_completed(est, monkeypatch):
    """A `docker run` that returned (no --rm) leaves an exited container; the
    finally removes it at once — the CLI prints its name, the reaper is done
    on the first call."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(cmd, 0, "10.0.0.5 OK 204\n", "")
        return cli_shape("docker rm -f <present>", cmd, name=cmd[3])

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est.time, "sleep", lambda s: pytest.fail("the reaper waited"))
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5"], 18299, None, HARNESS)
    assert results == [{"candidate": "10.0.0.5", "reachable": True}] and failure is None
    assert len([c for c in calls if c[:3] == ["docker", "rm", "-f"]]) == 1


# ------------------------------------------------- the shapes are measured

def test_cli_shapes_file_is_the_contract():
    """Every shape carries an exit code and both streams, names what reads
    it, and says what CLI it was measured on; every key a test in this suite
    asks cli_shape for exists."""
    assert CLI_SHAPES["format"] == "gsj-cli-shapes/1"
    for field in ("docker_client", "docker_server", "api", "daemons", "date", "cp"):
        assert CLI_SHAPES["measured"][field], field
    for key, shape in CLI_SHAPES["shapes"].items():
        assert shape["argv"][0] == "docker", key
        assert isinstance(shape["returncode"], int) and "stderr" in shape and shape["read_by"], key
        assert ("stdout" in shape) != ("stdout_re" in shape), f"{key}: exactly one of stdout / stdout_re"
        assert shape["setup"] in ("absent", "created", "running", "image-absent", "image-present", "daemon"), key
    asked = set()
    for module in TESTS_DIR.glob("test_*.py"):
        asked.update(re.findall(r'cli_shape\("([^"]+)"', module.read_text(encoding="utf-8")))
    assert asked, "no test asks for a shape"
    assert asked <= set(CLI_SHAPES["shapes"]), asked - set(CLI_SHAPES["shapes"])


def _daemon() -> tuple[str, str | None]:
    """(reason to skip, or '') and the live CLI/server version line."""
    if os.environ.get("GSJ_CLI_SHAPES_SKIP"):
        return "GSJ_CLI_SHAPES_SKIP is set", None
    if not shutil.which("docker"):
        return "no docker on PATH", None
    try:
        proc = subprocess.run(["docker", "version", "--format",
                               "client {{.Client.Version}} server {{.Server.Version}} api {{.Server.APIVersion}}"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"docker version did not answer: {exc}", None
    if proc.returncode != 0:
        return "no daemon answers: " + (proc.stderr.strip().splitlines() or ["?"])[-1], None
    present = subprocess.run(["docker", "image", "inspect", PRESENT_IMAGE], capture_output=True, text=True)
    if present.returncode != 0:
        pull = subprocess.run(["docker", "pull", PRESENT_IMAGE], capture_output=True, text=True, timeout=300)
        if pull.returncode != 0:
            return (f"{PRESENT_IMAGE} is absent and cannot be pulled (a firewalled daemon, the H200's shape): "
                    + (pull.stderr.strip().splitlines() or ["?"])[-1]), None
    return "", proc.stdout.strip()


def _setup(kind: str, name: str) -> None:
    if kind == "created":
        subprocess.run(["docker", "create", "--name", name, PRESENT_IMAGE, "true"], check=True, capture_output=True)
    elif kind == "running":
        subprocess.run(["docker", "run", "-d", "--name", name, PRESENT_IMAGE, "sleep", "60"], check=True, capture_output=True)


def test_cli_shapes_match_the_real_cli():
    """The measurement: every recorded shape re-taken against the CLI on
    PATH and a daemon that answers (the workstation, the CI runner). Skipped
    with the reason where nothing answers — never faked."""
    reason, version = _daemon()
    if reason:
        pytest.skip(f"cli_shapes.json not re-measured here — {reason}")
    name = f"gsj-shape-{os.getpid()}"
    mismatches = []
    try:
        for key, shape in CLI_SHAPES["shapes"].items():
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            _setup(shape["setup"], name)
            subs = {"name": {"image-absent": ABSENT_IMAGE, "image-present": PRESENT_IMAGE}.get(shape["setup"], name)}
            argv = [a.replace("{name}", subs["name"]) for a in shape["argv"]]
            live = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            expected_err = shape["stderr"].replace("{name}", subs["name"])
            ok_out = (re.fullmatch(shape["stdout_re"], live.stdout, re.S) is not None if "stdout_re" in shape
                      else live.stdout == shape["stdout"].replace("{name}", subs["name"]))
            if not (live.returncode == shape["returncode"] and ok_out and live.stderr == expected_err):
                mismatches.append((key, {"returncode": live.returncode, "stdout": live.stdout, "stderr": live.stderr},
                                   {"returncode": shape["returncode"], "stdout": shape.get("stdout", shape.get("stdout_re")),
                                    "stderr": expected_err}))
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    assert not mismatches, (f"{CLI_SHAPES_PATH.name} (measured on docker {CLI_SHAPES['measured']['docker_client']}) "
                            f"disagrees with the CLI here ({version}) — re-measure the file AND re-read the code that "
                            f"branches on these shapes (rule 10): {mismatches}")
