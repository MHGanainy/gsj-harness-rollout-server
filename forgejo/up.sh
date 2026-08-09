#!/usr/bin/env bash
# Idempotent, headless staging-Forgejo bootstrap (the CP-02 up.sh recipe on
# staging names/port): container up, health wait, admin user, API token.
# No install wizard (INSTALL_LOCK via environment). Safe to re-run: every
# step checks before it creates.
set -euo pipefail
cd "$(dirname "$0")"

HOST="http://172.28.9.10:3000"   # static container IP — no published ports
ADMIN_USER="gsj-admin"
ADMIN_PASS="gsj-staging-1"      # staging-only credential; the predecessor's staging/README.md
ADMIN_EMAIL="gsj-admin@gsj.invalid"
TOKEN_FILE=".token"             # gitignored

docker compose up -d

echo "waiting for Forgejo at ${HOST} ..."
for i in $(seq 1 90); do
  if curl -fsS "${HOST}/api/healthz" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "Forgejo did not become healthy within 90s" >&2
    exit 1
  fi
  sleep 1
done

# forgejo CLI must run as the in-container git user
fcli() { docker compose exec -T forgejo su git -c "$*"; }

if ! fcli "forgejo admin user list" | awk 'NR>1 {print $2}' | grep -qx "${ADMIN_USER}"; then
  fcli "forgejo admin user create --admin --username ${ADMIN_USER} \
        --password ${ADMIN_PASS} --email ${ADMIN_EMAIL} --must-change-password=false"
  echo "created admin user ${ADMIN_USER}"
fi

token_ok() {
  [ -f "${TOKEN_FILE}" ] && curl -fsS \
    -H "Authorization: token $(cat "${TOKEN_FILE}")" \
    "${HOST}/api/v1/user" >/dev/null 2>&1
}

if token_ok; then
  echo "existing token still valid"
else
  # token names must be unique per user; suffix so re-bootstraps never collide
  TOKEN_NAME="gsj-staging-$(date +%s)"
  fcli "forgejo admin user generate-access-token --username ${ADMIN_USER} \
        --token-name ${TOKEN_NAME} --scopes write:repository,write:user --raw" \
    | tr -d '[:space:]' > "${TOKEN_FILE}"
  chmod 600 "${TOKEN_FILE}"
  token_ok || { echo "token creation failed" >&2; exit 1; }
  echo "created access token ${TOKEN_NAME}"
fi

echo "Forgejo ready at ${HOST} (admin: ${ADMIN_USER}, token: forgejo/${TOKEN_FILE})"
