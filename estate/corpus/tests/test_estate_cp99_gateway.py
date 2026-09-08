"""CP-99: what round five found in the gateway-host probe — a label that
asserted a measurement it had not made, and killed a run.

`stranger-b1`'s `up` wrote `polar.gateway.public_url:
http://host.docker.internal:8200` and printed "(measured: dialable from a
container on 'gsj-helix-net' and from this host)". Neither dial worked;
the compose gateway `172.19.0.1` worked from both and was in the candidate
list, recorded `reachable: true` beside the three others. `submit` then sat
at `0/1 sessions terminal` for 22 minutes with every Polar worker pool at
zero and no sandbox container ever created — no refusal, no UNMEASURED, no
ERROR session. b1: "worse than not probing, because 'measured' told me to
trust it."

Three defects in one function, all asserted here:

  (a) the dial accepted ANY HTTP answer, so a foreign listener on the
      candidate's host:port passed it — the sentinel answers a NONCE now
      and the dial says WHAT answered (`our sentinel` / `a foreign
      listener` / `nothing`);
  (b) `host.docker.internal` was `insert(0, …)`ed on nothing but
      RESOLVING, and beat a candidate that answered — it is appended now;
  (c) a gateway port already in use meant `pass  # probe it`, measuring
      somebody else's listener under a `measured:` label — a port this
      process cannot bind is UNMEASURED, and says which port and why.

And the half of the label that was always inference: "and from this host"
was never dialed. It is now (`host_dial`), which is the second, independent
reason b1's address would have lost.

Hermetic — no Docker daemon, no estate. What is NOT faked here: the dial
payload (the real script, exec'd in this interpreter), the sentinel (the
real handler, on a real socket), and every HTTP answer (real servers). The
one `docker exec` shape a test fakes comes from `cli_shapes.json` (§8 rule
10), where CP-99 measured it: `docker exec … python -c …` on an image
without python exits **127 with the OCI error on STDOUT and an empty
stderr**, which is why `probe_dial`'s own failure branch could never fire.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import cli_shape

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"
HARNESS = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
NET = "gsj-helix-net"          # b1's network, by name


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp99", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    monkeypatch.setattr(module, "PH", module.Phases())
    return module


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def listener(body: str, port: int | None = None):
    """A real HTTP server answering `body` on 127.0.0.1 — somebody else's
    listener, or a stand-in for one."""
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = body.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a, **k):
            pass

    server = HTTPServer(("127.0.0.1", port or 0), _H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def run_dial(cmd: list, **kw) -> subprocess.CompletedProcess:
    """Execute the REAL dial payload in this interpreter and hand back what
    `docker exec` would have handed back. The payload is the thing under
    test; the CLI's only contribution is passing its stdout through."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(cmd[-1], {})            # noqa: S102 — the script this code generates
    return subprocess.CompletedProcess(cmd, 0, out.getvalue(), "")


# --------------------------------------------------- (a) the foreign listener

def test_the_dial_payload_says_what_answered_not_merely_that_something_did(est, monkeypatch):
    """The defect that killed b1's run, at the payload: an HTTP answer from a
    listener that is not ours used to print OK. Three real listeners, one
    real closed port, the real script."""
    monkeypatch.setattr(est, "run", run_dial)
    nonce = "gsj-probe-deadbeefdeadbeef"
    port = free_port()
    with listener(nonce, port):                                   # our sentinel
        results, failure = est.probe_dial(NET, ["127.0.0.1"], port, "gsj-helix-mcp",
                                          HARNESS, nonce)
        assert failure is None
        assert results == [{"candidate": "127.0.0.1", "container": "our sentinel"}]
    with listener('{"status":"ok","service":"polar-gateway"}', port):   # someone else's
        results, _ = est.probe_dial(NET, ["127.0.0.1"], port, "gsj-helix-mcp", HARNESS, nonce)
        assert results == [{"candidate": "127.0.0.1", "container": "a foreign listener"}]
    results, _ = est.probe_dial(NET, ["127.0.0.1"], port, "gsj-helix-mcp", HARNESS, nonce)
    assert results == [{"candidate": "127.0.0.1", "container": "nothing"}]


