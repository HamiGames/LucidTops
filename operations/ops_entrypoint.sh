#!/bin/sh
# LucidTops operations container entrypoint.
# Order: pull hardware → bind env → start uvicorn (values created at time of operation).
set -eu

OPS_DIR="${LUCID_PROJECT_ROOT:-/app}/operations"
BACKEND_DIR="${LUCID_PROJECT_ROOT:-/app}/backend"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${BACKEND_DIR}:${OPS_DIR}:${PYTHONPATH:-}"

ENV_FILE="$(mktemp)"
python "${OPS_DIR}/ops_pull_information.py" > "${ENV_FILE}"
# shellcheck disable=SC1090
. "${ENV_FILE}"
rm -f "${ENV_FILE}"

if [ -z "${OPERATIONS_BIND_HOST:-}" ] || [ -z "${OPERATIONS_BIND_PORT:-}" ]; then
  echo "OPERATIONS_BIND_HOST and OPERATIONS_BIND_PORT must be set at time of operation" >&2
  exit 1
fi

exec uvicorn --factory operations.app:create_app \
  --host "${OPERATIONS_BIND_HOST}" \
  --port "${OPERATIONS_BIND_PORT}" \
  --proxy-headers
