[Documentation](../README.md) › Reference

# Finding vocabulary

Every string `gsj_rollout.checks` can put in a findings list, grouped by family: the exact text, what makes the rule fire, which pins key or `CheckPolicy` knob it depends on, and what to do when you see it. Read this page with a quarantine file or a `rejected <session_id>: [...]` log line in front of you; read [Validation](../concepts/validation.md) first if you want the model behind the rules.

## Reading a finding

A finding is `{id}:{slug}[:detail]`. The `{id}:{slug}` prefix is one of the 42 entries of `checks.FINDING_VOCABULARY`, a sorted tuple that is snapshot-tested — a rename is a deliberate, breaking decision, because forensics downstream grep these strings. The detail after the prefix varies by rule and is documented per finding below.

![The 42 finding prefixes as a family tree: ADM admission, LP logprob discipline, TR tripwires, the gates split into hash gates and evidence gates, and the policy-gated H41, with the detail-suffix conventions](../img/finding-families.png)

<sub>Five families, 42 prefixes; hash gates compare a digest against an approved set in the pins file, evidence gates compare the trace against its own timestep, the pinned tail ids, or the reconstruction stats.</sub>

To map a finding back to its vocabulary entry, match on the prefix — never on equality, because most findings carry a detail:

```python
from gsj_rollout import checks

def vocabulary_entry(finding: str) -> str | None:
    return next((entry for entry in checks.FINDING_VOCABULARY
                 if finding.startswith(entry)), None)

findings = checks.validate_session_result(session_result)
for finding in findings:
    print(vocabulary_entry(finding), "<-", finding)
```

`vocabulary_entry` returns `None` for exactly one class of string: the validating builder's own findings, which admission re-emits verbatim after `ADM2` (see [What is not in the vocabulary](#what-is-not-in-the-vocabulary)).

### Detail suffixes

| suffix shape | meaning | used by |
|---|---|---|
| `:<value>` | the offending value, verbatim | `ADM1` (the status), `TR1` (the `finish_reason`), `TR2`, `TR3`, every `*_not_approved` (the digest, or `unhashable`) |
| `:first=<i>:count=<n>` | one finding per rule for a per-position scan: the first offending index and how many there are, so a systematically broken array cannot flood the list | `LP3`, `LP4`, `LP5`, `LP9` (array index), `G6:interstitial_ne_tail_ids` (1-based turn number) |
| `:<n>` | a count | `ADM2` (builder findings), `G7:chains_total_ne_1`, `G7:chains_truncated` |
| `:<a>!=<b>` | the two values that were supposed to be equal, observed first | `LP2`, `LP8`, `G7:completions_merged_ne_total`, `G7:raw_completions_ne_total`, `G5:checkout_max_page_ne_timestep`, `G5:workspace_branch_ne_timestep` |
| `:<page>><T>`, `:<zeros>/<trainable>><rate>` | a comparison that failed the other way | `G5:search_page_gt_timestep`, `LP6` |
| `:shallow=<v>,remotes=<v>`, `:<min>-<max>/<count>` | the checkout census as observed | `G5:checkout_history_posture`, `G5:checkout_pages_not_contiguous` |
| `missing_evidence:<field>` | not a suffix but a slug family: the rule needed `<field>` and the trace does not carry it. Two sub-forms name a member: `G7:missing_evidence:reconstruction_stats.<key>` and `G5:missing_evidence:workspace.pages` | `G1`, `G2`, `G3`, `G5`, `G6`, `G7` |

### Order and location

`validate_session_result` returns findings in a fixed order: admission (`ADM*`) first, then the session-level chain snapshot (`G7` stats), then each trace's rules in `run_trace_checks` order — logprob discipline, tripwires, page cutoff, workspace census, tool roster, system prompt, skill card, settings echo, thinking tail, toolless roster. No rule stops the others (the one exception is `ADM3`, after which there is nothing left to inspect), so a rejected result's list is the complete picture, not the first failure.

Where you will see them:

- **On the server**, a rejected result is written to `<quarantine_dir>/<session_id>.<mode>.json` as `{"findings": [...], "session_result": <the body>}` and logged at `WARNING` as `rejected <session_id>: [...]`. The receiver still answers Polar `200 {"accepted": n, "rejected": m}`; a finding is a validation verdict, not a delivery error. See [The receiver](../guides/receiver.md).
- **In the trainer**, `RolloutClient.collect` logs the same `rejected <session_id>: [...]` line and drops the result; `partition_session_results` returns the `(result, findings)` pairs if you want them.

