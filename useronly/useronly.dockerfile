# LucidTops UserOnly — downloadable GUI container (fixes.txt §14 / §16).
# Built from the useronly directory.
# Image tag: lucid-useronly:v1.0.0
# Ports: none (operational binds come from secrets at time of operation).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/useronly/useronly.dockerfile \
#     -t lucid-useronly:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/useronly/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC and paths come from pull → secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Target host: Raspberry Pi (pi-5) via SSH. Operation originates from cd /mnt/myssd/LucidTops.

FROM python:3.11-slim-bookworm

WORKDIR /app

# OS-native libraries required for Tk UserOnly GUI (listed in requirements.txt comments).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3-tk \
      tk \
      libx11-6 \
      libxext6 \
      libxrender1 \
      libxtst6 \
      libxi6 \
 && rm -rf /var/lib/apt/lists/*

COPY useronly/requirements.txt /app/useronly/requirements.txt
RUN test -s /app/useronly/requirements.txt \
 && pip install --no-cache-dir -r /app/useronly/requirements.txt

COPY useronly /app/useronly

RUN test -f /app/useronly/user_gui.py \
 && test -f /app/useronly/user_secrets.py \
 && test -f /app/useronly/pull_information.py \
 && test -f /app/useronly/LaunchUser.py \
 && test -f /app/useronly/install.py \
 && test -f /app/useronly/__main__.py \
 && test -s /app/useronly/requirements.txt

ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/useronly/secrets
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Secrets directory is expected at runtime (bind-mount); create path for validation.
RUN mkdir -p /mnt/myssd/LucidTops/useronly/secrets /mnt/myssd/LucidTops

# WORKDIR matches useronly Python package; PYTHONPATH=/app enables python -m useronly (§16.3)
WORKDIR /app/useronly

ENTRYPOINT ["python", "-m", "useronly"]
