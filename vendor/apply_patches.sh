#!/usr/bin/env bash
# Apply the carried patch set to a CLEAN vendored Polar tree, in order.
#
#   bash vendor/apply_patches.sh            # apply P1..P3 to vendor/polar (the re-vendor flow)
#   bash vendor/apply_patches.sh --verify   # change nothing; assert all three are applied
#
# The committed vendor/polar tree already has the patches applied (ADR-0005);
# the apply flow exists for re-vendoring (vendor/REVENDOR.md). git apply is
# atomic per patch: a single rejected hunk fails that whole patch, loudly,
# with a non-zero exit — never a silently half-applied tree.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
POLAR="$HERE/polar"
PATCHES=(
  "P1-non-agent-filter.patch"
  "P2-abort-to-error.patch"
  "P3-policy-version-storage.patch"
)

check() { # label, file, symbol
  if grep -qF "$3" "$POLAR/$2"; then
    echo "OK   $1  $2  ::  $3"
  else
    echo "FAIL $1  $2  ::  $3  -- MISSING" >&2
    FAILED=1
  fi
}

verify() {
  FAILED=0
  # P1: filter module present + wired into both builders
  check P1 src/polar/trajectory/builder/record_filters.py "_is_non_agent_side_completion"
  check P1 src/polar/trajectory/builder/per_request.py "filter_trainable_completions"
  check P1 src/polar/trajectory/builder/prefix_merging.py "filter_trainable_completions"
  check P1 src/polar/trajectory/builder/prefix_merging.py "raw_completions_total"
  # P2: abort helper + session-level check in build()
  check P2 src/polar/trajectory/builder/prefix_merging.py "_completion_finish_reason"
  check P2 src/polar/trajectory/builder/prefix_merging.py "session_had_abort"
  check P2 src/polar/trajectory/builder/prefix_merging.py 'error="aborted generation (weight-update cutoff)"'
  # P3: live-version stamping + the metadata persistence fix
  check P3 src/polar/gateway/storage.py "set_policy_version"
  check P3 src/polar/gateway/storage.py "session_would_span"
  check P3 src/polar/gateway/storage.py "dict(record.metadata)"
  if [[ "$FAILED" -ne 0 ]]; then
    echo "verification FAILED — the vendored tree is missing carried-patch symbols" >&2
    exit 1
  fi
  echo "all three patches verified present"
}

apply_one() {
  local patch="$HERE/patches/$1"
  echo "applying $1"
  if git -C "$POLAR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Inside a git worktree (the normal case: vendor/polar committed to the
    # gsj repo) git apply resolves paths against the repo top, so anchor the
    # patch onto the vendored subtree explicitly.
    local top prefix
    top="$(git -C "$POLAR" rev-parse --show-toplevel)"
    prefix="$(git -C "$POLAR" rev-parse --show-prefix)"
    (cd "$top" && git apply -p1 --directory="$prefix" "$patch")
  else
    (cd "$POLAR" && git apply -p1 "$patch")
  fi
}

if [[ "${1:-}" == "--verify" ]]; then
  verify
  exit 0
fi

for p in "${PATCHES[@]}"; do
  apply_one "$p"
done
echo "all patches applied; now run: bash $0 --verify"
