# LucidTops blockchain — FastAPI/DockerDNS core ledger container (fixes.txt §6 / §16).
# Image tag: lucid-blockchain:v1.0.0
# Called via MasterServer, NodeUser, AdminUser, MasterClassUser, and User.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES="ca-certificates curl iproute2"
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/blockchain/Blockchain.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-blockchain:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (§16.1) — created at time of operation (not baked into the image):
#   SECRETS_DIR=/mnt/myssd/LucidTops/blockchain/secrets
#   Seed (onion + DOCKER_NETWORK_NAME only — fixes.txt §19):
#     /mnt/myssd/LucidTops/Server/Secrets/Master.secrets
#     /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
#   Entrypoint: pull_information → ensure_blockchain_secrets → BuildBlockSystem → ConnectBlockRoutes
#   If empty: write blockchain.secrets from Master/proxy seed + live hardware pull.
#   Host mount required: -v /mnt/myssd/LucidTops:/mnt/myssd/LucidTops
#   Ledger replica (external): /mnt/myssd/LucidTops/Databases/LucidTopsBlockchain_Ledger
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; bind addresses come from hardware pull → blockchain.secrets.
# - no sensitive data in this image; data lives in the secrets file on the SSD mount.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.

# -----------------------------------------------------------------------------
# Build-args (declared before FROM for BASE_IMAGE; re-declared after FROM for use)
# -----------------------------------------------------------------------------
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# Runtime / install args (NOT used in COPY source paths)
# ca-certificates/curl/iproute2: listed in blockchain/requirements.txt (not assumed present — §16.6)
ARG APT_PACKAGES="ca-certificates curl iproute2"
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/blockchain/secrets
ARG BLOCKCHAIN_SECRETS_FILE=/mnt/myssd/LucidTops/blockchain/secrets/blockchain.secrets
ARG BLOCKCHAIN_CONFIGS_DIR=/mnt/myssd/LucidTops/blockchain/configs
ARG LEDGER_REPLICA_DIR=/mnt/myssd/LucidTops/Databases/LucidTopsBlockchain_Ledger
ARG RUN_BLOCKCHAIN_PULL_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/blockchain \
      /app/blockchain/run \
      /app/blockchain/configs \
      /app/blockchain/logs \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${BLOCKCHAIN_CONFIGS_DIR}" \
      "${LEDGER_REPLICA_DIR}" \
      "${LUCID_TOPS_ROOT}/blockchain" \
      "${LUCID_TOPS_ROOT}/logs/blockchain" \
      "${LUCID_TOPS_ROOT}/run/blockchain"; \
    test -d /app/blockchain; \
    test -d /app/blockchain/run; \
    test -d /app/blockchain/configs; \
    test -d /app/blockchain/logs; \
    test -d "${SECRETS_DIR}"; \
    test -d "${LEDGER_REPLICA_DIR}"; \
    test -d "${LUCID_TOPS_ROOT}"

# -----------------------------------------------------------------------------
# OS packages
# -----------------------------------------------------------------------------
RUN set -eu; \
    if [ -n "${APT_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
    fi

# -----------------------------------------------------------------------------
# Pip wheel installer + requirements (literal COPY — no ARG in source path)
# -----------------------------------------------------------------------------
COPY blockchain/requirements.txt /app/blockchain/requirements.txt
RUN set -eu; \
    test -s /app/blockchain/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/blockchain/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, pymongo"

# -----------------------------------------------------------------------------
# Copy blockchain package, then validate (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY blockchain/ /app/blockchain/

RUN set -eu; \
    test -f /app/blockchain/docker-entrypoint.sh; \
    test -f /app/blockchain/Blockchain-core.py; \
    test -f /app/blockchain/pull_information.py; \
    test -f /app/blockchain/blockchain_secrets.py; \
    test -f /app/blockchain/BuildBlockSystem.py; \
    test -f /app/blockchain/ConnectBlockRoutes.py; \
    test -f /app/blockchain/distribution.py; \
    test -f /app/blockchain/configBlock.py; \
    test -f /app/blockchain/CreateBlock.py; \
    test -f /app/blockchain/blockchain_schema.py; \
    test -f /app/blockchain/chunker.py; \
    test -f /app/blockchain/DataInsert.py; \
    test -s /app/blockchain/requirements.txt; \
    test -f /app/blockchain/Blockchain.dockerfile; \
    test -d /app/blockchain/run; \
    test -d /app/blockchain/configs; \
    test -d /app/blockchain/logs; \
    test -d "${SECRETS_DIR}"; \
    test -d "${LEDGER_REPLICA_DIR}"; \
    chmod +x /app/blockchain/docker-entrypoint.sh \
      /app/blockchain/pull_information.py \
      /app/blockchain/BuildBlockSystem.py \
      /app/blockchain/ConnectBlockRoutes.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app:/app/blockchain
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV BLOCKCHAIN_SECRETS_FILE=${BLOCKCHAIN_SECRETS_FILE}
ENV BLOCKCHAIN_CONFIGS_DIR=${BLOCKCHAIN_CONFIGS_DIR}
ENV LEDGER_REPLICA_DIR=${LEDGER_REPLICA_DIR}

# Optional blockchain pull + secrets write at build (default false — SSD/hardware at first start)
RUN set -eu; \
    if [ "${RUN_BLOCKCHAIN_PULL_ON_BUILD}" = "true" ]; then \
      python3 /app/blockchain/pull_information.py >/dev/null; \
      python3 -c "from blockchain_secrets import ensure_blockchain_secrets; print(ensure_blockchain_secrets())"; \
    fi

WORKDIR /app/blockchain
ENTRYPOINT ["/app/blockchain/docker-entrypoint.sh"]
CMD ["serve"]
