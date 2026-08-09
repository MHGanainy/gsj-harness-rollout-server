"""checks tests: the CP-08 seam contract + the CP-10 rules, fixture-driven.

Every "passes clean" assertion runs against a REAL trace (the CP-09
collected episode, the CP-07 corpus episode, the predecessor's golden
tokens); every "fails" assertion runs against exactly one doctored copy of
one of them, so a rule that fires for the wrong reason is visible.
"""

from __future__ import annotations

import copy

import pytest

import gsj_rollout.checks as checks


# --- CP-08: the seam contract, unchanged ---------------------------------


def test_never_raises_on_malformed_content():
    # ADR-0008 §6: findings, not exceptions — whatever the wire delivers.
    malformed = [
        {},
        {"session_id": "s"},
        {"session_id": "s", "trajectory": "oops"},
        {"session_id": "s", "trajectory": ["not", "a", "mapping"]},
        {"session_id": "s", "trajectory": {"metadata": "junk", "traces": [{}]}},
        {"session_id": "s", "trajectory": {"metadata": {"gsj_validation": "junk"}, "traces": [{}]}},
        {"session_id": "s", "trajectory": {"metadata": {"gsj_validation": {"findings": "F1"}}, "traces": [{}]}},
        {"session_id": "s", "trajectory": {"traces": "oops"}},
        {"session_id": "s", "trajectory": {"traces": [None, "junk"]}},
        {"status": "COMPLETED", "trajectory": {"traces": [{}, 42]}},
        # CP-10 shapes: junk where the rules read arrays and messages.
        {"status": "COMPLETED", "trajectory": {"traces": [{
            "response_ids": "nope", "loss_mask": {"a": 1}, "response_logprobs": 7,
            "finish_reason": None, "metadata": "junk",
            "response_messages": [None, {"role": "tool", "content": {"text": "x"}}],
        }]}},
        {"status": "COMPLETED", "trajectory": {"traces": [{
            "response_ids": [1], "loss_mask": [1], "response_logprobs": ["-0.5"],
            "finish_reason": "stop", "metadata": {"timestep": 12},
        }]}},
        # CP-11b verification shapes: JSON-legal values that once RAISED —
        # a big-int logprob (OverflowError at isfinite), an unhashable
        # tool_call id / tool_call_id, a non-string finish_reason.
        {"status": "COMPLETED", "trajectory": {"metadata": {}, "traces": [{
            "response_ids": [1, 2, 3], "loss_mask": [1, 0, 1],
            "response_logprobs": [-0.5, 10**400, 0.0], "finish_reason": ["stop"],
            "metadata": {"timestep": 12},
            "response_messages": [
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": [1, 2], "function": {"name": "mcp_gsj_search_case"}}]},
                {"role": "tool", "tool_call_id": {"k": 1}, "content": '{"page": 18}'},
            ],
        }]}},
    ]
    for body in malformed:
        findings = checks.validate_session_result(body)
        assert isinstance(findings, list) and findings, f"must reject, not accept: {body!r}"


def test_admission_vocabulary(callback_body):
    assert checks.validate_session_result(callback_body) == []

    errored = copy.deepcopy(callback_body)
    errored["status"] = "TIMEOUT"
    assert "ADM1:status_not_completed:TIMEOUT" in checks.validate_session_result(errored)

    no_traces = copy.deepcopy(callback_body)
    no_traces["trajectory"]["traces"] = []
    assert "ADM4:no_traces" in checks.validate_session_result(no_traces)

    non_list_findings = copy.deepcopy(callback_body)
    non_list_findings["trajectory"]["metadata"]["gsj_validation"]["findings"] = "S1:oops"
    result = checks.validate_session_result(non_list_findings)
    assert "ADM2:builder_findings_present:1" in result and "S1:oops" in result


def test_run_trace_checks_seam_is_wired(callback_body, monkeypatch):
    monkeypatch.setattr(checks, "run_trace_checks", lambda trace, policy=None: ["G7:stub_finding"])
    assert checks.validate_session_result(callback_body) == ["G7:stub_finding"]


# --- CP-10: the real traces pass clean -----------------------------------


