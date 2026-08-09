"""BOTH — trace validators. `docs/checks-spec.md` is the specification and
carries ALL reasoning (CP-11 budget migration); this module implements.

One entry point, `validate_session_result`: takes the callback-shaped
`SessionResult` mapping (never the on-disk `ses_*.json` — CP-07 finding 5),
returns byte-stable ``{id}:{slug}[:detail]`` findings, empty = accepted,
never raises on content (ADR-0008 §6). Both legs of law 6 call it. Live:
admission (`ADM*`), the logprob discipline (`LP*`/`TR*`), G5's backstop.
Gates G1–G4/G6/G7 are CP-11b's; replay is deliberately absent (spec
§Replay)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

ACCEPTED_STATUS = "COMPLETED"

# --- the failure vocabulary: byte-stable, greppable, never reworded ------
# (spec §The failure vocabulary; snapshot-tested, a rename is deliberate)
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

G5_MISSING_TIMESTEP = "G5:missing_evidence:timestep"
G5_SEARCH_PAGE_GT_TIMESTEP = "G5:search_page_gt_timestep"  # the predecessor's constant

FINDING_VOCABULARY = (
    ADM1_STATUS_NOT_COMPLETED, ADM2_BUILDER_FINDINGS_PRESENT, ADM3_TRAJECTORY_MISSING,
    ADM4_NO_TRACES, ADM5_MALFORMED_TRACE, G5_MISSING_TIMESTEP, G5_SEARCH_PAGE_GT_TIMESTEP,
    LP1_LOGPROBS_ABSENT, LP2_LOGPROBS_LENGTH, LP3_SENTINEL_AT_MASK1, LP4_NONFINITE,
    LP5_POSITIVE, LP6_ZERO_RATE_AT_MASK1, LP7_EMPTY_LOSS_MASK, LP8_MASK_LENGTH,
    LP9_MASK_DOMAIN, TR1_FINISH_REASON, TR2_REASONING_LOSS_MASK,
)

# Tail aborts fail here; mid-chain aborts are patch P2's job (D3).
ALLOWED_FINISH_REASONS = frozenset({"stop", "tool_calls", "stop_sequence", "length"})

# The binding compatibility contract (`mcp-service/README.md`; spec §G5).
_PAGE_MEMBER = re.compile(r'"page"\s*:\s*(\d+)')
_PAGE_FILE = re.compile(r"md/page_(\d{4})\.md")
_TIMESTEP_MEMBER = re.compile(r'"timestep"\s*:\s*(\d+)')

# Decisions and built-in reads are cutoff-exempt (spec §G5, ADR-0007(e)).
CUTOFF_SCOPED_TOOLS = frozenset({"mcp_gsj_search_case"})
_CASE_STATUS_TOOL = "mcp_gsj_case_status"


@dataclass(frozen=True)
class CheckPolicy:
    """The platform-conditioned knobs of the logprob discipline. Values and
    reasoning: spec §The logprob discipline (sentinel: the vLLM `-9999.0`
    floor; zero-rate: CP-09's bf16 measurements — a CUDA estate sets 0.0)."""

    sentinel_threshold: float = -9000.0
    zero_at_mask1_max_rate: float = 0.25


# Rebound by `config.load_config` from the YAML's `checks:` section and
# resolved at CALL time (spec §The CheckPolicy operator surface).
DEFAULT_POLICY = CheckPolicy()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_session_result(
    session_result: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """Validate one callback-shaped `SessionResult`; [] means accepted."""
    findings = _admission_findings(session_result)
    traces = _as_mapping(session_result.get("trajectory")).get("traces")
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
    ]


def check_logprob_discipline(
    trace: Mapping[str, Any], policy: CheckPolicy | None = None
) -> list[str]:
    """Spec §The logprob discipline (RAW semantics, R-aligned arrays,
    one finding per rule with `first=`/`count=`)."""
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
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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
    """The `finish_reason` allowlist + the re-vendor canary (spec §TR1/TR2)."""
    findings: list[str] = []
    finish_reason = trace.get("finish_reason")
    if finish_reason not in ALLOWED_FINISH_REASONS:
        findings.append(f"{TR1_FINISH_REASON}:{finish_reason}")
    masked = _as_mapping(
        _as_mapping(trace.get("metadata")).get("reasoning_loss_mask")
    ).get("masked_tokens")
    # deliberately not type-narrowed (spec §TR2)
    if masked not in (None, 0, False, "0", ""):
        findings.append(f"{TR2_REASONING_LOSS_MASK}:{masked}")
    return findings


def check_page_cutoff(trace: Mapping[str, Any]) -> list[str]:
    """G5's trace-side backstop (spec §G5's transcript backstop): no cited
    search page may exceed T; T from the trace only, metadata first (the
    CP-11 structural leg), `case_status` fallback, else fail closed."""
    timestep = _episode_timestep(trace)
    if timestep is None:
        return [G5_MISSING_TIMESTEP]
    return [
        f"{G5_SEARCH_PAGE_GT_TIMESTEP}:{page}>{timestep}"
        for page in _case_search_pages(trace)
        if page > timestep
    ]


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
        if name in CUTOFF_SCOPED_TOOLS:
            pages.update(int(page) for page in _PAGE_MEMBER.findall(text))
            pages.update(int(page) for page in _PAGE_FILE.findall(text))
    return sorted(pages)


def _tool_results(trace: Mapping[str, Any]) -> Iterator[tuple[Any, str]]:
    """Every tool result as `(name, text)`, name resolved by
    `tool_call_id` across both message lists in order (spec §G5)."""
    names: dict[Any, Any] = {}
    for message in _messages(trace):
        for call in _as_list(message.get("tool_calls")):
            if isinstance(call, Mapping):
                names[call.get("id")] = _as_mapping(call.get("function")).get("name")
        if message.get("role") == "tool":
            yield names.get(message.get("tool_call_id")), _content_text(message)


def _messages(trace: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for key in ("prompt_messages", "response_messages"):
        for message in _as_list(trace.get(key)):
            if isinstance(message, Mapping):
                yield message


def _content_text(message: Mapping[str, Any]) -> str:
    """Flatten `content` to text, typed parts included — finding (b), spec
    §The template findings: every offline reader normalizes parts first."""
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
