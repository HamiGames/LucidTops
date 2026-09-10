# LucidTops PaySystems — internal FastAPI payment container
# MasterServer + AdminUser access; ClearNet egress via Proxy Clearnet-package.
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build:
#   docker build \
#     -f /mnt/myssd/LucidTops/PaySystems/Pay.dockerfile \
#     -t lucid-paysystems \
#     /mnt/myssd/LucidTops
#
# Operation-time: payments.secrets + bind host/port from hardware pull / MasterServer.

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY PaySystems/requirements.txt /app/PaySystems/requirements.txt
RUN pip install --no-cache-dir -r /app/PaySystems/requirements.txt

COPY PaySystems /app/PaySystems
COPY proxy /app/proxy

RUN test -f /app/PaySystems/PayRoutes.py \
 && test -f /app/PaySystems/PaymentRoutes.py \
 && test -f /app/PaySystems/pay_entrypoint.sh \
 && test -s /app/PaySystems/requirements.txt \
 && test -d /app/proxy

ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ENV PYTHONPATH=/app:/app/PaySystems:/app/proxy

COPY PaySystems/pay_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
