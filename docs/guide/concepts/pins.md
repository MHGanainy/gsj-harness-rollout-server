[Documentation](../README.md) › Concepts

# Pins and approved sets

Five of the validators in `gsj_rollout.checks` compare a hash computed from a trace against an *approved set* — a list of hashes read from a pins file, never a constant in code. This page explains what those sets are, the `gsj-pins/1` file that holds them, which gate reads which key, how `checks` decides which file to read, why a thinking-on estate needs a second file on both sides of the wire, and what it takes to derive a pins file for an estate of your own.

## What a pin is

A pin names one property of the estate that every accepted trace must exhibit: the tool roster the agent saw, the system prompt it ran under, the skill card its prompt came from, the settings the harness rendered, the chat-template tail each assistant turn opens with, and (verified at bring-up rather than per trace) the tokenizer and chat template the engine serves.

Each pin's value is an **approved set**: an order-preserving, de-duplicated list of hashes. A gate computes the same hash from the trace in front of it and passes when the result is a member of the set. Three rules govern the sets, and they are enforced by the code, not by convention:

- **Generated, never literal.** Every value is derived from evidence the repository owns — a real episode's wire payload, a file on disk, a served artifact — and the derivation is reproducible (`pins/derive_pins.py`, below). No hash appears anywhere in `gsj_rollout/*.py`.
- **A set, not a value.** A key can hold several approved hashes (the reference file approves two skill cards). Entries whose source no longer exists are dropped, because a dead entry only widens what the gate accepts.
- **Never fail-open.** A pins file that cannot be read, or a key that is missing, empty, or not a list, raises `PinsConfigurationError` at the first `approved_set()` call. Content problems in a trace become findings; pins problems are the server's configuration fault and are raised, not reported.

```python
from gsj_rollout import checks

checks.PINS_PATH                          # the resolved file (a pathlib.Path)
checks.approved_set("tool_roster_hash")   # -> ['a7a7956b…']; raises PinsConfigurationError if unusable
```

## The file: `gsj-pins/1`

The shipped file is `pins/pins.gsj.json` in a checkout and `gsj_rollout/pins/pins.gsj.json` inside the installed package (the wheel copies it at build time; the checkout is the single source). Its shape, trimmed:

```json
{
  "format": "gsj-pins/1",
  "derived_at": "<when the walk ran>",
  "host": "<the estate the values were measured on>",
  "pins": {
    "tokenizer_hash":       ["949e1ec83f61520a25c75426edc4a43acc36f29a"],
    "chat_template_hash":   ["1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9"],
    "settings_hash":        ["dae8948524be8253e04c4174632477e0333adc0323e791a6e54ace3b31004d20"],
    "tool_roster_hash":     ["a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56"],
    "system_prompt_hash":   ["f56e8a6e9ea9dd1c19be89c6754a4e8d3d1c0f89e04bb21f60237aa2e8837df4"],
    "skill_card_hash":      ["d41ec6ea…", "15ae463e…"],
    "g6_expected_tail":     ["<|im_start|>assistant\n<think>\n\n</think>\n\n"],
    "g6_expected_tail_ids": [[151644, 77091, 198, 151667, 271, 151668, 271]]
  },
  "provenance": {
    "tool_roster_hash": {
      "algo": "sha256_canonical_json",
      "artifacts": ["docs/polar/pi-corpus/trace.json tools[] (episode sk-polar-…)", "…"],
      "notes": "…",
      "mac_specific": false
    }
  },
  "walk_status": { "derive": "…", "re_pin": "…", "first_episode_validate": "…" }
}
```

| top-level key | read by | what it holds |
| --- | --- | --- |
| `format` | people | always `"gsj-pins/1"` |
| `derived_at`, `host` | people | when and on which estate the values were measured |
| `mode` | the receiver | optional; `"thinking-on"` in the thinking-on file, absent in the reference file (absent means thinking-off). The receiver stamps it into every file it writes: `<traces_dir>/<session_id>.<mode>.json`, quarantine likewise, so an archive collected across restarts stays attributable. |
| `pins` | `checks.approved_set` | the approved sets — the only part of the file the validators read. Every value is a list; `g6_expected_tail_ids` is a list of id lists. |
| `provenance` | people and the walk | one block per key: `algo` (the hashing convention), `artifacts` (the evidence files, with episode ids where the evidence is a captured episode), `notes`, `mac_specific` |
| `walk_status` | people | where the derive → re-pin → first-episode-validate walk stands for this file |

