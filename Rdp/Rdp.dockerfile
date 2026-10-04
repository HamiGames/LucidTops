# LucidTops Rdp container — peer remote desktop (fixes.txt §4 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, DOCKER_BUILDKIT=1, after Master.secrets and proxy.secrets exist):
#   cd /mnt/myssd/LucidTops
#   DOCKER_BUILDKIT=1 docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/Rdp/Rdp.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-rdp:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Connection file (documentation/RDP.txt):
#   At image creation, createRDP.py reads
#   /mnt/myssd/LucidTops/Server/Secrets/Master.secrets and proxy.secrets
#   (BuildKit bind, not a copied layer) and writes /app/Secrets/rdp.secrets.
#   DockerDns reads that in-container file. It is not taken from /mnt/myssd at runtime.
#
# RULES:
# - no hardcoded values; BASE_IMAGE / APT_PACKAGES / PIP_PACKAGES supplied at time of operation.
# - no placeholder defaults for BASE_IMAGE; must be set from pull/output before build.
# - User-console files (settings.js, hardware, logs, USB) are written at container start
#   under the LucidTops program folder (DRIVER_DIR). They are not written into rdp.secrets.
# - no sensitive data; no GIT pull.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG RDP_DIRECTORY=Rdp
ARG PIP_PACKAGES=
ARG APT_PACKAGES=

WORKDIR /app

RUN if [ -n "${APT_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
    fi

RUN set -eu; \
  if [ ! -d /app/Rdp ]; then \
    mkdir -p /app/Rdp; \
    touch /app/Rdp/.gitkeep; \
  fi; \
  if [ ! -d /app/Secrets ]; then \
    mkdir -p /app/Secrets; \
    touch /app/Secrets/.gitkeep; \
  fi

COPY ${RDP_DIRECTORY}/requirements.txt /app/Rdp/requirements.txt
RUN test -s /app/Rdp/requirements.txt \
 && pip install --no-cache-dir -r /app/Rdp/requirements.txt \
 && if [ -n "${PIP_PACKAGES}" ]; then pip install --no-cache-dir ${PIP_PACKAGES}; fi

COPY ${RDP_DIRECTORY} /app/Rdp

RUN test -f /app/Rdp/createRDP.py \
 && test -f /app/Rdp/RunRdp.py \
 && test -f /app/Rdp/rdp_secrets.py \
 && test -f /app/Rdp/RdpMain.py \
 && test -f /app/Rdp/DockerDns.py \
 && test -f /app/Rdp/ViewerWindow.py \
 && test -s /app/Rdp/requirements.txt \
 && test -f /app/Rdp/pull_information.py \
 && chmod +x /app/Rdp/createRDP.py /app/Rdp/RunRdp.py /app/Rdp/pull_information.py 

ENV PYTHONPATH=/app/Rdp
ENV PYTHONUNBUFFERED=1
ENV SECRETS_DIR=/app/Secrets
ENV RDP_SECRETS_FILE=/app/Secrets/rdp.secrets

RUN --mount=type=bind,source=/mnt/myssd/LucidTops/Server/Secrets,target=/mnt/myssd/LucidTops/Server/Secrets,readonly \
    sh -c "RDP_SECRETS_AT_IMAGE_BUILD=true python /app/Rdp/pull_information.py && test -s /app/Secrets/rdp.secrets"

WORKDIR /app/Rdp
ENTRYPOINT ["python", "RunRdp.py"]
CMD ["run"]
