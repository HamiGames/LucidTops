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
# Secrets (User.txt / containers.txt):
#   Runtime connection file inside the image: /app/secrets/userGui.secrets
#   Built at image creation from Server/Secrets/proxy.secrets and Master.secrets.
#   Other user *.secrets and *.json stay in the local LucidTops program folder.
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC and paths come from pull → secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# No published ports. No DockerDNS network join.
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

# Creation-time routes. Both files must be in the build context
# (Server/Secrets on /mnt/myssd/LucidTops). The build fails when either is missing.
COPY Server/Secrets/proxy.secrets /app/useronly/internal/source/proxy.secrets
COPY Server/Secrets/Master.secrets /app/useronly/internal/source/Master.secrets

RUN test -s /app/useronly/internal/source/proxy.secrets \
 && test -s /app/useronly/internal/source/Master.secrets \
 && test -f /app/useronly/user_gui.py \
 && test -f /app/useronly/user_secrets.py \
 && test -f /app/useronly/pull_information.py \
 && test -f /app/useronly/internal_routes.py \
 && test -f /app/useronly/frontend_access.py \
 && test -f /app/useronly/LaunchUser.py \
 && test -f /app/useronly/LaunchNodeUser.py \
 && test -f /app/useronly/install.py \
 && test -f /app/useronly/__main__.py \
 && test -s /app/useronly/requirements.txt \
 && mkdir -p /app/secrets \
 && python -c "import sys; sys.path.insert(0, '/app/useronly'); from pull_information import write_usergui_secrets_at_image_build; write_usergui_secrets_at_image_build()" \
 && test -s /app/secrets/userGui.secrets

ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/app/secrets
ENV USER_SECRETS_FILE=/app/secrets/userGui.secrets
ENV USER_SECRETS_NAME=userGui.secrets
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# WORKDIR matches useronly Python package; PYTHONPATH=/app enables python -m useronly (§16.3)
WORKDIR /app/useronly

ENTRYPOINT ["python", "-m", "useronly"]
