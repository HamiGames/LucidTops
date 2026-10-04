# LucidTops PaySystems — ClearNet payment container (paysystems.txt).
# Image tag: lucid-paysystems:v1.0.0
# Access: backend container and AdminGui. Not a Tor-only service.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, after Master.secrets and proxy.secrets exist):
#   cd /mnt/myssd/LucidTops
#   DOCKER_BUILDKIT=1 docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/PaySystems/Pay.dockerfile \
#     --build-arg BASE_IMAGE=python:3.11-slim-bookworm \
#     -t lucid-paysystems:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets (containers.txt — Pi console, not inside the image):
#   SECRETS_DIR=/mnt/myssd/LucidTops/Server/Secrets
#   payments.secrets is written there at image creation from Master.secrets
#   and proxy.secrets. torrc is recorded when present.
#
# RULES:
# - no hardcoded operational values.
# - no GIT pull.
# - ClearNet PayNow processing stays in the PaySystems package.

ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

ARG APT_PACKAGES=""
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/Server/Secrets
ARG PAYMENTS_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/payments.secrets
ARG HOST_TOR_CONFIG_TORRC=/mnt/myssd/LucidTops/torrc

WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/PaySystems \
      /app/PaySystems/run \
      /app/PaySystems/configs \
      /app/PaySystems/logs \
      /app/proxy \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}"; \
    test -d /app/PaySystems; \
    test -d "${SECRETS_DIR}"

RUN set -eu; \
    if [ -n "${APT_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY PaySystems/requirements.txt /app/PaySystems/requirements.txt
RUN set -eu; \
    test -s /app/PaySystems/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/PaySystems/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi

COPY PaySystems /app/PaySystems
COPY proxy /app/proxy

RUN set -eu; \
    test -f /app/PaySystems/PayRoutes.py; \
    test -f /app/PaySystems/PaymentRoutes.py; \
    test -f /app/PaySystems/pay_entrypoint.sh; \
    test -f /app/PaySystems/pull_information.py; \
    test -f /app/PaySystems/payments_secrets.py; \
    test -s /app/PaySystems/requirements.txt; \
    test -d /app/proxy; \
    chmod +x /app/PaySystems/pay_entrypoint.sh /app/PaySystems/pull_information.py

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV PAYMENTS_SECRETS_FILE=${PAYMENTS_SECRETS_FILE}
ENV HOST_TOR_CONFIG_TORRC=${HOST_TOR_CONFIG_TORRC}
ENV PYTHONPATH=/app:/app/PaySystems:/app/proxy
ENV PYTHONUNBUFFERED=1

RUN --mount=type=bind,source=/mnt/myssd/LucidTops/Server/Secrets,target=/mnt/myssd/LucidTops/Server/Secrets \
    python3 /app/PaySystems/pull_information.py \
 && test -s /mnt/myssd/LucidTops/Server/Secrets/payments.secrets

WORKDIR /app/PaySystems
ENTRYPOINT ["/app/PaySystems/pay_entrypoint.sh"]
CMD []
