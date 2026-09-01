# infrastructure/containers/lucid-server-default/Dockerfile
# LucidTops master server — Tor daemon + FastAPI (sessions on same container)
# Target: linux/arm64 (Raspberry Pi)

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend

ENV LUCID_PROJECT_ROOT=/app
ENV PYTHONPATH=/app:/app/backend
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV CONTAINER_ONION_DIR=/app/run/lucid/onion
ENV HOST_TOR_LUCID_SERVER_DIR=/app/var/lib/tor/lucid_server
ENV HOST_TOR_LUCID_PORTAL_DIR=/app/var/lib/tor/lucid_portal
ENV HOST_TOR_LUCID_DEV_DIR=/app/var/lib/tor/lucid_node

COPY infrastructure/containers/lucid-server-default/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
