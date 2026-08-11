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
        # CP-13 verification shape: an UNHASHABLE tool-call `function.name`.
        # `name in CUTOFF_SCOPED_TOOLS` hashes, so a dict/list name raised
        # TypeError out of the census — the CP-11b corpus covered the
        # unhashable `id` and `tool_call_id` but not the name.
        {"status": "COMPLETED", "trajectory": {"metadata": {}, "traces": [{
            "response_ids": [1], "loss_mask": [1], "response_logprobs": [-0.5],
            "finish_reason": "stop", "metadata": {"timestep": 12},
            "response_messages": [
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "c1", "function": {"name": {"oops": 1}}},
                                {"id": "c2", "function": {"name": ["oops"]}}]},
                {"role": "tool", "tool_call_id": "c1", "content": '{"page": 18}'},
            ],
        }]}},
    ]
    for body in malformed:
        findings = checks.validate_session_result(body)
        assert isinstance(findings, list) and findings, f"must reject, not accept: {body!r}"


def test_admission_vocabulary(body13):
    assert checks.validate_session_result(body13) == []

    errored = copy.deepcopy(body13)
    errored["status"] = "TIMEOUT"
    assert "ADM1:status_not_completed:TIMEOUT" in checks.validate_session_result(errored)

    no_traces = copy.deepcopy(body13)
    no_traces["trajectory"]["traces"] = []
    assert "ADM4:no_traces" in checks.validate_session_result(no_traces)

    non_list_findings = copy.deepcopy(body13)
    non_list_findings["trajectory"]["metadata"]["gsj_validation"]["findings"] = "S1:oops"
    result = checks.validate_session_result(non_list_findings)
    assert "ADM2:builder_findings_present:1" in result and "S1:oops" in result


def test_run_trace_checks_seam_is_wired(callback_body, monkeypatch):
    monkeypatch.setattr(checks, "run_trace_checks", lambda trace, policy=None: ["G7:stub_finding"])
    assert checks.validate_session_result(callback_body) == ["G7:stub_finding"]


# --- CP-10: the real traces pass clean -----------------------------------


def test_cp09_collected_trace_passes_clean(trace13):
    """The whole point of the platform-conditioning decision: this trace
    carries 15 exact-`0.0` logprobs at mask==1 and must NOT be rejected."""
    logprobs, mask = trace13["response_logprobs"], trace13["loss_mask"]
    zeros = sum(1 for lp, m in zip(logprobs, mask) if m == 1 and lp == 0.0)
    assert (zeros, sum(mask)) == (15, 363), "fixture drifted from the CP-09 measurement"
    assert checks.run_trace_checks(trace13) == []


def test_cp07_corpus_trace_passes_clean(body13):
    trace = body13["trajectory"]["traces"][0]
    zeros = sum(1 for lp, m in zip(trace["response_logprobs"], trace["loss_mask"]) if m == 1 and lp == 0.0)
    assert (zeros, sum(trace["loss_mask"])) == (27, 441)
    assert checks.run_trace_checks(trace) == []


def test_fixture_era_bodies_fail_closed_on_the_cp13_statements(
    callback_body, fidelity_callback, fidelity_trace
):
    """CP-13/13a landed three fail-closed gates whose evidence (the stated
    `prompt_source`, the settings echo, the workspace echo) no pre-CP-13
    artifact carries: the raw bodies, verbatim, now earn exactly those
    findings — the golden-mapping precedent (honest fail-closed on
    evidence-less artifacts), not a grandfather clause."""
    expected = ["G5:missing_evidence:workspace",
                "G1:missing_evidence:prompt_source", "G7:missing_evidence:settings"]
    assert checks.run_trace_checks(fidelity_trace) == expected
    assert checks.validate_session_result(callback_body) == expected
    assert checks.validate_session_result(fidelity_callback) == expected


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
        "G5:missing_evidence:workspace", "G3:missing_evidence:tools",
        "G2:missing_evidence:system_prompt",
        "G1:missing_evidence:prompt_source", "G7:missing_evidence:settings"]


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
def test_one_doctored_trace_per_rule(trace13, mutate, expected):
    # equality, not membership: a rule that co-fires with another is a rule
    # firing for a reason the doctoring did not create.
    assert checks.run_trace_checks(_doctor(trace13, mutate)) == [expected]


