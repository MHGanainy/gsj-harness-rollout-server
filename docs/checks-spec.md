# checks-spec — the `checks.py` specification

Captured at CP-01, while the predecessor is fresh, so CP-10/CP-11
**implement rather than re-derive**. Normative sources: the predecessor's
`gsj/envloader/gates.py` and `gsj/envloader/pin.py` @ v0.8.0 (frozen — read
them, never modify them, law 3), its README §6, `mcp-service/README.md`
(the G3/G5 surface), and CP-00's report notes. `checks.py` runs on **both
sides of the wire** (law 6): the receiver drops bad traces at the source,
the trainer re-verifies what arrived — same code, no trust required.

## The pins and the approved-set format

All fingerprints are **generated data — never literals in code** (the
predecessor's delta law; its ADR-0013). Seven pins:

`tokenizer_hash` · `chat_template_hash` · `settings_hash` ·
`tool_roster_hash` · `system_prompt_hash` · `skill_card_hash` ·
`g6_expected_tail`

Every pin value is a **set**: an order-preserving, deduplicated list of
approved hashes (`format: gsj-pins/1`). Entries for path schemes that no
longer exist are dropped, not kept — dead entries only weaken a gate. A
missing pins key at check time **raises loudly**; the gates never fail
open. The predecessor's pinned values did not move (ADR-0002, gap row 23):
they are stale by construction under Polar's mounts, and the first valid
approved sets in this repo come from the derive → re-pin →
first-episode-validate walk (CP-07/CP-10/CP-11). The captured evidence the
walk starts from is in `pins/` (inventory at the end of this doc).

## The four hashing conventions

Four distinct conventions across the gates — reproduce **exactly**, one
shared implementation per convention, no inline copies:

1. **UTF-8 text sha256** — G1 (the skill-card text *as resolved at
   rollout*) and G2 (the *effective wire* system-prompt text). Hash the
   exact bytes of the text, UTF-8, no normalization, no stripping.
2. **Canonical-JSON sha256** — G3 (the tools array as sent on the wire)
   and G7 (the parsed settings document). Canonicalization is the
   predecessor's `canonical_json` (`gsj/envloader/store.py`): sorted keys,
   compact separators, UTF-8 — byte-for-byte, or every hash silently
   changes. Anchor for a correctness test: hashing
   `pins/tools.captured.json`'s wire array with the predecessor's
   convention reproduced the pinned roster hash `a7a7956b…48e56` at its
   CP-29 (a historical anchor for testing the *convention* — the value
   itself stays DATA, never a literal in `checks.py`).
3. **git-blob OID sha1 + template-string sha256** — G4. The tokenizer
   identity is the git blob OID (`sha1("blob <len>\0" + bytes)`) of
   `tokenizer.json`; the chat-template identity is the sha256 of the
   template *string extracted from the JSON field* of
   `tokenizer_config.json` (not of the file). Two different algorithms in
   one gate — do not "simplify" them into one.
4. **No hash at all** — G6. The decoded assistant-turn opening is compared
   **verbatim** with `str.endswith` against `g6_expected_tail`
   (`pins/g6_tail.captured.txt`, 41 bytes of Qwen chat-template tail).

## The gates (what survives is CP-11's call — gap rows 9–15)

| gate | verifies | evidence | mechanism |
|---|---|---|---|
| G1 | skill-card integrity | `prompt_source`, raw `skill_card_text` as resolved at rollout | `skill_card_hash` ∈ approved set (free rows: n/a, pass) |
| G2 | clean containerised system prompt | effective wire `system_prompt_text` | `system_prompt_hash` ∈ approved set; **path-sensitive** — the checkout path is the only case-dependent span, so constant container paths collapse the set to a singleton, and different Polar mounts change every hash on day one |
| G3 | the 11-tool roster, unmodified | `tools_wire` **as sent** | canonical-JSON `tool_roster_hash` match |
| G4 | pinned template + tokenizer | codec fingerprint (measured, never config-echoed) | `tokenizer_hash`/`chat_template_hash` ∈ approved sets |
| G5 | search respects the page cutoff | `timestep`, checkout page census, `search_case` result pages | max checkout page == T ∧ pages contiguous from 1 ∧ every search-result page ≤ T |
| G6 | thinking disabled | decoded assistant-turn openings | each ends with the pinned tail; **zero assistant turns fails closed** |
| G7 | no compaction, ever | `settings_text` read back from disk + chain snapshot | `settings_hash` ∈ approved set ∧ `compaction.enabled == false` ∧ the chain snapshot below |

## The failure vocabulary

Failures are **byte-stable strings** `G{n}:{slug}` (e.g.
`G5:search_page_gt_timestep` — the predecessor's actual constant), with the missing-evidence form
`G{n}:missing_evidence:<field>`. Downstream forensics **greps these
strings** — never reword, never localize, never restructure them. The
posture is fail-closed everywhere: evidence that was never gathered fails
its owning gate; any non-empty failure list means the trace is dropped at
the receiver (the trainer-side quarantine/forensics story is the trainer's
problem — gap row 16).

## The logprob discipline

`rollout_log_probs` must be **finite and ≤ 0 everywhere**, with a literal
`0.0` permitted **only** at `mask == 0` positions (the record-semantics
placeholder). Consequences:

- the fork-reported `-9999.0` sentinel (A-7, UNVERIFIED) is **exactly what
  this rejects** — the guard lands in `checks.py` regardless of whether
  CP-02 verifies the report;
- NaN/±inf anywhere is a hard failure;
- a positive logprob anywhere is a hard failure;
- `0.0` at a `mask == 1` position is suspicious enough to fail — a real
  sampled token with probability exactly 1.0 does not occur in this
  regime.

Alignment note carried from the predecessor: the response arrays
(`responses`, `response_mask`, `loss_mask`, `rollout_log_probs`) are
**R-aligned** (response-length), not P+R — validation that indexes them
over the full sequence is wrong by construction.

## G7's chain snapshot

G7 is not a static config check. Beyond the settings hash and
`compaction.enabled == false`, the predecessor demanded a gateway-side
chain snapshot of **exactly**:

- 1 active chain,
- 0 rollbacks,
- 0 dropped trainable tokens,
- 1 finalized trajectory.

Polar's capture layer must surface an equivalent snapshot **or G7 fails
closed** (gap row 15). The fork-reported abort→ERROR defect (A-7) is
adjacent: an aborted episode must never present a clean chain snapshot.

## The H-41 lesson (why loud failure is load-bearing)

In the predecessor, sglang was silently load-bearing for tool-call
parsing: its *absence* produced *gates-green but tool-free* episodes,
measured live (H-41). The lesson for `checks.py`: **validation must fail
loudly when the tool-parser stack is incomplete** — plausible-looking
degenerate traces are the enemy. Concretely: a trace whose roster (G3)
says tools were offered but which contains zero parsed tool calls is a
red flag, and the environment guard (the predecessor's `driver_factory`
refuses a parser-less env) must have an equivalent on the Polar side —
absence of a parser must be an error, never a silent no-tools episode.

## G3's actual mechanism (stricter than a config field)

G3 hashes the tools array **as sent on the wire** — `tools_wire`, captured
from the request pi actually made, canonical JSON. It does *not* hash the
`tools_allowlist` config field: matching the pin requires reproducing the
key order, whitespace-free canonical encoding, and schema shape of the
wire encoding (the SDK generates tool schemas from the declarations in
`mcp-service/gsj_mcp_service/tools.py`; the `mcp==2.0.0` pin is part of
the G3 surface — bumping it risks schema-serialization drift and a re-pin
walk). Two register consequences: gap row 11 (wire-roster capture must
exist under Polar's proxy) and gap row 31 (the roster must stay a pinned
config field rendered to the wire, or G3 has no pinned input).

## G5's transcript backstop

The structural clamp is server-side (`mcp-service`: filter to `page ≤ T`
**then** rank, T from verified token claims only). The trace-side backstop
parses the transcript's tool-result texts with two regexes — the
compatibility contract every backend and `checks.py` share:

```
"page"\s*:\s*(\d+)          # the "page" member of a search_case hit
md/page_(\d{4})\.md         # the file path of a hit
```

(the predecessor's `gates.extract_case_search_pages`, inlined at CP-01
into `mcp-service/tests/helpers.py`; `checks.py` reimplements it at
CP-11). A backend that renames the key or reformats the path blinds the
gate — `mcp-service/README.md` §Compatibility requirements is binding. If
the page census is unreconstructable from what Polar captures, that is an
abandonment trigger (§9).

## Carried evidence inventory (`pins/`)

| file | anchors |
|---|---|
| `system_prompt.captured.txt` | G2 derivation source (CP-05 capture; embeds the predecessor's host paths — byte-load-bearing, never rewrite) |
| `container/system_prompt.container.derived.txt` | G2 docker-mode singleton (`/workspace`-constant; the text the CP-04/CP-09 golden-reference comparison needs) |
| `tools.captured.json` | G3 wire roster (11 tools) — the canonical-JSON convention's test anchor |
| `settings.rendered.json` | G7 settings text (`{compaction: {enabled: false}}`) |
| `g6_tail.captured.txt` | G6 verbatim tail (41 bytes) |
| `derive_g2.py` | the byte-substitution derivation (`--work-root` per-case mode; `--constant-path` docker-singleton mode) |
