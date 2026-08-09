"""SERVER — callback endpoint + validation (ADR-0008 §2).

Validates the POSTed body, never the rollout server's disk: the on-disk
`ses_*.json` strips `trajectory.status`/`error` (CP-07 finding 5,
binding). `POST /callbacks/session_result` accepts a single
`SessionResult` (the per-session shape — the fixture's contract) or the
manager's terminal `TaskResult` envelope (`results: [SessionResult…]` —
the zero-patch live delivery via `TaskRequest.callback_url`); every
result runs `checks.validate_session_result` and is persisted verbatim
to `<traces_dir>/<session_id>.json` or quarantined with its findings to
`<quarantine_dir>/<session_id>.json` — forensics beat counters. Both
outcomes answer Polar 200 (`{"accepted": n, "rejected": m}`): rejection
is our validation decision, not a delivery failure; malformed bodies get
400. Stdlib HTTP on purpose (R1: FastAPI named, rejected — ADR-0008 §2);
no signal handlers here, ever (the embeddability property — `cli.serve`
owns signals).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import checks

logger = logging.getLogger("gsj_rollout.receiver")

# session_id becomes a filename — never let wire input walk the filesystem.
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _as_session_results(body: Any) -> list[dict[str, Any]]:
    """Unwrap either accepted shape; raise ValueError on anything else."""
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        candidates = body["results"]  # the manager's TaskResult envelope
    elif isinstance(body, dict):
        candidates = [body]
    else:
        raise ValueError("body must be a JSON object")
    for result in candidates:
        session_id = result.get("session_id") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or "trajectory" not in result
            or not isinstance(session_id, str)
            or not _SAFE_SESSION_ID.fullmatch(session_id)
        ):
            raise ValueError("not a SessionResult: needs a safe session_id and a trajectory")
    return candidates


class Receiver:
    """The callback endpoint. Construct, then `serve_forever()`/`shutdown()`."""

    def __init__(self, host: str, port: int, traces_dir: str, quarantine_dir: str):
        self.traces_dir = traces_dir
        self.quarantine_dir = quarantine_dir
        self.accepted = 0
        self.rejected = 0
        os.makedirs(traces_dir, exist_ok=True)
        os.makedirs(quarantine_dir, exist_ok=True)
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                logger.debug("%s %s", self.address_string(), fmt % args)

            def _reply(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path == "/healthz":
                    self._reply(200, {"status": "ok", "accepted": receiver.accepted,
                                      "rejected": receiver.rejected})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self) -> None:
                if self.path != "/callbacks/session_result":
                    self._reply(404, {"error": "not found"})
                    return
                try:
                    raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    accepted, rejected = receiver.ingest(json.loads(raw))
                except (ValueError, KeyError) as exc:
                    self._reply(400, {"error": str(exc)})
                    return
                self._reply(200, {"accepted": accepted, "rejected": rejected})

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._serving = threading.Event()

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def ingest(self, body: Any) -> tuple[int, int]:
        """Validate and land every SessionResult in `body`; (accepted, rejected)."""
        accepted = rejected = 0
        for result in _as_session_results(body):
            session_id = str(result["session_id"])
            findings = checks.validate_session_result(result)
            if findings:
                self._write(self.quarantine_dir, session_id,
                            {"findings": findings, "session_result": result})
                logger.warning("rejected %s: %s", session_id, findings)
                rejected += 1
                self.rejected += 1
            else:
                self._write(self.traces_dir, session_id, result)
                logger.info("accepted %s", session_id)
                accepted += 1
                self.accepted += 1
        return accepted, rejected

    @staticmethod
    def _write(directory: str, session_id: str, payload: dict[str, Any]) -> None:
        path = os.path.join(directory, f"{session_id}.json")
        tmp = f"{path}.tmp"
        with open(tmp, "w") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)

    def serve_forever(self) -> None:
        self._serving.set()
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        # Stdlib trap: BaseServer.shutdown() blocks forever unless
        # serve_forever's loop is there to acknowledge it.
        if self._serving.is_set():
            self._httpd.shutdown()
        self._httpd.server_close()
