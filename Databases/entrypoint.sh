#!/bin/sh
# LucidTops Databases orchestrator entrypoint — values from hardware pull at operation time.
# DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

set -eu

cd /app/Databases

PULL_ENV="${DATABASES_PULL_ENV_FILE:-/tmp/databases_pull.env}"
python pull_information.py > "${PULL_ENV}"
# shellcheck disable=SC1090
. "${PULL_ENV}"

if [ "${RUN_DATABASES_BOOTSTRAP_ON_START:-true}" = "true" ]; then
  python BootstrapDatabases.py
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec python LaunchDatabases.py --status-only
