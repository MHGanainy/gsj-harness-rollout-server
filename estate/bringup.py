#!/usr/bin/env python3
"""estate/bringup.py — corpus to estate, in one command (CP-59).

    estate/bringup.py up   [--corpus DIR] [--name RUN] [flags…]   # the estate
    estate/bringup.py status --name RUN                          # what stands
    estate/bringup.py down   --name RUN [--wipe]                 # stop what it created

Given a corpus in the contract's shape (docs/corpus-contract.md) this
script leaves behind a running estate — a git host holding one repository
per case, a retrieval service indexing them — plus the task table and the
one YAML the rollout server reads, under `estate/runs/<name>/`:

    rollout.yaml       the rollout server's config, validated (topology rendered)
    taskbank.parquet   the task table, with corpus.lock.json beside it
    run.json           the record: created vs adopted, every URL, the owner,
                       the embedding identity, the engine probe, timestamps —
                       it NAMES variables, never values
    .env               every secret, KEY=value, mode 0600 — source it, or
                       point compose at it; nothing is exported on a command line

It is the production sibling of gsj-rollout-demo's bootstrap.py: that one
always CREATES its estate; this one also ADOPTS an existing Forgejo or
retrieval service, probing what it did not build before touching it.
Running it twice on the same corpus and name REUSES (tokens verified,
repos converged, index fingerprint matched); `--rebuild` re-embeds
explicitly — the retrieval service's own posture (CP-57), not a second one.

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
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("bringup: PyYAML is missing — it rides the library install:\n"
          "  pip install -e '.[dev]'   (from the checkout root)", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent           # estate/
REPO = HERE.parent
RUNS = HERE / "runs"
INGEST = HERE / "corpus" / "ingest_corpus.py"
sys.path.insert(0, str(HERE / "corpus"))
import ingest_corpus as ic  # noqa: E402  — the pipeline, as a library

SCHEMA = 1
FORGEJO_IMAGE = "codeberg.org/forgejo/forgejo:16.0.2"
MCP_IMAGE = "gsj-mcp-service:0.4.0"       # CP-58: the store identity + the read credential
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
REFERENCE_MODEL = "Qwen/Qwen3-0.6B"
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
    print(f"[bringup +{time.monotonic() - _T0:6.1f}s] {_c('1', phase)} — {msg}",
          flush=True)


def warn(phase: str, msg: str) -> None:
    print(f"[bringup +{time.monotonic() - _T0:6.1f}s] {_c('33', phase)} — "
          f"{_c('33', 'WARNING')}: {msg}", flush=True)


def die(what: str, found: str | None, expected: str | None, fix: str) -> "None":
    """Every refusal: what it found, what it expected, what to do (CP-27)."""
    print(f"\nbringup: {_c('31', 'REFUSED')} — {what}", file=sys.stderr)
    if found is not None:
        print(f"  found:    {found}", file=sys.stderr)
    if expected is not None:
        print(f"  expected: {expected}", file=sys.stderr)
    print(f"  what to do: {fix}", file=sys.stderr, flush=True)
    sys.exit(1)


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


def script_version() -> dict:
    head = run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
               capture_output=True)
    dirty = run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                 "estate/bringup.py"], capture_output=True)
    try:
        import gsj_rollout
        lib = gsj_rollout.__version__
    except ImportError:
        lib = None
    return {"script": "estate/bringup.py",
            "commit": (head.stdout.strip() if head.returncode == 0 else None),
            "dirty": bool(dirty.stdout.strip()),
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
            return os.environ[env]
        path = getattr(self.args, file_key, None) or self.file.get(file_key)
        if path:
            try:
                value = Path(path).read_text().strip()
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
            return value
        if fallback:
            return fallback
        if self.interactive:
            value = getpass.getpass(f"{_c('36', '?')} {question} (not echoed): ").strip()
            if value:
                return value
        return None


# ------------------------------------------------------------- the corpus

def load_corpus(path: Path, owner_override: str | None):
    """validate — the contract, before anything runs; the Corpus object."""
    if not (path / "corpus.yaml").is_file():
        die(f"{path} is not a corpus root.", "no corpus.yaml there",
            "a tree in docs/corpus-contract.md's shape",
            "point --corpus at the corpus root (the directory holding "
            "corpus.yaml, AGENTS.md, skills/, train/ and/or eval/)")
    try:
        corpus = ic.phase_validate(path, owner_override=owner_override, quiet=False)
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
    with tempfile.TemporaryDirectory(prefix="gsj-bringup-build-") as tmp:
        return {case_id: ic.build_case_repo(corpus, case, Path(tmp), env)
                for case_id, case in sorted(corpus.cases.items())}


def pins_g1_check(corpus) -> dict:
    """Which of this corpus's skill cards the packaged approved set (G1)
    already carries — episodes on the others quarantine until the pins
    walk re-derives (pins/derive_pins.py); a warning, not a refusal."""
    try:
        from importlib.util import find_spec
        pins = REPO / "pins" / "pins.gsj.json"          # the checkout's source set
        if not pins.is_file():                          # an installed wheel's copy
            pins = Path(find_spec("gsj_rollout").origin).parent / "pins" / "pins.gsj.json"
        approved = set(json.loads(pins.read_text())["pins"]["skill_card_hash"])
    except Exception:  # noqa: BLE001 — a probe, not a gate
        return {"checked": False}
    cards = {name: sha256_file(card) for name, card in sorted(corpus.skills.items())}
    missing = sorted(n for n, h in cards.items() if h not in approved)
    return {"checked": True, "cards": len(cards), "not_in_packaged_pins": missing}


# ------------------------------------------------------------ the run dir

def _env_quote(value: str) -> str:
    """Single-quoted, `'` as `'\\''` — read back identically by POSIX `.` and
    by compose's dotenv parser; no metacharacter is live."""
    return "'" + value.replace("'", "'\\''") + "'"


