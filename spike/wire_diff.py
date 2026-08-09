#!/usr/bin/env python3
"""CP-06 Step 4 analysis — three-way diff of the request forms for each
completion of the pi-through-Polar run:

  original_request  (persisted)  = what pi sent to the gateway
  transformed_request (persisted) = post-transformer, PRE-engine-prepare
  wire (stub capture)             = what the engine actually received

Answers A-2 Q1 (translation fidelity + the actual wire capture point) and
Q4 (n / stop / choices arity), and G3's Q5 (which form carries the roster
the engine saw).
"""

import glob
import json

recs = sorted(
    glob.glob("spike/rollout_results/task_cp06-pi-hello/sessions/*/completions/*.json")
)
print("persisted completion records:", len(recs))
wire = [json.loads(l) for l in open("spike/captures/pi_polar_stub.jsonl")]

for i, path in enumerate(recs):
    rec = json.load(open(path))
    orig, trans = rec["original_request"], rec["transformed_request"]
    w = wire[i]["request"]
    name = path.split("/")[-1]
    print(f"=== completion {i + 1} ({name})")
    print("  original_request keys:", sorted(orig.keys()))
    print("  transformed_req keys: ", sorted(trans.keys()))
    print("  wire (stub) keys:     ", sorted(w.keys()))
    print("  model:", orig.get("model"), "->", trans.get("model"), "->", w.get("model"))
    print(
        "  stream:",
        repr(orig.get("stream")), "->", repr(trans.get("stream")), "->", repr(w.get("stream")),
    )
    print("  wire-only keys vs trans:", sorted(set(w) - set(trans)))
    print("  trans-only keys vs wire:", sorted(set(trans) - set(w)))
    print(
        "  n present anywhere:", any("n" in r for r in (orig, trans, w)),
        "| stop present anywhere:", any("stop" in r for r in (orig, trans, w)),
    )
    print("  choices in stub response:", len(wire[i]["response"]["choices"]))
    print(
        "  tools: orig==trans:", orig.get("tools") == trans.get("tools"),
        "| trans==wire:", trans.get("tools") == w.get("tools"),
    )
    print(
        "  messages: orig==trans:", orig.get("messages") == trans.get("messages"),
        "| trans==wire:", trans.get("messages") == w.get("messages"),
    )
    if orig.get("messages") != trans.get("messages"):
        for j, (a, b) in enumerate(zip(orig["messages"], trans["messages"])):
            if a != b:
                print(f"    msg[{j}] differs: roles {a.get('role')}/{b.get('role')}")
        if len(orig["messages"]) != len(trans["messages"]):
            print("    message counts:", len(orig["messages"]), len(trans["messages"]))
    for k in sorted(set(trans) & set(w)):
        if trans[k] != w[k] and k != "messages":
            tv, wv = json.dumps(trans[k])[:90], json.dumps(w[k])[:90]
            print(f"  shared key differs: {k}: trans={tv} wire={wv}")
