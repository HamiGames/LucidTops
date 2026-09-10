#!/bin/sh
# LucidTops sessions container entrypoint.
# Order: pull hardware → bind env → write sessions.secrets → start uvicorn.
set -eu

SESSIONS_DIR="${LUCID_PROJECT_ROOT:-/app}/sessions"
BACKEND_DIR="${LUCID_PROJECT_ROOT:-/app}/backend"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${BACKEND_DIR}:${SESSIONS_DIR}:${PYTHONPATH:-}"

ENV_FILE="$(mktemp)"
python "${SESSIONS_DIR}/sessions_pull_information.py" > "${ENV_FILE}"
# shellcheck disable=SC1090
. "${ENV_FILE}"
rm -f "${ENV_FILE}"

python -c "from Config_sessions import write_session_secrets; write_session_secrets(force=False)"

if [ -z "${SESSIONS_BIND_HOST:-}" ] || [ -z "${SESSIONS_BIND_PORT:-}" ]; then
  echo "SESSIONS_BIND_HOST and SESSIONS_BIND_PORT must be set at time of operation" >&2
  exit 1
fi

exec uvicorn --factory sessions.app:create_app \
  --host "${SESSIONS_BIND_HOST}" \
  --port "${SESSIONS_BIND_PORT}" \
  --proxy-headers
