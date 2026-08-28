#!/usr/bin/env python3
"""The pins walk, reproducible (CP-11; re-run at CP-04' on the H200 — G4's
measure-at-serve instrument, ADR-0011): re-derives every `pins.gsj.json`
approved value from the evidence named in its provenance block and exits
nonzero on any divergence.

CP-04' addition: the engine now serves an EXPLICIT template file
(`--chat-template`, the Direction-A flip), so the template the engine
actually renders with is the file, not a snapshot's embedded
`chat_template` field. Point GSJ_SERVED_TEMPLATE at that file (default:
estate/serving/qwen3_training.jinja); every snapshot-embedded template is
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

CP-51 addition (engine provenance, the simple form — gap row 22 / wishlist
38): the walk also states the ENGINE the approved values were measured
against — served model name (asked of GSJ_SERVED_ENDPOINT's /v1/models),
snapshot revision, and the sha256 of the generation config, the tokenizer
and the chat template as served — and with `--record` writes that block
into both pins documents' `provenance.engine`, leaving every approved value
byte-identical (refused otherwise). Every archive the receiver writes is
named for the pins file its process resolved (CP-33, F-48), so this is
where an archived trace becomes attributable to an engine without a
library line. Anything this host cannot measure is written as a NAMED
absence, never a default.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib import error, request

REPO = Path(__file__).resolve().parent.parent
HF = Path.home() / ".cache/huggingface/hub"
CODEC = Path(os.environ.get(
    "GSJ_CODEC_SNAPSHOT",
    HF / "models--Qwen--Qwen3-0.6B/snapshots/c1899de289a04d12100db370d81485cdf75e47ca"))
SERVED = Path(os.environ.get(
    "GSJ_SERVED_SNAPSHOT",
    HF / "models--Qwen--Qwen3-0.6B/snapshots/c1899de289a04d12100db370d81485cdf75e47ca"))
SERVED_TEMPLATE = Path(os.environ.get(
    "GSJ_SERVED_TEMPLATE", REPO / "estate/serving/qwen3_training.jinja"))
# CP-51: the engine the walk attests (e.g. http://127.0.0.1:8000). Unset, the
# served-model line is a named absence — the walk never invents an engine.
SERVED_ENDPOINT = os.environ.get("GSJ_SERVED_ENDPOINT")


def canonical_json(obj) -> str:  # the predecessor's convention, byte-exact
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def sha256_canonical_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _absent(why: str) -> dict:
    return {"absent": why}   # a stated absence — never a plausible default (CP-19)


def _shown(path: Path) -> str:
    """Paths as the provenance block already writes them: ~ for the home
    directory, repo-relative inside the checkout — host-portable text."""
    for root, prefix in ((REPO, ""), (Path.home(), "~/")):
        try:
            return prefix + str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def engine_provenance() -> dict:
    """CP-51 — the engine identity, recorded beside the values measured on it.

    Every value names its source. What this host cannot measure is an
    absence with its reason. NOT covered, by construction: an engine
    restarted mid-run without a re-derive — the walk states the engine at
    walk time; gap row 22 keeps that residual with its owner.
    """
    block: dict = {
        "recorded_by": "pins/derive_pins.py --record (CP-51) — re-run at every serve change",
        "served_model": _absent("GSJ_SERVED_ENDPOINT unset on this host — the walk asked no engine"),
        "snapshot_revision": _absent(f"served snapshot not on this host: {_shown(SERVED)}"),
        "generation_config_sha256": _absent(f"served snapshot not on this host: {_shown(SERVED)}"),
        "tokenizer_git_blob_oid": _absent(f"served snapshot not on this host: {_shown(SERVED)}"),
        "chat_template_sha256": _absent(f"served --chat-template file missing: {_shown(SERVED_TEMPLATE)}"),
    }
    if SERVED_ENDPOINT:
        url = f"{SERVED_ENDPOINT.rstrip('/')}/v1/models"
        try:
            with request.urlopen(url, timeout=5) as resp:
                models = json.loads(resp.read().decode("utf-8")).get("data") or []
        except (error.URLError, OSError, ValueError) as exc:
            block["served_model"] = _absent(f"GET {url} failed: {exc}")
        else:
            if not models:
                block["served_model"] = _absent(f"GET {url} listed no models")
            else:
                first = models[0]
                block["served_model"] = {
                    "id": first.get("id"), "root": first.get("root"),
                    "revision": (first["revision"] if first.get("revision") is not None else
                                 _absent("the endpoint reports no revision (vLLM's /v1/models "
                                         "carries none) — see snapshot_revision")),
                    "source": f"GET {url}" + (f" ({len(models)} listed; the first recorded)"
                                              if len(models) > 1 else ""),
                }
    if SERVED.exists():
        block["snapshot_revision"] = {
            "value": SERVED.name,
            "source": f"the served snapshot's path {_shown(SERVED)} — a local-disk fact, not the endpoint's"}
        for key, name, digest, why in (
                ("generation_config_sha256", "generation_config.json", sha256_bytes,
                 "the file serve.sh's --generation-config points at (the argv itself is not read)"),
                ("tokenizer_git_blob_oid", "tokenizer.json", git_blob_oid, "the served tokenizer")):
            path = SERVED / name
            block[key] = ({"value": digest(path.read_bytes()), "source": f"{_shown(path)} — {why}"}
                          if path.exists() else _absent(f"{_shown(path)} missing in the served snapshot"))
    if SERVED_TEMPLATE.exists():
        block["chat_template_sha256"] = {
            "value": sha256_bytes(SERVED_TEMPLATE.read_bytes()),
            "source": f"the served --chat-template file {_shown(SERVED_TEMPLATE)}"}
    return block


def record_engine_provenance(block: dict) -> None:
    """Write the block into BOTH pins documents (one estate, two modes —
    ADR-0024) under provenance.engine, with every approved value byte-identical:
    the walk re-parses what it is about to write and refuses if `pins` moved
    (CP-41's standard — a provenance edit that moves a hash is not one)."""
    for path in (REPO / "pins/pins.gsj.json", REPO / "pins/thinking-on/pins.gsj.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(doc["pins"], sort_keys=True)
        doc["provenance"]["engine"] = block
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        if json.dumps(json.loads(text)["pins"], sort_keys=True) != before:
            raise SystemExit(f"refusing to write {path}: an approved value would move")
        path.write_text(text, encoding="utf-8")
        print(f"recorded provenance.engine -> {path.relative_to(REPO)}")


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
    # CP-51 (wishlist 19(b)): every card in the tree, not a hardcoded pair — a
    # new card is pinnable without a script edit.
    for card in sorted((REPO / "estate/corpus/staging/skills").glob("*/SKILL.md")):
        expect("skill_card_hash", sha256_bytes(card.read_bytes()), str(card.relative_to(REPO)))
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
    # CP-30 (ADR-0024): the per-mode sibling — one estate mode per pins FILE,
    # selected via GSJ_PINS_PATH; this walk is the drift guard between them.
    on_pins = json.loads((REPO / "pins/thinking-on/pins.gsj.json").read_text())["pins"]
    g6_keys = {"g6_expected_tail", "g6_expected_tail_ids"}
    shared_ok = set(on_pins) == set(pins) and all(
        on_pins[key] == pins[key] for key in set(pins) - g6_keys)
    print(f"{'ok  ' if shared_ok else 'FAIL'} thinking-on pins: non-G6 approved sets == pins.gsj.json")
    if not shared_ok:
        failures.append("thinking-on pins: non-G6 sets diverge from pins.gsj.json")
    on_tail = (REPO / "pins/thinking-on/g6_tail.captured.txt").read_text()
    # EXACT identity, not startswith: the on tail is the off tail's first
    # line (through its '\n'), so any other prefix length fails deskside —
    # the adversarial pass measured bare startswith green on a corrupted
    # 41-byte or 12-byte tail file wherever the tokenizer leg skips.
    on_ok = (on_pins["g6_expected_tail"] == [on_tail]
             and on_tail == tail_text[:tail_text.index("\n") + 1]
             and on_pins["g6_expected_tail_ids"] == [pins["g6_expected_tail_ids"][0][:3]])
    print(f"{'ok  ' if on_ok else 'FAIL'} thinking-on tail: byte-prefix of the off tail, ids its first three")
    if not on_ok:
        failures.append("thinking-on tail/ids do not derive from the off tail")
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
            on_ids = tok(on_tail, add_special_tokens=False)["input_ids"]
            on_ids_ok = on_ids in on_pins["g6_expected_tail_ids"]
            print(f"{'ok  ' if on_ids_ok else 'FAIL'} thinking-on g6_expected_tail_ids "
                  f"<- served tokenizer: {on_ids}")
            if not on_ids_ok:
                failures.append(f"thinking-on g6_expected_tail_ids: derived {on_ids}, "
                                f"approved {on_pins['g6_expected_tail_ids']}")
        else:
            print("skip g6_expected_tail_ids (served snapshot absent)")

    # CP-51: the engine identity beside the values it was measured against.
    engine = engine_provenance()
    print("\nengine provenance (written by --record; absences are named, never defaulted):")
    print(json.dumps(engine, indent=2, ensure_ascii=False))

    if failures:
        print("\nDIVERGED:\n  " + "\n  ".join(failures))
        return 1
    if "--record" in sys.argv[1:]:   # only a walk that reproduced everything may record
        record_engine_provenance(engine)
    print("\nall approved values reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
