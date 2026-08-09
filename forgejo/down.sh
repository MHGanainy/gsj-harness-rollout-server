#!/usr/bin/env bash
# Idempotent teardown. Instance data persists in forgejo/forgejo-data/
# (gitignored) so up.sh restores the same state; pass --wipe to also delete
# the data directory and the API token. Wiping and re-pushing reproduces the
# identical frozen dataset (deterministic bares — the corpus pipeline
# re-scaffolds them; corpus/staging/corpus.lock.json is the freeze record).
set -euo pipefail
cd "$(dirname "$0")"

docker compose down --remove-orphans

if [ "${1:-}" = "--wipe" ]; then
  if [ -d ./forgejo-data ] && ! rm -rf ./forgejo-data 2>/dev/null; then
    # on Linux hosts the container chowns the bind mount to its own UID;
    # delete with the same image rather than requiring sudo
    docker run --rm --entrypoint /bin/sh \
      -v "$(pwd)/forgejo-data:/wipe" \
      codeberg.org/forgejo/forgejo:16.0.2 \
      -c 'rm -rf /wipe/* /wipe/.[!.]*' 2>/dev/null || true
    rmdir ./forgejo-data 2>/dev/null || rm -rf ./forgejo-data
  fi
  rm -f .token
  echo "wiped forgejo-data and token"
fi
