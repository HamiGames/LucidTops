# LucidTops Databases orchestration — MongoDB containers per named DB
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/Databases/Databases.dockerfile \
#     -t lucid-databases-orchestrator \
#     /mnt/myssd/LucidTops
#
# Target: linux/arm64 (Raspberry Pi 5)
# Operation-time: BootstrapDatabases.py + pull_information.py (hardware pull)

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY Databases/requirements.txt /app/Databases/requirements.txt
RUN pip install --no-cache-dir -r /app/Databases/requirements.txt

COPY Databases /app/Databases

RUN test -f /app/Databases/entrypoint.sh \
 && test -s /app/Databases/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV PYTHONPATH=/app/Databases
ENV RUN_DATABASES_BOOTSTRAP_ON_START=true

COPY Databases/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
