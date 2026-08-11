#!/usr/bin/env python3
"""The pins walk, reproducible (CP-11; re-run at CP-04' on the H200 — G4's
measure-at-serve instrument, ADR-0011): re-derives every `pins.gsj.json`
approved value from the evidence named in its provenance block and exits
nonzero on any divergence.

CP-04' addition: the engine now serves an EXPLICIT template file
(`--chat-template`, the Direction-A flip), so the template the engine
actually renders with is the file, not a snapshot's embedded
`chat_template` field. Point GSJ_SERVED_TEMPLATE at that file (default:
staging/serving/qwen3_training.jinja); every snapshot-embedded template is
then recorded-not-approved. `g6_expected_tail_ids` is verified against the
served tokenizer when transformers is importable (estate-side, where the
tokenizer exists at pin time — ADR-0011); on a tokenizer-less host that
step reports skip, never silently passes.

Conventions are `docs/checks-spec.md` §The four hashing conventions,
reproduced exactly (canonical_json == the predecessor's store.py:88-91);
the anchor test against pins/tools.captured.json proves the convention
before any value is trusted.

Snapshot roots default to the Mac estate's HF cache; override with
GSJ_CODEC_SNAPSHOT / GSJ_SERVED_SNAPSHOT.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HF = Path.home() / ".cache/huggingface/hub"
CODEC = Path(os.environ.get(
    "GSJ_CODEC_SNAPSHOT",
    HF / "models--Qwen--Qwen3-0.6B/snapshots/c1899de289a04d12100db370d81485cdf75e47ca"))
SERVED = Path(os.environ.get(
    "GSJ_SERVED_SNAPSHOT",
    HF / "models--Qwen--Qwen3-0.6B/snapshots/c1899de289a04d12100db370d81485cdf75e47ca"))
SERVED_TEMPLATE = Path(os.environ.get(
    "GSJ_SERVED_TEMPLATE", REPO / "staging/serving/qwen3_training.jinja"))


def canonical_json(obj) -> str:  # the predecessor's convention, byte-exact
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def sha256_canonical_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def main() -> int:
    pins = json.loads((REPO / "pins/pins.gsj.json").read_text())["pins"]
    failures: list[str] = []

    def expect(key: str, value: str, label: str) -> None:
        ok = value in pins[key]
        print(f"{'ok  ' if ok else 'FAIL'} {key} <- {label}: {value}")
        if not ok:
            failures.append(f"{key}: {label} derived {value}, approved {pins[key]}")

    # Convention anchor first — if this fails, nothing below is trustworthy.
    anchor = sha256_canonical_json(json.loads((REPO / "pins/tools.captured.json").read_text()))
    expect("tool_roster_hash", anchor, "convention anchor pins/tools.captured.json")

    for episode in ("pi-corpus", "fidelity"):
        trace = json.loads((REPO / f"docs/polar/{episode}/trace.json").read_text())
        expect("tool_roster_hash", sha256_canonical_json(trace["tools"]),
               f"docs/polar/{episode}/trace.json tools[]")
        first = trace["prompt_messages"][0]
        assert first["role"] == "system" and isinstance(first["content"], str), episode
        expect("system_prompt_hash", sha256_bytes(first["content"].encode("utf-8")),
               f"docs/polar/{episode}/trace.json prompt_messages[0]")

    expect("system_prompt_hash",
           sha256_bytes((REPO / "pins/container/system_prompt.container.derived.txt").read_bytes()),
           "pins/container/system_prompt.container.derived.txt")
    expect("settings_hash",
           sha256_canonical_json(json.loads((REPO / "pins/settings.rendered.json").read_text())),
           "pins/settings.rendered.json")
    expect("settings_hash", sha256_canonical_json({"compaction": {"enabled": False}}),
           "pi_harness settings_json constant")
    for skill in ("summarize", "analyze"):
        expect("skill_card_hash",
               sha256_bytes((REPO / f"corpus/staging/skills/{skill}/SKILL.md").read_bytes()),
               f"corpus/staging/skills/{skill}/SKILL.md")
    for label, snap in (("codec", CODEC), ("served", SERVED)):
        if not snap.exists():
            print(f"skip {label} snapshot (absent): {snap}")
            continue
        expect("tokenizer_hash", git_blob_oid((snap / "tokenizer.json").read_bytes()),
               f"{label} tokenizer.json")
        template = json.loads((snap / "tokenizer_config.json").read_text())["chat_template"]
        digest = sha256_bytes(template.encode("utf-8"))
        # CP-04': under --chat-template a snapshot-embedded template never
        # builds a wire prompt — measured and recorded, deliberately NOT
        # approved (finding (a)'s binding rule: pin what the engine renders
        # with; a dead entry weakens the gate).
        print(f"note chat_template_hash [{label} snapshot, not approved]: {digest}")
    expect("chat_template_hash", sha256_bytes(SERVED_TEMPLATE.read_bytes()),
           f"served --chat-template file {SERVED_TEMPLATE.name}")
    tail_text = (REPO / "pins/g6_tail.captured.txt").read_text()
    expect("g6_expected_tail", tail_text, "pins/g6_tail.captured.txt")
    try:
        from transformers import AutoTokenizer  # estate-side only (ADR-0011)
    except ImportError:
        print("skip g6_expected_tail_ids (no tokenizer on this host — "
              "pin-time verification is estate-side by design, ADR-0011)")
    else:
        if SERVED.exists():
            tok = AutoTokenizer.from_pretrained(str(SERVED))
            expect("g6_expected_tail_ids",
                   tok(tail_text, add_special_tokens=False)["input_ids"],
                   "served tokenizer over pins/g6_tail.captured.txt")
        else:
            print("skip g6_expected_tail_ids (served snapshot absent)")

    if failures:
        print("\nDIVERGED:\n  " + "\n  ".join(failures))
        return 1
    print("\nall approved values reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