def test_cp09_collected_trace_passes_clean(fidelity_trace):
    """The whole point of the platform-conditioning decision: this trace
    carries 15 exact-`0.0` logprobs at mask==1 and must NOT be rejected."""
    logprobs, mask = fidelity_trace["response_logprobs"], fidelity_trace["loss_mask"]
    zeros = sum(1 for lp, m in zip(logprobs, mask) if m == 1 and lp == 0.0)
    assert (zeros, sum(mask)) == (15, 363), "fixture drifted from the CP-09 measurement"
    assert checks.run_trace_checks(fidelity_trace) == []


def test_cp07_corpus_trace_passes_clean(callback_body):
    trace = callback_body["trajectory"]["traces"][0]
    zeros = sum(1 for lp, m in zip(trace["response_logprobs"], trace["loss_mask"]) if m == 1 and lp == 0.0)
    assert (zeros, sum(trace["loss_mask"])) == (27, 441)
    assert checks.run_trace_checks(trace) == []


def test_golden_tokens_pass_the_same_rules(golden_trace):
    """The predecessor's own golden record, through the structural
    mapping: 20/292 exact-`0.0` at mask==1 (MANIFEST's logprob caveat) —
    the rule as originally specced would have rejected it. The mapping
    carries no wire evidence (no `tools`, no `prompt_messages`), so as of
    CP-11b the hash gates fail closed on it — the posture, proven on a
    real artifact — while the discipline itself stays clean."""
    zeros = sum(1 for lp, m in zip(golden_trace["response_logprobs"], golden_trace["loss_mask"]) if m == 1 and lp == 0.0)
    assert (zeros, sum(golden_trace["loss_mask"]), len(golden_trace["response_ids"])) == (20, 292, 3747)
    assert checks.check_logprob_discipline(golden_trace) == []
    assert checks.run_trace_checks(golden_trace) == [
        "G3:missing_evidence:tools", "G2:missing_evidence:system_prompt"]


def test_suspicious_zero_rule_is_configurable_not_absent(fidelity_trace):
    """Platform-conditioned, not dropped: a CUDA estate can restore the
    original strictness, and a mostly-zero array fails at any setting."""
    strict = checks.CheckPolicy(zero_at_mask1_max_rate=0.0)
    assert checks.check_logprob_discipline(fidelity_trace, strict) == [
        "LP6:zero_logprob_rate_at_mask1:15/363>0.0"
    ]

    degenerate = _doctor(fidelity_trace, lambda t: t.update(
        response_logprobs=[0.0] * len(t["response_logprobs"])
    ))
    findings = checks.check_logprob_discipline(degenerate)
    assert findings == ["LP6:zero_logprob_rate_at_mask1:363/363>0.25"]


# --- CP-10: one doctored trace per rule ----------------------------------


def _doctor(trace, mutate):
    doctored = copy.deepcopy(dict(trace))
    mutate(doctored)
    return doctored


def _set(index, value):
    def mutate(trace):
        trace["response_logprobs"][index] = value
    return mutate


@pytest.mark.parametrize(
    "mutate, expected",
    [
        # the vLLM sentinel: finite, <= 0, not 0.0 — the naive discipline admits it
        (_set(0, -9999.0), "LP3:sentinel_logprob_at_mask1:first=0:count=1"),
        (_set(0, float("nan")), "LP4:nonfinite_logprob:first=0:count=1"),
        (_set(0, float("-inf")), "LP4:nonfinite_logprob:first=0:count=1"),
        (_set(1, 0.5), "LP5:positive_logprob:first=1:count=1"),
        (lambda t: t.update(response_logprobs=None), "LP1:response_logprobs_absent"),
        (lambda t: t.update(response_logprobs=t["response_logprobs"][:-1]),
         "LP2:response_logprobs_length_ne_response_ids:3789!=3790"),
        (lambda t: t.update(loss_mask=[]), "LP7:empty_loss_mask"),
        (lambda t: t.update(loss_mask=t["loss_mask"][:-1]),
         "LP8:loss_mask_length_ne_response_ids:3789!=3790"),
        (lambda t: t.update(finish_reason="abort"), "TR1:finish_reason_not_allowed:abort"),
        (lambda t: t["metadata"].update(reasoning_loss_mask={"masked_tokens": 12}),
         "TR2:reasoning_loss_mask_masked_tokens:12"),
    ],
)
def test_one_doctored_trace_per_rule(fidelity_trace, mutate, expected):
    # equality, not membership: a rule that co-fires with another is a rule
    # firing for a reason the doctoring did not create.
    assert checks.run_trace_checks(_doctor(fidelity_trace, mutate)) == [expected]


