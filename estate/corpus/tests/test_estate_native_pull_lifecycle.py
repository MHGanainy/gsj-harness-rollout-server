"""Native stdout must retain image_pull's error and process boundaries.

These are real controlled Python children, not invented Docker CLI output.
pytest and stdlib subprocess provide capture and process ownership.
"""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

ESTATE_PY = Path(__file__).resolve().parents[2] / "estate.py"
IMAGE = "registry.invalid/example@sha256:" + "ab" * 32


def load_estate():
    source = os.environ.get("GSJ_TEST_ESTATE_SOURCE", str(ESTATE_PY))
    spec = importlib.util.spec_from_file_location("estate_native_pull", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def child_pull(monkeypatch, tmp_path):
    est, owned, calls, readers = load_estate(), [], [], []

    def reader(*args, **kwargs):
        thread = threading.Thread(*args, **kwargs)
        readers.append(thread)
        return thread

    monkeypatch.setattr(est, "threading", SimpleNamespace(Thread=reader))

    def prepare(code, transform=lambda proc: None):
        script = tmp_path / "controlled-child.py"
        script.write_text(code, encoding="utf-8")
        def launch(cmd, **kw):
            calls.append((cmd, kw))
            proc = subprocess.Popen([sys.executable, str(script)], text=True,
                                    start_new_session=True, **kw)
            owned.append(proc)
            transform(proc)
            return proc
        monkeypatch.setattr(est, "popen", launch)
        return est, owned, calls

    yield prepare
    for proc in owned:
        # The direct child may already be reaped while descendants retain pipes.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        subprocess.Popen.wait(proc, timeout=3)
    for thread in readers:
        thread.join(timeout=3)
        assert not thread.is_alive(), "owned stderr reader survived group cleanup"
    for proc in owned:
        # Never close a buffered stream while its reader can hold the read lock.
        if proc.stderr:
            proc.stderr.close()
        if proc.stdout:
            proc.stdout.close()


@pytest.mark.parametrize("raw, code, expected", [
    (b"", 0, ""),
    (b"controlled diagnostic\n", 17, "controlled diagnostic\n"),
    (b"one\r\ntwo\rthree\n", 0, "one\ntwo\nthree\n"),
    (("controlled diagnostic: Ω\n" * 8192).encode(), 0, "controlled diagnostic: Ω\n" * 8192),
    (b"controlled prefix\n\xffinvalid UTF-8\n", 0, ""),
], ids=["empty", "diagnostic", "newlines", "large", "invalid"])
def test_captured_stderr_return_and_text_contract(child_pull, raw, code, expected):
    est, owned, calls = child_pull(
        f"import os; os.write(2, {raw!r}); raise SystemExit({code})")
    result = est.image_pull(IMAGE, "test")
    assert (result.args, result.returncode, result.stdout, result.stderr) == (
        ["docker", "pull", IMAGE], code, "", expected)
    assert owned[0].poll() == code


def test_native_stdout_and_inherited_environment_cwd(child_pull, monkeypatch, tmp_path, capfd):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GSJ_NATIVE_PULL_TEST", "owned-value")
    monkeypatch.setenv("DOCKER_DEFAULT_PLATFORM", "controlled-platform-marker")
    est, _, calls = child_pull(
        "import json,os; from pathlib import Path; "
        "Path('observed.json').write_text(json.dumps([os.getcwd(), "
        "os.environ['GSJ_NATIVE_PULL_TEST'], os.environ['DOCKER_DEFAULT_PLATFORM']])); "
        "os.write(1,b'controlled stdout\\n')")
    assert est.image_pull(IMAGE, "test").stdout == ""
    assert calls == [(["docker", "pull", IMAGE], {"stderr": subprocess.PIPE})]
    assert "controlled stdout\n" in capfd.readouterr().out
    assert json.loads((tmp_path / "observed.json").read_text()) == [
        str(tmp_path), "owned-value", "controlled-platform-marker"]


def test_launch_oserror_is_the_existing_completed_process(monkeypatch, tmp_path):
    est = load_estate()
    missing = str(tmp_path / "missing-executable")
    def launch(cmd, **kw):
        return subprocess.Popen([missing], text=True, **kw)
    monkeypatch.setattr(est, "popen", launch)
    try:
        subprocess.Popen([missing], text=True, stderr=subprocess.PIPE)
    except OSError as exc:
        expected = f"{type(exc).__name__}: {exc}"
    result = est.image_pull(IMAGE, "test")
    assert (result.args, result.returncode, result.stdout, result.stderr) == (
        ["docker", "pull", IMAGE], 1, "", expected)


@pytest.mark.parametrize("error", [OSError, ValueError])
def test_stderr_read_failures_keep_the_original_suppression(child_pull, error):
    def inject(proc):
        def fail_read():
            raise error("controlled injected read failure")
        proc.stderr.read = fail_read
    est, owned, _ = child_pull("import time; time.sleep(0.05)", inject)
    started = time.monotonic()
    result = est.image_pull(IMAGE, "test")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert owned[0].poll() == 0
    assert time.monotonic() - started < 2


def test_wait_exception_propagates_without_killing_the_child(child_pull):
    def inject(proc):
        def fail_wait(*args, **kw):
            raise RuntimeError("controlled injected wait failure")
        proc.wait = fail_wait
    est, owned, _ = child_pull("import time; time.sleep(30)", inject)
    with pytest.raises(RuntimeError, match="controlled injected wait failure"):
        est.image_pull(IMAGE, "test")
    assert owned[0].poll() is None


def run_worker(directory, scenario, *, send_signal=None, target="parent"):
    """Bound the observation independently; own the complete worker process group."""
    argv = [sys.executable, __file__, scenario, str(directory), target]
    observation = {"argv": argv, "scenario": scenario, "target": target,
                   "signal": send_signal, "outer_wait_seconds": 22}
    with (directory / "stdout").open("wb") as out, (directory / "stderr").open("wb") as err:
        proc = subprocess.Popen(argv,
                                stdout=out, stderr=err, start_new_session=True)
        observation["owned_pgid"] = proc.pid
        try:
            child_pid = None
            if send_signal is not None:
                deadline = time.monotonic() + 5
                markers = [directory / "ready", directory / "wait-entered"]
                while not all(p.exists() for p in markers) and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert all(p.exists() for p in markers), (directory / "stderr").read_text()
                child_pid = int((directory / "ready").read_text())
                observation["child_pid"] = child_pid
                if target == "group":
                    os.killpg(proc.pid, send_signal)
                else:
                    os.kill(child_pid if target == "child" else proc.pid, send_signal)
            # Covers direct-child delay + ten-second grace, with an outer margin.
            returncode = proc.wait(timeout=22)
            observation["worker_returncode"] = returncode
            result_path = directory / "result.json"
            result = json.loads(result_path.read_text()) if result_path.exists() else {}
            result["worker_returncode"] = returncode
            if send_signal == signal.SIGTERM:
                if target == "parent":
                    # Unlike kill(pid, 0), an acknowledgement excludes a zombie.
                    os.kill(child_pid, signal.SIGUSR1)
                    deadline = time.monotonic() + 3
                    while not (directory / "alive").exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    assert (directory / "alive").read_text() == "alive"
                    assert not (directory / "terminated").exists()
                    result["child_alive_before_cleanup"] = True
                else:
                    deadline = time.monotonic() + 3
                    while not (directory / "terminated").exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    assert (directory / "terminated").read_text() == str(signal.SIGTERM)
                    result["child_received_sigterm"] = True
            observation["result"] = result
            return result
        finally:
            # Always kill the group, including after the worker was reaped.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                observation["cleanup_group_signal"] = "SIGKILL"
            except ProcessLookupError:
                observation["cleanup_group_signal"] = "already absent"
            subprocess.Popen.wait(proc, timeout=3)
            (directory / "observer.json").write_text(json.dumps(observation))


@pytest.mark.parametrize("group", [False, True])
def test_sigint_propagates_and_preserves_child_lifetime(tmp_path, group):
    """Parent-only SIGINT leaves the child; terminal group SIGINT reaches both."""
    result = run_worker(tmp_path, "signal", send_signal=signal.SIGINT,
                        target="group" if group else "parent")
    assert result["worker_returncode"] == 0
    assert result["exception"] == "KeyboardInterrupt"
    assert result["child_returncode"] == (-signal.SIGINT if group else None)


@pytest.mark.parametrize("target", ["child", "parent", "group"])
def test_sigterm_keeps_existing_parent_and_child_process_boundaries(tmp_path, target):
    result = run_worker(tmp_path, "signal", send_signal=signal.SIGTERM, target=target)
    if target == "child":
        assert (result["worker_returncode"], result["returncode"], result["stdout"], result["stderr"]) == (
            0, -signal.SIGTERM, "", "")
        assert result["child_received_sigterm"]
    else:
        assert result["worker_returncode"] == -signal.SIGTERM
        assert "returncode" not in result and "exception" not in result
        assert result["child_alive_before_cleanup" if target == "parent" else "child_received_sigterm"]


def test_stderr_from_descendant_with_both_streams_retains_baseline_diagnostics(tmp_path):
    """The old stdout join gave this stderr reader time to receive the late error.

    Both original diagnostics remain required under the approved stderr grace.
    """
    result = run_worker(tmp_path, "both-six")
    assert (result["worker_returncode"], result["returncode"], result["stdout"], result["stderr"]) == (
        0, 0, "", "controlled diagnostic before child exit\n"
                  "controlled diagnostic after parent exit\n")


# These observations exercise the explicitly approved replacement grace policy.
@pytest.mark.parametrize("scenario", ["stderr-six", "delayed-child"])
def test_stderr_grace_retains_late_diagnostics_after_wait_returns(tmp_path, scenario):
    result = run_worker(tmp_path, scenario)
    assert (result["worker_returncode"], result["returncode"], result["stdout"], result["stderr"]) == (
        0, 0, "", "controlled diagnostic before child exit\n"
                  "controlled diagnostic after parent exit\n")
    assert 5.5 <= result["after_wait_s"] < 9
    if scenario == "delayed-child":
        assert result["elapsed_s"] >= 11.5  # Grace starts after wait, not launch.


@pytest.mark.parametrize("scenario, stderr", [
    ("stdout-only", "controlled diagnostic before child exit\n"),
    ("quick", "controlled diagnostic before child exit\n"),
    ("stderr-eof-first", "controlled diagnostic before child exit\n"),
])
def test_stderr_eof_returns_without_a_separate_stdout_wait(tmp_path, scenario, stderr):
    result = run_worker(tmp_path, scenario)
    assert (result["worker_returncode"], result["returncode"], result["stdout"], result["stderr"]) == (
        0, 0, "", stderr)
    assert result["after_wait_s"] < 2
    if scenario == "stderr-eof-first":
        assert result["elapsed_s"] >= 5.5  # Ordinary child wait remains authoritative.
    else:
        assert result["elapsed_s"] < 3


@pytest.mark.parametrize("scenario", ["stderr-open", "bytes-before-late-eof"])
def test_stderr_grace_is_bounded_and_does_not_return_partial_reads(tmp_path, scenario):
    result = run_worker(tmp_path, scenario)
    assert (result["worker_returncode"], result["returncode"], result["stdout"], result["stderr"]) == (
        0, 0, "", "")
    assert 9.5 <= result["after_wait_s"] < 13
    if scenario == "bytes-before-late-eof":
        assert (tmp_path / "late-bytes-written").read_text() == "written"


def worker(directory, scenario, target):
    est, owned = load_estate(), []
    if scenario == "signal":
        code = ("import os,signal,time\nfrom pathlib import Path\n"
                "def terminated(number, frame):\n"
                f"    Path({str(directory / 'terminated')!r}).write_text(str(number))\n"
                "    signal.signal(number, signal.SIG_DFL)\n"
                "    os.kill(os.getpid(), number)\n"
                "signal.signal(signal.SIGTERM, terminated)\n"
                f"signal.signal(signal.SIGUSR1, lambda number, frame: Path({str(directory / 'alive')!r}).write_text('alive'))\n"
                f"ready = Path({str(directory / 'ready')!r})\n"
                "ready.with_suffix('.tmp').write_text(str(os.getpid()))\n"
                "ready.with_suffix('.tmp').replace(ready)\ntime.sleep(30)\n")
    elif scenario in ("quick", "stderr-eof-first"):
        code = ("import os,time\n"
                "os.write(2,b'controlled diagnostic before child exit\\n')\n"
                "os.close(2)\n" + ("time.sleep(6)\n" if scenario == "stderr-eof-first" else ""))
    else:
        delay = 12 if scenario == "delayed-child" else 6
        close_stdout = "    os.close(1)\n" if scenario != "both-six" else ""
        if scenario == "stdout-only":
            descendant = "    os.close(2)\n    time.sleep(30)\n"
        elif scenario == "stderr-open":
            descendant = close_stdout + "    time.sleep(30)\n"
        elif scenario == "bytes-before-late-eof":
            descendant = (close_stdout + "    time.sleep(6)\n"
                          "    os.write(2,b'controlled late bytes without EOF\\n')\n"
                          f"    Path({str(directory / 'late-bytes-written')!r}).write_text('written')\n"
                          "    time.sleep(30)\n")
        else:
            descendant = (close_stdout + f"    time.sleep({delay})\n"
                          "    os.write(2,b'controlled diagnostic after parent exit\\n')\n")
        code = ("import os,time\n"
                "from pathlib import Path\n"
                "if os.fork() == 0:\n" + descendant +
                "    os._exit(0)\n"
                "os.write(2,b'controlled diagnostic before child exit\\n')\n" +
                ("time.sleep(6)\n" if scenario == "delayed-child" else ""))
    script = directory / "controlled-child.py"
    script.write_text(code, encoding="utf-8")
    wait_returned = []

    def launch(cmd, **kw):
        child = subprocess.Popen([sys.executable, str(script)], text=True, **kw)
        owned.append(child)
        ordinary_wait = child.wait

        def wait(*args, **kwargs):
            if scenario == "signal":
                (directory / "wait-entered").write_text("entered")
            result = ordinary_wait(*args, **kwargs)
            wait_returned.append(time.monotonic())
            return result

        child.wait = wait
        return child

    est.popen = launch
    started = time.monotonic()
    observation = {"source": str(Path(est.__file__).resolve()),
                   "source_sha256": hashlib.sha256(Path(est.__file__).read_bytes()).hexdigest(),
                   "python": sys.executable, "python_version": sys.version,
                   "platform": platform.platform(), "machine": platform.machine(),
                   "scenario": scenario, "target": target}
    try:
        result = est.image_pull(IMAGE, "test")
        observation.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                           elapsed_s=time.monotonic() - started,
                           after_wait_s=time.monotonic() - wait_returned[-1])
    except BaseException as exc:
        # Group SIGINT reaches both processes; reap it before observing status.
        # Parent-only SIGINT must leave its child alive until the outer cleanup.
        child_returncode = (subprocess.Popen.wait(owned[0], timeout=3)
                            if target == "group" else owned[0].poll())
        observation.update(exception=type(exc).__name__, child_returncode=child_returncode)
    (directory / "result.json").write_text(json.dumps(observation))


if __name__ == "__main__":
    worker(Path(sys.argv[2]), sys.argv[1], sys.argv[3])
