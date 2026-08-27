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
"""

from __future__ import annotations

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


def worker(config_path: str) -> None:
    """Runs in a FRESH process: init the state (build or fingerprint-match
    reuse — whichever the store dictates), run the fixed probes, dump JSON."""
    from helpers import make_state

    state = make_state(Path(config_path))
    assert state.status == "ready", state.error
    out: dict = {"reused": state.reused_index, "results": {}, "raw": {}}
    for case_id, timestep, query, k in CASE_QUERIES:
        vec, _ = state.encoder.encode_query(query)
        results = state.cases[case_id].search(vec, k=k, timestep=timestep)
        out["results"][f"{case_id}/T{timestep}/k{k}/{query}"] = results
    for query, k in DECISION_QUERIES:
        vec, _ = state.encoder.encode_query(query)
        out["results"][f"decisions/k{k}/{query}"] = state.decisions.search(
            vec, k=k)
    case_id, timestep, query = RAW_PROBE
    index = state.cases[case_id]
    vec, _ = state.encoder.encode_query(query)
    candidates = sum(1 for c in index.chunks if c.page <= timestep)
    raw = index.collection.query(
        query_embeddings=[vec], n_results=candidates,
        where={"page": {"$lte": timestep}}, include=["distances"])
    out["raw"] = {"ids": raw["ids"][0],
                  "distances": [repr(d) for d in raw["distances"][0]]}
    print(json.dumps(out, sort_keys=True))


def run_worker(config_path: Path) -> dict:
    proc = subprocess.run(
        [str(PYTHON), str(Path(__file__).resolve()), "worker",
         str(config_path)],
        capture_output=True, text=True, timeout=900, cwd=str(SERVICE_DIR))
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
    n = len(a["results"]) + 1
    print(f"{label}: {'IDENTICAL' if identical else 'NOT IDENTICAL'} "
          f"({n}/{n} probes)" if identical else f"{label}: NOT IDENTICAL")
    return identical


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(sys.argv[2])
        return

    root = Path(tempfile.mkdtemp(prefix="cp15-determinism-"))
    print(f"stores under {root}")
    clones = root / "clones"

    cfg1 = write_config(root / "s1", repos=ALL_REPOS, clone_cache_dir=clones,
                        index_path=root / "s1" / "index")
    cfg2 = write_config(root / "s2", repos=ALL_REPOS, clone_cache_dir=clones,
                        index_path=root / "s2" / "index")

    print("process A: fresh BUILD into store 1 ...")
    a = run_worker(cfg1)
    assert a["reused"] is False
    print("process B: fresh process, REUSE of store 1 ...")
    b = run_worker(cfg1)
    assert b["reused"] is True
    print("process C: fresh process, REUSE of store 1 ...")
    c = run_worker(cfg1)
    assert c["reused"] is True
    print("process D: fresh BUILD into store 2 (same inputs) ...")
    d = run_worker(cfg2)
    assert d["reused"] is False

    print()
    same_store = compare("B vs C (two fresh processes, same stored index)",
                         b, c)
    build_vs_load = compare("A vs B (builder process vs fresh loader)", a, b)
    rebuild = compare("A vs D (two independent builds, same inputs)", a, d)

    print()
    if same_store and build_vs_load and rebuild:
        print("VERDICT: IDENTICAL — ids, order, and scores byte-equal across "
              "fresh processes, across build-vs-load, and across two "
              "independent HNSW builds, at tool level and raw chunk level. "
              "HNSW happens to be reproducible at this scale "
              "(full-candidate-set fetch over 213 chunks); this is a "
              "measurement, not a guarantee — a larger corpus, a bounded "
              "fetch, or a Chroma bump reopens it (A-25).")
    else:
        print("VERDICT: NOT IDENTICAL — see per-comparison diffs above "
              "(membership vs order vs scores). A-25 must record the "
              "variance and every consumer that assumed reproducible "
              "retrieval must stop.")


if __name__ == "__main__":
    main()
