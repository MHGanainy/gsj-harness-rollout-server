#!/usr/bin/env bash
# Create a pipeline OWNER user on the staging Forgejo + issue TWO tokens:
# a write-scoped PUSH token (the corpus pipeline; the predecessor's CP-33,
# ADR-0046(e)/ADR-0047) and a read-scoped CLONE token (CP-56 — the sandbox
# agent's credential when the estate requires sign-in for read). Idempotent:
# existing users are kept, a still-valid token is kept. Run after up.sh.
#
#   ./create_owner.sh gsj-staging     # the staging corpus owner
#   ./create_owner.sh gsj-prod        # the prod owner (created empty at
#                                     #   the predecessor's CP-33 — the switch is one value)
#
# The tokens land in .token-<owner> (push) and .token-<owner>-read (clone),
# both gitignored, 0600. Each is read from the env var derived from the owner:
#   export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat .token-gsj-staging)"        # pushes
#   export GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING="$(cat .token-gsj-staging-read)" # clone_credential_env
set -euo pipefail
cd "$(dirname "$0")"

OWNER="${1:?usage: create_owner.sh <owner> (gsj-staging | gsj-prod)}"
HOST="http://172.28.9.10:3000"   # static container IP — no published ports
TOKEN_FILE=".token-${OWNER}"
READ_TOKEN_FILE=".token-${OWNER}-read"
PASS="${OWNER}-1"                # staging-only credential; the predecessor's staging/README.md
OWNER_ENV="$(echo "${OWNER}" | tr 'a-z-' 'A-Z_')"

# forgejo CLI must run as the in-container git user
fcli() { docker compose exec -T forgejo su git -c "$*"; }

if ! fcli "forgejo admin user list" | awk 'NR>1 {print $2}' | grep -qx "${OWNER}"; then
  fcli "forgejo admin user create --username ${OWNER} \
        --password ${PASS} --email ${OWNER}@gsj.invalid --must-change-password=false"
  echo "created user ${OWNER}"
fi

# A token is valid iff /api/v1/user answers as this owner (needs read:user in
# scope, so the read token below is minted read:repository,read:user).
token_ok() {
  [ -f "$1" ] && curl -fsS -H "Authorization: token $(cat "$1")" \
    "${HOST}/api/v1/user" 2>/dev/null | grep -q "\"login\":\"${OWNER}\""
}

# $1 file, $2 scopes, $3 human label
mint() {
  if token_ok "$1"; then
    echo "existing $3 token for ${OWNER} still valid"
    return
  fi
  # token names must be unique per user; suffix so re-bootstraps never collide
  local name="$3-$(date +%s)"
  fcli "forgejo admin user generate-access-token --username ${OWNER} \
        --token-name ${name} --scopes $2 --raw" | tr -d '[:space:]' > "$1"
  chmod 600 "$1"
  token_ok "$1" || { echo "$3 token creation failed" >&2; exit 1; }
  echo "created $3 token ${name} -> estate/forgejo/$1"
}

mint "${TOKEN_FILE}"      "write:repository,write:user" "corpus-pipeline"
mint "${READ_TOKEN_FILE}" "read:repository,read:user"   "sandbox-read"

echo "owner ${OWNER} ready:"
echo "  export GSJ_FORGEJO_TOKEN_${OWNER_ENV}=\$(cat estate/forgejo/${TOKEN_FILE})       # pipeline pushes"
echo "  export GSJ_FORGEJO_READ_TOKEN_${OWNER_ENV}=\$(cat estate/forgejo/${READ_TOKEN_FILE})  # rollout clone_credential_env"
