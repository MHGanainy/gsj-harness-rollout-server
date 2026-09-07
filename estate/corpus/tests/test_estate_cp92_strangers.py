"""CP-92: what four strangers found in estate.py's refusal and status texts.

Hermetic — no Docker daemon, no estate. The stderr strings below are the
ones the 2026-09-06 stranger daemons actually printed (a nested dockerd on
overlayfs: whiteout extraction refused, overlay upperdir unmountable)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ESTATE_DIR = Path(__file__).resolve().parents[2]
ESTATE_PY = ESTATE_DIR / "estate.py"

WHITEOUT = ('failed to extract layer sha256:5a5e4b3c2d1f: failed to convert whiteout file '
            '"usr/share/doc/.wh..wh..opq": operation not permitted: unknown')
OVERLAY = ("Error response from daemon: failed to create task for container: failed to "
           "create shim task: OCI runtime create failed: failed to mount /var/lib/docker/"
           "overlay2/abc/merged: mount options: fstype: overlay: invalid argument")
DOWNLOADS = ("manifest unknown", "dial tcp: lookup ghcr.io: no such host",
             "net/http: TLS handshake timeout", "unexpected EOF",
             # a firewalled daemon's errno rides a TRANSPORT failure — not storage
             "dial tcp 1.2.3.4:443: connect: operation not permitted",
             "dial tcp 1.2.3.4:443: connect: invalid argument")
HARNESS = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"


@pytest.fixture
def est(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("estate_cp92", ESTATE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS", tmp_path)
    return module


def invoke(runs: Path, *args: str) -> subprocess.CompletedProcess:
    """estate.py as a consumer runs it, behind a Docker canary that fails
    the test if any docker command is issued (the CP-90 pattern)."""
    with tempfile.TemporaryDirectory(prefix="cp92-docker-canary-") as scratch:
        fake_bin = Path(scratch)
        calls = fake_bin / "docker-calls"
        docker = fake_bin / "docker"
        docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CP92_DOCKER_CALLS"\nexit 97\n')
        docker.chmod(0o700)
        env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                   CP92_DOCKER_CALLS=str(calls), PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, str(ESTATE_PY), *args, "--runs-dir", str(runs)],
                              env=env, capture_output=True, text=True, timeout=30)
        assert not calls.exists(), "Docker canary intercepted: " + calls.read_text()
        return proc


# ------------------------------------------------- the ARM harness-image cure

def test_sandbox_image_fix_names_a_plain_pull_before_any_platform_override(est):
    fix = est.sandbox_image_fix(HARNESS)
    assert fix.startswith(f"docker pull {HARNESS}")
    assert "--platform linux/amd64" in fix
    # the override is conditioned on the one measured symptom, and only after it
    assert fix.index("no matching manifest") < fix.index("--platform linux/amd64")
    assert fix.index(f"docker pull {HARNESS}") < fix.index("no matching manifest")
    assert "two-platform" in fix and "native platform" in fix
    assert "--skip-sandbox-image" in fix and "docker save | docker load" in fix


def test_sandbox_refusal_does_not_read_the_daemon_arch_to_choose_a_platform(est, monkeypatch):
    # the old cure consulted daemon_arch() and made amd64 the default on ARM;
    # the new one is a pure function of the image — no daemon, no docker
    monkeypatch.setattr(est, "daemon_arch", lambda: pytest.fail("daemon_arch consulted"))
    monkeypatch.setattr(est, "run", lambda *a, **k: pytest.fail("docker consulted"))
    fix = est.sandbox_image_fix("example.invalid/harness:1")
    assert fix.startswith("docker pull example.invalid/harness:1")
    assert "docker pull --platform" not in fix
    assert fix.index("no matching manifest") < fix.index("--platform linux/amd64")


# --------------------------------------------- the split pull-failure message

@pytest.mark.parametrize("stderr", [WHITEOUT, OVERLAY, WHITEOUT.upper()])
def test_pull_failure_kind_reads_extraction_and_mount_failures_as_extract(est, stderr):
    assert est.pull_failure_kind(stderr) == "extract"


@pytest.mark.parametrize("stderr", DOWNLOADS + ("", None))
def test_pull_failure_kind_reads_registry_side_failures_as_download(est, stderr):
    assert est.pull_failure_kind(stderr) == "download"


def test_pull_failure_fix_keeps_todays_advice_for_a_download_failure(est):
    advice = "pass --forgejo-image <ref> naming a live one"
    assert est.pull_failure_fix("download", HARNESS, advice) == advice


def test_pull_failure_fix_for_extract_names_the_run_smoke_and_the_storage_cure(est):
    fix = est.pull_failure_fix("extract", HARNESS, "the registry advice, unused here")
    assert "the registry advice, unused here" not in fix
    assert "docker run --rm alpine true" in fix
    assert "plain `docker pull` PASSES" in fix and "only a run detects it" in fix
    assert "docker save | docker load` fails on the same layers" in fix
    assert "-v /var/lib/docker" in fix and "--storage-driver vfs" in fix
    assert "overlayfs" in fix and HARNESS in fix


def test_forgejo_pull_refusal_branches_on_where_the_pull_failed(est, monkeypatch, capsys):
    """The Forgejo pull refusal (wishlist 52's own step) through both branches."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "pull"]:
            return subprocess.CompletedProcess(cmd, 1, "", fake_run.stderr)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No such image")
        raise AssertionError(f"unexpected docker call {cmd}")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "write_compose", lambda *a, **k: None)
    monkeypatch.setattr(est, "PH", est.Phases())
    r = est.Run("canary")
    r.dir.mkdir()
    for stderr, expect, absent in ((WHITEOUT, "docker run --rm alpine true", "--forgejo-image"),
                                   ("manifest unknown", "--forgejo-image", "alpine true")):
        fake_run.stderr = stderr
        with pytest.raises(SystemExit) as exc:
            est.create_forgejo(r.dir, r, 3000, True, "gsj-canary-net", False,
                               "codeberg.org/forgejo/forgejo:16.0.3")
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "REFUSED" in err and expect in err and absent not in err
        assert "Traceback" not in err
    assert all(cmd[1] in ("image", "pull") for cmd in calls)


