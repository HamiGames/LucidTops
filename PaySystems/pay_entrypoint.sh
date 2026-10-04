#!/bin/sh
# LucidTops PaySystems container entrypoint.
# payments.secrets is on the Pi console (Server/Secrets), written at image creation.
set -eu

PAY_DIR="${LUCID_PROJECT_ROOT:-/app}/PaySystems"
export PYTHONPATH="${LUCID_PROJECT_ROOT:-/app}:${PAY_DIR}:${PYTHONPATH:-}"
export LUCID_TOPS_ROOT="${LUCID_TOPS_ROOT:-/mnt/myssd/LucidTops}"
export SECRETS_DIR="${SECRETS_DIR:-/mnt/myssd/LucidTops/Server/Secrets}"
export PAYMENTS_SECRETS_FILE="${PAYMENTS_SECRETS_FILE:-${SECRETS_DIR}/payments.secrets}"
export HOST_TOR_CONFIG_TORRC="${HOST_TOR_CONFIG_TORRC:-${LUCID_TOPS_ROOT}/torrc}"

if [ ! -s "${PAYMENTS_SECRETS_FILE}" ]; then
  echo "payments.secrets missing on the console — ${PAYMENTS_SECRETS_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "${PAYMENTS_SECRETS_FILE}"
set +a

if [ -z "${PAYSYSTEMS_BIND_HOST:-}" ] || [ -z "${PAYSYSTEMS_BIND_PORT:-}" ]; then
  echo "PAYSYSTEMS_BIND_HOST and PAYSYSTEMS_BIND_PORT must be in payments.secrets (from Master.secrets or proxy.secrets)" >&2
  exit 1
fi

exec uvicorn --factory PayRoutes:create_pay_container_app \
  --app-dir "${PAY_DIR}" \
  --host "${PAYSYSTEMS_BIND_HOST}" \
  --port "${PAYSYSTEMS_BIND_PORT}" \
  --proxy-headers
