#!/bin/sh
# LucidTops operations container entrypoint.
# Order: pull hardware → bind env → write operations.secrets → start uvicorn.
set -eu

OPS_DIR="${LUCID_PROJECT_ROOT:-/app}/operations"
BACKEND_DIR="${LUCID_PROJECT_ROOT:-/app}/backend"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${BACKEND_DIR}:${OPS_DIR}:${PYTHONPATH:-}"

ENV_FILE="$(mktemp)"
python "${OPS_DIR}/ops_pull_information.py" > "${ENV_FILE}"
# shellcheck disable=SC1090
. "${ENV_FILE}"
rm -f "${ENV_FILE}"

python -c "from operations_secrets import write_operations_secrets; write_operations_secrets(force=False)"
# Confirm DockerDNS targets + refuse serve if Master ledger write still allowed after genesis.
python -c "from operations_secrets import confirm_operations_blockchain_targets; import json; print(json.dumps(confirm_operations_blockchain_targets(), indent=2, default=str))"

if [ -z "${OPERATIONS_BIND_HOST:-}" ] || [ -z "${OPERATIONS_BIND_PORT:-}" ]; then
  echo "OPERATIONS_BIND_HOST and OPERATIONS_BIND_PORT must be set at time of operation" >&2
  exit 1
fi

if [ -z "${OPERATIONS_SECRETS_FILE:-}" ] || [ ! -f "${OPERATIONS_SECRETS_FILE}" ]; then
  echo "OPERATIONS_SECRETS_FILE missing after write — ${OPERATIONS_SECRETS_FILE:-unset}" >&2
  exit 1
fi

exec uvicorn --factory operations.app:create_app \
  --host "${OPERATIONS_BIND_HOST}" \
  --port "${OPERATIONS_BIND_PORT}" \
  --proxy-headers
