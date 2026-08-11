"""Shared plumbing for the gsj-mcp-service suite — constants, token minting,
raw-HTTP JSON-RPC probes, the real MCP streamable-http client wrapper, and the
server-subprocess spawner. Pure functions and dataclasses only; fixtures live
in conftest.py."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt
import yaml

TESTS_DIR = Path(__file__).resolve().parent
SERVICE_DIR = TESTS_DIR.parent
REPO_ROOT = SERVICE_DIR.parent
PYTHON = SERVICE_DIR / ".venv" / "bin" / "python"

# The suite's git source is the corpus source tree (CP-34, ADR-0048): the
# fixture builder and its generated bares/manifests died with the M8b purge,
# so the bares are built HERE, on demand, through the pipeline's own hermetic
# file:// rail — same deterministic recipe, same commit SHAs (the CP-33
# parity proof). Built once per corpus.lock.json fingerprint and cached in a
# gitignored dir; the facts ground truth is read straight off the pages.
CORPUS_ROOT = REPO_ROOT / "corpus" / "staging"
BARES_DIR = TESTS_DIR / ".corpus-bares"
FACT_RE = re.compile(r"^FACT-(?P<case>[a-z0-9_]+)-(?P<page>\d{4})-(?P<k>\d+): .*$")

REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
# >= 32 bytes so PyJWT's HS256 key-length warning never fires.
SECRET = "gsj-mcp-test-secret-0123456789abcdef0123456789abcdef"
WRONG_SECRET = "gsj-mcp-wrong-secret-fedcba9876543210fedcba9876543210"

ALL_REPOS = ["case_0001", "case_0002", "case_0003", "case_0004"]
CASE_PAGES = {"case_0001": 18, "case_0002": 22, "case_0003": 15, "case_0004": 20}
CASE_TIMESTEPS = {"case_0001": [5, 12, 18], "case_0002": [6, 14, 22],
                  "case_0003": [4, 9, 15], "case_0004": [7, 13, 20]}

SERVICE_MODULES = ["gsj_mcp_service", "gsj_mcp_service.config",
                   "gsj_mcp_service.decisions", "gsj_mcp_service.embedding",
                   "gsj_mcp_service.index", "gsj_mcp_service.ingest",
                   "gsj_mcp_service.state", "gsj_mcp_service.tokens",
                   "gsj_mcp_service.tools", "gsj_mcp_service.app",
                   "gsj_mcp_service.__main__"]

sys.path.insert(0, str(SERVICE_DIR))

# Hermetic + fast: the pinned snapshot is on disk, so skip HF network
# round-trips (only when the snapshot really is cached — never break a
# cold-cache machine).
_snapshot = (Path.home() / ".cache" / "huggingface" / "hub" /
             "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots" /
             REVISION)
if _snapshot.exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

SERIAL_RE = re.compile(r"SN-\d+")


# -- the corpus-built bare estate + fact ground truth -------------------------

def _load_corpus():
    """The parsed, contract-validated corpus source tree (pipeline API)."""
    if str(REPO_ROOT / "corpus") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "corpus"))
    import ingest_corpus as pipeline

    corpus = pipeline.phase_validate(CORPUS_ROOT, quiet=True)
    if corpus is None:
        raise RuntimeError(f"{CORPUS_ROOT} fails its own contract — cannot build bares")
    return pipeline, corpus


def _ensure_bares() -> str:
    """Build ``<owner>/<case>.git`` bares from the corpus tree once per
    fingerprint; return the ownerless-clone base URL. Deterministic: the
    pipeline's own builder, so the SHAs equal corpus.lock.json's refs."""
    fingerprint = (CORPUS_ROOT / "corpus.lock.json").read_bytes()
    stamp = BARES_DIR / ".fingerprint"
    pipeline, corpus = _load_corpus()
    root = BARES_DIR / corpus.owner
    if stamp.is_file() and stamp.read_bytes() == fingerprint and root.is_dir():
        return f"file://{root}"

    import shutil
    import tempfile
    shutil.rmtree(BARES_DIR, ignore_errors=True)
    BARES_DIR.mkdir(parents=True)
    env = pipeline.git_env(corpus.git_identity)
    base_url = f"file://{BARES_DIR}"
    with tempfile.TemporaryDirectory(prefix="gsj-mcp-tests-bares-") as tmp:
        for case_id in sorted(corpus.cases):
            pipeline.build_case_repo(corpus, corpus.cases[case_id], Path(tmp), env)
            pipeline.ensure_remote_repo(corpus, base_url, case_id, None)
            pipeline.push_repo(corpus, base_url, case_id, Path(tmp) / case_id, None, env)
    stamp.write_bytes(fingerprint)
    return f"file://{root}"


def load_facts() -> list[dict]:
    """The dataset's fact ground truth — ``[{case_id, page, k, line}]`` with
    unique SN-serials — read off the corpus pages themselves (the full page
    set = each case's largest timestep tree)."""
    _, corpus = _load_corpus()
    facts: list[dict] = []
    for case_id in sorted(corpus.cases):
        case = corpus.cases[case_id]
        largest = case.timesteps[case.max_t]
        for page, path in sorted(largest.pages.items()):
            for line in path.read_text(encoding="utf-8").splitlines():
                match = FACT_RE.match(line)
                if match and match.group("case") == case_id:
                    facts.append({"case_id": case_id, "page": page,
                                  "k": int(match.group("k")), "line": line})
    return facts


BARES_URL = _ensure_bares()


# -- config ------------------------------------------------------------------

def write_config(dst_dir: Path, *, repos: list[str], clone_cache_dir,
                 index_path, port: int = 8790, rebuild: str = "if-stale",
                 base_url: str = BARES_URL, max_tokens: int = 220,
                 overlap: int = 40, name: str = "config.yaml") -> Path:
    """A complete, valid config.yaml mirroring the service's own, pointed at
    the local deterministic bares (owner: null => ownerless file:// URLs)."""
    doc = {
        "source": {"base_url": base_url, "owner": None, "repos": list(repos),
                   "ref_main": "main", "ref_pattern": "timestep-{T}",
                   "auth_token_env": None,
                   "clone_cache_dir": str(clone_cache_dir)},
        "embedding": {"model": "sentence-transformers/all-MiniLM-L6-v2",
                      "revision": REVISION, "device": "cpu",
                      "batch_size": 32, "normalize": True},
        "chunking": {"max_tokens": max_tokens, "overlap": overlap,
                     "respect_page_boundaries": True},
        "index": {"path": str(index_path), "rebuild": rebuild},
        "search": {"default_k": 5, "max_k": 20, "method": "chroma"},
        "decisions": {"seed": 20260204, "corpus_size": 30},
        "auth": {"token_secret_env": "GSJ_MCP_TOKEN_SECRET", "leeway_s": 30},
        "server": {"host": "127.0.0.1", "port": port, "log_level": "warning"},
    }
    dst_dir.mkdir(parents=True, exist_ok=True)
    path = dst_dir / name
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def make_state(config_path: Path, encoder=None):
    """Build an AppState in-process (blocking initialize). ``encoder`` lets
    tests share one loaded MiniLM across states — pure test economy; the
    Encoder is config-identical in every use."""
    from gsj_mcp_service.config import load_config
    from gsj_mcp_service.state import AppState
    state = AppState(load_config(config_path))
    if encoder is not None:
        state.encoder = encoder
    state.initialize()
    return state


# -- tokens ------------------------------------------------------------------

def mint_token(case_id: str, timestep: int, *, episode_id: str = "ep-test",
               secret: str = SECRET, exp: int | None = None,
               exp_in: int = 3600) -> str:
    payload = {"case_id": case_id, "timestep": timestep,
               "episode_id": episode_id,
               "exp": exp if exp is not None else int(time.time()) + exp_in}
    return jwt.encode(payload, secret, algorithm="HS256")


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def tamper_timestep(token: str, new_timestep: int) -> str:
    """Re-encode the payload with an altered timestep, keeping the original
    signature — the classic privilege-escalation attempt."""
    header, payload, signature = token.split(".")
    claims = json.loads(_b64url_decode(payload))
    claims["timestep"] = new_timestep
    return ".".join([header, _b64url_encode(
        json.dumps(claims, separators=(",", ":")).encode()), signature])


def flip_payload_char(token: str) -> str:
    """Corrupt one character of the payload segment in place."""
    header, payload, signature = token.split(".")
    pos = len(payload) // 2
    flipped = "A" if payload[pos] != "A" else "B"
    return ".".join([header, payload[:pos] + flipped + payload[pos + 1:],
                     signature])


# -- raw HTTP (reject-path assertions) ---------------------------------------

def post_mcp(url: str, *, rpc_id=7, tool: str = "search_case",
             arguments: dict | None = None, timeout: float = 10):
    """Plain urllib POST of a tools/call JSON-RPC envelope -> (status, body).
    body is parsed JSON when possible, else the raw text."""
    envelope = json.dumps({
        "jsonrpc": "2.0", "id": rpc_id, "method": "tools/call",
        "params": {"name": tool,
                   "arguments": arguments if arguments is not None
                   else {"query": "probe", "k": 1}}}).encode()
    request = urllib.request.Request(url, data=envelope, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read().decode()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def get_health(base_url: str, timeout: float = 5) -> dict | None:
    """GET /health -> parsed body, or None while the socket is not up yet."""
    try:
        with urllib.request.urlopen(f"{base_url}/health",
                                    timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, ConnectionError, OSError):
        return None


def assert_reject(status: int, body, *needles: str, expect_status: int = 401,
                  rpc_id=7) -> None:
    """A reject is a JSON-RPC error envelope that echoes the request id,
    mentions each needle, and NEVER carries tool data."""
    assert status == expect_status, (status, body)
    assert isinstance(body, dict), body
    assert body.get("jsonrpc") == "2.0", body
    assert body.get("id") == rpc_id, body
    assert "result" not in body, body
    message = body["error"]["message"]
    for needle in needles:
        assert needle.lower() in message.lower(), (needle, message)
    dump = json.dumps(body)
    assert "SN-" not in dump, body          # no fact serials
    assert '"page"' not in dump, body       # no search-result members
    assert '"score"' not in dump, body


# -- MCP client (the real streamable-http SDK transport) ---------------------

@dataclasses.dataclass
class ToolReply:
    is_error: bool
    structured: object          # CallToolResult.structured_content, verbatim
    texts: list                 # every TextContent block's text, in order


def mcp_roundtrip(base_url: str, token: str, calls, *, list_tools: bool = False):
    """One MCP session over real streamable-http: initialize, optionally list
    tools, then run ``calls`` = [(tool_name, arguments), ...] sequentially.
    Returns (tool_names | None, [ToolReply, ...])."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _run():
        url = f"{base_url}/mcp/{token}"
        async with streamable_http_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                names = None
                if list_tools:
                    listing = await session.list_tools()
                    names = [tool.name for tool in listing.tools]
                replies = []
                for tool_name, arguments in calls:
                    result = await session.call_tool(
                        tool_name, arguments, read_timeout_seconds=120)
                    replies.append(ToolReply(
                        is_error=bool(result.is_error),
                        structured=result.structured_content,
                        texts=[block.text for block in result.content
                               if getattr(block, "type", None) == "text"]))
                return names, replies

    return asyncio.run(_run())


def unwrap(reply: ToolReply):
    """Structured content when present (the SDK wraps generic returns in
    {"result": ...}); otherwise the JSON text block (bare-dict returns)."""
    assert not reply.is_error, reply.texts
    if isinstance(reply.structured, dict) and set(reply.structured) == {"result"}:
        return reply.structured["result"]
    if reply.structured is not None:
        return reply.structured
    return json.loads(reply.texts[0])


def call_tools(base_url: str, token: str, calls) -> list:
    _, replies = mcp_roundtrip(base_url, token, calls)
    return [unwrap(reply) for reply in replies]


def call_tool(base_url: str, token: str, name: str, arguments: dict | None = None):
    return call_tools(base_url, token, [(name, arguments or {})])[0]


def check_case_results(results: list, *, timestep: int) -> None:
    """The search_case result contract: {page, file, score, text} per hit,
    every page within the cutoff, file matching the page, positive float
    scores, sorted by (-score, page)."""
    assert results == sorted(
        results, key=lambda hit: (-hit["score"], hit["page"])), results
    for hit in results:
        assert set(hit) == {"page", "file", "score", "text"}, hit.keys()
        assert isinstance(hit["page"], int), hit
        assert 1 <= hit["page"] <= timestep, (hit["page"], timestep)
        assert hit["file"] == f"md/page_{hit['page']:04d}.md", hit
        assert isinstance(hit["score"], float) and hit["score"] > 0, hit["score"]
        assert isinstance(hit["text"], str) and hit["text"], hit


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True)


# -- server subprocess -------------------------------------------------------

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclasses.dataclass
class ServerProc:
    proc: subprocess.Popen
    port: int
    base_url: str
    log_path: Path
    final_health: dict | None = None
    pre_ready: list = dataclasses.field(default_factory=list)
    not_ready_reject: tuple | None = None   # (status, body) captured pre-ready


def _log_tail(log_path: Path, n: int = 40) -> str:
    try:
        return "\n".join(log_path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return "<no log>"


def spawn_server(run_dir: Path, config_path: Path, port: int, *,
                 wait: str = "ready", timeout: float = 180,
                 secret: str = SECRET) -> tuple[ServerProc, object]:
    """Start ``python -m gsj_mcp_service --config ...`` and poll /health at
    10-20ms until ``wait`` ("ready" or "error"). While state == "indexing",
    record health snapshots and capture one 503 tool-call reject — the raw
    material for the /health-states and before-ready tests. Returns
    (ServerProc, log_file_handle)."""
    env = dict(os.environ)
    env["GSJ_MCP_TOKEN_SECRET"] = secret
    log_path = run_dir / "server.log"
    log_file = open(log_path, "wb")
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "gsj_mcp_service", "--config", str(config_path)],
        cwd=str(SERVICE_DIR), env=env, stdout=log_file, stderr=log_file)
    server = ServerProc(proc=proc, port=port,
                        base_url=f"http://127.0.0.1:{port}", log_path=log_path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_file.close()
            raise AssertionError(
                f"server exited rc={proc.returncode}\n{_log_tail(log_path)}")
        health = get_health(server.base_url, timeout=2)
        if health is None:
            time.sleep(0.01)
            continue
        if health["state"] == "indexing":
            if len(server.pre_ready) < 50:
                server.pre_ready.append(health)
            if server.not_ready_reject is None:
                status, body = post_mcp(
                    f"{server.base_url}/mcp/{mint_token('case_0001', 5)}",
                    timeout=5)
                if status == 503 and isinstance(body, dict):
                    server.not_ready_reject = (status, body)
        if health["state"] == wait:
            server.final_health = health
            return server, log_file
        if health["state"] == "error" and wait == "ready":
            log_file.close()
            raise AssertionError(f"server errored during startup: "
                                 f"{health.get('error')}\n{_log_tail(log_path)}")
        time.sleep(0.02)
    log_file.close()
    raise AssertionError(
        f"server never reached {wait!r} in {timeout}s\n{_log_tail(log_path)}")


def stop_server(server: ServerProc, log_file) -> None:
    if server.proc.poll() is None:
        server.proc.terminate()
        try:
            server.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.proc.kill()
            server.proc.wait(timeout=5)
    log_file.close()


# -- G5 transcript-backstop parser (inlined from the predecessor) ------------
# Carried byte-faithfully from the predecessor @ v0.8.0
# (gsj/envloader/gates.py: _PAGE_MEMBER, _PAGE_FILE,
# extract_case_search_pages). Before CP-01 this was the suite's ONE
# sanctioned predecessor-library import; the predecessor is frozen and its
# library is not a dependency of this repo (ADR-0002), so the two regexes —
# which ARE the compatibility contract (README §Compatibility requirements)
# — live here verbatim. This repo's checks.py reimplements the same
# backstop at CP-11 (docs/checks-spec.md).

_PAGE_MEMBER = re.compile(r'"page"\s*:\s*(\d+)')
_PAGE_FILE = re.compile(r"md/page_(\d{4})\.md")


def load_library_parser():
    def extract_case_search_pages(tool_result_texts):
        """Page numbers cited by ``mcp_gsj_search_case`` result texts,
        deduped and sorted — G5's transcript backstop."""
        pages: set[int] = set()
        for text in tool_result_texts:
            for match in _PAGE_MEMBER.finditer(text):
                pages.add(int(match.group(1)))
            for match in _PAGE_FILE.finditer(text):
                pages.add(int(match.group(1)))
        return sorted(pages)

    return extract_case_search_pages