def test_a_foreign_listener_that_answers_404_is_foreign_not_nothing(est, monkeypatch):
    """`urlopen` raises on >= 400, so the python payload used to print NOTHING
    for a listener that answered — "no listener there" for an occupied port,
    which is the misdiagnosis this whole change exists to stop. A vLLM on the
    gateway port answers 404 on `/`."""
    monkeypatch.setattr(est, "run", run_dial)
    port = free_port()

    class _404(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a, **k):
            pass

    server = HTTPServer(("127.0.0.1", port), _404)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        results, _ = est.probe_dial(NET, ["127.0.0.1"], port, "gsj-helix-mcp", HARNESS, "gsj-probe-n")
    finally:
        server.shutdown()
        server.server_close()
    assert results == [{"candidate": "127.0.0.1", "container": "a foreign listener"}]


def test_the_dial_payload_carries_the_nonce_in_both_forms(est, monkeypatch):
    """The `docker run` fallback speaks node, not python — the same rule, or
    the fallback would still pass a foreign listener."""
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "reap_container", lambda name, wait_s=30: True)
    est.probe_dial(NET, ["10.0.0.5"], 18299, None, HARNESS, "gsj-probe-abc")
    js = seen[0][-1]
    assert "N=\"gsj-probe-abc\"" in js and "t===N?'SENTINEL':'FOREIGN'" in js
    assert "await r.text()" in js


# ------------------------------------------------------- the host leg, dialed

def test_host_dial_says_what_answered_from_this_host(est):
    """"and from this host" was never a measurement — the docstring's "the
    host reaches its own interface IPs trivially" is true of a host IPv4 and
    false of every name. b1's `host.docker.internal` failed exactly here."""
    nonce = "gsj-probe-cafebabecafebabe"
    with listener(nonce) as port:
        assert est.host_dial("127.0.0.1", port, nonce) == "our sentinel"
    with listener("hello, I am something else") as port:
        assert est.host_dial("127.0.0.1", port, nonce) == "a foreign listener"
    assert est.host_dial("127.0.0.1", free_port(), nonce) == "nothing"


