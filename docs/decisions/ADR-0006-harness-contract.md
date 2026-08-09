# ADR-0006 — The harness contract

## Context

CP-07 promotes the CP-06 spike into `gsj_rollout/pi_harness.py`: our pinned
pi 0.83.0 as a Polar `import_path` harness, now with the corpus clone, the
per-episode cutoff token, and the MCP extension live. CP-06 measured the
wire (A-2, A-12, A-15), found the workdir/setup trap and the session-key
rule, and named the spike's argv-literal roster as the row-31 anti-pattern.
The MCP service verifies HS256 JWTs with the claim set
`{case_id, timestep, episode_id, exp}` (`mcp-service/gsj_mcp_service/
tokens.py:30-35,63-66`) delivered as the last path segment of
`/mcp/<token>`; the cutoff clamp filters to `page <= T` before ranking,
with T read only from verified claims (`index.py:69-89`, `tools.py:62-63`).
The predecessor's rendered `.pi/mcp.json` (its ADR-0041 template) and its
pi argv (its ADR-0008) are the working references.

## Decision

1. **What the harness receives — `AgentSpec.settings` is the channel.**
   The task request carries, per episode:

   | key | required | meaning |
   | --- | --- | --- |
   | `case_id` | yes | the case repo name (`case_0001`) |
   | `timestep` | yes | T — the branch to clone and the cutoff claim |
   | `clone_url_for` | yes | Forgejo clone URL pattern with `{case_id}` (anonymous read; owner `gsj-staging`) |
   | `mcp_url_base` | yes | the MCP service base; the token is appended as `<base>/mcp/<token>` |
   | `tools_allowlist` | yes | the full tool roster (list), rendered to `--tools` — **a config value, never an argv literal** (row 31; the 11-name roster includes the four `mcp_gsj_*` names because pi's `--tools` applies to extension tools too) |
   | `artifacts_dir` | yes | host directory where `postprocess()` lands the episode's artifacts |
   | `mcp_token_secret_env` | no (`GSJ_MCP_TOKEN_SECRET`) | NAME of the env var, in the gateway process, holding the HS256 secret |
   | `mcp_token_ttl_s` | no (3600) | token lifetime (predecessor's `mcp_launch.token_ttl_s` default) |
   | `workdir` | no (`/workspace`) | in-sandbox checkout/exec dir — see decision 6 |
   | `pi_entry` | no (`/opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js`) | the package entry, never the `.bin/pi` shim |
   | `pi_mcp_extension` | no (`/opt/pi/node_modules/pi-mcp-extension/src/index.ts`) | loaded via `--no-extensions --extension <path>` (discovery off, explicit path on) |
   | `context_window` / `max_tokens` / `thinking` | no (32768 / 8192 / `"off"`) | pi model config, spike carry-over |

   `model_name` stays `provider/model` (`gsj/Qwen/Qwen3-0.6B`).

2. **Where the token is minted: `run_steps()`, host-side, stdlib HS256.**
   Claims are exactly `{case_id, timestep, episode_id, exp}` —
   `episode_id` is the Polar session id (captured in `setup()` from
   `runtime.session_id`), which makes the MCP request log joinable to the
   Polar session; `exp = now + mcp_token_ttl_s`. The mint adopts the
   stdlib recipe already proven against this service
   (`corpus/ingest_corpus.py:797-810`, cross-verified by
   `mcp-service/tests/test_admin.py:133-146`) rather than adding PyJWT to
   Polar's venv (R1 candidate named; A-14 keeps our deps a subset of
   Polar's). The secret is read from the gateway process env at mint time
   and appears in no argv, log, or metadata — only the signed token does.
   Minting in `run_steps()` keeps the token fresh per episode and sits in
   the same step that needs the proxy env (CP-06's trap: exec-time-only
   values belong in `run_steps()`, not `setup()`).

3. **Where the cutoff is enforced: server-side, from verified claims
   only.** The harness supplies the token in the mcp.json URL; the MCP
   service verifies the signature and binds the claims before any tool
   body runs (`app.py:84-98`); `search_case` filters to
   `page <= claims.timestep` **then** ranks (`index.py:69-89`). The agent
   can read the token (it sits in `.pi/mcp.json` in its own cwd) and that
   is acceptable: every call it can make with it is already scoped to its
   own episode's timestep, and any mutation of the claims breaks the
   HS256 signature (service answers 401, code `-32001`). The adversarial
   probe in CP-07's episode asserts exactly this.

4. **`setup()` vs `run_steps()`.** `setup()` does the static,
   proxy-env-independent work: validates the settings contract, captures
   the session id, clones the case at `timestep-{T}` into the workdir,
   and writes pi's agent-dir config (settings.json with
   `compaction.enabled: false`, the models.json template). Every exec in
   `setup()` is checked loudly — CP-06's trap produced "exit 127, zero
   records" with no diagnosis. `run_steps()` does the per-episode,
   exec-time work: mints the token, renders `.pi/mcp.json`
   (streamable-http, `lifecycle: eager` — mandatory in print mode —
   server key `gsj` + toolPrefix `mcp`, load-bearing for the
   `mcp_gsj_*` names G3 hashes), renders models.json with the two
   exec-time substitutions (`$OPENAI_BASE_URL`, `$OPENAI_API_KEY` — the
   session-key rule), and emits the predecessor-ADR-0008 argv with the
   roster from settings.

5. **What `postprocess()` recovers — the only artifact exit.** The
   session temp dir is destroyed after the session (CP-06), so
   `postprocess()` downloads (a) pi's `--mode json` transcript
   (`<agent log dir>/pi.txt`) and (b) the deliverable `<workdir>/out/`
   if one exists, into `<artifacts_dir>/<session_id>/
   {pi_transcript.jsonl, out/}`. The trace references them by join key:
   `trajectory.metadata.session_id` names the directory. Artifact
   download failure is loud but non-fatal (evidence collection must not
   fail the run); a missing `out/` is normal (the golden episode produced
   none).

6. **`runtime.workdir` is never set to a harness-created path.** CP-06's
   evidence: `runtime.workdir` applies to every exec including the
   `setup()` that would create the dir; `docker exec -w <nonexistent>`
   fails before setup runs, and the presets discard exec results, so the
   only symptom is "step 0 exited with code 127" with zero records. The
   run step carries its own `cwd`. The workdir itself defaults to
   `/workspace` — the predecessor's docker-mode path — so the pinned G2
   `/workspace` singleton and the CP-09 `prompt_ids` comparison carry
   over instead of re-deriving against `/polar/session/...` on day one.

## Consequence

The roster chain config → `--tools` argv → wire `tools` → persisted
record → trace has a pinned input (row 31 closes when the episode shows
the wire matches the settings value). The cutoff rides a channel the
sandbox cannot forge (A-4 resolves at the CP-07 episode). The harness
stays runtime-agnostic — clone, render, and run are all
`exec`/`download` against `BaseRuntime` (law 5); the sandbox image must
provide `node` and `git`. Dev-loop caveat carried from CP-06: the gateway
caches the imported harness module — every harness edit needs a gateway
restart.
