"""Token verification at the HTTP surface (ADR-0040(g)): JWT HS256 in the URL
path, verified per request BEFORE the SDK app sees anything. Every reject is
an HTTP 401 JSON-RPC error envelope that echoes the request id, names the
failure, and NEVER carries tool data. Raw urllib POSTs — no MCP client."""

from __future__ import annotations

import time

import pytest

from helpers import (
    WRONG_SECRET,
    assert_reject,
    flip_payload_char,
    mint_token,
    post_mcp,
    tamper_timestep,
)


def _post(server, token, **kwargs):
    return post_mcp(f"{server.base_url}/mcp/{token}", **kwargs)


def test_tampered_payload_char_rejected(server):
    """Flipping one character of the payload segment breaks the HMAC — 401
    "token invalid", no tool data."""
    token = flip_payload_char(mint_token("case_0001", 5))
    status, body = _post(server, token)
    assert_reject(status, body, "unauthorized", "token invalid")


def test_tampered_timestep_reencoded_rejected(server):
    """Re-encoding the payload with an escalated timestep (5 -> 12) while
    keeping the original signature is the classic cutoff-widening attack —
    the signature no longer matches, 401."""
    token = tamper_timestep(mint_token("case_0001", 5), 12)
    status, body = _post(server, token, rpc_id=11)
    assert_reject(status, body, "unauthorized", "token invalid", rpc_id=11)


def test_expired_token_rejected_mentioning_expiry(server):
    """exp in the past beyond the 30s leeway — the reject names expiry."""
    token = mint_token("case_0001", 5, exp=int(time.time()) - 120)
    status, body = _post(server, token)
    assert_reject(status, body, "unauthorized", "expired")


def test_wrong_key_signature_rejected(server):
    """A structurally valid JWT signed with a different secret is invalid."""
    token = mint_token("case_0001", 5, secret=WRONG_SECRET)
    status, body = _post(server, token)
    assert_reject(status, body, "unauthorized", "token invalid")


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_missing_token_rejected(server, path):
    """POST /mcp and /mcp/ carry no token segment — 401 naming the missing
    token and the expected URL shape."""
    status, body = post_mcp(f"{server.base_url}{path}")
    assert_reject(status, body, "unauthorized", "missing token")


def test_unknown_case_rejected(server):
    """A validly signed token for a case outside the frozen dataset is
    rejected mentioning the unknown case id."""
    token = mint_token("case_0999", 5)
    status, body = _post(server, token)
    assert_reject(status, body, "unauthorized", "unknown case", "case_0999")


@pytest.mark.parametrize("case_id,timestep", [
    ("case_0001", 0),      # below the 1..N floor
    ("case_0001", 19),     # case_0001 has 18 pages
    ("case_0003", 16),     # case_0003 has 15 pages
    ("case_0002", 23),     # case_0002 has 22 pages
])
def test_timestep_out_of_range_rejected(server, case_id, timestep):
    """timestep must satisfy 1 <= T <= n_pages for the token's case; 0 and
    beyond-last-page values are 401s naming the valid range."""
    token = mint_token(case_id, timestep)
    status, body = _post(server, token)
    assert_reject(status, body, "unauthorized", f"timestep {timestep}",
                  "outside 1..")


def test_garbage_token_rejected(server):
    """A non-JWT path segment is a clean 401, not a server error."""
    status, body = _post(server, "not-a-jwt-at-all")
    assert_reject(status, body, "unauthorized", "token invalid")


def test_rejects_echo_request_id(server):
    """The reject body correlates to the request: jsonrpc 2.0 envelope with
    the POSTed id echoed back."""
    status, body = _post(server, "garbage", rpc_id="corr-42")
    assert_reject(status, body, "unauthorized", rpc_id="corr-42")


def test_foreign_host_header_is_not_rejected_by_default(server):
    """CP-29 regression: the SDK's DNS-rebinding protection 421'd
    ``Host: host.docker.internal:8790`` and killed every containerized
    episode's eager MCP connect. Default config DISABLES that check (the
    per-request token is the security boundary; clients are not browsers;
    the legitimate Host varies by channel) — a foreign Host header must
    reach token verification, never 421."""
    import http.client
    import json as _json

    host, port = server.base_url.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    envelope = _json.dumps({
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": "case_status", "arguments": {}}}).encode()
    token = mint_token("case_0001", 5)
    conn.request("POST", f"/mcp/{token}", body=envelope, headers={
        "Host": "host.docker.internal:8790",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    response = conn.getresponse()
    status, body = response.status, response.read().decode()
    conn.close()
    assert status != 421, f"DNS-rebinding check regressed: {status} {body[:200]}"
    assert status == 200, (status, body[:200])