```bash
# which quarantined sessions failed the cutoff gate?
grep -l '"G5:search_page_gt_timestep' quarantine/*.json
# the findings of one of them
python -c 'import json,sys; print(*json.load(open(sys.argv[1]))["findings"], sep="\n")' quarantine/<session_id>.<mode>.json
```

> [!WARNING]
> **Two things that look like findings and are not**
>
> A `PinsConfigurationError` (unreadable, corrupt, or mis-shaped pins file; a key missing, empty, or not a list) is an exception, not a finding — the receiver answers `500` and the trainer's collect fails outright. A body the receiver cannot even read as a `SessionResult` (no `trajectory` key, an unsafe `session_id`) is a `400`, never quarantined. Both are configuration or transport faults, and both are deliberately louder than a rejection.

## Admission — `ADM1`–`ADM5`

Session-level. Admission honors what the validating builder inside Polar already decided; it does not re-derive anything.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `ADM1:status_not_completed:<status>` | `status` is anything but `COMPLETED` — the raw value follows, `None` when absent | — | `ERROR` with `ADM2` alongside means the builder rejected the session: read the re-emitted builder findings. Any other status is Polar's own verdict on the episode (timeout, infrastructure) — check the rollout and gateway logs for the session id. |
| `ADM2:builder_findings_present:<n>` | `trajectory.metadata.gsj_validation.findings` is non-empty; `<n>` is the count and each builder finding follows verbatim (a non-list value is treated as a one-entry list) | — | The builder's findings name the session-level rule that failed (empty completion ids, choices arity, a mid-chain `length`, a changed roster, mixed policy versions, a filtered completion). They are properties of the collecting stack, not of the trace — fix the harness or builder configuration and re-collect. |
| `ADM3:trajectory_missing` | `trajectory` is not a JSON object (`null`, a string, a list). Admission stops here: no `ADM2`/`ADM4`, no chain snapshot, no trace rules | — | The episode produced no trajectory at all. On the receiver leg this means `trajectory` was present but not an object; on the trainer leg, inspect what the poll returned for the session. |
| `ADM4:no_traces` | `trajectory.traces` is absent, not a list, or empty | — | Usually rides with `ADM1:…:ERROR` — Polar's error shape carries `traces: []`. Look at the builder findings or the session's logs. A clean `COMPLETED` session with no traces is a builder that produced nothing trainable. |
| `ADM5:malformed_trace` | an entry of `traces` is not a JSON object; emitted once per such entry in the per-trace loop, and the other entries are still checked | — | A serializer fault or a hand-edited archive. Not a trace to repair — find where the entry was written. |

## The chain snapshot — `G7` stats

