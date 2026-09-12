# LucidTops blockchain — FastAPI/DockerDNS core ledger container (fixes.txt §6 / §16).
# Called via MasterServer, NodeUser, AdminUser, MasterClassUser, and User.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/blockchain/Blockchain.dockerfile \
#     -t lucid-blockchain:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/blockchain/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; bind addresses come from hardware pull → blockchain.secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BLOCKCHAIN_SECRETS_NAME=blockchain.secrets \
    LUCID_TOPS_ROOT=/mnt/myssd/LucidTops \
    SECRETS_DIR=/mnt/myssd/LucidTops/blockchain/secrets

WORKDIR /app/blockchain

# OS-native packages listed in blockchain/requirements.txt comments.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY blockchain/requirements.txt /app/blockchain/requirements.txt
RUN test -s /app/blockchain/requirements.txt \
 && pip install --no-cache-dir -r /app/blockchain/requirements.txt

COPY blockchain/ /app/blockchain/

RUN test -f /app/blockchain/requirements.txt \
 && test -s /app/blockchain/requirements.txt \
 && test -f /app/blockchain/docker-entrypoint.sh \
 && test -f /app/blockchain/Blockchain-core.py \
 && test -f /app/blockchain/pull_information.py \
 && test -f /app/blockchain/blockchain_secrets.py \
 && chmod +x /app/blockchain/docker-entrypoint.sh

COPY blockchain/docker-entrypoint.sh /usr/local/bin/blockchain-entrypoint.sh
RUN chmod +x /usr/local/bin/blockchain-entrypoint.sh \
 && test -f /usr/local/bin/blockchain-entrypoint.sh \
 && mkdir -p /mnt/myssd/LucidTops/blockchain/secrets /mnt/myssd/LucidTops

# Host SSD mount at run time (secrets, ledger replica, LucidTops root)
VOLUME ["/mnt/myssd/LucidTops"]

ENTRYPOINT ["/usr/local/bin/blockchain-entrypoint.sh"]
CMD ["serve"]
