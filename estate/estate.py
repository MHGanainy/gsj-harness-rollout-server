#!/usr/bin/env python3
"""estate/estate.py — the estate's one tool (CP-59's bring-up, renamed CP-72).

    estate/estate.py scaffold --out DIR                          # a starting corpus
    estate/estate.py validate [--corpus DIR]                     # the contract check
    estate/estate.py up   [--corpus DIR] [--name RUN] [flags…]    # the estate
    estate/estate.py ingest [--corpus DIR] [--mcp-url URL]       # re-index the retrieval service
    estate/estate.py update --name RUN [--corpus DIR]            # sync corpus edits into the estate
    estate/estate.py status --name RUN                           # what stands
    estate/estate.py down   --name RUN [--wipe]                  # stop what it created

`up` needs pyarrow in the same interpreter (`pip install pyarrow` — the
taskbank's parquet writer; the wheel does not install it, ADR-0022 §5).

Given a corpus in the contract's shape (docs/corpus-contract.md) this
script leaves behind a running estate — a git host holding one repository
per case, a retrieval service indexing them — plus the task table and the
one YAML the rollout server reads, under `estate/runs/<name>/`:

    rollout.yaml       the rollout server's config, validated (topology rendered)
    taskbank.parquet   the task table, with corpus.lock.json beside it
    run.json           the record: created vs adopted, every URL, the owner,
                       the embedding identity, the engine probe, timestamps —
                       it NAMES variables, never values
    .env               every secret, KEY='value', mode 0600 — `gsj-rollout submit`
                       reads it beside rollout.yaml (CP-75); compose takes --env-file;
                       serve_gateway's own shell sources it; no value on a command line
    .estate-run        ownership marker; --wipe requires this or matching legacy evidence

The runs root must already exist and be writable. Its .locks/<name>.lock holds
the command's kernel lock, survives --wipe, and must not be deleted; `status`
reads it — a held lock means an `up`, `update` or `down` is still running
(CP-94), and the sandbox image is checked before anything is pulled or created.

It is the production sibling of gsj-rollout-demo's bootstrap.py: that one
always CREATES its estate; this one also ADOPTS an existing Forgejo or
retrieval service, probing what it did not build before touching it.
Running it twice on the same corpus and name REUSES (tokens verified,
repos converged, index fingerprint matched); `--rebuild` re-embeds
explicitly — the retrieval service's own posture (CP-57), not a second one.
`update` (CP-73) syncs an EDITED corpus into the standing estate: it diffs
the tree against the run's lock, reports what moved and what that costs,
then pushes only the changed repos, rebuilds the bank, triggers one
reindex and re-verifies — report first, then act.

It stops at the estate: Polar's two processes and the receiver are the
operator's to start, and the final block prints the exact commands.
Every prompt has a default and a flag (or an `--answers` file), so a
straight enter through every prompt gives a working local estate, and a
script can drive it with no terminal at all. Every failure names what it
found, what it expected, and what to do — and stops.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import functools
import getpass
import hashlib
import http.client as _http_client
import http.server as _http_server
import json
import os
import platform
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager, ExitStack
from pathlib import Path

try:
    import yaml
except ImportError:
    print("estate: PyYAML is missing — it rides the library install:\n"
          "  pip install -e '.[dev]'   (from the checkout root)", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent           # estate/ — or site-packages/gsj_rollout/
REPO = HERE.parent
# CP-60: this file also ships in the wheel (force-included, one source) —
# as `gsj_rollout.estate` since the CP-72 rename (`gsj_rollout.bringup` on
# wheels <= 0.1.5). The pipeline is a sibling on both layouts — under
# estate/corpus/ in the checkout, force-included beside this file from the
# wheel — and the runs directory must never land inside site-packages.
CHECKOUT = (HERE / "corpus" / "ingest_corpus.py").is_file()
if CHECKOUT:
    sys.path.insert(0, str(HERE / "corpus"))
    import ingest_corpus as ic  # noqa: E402  — the pipeline, as a library
else:
    from gsj_rollout import ingest_corpus as ic  # noqa: E402  — the same file, from the wheel
INGEST = Path(ic.__file__)
RUNS = HERE / "runs" if CHECKOUT else Path.cwd() / "runs"   # --runs-dir overrides (CP-62)
PROG = "estate/estate.py" if CHECKOUT else "python -m gsj_rollout.estate"

SCHEMA = 1
# CP-62: the pin is a TAG on the canonical registry, with the index digest it
# resolved to when measured (2026-08-30, both platforms pull) — a re-cut tag
# is warned about after a pull, a loaded image (no RepoDigests) is not. Why
# not pin by digest: a `docker save | docker load` on a host that cannot
# reach registries (the H200) carries no digest, so a digest reference would
# never match the loaded image and compose would try to pull. 16.0.2, the
# pin CP-59 measured on, lost both platform manifests on codeberg (wishlist
# 52; the mirror code.forgejo.org still serves it at the same digest) —
# hence --forgejo-image: any registry event is routed around with one flag.
FORGEJO_IMAGE = "codeberg.org/forgejo/forgejo:16.0.3"
FORGEJO_HEALTHZ_BUDGET_S = 120.0
FORGEJO_IMAGE_DIGEST = "sha256:7c4e1db440be7b2ca685b49d0d7864cdd78e92431f531bf7893659def8200fc5"
FORGEJO_IMAGE_MIRROR = "code.forgejo.org/forgejo/forgejo"   # the same tags, measured digest-equal
MCP_IMAGE_PUBLISHED = "ghcr.io/mhganainy/gsj-mcp-service:0.5.0"   # CP-79's published two-platform decisions image
# CP-83: 0.5.0 supports the decisions drop (CP-79), retaining 0.4.1's
# batched add under chroma's 5,461-item ceiling and orphan sweep. From the
# checkout the local build tag (the H200 loads it out-of-band; nothing
# pulls there); from the wheel the published index, pulled when absent
# (wishlist 51 (b)).
MCP_IMAGE = "gsj-mcp-service:0.5.0" if CHECKOUT else MCP_IMAGE_PUBLISHED
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
REFERENCE_MODEL = "Qwen/Qwen3-0.6B"
# CP-92: the library-owned bring-your-own page — a foreign model's values
# (#your-model) and a foreign corpus's pins walk (#your-pins). Named by the
# warnings below because a wheel reader has no demo repo and no pins/ dir.
BRING_YOUR_OWN_URL = ("https://github.com/MHGanainy/gsj-harness-rollout-server/"
                      "blob/main/docs/guide/bring-your-own.md")
DEFAULT_ENGINE_URL = "http://127.0.0.1:8000"
ADMIN_USER = "gsj-admin"
ADMIN_PASSWORD_ENV = "GSJ_FORGEJO_ADMIN_PASSWORD"
MCP_SECRET_ENV = "GSJ_MCP_TOKEN_SECRET"
RUN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")

_T0 = time.monotonic()
_TTY = sys.stdout.isatty()


# ---------------------------------------------------------------- output

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def say(phase: str, msg: str) -> None:
    print(f"[estate +{time.monotonic() - _T0:6.1f}s] {_c('1', phase)} — {msg}",
          flush=True)


def warn(phase: str, msg: str) -> None:
    print(f"[estate +{time.monotonic() - _T0:6.1f}s] {_c('33', phase)} — "
          f"{_c('33', 'WARNING')}: {msg}", flush=True)


def die(what: str, found: str | None, expected: str | None, fix: str,
        code: int = 1) -> "None":
    """Every refusal: what it found, what it expected, what to do (CP-27).
    `code` is 1 except where a folded pipeline verb must keep the
    pipeline's usage exit code (2) — CP-72's fold contract."""
    print(f"\nestate: {_c('31', 'REFUSED')} — {what}", file=sys.stderr)
    if found is not None:
        print(f"  found:    {found}", file=sys.stderr)
    if expected is not None:
        print(f"  expected: {expected}", file=sys.stderr)
    print(f"  what to do: {fix}", file=sys.stderr, flush=True)
    sys.exit(code)


class Phases:
    """One line per phase with its elapsed time; the record keeps them."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._name = None
        self._t = 0.0

    def start(self, name: str, msg: str) -> None:
        self._name, self._t = name, time.monotonic()
        say(name, msg)

    def done(self, note: str) -> None:
        secs = round(time.monotonic() - self._t, 1)
        self.rows.append({"phase": self._name, "seconds": secs, "note": note})
        say(self._name, f"{note}  ({secs}s)")


PH = Phases()


# --------------------------------------------------------------- helpers

def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kw)


def run_phase(cmd: list, env: dict, phase: str) -> subprocess.CompletedProcess:
    """One pipeline phase as a subprocess. `verify` is captured and
    re-emitted with its headline corrected (CP-96, `verify_headline`);
    every other phase streams as before."""
    if phase != "verify":
        return run(cmd, env=env)
    proc = run(cmd, env=env, capture_output=True)
    if proc.stdout:
        print(verify_headline(proc.stdout), end="" if proc.stdout.endswith("\n") else "\n",
              flush=True)
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n",
              file=sys.stderr, flush=True)
    return proc


def http(method: str, url: str, body: dict | None = None, *,
         headers: dict | None = None, auth: tuple[str, str] | None = None,
         timeout: float = 10.0):
    """(status, parsed-json-or-text) — never raises; (None, reason) when
    the connection itself fails."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if auth:
        hdrs["Authorization"] = "Basic " + base64.b64encode(
            f"{auth[0]}:{auth[1]}".encode()).decode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, (json.loads(raw) if raw else None)
            except ValueError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except ValueError:
            return exc.code, raw.decode(errors="replace")[:300]
    except (urllib.error.URLError, _http_client.HTTPException, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return None, f"{type(exc).__name__}: {reason}"


def port_busy(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


def pick_port(want: str | int | None, default: int, flag: str,
              check: bool = True) -> int:
    """`auto` (the default) scans upward from the conventional port and says
    so; an explicit port must be free or the refusal names the flag. A port
    the run already recorded is kept as is (check=False: the service this
    run created may legitimately hold it)."""
    if want not in (None, "auto") and not check:
        return int(want)
    if want in (None, "auto"):
        port = default
        while port_busy(port):
            port += 1
        if port != default:
            say("ports", f"{default} is busy on this host; using {port} "
                         f"(pin one with {flag})")
        return port
    port = int(want)
    if port_busy(port):
        die(f"port {port} ({flag}) is already in use on 127.0.0.1.",
            f"something listens on 127.0.0.1:{port}", "a free port",
            f"pass {flag} auto (scan upward from {default}) or another port")
    return port


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bare_url(url: str, flag: str) -> str:
    """An adopted service URL: scheme://host[:port], no userinfo — a credential
    in the URL would land in run.json, rollout.yaml and mcp-config.yaml."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        die(f"{flag} {url!r} is not an http(s) URL.", repr(url), "http://host[:port]", flag)
    if parts.username or parts.password:
        die(f"{flag} carries a credential in its userinfo.", "user[:password]@ in the URL",
            "a bare scheme://host[:port]", "pass the credential through its environment "
            "variable or --…-file; the URL is recorded in run.json and the emitted config")
    return url.rstrip("/")


def localhost_to_container(url: str) -> str:
    """A host-loopback URL, as a container reaches it (the demo's rewrite)."""
    return re.sub(r"^(https?://)(localhost|127\.0\.0\.1)(?=[:/]|$)",
                  r"\1host.docker.internal", url.rstrip("/"))


def eurl_is_loopback(url: str) -> bool:
    return re.match(r"^https?://(localhost|127\.\d+\.\d+\.\d+|\[::1\])(?=[:/]|$)", url) is not None


def script_version() -> dict:
    head = run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
               capture_output=True) if CHECKOUT else None
    dirty = run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                 "estate/estate.py"], capture_output=True) if CHECKOUT else None
    try:
        import gsj_rollout
        lib = gsj_rollout.__version__
    except ImportError:
        lib = None
    # old run records carry the pre-CP-72 script names ("estate/bringup.py" /
    # "gsj_rollout.bringup"); the field is write-only — status/down never
    # parse it back, so mixed-vintage runs stay readable.
    return {"script": "estate/estate.py" if CHECKOUT else "gsj_rollout.estate",
            "commit": (head.stdout.strip() if head and head.returncode == 0 else None),
            "dirty": bool(dirty and dirty.stdout.strip()),
            "library": lib}


# ----------------------------------------------------------- the answers

