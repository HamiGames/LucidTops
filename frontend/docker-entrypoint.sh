#!/bin/sh
# Frontend container entrypoint — pull + secrets + runtime config + nginx at time of operation.
set -eu

cd /opt/lucid/frontend

export FRONTEND_WEBPAGE_ROOT="${FRONTEND_WEBPAGE_ROOT:-/opt/lucid/frontend/webpage}"
export FRONTEND_NGINX_CONF_DIR="${FRONTEND_NGINX_CONF_DIR:-/opt/lucid/frontend/nginx}"

python3 bootstrap_frontend.py

CONF="${FRONTEND_NGINX_CONF_DIR}/frontend.conf"
if [ ! -f "$CONF" ]; then
  echo "frontend nginx conf missing after bootstrap — abort" >&2
  exit 1
fi

# Prefer generated conf; fall back to daemon-off foreground nginx
exec nginx -g "daemon off;" -c "$CONF"
