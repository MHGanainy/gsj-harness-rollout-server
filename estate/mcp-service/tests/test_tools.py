"""The four tools over real streamable-http (ADR-0040(d)): the timestep
cutoff comes from the VERIFIED token claims only and is applied as a
candidate filter BEFORE ranking — the SN-serial probes prove pages beyond T
are unfindable under any query while page == T stays visible; the decisions
corpus is cutoff-EXEMPT (ADR-0007(e)); result shape stays parseable by the
library's transcript backstop."""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from helpers import (
    PYTHON,
    SERIAL_RE,
    SERVICE_DIR,
    SERVICE_MODULES,
    call_tool,
    call_tools,
    canonical,
    check_case_results,
    load_library_parser,
    mcp_roundtrip,
    mint_token,
    unwrap,
)

from gsj_mcp_service.decisions import decisions_corpus


def fact_for(facts, case_id: str, page: int, k: int = 1) -> dict:
    fact = next(f for f in facts
                if f["case_id"] == case_id and f["page"] == page and f["k"] == k)
    fact = dict(fact)
    fact["serial"] = SERIAL_RE.search(fact["line"]).group(0)
    return fact


def test_valid_token_lists_and_calls_tools(server):
    """A valid token initializes an MCP session, lists exactly the four gsj
    tools, and case_status echoes the token's claims."""
    token = mint_token("case_0001", 5)
    names, replies = mcp_roundtrip(server.base_url, token,
                                   [("case_status", {})], list_tools=True)
    assert names == ["search_case", "search_decisions", "case_status",
                     "decision_stats"]
    status = unwrap(replies[0])
    assert status == {"case_id": "case_0001", "timestep": 5,
                      "pages_visible": 5, "max_visible_page": 5,
                      "source": "service"}


@pytest.mark.parametrize("case_id,low_t,fact_page", [
    ("case_0001", 5, 12),
    ("case_0003", 4, 15),
])
def test_sn_probe_low_timestep_blocks_future_fact(server, facts, case_id,
                                                  low_t, fact_page):
    """THE cutoff probe: with a low-timestep token, a fact living on a future
    page is unreachable under every query shape — the exact serial, the full
    fact line, and generic queries — at every k up to the max (20). No result
    page exceeds T, no file exceeds md/page_000T.md, and the serial string
    appears in NO returned text."""
    fact = fact_for(facts, case_id, fact_page)
    token = mint_token(case_id, low_t)
    queries = [fact["serial"],                     # the exact serial
               fact["line"],                       # the full fact line
               "deposition slip filed by the registrar",
               "sealed ledgers moved to the antechamber",
               "invoice countersigned in the records room"]
    for query in queries:
        for k in (5, 20):
            results = call_tool(server.base_url, token, "search_case",
                                {"query": query, "k": k})
            assert results, "cutoff must filter candidates, not empty results"
            check_case_results(results, timestep=low_t)
            for hit in results:
                assert hit["page"] <= low_t
                assert hit["file"] <= f"md/page_{low_t:04d}.md"
                assert fact["serial"] not in hit["text"]
            assert fact["serial"] not in json.dumps(results)


@pytest.mark.parametrize("case_id,timestep,fact_page", [
    ("case_0001", 12, 12),
    ("case_0003", 15, 15),
])
def test_sn_probe_page_equal_to_timestep_is_visible(server, facts, case_id,
                                                    timestep, fact_page):
    """page == T is visible: with the timestep raised to the fact's page, the
    exact-serial query surfaces that page (file md/page_00TT.md) with the
    serial in its text — and still nothing beyond T."""
    fact = fact_for(facts, case_id, fact_page)
    token = mint_token(case_id, timestep)
    results = call_tool(server.base_url, token, "search_case",
                        {"query": fact["serial"], "k": 20})
    check_case_results(results, timestep=timestep)
    hits = [hit for hit in results if hit["page"] == fact_page]
    assert hits, f"page {fact_page} not returned at T={timestep}"
    assert hits[0]["file"] == f"md/page_{fact_page:04d}.md"
    assert fact["serial"] in hits[0]["text"]


def test_scores_positive_and_sorted(server):
    """Every returned score is a float > 0 and results are sorted by
    (-score, page) — asserted across cases and query shapes."""
    for case_id, timestep, query in [
            ("case_0001", 18, "insurance-claim settlement review"),
            ("case_0002", 14, "warehouse hearing witnesses"),
            ("case_0004", 13, "ledger entry against the account")]:
        token = mint_token(case_id, timestep)
        results = call_tool(server.base_url, token, "search_case",
                            {"query": query, "k": 20})
        assert results, (case_id, query)
        check_case_results(results, timestep=timestep)


# -- decisions: cutoff-exempt (ADR-0007(e)) ----------------------------------

def _docket(decision: dict) -> str:
    # decision_id D-{year}-{court}-{k} <=> docket AZ-{year}-{court}-{k}
    return "AZ-" + decision["decision_id"][2:]


def test_search_decisions_ignores_case_cutoff(server):
    """A low-timestep token still searches the FULL decisions corpus: exact
    docket queries hit their decision regardless of the case timestep."""
    token = mint_token("case_0001", 5)     # lowest recorded timestep
    corpus = decisions_corpus(20260204)
    for decision in (corpus[0], corpus[17]):
        docket = _docket(decision)
        results = call_tool(server.base_url, token, "search_decisions",
                            {"query": docket, "k": 5})
        assert results
        for hit in results:
            assert set(hit) == {"decision_id", "court", "year", "score", "text"}
            assert isinstance(hit["score"], float) and hit["score"] > 0
        exact = [hit for hit in results
                 if hit["decision_id"] == decision["decision_id"]]
        assert exact, f"docket {docket} not found"
        assert docket in exact[0]["text"]
        assert exact[0]["text"] == decision["text"]