Session-level, part of the G7 family: `check_chain_snapshot` reads `trajectory.metadata.reconstruction_stats`, the numbers Polar's prefix-merging builder records about how the episode's completions were merged into one token stream. The five stats are read in this order — `chains_total`, `chains_reconstructed_truncated`, `completions_total`, `completions_merged`, `raw_completions_total` — and all must be ints before any comparison.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G7:missing_evidence:reconstruction_stats` | the block is absent, not an object, or empty | — | The body did not come from the prefix-merging builder (or was built by hand). Not trainable evidence; find the source. |
| `G7:missing_evidence:reconstruction_stats.<key>` | the block exists but `<key>` is missing, not an int, or a bool; the first bad key is reported and the rule stops | — | Same as above — a stats block with a missing member is a different builder or a modified body. |
| `G7:chains_total_ne_1:<n>` | `chains_total != 1` | — | The prompts were not prefix-stable across turns, so the builder saw more than one chain: context compaction, a harness that edits earlier messages, or a chat template whose generation-prompt glue is not stitched out. Check `builder.generation_prompt_glue_ids` and `end_of_turn_token_id` in the config; a chain split is repaired at the builder, never on the trace. |
| `G7:chains_truncated:<n>` | `chains_reconstructed_truncated != 0` | — | A merge break dropped tail completions: the end-of-turn token could not be located in a canonical tail, or a retry re-sent an identical prompt. The trace is missing turns the engine actually ran — reject and look at the session's completions. |
| `G7:completions_merged_ne_total:<merged>!=<total>` | `completions_merged != completions_total` | — | Completions were filtered before merging. The pinned agent has no legitimate auxiliary calls, so a drop means the filter or the agent shape changed. |
| `G7:raw_completions_ne_total:<raw>!=<total>` | `raw_completions_total != completions_total` | — | Completions were dropped before the builder counted them — the only receiver-side signal that the capture saw more calls than were merged. Investigate the gateway capture for the session. |

## The logprob discipline — `LP1`–`LP9`

Trace-level. `response_logprobs` are raw model logprobs, aligned with `response_ids`, and must be finite and ≤ 0 everywhere; `loss_mask` is 0/1 ints of the same length. "Mask-1" means a position where `loss_mask[i] == 1`; "trainable" means the trace has at least one such position.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `LP1:response_logprobs_absent` | `response_logprobs` is not a list and the trace is trainable (or has non-empty `response_ids` with an empty mask). `LP2`–`LP6` are skipped | — | Polar nulls the whole array when any mask-1 position lacks a logprob, so this is an engine or capture fault: the serving engine did not return logprobs for every sampled token. Check the engine's logprob settings and the gateway capture. |
| `LP2:response_logprobs_length_ne_response_ids:<a>!=<b>` | `len(response_logprobs) != len(response_ids)` | — | The arrays were produced or serialized inconsistently. Not repairable; find the writer. |
| `LP3:sentinel_logprob_at_mask1:first=<i>:count=<n>` | a mask-1 logprob ≤ `sentinel_threshold` | `CheckPolicy.sentinel_threshold` (−9000.0) | vLLM writes `-9999.0` both as its missing-logprob default and as its clamp floor, so a sentinel at a sampled position means the logprob was never really measured. Fix the engine side. Do not lower the threshold to admit it: a value at the floor is indistinguishable from missing. |
| `LP4:nonfinite_logprob:first=<i>:count=<n>` | NaN, ±inf, a bool, a non-number, or an int too large for a float — anywhere in the array | — | A numerics or serialization fault (JSON on the wire really can carry `NaN` and `Infinity`). Reject; check the engine and the capture path. |
| `LP5:positive_logprob:first=<i>:count=<n>` | a value > 0 anywhere in the array | — | A probability above 1 — an engine numerics bug or a mislabeled field. Reject. |
| `LP6:zero_logprob_rate_at_mask1:<zeros>/<trainable>><rate>` | the share of exact `0.0` at mask-1 positions exceeds the allowance | `CheckPolicy.zero_at_mask1_max_rate` (0.25) | Exact zeros at sampled positions are a bf16 property on both reference platforms: a few to fifteen percent on clean episodes, up to a quarter on a repetitive-loop episode. A rate near 100 % is a placeholder array, not evidence — reject. A modest rate on an otherwise clean episode with a stricter policy means the knob is set too tight for the platform; see [`checks:`](../guides/configuration.md#checks). |
| `LP7:empty_loss_mask` | `loss_mask` is empty (or not a list) while `response_ids` is non-empty | — | Polar's own trace validator skips the length check on an empty mask, so this shape is legal on the wire and never trainable. The builder emitted no mask; reject and look at the session. `G6:missing_evidence:turns` fires beside it, for the same reason. |
| `LP8:loss_mask_length_ne_response_ids:<a>!=<b>` | the mask is non-empty and its length differs from `response_ids` | — | As `LP2` — inconsistent arrays, find the writer. |
| `LP9:loss_mask_value_not_binary:first=<i>:count=<n>` | any mask entry that is not the int `0` or `1` (bools, strings, floats, `null` all count) | — | Almost always a serializer that stringified the mask. Fix the serialization path. While this fires, `LP1`, `LP3` and `LP6` cannot see the trace (they test `== 1`), which is why the rule exists — the mask is 0/1 ints or it is not evidence. A bool mask still reaches `LP3`, because `True == 1` in Python. |

## Tripwires — `TR1`–`TR3`

Trace-level, three non-array rules. Emission order inside the rule is `TR1`, `TR3`, `TR2`.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `TR1:finish_reason_not_allowed:<value>` | `finish_reason` is not a string in `{stop, tool_calls, stop_sequence, length}` — the raw value follows (`abort`, `None`, …) | `checks.ALLOWED_FINISH_REASONS` | A tail abort: the last completion did not end naturally. Look at the harness and gateway logs for the session. Note that `length` is admitted on purpose — a length-terminated episode is a real trajectory up to the cut, and the CLI reports `length-terminated: K/N` so the trainer can decide. |
| `TR2:reasoning_loss_mask_masked_tokens:<value>` | `metadata.reasoning_loss_mask.masked_tokens` is present and is anything but `null`, `0`, `false`, `"0"` or `""`; deliberately not type-narrowed, so `3.0`, `"3"` and `[1]` all fire | — | A re-vendor canary. Polar's reasoning-masking code does not run in the vendored build; if this fires, a re-vendored Polar has started masking reasoning tokens. Stop and review the vendored builder before accepting any trace from that build. |
| `TR3:split_not_train_or_eval:<value>` | `metadata.split` is present and not `train` or `eval`. Absent is legal (unstated); an explicit `null` is rejected, because the renderer omits the key rather than writing `null` | `checks.ALLOWED_SPLITS` | The submit path stated an off-vocabulary split (`test`, `TRAIN`, an empty string). Fix the task request — `render_task_request(split=…)` only accepts `"train"`, `"eval"` or `None`. A `null` means something re-serialized the metadata on the way. |

## Gates — `G1`, `G2`, `G3`, `G5`, `G6`, `G7`

Trace-level (the G7 chain snapshot above is the session-level half of G7). Every hash gate loads its approved set through `checks.approved_set(key)`; a pins key that is missing, empty, or not a list raises `PinsConfigurationError` instead of producing a finding. `G4` has no entries — see [What is not in the vocabulary](#what-is-not-in-the-vocabulary).

> [!NOTE]
> **The pins file decides what `*_not_approved` means**
>
> Approval is set membership in whichever pins file `checks.PINS_PATH` resolved to. On an estate that is not the reference one, validating against the packaged pins fails every hash gate with `*_not_approved:<digest>` — loudly, on purpose. Before treating any `not_approved` finding as a defect, confirm both legs resolve your own pins file (`GSJ_PINS_PATH`, set before the first import) and that the file is the right mode. See [Pins and approved sets](../concepts/pins.md).

### G1 — skill-card integrity

Reads `metadata.prompt_source` and `metadata.skill_card_hash`, both stated by the submit path.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G1:missing_evidence:prompt_source` | `prompt_source` is absent, not a string, not `free`, and not `skill:<name>` with a non-blank name (`skill:`, `skill: `, `taskbank`, `""`, `7` all fire). Only the hoisted top-level metadata is read — a value under `task_metadata` does not count | — | Submit through `render_task_request`, which always states the source. A trace that predates the statement fails closed rather than being grandfathered. |
| `G1:missing_evidence:skill_card_hash` | `prompt_source` is `skill:<name>` but `skill_card_hash` is absent or not a non-empty string | — | A skill source must carry the card hash. `render_task_request(skill_card_text=…)` computes it from the card's raw UTF-8 bytes; do not compute it yourself from `path.read_text()`. |
| `G1:skill_card_hash_not_approved:<hash>` | the stated hash (first 64 characters) is not in the approved set | pins `skill_card_hash` | The card's bytes differ from every pinned card: the card drifted, or a new card was added. Fix the card, or re-pin (add its hash) if the change is intended. Note the gate is set membership, not name-to-card binding — any pinned card passes under any skill name. |

