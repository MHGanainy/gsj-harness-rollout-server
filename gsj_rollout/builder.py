"""SERVER — the validating `PrefixMergingBuilder` subclass (CP-07),
selected through Polar's registry seam, zero vendored edits. Runs the
*session-level* checks the callback cannot carry and rejects via
``status="ERROR"`` (the node only escalates, never clears — CP-05).
Reasoning: `docs/checks-spec.md` §silent-degradation (the S-rows) and
ADR-0007 (the generation-prompt glue stitch this module applies before
grouping — strict extension only; a mis-pin fails closed into split
chains the receiver's ``chains_total == 1`` rejects). Findings are
byte-stable ``{id}:{slug}[:detail]`` strings on
``trajectory.metadata["gsj_validation"]``, never on the reserved
``evaluation`` key. The trace-level gates stay `checks.py`'s (law 6).
"""

from __future__ import annotations

from typing import Any

from polar.trajectory.builder.prefix_merging import PrefixMergingBuilder
from polar.trajectory.builder.record_utils import build_trace_from_completion
from polar.trajectory.models import CompletionRecord, CompletionSession, Trajectory


def _choices(completion: CompletionRecord) -> list[Any]:
    response = completion.response if isinstance(completion.response, dict) else {}
    choices = response.get("choices")
    return choices if isinstance(choices, list) else []


def _has_agent_shape(completion: CompletionRecord) -> bool:
    """The pi-dialect agent-turn shape (A-12, the P1 replacement): system
    message + non-empty tools + bare `stream` + >= 2 messages (CP-06)."""
    request = completion.original_request if completion.original_request else completion.request
    if not isinstance(request, dict):
        return False
    messages = request.get("messages")
    tools = request.get("tools")
    return (
        isinstance(messages, list)
        and len(messages) >= 2
        and any(isinstance(m, dict) and m.get("role") == "system" for m in messages)
        and isinstance(tools, list)
        and bool(tools)
        and "stream" in request
    )


def _set_prompt_ids(record: CompletionRecord, prompt_ids: list[int]) -> None:
    """Patch the surface `build_trace_from_completion` reads first
    (`record_utils.py:136-140`)."""
    choices = _choices(record)
    choice = choices[0] if choices and isinstance(choices[0], dict) else None
    if isinstance(choice, dict) and isinstance(choice.get("input_token_ids"), list):
        choice["input_token_ids"] = prompt_ids
    elif isinstance(choice, dict) and isinstance(choice.get("prompt_token_ids"), list):
        choice["prompt_token_ids"] = prompt_ids
    else:
        record.response["prompt_token_ids"] = prompt_ids


class ValidatingPrefixMergingBuilder(PrefixMergingBuilder):
    """PrefixMergingBuilder + the gsj session-level validation layer."""

    def __init__(
        self,
        *,
        end_of_turn_token_id: int | None = None,
        generation_prompt_glue_ids: list[int] | None = None,
    ) -> None:
        super().__init__(end_of_turn_token_id=end_of_turn_token_id)
        self._glue_ids = list(generation_prompt_glue_ids or [])

    def _stitched_session(self, session: CompletionSession) -> tuple[CompletionSession, int]:
        """The ADR-0007 glue stitch, strict extension only: an identical
        retry (S3) and a non-matching boundary (S4) are left alone."""
        glue = self._glue_ids
        records = [record.model_copy(deep=True) for record in session.completions]
        stitched = 0
        prev_orig: list[int] | None = None
        prev_norm: list[int] | None = None
        for record in records:
            orig = build_trace_from_completion(record).prompt_ids
            norm = orig
            if (
                prev_orig is not None
                and len(orig) > len(prev_orig)
                and prev_orig[-len(glue):] == glue
                and orig[: len(prev_orig) - len(glue)] == prev_orig[: -len(glue)]
            ):
                norm = prev_norm + orig[len(prev_orig) - len(glue):]
                _set_prompt_ids(record, norm)
                stitched += 1
            prev_orig, prev_norm = orig, norm
        return session.model_copy(update={"completions": records}), stitched

    async def build(self, session: CompletionSession) -> Trajectory:
        findings = self._session_findings(session)
        build_session, glue_stitched = (
            self._stitched_session(session) if self._glue_ids else (session, 0)
        )
        trajectory = await super().build(build_session)

        completion_filter = trajectory.metadata.get("completion_filter")
        if isinstance(completion_filter, dict) and completion_filter.get("excluded"):
            findings.append(
                "A12:completion_filter_excluded_nonempty:"
                + ",".join(
                    str(item.get("completion_id")) for item in completion_filter["excluded"]
                )
            )

        trajectory.metadata["gsj_validation"] = {
            "builder": "gsj_rollout.builder:ValidatingPrefixMergingBuilder",
            "findings": findings,
            "glue_stitched": glue_stitched,
        }
        if findings and trajectory.status == "COMPLETED":
            trajectory.status = "ERROR"
            trajectory.error = f"gsj validation failed ({len(findings)} findings)"
        return trajectory

    def _session_findings(self, session: CompletionSession) -> list[str]:
        findings: list[str] = []
        if self._configured_eot_id is None:  # A-15: never rely on auto-detect
            findings.append("A15:end_of_turn_token_id_not_configured")

        completions = session.completions
        rosters: list[Any] = []
        policy_versions: set[Any] = set()
        prev_prompt_ids: list[int] | None = None

        for idx, completion in enumerate(completions):
            cid = completion.completion_id
            trace = build_trace_from_completion(completion)
            if not trace.prompt_ids:  # S1 at source
                findings.append(f"S1:empty_prompt_ids:{cid}")
            if not trace.response_ids:  # S6: partial capture gaps the stream
                findings.append(f"S6:empty_response_ids:{cid}")
            if len(_choices(completion)) != 1:  # S8: choices[0]-only capture
                findings.append(f"S8:choices_len_ne_1:{cid}:{len(_choices(completion))}")
            if prev_prompt_ids is not None and trace.prompt_ids == prev_prompt_ids:
                findings.append(f"S3:duplicate_consecutive_prompt:{cid}")  # retry
            prev_prompt_ids = trace.prompt_ids
            if idx < len(completions) - 1 and trace.finish_reason == "length":
                findings.append(f"S7:mid_chain_finish_length:{cid}")
            if not _has_agent_shape(completion):
                findings.append(f"A12:non_agent_shape:{cid}")
            # Roster stability (row 11): the persisted transformed request IS
            # the wire form for tools (CP-06) — equality, no hash convention
            # duplicated here (G3 proper hashes receiver-side at CP-11).
            rosters.append(completion.request.get("tools") if isinstance(completion.request, dict) else None)
            policy_versions.add(completion.metadata.get("policy_version"))

        if any(roster != rosters[0] for roster in rosters[1:]):
            findings.append("R11:roster_changed_across_completions")
        if len(policy_versions) > 1:  # S9 (A-13)
            findings.append(
                "S9:policy_version_mixed:" + ",".join(sorted(str(v) for v in policy_versions))
            )
        return findings
