"""Raw ASGI contract, including the historical non-HTTP rejection behavior."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from gsj_mcp_service.app import _RootApp


@pytest.mark.parametrize("helper,content_type", [
    ("_send_json", b"application/json"),
    ("_send_plain", b"text/plain"),
])
@pytest.mark.parametrize("status", [200, 202, 204, 304, 401, 404, 405, 503])
@pytest.mark.parametrize("body", [
    b"", b"not found", "é € 中文".encode(),
    json.dumps({"text": 'é\n\t"\\', "null": None}).encode(),
    json.dumps({"nan": float("nan"), "inf": float("inf")}).encode(),
])
def test_helpers_preserve_complete_message_sequence(helper, content_type, status, body):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(getattr(_RootApp, helper)(send, status, body))
    assert messages == [
        {"type": "http.response.start", "status": status,
         "headers": [(b"content-type", content_type),
                     (b"content-length", str(len(body)).encode())]},
        {"type": "http.response.body", "body": body},
    ]


@pytest.mark.parametrize("scope_type", ["websocket", "custom"])
def test_non_http_rejection_keeps_http_messages(scope_type):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(_RootApp(None, None, None)({"type": scope_type}, None, send))
    assert messages == [
        {"type": "http.response.start", "status": 404,
         "headers": [(b"content-type", b"text/plain"),
                     (b"content-length", b"9")]},
        {"type": "http.response.body", "body": b"not found"},
    ]


@pytest.mark.parametrize("helper", ["_send_json", "_send_plain"])
@pytest.mark.parametrize("fail_at", [1, 2])
@pytest.mark.parametrize("failure_type", [RuntimeError, asyncio.CancelledError])
def test_send_failure_and_cancellation_propagate_unchanged(helper, fail_at, failure_type):
    failure = failure_type("send stopped")
    messages = []

    async def send(message):
        messages.append(message)
        if len(messages) == fail_at:
            raise failure

    with pytest.raises(failure_type) as raised:
        asyncio.run(getattr(_RootApp, helper)(send, 503, b"unavailable"))
    assert raised.value is failure
    assert len(messages) == fail_at
    assert [m["type"] for m in messages] == [
        "http.response.start", "http.response.body"][:fail_at]


def test_health_keeps_existing_json_serialization_and_headers():
    messages = []
    state = SimpleNamespace(health=lambda: {"state": "ready", "text": "é",
                                          "value": float("nan")})

    async def send(message):
        messages.append(message)

    asyncio.run(_RootApp(None, state, None)(
        {"type": "http", "path": "/health"}, None, send))
    body = b'{"state": "ready", "text": "\\u00e9", "value": NaN}'
    assert messages == [
        {"type": "http.response.start", "status": 200,
         "headers": [(b"content-type", b"application/json"),
                     (b"content-length", str(len(body)).encode())]},
        {"type": "http.response.body", "body": body},
    ]


def test_missing_token_keeps_json_rpc_id_and_error_bytes():
    messages = []

    async def receive():
        return {"type": "http.request", "body": b'{"id": "corr-17"}'}

    async def send(message):
        messages.append(message)

    asyncio.run(_RootApp(None, None, None)(
        {"type": "http", "path": "/mcp", "method": "POST"}, receive, send))
    body = (b'{"jsonrpc": "2.0", "id": "corr-17", "error": {"code": -32001, '
            b'"message": "unauthorized: missing token \\u2014 the MCP URL is '
            b'/mcp/<token>"}}')
    assert messages == [
        {"type": "http.response.start", "status": 401,
         "headers": [(b"content-type", b"application/json"),
                     (b"content-length", str(len(body)).encode())]},
        {"type": "http.response.body", "body": body},
    ]
