"""Shared test fixtures: the real callback body, the CP-09 pair, a fake rollout server."""

from __future__ import annotations

import array
import ast
import json
import struct
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CALLBACK_FIXTURE = REPO_ROOT / "docs" / "polar" / "pi-corpus" / "callback_session_result.json"
FIDELITY_CALLBACK = REPO_ROOT / "docs" / "polar" / "fidelity" / "callback_session_result.json"
FIDELITY_TRACE = REPO_ROOT / "docs" / "polar" / "fidelity" / "trace.json"
GOLDEN_TOKENS = REPO_ROOT / "docs" / "golden" / "mac" / "tokens.npz"


@pytest.fixture(scope="session")
def callback_body() -> dict:
    with CALLBACK_FIXTURE.open() as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def fidelity_callback() -> dict:
    """The CP-09 episode's full callback body — the second real episode of
    the first-episode-validate leg (row 23)."""
    with FIDELITY_CALLBACK.open() as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def fidelity_trace() -> dict:
    """The CP-09 collected trace, verbatim — 363 mask-1 positions of which
    15 are exactly `0.0` (the measured MLX bf16 artifact, row 27)."""
    with FIDELITY_TRACE.open() as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def golden_trace() -> dict:
    """`docs/golden/mac/tokens.npz` under COMPARISON.md's structural
    mapping — `prompts↔prompt_ids`, `responses↔response_ids`,
    `loss_mask↔loss_mask`, `rollout_log_probs↔response_logprobs`. The two
    non-token fields come from the golden's own record: the episode is
    `case_0001 / timestep-12` (`MANIFEST.md`) and both turns finished
    `stop` (`record.json` → `env.steps[*].stop_reason`; the MANIFEST
    states only `finish_state=completed`). The predecessor's record
    carries no message log (its transcript is a separate artifact),
    so the mapped trace exercises the logprob discipline and G5's
    metadata path, not G5's census."""
    arrays = _read_npz(GOLDEN_TOKENS)
    return {
        "prompt_ids": arrays["prompts"],
        "response_ids": arrays["responses"],
        "loss_mask": arrays["loss_mask"],
        "response_logprobs": arrays["rollout_log_probs"],
        "finish_reason": "stop",
        "metadata": {"timestep": 12},
    }


def _read_npz(path: Path) -> dict[str, list]:
    """Minimal `.npz` reader — stdlib only (numpy is not a dependency of
    this package, and adding one to read a fixture would be backwards)."""
    typecodes = {"<i8": "q", "<i4": "i", "<f4": "f", "<f8": "d"}
    out: dict[str, list] = {}
    with zipfile.ZipFile(path) as bundle:
        for name in bundle.namelist():
            with bundle.open(name) as handle:
                assert handle.read(6) == b"\x93NUMPY", f"{name} is not a .npy member"
                major = handle.read(2)[0]
                width = 2 if major == 1 else 4
                length = struct.unpack("<H" if major == 1 else "<I", handle.read(width))[0]
                header = ast.literal_eval(handle.read(length).decode("latin1"))
                assert not header["fortran_order"] and len(header["shape"]) == 1
                values = array.array(typecodes[header["descr"]])
                values.frombytes(handle.read())
                if sys.byteorder == "big":  # the members are little-endian
                    values.byteswap()
                out[name[: -len(".npy")]] = list(values)
    return out


class FakeRollout:
    """Minimal stand-in for Polar's rollout API: submit + poll.

    `statuses` is the sequence of TaskStatus bodies GET returns (the last
    one repeats forever) — mirroring `GET /rollout/task/{id}`.
    """

    def __init__(self, statuses: list[dict], submit_status: int = 200):
        self.statuses = statuses
        self.polls = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def _reply(self, payload: dict, status: int = 200) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self._reply({"task_id": "t-1", "status": "running"}, status=submit_status)

            def do_GET(self):
                index = min(fake.polls, len(fake.statuses) - 1)
                fake.polls += 1
                self._reply(fake.statuses[index])

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def fake_rollout_factory():
    servers: list[FakeRollout] = []

    def make(statuses: list[dict], **kwargs) -> FakeRollout:
        server = FakeRollout(statuses, **kwargs)
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()


def task_status(results: list[dict], status: str = "completed") -> dict:
    return {
        "task_id": "t-1",
        "status": status,
        "total_sessions": max(len(results), 1),
        "completed_sessions": len(results),
        "results": results,
        "result_paths": [],
    }
