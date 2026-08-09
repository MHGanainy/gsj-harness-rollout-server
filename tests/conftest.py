"""Shared CP-08 test fixtures: the real callback body and a fake rollout server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CALLBACK_FIXTURE = REPO_ROOT / "docs" / "polar" / "pi-corpus" / "callback_session_result.json"


@pytest.fixture(scope="session")
def callback_body() -> dict:
    with CALLBACK_FIXTURE.open() as handle:
        return json.load(handle)


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
