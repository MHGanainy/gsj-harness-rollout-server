"""CP-96: what round four found in estate.py — the readiness probe as a class
(a `docker exec` into the run's own container, a named fallback that a
`finally` removes, a timeout that degrades instead of aborting), the clocks
(a monotonic budget, the measured wait printed beside it, a host sleep made
visible), the embed that reported nothing while it ran (the service's
`build` block read into the poll line, a heartbeat while nothing changes),
a `--rebuild` re-run that attaches instead of restarting, the verify
headline counting skips apart,
and the help text that says how to choose a gateway host.

Hermetic — no Docker daemon, no estate: the `run` and `http` seams
are faked, the clocks are faked where a budget is under test."""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import cli_shape

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"
HARNESS = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp96", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "PH", module.Phases())
    return module


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clocks(monkeypatch, est, *, step: float = 3.0, sleep_at: tuple | None = None) -> dict:
    """Two fake clocks: this process's (monotonic) and the wall's. Every
    `time.sleep` advances both by the slept amount; `sleep_at=(n, secs)`
    additionally jumps the WALL clock by `secs` on the n-th sleep — a host
    that slept. The startup tests' pattern, with the second clock."""
    state = {"mono": 100.0, "wall": 1_000_000.0, "sleeps": 0}
    monkeypatch.setattr(est.time, "monotonic", lambda: state["mono"])
    monkeypatch.setattr(est.time, "time", lambda: state["wall"])

    def sleep(seconds):
        state["mono"] += seconds
        state["wall"] += seconds
        state["sleeps"] += 1
        if sleep_at and state["sleeps"] == sleep_at[0]:
            state["wall"] += sleep_at[1]

    monkeypatch.setattr(est.time, "sleep", sleep)
    return state


# ------------------------------------------------- the probe, as a class

def no_hosts_line(monkeypatch, est):
    monkeypatch.setattr(est.socket, "gethostbyname", lambda name: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5", "192.168.1.9"])


def test_probe_dial_execs_into_the_running_retrieval_container_and_creates_nothing(est, monkeypatch):
    """b2 (round four): the old probe `docker run --rm`'d the 731 MiB sandbox
    image to make four HTTP calls, and on a copy-on-create daemon the
    create alone outlasted its budget. The dial now runs inside the run's
    own retrieval container: nothing is created, nothing can leak.

    CP-99 (round five): the dial's vocabulary is three-valued now — the
    sentinel's nonce, a foreign listener, or nothing — because b1's probe
    read a foreign listener's HTTP answer as the gateway address being
    reachable and wrote it as `measured:`."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        assert cmd[:2] == ["docker", "exec"] and cmd[2] == "gsj-canary-mcp" and cmd[3] == "python"
        assert kw.get("timeout") == est.PROBE_EXEC_TIMEOUT_S
        return subprocess.CompletedProcess(cmd, 0, "10.0.0.5 NOTHING\n192.168.1.9 SENTINEL\n", "")

    monkeypatch.setattr(est, "run", fake_run)
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5", "192.168.1.9"], 18299,
                                      "gsj-canary-mcp", HARNESS, "gsj-probe-abc123")
    assert failure is None
    # CP-99: the dial says WHAT answered, not merely that something did
    assert results == [{"candidate": "10.0.0.5", "container": "nothing"},
                       {"candidate": "192.168.1.9", "container": "our sentinel"}]
    assert len(calls) == 1 and not any(c[:2] == ["docker", "run"] or c[:2] == ["docker", "rm"]
                                       for c in calls)
    dial = calls[0][-1]
    assert "urlopen('http://%s:18299/' % h, timeout=3)" in dial and '"192.168.1.9"' in dial


def test_probe_fallback_run_is_named_and_removed_in_a_finally_when_it_times_out(est, monkeypatch, capsys):
    """a2 found `friendly_hopper`, b2 `eloquent_dijkstra`: a `docker run --rm`
    killed by subprocess never fires its --rm. With no container of the
    run's own to exec into, the fallback run is NAMED and `docker rm -f`'d
    whatever happens — and its timeout comes back as a sentence, not a
    traceback."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            assert "--rm" not in cmd and cmd[2] == "--name" and cmd[3].startswith("gsj-probe-")
            assert kw.get("timeout") == est.PROBE_RUN_TIMEOUT_S
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        assert cmd[:3] == ["docker", "rm", "-f"], cmd
        return cli_shape("docker rm -f <present>", cmd, name=cmd[3])   # the CLI names what it removed

    monkeypatch.setattr(est, "run", fake_run)
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5"], 18299, None, HARNESS,
                                      "gsj-probe-abc123")
    assert results == []
    assert failure.startswith("timed out after 120 s via a `docker run` of " + HARNESS)
    assert "copy-on-create" in failure and "still creating" not in failure
    names = [c[3] for c in calls if c[:2] == ["docker", "run"]]
    assert [c for c in calls if c[:3] == ["docker", "rm", "-f"]] == [["docker", "rm", "-f", names[0]]]


