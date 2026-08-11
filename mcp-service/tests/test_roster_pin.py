"""G3's roster pin, asserted in the service's own suite (CP-15, ADR-0016
invariant 1 — this test should have existed before; it exists now).

The tool NAMES, SIGNATURES and DOCSTRINGS in ``tools.py`` generate the wire
roster G3 hashes (`tool_roster_hash`, pinned ``a7a7956b…48e56``). Two
assertions close the loop without re-collecting an episode:

1. the captured wire array (``pins/tools.captured.json`` — the ``tools``
   array as pi 0.83.0 actually sent it, the G3 anchor) still
   canonical-JSON-hashes into the approved set in ``pins/pins.gsj.json``
   (checks-spec convention 2: sorted keys, compact separators, UTF-8);
2. the LIVE ``tools/list`` declarations, rendered to pi's measured wire
   form (``mcp_gsj_`` prefix, docstring as description, titles/defaults
   dropped, ``integer`` → ``number``, ``strict: false``), reproduce the
   captured four ``mcp_gsj_*`` entries byte-for-byte — so any drift in
   ``tools.py`` or the ``mcp`` SDK pin fails HERE, before an episode pays
   for it with a G3 rejection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from helpers import REPO_ROOT, call_tool, mint_token

PINS_PATH = REPO_ROOT / "pins" / "pins.gsj.json"
CAPTURED_PATH = REPO_ROOT / "pins" / "tools.captured.json"

GSJ_TOOLS = ["search_case", "search_decisions", "case_status",
             "decision_stats"]


def canonical_json(obj) -> str:
    """The predecessor's store.py convention (checks-spec convention 2)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256_canonical_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def approved_roster_hashes() -> list[str]:
    doc = json.loads(PINS_PATH.read_text())
    return doc["pins"]["tool_roster_hash"]


# -- pi 0.83.0's rendering of an MCP declaration into a wire tools entry ----
# Calibrated against pins/tools.captured.json (the measured wire form):
# titles and defaults dropped, JSON-schema "integer" rendered "number",
# anyOf branches kept in order, "required" present only when non-empty.

def _pi_type(schema_type: str) -> str:
    return "number" if schema_type == "integer" else schema_type


def _pi_property(prop: dict) -> dict:
    rendered: dict = {}
    if "anyOf" in prop:
        rendered["anyOf"] = [{"type": _pi_type(o["type"])}
                             for o in prop["anyOf"]]
    else:
        rendered["type"] = _pi_type(prop["type"])
    # pi's schema bridge (pi-mcp-extension 1.5.0, tool-bridge.ts) PRESERVES
    # per-property descriptions — the captured builtin entries carry them —
    # while dropping titles/defaults/bounds. Mirror it, or a
    # Field(description=...) added in tools.py would change the real wire
    # roster while this test slept (CP-15 review finding).
    if "description" in prop:
        rendered["description"] = prop["description"]
    return rendered


def pi_wire_entry(name: str, description: str, input_schema: dict) -> dict:
    parameters: dict = {"type": "object"}
    if input_schema.get("required"):
        parameters["required"] = list(input_schema["required"])
    parameters["properties"] = {
        key: _pi_property(value)
        for key, value in input_schema.get("properties", {}).items()}
    return {"type": "function",
            "function": {"name": f"mcp_gsj_{name}", "description": description,
                         "parameters": parameters, "strict": False}}


def list_tools_full(base_url: str, token: str):
    """tools/list over real streamable-http -> [(name, description,
    input_schema), ...] in server registration order."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _run():
        async with streamable_http_client(f"{base_url}/mcp/{token}") as (
                read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listing = await session.list_tools()
                return [(tool.name, tool.description, tool.input_schema)
                        for tool in listing.tools]

    return asyncio.run(_run())


def test_captured_wire_roster_hashes_into_the_pin():
    """The G3 anchor: canonical-JSON sha256 of the captured 11-tool wire
    array reproduces the pinned tool_roster_hash exactly."""
    captured = json.loads(CAPTURED_PATH.read_text())
    assert [t["function"]["name"] for t in captured
            if t["function"]["name"].startswith("mcp_gsj_")] == [
        f"mcp_gsj_{name}" for name in GSJ_TOOLS]
    digest = sha256_canonical_json(captured)
    approved = approved_roster_hashes()
    assert digest in approved, (digest, approved)


def test_live_declarations_reproduce_the_captured_wire_entries(server):
    """The four tools as served TODAY, rendered to pi's wire form, are
    byte-identical to the captured entries the pin hashes — any edit to
    tools.py names/signatures/docstrings, or an mcp SDK schema-generation
    change, fails here."""
    tools = list_tools_full(server.base_url, mint_token("case_0001", 5))
    assert [name for name, _, _ in tools] == GSJ_TOOLS

    captured = json.loads(CAPTURED_PATH.read_text())
    captured_gsj = [t for t in captured
                    if t["function"]["name"].startswith("mcp_gsj_")]
    rendered = [pi_wire_entry(name, description, schema)
                for name, description, schema in tools]
    for want, got in zip(captured_gsj, rendered):
        assert canonical_json(got) == canonical_json(want), (
            want["function"]["name"])


# The SDK's UNRENDERED input schemas, generated from the exact type hints
# and defaults in tools.py. The wire form is LOSSY (pi drops defaults and
# collapses integer to number), so a changed default (k = 5 -> 50) or an
# int -> float hint would slip both wire tests above while changing runtime
# behavior — this pin catches the drift classes the wire cannot see
# (CP-15 review finding).
EXPECTED_INPUT_SCHEMAS = {
    "search_case": {
        "properties": {
            "query": {"title": "Query", "type": "string"},
            "k": {"default": 5, "title": "K", "type": "integer"}},
        "required": ["query"], "title": "search_caseArguments",
        "type": "object"},
    "search_decisions": {
        "properties": {
            "query": {"title": "Query", "type": "string"},
            "k": {"default": 5, "title": "K", "type": "integer"}},
        "required": ["query"], "title": "search_decisionsArguments",
        "type": "object"},
    "case_status": {
        "properties": {}, "title": "case_statusArguments", "type": "object"},
    "decision_stats": {
        "properties": {
            "from_year": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                          "default": None, "title": "From Year"},
            "to_year": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                        "default": None, "title": "To Year"},
            "court": {"anyOf": [{"type": "string"}, {"type": "null"}],
                      "default": None, "title": "Court"}},
        "title": "decision_statsArguments", "type": "object"},
}


def test_source_level_signatures_pinned(server):
    tools = list_tools_full(server.base_url, mint_token("case_0001", 5))
    assert {name: schema for name, _, schema in tools} \
        == EXPECTED_INPUT_SCHEMAS


def test_default_k_serves_five(server):
    """The G3-pinned `k: int = 5` default, behaviorally: omitting k returns
    exactly five results where five-plus pages are within the cutoff."""
    results = call_tool(server.base_url, mint_token("case_0002", 22),
                        "search_case",
                        {"query": "the warehouse ledger and invoices"})
    assert len(results) == 5