def test_off_domain_loss_mask_cannot_disarm_the_discipline(fidelity_trace):
    """LP9. Every other mask-keyed rule tests `flag == 1`, which is False
    for "1", 2, and JSON NaN — so without a domain rule a single field's
    type change silently makes LP1/LP3/LP6 vacuous while the trace is
    accepted. Found by the CP-10 adversarial pass, fixed here."""
    expected = f"LP9:loss_mask_value_not_binary:first=0:count={len(fidelity_trace['loss_mask'])}"
    for bad in ("1", 2, float("nan"), None):
        stringly = _doctor(fidelity_trace, lambda t, bad=bad: t.update(
            loss_mask=[bad] * len(t["loss_mask"]),
            response_logprobs=[-9999.0] * len(t["response_logprobs"]),
        ))
        assert checks.run_trace_checks(stringly) == [expected], bad
    # `True == 1` in Python, so a bool mask still reaches the sentinel rule:
    # LP9 rejects the mask AND LP3 sees the values — both firing is correct.
    boolean = _doctor(fidelity_trace, lambda t: t.update(
        loss_mask=[True] * len(t["loss_mask"]),
        response_logprobs=[-9999.0] * len(t["response_logprobs"])))
    assert checks.run_trace_checks(boolean) == [
        expected, "LP3:sentinel_logprob_at_mask1:first=0:count=3790"]

    # and the same mask with the logprobs simply absent
    absent = _doctor(fidelity_trace, lambda t: t.update(
        loss_mask=["1"] * len(t["loss_mask"]), response_logprobs=None))
    assert "LP9:loss_mask_value_not_binary:first=0:count=3790" in checks.run_trace_checks(absent)


def test_revendor_canary_is_not_type_narrowed(fidelity_trace):
    """TR2 exists to make an UNKNOWN future upstream change loud, so it
    must not assume the encoding that change will use."""
    for masked in (12, 3.0, "3", [1]):
        doctored = _doctor(fidelity_trace, lambda t, m=masked: t["metadata"].update(
            reasoning_loss_mask={"masked_tokens": m}))
        assert checks.run_trace_checks(doctored) == [
            f"TR2:reasoning_loss_mask_masked_tokens:{masked}"
        ]
    for quiet in (0, "0", None):
        doctored = _doctor(fidelity_trace, lambda t, q=quiet: t["metadata"].update(
            reasoning_loss_mask={"masked_tokens": q}))
        assert checks.run_trace_checks(doctored) == []


def test_sentinel_at_mask0_is_not_a_finding(fidelity_trace):
    """The sentinel rule is a mask==1 rule: interstitial positions are
    Polar's placeholders and carry no engine claim."""
    mask0 = fidelity_trace["loss_mask"].index(0)
    findings = checks.run_trace_checks(_doctor(fidelity_trace, _set(mask0, -9999.0)))
    assert findings == []


# --- CP-10: G5, the cutoff ------------------------------------------------


def _tool_result(trace, name, text, call_id="doctored-1"):
    """Append a tool call + its result, the shape pi produces."""
    trace["response_messages"] = list(trace["response_messages"]) + [
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": call_id, "function": {"name": name}}]},
        {"role": "tool", "tool_call_id": call_id, "content": text},
    ]


def test_search_case_page_beyond_the_timestep_fails(fidelity_trace):
    hit = '{"page": 18, "file": "md/page_0018.md", "text": "..."}'
    doctored = _doctor(fidelity_trace, lambda t: _tool_result(t, "mcp_gsj_search_case", hit))
    assert checks.run_trace_checks(doctored) == ["G5:search_page_gt_timestep:18>12"]