def test_reap_container_keeps_trying_while_the_daemon_is_still_creating_it(est, monkeypatch, capsys):
    """CP-96's own proof found the race: a `docker rm -f` a second after the
    killed client found nothing, and the container turned up `Created` four
    minutes later when the vfs copy ended. The reaper retries for a bound
    and, past it, the failure names the container and the command.

    CP-98 (row 100): the fake here used to answer exit 1 while the container
    was missing — the real CLI answers exit 0 with `No such container` on
    STDERR, and CP-96's loop read exit 0 as removed, so the bound this test
    proved never ran on any daemon. The fake now takes the CLI's measured
    shape (cli_shapes.json); against CP-96's implementation this test fails
    on the call count (one call, not three) and on the bound (True, not
    False)."""
    monkeypatch.setattr(est.time, "sleep", lambda s: None)
    answers = iter(["docker rm -f <missing>", "docker rm -f <missing>", "docker rm -f <present>"])
    calls = []
    monkeypatch.setattr(est, "run", lambda cmd, **kw: (calls.append(cmd),
                                                       cli_shape(next(answers), cmd, name=cmd[3]))[1])
    assert est.reap_container("gsj-probe-1", wait_s=60) is True
    assert calls == [["docker", "rm", "-f", "gsj-probe-1"]] * 3
    clock = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(est.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape("docker rm -f <missing>", cmd, name=cmd[3]))
    assert est.reap_container("gsj-probe-2", wait_s=30) is False

    def fake_run(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return cli_shape("docker rm -f <missing>", cmd, name=cmd[3])

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "reap_container", lambda name, wait_s=30: False)
    results, failure = est.probe_dial("gsj-canary-net", ["10.0.0.5"], 18299, None, HARNESS,
                                      "gsj-probe-abc123")
    assert "the daemon is still creating gsj-probe-" in failure and "`docker rm -f gsj-probe-" in failure


def test_gateway_host_degrades_on_a_probe_that_cannot_run_naming_the_flag_and_the_candidates(
        est, monkeypatch, capsys):
    """b2 lost 23 minutes of successful work to an unhandled TimeoutExpired one
    file short of rollout.yaml. The value has a flag and a default rule: a
    probe that cannot run degrades to the first candidate, labelled
    unmeasured, and says --gateway-host, what it was about to try, and that
    the run is resumable."""
    no_hosts_line(monkeypatch, est)
    monkeypatch.setattr(est, "probe_dial", lambda *a, **k: ([], "timed out after 120 s via a `docker run` of x — on a copy-on-create storage driver (vfs) creating a container from a large image alone can take minutes"))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    host, how, results = est.gateway_host("gsj-canary-net", free_port(), None, HARNESS)
    assert host == "10.0.0.5" and results == []
    assert how == "10.0.0.5 = a host IPv4 (UNMEASURED — the probe timed out after 120 s via a `docker run` of x)"
    out = capsys.readouterr().out
    assert "WARNING" in out and "the gateway-host probe could not run — timed out after 120 s" in out
    assert "--gateway-host <address>" in out and "['10.0.0.5', '192.168.1.9']" in out
    assert "the run is resumable" in out and "Traceback" not in out


