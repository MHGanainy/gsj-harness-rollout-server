#!/usr/bin/env python3
"""The corpus ingestion pipeline (CP-33, ADR-0047).

One entry, five phases run as subcommands — ``validate`` → ``scaffold`` →
``ingest`` → ``taskbank`` → ``verify`` — plus ``all`` running them in order,
stopping at the first failure:

    validate   the source tree against docs/corpus-contract.md (the input;
               contract v2 since CP-14 — the train/eval split is the
               directory layout, ADR-0015)
    scaffold   deterministic case repos, pushed to Forgejo under `owner`
    ingest     trigger the MCP service reindex (POST /admin/reindex), wait ready
    taskbank   one row per (case, timestep, prompt) into taskbank.parquet
               (ADR-0022; split case-level from the lock, ADR-0015), its
               sha256 recorded in the lock
    verify     clone everything BACK from the git host, check the parquet's
               sha256 AND its rows against the tree, query the service —
               reality must match the tree and the lock

Pre-validation checks the input; post-verification checks reality.

The pipeline touches the environment through git + HTTP only. Credentials
come from environment variables named by the contract (never from files):
``GSJ_FORGEJO_TOKEN_<OWNER>`` (owner uppercased, ``-`` → ``_``) for pushes,
``GSJ_MCP_TOKEN_SECRET`` for the reindex trigger. ``file://`` base URLs are
a first-class rail (local bare estates for tests and rehearsals): no API,
no token — repos are bare-initialized under ``<path>/<owner>/``.

Determinism: commit identity + dates are fixed in corpus.yaml (the CP-02
recipe), so an unchanged tree reproduces identical commit SHAs on every
branch of every repo; pushes are ``--force --prune`` and converge.

The predecessor's taskbank library API (``CaseSpec``, ``PromptSpec``,
``build_taskbank``, ``write_taskbank``) is deliberately NOT a dependency of
this repo (ADR-0002, upheld when the ADR-0003 deferral resolved at CP-24):
the bank is built HERE, in the ADR-0022 row shape, with pyarrow — the one
dependency beyond PyYAML, recorded in ``corpus/requirements.txt`` and
imported lazily: validate/scaffold/ingest run without it (taskbank and
verify's row half need it).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# --------------------------------------------------------------------------
# Contract constants (docs/corpus-contract.md; ADR-0046)

OWNERS = ("gsj-staging", "gsj-prod")
CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TIMESTEP_DIR_RE = re.compile(r"^timestep-([1-9][0-9]*)$")
PAGE_FILE_RE = re.compile(r"^page_(\d{4})\.md$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # skill names / free slugs

# ADR-0006: task-written session files never dirty tracked state.
CASE_GITIGNORE = ".pi/\nout/*\n!out/.gitkeep\n"

LOCK_NAME = "corpus.lock.json"
TASKBANK_NAME = "taskbank.parquet"

CORPUS_YAML_KEYS = {"name", "owner", "forgejo", "mcp", "git", "sandbox_image"}
GIT_KEYS = {"name", "email", "date"}

# ADR-0015: exactly these two splits; a third needs its own ADR.
SPLITS = ("train", "eval")
RETIRED_EVAL_KEY_MSG = (
    "'eval_case_ids' is retired (ADR-0015) — the split is now the directory "
    "layout: move each listed case under <corpus-root>/eval/cases/, every "
    "other case under <corpus-root>/train/cases/, then delete this key")
PRE_SPLIT_CASES_MSG = (
    "cases/ at the corpus root is the retired pre-split shape (ADR-0015) — "
    "move each case under train/cases/ or eval/cases/")


def token_env_name(owner: str) -> str:
    return "GSJ_FORGEJO_TOKEN_" + owner.upper().replace("-", "_")


class PipelineError(Exception):
    """Usage/environment failure (exit 2) — distinct from a FAIL finding."""


# --------------------------------------------------------------------------
# The source-tree model

@dataclass(frozen=True)
class PromptEntry:
    id: str
    source: str          # "skill" | "free"
    name: str            # skill name or free slug (the id's suffix)
    text: str | None     # free text; None for skill entries


@dataclass
class TimestepTree:
    t: int
    dir: Path
    pages: dict[int, Path] = field(default_factory=dict)
    prompts: list[PromptEntry] = field(default_factory=list)


@dataclass
class CaseTree:
    case_id: str
    dir: Path
    split: str  # "train" | "eval" — the case's directory placement (ADR-0015)
    timesteps: dict[int, TimestepTree] = field(default_factory=dict)

    @property
    def max_t(self) -> int:
        return max(self.timesteps)


@dataclass
class Corpus:
    root: Path
    name: str
    owner: str
    base_url: str
    mcp_url: str | None
    git_identity: dict[str, str]
    sandbox_image: str
    agents_md: Path
    skills: dict[str, Path]          # skill name -> SKILL.md
    cases: dict[str, CaseTree] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    scope: str      # case id or "(corpus)"
    where: str      # timestep-N / repo / a corpus-level check name
    ok: bool
    detail: str
    split: str = "-"  # train | eval | "-" for corpus-level rows (ADR-0015)


def _read_utf8(path: Path) -> str | None:
    """Text of *path*, or None if it is not valid UTF-8."""
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Phase: validate

def load_corpus(root: Path, findings: list[Finding],
                owner_override: str | None = None) -> Corpus | None:
    """Parse + validate corpus.yaml and the corpus-level files. Returns None
    (with findings) when the corpus level is too broken to continue."""
    def fail(where: str, detail: str) -> None:
        findings.append(Finding("(corpus)", where, False, detail))

    yaml_path = root / "corpus.yaml"
    if not yaml_path.is_file():
        fail("corpus.yaml", "missing")
        return None
    text = _read_utf8(yaml_path)
    if text is None:
        fail("corpus.yaml", "not valid UTF-8")
        return None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        fail("corpus.yaml", f"invalid YAML — {error}")
        return None
    if not isinstance(raw, dict):
        fail("corpus.yaml", "top level must be a mapping")
        return None

    ok = True
    if "eval_case_ids" in raw:  # rejected by name, never silently ignored
        fail("corpus.yaml", RETIRED_EVAL_KEY_MSG)
        ok = False
    unknown = sorted(set(raw) - CORPUS_YAML_KEYS - {"eval_case_ids"})
    if unknown:
        fail("corpus.yaml", f"unknown keys {unknown}")
        ok = False
    for key in ("name", "owner", "sandbox_image"):
        if not isinstance(raw.get(key), str) or not raw.get(key):
            fail("corpus.yaml", f"{key!r} must be a non-empty string")
            ok = False
    name = raw.get("name", "")
    if isinstance(name, str) and name and not TOKEN_RE.match(name):
        fail("corpus.yaml", f"name {name!r} not a token (letters, digits, ._-)")
        ok = False
    owner = raw.get("owner", "")
    if isinstance(owner, str) and owner and owner not in OWNERS:
        fail("corpus.yaml",
             f"owner {owner!r} must be one of {list(OWNERS)}")
        ok = False
    forgejo = raw.get("forgejo")
    base_url = ""
    if not isinstance(forgejo, dict) or set(forgejo) != {"base_url"} \
            or not isinstance(forgejo.get("base_url"), str) or not forgejo["base_url"]:
        fail("corpus.yaml", "forgejo must be a mapping with exactly 'base_url'")
        ok = False
    else:
        base_url = forgejo["base_url"].rstrip("/")
    mcp_url: str | None = None
    if "mcp" in raw:
        mcp = raw["mcp"]
        if not isinstance(mcp, dict) or set(mcp) != {"url_base"} \
                or not isinstance(mcp.get("url_base"), str) or not mcp["url_base"]:
            fail("corpus.yaml", "mcp must be a mapping with exactly 'url_base'")
            ok = False
        else:
            mcp_url = mcp["url_base"].rstrip("/")
    git_identity = raw.get("git")
    if not isinstance(git_identity, dict) or set(git_identity) != GIT_KEYS \
            or not all(isinstance(git_identity.get(k), str) and git_identity[k]
                       for k in GIT_KEYS):
        fail("corpus.yaml",
             "git must be a mapping with exactly 'name', 'email', 'date' "
             "(non-empty strings)")
        ok = False
    agents_md = root / "AGENTS.md"
    if not agents_md.is_file():
        fail("AGENTS.md", "missing at corpus root")
        ok = False
    elif _read_utf8(agents_md) in (None, ""):
        fail("AGENTS.md", "empty or not valid UTF-8")
        ok = False

    skills: dict[str, Path] = {}
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        fail("skills/", "missing at corpus root (may be empty, must exist)")
        ok = False
    else:
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                fail("skills/", f"unexpected entry {entry.name!r} "
                     f"(only skills/<name>/SKILL.md is allowed)")
                ok = False
                continue
            if not TOKEN_RE.match(entry.name):
                fail("skills/", f"skill name {entry.name!r} not a token")
                ok = False
                continue
            card = entry / "SKILL.md"
            if not card.is_file():
                fail("skills/", f"{entry.name}: SKILL.md missing")
                ok = False
                continue
            if _read_utf8(card) in (None, ""):
                fail("skills/", f"{entry.name}/SKILL.md empty or not valid UTF-8")
                ok = False
                continue
            skills[entry.name] = card

    if not ok:
        return None
    return Corpus(root=root, name=name,
                  owner=owner_override or owner, base_url=base_url,
                  mcp_url=mcp_url, git_identity=dict(git_identity),
                  sandbox_image=raw["sandbox_image"], agents_md=agents_md,
                  skills=skills)


def _validate_prompts_yaml(path: Path, skills: dict[str, Path],
                           fail) -> list[PromptEntry]:
    """Contract rule 4. Returns the entries (possibly empty); failures via
    the ``fail`` callback."""
    if not path.is_file():
        return []  # absent = no rows at this timestep (legal)
    text = _read_utf8(path)
    if text is None:
        fail("prompts.yaml not valid UTF-8")
        return []
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        fail(f"prompts.yaml invalid YAML — {error}")
        return []
    if raw is None:
        return []  # empty file = no rows (legal)
    if not isinstance(raw, dict) or set(raw) != {"prompts"} \
            or not isinstance(raw["prompts"], list):
        fail("prompts.yaml must be a mapping with exactly the key 'prompts' "
             "(a list)")
        return []

    entries: list[PromptEntry] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw["prompts"]):
        label = f"prompts[{i}]"
        if not isinstance(item, dict):
            fail(f"{label}: must be a mapping")
            continue
        source = item.get("source")
        if source not in ("skill", "free"):
            fail(f"{label}: source must be 'skill' or 'free', got {source!r}")
            continue
        expected_keys = {"id", "source", "name"} if source == "skill" \
            else {"id", "source", "text"}
        if set(item) != expected_keys:
            fail(f"{label}: keys must be exactly {sorted(expected_keys)} "
                 f"for source={source!r}, got {sorted(item)}")
            continue
        pid = item.get("id")
        if not isinstance(pid, str) or not pid:
            fail(f"{label}: id must be a non-empty string")
            continue
        if source == "skill":
            skill_name = item.get("name")
            if not isinstance(skill_name, str) or not TOKEN_RE.match(skill_name):
                fail(f"{label}: name {skill_name!r} not a token")
                continue
            if pid != f"skill:{skill_name}":
                fail(f"{label}: id must be 'skill:{skill_name}', got {pid!r}")
                continue
            if skill_name not in skills:
                fail(f"{label}: unresolvable skill {skill_name!r} — no "
                     f"skills/{skill_name}/SKILL.md in this corpus")
                continue
            entry = PromptEntry(pid, "skill", skill_name, None)
        else:
            free_text = item.get("text")
            if not isinstance(free_text, str) or not free_text:
                fail(f"{label}: text must be a non-empty string")
                continue
            slug = pid.removeprefix("free:")
            if slug == pid or not TOKEN_RE.match(slug):
                fail(f"{label}: id must be 'free:<slug>' with a token slug, "
                     f"got {pid!r}")
                continue
            entry = PromptEntry(pid, "free", slug, free_text)
        if entry.id in seen_ids:
            fail(f"{label}: duplicate prompt id {entry.id!r} within this "
                 f"timestep")
            continue
        seen_ids.add(entry.id)
        entries.append(entry)
    return entries


def validate_case(case_dir: Path, split: str, skills: dict[str, Path],
                  findings: list[Finding]) -> CaseTree | None:
    case_id = case_dir.name
    case = CaseTree(case_id=case_id, dir=case_dir, split=split)
    ok = True

    def fail(where: str, detail: str) -> None:
        nonlocal ok
        findings.append(Finding(case_id, where, False, detail, split))
        ok = False

    if not CASE_ID_RE.match(case_id):
        fail("(case)", f"case id {case_id!r} does not match "
             f"{CASE_ID_RE.pattern} (it becomes a repo name)")
        return None

    # Strict tree: only case.yaml + timestep-<T>/ under a case directory.
    for entry in sorted(case_dir.iterdir()):
        if entry.name == "case.yaml" and entry.is_file():
            text = _read_utf8(entry)
            if text is None:
                fail("case.yaml", "not valid UTF-8")
                continue
            try:
                meta = yaml.safe_load(text)
            except yaml.YAMLError as error:
                fail("case.yaml", f"invalid YAML — {error}")
                continue
            if meta is not None:
                if not isinstance(meta, dict) or \
                        not set(meta) <= {"title", "notes"} or \
                        not all(isinstance(v, str) for v in meta.values()):
                    fail("case.yaml", "must be a mapping with keys from "
                         "{'title', 'notes'} (string values)")
            continue
        match = TIMESTEP_DIR_RE.match(entry.name)
        if match and entry.is_dir():
            case.timesteps[int(match.group(1))] = TimestepTree(
                t=int(match.group(1)), dir=entry)
            continue
        fail("(case)", f"unexpected entry {entry.name!r} — only case.yaml and "
             f"timestep-<T>/ (integer T, no leading zeros) are allowed")

    if not case.timesteps:
        fail("(case)", "no timestep-<T>/ directories")
        return None

    for t in sorted(case.timesteps):
        ts = case.timesteps[t]
        where = f"timestep-{t}"
        ts_ok = True

        def tfail(detail: str, _where: str = where) -> None:
            nonlocal ts_ok
            findings.append(Finding(case_id, _where, False, detail, split))
            ts_ok = False

        # Strict tree: only pages/ + prompts.yaml under a timestep directory.
        for entry in sorted(ts.dir.iterdir()):
            if entry.name == "pages" and entry.is_dir():
                continue
            if entry.name == "prompts.yaml" and entry.is_file():
                continue
            tfail(f"unexpected entry {entry.name!r} — only pages/ and "
                  f"prompts.yaml are allowed")

        pages_dir = ts.dir / "pages"
        if not pages_dir.is_dir():
            tfail("pages/ missing")
        else:
            for entry in sorted(pages_dir.iterdir()):
                match = PAGE_FILE_RE.match(entry.name)
                if not match or not entry.is_file():
                    tfail(f"unexpected entry pages/{entry.name!r} — only "
                          f"page_<NNNN>.md (4-digit) is allowed")
                    continue
                page = int(match.group(1))
                if _read_utf8(entry) is None:
                    tfail(f"pages/{entry.name} not valid UTF-8")
                    continue
                ts.pages[page] = entry
            expected = list(range(1, t + 1))
            if sorted(ts.pages) != expected:
                missing = sorted(set(expected) - set(ts.pages))
                extra = sorted(set(ts.pages) - set(expected))
                parts = []
                if missing:
                    parts.append(f"missing pages {missing}")
                if extra:
                    parts.append(f"pages beyond the cutoff {extra}")
                tfail(f"page census must be exactly 1..{t} (absolute "
                      f"numbering): " + "; ".join(parts))

        ts.prompts = _validate_prompts_yaml(ts.dir / "prompts.yaml", skills,
                                            tfail)
        if ts_ok:
            findings.append(Finding(
                case_id, where, True,
                f"{len(ts.pages)} pages, {len(ts.prompts)} prompts", split))

    # Prefix consistency (contract rule 3): consecutive timesteps compared
    # pairwise; transitivity covers every pair.
    steps = sorted(case.timesteps)
    for t1, t2 in zip(steps, steps[1:]):
        low, high = case.timesteps[t1], case.timesteps[t2]
        for page in sorted(low.pages):
            if page not in high.pages:
                continue  # census failure already reported above
            h_low = _sha256_file(low.pages[page])
            h_high = _sha256_file(high.pages[page])
            if h_low != h_high:
                fail(f"timestep-{t2}",
                     f"prefix divergence on page {page}: byte-identical "
                     f"pages required across timesteps — "
                     f"timestep-{t1}/pages/page_{page:04d}.md sha256 "
                     f"{h_low[:16]}… != timestep-{t2}'s {h_high[:16]}…")

    return case if ok else None


def phase_validate(root: Path, only: list[str] | None = None,
                   owner_override: str | None = None,
                   quiet: bool = False) -> Corpus | None:
    """The full contract. Prints the findings table; returns the parsed
    corpus when everything passed, else None."""
    findings: list[Finding] = []
    corpus = load_corpus(root, findings, owner_override)

    # The corpus root is strict for visible entries (ADR-0015): a
    # `test/cases/` tree must fail loudly, never silently vanish.
    # Dot-entries are ignored at the root only (a source tree may be a
    # git repo); everywhere below, the tree stays strict. Deliberately
    # independent of corpus.yaml parsing, so an unmigrated v1 tree
    # surfaces BOTH migration messages in one run.
    root_names = {"corpus.yaml", "AGENTS.md", "skills",
                  LOCK_NAME, TASKBANK_NAME, *SPLITS}
    for entry in sorted(root.iterdir()):
        if entry.name in root_names or entry.name.startswith("."):
            # A reserved NAME with the wrong TYPE must not fall through:
            # a stray file named `train` would otherwise silently vanish
            # the whole split (split selection is is_dir()-filtered).
            if entry.name in SPLITS and not entry.is_dir():
                findings.append(Finding(
                    "(corpus)", f"{entry.name}", False,
                    f"{entry.name!r} at the corpus root must be a "
                    f"directory (the {entry.name} split), not a file"))
            elif entry.name in (LOCK_NAME, TASKBANK_NAME) and entry.is_dir():
                findings.append(Finding(
                    "(corpus)", entry.name, False,
                    f"{entry.name!r} must be a generated file, not a "
                    f"directory"))
            continue
        if entry.name == "cases" and entry.is_dir():
            findings.append(Finding("(corpus)", "cases/", False,
                                    PRE_SPLIT_CASES_MSG))
            continue
        findings.append(Finding(
            "(corpus)", "(root)", False,
            f"unexpected entry {entry.name!r} — the corpus root allows "
            f"only corpus.yaml, AGENTS.md, skills/, train/, eval/ and "
            f"the generated {LOCK_NAME}/{TASKBANK_NAME}; a third split "
            f"needs its own ADR (ADR-0015)"))

    if corpus is not None:
        split_dirs = [s for s in SPLITS if (root / s).is_dir()]
        if not split_dirs:
            findings.append(Finding(
                "(corpus)", "train/eval", False,
                "no split directories — at least one of train/cases/ or "
                "eval/cases/ must exist (ADR-0015)"))
        case_dirs: list[tuple[str, Path]] = []
        for split in split_dirs:
            for entry in sorted((root / split).iterdir()):
                if entry.name == "cases" and entry.is_dir():
                    continue
                findings.append(Finding(
                    "(corpus)", f"{split}/", False,
                    f"unexpected entry {entry.name!r} — only cases/ is "
                    f"allowed under a split directory", split))
            cases_dir = root / split / "cases"
            if not cases_dir.is_dir():
                findings.append(Finding("(corpus)", f"{split}/cases/", False,
                                        "missing", split))
                continue
            for entry in sorted(cases_dir.iterdir()):
                if entry.is_dir():
                    case_dirs.append((split, entry))
                else:
                    findings.append(Finding(
                        "(corpus)", f"{split}/cases/", False,
                        f"unexpected file {entry.name!r} — only case "
                        f"directories are allowed", split))
        if split_dirs and not case_dirs:
            findings.append(Finding(
                "(corpus)", "cases", False,
                "no case directories under train/cases/ or eval/cases/"))
        if only:
            known = {e.name for _, e in case_dirs}
            unknown = sorted(set(only) - known)
            # Only a usage error on a structurally sound tree: with tree
            # findings pending, fall through so the table (and the
            # ADR-0015 migration messages) print instead of exit 2.
            if unknown and not any(not f.ok for f in findings):
                raise PipelineError(f"--only names unknown cases {unknown} "
                                    f"(have {sorted(known)})")
        membership: dict[str, str] = {}
        for split, entry in case_dirs:
            if entry.name in membership:  # ADR-0015: exactly one split
                findings.append(Finding(
                    entry.name, "(case)", False,
                    f"case {entry.name!r} present under both train/cases/ "
                    f"and eval/cases/ — a case belongs to exactly one split "
                    f"(ADR-0015); remove one", split))
                corpus.cases.pop(entry.name, None)
                continue
            membership[entry.name] = split
            if only and entry.name not in only:
                continue
            case = validate_case(entry, split, corpus.skills, findings)
            if case is not None:
                corpus.cases[case.case_id] = case

    failed = [f for f in findings if not f.ok]
    if not quiet or failed:
        _print_table("validate", findings)
    if failed or corpus is None:
        return None
    return corpus


def _print_table(title: str, findings: list[Finding]) -> None:
    rows = [(f.scope, f.split, f.where, "PASS" if f.ok else "FAIL", f.detail)
            for f in findings]
    if not rows:
        rows = [("(corpus)", "-", "-", "PASS", "nothing to check")]
    header = ("case", "split", "where", "result")
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(4)]
    print(f"== {title} ==")
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)) + "  detail")
    for row in rows:
        print("  ".join(v.ljust(w) for v, w in zip(row[:4], widths))
              + f"  {row[4]}")
    n_fail = sum(1 for r in rows if r[3] == "FAIL")
    print(f"== {title}: {'FAIL' if n_fail else 'PASS'} "
          f"({len(rows) - n_fail} pass / {n_fail} fail) ==")


# --------------------------------------------------------------------------
# Git plumbing (the CP-02 deterministic recipe)

def git_env(identity: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": identity["name"],
        "GIT_AUTHOR_EMAIL": identity["email"],
        "GIT_COMMITTER_NAME": identity["name"],
        "GIT_COMMITTER_EMAIL": identity["email"],
        "GIT_AUTHOR_DATE": identity["date"],
        "GIT_COMMITTER_DATE": identity["date"],
        "GIT_CONFIG_GLOBAL": os.devnull,   # user/system config must not
        "GIT_CONFIG_SYSTEM": os.devnull,   # influence SHAs (signing, eol, …)
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def git(cwd: Path, *args: str, env: dict[str, str],
        redact: str | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), "-c", "commit.gpgsign=false",
         "-c", "core.autocrlf=false", *args],
        env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        message = f"git {' '.join(args)} in {cwd} failed:\n{proc.stderr}"
        if redact:
            message = message.replace(redact, "***")
        raise PipelineError(message)
    return proc.stdout


def build_case_repo(corpus: Corpus, case: CaseTree, dest: Path,
                    env: dict[str, str]) -> dict[str, str]:
    """Build the ADR-0006-shaped repo for one case under *dest*; returns
    branch -> sha. Deterministic: fixed identity/dates, fixed messages,
    branches constructed main-first then truncated per cutoff (equivalent to
    copying each timestep directory — validated by contract rule 3, asserted
    against the source by verify)."""
    repo = dest / case.case_id
    git(dest, "init", "-q", "-b", "main", case.case_id, env=env)

    largest = case.timesteps[case.max_t]
    (repo / "AGENTS.md").write_bytes(corpus.agents_md.read_bytes())
    (repo / ".gitignore").write_text(CASE_GITIGNORE, encoding="utf-8")
    for skill_name, card in sorted(corpus.skills.items()):
        skill_dir = repo / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_bytes(card.read_bytes())
    (repo / "out").mkdir()
    (repo / "out" / ".gitkeep").write_text("", encoding="utf-8")
    md = repo / "md"
    md.mkdir()
    for page, path in sorted(largest.pages.items()):
        (md / f"page_{page:04d}.md").write_bytes(path.read_bytes())

    pages = case.max_t
    git(repo, "add", "-A", env=env)
    git(repo, "commit", "-q", "-m",
        f"{case.case_id}: full document ({pages} pages)", env=env)

    heads = {}
    for t in sorted(case.timesteps):
        branch = f"timestep-{t}"
        git(repo, "checkout", "-q", "-b", branch, "main", env=env)
        doomed = [f"md/page_{p:04d}.md" for p in range(t + 1, pages + 1)]
        if doomed:
            git(repo, "rm", "-q", "--", *doomed, env=env)
            git(repo, "commit", "-q", "-m",
                f"{branch}: truncate after page {t}", env=env)
        else:  # cutoff == full document: keep the one-commit-per-branch shape
            git(repo, "commit", "-q", "--allow-empty", "-m",
                f"{branch}: truncate after page {t} (no pages beyond cutoff)",
                env=env)
    git(repo, "checkout", "-q", "main", env=env)

    for branch in ["main"] + [f"timestep-{t}" for t in sorted(case.timesteps)]:
        heads[branch] = git(repo, "rev-parse", branch, env=env).strip()
    return heads


# --------------------------------------------------------------------------
# Forgejo (HTTP API) / local-bare (file://) remotes

def _is_file_url(base_url: str) -> bool:
    return base_url.startswith("file://")


def clone_url(base_url: str, owner: str, case_id: str) -> str:
    return f"{base_url}/{owner}/{case_id}.git"


def _api(base_url: str, token: str, method: str, path: str,
         payload: dict | None = None) -> tuple[int, dict | None]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{base_url}/api/v1{path}", data=body, method=method,
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        return error.code, None
    except urllib.error.URLError as error:
        raise PipelineError(
            f"Forgejo API unreachable at {base_url}: {error.reason}") from None


def resolve_push_auth(corpus: Corpus, base_url: str) -> str | None:
    """The push token for http(s) remotes, from the contract's env var —
    file:// remotes need none."""
    if _is_file_url(base_url):
        return None
    env_name = token_env_name(corpus.owner)
    token = os.environ.get(env_name)
    if not token:
        raise PipelineError(
            f"environment variable {env_name} is unset — the contract sources "
            f"the {corpus.owner!r} push credential from it (never from files)")
    return token