def test_compose_up_refusal_names_storage_when_the_daemon_cannot_mount(est, monkeypatch, capsys):
    """`docker compose up forgejo` failing with the overlay EINVAL the stranger
    saw: the refusal must not stop at `docker logs … if the container started`."""
    def fake_run(cmd, **kw):
        if cmd[:2] == ["docker", "pull"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, "sha256:abc [] linux/arm64", "")
        if cmd[:2] == ["docker", "compose"]:
            assert kw.get("capture_output"), "compose up must capture to classify"
            return subprocess.CompletedProcess(cmd, 1, "", " Container gsj-canary-forgejo Creating\n"
                                               + OVERLAY + "\n")
        raise AssertionError(f"unexpected docker call {cmd}")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "write_compose", lambda *a, **k: None)
    monkeypatch.setattr(est, "PH", est.Phases())
    r = est.Run("canary")
    r.dir.mkdir()
    with pytest.raises(SystemExit) as exc:
        est.create_forgejo(r.dir, r, 3000, True, "gsj-canary-net", False,
                           "codeberg.org/forgejo/forgejo:16.0.3")
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert "Container gsj-canary-forgejo Creating" in err     # compose's own lines re-emitted
    assert "could not extract or mount" in err
    assert "docker run --rm alpine true" in err and "-v /var/lib/docker" in err
    assert "if the container started" not in err


def test_pull_failure_kind_needs_a_storage_word_beside_a_bare_errno(est):
    # the errno words alone decide nothing; beside a storage word they do
    assert est.pull_failure_kind("something: operation not permitted") == "download"
    assert est.pull_failure_kind("unpack layer: operation not permitted") == "extract"
    assert est.pull_failure_kind("snapshotter: invalid argument") == "extract"
    # a transport marker wins over a bare errno, never over a strong sign
    assert est.pull_failure_kind("dial tcp 1.2.3.4:443: i/o timeout (layer)") == "download"
    assert est.pull_failure_kind("connection refused; failed to extract layer") == "extract"


