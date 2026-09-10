#!/bin/sh
# Blockchain container entrypoint: pull hardware -> secrets -> build -> serve FastAPI.
set -eu

cd /app/blockchain

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
