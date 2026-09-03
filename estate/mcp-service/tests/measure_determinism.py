#!/usr/bin/env python3
"""CP-15 Step 4 — determinism, measured (not a pytest module; run directly).

Two fresh processes, same query, same k, same case, same timestep — compare
ids, order, and scores, at both the tool level (search_case /
search_decisions results, full page text included) and the sharper chunk
level (raw collection ids + distances at full float repr, where a
tool-level page aggregation could mask a chunk reordering). Also measured:
a full REBUILD into a second store from the same inputs (HNSW construction
determinism), compared the same two ways.

    .venv/bin/python tests/measure_determinism.py

The verdict feeds assumption row A-25 (ADR-0016): identical => HNSW
happens to be reproducible at this scale (213 chunks, full-candidate-set
fetch), with no guarantee it survives a larger corpus; not identical =>
what varies and at what rate is printed per comparison.

At scale (CP-77 — the batched add path, wishlist 66a): point it at any
bare-repo tree and size the decisions corpus past chroma's 5,461-item
single-add ceiling; the probes for a non-staging case are given on the
command line (the staging probes above assume the staging pages):

    .venv/bin/python tests/measure_determinism.py \
        --base-url file:///path/to/bares --repos case_big \
        --decisions 12000 \
        --probe 'case_big:650:10:the sealed ledgers were moved' \
        --probe 'case_big:1300:20:salvage award appeal'

Over a real decisions drop (CP-79 — the level-2 surface, best piece per
unit over a fetch bounded by k): ``--decisions-path <dir>`` replaces the
synthetic corpus, ``--decision-probe 'K:QUERY'`` replaces the English
probes, and a raw decisions probe (the bounded fetch's ids + distances at
full float repr, the first decision probe) joins the raw chunk probe:

    .venv/bin/python tests/measure_determinism.py --repos case_0003 \
        --probe 'case_0003:9:10:deposition slip' \
        --decisions-path /path/to/drop \
        --decision-probe '5:Sittenwidrigkeit im Sinne von § 826 BGB' \
        --decision-probe '20:Widerruf eines Verbraucherdarlehensvertrags'
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ALL_REPOS, PYTHON, SERVICE_DIR, write_config  # noqa: E402

CASE_QUERIES = [
    ("case_0001", 12, "the sealed ledgers were moved to the antechamber", 10),
    ("case_0001", 5, "insurance-claim ledger entry", 20),
    ("case_0002", 14, "warehouse hearing witnesses", 10),
    ("case_0002", 22, "the warehouse ledger and invoices", 20),
    ("case_0003", 9, "deposition slip concerning the sealed ledgers", 10),
    ("case_0004", 13, "ledger entry against the account", 10),
]
DECISION_QUERIES = [
    ("warehouse lease counterclaim dismissed", 10),
    ("AZ-2021-OLG-B-1 salvage award appeal", 5),
]
RAW_PROBE = ("case_0002", 22, "the warehouse ledger and invoices")


def worker(config_path: str, probes_path: str | None = None) -> None:
    """Runs in a FRESH process: init the state (build or fingerprint-match
    reuse — whichever the store dictates), run the fixed probes, dump JSON."""
    from helpers import make_state

    case_queries, raw_probe = CASE_QUERIES, RAW_PROBE
    decision_queries = DECISION_QUERIES
    if probes_path:
        given = json.loads(Path(probes_path).read_text())
        case_queries = [tuple(p) for p in given["case_queries"]]
        raw_probe = tuple(given["raw_probe"])
        decision_queries = [tuple(p) for p in
                            given.get("decision_queries", DECISION_QUERIES)]
    state = make_state(Path(config_path))
    assert state.status == "ready", state.error
    out: dict = {"reused": state.reused_index, "results": {}, "raw": {},
                 "counts": {cid: idx.collection.count()
                            for cid, idx in state.cases.items()},
                 "decisions": state.decisions.collection.count()}
    for case_id, timestep, query, k in case_queries:
        vec, _ = state.encoder.encode_query(query)
        results = state.cases[case_id].search(vec, k=k, timestep=timestep)
        out["results"][f"{case_id}/T{timestep}/k{k}/{query}"] = results
    for query, k in decision_queries:
        vec, _ = state.encoder.encode_query(query)
        out["results"][f"decisions/k{k}/{query}"] = state.decisions.search(
            vec, k=k)
    if getattr(state.decisions, "kind", "synthetic") == "rii":
        # the bounded fetch itself (CP-79): which pieces, at what distance
        from gsj_mcp_service.index import DECISIONS_FETCH_PER_K
        query, k = decision_queries[0]
        vec, _ = state.encoder.encode_query(query)
        n = min(state.decisions.n_pieces, DECISIONS_FETCH_PER_K * k)
        raw = state.decisions.collection.query(
            query_embeddings=[vec], n_results=n, include=["distances"])
        out["raw_decisions"] = {"ids": raw["ids"][0],
                                "distances": [repr(d) for d in raw["distances"][0]]}
    case_id, timestep, query = raw_probe
    index = state.cases[case_id]
    vec, _ = state.encoder.encode_query(query)
    candidates = sum(1 for c in index.chunks if c.page <= timestep)
    raw = index.collection.query(
        query_embeddings=[vec], n_results=candidates,
        where={"page": {"$lte": timestep}}, include=["distances"])
    out["raw"] = {"ids": raw["ids"][0],
                  "distances": [repr(d) for d in raw["distances"][0]]}
    print(json.dumps(out, sort_keys=True))


def run_worker(config_path: Path, probes_path: Path | None = None) -> dict:
    argv = [str(PYTHON), str(Path(__file__).resolve()), "worker",
            str(config_path)]
    if probes_path is not None:
        argv.append(str(probes_path))
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=7200,
                          cwd=str(SERVICE_DIR))
    if proc.returncode != 0:
        raise RuntimeError(f"worker failed:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.splitlines()[-1])


def compare(label: str, a: dict, b: dict) -> bool:
    identical = True
    for key in sorted(a["results"]):
        left, right = a["results"][key], b["results"][key]
        if json.dumps(left, sort_keys=True) == json.dumps(right,
                                                          sort_keys=True):
            continue
        identical = False
        pages = lambda rs: [(r.get("page", r.get("decision_id")), r["score"])
                            for r in rs]
        print(f"  DIFF {label} :: {key}")
        print(f"    a: {pages(left)}")
        print(f"    b: {pages(right)}")
    raw_same = (a["raw"]["ids"] == b["raw"]["ids"]
                and a["raw"]["distances"] == b["raw"]["distances"])
    if not raw_same:
        identical = False
        same_membership = set(a["raw"]["ids"]) == set(b["raw"]["ids"])
        print(f"  DIFF {label} :: raw chunk probe — ids equal-as-sets: "
              f"{same_membership}, order equal: "
              f"{a['raw']['ids'] == b['raw']['ids']}")
    extra = 0
    if "raw_decisions" in a and "raw_decisions" in b:
        extra = 1
        ra, rb = a["raw_decisions"], b["raw_decisions"]
        if not (ra["ids"] == rb["ids"] and ra["distances"] == rb["distances"]):
            identical = False
            common = set(ra["ids"]) & set(rb["ids"])
            print(f"  DIFF {label} :: raw decisions probe (bounded fetch of "
                  f"{len(ra['ids'])}) — ids equal-as-sets: "
                  f"{set(ra['ids']) == set(rb['ids'])} ({len(common)} shared), "
                  f"order equal: {ra['ids'] == rb['ids']}")
    n = len(a["results"]) + 1 + extra
    print(f"{label}: {'IDENTICAL' if identical else 'NOT IDENTICAL'} "
          f"({n}/{n} probes)" if identical else f"{label}: NOT IDENTICAL")
    return identical


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=None,
                        help="bare-repo tree (default: the staging bares)")
    parser.add_argument("--repos", default=None,
                        help="comma-separated case ids (default: staging)")
    parser.add_argument("--decisions", type=int, default=30,
                        help="decisions corpus size (default 30; > 5461 "
                             "exercises the batched add)")
    parser.add_argument("--probe", action="append", default=[],
                        metavar="CASE:T:K:QUERY",
                        help="a search_case probe for a non-staging case; "
                             "the first one is also the raw chunk probe")
    parser.add_argument("--decisions-path", default=None,
                        help="a rii drop directory (CP-79) instead of the "
                             "synthetic corpus")
    parser.add_argument("--decision-probe", action="append", default=[],
                        metavar="K:QUERY",
                        help="a search_decisions probe (default: the two "
                             "English probes over the synthetic corpus); "
                             "the first is also the raw bounded-fetch probe")
    args = parser.parse_args(argv)
    for spec in args.decision_probe:
        if len(spec.split(":", 1)) != 2 or not spec.split(":", 1)[0].isdigit():
            parser.error(f"--decision-probe {spec!r}: expected K:QUERY")
    if args.repos and not args.probe:
        parser.error("--repos names non-staging cases: give at least one "
                     "--probe CASE:T:K:QUERY for them")
    for spec in args.probe:
        if len(spec.split(":", 3)) != 4:
            parser.error(f"--probe {spec!r}: expected CASE:T:K:QUERY")
    return args


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        return
    args = _parse_args(sys.argv[1:])
    repos = args.repos.split(",") if args.repos else ALL_REPOS
    extra = {"decisions_size": args.decisions}
    if args.base_url:
        extra["base_url"] = args.base_url
    if args.decisions_path:
        extra["decisions_path"] = str(Path(args.decisions_path).resolve())

    root = Path(tempfile.mkdtemp(prefix="cp15-determinism-"))
    print(f"stores under {root}")
    clones = root / "clones"
    probes_path = None
    if args.probe or args.decision_probe:
        case_queries, raw = list(CASE_QUERIES), RAW_PROBE
        if args.probe:
            case_queries, raw = [], None
            for spec in args.probe:
                case_id, timestep, k, query = spec.split(":", 3)
                case_queries.append((case_id, int(timestep), query, int(k)))
                raw = raw or (case_id, int(timestep), query)
        decision_queries = list(DECISION_QUERIES)
        if args.decision_probe:
            decision_queries = []
            for spec in args.decision_probe:
                k, query = spec.split(":", 1)
                decision_queries.append((query, int(k)))
        probes_path = root / "probes.json"
        probes_path.write_text(json.dumps(
            {"case_queries": case_queries, "raw_probe": raw,
             "decision_queries": decision_queries}))
    print(f"repos {repos}, decisions "
          f"{args.decisions_path or args.decisions}, "
          f"{len(args.probe) or len(CASE_QUERIES)} case probes, "
          f"{len(args.decision_probe) or len(DECISION_QUERIES)} decision probes")

    cfg1 = write_config(root / "s1", repos=repos, clone_cache_dir=clones,
                        index_path=root / "s1" / "index", **extra)
    cfg2 = write_config(root / "s2", repos=repos, clone_cache_dir=clones,
                        index_path=root / "s2" / "index", **extra)

    print("process A: fresh BUILD into store 1 ...")
    a = run_worker(cfg1, probes_path)
    assert a["reused"] is False
    print(f"  built: cases {a['counts']}, decisions {a['decisions']}")
    print("process B: fresh process, REUSE of store 1 ...")
    b = run_worker(cfg1, probes_path)
    assert b["reused"] is True
    print("process C: fresh process, REUSE of store 1 ...")
    c = run_worker(cfg1, probes_path)
    assert c["reused"] is True
    print("process D: fresh BUILD into store 2 (same inputs) ...")
    d = run_worker(cfg2, probes_path)
    assert d["reused"] is False

    print()
    same_store = compare("B vs C (two fresh processes, same stored index)",
                         b, c)
    build_vs_load = compare("A vs B (builder process vs fresh loader)", a, b)
    rebuild = compare("A vs D (two independent builds, same inputs)", a, d)

    print()
    from gsj_mcp_service.index import DECISIONS_FETCH_PER_K
    fetch = (f"the case fetch the full candidate set, the decisions fetch "
             f"bounded at {DECISIONS_FETCH_PER_K}·k pieces" if "raw_decisions" in a
             else "full-candidate-set fetch")
    scale = (f"{sum(a['counts'].values())} case chunks in {a['counts']}, "
             f"{a['decisions']} decision {'pieces' if 'raw_decisions' in a else 'vectors'}")
    if same_store and build_vs_load and rebuild:
        print("VERDICT: IDENTICAL — ids, order, and scores byte-equal across "
              "fresh processes, across build-vs-load, and across two "
              "independent HNSW builds, at tool level and raw chunk level. "
              f"HNSW happens to be reproducible at this scale ({scale}; "
              f"{fetch}); this is a measurement, not a "
              "guarantee — a larger corpus, a wider fetch, or a Chroma "
              "bump reopens it (A-25).")
    else:
        print("VERDICT: NOT IDENTICAL — see per-comparison diffs above "
              "(membership vs order vs scores). A-25 must record the "
              "variance and every consumer that assumed reproducible "
              "retrieval must stop.")


if __name__ == "__main__":
    main()
