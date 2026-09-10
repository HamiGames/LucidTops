# LucidTops Proxy — nginx reverse proxy + Tor + uvicorn/FastAPI
# Criteria (documentation/fixes.txt section 1).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/proxy/proxy.dockerfile \
#     --build-arg BASE_IMAGE=<image-from-operation> \
#     --build-arg APT_PACKAGES=<packages-from-operation> \
#     -t lucid-proxy \
#     /mnt/myssd/LucidTops
#
# Operational IP/MAC/DockerDNS/ports are NOT baked into the image.
# At container start, Bootstrap.pull_information writes proxy.secrets / Master.secrets.

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
RUN pip install --no-cache-dir -r /app/proxy/requirements.txt \
    && if [ -n "${PIP_PACKAGES}" ]; then pip install --no-cache-dir ${PIP_PACKAGES}; fi

COPY ${PROXY_DIRECTORY} /app/proxy

RUN test -f /app/proxy/Bootstrap.py \
 && test -f /app/proxy/RunProxy.py \
 && test -f /app/proxy/ProxyRoutes.py \
 && test -s /app/proxy/requirements.txt \
 && chmod +x /app/proxy/Bootstrap.py /app/proxy/RunProxy.py

ENV PYTHONPATH=/app/proxy
ENV PYTHONUNBUFFERED=1
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops

RUN mkdir -p /app/proxy/run /app/proxy/configs

RUN if [ "${RUN_BOOTSTRAP_ON_BUILD}" = "true" ]; then \
      python /app/proxy/Bootstrap.py; \
    fi

WORKDIR /app/proxy
ENTRYPOINT ["python", "RunProxy.py"]
CMD ["run"]