def test_off_domain_loss_mask_cannot_disarm_the_discipline(trace13):
    """LP9. Every other mask-keyed rule tests `flag == 1`, which is False
    for "1", 2, and JSON NaN — so without a domain rule a single field's
    type change silently makes LP1/LP3/LP6 vacuous while the trace is
    accepted. Found by the CP-10 adversarial pass, fixed here."""
    expected = f"LP9:loss_mask_value_not_binary:first=0:count={len(trace13['loss_mask'])}"
    for bad in ("1", 2, float("nan"), None):
        stringly = _doctor(trace13, lambda t, bad=bad: t.update(
            loss_mask=[bad] * len(t["loss_mask"]),
            response_logprobs=[-9999.0] * len(t["response_logprobs"]),
        ))
        assert checks.run_trace_checks(stringly) == [expected], bad
    # `True == 1` in Python, so a bool mask still reaches the sentinel rule:
    # LP9 rejects the mask AND LP3 sees the values — both firing is correct.
    boolean = _doctor(trace13, lambda t: t.update(
        loss_mask=[True] * len(t["loss_mask"]),
        response_logprobs=[-9999.0] * len(t["response_logprobs"])))
    assert checks.run_trace_checks(boolean) == [
        expected, "LP3:sentinel_logprob_at_mask1:first=0:count=3790"]

    # and the same mask with the logprobs simply absent
    absent = _doctor(trace13, lambda t: t.update(
        loss_mask=["1"] * len(t["loss_mask"]), response_logprobs=None))
    assert "LP9:loss_mask_value_not_binary:first=0:count=3790" in checks.run_trace_checks(absent)


def test_revendor_canary_is_not_type_narrowed(trace13):
    """TR2 exists to make an UNKNOWN future upstream change loud, so it
    must not assume the encoding that change will use."""
    for masked in (12, 3.0, "3", [1]):
        doctored = _doctor(trace13, lambda t, m=masked: t["metadata"].update(
            reasoning_loss_mask={"masked_tokens": m}))
        assert checks.run_trace_checks(doctored) == [
            f"TR2:reasoning_loss_mask_masked_tokens:{masked}"
        ]
    for quiet in (0, "0", None):
        doctored = _doctor(trace13, lambda t, q=quiet: t["metadata"].update(
            reasoning_loss_mask={"masked_tokens": q}))
        assert checks.run_trace_checks(doctored) == []


def test_split_label_tripwire_rejects_only_a_third_value(trace13):
    """TR3 (CP-14, ADR-0015): the split label is the submitter's OWN
    statement — absent is legal (unstated: the frozen cli path, every
    pre-CP-14 trace), but a stated value outside {train, eval} is
    rejected, so no de facto third split arrives through the metadata
    channel unnoticed."""
    assert "split" not in trace13["metadata"]  # absent = unstated: clean
    assert checks.run_trace_checks(trace13) == []
    for good in ("train", "eval"):
        doctored = _doctor(trace13, lambda t, g=good: t["metadata"].update(split=g))
        assert checks.run_trace_checks(doctored) == []
    # None included: an explicit null is present-but-outside-vocabulary —
    # the renderer can never produce it (None omits the key), so it is
    # exactly the serializer-mangled shape TR3 exists to flag.
    for bad in ("test", "TRAIN", "", 1, True, ["train"], None):
        doctored = _doctor(trace13, lambda t, b=bad: t["metadata"].update(split=b))
        assert checks.run_trace_checks(doctored) == [
            f"TR3:split_not_train_or_eval:{bad}"
        ]


def test_sentinel_at_mask0_is_not_a_finding(trace13):
    """The sentinel rule is a mask==1 rule: interstitial positions are
    Polar's placeholders and carry no engine claim."""
    mask0 = trace13["loss_mask"].index(0)
    findings = checks.run_trace_checks(_doctor(trace13, _set(mask0, -9999.0)))
    assert findings == []


# --- CP-10: G5, the cutoff ------------------------------------------------


def _tool_result(trace, name, text, call_id="doctored-1"):
    """Append a tool call + its result, the shape pi produces."""
    trace["response_messages"] = list(trace["response_messages"]) + [
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": call_id, "function": {"name": name}}]},
        {"role": "tool", "tool_call_id": call_id, "content": text},
    ]


def test_search_case_page_beyond_the_timestep_fails(trace13):
    hit = '{"page": 18, "file": "md/page_0018.md", "text": "..."}'
    doctored = _doctor(trace13, lambda t: _tool_result(t, "mcp_gsj_search_case", hit))
    assert checks.run_trace_checks(doctored) == ["G5:search_page_gt_timestep:18>12"]


