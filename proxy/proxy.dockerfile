# LucidTops Proxy — nginx reverse proxy + Tor + uvicorn/FastAPI (fixes.txt §1 / §16).
# Image tag: lucid-proxy:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES="ca-certificates curl iproute2 nginx tor"
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/proxy/proxy.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-proxy:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (Bootstrap / fixes.txt §16 + Server layout):
#   Canonical file: /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
#   §16 directory link: /mnt/myssd/LucidTops/proxy/secrets → Server/Secrets
#
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): join at run via dockercmd.txt.

# -----------------------------------------------------------------------------
# Build-args (declared before FROM for BASE_IMAGE; re-declared after FROM for use)
# -----------------------------------------------------------------------------
ARG BASE_IMAGE=
FROM ${BASE_IMAGE}

# Runtime / install args (NOT used in COPY source paths)
ARG APT_PACKAGES=""
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/Server/Secrets
ARG PROXY_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
ARG MASTER_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/Master.secrets
ARG PROXY_SECRETS_LINK=/mnt/myssd/LucidTops/proxy/secrets
ARG PROXY_CONFIGS_DIR=/mnt/myssd/LucidTops/proxy/configs
ARG CONTAINER_ONION_DIR=/mnt/myssd/LucidTops/onion
ARG RUN_BOOTSTRAP_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/proxy \
      /app/proxy/run \
      /app/proxy/configs \
      /app/proxy/logs \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${PROXY_CONFIGS_DIR}" \
      "${CONTAINER_ONION_DIR}" \
      "${LUCID_TOPS_ROOT}/proxy" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/master_server" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/frontend" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/node_user" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/rdp" \
      "${LUCID_TOPS_ROOT}/logs/nginx" \
      "${LUCID_TOPS_ROOT}/logs/proxy" \
      "${LUCID_TOPS_ROOT}/run/nginx" \
      "${LUCID_TOPS_ROOT}/run/proxy"; \
    test -d /app/proxy; \
    test -d "${SECRETS_DIR}"; \
    test -d "${LUCID_TOPS_ROOT}"

# Link §16 proxy/secrets → Server/Secrets (proxy.secrets lives here)
RUN set -eu; \
    rm -rf "${PROXY_SECRETS_LINK}"; \
    ln -sfn "${SECRETS_DIR}" "${PROXY_SECRETS_LINK}"; \
    test -L "${PROXY_SECRETS_LINK}"; \
    test "$(readlink -f "${PROXY_SECRETS_LINK}")" = "$(readlink -f "${SECRETS_DIR}")"

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
COPY proxy/requirements.txt /app/proxy/requirements.txt
RUN set -eu; \
    test -s /app/proxy/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/proxy/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, httpx, pydantic, socks"

# -----------------------------------------------------------------------------
# Copy entire proxy package, then validate required modules (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY proxy/ /app/proxy/

RUN set -eu; \
    test -f /app/proxy/Bootstrap.py; \
    test -f /app/proxy/RunProxy.py; \
    test -f /app/proxy/ProxyRoutes.py; \
    test -f /app/proxy/ProxyGate.py; \
    test -f /app/proxy/buildsecrets.py; \
    test -f /app/proxy/SetDeamon.py; \
    test -f /app/proxy/Clearnet-package.py; \
    test -s /app/proxy/requirements.txt; \
    test -f /app/proxy/proxy.dockerfile; \
    test -d /app/proxy/run; \
    test -d /app/proxy/configs; \
    test -d /app/proxy/logs; \
    test -L "${PROXY_SECRETS_LINK}"; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/proxy/Bootstrap.py /app/proxy/RunProxy.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app/proxy
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV PROXY_SECRETS_FILE=${PROXY_SECRETS_FILE}
ENV MASTER_SECRETS_FILE=${MASTER_SECRETS_FILE}
ENV PROXY_SECRETS_LINK=${PROXY_SECRETS_LINK}
ENV PROXY_CONFIGS_DIR=${PROXY_CONFIGS_DIR}
ENV CONTAINER_ONION_DIR=${CONTAINER_ONION_DIR}

# Optional bootstrap at build (default false — secrets on host / first start)
RUN set -eu; \
    if [ "${RUN_BOOTSTRAP_ON_BUILD}" = "true" ]; then \
      python3 /app/proxy/Bootstrap.py; \
      test -f "${PROXY_SECRETS_FILE}"; \
    fi

WORKDIR /app/proxy
ENTRYPOINT ["python3", "RunProxy.py"]
CMD ["run"]
