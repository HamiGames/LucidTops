# LucidTops sessions — FastAPI/uvicorn; DockerDNS peer meeting location for Rdp.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/sessions/sessions.dockerfile \
#     -t lucid-sessions \
#     /mnt/myssd/LucidTops
#
# Target: linux/arm64 (Raspberry Pi)
# Operation-time: sessions_pull_information.py + sessions.secrets (IP/MAC/DockerDNS from hardware)
# MasterServer creates SessionID only; non-standard chunk/New_BlockID → operations.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY sessions/requirements.txt /app/sessions/requirements.txt
RUN pip install --no-cache-dir -r /app/sessions/requirements.txt

COPY backend /app/backend
COPY sessions /app/sessions

RUN test -f /app/sessions/sessions_entrypoint.sh \
 && test -d /app/backend \
 && test -s /app/sessions/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV PYTHONPATH=/app:/app/backend:/app/sessions

COPY sessions/sessions_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