def ensure_remote_repo(corpus: Corpus, base_url: str, case_id: str,
                       token: str | None) -> None:
    if _is_file_url(base_url):
        bare = Path(base_url[len("file://"):]) / corpus.owner / f"{case_id}.git"
        if not bare.exists():
            bare.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", "--bare", str(bare)],
                           check=True, capture_output=True)
        return
    assert token is not None
    status, user = _api(base_url, token, "GET", "/user")
    if status != 200 or not isinstance(user, dict):
        raise PipelineError(
            f"the {token_env_name(corpus.owner)} token was rejected by "
            f"{base_url} (HTTP {status})")
    if user.get("login") != corpus.owner:
        raise PipelineError(
            f"the {token_env_name(corpus.owner)} token authenticates as "
            f"{user.get('login')!r}, not {corpus.owner!r} — wrong credential "
            f"for this owner")
    status, _ = _api(base_url, token, "GET",
                     f"/repos/{corpus.owner}/{case_id}")
    if status == 404:
        status, _ = _api(base_url, token, "POST", "/user/repos",
                         {"name": case_id, "private": False,
                          "auto_init": False, "default_branch": "main"})
        if status not in (200, 201):
            raise PipelineError(
                f"creating repo {corpus.owner}/{case_id} failed (HTTP {status})")
    elif status != 200:
        raise PipelineError(
            f"probing repo {corpus.owner}/{case_id} failed (HTTP {status})")


