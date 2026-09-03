#!/bin/bash
# infrastructure/containers/lucid-server-default/entrypoint.sh
# Start Tor (in-container hidden service) then FastAPI master server.

set -euo pipefail

TORRC="${HOST_TOR_CONFIG_TORRC:-/mnt/myssd/LucidTops/torrc}"
SECRETS_ENV="${SECRETS_ENV_FILE:-/mnt/myssd/LucidTops/secrets.env}"
CONFIG_SECRETS="${CONFIG_SECRETS_FILE:-/mnt/myssd/LucidTops/secrets/config.secrets}"
OPERATIONS_SECRETS="${OPERATIONS_SECRETS_FILE:-/mnt/myssd/LucidTops/secrets/operations.secrets}"

_source_secrets_if_present() {
  local path="$1"
  if [ -f "${path}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${path}"
    set +a
  fi
}

if [ -f "${SECRETS_ENV}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${SECRETS_ENV}"
  set +a
fi

if [ -f "${CONFIG_SECRETS}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG_SECRETS}"
  set +a
fi

if [ -f "${OPERATIONS_SECRETS}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${OPERATIONS_SECRETS}"
  set +a
fi

SECRETS_DIR="${SECRETS_DIR:-/mnt/myssd/LucidTops/secrets}"
MONGODB_SECRETS="${MONGODB_SECRETS_FILE:-${SECRETS_DIR}/mongodb.secrets}"
BLOCKCHAIN_SECRETS="${BLOCKCHAIN_SECRETS_FILE:-${SECRETS_DIR}/blockchain.secrets}"
PAYMENTS_SECRETS="${PAYMENTS_SECRETS_FILE:-${SECRETS_DIR}/payments.secrets}"

_source_secrets_if_present "${MONGODB_SECRETS}"
_source_secrets_if_present "${BLOCKCHAIN_SECRETS}"
_source_secrets_if_present "${PAYMENTS_SECRETS}"

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
