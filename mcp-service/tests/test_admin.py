"""POST /admin/reindex (CP-33, ADR-0047(d)): auth required (admin claims,
never episode tokens), idempotent while indexing, /health transitions back
to ready, and the pipeline's stdlib mint verifies against the service."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

import jwt
import pytest

from helpers import (
    REPO_ROOT,
    SECRET,
    WRONG_SECRET,
    free_port,
    get_health,
    mint_token,
    spawn_server,
    stop_server,
    write_config,
)


def mint_admin(secret: str = SECRET, exp_in: int = 300) -> str:
    return jwt.encode({"admin": "reindex", "exp": int(time.time()) + exp_in},
                      secret, algorithm="HS256")


def post_reindex(base_url: str, token: str | None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(f"{base_url}/admin/reindex",
                                     method="POST", data=b"", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture(scope="module")
def admin_server(tmp_path_factory, shared_dirs, built_state):
    """A dedicated server over the prebuilt index — reindexing here never
    races the shared session server."""
    run_dir = tmp_path_factory.mktemp("srv-admin")
    port = free_port()
    config_path = write_config(
        run_dir, repos=["case_0001", "case_0002", "case_0003", "case_0004"],
        clone_cache_dir=shared_dirs["clones"], index_path=shared_dirs["index"],
        port=port)
    proc, log_file = spawn_server(run_dir, config_path, port)
    yield proc
    stop_server(proc, log_file)


def wait_ready(base_url: str, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = get_health(base_url)
        if health and health["state"] == "ready":
            return health
        if health and health["state"] == "error":
            raise AssertionError(f"reindex errored: {health.get('error')}")
        time.sleep(0.05)
    raise AssertionError(f"not ready within {timeout}s")


# -- auth ---------------------------------------------------------------------

def test_no_auth_rejected(admin_server):
    status, body = post_reindex(admin_server.base_url, None)
    assert status == 401
    assert "Bearer" in body["error"]


def test_garbage_token_rejected(admin_server):
    status, body = post_reindex(admin_server.base_url, "not-a-jwt")
    assert status == 401
    assert "invalid" in body["error"]


def test_episode_token_never_authorizes_admin(admin_server):
    status, body = post_reindex(admin_server.base_url,
                                mint_token("case_0001", 5))
    assert status == 401
    assert "admin='reindex' required" in body["error"]


def test_wrong_secret_rejected(admin_server):
    status, body = post_reindex(admin_server.base_url,
                                mint_admin(secret=WRONG_SECRET))
    assert status == 401


def test_expired_admin_token_rejected(admin_server):
    status, body = post_reindex(admin_server.base_url,
                                mint_admin(exp_in=-120))
    assert status == 401
    assert "expired" in body["error"]


def test_get_method_not_allowed(admin_server):
    request = urllib.request.Request(
        f"{admin_server.base_url}/admin/reindex", method="GET",
        headers={"Authorization": f"Bearer {mint_admin()}"})
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=10)
    assert excinfo.value.code == 405


# -- the trigger --------------------------------------------------------------

def test_reindex_roundtrip_health_transitions(admin_server):
    """202 started -> state flips to indexing synchronously -> ready again
    with the SAME fingerprint (unchanged corpus => the stored index is
    reused, never re-embedded); a second trigger behaves identically."""
    before = wait_ready(admin_server.base_url)
    for round_no in (1, 2):
        status, body = post_reindex(admin_server.base_url, mint_admin())
        assert status == 202, body
        assert body["reindex"] == "started"
        assert body["state"] == "indexing"  # flipped before the response
        after = wait_ready(admin_server.base_url)
        assert after["fingerprint"] == before["fingerprint"], round_no
        assert after["index_reused"] is True, round_no
        assert after["cases"] == before["cases"], round_no


def test_pipeline_stdlib_mint_verifies(admin_server):
    """The pipeline mints its admin JWT with stdlib HMAC (no PyJWT on the
    corpus side) — cross-verify it against the real service."""
    corpus_dir = REPO_ROOT / "corpus"
    sys.path.insert(0, str(corpus_dir))
    try:
        from ingest_corpus import mint_admin_token
    finally:
        sys.path.remove(str(corpus_dir))
    status, body = post_reindex(admin_server.base_url,
                                mint_admin_token(SECRET))
    assert status == 202, body
    assert body["reindex"] == "started"
    wait_ready(admin_server.base_url)


def test_concurrent_trigger_is_idempotent(tmp_path, monkeypatch):
    """While one reindex runs, a second trigger returns already-indexing and
    spawns NO second thread — asserted in-process with a slow initialize.
    Uses a scratch index path: the real request_reindex evicts the chroma
    system cached for ITS path (restart-equivalence, ADR-0016), and this
    in-process test must never evict the session-shared store's."""
    import threading

    from gsj_mcp_service.config import load_config
    from gsj_mcp_service.state import AppState

    config_path = write_config(
        tmp_path, repos=["case_0001"], clone_cache_dir=tmp_path / "clones",
        index_path=tmp_path / "index")
    state = AppState(load_config(config_path))
    state.status = "ready"  # pretend the first init completed
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_initialize():
        calls.append(threading.current_thread().name)
        started.set()
        release.wait(timeout=30)
        state.status = "ready"

    monkeypatch.setattr(state, "initialize", slow_initialize)
    assert state.request_reindex() == "started"
    assert started.wait(timeout=10)
    assert state.status == "indexing"
    assert state.request_reindex() == "already-indexing"
    assert state.request_reindex() == "already-indexing"
    release.set()
    deadline = time.monotonic() + 10
    while state.status != "ready" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state.status == "ready"
    assert len(calls) == 1  # exactly one init thread ran
    # after completion a new trigger starts again
    assert state.request_reindex() == "started"
    assert started.wait(timeout=10)
    release.set()