def test_decisions_results_are_cutoff_exempt(fidelity_trace):
    """ADR-0007(e) of the predecessor: the decisions corpus is not
    page-scoped, so a high page number there must NOT fail."""
    hit = '{"decision_id": "D-2020-BGH-C-1", "page": 18, "file": "md/page_0018.md"}'
    doctored = _doctor(fidelity_trace, lambda t: _tool_result(t, "mcp_gsj_search_decisions", hit))
    assert checks.run_trace_checks(doctored) == []


def test_census_reads_both_regexes_and_only_search_case(fidelity_trace):
    assert checks._case_search_pages(fidelity_trace) == [1, 5, 7, 9, 11]
    by_path = _doctor(fidelity_trace, lambda t: _tool_result(
        t, "mcp_gsj_search_case", "see md/page_0013.md for the rest"))
    assert 13 in checks._case_search_pages(by_path)
    # a built-in `read` of a checkout page is not a search result
    by_read = _doctor(fidelity_trace, lambda t: _tool_result(t, "read", "md/page_0018.md"))
    assert checks._case_search_pages(by_read) == [1, 5, 7, 9, 11]


def test_timestep_comes_from_the_trace_and_metadata_wins(fidelity_trace):
    # the collected trace has no timestep in metadata: the service's own
    # case_status statement is the fallback (CP-09 episode: timestep 12)
    assert checks._episode_timestep(fidelity_trace) == 12
    from_metadata = _doctor(fidelity_trace, lambda t: t["metadata"].update(timestep=5))
    assert checks._episode_timestep(from_metadata) == 5
    assert "G5:search_page_gt_timestep:7>5" in checks.run_trace_checks(from_metadata)


def test_no_timestep_anywhere_fails_closed(fidelity_trace):
    """An episode that never called `case_status` and whose metadata does
    not carry the timestep has no in-trace T — the gate fails closed
    rather than assuming one. The cure is structural (CP-11: put the
    timestep in the submitted task metadata), not a default."""
    def strip_case_status(trace):
        ids = {call["id"]
               for message in trace["response_messages"]
               for call in (message.get("tool_calls") or [])
               if call["function"]["name"] == "mcp_gsj_case_status"}
        assert ids, "fixture drifted: the CP-09 episode called case_status"
        for message in trace["response_messages"]:
            message["tool_calls"] = [call for call in (message.get("tool_calls") or [])
                                     if call["id"] not in ids]
        trace["response_messages"] = [m for m in trace["response_messages"]
                                      if m.get("tool_call_id") not in ids]

    assert checks.run_trace_checks(_doctor(fidelity_trace, strip_case_status)) == [
        "G5:missing_evidence:timestep"
    ]


@pytest.mark.parametrize("content", [
    [{"type": "text", "text": '{"page": 18}'}],   # pi's typed-parts shape
    {"type": "text", "text": '{"page": 18}'},     # a bare part mapping
    ['{"page": 18}'],                              # a list of plain strings
    '{"page": 18}',                                # the plain-string shape
])
def test_content_parts_are_normalized_before_matching(fidelity_trace, content):
    """Finding (b): a typed-parts `content` must not read as empty. Reading
    a plausible envelope as empty text is how a census goes silently
    blind, so the flattener accepts every shape it can recognize."""
    doctored = _doctor(fidelity_trace,
                       lambda t: _tool_result(t, "mcp_gsj_search_case", content))
    assert checks.run_trace_checks(doctored) == ["G5:search_page_gt_timestep:18>12"]


# --- CP-10: the vocabulary is a contract ---------------------------------