def test_decision_stats_total_30(server):
    """Unfiltered decision_stats reports the full pinned corpus: total 30
    with by_year/by_court dicts that sum back to 30 and match a pure-python
    recomputation over decisions_corpus(20260204)."""
    token = mint_token("case_0003", 4)
    stats = call_tool(server.base_url, token, "decision_stats", {})
    corpus = decisions_corpus(20260204)
    assert stats["total"] == 30
    assert sum(stats["by_year"].values()) == 30
    assert sum(stats["by_court"].values()) == 30
    expected_by_year: dict[str, int] = {}
    expected_by_court: dict[str, int] = {}
    for decision in corpus:
        year, court = str(decision["year"]), decision["court"]
        expected_by_year[year] = expected_by_year.get(year, 0) + 1
        expected_by_court[court] = expected_by_court.get(court, 0) + 1
    assert stats["by_year"] == expected_by_year
    assert stats["by_court"] == expected_by_court


@pytest.mark.parametrize("filters", [
    {"from_year": 2021},
    {"to_year": 2022},
    {"court": "LG-A"},
    {"from_year": 2020, "to_year": 2024, "court": "BGH-C"},
])
def test_decision_stats_filtered_matches_recomputation(server, filters):
    """Filtered decision_stats equals an independent recount over the
    deterministic corpus under the same from_year/to_year/court filters."""
    token = mint_token("case_0001", 5)
    stats = call_tool(server.base_url, token, "decision_stats", filters)
    rows = [d for d in decisions_corpus(20260204)
            if ("from_year" not in filters or d["year"] >= filters["from_year"])
            and ("to_year" not in filters or d["year"] <= filters["to_year"])
            and ("court" not in filters or d["court"] == filters["court"])]
    assert stats["total"] == len(rows)
    by_year: dict[str, int] = {}
    by_court: dict[str, int] = {}
    for decision in rows:
        by_year[str(decision["year"])] = by_year.get(str(decision["year"]), 0) + 1
        by_court[decision["court"]] = by_court.get(decision["court"], 0) + 1
    assert stats["by_year"] == by_year
    assert stats["by_court"] == by_court
    if filters.get("court"):
        assert set(stats["by_court"]) <= {filters["court"]}


# -- k clamping (never an error) ---------------------------------------------

def test_k_zero_clamps_to_one(server):
    """k=0 behaves as k=1: exactly the single best hit, identical to the head
    of the k=5 ranking — no error, never empty."""
    token = mint_token("case_0001", 12)
    query = {"query": "sealed ledgers deposition"}
    one, five = call_tools(server.base_url, token, [
        ("search_case", dict(query, k=0)),
        ("search_case", dict(query, k=5))])
    assert len(one) == 1
    assert five
    assert canonical(one[0]) == canonical(five[0])


def test_k_huge_clamps_to_max_20(server):
    """k=999 clamps to max_k=20 with no error: case_0002 at T=22 has 22
    candidate pages, so the clamp is what caps the result count at 20 — and
    the list equals the explicit k=20 ranking."""
    token = mint_token("case_0002", 22)
    query = {"query": "the warehouse ledger and invoices"}
    huge, twenty = call_tools(server.base_url, token, [
        ("search_case", dict(query, k=999)),
        ("search_case", dict(query, k=20))])
    assert len(huge) == 20
    assert canonical(huge) == canonical(twenty)


# -- result-shape compatibility (the library's transcript backstop) ----------

def test_result_texts_parse_with_library_extractor(server):
    """checkpoint requirement: the JSON text blocks exactly as the MCP client
    received them feed the G5 transcript-backstop parser (inlined verbatim
    from the predecessor's gsj.envloader.gates.extract_case_search_pages —
    ADR-0002; before CP-01 the ONE sanctioned library import) and reproduce
    the structured page set — all within the token's cutoff."""
    extract_case_search_pages = load_library_parser()
    token = mint_token("case_0001", 5)
    _, replies = mcp_roundtrip(server.base_url, token, [
        ("search_case", {"query": "insurance-claim ledger entry", "k": 20})])
    reply = replies[0]
    results = unwrap(reply)
    assert results, "probe query returned nothing"
    assert reply.texts, "no text blocks came over the wire"
    parsed_pages = extract_case_search_pages(reply.texts)
    assert parsed_pages == sorted({hit["page"] for hit in results})
    assert all(page <= 5 for page in parsed_pages)


def test_service_runtime_never_imports_the_library():
    """The service is standalone: no gsj.envloader import anywhere in its
    modules — asserted twice, by source scan (import statements only; the
    docstring may mention the name) and by importing every service module in
    a fresh interpreter and checking sys.modules."""
    import_re = re.compile(r"^\s*(?:from|import)\s+gsj\b")
    for path in sorted((SERVICE_DIR / "gsj_mcp_service").glob("*.py")):
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            assert not import_re.match(line), f"{path.name}:{line_no}: {line}"

    program = (
        "import importlib, sys\n"
        f"for name in {SERVICE_MODULES!r}:\n"
        "    importlib.import_module(name)\n"
        "bad = [m for m in sys.modules if m == 'gsj' or m.startswith('gsj.')]\n"
        "assert not bad, bad\n"
        "print('CLEAN')\n")
    proc = subprocess.run([str(PYTHON), "-c", program], cwd=str(SERVICE_DIR),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "CLEAN" in proc.stdout
