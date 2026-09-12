# LucidTops Proxy — nginx reverse proxy + Tor + uvicorn/FastAPI (fixes.txt §1 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD — BASE_IMAGE and APT_PACKAGES from hardware pull at operation):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/proxy/proxy.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-proxy:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/proxy/secrets/*.secrets
#
# RULES:
# - no hardcoded values; BASE_IMAGE / APT_PACKAGES / PIP_PACKAGES supplied at time of operation.
# - no placeholder defaults for BASE_IMAGE; must be set from pull/output before build.
# - Operational IP/MAC/DockerDNS/ports are NOT baked into the image.
# - At container start, Bootstrap.pull_information writes proxy.secrets / Master.secrets.
# - no sensitive data; no GIT pull.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt + Bootstrap ensure_docker_networks.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG PROXY_DIRECTORY=proxy
ARG PIP_PACKAGES=
ARG APT_PACKAGES=
ARG RUN_BOOTSTRAP_ON_BUILD=false

WORKDIR /app

RUN if [ -n "${APT_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY ${PROXY_DIRECTORY}/requirements.txt /app/proxy/requirements.txt
RUN test -s /app/proxy/requirements.txt \
 && pip install --no-cache-dir -r /app/proxy/requirements.txt \
 && if [ -n "${PIP_PACKAGES}" ]; then pip install --no-cache-dir ${PIP_PACKAGES}; fi

COPY ${PROXY_DIRECTORY} /app/proxy

RUN test -f /app/proxy/Bootstrap.py \
 && test -f /app/proxy/RunProxy.py \
 && test -f /app/proxy/ProxyRoutes.py \
 && test -f /app/proxy/buildsecrets.py \
 && test -f /app/proxy/SetDeamon.py \
 && test -f /app/proxy/ProxyGate.py \
 && test -s /app/proxy/requirements.txt \
 && chmod +x /app/proxy/Bootstrap.py /app/proxy/RunProxy.py

ENV PYTHONPATH=/app/proxy
ENV PYTHONUNBUFFERED=1
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/proxy/secrets

RUN mkdir -p /app/proxy/run /app/proxy/configs \
 && mkdir -p /mnt/myssd/LucidTops/proxy/secrets /mnt/myssd/LucidTops

RUN if [ "${RUN_BOOTSTRAP_ON_BUILD}" = "true" ]; then \
      python /app/proxy/Bootstrap.py; \
    fi

WORKDIR /app/proxy
ENTRYPOINT ["python", "RunProxy.py"]
CMD ["run"]
