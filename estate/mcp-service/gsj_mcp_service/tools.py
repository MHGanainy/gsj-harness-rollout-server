"""The four `gsj` tools — declarations byte-identical to the pinned roster.

CONTRACT (G3, tool_roster_hash): the tool NAMES, PARAMETERS (names, type
hints and defaults — the SDK generates the input schemas from them) and
DOCSTRINGS below must stay byte-identical to the retired stub's (ADR-0007;
last at commit bbd4830) — the CP-29 Step 1 check proved this reproduces the
pinned wire roster hash `a7a7956b…48e56` over streamable-http. Any edit
there changes the wire roster and G3 fails until a deliberate `gsj-pin`
re-pin. Same SDK pin (mcp==2.0.0) for the same reason. The RETURN
annotation is outside the contract (CP-78, re-verified through the roster
suite's renderer): G3 hashes name + description + pi's rendering of the
INPUT schema, mcp 2.0.0 emits an output schema for `-> list[dict]` and none
for `-> dict`, and pi-mcp-extension 1.5.0 reads neither — so
`search_decisions` moved to `-> dict` at CP-79 for the spec's wrapper, and
had to: under mcp 2.0.0 a dict returned from a `-> list[dict]` tool fails
the SDK's output validation with a tool error.

Bodies differ from the stub by design: MiniLM cosine retrieval, T from the
VERIFIED TOKEN CLAIMS only (never a request field), one index per case with
the cutoff applied as a filter before ranking (ADR-0040(d)); since CP-79
`search_decisions` returns the decisions surface's response
(docs/decisions-surface.md §7: `{query, k, hits, index_commit}` — level-2
hits over a rii drop, the synthetic 30's level-0 hits with no path).
"""

from __future__ import annotations

import time

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .state import AppState, NotReadyError, request_log
from .tokens import TokenError, require_claims


def clamp_k(k: int, max_k: int) -> int:
    return max(1, min(max_k, k))


def build_mcp(state: AppState) -> MCPServer:
    app = MCPServer("gsj")
    max_k = state.config.search.max_k

    def _scope():
        """Verified claims + readiness, as clear MCP tool errors."""
        try:
            claims = require_claims()
        except TokenError as error:
            raise ToolError(f"unauthorized: {error.detail}") from None
        try:
            state.require_ready()
        except NotReadyError as error:
            raise ToolError(str(error)) from None
        return claims

    def _case(claims):
        try:
            return state.case(claims.case_id)
        except KeyError:
            raise ToolError(
                f"unknown case {claims.case_id!r} — not in the frozen "
                f"dataset") from None

    @app.tool()
    def search_case(query: str, k: int = 5) -> list[dict]:
        """Search the case pages visible at this session's timestep; returns page, file, score and full page text."""
        start = time.perf_counter()
        claims = _scope()
        index = _case(claims)
        vector, cache_hit = state.encoder.encode_query(query)
        results = index.search(vector, k=clamp_k(k, max_k),
                               timestep=claims.timestep)
        request_log(state, episode_id=claims.episode_id,
                    case_id=claims.case_id, timestep=claims.timestep,
                    tool="search_case", k=k, n_results=len(results),
                    latency_ms=round((time.perf_counter() - start) * 1e3, 2),
                    cache_hit=cache_hit)
        return results

    @app.tool()
    def search_decisions(query: str, k: int = 5) -> dict:
        """Search the decisions corpus (never clamped by the case timestep)."""
        start = time.perf_counter()
        claims = _scope()
        effective_k = clamp_k(k, max_k)
        vector, cache_hit = state.encoder.encode_query(query)
        hits = state.decisions.search(vector, k=effective_k)
        request_log(state, episode_id=claims.episode_id,
                    case_id=claims.case_id, timestep=claims.timestep,
                    tool="search_decisions", k=k, n_results=len(hits),
                    latency_ms=round((time.perf_counter() - start) * 1e3, 2),
                    cache_hit=cache_hit)
        # spec §7.2: the query as received, the EFFECTIVE k (§8.3), at most
        # k hits in §8.2's order, the index's opaque identity ("" unknown)
        return {"query": query, "k": effective_k, "hits": hits,
                "index_commit": state.decisions.index_commit}

    @app.tool()
    def case_status() -> dict:
        """Report this session's case id, timestep and visible-page bounds."""
        start = time.perf_counter()
        claims = _scope()
        index = _case(claims)
        visible = [page for page in index.pages if page <= claims.timestep]
        if not visible:
            raise ToolError(
                f"timestep {claims.timestep} leaves no visible pages "
                f"(case has {index.n_pages})")
        result = {"case_id": claims.case_id, "timestep": claims.timestep,
                  "pages_visible": len(visible),
                  "max_visible_page": max(visible), "source": "service"}
        request_log(state, episode_id=claims.episode_id,
                    case_id=claims.case_id, timestep=claims.timestep,
                    tool="case_status", k=None, n_results=1,
                    latency_ms=round((time.perf_counter() - start) * 1e3, 2),
                    cache_hit=None)
        return result

    @app.tool()
    def decision_stats(from_year: int | None = None,
                       to_year: int | None = None,
                       court: str | None = None) -> dict:
        """Aggregate decision counts (total, by_year, by_court) over the optionally filtered corpus."""
        start = time.perf_counter()
        claims = _scope()
        rows = [d for d in state.decisions.corpus
                if (from_year is None or d["year"] >= from_year)
                and (to_year is None or d["year"] <= to_year)
                and (court is None or d["court"] == court)]
        by_year: dict[str, int] = {}
        by_court: dict[str, int] = {}
        for d in sorted(rows, key=lambda d: (d["year"], d["court"])):
            by_year[str(d["year"])] = by_year.get(str(d["year"]), 0) + 1
            by_court[d["court"]] = by_court.get(d["court"], 0) + 1
        result = {"total": len(rows), "by_year": by_year, "by_court": by_court}
        request_log(state, episode_id=claims.episode_id,
                    case_id=claims.case_id, timestep=claims.timestep,
                    tool="decision_stats", k=None, n_results=result["total"],
                    latency_ms=round((time.perf_counter() - start) * 1e3, 2),
                    cache_hit=None)
        return result

    return app
