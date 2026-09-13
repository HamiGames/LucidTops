#!/bin/sh
# LucidTops blockchain container entrypoint.
# Order:
#   1) bind Server/Secrets seed paths (Master.secrets + proxy.secrets) for onion/network
#   2) pull hardware + seed Docker network / *.onion into env
#   3) write blockchain/secrets/blockchain.secrets
#   4) build/serve FastAPI
set -eu

cd /app/blockchain

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

# Blockchain write target (never Server/Secrets)
export SECRETS_DIR="${SECRETS_DIR:-${LUCID_TOPS_ROOT}/blockchain/secrets}"
export BLOCKCHAIN_SECRETS_FILE="${BLOCKCHAIN_SECRETS_FILE:-${SECRETS_DIR}/blockchain.secrets}"
mkdir -p "${SECRETS_DIR}"

if [ ! -f "${MASTER_SECRETS_FILE}" ] && [ ! -f "${PROXY_SECRETS_FILE}" ]; then
  echo "blockchain seed warning: neither Master.secrets nor proxy.secrets found under ${SERVER_SECRETS_DIR}" >&2
  echo "  expected: ${MASTER_SECRETS_FILE}" >&2
  echo "  expected: ${PROXY_SECRETS_FILE}" >&2
fi

echo "blockchain-entrypoint: pulling hardware and writing secrets"
python pull_information.py >/tmp/blockchain_pull.env || true
# shellcheck disable=SC1091
if [ -f /tmp/blockchain_pull.env ]; then
  # Export KEY=VALUE lines produced by pull_information
  eval "$(python -c "
import os, re, sys
from pathlib import Path
text = Path('/tmp/blockchain_pull.env').read_text(encoding='utf-8', errors='replace')
for line in text.splitlines():
    line=line.strip()
    if line.startswith('export '):
        print(line)
") "
fi

python -c "from blockchain_secrets import ensure_blockchain_secrets; print(ensure_blockchain_secrets())"

if [ -z "${BLOCKCHAIN_SECRETS_FILE:-}" ] || [ ! -f "${BLOCKCHAIN_SECRETS_FILE}" ]; then
  echo "BLOCKCHAIN_SECRETS_FILE missing after write — ${BLOCKCHAIN_SECRETS_FILE:-unset}" >&2
  exit 1
fi

# Refresh onion + network from written blockchain.secrets (seeded from Master/proxy).
DOCKER_NETWORK_NAME="$(grep -E '^DOCKER_NETWORK_NAME=' "${BLOCKCHAIN_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
BLOCKCHAIN_ONION="$(grep -E '^BLOCKCHAIN_ONION=' "${BLOCKCHAIN_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
MASTER_SERVER_ONION="$(grep -E '^MASTER_SERVER_ONION=' "${BLOCKCHAIN_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
NODEUSER_ONION="$(grep -E '^NODEUSER_ONION=' "${BLOCKCHAIN_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
ADMIN_ONION="$(grep -E '^ADMIN_ONION=' "${BLOCKCHAIN_SECRETS_FILE}" | head -1 | cut -d= -f2-)"
export DOCKER_NETWORK_NAME BLOCKCHAIN_ONION MASTER_SERVER_ONION NODEUSER_ONION ADMIN_ONION

if [ -z "${DOCKER_NETWORK_NAME:-}" ]; then
  echo "DOCKER_NETWORK_NAME missing in ${BLOCKCHAIN_SECRETS_FILE} — seed Master.secrets/proxy.secrets first" >&2
  exit 1
fi

COMMAND="${1:-serve}"
shift || true

case "$COMMAND" in
  build)
    exec python BuildBlockSystem.py build "$@"
    ;;
  run|start)
    python BuildBlockSystem.py run "$@"
    exec python ConnectBlockRoutes.py serve
    ;;
  serve)
    python BuildBlockSystem.py run || true
    python -c "from distribution import start_distribution_daemon; print(start_distribution_daemon())" || true
    exec python ConnectBlockRoutes.py serve
    ;;
  status)
    exec python BuildBlockSystem.py status
    ;;
  *)
    exec python BuildBlockSystem.py "$COMMAND" "$@"
    ;;
esac
