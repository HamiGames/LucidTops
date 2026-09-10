#!/bin/sh
# LucidTops PaySystems container entrypoint.
# Order: load secrets from mounted LucidTops → start uvicorn factory.
set -eu

PAY_DIR="${LUCID_PROJECT_ROOT:-/app}/PaySystems"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${PAY_DIR}:${PYTHONPATH:-}"
export LUCID_TOPS_ROOT="${LUCID_TOPS_ROOT:-/mnt/myssd/LucidTops}"

if [ -z "${PAYSYSTEMS_BIND_HOST:-}" ] || [ -z "${PAYSYSTEMS_BIND_PORT:-}" ]; then
  echo "PAYSYSTEMS_BIND_HOST and PAYSYSTEMS_BIND_PORT must be set at time of operation" >&2
  exit 1
fi

exec uvicorn --factory PayRoutes:create_pay_container_app \
  --app-dir "${PAY_DIR}" \
  --host "${PAYSYSTEMS_BIND_HOST}" \
  --port "${PAYSYSTEMS_BIND_PORT}" \
  --proxy-headers
