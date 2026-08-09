"""Session fixtures. Cost discipline: the full 4-case index is embedded ONCE
(``built_state``, in-process) into a session directory; every server
subprocess afterward points at the same index + clone cache, matches the
corpus fingerprint, and reuses the stored vectors — startups are model-load
fast, never a re-embed."""

from __future__ import annotations

import pytest

from helpers import (
    ALL_REPOS,
    free_port,
    load_facts,
    make_state,
    spawn_server,
    stop_server,
    write_config,
)


@pytest.fixture(scope="session")
def shared_dirs(tmp_path_factory):
    """The session-shared clone cache + index directory (built once)."""
    root = tmp_path_factory.mktemp("shared")
    return {"root": root, "clones": root / "clones", "index": root / "index"}


@pytest.fixture(scope="session")
def built_state(shared_dirs):
    """The FIRST-ever build: in-process AppState over all four cases. Every
    later server reuses this index via fingerprint match."""
    config_path = write_config(
        shared_dirs["root"], repos=ALL_REPOS,
        clone_cache_dir=shared_dirs["clones"], index_path=shared_dirs["index"])
    state = make_state(config_path)
    assert state.status == "ready", f"first build failed: {state.error}"
    assert state.reused_index is False
    return state


def _start_shared_server(tmp_path_factory, shared_dirs, name):
    run_dir = tmp_path_factory.mktemp(f"srv-{name}")
    port = free_port()
    config_path = write_config(
        run_dir, repos=ALL_REPOS, clone_cache_dir=shared_dirs["clones"],
        index_path=shared_dirs["index"], port=port)
    return spawn_server(run_dir, config_path, port)


@pytest.fixture(scope="session")
def server(tmp_path_factory, shared_dirs, built_state):
    """The main session server — a real subprocess over the prebuilt index."""
    proc, log_file = _start_shared_server(tmp_path_factory, shared_dirs, "main")
    yield proc
    stop_server(proc, log_file)


@pytest.fixture(scope="session")
def server2(tmp_path_factory, shared_dirs, built_state):
    """A second, independent server process over the SAME prebuilt index —
    the cross-process determinism counterpart."""
    proc, log_file = _start_shared_server(tmp_path_factory, shared_dirs, "second")
    yield proc
    stop_server(proc, log_file)


@pytest.fixture(scope="session")
def facts():
    """The dataset's fact ground truth: [{case_id, page, k, line}] with
    unique SN-serials embedded per fact line — read off the corpus source
    pages since CP-34 (the generated manifest died with the purge)."""
    facts = load_facts()
    assert facts, "no FACT- lines found in the corpus source tree"
    return facts
