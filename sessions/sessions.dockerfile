# LucidTops sessions — FastAPI/uvicorn; DockerDNS peer meeting location for Rdp (fixes.txt §5 / §16).
# Image tag: lucid-sessions:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES=""
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/sessions/sessions.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-sessions:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (§16.1) — created at time of operation (not baked into the image):
#   SECRETS_DIR=/mnt/myssd/LucidTops/sessions/secrets
#   Entrypoint: sessions_pull_information → write_session_secrets → uvicorn
#   If empty: write sessions.secrets from live hardware pull.
#   Host mount required: -v /mnt/myssd/LucidTops:/mnt/myssd/LucidTops
#
# RULES:
# - no hardcoded values; all values created at time of operation via sessions_pull_information.
# - no placeholder values; hardware IP/MAC/DockerDNS come from pull → sessions.secrets.
# - no sensitive data in this image; data lives in the secrets file on the SSD mount.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# MasterServer creates SessionID only; non-standard chunk/New_BlockID → operations.
# Runtime deps copied into image: backend (config/pull_information) for hardware pull + Mongo.

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
ARG SECRETS_DIR=/mnt/myssd/LucidTops/sessions/secrets
ARG SESSIONS_SECRETS_FILE=/mnt/myssd/LucidTops/sessions/secrets/sessions.secrets
ARG SESSIONS_CONFIGS_DIR=/mnt/myssd/LucidTops/sessions/configs
ARG RUN_SESSIONS_PULL_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/sessions \
      /app/sessions/run \
      /app/sessions/configs \
      /app/sessions/logs \
      /app/backend \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${SESSIONS_CONFIGS_DIR}" \
      "${LUCID_TOPS_ROOT}/sessions" \
      "${LUCID_TOPS_ROOT}/logs/sessions" \
      "${LUCID_TOPS_ROOT}/run/sessions"; \
    test -d /app/sessions; \
    test -d /app/sessions/run; \
    test -d /app/sessions/configs; \
    test -d /app/sessions/logs; \
    test -d "${SECRETS_DIR}"; \
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
COPY sessions/requirements.txt /app/sessions/requirements.txt
RUN set -eu; \
    test -s /app/sessions/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/sessions/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, pydantic, pymongo, socks, httpx, dotenv"

# -----------------------------------------------------------------------------
# Copy sessions package + runtime sibling backend, then validate (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY sessions/ /app/sessions/
COPY backend/ /app/backend/

RUN set -eu; \
    test -f /app/sessions/sessions_entrypoint.sh; \
    test -f /app/sessions/app.py; \
    test -f /app/sessions/sessions_pull_information.py; \
    test -f /app/sessions/Config_sessions.py; \
    test -f /app/sessions/SessionCore.py; \
    test -f /app/sessions/sessionID.py; \
    test -f /app/sessions/compress.py; \
    test -f /app/sessions/searchpeer.py; \
    test -f /app/sessions/SessionRoutes.py; \
    test -f /app/sessions/_common.py; \
    test -s /app/sessions/requirements.txt; \
    test -f /app/sessions/sessions.dockerfile; \
    test -d /app/sessions/run; \
    test -d /app/sessions/configs; \
    test -d /app/sessions/logs; \
    test -d /app/backend; \
    test -f /app/backend/config.py; \
    test -f /app/backend/pull_information.py; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/sessions/sessions_entrypoint.sh /app/sessions/sessions_pull_information.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app:/app/backend:/app/sessions
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV SESSIONS_SECRETS_FILE=${SESSIONS_SECRETS_FILE}
ENV SESSIONS_CONFIGS_DIR=${SESSIONS_CONFIGS_DIR}

# Optional sessions pull + secrets write at build (default false — SSD/hardware at first start)
RUN set -eu; \
    if [ "${RUN_SESSIONS_PULL_ON_BUILD}" = "true" ]; then \
      python3 /app/sessions/sessions_pull_information.py >/dev/null; \
      python3 -c "from Config_sessions import write_session_secrets; write_session_secrets(force=False)"; \
    fi

WORKDIR /app/sessions
ENTRYPOINT ["/app/sessions/sessions_entrypoint.sh"]
CMD []
