"""Process-level behavior: /health state machine (indexing -> ready; error),
before-ready 503s, cross-process byte-determinism over the same stored index,
and concurrent multi-token sessions with zero cross-talk (the contextvar
claims propagation, ADR-0040(f)/(g)/(h))."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers import (
    ALL_REPOS,
    CASE_PAGES,
    CASE_TIMESTEPS,
    REVISION,
    SERIAL_RE,
    call_tools,
    canonical,
    check_case_results,
    free_port,
    get_health,
    mint_token,
    post_mcp,
    spawn_server,
    stop_server,
    write_config,
)


# -- /health states ----------------------------------------------------------

def test_health_indexing_observed_before_ready(server, server2):
    """Right after process start /health answers state "indexing" with a
    progress map (liveness before readiness) — captured by the spawn-time
    fast poll on the real subprocesses."""
    snapshots = server.pre_ready + server2.pre_ready
    assert snapshots, "never observed the indexing state on either server"
    for snapshot in snapshots:
        assert snapshot["state"] == "indexing"
        assert set(snapshot["progress"]) == set(ALL_REPOS)
        assert "cases" not in snapshot          # ready-only fields absent
        assert "fingerprint" not in snapshot


def test_health_ready_shape(server, built_state):
    """Ready /health carries the full corpus summary: per-case pages, chunks
    and timesteps, decisions count 30, the corpus fingerprint, and
    index_reused True (the subprocess reused the session-built index)."""
    health = get_health(server.base_url)
    assert health["state"] == "ready"
    assert health["index_reused"] is True
    assert health["fingerprint"] == built_state.fingerprint
    assert health["decisions"] == 30
    assert health["embedding"]["revision"] == REVISION
    assert set(health["cases"]) == set(ALL_REPOS)
    for case_id, summary in health["cases"].items():
        assert summary["pages"] == CASE_PAGES[case_id]
        assert summary["timesteps"] == CASE_TIMESTEPS[case_id]
        assert summary["chunks"] == len(built_state.cases[case_id].chunks)
    for progress in health["progress"].values():
        assert progress["done"] is True


def test_tool_call_before_ready_gets_clear_503(server, server2):
    """A tool call while state == "indexing" is a 503 JSON-RPC error naming
    the not-ready state — NEVER empty results (captured live during the
    subprocess startup window)."""
    captured = server.not_ready_reject or server2.not_ready_reject
    assert captured, "no before-ready reject was captured during startup"
    status, body = captured
    assert status == 503
    assert body.get("jsonrpc") == "2.0"
    assert "result" not in body
    message = body["error"]["message"]
    assert "not ready" in message
    assert "indexing" in message
    assert "state=ready" in message          # tells the caller what to wait for


def test_error_state_bad_source(tmp_path_factory):
    """A config pointing at a nonexistent source base_url: /health eventually
    reports state "error" with an ingestion message, the process stays alive
    (liveness), and tool calls — any token — get a 503 JSON-RPC error naming
    the error state."""
    run_dir = tmp_path_factory.mktemp("srv-error")
    port = free_port()
    config_path = write_config(
        run_dir, repos=["case_0001"], clone_cache_dir=run_dir / "clones",
        index_path=run_dir / "index", port=port,
        base_url=f"file://{run_dir}/nonexistent-bares")
    server, log_file = spawn_server(run_dir, config_path, port, wait="error")
    try:
        health = get_health(server.base_url)
        assert health["state"] == "error"
        assert "git" in health["error"] and "failed" in health["error"]

        for token in (mint_token("case_0001", 5), "not-even-a-token"):
            status, body = post_mcp(f"{server.base_url}/mcp/{token}")
            assert status == 503, (status, body)
            assert body.get("jsonrpc") == "2.0"
            assert "result" not in body
            assert "state: error" in body["error"]["message"]

        assert server.proc.poll() is None            # still alive
        assert get_health(server.base_url)["state"] == "error"
    finally:
        stop_server(server, log_file)


# -- determinism across fresh processes (checkpoint requirement (f)) ---------

def test_identical_results_across_fresh_processes(server, server2):
    """Two separate server processes over the SAME pre-built index dir return
    byte-identical JSON — float scores included — for identical search_case
    and search_decisions queries (torch single-thread exact-cosine posture)."""
    token = mint_token("case_0001", 12)
    calls = [("search_case",
              {"query": "the sealed ledgers were moved to the antechamber",
               "k": 10}),
             ("search_decisions",
              {"query": "warehouse lease counterclaim dismissed", "k": 10})]
    first = call_tools(server.base_url, token, calls)
    second = call_tools(server2.base_url, token, calls)
    assert first[0] and first[1], "probe queries must return results"
    assert canonical(first[0]) == canonical(second[0])
    assert canonical(first[1]) == canonical(second[1])


# -- concurrency: zero cross-talk --------------------------------------------

TOKEN_SPECS = [("case_0001", 5), ("case_0002", 14), ("case_0003", 9),
               ("case_0004", 13), ("case_0001", 12)]


@pytest.fixture(scope="module")
def concurrency_plan(server, facts):
    """Per token: the calls each worker will make (case_status + two
    search_case, one being the exact serial of a fact BEYOND its cutoff) and
    the single-threaded baseline results."""
    plan = []
    for case_id, timestep in TOKEN_SPECS:
        token = mint_token(case_id, timestep,
                           episode_id=f"ep-{case_id}-t{timestep}")
        hidden = next(f for f in facts
                      if f["case_id"] == case_id and f["page"] > timestep)
        serial = SERIAL_RE.search(hidden["line"]).group(0)
        calls = [("case_status", {}),
                 ("search_case", {"query": "ledger entries and invoices "
                                           "countersigned", "k": 10}),
                 ("search_case", {"query": serial, "k": 20})]
        baseline = call_tools(server.base_url, token, calls)
        plan.append({"case_id": case_id, "timestep": timestep, "token": token,
                     "serial": serial, "calls": calls, "baseline": baseline})
    return plan


def test_concurrent_sessions_zero_crosstalk(server, concurrency_plan):
    """12 threads over one server, mixing different cases AND two timesteps
    of case_0001, each with its own token and MCP session: every case_status
    echoes exactly its token's claims, every search respects its OWN cutoff
    (beyond-cutoff serials stay invisible), and every thread's results are
    byte-identical to the single-threaded baseline."""
    jobs = [concurrency_plan[i % len(concurrency_plan)] for i in range(12)]

    def work(spec):
        return spec, call_tools(server.base_url, spec["token"], spec["calls"])

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        outcomes = list(pool.map(work, jobs))

    assert len(outcomes) == 12
    for spec, got in outcomes:
        status, generic, probe = got
        assert status["case_id"] == spec["case_id"]
        assert status["timestep"] == spec["timestep"]
        assert status["max_visible_page"] == spec["timestep"]
        for results in (generic, probe):
            check_case_results(results, timestep=spec["timestep"])
            assert spec["serial"] not in json.dumps(results)
        assert canonical(got) == canonical(spec["baseline"])