def test_gateway_host_prefers_the_exec_target_and_returns_the_measured_answer(est, monkeypatch, capsys):
    no_hosts_line(monkeypatch, est)
    seen = {}

    def fake_dial(network, candidates, gport, exec_container, probe_image, nonce):
        seen.update(exec_container=exec_container, probe_image=probe_image, candidates=candidates)
        # CP-99: 127.0.0.1 is the candidate whose HOST leg this test lets run for
        # real — the sentinel is bound on 0.0.0.0 of this process, so the host
        # dial reaches it and the nonce comes back. Nothing is faked below the
        # dial the container would have made.
        return [{"candidate": "10.0.0.5", "container": "nothing"},
                {"candidate": "127.0.0.1", "container": "our sentinel"}], None

    monkeypatch.setattr(est, "probe_dial", fake_dial)
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    host, how, results = est.gateway_host("gsj-canary-net", free_port(), None, HARNESS,
                                          recorded=None, exec_container="gsj-canary-mcp")
    assert host == "127.0.0.1" and how.startswith("measured: this run's own sentinel answered on :")
    assert "from a container on 'gsj-canary-net' and from this host" in how
    assert results == [{"candidate": "10.0.0.5", "container": "nothing",
                        "host": "not dialed", "reachable": False},
                       {"candidate": "127.0.0.1", "container": "our sentinel",
                        "host": "our sentinel", "reachable": True}]
    assert seen["exec_container"] == "gsj-canary-mcp" and seen["probe_image"] == HARNESS
    assert "WARNING" not in capsys.readouterr().out


def test_gateway_host_with_nothing_to_dial_from_labels_the_candidate_by_its_origin(est, monkeypatch, capsys):
    """b1: `--skip-sandbox-image` wrote `http://host.docker.internal:8200 (first
    host IPv4 (UNMEASURED))` — a hostname labelled as an IPv4. The label now
    names what the candidate is, and the probe no longer depends on the
    sandbox image when the run has a retrieval container of its own.

    CP-99: this host offers no IPv4 of its own here, so the resolvable name
    is the only candidate and still the one degraded to. Its ORDER against a
    real address moved this checkpoint (round five's b1 lost a working
    compose gateway to a name that merely resolved) and is asserted in
    test_estate_cp99_gateway.py."""
    monkeypatch.setattr(est, "host_ipv4s", lambda: [])
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(est.socket, "gethostbyname", lambda name: "192.168.65.254")
    host, how, results = est.gateway_host("gsj-canary-net", free_port(), None, None)
    assert host == "host.docker.internal"
    assert how == ("host.docker.internal = the name this host resolves (an /etc/hosts line) "
                   "(UNMEASURED — no container to probe from)")
    assert "IPv4" not in how
    out = capsys.readouterr().out
    assert "no container to dial from (the retrieval service is adopted and the sandbox image is absent)" in out
    assert "--help says how to choose one" in out


def test_gateway_host_measured_negative_is_still_a_refusal_that_names_the_resume(est, monkeypatch, capsys):
    no_hosts_line(monkeypatch, est)
    monkeypatch.setattr(est, "probe_dial", lambda *a, **k: ([{"candidate": "10.0.0.5", "container": "nothing"},
                                                             {"candidate": "192.168.1.9", "container": "nothing"}], None))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    with pytest.raises(SystemExit) as exc:
        est.gateway_host("gsj-canary-net", free_port(), None, HARNESS, exec_container="gsj-canary-mcp")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "no host address reached this probe's sentinel" in err
    assert "10.0.0.5: nothing from the container" in err and "resumable" in err


def test_gateway_host_explicit_is_never_probed(est, monkeypatch):
    monkeypatch.setattr(est, "probe_dial", lambda *a, **k: pytest.fail("probed"))
    assert est.gateway_host("n", 1, "172.19.0.1", HARNESS) == ("172.19.0.1", "--gateway-host (not probed)", [])


