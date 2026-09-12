# LucidTops MasterServer (backend) — FastAPI/uvicorn (fixes.txt §2 / §16).
# Tor/nginx owned by Proxy container.
# Image tag: lucid-server-default:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES=""
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/backend/Server.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-server-default:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (builderMasterServer / fixes.txt §16.1 + Server layout):
#   Canonical dir:  /mnt/myssd/LucidTops/Server/Secrets
#   §16 directory link: /mnt/myssd/LucidTops/backend/secrets → Server/Secrets
#   Master.secrets from Proxy Bootstrap; server.secrets from builder at start
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): join at run via dockercmd.txt.

# -----------------------------------------------------------------------------
# Build-args (declared before FROM for BASE_IMAGE; re-declared after FROM for use)
# -----------------------------------------------------------------------------
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# Runtime / install args (NOT used in COPY source paths)
ARG APT_PACKAGES=""
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/Server/Secrets
ARG MASTER_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/Master.secrets
ARG SERVER_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/server.secrets
ARG BACKEND_SECRETS_LINK=/mnt/myssd/LucidTops/backend/secrets
ARG BACKEND_CONFIGS_DIR=/mnt/myssd/LucidTops/backend/configs
ARG RUN_BUILDER_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/backend \
      /app/backend/run \
      /app/backend/configs \
      /app/backend/logs \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${BACKEND_CONFIGS_DIR}" \
      "${LUCID_TOPS_ROOT}/backend" \
      "${LUCID_TOPS_ROOT}/configs" \
      "${LUCID_TOPS_ROOT}/logs"; \
    test -d /app/backend; \
    test -d "${SECRETS_DIR}"; \
    test -d "${LUCID_TOPS_ROOT}"

# Link §16 backend/secrets → Server/Secrets (Master.secrets + server.secrets live here)
RUN set -eu; \
    rm -rf "${BACKEND_SECRETS_LINK}"; \
    ln -sfn "${SECRETS_DIR}" "${BACKEND_SECRETS_LINK}"; \
    test -L "${BACKEND_SECRETS_LINK}"; \
    test "$(readlink -f "${BACKEND_SECRETS_LINK}")" = "$(readlink -f "${SECRETS_DIR}")"

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
COPY backend/requirements.txt /app/backend/requirements.txt
RUN set -eu; \
    test -s /app/backend/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/backend/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, pydantic, pymongo, socks, httpx, dotenv"

# -----------------------------------------------------------------------------
# Copy entire backend package, then validate required modules (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY backend/ /app/backend/

RUN set -eu; \
    test -f /app/backend/main.py; \
    test -f /app/backend/LaunchServer.py; \
    test -f /app/backend/server_entrypoint.sh; \
    test -f /app/backend/pull_information.py; \
    test -f /app/backend/builderMasterServer.py; \
    test -f /app/backend/container_secrets.py; \
    test -f /app/backend/config.py; \
    test -f /app/backend/connection.py; \
    test -f /app/backend/MasterServerRoutes.py; \
    test -s /app/backend/requirements.txt; \
    test -f /app/backend/Server.dockerfile; \
    test -d /app/backend/run; \
    test -d /app/backend/configs; \
    test -d /app/backend/logs; \
    test -L "${BACKEND_SECRETS_LINK}"; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/backend/server_entrypoint.sh /app/backend/pull_information.py /app/backend/builderMasterServer.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app:/app/backend
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV MASTER_SECRETS_FILE=${MASTER_SECRETS_FILE}
ENV SERVER_SECRETS_FILE=${SERVER_SECRETS_FILE}
ENV BACKEND_SECRETS_LINK=${BACKEND_SECRETS_LINK}
ENV BACKEND_CONFIGS_DIR=${BACKEND_CONFIGS_DIR}
ENV RUN_BUILDER_ON_START=true

# Optional builder at build (default false — secrets on host / first start)
RUN set -eu; \
    if [ "${RUN_BUILDER_ON_BUILD}" = "true" ]; then \
      python3 /app/backend/builderMasterServer.py; \
      test -f "${SERVER_SECRETS_FILE}"; \
    fi

WORKDIR /app/backend
ENTRYPOINT ["/app/backend/server_entrypoint.sh"]
CMD []