def push_repo(corpus: Corpus, base_url: str, case_id: str, repo: Path,
              token: str | None, env: dict[str, str]) -> None:
    url = clone_url(base_url, corpus.owner, case_id)
    if token is not None:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{corpus.owner}:{token}@{rest}"
    git(repo, "push", "-q", "--force", "--prune", url,
        "refs/heads/*:refs/heads/*", env=env, redact=token)
    if not _is_file_url(base_url):
        _api(base_url, token, "PATCH", f"/repos/{corpus.owner}/{case_id}",
             {"default_branch": "main"})


def ls_remote_heads(base_url: str, owner: str, case_id: str) -> dict[str, str]:
    url = clone_url(base_url, owner, case_id)
    out = subprocess.run(
        ["git", "ls-remote", "--heads", url], check=True,
        capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).stdout
    heads: dict[str, str] = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        heads[ref.strip().removeprefix("refs/heads/")] = sha
    return heads


# --------------------------------------------------------------------------
# The lock file

def load_lock(root: Path, *, required: bool = False) -> dict:
    path = root / LOCK_NAME
    if not path.is_file():
        if required:
            raise PipelineError(f"{path} missing — run the scaffold phase first")
        return {}
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(
            f"{path} unreadable as JSON ({exc}) — a truncated or "
            f"merge-conflicted lock; restore it or re-run scaffold") from exc
    if not isinstance(lock, dict):
        raise PipelineError(f"{path} must hold a JSON object — re-run scaffold")
    return lock


