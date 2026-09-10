# LucidTops Frontend webpage — nginx + Tor *.onion public access point
# At time of operation: pull hardware → frontend.secrets → runtime-config.js → nginx.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/frontend/webpage.dockerfile \
#     -t lucid-frontend \
#     /mnt/myssd/LucidTops
#
# RULES:
# - No hardcoded operational IPs/ports/onions/tokens in the image.
# - Values created at time of operation via pull → secrets → runtime-config.js.

FROM nginx:1.27-alpine

RUN apk add --no-cache python3 py3-pip

WORKDIR /opt/lucid/frontend

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
 && test -f /opt/lucid/frontend/webpage/home_page.js \
 && test -f /opt/lucid/frontend/webpage/AdminHome.js \
 && test -f /opt/lucid/frontend/webpage/assets/lucid-theme.css \
 && test -f /docker-entrypoint-frontend.sh \
 && chmod +x /docker-entrypoint-frontend.sh \
 && mkdir -p /opt/lucid/frontend/nginx /var/log/nginx

ENV FRONTEND_WEBPAGE_ROOT=/opt/lucid/frontend/webpage \
    LUCID_TOPS_ROOT=/mnt/myssd/LucidTops \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["/docker-entrypoint-frontend.sh"]
