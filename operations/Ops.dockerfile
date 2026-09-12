# LucidTops operations — FastAPI/uvicorn; DockerDNS on the operations network (fixes.txt §7 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/operations/Ops.dockerfile \
#     -t lucid-operations:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/operations/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via ops_pull_information.
# - no placeholder values; hardware IP/MAC come from pull → operations.secrets / ID.secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Operators: NodeID | AdminID | MasterUserID | MasterServerID in LucidTopsNodeDB.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY operations/requirements.txt /app/operations/requirements.txt
RUN test -s /app/operations/requirements.txt \
 && pip install --no-cache-dir -r /app/operations/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend

RUN test -f /app/operations/ops_entrypoint.sh \
 && test -f /app/operations/app.py \
 && test -f /app/operations/ops_pull_information.py \
 && test -f /app/operations/operations_secrets.py \
 && test -f /app/operations/id_secrets.py \
 && test -d /app/backend \
 && test -d /app/sessions \
 && test -d /app/blockchain \
 && test -d /app/frontend \
 && test -s /app/operations/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/operations/secrets
ENV PYTHONPATH=/app:/app/backend:/app/operations
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /mnt/myssd/LucidTops/operations/secrets /mnt/myssd/LucidTops

COPY operations/ops_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# WORKDIR matches operations Python package content (§16.3)
WORKDIR /app/operations

ENTRYPOINT ["/entrypoint.sh"]