def test_container_running_reads_the_daemon(est, monkeypatch):
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape("docker inspect --format {{.State.Running}} <running>", cmd, name="x"))
    assert est.container_running("x")
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape("docker inspect --format {{.State.Running}} <created>", cmd, name="x"))
    assert not est.container_running("x")
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape("docker inspect --format {{.State.Running}} <missing>", cmd, name="x"))
    assert not est.container_running("x")


# ------------------------------------------------------------ the clocks

def waiting(monkeypatch, est, health):
    mcp = est.Mcp("http://127.0.0.1:9", "http://mcp:8790", "fixture-secret", "created")
    readings = iter(health)
    monkeypatch.setattr(mcp, "health", lambda: next(readings, health[-1]))
    monkeypatch.setattr(est, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, '{"Status": "running", "ExitCode": 0}', ""))
    return mcp


INDEXING = {"state": "indexing", "progress": {"case_a": {"done": True, "embedded": True},
                                              "case_b": {"done": True, "embedded": True}}}


def test_wait_ready_budget_is_monotonic_and_the_refusal_prints_what_it_waited(est, monkeypatch, capsys):
    """a2's overnight run: a wall-clock deadline on a host that slept fired on
    wake and printed the configured 1800 s as if it had been enforced. The
    budget is this process's clock now; the wall is read beside it so the
    sleep shows; the refusal prints both."""
    state = clocks(monkeypatch, est, sleep_at=(2, 30_000.0))
    mcp = waiting(monkeypatch, est, [INDEXING])
    with pytest.raises(SystemExit) as exc:
        mcp.wait_ready(20, "cold start", container="gsj-canary-mcp")
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    # 20 s of budget at 3 s per poll: seven polls, 21 s waited — not a wake-up
    assert state["mono"] - 100.0 == pytest.approx(21.0)
    assert "did not reach state=ready within the 20 s budget (--ingest-timeout)" in err
    assert "waited 21 s on this process's clock (the wall clock advanced 30021 s)" in err
    assert "last: indexing: 2/2 cases fetched, 2/2 embedded" in err
    assert "re-run `up` WITHOUT --rebuild" in err and "embed from zero" in err
    assert "the wall clock advanced 30006 s while this process waited 6 s" in out
    assert "the host slept or was paused for ~30000 s" in out
    assert "counts only the time this process waited" in out


def test_wait_ready_reads_the_build_block_so_a_decisions_embed_is_visible(est, monkeypatch, capsys):
    """While a decisions drop embeds, `progress` names only the case
    collections (both done) and the poll line read as finished — a2
    diagnosed a healthy service as wedged and restarted it. The service
    already publishes per-batch `build` progress (state.py, CP-77): read it."""
    clocks(monkeypatch, est)
    stale = {**INDEXING, "build": {"collection": "case_b", "vectors": 57, "total": 57,
                                   "batch": 1, "batches": 1}}      # the last case's last batch
    building = {**INDEXING, "build": {"collection": "decisions", "vectors": 2000, "total": 7219,
                                      "batch": 2, "batches": 8}}
    ready = {"state": "ready", "progress": INDEXING["progress"]}
    mcp = waiting(monkeypatch, est, [INDEXING, stale, building, ready])
    assert mcp.wait_ready(1800, "cold start", container="gsj-canary-mcp") == ready
    out = capsys.readouterr().out
    assert ("cold start: indexing: 2/2 cases fetched, 2/2 embedded; the service is still working "
            "(no batch has landed yet)") in out
    assert ("2/2 embedded; the service is still working (the next collection has not reported a "
            "batch yet)") in out and "building case_b" not in out
    assert "indexing: 2/2 cases fetched, 2/2 embedded; building decisions: batch 2/8 (2000/7219 vectors)" in out
    assert "cold start: ready: 2/2 cases fetched, 2/2 embedded — waited 9 s of the 1800 s budget" in out