def test_update_compose_recreate_refusal_branches_like_the_up_sites(est):
    """The third compose-up site (cmd_update's --force-recreate mcp) reads
    the same classifier: its source calls compose_up and pull_failure_fix."""
    src = ESTATE_PY.read_text()
    site = src.index('"--force-recreate", "mcp")')
    window = src[site - 200: site + 900]
    assert "compose_up(run_.dir" in window and "pull_failure_fix(kind" in window
    assert 'compose(run_.dir, "up"' not in src
    assert src.count("compose_up(") == 4            # the definition + three sites


def test_compose_up_refusal_keeps_the_log_advice_for_an_ordinary_failure(est, monkeypatch, capsys):
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, "sha256:abc [] linux/arm64", "")
        if cmd[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(cmd, 1, "", "Error: port is already allocated\n")
        raise AssertionError(f"unexpected docker call {cmd}")

    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "write_compose", lambda *a, **k: None)
    monkeypatch.setattr(est, "PH", est.Phases())
    r = est.Run("canary")
    r.dir.mkdir()
    with pytest.raises(SystemExit):
        est.create_forgejo(r.dir, r, 3000, True, "gsj-canary-net", False,
                           "codeberg.org/forgejo/forgejo:16.0.3")
    err = capsys.readouterr().err
    assert "port is already allocated" in err
    assert "docker logs gsj-canary-forgejo` if the container started" in err
    assert "alpine true" not in err


# ------------------------------------------------- status on a partial run

def partial_record(corpus_path: str, name="canary"):
    """What run.json holds when `up` dies at the MCP pull: the record landed
    right after rec["forgejo"] was set — BEFORE the owner block updated it —
    so no owner/token keys live under forgejo; the owner is the corpus
    phase's, the tokens are in .env, the scaffold's lock is in the tree."""
    return {"schema": 1, "run": name,
            "corpus": {"path": corpus_path, "name": "my-corpus",
                       "owner": "my-owner", "case_ids": ["case_example"]},
            "forgejo": {"mode": "created", "url": "http://127.0.0.1:9",
                        "admin_user": "gsj-admin", "require_signin_view": True},
            "compose": {"mcp": {"image": "registry.invalid/gsj-mcp-service:9", "container": "c",
                                "port": 8790, "data": "/d", "config": "/c", "read_env": "R"}},
            "secrets": {"names": ["GSJ_FORGEJO_ADMIN_PASSWORD"]}}


def partial_estate(tmp_path: Path, *, tokens=True, lock=True,
                   lock_host="http://127.0.0.1:9") -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    if lock:
        (corpus / "corpus.lock.json").write_text(json.dumps(
            {"cases": {"case_example": {"split": "train",
                                        "clone_url": f"{lock_host}/my-owner/case_example.git"}},
             "corpus": {"base_url": lock_host, "name": "my-corpus", "owner": "my-owner"},
             "taskbank": {}}))
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps(partial_record(str(corpus))))
    (rd / ".env").write_text(
        "GSJ_FORGEJO_ADMIN_PASSWORD='disposable-admin'\n"
        + ("GSJ_FORGEJO_TOKEN_MY_OWNER='disposable-push'\n"
           "GSJ_FORGEJO_READ_TOKEN_MY_OWNER='disposable-read'\n" if tokens else ""))
    return corpus


def test_status_reports_the_phases_that_stand_before_refusing_a_partial_run(tmp_path):
    corpus = partial_estate(tmp_path)
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1
    out = proc.stdout
    assert "== run canary ==" in out and "incomplete — up did not finish" in out
    assert "corpus    my-corpus: 1 case(s); owner 'my-owner'" in out
    # the owner comes from the corpus phase — never `owner None`
    assert "forgejo   created  http://127.0.0.1:9  healthz=None  sign-in=?  owner 'my-owner'" in out
    assert "owner None" not in out
    assert ("owner     'my-owner'; tokens minted in .env (GSJ_FORGEJO_TOKEN_MY_OWNER, "
            "GSJ_FORGEJO_READ_TOKEN_MY_OWNER)") in out
    assert f"scaffold  pushed — lock written " in out and f"(1 case(s)): {corpus / 'corpus.lock.json'}" in out
    assert "mcp       not reached — up died in or before this phase " \
           "(retrieval service image registry.invalid/gsj-mcp-service:9)" in out
    for phase in ("taskbank", "verify", "engine", "config"):
        assert f"{phase:9} not reached" in out
    assert "compose ps" not in out                       # no compose.yaml → no docker
    assert "REFUSED" in proc.stderr and "is incomplete" in proc.stderr
    assert "the phases above stand" in proc.stderr
    assert "up --name canary" in proc.stderr and "to resume" in proc.stderr
    # `up` resolves --corpus before it loads the record: the cure names it
    assert f"up --name canary --corpus {corpus} --runs-dir {tmp_path}" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_status_partial_reads_tokens_and_lock_from_disk_not_from_record_keys(tmp_path):
    partial_estate(tmp_path, tokens=False, lock=False)
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1
    assert "owner 'my-owner'" in proc.stdout           # forgejo row still names the owner
    assert "owner     not reached" in proc.stdout       # no tokens in .env
    assert "scaffold  not reached" in proc.stdout       # no lock in the tree
    assert "mcp       not reached — up died in or before this phase" in proc.stdout


