# LucidTops Databases orchestration — MongoDB containers per named DB (fixes.txt §11 / §16).
# Image tag: lucid-databases-orchestrator:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES="iproute2 ca-certificates curl gnupg"
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/Databases/Databases.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-databases-orchestrator:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Runtime (orchestrates sibling Mongo containers via host Docker daemon):
#   -v /mnt/myssd/LucidTops:/mnt/myssd/LucidTops
#   -v /var/run/docker.sock:/var/run/docker.sock
#
# Secrets (§16.1) — created at time of operation (not baked into the image):
#   SECRETS_DIR=/mnt/myssd/LucidTops/Databases/secrets
#   Seed: Server/Secrets/Master.secrets + proxy.secrets (Proxy Bootstrap)
#   Entrypoint: pull_information → BootstrapDatabases → LaunchDatabases
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC come from pull → databases secrets.
# - no sensitive data in this image; data lives in the secrets file on the SSD mount.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): join LucidDNS from Master.secrets; create tor/nontor DB nets as needed.
# Mongo data: host SSD bind mounts (Server/Databases / MONGODB_DATA_MOUNT) — not baked into image.

# -----------------------------------------------------------------------------
# Build-args (declared before FROM for BASE_IMAGE; re-declared after FROM for use)
# -----------------------------------------------------------------------------
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# Runtime / install args (NOT used in COPY source paths)
# iproute2: hardware pull (`ip`); curl/gnupg/ca-certificates: Docker CLI apt install
ARG APT_PACKAGES="iproute2 ca-certificates curl gnupg"
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/Databases/secrets
ARG DATABASES_SECRETS_FILE=/mnt/myssd/LucidTops/Databases/secrets/databases.secrets
ARG MONGODB_SECRETS_FILE=/mnt/myssd/LucidTops/Databases/secrets/mongodb.secrets
ARG DATABASES_CONFIGS_DIR=/mnt/myssd/LucidTops/Databases/configs
ARG MONGODB_DATA_MOUNT=/mnt/myssd/LucidTops/Server/Databases
ARG RUN_DATABASES_BOOTSTRAP_ON_BUILD=false
ARG INSTALL_DOCKER_CLI=true

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/Databases \
      /app/Databases/run \
      /app/Databases/configs \
      /app/Databases/logs \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${DATABASES_CONFIGS_DIR}" \
      "${MONGODB_DATA_MOUNT}" \
      "${LUCID_TOPS_ROOT}/Databases" \
      "${LUCID_TOPS_ROOT}/logs/Databases" \
      "${LUCID_TOPS_ROOT}/run/Databases"; \
    test -d /app/Databases; \
    test -d /app/Databases/run; \
    test -d /app/Databases/configs; \
    test -d /app/Databases/logs; \
    test -d "${SECRETS_DIR}"; \
    test -d "${MONGODB_DATA_MOUNT}"; \
    test -d "${LUCID_TOPS_ROOT}"

# -----------------------------------------------------------------------------
# OS packages (pull tools) + Docker CLI/compose plugin (sibling-container orchestrator)
# Docker CLI from download.docker.com — daemon remains on host via docker.sock
# -----------------------------------------------------------------------------
RUN set -eu; \
    apt-get update; \
    if [ -n "${APT_PACKAGES}" ]; then \
      apt-get install -y --no-install-recommends ${APT_PACKAGES}; \
    fi; \
    if [ "${INSTALL_DOCKER_CLI}" = "true" ]; then \
      apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
      install -m 0755 -d /etc/apt/keyrings; \
      curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
      chmod a+r /etc/apt/keyrings/docker.gpg; \
      ARCH="$(dpkg --print-architecture)"; \
      . /etc/os-release; \
      echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list; \
      apt-get update; \
      apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin; \
    fi; \
    command -v ip >/dev/null; \
    if [ "${INSTALL_DOCKER_CLI}" = "true" ]; then \
      command -v docker >/dev/null; \
      docker compose version >/dev/null; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Pip wheel installer + requirements (literal COPY — no ARG in source path)
# -----------------------------------------------------------------------------
COPY Databases/requirements.txt /app/Databases/requirements.txt
RUN set -eu; \
    test -s /app/Databases/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/Databases/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import pymongo, socks, dotenv"

# -----------------------------------------------------------------------------
# Copy Databases package, then validate (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY Databases/ /app/Databases/

RUN set -eu; \
    test -f /app/Databases/entrypoint.sh; \
    test -f /app/Databases/BootstrapDatabases.py; \
    test -f /app/Databases/pull_information.py; \
    test -f /app/Databases/databases_secrets.py; \
    test -f /app/Databases/LaunchDatabases.py; \
    test -f /app/Databases/BuildCompose.py; \
    test -f /app/Databases/Dns_databases.py; \
    test -f /app/Databases/DBSchemas.py; \
    test -f /app/Databases/connection.py; \
    test -f /app/Databases/NodeHostedDB.py; \
    test -s /app/Databases/requirements.txt; \
    test -f /app/Databases/Databases.dockerfile; \
    test -d /app/Databases/run; \
    test -d /app/Databases/configs; \
    test -d /app/Databases/logs; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/Databases/entrypoint.sh \
      /app/Databases/BootstrapDatabases.py \
      /app/Databases/pull_information.py \
      /app/Databases/LaunchDatabases.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app:/app/Databases
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV DATABASES_SECRETS_FILE=${DATABASES_SECRETS_FILE}
ENV MONGODB_SECRETS_FILE=${MONGODB_SECRETS_FILE}
ENV DATABASES_CONFIGS_DIR=${DATABASES_CONFIGS_DIR}
ENV MONGODB_DATA_MOUNT=${MONGODB_DATA_MOUNT}
ENV RUN_DATABASES_BOOTSTRAP_ON_START=true
ENV DOCKER_HOST=unix:///var/run/docker.sock

# Optional bootstrap at build (default false — SSD/hardware at first start)
RUN set -eu; \
    if [ "${RUN_DATABASES_BOOTSTRAP_ON_BUILD}" = "true" ]; then \
      python3 /app/Databases/BootstrapDatabases.py; \
      test -f "${DATABASES_SECRETS_FILE}"; \
    fi

WORKDIR /app/Databases
ENTRYPOINT ["/app/Databases/entrypoint.sh"]
CMD []
