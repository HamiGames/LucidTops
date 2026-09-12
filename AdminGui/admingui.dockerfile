# LucidTops AdminGui — downloadable AdminID GUI container (fixes.txt §15 / §16).
# Built from the AdminGui directory.
# Image tag: lucid-admingui:v1.0.0
# Ports: none (operational binds come from secrets at time of operation).
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/AdminGui/admingui.dockerfile \
#     -t lucid-admingui:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/AdminGui/secrets/*.secrets
#
# RULES:
# - no hardcoded values; all values created at time of operation via pull_information.
# - no placeholder values; hardware IP/MAC come from pull → secrets.
# - no sensitive data in this image; data lives in the secrets file.
# - NO pull from GIT repository.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.
# Target host: Raspberry Pi (pi-5) via SSH. Operation originates from cd /mnt/myssd/LucidTops.
#
# restrictions (fixes.txt §15):
#   1. no installer
#   2. uses a generated TokenID stored in the LucidTopsUserDB to compare to for validation.
#   3. will be a container with a security code for downloadable authentication.
#   4. code criteria from fixes.txt §15 (email/code comparison at operation — not baked here).

FROM python:3.11-slim-bookworm

WORKDIR /app

# OS-native libraries required for Tk AdminGui (listed in requirements.txt comments).
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

COPY AdminGui/requirements.txt /app/AdminGui/requirements.txt
RUN test -s /app/AdminGui/requirements.txt \
 && pip install --no-cache-dir -r /app/AdminGui/requirements.txt

COPY AdminGui /app/AdminGui

RUN test -f /app/AdminGui/admin_gui.py \
 && test -f /app/AdminGui/admin_secrets.py \
 && test -f /app/AdminGui/pull_information.py \
 && test -f /app/AdminGui/LaunchAdmin.py \
 && test -f /app/AdminGui/download_auth.py \
 && test -f /app/AdminGui/validate_admin.py \
 && test -f /app/AdminGui/firewall_allow.py \
 && test -f /app/AdminGui/admin_cli.py \
 && test -f /app/AdminGui/__main__.py \
 && test -s /app/AdminGui/requirements.txt

ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV SECRETS_DIR=/mnt/myssd/LucidTops/AdminGui/secrets
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Secrets directory is expected at runtime (bind-mount); create path for validation.
RUN mkdir -p /mnt/myssd/LucidTops/AdminGui/secrets /mnt/myssd/LucidTops

# WORKDIR matches AdminGui Python package; PYTHONPATH=/app enables python -m AdminGui (§16.3)
WORKDIR /app/AdminGui

ENTRYPOINT ["python", "-m", "AdminGui"]