`provenance` is documentation with teeth: `pins/derive_pins.py` reads the artifacts it names and fails if the recorded hash no longer reproduces. When you write your own file, fill the block in — it is the only record of what a hash *is*.

## Which gate consumes which key

The hashing conventions are four, and a gate reproduces its convention exactly; the reasoning behind each gate is in [Validation](validation.md) and in the [checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

| key | gate (function) | hashed from the trace | convention | on mismatch |
| --- | --- | --- | --- | --- |
| `skill_card_hash` | G1 `check_skill_card` | `metadata.skill_card_hash`, only when `metadata.prompt_source` is `skill:<name>`; `free` passes without a card | UTF-8 sha256 of the card text (computed trainer-side at submit) | `G1:skill_card_hash_not_approved:<hash>` |
| `system_prompt_hash` | G2 `check_system_prompt` | every `prompt_messages` entry with `role: system` (content-part lists are joined to text first) | UTF-8 sha256 of the text | one `G2:system_prompt_hash_not_approved:<digest>` per offending message |
| `tool_roster_hash` | G3 `check_tool_roster` | the `tools` array as sent on the wire | canonical-JSON sha256 | `G3:tool_roster_hash_not_approved:<digest>` |
| `settings_hash` | G7 `check_settings_echo` | `metadata.gsj_settings`, the settings document the harness rendered and echoed | canonical-JSON sha256 | `G7:settings_hash_not_approved:<digest>` |
| `g6_expected_tail_ids` | G6 `check_thinking_tail` | every assistant-turn opening: the suffix of `prompt_ids` for turn 1, the mask-0 run before each later turn | no hash — a list-`endswith` of token ids against any approved entry | `G6:prompt_suffix_ne_tail_ids`, `G6:interstitial_ne_tail_ids:first=<turn>:count=<n>` |
| `g6_expected_tail` | nothing at check time | — | verbatim text; the human-readable form of the ids entry, verified by the walk | — |
| `tokenizer_hash`, `chat_template_hash` | nothing at check time (G4) | — | git-blob OID of `tokenizer.json`; sha256 of the served `--chat-template` file's bytes | verified estate-side by `derive_pins.py` at bring-up |

Each hash gate also has a *missing evidence* finding (`G3:missing_evidence:tools`, `G2:missing_evidence:system_prompt`, `G7:missing_evidence:settings`, `G1:missing_evidence:prompt_source`, `G1:missing_evidence:skill_card_hash`, `G6:missing_evidence:turns`) that fires before any hashing when the trace does not carry what the gate needs. The full vocabulary is in [Finding vocabulary](../reference/findings.md).

Canonical JSON is exactly this, and every hash in the `sha256_canonical_json` rows depends on it byte-for-byte:

```python
json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
```

![Six keys of pins.gsj.json above six gates: five locks, G1 skill card, G2 system prompt, G3 tool roster, G7 settings echo and G6 turn openings, each labelled with the trace field it hashes and the convention on the arrow from its key; the sixth, G4, is an estate-side tile fed by tokenizer_hash and chat_template_hash with nothing arriving from the trace](../img/pins-gate-map.png)

<sub>Each lock compares one field of the trace, hashed under the key's convention, against that key's approved set; G6 compares token ids by list suffix rather than by hash, and G4's two keys are verified at bring-up because no codec evidence rides the callback.</sub>

> [!NOTE]
> **G4 is a bring-up check, not a trace check**
>
> No codec evidence rides the callback, and neither this package nor Polar's environment carries a tokenizer, so `checks.py` cannot verify the served tokenizer or template per trace. Those two keys are verified where the artifacts exist — on the serving host, by the walk — and G6's id list is the mechanism that lets the trace-side gate stay tokenizer-free: the ids were computed once, at pin time, with the served tokenizer.

## Resolution order

`checks.PINS_PATH` is resolved once, when `gsj_rollout.checks` is first imported, in this order:

1. **`GSJ_PINS_PATH`** is set → that file, unconditionally. A path that does not exist or does not parse is *not* a reason to fall back: the first `approved_set()` call raises `PinsConfigurationError` naming the path. Falling through would mean validating against another estate's approved sets without telling you.
2. Otherwise **`pins/pins.gsj.json` exists beside the package** (the repository checkout layout, `<repo>/pins/` next to `<repo>/gsj_rollout/`) → that file. This is the developer-in-tree case.
3. Otherwise the **packaged copy** `gsj_rollout/pins/pins.gsj.json` in site-packages → that file, **plus one `UserWarning`** at import:

    ```text
    gsj_rollout.checks: …/gsj_rollout/pins/pins.gsj.json holds the REFERENCE ESTATE's approved sets,
    not defaults — set GSJ_PINS_PATH to your own or every hash gate fails *_not_approved.
    ```

![Both legs, the receiver and your training process, import gsj_rollout.checks and follow one numbered strip: GSJ_PINS_PATH set, checkout pins/ exists, packaged copy. Each step yields a pins document; a bad path under the first raises PinsConfigurationError, the thinking-on set is reachable only through the first, and the third emits a UserWarning](../img/pins-resolution.png)

<sub>One rule on both legs, resolved once at import: the file you named (any path, either mode), else the checkout copy, else the packaged copy with a warning. A bad override raises instead of falling through; the thinking-on set is only ever reached by naming it.</sub>

Two facts the picture compresses. The file you name in `GSJ_PINS_PATH` may be either mode — the thinking-off reference, the thinking-on sibling, or a file of your own — while routes 2 and 3 always resolve to the thinking-off reference. And the thinking-on sibling is a valid target on both legs: `pins/thinking-on/pins.gsj.json` in a checkout, `gsj_rollout/pins/thinking-on/pins.gsj.json` in site-packages; nothing selects it for you (see [The thinking-on set](#the-thinking-on-set)).

The warning is the trap named in the README: a fresh `pip install` validates against *this* estate's pins, which is exactly right for a trainer talking to the reference server and exactly wrong for any other estate — where every hash gate fails `*_not_approved`, loudly, until you point `GSJ_PINS_PATH` at your own file.

Set the variable in the environment of **every process that imports `gsj_rollout`**, before the first import:

```bash
# server leg: the receiver validates at the source
GSJ_PINS_PATH=/etc/gsj/pins.gsj.json gsj-rollout serve --config rollout.yaml
```

```python
# trainer leg: the client re-runs the same validators on what it collects
import os
os.environ["GSJ_PINS_PATH"] = "/etc/gsj/pins.gsj.json"   # before the first import of gsj_rollout

from gsj_rollout import RolloutClient, checks
assert checks.PINS_PATH.name == "pins.gsj.json"
```

> [!WARNING]
> **Once per process**
>
> The file is read on the first `approved_set()` call and cached for the life of the process. Setting `GSJ_PINS_PATH` after `gsj_rollout.checks` has been imported changes nothing, and editing the pins file under a running receiver changes nothing — a re-pin needs a restart on both legs.

On the server, a pins fault surfaces as an HTTP 500 on the callback endpoint with body `{"error": "pins configuration: …"}` naming the key or path — never a 400 (that would blame Polar's body) and never a dropped connection. See [The receiver](../guides/receiver.md).

## The thinking-on set

Gate G6 asserts that every assistant turn opens with the served chat template's generation-prompt tail. That tail is different in the two harness modes, so **G6 is per-mode pins data** rather than a per-mode rule:

| mode | `g6_expected_tail` | `g6_expected_tail_ids` | file |
| --- | --- | --- | --- |
| thinking off (default) | `<|im_start|>assistant\n<think>\n\n</think>\n\n` — 41 bytes, the empty think block | `[151644, 77091, 198, 151667, 271, 151668, 271]` | `pins/pins.gsj.json` |
| thinking on | `<|im_start|>assistant\n` — 22 bytes, the bare generation prompt | `[151644, 77091, 198]` | `pins/thinking-on/pins.gsj.json` |

The on-tail is the first line of the off-tail, and its ids are the off-ids' first three — but it is **not** an `endswith` suffix of the off-ids (those end `271, 151668, 271`). So each file, on its own, asserts its mode in both directions: a thinking-off opening fails the on-pins exactly as a thinking-on opening fails the off-pins. The six non-G6 keys in the thinking-on file are byte-equal to the reference file's, because the thinking flag moves nothing else on the wire; the walk fails if the two files ever diverge on them.

The mode is selected by the harness knob and must be matched by the pins file:

```yaml
harness:
  thinking: medium      # off | minimal | low | medium | high | xhigh | max — "medium" is the conventional ON
```

`HarnessConfig.thinking` defaults to `"off"` and accepts only pi's own level names. Any other string is rejected at config load, by design: pi silently clamps an unknown `--thinking` value to `off`, so a typo would collect a thinking-off control wearing the measurement's label. Two YAML 1.1 spellings are handled explicitly: a bare `off` reaches the model as the boolean `False` and is mapped back to `"off"`; a bare `on` becomes `"on"`, which is not a pi level and is rejected by name.

> [!WARNING]
> **A non-off level needs the thinking-on set on BOTH legs**
>
> Default resolution — checkout or packaged — always means the thinking-off reference. Nothing selects the thinking-on file for you: set `GSJ_PINS_PATH` to it in the receiver's environment *and* in the trainer's. With the wrong file, G6 fails every episode (`G6:prompt_suffix_ne_tail_ids` plus one `G6:interstitial_ne_tail_ids:first=…:count=…` for the later turns), the receiver quarantines all of them, and the trainer collects nothing — loud and correct, but not what you meant.
>
> ```bash
> # a pip-only estate: the wheel carries the thinking-on set as data
> export GSJ_PINS_PATH="$(python -c 'import gsj_rollout, pathlib; print(pathlib.Path(gsj_rollout.__file__).parent / "pins/thinking-on/pins.gsj.json")')"
> ```

The thinking-on file declares `"mode": "thinking-on"`, so the receiver names what it writes `<session_id>.thinking-on.json`; files from the reference set are `<session_id>.thinking-off.json`. A mixed archive is therefore attributable after the fact.

## Re-pinning for your own estate

Any of the following changes a hash and therefore needs a re-pin: a different tool roster (`harness.tools_allowlist` — the default eleven tools hash into the shipped `tool_roster_hash`), a different in-image checkout path (`harness.workdir` — the shipped `system_prompt_hash` is the `/workspace` text), a different pi version or MCP SDK (both change the wire `tools` schema), your own skill cards, different harness settings, a different model snapshot or served chat template, or the thinking mode.

`pins/derive_pins.py` is the reproducible walk for the reference estate: it recomputes every approved value from the evidence its provenance names and exits non-zero on any divergence. Run it from a checkout:

```bash
python pins/derive_pins.py
# ok   tool_roster_hash <- convention anchor pins/tools.captured.json: a7a7956b…
# ok   system_prompt_hash <- docs/polar/pi-corpus/trace.json prompt_messages[0]: f56e8a6e…
# …
# skip g6_expected_tail_ids (no tokenizer on this host — pin-time verification is estate-side by design, …)
#
# engine provenance (written by --record; absences are named, never defaulted):
# { … }
#
# all approved values reproduced
```

![The walk as four numbered steps, read the evidence, hash by convention, compare to the sets, exit 1 on divergence. Six evidence files in the repository, skill cards, two real episodes, the container prompt, the rendered settings, the G6 tail capture and the convention anchor, feed derive_pins.py; the served tokenizer and template feed it from the estate side; the result is compared against pins.gsj.json and its thinking-on sibling, ending either in all values reproduced or DIVERGED with exit 1](../img/pins-derivation.png)

<sub>Every approved value is re-derived from a file the repository owns, then compared with the two pins documents; the served tokenizer and template are the one input measured outside the repository, on the serving host. A skip is printed as a skip and never counted as a pass.</sub>

What the walk reads, in order:

| evidence | verifies | override |
| --- | --- | --- |
| `pins/tools.captured.json` | the canonical-JSON convention itself — the anchor runs first; if it fails, nothing below is trustworthy | — |
| `docs/polar/pi-corpus/trace.json`, `docs/polar/fidelity/trace.json` | `tool_roster_hash` from each `tools[]`; `system_prompt_hash` from each `prompt_messages[0]` (asserted to be the system role) | — |
| `pins/container/system_prompt.container.derived.txt` | `system_prompt_hash` from the derived singleton text | — |
| `pins/settings.rendered.json` and the literal `{"compaction": {"enabled": false}}` | `settings_hash` twice — the carried evidence and the `settings_json` constant in `pi_harness.py` must agree | — |
| every `estate/corpus/staging/skills/*/SKILL.md` | `skill_card_hash`, one entry per card, hashed from the card bytes — the same bytes ingest writes into every case repository; a new card in the tree is pinnable without a script edit | — |
| `tokenizer.json` in the codec and served snapshots | `tokenizer_hash` (git-blob OID); the snapshot-embedded `chat_template` is printed as *not approved* | `GSJ_CODEC_SNAPSHOT`, `GSJ_SERVED_SNAPSHOT` (default: the Qwen3-0.6B snapshot in `~/.cache/huggingface/hub`) |
| the served `--chat-template` file | `chat_template_hash` — sha256 of the file the engine actually renders with | `GSJ_SERVED_TEMPLATE` (default `estate/serving/qwen3_training.jinja`) |
| `pins/g6_tail.captured.txt` | `g6_expected_tail` verbatim; `g6_expected_tail_ids` by tokenizing it with the served tokenizer | needs `transformers` and the served snapshot |
| `pins/thinking-on/pins.gsj.json`, `pins/thinking-on/g6_tail.captured.txt` | the sibling file: same key set, six non-G6 sets byte-equal, on-tail exactly the off-tail's first line, on-ids exactly the off-ids' first three | — |

**What fails loud** (a `FAIL` line, a `DIVERGED:` summary, exit 1): any derived value absent from its approved set; the thinking-on file diverging on a non-G6 key; the on-tail not being exactly the first line of the off-tail (a bare `startswith` was rejected deliberately — it passed a corrupted tail file); the on-ids not being the first three off-ids; a tokenized tail not matching the pinned ids. **What skips, and says so**: an absent snapshot directory, and the id re-verification when `transformers` is not importable — a skip prints `skip …` and never counts as a pass, because the tokenizer is expected to exist only on the serving host.

The walk closes by printing an *engine provenance* block — the served model name (asked of `GSJ_SERVED_ENDPOINT`'s `/v1/models` when that variable is set), the snapshot revision, and the sha256 of the served generation config, tokenizer and chat template; anything the host cannot measure is written as a named absence. `python pins/derive_pins.py --record` writes that block into both pins files under `provenance.engine`, and only after a walk that reproduced everything — it refuses if any approved value would move.

`pins/derive_g2.py` is the smaller tool behind `system_prompt_hash`. Its `--constant-path /workspace` mode takes an in-container capture of the system prompt, verifies the constant checkout path occurs in it and that **no** case id from `estate/corpus/staging/corpus.lock.json` does (the proof that the prompt is case-invariant, so one hash covers every case), and writes `pins/container/system_prompt.container.derived.txt` — removing it again if the read-back does not match byte-for-byte. Its `--work-root` mode is the per-case substitution for estates whose checkout path embeds the case id; there the approved set grows by one entry per case.

### Writing a file for another estate

The walk's evidence paths are the reference estate's. For your own estate you produce a `gsj-pins/1` document of your own and point `GSJ_PINS_PATH` at it — the format is the contract, the walk is the model. The practical sequence:

1. Bring the estate up and run one episode with the reference pins in place. It will quarantine, and each `*_not_approved:<digest>` finding carries the digest the gate computed. Read the quarantined body (`<quarantine_dir>/<session_id>.<pins_mode>.json`) and confirm that `trace.tools`, `prompt_messages[0].content`, and `metadata.gsj_settings` are what you intend the estate to run — pin what you have inspected, not whatever arrived.
2. Hash your own skill cards as bytes. The trainer computes `skill_card_hash` from the card text it submits, so read the file with `read_bytes().decode("utf-8")` — `read_text()` applies newline translation and the platform encoding, and either one changes the hash.
3. Take `tokenizer_hash` from the served snapshot's `tokenizer.json` and `chat_template_hash` from the template file the engine serves with.
4. Derive `g6_expected_tail` from that template's generation-prompt branch under your thinking mode, and `g6_expected_tail_ids` by tokenizing it with the served tokenizer, `add_special_tokens=False`.
5. Record a `provenance` block per key with the episode id or file each value came from, then restart both legs.

The conventions are short enough to copy verbatim from `pins/derive_pins.py`:

```python
import hashlib, json

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)

def sha256_canonical_json(obj) -> str:            # tool_roster_hash, settings_hash
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()

def sha256_bytes(data: bytes) -> str:             # system_prompt_hash, skill_card_hash, chat_template_hash
    return hashlib.sha256(data).hexdigest()

def git_blob_oid(data: bytes) -> str:             # tokenizer_hash
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()
```

> [!TIP]
> **Keep the anchor**
>
> Before trusting any value you compute, hash `pins/tools.captured.json` with `sha256_canonical_json` and check that it reproduces `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56`. If it does not, your canonicalization has drifted and every canonical-JSON hash you derive will be wrong in the same way.

## See also

- [Validation](validation.md) — what each gate protects against.
- [Finding vocabulary](../reference/findings.md) — the `*_not_approved` and `missing_evidence` strings.
- [Troubleshooting](../guides/troubleshooting.md#_not_approved--the-pins-do-not-describe-this-estate) — the `*_not_approved` findings by cause when a gate still fails after a re-pin.
- [Configuration](../guides/configuration.md#harness) — which `harness` keys feed which hash.
- [The receiver](../guides/receiver.md#on-disk) — how the pins file's `mode` reaches the file names.
