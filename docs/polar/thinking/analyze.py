#!/usr/bin/env python3
"""CP-28 analyzer: per-episode measurements over receiver-side SessionResults.

Reads accepted traces from <traces-dir>/*.json and quarantined ones from
<traces-dir>/quarantine/*.json (wrapper {"findings", "session_result"}).
Emits per-episode rows (JSON lines) + a summary. Tokenizer decode of think
spans is optional (--decode, needs transformers)."""
import argparse, glob, hashlib, json, os, statistics as st, sys

THINK_OPEN, THINK_CLOSE = 151667, 151668
EMPTY_TAIL = [151644, 77091, 198, 151667, 271, 151668, 271]
SHORT_TAIL = [151644, 77091, 198]
BUILTINS = {"read","ls","grep","find","write","edit","bash"}
G2_PIN = "f56e8a6e9ea9dd1c19be89c6754a4e8d3d1c0f89e04bb21f60237aa2e8837df4"

def spans(mask, val=1):
    out, start = [], None
    for i, f in enumerate(mask):
        if f == val and start is None: start = i
        elif f != val and start is not None: out.append((start, i)); start = None
    if start is not None: out.append((start, len(mask)))
    return out

def think_segments(ids):
    segs, i = [], 0
    while i < len(ids):
        if ids[i] == THINK_OPEN:
            j = i + 1
            while j < len(ids) and ids[j] != THINK_CLOSE: j += 1
            segs.append((i, min(j + 1, len(ids))))  # inclusive of both tags
            i = j + 1
        else: i += 1
    return segs

def tool_stats(messages):
    names = {}
    calls, results = [], []
    for m in messages:
        for c in (m.get("tool_calls") or []):
            fn = (c.get("function") or {}).get("name")
            names[c.get("id")] = fn
            calls.append(fn)
        if m.get("role") == "tool":
            content = m.get("content")
            if isinstance(content, list):
                content = "".join(p.get("text","") for p in content if isinstance(p,dict))
            content = content or ""
            is_err = bool(m.get("isError")) or content.lstrip().startswith("Error")
            results.append((names.get(m.get("tool_call_id")), not is_err))
    return calls, results

