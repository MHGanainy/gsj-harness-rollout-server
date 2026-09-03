#!/usr/bin/env python3
"""CP-79 — the bounded fetch's recall, measured (not a pytest module).

The decisions surface fetches ``DECISIONS_FETCH_PER_K × k`` pieces and
aggregates them best-piece-per-unit (docs/decisions-surface.md §8.1/§8.4);
nothing on the wire can test what that bound loses, so this script
measures it against an exact scan over the stored vectors themselves:

    .venv/bin/python tests/measure_decisions_recall.py --decisions-path <dir> \\
        [--store <dir>] [--queries N] [--seed S] [--factors 5,10,20,50,100]

It builds (or, pointed at an existing ``--store``, reuses) a store over
``case_0003`` and the drop, draws ``--queries`` probe queries from the
drop's own units (a sentence-sized slice of a unit, so every query has a
true nearest neighbour) plus a few free-text ones, and for each query and
each ``k`` in (5, 20) computes the EXACT top-k units (numpy over every
stored piece vector, the same best-piece-per-unit rule, the same order)
and compares: the service's own search at the shipped bound (recall@k =
|service top-k ∩ exact top-k| / k), the search at every ``--factors``
multiple of k, and an UNBOUNDED HNSW fetch (n_results = every piece, ids and
distances only — chroma's read path refuses a metadata fetch above
32,766 ids, the same SQLite variable limit CP-77 met on the write path,
measured at CP-79) — which separates what the bound loses from what the
HNSW graph itself loses (A-25's known tail). Prints a table and writes
the per-query numbers as JSON beside the store.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import make_state, write_config  # noqa: E402

FREE_QUERIES = [
    "Sittenwidrigkeit im Sinne von § 826 BGB",
    "Widerruf eines Verbraucherdarlehensvertrags",
    "Nichtzulassungsbeschwerde Beschwer Feststellung",
    "Kosten des Rechtsstreits trägt der Kläger",
    "Rechtsmittelbelehrung Anwaltsgerichtshof",
    "Haftung des Automobilherstellers Dieselfall",
    "Verjährung des Anspruchs Kenntnis des Gläubigers",
    "Zurückverweisung an das Berufungsgericht",
]


def exact_topk(vectors: np.ndarray, units: np.ndarray, order_key, query: np.ndarray,
               k: int) -> list[tuple[str, int]]:
    """Best piece per unit over EVERY stored vector, then §8.2's order."""
    scores = vectors @ query
    best: dict[int, float] = {}
    for unit_ix, score in zip(units.tolist(), scores.tolist()):
        if unit_ix not in best or score > best[unit_ix]:
            best[unit_ix] = score
    ranked = sorted(best.items(), key=lambda item: (-item[1], order_key(item[0])))
    return [order_key(u) for u, s in ranked[:k] if s > 0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--decisions-path", required=True)
    parser.add_argument("--store", default=None,
                        help="an existing config's directory to reuse (its "
                             "config.yaml, clones/ and index/); default: a "
                             "fresh temp store")
    parser.add_argument("--queries", type=int, default=40)
    parser.add_argument("--seed", type=int, default=79)
    parser.add_argument("--factors", default="5,10,20,50,100")
    args = parser.parse_args()
    factors = [int(f) for f in args.factors.split(",")]

    root = Path(args.store) if args.store else Path(
        tempfile.mkdtemp(prefix="cp79-recall-"))
    config_path = root / "config.yaml"
    wanted_path = str(Path(args.decisions_path).resolve())
    if not config_path.exists():
        write_config(root, repos=["case_0003"], clone_cache_dir=root / "clones",
                     index_path=root / "index", decisions_path=wanted_path)
    else:
        import yaml
        recorded = (yaml.safe_load(config_path.read_text()).get("decisions") or {}).get("path")
        if recorded != wanted_path:
            raise SystemExit(f"--store {root} was built over {recorded!r}, not "
                             f"--decisions-path {wanted_path!r}")
    print(f"store {root}")
    started = time.time()
    state = make_state(config_path)
    assert state.status == "ready", state.error
    index = state.decisions
    assert index.kind == "rii", "the config names no drop"
    print(f"ready in {time.time() - started:.0f}s — {index.n_decisions} decisions, "
          f"{index.n_units} units, {index.n_pieces} pieces "
          f"(index_reused={state.reused_index})")

    # every stored vector, with its unit
    unit_index: dict[tuple[str, int], int] = {}
    unit_keys: list[tuple[str, int]] = []
    for decision in index.decisions:
        for ordinal in range(len(decision["units"])):
            unit_index[(decision["decision_id"], ordinal)] = len(unit_keys)
            unit_keys.append((decision["decision_id"], ordinal))
    vectors, units = [], []
    unit_of_id: dict[str, int] = {}
    page = 5000
    for offset in range(0, index.n_pieces, page):
        got = index.collection.get(include=["embeddings", "metadatas"],
                                   limit=page, offset=offset)
        vectors.append(np.asarray(got["embeddings"], dtype=np.float32))
        for pid, m in zip(got["ids"], got["metadatas"]):
            unit_of_id[pid] = unit_index[(m["doknr"], int(m["unit"]))]
            units.append(unit_of_id[pid])
    vectors = np.concatenate(vectors)
    units = np.asarray(units)
    assert vectors.shape[0] == index.n_pieces == len(units)
    print(f"fetched {vectors.shape} vectors for the exact scan")

    def unbounded_topk(query: np.ndarray, k: int):
        """Every piece through HNSW (ids + distances only), then the same
        best-piece-per-unit rule and order as the exact scan."""
        got = index.collection.query(query_embeddings=[query],
                                     n_results=index.n_pieces,
                                     include=["distances"])
        best: dict[int, float] = {}
        for pid, distance in zip(got["ids"][0], got["distances"][0]):
            unit_ix, score = unit_of_id[pid], 1.0 - float(distance)
            if unit_ix not in best or score > best[unit_ix]:
                best[unit_ix] = score
        ranked = sorted(best.items(), key=lambda item: (-item[1], order_key(item[0])))
        return [order_key(u) for u, s in ranked[:k] if s > 0], len(got["ids"][0])

    from gsj_mcp_service.decisions import SECTION_ORDER

    def order_key(unit_ix: int):
        doknr, ordinal = unit_keys[unit_ix]
        unit = index._by_id[doknr]["units"][ordinal]
        return (doknr, SECTION_ORDER[unit["section"]], unit["rn"] is not None,
                unit["rn"] or 0, ordinal)

    def hit_key(hit: dict):
        doknr = hit["decision_id"]
        ordinal = next(i for i, u in enumerate(index._by_id[doknr]["units"])
                       if u["section"] == hit["section"] and u["rn"] == hit["rn"]
                       and u["text"] == hit["text"])
        return order_key(unit_index[(doknr, ordinal)])

    rng = random.Random(args.seed)
    queries = list(FREE_QUERIES)
    pool = [(d["decision_id"], u) for d in index.decisions for u in d["units"]
            if len(u["text"]) > 200]
    for _ in range(max(0, args.queries - len(queries))):
        _, unit = rng.choice(pool)
        text = unit["text"]
        start = rng.randrange(0, max(1, len(text) - 160))
        queries.append(" ".join(text[start:start + 160].split()[1:-1]))

    from gsj_mcp_service.index import DECISIONS_FETCH_PER_K
    rows = []
    ks = (5, 20)
    for qi, query in enumerate(queries):
        vec, _ = state.encoder.encode_query(query)
        row = {"query": query[:80], "k": {}}
        for k in ks:
            exact = exact_topk(vectors, units, order_key, vec, k)
            got = {}
            for factor in factors:
                hits = index.search(vec, k=k, fetch=factor * k)
                got[f"x{factor}"] = [hit_key(h) for h in hits]
            got["unbounded"], returned = unbounded_topk(vec, k)
            row.setdefault("unbounded_returned", returned)
            hits = index.search(vec, k=k)
            got["shipped"] = [hit_key(h) for h in hits]
            row["k"][k] = {
                name: {"recall": len(set(keys) & set(exact)) / max(1, len(exact)),
                       "top1": bool(keys and exact and keys[0] == exact[0]),
                       "exact_order": keys == exact}
                for name, keys in got.items()}
        rows.append(row)
        if (qi + 1) % 10 == 0:
            print(f"  {qi + 1}/{len(queries)} queries")

    print(f"\nrecall against the exact scan over {index.n_pieces} pieces "
          f"({index.n_units} units), {len(queries)} queries; shipped bound "
          f"= {DECISIONS_FETCH_PER_K}·k")
    names = [f"x{f}" for f in factors] + ["unbounded", "shipped"]
    print(f"{'fetch':>10} " + " ".join(f"{'k=' + str(k) + ' mean/min/top1/order':>28}" for k in ks))
    summary: dict = {}
    for name in names:
        cells = []
        for k in ks:
            recalls = [r["k"][k][name]["recall"] for r in rows]
            top1 = sum(r["k"][k][name]["top1"] for r in rows)
            order = sum(r["k"][k][name]["exact_order"] for r in rows)
            summary[f"{name}/k{k}"] = {"mean": sum(recalls) / len(recalls),
                                      "min": min(recalls), "top1": top1,
                                      "exact_order": order, "n": len(rows)}
            cells.append(f"{sum(recalls) / len(recalls):.4f}/{min(recalls):.2f}/"
                         f"{top1}/{order} of {len(rows)}")
        print(f"{name:>10} " + " ".join(f"{c:>28}" for c in cells))
    out = root / "recall.json"
    out.write_text(json.dumps({"pieces": index.n_pieces, "units": index.n_units,
                               "decisions": index.n_decisions,
                               "fetch_per_k": DECISIONS_FETCH_PER_K,
                               "summary": summary, "rows": rows},
                              ensure_ascii=False, indent=1))
    print(f"written {out}")


if __name__ == "__main__":
    main()
