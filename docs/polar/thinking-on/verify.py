import json, glob
for leg in ("off", "on"):
    stored = sorted(glob.glob(f"/home/sysadmin/cp30/traces-{leg}/*.json"))
    quar = glob.glob(f"/home/sysadmin/cp30/traces-{leg}/quarantine/*.json")
    print(f"== {leg}: stored={len(stored)} quarantined={len(quar)}")
    body = json.load(open(stored[0]))
    sr = body.get("session_result", body)
    meta = sr["trajectory"]["metadata"]
    stats = meta["reconstruction_stats"]
    t = sr["trajectory"]["traces"][0]
    mask, ids = t["loss_mask"], t["response_ids"]
    pids = t["prompt_ids"]
    think_m1 = sum(1 for i, f in zip(ids, mask) if f == 1 and i in (151667, 151668))
    think_m0 = sum(1 for i, f in zip(ids, mask) if f == 0 and i in (151667, 151668))
    spans = sum(1 for i, f in enumerate(mask) if f == 1 and (i == 0 or mask[i - 1] != 1))
    on_tail = [151644, 77091, 198]
    off_tail = [151644, 77091, 198, 151667, 271, 151668, 271]
    print(" session:", sr["session_id"], "status:", sr["status"])
    print(" stats:", {k: stats.get(k) for k in ("chains_total", "chains_reconstructed_full",
          "chains_reconstructed_truncated", "completions_total", "completions_merged",
          "raw_completions_total")})
    print(" gsj_validation:", meta.get("gsj_validation"))
    print(" prompt_ids=%d response_ids=%d mask1=%d turns=%d think_ids@mask1=%d think_ids@mask0=%d finish=%s"
          % (len(pids), len(ids), sum(1 for f in mask if f == 1), spans, think_m1, think_m0,
             t["finish_reason"]))
    print(" prompt tail is ON-tail:", pids[-3:] == on_tail and pids[-7:] != off_tail,
          "| prompt tail is OFF-tail:", pids[-7:] == off_tail)
    lp = t["response_logprobs"]
    z = sum(1 for v, f in zip(lp, mask) if f == 1 and v == 0.0)
    m1 = sum(1 for f in mask if f == 1)
    print(" logprobs: positive=%d zero@mask1=%d/%d (%.1f%%)"
          % (sum(1 for v in lp if v > 0), z, m1, 100.0 * z / m1 if m1 else 0))