### G2 — a clean system prompt

Reads every `prompt_messages` entry with `role: system`, content flattened to text (typed content parts included), and hashes its UTF-8 bytes. The approved set is loaded before the scan, so a pins fault raises even on a trace with no system message.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G2:missing_evidence:system_prompt` | no system message in `prompt_messages` | pins `system_prompt_hash` (loaded first) | The agent ran without its system prompt, or the wire evidence was not captured. Check the harness and the gateway capture. |
| `G2:system_prompt_hash_not_approved:<digest>` | one per system message whose text sha256 is not in the approved set; `unhashable` when the text carries a lone surrogate | pins `system_prompt_hash` | The prompt differs from the pinned one. The hash is path-sensitive by design: a different `harness.workdir`, a different agent version, or any edit to the prompt text changes it. Compare the digest against your pins file; re-pin if the change is intended. |

### G3 — the tool roster unmodified

Reads `tools` — the array exactly as sent on the wire — and hashes its canonical JSON (`sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False`).

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G3:missing_evidence:tools` | `tools` is absent, not a list, or empty | — | No roster was offered. This is G3's shape, deliberately not `H41`'s: check the harness's tool allowlist and the capture. |
| `G3:tool_roster_hash_not_approved:<digest>` | the digest is not in the approved set; `unhashable` when the array cannot be canonicalized (NaN, lone surrogates) | pins `tool_roster_hash` | The roster changed: a tool added or removed, a schema edit in the retrieval service, or an MCP SDK bump that changed how schemas serialize — key order and whitespace count. Re-pin if the change is intended. A merged trace carries the first completion's roster; drift across completions is the builder's `R11` finding, not this one. |

