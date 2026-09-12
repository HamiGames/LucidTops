# LucidTops Rdp container — peer remote desktop (fixes.txt §4 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD — BASE_IMAGE and APT_PACKAGES from hardware pull at operation):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/Rdp/Rdp.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-rdp:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/Rdp/secrets/*.secrets
#
# RULES:
# - no hardcoded values; BASE_IMAGE / APT_PACKAGES / PIP_PACKAGES supplied at time of operation.
# - no placeholder defaults for BASE_IMAGE; must be set from pull/output before build.
# - At container start, RunRdp → createRDP.pull_information writes rdp.secrets.
# - no sensitive data; no GIT pull.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG RDP_DIRECTORY=Rdp
ARG PIP_PACKAGES=
ARG APT_PACKAGES=
ARG RUN_CREATE_ON_BUILD=false

WORKDIR /app

RUN if [ -n "${APT_PACKAGES}" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
      && rm -rf /var/lib/apt/lists/*; \
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
 && test -s /app/Rdp/requirements.txt \
 && chmod +x /app/Rdp/createRDP.py /app/Rdp/RunRdp.py

ENV PYTHONPATH=/app/Rdp
ENV PYTHONUNBUFFERED=1
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/Rdp/secrets

RUN mkdir -p /app/Rdp/run /app/Rdp/logs /app/Rdp/share /app/Rdp/backup \
 && mkdir -p /mnt/myssd/LucidTops/Rdp/secrets /mnt/myssd/LucidTops

RUN if [ "${RUN_CREATE_ON_BUILD}" = "true" ]; then \
      python /app/Rdp/createRDP.py; \
    fi

WORKDIR /app/Rdp
ENTRYPOINT ["python", "RunRdp.py"]
CMD ["run"]
