# this is the Dockerfile to create the uvicorn server backend for the LucidTops system.
# the uvicorn server will be served via the nginx server.
# the uvicorn server will be served via the *.onion address.

# LucidTops master server — Tor daemon + FastAPI (uvicorn)
# Build context: repository root
#   docker build -f backend/Server.dockerfile -t lucid-server-default .
# Target: linux/arm64 (Raspberry Pi 5)
# Operation-time secrets: builderMasterServer.py writes server.secrets to LUCID_TOPS_ROOT/secrets

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tor nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend
COPY paysystems /app/paysystems

ENV LUCID_PROJECT_ROOT=/app
ENV PYTHONPATH=/app:/app/backend
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/secrets
ENV SERVER_ENV_FILE=/mnt/myssd/LucidTops/server.env
ENV SECRETS_ENV_FILE=/mnt/myssd/LucidTops/secrets.env
ENV SERVER_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/server.secrets
ENV CONFIG_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/config.secrets
ENV OPERATIONS_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/operations.secrets
ENV MONGODB_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/mongodb.secrets
ENV BLOCKCHAIN_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/blockchain.secrets
ENV PAYMENTS_SECRETS_FILE=/mnt/myssd/LucidTops/secrets/payments.secrets
ENV HOST_TOR_CONFIG_TORRC=/mnt/myssd/LucidTops/torrc
ENV CONTAINER_ONION_DIR=/app/run/lucid/onion
ENV HOST_TOR_LUCID_SERVER_DIR=/app/var/lib/tor/lucid_server
ENV HOST_TOR_LUCID_PORTAL_DIR=/app/var/lib/tor/lucid_portal
ENV HOST_TOR_LUCID_DEV_DIR=/app/var/lib/tor/lucid_node
ENV MASTER_SERVER_BIND_HOST=127.0.0.1
ENV MASTER_SERVER_TOR_ONLY=true
ENV MASTER_SERVER_PORT=8080
ENV RUN_BUILDER_ON_START=true

COPY backend/server_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/var/lib/tor /app/run/lucid/onion /etc/nginx/conf.d

EXPOSE 8080 80

ENTRYPOINT ["/entrypoint.sh"]