def test_failure_vocabulary_snapshot():
    """A slug rename is a breaking change for downstream forensics, which
    greps these strings. Changing this snapshot is that decision, made
    deliberately."""
    assert checks.FINDING_VOCABULARY == (
        "ADM1:status_not_completed",
        "ADM2:builder_findings_present",
        "ADM3:trajectory_missing",
        "ADM4:no_traces",
        "ADM5:malformed_trace",
        "G2:missing_evidence:system_prompt",
        "G2:system_prompt_hash_not_approved",
        "G3:missing_evidence:tools",
        "G3:tool_roster_hash_not_approved",
        "G5:missing_evidence:timestep",
        "G5:search_page_gt_timestep",
        "G7:chains_total_ne_1",
        "G7:chains_truncated",
        "G7:completions_merged_ne_total",
        "G7:missing_evidence:reconstruction_stats",
        "G7:raw_completions_ne_total",
        "H41:roster_offered_zero_tool_calls",
        "LP1:response_logprobs_absent",
        "LP2:response_logprobs_length_ne_response_ids",
        "LP3:sentinel_logprob_at_mask1",
        "LP4:nonfinite_logprob",
        "LP5:positive_logprob",
        "LP6:zero_logprob_rate_at_mask1",
        "LP7:empty_loss_mask",
        "LP8:loss_mask_length_ne_response_ids",
        "LP9:loss_mask_value_not_binary",
        "TR1:finish_reason_not_allowed",
        "TR2:reasoning_loss_mask_masked_tokens",
    )
    assert tuple(sorted(checks.FINDING_VOCABULARY)) == checks.FINDING_VOCABULARY
    assert checks.ALLOWED_FINISH_REASONS == {"stop", "tool_calls", "stop_sequence", "length"}


def test_every_emitted_finding_starts_with_a_vocabulary_entry(fidelity_trace):
    """Details vary; the `{id}:{slug}` prefix does not."""
    broken = _doctor(fidelity_trace, lambda t: t.update(
        response_logprobs=[1.0, float("nan")] + [-9999.0] * (len(t["response_ids"]) - 2),
        finish_reason="abort",
        metadata={"reasoning_loss_mask": {"masked_tokens": 3}},
    ))
    findings = checks.validate_session_result(
        {"status": "ERROR", "trajectory": {"metadata": {}, "traces": [broken]}}
    )
    assert len(findings) >= 6
    for finding in findings:
        assert any(finding.startswith(entry) for entry in checks.FINDING_VOCABULARY), finding


# --- CP-11b: the gates against the approved sets --------------------------


def _independent_canonical_sha256(obj):
    """The convention, reimplemented here rather than imported, so a drift
    in `checks._sha256_canonical_json` fails a test instead of hiding."""
    import hashlib
    import json

    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def test_gates_pass_clean_on_both_real_episodes(callback_body, fidelity_callback):
    """The first-episode-validate leg (row 23): the approved sets admit
    both known-good episodes — CP-07's and CP-09's — through the whole
    seam, gates included."""
    assert checks.validate_session_result(callback_body) == []
    assert checks.validate_session_result(fidelity_callback) == []


def test_g3_fails_on_a_doctored_roster(fidelity_trace):
    doctored = _doctor(fidelity_trace,
                       lambda t: t["tools"][0]["function"].update(name="doctored"))
    expected = _independent_canonical_sha256(doctored["tools"])
    assert checks.run_trace_checks(doctored) == [
        f"G3:tool_roster_hash_not_approved:{expected}"]


def test_g3_missing_roster_fails_closed(fidelity_trace):
    doctored = _doctor(fidelity_trace, lambda t: t.pop("tools"))
    assert checks.run_trace_checks(doctored) == ["G3:missing_evidence:tools"]


def test_g2_fails_on_a_doctored_system_prompt(fidelity_trace):
    doctored = _doctor(fidelity_trace, lambda t: t["prompt_messages"][0].update(
        content=t["prompt_messages"][0]["content"] + " "))
    findings = checks.run_trace_checks(doctored)
    assert len(findings) == 1 and findings[0].startswith(
        "G2:system_prompt_hash_not_approved:")


def test_g2_missing_system_prompt_fails_closed(fidelity_trace):
    doctored = _doctor(fidelity_trace, lambda t: t.update(
        prompt_messages=[m for m in t["prompt_messages"] if m["role"] != "system"]))
    assert checks.run_trace_checks(doctored) == ["G2:missing_evidence:system_prompt"]


