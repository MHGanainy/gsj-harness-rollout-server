[← Documentation index](README.md)

# Bring your own model and corpus

Two procedures the library owns, written after a stranger walked them first (2026-09-06, library 0.1.9 from PyPI, the library's own scaffold as the corpus, a `qwen3.6-27b` endpoint nobody here operates) and reproduced independently twice the next day at 0.1.10 (round three — [the end of the page](#what-the-walk-proves-and-what-it-does-not)): **[your model](#your-model)** — from an endpoint URL to the values `up` needs, and **[your pins](#your-pins)** — from the first quarantined episode to an accepted one. Each ends with a script you paste and run; each script *asserts* before it *derives*, and neither approves anything you did not inspect. That shape is the stranger's, kept on purpose: the values are cheap, the discipline is the point.

What this page assumes: a corpus in [the contract's shape](../corpus-contract.md) (start from `scaffold`), Docker whose daemon can run a container **and can pull, or already holds, the three images `up` needs** — Forgejo (~80 MB compressed, 277 MB extracted), the retrieval service `ghcr.io/mhganainy/gsj-mcp-service:0.5.0` (1.28 GiB compressed: tens of minutes on a slow pipe; `up` pulls both of these itself and prints a heartbeat while it waits) and the per-episode sandbox `ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3` (200 MiB compressed), which `up` **never pulls**: pull it yourself first, or `up` refuses — before anything is created, since CP-94; a round-three stranger met that refusal after 41 minutes of pipeline — and the estate tool — `estate/estate.py` in a checkout, `python -m gsj_rollout.estate` from the wheel (`pip install gsj-harness-rollout-server pyarrow`). Below, `$ESTATE` stands for whichever you have. **And one thing this page owes you before you start (CP-99):** everything here — the corpus, the estate, the pins — works from the wheel alone, but the *episode* at the end of the walk does not. Episode execution is Polar's, which ships in no Python artifact; you need a checkout's `vendor/polar` venv or the demo's published `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14`. Two round-five strangers filed this independently from the PyPI door — one after standing a whole estate from the wheel — and that one ranked it first of everything it found.

> [!NOTE]
> **Why a page and not a script in the wheel.** The wheel ships no documentation and only two force-included modules; a shipped script is a release. And the walk's load-bearing step is the one no script can do — reading the quarantined body and deciding that what ran is what you meant to approve. The stranger who proved this path refused to approve automatically; so do the scripts below (they stop on anything unexpected). `estate.py up` deliberately writes no pins ([corpus-contract.md](../corpus-contract.md)); this page does not change that. What it writes since 0.1.12 (CP-97, ADR-0042) is the **skeleton** — `<run>/pins.skeleton.json` beside `rollout.yaml`: the two carried sets from the pins in force, the tail and the end-of-turn id measured from your endpoint's own render, the two derived sets and G4's empty, `not_measured` and `coverage` stated — under a format (`gsj-pins-skeleton/1`) the library refuses on first use and `up` refuses before anything runs, so nothing consumes it as pins by accident. The script in [your pins](#your-pins) reads it; the judgement stays yours. The one-command form for the reference-model case is the demo repo's `bootstrap.py`.

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

**What an endpoint cannot give you — say so, do not copy.** No OpenAI-compatible API exposes the bytes of `tokenizer.json` or of the served chat template (G4's two hashes), the weights revision, or the server's sampling defaults (pi sends no sampling parameters; whatever the server defaults to *is* your policy). The tool-call parser's *identity* is a serve flag, not an API fact — its *presence* is: one 16-token chat completion with `tool_choice: auto` tells you whether the engine was served with `--enable-auto-tool-choice`/`--tool-call-parser` at all, and the script's step 5 asks, because the alternative is learning it from an ERRORed episode on an endpoint only its operator can fix ([the borrowed endpoint](#the-borrowed-endpoint)). Your pins file records these as **not measured** rather than carrying the reference model's values across, which would be a lie about your model. The estate-side G4 walk (`pins/derive_pins.py`, a checkout only) is where those are verified when you hold the snapshot; the demo's [`docs/MODEL-SURFACE.md`](https://github.com/MHGanainy/gsj-rollout-demo/blob/main/docs/MODEL-SURFACE.md) walks the whole surface item by item. What you *can* read: vLLM's `/v1/models` reports `max_model_len` — the context window.

**No `/tokenize` in its chat form?** The script needs vLLM's `/tokenize` with `messages`, `add_generation_prompt` and `chat_template_kwargs` — a tokenize endpoint that does not render the served template cannot give the delta. Without it the script below cannot run; derive the same two values from a local snapshot with `transformers` (MODEL-SURFACE's recipe) and record that the endpoint itself was not measured.

### The script

Paste it as `probe_model.py`. Stdlib only; asserts before it derives; writes `model-probe.json` (the request/response pairs and the derived values — keep it, the pins walk reads it).

```python
#!/usr/bin/env python3
"""bring-your-own.md#your-model: from an endpoint URL to the values `up` needs.
ENGINE=<engine root, no /v1>   MODEL=<served id> (optional when exactly one is served)
MARKER=<the template's end-of-turn token> (default <|im_end|>)   THINKING=off, or a pi level (default off; medium is the conventional ON — a bare "on" is not a level)
Writes ./model-probe.json. Every assert is a stop, not a warning: read it, do not guess past it."""
import json, os, urllib.error, urllib.request

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

# 5. can this endpoint actually run an episode? pi always sends tool_choice: auto, and the
#    capture needs logprobs — one 16-token completion answers both (a round-three stranger
#    wrote this check itself; it took one second, and the alternative is an ERRORed episode)
probe = {"model": model, "messages": [{"role": "user", "content": "Say OK."}],
         "max_tokens": 16, "tool_choice": "auto", "logprobs": True,
         "tools": [{"type": "function", "function": {"name": "ping", "description": "ping",
                    "parameters": {"type": "object", "properties": {}}}}],
         "chat_template_kwargs": kwargs}
try:
    body = call("/v1/chat/completions", probe)
except urllib.error.HTTPError as exc:
    # HTTP 400 here means the engine was served WITHOUT --enable-auto-tool-choice /
    # --tool-call-parser: every episode will ERROR, and only the engine's operator can fix
    # it. The body's message reads: "auto" tool choice requires --enable-auto-tool-choice and
    # --tool-call-parser to be set (vLLM wraps it as {"object":"error","message":…}, vllm-metal
    # as {"error":{"message":…}} — measured on both, CP-94)
    raise SystemExit(f"chat completion with tool_choice=auto -> HTTP {exc.code}: "
                     f"{exc.read().decode(errors='replace')[:300]}\n"
                     "this engine cannot run an episode as served; its operator must add the two flags")
assert (body["choices"][0].get("logprobs") or {}).get("content"), "no logprobs: the capture has nothing to record"
results["requests"]["episode_probe"] = {"request": probe, "response": body}

results["derived"] = {
    "served_model": model,
    "end_of_turn_token_id": eot[0],
    "g6_expected_tail_ids": tail,
    "thinking": thinking,
    "not_measured": ["tokenizer_hash (G4: the bytes of tokenizer.json; no API exposes them)",
                     "chat_template_hash (G4: the bytes of the served template)",
                     "weights revision", "sampling policy (pi sends none; the server's defaults are it)",
                     "tool-call parser IDENTITY (a serve flag; its presence was probed in step 5)"],
}
with open("model-probe.json", "w") as handle:
    json.dump(results, handle, indent=2)
print(f"served model          {model!r}  (of {served})")
print(f"end_of_turn_token_id  {eot[0]}  ({marker!r})")
print(f"g6_expected_tail_ids  {tail}  (thinking {thinking}: {kwargs})")
print(f"episode probe         tool_choice=auto accepted, logprobs present "
      f"({len(body['choices'][0]['logprobs']['content'])} tokens) — this endpoint can run an episode")
print(f"not measured          {', '.join(results['derived']['not_measured'])}")
print("written               model-probe.json")
```

Run it, then hand the served model's name to `up` — since 0.1.12 `up` measures the end-of-turn id and the tail itself:

```bash
ENGINE=http://127.0.0.1:8100 python3 probe_model.py          # MODEL=… when several are served; MARKER=… off the Qwen family; THINKING=medium for a thinking-on estate
mkdir -p runs                # `up` REFUSES to create its own runs root (CP-90): from a wheel
                             # that root is ./runs, and on a fresh box it does not exist yet.
                             # `--runs-dir <dir>` names another; the refusal says both.
$ESTATE up --corpus <root> --engine-url http://127.0.0.1:8100 \
    --engine-model "<served model>" -y          # no --end-of-turn-token-id: up measures it (0.1.12+)
```

`up` records both in the run's `rollout.yaml` (neither is binding: edit the file or re-run `up`). Pass `--end-of-turn-token-id <id>` only to override the measurement (on wheels through 0.1.11, which do not measure it, pass the probe's id): an explicit value wins in `rollout.yaml` and persists across re-runs, while `up` still prints its own measurement beside it and warns if the two disagree — a cross-check, which is how round seven's library-door b1 used it (its own probe's id passed, `up`'s measurement agreeing, no warning). This block showed the flag on every `up` through CP-103, stale beside the measurement described next. **Since 0.1.12 `up` performs this measurement itself** (step 3 under the same kwargs, for the `--thinking` level it is given, and the end-of-turn id taken as the first non-whitespace token the template emits after assistant content in a closed render — the demo's rule, not step 2's known-marker check; without `/detokenize` the tail is measured and the id is not, said so): `builder.end_of_turn_token_id` takes the measured id unless `--end-of-turn-token-id` says otherwise (an explicit value persists across re-runs and a disagreement is warned about), the engine phase prints both values, and both land in `<run>/pins.skeleton.json` with every request/response pair — so from 0.1.12 on this script is the read-only check you run *before* `up`, and step 5 (the tool-choice probe) is the part `up` still does not do. On wheels through 0.1.11 the tail ids are not `up`'s to write — they go into your pins file, next. What the stranger measured this way, for the record: `qwen3.6-27b`, `<|im_end|>` = **248046** (the reference model's is 151645), tail `[248045, 74455, 198, 248068, 271, 248069, 271]`; `up`'s warning through 0.1.11 said the id "stays the Qwen3 default unless told otherwise" — this is how you told it, and since 0.1.12 it is measured.

## Polar's two processes

`up` stands the estate; it does not run episodes. That last step is Polar's, and
Polar publishes no Python artifact — the boundary named in the assumptions above.
Two routes reach it, and **round six's two library-door strangers took one each,
independently, without being asked**. Both ranked what was missing here first of
everything they found: naming the image (CP-99, register row 108) was *necessary
and is not sufficient*, because a named image you cannot invoke is still a wall.
The invocations below are the first stranger's, verified rather than invented —
it derived them from the image and the vendored source and wrote, accurately,
*"Commands (mine; no page contains them)"*.

### Route A — the published image

`ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14` is public and anonymously
pullable, and carries this release's wheel beside Polar. `$RUN` is your run
directory (`<runs>/<name>`), `$RUNS_PARENT` the directory that holds it.

```bash
docker run -d --name gsj-polar-rollout --network host \
  -v "$RUNS_PARENT:$RUNS_PARENT" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14 \
  polar serve_rollout -c "$RUN/topology.rendered.yaml"

mkdir -p "$RUNS_PARENT/polar-sessions"          # the session dir, host-side — see TMPDIR below
docker run -d --name gsj-polar-gateway --network host \
  -v "$RUNS_PARENT:$RUNS_PARENT" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e TMPDIR="$RUNS_PARENT/polar-sessions" \
  --env-file <(grep '^GSJ_MCP_TOKEN_SECRET=' "$RUN/.env" | sed "s/'//g") \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14 \
  polar serve_gateway -c "$RUN/topology.rendered.yaml"
```

What each flag is for — this is the content the boundary owes you:

- **`--network host`** — with `--polar-leg host` (the default) `rollout.yaml` binds
  the rollout API and the receiver on loopback and advertises the gateway at the
  address `up` measured. Sharing the host's network namespace makes all four of
  those addresses true inside the container **without re-addressing a single key**.
  It is the whole reason not to take `--polar-leg container`, which asks you to
  re-address four values by hand.
- **`-v "$RUNS_PARENT:$RUNS_PARENT"`, at the identical path** — `topology.rendered.yaml`,
  `harness.artifacts_dir` and `receiver.traces_dir` are absolute *host* paths. The
  container must see them at the same string, or Polar writes evidence somewhere
  the host cannot read.
- **`-v /var/run/docker.sock`** — `serve_gateway` starts one sandbox container per
  episode, as a sibling on the host daemon. No page said this; the Docker CLI baked
  into the image is the only hint, and a hint is not a document.
- **`-e TMPDIR=<a path bind-mounted identically>`** — the flag that does not announce
  itself, and the one that cost round six an episode. Polar `mkdtemp`s each session
  directory under the **gateway process's** `$TMPDIR` and bind-mounts it into the
  sandbox through the socket, so the *daemon* must be able to resolve that path.
  A containerised gateway's default `/tmp/session-…` does not exist on the host; the
  daemon silently creates an empty host directory and mounts that instead, and the
  episode fails in the worst possible way — see
  [a whole episode marked ERROR](troubleshooting.md#a-containerised-gateway-and-tmpdir).
  Point `TMPDIR` at a directory that is bind-mounted at its own path, as above. It is
  empty between episodes, and that is correct: Polar removes each session's directory
  when the session ends, and what an episode leaves is under `<artifacts_dir>/<session_id>/`
  ([troubleshooting.md](troubleshooting.md): *the log the table points at is already gone* — round seven's b1 found
  its `polar-sessions/` empty after three episodes and could not tell whether anything
  had been lost).
- **`--env-file` with the quotes stripped** — the secret goes on the **gateway line
  only** ([server-guide.md](server-guide.md)). `estate.py` writes its `.env` as
  `KEY='value'`, and **compose's dotenv parser strips those quotes while
  `docker run --env-file` does not**: pipe the file in unedited and the gateway
  holds a 66-character secret against the retrieval service's 64-character one,
  every `search_case` returns 401, and the episode completes *green with no
  retrieved pages* — the one failure mode nothing in the trace names. The stranger
  caught it only by measuring inside the container
  (`docker exec gsj-polar-gateway sh -c 'echo ${#GSJ_MCP_TOKEN_SECRET}'` → 64).
  The `<(…)` form is bash's; in `sh`, write the filtered file out first — under
  `umask 077`, because that file is the secret in clear and the recipe copies it out of
  a `0600` `.env` (round seven's b1 added the `umask` itself and asked the page to).

Check both came up before submitting — the gateway must have *registered* with the
rollout API, not merely started:

```bash
docker run --rm --network host -v "$RUNS_PARENT:$RUNS_PARENT" \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14 \
  polar status -c "$RUN/topology.rendered.yaml"     # Registered Nodes: 1, the gateway [UP] under it
```

### Route B — a checkout

The other stranger never pulled the image: the container recipe lived in a repo it
had been told not to read, so it took the documented checkout route instead, and
reached the same accepted episode.

```bash
git clone https://github.com/MHGanainy/gsj-harness-rollout-server
cd gsj-harness-rollout-server/vendor/polar && uv venv && uv pip install -e .
```

Then Polar's two processes are the ones `gsj-rollout serve` prints, run from that
venv with the checkout on `PYTHONPATH` (`vendor/REVENDOR.md` carries the recipe,
including the A-14 `gsj_rollout` install).

> [!NOTE]
> **What `gsj-rollout serve` prints, and why it does not say this.** From a wheel,
> `serve`'s `NOTE:` names only a `<checkout>` and spells no image. `estate.py`'s
> closing block — one command earlier — spells the pullable reference and links this
> section since CP-104; through 0.1.14 it said only "the published gsj-polar image"
> and named a second repository, which round seven's b1 filed first of everything it
> found (the string existed on the PyPI page and on this page only). A round-six
> stranger had hit the `serve`/`up` disagreement before it. They still do not match:
> `gsj_rollout/cli.py` is inside the 2,034-line size law, whose headroom is zero by
> design, so the `serve` line is register row 108's standing residue rather than an
> oversight. This page is where the recipe lives until a checkpoint funds the line.

## Your pins

The wheel ships the **reference estate's** approved sets. On your corpus every episode quarantines — `G2:system_prompt_hash_not_approved:<hash>` for your `AGENTS.md`, `G1:skill_card_hash_not_approved:<hash>` for your skill cards on a skill row — and on a non-reference model `G6:prompt_suffix_ne_tail_ids` (and `G6:interstitial_ne_tail_ids:…` on later turns) for the tail. That first quarantine is not a failure; it is the evidence the walk reads. The order matters:

1. **Stand the estate up and start the three processes with the reference pins** (`GSJ_PINS_PATH` unset) — the receiver is `gsj-rollout serve` from the wheel, and Polar's two are [above](#polars-two-processes). `up`'s pins line already warns which cards the reference set lacks — and since 0.1.12 it has written `<run>/pins.skeleton.json`, which step 4's script reads and which `GSJ_PINS_PATH` must never name (`up` refuses one before anything runs; the library refuses it on first use — the first hash gate a `COMPLETED` body reaches, *after* the admission gates: validating `{}` against it returns `ADM1`/`ADM3` and no refusal, which is not the test — round seven's b1 nearly filed it as one).
2. **Run one episode against the reference pins**, with a task id you will recognise:
   ```bash
   gsj-rollout submit --config <run>/rollout.yaml --from-bank <run>/taskbank.parquet --row 0 \
       --task-id pins-walk-reference --out <run>/first-attempt
   ```
   Expect `rejected <session_id>: [...]` and exit 1, with the receiver's copy at `<run>/traces/quarantine/<session_id>.thinking-off.json`. The bank is sorted by `(case_id, timestep, prompt_id)`, so `free:` rows precede `skill:` rows *within a timestep* — on a scaffold that makes row 0 the free prompt and row 1 the skill row, and on your own corpus it makes row 0 whatever sorts first (round seven's b1 would have landed on an `eval` row of the wrong case). Read your bank before choosing `--row`: since CP-104 `up`'s closing block and `status` list every row as `--row N case@T prompt_id [split]`.
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
   - `g6_expected_tail_ids`: the measured delta from [your model](#your-model) — since 0.1.12 the skeleton's, measured by `up`; `model-probe.json` when you ran the probe (the two must agree); the packaged value on the reference model — accepted only if turn 1's opening ends with it and **every** later assistant turn's interstitial does too, exactly as G6 checks (`checks.check_thinking_tail`).
   - **record what was not measured.** The file carries `not_measured` — the skeleton's list when one was read (tokenizer.json identity, the served template's bytes, the weights revision, the sampling policy, the tool-call parser's identity and, unless step 5 ran, its presence), else the fixed four — instead of the reference model's codec hashes. This is the discipline the whole page exists for: an approved set states what was measured on *this* estate, and names what was not.
5. **Point both legs at the file and restart.** `GSJ_PINS_PATH` is read once per process, at the first import of `gsj_rollout.checks`; set it in the environment of the receiver (`gsj-rollout serve`) and of every trainer process (`gsj-rollout submit`, your `RolloutClient`), then restart the receiver. Polar's two processes read no pins; restarting them is harmless. A wrong path never falls back to the packaged copy — it raises `PinsConfigurationError` on first use.
6. **Submit again, a new task id**, and expect `collected 1/1 episodes`, exit 0. Then re-verify in a **separate process**: load the accepted body with the same `GSJ_PINS_PATH` and `checks.validate_session_result(body) == []`; the receiver's file, the rollout API's poll result and the trainer's export are the same bytes.

### The script

Paste it as `derive_my_pins.py` (the checkout's `pins/derive_pins.py` is a different tool: it re-verifies the reference set) and run it with `GSJ_PINS_PATH` **unset** (the comparison is against the reference set) and the same `python` the estate tool runs under (it imports `gsj_rollout`).

```python
#!/usr/bin/env python3
"""bring-your-own.md#your-pins: a gsj-pins/1 file from ONE inspected quarantined episode.
RUN=<run dir>  CORPUS=<corpus root>
SKELETON=<pins.skeleton.json> (default <run>/pins.skeleton.json when `up` wrote one — since 0.1.12, ADR-0042: the carried sets,
the tail and end-of-turn id measured from your endpoint, the endpoint's provenance; read here, never named by GSJ_PINS_PATH)
PROBE=<model-probe.json from #your-model> (the tail's other source — needed when no skeleton measured one; omit on the reference
model in thinking-off; for a non-off level pass the probe you ran with that THINKING — the comparison set here is always the
thinking-off reference)   BODY=<the inspected quarantine file> (optional when the quarantine holds exactly one)
MODE=thinking-on (only for a non-off level; a skeleton written for one carries it)
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
# the skeleton `up` writes since 0.1.12: read, checked against the reference, never approved from
skeleton_path = Path(os.environ["SKELETON"]) if os.environ.get("SKELETON") else run / "pins.skeleton.json"
skeleton = json.loads(skeleton_path.read_bytes()) if skeleton_path.is_file() else None
assert not os.environ.get("SKELETON") or skeleton, f"SKELETON={skeleton_path} does not exist: name the pins.skeleton.json `up` wrote, or unset SKELETON for <run>/pins.skeleton.json"
if skeleton:
    assert skeleton.get("format") == "gsj-pins-skeleton/1", f"{skeleton_path} is not a pins skeleton (format {skeleton.get('format')!r})"
    for key in ("tool_roster_hash", "settings_hash"):
        assert skeleton["pins"][key] == reference[key], f"the skeleton's {key} is not the reference's: it was written under another pins file — investigate"
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
measured = skeleton["pins"]["g6_expected_tail_ids"][0] if skeleton and skeleton["pins"]["g6_expected_tail_ids"] else None
if probe and measured:
    assert probe["g6_expected_tail_ids"] == measured, (f"model-probe.json ({probe['g6_expected_tail_ids']}) and the skeleton ({measured}) "
                                                        "measured different tails: the endpoint or the thinking level changed between them")
tail = probe["g6_expected_tail_ids"] if probe else measured if measured else reference["g6_expected_tail_ids"][0]
tail_source = ("the live /tokenize add_generation_prompt delta under pi's kwargs (model-probe.json)" if probe
               else f"the endpoint's own render as `up` measured it ({skeleton_path.name})" if measured
               else "the packaged reference tail (the reference model)")
tail_artifact = os.environ.get("PROBE") or (str(skeleton_path) if measured else str(reference_path))
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
    "host": (f"{run}: derived by docs/guide/bring-your-own.md#your-pins from the inspected body {source.name}"
             + (f", starting from the skeleton `up` wrote ({skeleton_path.name})" if skeleton else "")),
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
        "g6_expected_tail_ids": {"algo": tail_source + "; matched at every turn opening of the inspected body",
                                 "artifacts": [tail_artifact, str(source)]},
    },
    # what was not measured: the skeleton's own list when one was read (the tail was matched above), else the fixed four
    "not_measured": [("tool-call parser IDENTITY (a serve flag; its presence was probed in step 5)" if probe and "tool-call parser" in n else n)
                     for n in skeleton["not_measured"] if not n.startswith(("g6_expected_tail_ids", "end_of_turn_token_id"))] if skeleton
                    else ["tokenizer_hash (G4: tokenizer.json identity)", "chat_template_hash (G4: the served template's bytes)",
                          "weights revision", "sampling policy"],
    # what an acceptance under this file covers, per set (bring-your-own.md#what-an-acceptance-covers)
    "coverage": {
        "skill_card_hash": "derived here from this corpus's cards (G1); checked on every trace",
        "system_prompt_hash": "derived here from the inspected body's wire prompt (G2); checked on every trace",
        "tool_roster_hash": "carried from the reference — asserted equal above; checked on every trace (G3)",
        "settings_hash": "carried from the reference — asserted equal above; checked on every trace (G7's settings clause)",
        "g6_expected_tail_ids": ("derived here from the endpoint's own render (G6); checked on every trace" if probe or measured
                                 else "the packaged reference tail (G6); checked on every trace"),
        "tokenizer_hash": "NOT MEASURED — no approved set; nothing on this estate checks it (G4 is estate-side)",
        "chat_template_hash": "NOT MEASURED — no approved set; nothing on this estate checks it (G4 is estate-side)",
        "sampling_policy": "UNKNOWN — pi sends none; the endpoint's defaults are the policy; no gate covers it",
    },
    "walk_status": {"derive": f"done here, from {source.name}",
                    "re_pin": "re-run this script from a fresh quarantined episode after any corpus, harness, model or mode change",
                    "first_episode_validate": "yours: the next submit under GSJ_PINS_PATH must collect 1/1"},
}
if skeleton:
    engine = skeleton["provenance"]["engine"]
    if engine["served_model"]["served"]:
        pins["provenance"]["engine"] = engine     # the endpoint as `up` probed it
    else:
        print(f"engine block NOT carried: `up` probed {engine['served_model']['id']!r} before it was served — re-run `up` to refresh the skeleton")
    print(f"skeleton read {skeleton_path} (tail {'measured by up' if measured else 'not measured by up'})")
if os.environ.get("MODE") or (skeleton and skeleton.get("mode")):
    pins["mode"] = os.environ.get("MODE") or skeleton["mode"]
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

Proved by the stranger (2026-09-06: `pip install` → scaffold → `up` → one episode quarantined `G2` + `G6` on `qwen3.6-27b` → inspected → derived → restarted → `collected 1/1`, findings `[]` in a fresh process, the receiver's, the poll's and the trainer's bodies equal) and re-walked at CP-92 on a workstation estate against the reference model (CP-92's `#your-model` script re-measured the stranger's `qwen3.6-27b` endpoint read-only and both reference modes; CP-92's accepted episode is the reference model's). Round three (2026-09-07, four containerised strangers on 0.1.10, the same `qwen3.6-27b` endpoint) reproduced both sections independently, twice: one stranger on the library's own scaffold derived `G2: 8b159eb8…` — the value CP-92 measured and round two's stranger measured before it — and `G1: c1ade0f2…`; another wrote its own six-page corpus, got a different G2 (`f1603bea…`) and G1 (`cc6509b3…`) correctly, ran the skill row, and both landed on the identical tail `[248045, 74455, 198, 248068, 271, 248069, 271]` and eot `248046`, with the roster `a7a7956b…` and settings `dae89485…` matched to the reference. Different hosts, corpora, models, agents; same procedure, same answers (one of them also noticed that this page publishes those very answers for that very endpoint, said so before running, and turned the walk into a check that they are still right — they were; the fix for the experiment is a different endpoint, not a page that withholds its measurements). Across the walks: the library's own scaffold and a stranger's corpus, a model the library never measured, five accepted episodes. Round four (2026-09-08, two more B-door strangers on 0.1.11, the same borrowed endpoint) walked it a third and fourth time: both derived the same file, both reached `collected 1/1` — one of them after `up` had died at the gateway-host probe one file short of `rollout.yaml` and resumed with `--gateway-host` (fixed as a class at CP-96), and one of them measured the endpoint's values before cloning so its own walk stayed a measurement. That stranger also asked why `up` writes no pins at all when it already holds the skeleton — the two carried hashes, the tail it measures, the `not_measured` and `coverage` blocks — leaving only the two hashes an inspected episode supplies; CP-96 argued it (ADR-0042) and CP-97 built it, shipped in 0.1.12: `up` writes that skeleton as `<run>/pins.skeleton.json`, beside the run's own `rollout.yaml` and never as `pins.gsj.json` — with the tail and the end-of-turn id measured from the endpoint's own render (which is also how `builder.end_of_turn_token_id` stopped defaulting to the reference model's), under a format both the library and `up` refuse as pins — so the file the gates read still comes from a person who read a quarantined body, and the script above starts from what was measured. Not proved: a training run consuming such episodes; the skill row, unless you ran it (its G1 hash is derived from the card's bytes either way); the estate-side G4 walk, which needs the snapshot and a checkout. A re-pin is the same walk from a fresh quarantined episode — after any change to `AGENTS.md`, a skill card, the harness settings, the model, its template, or the thinking mode; `estate.py update` says out loud when a corpus edit moves G1 or G2.

## What an acceptance covers

`collected 1/1` means the receiver's gates found nothing to complain about **under the pins in force** — and on a foreign endpoint not every approved set in that file is yours. The eight slots of a `gsj-pins/1` file, as the walk above leaves them (the demo's `bootstrap.py` writes the same shape, with the two G4 keys present and empty; `up` prints which sets are empty, writes the skeleton with the two derived sets empty since 0.1.12 — refused as pins by both sides — and the file's `coverage` block says this per set):

| approved set | gate | after the walk on a foreign endpoint | what an acceptance therefore says |
| --- | --- | --- | --- |
| `skill_card_hash` | G1 | **derived here** from your corpus's cards | the card the row resolved is one of yours |
| `system_prompt_hash` | G2 | **derived here** from the inspected body's wire prompt | the system prompt is yours, byte for byte |
| `tool_roster_hash` | G3 | **carried** from the reference — the script *asserts* the trace's roster equals it, never derives one | the roster on the wire is the reference's eleven tools, checked on every trace |
| `settings_hash` | G7, settings clause | **carried** from the reference, asserted equal the same way | the harness settings are the reference's (compaction off), checked on every trace |
| `g6_expected_tail_ids` | G6 | **derived here** from the endpoint's own render, matched at every turn opening | every assistant turn opened with the tail your template renders |
| `tokenizer_hash` | G4 | **not measured** — no set (the demo: an empty set) | **nothing** — no trace gate reads it; the served tokenizer's bytes were never verified on this estate |
| `chat_template_hash` | G4 | **not measured** — no set (the demo: an empty set) | **nothing** — the served template's bytes were never verified |
| — | sampling | **unknown** — pi sends none | **nothing** — the temperature that produced the logprobs is recorded nowhere |

A carried set that *matches* is still a measurement: G3 and G7 prove, on every trace, that the harness is the reference harness. An empty or absent set is not a gate that passed — it is a gate nothing checks. On the reference estate the G4 walk (`pins/derive_pins.py`, a checkout with the snapshot) verified those bytes once, at pin time; on your endpoint nobody has, and the accepted archive cannot tell you: a rejection names its gate, an acceptance names nothing. What does say so: the pins file the receiver validated against (`not_measured`, `coverage`, and in the demo's file `provenance.engine`), which is exactly the file a trainer sets `GSJ_PINS_PATH` to. Where else the warning could live was argued at CP-94 and priced: `up`'s pins line prints the empty sets now (an estate-side line, free); the demo's reader can print it beside `accepted` (parked, demo F-87); a line in `submit` or the receiver would cost the size law and a release for a fact the archive already carries by reference — declined, register row 87.

## The borrowed endpoint

Every sentence above about sampling — "pin them server-side", "the serve argv is yours to write", "treat the argv as provenance" — assumes you serve the model. The other case is the normal one, and the one this page exists for: a platform team hands you a URL you may not restart or re-argv (both round-three doors were in it). Then the tool-call parser's **presence** is testable read-only (step 5 of the script) and its identity, the weights revision and the sampling policy are not; `up` proceeds, the episodes are accepted, and nothing downstream says the policy was unknown — except the pins file, whose `not_measured` and `coverage.sampling_policy` say `unknown`. Read such traces accordingly: they are sound for **provenance work** — the cutoff, the pinned prompt and cards, the roster, the tail, the reconstruction, every claim the validators make — and **not for training-distribution work**, where the temperature that produced the logprobs is the single largest unknown in the artifact. The library's register carries the per-episode engine binding as its open row 22; when you *can* pin, do, and record the argv beside the pins file.

## See also

- [validation-and-pins.md](validation-and-pins.md) — the `gsj-pins/1` format, the resolution order, the thinking-on set, the complete finding vocabulary.
- [server-guide.md](server-guide.md) — the YAML the values land in, and the estate section for `up`.
- [troubleshooting.md](troubleshooting.md) — every finding family, and the refusals `up` can print on the way here.
- [checks-spec.md](../checks-spec.md) — why each gate exists, the hashing conventions, the pi wire dialect these kwargs come from.
