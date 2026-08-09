#!/usr/bin/env bash
# Create a pipeline OWNER user on the staging Forgejo + issue its push token
# (CP-33, ADR-0046(e)/ADR-0047). Idempotent: existing users are kept, a
# still-valid token is kept. Run on the H200 after up.sh.
#
#   ./create_owner.sh gsj-staging     # the staging corpus owner
#   ./create_owner.sh gsj-prod        # the prod owner (created empty at
#                                     #   CP-33 — the switch is one value)
#
# The token lands in .token-<owner> (gitignored, 0600). The pipeline reads
# it from the env var the contract derives from the owner name:
#   export GSJ_FORGEJO_TOKEN_GSJ_STAGING="$(cat .token-gsj-staging)"
#   export GSJ_FORGEJO_TOKEN_GSJ_PROD="$(cat .token-gsj-prod)"
set -euo pipefail
cd "$(dirname "$0")"

OWNER="${1:?usage: create_owner.sh <owner> (gsj-staging | gsj-prod)}"
HOST="http://172.28.9.10:3000"   # static container IP — no published ports
TOKEN_FILE=".token-${OWNER}"
PASS="${OWNER}-1"                # staging-only credential; the predecessor's staging/README.md

# forgejo CLI must run as the in-container git user
fcli() { docker compose exec -T forgejo su git -c "$*"; }

if ! fcli "forgejo admin user list" | awk 'NR>1 {print $2}' | grep -qx "${OWNER}"; then
  fcli "forgejo admin user create --username ${OWNER} \
        --password ${PASS} --email ${OWNER}@gsj.invalid --must-change-password=false"
  echo "created user ${OWNER}"
fi

token_ok() {
  [ -f "${TOKEN_FILE}" ] && curl -fsS \
    -H "Authorization: token $(cat "${TOKEN_FILE}")" \
    "${HOST}/api/v1/user" 2>/dev/null | grep -q "\"login\":\"${OWNER}\""
}

if token_ok; then
  echo "existing token for ${OWNER} still valid"
else
  # token names must be unique per user; suffix so re-bootstraps never collide
  TOKEN_NAME="corpus-pipeline-$(date +%s)"
  fcli "forgejo admin user generate-access-token --username ${OWNER} \
        --token-name ${TOKEN_NAME} --scopes write:repository,write:user --raw" \
    | tr -d '[:space:]' > "${TOKEN_FILE}"
  chmod 600 "${TOKEN_FILE}"
  token_ok || { echo "token creation failed" >&2; exit 1; }
  echo "created access token ${TOKEN_NAME} -> forgejo/${TOKEN_FILE}"
fi

echo "owner ${OWNER} ready; export GSJ_FORGEJO_TOKEN_$(echo "${OWNER}" | tr 'a-z-' 'A-Z_')=\$(cat forgejo/${TOKEN_FILE})"