def test_g2_typed_parts_carry_the_same_prompt(fidelity_trace):
    """Finding (b) is binding on G2: the same wire prompt re-enveloped as
    content parts is the SAME prompt and must pass — a raw `content` read
    would hash '' (a prompt that never existed) and reject it."""
    reenveloped = _doctor(fidelity_trace, lambda t: t["prompt_messages"][0].update(
        content=[{"type": "text", "text": t["prompt_messages"][0]["content"]}]))
    assert checks.run_trace_checks(reenveloped) == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        ({"chains_total": 2}, "G7:chains_total_ne_1:2"),          # S1/S4: split chains
        ({"chains_reconstructed_truncated": 1}, "G7:chains_truncated:1"),  # S2/S3
        ({"completions_merged": 1}, "G7:completions_merged_ne_total:1!=2"),  # filter amputation
        ({"raw_completions_total": 3}, "G7:raw_completions_ne_total:3!=2"),  # A-12 drops
    ],
)
def test_g7_each_clause_fires_for_its_own_reason(callback_body, mutate, expected):
    doctored = copy.deepcopy(callback_body)
    doctored["trajectory"]["metadata"]["reconstruction_stats"].update(mutate)
    assert checks.validate_session_result(doctored) == [expected]


def test_g7_missing_stats_fail_closed(callback_body):
    absent = copy.deepcopy(callback_body)
    del absent["trajectory"]["metadata"]["reconstruction_stats"]
    assert checks.validate_session_result(absent) == [
        "G7:missing_evidence:reconstruction_stats"]
    partial = copy.deepcopy(callback_body)
    del partial["trajectory"]["metadata"]["reconstruction_stats"]["chains_total"]
    assert checks.validate_session_result(partial) == [
        "G7:missing_evidence:reconstruction_stats.chains_total"]


def test_h41_flag_is_policy_gated_and_fires_for_its_own_reason(fidelity_trace):
    armed = checks.CheckPolicy(reject_toolless_roster=True)
    # the real episode calls tools: armed stays clean
    assert checks.run_trace_checks(fidelity_trace, armed) == []
    # strip every tool interaction; keep T in metadata so G5 stays satisfied
    toolless = _doctor(fidelity_trace, lambda t: (
        t["metadata"].update(timestep=12),
        t.update(response_messages=[
            m for m in t["response_messages"]
            if m.get("role") != "tool" and not m.get("tool_calls")]),
    ))
    assert checks.run_trace_checks(toolless) == []  # default policy: visible, not fatal
    assert checks.run_trace_checks(toolless, armed) == [
        "H41:roster_offered_zero_tool_calls"]
    # no roster offered is G3's shape, never H41's
    no_roster = _doctor(toolless, lambda t: t.pop("tools"))
    assert checks.run_trace_checks(no_roster, armed) == ["G3:missing_evidence:tools"]


def test_pins_are_loaded_not_inlined_and_raise_loudly(monkeypatch):
    """Spec §The pins: a missing pins key RAISES — the gates never fail
    open — and no hash literal lives in `checks.py`."""
    trace = {"tools": [{"a": 1}],
             "prompt_messages": [{"role": "system", "content": "s"}]}
    monkeypatch.setattr(checks, "_pins_cache", {"system_prompt_hash": ["x"]})
    with pytest.raises(KeyError, match="tool_roster_hash"):
        checks.check_tool_roster(trace)
    monkeypatch.setattr(checks, "_pins_cache", {"system_prompt_hash": []})
    with pytest.raises(KeyError, match="system_prompt_hash"):
        checks.check_system_prompt(trace)
    import inspect
    import json
    for value in json.loads(checks.PINS_PATH.read_text())["pins"].values():
        for pinned in value if isinstance(value, list) else [value]:
            assert pinned not in inspect.getsource(checks)


def test_unhashable_content_is_a_finding_not_a_raise(fidelity_trace):
    """JSON admits NaN and lone surrogates; the canonical convention
    (`allow_nan=False`) and UTF-8 must yield findings, not exceptions."""
    nan_roster = _doctor(fidelity_trace, lambda t: t["tools"][0].update(x=float("nan")))
    assert checks.run_trace_checks(nan_roster) == [
        "G3:tool_roster_hash_not_approved:unhashable"]
    surrogate = _doctor(fidelity_trace,
                        lambda t: t["prompt_messages"][0].update(content="\ud800"))
    assert checks.run_trace_checks(surrogate) == [
        "G2:system_prompt_hash_not_approved:unhashable"]
