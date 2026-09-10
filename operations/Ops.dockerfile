# LucidTops operations — FastAPI/uvicorn; DockerDNS on the operations network.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/operations/Ops.dockerfile \
#     -t lucid-operations \
#     /mnt/myssd/LucidTops
#
# Target: linux/arm64 (Raspberry Pi)
# Operation-time: ops_pull_information.py + operations.secrets + ID.secrets
# Operators: NodeID | AdminID | MasterUserID | MasterServerID in LucidTopsNodeDB.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY operations/requirements.txt /app/operations/requirements.txt
RUN pip install --no-cache-dir -r /app/operations/requirements.txt

COPY backend /app/backend
COPY operations /app/operations
COPY sessions /app/sessions
COPY blockchain /app/blockchain
COPY frontend /app/frontend

RUN test -f /app/operations/ops_entrypoint.sh \
 && test -d /app/backend \
 && test -d /app/sessions \
 && test -d /app/blockchain \
 && test -d /app/frontend \
 && test -s /app/operations/requirements.txt

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV PYTHONPATH=/app:/app/backend:/app/operations

COPY operations/ops_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