def test_status_partial_does_not_claim_another_hosts_lock_as_this_runs_push(tmp_path):
    """A tree scaffolded against another run's Forgejo carries a lock whose
    recorded base_url is not this run's — that is not a phase this run entered."""
    corpus = partial_estate(tmp_path, lock_host="http://forgejo.elsewhere:3000")
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1
    assert ("scaffold  a lock from another git host (http://forgejo.elsewhere:3000) — not "
            f"this run's push: {corpus / 'corpus.lock.json'}") in proc.stdout
    assert "pushed" not in proc.stdout


def test_status_partial_without_a_corpus_path_names_a_placeholder_corpus_in_the_cure(tmp_path):
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps({"schema": 1, "run": "canary",
                                             "forgejo": {"mode": "created",
                                                         "url": "http://127.0.0.1:9"}}))
    (rd / ".env").write_text("")
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1
    assert "corpus    not reached" in proc.stdout
    assert "up --name canary --corpus <the run's corpus root> --runs-dir" in proc.stderr


def test_status_partial_names_a_run_that_died_before_forgejo(tmp_path):
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps({"schema": 1, "run": "canary",
                                             "corpus": partial_record("/disposable")["corpus"]}))
    (rd / ".env").write_text("")
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 1
    assert "forgejo   not reached" in proc.stdout and "owner     not reached" in proc.stdout
    assert "scaffold  not reached" in proc.stdout
    assert "mcp       not reached — up died in or before this phase" in proc.stdout
    assert "is incomplete" in proc.stderr


def test_status_on_a_complete_record_keeps_its_first_line_byte_identical(tmp_path):
    """The demo parses `== run <name> ==`; the complete path is untouched."""
    rd = tmp_path / "canary"
    rd.mkdir()
    (rd / "run.json").write_text(json.dumps({**partial_record("/disposable"),
                                             "mcp": {"mode": "adopted", "url": "http://127.0.0.1:9"},
                                             "last_run": {"at": "2026-09-07T00:00:00+00:00",
                                                          "mode": "first run"}}))
    (rd / ".env").write_text("")
    proc = invoke(tmp_path, "status", "--name", "canary")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith(f"== run canary == {rd}  (last run 2026-09-07T00:00:00+00:00, "
                                  "first run)\n")
    assert "incomplete" not in proc.stdout and "incomplete" not in proc.stderr


# ---------------------------------------------- row 60: the help summary

def test_help_summary_renders_all_seven_verbs(tmp_path):
    proc = invoke(tmp_path, "--help")
    assert proc.returncode == 0
    assert "{scaffold,validate,up,ingest,update,status,down}" in proc.stdout
    assert "{scaffold,validate,up,ingest,status,down}" not in proc.stdout
    assert "\n    update" in proc.stdout or "\n  update" in proc.stdout


# ----------------------------------------- the warnings name the library page

def test_the_warnings_name_the_library_page_not_the_demo_or_the_pins_dir(est):
    src = ESTATE_PY.read_text()
    assert "MODEL-SURFACE.md" not in src
    assert src.count("#your-pins") >= 3 and src.count("#your-model") >= 1
    assert est.BRING_YOUR_OWN_URL.endswith("docs/guide/bring-your-own.md")
    assert "the pins walk re-derives (pins/derive_pins.py)" not in src
    assert "`up` needs pyarrow" in est.__doc__
