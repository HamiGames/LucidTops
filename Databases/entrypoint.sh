#!/bin/sh
# LucidTops Databases orchestrator entrypoint.
# Order:
#   1) bind Server/Secrets seed paths (Master.secrets + proxy.secrets)
#   2) pull hardware + seed DockerDNS/network into env
#   3) BootstrapDatabases → write Databases/secrets/*.secrets
#   4) status / optional command
# DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

set -eu

cd /app/Databases

LUCID_TOPS_ROOT="${LUCID_TOPS_ROOT:-/mnt/myssd/LucidTops}"
export LUCID_TOPS_ROOT

# Seed sources (Proxy Bootstrap → Server/Secrets). Accept Proxy.secrets or proxy.secrets.
SERVER_SECRETS_DIR="${MASTER_SECRETS_DIR:-${SERVER_SECRETS_DIR:-${LUCID_TOPS_ROOT}/Server/Secrets}}"
export SERVER_SECRETS_DIR
export MASTER_SECRETS_DIR="${MASTER_SECRETS_DIR:-${SERVER_SECRETS_DIR}}"
export MASTER_SECRETS_FILE="${MASTER_SECRETS_FILE:-${SERVER_SECRETS_DIR}/Master.secrets}"
if [ -z "${PROXY_SECRETS_FILE:-}" ]; then
  if [ -f "${SERVER_SECRETS_DIR}/proxy.secrets" ]; then
    PROXY_SECRETS_FILE="${SERVER_SECRETS_DIR}/proxy.secrets"
  elif [ -f "${SERVER_SECRETS_DIR}/Proxy.secrets" ]; then
    PROXY_SECRETS_FILE="${SERVER_SECRETS_DIR}/Proxy.secrets"
  else
    PROXY_SECRETS_FILE="${SERVER_SECRETS_DIR}/proxy.secrets"
  fi
fi
export PROXY_SECRETS_FILE

# Databases write target (never Server/Secrets)
export SECRETS_DIR="${SECRETS_DIR:-${LUCID_TOPS_ROOT}/Databases/secrets}"
export DATABASES_SECRETS_FILE="${DATABASES_SECRETS_FILE:-${SECRETS_DIR}/databases.secrets}"
export MONGODB_SECRETS_FILE="${MONGODB_SECRETS_FILE:-${SECRETS_DIR}/mongodb.secrets}"
mkdir -p "${SECRETS_DIR}"

if [ ! -f "${MASTER_SECRETS_FILE}" ] && [ ! -f "${PROXY_SECRETS_FILE}" ]; then
  echo "databases seed error: neither Master.secrets nor proxy.secrets found under ${SERVER_SECRETS_DIR}" >&2
  echo "  expected: ${MASTER_SECRETS_FILE}" >&2
  echo "  expected: ${PROXY_SECRETS_FILE}" >&2
  echo "  run Proxy/Bootstrap.py before starting lucid-databases-orchestrator" >&2
  exit 1
fi

PULL_ENV="${DATABASES_PULL_ENV_FILE:-/tmp/databases_pull.env}"
python pull_information.py > "${PULL_ENV}"
# shellcheck disable=SC1090
. "${PULL_ENV}"

if [ -z "${DOCKER_NETWORK_NAME:-}" ]; then
  echo "DOCKER_NETWORK_NAME missing after pull — seed Master.secrets/proxy.secrets first" >&2
  exit 1
fi

if [ "${RUN_DATABASES_BOOTSTRAP_ON_START:-true}" = "true" ]; then
  python BootstrapDatabases.py
fi

if [ -z "${DATABASES_SECRETS_FILE:-}" ] || [ ! -f "${DATABASES_SECRETS_FILE}" ]; then
  echo "DATABASES_SECRETS_FILE missing after bootstrap — ${DATABASES_SECRETS_FILE:-unset}" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec python LaunchDatabases.py --status-only
