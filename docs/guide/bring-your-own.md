[← Documentation index](README.md)

# Bring your own model and corpus

Two procedures the library owns, written after a stranger walked them first (2026-09-06, library 0.1.9 from PyPI, the library's own scaffold as the corpus, a `qwen3.6-27b` endpoint nobody here operates): **[your model](#your-model)** — from an endpoint URL to the values `up` needs, and **[your pins](#your-pins)** — from the first quarantined episode to an accepted one. Each ends with a script you paste and run; each script *asserts* before it *derives*, and neither approves anything you did not inspect. That shape is the stranger's, kept on purpose: the values are cheap, the discipline is the point.

What this page assumes: a corpus in [the contract's shape](../corpus-contract.md) (start from `scaffold`), Docker whose daemon can run a container, and the estate tool — `estate/estate.py` in a checkout, `python -m gsj_rollout.estate` from the wheel (`pip install gsj-harness-rollout-server pyarrow`). Below, `$ESTATE` stands for whichever you have.

> [!NOTE]
> **Why a page and not a script in the wheel.** The wheel ships no documentation and only two force-included modules; a shipped script is a release. And the walk's load-bearing step is the one no script can do — reading the quarantined body and deciding that what ran is what you meant to approve. The stranger who proved this path refused to approve automatically; so do the scripts below (they stop on anything unexpected). `estate.py up` deliberately writes no pins ([corpus-contract.md](../corpus-contract.md)); this page does not change that. The one-command form for the reference-model case is the demo repo's `bootstrap.py`.

## Your model

`up` needs three things about your endpoint that only the endpoint can tell you, and a fourth list of things it cannot.

| value | where it goes | how it is measured |
| --- | --- | --- |
| the served name | `--engine-model` (`estate.model`) | `GET <base>/v1/models` → `data[].id`, byte-for-byte |
| the end-of-turn id | `--end-of-turn-token-id` (`builder.end_of_turn_token_id`) | `POST <base>/tokenize` of the template's end-of-turn marker, which must be **one** token, and which must close an assistant turn in the template's own render |
| the generation-prompt delta (G6's tail) | `g6_expected_tail_ids` in your pins file ([below](#your-pins)) | the ids `add_generation_prompt: true` adds to the same render with `false`, under the `chat_template_kwargs` pi sends |
| the thinking mode | `--thinking` (`harness.thinking`) | your decision; it changes the kwargs and therefore the tail — `off` unless the family has the mode; a non-off value is one of pi's levels (`medium` is the conventional ON — a bare `on` is refused at config load; [validation-and-pins.md](validation-and-pins.md#the-thinking-on-set)) |

`<base>` is the engine **root** — no `/v1`: Polar's proxy appends `/v1/chat/completions` itself, and `up` refuses a suffixed URL.

**The kwargs pi sends.** Every chat completion pi 0.83.0 issues carries `chat_template_kwargs: {"enable_thinking": <level != off>, "preserve_thinking": true}` ([checks-spec.md, the pi wire dialect](../checks-spec.md#the-pi-0830-wire-dialect-cp-06-measured); charter A-12). Measure the tail under exactly those kwargs — a render without them can differ by the whole think block on a Qwen3 template, and G6 compares ids, not intent. On a template that never reads `enable_thinking` (Llama-3.x, measured at CP-38) both modes render the same tail; the kwargs are then a wire no-op and `off` is the honest setting.

**What an endpoint cannot give you — say so, do not copy.** No OpenAI-compatible API exposes the bytes of `tokenizer.json` or of the served chat template (G4's two hashes), the weights revision, or the server's sampling defaults (pi sends no sampling parameters; whatever the server defaults to *is* your policy). The tool-call parser is a serve flag, not an API fact. Your pins file records these as **not measured** rather than carrying the reference model's values across, which would be a lie about your model. The estate-side G4 walk (`pins/derive_pins.py`, a checkout only) is where those are verified when you hold the snapshot; the demo's [`docs/MODEL-SURFACE.md`](https://github.com/MHGanainy/gsj-rollout-demo/blob/main/docs/MODEL-SURFACE.md) walks the whole surface item by item. What you *can* read: vLLM's `/v1/models` reports `max_model_len` — the context window.

**No `/tokenize` in its chat form?** The script needs vLLM's `/tokenize` with `messages`, `add_generation_prompt` and `chat_template_kwargs` — a tokenize endpoint that does not render the served template cannot give the delta. Without it the script below cannot run; derive the same two values from a local snapshot with `transformers` (MODEL-SURFACE's recipe) and record that the endpoint itself was not measured.

### The script

Paste it as `probe_model.py`. Stdlib only; asserts before it derives; writes `model-probe.json` (the request/response pairs and the derived values — keep it, the pins walk reads it).

```python
#!/usr/bin/env python3
"""bring-your-own.md#your-model: from an endpoint URL to the values `up` needs.
ENGINE=<engine root, no /v1>   MODEL=<served id> (optional when exactly one is served)
MARKER=<the template's end-of-turn token> (default <|im_end|>)   THINKING=off, or a pi level (default off; medium is the conventional ON — a bare "on" is not a level)
Writes ./model-probe.json. Every assert is a stop, not a warning: read it, do not guess past it."""
import json, os, urllib.request

root = os.environ["ENGINE"].rstrip("/")
assert not root.endswith("/v1"), "ENGINE is the engine ROOT (no /v1): the gateway appends /v1/chat/completions"
thinking = os.environ.get("THINKING", "off")
marker = os.environ.get("MARKER", "<|im_end|>")
results = {"engine": root, "thinking": thinking, "marker": marker, "requests": {}}


def call(path, payload=None):
    req = urllib.request.Request(root + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


# 1. the served name, byte-for-byte, from the endpoint itself
models = call("/v1/models")["data"]
served = [m["id"] for m in models]
assert served, "the endpoint lists no model: it is not up, or not OpenAI-compatible"
model = os.environ.get("MODEL") or (served[0] if len(served) == 1 else None)
assert model in served, f"MODEL must be one of {served} (set MODEL when several are served)"
results.update(model=model, served=served,
               max_model_len=next((m.get("max_model_len") for m in models if m["id"] == model), None))


def tokenize(label, **fields):
    payload = {"model": model, "add_special_tokens": False, **fields}
    body = call("/tokenize", payload)
    results["requests"][label] = {"request": payload, "response": body}
    return body["tokens"]


# 2. the end-of-turn id: the documented marker must be ONE token
eot = tokenize("marker", prompt=marker)
assert len(eot) == 1, f"{marker!r} tokenizes to {len(eot)} ids, not one: do not guess a replacement, read the served template"

# 3. the generation-prompt delta under the kwargs pi actually sends
kwargs = {"enable_thinking": thinking != "off", "preserve_thinking": True}
messages = [{"role": "user", "content": [{"type": "text", "text": "Hello."}]}]
base = tokenize("history_only", messages=messages, add_generation_prompt=False, chat_template_kwargs=kwargs)
full = tokenize("with_generation_prompt", messages=messages, add_generation_prompt=True, chat_template_kwargs=kwargs)
assert full[:len(base)] == base and len(full) > len(base), \
    "no clean, non-empty generation-prompt delta: this template has no G6 tail, and none must be pinned"
tail = full[len(base):]

# 4. the marker closes an assistant turn in the template's OWN render
closed = tokenize("assistant_closed", messages=messages + [{"role": "assistant", "content": "Hello."}],
                  add_generation_prompt=False, chat_template_kwargs=kwargs)
if closed[:len(full)] != full:
    print("WARNING: the history re-render does not extend the generation prompt: this template rewrites history;"
          " multi-turn episodes reconstruct as disconnected chains (G7) unless the lost span is constant"
          " (builder.generation_prompt_glue_ids) — see MODEL-SURFACE's prefix-extension section")
assert eot[0] in closed[len(base):], f"{marker!r} ({eot[0]}) never appears in the closed assistant turn: it is not this template's end-of-turn id"

results["derived"] = {
    "served_model": model,
    "end_of_turn_token_id": eot[0],
    "g6_expected_tail_ids": tail,
    "thinking": thinking,
    "not_measured": ["tokenizer_hash (G4: the bytes of tokenizer.json; no API exposes them)",
                     "chat_template_hash (G4: the bytes of the served template)",
                     "weights revision", "sampling policy (pi sends none; the server's defaults are it)",
                     "tool-call parser (a serve flag)"],
}
with open("model-probe.json", "w") as handle:
    json.dump(results, handle, indent=2)
print(f"served model          {model!r}  (of {served})")
print(f"end_of_turn_token_id  {eot[0]}  ({marker!r})")
print(f"g6_expected_tail_ids  {tail}  (thinking {thinking}: {kwargs})")
print(f"not measured          {', '.join(results['derived']['not_measured'])}")
print("written               model-probe.json")
```

Run it, then hand the values to `up`:

```bash
ENGINE=http://127.0.0.1:8100 python3 probe_model.py          # MODEL=… when several are served; MARKER=… off the Qwen family; THINKING=medium for a thinking-on estate
$ESTATE up --corpus <root> --engine-url http://127.0.0.1:8100 \
    --engine-model "<served model>" --end-of-turn-token-id <id> -y
```

`up` records both in the run's `rollout.yaml` (neither is binding: edit the file or re-run `up`). The tail ids are not `up`'s to write — they go into your pins file, next. What the stranger measured this way, for the record: `qwen3.6-27b`, `<|im_end|>` = **248046** (the reference model's is 151645), tail `[248045, 74455, 198, 248068, 271, 248069, 271]`; `up`'s warning had said the id "stays the Qwen3 default unless told otherwise" — this is how you tell it.

## Your pins

The wheel ships the **reference estate's** approved sets. On your corpus every episode quarantines — `G2:system_prompt_hash_not_approved:<hash>` for your `AGENTS.md`, `G1:skill_card_hash_not_approved:<hash>` for your skill cards on a skill row — and on a non-reference model `G6:prompt_suffix_ne_tail_ids` (and `G6:interstitial_ne_tail_ids:…` on later turns) for the tail. That first quarantine is not a failure; it is the evidence the walk reads. The order matters:

1. **Stand the estate up and start the three processes with the reference pins** (`GSJ_PINS_PATH` unset). `up`'s pins line already warns which cards the reference set lacks.
2. **Run one episode against the reference pins**, with a task id you will recognise:
   ```bash
   gsj-rollout submit --config <run>/rollout.yaml --from-bank <run>/taskbank.parquet --row 0 \
       --task-id pins-walk-reference --out <run>/first-attempt
   ```
   Expect `rejected <session_id>: [...]` and exit 1, with the receiver's copy at `<run>/traces/quarantine/<session_id>.thinking-off.json`. Row 0 of a scaffold is its free prompt; row 1 is the skill row.
3. **Inspect the quarantined body before approving anything.** The body is `{"findings": [...], "session_result": {...}}`. What you are checking is that *what ran is what you meant to approve* — the script below asserts the mechanical half, you read the rest:
   - `findings` holds **only** the expected `G1`/`G2`/`G6` kinds. Anything else — an `ADM*`, `LP*`, `G5*`, `G7*` finding — is a different problem; stop and read [troubleshooting.md](troubleshooting.md).
   - `session_result.status` is `COMPLETED`; `trajectory.metadata.reconstruction_stats` shows one chain, nothing truncated, every completion merged.
   - `prompt_messages` has exactly one `system` message, a string, and it contains your corpus's `AGENTS.md` bytes exactly once.
   - `tools` is the roster you expect (pi's fixed 11-tool roster on the reference harness); `metadata.gsj_settings` shows compaction disabled; `metadata.gsj_workspace` is shallow, has zero remotes, is on `timestep-<T>` and holds pages `1..T`.
   - the transcript: did the agent search and read (the `mcp_gsj_*` and `read` calls)? A tool-free green episode is legal but proves less.
4. **Derive from what actually ran**, with the script below. Its rules, each the stranger's:
   - `system_prompt_hash`: sha256 of the wire system prompt as **UTF-8 bytes**, only after the `AGENTS.md`-appears-once check.
   - `skill_card_hash`: sha256 of each `skills/<name>/SKILL.md` file's **raw bytes** (`read_bytes()`) — never `read_text()`, whose newline translation changes the hash.
   - `tool_roster_hash` and `settings_hash`: canonical-JSON sha256 (`sort_keys`, `(",", ":")` separators, `ensure_ascii=False`, `allow_nan=False`) of `tools` and `metadata.gsj_settings` — kept **only if they independently match the packaged reference**. A different value is a changed roster or changed harness settings: investigate, never approve automatically.
   - the canonicalization anchor: the reference roster hash is `a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56`, the canonical sha256 of `pins/tools.captured.json` in a checkout. Reproducing it from the trace's own `tools` array proves the canonicalization and the roster in one check; if your canonical hash of the same roster differs, every canonical-JSON hash you derive is wrong the same way.
   - `g6_expected_tail_ids`: the measured delta from [your model](#your-model) (the packaged value on the reference model) — accepted only if turn 1's opening ends with it and **every** later assistant turn's interstitial does too, exactly as G6 checks (`checks.check_thinking_tail`).
   - **record what was not measured.** The file carries `not_measured: [tokenizer.json identity, served chat-template bytes, weights revision]` instead of the reference model's codec hashes. This is the discipline the whole page exists for: an approved set states what was measured on *this* estate, and names what was not.
5. **Point both legs at the file and restart.** `GSJ_PINS_PATH` is read once per process, at the first import of `gsj_rollout.checks`; set it in the environment of the receiver (`gsj-rollout serve`) and of every trainer process (`gsj-rollout submit`, your `RolloutClient`), then restart the receiver. Polar's two processes read no pins; restarting them is harmless. A wrong path never falls back to the packaged copy — it raises `PinsConfigurationError` on first use.
6. **Submit again, a new task id**, and expect `collected 1/1 episodes`, exit 0. Then re-verify in a **separate process**: load the accepted body with the same `GSJ_PINS_PATH` and `checks.validate_session_result(body) == []`; the receiver's file, the rollout API's poll result and the trainer's export are the same bytes.

### The script

Paste it as `derive_my_pins.py` (the checkout's `pins/derive_pins.py` is a different tool: it re-verifies the reference set) and run it with `GSJ_PINS_PATH` **unset** (the comparison is against the reference set) and the same `python` the estate tool runs under (it imports `gsj_rollout`).

```python
#!/usr/bin/env python3
"""bring-your-own.md#your-pins: a gsj-pins/1 file from ONE inspected quarantined episode.
RUN=<run dir>  CORPUS=<corpus root>  PROBE=<model-probe.json from #your-model> (omit only on the reference model in thinking-off;
for a non-off level pass the probe you ran with that THINKING — the comparison set here is always the thinking-off reference)
BODY=<the inspected quarantine file> (optional when the quarantine holds exactly one)  MODE=thinking-on (only for a non-off level)
Every assert is a stop: it refuses to approve what it did not expect."""
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

assert "GSJ_PINS_PATH" not in os.environ, "unset GSJ_PINS_PATH: the derivation compares against the REFERENCE set"
from gsj_rollout import checks  # noqa: E402  (the packaged-pins UserWarning is expected here)

ANCHOR = "a7a7956b4842b79f8b20448d43bc8225eebe6360c3d1d3979d41c6f9b9948e56"
run, corpus = Path(os.environ["RUN"]), Path(os.environ["CORPUS"])
reference_path = Path(checks.PINS_PATH)
reference = json.loads(reference_path.read_bytes())["pins"]
assert ANCHOR in reference["tool_roster_hash"], f"{reference_path} is not the reference set this walk compares against"
sha = lambda data: hashlib.sha256(data).hexdigest()
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")

# the inspected body: named, or the only one
quarantine = sorted((run / "traces" / "quarantine").glob("*.json"))
source = Path(os.environ["BODY"]) if os.environ.get("BODY") else (quarantine[0] if len(quarantine) == 1 else None)
assert source, f"name the inspected body with BODY=<path> ({len(quarantine)} files in {run / 'traces' / 'quarantine'})"
wrapper = json.loads(source.read_bytes())
findings, result = wrapper["findings"], wrapper["session_result"]
expected = ("G1:skill_card_hash_not_approved:", "G2:system_prompt_hash_not_approved:",
            "G6:prompt_suffix_ne_tail_ids", "G6:interstitial_ne_tail_ids:")
unexplained = [f for f in findings if not f.startswith(expected)]
assert not unexplained, f"the body carries findings this walk does not explain: {unexplained} — stop and read them"
assert result["status"] == "COMPLETED", result["status"]
stats = result["trajectory"]["metadata"]["reconstruction_stats"]
assert stats["chains_total"] == 1 and stats["chains_reconstructed_truncated"] == 0, stats
assert stats["completions_merged"] == stats["completions_total"] == stats["raw_completions_total"], stats
traces = result["trajectory"]["traces"]
assert len(traces) == 1, f"{len(traces)} traces: inspect each; this walk approves from one"
trace = traces[0]

# G2: the wire system prompt, once, containing this corpus's AGENTS.md once
systems = [m["content"] for m in trace["prompt_messages"] if m["role"] == "system"]
assert len(systems) == 1 and isinstance(systems[0], str), "expected exactly one string system message"
agents = (corpus / "AGENTS.md").read_bytes().decode("utf-8")
assert systems[0].count(agents) == 1, "the wire system prompt does not embed this corpus's AGENTS.md exactly once"

# G3 and G7's settings clause: kept only when they independently match the reference
roster = sha(canonical(trace["tools"]))
settings = sha(canonical(trace["metadata"]["gsj_settings"]))
assert roster in reference["tool_roster_hash"], f"tool roster {roster} is not the reference's: investigate, never approve automatically"
assert settings in reference["settings_hash"], f"harness settings {settings} are not the reference's: investigate, never approve automatically"
assert roster == ANCHOR, "the canonicalization anchor did not reproduce from the trace's tools array"

# G6: the tail, checked exactly as the validator checks it (turn 1 at the prompt's end, later turns at their interstitial)
probe = json.loads(Path(os.environ["PROBE"]).read_bytes())["derived"] if os.environ.get("PROBE") else None
tail = probe["g6_expected_tail_ids"] if probe else reference["g6_expected_tail_ids"][0]
ids, mask = trace["response_ids"], trace["loss_mask"]
starts = [i for i, f in enumerate(mask) if f == 1 and (not i or mask[i - 1] != 1)]
ends = [i + 1 for i, f in enumerate(mask) if f == 1 and mask[i + 1:i + 2] != [1]]
assert starts, "no trainable turn in the trace"
for turn, start in enumerate(starts, 1):
    opening = (trace["prompt_ids"] + ids[:start]) if turn == 1 else ids[ends[turn - 2]:start]
    assert opening[-len(tail):] == tail, f"turn {turn}'s opening does not end with the tail {tail}"

# G1: the cards, raw bytes
cards = sorted(corpus.glob("skills/*/SKILL.md"))
assert cards, f"no skills/<name>/SKILL.md under {corpus}"

pins = {
    "format": "gsj-pins/1",
    "derived_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "host": f"{run}: derived by docs/guide/bring-your-own.md#your-pins from the inspected body {source.name}",
    "pins": {
        "system_prompt_hash": [sha(systems[0].encode("utf-8"))],
        "tool_roster_hash": [roster],
        "settings_hash": [settings],
        "skill_card_hash": [sha(card.read_bytes()) for card in cards],
        "g6_expected_tail_ids": [tail],
    },
    "provenance": {
        "system_prompt_hash": {"algo": "sha256 of the wire system prompt as UTF-8 bytes; the corpus AGENTS.md verified present once",
                               "artifacts": [str(source), str(corpus / "AGENTS.md")]},
        "tool_roster_hash": {"algo": "canonical-JSON sha256 of trace.tools; equals the reference roster and the a7a7956b anchor",
                             "artifacts": [str(source), str(reference_path)]},
        "settings_hash": {"algo": "canonical-JSON sha256 of trace.metadata.gsj_settings; equals the reference value",
                          "artifacts": [str(source), str(reference_path)]},
        "skill_card_hash": {"algo": "sha256 of each card's raw file bytes", "artifacts": [str(card) for card in cards]},
        "g6_expected_tail_ids": {"algo": ("the live /tokenize add_generation_prompt delta under pi's kwargs (model-probe.json)"
                                          if probe else "the packaged reference tail (the reference model)")
                                         + "; matched at every turn opening of the inspected body",
                                 "artifacts": [os.environ.get("PROBE", str(reference_path)), str(source)]},
    },
    "not_measured": ["tokenizer_hash (G4: tokenizer.json identity)", "chat_template_hash (G4: the served template's bytes)",
                     "weights revision", "sampling policy"],
    "walk_status": {"derive": f"done here, from {source.name}",
                    "re_pin": "re-run this script from a fresh quarantined episode after any corpus, harness, model or mode change",
                    "first_episode_validate": "yours: the next submit under GSJ_PINS_PATH must collect 1/1"},
}
if os.environ.get("MODE"):
    pins["mode"] = os.environ["MODE"]
out = run / "pins.gsj.json"
out.write_text(json.dumps(pins, indent=2) + "\n")
print(f"written  {out}")
print(json.dumps(pins["pins"], indent=2))
print("not measured:", ", ".join(pins["not_measured"]))
```

Then the restart and the second episode:

```bash
export RUN=<run dir>; export GSJ_PINS_PATH=$RUN/pins.gsj.json   # in the receiver's shell AND the trainer's
gsj-rollout serve --config $RUN/rollout.yaml &                     # its own terminal in practice: serve runs until Ctrl-C
gsj-rollout submit --config $RUN/rollout.yaml --from-bank $RUN/taskbank.parquet --row 0 \
    --task-id pins-walk-accepted --out $RUN/accepted
python3 - "$RUN/accepted" <<'PY'                # a separate process re-verifies what the receiver accepted
import json, sys
from pathlib import Path
from gsj_rollout import checks
body = json.loads(next(Path(sys.argv[1]).glob("*.json")).read_bytes())
print(checks.PINS_PATH, checks.validate_session_result(body))     # your file, and []
PY
```

### What the walk proves, and what it does not

Proved by the stranger (2026-09-06: `pip install` → scaffold → `up` → one episode quarantined `G2` + `G6` on `qwen3.6-27b` → inspected → derived → restarted → `collected 1/1`, findings `[]` in a fresh process, the receiver's, the poll's and the trainer's bodies equal) and re-walked at CP-92 on a workstation estate against the reference model (CP-92's `#your-model` script re-measured the stranger's `qwen3.6-27b` endpoint read-only and both reference modes; CP-92's accepted episode is the reference model's). Across the two walks: the library's own scaffold, a model the library never measured, one accepted episode. Not proved: a training run consuming such episodes; the skill row, unless you ran it (its G1 hash is derived from the card's bytes either way); the estate-side G4 walk, which needs the snapshot and a checkout. A re-pin is the same walk from a fresh quarantined episode — after any change to `AGENTS.md`, a skill card, the harness settings, the model, its template, or the thinking mode; `estate.py update` says out loud when a corpus edit moves G1 or G2.

## See also

- [validation-and-pins.md](validation-and-pins.md) — the `gsj-pins/1` format, the resolution order, the thinking-on set, the complete finding vocabulary.
- [server-guide.md](server-guide.md) — the YAML the values land in, and the estate section for `up`.
- [troubleshooting.md](troubleshooting.md) — every finding family, and the refusals `up` can print on the way here.
- [checks-spec.md](../checks-spec.md) — why each gate exists, the hashing conventions, the pi wire dialect these kwargs come from.
