#!/bin/sh
# LucidTops operations container entrypoint.
# operations.secrets is created at image build (/app/secrets/operations.secrets).
# This script only reads that file and starts uvicorn.
set -eu

OPS_DIR="${LUCID_PROJECT_ROOT:-/app}/operations"
BACKEND_DIR="${LUCID_PROJECT_ROOT:-/app}/backend"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${BACKEND_DIR}:${OPS_DIR}:${PYTHONPATH:-}"
export SECRETS_DIR="${SECRETS_DIR:-/app/secrets}"
export OPERATIONS_SECRETS_FILE="${OPERATIONS_SECRETS_FILE:-/app/secrets/operations.secrets}"

if [ ! -s "${OPERATIONS_SECRETS_FILE}" ]; then
  echo "operations.secrets missing inside the image — ${OPERATIONS_SECRETS_FILE}" >&2
  exit 1
fi

BIND_ENV="$(python -c '
import json
import shlex
import sys

from operations_secrets import confirm_operations_blockchain_targets, load_operations_secrets

data = load_operations_secrets(reload=True)
result = confirm_operations_blockchain_targets()
print(json.dumps(result, default=str), file=sys.stderr)
if not result.get("confirmed"):
    sys.exit(1)
for key in ("OPERATIONS_BIND_HOST", "OPERATIONS_BIND_PORT"):
    value = str(data.get(key) or "").strip()
    if not value:
        print(f"{key} missing from in-image operations.secrets", file=sys.stderr)
        sys.exit(1)
    print(f"export {key}={shlex.quote(value)}")
')"
# shellcheck disable=SC2086
eval "$BIND_ENV"

exec uvicorn --factory operations.app:create_app \
  --host "${OPERATIONS_BIND_HOST}" \
  --port "${OPERATIONS_BIND_PORT}" \
  --proxy-headers
