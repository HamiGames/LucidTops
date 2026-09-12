# LucidTops operations — FastAPI/uvicorn; DockerDNS on the operations network (fixes.txt §7 / §16).
# Image tag: lucid-operations:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES=""
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/operations/Ops.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-operations:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (§16.1) — created at time of operation (not baked into the image):
#   SECRETS_DIR=/mnt/myssd/LucidTops/operations/secrets
#   Entrypoint: ops_pull_information → write_operations_secrets → uvicorn
#   If empty: write operations.secrets from live hardware pull.
#   If Master already wrote Server/Secrets/operations.secrets, those values are seeded in.
#   Host mount required: -v /mnt/myssd/LucidTops:/mnt/myssd/LucidTops
#
# RULES:
# - no hardcoded values; all values created at time of operation via ops_pull_information.
# - no placeholder values; hardware IP/MAC come from pull → operations.secrets / ID.secrets.
# - no sensitive data in this image; data lives in the secrets file on the SSD mount.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Operators: NodeID | AdminID | MasterUserID | MasterServerID in LucidTopsNodeDB.
# Runtime deps copied into image: backend (config/pull/load_module) + sessions (chunk/session APIs).

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
ARG SECRETS_DIR=/mnt/myssd/LucidTops/operations/secrets
ARG OPERATIONS_SECRETS_FILE=/mnt/myssd/LucidTops/operations/secrets/operations.secrets
ARG OPERATIONS_CONFIGS_DIR=/mnt/myssd/LucidTops/operations/configs
ARG RUN_OPS_PULL_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/operations \
      /app/operations/run \
      /app/operations/configs \
      /app/operations/logs \
      /app/backend \
      /app/sessions \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${OPERATIONS_CONFIGS_DIR}" \
      "${LUCID_TOPS_ROOT}/operations" \
      "${LUCID_TOPS_ROOT}/logs/operations" \
      "${LUCID_TOPS_ROOT}/run/operations"; \
    test -d /app/operations; \
    test -d /app/operations/run; \
    test -d /app/operations/configs; \
    test -d /app/operations/logs; \
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
COPY operations/requirements.txt /app/operations/requirements.txt
RUN set -eu; \
    test -s /app/operations/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/operations/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, pydantic, pymongo, socks, httpx, dotenv"

# -----------------------------------------------------------------------------
# Copy operations package + runtime siblings, then validate (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY operations/ /app/operations/
COPY backend/ /app/backend/
COPY sessions/ /app/sessions/

RUN set -eu; \
    test -f /app/operations/ops_entrypoint.sh; \
    test -f /app/operations/app.py; \
    test -f /app/operations/ops_pull_information.py; \
    test -f /app/operations/operations_secrets.py; \
    test -f /app/operations/id_secrets.py; \
    test -f /app/operations/_common.py; \
    test -f /app/operations/session.py; \
    test -f /app/operations/session_to_block.py; \
    test -s /app/operations/requirements.txt; \
    test -f /app/operations/Ops.dockerfile; \
    test -d /app/operations/run; \
    test -d /app/operations/configs; \
    test -d /app/operations/logs; \
    test -d /app/backend; \
    test -f /app/backend/config.py; \
    test -f /app/backend/WebPageLink.py; \
    test -f /app/backend/load_module.py; \
    test -f /app/backend/pull_information.py; \
    test -f /app/backend/NodeDbSchema.py; \
    test -f /app/backend/data-chunker.py; \
    test -d /app/sessions; \
    test -f /app/sessions/compress.py; \
    test -f /app/sessions/SessionCore.py; \
    test -f /app/sessions/sessionID.py; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/operations/ops_entrypoint.sh /app/operations/ops_pull_information.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app:/app/backend:/app/operations:/app/sessions
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV OPERATIONS_SECRETS_FILE=${OPERATIONS_SECRETS_FILE}
ENV OPERATIONS_CONFIGS_DIR=${OPERATIONS_CONFIGS_DIR}

# Optional ops pull + secrets write at build (default false — SSD/hardware at first start)
RUN set -eu; \
    if [ "${RUN_OPS_PULL_ON_BUILD}" = "true" ]; then \
      python3 /app/operations/ops_pull_information.py >/dev/null; \
      python3 -c "from operations_secrets import write_operations_secrets; write_operations_secrets(force=False)"; \
    fi

WORKDIR /app/operations
ENTRYPOINT ["/app/operations/ops_entrypoint.sh"]
CMD []