def test_decisions_results_are_cutoff_exempt(trace13):
    """ADR-0007(e) of the predecessor: the decisions corpus is not
    page-scoped, so a high page number there must NOT fail."""
    hit = '{"decision_id": "D-2020-BGH-C-1", "page": 18, "file": "md/page_0018.md"}'
    doctored = _doctor(trace13, lambda t: _tool_result(t, "mcp_gsj_search_decisions", hit))
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


def test_no_timestep_anywhere_fails_closed(trace13):
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

    assert checks.run_trace_checks(_doctor(trace13, strip_case_status)) == [
        "G5:missing_evidence:timestep"
    ]


@pytest.mark.parametrize("content", [
    [{"type": "text", "text": '{"page": 18}'}],   # pi's typed-parts shape
    {"type": "text", "text": '{"page": 18}'},     # a bare part mapping
    ['{"page": 18}'],                              # a list of plain strings
    '{"page": 18}',                                # the plain-string shape
])
def test_content_parts_are_normalized_before_matching(trace13, content):
    """Finding (b): a typed-parts `content` must not read as empty. Reading
    a plausible envelope as empty text is how a census goes silently
    blind, so the flattener accepts every shape it can recognize."""
    doctored = _doctor(trace13,
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
        "G1:missing_evidence:prompt_source",
        "G1:missing_evidence:skill_card_hash",
        "G1:skill_card_hash_not_approved",
        "G2:missing_evidence:system_prompt",
        "G2:system_prompt_hash_not_approved",
        "G3:missing_evidence:tools",
        "G3:tool_roster_hash_not_approved",
        "G5:checkout_history_posture",
        "G5:checkout_max_page_ne_timestep",
        "G5:checkout_pages_not_contiguous",
        "G5:missing_evidence:timestep",
        "G5:missing_evidence:workspace",
        "G5:search_page_gt_timestep",
        "G5:workspace_branch_ne_timestep",
        "G7:chains_total_ne_1",
        "G7:chains_truncated",
        "G7:completions_merged_ne_total",
        "G7:missing_evidence:reconstruction_stats",
        "G7:missing_evidence:settings",
        "G7:raw_completions_ne_total",
        "G7:settings_hash_not_approved",
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
        "TR3:split_not_train_or_eval",
    )
    assert tuple(sorted(checks.FINDING_VOCABULARY)) == checks.FINDING_VOCABULARY
    assert checks.ALLOWED_FINISH_REASONS == {"stop", "tool_calls", "stop_sequence", "length"}
    assert checks.ALLOWED_SPLITS == ("train", "eval")  # ADR-0015: no third


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


def test_gates_pass_clean_on_both_real_episodes(body13, fidelity_body13):
    """The first-episode-validate leg (row 23), post-CP-13 shape: the
    approved sets admit both known-good episodes — CP-07's and CP-09's —
    through the whole seam, gates included. The two stamped statements are
    exactly what a CP-13 submit+collect carries; the raw fixture-era
    bodies earn the two missing-evidence findings (asserted above)."""
    assert checks.validate_session_result(body13) == []
    assert checks.validate_session_result(fidelity_body13) == []


def test_g3_fails_on_a_doctored_roster(trace13):
    doctored = _doctor(trace13,
                       lambda t: t["tools"][0]["function"].update(name="doctored"))
    expected = _independent_canonical_sha256(doctored["tools"])
    assert checks.run_trace_checks(doctored) == [
        f"G3:tool_roster_hash_not_approved:{expected}"]


def test_g3_missing_roster_fails_closed(trace13):
    doctored = _doctor(trace13, lambda t: t.pop("tools"))
    assert checks.run_trace_checks(doctored) == ["G3:missing_evidence:tools"]


def test_g2_fails_on_a_doctored_system_prompt(trace13):
    doctored = _doctor(trace13, lambda t: t["prompt_messages"][0].update(
        content=t["prompt_messages"][0]["content"] + " "))
    findings = checks.run_trace_checks(doctored)
    assert len(findings) == 1 and findings[0].startswith(
        "G2:system_prompt_hash_not_approved:")


def test_g2_missing_system_prompt_fails_closed(trace13):
    doctored = _doctor(trace13, lambda t: t.update(
        prompt_messages=[m for m in t["prompt_messages"] if m["role"] != "system"]))
    assert checks.run_trace_checks(doctored) == ["G2:missing_evidence:system_prompt"]


