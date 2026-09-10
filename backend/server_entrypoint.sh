#!/bin/bash
# backend/server_entrypoint.sh — Server.dockerfile container entrypoint
# 1) Pull real-world hardware facts at time of operation (IP, MAC, mounts, DockerDNS)
# 2) Run builderMasterServer.py at operation time (produces server.secrets; consumes Master.secrets)
# 3) Source secrets (no placeholders — values generated/pulled at operation time)
# 4) Start uvicorn FastAPI master server (Proxy owns Tor/nginx; ProxyGate reaches this bind)

set -euo pipefail

cd /app/backend

PULL_ENV="$(mktemp)"
python pull_information.py > "${PULL_ENV}"
# shellcheck disable=SC1090
set -a
source "${PULL_ENV}"
set +a
rm -f "${PULL_ENV}"

: "${LUCID_TOPS_ROOT:?entrypoint: LUCID_TOPS_ROOT missing after hardware pull}"
: "${SECRETS_DIR:?entrypoint: SECRETS_DIR missing after hardware pull}"

SERVER_SECRETS="${SERVER_SECRETS_FILE:-}"
CONFIG_SECRETS="${CONFIG_SECRETS_FILE:-}"
OPERATIONS_SECRETS="${OPERATIONS_SECRETS_FILE:-}"
SECRETS_ENV="${SECRETS_ENV_FILE:-}"
MASTER_SECRETS="${MASTER_SECRETS_FILE:-}"
RUN_BUILDER_ON_START="${RUN_BUILDER_ON_START:-true}"

mkdir -p "${LUCID_TOPS_ROOT}" \
         "${SECRETS_DIR}" \
         "${LUCID_TOPS_ROOT}/configs" \
         "${LUCID_TOPS_ROOT}/logs"

_source_secrets_if_present() {
  local path="$1"
  if [ -n "${path}" ] && [ -f "${path}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${path}"
    set +a
  fi
}

# Proxy-synced Master.secrets first (Tor/SOCKS/onion/ProxyGate tokens)
_source_secrets_if_present "${MASTER_SECRETS}"

if [ "${RUN_BUILDER_ON_START}" = "true" ] || [ ! -f "${SERVER_SECRETS}" ]; then
  echo "entrypoint: running builderMasterServer.py (operation-time secrets generation)"
  python builderMasterServer.py
fi

_source_secrets_if_present "${SECRETS_ENV}"
_source_secrets_if_present "${MASTER_SECRETS}"
_source_secrets_if_present "${SERVER_SECRETS}"
_source_secrets_if_present "${CONFIG_SECRETS}"
_source_secrets_if_present "${OPERATIONS_SECRETS}"

MONGODB_SECRETS="${MONGODB_SECRETS_FILE:-}"
DATABASES_SECRETS="${DATABASES_SECRETS_FILE:-}"
BLOCKCHAIN_SECRETS="${BLOCKCHAIN_SECRETS_FILE:-}"
PAYMENTS_SECRETS="${PAYMENTS_SECRETS_FILE:-}"
BACKEND_SECRETS="${BACKEND_SECRETS_FILE:-}"
_source_secrets_if_present "${MONGODB_SECRETS}"
_source_secrets_if_present "${DATABASES_SECRETS}"
_source_secrets_if_present "${BLOCKCHAIN_SECRETS}"
_source_secrets_if_present "${PAYMENTS_SECRETS}"
_source_secrets_if_present "${BACKEND_SECRETS}"

if [ -z "${SERVER_SECRETS}" ] || [ ! -f "${SERVER_SECRETS}" ]; then
  echo "entrypoint: error — server.secrets was not produced" >&2
  exit 2
fi

: "${MASTER_SERVER_BIND_HOST:?entrypoint: MASTER_SERVER_BIND_HOST required (from pull/secrets)}"
: "${MASTER_SERVER_PORT:?entrypoint: MASTER_SERVER_PORT required (from pull/secrets)}"
: "${LOG_LEVEL:?entrypoint: LOG_LEVEL required from secrets}"

BIND_HOST="${MASTER_SERVER_BIND_HOST}"
PORT="${MASTER_SERVER_PORT}"

echo "entrypoint: starting uvicorn MasterServer -> ${BIND_HOST}:${PORT} (Proxy-mediated Tor)"
exec python -m uvicorn main:create_app \
  --factory \
  --host "${BIND_HOST}" \
  --port "${PORT}" \
  --log-level "${LOG_LEVEL}"