def test_wait_ready_heartbeats_with_the_measured_wait_when_nothing_changes(est, monkeypatch, capsys):
    """The loop printed only on change, so a long embed — or a resumed host —
    emitted nothing. Once a heartbeat interval passes unchanged, the line is
    said again with what has been waited of what was budgeted."""
    clocks(monkeypatch, est)
    monkeypatch.setattr(est, "PULL_HEARTBEAT_S", 6.0)
    ready = {"state": "ready", "progress": INDEXING["progress"]}
    mcp = waiting(monkeypatch, est, [INDEXING] * 6 + [ready])
    mcp.wait_ready(1800, "cold start", container="gsj-canary-mcp")
    out = capsys.readouterr().out
    beats = [ln for ln in out.splitlines() if "still indexing: 2/2 cases fetched" in ln]
    assert beats and all("waited" in b and "of the 1800 s budget" in b for b in beats), out


def test_wait_ready_reads_the_container_log_once_per_twenty_seconds_not_every_poll(est, monkeypatch, capsys):
    """Three things made the poll heavier on a contended host: a 5 s health
    read that took a slow service for an unreachable one, and a docker
    inspect + docker logs subprocess on EVERY poll after 20 s. The tail is
    read once per 20 s now; the health read has 15 s."""
    clocks(monkeypatch, est)
    commands = []

    def fake_run(cmd, **kw):
        commands.append(cmd[:2])
        return subprocess.CompletedProcess(cmd, 0, '{"Status": "running", "ExitCode": 0}' if cmd[1] == "inspect" else "", "")

    monkeypatch.setattr(est, "run", fake_run)
    mcp = est.Mcp("http://127.0.0.1:9", "http://mcp:8790", "s", "created")
    monkeypatch.setattr(mcp, "health", lambda: None)
    with pytest.raises(SystemExit):
        mcp.wait_ready(60, "cold start", container="gsj-canary-mcp")
    logs = [c for c in commands if c == ["docker", "logs"]]
    assert 1 <= len(logs) <= 3, commands       # 60 s / 3 s = 20 polls; ~2 tails, not ~13
    assert est.HEALTH_TIMEOUT_S == 15.0


def test_forgejo_healthz_wait_is_monotonic_and_the_refusal_prints_what_it_waited(est, monkeypatch, capsys):
    state = clocks(monkeypatch, est, step=2.0, sleep_at=(2, 5_000.0))
    monkeypatch.setattr(est, "FORGEJO_HEALTHZ_BUDGET_S", 10.0)

    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, "sha256:abc [] linux/arm64", "")
        if cmd[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected docker call {cmd}")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "http", lambda *a, **k: (None, "ConnectionRefusedError"))
    monkeypatch.setattr(est, "write_compose", lambda *a, **k: None)
    r = est.Run("canary")
    r.dir.mkdir()
    with pytest.raises(SystemExit) as exc:
        est.create_forgejo(r.dir, r, 3000, True, "gsj-canary-net", False,
                           "codeberg.org/forgejo/forgejo:16.0.3")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Forgejo did not answer /api/healthz within the 10 s budget" in err
    assert "waited 10 s on this process's clock (the wall clock advanced 5010 s)" in err
    assert "the run is resumable" in err
    assert state["mono"] - 100.0 == pytest.approx(10.0)


def test_rebuild_in_progress_reads_the_running_container_and_its_health(est, monkeypatch):
    """A --rebuild whose previous attempt timed out at the wait used to
    recreate the container and embed from zero on every re-run."""
    monkeypatch.setattr(est, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "true\n", ""))
    monkeypatch.setattr(est, "http", lambda *a, **k: (200, {"state": "indexing"}))
    assert est.rebuild_in_progress("http://127.0.0.1:8790", "gsj-canary-mcp")
    monkeypatch.setattr(est, "http", lambda *a, **k: (200, {"state": "ready"}))
    assert not est.rebuild_in_progress("http://127.0.0.1:8790", "gsj-canary-mcp")
    monkeypatch.setattr(est, "http", lambda *a, **k: (200, {"state": "indexing"}))
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape("docker inspect --format {{.State.Running}} <missing>", cmd, name="gsj-canary-mcp"))
    assert not est.rebuild_in_progress("http://127.0.0.1:8790", "gsj-canary-mcp")


# ------------------------------------------------- the verify headline

