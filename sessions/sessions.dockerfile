# LucidTops sessions — FastAPI/uvicorn; DockerDNS peer meeting location for Rdp (fixes.txt §5 / §16).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/sessions/sessions.dockerfile \
#     -t lucid-sessions:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/sessions/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via sessions_pull_information.
# - no placeholder values; hardware IP/MAC/DockerDNS come from pull → sessions.secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# MasterServer creates SessionID only; non-standard chunk/New_BlockID → operations.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY sessions/requirements.txt /app/sessions/requirements.txt
RUN test -s /app/sessions/requirements.txt \
 && pip install --no-cache-dir -r /app/sessions/requirements.txt

COPY backend /app/backend
COPY sessions /app/sessions

RUN test -f /app/sessions/sessions_entrypoint.sh \
 && test -f /app/sessions/app.py \
 && test -f /app/sessions/sessions_pull_information.py \
 && test -f /app/sessions/Config_sessions.py \
 && test -d /app/backend \
 && test -s /app/sessions/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/sessions/secrets
ENV PYTHONPATH=/app:/app/backend:/app/sessions
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /mnt/myssd/LucidTops/sessions/secrets /mnt/myssd/LucidTops

COPY sessions/sessions_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# WORKDIR matches sessions Python package content (§16.3)
WORKDIR /app/sessions

ENTRYPOINT ["/entrypoint.sh"]