def test_a_candidate_that_answers_only_from_the_container_is_refused(est, monkeypatch, capsys):
    """CP-03's rule is ONE address both legs dial. A candidate the container
    reaches and the host does not is not that address, and the refusal says
    which leg failed for which candidate."""
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5"])
    monkeypatch.setattr(est.socket, "gethostbyname",
                        lambda name: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(est, "probe_dial",
                        lambda *a, **k: ([{"candidate": "10.0.0.5", "container": "our sentinel"}], None))
    monkeypatch.setattr(est, "http", lambda *a, **k: (None, "ConnectionRefusedError"))
    with pytest.raises(SystemExit) as exc:
        est.gateway_host(NET, free_port(), None, HARNESS, exec_container="gsj-helix-mcp")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "10.0.0.5: our sentinel from the container, nothing from this host" in err


# ------------------------------------- (b) the ordering, and b1's topology

def test_host_docker_internal_is_appended_not_put_first(est, monkeypatch):
    """It was `candidates.insert(0, …)` on nothing but `gethostbyname`
    succeeding. b1's working candidate was in the list and lost on order."""
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5", "192.168.1.9"])
    monkeypatch.setattr(est.socket, "gethostbyname", lambda name: "192.168.65.254")
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    seen = {}

    def fake_dial(network, candidates, gport, exec_container, probe_image, nonce):
        seen["candidates"] = list(candidates)
        return [], "the probe did not run in this test"

    monkeypatch.setattr(est, "probe_dial", fake_dial)
    host, how, _ = est.gateway_host(NET, free_port(), None, HARNESS,
                                    exec_container="gsj-helix-mcp")
    assert seen["candidates"] == ["10.0.0.5", "192.168.1.9", "host.docker.internal"]
    assert seen["candidates"][0] != "host.docker.internal"
    # …and the ORDER THE PROBE DIALS IN is not the order to GUESS in. When the
    # probe cannot dial at all, a Docker Desktop host still wants the name a
    # container can reach by construction, not a DHCP LAN lease that happened
    # to be first: appending for the probe's sake must not move the degrade.
    assert host == "host.docker.internal" and "UNMEASURED" in how
    assert how.startswith("host.docker.internal = the name this host resolves")


def test_b1s_topology_reproduced_up_chooses_the_address_that_answers(est, monkeypatch, capsys):
    """b1's exact shape, hermetically: a name that RESOLVES on this host and
    whose port answers something that is not ours (the Desktop VM's
    host-gateway line, and a listener out there on 8200), beside a compose
    gateway that really is this run's sentinel. 0.1.12 wrote the name,
    labelled `measured: dialable … and from this host`, and hung the
    episode. It writes the gateway now, and records what the name was."""
    gport = free_port()
    with listener('{"status":"ok","service":"polar-gateway"}') as foreign_port:
        real_getaddrinfo = socket.getaddrinfo

        def getaddrinfo(host, port, *a, **k):        # the /etc/hosts line, and where it goes
            if host == "host.docker.internal":
                return real_getaddrinfo("127.0.0.1", foreign_port, *a, **k)
            return real_getaddrinfo(host, port, *a, **k)

        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(est.socket, "gethostbyname", lambda name: "192.168.65.254")
        monkeypatch.setattr(est.platform, "system", lambda: "Linux")
        monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
        monkeypatch.setattr(est, "host_ipv4s", lambda: [])

        def fake_run(cmd, **kw):
            if cmd[:3] == ["docker", "network", "inspect"]:
                return subprocess.CompletedProcess(cmd, 0, "127.0.0.1\n", "")
            assert cmd[:2] == ["docker", "exec"] and cmd[2] == "gsj-helix-mcp"
            return run_dial(cmd)

        monkeypatch.setattr(est, "run", fake_run)
        host, how, results = est.gateway_host(NET, gport, None, HARNESS,
                                              exec_container="gsj-helix-mcp")

    assert host == "127.0.0.1"                     # the compose gateway (172.19.0.1 in b1's run)
    assert how == (f"measured: this run's own sentinel answered on :{gport} "
                   f"from a container on {NET!r} and from this host")
    assert results == [
        {"candidate": "127.0.0.1", "container": "our sentinel",
         "host": "our sentinel", "reachable": True},
        {"candidate": "host.docker.internal", "container": "a foreign listener",
         "host": "not dialed", "reachable": False},
    ]
    # the record now says what answered, so a reader can tell this shape apart
    # from a network that is simply down — b1's run.json said `reachable: true`
    # for all four candidates and named no leg at all.
    assert "WARNING" not in capsys.readouterr().out


# ----------------------------------------------- (c) a port already in use

def test_a_port_it_cannot_bind_is_unmeasurable_never_measured(est, monkeypatch, capsys):
    """`except OSError: pass  # something … already listens: probe it` — and
    then it printed `measured:` about somebody else's listener. A port this
    process cannot bind carries no sentinel, so there is nothing to measure;
    the honest answer is UNMEASURED, naming the port."""
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5"])
    monkeypatch.setattr(est.socket, "gethostbyname",
                        lambda name: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(est, "probe_dial",
                        lambda *a, **k: pytest.fail("dialed a port it could not bind"))
    busy = free_port()
    held = socket.socket()
    held.bind(("0.0.0.0", busy))     # the wildcard bind the probe itself makes
    held.listen(1)
    try:
        host, how, results = est.gateway_host(NET, busy, None, HARNESS,
                                              exec_container="gsj-helix-mcp")
    finally:
        held.close()
    assert host == "10.0.0.5" and results == []
    assert how == (f"10.0.0.5 = a host IPv4 (UNMEASURED — port {busy} could not be bound: "
                   "the probe has no sentinel to dial)")
    out = capsys.readouterr().out
    assert f"port {busy} is already in use on this host" in out
    assert "anything answering there is somebody else's listener" in out
    assert "--gateway-host <address>" in out and "measured:" not in out
    assert "Free the port" in out          # EADDRINUSE's remedy, and only its


def test_a_bind_failure_that_is_not_a_busy_port_says_so(est, monkeypatch, capsys):
    """`except OSError` catches more than EADDRINUSE. Telling an operator who
    asked for :443 as a non-root user to "free the port" sends them hunting
    for a listener that does not exist."""
    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5"])
    monkeypatch.setattr(est.socket, "gethostbyname",
                        lambda name: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(est, "probe_dial", lambda *a, **k: pytest.fail("dialed"))

    def refuse(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(est._http_server, "HTTPServer", refuse)
    host, how, _ = est.gateway_host(NET, 443, None, HARNESS, exec_container="gsj-helix-mcp")
    out = capsys.readouterr().out
    assert host == "10.0.0.5" and "could not be bound" in how
    assert "port 443 could not be bound on 0.0.0.0 (Permission denied)" in out
    assert "already in use" not in out and "Free the port" not in out
    assert "--gateway-port" in out


# ------------------------------- the failure branch the real CLI never reached

def test_an_exec_that_could_not_start_the_interpreter_is_a_failure_not_a_silent_refusal(
        est, monkeypatch, capsys):
    """Measured at CP-99 (rule 10): `docker exec <c> python -c …` on an image
    without python exits 127 with the OCI error on **stdout** and an empty
    stderr. CP-96's guard was `returncode != 0 and not proc.stdout.strip()`,
    so that shape recorded NO failure, the dial parsed nothing, and `up`
    refused with `no host address is dialable` — a refusal about the network
    for a probe that never ran. The guard is the parsed dial now."""
    # `stdout_re` in the file means the value is the host's, not the CLI's: the
    # trailing `: unknown` is the runtime's and differs by version (present on
    # 28.5.1, absent on the CI runner's 28.0.4 — CP-99's own CI caught it), so
    # the fake carries a literal the measuring test accepts on both.
    oci = ('OCI runtime exec failed: exec failed: unable to start container process: '
           'exec: "python": executable file not found in $PATH: unknown\n')
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape(
        "docker exec <running> python -c <script>, no interpreter in the image", cmd,
        name=cmd[2], stdout=oci))
    results, failure = est.probe_dial(NET, ["10.0.0.5"], 18299, "gsj-helix-mcp", None,
                                      "gsj-probe-abc")
    assert results == []
    assert failure.startswith("exit 127 via `docker exec gsj-helix-mcp`")
    assert "executable file not found in $PATH" in failure

    monkeypatch.setattr(est.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(est, "host_ipv4s", lambda: ["10.0.0.5"])
    monkeypatch.setattr(est.socket, "gethostbyname",
                        lambda name: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(est.shutil, "which", lambda name: "/usr/bin/docker")
    host, how, _ = est.gateway_host(NET, free_port(), None, HARNESS,
                                    exec_container="gsj-helix-mcp")
    assert host == "10.0.0.5" and "UNMEASURED" in how
    assert "the gateway-host probe could not run — exit 127" in capsys.readouterr().out


def test_an_exec_into_a_container_that_died_is_still_read_off_stderr(est, monkeypatch):
    """The other measured exec shape, where the message IS on stderr — the
    fix must not lose the branch CP-96 got right."""
    monkeypatch.setattr(est, "run", lambda cmd, **kw: cli_shape(
        "docker exec <absent> python -c <script>", cmd, name=cmd[2]))
    results, failure = est.probe_dial(NET, ["10.0.0.5"], 18299, "gsj-helix-mcp", None, "n")
    assert results == []
    assert failure == ("exit 1 via `docker exec gsj-helix-mcp` (this run's own container, "
                       f"already on {NET!r}): Error response from daemon: No such container: "
                       "gsj-helix-mcp")


# ------------------------------------------- a2's second packaging defect (F9)

def test_no_printed_url_runs_into_the_prose(est):
    """a2: the skeleton line's `…/bring-your-own.md#your-pins's derive_my_pins.py`
    linkifies as `#your-pins's`, which is not the anchor — "printed twice per
    `up`, on the pins-skeleton line … a link about the one file the output
    warns you not to misuse". Every printed URL ends at whitespace now."""
    src = ESTATE_PY.read_text(encoding="utf-8")
    glued = re.findall(r"BRING_YOUR_OWN_URL\}#[a-z-]+['’]s", src)
    assert glued == [], glued
    assert src.count("#your-pins — its derive_my_pins.py reads the skeleton — and") == 1
    assert src.count("the derive_my_pins.py at {BRING_YOUR_OWN_URL}#your-pins") == 3
