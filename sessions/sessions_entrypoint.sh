#!/bin/sh
# LucidTops sessions container entrypoint.
# Order:
#   1) bind Server/Secrets seed paths (Master.secrets + proxy.secrets)
#   2) pull hardware + seed DockerDNS/network into env
#   3) write sessions/secrets/sessions.secrets
#   4) start uvicorn
set -eu

SESSIONS_DIR="${LUCID_PROJECT_ROOT:-/app}/sessions"
BACKEND_DIR="${LUCID_PROJECT_ROOT:-/app}/backend"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${BACKEND_DIR}:${SESSIONS_DIR}:${PYTHONPATH:-}"

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

# Sessions write target (never Server/Secrets)
export SECRETS_DIR="${SECRETS_DIR:-${LUCID_TOPS_ROOT}/sessions/secrets}"
export SESSIONS_SECRETS_FILE="${SESSIONS_SECRETS_FILE:-${SECRETS_DIR}/sessions.secrets}"
mkdir -p "${SECRETS_DIR}"

if [ ! -f "${MASTER_SECRETS_FILE}" ] && [ ! -f "${PROXY_SECRETS_FILE}" ]; then
  echo "sessions seed warning: neither Master.secrets nor proxy.secrets found under ${SERVER_SECRETS_DIR}" >&2
  echo "  expected: ${MASTER_SECRETS_FILE}" >&2
  echo "  expected: ${PROXY_SECRETS_FILE}" >&2
fi

ENV_FILE="$(mktemp)"
python "${SESSIONS_DIR}/sessions_pull_information.py" > "${ENV_FILE}"
# shellcheck disable=SC1090
. "${ENV_FILE}"
rm -f "${ENV_FILE}"

python -c "from Config_sessions import write_session_secrets; write_session_secrets(force=False)"

if [ -z "${SESSIONS_SECRETS_FILE:-}" ] || [ ! -f "${SESSIONS_SECRETS_FILE}" ]; then
  echo "SESSIONS_SECRETS_FILE missing after write — ${SESSIONS_SECRETS_FILE:-unset}" >&2
  exit 1
fi

# Refresh bind + network from written sessions.secrets (seeded from Master/proxy).
SESSIONS_BIND_HOST="$(grep -E '^SESSIONS_BIND_HOST=' "${SESSIONS_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
SESSIONS_BIND_PORT="$(grep -E '^SESSIONS_BIND_PORT=' "${SESSIONS_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
DOCKER_NETWORK_NAME="$(grep -E '^DOCKER_NETWORK_NAME=' "${SESSIONS_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
export SESSIONS_BIND_HOST SESSIONS_BIND_PORT DOCKER_NETWORK_NAME

if [ -z "${SESSIONS_BIND_HOST:-}" ] || [ -z "${SESSIONS_BIND_PORT:-}" ]; then
  echo "SESSIONS_BIND_HOST and SESSIONS_BIND_PORT must be set at time of operation" >&2
  exit 1
fi

if [ -z "${DOCKER_NETWORK_NAME:-}" ]; then
  echo "DOCKER_NETWORK_NAME missing in ${SESSIONS_SECRETS_FILE} — seed Master.secrets/proxy.secrets first" >&2
  exit 1
fi

exec uvicorn --factory sessions.app:create_app \
  --host "${SESSIONS_BIND_HOST}" \
  --port "${SESSIONS_BIND_PORT}" \
  --proxy-headers
