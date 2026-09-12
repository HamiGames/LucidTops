# LucidTops Frontend webpage — nginx + Tor *.onion public access point (fixes.txt §3 / §16).
# At time of operation: pull hardware → frontend.secrets → runtime-config.js → nginx.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/frontend/webpage.dockerfile \
#     -t lucid-frontend:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Secrets mount (§16.1):
#   /mnt/myssd/LucidTops/frontend/secrets/*.secrets
#
# RULES:
# - No hardcoded operational IPs/ports/onions/tokens in the image.
# - Values created at time of operation via pull → secrets → runtime-config.js.
# - no sensitive data; no GIT pull.
#
# Rebuild rule (§16.7): if image exists, wipe generated content and volumes before rebuild.
# Networks (§16.4): created/joined at operation via dockercmd.txt using names from secrets.

FROM nginx:1.27-alpine

# OS-native packages listed in frontend/requirements.txt comments.
RUN apk add --no-cache python3 py3-pip

WORKDIR /opt/lucid/frontend

COPY frontend/requirements.txt /opt/lucid/frontend/requirements.txt
RUN test -s /opt/lucid/frontend/requirements.txt \
 && pip3 install --no-cache-dir --break-system-packages -r /opt/lucid/frontend/requirements.txt

COPY frontend/pull_information.py \
     frontend/bootstrap_frontend.py \
     frontend/frontend_secrets.py \
     frontend/tunnel.py \
     ./

COPY frontend/webpage/ /opt/lucid/frontend/webpage/

COPY frontend/home_page.js \
     frontend/login.js \
     frontend/register.js \
     frontend/logout.js \
     frontend/tier-select.js \
     frontend/node-registration.js \
     frontend/dashboard.js \
     frontend/find-peer.js \
     frontend/connect-handshake.js \
     frontend/settings.js \
     frontend/RemoteView.js \
     frontend/LucidLedger.js \
     frontend/LucidMarket.js \
     frontend/AdminHome.js \
     frontend/MasterUser-dashboard.js \
     /opt/lucid/frontend/webpage/

COPY frontend/docker-entrypoint.sh /docker-entrypoint-frontend.sh

RUN test -f /opt/lucid/frontend/pull_information.py \
 && test -f /opt/lucid/frontend/bootstrap_frontend.py \
 && test -f /opt/lucid/frontend/frontend_secrets.py \
 && test -f /opt/lucid/frontend/tunnel.py \
 && test -f /opt/lucid/frontend/webpage/home_page.js \
 && test -f /opt/lucid/frontend/webpage/AdminHome.js \
 && test -f /opt/lucid/frontend/webpage/assets/lucid-theme.css \
 && test -f /docker-entrypoint-frontend.sh \
 && test -s /opt/lucid/frontend/requirements.txt \
 && chmod +x /docker-entrypoint-frontend.sh \
 && mkdir -p /opt/lucid/frontend/nginx /var/log/nginx \
 && mkdir -p /mnt/myssd/LucidTops/frontend/secrets /mnt/myssd/LucidTops

ENV FRONTEND_WEBPAGE_ROOT=/opt/lucid/frontend/webpage \
    LUCID_TOPS_ROOT=/mnt/myssd/LucidTops \
    SECRETS_DIR=/mnt/myssd/LucidTops/frontend/secrets \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["/docker-entrypoint-frontend.sh"]