VERIFY_OUT = """== verify ==
case           split  where          result  detail
case_delivery  train  main/timestep-1  PASS    pages, contract files OK
(corpus)       -      mcp            PASS    SKIPPED (--skip-ingest)
(corpus)       -      taskbank       PASS    4 rows
== verify: PASS (8 pass / 0 fail) ==
"""


def test_verify_headline_counts_a_skip_apart_from_a_pass(est):
    """b1: `PASS (8 pass / 0 fail)` with `mcp — SKIPPED (--skip-ingest)` among
    the rows; the detail row was honest, the headline was not."""
    fixed = est.verify_headline(VERIFY_OUT)
    assert "== verify: PASS (7 pass / 1 skipped / 0 fail) ==" in fixed
    assert fixed.count("== verify:") == 1 and "SKIPPED (--skip-ingest)" in fixed
    plain = VERIFY_OUT.replace("SKIPPED (--skip-ingest)", "census 3 pages")
    assert est.verify_headline(plain) == plain
    failing = VERIFY_OUT.replace("PASS (8 pass / 0 fail)", "FAIL (7 pass / 1 fail)")
    assert "== verify: FAIL (6 pass / 1 skipped / 1 fail) ==" in est.verify_headline(failing)


def test_run_phase_captures_verify_and_reemits_it_corrected_streaming_every_other_phase(est, monkeypatch, capsys):
    seen = []

    def fake_run(cmd, **kw):
        seen.append(kw.get("capture_output"))
        return subprocess.CompletedProcess(cmd, 0, VERIFY_OUT if kw.get("capture_output") else None,
                                           "one warning\n" if kw.get("capture_output") else None)

    monkeypatch.setattr(est, "run", fake_run)
    est.run_phase(["x", "scaffold"], {}, "scaffold")
    proc = est.run_phase(["x", "verify"], {}, "verify")
    assert seen == [None, True] and proc.returncode == 0
    out, err = capsys.readouterr()
    assert "== verify: PASS (7 pass / 1 skipped / 0 fail) ==" in out and "(8 pass" not in out
    assert err == "one warning\n"


# ------------------------------------------------------------ the help

def test_up_help_says_how_to_choose_a_gateway_host_and_what_skip_sandbox_image_means_now():
    """b2's finding 14 and b1's finding 2, in the help text."""
    proc = subprocess.run([sys.executable, str(ESTATE_PY), "up", "--help"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    text = " ".join(proc.stdout.split())
    assert "How to choose one when the probe cannot run" in text
    assert "docker network inspect gsj-<name>-net" in text and "127.0.0.1 host.docker.internal" in text
    assert "the gateway-host probe no longer needs it" in text
    assert "seconds each readiness wait may take, on this process's clock" in text
    assert "a suspended host does not" in text


# ------------------------------------------------- the storage driver

def test_check_daemon_names_a_copy_on_create_driver_from_the_same_docker_info_call(est, monkeypatch, capsys):
    """b2 priced vfs after the fact; the daemon check already runs
    `docker info` — one more field says it first.

    CP-99 re-words the price to round five's CONTROLLED pair (same door,
    same corpus, same row 2, the driver the only difference) instead of
    round four's single loaded host: 19.4 s against 1.1 s to create the
    sandbox container, 31 G against 8.4 G of data root for the same
    4.061 GB of images. "~13 GB per container" was never measured."""
    calls = []
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(est, "run", lambda cmd, **kw: (calls.append(cmd),
                                                       subprocess.CompletedProcess(cmd, 0, "29.0.0 vfs\n", ""))[1])
    est.check_daemon()
    assert calls == [["docker", "info", "--format", "{{.ServerVersion}} {{.Driver}}"]]
    out = capsys.readouterr().out
    assert "WARNING" in out and "storage driver 'vfs': every container is a full COPY" in out
    assert "sandbox init took 19.4 s here against 1.1 s there, 17×" in out
    assert "Continuing — slowly" in out
    assert "31 G against 8.4 G for 4.061 GB of images" in out
    assert "~13 GB per container" not in out      # inferred once, never measured (CP-99)
    monkeypatch.setattr(est, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "29.0.0 overlay2\n", ""))
    est.check_daemon()
    assert "storage driver" not in capsys.readouterr().out