def test_g2_typed_parts_carry_the_same_prompt(trace13):
    """Finding (b) is binding on G2: the same wire prompt re-enveloped as
    content parts is the SAME prompt and must pass — a raw `content` read
    would hash '' (a prompt that never existed) and reject it."""
    reenveloped = _doctor(trace13, lambda t: t["prompt_messages"][0].update(
        content=[{"type": "text", "text": t["prompt_messages"][0]["content"]}]))
    assert checks.run_trace_checks(reenveloped) == []


# --- CP-13: G1 and G7's settings clause -----------------------------------


def _approved(key):
    import json

    return json.loads(checks.PINS_PATH.read_text())["pins"][key]


def test_g1_skill_source_with_an_approved_card_passes(trace13):
    """The n/a-free leg: a stated skill source whose stated card-bytes hash
    is pinned passes; `free` (the stamped baseline) passes n/a — both
    finding-free."""
    for card_hash in _approved("skill_card_hash"):
        skill = _doctor(trace13, lambda t, h=card_hash: t["metadata"].update(
            prompt_source="skill:summarize", skill_card_hash=h))
        assert checks.run_trace_checks(skill) == []


def test_g1_unapproved_card_hash_fails(trace13):
    doctored = _doctor(trace13, lambda t: t["metadata"].update(
        prompt_source="skill:summarize", skill_card_hash="0" * 64))
    assert checks.run_trace_checks(doctored) == [
        "G1:skill_card_hash_not_approved:" + "0" * 64]


def test_g1_skill_source_without_a_card_hash_fails_closed(trace13):
    doctored = _doctor(trace13, lambda t: t["metadata"].update(
        prompt_source="skill:summarize"))
    assert checks.run_trace_checks(doctored) == ["G1:missing_evidence:skill_card_hash"]


def test_g1_unrecognized_prompt_source_fails_closed(trace13):
    """Neither `free` nor `skill:<name>` — including the bare prefix and a
    non-string — is missing evidence, never a pass."""
    for source in ("taskbank", "skill:", 7, ""):
        doctored = _doctor(trace13, lambda t, s=source: t["metadata"].update(
            prompt_source=s))
        assert checks.run_trace_checks(doctored) == [
            "G1:missing_evidence:prompt_source"], source


def test_g1_reads_only_the_hoisted_statement(trace13):
    """G1 reads the hoisted top level and nothing else. A `task_metadata`
    fallback was written first and removed: the CP-13 verification measured
    that every vendored shape carrying `task_metadata` also carries
    `traces=[]` (node.py:806-823), so no trace-level gate ever runs on one
    — the leg was dead for its stated purpose while widening the accept
    surface (a source at one level and a hash at the other would pass)."""
    nested = _doctor(trace13, lambda t: (
        t["metadata"].pop("prompt_source"),
        t["metadata"].update(task_metadata={"prompt_source": "free"}),
    ))
    assert checks.run_trace_checks(nested) == ["G1:missing_evidence:prompt_source"]
    # and the vendored ERROR shape is caught by admission, before any gate
    error_shape = {"session_id": "s", "status": "ERROR", "trajectory": {
        "status": "ERROR", "metadata": {"task_metadata": {"prompt_source": "free"}},
        "traces": []}}
    assert "ADM4:no_traces" in checks.validate_session_result(error_shape)


def test_g1_blank_skill_name_fails_closed(trace13):
    for blank in ("skill: ", "skill:\n", "skill:\t"):
        doctored = _doctor(trace13, lambda t, b=blank: t["metadata"].update(
            prompt_source=b, skill_card_hash=_approved("skill_card_hash")[0]))
        assert checks.run_trace_checks(doctored) == [
            "G1:missing_evidence:prompt_source"], blank


# --- CP-13a: G5's checkout census, returned -------------------------------


def _workspace(trace13, **overrides):
    """One doctored workspace echo, everything else the real episode's."""
    def mutate(trace):
        trace["metadata"]["gsj_workspace"] = {**trace["metadata"]["gsj_workspace"],
                                              **overrides}
    return _doctor(trace13, mutate)


