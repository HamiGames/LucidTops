# LucidTops Rdp container — peer remote desktop (fixes.txt section 4).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/Rdp/Rdp.dockerfile \
#     --build-arg BASE_IMAGE=<image-from-operation> \
#     --build-arg APT_PACKAGES=<packages-from-operation> \
#     -t lucid-rdp \
#     /mnt/myssd/LucidTops
#
# At container start, RunRdp → createRDP.pull_information writes rdp.secrets.

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
RUN pip install --no-cache-dir -r /app/Rdp/requirements.txt \
    && if [ -n "${PIP_PACKAGES}" ]; then pip install --no-cache-dir ${PIP_PACKAGES}; fi

COPY ${RDP_DIRECTORY} /app/Rdp

RUN test -f /app/Rdp/createRDP.py \
 && test -f /app/Rdp/RunRdp.py \
 && test -s /app/Rdp/requirements.txt \
 && chmod +x /app/Rdp/createRDP.py /app/Rdp/RunRdp.py

ENV PYTHONPATH=/app/Rdp
ENV PYTHONUNBUFFERED=1
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops

RUN mkdir -p /app/Rdp/run /app/Rdp/logs /app/Rdp/share /app/Rdp/backup

RUN if [ "${RUN_CREATE_ON_BUILD}" = "true" ]; then \
      python /app/Rdp/createRDP.py; \
    fi

WORKDIR /app/Rdp
ENTRYPOINT ["python", "RunRdp.py"]
CMD ["run"]
