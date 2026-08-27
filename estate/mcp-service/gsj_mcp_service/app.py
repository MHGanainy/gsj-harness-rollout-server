"""ASGI assembly: /health + token-scoped /mcp/<token> (ADR-0040(g)/(h)).

The MCP endpoint is the SDK's own streamable-http Starlette app (stateless —
every request stands alone, matching per-request token verification). This
wrapper owns the URL surface:

    GET  /health         liveness + readiness (state: indexing|ready|error)
    POST /admin/reindex  re-ingest + reuse-or-rebuild (CP-33, ADR-0047(d));
                         Authorization: Bearer <admin JWT> — same secret,
                         claims {admin: "reindex", exp}
    *    /mcp/<token>    the MCP endpoint; <token> is the per-episode JWT

The token travels in the URL path because that is the channel the rendered
`.pi/mcp.json` carries (`url` is used verbatim by the pi-mcp-extension).
Verification happens here, per request, BEFORE the SDK app sees anything:
tampered/expired/wrong-key/missing/unknown-case all produce a clear JSON-RPC
error body (HTTP 401; 503 while indexing) and the MCP layer is never
reached. Verified claims ride a contextvar into the tool bodies.
"""

from __future__ import annotations

import json

from mcp.server.transport_security import TransportSecuritySettings

from .state import AppState
from .tokens import TokenError, TokenVerifier, current_claims
from .tools import build_mcp

_MAX_ERROR_BODY_READ = 1 << 20  # read request body for the JSON-RPC id only


def build_asgi(state: AppState, verifier: TokenVerifier):
    server_cfg = state.config.server
    inner = build_mcp(state).streamable_http_app(
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=server_cfg.dns_rebinding_protection,
            allowed_hosts=server_cfg.allowed_hosts,
        ),
    )
    return _RootApp(inner, state, verifier)


class _RootApp:
    def __init__(self, inner, state: AppState, verifier: TokenVerifier) -> None:
        self._inner = inner
        self._state = state
        self._verifier = verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            # the SDK app's lifespan runs its session manager task group
            await self._inner(scope, receive, send)
            return
        if scope["type"] != "http":
            await self._send_plain(send, 404, b"not found")
            return

        path = scope["path"]
        if path == "/health":
            body = json.dumps(self._state.health()).encode()
            await self._send_json(send, 200, body)
            return
        if path == "/admin/reindex":
            await self._admin_reindex(scope, send)
            return
        if path == "/mcp" or path == "/mcp/":
            await self._reject(scope, receive, send, 401,
                               "unauthorized: missing token — the MCP URL is "
                               "/mcp/<token>")
            return
        if path.startswith("/mcp/"):
            token = path[len("/mcp/"):]
            if self._state.status != "ready":
                detail = (self._state.error if self._state.status == "error"
                          else "still indexing")
                await self._reject(
                    scope, receive, send, 503,
                    f"service not ready (state: {self._state.status} — "
                    f"{detail}); retry after /health reports state=ready")
                return
            try:
                claims = self._verifier.verify(token)
                self._validate_scope(claims)
            except TokenError as error:
                await self._reject(scope, receive, send, 401,
                                   f"unauthorized: {error.detail}")
                return
            scope = dict(scope)
            scope["path"] = "/mcp"
            scope["raw_path"] = b"/mcp"
            ctx_token = current_claims.set(claims)
            try:
                await self._inner(scope, receive, send)
            finally:
                current_claims.reset(ctx_token)
            return
        await self._send_plain(send, 404, b"not found")

    async def _admin_reindex(self, scope, send) -> None:
        """POST /admin/reindex (CP-33, ADR-0047(d)): guarded by an admin JWT
        signed with the SAME token secret (claims {admin: "reindex", exp} —
        episode tokens never authorize this, see TokenVerifier.verify_admin).
        202 {"reindex": "started"} kicks off the background re-ingest;
        202 {"reindex": "already-indexing"} while one is running (idempotent —
        no second thread). Poll /health until state=ready."""
        if scope.get("method") != "POST":
            await self._send_json(send, 405, json.dumps(
                {"error": "method not allowed — POST /admin/reindex"}).encode())
            return
        header = dict(scope.get("headers") or {}).get(b"authorization", b"")
        token = header.decode(errors="replace")
        if token.lower().startswith("bearer "):
            token = token[len("bearer "):].strip()
        else:
            token = ""
        if not token:
            await self._send_json(send, 401, json.dumps(
                {"error": "unauthorized: Authorization: Bearer <admin token> "
                          "required"}).encode())
            return
        try:
            self._verifier.verify_admin(token)
        except TokenError as error:
            await self._send_json(send, 401, json.dumps(
                {"error": f"unauthorized: {error.detail}"}).encode())
            return
        verdict = self._state.request_reindex()
        await self._send_json(send, 202, json.dumps(
            {"reindex": verdict, "state": self._state.status}).encode())

    def _validate_scope(self, claims) -> None:
        """Ready-state claim validation: the case must be in the frozen
        dataset and the timestep within its page range."""
        index = self._state.cases.get(claims.case_id)
        if index is None:
            raise TokenError(
                "unknown_case",
                f"unknown case {claims.case_id!r} — not in the frozen dataset")
        if not 1 <= claims.timestep <= index.n_pages:
            raise TokenError(
                "bad_timestep",
                f"timestep {claims.timestep} outside 1..{index.n_pages} "
                f"for {claims.case_id}")

    async def _reject(self, scope, receive, send, status: int, message: str):
        """Clear JSON-RPC error body; echoes the request's id when one can be
        read, so well-behaved clients correlate the failure."""
        request_id = None
        if scope.get("method") == "POST":
            body = b""
            while len(body) <= _MAX_ERROR_BODY_READ:
                event = await receive()
                body += event.get("body", b"")
                if not event.get("more_body"):
                    break
            try:
                request_id = json.loads(body.decode()).get("id")
            except (ValueError, AttributeError, UnicodeDecodeError):
                request_id = None
        payload = json.dumps({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32001, "message": message},
        }).encode()
        await self._send_json(send, status, payload)

    @staticmethod
    async def _send_json(send, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _send_plain(send, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