class Answers:
    """flag > answers file > prompt (interactive) > default. Secrets: env
    var > file > prompt (getpass) > refuse — never a command-line value."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.file: dict = {}
        if args.answers:
            try:
                self.file = yaml.safe_load(Path(args.answers).read_text()) or {}
            except (OSError, yaml.YAMLError) as exc:
                die(f"--answers {args.answers} is unreadable.", str(exc),
                    "a YAML mapping of flag names to values",
                    "fix the file (keys are the long flag names with "
                    "underscores, e.g. forgejo_url)")
            if not isinstance(self.file, dict):
                die(f"--answers {args.answers} is not a mapping.", None, None,
                    "one key per flag, e.g.  corpus: ./my-corpus")
        self.interactive = (not args.defaults and sys.stdin.isatty()
                            and not args.answers)

    def get(self, key: str, question: str, default=None, *,
            choices: tuple | None = None, required: bool = False):
        value = getattr(self.args, key, None)
        if value is None and key in self.file:
            value = self.file[key]
        if value is None and self.interactive and question:
            shown = f" [{default}]" if default is not None else ""
            hint = f" ({'/'.join(choices)})" if choices else ""
            try:
                typed = input(f"{_c('36', '?')} {question}{hint}{shown}: ").strip()
            except EOFError:
                typed = ""
            value = typed or default
        if value is None:
            value = default
        if value is None and required:
            die(f"{question}: no value.", None, None,
                f"pass --{key.replace('_', '-')} (or put {key}: in an "
                f"--answers file)")
        if choices and value not in choices:
            die(f"{question}: {value!r} is not a choice.", repr(value),
                "one of " + "/".join(choices), f"--{key.replace('_', '-')}")
        return value

    def secret(self, question: str, *, env: str, file_key: str,
               fallback: str | None = None) -> str | None:
        if os.environ.get(env):
            say("secrets", f"{question}: taken from ${env} (the environment)")
            return credential(os.environ[env], env)
        path = getattr(self.args, file_key, None) or self.file.get(file_key)
        if path:
            try:
                value = Path(path).read_bytes().decode("utf-8").removesuffix("\n")
            except UnicodeError:
                die(f"{env}: the credential file is not UTF-8 text.", "a non-ASCII byte sequence",
                    "a printable ASCII credential",
                    "rotate the credential at its service, or use a token without non-ASCII "
                    "bytes; supply that exact value in the credential file and re-run")
            except OSError as exc:
                die(f"{question}: the file is unreadable.", str(exc), None,
                    f"--{file_key.replace('_', '-')} names a readable file "
                    f"holding the value")
            if not value:
                die(f"{question}: {path} is empty.", None, None, "put the value in it")
            if os.stat(path).st_mode & 0o077:
                warn("secrets", f"{path} is group/world-readable "
                                f"({oct(os.stat(path).st_mode & 0o777)}) — chmod 600 it")
            say("secrets", f"{question}: read from {path}")
            return credential(value, env)
        if fallback:
            return credential(fallback, env)
        if self.interactive:
            value = getpass.getpass(f"{_c('36', '?')} {question} (not echoed): ")
            if value:
                return credential(value, env)
        return None


# ------------------------------------------------------------- the corpus

def load_corpus(path: Path, owner_override: str | None,
                sandbox_image: str | None = None, *, refusal_code: int = 1):
    """validate — the contract, before anything runs; the Corpus object.
    `refusal_code` reaches only the not-a-corpus-root refusal: the folded
    pipeline verbs pass 2 (the pipeline's usage exit code), `up` keeps 1."""
    if not (path / "corpus.yaml").is_file():
        # CP-71: the empty-directory reader is starting, not failing —
        # the refusal hands them the verb that writes a corpus (the same
        # class as CP-59's refusals: what to do, not just what is wrong)
        die(f"{path} is not a corpus root.", "no corpus.yaml there",
            "a tree in docs/corpus-contract.md's shape",
            f"there is no corpus there — `{PROG} scaffold --out {path}` "
            f"writes an annotated starting tree (edit it, `validate`, then "
            f"re-run `up`); or point --corpus at the directory holding "
            f"corpus.yaml, AGENTS.md, skills/, train/ and/or eval/",
            code=refusal_code)
    try:
        corpus = ic.phase_validate(path, owner_override=owner_override,
                                   quiet=False,
                                   sandbox_image_override=sandbox_image)
    except ic.PipelineError as exc:
        die("the corpus failed validation.", str(exc), "a tree that passes "
            "the contract", "fix the rows marked FAIL above and re-run")
    if corpus is None:
        die("the corpus tree failed validation — nothing was stood up.",
            "FAIL rows above (each names its file and rule)",
            "zero FAIL rows", "fix them and re-run; the contract is "
            "docs/corpus-contract.md")
    return corpus


def built_heads(corpus) -> dict[str, dict[str, str]]:
    """What THIS corpus builds, per case — deterministic SHAs, no push."""
    env = ic.git_env(corpus.git_identity)
    with tempfile.TemporaryDirectory(prefix="gsj-estate-build-") as tmp:
        return {case_id: ic.build_case_repo(corpus, case, Path(tmp), env)
                for case_id, case in sorted(corpus.cases.items())}


def pins_g1_check(corpus) -> dict:
    """Which of this corpus's skill cards the approved set the library will
    actually validate against (G1) already carries — the document `checks`
    selected: `GSJ_PINS_PATH`, else the checkout's source set, else the
    packaged reference set (CP-62: the same resolver, so an estate whose own
    pins are named is not warned about the packaged ones — wishlist 51 (c)).
    Episodes on the others quarantine until the pins walk re-derives
    (pins/derive_pins.py); a warning, not a refusal."""
    try:
        from gsj_rollout import checks
        pins = checks.PINS_PATH
        source = ("GSJ_PINS_PATH" if os.environ.get("GSJ_PINS_PATH")
                  else "packaged" if pins == checks.PACKAGED_PINS else "checkout")
        sets = json.loads(pins.read_text())["pins"]
        approved = set(sets["skill_card_hash"])
    except Exception:  # noqa: BLE001 — a probe, not a gate
        return {"checked": False}
    cards = {name: sha256_file(card) for name, card in sorted(corpus.skills.items())}
    missing = sorted(n for n, h in cards.items() if h not in approved)
    # CP-94: an approved set left EMPTY on purpose (a foreign model's G4
    # slots) is not a gate that passed — it is a gate nothing checks
    empty = sorted(k for k, v in sets.items() if isinstance(v, list) and not v)
    return {"checked": True, "cards": len(cards), "pins_path": str(pins),
            "pins_source": source, "not_in_approved_set": missing, "empty_sets": empty}


# ------------------------------------------------------------ the run dir

def credential(value: str, name: str, *, cure: str | None = None) -> str:
    """CP-84: one literal value across shell, Compose and the package reader."""
    problem = ("a non-string credential" if not isinstance(value, str) else
               "an empty credential" if not value else
               "an apostrophe (single quote)" if "'" in value else
               "an ASCII control character (including newline, tab or DEL)"
               if any(ord(c) < 32 or ord(c) == 127 for c in value) else
               "a non-ASCII character (including Unicode line separators)"
               if not value.isascii() else
               "an odd run of trailing backslashes"
               if (len(value) - len(value.rstrip("\\"))) % 2 else None)
    if problem:
        die(f"{name} has an unsupported credential value.", problem,
            "nonempty printable ASCII without apostrophes or an odd run of trailing "
            "backslashes; spaces, internal backslashes and even trailing runs are literal",
            cure or f"rotate the credential at its service, or use a token without that character "
            f"class/ending; supply the replacement through {name} or its credential file. "
            "Credential files hold the exact value, optionally followed by one LF "
            "(no CRLF or other newline); "
            "then re-run; do not trim or escape the credential")
    return value


def _env_quote(value: str) -> str:
    """CP-75's shell encoding; write_env validates CP-84's shared grammar first.
    Keep its legacy apostrophe representation readable for a precise refusal."""
    return "'" + value.replace("'", "'\\''") + "'"


def _env_unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("'\\''", "'")
    return raw


class Run:
    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not RUN_NAME_RE.fullmatch(name):
            die(f"run name {name!r} is not a token.", repr(name),
                "lowercase letters or digits first, then lowercase letters, digits, - or _",
                "pass --name <token>; paths and parent components are not run names")
        self.name = name
        self.root = RUNS.resolve()
        self.dir = self.root / name
        if self.dir.is_symlink() or self.dir.resolve() != self.dir:
            die(f"run {name!r} escapes its named directory.", str(self.dir),
                f"the direct directory {self.dir}, without a symlink",
                "use the original --runs-dir and run name; do not point a run at another directory")
        if self.dir.exists() and not self.dir.is_dir():
            die(f"run {name!r} is not a directory.", str(self.dir),
                "a directory beneath --runs-dir", "choose another run name; preserve the existing file")
        self.env: dict[str, str] = {}
        self.record: dict = {}
        self.existing = False
        self._locked = False

    @contextmanager
    def mutation(self):
        """Kernel exclusion lasts for a command; its inode survives `--wipe`."""
        if self._locked:
            yield
            return
        locks = self.root / ".locks"
        if locks.is_symlink() or (locks.exists() and not locks.is_dir()):
            die("the run lock directory is not a real directory.", str(locks),
                f"a real directory at {locks}", "restore the runs directory's lock directory")
        try:
            locks.mkdir(exist_ok=True, mode=0o700)
        except OSError as exc:
            die("cannot prepare the run lock directory.", f"{self.root}: {exc}",
                f"an existing writable runs directory at {self.root}; .locks/ is created on first use",
                "make the runs directory writable, or pass --runs-dir naming the directory "
                "that holds the run; create that root directory first for a new estate")
        try:
            fd = os.open(locks / f"{self.name}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            if isinstance(exc, PermissionError) and not os.access(locks, os.W_OK | os.X_OK):
                die("the run lock directory is not writable/searchable by this caller.",
                    f"{locks}: owner uid {locks.stat().st_uid}; caller uid {os.geteuid()}",
                    "write and search permission on the lock directory",
                    f"run as the user that owns {locks}, with directory write/search permissions; "
                    "do not delete lock files")
            die(f"cannot open the lock for run {self.name!r}.", str(exc),
                "a regular writable lock file", "restore the lock file and its permissions; then re-run")
        with os.fdopen(fd, "w") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                die(f"the lock for run {self.name!r} is not a regular file.",
                    str(locks / f"{self.name}.lock"), "a regular run lock file",
                    "restore the lock file before re-running; do not replace a live lock")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                die(f"run {self.name!r} is busy — another command holds it.",
                    "the run's exclusive lock is held", "one mutating command per run",
                    f"wait for it to finish or check status: {PROG} status --name {self.name} "
                    f"--runs-dir {self.root}; do not delete the lock file")
            self._locked = True
            try:
                yield
            finally:
                self._locked = False
                fcntl.flock(handle, fcntl.LOCK_UN)

    def read_record(self, *, tolerant: bool = False) -> dict:
        rec = self.dir / "run.json"
        try:
            record = json.loads(rec.read_text())
            problem = record_problem(record, self.name)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            record, problem = {}, f"unreadable JSON ({type(exc).__name__})"
        if problem:
            if tolerant:  # down owns resources by namespace/evidence, not damaged JSON
                return {}
            die(f"{rec} is not a supported run record.", problem,
                f"a schema-{SCHEMA} object for run {self.name!r}",
                "restore run.json from backup, or use the tool version that wrote it; "
                f"to stop a partial run use `{PROG} down --name {self.name} "
                f"--runs-dir {self.root}`; never hand-edit run.json")
        return record

    def owned(self) -> bool:
        """Accept our marker or legacy identity; mere directory existence is not ownership."""
        marker = self.dir / ".estate-run"
        try:
            if not marker.is_symlink() and marker.read_text() == f"estate run {self.name}\n":
                return True
        except (OSError, UnicodeError):
            pass
        if self.read_record(tolerant=True):
            return True
        for filename in ("compose.yaml", ".env"):
            path = self.dir / filename
            try:
                first = path.read_text().splitlines()[0] if not path.is_symlink() else ""
            except (OSError, IndexError, UnicodeError):
                continue
            if (filename == "compose.yaml" and first.startswith("# GENERATED by ")
                    and first.endswith(f" for run {self.name} — do not edit; re-run `up`.")):
                return True
            if filename == ".env" and first.endswith(f" — every secret of run {self.name}, KEY='value'."):
                return True
        return False

    def require_wipe_owned(self) -> None:
        if not self.owned():
            die(f"refusing to wipe {self.dir}: run ownership is unproved.",
                "no matching estate marker, supported run record or generated run file",
                "a directory this estate tool created",
                "restore this run's metadata from backup; use down without --wipe to stop "
                "recoverable owned services, and inspect unrecognized files yourself")

    def prepare(self) -> None:
        if self.dir.exists() and any(self.dir.iterdir()) and not self.owned():
            die(f"refusing to use {self.dir} as a run.",
                "a nonempty directory with no matching estate ownership evidence",
                "an empty new directory or a run this tool created",
                "choose another --name or restore this run's metadata from backup; "
                "preserve the unrecognized directory")
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = self.dir / ".estate-run"
        if marker.is_symlink():
            die("the run ownership marker is a symlink.", str(marker),
                "the run's own regular marker file", "restore it from backup before re-running up")
        marker.write_text(f"estate run {self.name}\n")

    def load(self) -> None:
        rec = self.dir / "run.json"
        envf = self.dir / ".env"
        if rec.is_file():
            self.record = self.read_record()
            self.existing = True
            if not envf.is_file():
                names = sorted(self.record.get("secrets", {}).get("names", []))
                die(f"run '{self.name}' exists but its .env is missing.",
                    f"{rec} present, {envf} absent",
                    f"{envf} holding {', '.join(names) or 'the run secrets'}",
                    "restore .env from your backup — re-minting would "
                    "silently invalidate the running retrieval service's "
                    "secret and every token the record names; or start "
                    f"over: `{PROG} down --name "
                    f"{self.name} --wipe` then `up`")
        if envf.is_file():
            loaded = {}
            # splitlines treats VT/U+2028 as record delimiters and silently
            # shortened old credentials. Only the writer's LF ends a record.
            for number, line in enumerate(envf.read_bytes().decode("utf-8").split("\n"), 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                k, eq, raw = (part.strip() for part in line.partition("="))
                key = k if k.isidentifier() else "KEY"
                cure = (f"rotate the credential at its service or use a compatible token; edit "
                        f"{envf} line {number} by hand to {key}='value' form with the exact "
                        "supported value on one LF-terminated line. After that repair, re-run "
                        "up to re-adopt from the environment or credential file; or "
                        f"`{PROG} down --name {self.name} --runs-dir {self.root} --wipe` "
                        "and start over (deletes this run's data)")
                # strip() above must not erase CR record framing either.
                if "\r" in line:
                    credential("\r", f"{envf} line {number} ({key})", cure=cure)
                if not eq or not k.isidentifier() or (raw and not (
                        len(raw) >= 2 and raw[0] == raw[-1] == "'")):
                    die(f"{envf} line {number} is not a complete KEY='value' record.",
                        "a malformed or multi-line credential record", "one quoted value per line",
                        cure)
                value = _env_unquote(raw)
                loaded[k] = credential(value, f"{envf} line {number} ({k})", cure=cure) if value else value
            self.env.update(loaded)

    def write_env(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.dir.chmod(0o700)
        envf = self.dir / ".env"
        body = ("# %s — every secret of run %s, KEY='value'.\n"
                "# `gsj-rollout submit` (since 0.1.7, CP-75) reads this file beside rollout.yaml\n"
                "# for an unset named variable; the environment wins when already set.\n"
                "# Historical wheels through 0.1.6 need it sourced before submit.\n"
                "# compose takes --env-file; Polar's serve_gateway reads ITS environment —\n"
                "# source it there: (set -a; . %s; set +a; polar serve_gateway …).\n"
                "# Never commit; never paste values on a command line.\n"
                % (envf, self.name, envf))
        for k, v in sorted(self.env.items()):
            if v != "":
                credential(v, k)
            body += f"{k}={_env_quote(v)}\n"
        fd = os.open(envf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 0600 from birth
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        envf.chmod(0o600)

    def write_record(self) -> None:
        with self.mutation():
            self._write_record()

    def _write_record(self) -> None:
        self.record["schema"] = SCHEMA
        self.record["updated_at"] = now_iso()
        self.record.setdefault("created_at", self.record["updated_at"])
        self.record["secrets"] = {
            "file": str(self.dir / ".env"), "mode": "0600",
            "names": sorted(self.env)}
        text = json.dumps(self.record, indent=2, sort_keys=False) + "\n"
        # the record names variables, never values — proven before it lands
        for name, value in self.env.items():
            if value and value in text:
                die("internal: a secret value would land in run.json.",
                    f"the value of {name}", "names only", "report this bug")
        with tempfile.NamedTemporaryFile(mode="w", prefix="run.json.", suffix=".tmp",
                                         dir=self.dir, delete=False) as handle:
            tmp = Path(handle.name)
            handle.write(text)
        try:
            os.replace(tmp, self.dir / "run.json")
        finally:
            tmp.unlink(missing_ok=True)


def record_problem(record, name: str) -> str | None:
    """Check the state boundary, retaining schema 1's optional historical fields."""
    if not isinstance(record, dict):
        return "run.json root is not an object"
    if type(record.get("schema")) is not int or record["schema"] != SCHEMA:
        return "schema is missing or unsupported (only integer 1 is supported)"
    if record.get("run") != name:
        return "run is missing or does not match the requested name"
    mappings = ("version corpus network forgejo mcp engine pins ports artifacts secrets last_run "
                "harness compose mcp.embedding mcp.backend compose.forgejo compose.mcp "
                "compose.mcp.chunking compose.mcp.config_overrides").split()
    for path in mappings:
        parent = record
        keys = path.split(".")
        for key in keys[:-1]:
            parent = parent.get(key, {})
        if path in ("mcp.embedding", "mcp.backend") and parent.get(keys[-1]) is None:
            continue  # /health may omit these optional observations, including explicit null
        if keys[-1] in parent and not isinstance(parent[keys[-1]], dict):
            return f"{path} is not an object"
    for section in ("forgejo", "mcp"):
        if section not in record:
            continue  # a record saved after Forgejo creation is recoverable by up
        service = record[section]
        if service.get("mode") not in ("created", "adopted"):
            return f"{section}.mode is not created or adopted"
        if "url" not in service:
            return f"{section}.url is missing"
    for section in ("forgejo", "mcp", "engine"):
        url = record.get(section, {}).get("url")
        if section == "engine" and url is None:
            continue
        try:
            parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
            valid = (parsed is not None and parsed.scheme in ("http", "https")
                     and parsed.hostname and not re.search(r"\s", url)
                     and (parsed.port is None or 0 < parsed.port <= 65535))
        except ValueError:
            valid = False
        if section in record and not valid:
            return f"{section}.url is not an HTTP(S) URL"
    strings = {
        "": "run_dir sandbox_image polar_leg gateway_host",
        "corpus": "path name owner sandbox_image",
        "network": "name",
        "forgejo": "container_url owner admin_user admin_credential_env push_token_env read_token_env",
        "mcp": "container_url secret_env",
        "mcp.embedding": "model revision",
        "engine": "url model",
    }
    for section, keys in strings.items():
        values = record
        for part in section.split(".") if section else ():
            values = values.get(part) or {}
        for key in keys.split():
            if key in values and not isinstance(values[key], str):
                return f"{section + '.' if section else ''}{key} is not a string"
    for service, fields in {
        "forgejo": {"image": str, "container": str, "port": int, "data": str,
                    "signin": bool, "uid": int, "gid": int},
        "mcp": {"image": str, "container": str, "port": int, "data": str,
                "config": str, "read_env": str},
    }.items():
        values = record.get("compose", {}).get(service, {})
        if not values:
            continue
        for key, kind in fields.items():
            if type(values.get(key)) is not kind:
                return f"compose.{service}.{key} is missing or is not {kind.__name__}"
    for key, port in record.get("ports", {}).items():
        if type(port) is not int or not 1 <= port <= 65535:
            return f"ports.{key} is not a port in 1..65535"
    for key in ("external", "created_by_run"):
        network = record.get("network", {})
        if key in network and type(network[key]) is not bool:
            return f"network.{key} is not a boolean"
    names = record.get("secrets", {}).get("names", [])
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        return "secrets.names is not a list of variable names"
    return None


def _command_run(args: argparse.Namespace, name: str) -> Run:
    if getattr(args, "_estate_run", None) is None:
        args._estate_run = Run(name)
        if not getattr(args, "dry_run", False):
            args._estate_locks.enter_context(args._estate_run.mutation())
    return args._estate_run


def mutating_command(func):
    @functools.wraps(func)
    def wrapped(args):
        with ExitStack() as args._estate_locks:
            args._estate_run = None
            try:
                if getattr(args, "name", None):
                    if func.__name__ in ("cmd_down", "cmd_update"):
                        r = Run(args.name)
                        required = r.dir if func.__name__ == "cmd_down" else r.dir / "run.json"
                        exists = required.is_dir() if func.__name__ == "cmd_down" else required.is_file()
                        if not exists:
                            die(f"no run named {args.name!r}.",
                                f"{r.dir} does not exist" if func.__name__ == "cmd_down" else
                                f"{r.dir} has no run.json", "a run this script created",
                                f"{PROG} up --name {args.name} (or --runs-dir "
                                "naming the directory that holds it)")
                    _command_run(args, args.name)
                return func(args)
            finally:
                del args._estate_locks, args._estate_run
    return wrapped


# ---------------------------------------------------------------- docker

def check_daemon() -> None:
    """`docker` on PATH and a daemon that answers — the half of check_docker()
    every image inspection needs (CP-94: the sandbox check runs first now,
    and a stopped daemon must be named as such, not as a missing image)."""
    if shutil.which("docker") is None:
        die("`docker` is not on PATH.", None, "Docker with the compose v2 plugin",
            "install Docker (https://docs.docker.com/engine/install/) or "
            "adopt existing services instead of creating them")
    probe = run(["docker", "info", "--format", "{{.ServerVersion}} {{.Driver}}"],
                capture_output=True)
    if probe.returncode != 0:
        die("the Docker daemon is not reachable.",
            (probe.stderr.strip().splitlines() or ["nothing"])[-1],
            "a running daemon", "start Docker (or fix socket permissions), then re-run")
    driver = (probe.stdout.split() + ["", ""])[1]
    if driver in COPY_ON_CREATE_DRIVERS:
        # CP-96 (round four): the price of a copy-on-create daemon surfaced
        # post-mortem — ~13 GB per sandbox container, minutes per create,
        # Polar's 600 s sandbox-create budget blown — from the same call
        # that already answers "is there a daemon"
        warn("docker", f"storage driver {driver!r}: every container is a full COPY of its image, "
                       "not a layer over it — each episode's sandbox container copies the harness "
                       "image (~13 GB per container and minutes per create measured at round four; "
                       "Polar's 600 s sandbox-create budget was blown on a busy host), and the "
                       "retrieval container copies its 4 GB image before it can start. The cure is "
                       "the daemon, not this tool: a data root on ext4/xfs with overlay2 (a nested "
                       "daemon: `-v /var/lib/docker`). Continuing — slowly")


def check_docker() -> None:
    check_daemon()
    probe = run(["docker", "compose", "version", "--short"], capture_output=True)
    if probe.returncode != 0:
        die("`docker compose` (v2 plugin) is missing.", None, None,
            "install the Compose plugin and re-run")


def daemon_arch() -> str:
    proc = run(["docker", "version", "--format", "{{.Server.Arch}}"],
               capture_output=True)
    return (proc.stdout.strip() if proc.returncode == 0 else "") or platform.machine().lower()


def image_present(image: str) -> bool:
    return run(["docker", "image", "inspect", image],
               capture_output=True).returncode == 0


def image_has_registry(image: str) -> bool:
    """A reference with a path (`registry/…`, or Docker Hub's `user/repo`) is
    pullable; a bare single-component build tag (`gsj-mcp-service:0.4.0`)
    exists only on the daemon that built it — Docker would look it up under
    `library/` on Docker Hub, where it does not exist."""
    return "/" in image


def image_tag(image: str) -> str:
    """The tag of a reference, from its LAST path component (a registry port
    is not a tag); `<tag>` for a digest reference or an untagged one."""
    last = image.rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last and "@" not in last else "<tag>"


# CP-94 (round three, 2026-09-07): `docker pull` prints a line only when a
# layer changes state, so one large layer on a slow pipe is silent for as
# long as it takes — 21 minutes measured by one stranger, 39 by another —
# and a captured child printed nothing at all. Either could not tell a
# working pull from a hung one without sampling /proc/net/dev by hand.
PULL_HEARTBEAT_S = float(os.environ.get("GSJ_ESTATE_PULL_HEARTBEAT_S", "60"))
COPY_ON_CREATE_DRIVERS = ("vfs",)   # CP-96: named at the first Docker call, not in a post-mortem
HEALTH_TIMEOUT_S = 15.0         # one /health read (CP-96: 5 s read a slow host as unreachable)
SLEEP_SKEW_S = 30.0             # wall minus monotonic beyond this = the host slept (CP-96)


def host_rx_bytes() -> int | None:
    """Bytes THIS host's non-loopback interfaces have received, or None where
    it cannot be read (the daemon may be remote; the number is a liveness
    signal for the pipe, never the pull's own byte count)."""
    try:
        if platform.system() == "Linux":
            total = 0
            for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
                name, _, rest = line.partition(":")
                if name.strip() != "lo" and rest.split():
                    total += int(rest.split()[0])
            return total
        if platform.system() == "Darwin":
            total = 0
            out = subprocess.run(["netstat", "-ibn"], capture_output=True, text=True).stdout
            for line in out.splitlines()[1:]:
                cols = line.split()
                # one row per interface carries the link-level counters
                if len(cols) >= 10 and cols[2].startswith("<Link#") and not cols[0].startswith("lo"):
                    total += int(cols[6])
            return total
    except (OSError, ValueError, IndexError):
        pass
    return None


def _human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


def popen(cmd: list, **kw) -> subprocess.Popen:
    """The streaming seam beside `run` (CP-96): a process whose stdout is
    read line by line while it runs — the tests hand back a fake."""
    return subprocess.Popen(cmd, text=True, **kw)


# `docker pull` without a TTY prints one line per layer state transition:
# "<id>: Pulling fs layer" → "Downloading" → "Verifying Checksum" →
# "Download complete" → "Extracting" → "Pull complete" (and "Already exists").
_PULL_STATES = ("Pull complete", "Already exists", "Extracting", "Download complete",
                "Verifying Checksum", "Downloading", "Pulling fs layer", "Waiting")


def pull_phase_tally(layers: dict, line: str) -> None:
    """Fold one line of docker's pull output into the per-layer state map."""
    head, sep, state = line.strip().partition(": ")
    if not sep or " " in head or len(head) < 8:
        return                                  # the tag line, Digest:, Status:
    for known in _PULL_STATES:
        if state.startswith(known):
            layers[head] = known
            return


def pull_phase_summary(layers: dict) -> tuple[str, bool]:
    """What the layers are doing, and whether the pipe SHOULD be moving —
    round four (CP-96): a heartbeat that reads only received bytes said
    "the pipe is moving" through an extraction (26 KiB of noise) and a
    stranger counted `Download complete` against `Pull complete` by hand to
    tell a phase change from a stall. Extraction expects no bytes."""
    if not layers:
        return "no layer line from docker yet (the manifest is still being resolved)", True
    counts = {s: 0 for s in _PULL_STATES}
    for state in layers.values():
        counts[state] += 1
    done = counts["Pull complete"] + counts["Already exists"]
    downloading = counts["Downloading"] + counts["Pulling fs layer"] + counts["Waiting"]
    queued = counts["Download complete"] + counts["Verifying Checksum"]
    parts = [f"{done}/{len(layers)} layers complete"]
    if counts["Extracting"]:
        parts.append(f"{counts['Extracting']} extracting")
    if queued:
        parts.append(f"{queued} downloaded, waiting to extract")
    if downloading:
        parts.append(f"{downloading} downloading")
    text = ", ".join(parts)
    if downloading:
        return text, True
    if counts["Extracting"] or queued:
        return text + " — EXTRACTION: no bytes are expected on the pipe now", False
    return text, True


def image_pull(image: str, phase: str) -> subprocess.CompletedProcess:
    """One pull, said out loud; the caller decides what a failure means.
    docker's own stdout passes through live (a TTY draws bytes per layer; a
    log gets one line per layer state — and a large layer on a slow pipe
    prints nothing until it lands), stderr is kept for the refusal, and once
    a minute a heartbeat says how long the pull has run, which phase its
    layers are in (CP-96: extraction expects no bytes, so a quiet pipe is
    not a stall there) and how many bytes this host received meanwhile —
    what a reader needs before concluding it hung
    (docs/guide/troubleshooting.md, the pull row)."""
    say(phase, f"{image} is absent on this daemon — pulling it (docker's progress follows; a "
               f"large layer on a slow pipe prints nothing until it lands — a heartbeat every "
               f"{PULL_HEARTBEAT_S:.0f}s says which phase the layers are in and whether this "
               "host's pipe is moving)")
    layers: dict = {}
    errors: list = []
    cmd = ["docker", "pull", image]
    try:
        proc = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 1, "", f"{type(exc).__name__}: {exc}")

    def drain_stderr() -> None:
        try:
            errors.append(proc.stderr.read() or "")
        except (OSError, ValueError):
            pass

    def drain_stdout() -> None:
        try:
            for line in proc.stdout:
                print(line, end="" if line.endswith("\n") else "\n", flush=True)
                pull_phase_tally(layers, line)
        except (OSError, ValueError):
            pass

    drainers = [threading.Thread(target=t, daemon=True) for t in (drain_stderr, drain_stdout)]
    for t in drainers:
        t.start()
    started, rx0 = time.monotonic(), host_rx_bytes()
    while True:
        try:
            proc.wait(timeout=PULL_HEARTBEAT_S)
            break
        except subprocess.TimeoutExpired:
            pass
        rx1 = host_rx_bytes()
        where, expects_bytes = pull_phase_summary(layers)
        if rx0 is None or rx1 is None:
            moved = "this host's byte counters are not readable here"
        elif rx1 - rx0 > 0:
            moved = f"this host received {_human(rx1 - rx0)} in the last {PULL_HEARTBEAT_S:.0f}s — the pipe is moving"
        elif not expects_bytes:
            moved = (f"this host received NOTHING in the last {PULL_HEARTBEAT_S:.0f}s — as expected "
                     "while the daemon extracts (watch the daemon's data root grow instead)")
        else:
            moved = (f"this host received NOTHING in the last {PULL_HEARTBEAT_S:.0f}s — before killing it, "
                     "the three checks: docs/guide/troubleshooting.md, the pull row")
        rx0 = rx1
        elapsed = int(time.monotonic() - started)
        say(phase, f"still pulling {image} — {elapsed // 60}m{elapsed % 60:02d}s elapsed; {where}; "
                   f"{moved} (a liveness signal for the pipe, not the pull's own byte count)")
    for t in drainers:                          # the last lines land before the verdict
        t.join(timeout=5)
    return subprocess.CompletedProcess(cmd, proc.returncode, "", "".join(errors))


# CP-92 (the stranger runs of 2026-09-06): a pull can fail AFTER the
# registry answered — every layer downloaded, then the daemon's storage
# could not extract or mount one (a nested dockerd whose data root sits on
# overlayfs; a full or read-only data root). The old advice named only
# download-side causes and a save/load that fails on the same layers.
_EXTRACT_STRONG = ("failed to extract", "failed to mount", "whiteout",
                   "failed to register layer", "no space left", "read-only file system")
# the bare errno words only count beside a storage word: `dial tcp …: connect:
# operation not permitted` is a firewalled daemon, not a broken data root
_EXTRACT_ERRNO = ("operation not permitted", "invalid argument")
_STORAGE_WORDS = ("layer", "extract", "mount", "overlay", "snapshotter", "unpack",
                  "whiteout", "rootfs")
_TRANSPORT_MARKS = ("dial tcp", "lookup ", "tls handshake", "unexpected eof",
                    "connection refused", "no such host", "i/o timeout", "manifest unknown")


_VERIFY_HEADLINE = re.compile(r"^== verify: (PASS|FAIL) \((\d+) pass / (\d+) fail\) ==$", re.M)


def verify_headline(text: str) -> str:
    """The pipeline's verify table counts a SKIPPED row as a pass in its
    headline (`8 pass / 0 fail` with `mcp — SKIPPED (--skip-ingest)` among
    the rows — round four, CP-96). The detail row is honest; the headline
    is corrected here, in the driver, until ingest_corpus.py's next lift."""
    m = _VERIFY_HEADLINE.search(text)
    if not m:
        return text
    skipped = sum(1 for line in text.splitlines() if "  SKIPPED (" in line)
    if not skipped:
        return text
    passed = int(m.group(2)) - skipped
    return text[:m.start()] + (f"== verify: {m.group(1)} ({passed} pass / {skipped} skipped / "
                               f"{m.group(3)} fail) ==") + text[m.end():]


def pull_failure_kind(stderr: str) -> str:
    """`extract` when the daemon's error text says the bytes arrived and the
    storage refused them; `download` for everything else (unreachable
    registry, a dropped manifest, a TLS or EOF failure, a firewalled
    daemon's errno). A transport marker with no strong extract sign is a
    download failure whatever errno rides with it."""
    text = (stderr or "").lower()
    if any(sign in text for sign in _EXTRACT_STRONG):
        return "extract"
    if any(mark in text for mark in _TRANSPORT_MARKS):
        return "download"
    if any(err in text for err in _EXTRACT_ERRNO) and any(w in text for w in _STORAGE_WORDS):
        return "extract"
    return "download"


def pull_failure_fix(kind: str, image: str, download_fix: str) -> str:
    """The `what to do` for a failed pull or a compose up that could not
    mount: a download failure keeps the registry-side advice it was given;
    an extraction/mount failure names the daemon's storage and the one
    check that detects it — a RUN, because a plain pull passes on such a
    daemon (measured 2026-09-06: `docker pull debian:stable-slim` succeeded
    on a stranger's daemon where no container could start)."""
    if kind != "extract":
        return download_fix
    return (f"the registry answered and every layer downloaded, but THIS daemon's "
            f"storage could not extract or mount {image} — a nested daemon whose data "
            "root sits on overlayfs, or a full or read-only data root. Prove it with "
            "`docker run --rm alpine true` (exit 0 means the daemon can run a container): "
            "a plain `docker pull` PASSES on such a daemon and only a run detects it "
            "(measured 2026-09-06 on a stranger's daemon — `docker pull debian:stable-slim` "
            "succeeded where no container could start). The cure is the daemon's storage "
            "— `-v /var/lib/docker` on a nested daemon, or `--storage-driver vfs` — not "
            "the registry; `docker save | docker load` fails on the same layers")


def sandbox_image_fix(image: str) -> str:
    """The cure for an absent sandbox image: a PLAIN pull first. The
    published tag is a two-platform index since CP-64, so a plain pull
    resolves this daemon's native platform (a stranger's arm64 daemon got
    native arm64 and ran Node, 2026-09-06); the amd64 override is for one
    measured condition only, never a default on ARM."""
    return (f"docker pull {image}   (a plain pull: the published tag is a two-platform "
            "index since CP-64 and resolves this daemon's native platform; if — and only "
            "if — that pull answers `no matching manifest for linux/<arch>`, pull again "
            "with --platform linux/amd64 and the sandbox runs under emulation) — or load "
            "it out-of-band (docker save | docker load); --skip-sandbox-image records the "
            "absence and continues")


def compose_up(rundir: Path, *args: str) -> subprocess.CompletedProcess:
    """`docker compose up` with its output captured so a failure can be
    classified (pull_failure_kind), then re-emitted so the live
    `Container … Started` lines still reach the terminal."""
    proc = compose(rundir, "up", *args, capture_output=True)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n", flush=True)
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n",
              file=sys.stderr, flush=True)
    return proc


def image_identity(image: str) -> dict:
    """What the daemon holds under this reference: the image id and the
    registry digests it was pulled by (a `docker load`ed image has none)."""
    proc = run(["docker", "image", "inspect", "--format",
                "{{.Id}} {{json .RepoDigests}} {{.Os}}/{{.Architecture}}", image],
               capture_output=True)
    if proc.returncode != 0:
        return {}
    ident, digests, plat = proc.stdout.strip().split(" ", 2)
    try:
        digests = json.loads(digests)
    except ValueError:
        digests = []
    return {"id": ident, "repo_digests": digests, "platform": plat}


def compose(rundir: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return run(["docker", "compose", "-f", str(rundir / "compose.yaml"),
                "--env-file", str(rundir / ".env"), *args], **kw)


COMPOSE_HEAD = """\
# GENERATED by {prog} for run {run} — do not edit; re-run `up`.
# Only the services this run CREATED are here; adopted ones live elsewhere.
# Secrets are interpolated from the run's .env (compose --env-file), never
# written into this file.
name: {project}
services:
"""

COMPOSE_FORGEJO = """\
  forgejo:
    image: {image}
    container_name: {container}
    environment:
      USER_UID: "{uid}"
      USER_GID: "{gid}"
      FORGEJO__security__INSTALL_LOCK: "true"
      FORGEJO__server__DOMAIN: {container}
      FORGEJO__server__HTTP_PORT: "3000"
      FORGEJO__server__ROOT_URL: http://{container}:3000/
      FORGEJO__server__DISABLE_SSH: "true"
      FORGEJO__service__DISABLE_REGISTRATION: "true"
      # closed from the first start (CP-56/CP-58): every reader presents the
      # read-scoped token — the scaffold's read-back (CP-59), verify's
      # clone-back, the MCP index build, the sandbox clone
      FORGEJO__service__REQUIRE_SIGNIN_VIEW: "{signin}"
      FORGEJO__mailer__ENABLED: "false"
      FORGEJO__log__LEVEL: Warn
    ports:
      - "127.0.0.1:{port}:3000"
    volumes:
      - {data}:/data
    restart: unless-stopped
"""

COMPOSE_MCP = """\
  mcp:
    image: {image}
    container_name: {container}
{user}    environment:
      {secret_env}: ${{{secret_env}:?the run's .env carries it — pass --env-file}}
      {read_env}: ${{{read_env}:?the run's .env carries it — pass --env-file}}
    ports:
      - "127.0.0.1:{port}:8790"
    extra_hosts:
      - host.docker.internal:host-gateway
    volumes:
      - {data}:/app/data
      - {config}:/app/config.yaml:ro
{hf_mount}{decisions_mount}    restart: unless-stopped
"""

MCP_DECISIONS_MOUNT = "/app/decisions"     # where the decisions drop lands, read-only


# CP-88 (corpus-contract v3, ADR-0038): the corpus's own `decisions/` is
# the DEFAULT drop — validated with the tree, locked in decisions.lock.json,
# verified against the served drop; `--decisions-dir` is the OVERRIDE (the
# CP-79 route, kept: a drop beside the corpus, recorded, a re-run keeps it,
# '' removes it). Both named at once is a refusal that says which wins —
# never a silent precedence.

class DecisionsSourceConflict(Exception):
    def __init__(self, what: str, found: str, expected: str, fix: str) -> None:
        super().__init__(f"{what} found: {found} expected: {expected} what to do: {fix}")
        self.parts = (what, found, expected, fix)


def corpus_decisions_dir(corpus_path: Path) -> str | None:
    """`<corpus>/decisions` when it holds at least one .xml file, else None
    (absent, or the scaffold's README-only directory — the synthetic 30)."""
    ddir = Path(corpus_path) / ic.DECISIONS_DIR
    if ddir.is_dir() and any(n.endswith(".xml") for n in os.listdir(ddir)):
        return str(ddir.resolve())
    return None


def recorded_decisions_flag(prior_mcp: dict) -> str | None:
    """The --decisions-dir a previous `up` recorded, if the record's drop came
    from the flag (a pre-CP-88 record has no `decisions_source`: the flag
    was the only route then). A recorded corpus-route drop is re-resolved
    from the corpus, never replayed as an override."""
    source = prior_mcp.get("decisions_source") or ("flag" if prior_mcp.get("decisions_dir") else "none")
    return prior_mcp.get("decisions_dir") if source == "flag" else None


def resolve_decisions_source(corpus_drop: str | None, override) -> tuple[str | None, str]:
    """(host directory to mount or None, source in {corpus, flag, none}).
    `override` is --decisions-dir as answered (flag, answers file, prompt,
    or the recorded flag): '' or None = no override."""
    override = str(override) if override not in (None, "") else None
    if override and corpus_drop and \
            str(Path(override).expanduser().resolve()) == corpus_drop:
        return corpus_drop, "corpus"       # the flag named the corpus's own decisions/
    if override and corpus_drop:
        n_xml = len([n for n in os.listdir(corpus_drop) if n.endswith(".xml")])
        raise DecisionsSourceConflict(
            "two decisions drops for one estate.",
            f"the corpus's own decisions/ ({corpus_drop}, {n_xml} .xml file(s)) AND "
            f"--decisions-dir {override} (given now, or recorded by this run's earlier `up`)",
            "one drop — the corpus's decisions/ WINS under corpus-contract v3 (row 73): it "
            "is corpus data, locked in decisions.lock.json and verified against the served "
            "drop; the flag is the override for a drop kept outside a corpus",
            f"serve the corpus's: omit --decisions-dir (a recorded one: pass --decisions-dir "
            f"''); or keep the flag's drop: move the corpus's out (mv {corpus_drop} "
            f"<elsewhere>) and re-run")
    if override:
        return str(Path(override).expanduser().resolve()), "flag"
    if corpus_drop:
        return corpus_drop, "corpus"
    return None, "none"

COMPOSE_NET_OWN = """\
networks:
  default:
    name: {network}
"""

COMPOSE_NET_EXT = """\
networks:
  default:
    name: {network}
    external: true
"""


# --------------------------------------------------------------- forgejo

class Forgejo:
    def __init__(self, url: str, container_url: str, admin: tuple[str, str] | None,
                 mode: str) -> None:
        self.url = url.rstrip("/")                  # as this host reaches it
        self.container_url = container_url.rstrip("/")   # as a container does
        self.admin = admin
        self.mode = mode                            # created | adopted
        self.signin: bool | None = None

    def api(self, method: str, path: str, body: dict | None = None,
            auth: tuple[str, str] | None = None, token: str | None = None):
        headers = {"Authorization": f"token {token}"} if token else None
        return http(method, f"{self.url}/api/v1{path}", body, headers=headers,
                    auth=auth if not token else None)

    def probe(self) -> None:
        status, body = http("GET", f"{self.url}/api/healthz", timeout=5)
        if status != 200:
            die(f"Forgejo at {self.url} is not reachable.",
                f"GET /api/healthz -> {status} {body}", "200",
                "check the URL (this host must reach it), that the instance "
                "is up, and that the port is published to this host")
        status, _ = http("GET", f"{self.url}/api/v1/version", timeout=5)
        self.signin = status == 403     # anonymous read refused = sign-in required
        status, me = self.api("GET", "/user", auth=self.admin)
        if status != 200 or not isinstance(me, dict):
            die(f"the admin credential for {self.url} was rejected.",
                f"GET /api/v1/user as {self.admin[0]!r} -> {status}", "200",
                f"the admin's username and PASSWORD (basic auth — an admin "
                f"token cannot mint tokens for the owner, measured on Forgejo "
                f"16); export {ADMIN_PASSWORD_ENV} or pass "
                f"--forgejo-admin-password-file")
        if not me.get("is_admin"):
            die(f"{self.admin[0]!r} is not a Forgejo administrator on {self.url}.",
                f"is_admin={me.get('is_admin')}", "an admin account",
                "creating the owner and minting its tokens needs an admin; "
                "use one, or have the owner's tokens minted for you")

    def owner_exists(self, owner: str) -> bool:
        status, _ = self.api("GET", f"/users/{owner}", auth=self.admin)
        return status == 200

    def create_owner(self, owner: str, password: str) -> None:
        status, body = self.api("POST", "/admin/users", {
            "username": owner, "password": password,
            "email": f"{owner}@gsj.invalid", "must_change_password": False,
        }, auth=self.admin)
        if status not in (200, 201):
            die(f"could not create the owner {owner!r} on {self.url}.",
                f"POST /api/v1/admin/users -> {status} {body}", "201",
                "Forgejo's message above is authoritative")

    def _pages(self, path: str, what: str) -> list:
        """Every page of a list endpoint — until an empty page, since the
        server caps the page size (MAX_RESPONSE_ITEMS) below what is asked."""
        items, page = [], 1
        while True:
            status, body = self.api("GET", f"{path}?limit=50&page={page}", auth=self.admin)
            if status != 200 or not isinstance(body, list):
                die(f"could not list {what}.", f"GET {path} -> {status}", "200", "see above")
            if not body:
                return items
            items += body
            page += 1
            if page > 200:
                return items

    def owner_repos(self, owner: str) -> list[str]:
        return sorted(r["name"] for r in self._pages(f"/users/{owner}/repos",
                                                     f"{owner!r}'s repositories"))

    def branches(self, owner: str, repo: str) -> dict[str, str]:
        return {b["name"]: b["commit"]["id"]
                for b in self._pages(f"/repos/{owner}/{repo}/branches",
                                     f"the branches of {owner}/{repo}")}

    def token_valid(self, token: str, owner: str) -> bool:
        status, me = self.api("GET", "/user", token=token)
        return status == 200 and isinstance(me, dict) and me.get("login") == owner

    def mint_token(self, owner: str, label: str, scopes: list[str]) -> str:
        name = f"estate-{label}-{int(time.time())}"   # pre-CP-72 tokens are named bringup-*
        status, body = self.api("POST", f"/users/{owner}/tokens",
                                {"name": name, "scopes": scopes}, auth=self.admin)
        if status not in (200, 201) or not isinstance(body, dict) or "sha1" not in body:
            die(f"could not mint the {label} token for {owner!r}.",
                f"POST /users/{owner}/tokens -> {status} {body}", "201 with sha1",
                "the admin must authenticate with its PASSWORD (basic auth); "
                "Forgejo refuses token-for-others under token auth")
        return credential(body["sha1"], f"Forgejo {label} token")


def create_forgejo(rundir: Path, run: Run, port: int, signin: bool,
                   network: str, external_net: bool, image: str) -> Forgejo:
    container = f"gsj-{run.name}-forgejo"
    uid = os.getuid() if platform.system() == "Linux" else 1000
    gid = os.getgid() if platform.system() == "Linux" else 1000
    (rundir / "forgejo-data").mkdir(exist_ok=True)
    run.record.setdefault("compose", {})["forgejo"] = {
        "image": image, "container": container, "port": port,
        "data": str(rundir / "forgejo-data"), "signin": signin, "uid": uid, "gid": gid}
    write_compose(rundir, run, network, external_net)
    PH.start("forgejo", f"docker compose up ({container}, {image}, 127.0.0.1:{port}, "
                        f"sign-in {'ON' if signin else 'OFF'} from the first start)")
    pulled = False
    if not image_present(image):
        # the pull is compose's own step; done here first so a registry
        # failure is THIS refusal (wishlist 52) and not a compose stack trace
        pulled = True
        pull = image_pull(image, "forgejo")
        if pull.returncode != 0:
            tag = image_tag(image)
            kind = pull_failure_kind(pull.stderr)
            die(f"the Forgejo image {image} could not be pulled"
                + (" — downloaded, then not extractable." if kind == "extract" else "."),
                (pull.stderr.strip().splitlines() or ["no error text"])[-1],
                "a pullable image (both platform manifests served — a registry "
                "cleanup can drop them while the tag's index still lists them: "
                "16.0.2 on codeberg, measured 2026-08-30)" if kind != "extract"
                else "a daemon whose storage can extract and mount OCI layers",
                pull_failure_fix(
                    kind, image,
                    f"pass --forgejo-image <ref> naming a live one — another tag "
                    f"(the pin {FORGEJO_IMAGE} was measured pullable 2026-08-30), the "
                    f"mirror {FORGEJO_IMAGE_MIRROR}:{tag} (measured then to serve the "
                    f"16.0.x tags at codeberg's own digests), or name@sha256:<digest> to "
                    f"pin bytes — or, on a host that cannot reach registries, load "
                    f"{image} out-of-band (docker save | docker load) and re-run"))
    up = compose_up(rundir, "-d", "forgejo")
    if up.returncode != 0:
        kind = pull_failure_kind(up.stderr)
        die("`docker compose up forgejo` failed"
            + (" — the daemon could not extract or mount the image." if kind == "extract"
               else "."),
            (up.stderr.strip().splitlines() or ["the compose error above"])[-1],
            "a daemon whose storage can extract and mount OCI layers" if kind == "extract"
            else None,
            pull_failure_fix(kind, image,
                             "the compose error is authoritative (the image is present: "
                             f"{image}); `docker logs {container}` if the container started"))
    ident = image_identity(image)
    run.record["compose"]["forgejo"].update(
        {"image_id": ident.get("id"), "image_repo_digests": ident.get("repo_digests"),
         "image_platform": ident.get("platform"), "image_pulled_by_run": pulled})
    if image == FORGEJO_IMAGE and ident.get("repo_digests") and not any(
            d.endswith("@" + FORGEJO_IMAGE_DIGEST) for d in ident["repo_digests"]):
        warn("forgejo", f"{image} resolved to {ident['repo_digests']}, not the index "
             f"this script measured ({FORGEJO_IMAGE_DIGEST[:19]}…, 2026-08-30) — the "
             "tag was re-cut on its registry; the admin-CLI/token/sign-in behaviour "
             "below was measured on the pinned bytes, so read this run's phases "
             "critically (pin bytes with --forgejo-image name@sha256:…)")
    url = f"http://127.0.0.1:{port}"
    started, wall0 = time.monotonic(), time.time()     # monotonic budget (CP-96)
    while time.monotonic() - started < FORGEJO_HEALTHZ_BUDGET_S:
        if http("GET", f"{url}/api/healthz", timeout=3)[0] == 200:
            break
        time.sleep(2)
    else:
        die(f"Forgejo did not answer /api/healthz within the {FORGEJO_HEALTHZ_BUDGET_S:.0f} s budget.",
            f"waited {time.monotonic() - started:.0f} s on this process's clock (the wall clock "
            f"advanced {time.time() - wall0:.0f} s)", "HTTP 200 from /api/healthz",
            f"docker logs {container}; the first start initialises the "
            f"instance — re-run once it settles (the run is resumable)")
    # the admin: created once via the in-container CLI with a RANDOM password
    # (never on an argv), kept in the run's .env
    listing = compose(rundir, "exec", "-T", "forgejo", "su", "git", "-c",
                      "forgejo admin user list", capture_output=True)
    if listing.returncode != 0:
        die("forgejo's CLI did not answer inside the container.",
            listing.stderr.strip(), None, f"docker logs {container}; then re-run")
    if not re.search(rf"^\d+\s+{re.escape(ADMIN_USER)}\s", listing.stdout, re.M):
        made = compose(rundir, "exec", "-T", "forgejo", "su", "git", "-c",
                       f"forgejo admin user create --admin --username {ADMIN_USER} "
                       f"--random-password --email {ADMIN_USER}@gsj.invalid "
                       f"--must-change-password=false", capture_output=True)
        m = re.search(r"password is '([^']+)'", made.stdout)
        if made.returncode != 0 or not m:
            die(f"could not create the admin {ADMIN_USER!r}.",
                (made.stderr or made.stdout).strip(), "a random password printed",
                f"docker logs {container}")
        run.env[ADMIN_PASSWORD_ENV] = credential(m.group(1), ADMIN_PASSWORD_ENV)
        run.write_env()
        say("forgejo", f"admin {ADMIN_USER!r} created; its password is in .env "
                       f"as {ADMIN_PASSWORD_ENV}")
    elif ADMIN_PASSWORD_ENV not in run.env:
        die(f"the admin {ADMIN_USER!r} exists but its password is not in this run's .env.",
            f"{ADMIN_USER} listed; {ADMIN_PASSWORD_ENV} absent from {rundir / '.env'}",
            "the password this run generated",
            "restore .env, or set the admin's password by hand (`forgejo admin "
            f"user change-password`) and put it in .env as {ADMIN_PASSWORD_ENV}")
    fj = Forgejo(url, f"http://{container}:3000",
                 (ADMIN_USER, run.env[ADMIN_PASSWORD_ENV]), "created")
    fj.probe()
    PH.done(f"healthy at {url} (containers: {fj.container_url}); {image}"
            f"{' pulled' if pulled else ' present'}; sign-in {'ON' if fj.signin else 'OFF'}")
    return fj


def write_compose(rundir: Path, run: Run, network: str, external_net: bool) -> None:
    parts = [COMPOSE_HEAD.format(prog=PROG, run=run.name, project=f"gsj-{run.name}")]
    cf = run.record.get("compose", {}).get("forgejo")
    if cf:
        parts.append(COMPOSE_FORGEJO.format(
            image=cf["image"], container=cf["container"], port=cf["port"],
            data=cf["data"], signin="true" if cf["signin"] else "false",
            uid=cf["uid"], gid=cf["gid"]))
    cm = run.record.get("compose", {}).get("mcp")
    if cm:
        hf_mount = ("      - %s:%s:ro\n" % (cm["hf_model_dir"], cm["hf_model_mount"])
                    if cm.get("hf_model_dir") else "")
        decisions_mount = ("      - %s:%s:ro\n" % (cm["decisions_dir"], MCP_DECISIONS_MOUNT)
                           if cm.get("decisions_dir") else "")
        user = f'    user: "{cm["uid"]}:{cm["gid"]}"\n' if cm.get("uid") is not None else ""
        parts.append(COMPOSE_MCP.format(
            image=cm["image"], container=cm["container"], port=cm["port"],
            data=cm["data"], config=cm["config"], secret_env=MCP_SECRET_ENV,
            read_env=cm["read_env"], hf_mount=hf_mount,
            decisions_mount=decisions_mount, user=user))
    parts.append((COMPOSE_NET_EXT if external_net else COMPOSE_NET_OWN)
                 .format(network=network))
    (rundir / "compose.yaml").write_text("".join(parts))


# ------------------------------------------------------------------- mcp

MCP_CONFIG = """\
# GENERATED by {prog} for run {run} — do not edit; re-run `up`.
# Schema: estate/mcp-service/config.yaml (README.md#configuration-reference).
source:
  base_url: {forgejo_url}
  owner: {owner}
  repos: [{repos}]
  ref_main: main
  ref_pattern: "timestep-{{T}}"
  auth_token_env: {read_env}
  clone_cache_dir: ./data/clones

embedding:
  model: {model}
  revision: {revision}
  device: cpu
  batch_size: 32
  normalize: true

chunking:
  max_tokens: {chunk_max}
  overlap: {chunk_overlap}
  respect_page_boundaries: true

index:
  path: ./data/index
  rebuild: {rebuild}

search:
  default_k: 5
  max_k: 20
  method: chroma

decisions:
  seed: 20260204
  corpus_size: 30

auth:
  token_secret_env: {secret_env}
  leeway_s: 30

server:
  host: 0.0.0.0
  port: 8790
  log_level: info
  request_log_fields: [episode_id, case_id, timestep, tool, k, n_results,
                       latency_ms, cache_hit]
"""


# CP-73 (CP-70 item 7): the config the index is built under is the
# operator's to see BEFORE the embed — the most expensive step of a real
# bring-up and the one hardest to undo. Two halves: `--mcp-config` (the
# scripted answer: a YAML of retrieval-section overrides merged onto the
# generated config) and the review block below (the human one: printed
# always, confirmed only when an embed is about to be spent — never a
# stop under -y). The estate keeps its own sections: source/auth/index/
# server are the run's wiring (URLs, token variable names, the store
# path, the --rebuild posture) and a file that sets them is refused.

# One host description of each operator setting. Contract tests execute the
# actual ServiceConfig, including validators that JSON Schema cannot express.
# Types stay the estate's strict YAML subset (no Pydantic coercion at this seam).
MCP_FIELDS = {
    "embedding": {
        "model": {"type": str, "answer": "embedding_model", "pattern": r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?",
                  "consequence": "model re-pin", "review": "HF model id; use name or owner/name", "fingerprint": True},
        "revision": {"type": str, "answer": "embedding_revision", "pattern": r"[0-9a-f]{40}", "consequence": "model re-pin",
                     "review": "full 40-character lowercase hexadecimal commit SHA; resolve a branch/tag to its commit", "fingerprint": True},
        "device": {"type": str, "consequence": "speed only, not identity",
                   "review": "embedding device", "fingerprint": False},
        "batch_size": {"type": int, "minimum": 1, "consequence": "whole-corpus re-embed",
                       "review": "encode composition is identity, not only speed; 32 preserves the pre-CP-79 fingerprint bytes (absent when 32)", "fingerprint": True},
        "normalize": {"type": bool, "literal": True, "consequence": "model re-pin",
                      "review": "cosine-space embeddings require true; false is retired", "fingerprint": True},
    },
    "chunking": {
        "max_tokens": {"type": int, "answer": "chunk_max_tokens", "minimum": 16, "consequence": "whole-corpus re-embed",
                       "review": "token window", "fingerprint": True},
        "overlap": {"type": int, "answer": "chunk_overlap", "minimum": 0, "consequence": "whole-corpus re-embed",
                    "less_than": "max_tokens", "review": "overlap must be smaller than max_tokens", "fingerprint": True},
        "respect_page_boundaries": {"type": bool, "literal": True, "consequence": "whole-corpus re-embed",
                                    "review": "page boundaries require true", "fingerprint": True},
    },
    "search": {
        "default_k": {"type": int, "minimum": 1, "consequence": "serving-only",
                      "review": "default number of hits", "fingerprint": False},
        "max_k": {"type": int, "minimum": 1, "consequence": "serving-only",
                  "review": "maximum number of hits", "fingerprint": False},
        "method": {"type": str, "literal": "chroma", "consequence": "serving-only",
                   "review": "use chroma; exact search is retired", "fingerprint": False},
    },
    "decisions": {
        "seed": {"type": int, "consequence": "decisions collection alone",
                 "review": "synthetic generator seed", "fingerprint": True},
        "corpus_size": {"type": int, "minimum": 1, "consequence": "decisions collection alone",
                        "review": "synthetic decision count", "fingerprint": True},
        "path": {"type": str, "nullable": True, "flag_only": True,
                 "consequence": "decisions collection alone", "review": "the corpus's decisions/ by default (corpus-contract v3), --decisions-dir overrides; the estate writes the read-only container mount", "fingerprint": True},
    },
}
MCP_OPERATOR_SECTIONS = tuple(MCP_FIELDS)
MCP_ESTATE_SECTIONS = ("source", "auth", "index", "server")
MCP_SECTION_KEYS = {section: tuple(fields) for section, fields in MCP_FIELDS.items()}
MCP_FINGERPRINT_KEYS = tuple((section, key) for section, fields in MCP_FIELDS.items()
                             for key, spec in fields.items() if spec["fingerprint"])
MCP_CONSEQUENCES = {
    "model re-pin": "REFUSED against the built store until --rebuild re-embeds it (CP-57: a model change is a re-pin, not staleness)",
    "whole-corpus re-embed": "a re-embed of the WHOLE corpus (fingerprint components — the next start rebuilds the index)",
    "decisions collection alone": "the decisions collection alone re-embeds; the case-page collections reuse",
    "serving-only": "nothing re-embeds — edit {cfg_path} and restart the container (serving-only)",
    "speed only, not identity": "speed only, not identity",
}


def mcp_fingerprint_components(doc: dict) -> dict:
    return {f"{sec}.{key}": (doc.get(sec) or {}).get(key)
            for sec, key in MCP_FINGERPRINT_KEYS}


def _mcp_problems(doc, *, overrides: bool) -> list[str]:
    if not isinstance(doc, dict):
        return ["the file is not a YAML mapping — use section: {key: value}"]
    problems = []
    for section in sorted(doc, key=str):
        if section in MCP_ESTATE_SECTIONS:
            if overrides:
                problems.append(f"{section}: is the estate's (the run's wiring) — remove this section")
            continue
        if section not in MCP_FIELDS:
            problems.append(f"{section}: not a retrieval section — use {', '.join(MCP_FIELDS)}")
            continue
        values = doc[section]
        if not isinstance(values, dict):
            problems.append(f"{section}: must be a mapping of that section's keys — use key: value")
            continue
        for key in sorted(values, key=str):
            name, value = f"{section}.{key}", values[key]
            spec = MCP_FIELDS[section].get(key)
            if spec is None:
                problems.append(f"{name}: not a key of that section — remove it or use {', '.join(MCP_FIELDS[section])}")
                continue
            if overrides and spec.get("flag_only"):
                problems.append(f"{name}: cannot be set in this file — {spec['review']}")
                continue
            if value is None and spec.get("nullable"):
                continue
            if type(value) is not spec["type"]:
                problems.append(f"{name}: got {value!r}; must be {spec['type'].__name__} — use that YAML type (the estate does not coerce values)")
                continue
            if "minimum" in spec and value < spec["minimum"]:
                problems.append(f"{name}: got {value!r}; expected >= {spec['minimum']} — set {name} to at least {spec['minimum']}")
            if "literal" in spec and value != spec["literal"]:
                problems.append(f"{name}: got {value!r}; expected {spec['literal']!r} — {spec['review']}")
            if "pattern" in spec and re.fullmatch(spec["pattern"], value) is None:
                problems.append(f"{name}: got {value!r}; expected {spec['review']} — replace {name} with that value")
            other = spec.get("less_than")
            if not overrides and other and type(values.get(other)) is int and value >= values[other]:
                problems.append(f"{name}: got {value!r}; expected < {section}.{other} ({values[other]}) — lower {name} or increase {section}.{other}")
    return problems


def mcp_override_problems(doc) -> list[str]:
    """Validate a partial operator file; wiring stays owned by the estate."""
    return _mcp_problems(doc, overrides=True)


def mcp_config_problems(doc) -> list[str]:
    """Validate effective operator settings after template/record/flag merging."""
    return _mcp_problems(doc, overrides=False)


def load_mcp_overrides(path: str | None) -> dict | None:
    """None = no flag; {} = empty YAML (clears recorded residuals)."""
    if not path:
        return None
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        die(f"--mcp-config {path} is unreadable.", str(exc),
            "a YAML mapping of retrieval sections "
            f"({', '.join(MCP_OPERATOR_SECTIONS)})", "fix the file")
    if doc is None:
        doc = {}
    problems = mcp_override_problems(doc)
    if problems:
        die(f"--mcp-config {path} is not a retrieval-config overrides file.",
            "; ".join(problems),
            f"only the operator sections: {', '.join(MCP_OPERATOR_SECTIONS)} "
            "with the keyed types and constraints above",
            "correct each named key as advised above and re-run; source, auth, "
            "index and server are wired by this run and must be removed if present")
    return doc


def render_mcp_template(**values) -> str:
    # HF ids such as "on" and all-digit SHAs are valid strings, but bare
    # YAML would reinterpret them. Quote only those scalars; default bytes
    # and MCP_CONFIG's public placeholder set stay unchanged.
    for key in ("model", "revision"):
        value = values[key]
        if type(value) is str and type(yaml.safe_load(value)) is not str:
            values[key] = json.dumps(value)
    return MCP_CONFIG.format(**values)


def render_mcp_config(base_text: str, overrides: dict) -> str:
    """Keep default template bytes exact; an override updates only named keys."""
    if not overrides:
        return base_text
    doc = yaml.safe_load(base_text)
    for section, values in overrides.items():
        doc.setdefault(section, {}).update(values)
    head = ""
    for line in base_text.splitlines():
        if not line.startswith("#"):
            break
        head += line + "\n"
    return head + yaml.safe_dump(doc, sort_keys=False)


def mcp_config_review(doc: dict, cfg_path: Path,
                      decisions_dir: str | None = None,
                      decisions_source: str = "flag") -> str:
    lines = ["effective retrieval config (written to " + str(cfg_path) + "):"]
    for section, fields in MCP_FIELDS.items():
        for key, spec in fields.items():
            value = (doc.get(section) or {}).get(key)
            lines.append(f"      {section}.{key} {value!r} — {spec['review']}")
            consequence = MCP_CONSEQUENCES[spec["consequence"]].format(cfg_path=cfg_path)
            lines.append(f"          to change later: {consequence}")
    d = doc.get("decisions") or {}
    if d.get("path"):
        count = (len([f for f in os.listdir(decisions_dir) if f.endswith(".xml")])
                 if decisions_dir and os.path.isdir(decisions_dir) else "?")
        origin = ("the corpus's own decisions/ (corpus-contract v3, locked in decisions.lock.json)"
                  if decisions_source == "corpus" else "--decisions-dir, the override")
        lines.append(f"      decisions           rii-dok v1 drop — {count} .xml file(s) in {decisions_dir} (read-only; {origin}), not the synthetic generator\n"
                     "          Randnummern chunks from the drop; a cold embed is minutes on a contended CPU host (round four: a 313-unit drop inside a laptop's nested container), seconds on an idle server")
    else:
        lines.append(f"      decisions           synthetic (seed {d.get('seed')}, corpus_size {d.get('corpus_size')}) — no real court text; synthetic 30 by default (no drop)")
    return "\n".join(lines)


def mcp_integer_answer(value, key: str) -> int:
    # Numeric strings were valid answer-file inputs. Floats/bools must not
    # silently become a different integer before the descriptor sees them.
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        return int(value)
    die(f"{key}: the chunk window answer is not an integer.", repr(value),
        "an integer, without a fractional part or boolean coercion",
        f"correct {key} in --answers or its --chunk flag and re-run")


def mcp_config_inputs(A: Answers, previous: dict) -> dict:
    """Resolve once, before creating anything; preserve CP-73 answer precedence."""
    prior = previous.get("mcp") or {}
    pm = previous.get("compose", {}).get("mcp") or {}
    mode = A.get("mcp", "retrieval service (MCP): create, or adopt "
                 "(recorded: a re-run keeps it; --retarget moves it)",
                 "adopt" if prior.get("mode") == "adopted" else "create",
                 choices=("create", "adopt"))
    overrides = load_mcp_overrides(A.get("mcp_config", None, None))
    if mode == "adopt" and (overrides is not None or A.get("decisions_dir", None, None)):
        die("--mcp-config and --decisions-dir configure a service this run would CREATE.",
            "--mcp adopt with a create-only configuration flag", "--mcp create, or neither flag",
            "change the adopted service's own config and restart it there; "
            "its operator owns the file and decisions mount")
    emb = (overrides or {}).get("embedding") or {}
    chunk = (overrides or {}).get("chunking") or {}
    model = A.get("embedding_model", "embedding model (HF id; binding to the "
                  "index store until --rebuild — CP-57)",
                  emb.get("model") or (prior.get("embedding") or {}).get("model") or DEFAULT_EMBEDDING_MODEL)
    revision = A.get("embedding_revision", "embedding revision (full commit SHA; binding with the model)",
                     (emb.get("revision") if emb.get("model") in (None, model) else None)
                     or ((prior.get("embedding") or {}).get("revision")
                         if (prior.get("embedding") or {}).get("model") == model
                         else DEFAULT_EMBEDDING_REVISION if model == DEFAULT_EMBEDDING_MODEL else None),
                     required=True)
    chunk_prev = pm.get("chunking") or {}
    chunk_max = mcp_integer_answer(A.get("chunk_max_tokens", None,
                                        chunk.get("max_tokens", chunk_prev.get("max_tokens", 220))),
                                   "chunking.max_tokens")
    chunk_overlap = mcp_integer_answer(A.get("chunk_overlap", None,
                                            chunk.get("overlap", chunk_prev.get("overlap", 40))),
                                       "chunking.overlap")
    # Identity/window answers bind above; every other key is a recorded residual.
    residual = {sec: {k: v for k, v in vals.items() if not MCP_FIELDS[sec][k].get("answer")}
                for sec, vals in (overrides or {}).items()}
    residual = {sec: vals for sec, vals in residual.items() if vals}
    if overrides is None and pm.get("config_overrides"):
        residual = pm["config_overrides"]
        say("mcp", f"--mcp-config overrides kept from the record: {sorted(residual)} "
                   "(pass --mcp-config to replace them; an empty file clears them)")
    problems = mcp_override_problems(residual)
    if not problems:
        for section, fields in residual.items():
            for key in fields:
                if MCP_FIELDS[section][key].get("answer"):
                    problems.append(f"recorded config_overrides.{section}.{key}: is a bound answer, not a residual — "
                                    f"replace the recorded overrides with --mcp-config and set --{MCP_FIELDS[section][key]['answer'].replace('_', '-')}")
    problems += mcp_config_problems({"embedding": {"model": model, "revision": revision},
                                     "chunking": {"max_tokens": chunk_max, "overlap": chunk_overlap}})
    if not problems:
        # Wiring is irrelevant to these validators. Use the SAME template and
        # residual merge as the generated file, so effective cross-field checks
        # see the chosen flags/record, never guessed defaults from a partial file.
        base = render_mcp_template(prog=PROG, run="preflight", forgejo_url="http://preflight",
                                 owner="preflight", repos="preflight", read_env="PREFLIGHT",
                                 model=model, revision=revision, chunk_max=chunk_max,
                                 chunk_overlap=chunk_overlap, rebuild="if-stale", secret_env=MCP_SECRET_ENV)
        doc = yaml.safe_load(render_mcp_config(base, residual))
        problems = mcp_config_problems(doc)
    if problems:
        die("the effective retrieval config is invalid; no service was created.",
            "; ".join(problems), "the keyed types, bounds and pinned values above",
            "correct the named --mcp-config key or --embedding/--chunk flag and re-run; "
            "for recorded residuals pass a corrected --mcp-config (an empty file clears them)")
    return dict(mode=mode, model=model, revision=revision, chunk_max=chunk_max,
                chunk_overlap=chunk_overlap, residual=residual)


def require_decisions_image(image: str, decisions_dir: str | None,
                            source: str = "flag") -> None:
    """Only known pre-decisions tags are rejected; custom/offline images stay valid.
    `source` (CP-88) words the refusal for the route the drop came by."""
    known = re.fullmatch(r"(?:ghcr\.io/mhganainy/)?gsj-mcp-service:"
                         r"(\d+)\.(\d+)\.(\d+)(?:-(?:arm64|aarch64|amd64))?", str(image))
    if decisions_dir and known and tuple(map(int, known.groups())) < (0, 5, 0):
        corpus_route = source == "corpus"
        die("the selected retrieval image does not support a decisions drop.",
            f"{image} with " + (f"the corpus's own decisions/ ({decisions_dir}) — "
                                "corpus-contract v3 (decisions.path)" if corpus_route
                                else "--decisions-dir (decisions.path)"),
            "MCP 0.5.0 or a custom image supporting decisions.path",
            f"pass --mcp-image {MCP_IMAGE_PUBLISHED}; on an offline host, "
            "load that image out-of-band first (docker save | docker load); "
            + ("or move decisions/ out of the corpus (then validate) to serve the synthetic 30"
               if corpus_route else
               "or omit the drop (--decisions-dir '' removes a recorded one)"))


class Mcp:
    def __init__(self, url: str, container_url: str, secret: str, mode: str) -> None:
        self.url = url.rstrip("/")
        self.container_url = container_url.rstrip("/")
        self.secret = secret
        self.mode = mode

    def health(self) -> dict | None:
        # 15 s, not 5 (CP-96): on a contended CPU host a slow /health read
        # as "unreachable" and started the docker inspect/logs cascade
        status, body = http("GET", f"{self.url}/health", timeout=HEALTH_TIMEOUT_S)
        return body if status == 200 and isinstance(body, dict) else None

    @staticmethod
    def progress_line(h: dict) -> str:
        """The poll line: the case collections' fetched/embedded counts, and
        — CP-96, round four — the collection the service is BUILDING right
        now from its per-batch `build` block (mcp-service state.py, CP-77):
        while a decisions drop embeds, `progress` names only the case
        collections (both done) and reads as finished; a stranger diagnosed
        a healthy service as wedged and restarted it."""
        prog = h.get("progress") or {}
        fetched = sum(1 for p in prog.values() if p.get("done"))
        embedded = sum(1 for p in prog.values() if p.get("embedded"))
        line = (f"{h.get('state')}: {fetched}/{len(prog)} cases fetched, "
                f"{embedded}/{len(prog)} embedded")
        b = h.get("build")
        # the block stays on a collection's LAST batch until the next
        # collection's first batch lands (measured: 30 s between the last
        # case and a 4,089-piece drop's first batch) — say so, not "building"
        stale = (isinstance(b, dict) and b.get("collection") in prog
                 and prog[b["collection"]].get("embedded") and b.get("batch") == b.get("batches"))
        if isinstance(b, dict) and b.get("collection") and not stale:
            line += (f"; building {b['collection']}: batch {b.get('batch')}/{b.get('batches')} "
                     f"({b.get('vectors')}/{b.get('total')} vectors)")
        elif h.get("state") not in ("ready", "error") and prog and embedded == len(prog):
            line += ("; the service is still working (the next collection has not reported a batch yet)"
                     if stale else "; the service is still working (no batch has landed yet)")
        return line

    def wait_ready(self, timeout_s: float, what: str,
                   container: str | None = None) -> dict:
        # CP-96: the budget is MONOTONIC — a suspended host no longer burns it
        # (round four's overnight run slept under a wall-clock deadline);
        # the wall clock is read beside it so a sleep shows in the log
        started, wall0 = time.monotonic(), time.time()
        deadline = started + timeout_s
        last = None
        last_said = started
        silent_since = None
        last_tail = None
        skew_said = 0.0
        while time.monotonic() < deadline:
            elapsed = time.monotonic() - started
            skew = (time.time() - wall0) - elapsed
            if skew - skew_said > SLEEP_SKEW_S:
                warn("mcp", f"the wall clock advanced {time.time() - wall0:.0f} s while this "
                            f"process waited {elapsed:.0f} s — the host slept or was paused "
                            f"for ~{skew:.0f} s; the {timeout_s:.0f} s budget (--ingest-timeout) "
                            "counts only the time this process waited")
                skew_said = skew
            h = self.health()
            if h is None:
                line = "unreachable"
                silent_since = silent_since or time.monotonic()
                state = {}
                if container:
                    inspected = run(["docker", "inspect", "--format", "{{json .State}}", container],
                                    capture_output=True)
                    if inspected.returncode == 0:
                        try:
                            state = json.loads(inspected.stdout)
                        except (ValueError, TypeError):
                            pass
                    if not isinstance(state, dict):
                        state = {}
                terminal = state.get("Status") in ("exited", "dead", "restarting")
                quiet = time.monotonic() - silent_since
                if container and (terminal or (quiet > 20 and (
                        last_tail is None or time.monotonic() - last_tail > 20))):
                    # a service that stops answering is not "still indexing":
                    # read the container's own tail (once per 20 s, CP-96 —
                    # not every poll) before waiting on (measured at CP-59:
                    # the amd64 image under qemu on an arm64 daemon
                    # segfaults at the embed step and the container stays
                    # "running" with a dead process)
                    last_tail = time.monotonic()
                    tail = run(["docker", "logs", "--tail", "20", container],
                               capture_output=True)
                    text = (tail.stdout or "") + (tail.stderr or "")
                    if "signal 11" in text or "Segmentation fault" in text or "rosetta error" in text:
                        die(f"the retrieval service in {container} crashed "
                            f"(its process died; the container still shows running).",
                            text.strip().splitlines()[-1],
                            "a service that answers /health while it indexes",
                            f"this daemon is {daemon_arch()} and the image is "
                            f"{'amd64' if daemon_arch() in ('arm64', 'aarch64') else 'foreign'}"
                            "-emulated — build the service natively for this arch "
                            f"(`docker build --platform linux/<arch> -t {MCP_IMAGE}-<arch> "
                            "estate/mcp-service`) and pass it with --mcp-image; production "
                            "is amd64 and runs the shipped image as is")
                    if terminal:
                        fix = (f"the service rejected decisions.path: pass --mcp-image {MCP_IMAGE_PUBLISHED} "
                               "(or a custom image supporting the drop), then re-run up"
                               if "decisions.path" in text else
                               f"inspect `docker logs --tail 80 {container}` and the run's "
                               "mcp-config.yaml; correct the startup/config error, then re-run up")
                        die(f"the retrieval service in {container} exited during startup.",
                            f"container state={state.get('Status')}, exit={state.get('ExitCode')}",
                            "a running service answering /health while it indexes", fix)
            else:
                silent_since = None
                line = self.progress_line(h)
            if h and h.get("state") == "ready":
                say("mcp", f"{what}: {line} — waited {elapsed:.0f} s of the "
                           f"{timeout_s:.0f} s budget")
                return h
            if line != last:
                say("mcp", f"{what}: {line}")
                last, last_said = line, time.monotonic()
            elif time.monotonic() - last_said >= PULL_HEARTBEAT_S:
                # nothing changed for a heartbeat interval: say so with the
                # measured wait (CP-96 — the log used to go silent for the
                # whole embed, and could not show a resumed host's clocks)
                say("mcp", f"{what}: still {line} — waited {elapsed:.0f} s of the "
                           f"{timeout_s:.0f} s budget")
                last_said = time.monotonic()
            if h and h.get("state") == "error":
                die("the retrieval service reached state=error.",
                    h.get("error"), "state=ready",
                    "the message above is the service's own; an EMBEDDING "
                    "MODEL MISMATCH is CP-57's refusal (re-run with --rebuild "
                    "to re-embed under the configured model, or ask for the "
                    "model that built the store); a chunk-window refusal "
                    "wants --chunk-max-tokens/--chunk-overlap sized to the "
                    "model; a clone failure means the read token or the "
                    "Forgejo URL as seen from the container is wrong")
            time.sleep(3)
        elapsed = time.monotonic() - started
        fix = ("the service is still building (a cold embed on a contended CPU host is minutes, "
               "not seconds — round four's laptops, four containers deep): "
               "re-run `up` WITHOUT --rebuild to keep waiting — the index survives and the "
               "service keeps building; a re-run WITH --rebuild would recreate the container and "
               "embed from zero — or raise --ingest-timeout" if last != "unreachable" else
               f"check {self.url}/health and the service's startup logs "
               + (f"(`docker logs --tail 80 {container}`); " if container else "; ")
               + "correct the service URL or startup error, then re-run")
        die(f"the retrieval service did not reach state=ready within the {timeout_s:.0f} s "
            "budget (--ingest-timeout).",
            f"waited {elapsed:.0f} s on this process's clock (the wall clock advanced "
            f"{time.time() - wall0:.0f} s); last: {last}", "state=ready", fix)

    def reindex(self) -> tuple[int, object]:
        token = ic.mint_admin_token(self.secret)
        return http("POST", f"{self.url}/admin/reindex", None,
                    headers={"Authorization": f"Bearer {token}"}, timeout=30)


def store_identity(rundir: Path) -> dict | None:
    f = rundir / "mcp-data" / "index" / "fingerprint.json"
    if not f.is_file():
        return None
    try:
        doc = json.loads(f.read_text())
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def hf_model_dir(model: str, revision: str, hf_cache: str | None) -> Path | None:
    """The host's HF cache directory for model@revision, if present."""
    home = Path(hf_cache) if hf_cache else Path(
        os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub = home / "hub" if (home / "hub").is_dir() else home
    d = hub / ("models--" + model.replace("/", "--"))
    return d if (d / "snapshots" / revision).is_dir() else None


# ----------------------------------------------------------------- engine

def probe_engine(url: str, model: str) -> dict:
    out: dict = {"url": url, "model": model, "reachable": False,
                 "models": [], "model_served": False, "tokenize": None}
    status, body = http("GET", f"{url}/v1/models", timeout=5)
    if status != 200 or not isinstance(body, dict):
        out["detail"] = f"GET /v1/models -> {status} {body}"
        return out
    out["reachable"] = True
    out["models"] = [m.get("id") for m in body.get("data", [])]
    out["model_served"] = model in out["models"]
    status, body = http("POST", f"{url}/tokenize",
                        {"model": model, "prompt": "x", "add_special_tokens": False},
                        timeout=10)
    out["tokenize"] = ("available" if status == 200 and isinstance(body, dict)
                       and isinstance(body.get("tokens"), list)
                       else f"not available (POST /tokenize -> {status})")
    return out


def host_ipv4s() -> list[str]:
    """Every non-loopback IPv4 this host carries, in interface order."""
    ips: list[str] = []
    try:
        if platform.system() == "Darwin":
            text = run(["ifconfig"], capture_output=True).stdout
        else:
            text = run(["ip", "-4", "-o", "addr"], capture_output=True).stdout
    except (FileNotFoundError, OSError):
        try:
            return sorted({ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None,
                                                                socket.AF_INET)}
                          - {"127.0.0.1"})
        except OSError:
            return []
    for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", text):
        ip = m.group(1)
        if not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    return ips


PROBE_EXEC_TIMEOUT_S = 60.0     # a `docker exec` dial loop: 3 s per candidate + slack
PROBE_RUN_TIMEOUT_S = 120.0     # the fallback `docker run` — the create is the cost
PROBE_REAP_S = 30.0             # how long a `finally` keeps trying to remove a killed run's container


def reap_container(name: str, wait_s: float = PROBE_REAP_S) -> bool:
    """Remove a named container a killed `docker run` client left to the
    daemon — and keep trying for a bound: on a copy-on-create daemon the
    create is still in flight when the client dies, and the container
    appears only when the copy ends (measured at CP-96's own proof: a
    `docker rm -f` a second after the kill found nothing, and the
    container turned up `Created` four minutes later). True when it is
    gone or never appeared within the bound."""
    started = time.monotonic()
    while True:
        removed = run(["docker", "rm", "-f", name], capture_output=True).returncode == 0
        if removed:
            return True
        if time.monotonic() - started >= wait_s:
            return False
        time.sleep(2)


def container_running(name: str) -> bool:
    proc = run(["docker", "inspect", "--format", "{{.State.Running}}", name],
               capture_output=True)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def rebuild_in_progress(url: str, container: str) -> bool:
    """A running retrieval container whose /health says it is still
    indexing (not ready, not error) — the state a timed-out --rebuild
    leaves behind (CP-96)."""
    if not container_running(container):
        return False
    status, body = http("GET", f"{url.rstrip('/')}/health", timeout=HEALTH_TIMEOUT_S)
    return (status == 200 and isinstance(body, dict)
            and body.get("state") not in (None, "ready", "error"))


def probe_dial(network: str, candidates: list, gport: int, exec_container: str | None,
               probe_image: str | None) -> tuple[list, str | None]:
    """Dial every candidate from INSIDE the run's network and say which
    answered — (results, failure). The class fix of CP-96 (round four, four
    times in three containers, both codebases): the probe used to `docker
    run --rm` the 731 MiB sandbox image under a 120 s budget, and on a
    copy-on-create storage driver the create alone outlasts the budget, so
    the probe could never pass there however often `up` re-ran — and the
    killed `docker run --rm` never fired its --rm, leaving a Created
    container per attempt. Now: `docker exec` into a container this run
    already has running on the network (nothing is created, nothing can
    leak); only with none available does it fall back to a NAMED `docker
    run` of the sandbox image that a `finally` removes; and whatever times
    out is caught and reported, never raised."""
    dial = ("import urllib.request as u\nfor h in %s:\n"
            "    try:\n        r = u.urlopen('http://%%s:%d/' %% h, timeout=3)\n"
            "        print(h, 'OK', r.status)\n"
            "    except Exception:\n        print(h, 'FAIL')\n"
            % (json.dumps(candidates), gport))
    js = ("const c=%s;(async()=>{for(const h of c){try{const r=await fetch("
          "'http://'+h+':%d/',{signal:AbortSignal.timeout(3000)});"
          "console.log(h,'OK',r.status)}catch(e){console.log(h,'FAIL')}}})()"
          % (json.dumps(candidates), gport))
    if exec_container:
        cmd, budget, cleanup = (["docker", "exec", exec_container, "python", "-c", dial],
                                PROBE_EXEC_TIMEOUT_S, None)
        via = f"`docker exec {exec_container}` (this run's own container, already on {network!r})"
    elif probe_image:
        cleanup = f"gsj-probe-{os.getpid()}"
        cmd, budget = (["docker", "run", "--name", cleanup, "--network", network, probe_image,
                        "node", "-e", js], PROBE_RUN_TIMEOUT_S)
        via = f"a `docker run` of {probe_image} named {cleanup} (removed after)"
    else:
        return [], "no container to dial from (the retrieval service is adopted and the sandbox image is absent)"
    proc, failure = None, None
    try:
        proc = run(cmd, capture_output=True, timeout=budget)
    except subprocess.TimeoutExpired:
        failure = (f"timed out after {budget:.0f} s via {via} — on a copy-on-create storage "
                   "driver (vfs) creating a container from a large image alone can take minutes")
    except OSError as exc:
        failure = f"could not start via {via}: {exc}"
    finally:
        if cleanup and not reap_container(cleanup):   # a killed `docker run --rm` never fires its --rm
            failure = ((failure or "") + f"; the daemon is still creating {cleanup} — it will appear "
                       f"as `Created` when the copy ends: `docker rm -f {cleanup}` removes it")
    if proc is not None and proc.returncode != 0 and not proc.stdout.strip():
        failure = (f"exit {proc.returncode} via {via}: "
                   + (proc.stderr.strip().splitlines() or ["no output"])[-1])
    results: list = []
    for line in (proc.stdout if proc is not None else "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in candidates:
            results.append({"candidate": parts[0], "reachable": parts[1] == "OK"})
    return results, failure


def gateway_host(network: str, gport: int, explicit: str | None,
                 probe_image: str | None, recorded: str | None = None,
                 exec_container: str | None = None) -> tuple[str, str, list]:
    """ONE address reachable from host dispatch AND from inside episode
    containers (CP-03 finding 2) — MEASURED, not assumed: a listener on
    the gateway port, and a container on the run's network dialing every
    candidate; the first that answers wins (the host reaches its own
    interface IPs trivially). Measured at CP-59 on a Docker Desktop Mac: the
    LAN interface was host-only, host.docker.internal container-only, and a
    VPN interface the one address both could dial — no heuristic knows that.
    Candidates: the compose network's gateway IP (Linux — the H200's answer),
    then every host IPv4. The dial runs inside `exec_container` when the run
    has one (CP-96); a probe that cannot run DEGRADES to the first candidate,
    labelled unmeasured, with the flag that writes a better one — it no
    longer aborts a bring-up one file short of rollout.yaml."""
    if explicit:
        return explicit, "--gateway-host (not probed)", []
    candidates: list[str] = []
    origin: dict[str, str] = {}
    if platform.system() == "Linux" and shutil.which("docker"):
        proc = run(["docker", "network", "inspect", network, "--format",
                    "{{(index .IPAM.Config 0).Gateway}}"], capture_output=True)
        if proc.returncode == 0 and proc.stdout.strip():
            candidates.append(proc.stdout.strip())
            origin[candidates[-1]] = f"the gateway IP of the compose network {network!r}"
    if recorded and recorded not in candidates:
        candidates.append(recorded)     # the run's last measured answer, re-measured
        origin[recorded] = "the run's last recorded answer"
    for ip in host_ipv4s():
        if ip not in candidates:
            candidates.append(ip)
            origin[ip] = "a host IPv4"
    try:                                # Docker Desktop with the /etc/hosts line:
        socket.gethostbyname("host.docker.internal")   # both sides dial the name
        candidates.insert(0, "host.docker.internal")
        origin["host.docker.internal"] = "the name this host resolves (an /etc/hosts line)"
    except OSError:
        pass
    results: list = []
    if not candidates:
        return "127.0.0.1", "fallback — 127.0.0.1 is NOT reachable from a sandbox", results
    first = f"{candidates[0]} = {origin.get(candidates[0], 'the first candidate')}"
    if not shutil.which("docker") or not (exec_container or probe_image):
        warn("config", f"no container to dial from ({'no docker on PATH' if not shutil.which('docker') else 'the retrieval service is adopted and the sandbox image is absent'}) — "
                       f"the gateway host is {first}, UNMEASURED; pass --gateway-host <address> "
                       "if a sandbox cannot dial it (--help says how to choose one)")
        return candidates[0], f"{first} (UNMEASURED — no container to probe from)", results
    import threading

    class _Probe(_http_server.BaseHTTPRequestHandler):   # answers 204, serves nothing
        def do_GET(self):
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a, **k):
            pass

    server = None
    try:
        server = _http_server.HTTPServer(("0.0.0.0", gport), _Probe)
    except OSError:
        pass    # something (the gateway itself?) already listens: probe it
    if server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        results, failure = probe_dial(network, candidates, gport, exec_container, probe_image)
    finally:
        if server:
            server.shutdown()
            server.server_close()
    if failure:
        warn("config", f"the gateway-host probe could not run — {failure}. The run continues "
                       f"with {first}, UNMEASURED; it was about to try {candidates}. "
                       "If a sandbox cannot dial it, re-run `up` with --gateway-host "
                       "<address> (the run is resumable: every phase before this one is "
                       "recorded and reused; --help says how to choose the address)")
        return candidates[0], f"{first} (UNMEASURED — the probe {failure.split(' —')[0].split(':')[0]})", results
    for r in results:
        if r["reachable"]:
            return r["candidate"], ("measured: dialable from a container on "
                                    f"{network!r} and from this host"), results
    die(f"no host address is dialable from a container on {network!r}.",
        f"tried {candidates} — every one timed out from the container",
        "ONE address the rollout API (host) and the sandbox both dial (CP-03)",
        "on Docker Desktop add `127.0.0.1 host.docker.internal` to /etc/hosts and "
        "pass --gateway-host host.docker.internal; on Linux the compose network's "
        "gateway IP usually works; --gateway-host <address> writes it unprobed "
        "(the run is resumable — re-run `up` with the flag)")


# ------------------------------------------------------------- the estate

@mutating_command
def cmd_up(args: argparse.Namespace) -> None:
    A = Answers(args)
    try:
        import pyarrow  # noqa: F401 — the taskbank's writer (ADR-0022 §5)
    except ImportError:
        die("pyarrow is not importable from this python.", sys.executable,
            "the taskbank phase's parquet writer",
            "pip install -r estate/corpus/requirements.txt  (same environment)"
            if CHECKOUT else "pip install pyarrow  (same environment)")
    try:
        import gsj_rollout  # noqa: F401
    except ImportError:
        die("the gsj_rollout library is not importable from this python.",
            sys.executable, "the checkout's venv (pip install -e '.[dev]')",
            "run this script with the checkout's python")
    if shutil.which("git") is None:
        die("`git` is not on PATH.", None, None, "install git")

    # ---- the corpus, validated before anything runs
    # the checkout's staging corpus is the default; the wheel has none (--corpus is required there)
    # CP-73: every interactive question says whether its answer BINDS —
    # and where a non-binding one lands, so the operator knows what to
    # edit later, not just that they may (CP-70 item 9's class).
    corpus_path = Path(A.get("corpus", "corpus root (not binding: `update` "
                                       "syncs later edits into the standing "
                                       "estate)",
                             str(HERE / "corpus" / "staging") if CHECKOUT else None,
                             required=True)).expanduser().resolve()
    if not (corpus_path / "corpus.yaml").is_file():
        load_corpus(corpus_path, None)          # the refusal, before any prompt
    try:
        raw_yaml = yaml.safe_load((corpus_path / "corpus.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw_yaml = {}
    yaml_owner = raw_yaml.get("owner") if isinstance(raw_yaml.get("owner"), str) else None
    yaml_name = raw_yaml.get("name") if isinstance(raw_yaml.get("name"), str) else None

    # ---- the run: its record is the source of every re-run default
    name = A.get("name", "run name (binding: it names the run directory, "
                         "the containers and the network)",
                 yaml_name, required=True)
    run_ = _command_run(args, name)
    run_.load()
    mc = mcp_config_inputs(A, run_.record)
    mmode, model, revision = mc["mode"], mc["model"], mc["revision"]
    chunk_max, chunk_overlap, residual = mc["chunk_max"], mc["chunk_overlap"], mc["residual"]
    prior_mcp = run_.record.get("compose", {}).get("mcp") or {}
    # CP-88: the corpus's own decisions/ is the default drop, --decisions-dir
    # the override; both named (flag, answers file or record) is refused
    # here, before any estate work — the interactive answer is resolved
    # again once the corpus has validated
    corpus_drop = corpus_decisions_dir(corpus_path)
    recorded_flag = recorded_decisions_flag(prior_mcp)
    ddir_answer = None
    if mmode == "create":
        # the one decisions question, here — before the run directory, .env
        # or any container exists — so every route (flag, answers file,
        # record, the interactive prompt) refuses two drops before estate work
        ddir_answer = A.get(
            "decisions_dir",
            "decisions drop directory (jb-<doknr>.xml files, rii-dok v1) — an OVERRIDE "
            "of the corpus's own decisions/; empty = the corpus's decisions/ when it "
            "holds any, else the synthetic 30 (a recorded override is the default "
            "shown; to drop one pass --decisions-dir '' on the command line)",
            recorded_flag)
        try:
            early_ddir, early_source = resolve_decisions_source(corpus_drop, ddir_answer)
        except DecisionsSourceConflict as exc:
            die(*exc.parts)
        require_decisions_image(A.get("mcp_image", None, prior_mcp.get("image", MCP_IMAGE)),
                                early_ddir, early_source)
    elif corpus_drop:
        warn("mcp", f"the corpus carries decisions/ ({corpus_drop}) but the adopted "
                    f"retrieval service's mount is its operator's — this `up` passes "
                    f"verify only if that service already serves this exact drop "
                    f"(/health.decisions_drop.sha256 == decisions.lock.json's); otherwise "
                    f"move decisions/ out of the corpus, or use --mcp create")
    rundir = run_.dir
    run_.prepare()
    rundir.chmod(0o700)   # the whole run is the operator's: .env, and the MCP's
    # clone cache, whose cold `clone --bare` writes the read token into
    # <case>.git/config (wishlist 47 — frozen-side; measured here at CP-59)
    run_.write_env()      # compose wants its --env-file to exist from the first `up`
    rec = run_.record
    prev = dict(rec) if run_.existing else {}
    if run_.existing:
        say("run", f"'{name}' exists (created {rec.get('created_at')}) — "
                   f"re-run: adopting what stands, backfilling what is missing")
    owner = A.get("owner", "Forgejo owner for the case repos (binding: the "
                           "repos live under it; a re-run asking for another "
                           "is refused without --retarget)",
                  prev.get("corpus", {}).get("owner") or yaml_owner)
    # CP-71: the sandbox image is the ESTATE's answer, not the corpus's —
    # a corpus.yaml that still declares one is ignored with a warning; the
    # same value rides every task row AND rollout.yaml's runtime.image, so
    # submit's row-vs-config guard passes by construction.
    simage = str(A.get("sandbox_image", "sandbox image (the harness every "
                                        "episode runs in)",
                       prev.get("sandbox_image")
                       or prev.get("corpus", {}).get("sandbox_image")  # pre-CP-71 record
                       or ic.DEFAULT_SANDBOX_IMAGE))
    corpus = load_corpus(corpus_path, owner if owner != yaml_owner else None,
                         simage)
    owner = corpus.owner
    case_ids = sorted(corpus.cases)
    push_env, read_env = ic.token_env_name(owner), ic.read_token_env_name(owner)
    say("corpus", f"{corpus.name}: {len(case_ids)} case(s) {case_ids}; owner {owner!r}; "
                  f"sandbox image {corpus.sandbox_image} (the estate's answer)")
    # ---- the sandbox image, present or named — checked HERE, before any
    # container is created or pulled (CP-94: a stranger's `up` stood Forgejo
    # up, minted tokens, pushed repos, pulled 1.28 GiB and built an index
    # for 41 minutes, then met this refusal for an image whose name it had
    # printed at +0.0s). The daemon is checked first so a stopped daemon is
    # named as such, not as a missing image; the refusal text is CP-92's.
    if not A.get("skip_sandbox_image", None, False):
        if shutil.which("docker"):
            check_daemon()
        if shutil.which("docker") and image_present(corpus.sandbox_image):
            say("sandbox", f"{corpus.sandbox_image} present — episodes run in it")
            rec["sandbox_image_present"] = True
        else:
            # CP-92: a plain pull — the published tag resolves natively on
            # arm64 since CP-64; the amd64 override was a stranger's near
            # miss when it was the default cure on every ARM daemon
            die(f"the sandbox image {corpus.sandbox_image} is not present on this daemon.",
                "docker image inspect failed (or no docker here)",
                "the image every task row names (the estate's --sandbox-image "
                "answer; corpus.yaml's own key is ignored since CP-71)",
                sandbox_image_fix(corpus.sandbox_image))
    else:
        rec["sandbox_image_present"] = (shutil.which("docker") is not None
                                        and image_present(corpus.sandbox_image))
    rec.update({"run": name, "run_dir": str(rundir), "version": script_version(),
                "sandbox_image": simage,
                "corpus": {"path": str(corpus_path), "name": corpus.name,
                           "owner": owner, "case_ids": case_ids,
                           "yaml_forgejo_base_url": corpus.base_url,
                           "yaml_mcp_url_base": corpus.mcp_url}})
    reused: list[str] = []
    backfilled: list[str] = []
    network = A.get("network", "docker network the sandbox joins (recorded: "
                               "a re-run naming another is refused without "
                               "--retarget)",
                    prev.get("network", {}).get("name", f"gsj-{name}-net"))
    external_net = network != f"gsj-{name}-net"
    rec["network"] = {"name": network, "external": external_net,
                      "created_by_run": prev.get("network", {}).get("created_by_run", False)}
    changed: list[str] = []
    prev_simage = prev.get("sandbox_image") or prev.get("corpus", {}).get("sandbox_image")
    if prev_simage and prev_simage != simage:
        changed.append(f"the sandbox image: {prev_simage!r} -> {simage!r} "
                       "(the bank rows and runtime.image move with it)")

    def retarget(what: str, before, after) -> None:
        """A re-run that asks for a different estate identity is not a re-run:
        refuse unless --retarget says so, and then say what changed."""
        if before is None or before == after:
            return
        if not A.get("retarget", None, False):
            die(f"run {name!r} recorded {what} = {before!r}; this invocation asks for {after!r}.",
                repr(before) + " (run.json)", repr(after) + " (this invocation)",
                "a re-run reuses the recorded estate — pick a new --name for another "
                "one, `down --wipe` this run, or pass --retarget to move it (its "
                "record and config are rewritten; nothing it created is removed)")
        changed.append(f"{what}: {before!r} -> {after!r}")

    retarget("the owner", prev.get("corpus", {}).get("owner"), owner)
    retarget("the docker network", prev.get("network", {}).get("name"), network)

    # ---- where Polar's leg runs (CP-62, wishlist 51 (a)/(h)) — decided
    # before anything is pulled, because a container leg needs one answer
    # only the consumer has: on this host the config binds loopback and the
    # three ports are scanned free here; in containers of the consumer's own
    # the conventional ports are written unscanned, the rollout API and the
    # receiver bind 0.0.0.0, and the gateway's public address is answered,
    # not probed (the probe measures THIS host's interfaces)
    prev_leg = (prev.get("polar_leg") or "host") if prev else None   # a pre-CP-62 record is a host leg
    leg = str(A.get("polar_leg", "Polar's leg: on this host, or in containers",
                    prev_leg or "host", choices=("host", "container")))
    leg_moved = prev_leg is not None and prev_leg != leg
    if leg_moved:
        changed.append(f"polar_leg: {prev_leg!r} -> {leg!r} (the binds and the ports' meaning)")
    explicit_ghost = A.get("gateway_host", None, None)
    if leg == "container":
        explicit_ghost = explicit_ghost or (prev.get("gateway_host") if not leg_moved else None)
        if not explicit_ghost:
            die("--polar-leg container needs --gateway-host.", "no --gateway-host answer",
                "the ONE address your rollout-API container and every sandbox dial the "
                "gateway on (a compose DNS name such as polar-gateway, or an address you "
                "publish) — CP-03's one-URL rule",
                "pass --gateway-host <name-or-address>; the host-address probe this "
                "script runs for a host leg measures this host, which is not where your "
                "gateway runs")

    # ---- Forgejo
    def _choice(section: str) -> str:   # the record says created/adopted
        return "adopt" if prev.get(section, {}).get("mode") == "adopted" else "create"

    fmode = A.get("forgejo", "Forgejo: create a new instance, or adopt one "
                             "(recorded: a re-run keeps it; --retarget moves it)",
                  _choice("forgejo"), choices=("create", "adopt"))
    if fmode == "adopt" and prev.get("forgejo", {}).get("mode") == "created":
        retarget("Forgejo", "created", "adopted")
    if fmode == "adopt":
        furl = bare_url(A.get("forgejo_url", "Forgejo URL (as this host reaches "
                              "it; recorded: a re-run pointing elsewhere is "
                              "refused without --retarget)",
                              prev.get("forgejo", {}).get("url"), required=True), "--forgejo-url")
        retarget("the Forgejo URL", prev.get("forgejo", {}).get("url"), furl)
        fsandbox = bare_url(A.get("forgejo_sandbox_url",
                                  "Forgejo URL as a sandbox/container reaches it",
                                  prev.get("forgejo", {}).get("container_url")
                                  or localhost_to_container(furl)), "--forgejo-sandbox-url")
        admin_user = A.get("forgejo_admin_user", "Forgejo admin username",
                           prev.get("forgejo", {}).get("admin_user", ADMIN_USER))
        admin_pw = A.secret("Forgejo admin password", env=ADMIN_PASSWORD_ENV,
                            file_key="forgejo_admin_password_file",
                            fallback=run_.env.get(ADMIN_PASSWORD_ENV))
        if not admin_pw:
            die("adopting a Forgejo needs its admin PASSWORD.", None,
                f"${ADMIN_PASSWORD_ENV}, --forgejo-admin-password-file, or a prompt",
                "export it or point at a file; a token is not enough (Forgejo "
                "mints tokens for another user only under basic auth)")
        run_.env[ADMIN_PASSWORD_ENV] = admin_pw
        PH.start("forgejo", f"adopting {furl}")
        fj = Forgejo(furl, fsandbox, (admin_user, admin_pw), "adopted")
        fj.probe()
        PH.done(f"reachable; admin {admin_user!r} valid; sign-in "
                f"{'ON (anonymous read refused)' if fj.signin else 'OFF (anonymous read served)'}")
        if not fj.signin:
            warn("forgejo", "this instance serves anonymous git read — a sandbox "
                 "agent that guesses a clone URL can read past its cutoff (gap row "
                 "2); on an estate meant for training set REQUIRE_SIGNIN_VIEW "
                 "there (every reader here presents the read token either way)")
        if "host.docker.internal" in fsandbox and platform.system() == "Linux":
            warn("forgejo", f"the sandbox URL {fsandbox} relies on host.docker.internal, "
                 "which Polar's runtime does not map on Linux — pass "
                 "--forgejo-sandbox-url with an address the sandbox can reach "
                 "(the compose network's gateway IP if the service binds beyond "
                 "loopback), or --network <its network> and its container name")
        if rec.get("compose", {}).get("forgejo"):
            del rec["compose"]["forgejo"]
    else:
        check_docker()
        pf = prev.get("compose", {}).get("forgejo")
        if prev.get("forgejo", {}).get("mode") == "adopted":
            retarget("Forgejo", "adopted " + str(prev["forgejo"].get("url")), "created")
        anon = A.get("anonymous_read", None, None)
        signin = pf["signin"] if (anon is None and pf) else not bool(anon)
        if pf and signin != pf["signin"]:
            retarget("REQUIRE_SIGNIN_VIEW", pf["signin"], signin)
        fport = (pick_port(pf["port"], 3000, "--forgejo-port", check=False) if pf
                 else pick_port(A.get("forgejo_port", "Forgejo host port", "auto"),
                                3000, "--forgejo-port"))
        # the image: an answer since CP-62 — the run's record on a re-run,
        # else the pin; a changed answer recreates the container (compose
        # sees the service definition change; Forgejo migrates its data
        # forward on start and refuses a downgrade itself)
        fimage = str(A.get("forgejo_image", "Forgejo image (a pullable reference)",
                           pf["image"] if pf else FORGEJO_IMAGE))
        if pf and fimage != pf["image"]:
            changed.append(f"the Forgejo image: {pf['image']!r} -> {fimage!r} (the container "
                           "recreated on the new image)")
        elif pf:
            reused.append(f"forgejo container gsj-{name}-forgejo (compose up -d is idempotent)")
        fj = create_forgejo(rundir, run_, fport, signin, network, external_net, fimage)
    rec["forgejo"] = {"mode": fj.mode, "url": fj.url, "container_url": fj.container_url,
                      "admin_user": fj.admin[0], "admin_credential_env": ADMIN_PASSWORD_ENV,
                      "require_signin_view": fj.signin}
    # the record lands NOW, not only at the end: a later phase that dies must
    # not leave the next `up` defaulting to an image this run already moved
    # away from (Forgejo migrates forward and refuses a downgrade)
    run_.write_record()

    # ---- the owner and its two tokens
    PH.start("owner", f"{owner!r} on {fj.url}")
    omode = A.get("owner_mode", "owner: create it, or use one that exists",
                  "auto", choices=("auto", "create", "existing"))
    exists = fj.owner_exists(owner)
    if exists and omode == "create":
        die(f"owner {owner!r} already exists on {fj.url}.", "the account exists",
            "--owner-mode create wants a fresh account",
            "use --owner-mode existing (its repos are checked against this "
            "corpus before anything is pushed), or another --owner")
    if not exists and omode == "existing":
        die(f"owner {owner!r} does not exist on {fj.url}.", "no such user",
            "--owner-mode existing", "create it (--owner-mode auto|create) or "
            "name the account that holds the corpus")
    if not exists:
        pw = credential(secrets.token_urlsafe(18), "Forgejo owner password")
        fj.create_owner(owner, pw)
        run_.env[f"GSJ_FORGEJO_OWNER_PASSWORD_{owner.upper().replace('-', '_')}"] = pw
        say("owner", f"created {owner!r} (its password is in .env)")
        owner_mode = "created"
    else:
        # the record keeps what THIS run created: an owner created by the
        # first run is still "created" on every re-run that finds it
        owner_mode = ("created" if prev.get("forgejo", {}).get("owner_mode") == "created"
                      and prev.get("forgejo", {}).get("owner") == owner else "existing")
        # the collision check: repos of this owner named like our case ids
        held = fj.owner_repos(owner)
        colliding = sorted(set(held) & set(case_ids))
        if colliding:
            say("owner", f"{owner!r} exists and already holds {len(colliding)} "
                         f"repo(s) named like this corpus's cases: {colliding} — "
                         f"comparing their branches with what this corpus builds")
            built = built_heads(corpus)
            drift = {}
            for cid in colliding:
                live = fj.branches(owner, cid)
                if live != built[cid]:
                    drift[cid] = {"live": live, "built": built[cid]}
            if drift and not A.get("overwrite_repos", None, False):
                lines = []
                for cid, d in drift.items():
                    diff = sorted(set(d["live"]) ^ set(d["built"])
                                  | {b for b in d["live"] if d["built"].get(b) != d["live"][b]})
                    lines.append(f"{owner}/{cid}: branches differing {diff} "
                                 f"(live {d['live']}, this corpus builds {d['built']})")
                die(f"owner {owner!r} on {fj.url} holds {len(drift)} repo(s) whose "
                    f"content is NOT what this corpus builds.",
                    "\n            ".join(lines),
                    "either no repos named like these cases, or repos whose every "
                    "branch already equals this corpus's deterministic build",
                    "pick another --owner, delete those repos there, or pass "
                    "--overwrite-repos to push over them (a --force --prune push: "
                    "their current branches are lost)")
            if drift:
                warn("owner", f"--overwrite-repos: {sorted(drift)} will be pushed over")
            else:
                say("owner", f"every colliding repo already holds exactly this corpus's "
                             f"build ({len(colliding)}/{len(colliding)}) — adopting them")
                reused.append(f"{len(colliding)} case repo(s) under {owner!r} (converged)")
        elif held:
            say("owner", f"{owner!r} exists; its {len(held)} repo(s) do not collide "
                         f"with this corpus's case ids")
        else:
            say("owner", f"{owner!r} exists with no repositories")
    for label, env_name, scopes in (("push", push_env, ["write:repository", "write:user"]),
                                     ("read", read_env, ["read:repository", "read:user"])):
        tok = run_.env.get(env_name)
        if tok and fj.token_valid(tok, owner):
            reused.append(f"{label} token ({env_name}, still valid)")
        else:
            if tok:
                backfilled.append(f"{label} token ({env_name}: the stored one no longer authenticates)")
            run_.env[env_name] = fj.mint_token(owner, label, scopes)
            if not fj.token_valid(run_.env[env_name], owner):
                die(f"the freshly minted {label} token does not authenticate as {owner!r}.",
                    None, None, f"docker logs the Forgejo instance; token names are unique per user")
            say("owner", f"{label} token minted ({', '.join(scopes)}) -> .env {env_name}")
    run_.write_env()
    rec["forgejo"].update({"owner": owner, "owner_mode": owner_mode,
                           "push_token_env": push_env, "read_token_env": read_env})
    PH.done(f"{owner!r} {owner_mode}; tokens in .env as {push_env}, {read_env}")

    # ---- the pipeline: its credentials ride the ENVIRONMENT of the child
    # process, taken from the run's .env at call time (never an argv)
    if not corpus.base_url:
        say("corpus", f"corpus.yaml names no git host (the CP-71 shape) — the "
                      f"pipeline runs against {fj.url} and the lock records "
                      f"that URL as canonical")
    elif corpus.base_url != fj.container_url:
        say("corpus", f"corpus.yaml names forgejo.base_url {corpus.base_url} — the lock "
                      f"keeps that canonical URL; this estate is reached at {fj.url} "
                      f"(transport override) and by sandboxes at {fj.container_url}")

    def pipeline(phase: str, *extra: str, mcp_url: str | None = None) -> None:
        # --sandbox-image on every phase: the rows and verify's re-derived
        # expectation must resolve the same estate value (CP-71)
        cmd = [sys.executable, str(INGEST), phase, "--corpus", str(corpus_path),
               "--base-url", fj.url, "--sandbox-image", simage,
               "--ingest-timeout", str(args.ingest_timeout)]
        if mcp_url:
            cmd += ["--mcp-url", mcp_url]
        if owner != yaml_owner:
            cmd += ["--owner-override", owner]
        cmd += list(extra)
        PH.start(phase, f"{INGEST.name} {phase}")
        # the estate tool IS the new command (CP-72): the pipeline's own
        # deprecated-entry notice must not fire on its driver's calls
        penv = {**os.environ, "GSJ_PIPELINE_DRIVER": "estate",
                **{k: v for k, v in run_.env.items()
                   if k in (push_env, read_env, MCP_SECRET_ENV)}}
        proc = run_phase(cmd, penv, phase)
        if proc.returncode != 0:
            die(f"the corpus pipeline's `{phase}` phase failed (exit {proc.returncode}).",
                "the pipeline's own message above (it names the file, rule or variable)",
                "exit 0", "fix what it names and re-run — every phase is idempotent")

    # scaffold: deterministic repos pushed under the owner; the read-back
    # presents the read token (CP-59), so this runs on a closed estate
    pipeline("scaffold")
    lock = ic.load_lock(corpus_path, required=True)
    PH.done(f"{len(case_ids)} case repo(s) converged under {owner!r}; lock written")

    # ---- the retrieval service
    if prev.get("mcp", {}).get("mode") in ("created", "adopted") and \
            prev["mcp"]["mode"] != ("created" if mmode == "create" else "adopted"):
        retarget("the retrieval service", prev["mcp"]["mode"],
                 "created" if mmode == "create" else "adopted")
    secret = None
    if mmode == "adopt":
        murl = bare_url(A.get("mcp_url", "MCP URL (as this host reaches it; "
                              "recorded: a re-run pointing elsewhere is "
                              "refused without --retarget)",
                              prev.get("mcp", {}).get("url"), required=True), "--mcp-url")
        retarget("the MCP URL", prev.get("mcp", {}).get("url"), murl)
        msandbox = bare_url(A.get("mcp_sandbox_url", "MCP URL as a sandbox reaches it",
                                  prev.get("mcp", {}).get("container_url")
                                  or localhost_to_container(murl)), "--mcp-sandbox-url")
        secret = A.secret("MCP token secret", env=MCP_SECRET_ENV, file_key="mcp_secret_file",
                          fallback=run_.env.get(MCP_SECRET_ENV))
        if secret and run_.env.get(MCP_SECRET_ENV) and secret != run_.env[MCP_SECRET_ENV]:
            warn("mcp", f"${MCP_SECRET_ENV} in this shell differs from the run's .env — the "
                        "shell's value is used and proven below before it replaces the stored one")
        if not secret:
            die("adopting a retrieval service needs its token secret.", None,
                f"${MCP_SECRET_ENV}, --mcp-secret-file, or a prompt",
                "the service's operator has it (its config names the variable)")
        PH.start("mcp", f"adopting {murl}")
        mcp = Mcp(murl, msandbox, secret, "adopted")
        h = mcp.health()
        if h is None:
            die(f"the retrieval service at {murl} is not reachable.",
                f"GET /health failed", "a JSON /health", "check the URL and that the service is up")
        served = h.get("embedding") or {}
        if served.get("model") != model or served.get("revision") != revision:
            die("the adopted retrieval service serves a different embedding identity.",
                f"/health.embedding = {served.get('model')!r} @ {served.get('revision')!r} "
                f"({served.get('dimension')} dims)",
                f"{model!r} @ {revision!r} (what this run asked for)",
                "an adopted service's config is its operator's: either ask for the "
                "identity it serves (--embedding-model/--embedding-revision as above) "
                "or re-pin the service there — index.rebuild: always for one start, "
                "then back to if-stale (CP-57's explicit re-embed) — and re-run")
        if h.get("state") == "error":
            die("the adopted retrieval service is in state=error.", h.get("error"),
                "state=ready (or indexing)", "the service's message is authoritative; "
                "fix it there and re-run")
        if h.get("state") == "ready":
            missing = sorted(set(case_ids) - set((h.get("cases") or {}).keys()))
            if missing:
                die("the adopted retrieval service does not index every case of this corpus.",
                    f"/health.cases = {sorted((h.get('cases') or {}).keys())}",
                    f"all of {case_ids}",
                    "its config.yaml's source.repos is its operator's — add the "
                    f"missing cases {missing} there (owner {owner!r} on this Forgejo) "
                    "and restart it, or create a service (--mcp create)")
        # the secret, proven: /admin/reindex is the one secret-guarded path
        # (a match is cheap — fingerprint reuse — and the pipeline's ingest
        # phase triggers it anyway)
        status, body = mcp.reindex()
        if status in (401, 403):
            die("the adopted retrieval service rejected the token secret.",
                f"POST /admin/reindex -> {status} {str(body)[:120]}", "202 (reindex started)",
                f"the value of ${MCP_SECRET_ENV} (or --mcp-secret-file) must equal the "
                "secret the service's own config.yaml token_secret_env names — "
                "ask its operator")
        if status not in (200, 202):
            die("the adopted retrieval service did not accept a reindex.",
                f"POST /admin/reindex -> {status} {str(body)[:120]}", "202",
                "the service's own message is authoritative")
        PH.done(f"reachable, state={h.get('state')}, embedding {served.get('model')} @ "
                f"{str(served.get('revision'))[:12]}… ({served.get('dimension')} dims); "
                f"secret accepted (reindex {body.get('reindex') if isinstance(body, dict) else status})")
        if rec.get("compose", {}).get("mcp"):
            del rec["compose"]["mcp"]
        run_.env[MCP_SECRET_ENV] = secret
    else:
        check_docker()
        pm = prev.get("compose", {}).get("mcp")
        arch = daemon_arch()
        native = f"{MCP_IMAGE}-{arch}"     # a local native build of the checkout's tag
        image_default = pm["image"] if pm else (
            native if CHECKOUT and arch in ("arm64", "aarch64") and image_present(native)
            else MCP_IMAGE)
        image = str(A.get("mcp_image", "retrieval service image", image_default))
        if not pm and image == native and image != MCP_IMAGE:
            # said AFTER the answer is read (wishlist 51 (d)): the line is
            # true only when the native build is what runs
            say("mcp", f"this daemon is {arch}: the native image {image} runs (the "
                       "amd64 local build dies under qemu — wishlist 49)")
        if pm and image != pm["image"]:
            changed.append(f"the retrieval service image: {pm['image']!r} -> {image!r}")
        if not image_present(image):
            # wishlist 51 (b): a registry reference is pulled once; a bare
            # build tag has nowhere to come from but this daemon
            pull = image_pull(image, "mcp") if image_has_registry(image) else None
            if pull is None or pull.returncode != 0:
                native_arch = 'arm64' if arch in ('arm64', 'aarch64') else 'amd64'
                kind = pull_failure_kind(pull.stderr) if pull is not None else "download"
                if pull is not None:        # a registry reference that did not come
                    fix = pull_failure_fix(
                        kind, image,
                        f"the registry refused or is unreachable from this host: on a "
                        f"host that cannot reach registries, load {image} out-of-band "
                        f"(docker save | docker load); otherwise --mcp-image names another "
                        f"reference"
                        + ("" if image == MCP_IMAGE_PUBLISHED else
                           f" (the published two-platform index is {MCP_IMAGE_PUBLISHED})"))
                else:                       # a bare build tag
                    fix = (f"--mcp-image {MCP_IMAGE_PUBLISHED} (the published two-platform "
                           "index, pulled when absent)"
                           + (f", or build it from estate/mcp-service/ (`docker build "
                              f"--platform linux/{native_arch} -t {image} estate/mcp-service`), "
                              "or `docker load` the tarball the estate ships" if CHECKOUT
                              else ", or `docker load` an image so tagged"))
                die(f"the retrieval service image {image} is not present on this daemon"
                    + (" and could not be pulled — downloaded, then not extractable."
                       if kind == "extract" else " and could not be pulled."
                       if pull is not None else " (a local build tag — nothing to pull)."),
                    (pull.stderr.strip().splitlines() or ["no error text"])[-1]
                    if pull is not None else "docker image inspect failed",
                    "a daemon whose storage can extract and mount OCI layers"
                    if kind == "extract" else "the image present, or pullable", fix
                    + (" (this daemon is arm64: an amd64 image dies under qemu at the "
                       "embed step — wishlist 49)" if arch in ("arm64", "aarch64") else ""))
        secret = run_.env.get(MCP_SECRET_ENV)
        if secret:
            reused.append(f"MCP token secret ({MCP_SECRET_ENV})")
        else:
            secret = credential(secrets.token_hex(32), MCP_SECRET_ENV)
            run_.env[MCP_SECRET_ENV] = secret
            say("mcp", f"token secret generated -> .env {MCP_SECRET_ENV}")
        run_.write_env()
        rebuild = bool(A.get("rebuild", None, False))
        stored = store_identity(rundir)
        if stored is not None:
            ident = stored.get("embedding") or {"model": DEFAULT_EMBEDDING_MODEL,
                                                "revision": DEFAULT_EMBEDDING_REVISION,
                                                "note": "pre-CP-57 store, assumed"}
            if (ident.get("model"), ident.get("revision")) == (model, revision):
                say("mcp", f"the store under {rundir / 'mcp-data'} was built by "
                           f"{ident.get('model')} @ {str(ident.get('revision'))[:12]}… "
                           f"— the requested identity; reusing it"
                           + (" (--rebuild: re-embedding anyway)" if rebuild else ""))
                if not rebuild:
                    reused.append(f"the index store (identity {ident.get('model')})")
            elif not rebuild:
                die("the run's index store was built by a different embedding model.",
                    f"{rundir / 'mcp-data/index/fingerprint.json'}: "
                    f"{ident.get('model')!r} @ {ident.get('revision')!r}"
                    f" ({ident.get('dimension')} dims)",
                    f"{model!r} @ {revision!r} (what this run asked for)",
                    "this is a model re-pin, not staleness (CP-57): re-run with "
                    "--rebuild to re-embed the corpus under the requested model "
                    "(the old store is destroyed), or ask for the identity that "
                    "built it")
            else:
                warn("mcp", f"--rebuild: the store built by {ident.get('model')} is "
                            f"re-embedded under {model}")
                backfilled.append(f"the index store, re-embedded under {model}")
        elif rebuild:
            say("mcp", "--rebuild given, no store yet: a fresh build either way")
        hf_dir = None
        if (model, revision) != (DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_REVISION):
            hf_dir = hf_model_dir(model, revision, A.get("hf_cache", None, None))
            if hf_dir is None:
                die(f"{model} @ {revision} is not in this host's HuggingFace cache.",
                    "no hub/models--…/snapshots/<revision> directory",
                    "the model snapshot on disk (the image bakes only "
                    f"{DEFAULT_EMBEDDING_MODEL} and runs offline)",
                    f"huggingface-cli download {model} --revision {revision}   "
                    "(or --hf-cache <dir> naming a cache that holds it)")
            say("mcp", f"{model} is not the image's baked model — mounting the host's "
                       f"snapshot {hf_dir} into the container (offline load)")
        # CP-79/CP-88: the decisions drop — the corpus's own decisions/ by
        # default (corpus-contract v3: validated with the tree), a host
        # directory of rii-dok v1 files under --decisions-dir as the
        # override; both is a refusal. Mounted read-only into the service;
        # the config names the mount. Recorded, so a re-run keeps it; a new
        # value replaces it (the decisions collection alone re-embeds, its
        # own fingerprint)
        try:
            ddir, dsource = resolve_decisions_source(corpus_drop, ddir_answer)
        except DecisionsSourceConflict as exc:
            die(*exc.parts)
        require_decisions_image(image, ddir, dsource)
        if ddir and dsource == "flag":
            if not os.path.isdir(ddir):
                die(f"--decisions-dir {ddir} is not a directory.", None,
                    "a directory of jb-<doknr>.xml files (docs/decisions-surface.md §2)",
                    "point --decisions-dir at the drop, or omit it for the synthetic 30")
            n_xml = len([f for f in os.listdir(ddir) if f.endswith(".xml")])
            if n_xml == 0:
                die(f"--decisions-dir {ddir} holds no .xml file.", None,
                    "at least one jb-<doknr>.xml (the service refuses a drop "
                    "with no conforming decision at its start)",
                    "point --decisions-dir at the drop, or omit it for the synthetic 30")
        ddir_changed = bool(pm) and (pm.get("decisions_dir") or None) != ddir
        if ddir_changed:
            changed.append(f"the decisions drop: {pm.get('decisions_dir')!r} -> {ddir!r}")
        mport = (pick_port(pm["port"], 8790, "--mcp-port", check=False) if pm
                 else pick_port(A.get("mcp_port", "MCP host port", "auto"),
                                8790, "--mcp-port"))
        container = f"gsj-{name}-mcp"
        (rundir / "mcp-data").mkdir(exist_ok=True)
        cfg = rundir / "mcp-config.yaml"
        cfg_before = sha256_file(cfg) if cfg.is_file() else None
        if cfg.is_file() and "rebuild: always" in cfg.read_text() and not rebuild:
            # a --rebuild that died between the start and the revert: the
            # service reads the file only at start, so finish that rebuild
            # rather than force another
            warn("mcp", "mcp-config.yaml still says index.rebuild: always (an interrupted "
                        "--rebuild) — waiting for that rebuild, then reverting")
            rebuild = True
        chunk_prev = (pm or {}).get("chunking") or {}
        if chunk_prev and (chunk_max, chunk_overlap) != (chunk_prev["max_tokens"], chunk_prev["overlap"]):
            changed.append(f"chunking: {chunk_prev} -> {{'max_tokens': {chunk_max}, 'overlap': {chunk_overlap}}}")
        cfg_text = render_mcp_template(
            prog=PROG, run=name, forgejo_url=fj.container_url, owner=owner,
            repos=", ".join(case_ids), read_env=read_env, model=model,
            revision=revision, chunk_max=chunk_max, chunk_overlap=chunk_overlap,
            rebuild="always" if rebuild else "if-stale", secret_env=MCP_SECRET_ENV)
        if ddir:
            # the drop's line joins the template's decisions block after the
            # format (the template's placeholder set is pinned by the frozen
            # corpus suite — CP-79's first CI run)
            anchor = "  corpus_size: 30\n"
            assert cfg_text.count(anchor) == 1, "MCP_CONFIG's decisions block moved"
            cfg_text = cfg_text.replace(
                anchor, anchor + f"  path: {MCP_DECISIONS_MOUNT}   # "
                                 + (f"the corpus's decisions/ {ddir} (corpus-contract v3, CP-88)"
                                    if dsource == "corpus" else f"--decisions-dir {ddir} (CP-79)")
                                 + ", mounted read-only\n", 1)
        cfg_text = render_mcp_config(cfg_text, residual)
        # the review (CP-70 item 7): shown before anything is embedded under
        # it — every run, so a -y run still sees what it is spending; the
        # CONFIRM fires only when an embed is actually about to be spent —
        # cold store, --rebuild, or ANY fingerprint component moving vs the
        # run's existing config (the chunk window, normalize, the decisions
        # params — the review's own pricing, read off the same key set) —
        # and never in a non-interactive run
        old_components = None
        if cfg_before is not None:
            try:
                old_components = mcp_fingerprint_components(yaml.safe_load(cfg.read_text()))
            except yaml.YAMLError:
                old_components = None      # unreadable old config: treat as moved
        new_components = mcp_fingerprint_components(yaml.safe_load(cfg_text))
        # a swapped drop renders to the same mount path, so the components
        # cannot see it — the record can (CP-79 review)
        embed_spend = (stored is None or rebuild or ddir_changed
                       or (cfg_before is not None and old_components != new_components))
        say("mcp-config", mcp_config_review(yaml.safe_load(cfg_text), cfg, ddir, dsource)
            + ("" if embed_spend else
               "\n      (this config matches the store's — an embed happens now "
               "only if the corpus itself moved)"))
        if A.interactive and embed_spend:
            try:
                typed = input(f"{_c('36', '?')} build the index under this config? "
                              f"(yes / no — no aborts) [yes]: ").strip().lower()
            except EOFError:
                # a spending confirm is not a value prompt: a closed stdin is
                # a decline, never consent (-y is the non-interactive form)
                typed = "no (stdin closed)"
            if typed not in ("", "y", "yes"):
                die("the retrieval config was declined at the review.",
                    "the operator answered no", "yes (or an edited config)",
                    "adjust --embedding-model/--embedding-revision, "
                    "--chunk-max-tokens/--chunk-overlap, or supply "
                    "--mcp-config <yaml> (sections: "
                    f"{', '.join(MCP_OPERATOR_SECTIONS)}) and re-run — "
                    "nothing was embedded")
        cfg.write_text(cfg_text)
        rec.setdefault("compose", {})["mcp"] = {
            "image": image, "container": container, "port": mport,
            "data": str(rundir / "mcp-data"), "config": str(cfg), "read_env": read_env,
            "hf_model_dir": str(hf_dir) if hf_dir else None,
            "hf_model_mount": f"/opt/hf-cache/hub/{hf_dir.name}" if hf_dir else None,
            "decisions_dir": ddir,
            "decisions_source": dsource,          # CP-88: corpus | flag | none
            "chunking": {"max_tokens": chunk_max, "overlap": chunk_overlap},
            "config_overrides": residual,
            "uid": os.getuid() if platform.system() == "Linux" else None,
            "gid": os.getgid() if platform.system() == "Linux" else None}
        write_compose(rundir, run_, network, external_net)
        # the record lands BEFORE the embed (the forgejo pattern): an
        # interrupted build must not leave the next re-run defaulting to a
        # config this run already moved away from (image, chunking, the
        # --mcp-config residuals)
        run_.write_record()
        PH.start("mcp", f"docker compose up ({container}, 127.0.0.1:{mport}) — a cold "
                        f"start clones and embeds; a warm one matches the fingerprint")
        # compose recreates on a changed service definition (image, env,
        # ports) by itself; a changed MOUNTED config or --rebuild is read only
        # at start, so those force the recreate — an untouched run is a no-op
        recreate = rebuild or (cfg_before is not None and cfg_before != sha256_file(cfg))
        if recreate and rebuild_in_progress(f"http://127.0.0.1:{mport}", container):
            # CP-96 (round four): a --rebuild whose previous attempt timed out
            # at the wait used to recreate the container and embed from zero
            # on every re-run; the service is still building — attach to it
            warn("mcp", f"{container} is still building under index.rebuild: always — "
                        "attaching to that build instead of recreating the container "
                        "(a recreate would embed from zero again)")
            recreate = False
        up = compose_up(rundir, "-d", *(["--force-recreate"] if recreate else []), "mcp")
        if up.returncode != 0:
            kind = pull_failure_kind(up.stderr)
            die("`docker compose up mcp` failed"
                + (" — the daemon could not extract or mount the image." if kind == "extract"
                   else "."),
                (up.stderr.strip().splitlines() or ["the compose error above"])[-1],
                "a daemon whose storage can extract and mount OCI layers" if kind == "extract"
                else None,
                pull_failure_fix(kind, image,
                                 "the error is authoritative; the container keeps its "
                                 "creation-time env, so a rotated token needs this recreate "
                                 "(done here)"))
        mcp = Mcp(f"http://127.0.0.1:{mport}", f"http://{container}:8790", secret, "created")
        h = None
        try:
            h = mcp.wait_ready(args.ingest_timeout, "cold start" if stored is None else "start",
                               container=container)
        finally:
            # revert only once the rebuild finished: an interrupted one keeps
            # `always` and the next `up` waits for it (see the entry check)
            if rebuild and h is not None:
                cfg.write_text(cfg.read_text().replace("rebuild: always", "rebuild: if-stale"))
                say("mcp", "re-embedded; mcp-config.yaml set back to index.rebuild: if-stale "
                           "so the next start reuses this store")
        dd = h.get("decisions_drop")
        PH.done(f"ready at {mcp.url} (containers: {mcp.container_url}); fingerprint "
                f"{str(h.get('fingerprint'))[:12]}…; index_reused={h.get('index_reused')}"
                + (f"; rebuilt {h['rebuilt']}" if h.get("rebuilt") else "")
                + (f"; decisions: {dd['files']} files, {dd['units']} units, "
                   f"{dd['pieces']} pieces (drop {dd['sha256'][:12]}…)" if dd
                   else f"; decisions: the synthetic {h.get('decisions')}"))
        if stored is not None and h.get("index_reused"):
            pass
        elif stored is not None and not rebuild:
            backfilled.append("the index (fingerprint changed — rebuilt by the service)")
    run_.write_env()

    if not rec.get("compose"):
        # nothing composed: the sandbox network the config names must still
        # exist — create the run's own, verify an external one (the review's
        # finding on run 4: an adopted-only run named a network nothing made)
        if shutil.which("docker"):
            probe_net = run(["docker", "network", "inspect", network], capture_output=True)
            if probe_net.returncode != 0 and external_net:
                die(f"--network {network!r} does not exist on this daemon.",
                    "docker network inspect failed", "an existing network the sandbox can join",
                    "create it, or omit --network to let the run create its own")
            if probe_net.returncode != 0:
                made = run(["docker", "network", "create", network], capture_output=True)
                if made.returncode != 0:
                    die(f"could not create the docker network {network!r}.", made.stderr.strip(),
                        None, "the docker error is authoritative")
                rec["network"]["created_by_run"] = True
                say("network", f"{network} created (nothing else of this run lives on it; "
                               "`down` removes it)")
            else:
                say("network", f"{network} exists")
        else:
            warn("network", f"no docker here — {network!r} cannot be verified; the sandbox must "
                            "be able to join it where Polar runs")

    # ingest: the reindex trigger proves the secret; a matching fingerprint reuses
    pipeline("ingest", mcp_url=mcp.url)
    h = mcp.health() or {}
    PH.done(f"state={h.get('state')}, fingerprint {str(h.get('fingerprint'))[:12]}…, "
            f"index_reused={h.get('index_reused')}")
    if h.get("index_reused") and run_.existing:
        reused.append(f"the index (fingerprint {str(h.get('fingerprint'))[:12]}…)")
    rec["mcp"] = {"mode": mcp.mode, "url": mcp.url, "container_url": mcp.container_url,
                  "secret_env": MCP_SECRET_ENV, "state": h.get("state"),
                  "fingerprint": h.get("fingerprint"), "index_reused": h.get("index_reused"),
                  "embedding": h.get("embedding"), "backend": h.get("backend"),
                  "cases": h.get("cases")}
    if mcp.mode == "created":
        rec["mcp"]["image"] = rec["compose"]["mcp"]["image"]
        rec["mcp"]["store"] = str(rundir / "mcp-data" / "index" / "fingerprint.json")

    # taskbank + verify
    bank = corpus_path / ic.TASKBANK_NAME
    run_bank = rundir / ic.TASKBANK_NAME              # this run's own copy
    bank_before = sha256_file(run_bank) if run_bank.is_file() else None
    tree_before = sha256_file(bank) if bank.is_file() else None
    pipeline("taskbank")
    bank_sha = sha256_file(bank)
    if bank_before == bank_sha:
        PH.done("unchanged (byte-identical to this run's previous bank)")
        reused.append("taskbank.parquet (byte-identical)")
    elif tree_before == bank_sha:
        PH.done(f"written, sha256 {bank_sha[:12]}… (matches the bank the corpus tree already held)")
    else:
        PH.done(f"written, sha256 {bank_sha[:12]}…")
    pipeline("verify", mcp_url=mcp.url)
    PH.done("PASS — the live repos, the index census and the bank rows match the tree")
    for src in (ic.TASKBANK_NAME, ic.LOCK_NAME):
        shutil.copyfile(corpus_path / src, rundir / src)
    # CP-88: the decisions lock rides along when the corpus carries one
    if (corpus_path / ic.DECISIONS_LOCK_NAME).is_file():
        shutil.copyfile(corpus_path / ic.DECISIONS_LOCK_NAME, rundir / ic.DECISIONS_LOCK_NAME)
    else:
        (rundir / ic.DECISIONS_LOCK_NAME).unlink(missing_ok=True)
    lock = ic.load_lock(corpus_path, required=True)
    rec["corpus"].update({"lock_sha256": sha256_file(rundir / ic.LOCK_NAME),
                          "decisions_lock_sha256": (sha256_file(rundir / ic.DECISIONS_LOCK_NAME)
                                                    if (rundir / ic.DECISIONS_LOCK_NAME).is_file()
                                                    else None),
                          "taskbank_sha256": bank_sha,
                          "taskbank_rows": (lock.get("taskbank") or {}).get("rows"),
                          "repos": {cid: lock["cases"][cid]["refs"] for cid in case_ids}})

    # ---- the engine: always the operator's, never created. The answer is
    # NOT binding (CP-70 item 9): it lands in rollout.yaml, the probe below
    # records rather than refuses, and the operator changes it at any time.
    eurl = A.get("engine_url", "inference endpoint (root URL, no /v1) — not "
                               "binding: written to rollout.yaml's "
                               "estate.serving_base_url and only probed (a "
                               "warning, never a refusal); change it later by "
                               "editing that file or re-running up",
                 prev.get("engine", {}).get("url", DEFAULT_ENGINE_URL)).rstrip("/")
    if eurl.endswith("/v1"):
        die("the engine URL must not end in /v1.", eurl, "the root — Polar's proxy "
            "appends /v1/chat/completions itself", f"--engine-url {eurl[:-3]}")
    emodel = A.get("engine_model", "served model name (as GET /v1/models lists "
                                   "it) — not binding: written to "
                                   "rollout.yaml's estate.model; edit it "
                                   "there or re-run up",
                   prev.get("engine", {}).get("model", REFERENCE_MODEL))
    PH.start("engine", f"probing {eurl} for {emodel!r}")
    probe = probe_engine(eurl, emodel)
    probe["probed_at"] = now_iso()
    rec["engine"] = probe
    if not probe["reachable"]:
        warn("engine", f"{eurl} is not reachable ({probe.get('detail')}) — the estate "
             "stands either way, but no episode runs until it is; serve the model "
             f"under exactly {emodel!r} and re-run (or just start episodes later)")
        PH.done("NOT reachable — recorded")
    elif not probe["model_served"]:
        warn("engine", f"{eurl} serves {probe['models']}, not {emodel!r} — Polar's "
             "gateway dispatches to the configured name; --engine-model must match "
             "byte-for-byte")
        PH.done(f"reachable, model NOT served; /tokenize {probe['tokenize']}")
    else:
        PH.done(f"reachable, {emodel!r} served; /tokenize {probe['tokenize']}")
    hp = prev.get("harness", {})
    eot = A.get("end_of_turn_token_id", None, hp.get("end_of_turn_token_id"))
    if emodel != REFERENCE_MODEL and eot is None:
        warn("engine", f"{emodel!r} is not the reference model: builder.end_of_turn_token_id "
             "stays the Qwen3 default (151645) unless --end-of-turn-token-id says "
             "otherwise — derive it from the served tokenizer: the recipe is "
             f"{BRING_YOUR_OWN_URL}#your-model (from an endpoint URL to the values "
             "this tool needs, and what an endpoint alone cannot give)")

    # ---- pins: which skill cards the approved set in force already carries
    g1 = pins_g1_check(corpus)
    rec["pins"] = g1
    if g1.get("checked") and g1["not_in_approved_set"]:
        warn("pins", f"{len(g1['not_in_approved_set'])}/{g1['cards']} skill card(s) are not "
             f"in the approved set the library validates against (G1: {g1['pins_path']}, "
             f"{'the packaged REFERENCE set — set GSJ_PINS_PATH to your own' if g1['pins_source'] == 'packaged' else 'via ' + g1['pins_source']}): "
             f"{g1['not_in_approved_set']} — episodes on them quarantine until the pins "
             f"walk re-derives — {BRING_YOUR_OWN_URL}#your-pins (pins/derive_pins.py "
             "re-verifies the REFERENCE set only and does not ship on the wheel); this "
             "script does not write pins")
    elif g1.get("checked"):
        say("pins", f"every skill card ({g1['cards']}) is in the approved set at "
                    f"{g1['pins_path']} ({g1['pins_source']})")
    if g1.get("checked") and g1.get("empty_sets"):
        warn("pins", f"the approved set in force leaves {', '.join(g1['empty_sets'])} EMPTY — "
             "nothing checks those on this estate (G4's tokenizer/chat-template bytes are "
             "estate-side and were not measured): an accepted episode says nothing about "
             f"them — {BRING_YOUR_OWN_URL}#what-an-acceptance-covers")

    # ---- rollout.yaml — the config the rollout server needs
    PH.start("config", "rollout.yaml")
    pp = prev.get("ports", {})

    def leg_port(key: str, default: int, flag: str) -> int:
        want = A.get(f"{key}_port", None, pp.get(key, "auto"))
        if leg == "container":
            return int(default if want in (None, "auto") else want)
        # a recorded host port is kept unchecked (this run's own process may
        # hold it) — unless the leg just moved to this host, where nothing did
        return pick_port(want, default, flag, check=key not in pp or leg_moved)

    rport = leg_port("rollout", 8080, "--rollout-port")
    gport = leg_port("gateway", 8200, "--gateway-port")
    xport = leg_port("receiver", 8300, "--receiver-port")
    bind = "0.0.0.0" if leg == "container" else "127.0.0.1"
    probe_image = (corpus.sandbox_image if rec.get("sandbox_image_present")
                   else None)
    if leg == "container":
        if eurl_is_loopback(eurl):
            warn("config", f"the engine URL {eurl} is loopback — inside your gateway's "
                 "container that is the container itself; re-address "
                 "estate.serving_base_url to an address the gateway container can dial "
                 "(host.docker.internal on Docker Desktop, the compose network's gateway "
                 "IP on Linux) before it starts — the closing block lists the keys")
    # CP-96: the dial runs inside this run's retrieval container when it has
    # one (nothing to create, nothing to leak); the sandbox image is the
    # fallback only for an adopted service
    probe_exec = (f"gsj-{name}-mcp" if mcp.mode == "created"
                  and container_running(f"gsj-{name}-mcp") else None)
    ghost, ghow, gprobe = gateway_host(network, gport, explicit_ghost,
                                       probe_image, prev.get("gateway_host"),
                                       exec_container=probe_exec)
    if prev.get("gateway_host") and prev["gateway_host"] != ghost:
        changed.append(f"the gateway host: {prev['gateway_host']!r} -> {ghost!r} ({ghow})")
    rec["ports"] = {"rollout": rport, "gateway": gport, "receiver": xport}
    rec["polar_leg"] = leg
    rec["gateway_host"] = ghost
    rec["gateway_host_derived_from"] = ghow
    rec["gateway_host_probe"] = gprobe
    (rundir / "traces").mkdir(exist_ok=True)
    (rundir / "artifacts").mkdir(exist_ok=True)
    cfg = {
        "estate": {
            "clone_url_for": f"{fj.container_url}/{owner}/{{case_id}}.git",
            "clone_credential_env": read_env,
            "mcp_url_base": mcp.container_url,
            "mcp_token_secret_env": MCP_SECRET_ENV,
            "serving_base_url": eurl,
            "provider": "gsj",
            "model": emodel,
        },
        "runtime": {"backend": "docker", "image": corpus.sandbox_image, "network": network},
        "harness": {"artifacts_dir": str(rundir / "artifacts"),
                    "context_window": int(A.get("context_window", None, hp.get("context_window", 32768))),
                    "max_tokens": int(A.get("max_tokens", None, hp.get("max_tokens", 8192))),
                    "thinking": str(A.get("thinking", None, hp.get("thinking", "off")))},
        "polar": {"rollout": {"host": bind, "port": rport},
                  "gateway": {"id": f"gsj-{name}", "host": "0.0.0.0", "port": gport,
                              "public_url": f"http://{ghost}:{gport}", "engine": "vllm"}},
        "receiver": {"host": bind, "port": xport, "traces_dir": str(rundir / "traces")},
    }
    if eot is not None:
        cfg["builder"] = {"end_of_turn_token_id": int(eot)}
    rec["harness"] = {**cfg["harness"], "end_of_turn_token_id": eot}
    for key in ("context_window", "max_tokens", "thinking", "end_of_turn_token_id"):
        if hp and key in hp and hp[key] != rec["harness"].get(key):
            changed.append(f"harness.{key}: {hp[key]!r} -> {rec['harness'].get(key)!r}")
    head = (f"# GENERATED by {PROG} for run {name} — do not edit (run.json dates it);\n"
            f"# re-run `{PROG} up --name {name}`. Schema: gsj_rollout/config.py\n"
            f"# (the one YAML). Secrets are named by variable and live in {rundir / '.env'}:\n"
            f"# `gsj-rollout submit` (since 0.1.7, CP-75) reads it beside this file for an unset\n"
            f"# named variable; the environment wins when already set. Historical wheels through\n"
            f"# 0.1.6 need it sourced before submit, in a subshell. Polar's serve_gateway\n"
            f"# reads its own environment — source it there, in a subshell. `serve` needs no secret.\n"
            f"# Sandbox-side addresses ({fj.container_url}, {mcp.container_url}) resolve on\n"
            f"# the docker network {network!r}; host-side ones ({fj.url}, {mcp.url}) are\n"
            f"# recorded in run.json. Polar's leg: {leg}"
            + (" — the rollout API and the receiver bind 0.0.0.0 on unscanned ports;\n"
               "# re-address polar.rollout.public_url, receiver.public_url, receiver.traces_dir\n"
               "# and harness.artifacts_dir for your containers (only you know their names);\n"
               "# polar.gateway.public_url is your --gateway-host answer; estate.serving_base_url\n"
               "# must be dialable from the gateway's container (a loopback engine URL is not).\n"
               if leg == "container" else " (this host: loopback, ports scanned free).\n"))
    ry = rundir / "rollout.yaml"
    ry.write_text(head + yaml.safe_dump(cfg, sort_keys=False))
    render = run([sys.executable, "-m", "gsj_rollout.cli", "serve", "--config", str(ry),
                  "--render-only"], capture_output=True)
    if render.returncode != 0:
        die("the library rejected the generated rollout.yaml.", render.stderr.strip() or render.stdout,
            "a config load_config accepts", "this is an estate.py bug — report it with the output")
    PH.done(f"written and validated (topology.rendered.yaml beside it); gateway public "
            f"URL http://{ghost}:{gport} ({ghow})")

    # ---- the record
    rec["artifacts"] = {"rollout_yaml": str(ry), "topology": str(rundir / "topology.rendered.yaml"),
                        "taskbank": str(rundir / ic.TASKBANK_NAME), "lock": str(rundir / ic.LOCK_NAME),
                        "env": str(rundir / ".env"), "compose": (str(rundir / "compose.yaml")
                                                                 if rec.get("compose") else None),
                        "mcp_config": str(rundir / "mcp-config.yaml") if mcp.mode == "created" else None}
    rec["phases"] = PH.rows
    rec["last_run"] = {"at": now_iso(), "reused": reused, "backfilled": backfilled,
                       "changed": changed, "mode": "re-run" if run_.existing else "first run"}
    run_.write_env()
    run_.write_record()
    short = sorted(k for k, v in run_.env.items() if len(v) < 8)
    if short:
        warn("record", f"{short} hold values shorter than 8 characters — too short for the "
                       "secret-absence scan to be meaningful; they are skipped")
    for f in sorted(rundir.iterdir()):
        if not f.is_file() or f.name == ".env":
            continue
        blob = f.read_bytes()
        leak = [k for k, v in run_.env.items() if len(v) >= 8 and v.encode() in blob]
        if leak:
            die(f"internal: {f.name} would carry a secret value.", str(leak), "names only",
                "report this bug")
    say("record", f"run.json written — names {len(run_.env)} variable(s), no values; "
                  f".env is {oct(os.stat(rundir / '.env').st_mode & 0o777)}")

    # ---- the final block
    total = round(time.monotonic() - _T0, 1)
    say("up", f"complete in {total}s" + (f" — reused: {len(reused)}; backfilled: {len(backfilled)}"
                                        if run_.existing else ""))
    if run_.existing:
        for r in reused:
            print(f"    reused:     {r}")
        for b in backfilled:
            print(f"    backfilled: {b}")
        for c in changed:
            print(f"    changed:    {c}")
    rel = os.path.relpath(rundir, Path.cwd())
    # The checkout's Polar venv, with the checkout on PYTHONPATH so Polar's
    # import_path finds gsj_rollout; from the wheel both are the consumer's.
    # CP-94: a bare `polar` is on nobody's PATH from a wheel — the two Polar
    # processes need a checkout's vendor/polar venv (or the demo's gsj-polar
    # image), exactly what `gsj-rollout serve` says in its NOTE line
    polar = (f"PYTHONPATH={REPO} {REPO / 'vendor' / 'polar' / '.venv' / 'bin' / 'polar'}" if CHECKOUT
             else "PYTHONPATH=<checkout> <checkout>/vendor/polar/.venv/bin/polar")
    polar_note = ("" if CHECKOUT else
                  "\n  NOTE: no wheel ships vendor/polar — the two `polar` lines need a checkout "
                  "(git clone https://github.com/MHGanainy/gsj-harness-rollout-server; build "
                  "vendor/polar's venv per its README) with the checkout on PYTHONPATH, or the "
                  "published gsj-polar image (gsj-rollout-demo's shape); `gsj-rollout serve` "
                  "runs from this wheel as printed")
    gsjr = Path(sys.executable).parent / "gsj-rollout"
    gsjr_cmd = str(gsjr) if gsjr.exists() else f"{sys.executable} -m gsj_rollout.cli"
    if leg == "container":
        nxt = f"""
next — Polar's leg is yours, in containers (--polar-leg container): rollout.yaml binds the rollout
  API and the receiver on 0.0.0.0:{rport}/{xport} (unscanned) and the gateway on 0.0.0.0:{gport} with
  public_url http://{ghost}:{gport} (your --gateway-host answer, unprobed — the address your rollout-API
  container AND every sandbox dial); before your containers read it, re-address what only you know:
    polar.rollout.public_url     the rollout API as your submit reaches it
    receiver.public_url          the receiver as the rollout API's callback reaches it
    receiver.traces_dir          the traces directory INSIDE the receiver's container
    harness.artifacts_dir        the artifacts directory INSIDE the rollout API's container
    estate.serving_base_url      {eurl}{' — LOOPBACK: inside the gateway container that is itself; use an address it can dial' if eurl_is_loopback(eurl) else ' — as the gateway container dials it'}
  (gsj-rollout-demo's bootstrap.py `containerize_rollout_yaml` is the worked example), then run
  `gsj-rollout serve` and `polar serve_rollout` in their containers with no secret, and
  `polar serve_gateway` with .env's {MCP_SECRET_ENV} in its environment (compose --env-file) — of
  the three, the only one that needs a value.
then one episode (the config's whole claim), from a container on {network!r} — submit reads the
  named read token from the .env beside the rollout.yaml it is given: mount the run's .env beside
  your re-addressed copy (since 0.1.7, CP-75); the environment wins when already set.
  Historical wheels through 0.1.6 read the environment only (docker -e <name>):
  gsj-rollout submit --config <your rollout.yaml> --from-bank <the taskbank> --row 0"""
    else:
        nxt = f"""
next — the receiver and Polar's two processes, on this host (three terminals; only the gateway needs .env —
  pi_harness reads {MCP_SECRET_ENV} from that process's environment, so source it there, in a subshell):
  {gsjr_cmd} serve --config {rel}/rollout.yaml
  {polar} serve_rollout -c {rel}/topology.rendered.yaml
  (set -a; . {rel}/.env; set +a; {polar} serve_gateway -c {rel}/topology.rendered.yaml){polar_note}
then one episode (the config's whole claim) — nothing exported: submit reads {rel}/.env beside rollout.yaml
  for an unset named read token (since 0.1.7, CP-75); the environment wins when already set.
  Historical wheels through 0.1.6 need .env sourced in a subshell before submit:
  {gsjr_cmd} submit --config {rel}/rollout.yaml --from-bank {rel}/taskbank.parquet --row 0"""
    print(f"""
== run {name} == {rel}/
  rollout.yaml       the rollout server's config (validated; topology.rendered.yaml beside it)
  taskbank.parquet   {rec['corpus'].get('taskbank_rows')} rows, sha256 {bank_sha[:12]}…; corpus.lock.json beside it
  run.json           the record — {fj.mode} Forgejo {fj.url}, {mcp.mode} MCP {mcp.url}, owner {owner!r},
                     embedding {(h.get('embedding') or {}).get('model')}, engine {eurl} ({'ok' if probe['model_served'] else 'NOT OK'})
  .env               {len(run_.env)} secret(s), mode 0600 — the only place a value lives
{nxt}
what stands / stop what this run created:
  {PROG} status --name {name}    |    {PROG} down --name {name} [--wipe]""")


# -------------------------------------------------------------- scaffold
# CP-71 (CP-70 item 12): there was no way to start a corpus except by
# reading the contract and guessing. `scaffold` writes an annotated
# starting tree that passes `validate` unmodified; every file says what it
# is and what to change. It reads NOTHING from the installed library — no
# packaged G2 capture, no pins (CP-70 item 3: the synthetic generator
# refuses under an editable install because it hashes the packaged capture;
# an author's AGENTS.md is theirs to write, so this tool has no such
# dependency — the pins consequence is stated in the files instead).

SCAFFOLD_CORPUS_YAML = """\
# corpus.yaml — the corpus's own identity, and nothing else. The git host,
# the retrieval service and the harness image belong to the ESTATE and are
# answered at bring-up (`{prog} up`), not written here. The contract is
# docs/corpus-contract.md (gsj-harness-rollout-server); `validate` checks
# every rule and names the exact file and rule when it is unhappy.

# CHANGE THIS — the corpus's name (letters, digits, . _ -). It becomes
# the default run name when it fits one (a run name is lowercase letters,
# digits, - and _; capitals or dots need --name at `up`), and the run
# name prefixes everything the bring-up creates: the containers
# gsj-<name>-forgejo / gsj-<name>-mcp, the docker network gsj-<name>-net,
# and the run directory runs/<name>/.
name: my-corpus

# CHANGE THIS (or keep it — any usable Forgejo username works; the old
# two-value allowlist is gone). The git-host account that owns one
# repository per case. The credential environment variables are named
# after it — GSJ_FORGEJO_TOKEN_<OWNER> and GSJ_FORGEJO_READ_TOKEN_<OWNER>,
# the owner uppercased with '-' -> '_' (which is why '.' is not allowed
# in it) — and it appears in the clone URL every episode's sandbox
# receives: <base_url>/<owner>/<case_id>.git. `up` creates the account
# and mints its tokens when they do not exist.
owner: my-owner

# DO NOT CHANGE these three. A commit SHA is a function of content plus
# author plus date, so fixing the identity and the date makes the case
# repos byte-reproducible: re-running the pipeline on an unchanged tree
# converges to identical commit SHAs — which is what makes the lock's
# recorded SHAs mean anything. The date records nothing; do not update it
# when you edit the corpus.
git:
  name: gsj-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"

# Three fields older corpora carried here are DEPRECATED — they are the
# estate's, not the corpus's, and this scaffold does not write them:
#   forgejo.base_url   -> answered by `up` (standalone pipeline: --base-url)
#   mcp.url_base       -> answered by `up` (standalone pipeline: --mcp-url)
#   sandbox_image      -> IGNORED if present: a corpus is not bound to a
#                         runtime; the task rows take the estate's value
#                         (`up`'s --sandbox-image answer / rollout.yaml's
#                         runtime.image)
"""

SCAFFOLD_AGENTS_MD = """\
# AGENTS.md — the agent's standing instructions (REPLACE THIS)

This file is copied verbatim into every case repository, on every branch,
and the harness serves it to the agent as its project instructions. It is
yours to write — two things are load-bearing:

- Cite pages as `page:N` (the file `md/page_NNNN.md` in the checkout).
  Retrieval and grading downstream rely on that convention.
- The rollout side pins the system prompt these instructions become (G2)
  and each skill card (G1). This example text is NOT the pinned reference
  text, so episodes on this corpus will quarantine at trace validation
  until the estate's pins are re-derived from YOUR AGENTS.md and cards —
  docs/corpus-contract.md, "Bringing your own corpus", has the steps.

Replace everything below with your own instructions.

- Work only from the case file in this checkout (`md/`) and the retrieval
  tools. Cite a page for every fact, as `page:N`.
- Write your deliverable into the `out/` directory.
"""

SCAFFOLD_SKILL_MD = """\
# Skill: example (REPLACE THIS)

A skill card is a reusable prompt. A timestep's `prompts.yaml` references
it by name (`source: skill, name: example`) instead of repeating text, and
the pipeline resolves the card's bytes into every task row that references
it, at build time. The card's sha256 is what the rollout side verifies
episodes against (G1): edit a card and the estate's pins must be
re-derived before episodes on it pass validation.

Replace this file with a real task. The shape that works:

1. Say what to produce, concretely.
2. Say what to base it on — only the case file in this checkout and the
   retrieval tools.
3. Require citations: every fact cited as (page:N).
4. Name the deliverable file under `out/`.
"""

SCAFFOLD_PAGE = """\
# Page 1 (REPLACE THIS)

A page is the corpus's unit: one Markdown file, ABSOLUTELY numbered —
`page_0001.md` is page 1 of the case in every timestep that contains it
(4-digit, never renumbered per directory). A `timestep-<T>/pages/`
directory holds the complete case as it stands at that cutoff, exactly
pages 1..T, and a page present in two timesteps must be byte-identical in
both. Downstream, retrieval filters on `page <= T` and citations say
`page:N` — absolute numbering is what makes the cutoff real.
"""

SCAFFOLD_DECISIONS_README = """\
# decisions/ — court decisions as corpus data (OPTIONAL; corpus-contract v3)

Put one rii-dok v1 XML file per decision here, named `jb-<doknr>.xml`
exactly as rechtsprechung-im-internet.de publishes them (the library's
docs/decisions-surface.md §2: root `<dokument>` with the 26 DTD elements in
order; `doknr` of the shape KORE123456789 / JURE123456789, equal to the
filename stem, unique; an eight-digit `entsch-datum`; non-empty `gertyp`
and `doktyp`). `validate` refuses a non-conforming file naming the file
and the rule, and reports the tolerated anomalies (§2.3) without refusing.
`up` locks the drop into `decisions.lock.json` (content hash, file and
unit census — no per-file rows) and mounts this directory read-only into
the retrieval service, whose `search_decisions` tool then serves these
decisions by Randnummer (level 2); `verify` compares the served drop
against the lock. `--decisions-dir` remains the override for a drop kept
outside a corpus; a drop here AND that flag is refused.

Leave this directory empty (this README only) and the estate serves the
library's synthetic 30 decisions instead. This README is ignored by the
pipeline and the service; nothing but `jb-<doknr>.xml` files may sit here.
"""

SCAFFOLD_PROMPTS_YAML = """\
# prompts.yaml — what gets asked at THIS timestep. One file per timestep;
# empty or absent is legal (the timestep then contributes no task rows).
# Each entry becomes one row of the task table. Two forms:
prompts:
  # a skill reference — resolves skills/<name>/SKILL.md at build time
  - {source: skill, name: example}
  # a free prompt — the text is the user message, verbatim
  - {source: free,
     text: "Which parties are named so far? Cite pages as (page:N)."}
  # ids are optional and generated (skill:<name>; free:<12 hex of the
  # text's sha256>). Add id: "free:<your-slug>" only if you want an id
  # that survives edits to the text.
"""


def cmd_scaffold(args: argparse.Namespace) -> None:
    out = Path(args.out).expanduser().resolve()
    if out.exists() and not out.is_dir():
        die(f"{out} exists and is not a directory.",
            "a file where the corpus root would go",
            "a new or empty directory for the starting tree",
            "pick another --out")
    if out.is_dir() and any(out.iterdir()):
        die(f"{out} already exists and is not empty.",
            "an existing directory with entries",
            "a new or empty directory for the starting tree",
            "pick another --out, or clear it yourself — scaffold never "
            "overwrites")
    case_dir = out / "train" / "cases" / "case_example" / "timestep-1"
    try:
        (case_dir / "pages").mkdir(parents=True, exist_ok=True)
        (out / "eval" / "cases").mkdir(parents=True)
        (out / "skills" / "example").mkdir(parents=True)
        (out / "corpus.yaml").write_text(
            SCAFFOLD_CORPUS_YAML.format(prog=PROG), encoding="utf-8")
        (out / "AGENTS.md").write_text(SCAFFOLD_AGENTS_MD, encoding="utf-8")
        (out / "skills" / "example" / "SKILL.md").write_text(
            SCAFFOLD_SKILL_MD, encoding="utf-8")
        (case_dir / "pages" / "page_0001.md").write_text(
            SCAFFOLD_PAGE, encoding="utf-8")
        (case_dir / "prompts.yaml").write_text(
            SCAFFOLD_PROMPTS_YAML, encoding="utf-8")
        (out / ic.DECISIONS_DIR).mkdir()
        (out / ic.DECISIONS_DIR / ic.DECISIONS_README).write_text(
            SCAFFOLD_DECISIONS_README, encoding="utf-8")
    except OSError as exc:
        die(f"could not write the starting tree under {out}.", str(exc),
            "a writable location for the new directory", "pick another --out")
    # the promise, kept by construction: the tree it writes validates
    if ic.phase_validate(out, quiet=True) is None:
        die("internal: the scaffolded tree does not pass validate.",
            None, "a tree that validates unmodified", "report this bug")
    rel = os.path.relpath(out, Path.cwd())
    if rel.startswith(".."):
        rel = str(out)          # far from here: the absolute path reads better
    print(f"""== scaffolded {rel}/ == (validates as written; every file says what to change)
  corpus.yaml                the corpus's identity — name and owner are yours to set
  AGENTS.md                  the agent's standing instructions — REPLACE
  skills/example/SKILL.md    one example skill card — REPLACE (it explains what a card is)
  train/cases/case_example/  one case, one timestep, one page, both prompt forms
  eval/cases/                the held-out split (empty; move WHOLE cases here to hold them out)
  decisions/                 court decisions, rii-dok v1 jb-<doknr>.xml — OPTIONAL (empty = the synthetic 30)
next — make it yours, prove it, stand it up:
  1. edit the files marked REPLACE / CHANGE THIS
  2. {PROG} validate --corpus {rel}
  3. {PROG} up --corpus {rel}
your AGENTS.md and skill cards change what the rollout side pins (G1/G2) —
docs/corpus-contract.md, "Bringing your own corpus", carries the re-derivation.""")


# ------------------------------------------- the folded pipeline verbs
# CP-72: `validate` and `ingest` were the pipeline entry points consumers
# ran standalone; they fold in here (in-process, the cmd_scaffold pattern)
# with the pipeline's own exit codes (0 pass / 1 contract fail / 2 pipeline
# error), and `python -m gsj_rollout.ingest_corpus` becomes a deprecated
# alias that keeps working with a notice. The other phases (scaffold /
# taskbank / verify) run inside `up` and keep their pipeline-only form.

def _corpus_root(args: argparse.Namespace) -> Path:
    # usage-class refusals exit 2 here — the pipeline's own code for a bad
    # or missing corpus root, kept so a caller migrating off the deprecated
    # entry reads rc 1 as "the tree fails the contract" and nothing else
    raw = args.corpus or (str(HERE / "corpus" / "staging") if CHECKOUT else None)
    if not raw:
        die("no corpus named.",
            "--corpus not given (a wheel install has no default corpus)",
            "a corpus root in docs/corpus-contract.md's shape",
            f"{PROG} {args.command} --corpus <root>", code=2)
    root = Path(raw).expanduser().resolve()
    if not (root / "corpus.yaml").is_file():
        load_corpus(root, None, refusal_code=2)  # the refusal that names `scaffold`
    return root


def cmd_validate(args: argparse.Namespace) -> None:
    root = _corpus_root(args)
    try:
        corpus = ic.phase_validate(root, only=args.only,
                                   owner_override=args.owner_override,
                                   sandbox_image_override=args.sandbox_image)
    except ic.PipelineError as exc:
        print(f"estate: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if corpus is not None else 1)


def cmd_ingest(args: argparse.Namespace) -> None:
    root = _corpus_root(args)
    try:
        corpus = ic.phase_validate(root, quiet=True)
        if corpus is None:
            die("the corpus tree failed validation — nothing was ingested.",
                "FAIL rows above (each names its file and rule)",
                "zero FAIL rows", f"fix them and re-run; {PROG} validate "
                f"--corpus {root} prints the full table")
        mcp_url = (args.mcp_url.rstrip("/") if args.mcp_url else corpus.mcp_url)
        ic.phase_ingest(corpus, mcp_url, timeout_s=args.ingest_timeout)
    except ic.PipelineError as exc:
        print(f"estate: {exc}", file=sys.stderr)
        sys.exit(2)


# ------------------------------------------------------------------ update
# CP-73 (CP-70 item 10): a changed corpus used to mean a re-run that adopts
# and does not notice, or --rebuild, which re-embeds everything. `update`
# syncs EDITS: it diffs the tree against the RUN's lock (what this estate
# last converged to), reports what moved and what that costs, then acts —
# scaffold --only over the changed cases, one corpus-wide taskbank, one
# reindex trigger, verify. Pure orchestration over phases the pipeline
# already has; no new phase was needed. What it refuses: a corpus whose
# git identity changed (every SHA moves — that is a new corpus, not an
# update), a case removed from the tree (the estate would fail verify on
# the stray lock entry), and a push over branches the estate's record does
# not account for (that is `up --overwrite-repos`, deliberately explicit
# since CP-59). What it never does: force a re-embed — the reindex is the
# service's own if-stale decision, and --rebuild stays `up`'s.

def _parse_git_date(text: str):
    text = (text or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def same_git_identity(tree: dict, live: dict) -> bool | None:
    """corpus.yaml's git block vs a live commit's author — None when the
    dates cannot be compared (unparseable), never a guess."""
    if tree.get("name") != live.get("name") or tree.get("email") != live.get("email"):
        return False
    t, l = _parse_git_date(tree.get("date", "")), _parse_git_date(live.get("date", ""))
    if t is None or l is None:
        return None
    # the author line carries the OFFSET into the SHA, so equal instants at
    # different offsets are still different identities
    return t == l and t.utcoffset() == l.utcoffset()


def update_plan(corpus, lock_cases: dict, built: dict[str, dict[str, str]]) -> dict:
    """The local diff: what moved between the tree and the estate's lock,
    per case, with the downstream consequence on every line. Pure — the
    live checks (drift, identity, AGENTS/card attribution) come after."""
    plan = {"unchanged": [], "push": {}, "new": [], "removed": [],
            "bank_moves": False, "repos_move": False}
    plan["removed"] = sorted(set(lock_cases) - set(corpus.cases))
    for cid in sorted(corpus.cases):
        case = corpus.cases[cid]
        entry = lock_cases.get(cid)
        if not isinstance(entry, dict):
            plan["new"].append(cid)
            plan["push"][cid] = ["NEW — repo created and pushed; the index "
                                 "gains the case; the bank gains its rows"]
            plan["bank_moves"] = plan["repos_move"] = True
            continue
        reasons: list[str] = []
        old_refs = entry.get("refs") or {}
        new_refs = built[cid]
        old_ts = entry.get("timesteps") or {}
        if new_refs != old_refs:
            plan["repos_move"] = True
            added = sorted(set(new_refs) - set(old_refs))
            gone = sorted(set(old_refs) - set(new_refs))
            moved = sorted(b for b in new_refs
                           if b in old_refs and new_refs[b] != old_refs[b])
            if added:
                reasons.append(f"new branch(es) {added} — new timestep(s); "
                               "the index and the bank gain them")
            if gone:
                reasons.append(f"branch(es) {gone} removed — the push prunes "
                               "them; the index and the bank lose them")
            if moved:
                # the census cannot drift on its own: the contract pins each
                # timestep-T to exactly pages 1..T, so a census change IS a
                # branch-set change (added/gone above)
                if added or gone:
                    reasons.append(f"branches {moved} re-derived — main holds "
                                   "the largest timestep and every timestep "
                                   "branch truncates from it, so a timestep "
                                   "added or removed moves them all (page "
                                   "bytes may also have changed)")
                else:
                    reasons.append(f"content moved on {moved} with the page "
                                   "census unchanged — page bytes, AGENTS.md "
                                   "or a skill card (the corpus lines "
                                   "attribute it)")
        if entry.get("split") != case.split:
            reasons.append(f"split {entry.get('split')!r} -> {case.split!r} — "
                           "the lock's split and the bank's rows move")
            plan["bank_moves"] = True
        for t in sorted(case.timesteps):
            old_ids = (old_ts.get(str(t)) or {}).get("prompt_ids")
            new_ids = [p.id for p in case.timesteps[t].prompts]
            if old_ids is not None and old_ids != new_ids:
                reasons.append(f"prompts at timestep-{t}: {old_ids} -> "
                               f"{new_ids} — the bank's rows move"
                               + ("" if new_refs != old_refs else
                                  " (the repo itself is unchanged; the push "
                                  "converges to the same SHAs and refreshes "
                                  "the lock row)"))
                plan["bank_moves"] = True
        if new_refs != old_refs:
            plan["bank_moves"] = True
        if reasons:
            plan["push"][cid] = reasons
        else:
            plan["unchanged"].append(cid)
    return plan


def _fj_json(url: str, token: str, path: str):
    return http("GET", f"{url}/api/v1{path}",
                headers={"Authorization": f"token {token}"})


def _fj_raw(url: str, token: str, owner: str, cid: str,
            path: str) -> tuple[str | None, bool]:
    """(text, known): text is the live file (None when absent), and `known`
    is False when the fetch itself failed — absence and failure must never
    read the same (a transient 500 is not a NEW skill card)."""
    status, body = _fj_json(url, token, f"/repos/{owner}/{cid}/raw/{path}?ref=main")
    if status == 200 and isinstance(body, str):
        return body, True
    if status == 404:
        return None, True
    return None, False


def _fj_branches(url: str, token: str, owner: str, cid: str) -> dict[str, str] | None:
    """branch -> sha for a live repo; None when the repo does not exist."""
    status, _ = _fj_json(url, token, f"/repos/{owner}/{cid}")
    if status == 404:
        return None
    heads: dict[str, str] = {}
    page = 1
    while page <= 200:
        status, body = _fj_json(url, token,
                                f"/repos/{owner}/{cid}/branches?limit=50&page={page}")
        if status != 200 or not isinstance(body, list):
            die(f"could not list the branches of {owner}/{cid}.",
                f"GET /repos/{owner}/{cid}/branches -> {status} {str(body)[:120]}",
                "200",
                "the run's read token must still be valid (run.json names "
                "the variable; the value is in the run's .env), and the "
                "instance reachable")
        if not body:
            return heads
        heads.update({b["name"]: b["commit"]["id"] for b in body})
        page += 1
    return heads


@mutating_command
def cmd_update(args: argparse.Namespace) -> None:
    run_ = _load_run(args.name, _command_run(args, args.name))
    rec = run_.record
    fj_rec, mcp_rec = rec.get("forgejo", {}), rec.get("mcp", {})
    owner = fj_rec.get("owner") or rec.get("corpus", {}).get("owner")
    if not owner or not fj_rec.get("url"):
        die(f"run {args.name!r} has no estate to update.",
            "run.json records no Forgejo URL or owner",
            "a run `up` completed at least once",
            f"{PROG} up --name {args.name} first")
    raw_path = args.corpus or rec.get("corpus", {}).get("path")
    if not raw_path:
        die(f"run {args.name!r} records no corpus path.", "run.json", None,
            "pass --corpus <root>")
    corpus_path = Path(raw_path).expanduser().resolve()
    simage = (rec.get("sandbox_image")
              or rec.get("corpus", {}).get("sandbox_image")  # pre-CP-71 record
              or ic.DEFAULT_SANDBOX_IMAGE)
    push_env, read_env = ic.token_env_name(owner), ic.read_token_env_name(owner)

    # ---- the tree, validated; the estate's answers stand (owner, image)
    try:
        raw_yaml = yaml.safe_load((corpus_path / "corpus.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw_yaml = {}
    yaml_owner = raw_yaml.get("owner") if isinstance(raw_yaml.get("owner"), str) else None
    corpus = load_corpus(corpus_path, owner if owner != yaml_owner else None,
                         simage)
    if yaml_owner and yaml_owner != owner:
        say("update", f"corpus.yaml says owner {yaml_owner!r}; the estate's "
                      f"answer {owner!r} stands (moving owners is `up "
                      f"--retarget`'s, not an update)")
    # the review's find: every scaffolded corpus shares the template's git
    # identity, so the identity check cannot tell two corpora apart — the
    # NAME is the one discriminator a wrong --corpus reliably trips
    rec_name = rec.get("corpus", {}).get("name")
    if rec_name and corpus.name != rec_name:
        die(f"the corpus at {corpus_path} names itself {corpus.name!r}; run "
            f"{args.name!r} stands on {rec_name!r}.",
            f"corpus.yaml name: {corpus.name!r}",
            f"{rec_name!r} (run.json — an update edits the SAME corpus)",
            "if this is a different corpus, stand it up as its own run "
            f"(`{PROG} up --name <new>`); if you renamed corpus.yaml's "
            "`name:`, restore it — a renamed corpus cannot be told apart "
            "from a wrong --corpus, and pushing one corpus over another "
            "estate is exactly what this refusal exists to stop")
    if args.corpus and str(corpus_path) != rec.get("corpus", {}).get("path"):
        say("update", f"corpus path differs from the record "
                      f"({rec.get('corpus', {}).get('path')}) — same corpus, "
                      "moved; the record follows a completed update")

    # ---- the baseline: the RUN's lock — what this estate last converged to
    run_lock_path = run_.dir / ic.LOCK_NAME
    if not run_lock_path.is_file():
        die(f"run {args.name!r} holds no {ic.LOCK_NAME} copy.",
            f"{run_lock_path} absent",
            "the lock `up` copies beside run.json when it completes",
            f"{PROG} up --name {args.name} once, then update")
    try:
        lock = json.loads(run_lock_path.read_text())
    except (OSError, ValueError) as exc:
        die(f"{run_lock_path} is unreadable.", str(exc),
            "the lock copy `up` wrote beside run.json",
            f"restore it from backup, or `{PROG} up --name {args.name}` "
            "re-copies it after a converged run")
    lock_cases = lock.get("cases") if isinstance(lock.get("cases"), dict) else {}

    # the run's copy is the baseline the phases must also act on: scaffold
    # merges --only rows into the TREE's lock, taskbank refuses any case
    # missing from it, verify checks its strays — so a tree lock that is
    # absent (a fresh checkout of the corpus source) or divergent would
    # push first and fail after (the review reproduced both). The baseline
    # is SEEDED into the tree before acting, below.
    tree_lock = ic.load_lock(corpus_path)
    seed_tree_lock = tree_lock != lock
    if tree_lock and seed_tree_lock:
        warn("update", "the corpus tree's own lock differs from the run's "
             "copy (the tree was scaffolded outside this run) — the run's "
             "copy is the baseline and is seeded into the tree before "
             "acting; verify stays the arbiter")

    PH.start("diff", f"{corpus_path} vs the estate's lock ({run_lock_path})")
    built = built_heads(corpus)
    plan = update_plan(corpus, lock_cases, built)
    # a free prompt edited under an EXPLICIT id moves neither refs nor
    # prompt ids (the id surviving edits is that feature's point) — the
    # run's own bank copy records the text last served, so the text is
    # diffed against it (skill-card text always moves refs; free text is
    # the one silent channel)
    run_bank = run_.dir / ic.TASKBANK_NAME
    old_rows = None
    if run_bank.is_file():
        try:
            old_rows = {(r["case_id"], r["timestep"], r["prompt_id"]):
                        r.get("prompt_text")
                        for r in ic.read_taskbank_rows(run_bank)}
        except ic.PipelineError as exc:
            warn("update", f"the run's bank copy is unreadable ({exc}) — a "
                 "free-prompt text edit under an explicit id cannot be "
                 "detected this run")
    else:
        warn("update", "the run holds no taskbank copy — a free-prompt text "
             "edit under an explicit id cannot be detected this run")
    if old_rows is not None:
        for cid in list(plan["unchanged"]):
            case = corpus.cases[cid]
            edited = sorted({f"timestep-{t}" for t in case.timesteps
                             for p in case.timesteps[t].prompts
                             if p.source == "free"
                             and (cid, t, p.id) in old_rows
                             and old_rows[(cid, t, p.id)] != p.text})
            if edited:
                plan["push"][cid] = [
                    f"free-prompt TEXT edited at {edited} under an explicit "
                    "id (the id survives edits by design; diffed against the "
                    "run's bank) — the bank's rows move; the repo is "
                    "unchanged and the push converges"]
                plan["unchanged"].remove(cid)
                plan["bank_moves"] = True
    PH.done(f"{len(plan['push'])} case(s) to sync, {len(plan['unchanged'])} "
            f"unchanged, {len(plan['removed'])} removed")

    if plan["removed"]:
        die(f"case(s) {plan['removed']} are in the estate's lock but not in "
            f"the corpus tree.",
            "a case removed from the tree (its live repo and lock entry remain)",
            "an update only EDITS: pages, timesteps, prompts, cards, new cases",
            "removing a case is not an update — delete its repo on the git "
            "host and its corpus.lock.json entries (tree and run copies) "
            "yourself, or `down --wipe` and stand the smaller corpus up as "
            "a fresh run; verify fails on the stray lock entry until then")

    # ---- report (the local half)
    print(f"\n== update plan: run {args.name} ==")
    for cid in plan["unchanged"]:
        print(f"  {cid:14} unchanged")
    for cid, reasons in sorted(plan["push"].items()):
        print(f"  {cid:14} " + f"\n  {'':14} ".join(reasons))
    if not plan["push"]:
        print("  nothing moved — the corpus matches the estate's lock; "
              "nothing to do")
        return
    if args.dry_run:
        print("  (--dry-run: the local diff only — the live checks (branch "
              "drift, git identity, AGENTS/skill-card attribution) run "
              "before a real update acts; nothing was touched)")
        return

    # ---- the live checks: the estate must stand, and account for itself
    status, body = http("GET", f"{fj_rec['url']}/api/healthz", timeout=5)
    if status != 200:
        die(f"the run's Forgejo at {fj_rec['url']} is not answering.",
            f"GET /api/healthz -> {status if status is not None else body}",
            "200 (update syncs a STANDING estate)",
            f"{PROG} up --name {args.name} brings it back, then update")
    read_tok = run_.env.get(read_env) or run_.env.get(push_env)
    if not read_tok:
        die(f"the run's .env holds neither {read_env} nor {push_env}.",
            f"{run_.dir / '.env'}", "the tokens `up` minted",
            "restore .env from your backup, or re-run `up` to re-mint")

    # git identity: read one recorded commit's author off the live estate —
    # a changed identity moves EVERY sha and is a new corpus, not an update
    ident_checked = False
    for cid in sorted(lock_cases):
        if not isinstance(lock_cases[cid], dict):
            continue        # update_plan already classed it as NEW
        sha = (lock_cases[cid].get("refs") or {}).get("main")
        if not sha:
            continue
        status, body = _fj_json(fj_rec["url"], read_tok,
                                f"/repos/{owner}/{cid}/git/commits/{sha}")
        if status != 200 or not isinstance(body, dict):
            break
        live_author = (body.get("commit") or {}).get("author") or {}
        verdict = same_git_identity(corpus.git_identity, live_author)
        ident_checked = verdict is not None
        if verdict is False:
            die("the corpus git identity changed — every SHA moves; that is "
                "not an update.",
                f"the live estate's commits: {live_author.get('name')!r} "
                f"<{live_author.get('email')}> @ {live_author.get('date')}",
                f"corpus.yaml's git block: {corpus.git_identity['name']!r} "
                f"<{corpus.git_identity['email']}> @ {corpus.git_identity['date']}",
                "restore corpus.yaml's git: block (the three DO-NOT-CHANGE "
                "values), or stand the re-identified corpus up as its own "
                f"run: {PROG} up --name <new>")
        break
    if not ident_checked:
        warn("update", "the git identity could not be verified against a "
             "live commit — if corpus.yaml's git: block changed, every SHA "
             "below reads as content movement")

    # AGENTS.md / skill cards: live bytes vs tree bytes, from a recorded
    # case — the G1/G2 attribution, and the pins consequence OUT LOUD
    corpus_lines: list[str] = []
    pins_move = False
    ref_case = sorted(lock_cases)[0] if lock_cases else None
    if ref_case and plan["repos_move"]:
        live_agents, known = _fj_raw(fj_rec["url"], read_tok, owner, ref_case,
                                     "AGENTS.md")
        if not known or live_agents is None:
            # a failed fetch is NOT absence — and every built repo carries
            # AGENTS.md, so a 404 here means the REFERENCE REPO is gone:
            # skip card attribution too rather than misread every card as NEW
            warn("update", "AGENTS.md attribution unavailable (the raw fetch "
                 f"did not answer with the file — {ref_case}'s repo may be "
                 "gone) — if you edited AGENTS.md or a skill card, G1/G2 "
                 "move and the pins consequence applies; card attribution "
                 "skipped this run")
            ref_case = None
        elif live_agents != corpus.agents_md.read_text(encoding="utf-8"):
            corpus_lines.append("AGENTS.md EDITED — it rides every branch "
                                "of every case, and G2 (the pinned system "
                                "prompt) moves with it")
            pins_move = True
        else:
            corpus_lines.append("AGENTS.md unchanged")
        for skill_name in sorted(corpus.skills) if ref_case else []:
            live_card, known = _fj_raw(fj_rec["url"], read_tok, owner, ref_case,
                                       f"skills/{skill_name}/SKILL.md")
            tree_card = corpus.skills[skill_name].read_text(encoding="utf-8")
            if not known:
                warn("update", f"skill card {skill_name!r} attribution "
                     "unavailable (the raw fetch failed) — if you edited it, "
                     "G1 moves and the pins consequence applies")
            elif live_card is None:
                corpus_lines.append(f"skill card {skill_name!r} NEW — it rides "
                                    "every repo; G1 pins it")
                pins_move = True
            elif live_card != tree_card:
                corpus_lines.append(f"skill card {skill_name!r} EDITED — G1 "
                                    "moves; its resolved bytes ride every "
                                    "bank row that references it")
                pins_move = True
        status, listing = (_fj_json(fj_rec["url"], read_tok,
                                    f"/repos/{owner}/{ref_case}/contents/skills?ref=main")
                           if ref_case else (None, None))
        if status == 200 and isinstance(listing, list):
            gone_cards = sorted({e.get("name") for e in listing
                                 if isinstance(e, dict)} - set(corpus.skills) - {None})
            for skill_name in gone_cards:
                corpus_lines.append(f"skill card {skill_name!r} REMOVED — it "
                                    "leaves every repo; episodes pinned to it "
                                    "stay quarantined history")
                pins_move = True
    for line in corpus_lines:
        print(f"  {'corpus':14} {line}")
    if pins_move:
        warn("update", "G1/G2 move with this update: every episode on the "
             "affected cards QUARANTINES at trace validation until the "
             f"approved pins are re-derived — {BRING_YOUR_OWN_URL}#your-pins "
             "(pins/derive_pins.py re-verifies the REFERENCE set only and does "
             "not ship on the wheel; GSJ_PINS_PATH names the set in force) — "
             "this tool does not write pins")

    # drift: update pushes ONLY over branches the estate's record accounts
    # for; anything else diverged out-of-band and is up --overwrite-repos's
    for cid in sorted(plan["push"]):
        live = _fj_branches(fj_rec["url"], read_tok, owner, cid)
        entry = lock_cases.get(cid)
        entry = entry if isinstance(entry, dict) else {}
        if cid in plan["new"]:
            if live is None:
                continue
            if live == built[cid]:
                say("update", f"{cid}: the repo already holds exactly this "
                              "build — adopting it")
                continue
            die(f"{owner}/{cid} exists on {fj_rec['url']} and is NOT what "
                f"this corpus builds.",
                f"live {live}", f"no repo, or exactly {built[cid]}",
                "a new case must land on a fresh repo — delete the "
                "colliding one there, rename the case, or use `up "
                "--overwrite-repos` if pushing over it is really meant")
        elif live is not None and live != (entry.get("refs") or {}):
            if live == built[cid]:
                # not drift: OUR build, pushed by an update that died before
                # its record refresh — a resumed update adopts it (the same
                # convergence-by-determinism that makes re-push a no-op)
                say("update", f"{cid}: the live repo already holds exactly "
                              "this corpus's build (an earlier update's push) "
                              "— resuming")
                continue
            diff = sorted({b for b in set(live) | set(entry.get("refs") or {})
                           if live.get(b) != (entry.get("refs") or {}).get(b)})
            die(f"{owner}/{cid} on {fj_rec['url']} diverged from what this "
                f"estate recorded — update does not push over it.",
                f"branches differing {diff} (live vs the run's lock)",
                "a live repo still holding exactly the recorded build (or "
                "exactly what this corpus builds — a resumed update)",
                "someone pushed to the estate out-of-band: reconcile there, "
                "or `up --overwrite-repos` if losing those branches is "
                "really meant (CP-59 made that explicit for a reason)")
        elif live is None:
            say("update", f"{cid}: the recorded repo is gone from the estate "
                          "— it will be recreated")

    # the MCP: a standing service to reindex (never a forced re-embed). A
    # NEW case cannot enter a running service by reindex alone — its
    # source.repos is read at START only — so a created service's config
    # (this run's own artifact) is rewritten and its container restarted,
    # while an adopted service's config is its operator's: refused with
    # the fix named (the `up --mcp adopt` posture).
    mcp_url = mcp_rec.get("url")
    mcp_created = mcp_rec.get("mode") == "created" and bool(rec.get("compose", {}).get("mcp"))
    if mcp_url:
        hstat, h = http("GET", f"{mcp_url}/health", timeout=5)
        if not isinstance(h, dict):
            die(f"the run's retrieval service at {mcp_url} is not answering.",
                f"GET /health -> {hstat if hstat is not None else h}",
                "a standing service (update syncs it)",
                f"{PROG} up --name {args.name} brings it back, then update")
        if plan["new"] and not mcp_created:
            die("the adopted retrieval service cannot gain the new case(s) "
                "from here.",
                f"new case(s) {plan['new']} — the service's source.repos is "
                "its operator's, read at its start",
                "a service already indexing every case of this corpus",
                "add the new case(s) to its config.yaml source.repos and "
                "restart it there, then re-run update (the same posture as "
                "`up --mcp adopt`)")

    restart_note = ("" if not (plan["new"] and mcp_created) else
                    f"\n        new case(s) {plan['new']}: the created service's config gains"
                    "\n        them and its container restarts (source.repos is start-time"
                    "\n        only) —")
    print(f"""  will: push {len(plan['push'])} repo(s) (only those), refresh their lock rows,
        rebuild the taskbank (corpus-wide by design),{restart_note} trigger ONE reindex —
        the service's own if-stale decision: since 0.5.0 (CP-79) it keeps
        one fingerprint per collection and re-embeds only the case(s) that
        moved (a decisions drop and the untouched cases are reused as they
        are — wishlist row 61); a service before 0.5.0 re-embeds the WHOLE
        corpus when any case moved — then verify, and refresh the run's
        lock/bank copies.
  will not: force a re-embed (--rebuild is `up`'s), push over branches the
        record does not account for (--overwrite-repos is `up`'s).""")
    if not args.defaults and sys.stdin.isatty():
        try:
            typed = input(f"{_c('36', '?')} apply this update? (yes / no) "
                          f"[yes]: ").strip().lower()
        except EOFError:
            typed = "no (stdin closed)"   # a spending confirm: EOF declines
        if typed not in ("", "y", "yes"):
            die("the update was declined at the plan.", "the operator answered no",
                "yes", "nothing was touched; re-run when the plan reads right")

    # ---- act: the pipeline's own phases, only where the plan says
    def pipeline(phase: str, *extra: str, mcp: str | None = None) -> None:
        cmd = [sys.executable, str(INGEST), phase, "--corpus", str(corpus_path),
               "--base-url", fj_rec["url"], "--sandbox-image", simage,
               "--ingest-timeout", str(args.ingest_timeout)]
        if mcp:
            cmd += ["--mcp-url", mcp]
        if owner != yaml_owner:
            cmd += ["--owner-override", owner]
        cmd += list(extra)
        PH.start(phase, f"{INGEST.name} {phase}" + (f" --only {' '.join(sorted(plan['push']))}"
                                                    if "--only" in extra else ""))
        penv = {**os.environ, "GSJ_PIPELINE_DRIVER": "estate",
                **{k: v for k, v in run_.env.items()
                   if k in (push_env, read_env, MCP_SECRET_ENV)}}
        proc = run_phase(cmd, penv, phase)
        if proc.returncode != 0:
            die(f"the corpus pipeline's `{phase}` phase failed (exit {proc.returncode}).",
                "the pipeline's own message above", "exit 0",
                "fix what it names and re-run `update` — every phase is idempotent")

    case_ids = sorted(corpus.cases)
    if seed_tree_lock:
        # the phases key off the TREE's lock; a fresh checkout has none and
        # a divergent one mis-splits the bank or strays at verify — the
        # baseline this update diffed against becomes the tree's
        shutil.copyfile(run_lock_path, corpus_path / ic.LOCK_NAME)
        say("update", f"{ic.LOCK_NAME} seeded into the tree from the run's "
                      "baseline copy (the phases below refresh it)")
    pipeline("scaffold", "--only", *sorted(plan["push"]))
    PH.done(f"{len(plan['push'])} case repo(s) pushed and converged; lock rows refreshed")
    pipeline("taskbank")
    bank_sha = sha256_file(corpus_path / ic.TASKBANK_NAME)
    PH.done(f"rebuilt, sha256 {bank_sha[:12]}…")
    if plan["new"] and mcp_created and mcp_url:
        cm = rec["compose"]["mcp"]
        cfg_path = Path(cm["config"])
        text = cfg_path.read_text()
        doc = yaml.safe_load(text)
        doc.setdefault("source", {})["repos"] = case_ids
        head = ""
        for line in text.splitlines():
            if not line.startswith("#"):
                break
            head += line + "\n"
        cfg_path.write_text(head + yaml.safe_dump(doc, sort_keys=False))
        PH.start("mcp", f"source gains {plan['new']} — mcp-config.yaml rewritten; "
                        "the container restarts to read it (source.repos is "
                        "start-time only)")
        up = compose_up(run_.dir, "-d", "--force-recreate", "mcp")
        if up.returncode != 0:
            kind = pull_failure_kind(up.stderr)
            die("`docker compose up --force-recreate mcp` failed"
                + (" — the daemon could not extract or mount the image." if kind == "extract"
                   else "."),
                (up.stderr.strip().splitlines() or ["the compose error above"])[-1],
                "a daemon whose storage can extract and mount OCI layers" if kind == "extract"
                else None,
                pull_failure_fix(kind, str(cm.get("image")), "the error is authoritative"))
        mcp = Mcp(mcp_url, mcp_rec.get("container_url") or "",
                  run_.env.get(MCP_SECRET_ENV, ""), "created")
        h0 = mcp.wait_ready(args.ingest_timeout, "restart with the new case set",
                            container=cm.get("container"))
        PH.done(f"ready; cases {sorted((h0.get('cases') or {}).keys())}")
    if mcp_url:
        pipeline("ingest", mcp=mcp_url)
        h = http("GET", f"{mcp_url}/health", timeout=10)[1]
        h = h if isinstance(h, dict) else {}
        PH.done(f"state={h.get('state')}, fingerprint {str(h.get('fingerprint'))[:12]}…, "
                f"index_reused={h.get('index_reused')}")
    else:
        h = {}
        say("update", "the run records no retrieval service — reindex skipped")
    pipeline("verify", mcp=mcp_url)
    PH.done("PASS — the live repos, the index census and the bank rows match the tree")

    # ---- the record and the run's copies move with the corpus
    for src in (ic.TASKBANK_NAME, ic.LOCK_NAME):
        shutil.copyfile(corpus_path / src, run_.dir / src)
    if (corpus_path / ic.DECISIONS_LOCK_NAME).is_file():     # CP-88: the drop's lock rides along
        shutil.copyfile(corpus_path / ic.DECISIONS_LOCK_NAME, run_.dir / ic.DECISIONS_LOCK_NAME)
    else:
        (run_.dir / ic.DECISIONS_LOCK_NAME).unlink(missing_ok=True)
    new_lock = ic.load_lock(corpus_path, required=True)
    rec.setdefault("corpus", {}).update({
        "path": str(corpus_path), "name": corpus.name, "owner": owner,
        "case_ids": case_ids,
        "lock_sha256": sha256_file(run_.dir / ic.LOCK_NAME),
        "decisions_lock_sha256": (sha256_file(run_.dir / ic.DECISIONS_LOCK_NAME)
                                  if (run_.dir / ic.DECISIONS_LOCK_NAME).is_file() else None),
        "taskbank_sha256": bank_sha,
        "taskbank_rows": (new_lock.get("taskbank") or {}).get("rows"),
        "repos": {cid: new_lock["cases"][cid]["refs"] for cid in case_ids}})
    if mcp_url and h:
        rec.setdefault("mcp", {}).update(
            {"state": h.get("state"), "fingerprint": h.get("fingerprint"),
             "index_reused": h.get("index_reused"), "cases": h.get("cases")})
    rec["phases"] = PH.rows
    rec["last_run"] = {"at": now_iso(), "mode": "update",
                       "synced": sorted(plan["push"]),
                       "unchanged": plan["unchanged"],
                       "pins_move": pins_move}
    run_.write_record()
    g1 = pins_g1_check(corpus)
    rec["pins"] = g1
    run_.write_record()
    if g1.get("checked") and g1["not_in_approved_set"]:
        warn("update", f"{len(g1['not_in_approved_set'])}/{g1['cards']} skill "
             f"card(s) are not in the approved set at {g1['pins_path']}: "
             f"{g1['not_in_approved_set']} — episodes on them quarantine "
             f"until the pins walk re-derives — {BRING_YOUR_OWN_URL}#your-pins "
             "(pins/derive_pins.py re-verifies the REFERENCE set only and does "
             "not ship on the wheel)")
    say("update", f"complete in {round(time.monotonic() - _T0, 1)}s — synced "
                  f"{sorted(plan['push'])}; verify PASS; the run's lock and "
                  f"bank copies are current")


# ------------------------------------------------------- status and down

def _load_run(name: str, r: Run | None = None) -> Run:
    r = r or Run(name)
    if not (r.dir / "run.json").is_file():
        die(f"no run named {name!r}.", f"{r.dir} has no run.json",
            "a run this script created", f"{PROG} up --name {name} (or --runs-dir "
            "naming the directory that holds it)")
    r.load()
    return r


def _forgejo_status_line(fj: dict) -> str:
    status, _ = http("GET", f"{fj.get('url')}/api/healthz", timeout=3)
    vstat, _ = http("GET", f"{fj.get('url')}/api/v1/version", timeout=3)
    return (f"forgejo  {fj.get('mode'):8} {fj.get('url')}  healthz={status}  "
            f"sign-in={'ON' if vstat == 403 else 'OFF' if vstat == 200 else '?'}  "
            f"owner {fj.get('owner')!r}")


def lock_held(r: Run) -> bool:
    """CP-94 (three strangers, three wrong `status` answers on runs that had
    not died): the run lock is the discriminator between a run in flight and
    one that stopped — `up`, `update` and `down` hold <runs-dir>/.locks/<name>.lock
    for their whole command and the kernel drops it with the process. A
    non-blocking probe: held means active; absent or free means not."""
    lock = r.root / ".locks" / f"{r.name}.lock"
    try:
        fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False          # never locked (a pre-CP-59 run dir): not in flight
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _compose_ps_lines(r: Run) -> list[str]:
    ps = compose(r.dir, "ps", "--format", "table {{.Name}}\t{{.Status}}", capture_output=True)
    return (ps.stdout.rstrip() or "(nothing running)").splitlines()


def status_rows(r: Run, rec: dict, *, active: bool = False) -> list[tuple[str, str]]:
    """One row per phase in `up`'s order, read from what is ON DISK and what
    the daemon says — never only from record keys a later phase writes
    (CP-92's first cut, and CP-94's `mcp not reached` beside a running
    container: the record's mcp block lands after ingest, the engine and
    config blocks with the closing write)."""
    rows: list[tuple[str, str]] = []
    # an ACTIVE run has not died: what it has not reached, it has not reached YET
    unreached = "not reached yet" if active else "not reached"
    c = rec.get("corpus") or {}
    rows.append(("corpus", f"{c.get('name')}: {len(c.get('case_ids') or [])} case(s); "
                           f"owner {c.get('owner')!r}; {c.get('path')}") if c
                else ("corpus", unreached))
    # what is on disk when `up` dies mid-phase: run.json lands right after
    # rec["forgejo"] is set (before the owner block), the tokens land in
    # .env (write_env) and the scaffold writes the corpus tree's lock — so
    # the owner comes from the corpus phase, the tokens from .env, the
    # scaffold from the lock, never from record keys a later phase writes
    owner = (rec.get("forgejo") or {}).get("owner") or c.get("owner")
    fj = rec.get("forgejo") or {}
    rows.append(("forgejo", _forgejo_status_line({**fj, "owner": owner})[len("forgejo  "):])
                if fj else ("forgejo", unreached))
    if owner and all(name in r.env for name in (ic.token_env_name(owner),
                                                 ic.read_token_env_name(owner))):
        rows.append(("owner", f"{owner!r}; tokens minted in .env ({ic.token_env_name(owner)}, "
                              f"{ic.read_token_env_name(owner)})"))
    else:
        rows.append(("owner", unreached))
    # the tree's lock records the git host the scaffold pushed to
    # (`corpus.base_url` — cmd_up passes --base-url fj.url, or corpus.yaml's
    # own canonical one); a lock from another host is another run's push
    lock = Path(str(c.get("path"))) / ic.LOCK_NAME if c.get("path") else None
    lock_doc: dict = {}
    if lock and lock.is_file():
        try:
            lock_doc = json.loads(lock.read_bytes())
        except (OSError, ValueError):
            lock_doc = {}
    lock_doc = lock_doc if isinstance(lock_doc, dict) else {}
    lock_host = str((lock_doc.get("corpus") or {}).get("base_url") or "").rstrip("/")
    this_hosts = {str(fj.get(k) or "").rstrip("/") for k in ("url", "container_url")} - {""}
    try:                                    # a corpus.yaml naming its own canonical host
        own = (yaml.safe_load((Path(str(c.get("path"))) / "corpus.yaml").read_text())
               or {}).get("forgejo", {}).get("base_url") if c.get("path") else None
        if isinstance(own, str) and own:
            this_hosts.add(own.rstrip("/"))
    except (OSError, yaml.YAMLError, AttributeError):
        pass
    if lock_doc and lock_host and lock_host in this_hosts:
        cases = len(lock_doc.get("cases") or {})
        stamp = datetime.fromtimestamp(lock.stat().st_mtime, timezone.utc).replace(
            microsecond=0).isoformat()
        rows.append(("scaffold", f"pushed — lock written {stamp} ({cases} case(s)): {lock}"))
    elif lock_doc:
        rows.append(("scaffold", f"a lock from another git host ({lock_host or 'none recorded'}) "
                                 f"— not this run's push: {lock}"))
    else:
        rows.append(("scaffold", unreached))
    m = rec.get("mcp") or {}
    cm = (rec.get("compose") or {}).get("mcp") or {}
    if m:
        hstat, h = http("GET", f"{m.get('url')}/health", timeout=3)
        h = h if isinstance(h, dict) else {}
        rows.append(("mcp", f"{m.get('mode')} {m.get('url')}  state={h.get('state', hstat)}"))
    elif cm and (r.dir / "compose.yaml").is_file():
        # CP-94: the compose block and the container land BEFORE the embed,
        # the record's mcp block only after ingest — so ask the daemon, which
        # is what a reader sees two lines below in compose ps
        url = f"http://127.0.0.1:{cm.get('port')}"
        hstat, h = http("GET", f"{url}/health", timeout=3)
        h = h if isinstance(h, dict) else {}
        # docker's `table` format pads columns with spaces, never tabs
        line = next((ln for ln in _compose_ps_lines(r)
                     if ln.split() and ln.split()[0] == str(cm.get("container"))), "")
        if line or hstat is not None:
            rows.append(("mcp", f"created {url}  state={h.get('state', hstat)}  container "
                                f"{' '.join(line.split()[1:]) if line else 'not running'} "
                                "— reached (the record's mcp block lands after ingest; a "
                                "resume adopts what stands)"))
        else:
            rows.append(("mcp", f"{unreached} — up {'is' if active else 'died'} in or before this phase "
                                f"(retrieval service image {cm.get('image')})"))
    else:
        rows.append(("mcp", f"{unreached} — up {'is' if active else 'died'} in or before this phase"
                            + (f" (retrieval service image {cm.get('image')})" if cm else "")))
    bank = r.dir / ic.TASKBANK_NAME
    rows.append(("taskbank", f"{bank} present" if bank.is_file() else unreached))
    rows.append(("verify", f"{r.dir / ic.LOCK_NAME} present (copied after verify PASS)"
                 if (r.dir / ic.LOCK_NAME).is_file() else unreached))
    e = rec.get("engine") or {}
    rows.append(("engine", f"{e.get('url')} probed: reachable={e.get('reachable')} "
                           f"model_served={e.get('model_served')}") if e
                else ("engine", "not recorded yet — probed after verify" if active else
                                "not recorded — probed after verify; its record lands with "
                                "the closing write (a resume re-probes)"))
    cfg = r.dir / "rollout.yaml"
    rows.append(("config", f"{cfg} present" if cfg.is_file() else
                 ("not written yet" if active else "not written")))
    return rows


def _print_rows_and_services(r: Run, rec: dict, *, active: bool = False) -> None:
    for phase, text in status_rows(r, rec, active=active):
        print(f"  {phase:9} {text}")
    if (r.dir / "compose.yaml").is_file():
        print("  created services (compose ps):")
        print("    " + "\n    ".join(_compose_ps_lines(r)))
    sys.stdout.flush()      # the report lands before any refusal, piped or not


def status_active(name: str, r: Run, rec: dict) -> None:
    """CP-94: a held lock — the run is in flight; say so, say wait, exit 0.
    Nothing here recommends a second `up` (it would be refused as busy)."""
    print(f"== run {name} == {r.dir}  (ACTIVE — a command holds this run's lock: an `up`, "
          "`update` or `down` is still running)")
    if rec:
        _print_rows_and_services(r, rec, active=True)
    else:
        print("  (no record yet — `up` is in its first phase; run.json lands once Forgejo stands)")
    print(f"\nestate: run {name!r} is ACTIVE — wait for the running command (its own output says "
          f"where it is; a pull prints a heartbeat every {PULL_HEARTBEAT_S:.0f}s), then `status` "
          "again. Do not start a second `up` (refused as busy) and never delete the lock file.")
    sys.stdout.flush()


def status_partial(name: str, r: Run, rec: dict) -> None:
    """CP-92 (a stranger's finding): an `up` that stopped mid-phase leaves a
    record that names what stands — report it, phase by phase in `up`'s
    order, THEN refuse with the resume cure. The lock says the run is NOT in
    flight (CP-94: that case is status_active)."""
    print(f"== run {name} == {r.dir}  (incomplete — up did not finish)")
    _print_rows_and_services(r, rec)
    c = rec.get("corpus") or {}
    # `up` resolves --corpus BEFORE it loads the record (no default on the
    # wheel; the staging fixture in a checkout), so the cure names the run's own
    corpus_arg = f"--corpus {c['path']}" if c.get("path") else "--corpus <the run's corpus root>"
    die(f"run {name!r} is incomplete.", f"{r.dir / 'run.json'} records only part of up "
        "(the phases above stand)", "a completed Forgejo and MCP record",
        f"re-run `{PROG} up --name {name} {corpus_arg} --runs-dir {r.root}` to resume "
        "(it adopts what stands and backfills the rest), or use down to stop its "
        "created services")


def cmd_status(args: argparse.Namespace) -> None:
    # CP-94: three states — ACTIVE (the lock is held: say wait), incomplete
    # (the record stopped short: the phases that stand, then the resume
    # cure) and complete (the standing report). The lock is read before the
    # record: during `up`'s first phase there is no run.json yet.
    r = Run(args.name)
    if lock_held(r):
        if (r.dir / "run.json").is_file():
            r.load()            # the record AND .env: the owner row reads the minted tokens
        status_active(args.name, r, r.record)
        return
    r = _load_run(args.name, r)
    rec = r.record
    if not all(rec.get(service) for service in ("forgejo", "mcp")):
        status_partial(args.name, r, rec)
    print(f"== run {args.name} == {r.dir}  (last run {rec.get('last_run', {}).get('at')}, "
          f"{rec.get('last_run', {}).get('mode')})")
    if (r.dir / "compose.yaml").is_file():
        ps = compose(r.dir, "ps", "--format", "table {{.Name}}\t{{.Status}}", capture_output=True)
        print(ps.stdout.rstrip() or "(nothing running)")
    print(_forgejo_status_line(rec.get("forgejo", {})))
    m = rec.get("mcp", {})
    hstat, h = http("GET", f"{m.get('url')}/health", timeout=3)
    h = h if isinstance(h, dict) else {}
    print(f"mcp      {m.get('mode'):8} {m.get('url')}  state={h.get('state', hstat)}  "
          f"embedding={(h.get('embedding') or {}).get('model')}  fingerprint="
          f"{str(h.get('fingerprint'))[:12]}…")
    e = rec.get("engine", {})
    probe = (probe_engine(e["url"], e.get("model", "")) if e.get("url")
             else {"reachable": False, "model_served": False})
    print(f"engine   operator {e.get('url')}  reachable={probe['reachable']}  "
          f"model_served={probe['model_served']}")
    ports = rec.get("ports", {})
    if rec.get("polar_leg") == "container":
        print(f"receiver :{ports.get('receiver')}  | rollout :{ports.get('rollout')}  | gateway "
              f":{ports.get('gateway')} — in your containers (--polar-leg container; not "
              f"probed from this host); gateway public URL http://{rec.get('gateway_host')}:"
              f"{ports.get('gateway')}")
    else:
        print(f"receiver 127.0.0.1:{ports.get('receiver')}  "
              f"{'listening' if port_busy(ports.get('receiver', 0)) else 'not listening'}"
              f"  | rollout 127.0.0.1:{ports.get('rollout')}  "
              f"{'listening' if port_busy(ports.get('rollout', 0)) else 'not listening'}")


@mutating_command
def cmd_down(args: argparse.Namespace) -> None:
    r = _command_run(args, args.name)  # a run that died before its record exists, or whose
    if not r.dir.is_dir():      # .env/run.json are gone, must still come down
        die(f"no run named {args.name!r}.", f"{r.dir} does not exist",
            "a run this script created", f"{PROG} up --name {args.name} (or --runs-dir "
            "naming the directory that holds it)")
    # Recovery cannot depend on a healthy record or .env. A damaged record
    # contributes no ownership claims; generated Compose still names this run.
    r.record = r.read_record(tolerant=True)
    if args.wipe:
        r.require_wipe_owned()
    composed = (r.dir / "compose.yaml").is_file()
    services = composed or bool(r.record.get("compose"))
    net = r.record.get("network", {})
    net = net if isinstance(net, dict) else {}
    own = f"gsj-{args.name}-net"
    external = net.get("external") or net.get("name", own) != own
    network = not external and (services or net.get("name") == own or
                                net.get("created_by_run") is True)

    if not composed and not r.record:
        cure = ("restore run.json from backup, then re-run down so its network ownership "
                "can be verified; preserve the run directory and inspect "
                f"`docker network inspect {own}` with the network's owner")
        if args.wipe:
            die(f"run {args.name!r}: network {own} is unverified; refusing --wipe.",
                "no usable run.json or generated compose.yaml establishes network ownership",
                "verified teardown before deleting the run directory", cure)
        warn("down", f"network {own} is unverified; {cure}")

    def failed(action: str, detail: str) -> None:
        die(f"run {args.name!r}: Docker cleanup failed or is unverified ({action}).",
            detail, "owned containers and network absent before success or --wipe",
            "inspect the Docker error above; restore daemon/socket access if unreachable, "
            "or fix the reported Compose configuration/resource error. "
            f"inspect `docker ps -a --filter label=com.docker.compose.project=gsj-{args.name}` "
            f"and `docker network inspect {own}`, then re-run down. "
            "Resolve any active network endpoints with their owner; run data was preserved.")

    def checked(cmd: list[str], action: str):
        proc = run(cmd, capture_output=True)
        if proc.returncode:
            failed(action, proc.stderr.strip() or f"docker exited {proc.returncode}")
        return proc

    if services or network:
        if not r.owned():
            die(f"run {args.name!r} has no matching estate ownership evidence.",
                str(r.dir), "this run's generated Compose or estate record/marker",
                "restore this run's generated files from backup before stopping services")
        if shutil.which("docker") is None:
            failed("docker is not on PATH", "Docker executable missing")
        if services:
            if composed and (r.dir / ".env").is_file():
                stopped = compose(r.dir, "down", "--remove-orphans", capture_output=True)
            else:   # project labels survive missing .env/Compose/record metadata
                stopped = run(["docker", "compose", "-p", f"gsj-{args.name}",
                               "down", "--remove-orphans"], capture_output=True)
            if stopped.returncode:
                failed("compose down", stopped.stderr.strip() or
                       f"docker compose exited {stopped.returncode}")
            remaining = checked(["docker", "ps", "-a", "--filter",
                                 f"label=com.docker.compose.project=gsj-{args.name}",
                                 "--format", "{{.Names}}"], "inspect owned containers")
            if remaining.stdout.strip():
                failed("owned containers remain", remaining.stdout.strip())
        if network:
            # Listing has an unambiguous successful-empty result; a failed
            # inspect alone cannot distinguish absence from an unavailable daemon.
            cmd = ["docker", "network", "ls", "--filter", f"name=^{own}$",
                   "--format", "{{.Name}}"]
            present = checked(cmd, "inspect owned network").stdout.splitlines()
            if own in present:
                checked(["docker", "network", "rm", own], "remove owned network")
                if own in checked(cmd, "verify removed network").stdout.splitlines():
                    failed("owned network remains", own)
                say("down", f"network {own} removed (this run's own)")
        say("down", f"created services stopped; owned resources absent "
                    f"(data under {r.dir} survives)")
    elif r.record:
        say("down", "this run records no owned Docker resources; nothing to stop")
    if args.wipe:
        r.require_wipe_owned()
        say("wipe", f"deleting {r.dir}")
        try:
            shutil.rmtree(r.dir)
        except PermissionError:
            removed = run(["docker", "run", "--rm", "-v", f"{r.dir}:/wipe", "alpine:latest",
                           "find", "/wipe", "-mindepth", "1", "-delete"], capture_output=True)
            if removed.returncode:
                die("wipe did not finish; some run data may have been removed.",
                    removed.stderr.strip() or f"docker exited {removed.returncode}",
                    "an absent run directory",
                    f"fix the Docker/filesystem error above under {r.dir}, then re-run down --wipe")
            try:
                r.dir.rmdir()
            except OSError as exc:
                die("wipe did not finish.", str(exc), "an absent run directory",
                    f"fix filesystem permissions under {r.dir} and re-run down --wipe")
        say("wipe", "done; the next `up` builds a fresh run")


# ------------------------------------------------------------------- main

def main() -> None:
    global RUNS
    # the docstring is the checkout's; from the wheel the same words name the
    # module and the cwd-relative runs directory (wishlist 51 (e))
    doc = (__doc__ if CHECKOUT else __doc__.replace("estate/estate.py", PROG)
           .replace("`estate/runs/<name>/`", "`./runs/<name>/` (--runs-dir)"))
    ap = argparse.ArgumentParser(description=doc,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--runs-dir", help=f"where runs live (default {RUNS}) — an EXISTING "
                                           "writable directory: the tool creates <name>/ "
                                           "beneath it, never the root itself")
    # CP-92 retired CP-73's six-verb metavar pin (wishlist row 60): argparse
    # renders the summary from the parsers below, so `update` cannot drop
    # out of it again; test_wheel_pipeline.py and the corpus suite both
    # assert the seven-verb brace.
    sub = ap.add_subparsers(dest="command", required=True)
    sc = sub.add_parser("scaffold", parents=[common],
                        help="write an annotated starting corpus that "
                             "validates as written (edit -> validate -> up)")
    sc.add_argument("--out", required=True,
                    help="directory to create (must be new or empty)")
    sc.set_defaults(func=cmd_scaffold)
    va = sub.add_parser("validate", parents=[common],
                        help="the contract check, tree only — the pipeline's "
                             "validate phase (CP-72: folded from "
                             "`python -m gsj_rollout.ingest_corpus validate`)")
    va.add_argument("--corpus", help="corpus root" + (" (default: estate/corpus/staging)"
                                                      if CHECKOUT else " (no default)"))
    va.add_argument("--only", nargs="+", metavar="CASE_ID",
                    help="limit the check to these cases")
    va.add_argument("--owner-override",
                    help="validate under this Forgejo owner instead of corpus.yaml's")
    va.add_argument("--sandbox-image",
                    help="the estate's harness image (a corpus.yaml sandbox_image "
                         "key is ignored since CP-71)")
    va.set_defaults(func=cmd_validate)
    up = sub.add_parser("up", parents=[common],
                        help="corpus -> running estate + taskbank + rollout.yaml")
    up.add_argument("--corpus", help="corpus root" + (" (default: estate/corpus/staging)"
                                                      if CHECKOUT else " (no default)"))
    up.add_argument("--name", help="run name -> <runs-dir>/<name>/ (default: the corpus name)")
    up.add_argument("--answers", help="YAML of answers, keyed by flag name (skips every prompt)")
    up.add_argument("-y", "--defaults", action="store_true",
                    help="no prompts: every unset value takes its default")
    up.add_argument("--owner", help="Forgejo owner (default: corpus.yaml's; "
                                    "any usable Forgejo username)")
    up.add_argument("--owner-mode", choices=("auto", "create", "existing"))
    up.add_argument("--overwrite-repos", action="store_true", default=None,
                    help="push over an existing owner's colliding repos (never the default)")
    up.add_argument("--network", help="docker network the sandbox joins (default: gsj-<name>-net, "
                                      "created; an existing name is used as external)")
    up.add_argument("--retarget", action="store_true", default=None,
                    help="let a re-run change the recorded estate identity (owner, URLs, "
                         "network, create/adopt) and print what changed")
    fg = up.add_argument_group("Forgejo")
    fg.add_argument("--forgejo", choices=("create", "adopt"))
    fg.add_argument("--forgejo-url", help="adopt: the instance, as this host reaches it")
    fg.add_argument("--forgejo-sandbox-url", help="adopt: the same instance as a sandbox reaches it "
                                                 "(default: localhost rewritten to host.docker.internal)")
    fg.add_argument("--forgejo-admin-user", help=f"adopt: admin username (default {ADMIN_USER})")
    fg.add_argument("--forgejo-admin-password-file",
                    help=f"adopt: file holding the admin password (or export {ADMIN_PASSWORD_ENV})")
    fg.add_argument("--forgejo-port", help="create: host port (default auto: 3000 upward)")
    fg.add_argument("--forgejo-image",
                    help=f"create: the image (default {FORGEJO_IMAGE}, measured 2026-08-30 as "
                         f"{FORGEJO_IMAGE_DIGEST[:19]}…; a re-run keeps its record's); any "
                         "pullable reference — another tag, the mirror "
                         f"{FORGEJO_IMAGE_MIRROR}:<tag>, or name@sha256:… to pin bytes")
    fg.add_argument("--anonymous-read", action="store_true", default=None,
                    help="create: leave REQUIRE_SIGNIN_VIEW off (an evaluation estate only)")
    mg = up.add_argument_group("retrieval service (MCP)")
    mg.add_argument("--mcp", choices=("create", "adopt"))
    mg.add_argument("--mcp-url", help="adopt: the service, as this host reaches it")
    mg.add_argument("--mcp-sandbox-url", help="adopt: the service as a sandbox reaches it")
    mg.add_argument("--mcp-secret-file", help=f"adopt: file holding its token secret (or export {MCP_SECRET_ENV})")
    mg.add_argument("--mcp-port", help="create: host port (default auto: 8790 upward)")
    mg.add_argument("--mcp-image", help=f"create: image (default {MCP_IMAGE}; a registry "
                                        "reference is pulled when absent, a local build tag "
                                        "must be present)")
    mg.add_argument("--embedding-model", help=f"HF id (default {DEFAULT_EMBEDDING_MODEL})")
    mg.add_argument("--embedding-revision", help="full commit SHA (default: the shipped MiniLM pin)")
    mg.add_argument("--hf-cache", help="create: a HuggingFace cache dir holding a non-default model")
    mg.add_argument("--chunk-max-tokens", type=int, help="create: chunking.max_tokens (default 220)")
    mg.add_argument("--chunk-overlap", type=int, help="create: chunking.overlap (default 40)")
    mg.add_argument("--decisions-dir",
                    help="create: OVERRIDE — a directory of rii-dok v1 decisions "
                         "(jb-<doknr>.xml, as published by rechtsprechung-im-internet.de) "
                         f"kept outside a corpus, mounted read-only at {MCP_DECISIONS_MOUNT} "
                         "— the decisions tool then serves Randnummern "
                         "(docs/decisions-surface.md, level 2). Absent: the corpus's own "
                         "decisions/ when it holds any (corpus-contract v3, CP-88), else the "
                         "synthetic 30; a corpus decisions/ AND this flag is refused. "
                         "Recorded; a re-run keeps it, '' removes it")
    mg.add_argument("--mcp-config",
                    help="create: YAML of retrieval-config overrides merged "
                         "onto the generated config — the operator sections "
                         f"only ({', '.join(MCP_OPERATOR_SECTIONS)}; schema: "
                         "estate/mcp-service/config.yaml). source/auth/index/"
                         "server are the run's wiring and are refused; the "
                         "effective config is printed for review before the "
                         "index is built under it")
    mg.add_argument("--rebuild", action="store_true", default=None,
                    help="create: re-embed the run's store under the requested model "
                         "(index.rebuild: always for one start)")
    mg.add_argument("--ingest-timeout", type=float, default=1800.0,
                    help="seconds each readiness wait may take, on this process's clock — the "
                         "bring-up's own wait for the service and the pipeline's wait after a "
                         "reindex both spend it; a suspended host does not (CP-96); a cold embed "
                         "of a decisions drop on a contended CPU host is minutes, not seconds "
                         "(default 1800)")
    eg = up.add_argument_group("engine and rollout config")
    eg.add_argument("--engine-url", help=f"the inference endpoint's root (default {DEFAULT_ENGINE_URL})")
    eg.add_argument("--engine-model", help=f"served model name (default {REFERENCE_MODEL})")
    eg.add_argument("--end-of-turn-token-id", type=int,
                    help="the served tokenizer's end-of-turn id, builder.end_of_turn_token_id "
                         "(default 151645, Qwen3's <|im_end|>; a re-run keeps its record's) — "
                         "for any other model measure it: bring-your-own.md#your-model")
    eg.add_argument("--context-window", type=int,
                    help="harness.context_window, the window pi plans against (default 32768; "
                         "must not exceed the endpoint's max_model_len)")
    eg.add_argument("--max-tokens", type=int,
                    help="harness.max_tokens, the per-turn generation budget (default 8192)")
    eg.add_argument("--thinking", help="pi thinking level (default off)")
    eg.add_argument("--gateway-host",
                    help="the address BOTH the host and sandboxes dial the gateway on "
                         "(default: probed — a dial from inside the run's retrieval container "
                         "to each of this host's addresses; explicit skips the probe; required "
                         "with --polar-leg container). How to choose one when the probe cannot "
                         "run: on Linux the compose network's gateway IP (`docker network "
                         "inspect gsj-<name>-net --format '{{(index .IPAM.Config 0).Gateway}}'`); "
                         "on Docker Desktop `host.docker.internal` after adding "
                         "`127.0.0.1 host.docker.internal` to /etc/hosts; verify with "
                         "`docker run --rm --network gsj-<name>-net alpine wget -qO- "
                         "http://<address>:<gateway port>/` while something listens there")
    eg.add_argument("--polar-leg", choices=("host", "container"),
                    help="where Polar's two processes and the receiver run (default host: "
                         "loopback binds, ports scanned free here; container: 0.0.0.0 binds, "
                         "the ports below unscanned, the public URLs and paths yours to "
                         "re-address — the closing block names the keys)")
    eg.add_argument("--rollout-port", help="default auto: 8080 upward (container leg: 8080)")
    eg.add_argument("--gateway-port", help="default auto: 8200 upward (container leg: 8200)")
    eg.add_argument("--receiver-port", help="default auto: 8300 upward (container leg: 8300)")
    eg.add_argument("--sandbox-image",
                    help="the harness image every episode runs in — rides "
                         "every task row and rollout.yaml's runtime.image "
                         f"(default: the run's record, else {ic.DEFAULT_SANDBOX_IMAGE}; "
                         "a corpus.yaml sandbox_image key is ignored since CP-71)")
    eg.add_argument("--skip-sandbox-image", action="store_true", default=None,
                    help="do not refuse when the sandbox image is absent (the gateway-host "
                         "probe no longer needs it — CP-96 — except with an ADOPTED retrieval "
                         "service, where the host is then written unmeasured; the sandbox "
                         "image is still needed before the first episode)")
    up.set_defaults(func=cmd_up)
    ig = sub.add_parser("ingest", parents=[common],
                        help="re-index the corpus into a standing retrieval "
                             "service — the pipeline's ingest phase (CP-72: "
                             "folded from `python -m gsj_rollout.ingest_corpus "
                             "ingest`)")
    ig.add_argument("--corpus", help="corpus root" + (" (default: estate/corpus/staging)"
                                                      if CHECKOUT else " (no default)"))
    ig.add_argument("--mcp-url", help="the retrieval service, as this host reaches it "
                                      "(default: corpus.yaml's deprecated mcp.url_base; "
                                      "neither named skips the re-index, loudly)")
    ig.add_argument("--ingest-timeout", type=float, default=900.0,
                    help="seconds the wait for /health ready may take, on this process's "
                         "clock (default 900)")
    ig.set_defaults(func=cmd_ingest)
    ud = sub.add_parser("update", parents=[common],
                        help="sync corpus EDITS into a standing estate: diff "
                             "the tree against the run's lock, report what "
                             "moved and what it costs, then push only the "
                             "changed repos, rebuild the bank, reindex "
                             "(if-stale — never a forced re-embed) and "
                             "verify (CP-73)")
    ud.add_argument("--name", required=True, help="the run to sync into")
    ud.add_argument("--corpus", help="corpus root (default: the run record's)")
    ud.add_argument("-y", "--defaults", action="store_true",
                    help="no confirm: report the plan, then act")
    ud.add_argument("--dry-run", action="store_true",
                    help="the local diff report only — touch nothing, ask nothing")
    ud.add_argument("--ingest-timeout", type=float, default=1800.0,
                    help="seconds each readiness wait may take, on this process's clock "
                         "(default 1800)")
    ud.set_defaults(func=cmd_update)
    st = sub.add_parser("status", parents=[common], help="what stands for a run")
    st.add_argument("--name", required=True)
    st.set_defaults(func=cmd_status)
    dn = sub.add_parser("down", parents=[common],
                        help="stop the services a run created (data survives)")
    dn.add_argument("--name", required=True)
    dn.add_argument("--wipe", action="store_true", help="also delete <runs-dir>/<name>/ after "
                    "verified teardown and matching estate ownership evidence; .locks/ survives")
    dn.set_defaults(func=cmd_down)
    args = ap.parse_args()
    if args.runs_dir:
        RUNS = Path(args.runs_dir).expanduser().resolve()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nestate: interrupted — re-run the verb; every phase is idempotent", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