def write_lock(root: Path, lock: dict) -> None:
    lock["_comment"] = [
        "Generated by corpus/ingest_corpus.py (ADR-0047) — the record of",
        "what is live: per case and per branch the commit SHA, the page",
        "census and prompt ids, and the taskbank identity. Regenerated by",
        "the scaffold/taskbank phases; verified against reality by verify.",
        "Deterministic: an unchanged source tree reproduces this file",
        "byte-identically (no timestamps by design).",
    ]
    path = root / LOCK_NAME
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def phase_scaffold(corpus: Corpus, base_url: str, *, dry_run: bool = False,
                   only: list[str] | None = None) -> None:
    env = git_env(corpus.git_identity)
    token = None if dry_run else resolve_push_auth(corpus, base_url)
    lock = load_lock(corpus.root)
    lock.setdefault("corpus", {})
    lock["corpus"] = {"name": corpus.name, "owner": corpus.owner,
                      "base_url": corpus.base_url,
                      "sandbox_image": corpus.sandbox_image}
    lock.setdefault("cases", {})

    print(f"== scaffold ({'DRY-RUN — nothing pushed' if dry_run else base_url}) ==")
    with tempfile.TemporaryDirectory(prefix="gsj-corpus-scaffold-") as tmp:
        for case_id in sorted(corpus.cases):
            if only and case_id not in only:
                continue
            case = corpus.cases[case_id]
            heads = build_case_repo(corpus, case, Path(tmp), env)
            if not dry_run:
                ensure_remote_repo(corpus, base_url, case_id, token)
                push_repo(corpus, base_url, case_id, Path(tmp) / case_id,
                          token, env)
                live = ls_remote_heads(base_url, corpus.owner, case_id)
                if live != heads:
                    raise PipelineError(
                        f"{case_id}: push did not converge — built {heads}, "
                        f"remote has {live}")
            # ADR-0006/ADR-0015: the repo build is split-agnostic — the
            # repo name is `<case_id>` under `owner`, never `<split>/…`;
            # only the lock records which split holds the case.
            lock["cases"][case_id] = {
                "clone_url": clone_url(corpus.base_url, corpus.owner, case_id),
                "refs": heads,
                "split": case.split,
                "timesteps": {
                    str(t): {
                        "pages": len(case.timesteps[t].pages),
                        "prompt_ids": [p.id for p in case.timesteps[t].prompts],
                    } for t in sorted(case.timesteps)},
            }
            branches = ", ".join(sorted(heads))
            print(f"{case_id} [{case.split}]: {case.max_t} pages on main; "
                  f"branches: {branches}"
                  f"{'' if dry_run else '  [pushed, converged]'}")
    if not dry_run:
        write_lock(corpus.root, lock)
        print(f"lock written: {corpus.root / LOCK_NAME}")


