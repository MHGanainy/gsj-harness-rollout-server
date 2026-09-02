"""CP-08 CLI tests: help, stated exit codes, bounded exit, embeddability."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, task_status

from gsj_rollout import cli

FIXTURE = Path(__file__).parent / "fixtures" / "rollout.yaml"


def _config_for(tmp_path, base_url: str) -> Path:
    doc = yaml.safe_load(FIXTURE.read_text())
    host, port = base_url.removeprefix("http://").split(":")
    doc["polar"]["rollout"] = {"host": host, "port": int(port)}
    doc["receiver"]["traces_dir"] = str(tmp_path / "traces")
    doc["receiver"]["port"] = 0  # never collide with a real port in tests
    path = tmp_path / "rollout.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_help_exits_zero(capsys):
    for argv in (["--help"], ["serve", "--help"], ["submit", "--help"]):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(argv)
        assert excinfo.value.code == 0
    assert "Collect-N semantics" in capsys.readouterr().out  # row 26, stated


def test_bad_config_exits_2(tmp_path, capsys):
    submit = ["submit", "--case", "case_0001", "--timestep", "12", "--prompt", "p"]
    assert cli.main(submit + ["--config", str(tmp_path / "missing.yaml")]) == 2
    bad = tmp_path / "bad.yaml"
    doc = yaml.safe_load(FIXTURE.read_text())
    doc["estate"]["unknown_knob"] = 1
    bad.write_text(yaml.safe_dump(doc))
    assert cli.main(submit + ["--config", str(bad)]) == 2
    assert cli.main(["serve", "--config", str(bad), "--render-only"]) == 2
    assert "unknown key 'unknown_knob'" in capsys.readouterr().err
    broken = tmp_path / "broken.yaml"
    broken.write_text("estate: [unclosed")  # yaml.YAMLError, not ValueError
    assert cli.main(submit + ["--config", str(broken)]) == 2
    assert "invalid YAML" in capsys.readouterr().err


def test_unreachable_server_exits_3(tmp_path):
    config = _config_for(tmp_path, "http://127.0.0.1:1")  # nothing listens on port 1
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p"])
    assert code == 3


def test_reachable_but_erroring_server_exits_3(tmp_path, fake_rollout_factory, capsys):
    server = fake_rollout_factory([], submit_status=500)
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p"])
    assert code == 3  # an HTTP error is never conflated with exit 1's meaning
    assert "--task-id" not in capsys.readouterr().err  # the 409 hint is 409-only


def test_rejected_episode_exits_1(tmp_path, fake_rollout_factory, callback_body, capsys):
    import copy

    errored = copy.deepcopy(callback_body)
    errored["session_id"] = "sk-polar-cli-errored"
    errored["status"] = "ERROR"
    server = fake_rollout_factory([task_status([errored])])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p", "--poll-interval", "0.02"])
    assert code == 1  # a consumed attempt that was not collected
    out = capsys.readouterr().out
    assert "rejected sk-polar-cli-errored" in out and "collected 0/1" in out


def test_bounded_exit_on_never_terminal_task(tmp_path, fake_rollout_factory):
    server = fake_rollout_factory([task_status([], status="running")])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p",
                     "--timeout", "0.3", "--grace", "0", "--poll-interval", "0.02"])
    assert code == 1  # terminal for us, not collected — never hangs


def test_submit_collects_and_writes_out(tmp_path, fake_rollout_factory, body13, capsys):
    server = fake_rollout_factory([task_status([body13])])
    config = _config_for(tmp_path, server.base_url)
    out = tmp_path / "collected"
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p", "--out", str(out),
                     "--poll-interval", "0.02"])
    assert code == 0
    assert (out / f"{body13['session_id']}.json").exists()
    # ADR-0025: the count line is unconditional — zero is a measurement too.
    assert "length-terminated: 0/1 accepted episodes" in capsys.readouterr().out


def test_serve_render_only(tmp_path, capsys):
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    rendered = tmp_path / "topology.rendered.yaml"
    assert rendered.exists()
    assert yaml.safe_load(rendered.read_text())["gateway"]["nodes"][0]["model_served"] == "Qwen/Qwen3-0.6B"
    out = capsys.readouterr().out
    assert "serve_rollout" in out and "serve_gateway" in out


# --- CP-27: the strangerward lift (wishlist 19, 22; F-20, F-21) -----------


def test_module_form_help_exits_zero_and_prints():
    """Wishlist 19's other half: the module form must behave like the
    console script, not like an import."""
    result = subprocess.run([sys.executable, "-m", "gsj_rollout.cli", "--help"],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0
    assert "gsj-rollout" in result.stdout


def test_module_form_serve_bad_config_exits_2_not_silently_0(tmp_path):
    """Hypothesis (f), measured at CP-26: `python -m gsj_rollout.cli serve`
    exited 0 with zero bytes of output having started nothing. With the
    __main__ guard it takes the CP-08 contract: stated exit code, says why."""
    result = subprocess.run(
        [sys.executable, "-m", "gsj_rollout.cli", "serve",
         "--config", str(tmp_path / "missing.yaml")],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2  # EXIT_CONFIG, not the silent 0
    assert result.stderr.strip()   # and it says why


def test_serve_instructions_survive_a_pipe(tmp_path):
    """F-20: the topology + the two Polar commands are the session's only
    instructions, and block-buffered stdout lost them under `nohup … > log`.
    Through a pipe (not a tty), they must arrive WHILE the server runs."""
    import queue
    import threading
    import time

    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    proc = subprocess.Popen(
        [sys.executable, "-m", "gsj_rollout.cli", "serve", "--config", str(config)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO_ROOT,
        # a parent env with PYTHONUNBUFFERED set would make this test pass
        # without the flush — pin it off so the coverage is unconditional;
        # PATH empty pins shutil.which("polar") to None (CP-65's third-shape
        # branch cannot fire), so the F-21 vendored-path assert holds on a
        # host that has a `polar` on PATH — a subprocess takes no monkeypatch
        env={**os.environ, "PYTHONUNBUFFERED": "", "PATH": ""})
    channel: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=lambda: [channel.put(line) for line in proc.stdout],
                     daemon=True).start()
    lines: list[str] = []
    try:
        deadline = time.monotonic() + 15.0
        # collect until the serve block's last line arrives — the line COUNT
        # varies by install shape (the F-45 NOTE prints when the Polar venv
        # is absent, which is every hosted CI runner; measured CP-33)
        while (time.monotonic() < deadline
               and not any("receiver listening" in line for line in lines)):
            try:
                lines.append(channel.get(timeout=0.2))
            except queue.Empty:
                pass
        assert proc.poll() is None, (proc.returncode, proc.stderr.read())
        joined = "".join(lines)
        assert "serve_rollout" in joined and "serve_gateway" in joined
        assert "receiver listening" in joined
        # F-21: the printed Polar path is absolute, not cwd-relative
        assert str(REPO_ROOT / "vendor" / "polar" / ".venv") in joined
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_no_signal_handler_installed_at_import():
    # The predecessor's embeddability property, checked in a clean interpreter.
    probe = (
        "import signal, gsj_rollout.cli, gsj_rollout.receiver;"
        "assert signal.getsignal(signal.SIGINT) is signal.default_int_handler;"
        "assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL;"
        "print('clean')"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                            text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"


# --- CP-33: the wishlist cluster ------------------------------------------


def test_serve_printout_says_which_case_when_no_polar_anywhere(tmp_path, capsys, monkeypatch):
    """F-45 (wishlist 29): under a pip install the resolved Polar path is
    site-packages and no wheel ships vendor/ — run as printed, the command
    died ENOENT at the stranger test. The printout must say which case it
    is and what the other needs, with <checkout> placeholders that stay
    honest instead of a path the library cannot know."""
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)  # CP-65: no PATH polar here
    real_exists, real_isdir = os.path.exists, os.path.isdir
    monkeypatch.setattr(cli.os.path, "exists",
                        lambda p: False if p.endswith(os.path.join("bin", "polar"))
                        else real_exists(p))
    monkeypatch.setattr(cli.os.path, "isdir",
                        lambda p: False if p.endswith(os.path.join("vendor", "polar"))
                        else real_isdir(p))
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    out = capsys.readouterr().out
    assert "does not exist" in out and "installed wheel" in out
    assert "<checkout>/vendor/polar/.venv/bin/polar serve_rollout" in out
    assert "PYTHONPATH=<checkout>" in out


def test_serve_printout_hints_the_unbuilt_venv(tmp_path, capsys, monkeypatch):
    """Row 22's residual (F-21's other half): a fresh checkout holds
    vendor/polar but no .venv — the hint names the provisioning recipe
    (REVENDOR.md, which includes the A-14 gsj_rollout install) instead of
    leaving the stranger an unexplained ENOENT."""
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)  # CP-65: no PATH polar here
    real_exists, real_isdir = os.path.exists, os.path.isdir
    monkeypatch.setattr(cli.os.path, "exists",
                        lambda p: False if p.endswith(os.path.join("bin", "polar"))
                        else real_exists(p))
    # CP-51 (CP-47's accidental coupling): cli.py picks this branch on
    # isdir(vendor/polar) — answer it here, so the suite no longer needs the
    # vendored tree on disk to pass.
    monkeypatch.setattr(cli.os.path, "isdir",
                        lambda p: True if p.endswith(os.path.join("vendor", "polar"))
                        else real_isdir(p))
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    out = capsys.readouterr().out
    assert "venv is unbuilt" in out and "REVENDOR.md" in out


def test_collect_prints_the_length_terminated_count(tmp_path, fake_rollout_factory,
                                                    body13, capsys):
    """ADR-0025 (F-47): tail finish_reason=length qualifies BY DESIGN — at
    CP-32 7/72 thinking-on episodes entered the batch silently. The collect
    surface now says the count out loud, unconditionally."""
    import copy

    truncated = copy.deepcopy(body13)
    truncated["session_id"] = "sk-polar-cli-truncated"
    truncated["trajectory"]["traces"][0]["finish_reason"] = "length"
    server = fake_rollout_factory([task_status([body13, truncated])])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p", "--episodes", "2",
                     "--poll-interval", "0.02"])
    assert code == 0  # both qualified — length is in TR1's allowlist
    out = capsys.readouterr().out
    assert "length-terminated: 1/2 accepted episodes" in out
    assert "ADR-0025" in out


def _bank(tmp_path, rows):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as parquet
    schema = pa.schema([
        ("case_id", pa.string()), ("timestep", pa.int64()),
        ("prompt_id", pa.string()), ("split", pa.string()),
        ("prompt_source", pa.string()), ("prompt_text", pa.string()),
        ("skill_card_text", pa.string()), ("sandbox_image", pa.string()),
    ])
    path = tmp_path / "taskbank.parquet"
    parquet.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    return path


_IMAGE = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"  # the fixture's runtime.image
_FREE_ROW = {"case_id": "case_0001", "timestep": 12, "prompt_id": "p-free",
             "split": "train", "prompt_source": "free",
             "prompt_text": "the instruction", "skill_card_text": None,
             "sandbox_image": _IMAGE}
_SKILL_ROW = {"case_id": "case_0002", "timestep": 7, "prompt_id": "p-skill",
              "split": "eval", "prompt_source": "skill:summarize",
              "prompt_text": None, "skill_card_text": "# The card\n",
              "sandbox_image": _IMAGE}


def test_from_bank_submits_the_row_with_zero_translation(tmp_path, fake_rollout_factory,
                                                         body13):
    """Wishlist 20: the CP-24 bank's own columns render the TaskRequest —
    triple, prompt text, prompt_source, split — nothing re-typed by hand,
    exactly the ADR-0022 zero-translation property, now reachable from the
    CLI (`train.py` was the only path before this)."""
    bank = _bank(tmp_path, [_FREE_ROW, _SKILL_ROW])
    server = fake_rollout_factory([task_status([body13])])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--from-bank", str(bank),
                     "--poll-interval", "0.02"])
    assert code == 0
    request = server.submitted[0]
    assert request["instruction"] == "the instruction"
    assert request["metadata"]["case_id"] == "case_0001"
    assert request["metadata"]["timestep"] == 12
    assert request["metadata"]["prompt_source"] == "free"
    assert request["metadata"]["split"] == "train"
    assert "skill_card_hash" not in request["metadata"]


def test_from_bank_skill_row_states_the_card_hash(tmp_path, fake_rollout_factory, body13):
    """The skill row's resolved card text is the instruction AND the G1
    hash statement (convention 1) — `--row` picks it."""
    bank = _bank(tmp_path, [_FREE_ROW, _SKILL_ROW])
    server = fake_rollout_factory([task_status([body13])])
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--from-bank", str(bank),
                     "--row", "1", "--poll-interval", "0.02"])
    assert code == 0
    request = server.submitted[0]
    assert request["instruction"] == "# The card\n"
    assert request["metadata"]["prompt_source"] == "skill:summarize"
    assert request["metadata"]["split"] == "eval"
    assert len(request["metadata"]["skill_card_hash"]) == 64


def test_from_bank_errors_name_their_cause(tmp_path, capsys, monkeypatch):
    """Each refusal names the fact and the fix (the CP-27 message
    standard): range, mixed flags, image mismatch, missing pyarrow."""
    import copy

    bank = _bank(tmp_path, [_FREE_ROW])
    config = _config_for(tmp_path, "http://127.0.0.1:9")  # never dialed
    assert cli.main(["submit", "--config", str(config), "--from-bank", str(bank),
                     "--row", "5"]) == 2
    assert "out of range" in capsys.readouterr().err

    assert cli.main(["submit", "--config", str(config), "--from-bank", str(bank),
                     "--case", "case_0001"]) == 2
    assert "drop --case" in capsys.readouterr().err

    foreign = copy.deepcopy(_FREE_ROW)
    foreign["sandbox_image"] = "ghcr.io/somewhere/else:latest"
    foreign_bank_dir = tmp_path / "foreign"
    foreign_bank_dir.mkdir()
    foreign_bank = _bank(foreign_bank_dir, [foreign])
    assert cli.main(["submit", "--config", str(config),
                     "--from-bank", str(foreign_bank)]) == 2
    err = capsys.readouterr().err
    assert "sandbox_image" in err and "runtime.image" in err

    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    assert cli.main(["submit", "--config", str(config), "--from-bank", str(bank)]) == 2
    assert "needs pyarrow" in capsys.readouterr().err


# --- CP-65: the cli.py allowance (ADR-0028; rows 51 (f)/(g), 37) ----------


def test_second_submit_conflict_names_task_id(tmp_path, fake_rollout_factory, capsys):
    """Row 51 (f), measured at CP-61: a second submit while one runs answers an
    opaque `409 Conflict` — the message must name --task-id as the cure."""
    server = fake_rollout_factory([], submit_status=409)
    config = _config_for(tmp_path, server.base_url)
    code = cli.main(["submit", "--config", str(config), "--case", "case_0001",
                     "--timestep", "12", "--prompt", "p"])
    assert code == 3
    err = capsys.readouterr().err
    assert "409" in err and "--task-id" in err


def test_serve_never_rewrites_an_identical_topology_render(tmp_path):
    """Row 51 (g), measured at CP-61: Polar's container legs read the rendered
    topology at THEIR start, and a receiver (re)start rewrote it in place.
    Identical bytes must be left untouched (same inode, same mtime); a real
    config change must land whole via rename, with no .tmp residue."""
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    rendered = tmp_path / "topology.rendered.yaml"
    first = rendered.stat()
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    second = rendered.stat()
    assert (second.st_mtime_ns, second.st_ino) == (first.st_mtime_ns, first.st_ino)
    doc = yaml.safe_load(config.read_text())
    doc["polar"]["rollout"] = {"host": "10.9.9.9", "port": 8123}
    config.write_text(yaml.safe_dump(doc))
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    assert "10.9.9.9" in rendered.read_text()  # a changed config DOES re-render
    assert not list(tmp_path.glob("topology.rendered.yaml.*"))  # no tmp residue


def test_serve_printout_third_shape_bare_polar_on_path(tmp_path, capsys, monkeypatch):
    """Row 37 (F-77): inside the estate image the `polar` console script is on
    PATH beside an installed gsj_rollout — the printout must give the bare
    runnable commands, not clone-the-repo advice no container user can run."""
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    real_exists = os.path.exists
    monkeypatch.setattr(cli.os.path, "exists",
                        lambda p: False if p.endswith(os.path.join("bin", "polar"))
                        else real_exists(p))
    beside = os.path.join(os.path.dirname(sys.executable), "polar")  # co-installed
    monkeypatch.setattr(cli.shutil, "which",
                        lambda cmd: beside if cmd == "polar" else None)
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    out = capsys.readouterr().out
    assert f"  {beside} serve_rollout -c " in out
    assert f"{beside} serve_gateway -c " in out
    assert "PYTHONPATH" not in out and "NOTE:" not in out and "<checkout>" not in out


def test_serve_printout_foreign_path_polar_still_hints(tmp_path, capsys, monkeypatch):
    """Row 37's discriminator: a PATH `polar` that is NOT beside this
    interpreter (a different tool, or a Polar whose env cannot import
    gsj_rollout) is not the co-installed shape — the F-45/REVENDOR hints
    must survive it, and no bare command may name a foreign binary."""
    config = _config_for(tmp_path, "http://127.0.0.1:8080")
    real_exists, real_isdir = os.path.exists, os.path.isdir
    monkeypatch.setattr(cli.os.path, "exists",
                        lambda p: False if p.endswith(os.path.join("bin", "polar"))
                        else real_exists(p))
    monkeypatch.setattr(cli.os.path, "isdir",
                        lambda p: True if p.endswith(os.path.join("vendor", "polar"))
                        else real_isdir(p))
    foreign = str(tmp_path / "polar")  # never the interpreter's own bin dir
    monkeypatch.setattr(cli.shutil, "which",
                        lambda cmd: foreign if cmd == "polar" else None)
    assert cli.main(["serve", "--config", str(config), "--render-only"]) == 0
    out = capsys.readouterr().out
    assert "NOTE:" in out and "REVENDOR.md" in out
    assert foreign not in out


def test_size_law_census_is_machine_checked():
    """ADR-0028 (2,016) → ADR-0033 (2,034): scope law 2 is the landed size
    EXACTLY, zero headroom by design, an equality in both directions
    (ADR-0021's form applied to the whole census). Growth is a
    stop-and-justify; a shrink must lower the law with it. Moving this number
    is an ADR's decision plus this line, together. (Homed here by CP-65's
    freeze-lift; the assertion, not the address, is the decision.)"""
    census = sum(path.read_text().count("\n")  # [!.]*: wc -l's shell glob skips dotfiles
                 for path in sorted((REPO_ROOT / "gsj_rollout").glob("[!.]*.py")))
    assert census == 2034, f"gsj_rollout census {census} != ADR-0033's exact 2,034"
