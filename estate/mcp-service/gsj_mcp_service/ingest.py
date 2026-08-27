"""Ingestion at init, from Forgejo (ADR-0040(c)).

Clone/fetch each case's bare mirror into the clone cache, read ``main`` for
the FULL page set (git plumbing — never a working-tree checkout), chunk each
page (never across page boundaries), and hand the chunks to the indexer.

The full document is indexed once per case — NOT per timestep; the cutoff is
a query-time filter (ADR-0040(d), the ADR-0007 leaky-server posture carried
over). Re-index trigger: a corpus-fingerprint mismatch (repo SHAs + model
revision + chunking params) — with the dataset frozen, that only happens on
a deliberate re-pin.

Git via the CLI (the official client, ADR-0034 prior-art); the source auth
token (if configured) is injected into the clone URL at call time and never
logged.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import ChunkingConfig, SourceConfig

PAGE_PATH_RE = re.compile(r"^md/page_(\d{4})\.md$")


class IngestError(Exception):
    """Ingestion failure with a message safe to surface in /health."""


@dataclass(frozen=True)
class Chunk:
    case_id: str
    page: int
    file: str  # md/page_NNNN.md
    chunk_idx: int
    text: str


@dataclass(frozen=True)
class CaseSource:
    case_id: str
    refs: dict[str, str]  # ref name -> sha (all branches, the frozen record)
    main_sha: str
    timesteps: list[int]  # parsed from ref_pattern matches
    pages: dict[int, str]  # page -> full page text
    chunks: list[Chunk]


def _git(*args: str, redact: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True,
            timeout=120)
    except subprocess.CalledProcessError as error:
        message = f"git {args[0]} failed (rc {error.returncode}): {error.stderr.strip()}"
        if redact:
            message = message.replace(redact, "***")
        raise IngestError(message) from None
    except subprocess.TimeoutExpired:
        raise IngestError(f"git {args[0]} timed out") from None
    return result.stdout


def _authed_url(source: SourceConfig, repo: str, token: str | None) -> str:
    url = source.clone_url(repo)
    if token is None or not url.startswith(("http://", "https://")):
        return url
    scheme, rest = url.split("://", 1)
    user = source.owner or "token"
    return f"{scheme}://{user}:{token}@{rest}"


def clone_or_fetch(source: SourceConfig, repo: str, token: str | None) -> Path:
    """Bare mirror clone (first start) or fetch --prune (restart) -> git dir."""
    source.clone_cache_dir.mkdir(parents=True, exist_ok=True)
    git_dir = source.clone_cache_dir / f"{repo}.git"
    url = _authed_url(source, repo, token)
    if not git_dir.exists():
        _git("clone", "--bare", "--quiet", url, str(git_dir), redact=token)
    else:
        _git("--git-dir", str(git_dir), "fetch", "--quiet", "--prune", url,
             "+refs/heads/*:refs/heads/*", redact=token)
    return git_dir


def read_refs(git_dir: Path) -> dict[str, str]:
    out = _git("--git-dir", str(git_dir), "for-each-ref",
               "--format=%(refname:short) %(objectname)", "refs/heads")
    refs: dict[str, str] = {}
    for line in out.splitlines():
        name, _, sha = line.strip().partition(" ")
        if name:
            refs[name] = sha
    return refs


def read_pages(git_dir: Path, case_id: str, ref_main: str) -> dict[int, str]:
    """Full page set from main, contiguous 1..N enforced."""
    listing = _git("--git-dir", str(git_dir), "ls-tree", "-r", "--name-only",
                   ref_main)
    pages: dict[int, str] = {}
    for path in listing.splitlines():
        match = PAGE_PATH_RE.match(path.strip())
        if match:
            text = _git("--git-dir", str(git_dir), "show",
                        f"{ref_main}:{path.strip()}")
            pages[int(match.group(1))] = text
    if not pages:
        raise IngestError(f"{case_id}: no md/page_NNNN.md files on {ref_main!r}")
    if sorted(pages) != list(range(1, max(pages) + 1)):
        raise IngestError(
            f"{case_id}: pages not contiguous 1..N — got {sorted(pages)}")
    return pages


def parse_timesteps(refs: dict[str, str], ref_pattern: str) -> list[int]:
    pattern = re.compile(
        "^" + re.escape(ref_pattern).replace(re.escape("{T}"), r"(\d+)") + "$")
    steps = sorted(int(m.group(1)) for name in refs
                   if (m := pattern.match(name)))
    return steps


def chunk_page(tokenizer, case_id: str, page: int, text: str,
               chunking: ChunkingConfig) -> list[Chunk]:
    """Token-window chunks of ONE page — never across pages (ADR-0040(e)).

    Windows of ``max_tokens`` tokenizer tokens with ``overlap`` token overlap,
    mapped back to character spans so chunk text is a verbatim slice of the
    page. Every chunk carries exactly one (page, file).
    """
    encoding = tokenizer(text, add_special_tokens=False,
                         return_offsets_mapping=True)
    offsets = [span for span in encoding["offset_mapping"] if span[1] > span[0]]
    file = f"md/page_{page:04d}.md"
    if not offsets:
        return [Chunk(case_id, page, file, 0, text)]
    stride = chunking.max_tokens - chunking.overlap
    chunks: list[Chunk] = []
    start_tok = 0
    while start_tok < len(offsets):
        window = offsets[start_tok:start_tok + chunking.max_tokens]
        begin, end = window[0][0], window[-1][1]
        chunks.append(Chunk(case_id, page, file, len(chunks), text[begin:end]))
        if start_tok + chunking.max_tokens >= len(offsets):
            break
        start_tok += stride
    return chunks


def ingest_case(source: SourceConfig, chunking: ChunkingConfig, tokenizer,
                repo: str, token: str | None) -> CaseSource:
    git_dir = clone_or_fetch(source, repo, token)
    refs = read_refs(git_dir)
    if source.ref_main not in refs:
        raise IngestError(f"{repo}: ref {source.ref_main!r} not found "
                          f"(refs: {sorted(refs)})")
    pages = read_pages(git_dir, repo, source.ref_main)
    chunks: list[Chunk] = []
    for page in sorted(pages):
        chunks.extend(chunk_page(tokenizer, repo, page, pages[page], chunking))
    return CaseSource(
        case_id=repo, refs=refs, main_sha=refs[source.ref_main],
        timesteps=parse_timesteps(refs, source.ref_pattern),
        pages=pages, chunks=chunks)
