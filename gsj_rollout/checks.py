"""BOTH — trace validators (interface at CP-08; the first rules at CP-10).

The same code runs on both sides of the wire (scope law 6): the receiver
drops bad traces at the source, the trainer re-verifies what it fetched.
One entry point, `validate_session_result`, takes the callback-shaped
`SessionResult` mapping (never the rollout server's on-disk `ses_*.json`,
which strips `trajectory.status`/`error` — CP-07 finding 5) and returns
findings as byte-stable ``{id}:{slug}[:detail]`` strings. An empty list
means accepted; it never raises on content (ADR-0008 §6).

Three layers, all specified in `docs/checks-spec.md` — this module
implements, it does not re-derive:

- **admission** (CP-08, `ADM*`) — honor what the builder already decided;
- **the logprob discipline** (CP-10, `LP*` + the `TR*` tripwires);
- **G5's cutoff backstop** (CP-10) — the page census reconstructed from
  the trace's own tool-result texts.

Gates G1–G4/G6/G7 and the G7 stats conjunction are CP-11's. **No
replay-style rule lives here, deliberately** (CP-09 F2–F4 — it needs an
engine, cannot run on Mac estates, its tolerance anchor does not transfer,
and on a multi-turn trace the check itself could be wrong); the reasoning
is recorded in `docs/checks-spec.md` §Replay.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

ACCEPTED_STATUS = "COMPLETED"

# --- the failure vocabulary: byte-stable, greppable, never reworded ------
# Downstream forensics greps these; a rename is a breaking change, and the
# snapshot test in `tests/test_checks.py` makes it a deliberate one.
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

# Catches tail aborts for free (`finish_reason == "abort"`, D3); mid-chain
# aborts are invisible on the wire at the pin and are patch P2's job.
ALLOWED_FINISH_REASONS = frozenset({"stop", "tool_calls", "stop_sequence", "length"})

# The compatibility contract every backend and `checks.py` share
# (`mcp-service/README.md` §Compatibility requirements; inlined from the
# predecessor's `gates.extract_case_search_pages`). Rename the key or
# reformat the path and the gate goes blind.
_PAGE_MEMBER = re.compile(r'"page"\s*:\s*(\d+)')
_PAGE_FILE = re.compile(r"md/page_(\d{4})\.md")
_TIMESTEP_MEMBER = re.compile(r'"timestep"\s*:\s*(\d+)')

# Only case-search results are cutoff-scoped: the decisions corpus is
# exempt (the predecessor's ADR-0007(e)), and a built-in `read` of
# `md/page_0007.md` cites the checkout, already clamped to `timestep-{T}`.
CUTOFF_SCOPED_TOOLS = frozenset({"mcp_gsj_search_case"})
_CASE_STATUS_TOOL = "mcp_gsj_case_status"


@dataclass(frozen=True)
class CheckPolicy:
    """The two platform-conditioned knobs of the logprob discipline.

    `sentinel_threshold`: any `mask == 1` logprob at or below it fails
    hard. vLLM writes `-9999.0` as both the missing-logprob default and
    its clamp floor — finite, ≤ 0, not `0.0`, so the naive discipline
    admits it (spec corrected at CP-02) and nothing upstream value-checks
    logprobs at all. Accepted false positive: a genuine ultra-low logprob
    clamped to the floor is indistinguishable from a missing one.

    `zero_at_mask1_max_rate`: the suspicious-zero allowance, as a fraction
    of `mask == 1` positions. Polar's `0.0` placeholder can never land at
    `mask == 1` (`prefix_merging.py:364,368` nulls the whole array first),
    so a `0.0` there IS engine-reported — but CP-09 measured it on BOTH
    stacks (golden 20/292 = 6.8%, collected 15/363 = 4.1%) as bf16
    rounding of genuinely-near-zero RAW logprobs (the raw replay
    hypothesis fits at the numerics floor, the renormalized one ~6×
    worse). A hard fail would reject every well-formed MLX trace, so this
    is an allowance instead: 0.25 is ~3.6× the highest measurement — no
    measured trace trips it, a degenerate mostly-zero array still does. A
    CUDA estate restores the original strictness with 0.0.
    """

    sentinel_threshold: float = -9000.0
    zero_at_mask1_max_rate: float = 0.25


DEFAULT_POLICY = CheckPolicy()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_session_result(
    session_result: Mapping[str, Any], policy: CheckPolicy = DEFAULT_POLICY
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
    trace: Mapping[str, Any], policy: CheckPolicy = DEFAULT_POLICY
) -> list[str]:
    """Every trace-level rule, on one trace — the CP-08 seam, now live.

    Both legs of law 6 reach the rules only through here, so they cannot
    drift between receiver and trainer.
    """
    return [
        *check_logprob_discipline(trace, policy),
        *check_trace_tripwires(trace),
        *check_page_cutoff(trace),
    ]


def check_logprob_discipline(
    trace: Mapping[str, Any], policy: CheckPolicy = DEFAULT_POLICY
) -> list[str]:
    """`docs/checks-spec.md` §The logprob discipline, with CP-09's numbers.

    Captured values are RAW model logprobs (CP-09), so no renormalization
    transform appears in this math. The arrays are R-aligned, never P+R.
    Offenders are reported one finding per rule with `first=`/`count=`, so
    a systematically broken array cannot flood the findings list.
    """
    findings: list[str] = []
    response_ids = _as_list(trace.get("response_ids"))
    mask = _as_list(trace.get("loss_mask"))
    logprobs = trace.get("response_logprobs")

    # The pin's `Trace` validator skips the length check when the mask is
    # empty (`models.py:116`), admitting an N-token trace with no mask.
    if response_ids and not mask:
        findings.append(LP7_EMPTY_LOSS_MASK)
    if mask and len(mask) != len(response_ids):
        findings.append(f"{LP8_MASK_LENGTH}:{len(mask)}!={len(response_ids)}")

    # LP9 closes the hole every other mask-keyed rule depends on: `flag == 1`
    # is False for "1", 2, 1.0-as-string and JSON NaN, so an off-domain mask
    # would silently make LP1/LP3/LP6 vacuous — a type change on one field
    # disarming the discipline. The mask is 0/1 ints or it is not evidence.
    off_domain = [
        index
        for index, flag in enumerate(mask)
        if isinstance(flag, bool) or not isinstance(flag, int) or flag not in (0, 1)
    ]
    if off_domain:
        findings.append(f"{LP9_MASK_DOMAIN}:first={off_domain[0]}:count={len(off_domain)}")

    trainable = [index for index, flag in enumerate(mask) if flag == 1]
    if not isinstance(logprobs, list):
        # Any missing trainable slot nulls the ENTIRE array upstream
        # (`prefix_merging.py:364`); upstream's own rejection of that is
        # status-derived, not a config surface (`adapter.py:120,268`).
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
    """The two non-array rules of the same spec section: the
    `finish_reason` allowlist, and the re-vendor canary for
    reasoning-masking (fork-only code today — D4 refuted upstream — so its
    silent arrival in a future re-vendor must be loud)."""
    findings: list[str] = []
    finish_reason = trace.get("finish_reason")
    if finish_reason not in ALLOWED_FINISH_REASONS:
        findings.append(f"{TR1_FINISH_REASON}:{finish_reason}")
    masked = _as_mapping(
        _as_mapping(trace.get("metadata")).get("reasoning_loss_mask")
    ).get("masked_tokens")
    # Deliberately not type-narrowed: this fires on anything that is not a
    # recognized zero. A canary for an UNKNOWN future upstream change must
    # not assume the encoding that change will use.
    if masked not in (None, 0, False, "0", ""):
        findings.append(f"{TR2_REASONING_LOSS_MASK}:{masked}")
    return findings


def check_page_cutoff(trace: Mapping[str, Any]) -> list[str]:
    """G5's trace-side backstop: no cited page may exceed the timestep.

    **A backstop, not the enforcement.** The structural clamp is
    server-side — `mcp-service` filters to `page ≤ T` then ranks, T from
    the episode token's verified claims (CP-07: the tamper probe rejected
    401). This catches a service that misbehaved or a result shape that
    changed under us.

    T comes from the trace, never from a caller — a check that can be told
    what to believe is not a check. Precedence: the trace's own metadata
    (`metadata.timestep`, then `metadata.task_metadata.timestep`), then
    the `mcp_gsj_case_status` result's `timestep`, stated by the service
    from the same verified claims that drive the clamp. The second is
    strictly weaker (a service lying about both T and the pages defeats
    it) and is in use only because nothing puts the timestep into trace
    metadata today — the structural fix is on CP-11's list. Neither source
    ⇒ `G5:missing_evidence:timestep`: evidence never gathered fails its
    owning gate.
    """
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
    """Every tool result as `(tool name, text)`, name resolved by id: the
    name rides the assistant turn that requested the call, the result
    carries only `tool_call_id`. Both message lists are scanned in order,
    so a merged multi-turn trace resolves calls made before the result."""
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
    """Flatten `content` to text, content-part lists included — the CP-10
    investigation's finding (b): the codec template coerces a non-string
    `content` to `''` and pi sends typed parts, so any check that reads or
    re-renders message content without normalizing first validates against
    text that never existed. Live serving is safe (vLLM flattens before
    templating); every offline reader must do this itself. A bare part
    mapping and plain-string list items are accepted too — reading a
    plausible envelope as empty text is exactly how a census goes silently
    blind."""
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
