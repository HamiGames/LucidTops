# LucidTops MasterServer (backend) — FastAPI/uvicorn (fixes.txt §2 / §16).
# Tor/nginx owned by Proxy container.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/backend/Server.dockerfile \
#     -t lucid-server-default:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/backend/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC and paths come from pull → secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Operation-time: builderMasterServer.py + pull_information.py (hardware pull).

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN test -s /app/backend/requirements.txt \
 && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend
COPY PaySystems /app/PaySystems

# Fail build if COPY landed empty/missing (negate ghost copy)
RUN test -f /app/backend/main.py \
 && test -f /app/backend/server_entrypoint.sh \
 && test -f /app/backend/pull_information.py \
 && test -f /app/backend/container_secrets.py \
 && test -f /app/backend/builderMasterServer.py \
 && test -f /app/operations/ops_entrypoint.sh \
 && test -d /app/sessions \
 && test -d /app/blockchain \
 && test -d /app/frontend \
 && test -f /app/PaySystems/PayRoutes.py \
 && test -s /app/backend/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/backend/secrets
ENV PYTHONPATH=/app:/app/backend
ENV RUN_BUILDER_ON_START=true
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /mnt/myssd/LucidTops/backend/secrets /mnt/myssd/LucidTops

COPY backend/server_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && test -x /entrypoint.sh -o -f /entrypoint.sh

# WORKDIR matches backend Python package content (§16.3)
WORKDIR /app/backend

ENTRYPOINT ["/entrypoint.sh"]
