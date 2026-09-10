# LucidTops blockchain — FastAPI/DockerDNS core ledger container.
# Called via MasterServer, NodeUser, AdminUser, MasterClassUser, and User.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/blockchain/Blockchain.dockerfile \
#     -t lucid-blockchain \
#     /mnt/myssd/LucidTops
#
# Secrets and bind addresses created at container start from hardware pull.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BLOCKCHAIN_SECRETS_NAME=blockchain.secrets \
    LUCID_TOPS_ROOT=/mnt/myssd/LucidTops

WORKDIR /app/blockchain

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY blockchain/requirements.txt /app/blockchain/requirements.txt
RUN pip install --no-cache-dir -r /app/blockchain/requirements.txt

COPY blockchain/ /app/blockchain/

RUN test -f /app/blockchain/requirements.txt \
 && test -s /app/blockchain/requirements.txt \
 && test -f /app/blockchain/docker-entrypoint.sh \
 && test -f /app/blockchain/Blockchain-core.py \
 && chmod +x /app/blockchain/docker-entrypoint.sh

COPY blockchain/docker-entrypoint.sh /usr/local/bin/blockchain-entrypoint.sh
RUN chmod +x /usr/local/bin/blockchain-entrypoint.sh \
 && test -f /usr/local/bin/blockchain-entrypoint.sh

# Host SSD mount at run time (secrets, ledger replica, LucidTops root)
VOLUME ["/mnt/myssd/LucidTops"]

ENTRYPOINT ["/usr/local/bin/blockchain-entrypoint.sh"]
CMD ["serve"]