def test_the_checkout_census_passes_clean_on_both_real_episodes(trace13, body13):
    """Clean on the echo a correct clone produces: shallow, remoteless,
    pages 1–12 contiguous, branch `timestep-12` agreeing with the
    trainer's own `timestep: 12`."""
    assert checks.check_workspace(trace13) == []
    assert checks.run_trace_checks(body13["trajectory"]["traces"][0]) == []


@pytest.mark.parametrize("overrides, expected", [
    # cross-sourced: the harness's branch vs the trainer's timestep
    ({"branch": "timestep-18"},
     "G5:workspace_branch_ne_timestep:timestep-18!=timestep-12"),
    # cross-sourced: the checkout's own max page vs the trainer's timestep —
    # the predecessor's clause, unreconstructable until CP-13a
    ({"pages": {"count": 18, "min": 1, "max": 18}},
     "G5:checkout_max_page_ne_timestep:18!=12"),
    # single-source: an honest truncated or mis-built checkout
    ({"pages": {"count": 11, "min": 2, "max": 12}},
     "G5:checkout_pages_not_contiguous:2-12/11"),
    # the CP-11 cure, attested per-episode instead of assumed
    ({"shallow": False}, "G5:checkout_history_posture:shallow=False,remotes=0"),
    ({"remotes": 1}, "G5:checkout_history_posture:shallow=True,remotes=1"),
])
def test_each_census_clause_fires_for_its_own_reason(trace13, overrides, expected):
    assert checks.check_workspace(_workspace(trace13, **overrides)) == [expected]


def test_a_missing_or_malformed_workspace_echo_fails_closed(trace13):
    absent = _doctor(trace13, lambda t: t["metadata"].pop("gsj_workspace"))
    assert checks.check_workspace(absent) == ["G5:missing_evidence:workspace"]
    for junk in ("nope", [], {}, 7):
        doctored = _doctor(trace13, lambda t, j=junk: t["metadata"].update(gsj_workspace=j))
        assert checks.check_workspace(doctored) == ["G5:missing_evidence:workspace"], junk
    # a present echo whose page census is not integers is evidence-less too
    no_pages = _workspace(trace13, pages={"count": None, "min": 1, "max": 12})
    assert checks.check_workspace(no_pages) == ["G5:missing_evidence:workspace.pages"]


def test_the_census_never_double_reports_a_missing_timestep(trace13):
    """`check_page_cutoff` owns `G5:missing_evidence:timestep`; without T
    the census reports only what it can judge single-source."""
    def strip(trace):
        trace["metadata"].pop("timestep", None)
        trace["metadata"]["gsj_workspace"] = {
            **trace["metadata"]["gsj_workspace"], "shallow": False}
        trace["response_messages"] = [
            m for m in trace["response_messages"]
            if m.get("role") != "tool" and not m.get("tool_calls")]
    doctored = _doctor(trace13, strip)
    assert checks.check_workspace(doctored) == [
        "G5:checkout_history_posture:shallow=False,remotes=0"]
    assert "G5:missing_evidence:timestep" in checks.run_trace_checks(doctored)


def test_g7_settings_echo_missing_fails_closed(trace13):
    doctored = _doctor(trace13, lambda t: t["metadata"].pop("gsj_settings"))
    assert checks.run_trace_checks(doctored) == ["G7:missing_evidence:settings"]


def test_g7_doctored_settings_fail(trace13):
    """The clause G7 could never verify before the echo: compaction ON in
    the echoed document is a different canonical hash — rejected."""
    compaction_on = {"compaction": {"enabled": True}}
    doctored = _doctor(trace13, lambda t: t["metadata"].update(
        gsj_settings=compaction_on))
    assert checks.run_trace_checks(doctored) == [
        f"G7:settings_hash_not_approved:{_independent_canonical_sha256(compaction_on)}"]


def test_g7_unhashable_settings_are_a_finding_not_a_raise(trace13):
    doctored = _doctor(trace13, lambda t: t["metadata"].update(
        gsj_settings={"compaction": float("nan")}))
    assert checks.run_trace_checks(doctored) == [
        "G7:settings_hash_not_approved:unhashable"]


@pytest.mark.parametrize(
    "mutate, expected",
    [
        ({"chains_total": 2}, "G7:chains_total_ne_1:2"),          # S1/S4: split chains
        ({"chains_reconstructed_truncated": 1}, "G7:chains_truncated:1"),  # S2/S3
        ({"completions_merged": 1}, "G7:completions_merged_ne_total:1!=2"),  # filter amputation
        ({"raw_completions_total": 3}, "G7:raw_completions_ne_total:3!=2"),  # A-12 drops
    ],
)
def test_g7_each_clause_fires_for_its_own_reason(body13, mutate, expected):
    doctored = copy.deepcopy(body13)
    doctored["trajectory"]["metadata"]["reconstruction_stats"].update(mutate)
    assert checks.validate_session_result(doctored) == [expected]


