# LucidTops MasterServer (backend) — FastAPI/uvicorn
# Tor/nginx owned by Proxy container.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   docker build \
#     -f /mnt/myssd/LucidTops/backend/Server.dockerfile \
#     -t lucid-server-default \
#     /mnt/myssd/LucidTops
#
# Target: linux/arm64 (Raspberry Pi 5)
# Operation-time secrets: builderMasterServer.py + pull_information.py (hardware pull)
# Paths/ports/hosts: injected at container run from pulled hardware / Master.secrets — not baked here.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend
COPY PaySystems /app/PaySystems

# Fail build if COPY landed empty/missing (negate ghost copy)
RUN test -f /app/backend/main.py \
 && test -f /app/backend/server_entrypoint.sh \
 && test -f /app/operations/ops_entrypoint.sh \
 && test -d /app/sessions \
 && test -d /app/blockchain \
 && test -d /app/frontend \
 && test -f /app/PaySystems/PayRoutes.py \
 && test -s /app/backend/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV PYTHONPATH=/app:/app/backend
ENV RUN_BUILDER_ON_START=true

COPY backend/server_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && test -x /entrypoint.sh -o -f /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
