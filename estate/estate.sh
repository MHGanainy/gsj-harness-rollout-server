#!/usr/bin/env bash
# estate/estate.sh — the front door to this repo's H200 estate (CP-50).
#
# THIN BY LAW: every verb execs an existing script or compose file in
# place; nothing here reimplements a recipe. The recipes are this
# directory's README.md; bring-up-from-nothing belongs to the demo repo
# (gsj-rollout-demo/bootstrap.py), not here. Scripts keep their homes —
# serve.sh reads its sibling model-*.env files and ships its own jinja,
# up.sh cd's to its compose — so this file only routes.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  cat <<'USAGE'
estate.sh — front door to the H200 estate scripts (see estate/README.md)

  up                    start Forgejo (forgejo/up.sh: compose up, health
                        wait, admin user, API token). Needs: docker.
  owner <name>          create a Forgejo owner + a push token AND a read-scoped
                        clone token (forgejo/create_owner.sh; CP-56). Prints the
                        two export lines; the read token feeds rollout.h200.yaml's
                        clone_credential_env. Needs: Forgejo up.
  down [--wipe]         stop Forgejo (forgejo/down.sh). --wipe also deletes
                        instance data + token — the README's caveats apply.
  mcp-up                start the MCP service (mcp-service/compose.yml).
                        Needs: docker, the gsj-mcp-service image loaded,
                        GSJ_MCP_TOKEN_SECRET and (CP-58: the index build
                        clones under sign-in) GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING
                        in the environment.
  mcp-down              stop the MCP service (needs the same two variables:
                        compose interpolates them on down as well).
  serve <0.6b|llama31>  serve a model (serving/serve.sh or
                        serving/serve-llama31.sh). Needs: the H200's venv
                        + snapshot (BRINGUP §3 — these scripts start, they
                        do not install).
  serve-updated <dir>   serve a trainer's HF-format export
                        (serving/serve-updated.sh — the weight-sync half).
  health                probe the served engine (serving/healthcheck.sh).
  status                compose ps for Forgejo + MCP, then the engine probe.
USAGE
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found — $2" >&2; exit 1; }; }

case "${1:---help}" in
  up)
    need docker "install docker or run this on the estate host"
    exec forgejo/up.sh ;;
  owner)
    [ $# -ge 2 ] || { echo "ERROR: owner needs a name — try: estate.sh owner gsj-staging" >&2; exit 1; }
    shift; exec forgejo/create_owner.sh "$@" ;;
  down)
    shift || true; exec forgejo/down.sh "$@" ;;
  mcp-up)
    need docker "install docker or run this on the estate host"
    [ -n "${GSJ_MCP_TOKEN_SECRET:-}" ] || { echo "ERROR: GSJ_MCP_TOKEN_SECRET is not set — export it first (the compose refuses without it; value never lands in a file)" >&2; exit 1; }
    [ -n "${GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING:-}" ] || { echo "ERROR: GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING is not set — export GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING=\$(cat estate/forgejo/.token-gsj-staging-read) first (CP-58: the estate requires sign-in for read, the index build clones with it)" >&2; exit 1; }
    exec docker compose -f mcp-service/compose.yml up -d ;;
  mcp-down)
    need docker "install docker or run this on the estate host"
    # compose interpolates the \${VAR:?} lines on down too — both must be set
    [ -n "${GSJ_MCP_TOKEN_SECRET:-}" ] || { echo "ERROR: GSJ_MCP_TOKEN_SECRET is not set — compose interpolates it even for down; export it first" >&2; exit 1; }
    [ -n "${GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING:-}" ] || { echo "ERROR: GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING is not set — compose interpolates it even for down; export GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING=\$(cat estate/forgejo/.token-gsj-staging-read) first" >&2; exit 1; }
    exec docker compose -f mcp-service/compose.yml down ;;
  serve)
    case "${2:-}" in
      0.6b)    exec serving/serve.sh ;;
      llama31) exec serving/serve-llama31.sh ;;
      *) echo "ERROR: serve needs a model family — 0.6b (Qwen3-0.6B, serving/serve.sh) or llama31 (Llama-3.1-8B, serving/serve-llama31.sh)" >&2; exit 1 ;;
    esac ;;
  serve-updated)
    [ $# -ge 2 ] || { echo "ERROR: serve-updated needs the trainer export directory — try: estate.sh serve-updated /path/to/hf_export" >&2; exit 1; }
    shift; exec serving/serve-updated.sh "$@" ;;
  health)
    exec serving/healthcheck.sh ;;
  status)
    need docker "install docker or run this on the estate host"
    echo "— Forgejo:"; docker compose -f forgejo/docker-compose.yml ps || true
    echo "— MCP service:"; docker compose -f mcp-service/compose.yml ps || true
    echo "— engine:"; serving/healthcheck.sh || true ;;
  -h|--help|help)
    usage ;;
  *)
    echo "ERROR: unknown verb '${1}' — run estate.sh --help for the verb table" >&2; exit 1 ;;
esac