def test_g7_missing_stats_fail_closed(body13):
    absent = copy.deepcopy(body13)
    del absent["trajectory"]["metadata"]["reconstruction_stats"]
    assert checks.validate_session_result(absent) == [
        "G7:missing_evidence:reconstruction_stats"]
    partial = copy.deepcopy(body13)
    del partial["trajectory"]["metadata"]["reconstruction_stats"]["chains_total"]
    assert checks.validate_session_result(partial) == [
        "G7:missing_evidence:reconstruction_stats.chains_total"]


def test_h41_flag_is_policy_gated_and_fires_for_its_own_reason(trace13):
    armed = checks.CheckPolicy(reject_toolless_roster=True)
    # the real episode calls tools: armed stays clean
    assert checks.run_trace_checks(trace13, armed) == []
    # strip every tool interaction; keep T in metadata so G5 stays satisfied
    toolless = _doctor(trace13, lambda t: (
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
    with pytest.raises(checks.PinsConfigurationError, match="tool_roster_hash"):
        checks.check_tool_roster(trace)
    with pytest.raises(checks.PinsConfigurationError, match="skill_card_hash"):
        checks.check_skill_card(
            {"metadata": {"prompt_source": "skill:x", "skill_card_hash": "h"}})
    with pytest.raises(checks.PinsConfigurationError, match="settings_hash"):
        checks.check_settings_echo({"metadata": {"gsj_settings": {"a": 1}}})
    monkeypatch.setattr(checks, "_pins_cache", {"system_prompt_hash": []})
    with pytest.raises(checks.PinsConfigurationError, match="system_prompt_hash"):
        checks.check_system_prompt(trace)
    import inspect
    import json
    for value in json.loads(checks.PINS_PATH.read_text())["pins"].values():
        for pinned in value if isinstance(value, list) else [value]:
            # CP-04' adds a list-typed pin (g6_expected_tail_ids); the
            # no-literal assertion covers it via its JSON rendering.
            if not isinstance(pinned, str):
                pinned = json.dumps(pinned)
            assert pinned not in inspect.getsource(checks)


def test_a_string_valued_pins_key_raises_rather_than_substring_matching(monkeypatch):
    """`hash in "somestring"` is substring containment, not set membership:
    a bare-string pins value would accept any prefix of the real hash as
    approved. Found by the CP-13 adversarial pass — the third
    configuration case, and the one that failed OPEN."""
    real = _approved("skill_card_hash")[0]
    monkeypatch.setattr(checks, "_pins_cache", {"skill_card_hash": real})  # unwrapped
    for stated in (real[:1], real[:6], real):
        with pytest.raises(checks.PinsConfigurationError, match="not a list"):
            checks.check_skill_card(
                {"metadata": {"prompt_source": "skill:x", "skill_card_hash": stated}})


@pytest.mark.parametrize("broken, match", [
    ('{"pins": {"skill_card_hash": ["a"]}', "unusable"),      # corrupt JSON
    ('{"no_pins_key": {}}', "unusable"),                       # wrong shape
    ('["not", "a", "mapping"]', "unusable"),                   # list at the top
])
def test_every_unusable_pins_file_raises_one_configuration_error(tmp_path, monkeypatch, broken, match):
    """Classified by ORIGIN: corrupt, mis-shaped, missing, unreadable — all
    of them are the server's configuration fault, so all of them raise the
    same type the receiver maps to 500 (never a 400, never a crash)."""
    path = tmp_path / "pins.gsj.json"
    path.write_text(broken)
    monkeypatch.setattr(checks, "_pins_cache", None)
    monkeypatch.setattr(checks, "PINS_PATH", path)
    with pytest.raises(checks.PinsConfigurationError, match=match):
        checks.approved_set("skill_card_hash")
    monkeypatch.setattr(checks, "_pins_cache", None)
    monkeypatch.setattr(checks, "PINS_PATH", tmp_path / "absent.json")
    with pytest.raises(checks.PinsConfigurationError, match="unusable"):
        checks.approved_set("skill_card_hash")


def test_unhashable_content_is_a_finding_not_a_raise(trace13):
    """JSON admits NaN and lone surrogates; the canonical convention
    (`allow_nan=False`) and UTF-8 must yield findings, not exceptions."""
    nan_roster = _doctor(trace13, lambda t: t["tools"][0].update(x=float("nan")))
    assert checks.run_trace_checks(nan_roster) == [
        "G3:tool_roster_hash_not_approved:unhashable"]
    surrogate = _doctor(trace13,
                        lambda t: t["prompt_messages"][0].update(content="\ud800"))
    assert checks.run_trace_checks(surrogate) == [
        "G2:system_prompt_hash_not_approved:unhashable"]


# --- CP-16: the pins resolver (ADR-0017, wishlist row 11) ----------------

# Subprocesses, not importlib.reload: resolution happens at FIRST import of
# `gsj_rollout.checks`, and the tests must prove exactly that path — a
# reload would also reset `DEFAULT_POLICY` and `_pins_cache` under every
# other test's feet.


def _resolver_subprocess(code, env, cwd):
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, cwd=cwd,
    )


def test_pins_env_override_wins_even_inside_a_checkout(tmp_path):
    """`GSJ_PINS_PATH` beats the checkout — the only escape an estate with
    its own approved sets has from the shipped values (ADR-0017)."""
    import json
    import os
    pins = tmp_path / "estate.pins.json"
    pins.write_text(json.dumps({"pins": {"tool_roster_hash": ["estate-own-set"]}}))
    result = _resolver_subprocess(
        "from gsj_rollout import checks; print(checks.PINS_PATH); "
        "print(checks.approved_set('tool_roster_hash'))",
        env={**os.environ, "GSJ_PINS_PATH": str(pins)}, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert str(pins) in result.stdout
    assert "estate-own-set" in result.stdout


def test_pins_env_override_to_an_absent_file_raises_loudly(tmp_path):
    """A wrong override is configuration, not content: the first
    `approved_set` call raises `PinsConfigurationError` naming the path —
    never a fall-through to the shipped values (that would be validating
    against the wrong estate's approved sets, silently)."""
    import os
    absent = tmp_path / "no-such-pins.json"
    result = _resolver_subprocess(
        "from gsj_rollout import checks; checks.approved_set('tool_roster_hash')",
        env={**os.environ, "GSJ_PINS_PATH": str(absent)}, cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "PinsConfigurationError" in result.stderr
    assert "no-such-pins.json" in result.stderr


def test_packaged_pins_serve_the_wheel_layout(tmp_path):
    """Step 1's proof, in-suite and hermetic: reconstruct the exact layout
    the wheel installs (`site/gsj_rollout/*.py` + the force-included
    `site/gsj_rollout/pins/pins.gsj.json`, no `pins/` above it), import
    from OUTSIDE every repo, and validate the real CP-09' body — the
    trainer leg that CP-11b measured as non-functional."""
    import json
    import os
    import shutil
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    package = tmp_path / "site" / "gsj_rollout"
    package.mkdir(parents=True)
    for source in (repo_root / "gsj_rollout").glob("*.py"):
        shutil.copy(source, package / source.name)
    (package / "pins").mkdir()
    shutil.copy(repo_root / "pins" / "pins.gsj.json",
                package / "pins" / "pins.gsj.json")

    body_path = repo_root / "docs" / "polar" / "h200-fidelity" / "callback_session_result.json"
    env = {key: value for key, value in os.environ.items() if key != "GSJ_PINS_PATH"}
    env["PYTHONPATH"] = str(tmp_path / "site")
    result = _resolver_subprocess(
        "import json; from gsj_rollout import checks; "
        f"body = json.load(open({str(body_path)!r})); "
        "print('resolved:', checks.PINS_PATH); "
        "print('findings:', checks.validate_session_result(body))",
        env=env, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert str(package / "pins" / "pins.gsj.json") in result.stdout
    assert "findings: []" in result.stdout


def test_the_wheel_ships_the_pins_by_config():
    """The force-include mapping is load-bearing: if it drifts, the packaged
    leg dies with it. `tomllib` arbitrates — fast and hermetic — while the
    CP-16 DoD proves the built artifact itself once, in a scratch venv."""
    import tomllib
    from pathlib import Path
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text())
    include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert include["pins/pins.gsj.json"] == "gsj_rollout/pins/pins.gsj.json"