### G5 — the page cutoff held

Two instruments. Both need the trace's own timestep `T`, resolved in this order: an int `metadata.timestep`, then an int `metadata.task_metadata.timestep`, then the `"timestep": N` member of an `mcp_gsj_case_status` result. No pin — the trace is compared against itself. Background in [The timestep cutoff](../concepts/timestep-cutoff.md).

**The transcript backstop** (`check_page_cutoff`) scans every tool result whose call resolves to `mcp_gsj_search_case` (by `tool_call_id` against the assistant turn's `tool_calls`) with the two regexes every retrieval backend must honour: `"page": N` and `md/page_NNNN.md`. Decisions results and built-in file reads are exempt.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G5:missing_evidence:timestep` | none of the three sources yields an int. `check_workspace` then skips its two T-dependent clauses, so the missing timestep is reported once | — | Submit through `render_task_request`, which puts `timestep` into the task metadata that Polar stamps onto the trace. An episode that never called `case_status` and carries no metadata timestep has no `T` and fails closed by design. |
| `G5:search_page_gt_timestep:<page>><T>` | one finding per distinct page above `T` found in a `search_case` result, ascending | — | A real cutoff breach: the retrieval service returned a page past the timestep. Do not train on it. The service clamps `page ≤ T` from verified token claims, so investigate the service and the token the sandbox presented — see [The retrieval service](../guides/retrieval-service.md). |

**The checkout census** (`check_workspace`) reads `metadata.gsj_workspace`, the echo the harness records after the clone and before the agent starts.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G5:missing_evidence:workspace` | `gsj_workspace` is absent, not an object, or empty; nothing else from the census is reported | — | The harness did not echo its workspace probe: a harness other than the pinned `pi_harness.py`, or a trace that predates the echo. Fails closed rather than being grandfathered. |
| `G5:checkout_history_posture:shallow=<v>,remotes=<v>` | `shallow` is not exactly `true`, or `remotes` is not `0` | — | The clone lost `--depth 1`, or a remote survived. Both re-open the history channel around the cutoff — fix the harness's clone step. |
| `G5:missing_evidence:workspace.pages` | `pages.min`, `pages.max`, `pages.count` are not all ints (bools excluded); the posture clause above has already been judged, the page and branch clauses are skipped | — | The probe ran but could not count pages — an empty or non-standard checkout. Inspect the case repository. |
| `G5:checkout_pages_not_contiguous:<min>-<max>/<count>` | `min != 1` or `count != max` | — | The checkout's `md/page_NNNN.md` files do not run 1..max — a mis-built or truncated case repository. Fix the corpus ingest; see [The corpus](../guides/corpus.md). |
| `G5:workspace_branch_ne_timestep:<branch>!=timestep-<T>` | the checked-out branch is not `timestep-<T>` (cross-sourced: the harness's git against the trainer's timestep) | — | The harness cloned the wrong branch for the task, or the task metadata carried a different timestep than the harness received. |
| `G5:checkout_max_page_ne_timestep:<max>!=<T>` | the highest page in the checkout is not `T` | — | The `timestep-<T>` branch holds a different page count than `T` — a corpus ingest problem for that case. |

### G6 — the thinking tail

Tokenizer-free. Assistant turns are the maximal mask-1 runs of `loss_mask`; turn 1's opening is `prompt_ids` plus any leading mask-0 run of `response_ids`, and each later turn's opening is the mask-0 run before its span. Each opening must end (a list `endswith` on token ids) with an entry of `g6_expected_tail_ids`; only non-empty list entries are used, so a mis-shaped pin fails closed. The approved set is loaded before anything else, so a pins fault raises first.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G6:missing_evidence:turns` | no mask-1 run at all — an empty, all-zero, or off-domain mask | pins `g6_expected_tail_ids` (loaded first) | Nothing trainable in the trace. Rides with `LP7` or `LP9` when the mask itself is the problem; alone, it means the builder produced no trainable span. |
| `G6:prompt_suffix_ne_tail_ids` | turn 1's opening does not end with any pinned tail | pins `g6_expected_tail_ids` | The first thing to check is the mode: under the thinking-off pins the tail is the empty think block, under the thinking-on pins it is the bare generation prompt, and running an estate in one mode against the other's pins fails every episode this way. Align `harness.thinking` with the file `GSJ_PINS_PATH` selects on both legs. If the modes agree, the served chat template differs from the pinned one — derive the tail from the served endpoint and re-pin. |
| `G6:interstitial_ne_tail_ids:first=<turn>:count=<n>` | later turns whose pre-turn mask-0 run does not end with any pinned tail; `<turn>` is 1-based and always ≥ 2 | pins `g6_expected_tail_ids` | Same causes as above, seen at the history re-render rather than the generation prompt. Alone, without the prompt-suffix finding, it points at the template's history rendering or at a stitched glue that does not match the pinned tail. |

### G7 — no compaction (the settings echo)

Reads `metadata.gsj_settings`, the settings document the harness rendered and echoed into the trace metadata the capture layer stamped — never a caller-supplied `task_metadata`, so a trainer cannot certify compaction-off in the same request that asks for the episode.

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `G7:missing_evidence:settings` | `gsj_settings` is absent, not an object, or empty | — | The harness did not echo its settings: a harness other than the pinned one, or a trace that predates the echo. |
| `G7:settings_hash_not_approved:<digest>` | the canonical-JSON sha256 of the document is not in the approved set; `unhashable` for NaN or lone surrogates | pins `settings_hash` | The approved set holds one value, the hash of `{"compaction":{"enabled":false}}`, so any other document — compaction on, or extra keys — fails. Fix the harness's rendered settings; re-pin only if a different document is genuinely intended. |

## Policy-gated — `H41`

Trace-level, off by default. Emitted only when `CheckPolicy.reject_toolless_roster` is `True` (YAML: `checks.reject_toolless_roster: true`).

| finding | fires when | depends on | what to do |
|---|---|---|---|
| `H41:roster_offered_zero_tool_calls` | the policy is armed, `tools` is a non-empty list, and no message in `prompt_messages` or `response_messages` carries a non-empty `tool_calls`. An absent roster is `G3:missing_evidence:tools`, never `H41` | `CheckPolicy.reject_toolless_roster` | A legitimate episode can call no tools, which is why the default is off. Armed, it makes the "gates green but tool-free" shape loud — the shape a serving stack without a working tool-call parser produces. One `H41` is an episode; `H41` across a whole collection is the engine's tool-call parsing path (its serve flags), not the traces. |

## What is not in the vocabulary

- **`G4`.** No codec evidence rides the callback, so the served tokenizer and chat template are verified on the estate at bring-up by `pins/derive_pins.py`, never per trace. `checks.py` has no `G4:*` string.
- **The builder's findings.** `ADM2` re-emits whatever the validating builder recorded — strings such as `S1:empty_prompt_ids:<cid>`, `S6:empty_response_ids:<cid>`, `S8:choices_len_ne_1:<cid>:<n>`, `S3:duplicate_consecutive_prompt:<cid>`, `S7:mid_chain_finish_length:<cid>`, `A12:non_agent_shape:<cid>`, `A12:completion_filter_excluded_nonempty:…`, `A15:end_of_turn_token_id_not_configured`, `R11:roster_changed_across_completions`, `S9:policy_version_mixed:…`. They are byte-stable too, but they belong to `builder.py`, not to `FINDING_VOCABULARY`.
- **Replay.** No rule re-scores `response_ids` against an engine; there is no finding for logprob drift. The reasons are recorded in the [checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

> [!TIP]
> **Adding a finding**
>
> New entries are pure additions: append the constant, add it to `FINDING_VOCABULARY` in sorted position, and update the snapshot test. Never rename or restructure an existing entry — an archive of quarantine files and every grep written against them depend on the old spelling.

## See also

- [Validation](../concepts/validation.md) — the model behind the rules and the order they run in.
- [Pins and approved sets](../concepts/pins.md) — the keys the hash gates and G6 read.
- [The receiver](../guides/receiver.md#reading-a-quarantined-file) — reading a quarantine file.
- [Troubleshooting](../guides/troubleshooting.md#at-the-callback-findings-by-family) — the triage view of the same families.
