#!/usr/bin/env python3
"""Derive the per-case G2 system-prompt texts (ADR-0014 / ADR-0023(i)).

The effective system prompt embeds the checkout path — under the ADR-0014
path scheme that is ``<work_root>/<case_id>``, the ONLY case-dependent span
in the text (branch switches are invisible to the system prompt). So each
case's expected text is derivable from the captured case_0001 prompt by pure
byte substitution, no live episode per case required:

    derived(case) = captured.replace(f"{work_root}/case_0001",
                                     f"{work_root}/{case}")

Everything runs on BYTES (no text-mode newline/encoding drift), and the
identity check runs BEFORE any file is written: derived(case_0001) must equal
the captured bytes — the substitution is the identity there, so a mismatch
means the derivation logic itself drifted (a wrong ``--work-root`` is caught
earlier, by the occurrence check). After writing, the case_0001 file is
read back and compared byte-for-byte; on any failure every derived file is
removed — a FAIL never leaves poisoned artifacts for a later ``gsj-pin``
run to pin.

The three non-captured hashes (case_0002..case_0004) are validated
empirically at P7's first non-case_0001 real episode — until then they are
scheme-derived, not observed (noted in the predecessor's reports/CP-12.md;
CP/ADR numbers in this file are the predecessor's, @ v0.8.0).

Usage (from the repo root; work_root must match the dev TaskConfig — the
CP-05 capture used /private/tmp/gsj-ep-cp05):

    python3 pins/derive_g2.py --work-root /private/tmp/gsj-ep-cp05

then re-pin (the predecessor's ``gsj-pin``; this repo's re-pin tooling
arrives with checks.py, CP-11 — docs/checks-spec.md): the
``system_prompt_hash`` approved set grows 1→4 and nothing else changes.

``--constant-path`` (CP-22, ADR-0034(c)) is the docker-mode singleton
derivation: the in-container prompt embeds the constant ``/workspace``
checkout path, so there is nothing to substitute — the mode verifies the
constant path occurs, verifies NO fixture case id occurs (the
case-invariance proof), and writes ONE artifact,
``system_prompt.container.derived.txt``, for gsj-pin to pin:

    python3 pins/derive_g2.py --constant-path /workspace \\
        --captured <in-container capture> --out-dir pins/container
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PINS_DIR = Path(__file__).resolve().parent
REPO = PINS_DIR.parent          # pins/ sits at the repo root since CP-01
CAPTURED = PINS_DIR / "system_prompt.captured.txt"
# Case ids come from the corpus pipeline's freeze record (CP-34, ADR-0048;
# was the fixture builder's cases_manifest.json until the M8b purge).
CASES_MANIFEST = REPO / "corpus" / "staging" / "corpus.lock.json"
CAPTURED_CASE_ID = "case_0001"  # the CP-05 capture's case


def constant_path_mode(args) -> int:
    """Docker-mode singleton (ADR-0034(c)): verify + copy, no substitution."""
    captured = args.captured.read_bytes()
    constant = args.constant_path.rstrip("/").encode()
    if constant not in captured:
        print(
            f"FAIL: constant path {constant.decode()!r} does not occur in "
            f"{args.captured} — not an in-container capture",
            file=sys.stderr,
        )
        return 1
    case_ids = sorted(json.loads(args.cases_manifest.read_text())["cases"])
    leaked = [case_id for case_id in case_ids if case_id.encode() in captured]
    if leaked:
        print(
            f"FAIL: case id(s) {leaked} occur in the capture — the prompt is "
            "not case-invariant, the singleton collapse does not hold",
            file=sys.stderr,
        )
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "system_prompt.container.derived.txt"
    out.write_bytes(captured)
    if out.read_bytes() != captured:
        out.unlink(missing_ok=True)
        print("FAIL: write/read round-trip drift; derived file removed",
              file=sys.stderr)
        return 1
    print(f"{out.name}: constant path × {captured.count(constant)}, "
          f"0 case-id leaks across {len(case_ids)} corpus cases")
    print("case-invariance check (docker singleton): PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--work-root",
        help="the dev TaskConfig work_root the capture ran under "
             "(checkouts at <work_root>/<case_id>, ADR-0014)",
    )
    parser.add_argument(
        "--constant-path",
        help="docker-mode singleton derivation (ADR-0034(c)): the constant "
             "in-container checkout path (/workspace); mutually exclusive "
             "with --work-root",
    )
    parser.add_argument("--captured", type=Path, default=CAPTURED)
    parser.add_argument(
        "--cases-manifest", type=Path, default=CASES_MANIFEST,
        help="case ids: a JSON file with a 'cases' mapping "
             "(corpus/staging/corpus.lock.json)",
    )
    parser.add_argument("--out-dir", type=Path, default=PINS_DIR)
    args = parser.parse_args()
    if bool(args.work_root) == bool(args.constant_path):
        parser.error("exactly one of --work-root / --constant-path is required")
    if args.constant_path:
        return constant_path_mode(args)

    captured = args.captured.read_bytes()
    work_root = args.work_root.rstrip("/")
    needle = f"{work_root}/{CAPTURED_CASE_ID}".encode()
    occurrences = captured.count(needle)
    if not occurrences:
        print(
            f"FAIL: {needle.decode()!r} does not occur in {args.captured} — "
            "--work-root does not match the captured checkout path scheme",
            file=sys.stderr,
        )
        return 1

    case_ids = sorted(json.loads(args.cases_manifest.read_text())["cases"])
    if CAPTURED_CASE_ID not in case_ids:
        print(f"FAIL: {CAPTURED_CASE_ID} missing from {args.cases_manifest}",
              file=sys.stderr)
        return 1

    derived = {
        case_id: captured.replace(needle, f"{work_root}/{case_id}".encode())
        for case_id in case_ids
    }
    # identity check BEFORE any write: substitution must be the identity on
    # the captured case — a mismatch is derivation-logic drift, hard fail
    if derived[CAPTURED_CASE_ID] != captured:
        print(f"identity check ({CAPTURED_CASE_ID}): FAIL — derivation is not "
              "the identity on the captured case; nothing written",
              file=sys.stderr)
        return 1

    outputs = {
        case_id: args.out_dir / f"system_prompt.{case_id}.derived.txt"
        for case_id in case_ids
    }
    for case_id, out in outputs.items():
        out.write_bytes(derived[case_id])
        print(f"{out.name}: {occurrences} path substitution(s)")

    # read-back round-trip guard; a FAIL removes everything just written
    if outputs[CAPTURED_CASE_ID].read_bytes() != args.captured.read_bytes():
        for out in outputs.values():
            out.unlink(missing_ok=True)
        print(f"identity check ({CAPTURED_CASE_ID}): FAIL — write/read "
              "round-trip drift; derived files removed", file=sys.stderr)
        return 1
    print(f"identity check ({CAPTURED_CASE_ID} derived == captured, "
          "byte-for-byte): PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
