"""BOTH — trace validators. `docs/checks-spec.md` is the specification and
carries ALL reasoning (CP-11 budget migration); this module implements.

One entry point, `validate_session_result`: takes the callback-shaped
`SessionResult` mapping (never the on-disk `ses_*.json` — CP-07 finding 5),
returns byte-stable ``{id}:{slug}[:detail]`` findings, empty = accepted,
never raises on content (ADR-0008 §6; unusable pins are configuration, not
content — they raise `PinsConfigurationError`, the gates never fail open). Both
legs of law 6 call it. Live: `ADM*`, `LP*`/`TR*`, G5's backstop, gates
G1/G2/G3/G7 (stats + settings echo) against `pins/pins.gsj.json`, the
policy-gated H-41 flag. Not here, reasons in the spec: G4/G6 (ADR-0011),
replay."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

ACCEPTED_STATUS = "COMPLETED"

# The failure vocabulary: byte-stable, greppable, snapshot-tested (spec).
ADM1_STATUS_NOT_COMPLETED = "ADM1:status_not_completed"
ADM2_BUILDER_FINDINGS_PRESENT = "ADM2:builder_findings_present"
ADM3_TRAJECTORY_MISSING = "ADM3:trajectory_missing"
ADM4_NO_TRACES = "ADM4:no_traces"
ADM5_MALFORMED_TRACE = "ADM5:malformed_trace"

LP1_LOGPROBS_ABSENT = "LP1:response_logprobs_absent"
LP2_LOGPROBS_LENGTH = "LP2:response_logprobs_length_ne_response_ids"
LP3_SENTINEL_AT_MASK1 = "LP3:sentinel_logprob_at_mask1"
LP4_NONFINITE = "LP4:nonfinite_logprob"
LP5_POSITIVE = "LP5:positive_logprob"
LP6_ZERO_RATE_AT_MASK1 = "LP6:zero_logprob_rate_at_mask1"
LP7_EMPTY_LOSS_MASK = "LP7:empty_loss_mask"
LP8_MASK_LENGTH = "LP8:loss_mask_length_ne_response_ids"
LP9_MASK_DOMAIN = "LP9:loss_mask_value_not_binary"
TR1_FINISH_REASON = "TR1:finish_reason_not_allowed"
TR2_REASONING_LOSS_MASK = "TR2:reasoning_loss_mask_masked_tokens"
TR3_SPLIT_DOMAIN = "TR3:split_not_train_or_eval"

G1_MISSING_SOURCE = "G1:missing_evidence:prompt_source"
G1_MISSING_CARD_HASH = "G1:missing_evidence:skill_card_hash"
G1_NOT_APPROVED = "G1:skill_card_hash_not_approved"
G2_MISSING_SYSTEM_PROMPT = "G2:missing_evidence:system_prompt"
G2_NOT_APPROVED = "G2:system_prompt_hash_not_approved"
G3_MISSING_TOOLS = "G3:missing_evidence:tools"
G3_NOT_APPROVED = "G3:tool_roster_hash_not_approved"
G5_CHECKOUT_MAX_PAGE = "G5:checkout_max_page_ne_timestep"
G5_CHECKOUT_NOT_CONTIGUOUS = "G5:checkout_pages_not_contiguous"
G5_CHECKOUT_POSTURE = "G5:checkout_history_posture"
G5_MISSING_TIMESTEP = "G5:missing_evidence:timestep"
G5_MISSING_WORKSPACE = "G5:missing_evidence:workspace"
G5_SEARCH_PAGE_GT_TIMESTEP = "G5:search_page_gt_timestep"  # the predecessor's constant
G5_WORKSPACE_BRANCH = "G5:workspace_branch_ne_timestep"
G7_CHAINS_TOTAL = "G7:chains_total_ne_1"
G7_CHAINS_TRUNCATED = "G7:chains_truncated"
G7_MERGED = "G7:completions_merged_ne_total"
G7_MISSING_STATS = "G7:missing_evidence:reconstruction_stats"
G7_MISSING_SETTINGS = "G7:missing_evidence:settings"
G7_RAW = "G7:raw_completions_ne_total"
G7_SETTINGS_NOT_APPROVED = "G7:settings_hash_not_approved"
H41_TOOLLESS_ROSTER = "H41:roster_offered_zero_tool_calls"

FINDING_VOCABULARY = (
    ADM1_STATUS_NOT_COMPLETED, ADM2_BUILDER_FINDINGS_PRESENT, ADM3_TRAJECTORY_MISSING,
    ADM4_NO_TRACES, ADM5_MALFORMED_TRACE, G1_MISSING_SOURCE, G1_MISSING_CARD_HASH,
    G1_NOT_APPROVED, G2_MISSING_SYSTEM_PROMPT, G2_NOT_APPROVED,
    G3_MISSING_TOOLS, G3_NOT_APPROVED, G5_CHECKOUT_POSTURE, G5_CHECKOUT_MAX_PAGE,
    G5_CHECKOUT_NOT_CONTIGUOUS, G5_MISSING_TIMESTEP, G5_MISSING_WORKSPACE,
    G5_SEARCH_PAGE_GT_TIMESTEP, G5_WORKSPACE_BRANCH,
    G7_CHAINS_TOTAL, G7_CHAINS_TRUNCATED, G7_MERGED, G7_MISSING_STATS,
    G7_MISSING_SETTINGS, G7_RAW, G7_SETTINGS_NOT_APPROVED, H41_TOOLLESS_ROSTER,
    LP1_LOGPROBS_ABSENT, LP2_LOGPROBS_LENGTH, LP3_SENTINEL_AT_MASK1, LP4_NONFINITE,
    LP5_POSITIVE, LP6_ZERO_RATE_AT_MASK1, LP7_EMPTY_LOSS_MASK, LP8_MASK_LENGTH,
    LP9_MASK_DOMAIN, TR1_FINISH_REASON, TR2_REASONING_LOSS_MASK, TR3_SPLIT_DOMAIN,
)

ALLOWED_FINISH_REASONS = frozenset({"stop", "tool_calls", "stop_sequence", "length"})
# ADR-0015: a tuple, not a frozenset — membership must not hash (wire content
# can be unhashable, and checks never raise on content).
ALLOWED_SPLITS = ("train", "eval")

# The binding compatibility contract (`mcp-service/README.md`; spec §G5).
_PAGE_MEMBER = re.compile(r'"page"\s*:\s*(\d+)')
_PAGE_FILE = re.compile(r"md/page_(\d{4})\.md")
_TIMESTEP_MEMBER = re.compile(r'"timestep"\s*:\s*(\d+)')

# Decisions and built-in reads are cutoff-exempt (spec §G5, ADR-0007(e)).
CUTOFF_SCOPED_TOOLS = frozenset({"mcp_gsj_search_case"})
_CASE_STATUS_TOOL = "mcp_gsj_case_status"


@dataclass(frozen=True)
class CheckPolicy:
    """The platform-conditioned knobs (spec §The logprob discipline —
    sentinel: the vLLM `-9999.0` floor; zero-rate: CP-09's bf16 numbers, a
    CUDA estate sets 0.0). `reject_toolless_roster` arms H-41 (spec §H-41)."""

    sentinel_threshold: float = -9000.0
    zero_at_mask1_max_rate: float = 0.25
    reject_toolless_roster: bool = False


# Rebound by `config.load_config`, resolved at CALL time (ADR-0010).
DEFAULT_POLICY = CheckPolicy()

# The approved sets (spec §The pins…): generated data, never literals here.
PINS_PATH = Path(__file__).resolve().parent.parent / "pins" / "pins.gsj.json"
_pins_cache: Mapping[str, list[str]] | None = None  # process-lifetime; a re-pin needs a restart


class PinsConfigurationError(Exception):
    """Pins are configuration, not content: every way loading them can fail
    is the server's fault, never the caller's (spec §the pins seam)."""


def approved_set(key: str) -> list[str]:
    """The approved hashes for one pin key — raises loudly when unusable."""
    global _pins_cache
    if _pins_cache is None:
        try:
            _pins_cache = json.loads(PINS_PATH.read_text())["pins"]
        except Exception as exc:  # unreadable, corrupt, wrong shape — all ours
            raise PinsConfigurationError(f"pins file {PINS_PATH} unusable: {exc!r}") from exc
    values = _pins_cache.get(key) if isinstance(_pins_cache, Mapping) else None
    # list, not str: `hash in "somestring"` is substring containment — a fail-open
    if not isinstance(values, list) or not values:
        raise PinsConfigurationError(
            f"pins key {key!r} missing, empty, or not a list in {PINS_PATH}"
        )
    return values


def _sha256_text(text: str) -> str | None:
    """Convention 1, UTF-8 text sha256; None = unencodable (finding, not raise)."""
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:  # JSON admits lone surrogates
        return None


def _sha256_canonical_json(obj: Any) -> str | None:
    """Convention 2 — the predecessor's `canonical_json` byte-exact (`store.py:88-91`)."""
    try:
        text = json.dumps(obj, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):  # NaN/Infinity really do arrive off the wire
        return None
    return _sha256_text(text)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_session_result(
    session_result: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """Validate one callback-shaped `SessionResult`; [] means accepted."""
    findings = _admission_findings(session_result)
    trajectory = session_result.get("trajectory")
    if isinstance(trajectory, Mapping):  # else ADM3 already fired
        findings.extend(check_chain_snapshot(_as_mapping(trajectory.get("metadata"))))
    traces = _as_mapping(trajectory).get("traces")
    for trace in traces if isinstance(traces, list) else []:
        if isinstance(trace, Mapping):
            findings.extend(run_trace_checks(trace, policy))
        else:
            findings.append(ADM5_MALFORMED_TRACE)
    return findings


def _admission_findings(session_result: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    status = session_result.get("status")
    if status != ACCEPTED_STATUS:
        findings.append(f"{ADM1_STATUS_NOT_COMPLETED}:{status}")
    trajectory = session_result.get("trajectory")
    if not isinstance(trajectory, Mapping):
        findings.append(ADM3_TRAJECTORY_MISSING)
        return findings
    builder_findings = _as_mapping(
        _as_mapping(trajectory.get("metadata")).get("gsj_validation")
    ).get("findings") or []
    if not isinstance(builder_findings, list):
        builder_findings = [builder_findings]
    if builder_findings:
        findings.append(f"{ADM2_BUILDER_FINDINGS_PRESENT}:{len(builder_findings)}")
        findings.extend(str(finding) for finding in builder_findings)
    traces = trajectory.get("traces")
    if not (isinstance(traces, list) and traces):
        findings.append(ADM4_NO_TRACES)
    return findings


def run_trace_checks(
    trace: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """Every trace-level rule on one trace — law 6's shared seam."""
    return [
        *check_logprob_discipline(trace, policy),
        *check_trace_tripwires(trace),
        *check_page_cutoff(trace),
        *check_workspace(trace),
        *check_tool_roster(trace),
        *check_system_prompt(trace),
        *check_skill_card(trace),
        *check_settings_echo(trace),
        *check_toolless_roster(trace, policy),
    ]


def check_tool_roster(trace: Mapping[str, Any]) -> list[str]:
    """G3 (spec §G3's actual mechanism): canonical-JSON hash of the wire
    `tools` ∈ approved set. CP-05 caveat: a merged trace carries the FIRST
    completion's tools — cross-completion stability is the builder's `R11`."""
    tools = trace.get("tools")
    if not isinstance(tools, list) or not tools:
        return [G3_MISSING_TOOLS]
    digest = _sha256_canonical_json(tools)
    if digest in approved_set("tool_roster_hash"):
        return []
    return [f"{G3_NOT_APPROVED}:{digest or 'unhashable'}"]


def check_system_prompt(trace: Mapping[str, Any]) -> list[str]:
    """G2: sha256 of every wire `system` text ∈ the approved singleton,
    flattened via `_content_text` first (finding (b) is binding — spec)."""
    approved = approved_set("system_prompt_hash")
    findings, seen = [], 0
    for message in _as_list(trace.get("prompt_messages")):
        if isinstance(message, Mapping) and message.get("role") == "system":
            seen += 1
            digest = _sha256_text(_content_text(message))
            if digest not in approved:
                findings.append(f"{G2_NOT_APPROVED}:{digest or 'unhashable'}")
    return findings if seen else [G2_MISSING_SYSTEM_PROMPT]


def check_skill_card(trace: Mapping[str, Any]) -> list[str]:
    """G1 (spec §The gates as landed, CP-13): the stated `prompt_source`
    decides — `skill:<name>`: stated card-bytes hash ∈ `skill_card_hash`;
    `free`: n/a, pass; neither/absent: fail closed. Stated-evidence limit
    recorded in row 9."""
    metadata = _as_mapping(trace.get("metadata"))
    source = metadata.get("prompt_source")
    if source == "free":
        return []
    if isinstance(source, str) and source.startswith("skill:") and source[len("skill:"):].strip():
        card_hash = metadata.get("skill_card_hash")
        if not isinstance(card_hash, str) or not card_hash:
            return [G1_MISSING_CARD_HASH]
        if card_hash in approved_set("skill_card_hash"):
            return []
        return [f"{G1_NOT_APPROVED}:{card_hash[:64]}"]
    return [G1_MISSING_SOURCE]


def check_settings_echo(trace: Mapping[str, Any]) -> list[str]:
    """G7's settings clause (spec §G7's chain snapshot, CP-13): canonical
    hash of the harness-echoed rendered settings ∈ `settings_hash`; a
    missing echo fails closed (row 15's residual, closed)."""
    settings = _as_mapping(trace.get("metadata")).get("gsj_settings")
    if not isinstance(settings, Mapping) or not settings:
        return [G7_MISSING_SETTINGS]
    digest = _sha256_canonical_json(settings)
    if digest in approved_set("settings_hash"):
        return []
    return [f"{G7_SETTINGS_NOT_APPROVED}:{digest or 'unhashable'}"]


_G7_STAT_KEYS = ("chains_total", "chains_reconstructed_truncated",
                 "completions_total", "completions_merged", "raw_completions_total")


def check_chain_snapshot(trajectory_metadata: Mapping[str, Any]) -> list[str]:
    """G7's stats conjunction (spec §G7's chain snapshot; CP-05 tightening).
    The settings-hash clause has no callback evidence — recorded gap, row 15."""
    stats = _as_mapping(trajectory_metadata.get("reconstruction_stats"))
    for key in _G7_STAT_KEYS:  # fail-closed before any comparison
        if isinstance(stats.get(key), bool) or not isinstance(stats.get(key), int):
            return [f"{G7_MISSING_STATS}.{key}" if stats else G7_MISSING_STATS]
    findings = []
    if stats["chains_total"] != 1:
        findings.append(f"{G7_CHAINS_TOTAL}:{stats['chains_total']}")
    if stats["chains_reconstructed_truncated"] != 0:
        findings.append(f"{G7_CHAINS_TRUNCATED}:{stats['chains_reconstructed_truncated']}")
    total = stats["completions_total"]
    if stats["completions_merged"] != total:
        findings.append(f"{G7_MERGED}:{stats['completions_merged']}!={total}")
    if stats["raw_completions_total"] != total:
        findings.append(f"{G7_RAW}:{stats['raw_completions_total']}!={total}")
    return findings


def check_toolless_roster(
    trace: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """H-41 (spec §The H-41 lesson): roster offered, zero parsed tool calls.
    POLICY-GATED, default off — a legitimate episode can call no tools."""
    policy = DEFAULT_POLICY if policy is None else policy
    if not policy.reject_toolless_roster:
        return []
    tools = trace.get("tools")
    if not (isinstance(tools, list) and tools):
        return []  # no roster offered — not this flag's shape (G3's job)
    if any(_as_list(message.get("tool_calls")) for message in _messages(trace)):
        return []
    return [H41_TOOLLESS_ROSTER]


def check_logprob_discipline(
    trace: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """Spec §The logprob discipline (RAW, R-aligned, one finding per rule)."""
    policy = DEFAULT_POLICY if policy is None else policy
    findings: list[str] = []
    response_ids = _as_list(trace.get("response_ids"))
    mask = _as_list(trace.get("loss_mask"))
    logprobs = trace.get("response_logprobs")

    if response_ids and not mask:  # the `models.py:116` validator escape
        findings.append(LP7_EMPTY_LOSS_MASK)
    if mask and len(mask) != len(response_ids):
        findings.append(f"{LP8_MASK_LENGTH}:{len(mask)}!={len(response_ids)}")

    # LP9: the mask is 0/1 ints or it is not evidence (spec §LP9).
    off_domain = [
        index
        for index, flag in enumerate(mask)
        if isinstance(flag, bool) or not isinstance(flag, int) or flag not in (0, 1)
    ]
    if off_domain:
        findings.append(f"{LP9_MASK_DOMAIN}:first={off_domain[0]}:count={len(off_domain)}")

    trainable = [index for index, flag in enumerate(mask) if flag == 1]
    if not isinstance(logprobs, list):
        # a missing trainable slot nulls the whole array upstream (spec §LP1)
        if trainable or (response_ids and not mask):
            findings.append(LP1_LOGPROBS_ABSENT)
        return findings
    if len(logprobs) != len(response_ids):
        findings.append(f"{LP2_LOGPROBS_LENGTH}:{len(logprobs)}!={len(response_ids)}")

    nonfinite: list[int] = []
    positive: list[int] = []
    sentinel: list[int] = []
    zeros = 0
    for index, value in enumerate(logprobs):
        try:
            bad = isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        except OverflowError:  # a JSON int beyond float range is not evidence
            bad = True
        if bad:
            nonfinite.append(index)
            continue
        at_mask1 = index < len(mask) and mask[index] == 1
        if value > 0.0:
            positive.append(index)
        if at_mask1 and value <= policy.sentinel_threshold:
            sentinel.append(index)
        if at_mask1 and value == 0.0:
            zeros += 1
    for finding_id, offenders in (
        (LP3_SENTINEL_AT_MASK1, sentinel),
        (LP4_NONFINITE, nonfinite),
        (LP5_POSITIVE, positive),
    ):
        if offenders:
            findings.append(f"{finding_id}:first={offenders[0]}:count={len(offenders)}")
    if trainable and zeros / len(trainable) > policy.zero_at_mask1_max_rate:
        findings.append(
            f"{LP6_ZERO_RATE_AT_MASK1}:{zeros}/{len(trainable)}>{policy.zero_at_mask1_max_rate}"
        )
    return findings


def check_trace_tripwires(trace: Mapping[str, Any]) -> list[str]:
    """The `finish_reason` allowlist, the re-vendor canary, and the split
    vocabulary (spec §TR1/TR2/TR3). TR3 verifies the submitter's own
    statement — absent is legal (unstated, ADR-0015), a third value is not."""
    findings: list[str] = []
    finish_reason = trace.get("finish_reason")
    if not (isinstance(finish_reason, str) and finish_reason in ALLOWED_FINISH_REASONS):
        findings.append(f"{TR1_FINISH_REASON}:{finish_reason}")
    metadata = _as_mapping(trace.get("metadata"))
    # Presence-based, not None-based: an explicit null is a value the
    # renderer can never produce (None omits the key) — exactly the
    # serializer-mangled shape TR3 exists to flag (spec §The split label).
    if "split" in metadata and metadata["split"] not in ALLOWED_SPLITS:
        findings.append(f"{TR3_SPLIT_DOMAIN}:{metadata['split']}")
    masked = _as_mapping(
        _as_mapping(trace.get("metadata")).get("reasoning_loss_mask")
    ).get("masked_tokens")
    # deliberately not type-narrowed (spec §TR2)
    if masked not in (None, 0, False, "0", ""):
        findings.append(f"{TR2_REASONING_LOSS_MASK}:{masked}")
    return findings


def check_page_cutoff(trace: Mapping[str, Any]) -> list[str]:
    """G5's backstop (spec §G5): no cited search page may exceed T; T from
    the trace only (metadata first, `case_status` fallback), else fail closed."""
    timestep = _episode_timestep(trace)
    if timestep is None:
        return [G5_MISSING_TIMESTEP]
    return [
        f"{G5_SEARCH_PAGE_GT_TIMESTEP}:{page}>{timestep}"
        for page in _case_search_pages(trace)
        if page > timestep
    ]


def check_workspace(trace: Mapping[str, Any]) -> list[str]:
    """G5's checkout census, returned (spec §G5, CP-13a): the harness echoes
    what the sandbox CONTAINED and the branch/max-page clauses cross-check it
    against the trainer's independently-sourced timestep. Detects an honest
    misconfiguration, not a hostile harness — reasoning in the spec."""
    workspace = _as_mapping(trace.get("metadata")).get("gsj_workspace")
    if not isinstance(workspace, Mapping) or not workspace:
        return [G5_MISSING_WORKSPACE]
    findings: list[str] = []
    if not (workspace.get("shallow") is True and workspace.get("remotes") == 0):
        findings.append(f"{G5_CHECKOUT_POSTURE}:shallow={workspace.get('shallow')}"
                        f",remotes={workspace.get('remotes')}")
    pages = _as_mapping(workspace.get("pages"))
    low, high, count = pages.get("min"), pages.get("max"), pages.get("count")
    if not all(isinstance(value, int) and not isinstance(value, bool)
               for value in (low, high, count)):
        return findings + [f"{G5_MISSING_WORKSPACE}.pages"]
    if low != 1 or count != high:  # contiguous from 1 — the predecessor's clause
        findings.append(f"{G5_CHECKOUT_NOT_CONTIGUOUS}:{low}-{high}/{count}")
    timestep = _episode_timestep(trace)
    if timestep is None:  # check_page_cutoff owns that finding; no double-report
        return findings
    if workspace.get("branch") != f"timestep-{timestep}":
        findings.append(f"{G5_WORKSPACE_BRANCH}:{workspace.get('branch')}!=timestep-{timestep}")
    if high != timestep:  # max checkout page == T — the predecessor's clause
        findings.append(f"{G5_CHECKOUT_MAX_PAGE}:{high}!={timestep}")
    return findings


def _episode_timestep(trace: Mapping[str, Any]) -> int | None:
    metadata = _as_mapping(trace.get("metadata"))
    for candidate in (
        metadata.get("timestep"),
        _as_mapping(metadata.get("task_metadata")).get("timestep"),
    ):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return candidate
    for name, text in _tool_results(trace):
        if name == _CASE_STATUS_TOOL:
            match = _TIMESTEP_MEMBER.search(text)
            if match:
                return int(match.group(1))
    return None


def _case_search_pages(trace: Mapping[str, Any]) -> list[int]:
    pages: set[int] = set()
    for name, text in _tool_results(trace):
        # `in` on a frozenset hashes: an unhashable wire name must not raise
        if isinstance(name, str) and name in CUTOFF_SCOPED_TOOLS:
            pages.update(int(page) for page in _PAGE_MEMBER.findall(text))
            pages.update(int(page) for page in _PAGE_FILE.findall(text))
    return sorted(pages)


def _tool_results(trace: Mapping[str, Any]) -> Iterator[tuple[Any, str]]:
    """Every tool result as `(name, text)`, name resolved by id (spec §G5)."""
    names: dict[Any, Any] = {}
    for message in _messages(trace):
        for call in _as_list(message.get("tool_calls")):
            if isinstance(call, Mapping) and isinstance(call.get("id"), (str, int)):
                names[call.get("id")] = _as_mapping(call.get("function")).get("name")
        if message.get("role") == "tool":
            key = message.get("tool_call_id")
            yield names.get(key) if isinstance(key, (str, int)) else None, _content_text(message)


def _messages(trace: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for key in ("prompt_messages", "response_messages"):
        for message in _as_list(trace.get(key)):
            if isinstance(message, Mapping):
                yield message


def _content_text(message: Mapping[str, Any]) -> str:
    """Flatten `content` to text, typed parts included (finding (b), spec)."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts = [content] if isinstance(content, Mapping) else _as_list(content)
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, Mapping) and isinstance(part.get("text"), str):
            texts.append(part["text"])
    return "".join(texts)