def episode_row(sr, findings, source):
    t = sr["trajectory"]; meta = t["metadata"]
    tr = (t.get("traces") or [{}])[0]
    ids, mask = tr.get("response_ids") or [], tr.get("loss_mask") or []
    pids = tr.get("prompt_ids") or []
    m1 = spans(mask, 1)
    sampled = [ids[a:b] for a, b in m1]
    think_tok = think_blocks = 0
    per_turn_think = []
    for seg in sampled:
        segs = think_segments(seg)
        n = sum(b - a for a, b in segs)
        think_blocks += len(segs); think_tok += n
        per_turn_think.append(n)
    mask1 = sum(mask)
    calls, results = tool_stats(tr.get("response_messages") or [])
    ok_by = {}
    for name, ok in results:
        ok_by.setdefault(name, [0,0]); ok_by[name][ok] += 1
    builtin_ok = sum(v[1] for k, v in ok_by.items() if k in BUILTINS)
    mcp_ok = sum(v[1] for k, v in ok_by.items() if k and k.startswith("mcp_gsj_"))
    sysmsgs = [m for m in (tr.get("prompt_messages") or []) if m.get("role")=="system"]
    def flat(c):
        if isinstance(c, list): return "".join(p.get("text","") for p in c if isinstance(p,dict))
        return c or ""
    g2_ok = all(hashlib.sha256(flat(m.get("content")).encode()).hexdigest()==G2_PIN for m in sysmsgs) if sysmsgs else None
    rs = meta.get("reconstruction_stats") or {}
    gv = meta.get("gsj_validation") or {}
    interstitials = []
    ends = [b for _, b in m1]
    for k, (a, b) in enumerate(m1):
        opening = (pids + ids[:a]) if k == 0 else ids[ends[k-1]:a]
        tail7 = opening[-7:] == EMPTY_TAIL
        tail3 = opening[-3:] == SHORT_TAIL
        interstitials.append("empty7" if tail7 else ("short3" if tail3 else "other:"+repr(opening[-8:])))
    return {
        "session_id": sr.get("session_id"), "task_id": sr.get("task_id"),
        "source": source, "status": sr.get("status"),
        "run_ms": round((sr.get("timing") or {}).get("run_ms") or 0),
        "findings": findings, "builder_findings": gv.get("findings"),
        "chains_total": rs.get("chains_total"), "completions": rs.get("completions_total"),
        "glue_stitched": gv.get("glue_stitched"),
        "prompt_len": len(pids), "response_len": len(ids),
        "total_len": len(pids)+len(ids), "pct_32k": round(100*(len(pids)+len(ids))/32768,1),
        "finish_reason": tr.get("finish_reason"), "mask1": mask1,
        "turns": len(m1), "think_blocks": think_blocks, "think_tokens": think_tok,
        "think_frac_of_sampled": round(think_tok/mask1, 3) if mask1 else None,
        "per_turn_think": per_turn_think,
        "tool_calls_total": len(calls),
        "tool_calls_mcp": sum(1 for c in calls if c and c.startswith("mcp_gsj_")),
        "tool_calls_builtin": sum(1 for c in calls if c in BUILTINS),
        "builtin_ok": builtin_ok, "mcp_ok": mcp_ok,
        "tool_ok_by_name": {k: {"err": v[0], "ok": v[1]} for k, v in ok_by.items()},
        "g2_system_prompt_matches_pin": g2_ok,
        "turn_opening_tails": interstitials,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces_dir"); ap.add_argument("--decode", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    for f in sorted(glob.glob(os.path.join(a.traces_dir, "sk-*.json"))):
        sr = json.load(open(f)); rows.append(episode_row(sr, [], "accepted"))
    qdir = os.path.join(a.traces_dir, "quarantine")
    for f in sorted(glob.glob(os.path.join(qdir, "sk-*.json"))):
        d = json.load(open(f)); rows.append(episode_row(d["session_result"], d.get("findings"), "quarantined"))
    if a.decode and rows:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B",
              revision="c1899de289a04d12100db370d81485cdf75e47ca")
        for row, f in zip(rows, sorted(glob.glob(os.path.join(a.traces_dir,"sk-*.json"))) +
                          sorted(glob.glob(os.path.join(qdir,"sk-*.json")))):
            d = json.load(open(f)); sr = d.get("session_result", d)
            tr = sr["trajectory"]["traces"][0]
            ids, mask = tr["response_ids"], tr["loss_mask"]
            texts = []
            for s, e in spans(mask, 1):
                for x, y in think_segments(ids[s:e]):
                    texts.append(tok.decode(ids[s+x:s+y]))
            row["think_texts"] = texts
    out = a.out or "-"
    payload = {"dir": a.traces_dir, "episodes": rows}
    lens = [r["think_tokens"] for r in rows]
    resp = [r["response_len"] for r in rows]
    tot  = [r["total_len"] for r in rows]
    ms   = [r["run_ms"] for r in rows]
    def dist(v):
        if not v: return None
        q = sorted(v)
        return {"n": len(v), "min": q[0], "p25": q[len(q)//4], "median": q[len(q)//2],
                "p75": q[3*len(q)//4], "max": q[-1], "mean": round(st.mean(v),1)}
    payload["summary"] = {
        "n": len(rows),
        "accepted": sum(1 for r in rows if r["source"]=="accepted"),
        "quarantined": sum(1 for r in rows if r["source"]=="quarantined"),
        "think_tokens": dist(lens), "response_len": dist(resp), "total_len": dist(tot),
        "run_ms": dist(ms),
        "finish_reasons": {fr: sum(1 for r in rows if r["finish_reason"]==fr) for fr in {r["finish_reason"] for r in rows}},
        "chains_total_ne_1": sum(1 for r in rows if r["chains_total"] != 1),
        "mcp_ok_ge_1": sum(1 for r in rows if r["mcp_ok"] >= 1),
        "builtin_ok_ge_1": sum(1 for r in rows if r["builtin_ok"] >= 1),
    }
    s = json.dumps(payload, indent=1)
    (open(out, "w").write(s) if out != "-" else print(s))
    print(json.dumps(payload["summary"], indent=1), file=sys.stderr)

if __name__ == "__main__":
    main()
