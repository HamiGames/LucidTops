#!/bin/bash
# infrastructure/containers/lucid-server-default/entrypoint.sh
# Start Tor (in-container hidden service) then FastAPI master server.

set -euo pipefail

TORRC="${HOST_TOR_CONFIG_TORRC:-/mnt/myssd/LucidTops/torrc}"
SECRETS_ENV="${SECRETS_ENV_FILE:-/mnt/myssd/LucidTops/secrets.env}"

if [ -f "${SECRETS_ENV}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${SECRETS_ENV}"
  set +a
fi

mkdir -p /app/var/lib/tor/lucid_server \
         /app/var/lib/tor/lucid_portal \
         /app/var/lib/tor/lucid_node \
         /app/run/lucid/onion

if [ -f "${TORRC}" ]; then
  echo "entrypoint: starting tor with ${TORRC}"
  tor -f "${TORRC}" &
  sleep 5
  for svc in lucid_server lucid_portal lucid_node; do
    hostname_file="/app/var/lib/tor/${svc}/hostname"
    if [ -f "${hostname_file}" ]; then
      onion="$(tr -d '[:space:]' < "${hostname_file}")"
      echo "${onion}" > "/app/run/lucid/onion/${svc}.onion"
    fi
  done
else
  echo "entrypoint: warning — torrc not found at ${TORRC}; API will not be reachable via *.onion"
fi

BIND_HOST="${MASTER_SERVER_BIND_HOST:-127.0.0.1}"
PORT="${MASTER_SERVER_PORT:-8080}"

cd /app/backend
exec python -m uvicorn main:create_app \
  --factory \
  --host "${BIND_HOST}" \
  --port "${PORT}" \
  --log-level "${LOG_LEVEL:-info}"