def _env_unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("'\\''", "'")
    return raw


class Run:
    def __init__(self, name: str) -> None:
        self.name = name
        self.dir = RUNS / name
        self.env: dict[str, str] = {}
        self.record: dict = {}
        self.existing = False

    def load(self) -> None:
        rec = self.dir / "run.json"
        envf = self.dir / ".env"
        if rec.is_file():
            try:
                self.record = json.loads(rec.read_text())
            except ValueError as exc:
                die(f"{rec} is not valid JSON.", str(exc), "the record this "
                    "script wrote", "restore it from backup, or pick another "
                    "--name; never hand-edit run.json")
            self.existing = True
            if not envf.is_file():
                names = sorted(self.record.get("secrets", {}).get("names", []))
                die(f"run '{self.name}' exists but its .env is missing.",
                    f"{rec} present, {envf} absent",
                    f"{envf} holding {', '.join(names) or 'the run secrets'}",
                    "restore .env from your backup — re-minting would "
                    "silently invalidate the running retrieval service's "
                    "secret and every token the record names; or start "
                    "over: `estate/bringup.py down --name "
                    f"{self.name} --wipe` then `up`")
        if envf.is_file():
            for line in envf.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    self.env[k.strip()] = _env_unquote(v.strip())

    def write_env(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.dir.chmod(0o700)
        envf = self.dir / ".env"
        body = ("# estate/runs/%s/.env — every secret of this run, KEY='value'.\n"
                "# Source it (set -a; . %s; set +a) or point compose at it\n"
                "# (--env-file). Never commit; never paste values on a command line.\n"
                % (self.name, envf))
        for k, v in sorted(self.env.items()):
            if "\n" in v or "\r" in v:
                die(f"the value of {k} contains a newline.", "a multi-line secret",
                    "one line — .env is KEY='value' per line", f"give {k} a one-line value")
            body += f"{k}={_env_quote(v)}\n"
        fd = os.open(envf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 0600 from birth
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        envf.chmod(0o600)

    def write_record(self) -> None:
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
        tmp = self.dir / "run.json.tmp"       # atomic: never a half-written record
        tmp.write_text(text)
        os.replace(tmp, self.dir / "run.json")


# ---------------------------------------------------------------- docker

def check_docker() -> None:
    if shutil.which("docker") is None:
        die("`docker` is not on PATH.", None, "Docker with the compose v2 plugin",
            "install Docker (https://docs.docker.com/engine/install/) or "
            "adopt existing services instead of creating them")
    probe = run(["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True)
    if probe.returncode != 0:
        die("the Docker daemon is not reachable.",
            (probe.stderr.strip().splitlines() or ["nothing"])[-1],
            "a running daemon", "start Docker (or fix socket permissions), then re-run")
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


def compose(rundir: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return run(["docker", "compose", "-f", str(rundir / "compose.yaml"),
                "--env-file", str(rundir / ".env"), *args], **kw)


COMPOSE_HEAD = """\
# GENERATED by estate/bringup.py for run {run} — do not edit; re-run `up`.
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
{hf_mount}    restart: unless-stopped
"""

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
        name = f"bringup-{label}-{int(time.time())}"
        status, body = self.api("POST", f"/users/{owner}/tokens",
                                {"name": name, "scopes": scopes}, auth=self.admin)
        if status not in (200, 201) or not isinstance(body, dict) or "sha1" not in body:
            die(f"could not mint the {label} token for {owner!r}.",
                f"POST /users/{owner}/tokens -> {status} {body}", "201 with sha1",
                "the admin must authenticate with its PASSWORD (basic auth); "
                "Forgejo refuses token-for-others under token auth")
        return body["sha1"]


def create_forgejo(rundir: Path, run: Run, port: int, signin: bool,
                   network: str, external_net: bool) -> Forgejo:
    container = f"gsj-{run.name}-forgejo"
    uid = os.getuid() if platform.system() == "Linux" else 1000
    gid = os.getgid() if platform.system() == "Linux" else 1000
    (rundir / "forgejo-data").mkdir(exist_ok=True)
    run.record.setdefault("compose", {})["forgejo"] = {
        "image": FORGEJO_IMAGE, "container": container, "port": port,
        "data": str(rundir / "forgejo-data"), "signin": signin, "uid": uid, "gid": gid}
    write_compose(rundir, run, network, external_net)
    PH.start("forgejo", f"docker compose up ({container}, 127.0.0.1:{port}, "
                        f"sign-in {'ON' if signin else 'OFF'} from the first start)")
    if compose(rundir, "up", "-d", "forgejo").returncode != 0:
        die("`docker compose up forgejo` failed.", "the compose error above",
            None, f"if the pull failed and this host cannot reach registries, "
                  f"load {FORGEJO_IMAGE} out-of-band (docker save/load) and re-run")
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120
    while time.time() < deadline:
        if http("GET", f"{url}/api/healthz", timeout=3)[0] == 200:
            break
        time.sleep(2)
    else:
        die("Forgejo did not answer /api/healthz within 120 s.", None, None,
            f"docker logs {container}; the first start initialises the "
            f"instance — re-run once it settles")
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
        run.env[ADMIN_PASSWORD_ENV] = m.group(1)
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
    PH.done(f"healthy at {url} (containers: {fj.container_url}); "
            f"sign-in {'ON' if fj.signin else 'OFF'}")
    return fj


def write_compose(rundir: Path, run: Run, network: str, external_net: bool) -> None:
    parts = [COMPOSE_HEAD.format(run=run.name, project=f"gsj-{run.name}")]
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
        user = f'    user: "{cm["uid"]}:{cm["gid"]}"\n' if cm.get("uid") is not None else ""
        parts.append(COMPOSE_MCP.format(
            image=cm["image"], container=cm["container"], port=cm["port"],
            data=cm["data"], config=cm["config"], secret_env=MCP_SECRET_ENV,
            read_env=cm["read_env"], hf_mount=hf_mount, user=user))
    parts.append((COMPOSE_NET_EXT if external_net else COMPOSE_NET_OWN)
                 .format(network=network))
    (rundir / "compose.yaml").write_text("".join(parts))


# ------------------------------------------------------------------- mcp

MCP_CONFIG = """\
# GENERATED by estate/bringup.py for run {run} — do not edit; re-run `up`.
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


class Mcp:
    def __init__(self, url: str, container_url: str, secret: str, mode: str) -> None:
        self.url = url.rstrip("/")
        self.container_url = container_url.rstrip("/")
        self.secret = secret
        self.mode = mode

    def health(self) -> dict | None:
        status, body = http("GET", f"{self.url}/health", timeout=5)
        return body if status == 200 and isinstance(body, dict) else None

    def wait_ready(self, timeout_s: float, what: str,
                   container: str | None = None) -> dict:
        deadline = time.time() + timeout_s
        last = None
        silent_since = None
        while time.time() < deadline:
            h = self.health()
            if h is None:
                line = "unreachable"
                silent_since = silent_since or time.time()
                if container and time.time() - silent_since > 20:
                    # a service that stops answering is not "still indexing":
                    # read the container's own tail once before waiting on
                    # (measured at CP-59: the amd64 image under qemu on an
                    # arm64 daemon segfaults at the embed step and the
                    # container stays "running" with a dead process)
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
                            "(`docker build --platform linux/<arch> -t gsj-mcp-service:0.4.0-<arch> "
                            "estate/mcp-service`) and pass it with --mcp-image; production "
                            "is amd64 and runs the shipped image as is")
            else:
                silent_since = None
                prog = h.get("progress") or {}
                fetched = sum(1 for p in prog.values() if p.get("done"))
                embedded = sum(1 for p in prog.values() if p.get("embedded"))
                line = (f"{h.get('state')}: {fetched}/{len(prog)} cases fetched, "
                        f"{embedded}/{len(prog)} embedded")
            if line != last:
                say("mcp", f"{what}: {line}")
                last = line
            if h and h.get("state") == "ready":
                return h
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
        die(f"the retrieval service did not reach state=ready within {timeout_s:.0f} s.",
            last, "state=ready", "large corpora embed for a while on cpu — "
            "re-run to keep waiting (the index survives), or --ingest-timeout")

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


def gateway_host(network: str, gport: int, explicit: str | None,
                 probe_image: str | None, recorded: str | None = None) -> tuple[str, str, list]:
    """ONE address reachable from host dispatch AND from inside episode
    containers (CP-03 finding 2) — MEASURED, not assumed: a listener on
    the gateway port, and a container on the run's network dialing every
    candidate; the first that answers wins (the host reaches its own
    interface IPs trivially). Measured at CP-59 on a Docker Desktop Mac: the
    LAN interface was host-only, host.docker.internal container-only, and a
    VPN interface the one address both could dial — no heuristic knows that.
    Candidates: the compose network's gateway IP (Linux — the H200's answer),
    then every host IPv4."""
    if explicit:
        return explicit, "--gateway-host (not probed)", []
    candidates: list[str] = []
    if platform.system() == "Linux" and shutil.which("docker"):
        proc = run(["docker", "network", "inspect", network, "--format",
                    "{{(index .IPAM.Config 0).Gateway}}"], capture_output=True)
        if proc.returncode == 0 and proc.stdout.strip():
            candidates.append(proc.stdout.strip())
    if recorded and recorded not in candidates:
        candidates.append(recorded)     # the run's last measured answer, re-measured
    candidates += [ip for ip in host_ipv4s() if ip not in candidates]
    try:                                # Docker Desktop with the /etc/hosts line:
        socket.gethostbyname("host.docker.internal")   # both sides dial the name
        candidates.insert(0, "host.docker.internal")
    except OSError:
        pass
    results: list = []
    if probe_image and candidates and shutil.which("docker"):
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
        js = ("const c=%s;(async()=>{for(const h of c){try{const r=await fetch("
              "'http://'+h+':%d/',{signal:AbortSignal.timeout(3000)});"
              "console.log(h,'OK',r.status)}catch(e){console.log(h,'FAIL')}}})()"
              % (json.dumps(candidates), gport))
        proc = run(["docker", "run", "--rm", "--network", network, probe_image,
                    "node", "-e", js], capture_output=True, timeout=120)
        if server:
            server.shutdown()
            server.server_close()
        if proc.returncode != 0 and not proc.stdout.strip():
            die(f"the gateway-host probe container could not run on network {network!r}.",
                (proc.stderr.strip().splitlines() or ["no output"])[-1],
                "a container on the sandbox's network dialing this host",
                "the network must exist (a created run makes its own; an adopted-only "
                "run creates or verifies it); --gateway-host <address> skips the probe")
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in candidates:
                results.append({"candidate": parts[0], "reachable": parts[1] == "OK"})
        for r in results:
            if r["reachable"]:
                return r["candidate"], ("measured: dialable from a container on "
                                        f"{network!r} and from this host"), results
        die(f"no host address is dialable from a container on {network!r}.",
            f"tried {candidates} — every one timed out from the container",
            "ONE address the rollout API (host) and the sandbox both dial (CP-03)",
            "on Docker Desktop add `127.0.0.1 host.docker.internal` to /etc/hosts and "
            "pass --gateway-host host.docker.internal; on Linux the compose network's "
            "gateway IP usually works; --gateway-host <address> writes it unprobed")
    elif candidates:
        warn("config", "no image to probe from (the sandbox image is absent) — the "
             "gateway host is the first host IPv4, unmeasured; pass --gateway-host "
             "if a sandbox cannot dial it")
    if candidates:
        return candidates[0], "first host IPv4 (UNMEASURED)", results
    return "127.0.0.1", "fallback — 127.0.0.1 is NOT reachable from a sandbox", results


# ------------------------------------------------------------- the estate

def cmd_up(args: argparse.Namespace) -> None:
    A = Answers(args)
    try:
        import pyarrow  # noqa: F401 — the taskbank's writer (ADR-0022 §5)
    except ImportError:
        die("pyarrow is not importable from this python.", sys.executable,
            "the taskbank phase's parquet writer",
            "pip install -r estate/corpus/requirements.txt  (same environment)")
    try:
        import gsj_rollout  # noqa: F401
    except ImportError:
        die("the gsj_rollout library is not importable from this python.",
            sys.executable, "the checkout's venv (pip install -e '.[dev]')",
            "run this script with the checkout's python")
    if shutil.which("git") is None:
        die("`git` is not on PATH.", None, None, "install git")

    # ---- the corpus, validated before anything runs
    corpus_path = Path(A.get("corpus", "corpus root", str(HERE / "corpus" / "staging"))).expanduser().resolve()
    if not (corpus_path / "corpus.yaml").is_file():
        load_corpus(corpus_path, None)          # the refusal, before any prompt
    try:
        raw_yaml = yaml.safe_load((corpus_path / "corpus.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw_yaml = {}
    yaml_owner = raw_yaml.get("owner") if isinstance(raw_yaml.get("owner"), str) else None
    yaml_name = raw_yaml.get("name") if isinstance(raw_yaml.get("name"), str) else None

    # ---- the run: its record is the source of every re-run default
    name = A.get("name", "run name", yaml_name, required=True)
    if not RUN_NAME_RE.match(name):
        die(f"run name {name!r} is not a token.", repr(name),
            "lowercase letters, digits, - and _ (it names a compose project)", "--name")
    run_ = Run(name)
    run_.load()
    rundir = run_.dir
    rundir.mkdir(parents=True, exist_ok=True)
    rundir.chmod(0o700)   # the whole run is the operator's: .env, and the MCP's
    # clone cache, whose cold `clone --bare` writes the read token into
    # <case>.git/config (wishlist 47 — frozen-side; measured here at CP-59)
    run_.write_env()      # compose wants its --env-file to exist from the first `up`
    rec = run_.record
    prev = dict(rec) if run_.existing else {}
    if run_.existing:
        say("run", f"'{name}' exists (created {rec.get('created_at')}) — "
                   f"re-run: adopting what stands, backfilling what is missing")
    owner = A.get("owner", "Forgejo owner for the case repos",
                  prev.get("corpus", {}).get("owner") or yaml_owner)
    corpus = load_corpus(corpus_path, owner if owner != yaml_owner else None)
    owner = corpus.owner
    case_ids = sorted(corpus.cases)
    push_env, read_env = ic.token_env_name(owner), ic.read_token_env_name(owner)
    say("corpus", f"{corpus.name}: {len(case_ids)} case(s) {case_ids}; owner {owner!r}; "
                  f"sandbox image {corpus.sandbox_image}")
    rec.update({"run": name, "run_dir": str(rundir), "version": script_version(),
                "corpus": {"path": str(corpus_path), "name": corpus.name,
                           "owner": owner, "case_ids": case_ids,
                           "sandbox_image": corpus.sandbox_image,
                           "yaml_forgejo_base_url": corpus.base_url,
                           "yaml_mcp_url_base": corpus.mcp_url}})
    reused: list[str] = []
    backfilled: list[str] = []
    network = A.get("network", "docker network the sandbox joins",
                    prev.get("network", {}).get("name", f"gsj-{name}-net"))
    external_net = network != f"gsj-{name}-net"
    rec["network"] = {"name": network, "external": external_net,
                      "created_by_run": prev.get("network", {}).get("created_by_run", False)}
    changed: list[str] = []

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

    # ---- Forgejo
    def _choice(section: str) -> str:   # the record says created/adopted
        return "adopt" if prev.get(section, {}).get("mode") == "adopted" else "create"

    fmode = A.get("forgejo", "Forgejo: create a new instance, or adopt one",
                  _choice("forgejo"), choices=("create", "adopt"))
    if fmode == "adopt" and prev.get("forgejo", {}).get("mode") == "created":
        retarget("Forgejo", "created", "adopted")
    if fmode == "adopt":
        furl = bare_url(A.get("forgejo_url", "Forgejo URL (as this host reaches it)",
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
        if prev.get("compose", {}).get("forgejo"):
            reused.append(f"forgejo container gsj-{name}-forgejo (compose up -d is idempotent)")
        fj = create_forgejo(rundir, run_, fport, signin, network, external_net)
    rec["forgejo"] = {"mode": fj.mode, "url": fj.url, "container_url": fj.container_url,
                      "admin_user": fj.admin[0], "admin_credential_env": ADMIN_PASSWORD_ENV,
                      "require_signin_view": fj.signin}

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
        pw = secrets.token_urlsafe(18)
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
    if corpus.base_url != fj.container_url:
        say("corpus", f"corpus.yaml names forgejo.base_url {corpus.base_url} — the lock "
                      f"keeps that canonical URL; this estate is reached at {fj.url} "
                      f"(transport override) and by sandboxes at {fj.container_url}")

    def pipeline(phase: str, *extra: str, mcp_url: str | None = None) -> None:
        cmd = [sys.executable, str(INGEST), phase, "--corpus", str(corpus_path),
               "--base-url", fj.url, "--ingest-timeout", str(args.ingest_timeout)]
        if mcp_url:
            cmd += ["--mcp-url", mcp_url]
        if owner != yaml_owner:
            cmd += ["--owner-override", owner]
        cmd += list(extra)
        PH.start(phase, f"estate/corpus/ingest_corpus.py {phase}")
        penv = {**os.environ, **{k: v for k, v in run_.env.items()
                                 if k in (push_env, read_env, MCP_SECRET_ENV)}}
        proc = run(cmd, env=penv)
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
    mmode = A.get("mcp", "retrieval service (MCP): create, or adopt",
                  _choice("mcp"), choices=("create", "adopt"))
    if prev.get("mcp", {}).get("mode") in ("created", "adopted") and \
            prev["mcp"]["mode"] != ("created" if mmode == "create" else "adopted"):
        retarget("the retrieval service", prev["mcp"]["mode"],
                 "created" if mmode == "create" else "adopted")
    model = A.get("embedding_model", "embedding model (HF id)",
                  prev.get("mcp", {}).get("embedding", {}).get("model") or DEFAULT_EMBEDDING_MODEL)
    revision = A.get("embedding_revision", "embedding revision (full commit SHA)",
                     prev.get("mcp", {}).get("embedding", {}).get("revision")
                     if prev.get("mcp", {}).get("embedding", {}).get("model") == model
                     else (DEFAULT_EMBEDDING_REVISION if model == DEFAULT_EMBEDDING_MODEL else None),
                     required=True)
    if not HEX40.match(str(revision)):
        die(f"embedding revision {revision!r} is not a full commit SHA.", repr(revision),
            "40 hex characters (a branch or tag can move under the index — the "
            "service refuses it too)", "--embedding-revision <sha>")
    secret = None
    if mmode == "adopt":
        murl = bare_url(A.get("mcp_url", "MCP URL (as this host reaches it)",
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
        image_default = pm["image"] if pm else MCP_IMAGE
        if not pm and daemon_arch() in ("arm64", "aarch64") and \
                image_present(f"{MCP_IMAGE}-{daemon_arch()}"):
            image_default = f"{MCP_IMAGE}-{daemon_arch()}"     # the native build, if present
            say("mcp", f"this daemon is {daemon_arch()}: defaulting to the native image "
                       f"{image_default} (the amd64 one dies under qemu — wishlist 49)")
        image = A.get("mcp_image", "retrieval service image", image_default)
        if pm and image != pm["image"]:
            changed.append(f"the retrieval service image: {pm['image']!r} -> {image!r}")
        if not image_present(image):
            arch = daemon_arch()
            die(f"the retrieval service image {image} is not present on this daemon.",
                "docker image inspect failed", "the image loaded",
                "build it from estate/mcp-service/ (`DOCKER_DEFAULT_PLATFORM=linux/amd64 "
                f"docker build -t {image} estate/mcp-service`), or `docker load` the "
                f"tarball the estate ships; --mcp-image names another"
                + (" (this daemon is arm64: an amd64 image runs under emulation)"
                   if arch in ("arm64", "aarch64") else ""))
        secret = run_.env.get(MCP_SECRET_ENV)
        if secret:
            reused.append(f"MCP token secret ({MCP_SECRET_ENV})")
        else:
            secret = secrets.token_hex(32)
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
        chunk_max = int(A.get("chunk_max_tokens", None, chunk_prev.get("max_tokens", 220)))
        chunk_overlap = int(A.get("chunk_overlap", None, chunk_prev.get("overlap", 40)))
        if chunk_prev and (chunk_max, chunk_overlap) != (chunk_prev["max_tokens"], chunk_prev["overlap"]):
            changed.append(f"chunking: {chunk_prev} -> {{'max_tokens': {chunk_max}, 'overlap': {chunk_overlap}}}")
        cfg.write_text(MCP_CONFIG.format(
            run=name, forgejo_url=fj.container_url, owner=owner,
            repos=", ".join(case_ids), read_env=read_env, model=model,
            revision=revision, chunk_max=chunk_max, chunk_overlap=chunk_overlap,
            rebuild="always" if rebuild else "if-stale", secret_env=MCP_SECRET_ENV))
        rec.setdefault("compose", {})["mcp"] = {
            "image": image, "container": container, "port": mport,
            "data": str(rundir / "mcp-data"), "config": str(cfg), "read_env": read_env,
            "hf_model_dir": str(hf_dir) if hf_dir else None,
            "hf_model_mount": f"/opt/hf-cache/hub/{hf_dir.name}" if hf_dir else None,
            "chunking": {"max_tokens": chunk_max, "overlap": chunk_overlap},
            "uid": os.getuid() if platform.system() == "Linux" else None,
            "gid": os.getgid() if platform.system() == "Linux" else None}
        write_compose(rundir, run_, network, external_net)
        PH.start("mcp", f"docker compose up ({container}, 127.0.0.1:{mport}) — a cold "
                        f"start clones and embeds; a warm one matches the fingerprint")
        # compose recreates on a changed service definition (image, env,
        # ports) by itself; a changed MOUNTED config or --rebuild is read only
        # at start, so those force the recreate — an untouched run is a no-op
        recreate = rebuild or (cfg_before is not None and cfg_before != sha256_file(cfg))
        up = compose(rundir, "up", "-d", *(["--force-recreate"] if recreate else []), "mcp")
        if up.returncode != 0:
            die("`docker compose up mcp` failed.", "the compose error above", None,
                "the error is authoritative; the container keeps its creation-time "
                "env, so a rotated token needs this recreate (done here)")
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
        PH.done(f"ready at {mcp.url} (containers: {mcp.container_url}); fingerprint "
                f"{str(h.get('fingerprint'))[:12]}…; index_reused={h.get('index_reused')}")
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
    lock = ic.load_lock(corpus_path, required=True)
    rec["corpus"].update({"lock_sha256": sha256_file(rundir / ic.LOCK_NAME),
                          "taskbank_sha256": bank_sha,
                          "taskbank_rows": (lock.get("taskbank") or {}).get("rows"),
                          "repos": {cid: lock["cases"][cid]["refs"] for cid in case_ids}})

    # ---- the engine: always the operator's, never created
    eurl = A.get("engine_url", "inference endpoint (root URL, no /v1)",
                 prev.get("engine", {}).get("url", DEFAULT_ENGINE_URL)).rstrip("/")
    if eurl.endswith("/v1"):
        die("the engine URL must not end in /v1.", eurl, "the root — Polar's proxy "
            "appends /v1/chat/completions itself", f"--engine-url {eurl[:-3]}")
    emodel = A.get("engine_model", "served model name (as GET /v1/models lists it)",
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
             "otherwise — derive it from the served tokenizer (docs/MODEL-SURFACE.md "
             "in the demo repo owns the recipe)")

    # ---- the sandbox image, present or named
    if not A.get("skip_sandbox_image", None, False):
        if shutil.which("docker") and image_present(corpus.sandbox_image):
            say("sandbox", f"{corpus.sandbox_image} present — episodes run in it")
            rec["corpus"]["sandbox_image_present"] = True
        else:
            hint = (" --platform linux/amd64" if shutil.which("docker")
                    and daemon_arch() in ("arm64", "aarch64") else "")
            die(f"the sandbox image {corpus.sandbox_image} is not present on this daemon.",
                "docker image inspect failed (or no docker here)",
                "the image every task row names (corpus.yaml sandbox_image)",
                f"docker pull{hint} {corpus.sandbox_image}   — or load it out-of-band; "
                "--skip-sandbox-image records the absence and continues")
    else:
        rec["corpus"]["sandbox_image_present"] = (shutil.which("docker") is not None
                                                  and image_present(corpus.sandbox_image))

    # ---- pins: which skill cards the packaged approved set already carries
    g1 = pins_g1_check(corpus)
    rec["pins"] = g1
    if g1.get("checked") and g1["not_in_packaged_pins"]:
        warn("pins", f"{len(g1['not_in_packaged_pins'])}/{g1['cards']} skill card(s) are not "
             f"in the packaged approved set (G1): {g1['not_in_packaged_pins']} — episodes "
             "on them quarantine until the pins walk re-derives (pins/derive_pins.py); "
             "this script does not write pins")

    # ---- rollout.yaml — the config the rollout server needs
    PH.start("config", "rollout.yaml")
    pp = prev.get("ports", {})
    rport = pick_port(A.get("rollout_port", None, pp.get("rollout", "auto")), 8080,
                      "--rollout-port", check="rollout" not in pp)
    gport = pick_port(A.get("gateway_port", None, pp.get("gateway", "auto")), 8200,
                      "--gateway-port", check="gateway" not in pp)
    xport = pick_port(A.get("receiver_port", None, pp.get("receiver", "auto")), 8300,
                      "--receiver-port", check="receiver" not in pp)
    probe_image = (corpus.sandbox_image if rec["corpus"].get("sandbox_image_present")
                   else None)
    ghost, ghow, gprobe = gateway_host(network, gport, A.get("gateway_host", None, None),
                                       probe_image, prev.get("gateway_host"))
    if prev.get("gateway_host") and prev["gateway_host"] != ghost:
        changed.append(f"the gateway host: {prev['gateway_host']!r} -> {ghost!r} ({ghow})")
    rec["ports"] = {"rollout": rport, "gateway": gport, "receiver": xport}
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
        "polar": {"rollout": {"host": "127.0.0.1", "port": rport},
                  "gateway": {"id": f"gsj-{name}", "host": "0.0.0.0", "port": gport,
                              "public_url": f"http://{ghost}:{gport}", "engine": "vllm"}},
        "receiver": {"host": "127.0.0.1", "port": xport, "traces_dir": str(rundir / "traces")},
    }
    if eot is not None:
        cfg["builder"] = {"end_of_turn_token_id": int(eot)}
    rec["harness"] = {**cfg["harness"], "end_of_turn_token_id": eot}
    for key in ("context_window", "max_tokens", "thinking", "end_of_turn_token_id"):
        if hp and key in hp and hp[key] != rec["harness"].get(key):
            changed.append(f"harness.{key}: {hp[key]!r} -> {rec['harness'].get(key)!r}")
    head = (f"# GENERATED by estate/bringup.py for run {name} — do not edit (run.json dates it);\n"
            f"# re-run `estate/bringup.py up --name {name}`. Schema: gsj_rollout/config.py\n"
            f"# (the one YAML). Secrets are named by variable and live in {rundir / '.env'}:\n"
            f"# source it before `gsj-rollout serve|submit` and Polar's serve_gateway.\n"
            f"# Sandbox-side addresses ({fj.container_url}, {mcp.container_url}) resolve on\n"
            f"# the docker network {network!r}; host-side ones ({fj.url}, {mcp.url}) are\n"
            f"# recorded in run.json.\n")
    ry = rundir / "rollout.yaml"
    ry.write_text(head + yaml.safe_dump(cfg, sort_keys=False))
    render = run([sys.executable, "-m", "gsj_rollout.cli", "serve", "--config", str(ry),
                  "--render-only"], capture_output=True)
    if render.returncode != 0:
        die("the library rejected the generated rollout.yaml.", render.stderr.strip() or render.stdout,
            "a config load_config accepts", "this is a bringup bug — report it with the output")
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
    polar = REPO / "vendor" / "polar" / ".venv" / "bin" / "polar"
    gsjr = Path(sys.executable).parent / "gsj-rollout"
    gsjr_cmd = str(gsjr) if gsjr.exists() else f"{sys.executable} -m gsj_rollout.cli"
    print(f"""
== run {name} == {rel}/
  rollout.yaml       the rollout server's config (validated; topology.rendered.yaml beside it)
  taskbank.parquet   {rec['corpus'].get('taskbank_rows')} rows, sha256 {bank_sha[:12]}…; corpus.lock.json beside it
  run.json           the record — {fj.mode} Forgejo {fj.url}, {mcp.mode} MCP {mcp.url}, owner {owner!r},
                     embedding {(h.get('embedding') or {}).get('model')}, engine {eurl} ({'ok' if probe['model_served'] else 'NOT OK'})
  .env               {len(run_.env)} secret(s), mode 0600 — the only place a value lives

next — the receiver and Polar's two processes, on this host (three terminals; each sources .env first):
  set -a; . {rel}/.env; set +a
  {gsjr_cmd} serve --config {rel}/rollout.yaml
  PYTHONPATH={REPO} {polar} serve_rollout -c {rel}/topology.rendered.yaml
  PYTHONPATH={REPO} {polar} serve_gateway -c {rel}/topology.rendered.yaml
then one episode (the config's whole claim):
  {gsjr_cmd} submit --config {rel}/rollout.yaml --from-bank {rel}/taskbank.parquet --row 0
what stands / stop what this run created:
  estate/bringup.py status --name {name}    |    estate/bringup.py down --name {name} [--wipe]""")


# ------------------------------------------------------- status and down

def _load_run(name: str) -> Run:
    r = Run(name)
    if not (r.dir / "run.json").is_file():
        die(f"no run named {name!r}.", f"{r.dir} has no run.json",
            "a run this script created", "estate/bringup.py up --name " + name)
    r.load()
    return r


def cmd_status(args: argparse.Namespace) -> None:
    r = _load_run(args.name)
    rec = r.record
    print(f"== run {args.name} == {r.dir}  (last run {rec.get('last_run', {}).get('at')}, "
          f"{rec.get('last_run', {}).get('mode')})")
    if (r.dir / "compose.yaml").is_file():
        ps = compose(r.dir, "ps", "--format", "table {{.Name}}\t{{.Status}}", capture_output=True)
        print(ps.stdout.rstrip() or "(nothing running)")
    fj = rec.get("forgejo", {})
    status, _ = http("GET", f"{fj.get('url')}/api/healthz", timeout=3)
    vstat, _ = http("GET", f"{fj.get('url')}/api/v1/version", timeout=3)
    print(f"forgejo  {fj.get('mode'):8} {fj.get('url')}  healthz={status}  "
          f"sign-in={'ON' if vstat == 403 else 'OFF' if vstat == 200 else '?'}  owner {fj.get('owner')!r}")
    m = rec.get("mcp", {})
    hstat, h = http("GET", f"{m.get('url')}/health", timeout=3)
    h = h if isinstance(h, dict) else {}
    print(f"mcp      {m.get('mode'):8} {m.get('url')}  state={h.get('state', hstat)}  "
          f"embedding={(h.get('embedding') or {}).get('model')}  fingerprint="
          f"{str(h.get('fingerprint'))[:12]}…")
    e = rec.get("engine", {})
    probe = probe_engine(e.get("url", ""), e.get("model", ""))
    print(f"engine   operator {e.get('url')}  reachable={probe['reachable']}  "
          f"model_served={probe['model_served']}")
    print(f"receiver 127.0.0.1:{rec.get('ports', {}).get('receiver')}  "
          f"{'listening' if port_busy(rec.get('ports', {}).get('receiver', 0)) else 'not listening'}"
          f"  | rollout 127.0.0.1:{rec.get('ports', {}).get('rollout')}  "
          f"{'listening' if port_busy(rec.get('ports', {}).get('rollout', 0)) else 'not listening'}")


def cmd_down(args: argparse.Namespace) -> None:
    r = Run(args.name)          # a run that died before its record exists, or whose
    if not r.dir.is_dir():      # .env/run.json are gone, must still come down
        die(f"no run named {args.name!r}.", f"{r.dir} does not exist",
            "a run this script created", "estate/bringup.py up --name " + args.name)
    try:
        r.record = json.loads((r.dir / "run.json").read_text())
    except (OSError, ValueError):
        r.record = {}
    if (r.dir / "compose.yaml").is_file():
        if shutil.which("docker") is None:
            die("`docker` is not on PATH.", None, None, "install docker to stop the services")
        if (r.dir / ".env").is_file():
            compose(r.dir, "down", "--remove-orphans")
        else:   # compose interpolates ${VAR:?} even on down: the project-name form needs no file
            run(["docker", "compose", "-p", f"gsj-{args.name}", "down", "--remove-orphans"])
        say("down", f"created services stopped (data under {r.dir} survives)")
    else:
        say("down", "this run created no services; nothing to stop")
    net = r.record.get("network", {})
    own = f"gsj-{args.name}-net"    # the run's own network name: also what a run
    # that died before its record could have created (and never recorded)
    if shutil.which("docker") and not (r.dir / "compose.yaml").is_file() and (
            net.get("created_by_run") or (net.get("name", own) == own and
                                          run(["docker", "network", "inspect", own],
                                              capture_output=True).returncode == 0)):
        gone = run(["docker", "network", "rm", net.get("name", own)], capture_output=True)
        if gone.returncode == 0:
            say("down", f"network {net.get('name', own)} removed (this run's own)")
    if args.wipe:
        say("wipe", f"deleting {r.dir}")
        try:
            shutil.rmtree(r.dir)
        except PermissionError:
            run(["docker", "run", "--rm", "-v", f"{r.dir}:/wipe", "alpine:latest",
                 "sh", "-c", "rm -rf /wipe/* /wipe/.[!.]* 2>/dev/null || true"])
            shutil.rmtree(r.dir, ignore_errors=True)
        say("wipe", "done; the next `up` builds a fresh run")


# ------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    up = sub.add_parser("up", help="corpus -> running estate + taskbank + rollout.yaml")
    up.add_argument("--corpus", help="corpus root (default: estate/corpus/staging)")
    up.add_argument("--name", help="run name -> estate/runs/<name>/ (default: the corpus name)")
    up.add_argument("--answers", help="YAML of answers, keyed by flag name (skips every prompt)")
    up.add_argument("-y", "--defaults", action="store_true",
                    help="no prompts: every unset value takes its default")
    up.add_argument("--owner", help="Forgejo owner (default: corpus.yaml's; gsj-staging|gsj-prod)")
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
    fg.add_argument("--anonymous-read", action="store_true", default=None,
                    help="create: leave REQUIRE_SIGNIN_VIEW off (an evaluation estate only)")
    mg = up.add_argument_group("retrieval service (MCP)")
    mg.add_argument("--mcp", choices=("create", "adopt"))
    mg.add_argument("--mcp-url", help="adopt: the service, as this host reaches it")
    mg.add_argument("--mcp-sandbox-url", help="adopt: the service as a sandbox reaches it")
    mg.add_argument("--mcp-secret-file", help=f"adopt: file holding its token secret (or export {MCP_SECRET_ENV})")
    mg.add_argument("--mcp-port", help="create: host port (default auto: 8790 upward)")
    mg.add_argument("--mcp-image", help=f"create: image (default {MCP_IMAGE})")
    mg.add_argument("--embedding-model", help=f"HF id (default {DEFAULT_EMBEDDING_MODEL})")
    mg.add_argument("--embedding-revision", help="full commit SHA (default: the shipped MiniLM pin)")
    mg.add_argument("--hf-cache", help="create: a HuggingFace cache dir holding a non-default model")
    mg.add_argument("--chunk-max-tokens", type=int, help="create: chunking.max_tokens (default 220)")
    mg.add_argument("--chunk-overlap", type=int, help="create: chunking.overlap (default 40)")
    mg.add_argument("--rebuild", action="store_true", default=None,
                    help="create: re-embed the run's store under the requested model "
                         "(index.rebuild: always for one start)")
    mg.add_argument("--ingest-timeout", type=float, default=1800.0,
                    help="seconds to wait for the index (default 1800)")
    eg = up.add_argument_group("engine and rollout config")
    eg.add_argument("--engine-url", help=f"the inference endpoint's root (default {DEFAULT_ENGINE_URL})")
    eg.add_argument("--engine-model", help=f"served model name (default {REFERENCE_MODEL})")
    eg.add_argument("--end-of-turn-token-id", type=int)
    eg.add_argument("--context-window", type=int)
    eg.add_argument("--max-tokens", type=int)
    eg.add_argument("--thinking", help="pi thinking level (default off)")
    eg.add_argument("--gateway-host", help="the address BOTH the host and sandboxes dial the gateway on")
    eg.add_argument("--rollout-port", help="default auto: 8080 upward")
    eg.add_argument("--gateway-port", help="default auto: 8200 upward")
    eg.add_argument("--receiver-port", help="default auto: 8300 upward")
    eg.add_argument("--skip-sandbox-image", action="store_true", default=None,
                    help="do not refuse when the sandbox image is absent")
    up.set_defaults(func=cmd_up)
    st = sub.add_parser("status", help="what stands for a run")
    st.add_argument("--name", required=True)
    st.set_defaults(func=cmd_status)
    dn = sub.add_parser("down", help="stop the services a run created (data survives)")
    dn.add_argument("--name", required=True)
    dn.add_argument("--wipe", action="store_true", help="also delete estate/runs/<name>/")
    dn.set_defaults(func=cmd_down)
    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nbringup: interrupted — re-run `up`; every phase is idempotent", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