# --------------------------------------------------------------------------
# Phase: ingest (the MCP reindex trigger, ADR-0047(d))

def mint_admin_token(secret: str, ttl_s: int = 300) -> str:
    """Stdlib HS256 JWT with the admin claim — the ADR-0041 mint recipe."""
    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"},
                            separators=(",", ":")).encode())
    payload = b64(json.dumps({"admin": "reindex",
                              "exp": int(time.time()) + ttl_s},
                             separators=(",", ":")).encode())
    signing_input = header + b"." + payload
    signature = b64(hmac.new(secret.encode(), signing_input,
                             hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


def get_health(mcp_url: str, timeout: float = 10.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{mcp_url}/health",
                                    timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, ConnectionError, OSError, ValueError):
        return None


def phase_ingest(corpus: Corpus, mcp_url: str | None, *,
                 dry_run: bool = False, timeout_s: float = 900.0) -> None:
    if mcp_url is None:
        # corpus.yaml's mcp block is optional: no service configured = no
        # re-index to trigger (the contract's "omit to skip"). Loud, never
        # silent — and verify's census check skips on the same condition.
        print("== ingest == SKIPPED (no mcp.url_base configured in "
              "corpus.yaml; pass --mcp-url to name one)")
        return
    if dry_run:
        print(f"== ingest (DRY-RUN) == would POST {mcp_url}/admin/reindex "
              f"and wait for /health state=ready")
        return
    secret = os.environ.get("GSJ_MCP_TOKEN_SECRET")
    if not secret:
        raise PipelineError(
            "environment variable GSJ_MCP_TOKEN_SECRET is unset — the "
            "reindex trigger is guarded by the service's token secret")
    token = mint_admin_token(secret)
    request = urllib.request.Request(
        f"{mcp_url}/admin/reindex", method="POST", data=b"",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read())
            status = response.status
    except urllib.error.HTTPError as error:
        raise PipelineError(
            f"POST /admin/reindex failed: HTTP {error.code} "
            f"{error.read().decode(errors='replace')[:400]}") from None
    except urllib.error.URLError as error:
        raise PipelineError(
            f"MCP service unreachable at {mcp_url}: {error.reason}") from None
    print(f"== ingest == POST /admin/reindex -> {status} {body}")

    deadline = time.monotonic() + timeout_s
    last_state = None
    while time.monotonic() < deadline:
        health = get_health(mcp_url)
        state = health.get("state") if health else "unreachable"
        if state != last_state:
            print(f"  /health state={state}")
            last_state = state
        if state == "ready":
            print(f"  fingerprint={health.get('fingerprint')} "
                  f"index_reused={health.get('index_reused')}")
            return
        if state == "error":
            raise PipelineError(
                f"MCP reindex failed: {health.get('error')}")
        time.sleep(2.0)
    raise PipelineError(f"MCP service not ready within {timeout_s:.0f}s")


# --------------------------------------------------------------------------
# Phase: taskbank (ADR-0022; the ADR-0003 deferral resolved at CP-24)

TASKBANK_COLUMNS = ("case_id", "timestep", "prompt_id", "split",
                    "prompt_source", "prompt_text", "skill_card_text",
                    "sandbox_image")


def _pyarrow():
    """The parquet writer/reader, lazily (ADR-0022 §5) — a dependency of
    this moved component only (corpus/requirements.txt), never the root
    package's; every other phase runs without it."""
    try:
        import pyarrow
        import pyarrow.parquet  # noqa: F401 — registers pyarrow.parquet
        return pyarrow
    except ImportError:
        raise PipelineError(
            "the taskbank phase needs pyarrow (see corpus/requirements.txt): "
            "pip install pyarrow") from None


def _taskbank_schema(pa):
    return pa.schema([
        ("case_id", pa.string()), ("timestep", pa.int64()),
        ("prompt_id", pa.string()), ("split", pa.string()),
        ("prompt_source", pa.string()), ("prompt_text", pa.string()),
        ("skill_card_text", pa.string()), ("sandbox_image", pa.string()),
    ])


def _resolved_columns(corpus: Corpus, prompt: PromptEntry) -> dict:
    """The per-prompt half of an ADR-0022 row. Skill rows carry the
    corpus-level card RESOLVED — raw file bytes decoded, never
    read_text() (CP-13's binding constraint: locale/newline translation
    would silently move the downstream hash); free rows carry the
    contract's verbatim text."""
    if prompt.source == "skill":
        card_text = corpus.skills[prompt.name].read_bytes().decode("utf-8")
        return {"prompt_source": f"skill:{prompt.name}", "prompt_text": None,
                "skill_card_text": card_text}
    return {"prompt_source": "free", "prompt_text": prompt.text,
            "skill_card_text": None}


def build_taskbank_rows(corpus: Corpus,
                        split_of: dict[str, str]) -> list[dict]:
    """One row per (case, timestep, prompt), sorted by
    (case_id, timestep, prompt_id) — deterministic by construction
    (ADR-0022 §4: fixed order, fixed schema, no timestamps)."""
    rows: list[dict] = []
    for case_id in sorted(corpus.cases):
        case = corpus.cases[case_id]
        for t in sorted(case.timesteps):
            for prompt in case.timesteps[t].prompts:
                rows.append({
                    "case_id": case_id, "timestep": t,
                    "prompt_id": prompt.id, "split": split_of[case_id],
                    **_resolved_columns(corpus, prompt),
                    "sandbox_image": corpus.sandbox_image,
                })
    rows.sort(key=lambda r: (r["case_id"], r["timestep"], r["prompt_id"]))
    return rows


def read_taskbank_rows(path: Path) -> list[dict]:
    """The bank read back for verify and for consumers' reference —
    refuses anything that is not the ADR-0022 shape."""
    pa = _pyarrow()
    try:
        table = pa.parquet.read_table(path)
    except Exception as exc:
        raise PipelineError(
            f"{path} is not readable as parquet: {exc!r}") from exc
    # Full schema equality, not just column names: a float64 timestep is
    # 1.0 == 1 in every downstream comparison and would verify clean while
    # handing consumers the wrong types (CP-24's own adversarial pass).
    if not table.schema.equals(_taskbank_schema(pa)):
        raise PipelineError(
            f"{path} schema != the ADR-0022 row shape — got "
            f"{[(f.name, str(f.type)) for f in table.schema]}, want "
            f"{[(f.name, str(f.type)) for f in _taskbank_schema(pa)]}")
    return table.to_pylist()


def phase_taskbank(corpus: Corpus, *, dry_run: bool = False,
                   only: list[str] | None = None) -> None:
    """ADR-0022. The split is sourced from ``corpus.lock.json``
    ``cases.<case_id>.split`` (ADR-0015's row-spec, binding) — so the
    phase needs a scaffolded lock that AGREES with the tree; the counts
    land in the lock's ``taskbank`` block beside the sha256."""
    if only:
        raise PipelineError(
            "--only cannot build the taskbank — the bank is corpus-wide and "
            "a partial bank is the ADR-0047(e) footgun; run a plain "
            "`taskbank`")
    if dry_run:
        # A never-scaffolded tree has no lock; the preview sources the
        # split from the tree (verify holds tree == lock everywhere else).
        rows = build_taskbank_rows(
            corpus, {cid: case.split for cid, case in corpus.cases.items()})
        train = sum(1 for r in rows if r["split"] == "train")
        print(f"== taskbank (DRY-RUN — nothing written) == would write "
              f"{len(rows)} rows (train {train} / eval {len(rows) - train}) "
              f"to {corpus.root / TASKBANK_NAME}")
        return
    lock = load_lock(corpus.root, required=True)
    lock_cases = lock.get("cases")
    lock_cases = lock_cases if isinstance(lock_cases, dict) else {}
    split_of: dict[str, str] = {}
    for case_id in sorted(corpus.cases):
        if not isinstance(lock_cases.get(case_id), dict):
            raise PipelineError(
                f"{case_id} is not in the lock (or its entry is malformed) "
                f"— run the scaffold phase first (the row's split is "
                f"sourced from cases.{case_id}.split, ADR-0015)")
        lock_split = lock_cases[case_id].get("split")
        if lock_split != corpus.cases[case_id].split:
            raise PipelineError(
                f"{case_id}: split as sourced "
                f"{corpus.cases[case_id].split!r} != lock {lock_split!r} — "
                f"a case that moves splits must be re-scaffolded before the "
                f"bank states its split (ADR-0015)")
        split_of[case_id] = lock_split
    rows = build_taskbank_rows(corpus, split_of)
    pa = _pyarrow()
    bank_path = corpus.root / TASKBANK_NAME
    pa.parquet.write_table(
        pa.Table.from_pylist(rows, schema=_taskbank_schema(pa)), bank_path)
    train = sum(1 for r in rows if r["split"] == "train")
    digest = _sha256_file(bank_path)
    lock["taskbank"] = {"path": TASKBANK_NAME, "rows": len(rows),
                        "train": train, "eval": len(rows) - train,
                        "sha256": digest}
    write_lock(corpus.root, lock)
    print(f"== taskbank == {len(rows)} rows (train {train} / eval "
          f"{len(rows) - train}) -> {bank_path}; sha256 {digest[:16]}… "
          f"recorded in the lock")


# --------------------------------------------------------------------------
# Phase: verify (post — reality vs the tree and the lock)

def _branch_files(clone: Path, branch: str) -> dict[str, str]:
    """path -> blob sha256 (content hash, not git oid) for one branch. A
    fresh clone materializes only HEAD locally — read every branch through
    its remote-tracking ref, which IS the state as cloned."""
    ref = f"refs/remotes/origin/{branch}"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    listing = git(clone, "ls-tree", "-r", "--name-only", ref, env=env)
    files: dict[str, str] = {}
    for path in listing.splitlines():
        path = path.strip()
        if not path:
            continue
        blob = subprocess.run(
            ["git", "-C", str(clone), "show", f"{ref}:{path}"],
            check=True, capture_output=True).stdout
        files[path] = hashlib.sha256(blob).hexdigest()
    return files


def verify_case_clone(corpus: Corpus, case: CaseTree, base_url: str,
                      lock_case: dict, tmp: Path,
                      findings: list[Finding]) -> None:
    case_id = case.case_id
    url = clone_url(base_url, corpus.owner, case_id)
    clone = tmp / case_id
    try:
        subprocess.run(["git", "clone", "-q", url, str(clone)], check=True,
                       capture_output=True, text=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.CalledProcessError as error:
        findings.append(Finding(case_id, "clone", False,
                                f"git clone {url} failed: {error.stderr.strip()}",
                                case.split))
        return

    live = ls_remote_heads(base_url, corpus.owner, case_id)
    if live != lock_case.get("refs"):
        findings.append(Finding(
            case_id, "refs", False,
            f"live refs != lock: live={live} lock={lock_case.get('refs')}",
            case.split))
    else:
        findings.append(Finding(case_id, "refs", True,
                                f"{len(live)} refs match the lock",
                                case.split))

    # ADR-0015: the split checks back from the lock — a case that moved
    # splits without a re-scaffold is a reality mismatch.
    lock_split = lock_case.get("split")
    if lock_split != case.split:
        findings.append(Finding(
            case_id, "split", False,
            f"split as sourced {case.split!r} != lock {lock_split!r} — a "
            f"case that moves splits must be re-scaffolded (the lock is "
            f"the freeze record)", case.split))
    else:
        findings.append(Finding(case_id, "split", True,
                                "matches the lock", case.split))

    fixed = {"AGENTS.md": hashlib.sha256(
                 corpus.agents_md.read_bytes()).hexdigest(),
             ".gitignore": hashlib.sha256(
                 CASE_GITIGNORE.encode()).hexdigest(),
             "out/.gitkeep": hashlib.sha256(b"").hexdigest()}
    for name, card in corpus.skills.items():
        fixed[f"skills/{name}/SKILL.md"] = hashlib.sha256(
            card.read_bytes()).hexdigest()

    branch_pages: dict[str, dict[int, str]] = {}
    expected_branches = {"main": case.timesteps[case.max_t]}
    expected_branches.update({f"timestep-{t}": case.timesteps[t]
                              for t in sorted(case.timesteps)})
    for branch, source_ts in expected_branches.items():
        ok = True
        try:
            files = _branch_files(clone, branch)
        except PipelineError as error:
            findings.append(Finding(case_id, branch, False, str(error),
                                    case.split))
            continue
        pages: dict[int, str] = {}
        for path, digest in files.items():
            match = re.match(r"^md/page_(\d{4})\.md$", path)
            if match:
                pages[int(match.group(1))] = digest
        branch_pages[branch] = pages

        expected_census = sorted(source_ts.pages)
        if sorted(pages) != expected_census:
            findings.append(Finding(
                case_id, branch, False,
                f"page census as cloned {sorted(pages)} != source "
                f"{expected_census}", case.split))
            ok = False
        for page in sorted(source_ts.pages):
            src = _sha256_file(source_ts.pages[page])
            got = pages.get(page)
            if got is not None and got != src:
                findings.append(Finding(
                    case_id, branch, False,
                    f"page {page} bytes differ from the source: cloned "
                    f"{got[:16]}… != source {src[:16]}…", case.split))
                ok = False
        for path, digest in fixed.items():
            if files.get(path) != digest:
                findings.append(Finding(
                    case_id, branch, False,
                    f"{path} {'missing' if path not in files else 'differs'} "
                    f"in the cloned branch", case.split))
                ok = False
        extras = sorted(set(files) - set(fixed)
                        - {f"md/page_{p:04d}.md" for p in source_ts.pages})
        if extras:
            findings.append(Finding(
                case_id, branch, False, f"unexpected tracked files {extras}",
                case.split))
            ok = False
        if ok:
            findings.append(Finding(case_id, branch, True,
                                    f"{len(pages)} pages, contract files OK",
                                    case.split))

    # Prefix consistency across branches AS CLONED (not just as sourced).
    steps = sorted(case.timesteps)
    for t1, t2 in zip(steps, steps[1:]):
        low = branch_pages.get(f"timestep-{t1}", {})
        high = branch_pages.get(f"timestep-{t2}", {})
        for page in sorted(low):
            if page in high and low[page] != high[page]:
                findings.append(Finding(
                    case_id, f"timestep-{t2}", False,
                    f"prefix divergence AS CLONED on page {page}: "
                    f"timestep-{t1} {low[page][:16]}… != {high[page][:16]}…",
                    case.split))


def _bank_row_findings(corpus: Corpus, lock_bank: dict,
                       rows: list[dict]) -> list[Finding]:
    """verify's row-level half (ADR-0022; deferred since CP-01 with the
    phase): counts vs the lock, every (case, timestep, prompt_id) triple
    exactly once and set-equal to the tree, and each row's split /
    sandbox_image / text columns re-derived from the tree —
    bytes-independent, so it holds even if the parquet writer changes."""
    findings: list[Finding] = []

    def fail(detail: str) -> None:
        findings.append(Finding("(corpus)", "taskbank rows", False, detail))

    expected: dict[tuple[str, int, str], dict] = {
        (case_id, t, prompt.id): {
            "split": case.split,
            **_resolved_columns(corpus, prompt),
            "sandbox_image": corpus.sandbox_image,
        }
        for case_id, case in corpus.cases.items()
        for t in sorted(case.timesteps)
        for prompt in case.timesteps[t].prompts
    }

    if len(rows) != lock_bank.get("rows"):
        fail(f"row count {len(rows)} != lock {lock_bank.get('rows')}")
    counts = Counter(r.get("split") for r in rows)
    for split in SPLITS:
        if counts.get(split, 0) != lock_bank.get(split):
            fail(f"{split} row count {counts.get(split, 0)} != lock "
                 f"{lock_bank.get(split)}")

    # key=repr on every sort: a doctored bank may carry null/mixed-typed
    # triple values, and the verifier must FAIL on those, never crash.
    triples = Counter((r.get("case_id"), r.get("timestep"),
                       r.get("prompt_id")) for r in rows)
    for triple, n in sorted(triples.items(), key=repr):
        if n > 1:
            fail(f"triple {triple} appears {n} times — one row per "
                 f"(case, timestep, prompt)")
    missing = sorted(set(expected) - set(triples), key=repr)
    extra = sorted(set(triples) - set(expected), key=repr)
    if missing:
        fail(f"triples in the tree but missing from the bank: {missing}")
    if extra:
        fail(f"triples in the bank but not in the tree: {extra}")

    for row in rows:
        triple = (row.get("case_id"), row.get("timestep"),
                  row.get("prompt_id"))
        want = expected.get(triple)
        if want is None:
            continue  # already reported under `extra`
        for column, value in want.items():
            if row.get(column) != value:
                shown = value if column == "split" or column == "sandbox_image" \
                    else "the tree's bytes"
                fail(f"row {triple}: {column} != {shown}")

    if not findings:
        findings.append(Finding(
            "(corpus)", "taskbank rows", True,
            f"{len(rows)} rows (train {counts.get('train', 0)} / eval "
            f"{counts.get('eval', 0)}): triples set-equal the tree, "
            f"splits and text columns verified"))
    return findings


def phase_verify(corpus: Corpus, base_url: str, mcp_url: str | None, *,
                 skip_mcp: bool = False, only: list[str] | None = None) -> int:
    lock = load_lock(corpus.root, required=True)
    findings: list[Finding] = []

    lock_cases = lock.get("cases")
    lock_cases = lock_cases if isinstance(lock_cases, dict) else {}
    with tempfile.TemporaryDirectory(prefix="gsj-corpus-verify-") as tmp:
        for case_id in sorted(corpus.cases):
            if only and case_id not in only:
                continue
            if not isinstance(lock_cases.get(case_id), dict):
                findings.append(Finding(case_id, "lock", False,
                                        "case missing from the lock (or "
                                        "its entry malformed) — run "
                                        "scaffold",
                                        corpus.cases[case_id].split))
                continue
            verify_case_clone(corpus, corpus.cases[case_id], base_url,
                              lock_cases[case_id], Path(tmp), findings)
        if not only:
            stray = sorted(set(lock_cases) - set(corpus.cases))
            if stray:
                findings.append(Finding("(corpus)", "lock", False,
                                        f"lock records cases not in the "
                                        f"source tree: {stray}"))

    # MCP census vs the lock.
    if skip_mcp:
        findings.append(Finding("(corpus)", "mcp", True,
                                "SKIPPED (--skip-ingest)"))
    elif mcp_url is None:
        findings.append(Finding("(corpus)", "mcp", True,
                                "SKIPPED (no mcp.url_base configured)"))
    else:
        health = get_health(mcp_url)
        if health is None or health.get("state") != "ready":
            findings.append(Finding(
                "(corpus)", "mcp", False,
                f"service at {mcp_url} not ready: "
                f"{health.get('state') if health else 'unreachable'}"))
        else:
            served = health.get("cases", {})
            wanted = {cid: corpus.cases[cid] for cid in corpus.cases
                      if not only or cid in only}
            if not only and set(served) != set(wanted):
                findings.append(Finding(
                    "(corpus)", "mcp", False,
                    f"served case set {sorted(served)} != corpus "
                    f"{sorted(wanted)}"))
            for cid, case in sorted(wanted.items()):
                info = served.get(cid)
                if info is None:
                    findings.append(Finding(cid, "mcp", False,
                                            "case not served"))
                    continue
                want = {"pages": case.max_t,
                        "timesteps": sorted(case.timesteps)}
                got = {"pages": info.get("pages"),
                       "timesteps": info.get("timesteps")}
                if want != got:
                    findings.append(Finding(
                        cid, "mcp", False,
                        f"census mismatch: served {got} != corpus {want}"))
                else:
                    findings.append(Finding(
                        cid, "mcp", True,
                        f"census {got['pages']} pages, "
                        f"timesteps {got['timesteps']}"))

    # The parquet vs the lock and the tree: the byte half (sha256) and the
    # row-level half deferred since CP-01 with the phase — landed, ADR-0022.
    bank_path = corpus.root / TASKBANK_NAME
    lock_bank = lock.get("taskbank")
    if only:
        findings.append(Finding("(corpus)", "taskbank", True,
                                "SKIPPED (--only: the bank is corpus-wide)"))
    elif not isinstance(lock_bank, dict):
        findings.append(Finding("(corpus)", "taskbank", False,
                                "no bank recorded in the lock (or the "
                                "taskbank block is malformed) — run the "
                                "taskbank phase (ADR-0022)"))
    elif not bank_path.is_file():
        findings.append(Finding("(corpus)", "taskbank", False,
                                f"{bank_path} missing but recorded in the "
                                f"lock"))
    else:
        digest = _sha256_file(bank_path)
        if digest != lock_bank.get("sha256"):
            findings.append(Finding(
                "(corpus)", "taskbank", False,
                f"sha256 {digest[:16]}… != lock {str(lock_bank.get('sha256'))[:16]}…"))
        else:
            findings.append(Finding("(corpus)", "taskbank", True,
                                    "sha matches the lock"))
        try:
            rows = read_taskbank_rows(bank_path)
        except PipelineError as error:
            findings.append(Finding("(corpus)", "taskbank", False,
                                    str(error)))
        else:
            findings.extend(_bank_row_findings(corpus, lock_bank, rows))

    _print_table("verify", findings)
    return 1 if any(not f.ok for f in findings) else 0


# --------------------------------------------------------------------------
# CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", choices=["validate", "scaffold", "ingest",
                                          "taskbank", "verify", "all"])
    parser.add_argument("--corpus", type=Path, required=True,
                        help="the corpus root (docs/corpus-contract.md)")
    parser.add_argument("--owner-override",
                        help="push under this Forgejo owner instead of "
                             "corpus.yaml's (its token env var applies)")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate + build locally; push nothing, write "
                             "nothing, trigger nothing")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="skip the MCP reindex trigger / census check")
    parser.add_argument("--only", nargs="+", metavar="CASE_ID",
                        help="limit validate/scaffold/verify repo work to "
                             "these cases; the taskbank phase is SKIPPED "
                             "(the bank is corpus-wide — refresh it with a "
                             "plain `taskbank` run)")
    parser.add_argument("--base-url",
                        help="transport override for the Forgejo base URL "
                             "(e.g. a workstation tunnel); the lock keeps "
                             "corpus.yaml's canonical URL")
    parser.add_argument("--mcp-url",
                        help="transport override for the MCP service URL")
    parser.add_argument("--ingest-timeout", type=float, default=900.0,
                        help="seconds to wait for /health ready (default 900)")
    args = parser.parse_args(argv)

    root = args.corpus.resolve()
    if not root.is_dir():
        print(f"ingest_corpus: corpus root {root} is not a directory",
              file=sys.stderr)
        return 2

    try:
        # Every phase re-validates first: nothing downstream runs on a tree
        # that fails the contract.
        corpus = phase_validate(root, only=args.only,
                                owner_override=args.owner_override,
                                quiet=args.phase not in ("validate", "all"))
        if corpus is None:
            return 1
        if args.phase == "validate":
            return 0

        base_url = (args.base_url.rstrip("/") if args.base_url
                    else corpus.base_url)
        mcp_url = (args.mcp_url.rstrip("/") if args.mcp_url
                   else corpus.mcp_url)

        if args.phase in ("scaffold", "all"):
            phase_scaffold(corpus, base_url, dry_run=args.dry_run,
                           only=args.only)
        if args.phase in ("ingest", "all"):
            if args.skip_ingest:
                print("== ingest == SKIPPED (--skip-ingest)")
            else:
                phase_ingest(corpus, mcp_url, dry_run=args.dry_run,
                             timeout_s=args.ingest_timeout)
        if args.phase in ("taskbank", "all"):
            if args.phase == "all" and args.only:
                # ADR-0047(e): a partial bank must never exist — under
                # --only the bank is skipped LOUDLY and the committed one
                # is left alone; an explicit `taskbank --only` raises.
                print("== taskbank == SKIPPED (--only: the bank is "
                      "corpus-wide — refresh it with a plain `taskbank` "
                      "run)")
            else:
                phase_taskbank(corpus, dry_run=args.dry_run, only=args.only)
        if args.phase in ("verify", "all"):
            if args.dry_run:
                print("== verify == SKIPPED (--dry-run pushed nothing)")
                return 0
            return phase_verify(corpus, base_url, mcp_url,
                                skip_mcp=args.skip_ingest, only=args.only)
        return 0
    except PipelineError as error:
        print(f"ingest_corpus: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
