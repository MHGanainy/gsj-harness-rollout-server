"""Pull policy through real callers/files; unrelated services are substituted.

CLI outcomes use cli_shapes; live mode keeps actual image inspect/pull/identity.
The script observer supports independent committed baseline/candidate processes.
It stops at the next corpus ingest (MCP), or returns from create_forgejo using
measured Forgejo admin-list program stdout at the unchanged Compose exec
parsing boundary. No service is started here; HTTP health/authentication are
substituted. This is not service/readiness integration proof.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from conftest import CLI_SHAPES, cli_shape, make_corpus

SOURCE = Path(os.environ.get("GSJ_NATIVE_PULL_SOURCE", Path(__file__).resolve().parents[3]))
IMAGE = "codeberg.org/forgejo/forgejo@sha256:7c4e1db440be7b2ca685b49d0d7864cdd78e92431f531bf7893659def8200fc5"
MISSING = "codeberg.org/forgejo/forgejo:compose-progress-no-such-20260911t124234z"
PULL_OK = "docker pull --platform linux/arm64 <cached-forgejo>"
PULL_MISSING = "docker pull --platform linux/arm64 <missing-forgejo-tag>"
ADMIN_LIST = "docker exec <forgejo-admin> su git -c forgejo admin user list"


class Boundary(Exception):
    """The next unrelated service or ingestion operation is outside this proof."""


def observe(source, work, service, image, *, present=False, failure=False,
            live=False, repeat=False, wait_interrupt=False, explicit=True):
    source, work = Path(source).resolve(), Path(work).resolve()
    sys.path.insert(0, str(source))
    import gsj_rollout
    assert Path(gsj_rollout.__file__).resolve() == source / "gsj_rollout/__init__.py"
    spec = importlib.util.spec_from_file_location("native_pull_subject", source / "estate/estate.py")
    est = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = est
    spec.loader.exec_module(est)
    assert Path(est.__file__).resolve() == source / "estate/estate.py"
    assert Path(est.ic.__file__).resolve() == source / "estate/corpus/ingest_corpus.py"
    work.mkdir(parents=True)
    corpus = make_corpus(work / "corpus", estate_fields=False)
    bare = work / "bare"
    bare.mkdir()
    runs = work / "runs"
    runs.mkdir()
    events, outcomes = [], []
    state = {"present": present, "active": False, "wait_interrupt": wait_interrupt}
    with pytest.MonkeyPatch.context() as patch:
        for key in list(os.environ):
            if key.startswith("GSJ_"):
                patch.delenv(key)
        patch.setenv(est.ADMIN_PASSWORD_ENV, "fixture-admin-password")
        patch.setenv(est.MCP_SECRET_ENV, "c" * 64)
        patch.setattr(est, "RUNS", runs)
        patch.setattr(est, "PH", est.Phases())
        patch.setattr(est, "now_iso", lambda: "2026-09-11T00:00:00+00:00")
        patch.setattr(est, "script_version", lambda: {"script": "estate/estate.py", "commit": "comparison", "dirty": False, "library": "0.1.16"})
        patch.setattr(est, "secrets", SimpleNamespace(token_hex=lambda size: (events.append(["secret_generated", size]) or "c" * (2 * size))))
        patch.setattr(est, "pick_port", lambda want, default, *a, **k: default)
        patch.setattr(est, "check_docker", lambda: events.append(["check_docker"]))
        patch.setattr(est, "daemon_arch", lambda: "arm64")
        patch.setattr(est.Forgejo, "probe", lambda self: setattr(self, "signin", True))
        patch.setattr(est.Forgejo, "owner_exists", lambda self, owner: True)
        patch.setattr(est.Forgejo, "owner_repos", lambda self, owner: [])
        patch.setattr(est.Forgejo, "token_valid", lambda self, token, owner: True)
        patch.setattr(est.Forgejo, "mint_token", lambda self, owner, label, scopes: "fixture-" + label + "-token")
        health = {"state": "ready", "fingerprint": "f" * 64, "index_reused": True,
                  "embedding": {"model": est.DEFAULT_EMBEDDING_MODEL,
                                "revision": est.DEFAULT_EMBEDDING_REVISION, "dimension": 384},
                  "decisions": 30, "progress": {}, "backend": {"kind": "chroma"}}
        patch.setattr(est, "http", lambda *a, **k: (200, health))
        patch.setattr(est, "rebuild_in_progress", lambda *a: state["active"])
        original_wait, original_pull, original_present = est.Mcp.wait_ready, est.image_pull, est.image_present

        def wait(self, *args, **kwargs):
            events.append(["wait_ready", list(args), kwargs])
            if state["wait_interrupt"]:
                raise KeyboardInterrupt("controlled readiness boundary")
            return original_wait(self, *args, **kwargs)

        def inspect(ref):
            events.append(["image_present", ref])
            if live:
                return original_present(ref)
            return cli_shape("docker image inspect <present>" if state["present"] and ref == image
                             else "docker image inspect <missing>", name=ref).returncode == 0

        def pull(ref, phase):
            events.append(["image_pull", ref, phase, sorted(p.name for p in (runs / "pull-caller").iterdir())])
            if live:
                result = original_pull(ref, phase)
            else:
                result = cli_shape(PULL_MISSING if failure else PULL_OK, ["docker", "pull", ref])
                result.stdout = ""  # image_pull's established return contract; CLI stdout is presentation
            if result.returncode == 0:
                state["present"] = True
            events.append(["pull_result", result.returncode, result.stdout, result.stderr])
            return result

        def compose(root, *args, **kwargs):
            events.append(["compose", list(args), kwargs])
            if args[0] == "exec":
                assert args == ("exec", "-T", "forgejo", "su", "git", "-c", "forgejo admin user list")
                # Actual program stdout, measured via docker exec; not a claim about Compose transport.
                return cli_shape(ADMIN_LIST, list(args))
            assert args[0] == "up", args
            record = json.loads((root / "run.json").read_text()) if (root / "run.json").exists() else {}
            events.append(["activation_checkpoint", sorted(record.get("compose", {}))])
            key = ("docker compose up -d mcp <running>" if state["active"]
                   else "docker compose up -d mcp <absent>")
            state["active"] = True
            return cli_shape(key, list(args), name="gsj-pull-caller-" + args[-1], network="pull-fixture-net")

        def pipeline(phase, *args, **kwargs):
            events.append(["pipeline", phase])
            if phase == "ingest":
                raise Boundary("next corpus ingest")
            assert phase == "scaffold"
            child = subprocess.run([sys.executable, str(est.INGEST), "scaffold", "--corpus", str(corpus),
                                    "--base-url", bare.as_uri()], text=True, capture_output=True,
                                   env={**os.environ, "GSJ_PIPELINE_DRIVER": "estate"}, timeout=30)
            assert child.returncode == 0, child.stdout + child.stderr
            return child

        patch.setattr(est.Mcp, "wait_ready", wait)
        patch.setattr(est, "image_present", inspect)
        patch.setattr(est, "image_pull", pull)
        patch.setattr(est, "compose", compose)
        patch.setattr(est, "_run_corpus_phase", pipeline)
        if not live:
            # This helper return is recorded image metadata, not invented CLI text.
            patch.setattr(est, "image_identity", lambda ref: {"id": "sha256:e9161d8985edea79b58eea10904d1a0686bdbaf5ad9fdd70652b2f8f5049d3ed",
                                                            "repo_digests": [IMAGE], "platform": "linux/arm64"})
        args = argparse.Namespace(answers=None, defaults=True, corpus=str(corpus), name="pull-caller",
                                  forgejo="adopt", forgejo_url="http://forgejo.fixture:3000",
                                  forgejo_sandbox_url="http://forgejo.fixture:3000", network="pull-fixture-net",
                                  mcp="create", mcp_image=image, skip_sandbox_image=True, ingest_timeout=19.5)
        if not explicit:
            del args.mcp_image
        for index in range(2 if repeat else 1):
            before = len(events)
            run = est.Run(args.name)
            try:
                if service == "forgejo":
                    with run.mutation():
                        run.load()
                        run.prepare()
                        run.env[est.ADMIN_PASSWORD_ENV] = "fixture-admin-password"
                        run.write_env()
                        est.create_forgejo(run.dir, run, 3000, True, "pull-fixture-net", True, image)
                else:
                    est.cmd_up(args)
                outcome = None
            except BaseException as exc:
                outcome = [type(exc).__name__, str(exc)]
            files = {str(p.relative_to(runs)): {"body": p.read_text(), "mode": oct(p.stat().st_mode & 0o777)}
                     for p in sorted(runs.rglob("*")) if p.is_file()}
            lock = runs / ".locks/pull-caller.lock"
            assert lock.exists()
            import fcntl
            with lock.open("r+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle, fcntl.LOCK_UN)
            outcomes.append({"iteration": index, "outcome": outcome, "events": events[before:],
                             "files": files, "record": run.record if service == "forgejo" else None,
                             "phases": [dict(row, seconds="<elapsed>") for row in est.PH.rows],
                             "lock_released": True})
            state["wait_interrupt"] = False
    encoded = json.dumps(outcomes, sort_keys=True).replace(str(work), "<WORK>").replace(str(source), "<SOURCE>")
    return json.loads(encoded)


@pytest.mark.parametrize("service", ["forgejo", "mcp"])
@pytest.mark.parametrize("present", [False, True])
def test_pull_presence_gates_and_checkpoint_order(tmp_path, service, present):
    rows = observe(SOURCE, tmp_path / "work", service, IMAGE, present=present, repeat=True)
    pulls = [event for event in rows[0]["events"] if event[0] == "image_pull"]
    assert len(pulls) == (0 if present else 1)
    assert not [event for event in rows[1]["events"] if event[0] == "image_pull"]
    assert all(row["lock_released"] for row in rows)
    if service == "forgejo":
        assert all(row["outcome"] is None for row in rows)
        assert all(row["phases"][-1]["phase"] == "forgejo" for row in rows)
        first, second = (row["record"]["compose"]["forgejo"] for row in rows)
        assert first["image_pulled_by_run"] is (not present)
        assert second["image_pulled_by_run"] is False
        assert first["image_platform"] == "linux/arm64" and first["image_id"] == second["image_id"]
    else:
        assert all(row["outcome"] == ["Boundary", "next corpus ingest"] for row in rows)
        assert ["activation_checkpoint", ["mcp"]] in rows[0]["events"]
        assert ("pull-caller/mcp-config.yaml" in rows[0]["files"]
                and "pull-caller/run.json" in rows[0]["files"])
        assert [event for event in rows[0]["events"] if event[0] == "wait_ready"]
        kinds = [event[0] for event in rows[0]["events"]]
        if not present:
            assert kinds.index("image_pull") < kinds.index("secret_generated") < kinds.index("compose") < kinds.index("wait_ready")
        assert not [event for event in rows[1]["events"] if event[0] == "secret_generated"]


@pytest.mark.parametrize("service", ["forgejo", "mcp"])
def test_pull_failure_keeps_refusal_and_pre_pull_files(tmp_path, capsys, service):
    row = observe(SOURCE, tmp_path / "work", service, MISSING, failure=True)[0]
    assert row["outcome"] == ["SystemExit", "1"]
    assert not [event for event in row["events"] if event[0] in ("compose", "wait_ready")]
    assert "pull-caller/mcp-config.yaml" not in row["files"]
    assert ("pull-caller/run.json" in row["files"]) is (service == "mcp")
    err = capsys.readouterr().err
    assert "REFUSED" in err and "manifest unknown" in err and "found:" in err
    assert "expected:" in err and "what to do:" in err and "docker save | docker load" in err
    assert ("--forgejo-image" if service == "forgejo" else "--mcp-image") in err


def test_absent_local_mcp_refuses_without_pull_and_preserves_forgejo_checkpoint(tmp_path, capsys):
    row = observe(SOURCE, tmp_path / "work", "mcp", "gsj-mcp-service:local-preview")[0]
    assert row["outcome"] == ["SystemExit", "1"]
    assert not [event for event in row["events"] if event[0] in ("image_pull", "compose")]
    assert "pull-caller/run.json" in row["files"] and "pull-caller/mcp-config.yaml" not in row["files"]
    assert "a local build tag — nothing to pull" in capsys.readouterr().err


def test_readiness_interruption_keeps_checkpoint_and_can_resume_without_repull(tmp_path):
    rows = observe(SOURCE, tmp_path / "work", "mcp", IMAGE, repeat=True, wait_interrupt=True)
    assert rows[0]["outcome"] == ["KeyboardInterrupt", "controlled readiness boundary"]
    assert rows[1]["outcome"] == ["Boundary", "next corpus ingest"]
    assert "pull-caller/run.json" in rows[0]["files"]
    assert "pull-caller/mcp-config.yaml" in rows[0]["files"]
    assert not [event for event in rows[1]["events"] if event[0] == "image_pull"]
    assert all(row["lock_released"] for row in rows)


@pytest.mark.parametrize("service", ["forgejo", "mcp"])
def test_present_local_tag_skips_pull(tmp_path, service):
    row = observe(SOURCE, tmp_path / "work", service, "gsj-mcp-service:local-preview", present=True)[0]
    assert not [event for event in row["events"] if event[0] == "image_pull"]
    expected = None if service == "forgejo" else ["Boundary", "next corpus ingest"]
    assert row["outcome"] == expected


def test_forgejo_attempts_absent_bare_reference_unlike_mcp(tmp_path):
    row = observe(SOURCE, tmp_path / "work", "forgejo", "local-forgejo:preview", failure=True)[0]
    pulls = [event for event in row["events"] if event[0] == "image_pull"]
    assert len(pulls) == 1 and pulls[0][1:3] == ["local-forgejo:preview", "forgejo"]
    assert row["outcome"] == ["SystemExit", "1"]


def test_checkout_arm_default_selects_present_native_local_build(tmp_path):
    image = "gsj-mcp-service:0.5.1-arm64"
    row = observe(SOURCE, tmp_path / "work", "mcp", image, present=True, explicit=False)[0]
    assert row["outcome"] == ["Boundary", "next corpus ingest"]
    record = json.loads(row["files"]["pull-caller/run.json"]["body"])
    assert record["compose"]["mcp"]["image"] == image
    assert not [event for event in row["events"] if event[0] == "image_pull"]


@pytest.mark.parametrize("key", [PULL_OK, PULL_MISSING])
def test_pull_cli_shapes_match_real_cli_when_fixture_is_present(key):
    """No cold image download for this shape check; run on an explicitly owned daemon."""
    if os.environ.get("GSJ_CLI_SHAPES_SKIP"):
        pytest.skip("GSJ_CLI_SHAPES_SKIP is set")
    try:
        present = subprocess.run(["docker", "image", "inspect", IMAGE], text=True,
                                 capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"pull shapes: no usable Docker CLI/daemon: {exc}")
    if present.returncode:
        pytest.skip("pull shapes: the measured Forgejo fixture is absent; no cold download in this check")
    inspected = json.loads(present.stdout)[0]
    if (inspected["Os"], inspected["Architecture"]) != ("linux", "arm64"):
        pytest.skip("pull shapes: cached fixture has another platform; no cold layer transfer in this check")
    shape = CLI_SHAPES["shapes"][key]
    actual = subprocess.run(shape["argv"], text=True, capture_output=True, timeout=60)
    expected = cli_shape(key)
    assert (actual.returncode, actual.stdout, actual.stderr) == (expected.returncode, expected.stdout, expected.stderr)


def test_admin_program_shape_from_explicit_owned_container():
    """Read-only program remeasurement; fixture creation/cleanup belongs to its owner."""
    name, owner = os.environ.get("GSJ_PULL_ADMIN_CONTAINER"), os.environ.get("GSJ_PULL_ADMIN_OWNER")
    if os.environ.get("GSJ_CLI_SHAPES_SKIP") or not name or not owner:
        pytest.skip("admin shape: explicit owned container and owner label were not supplied")
    inspected = subprocess.run(["docker", "container", "inspect", name], text=True,
                               capture_output=True, timeout=10)
    assert inspected.returncode == 0, inspected.stderr
    container = json.loads(inspected.stdout)[0]
    assert container["Config"]["Labels"]["comparison.owner"] == owner
    shape = CLI_SHAPES["shapes"][ADMIN_LIST]
    assert container["Image"] == shape["measured"]["image_id"]
    actual = subprocess.run([part.replace("{name}", name) for part in shape["argv"]],
                            text=True, capture_output=True, timeout=30)
    expected = cli_shape(ADMIN_LIST, name=name)
    assert (actual.returncode, actual.stdout, actual.stderr) == (expected.returncode, expected.stdout, expected.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("service", choices=["forgejo", "mcp"])
    parser.add_argument("image")
    parser.add_argument("result", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--present", action="store_true")
    parser.add_argument("--failure", action="store_true")
    parser.add_argument("--repeat", action="store_true")
    options = parser.parse_args()
    rows = observe(options.source, options.work, options.service, options.image, present=options.present,
                   failure=options.failure, live=options.live, repeat=options.repeat)
    options.result.write_text(json.dumps({"source": str(options.source.resolve()),
                                          "source_sha256": hashlib.sha256((options.source / "estate/estate.py").read_bytes()).hexdigest(),
                                          "live_image_commands": options.live, "outcomes": rows}, indent=2) + "\n")
    last = rows[-1]["outcome"]
    if last and last[0] == "SystemExit":
        raise SystemExit(int(last[1]))
    if last and last[0] == "KeyboardInterrupt":
        raise SystemExit(130)
