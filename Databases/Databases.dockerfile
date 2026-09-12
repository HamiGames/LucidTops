# LucidTops Databases orchestration — MongoDB containers per named DB (fixes.txt §11 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/Databases/Databases.dockerfile \
#     -t lucid-databases-orchestrator:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/Databases/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC come from pull → databases secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Operation-time: BootstrapDatabases.py + pull_information.py (hardware pull).

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY Databases/requirements.txt /app/Databases/requirements.txt
RUN test -s /app/Databases/requirements.txt \
 && pip install --no-cache-dir -r /app/Databases/requirements.txt

COPY Databases /app/Databases

RUN test -f /app/Databases/entrypoint.sh \
 && test -f /app/Databases/BootstrapDatabases.py \
 && test -f /app/Databases/pull_information.py \
 && test -f /app/Databases/databases_secrets.py \
 && test -s /app/Databases/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/Databases/secrets
ENV PYTHONPATH=/app/Databases
ENV RUN_DATABASES_BOOTSTRAP_ON_START=true
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /mnt/myssd/LucidTops/Databases/secrets /mnt/myssd/LucidTops

COPY Databases/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# WORKDIR matches Databases Python package content (§16.3)
WORKDIR /app/Databases

ENTRYPOINT ["/entrypoint.sh"]
