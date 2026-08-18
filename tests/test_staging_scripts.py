"""CP-33 (F-53, wishlist 33): the sync script's remote delivery, guarded."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "staging" / "serving" / "serve-updated.sh"


def test_health_gate_rides_bash_s_not_bash_c():
    """`ssh … bash -c '<newline>…'` word-joins: the remote `bash -c` received
    an EMPTY first line as its whole script and the health gate ran in the
    remote LOGIN shell by accident (F-53, verified at CP-32 — the sync
    completed through it and was proven only by the probe). The fix is the
    script's own idiom — `bash -s` with the port as a positional. A content
    tripwire, deliberately: staging shell has no unit seam, and this fails
    the moment the accidental form returns."""
    text = SCRIPT.read_text()
    executable = "\n".join(line for line in text.splitlines()
                           if not line.lstrip().startswith("#"))
    assert "bash -c" not in executable  # the comment may name the old form
    assert 'bash -s "$PORT" <<' in executable
    assert text.count("REMOTE_HEALTH") == 2  # heredoc open + close


def test_sync_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
