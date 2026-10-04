# LucidTops Proxy — nginx reverse proxy + Tor + uvicorn/FastAPI (fixes.txt §1 / §16).
# Image tag: lucid-proxy:v1.0.0
#
# COPY context (mandatory — no other context allowed):
#   /mnt/myssd/LucidTops
#
# Build (on Pi, from mounted SSD):
#   cd /mnt/myssd/LucidTops
#   BASE_IMAGE=python:3.11-slim-bookworm
#   APT_PACKAGES="ca-certificates curl gnupg iproute2 nginx tor"
#   sudo docker build --no-cache --platform linux/arm64 \
#     -f /mnt/myssd/LucidTops/proxy/proxy.dockerfile \
#     --build-arg BASE_IMAGE="${BASE_IMAGE}" \
#     --build-arg APT_PACKAGES="${APT_PACKAGES}" \
#     -t lucid-proxy:v1.0.0 \
#     /mnt/myssd/LucidTops
#
# Runtime (gate for Tor and the frontend; secrets stay on the console):
#   sudo docker run --rm \
#     --network <DOCKER_NETWORK_NAME> \
#     -v /mnt/myssd/LucidTops:/mnt/myssd/LucidTops \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     lucid-proxy:v1.0.0
#
# Secrets (Bootstrap / fixes.txt §16 + Server layout):
#   Canonical file: /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
#   §16 directory link: /mnt/myssd/LucidTops/proxy/secrets → Server/Secrets
#   No secrets are baked into the image.
#
# Rebuild rule (§16.7): wipe image/volumes before rebuild.
# Networks (§16.4): join DOCKER_NETWORK_NAME from proxy.secrets / Master.secrets.

# -----------------------------------------------------------------------------
# Build-args (declared before FROM for BASE_IMAGE; re-declared after FROM for use)
# -----------------------------------------------------------------------------
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

# Runtime / install args (NOT used in COPY source paths)
# nginx + tor: the gate. iproute2: hardware pull. gnupg/curl: Docker CLI apt repo.
ARG APT_PACKAGES="ca-certificates curl gnupg iproute2 nginx tor"
ARG INSTALL_DOCKER_CLI=true
ARG PIP_PACKAGES=""
ARG PIP_WHEEL_PACKAGES="pip setuptools wheel"
ARG LUCID_TOPS_ROOT=/mnt/myssd/LucidTops
ARG SECRETS_DIR=/mnt/myssd/LucidTops/Server/Secrets
ARG PROXY_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
ARG MASTER_SECRETS_FILE=/mnt/myssd/LucidTops/Server/Secrets/Master.secrets
ARG PROXY_SECRETS_LINK=/mnt/myssd/LucidTops/proxy/secrets
ARG PROXY_CONFIGS_DIR=/mnt/myssd/LucidTops/proxy/configs
ARG CONTAINER_ONION_DIR=/mnt/myssd/LucidTops/onion
ARG RUN_BOOTSTRAP_ON_BUILD=false

# -----------------------------------------------------------------------------
# Container skeleton (fixes.txt §16.5)
# -----------------------------------------------------------------------------
WORKDIR /app

RUN set -eu; \
    mkdir -p \
      /app/proxy \
      /app/proxy/run \
      /app/proxy/configs \
      /app/proxy/logs \
      "${LUCID_TOPS_ROOT}" \
      "${SECRETS_DIR}" \
      "${PROXY_CONFIGS_DIR}" \
      "${CONTAINER_ONION_DIR}" \
      "${LUCID_TOPS_ROOT}/proxy" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/master_server" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/frontend" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/node_user" \
      "${LUCID_TOPS_ROOT}/tor/hidden_service/rdp" \
      "${LUCID_TOPS_ROOT}/logs/nginx" \
      "${LUCID_TOPS_ROOT}/logs/proxy" \
      "${LUCID_TOPS_ROOT}/run/nginx" \
      "${LUCID_TOPS_ROOT}/run/proxy"; \
    test -d /app/proxy; \
    test -d "${SECRETS_DIR}"; \
    test -d "${LUCID_TOPS_ROOT}"

# Link §16 proxy/secrets → Server/Secrets (proxy.secrets lives here)
RUN set -eu; \
    rm -rf "${PROXY_SECRETS_LINK}"; \
    ln -sfn "${SECRETS_DIR}" "${PROXY_SECRETS_LINK}"; \
    test -L "${PROXY_SECRETS_LINK}"; \
    test "$(readlink -f "${PROXY_SECRETS_LINK}")" = "$(readlink -f "${SECRETS_DIR}")"

# -----------------------------------------------------------------------------
# OS packages + Docker CLI (daemon stays on the Pi via docker.sock)
# -----------------------------------------------------------------------------
RUN set -eu; \
    apt-get update; \
    if [ -n "${APT_PACKAGES}" ]; then \
      apt-get install -y --no-install-recommends ${APT_PACKAGES}; \
    fi; \
    if [ "${INSTALL_DOCKER_CLI}" = "true" ]; then \
      apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
      install -m 0755 -d /etc/apt/keyrings; \
      curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
      chmod a+r /etc/apt/keyrings/docker.gpg; \
      ARCH="$(dpkg --print-architecture)"; \
      . /etc/os-release; \
      echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list; \
      apt-get update; \
      apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin; \
    fi; \
    command -v ip >/dev/null; \
    command -v nginx >/dev/null; \
    command -v tor >/dev/null; \
    if [ "${INSTALL_DOCKER_CLI}" = "true" ]; then \
      command -v docker >/dev/null; \
      docker compose version >/dev/null; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# systemctl is not available in this image. Bootstrap still calls
# systemctl for tor@default and nginx. This shim starts those processes directly.
RUN cat > /usr/local/bin/systemctl <<'EOF'
#!/bin/sh
set -eu

cmd=""
unit=""
for arg in "$@"; do
  case "$arg" in
    start|stop|restart|is-active|list-units|list-unit-files) cmd="$arg" ;;
    --*) ;;
    *) unit="$arg" ;;
  esac
done
unit="${unit%.service}"

secret_value() {
  file="/mnt/myssd/LucidTops/Server/Secrets/proxy.secrets"
  if [ ! -f "$file" ]; then
    return 0
  fi
  grep "^${1}=" "$file" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

tor_up() {
  python3 -c 'import socket; socket.create_connection(("127.0.0.1", 9050), 1).close()' >/dev/null 2>&1
}

write_container_torrc() {
  dest="/etc/lucid-proxy/torrc"
  mkdir -p /etc/lucid-proxy /var/lib/tor /var/log/tor /var/run
  {
    echo "User debian-tor"
    echo "SocksPort 127.0.0.1:9050"
    echo "ControlPort 127.0.0.1:9051"
    echo "CookieAuthentication 1"
    echo "DataDirectory /var/lib/tor"
    echo "PidFile /var/run/tor.pid"
    echo "Log notice file /var/log/tor/notices.log"
  } > "$dest"
  host_torrc="$(secret_value TORRC_PATH)"
  if [ -z "$host_torrc" ]; then
    host_torrc="/mnt/myssd/LucidTops/torrc"
  fi
  if [ -f "$host_torrc" ]; then
    grep -E '^HiddenService' "$host_torrc" >> "$dest" || true
  fi
  snippet="$(secret_value PROXY_TORRC_SNIPPET_PATH)"
  if [ -n "$snippet" ] && [ -f "$snippet" ]; then
    grep -E '^HiddenService' "$snippet" >> "$dest" || true
  fi
  grep '^HiddenServiceDir ' "$dest" | awk '{print $2}' | while read -r hs_dir; do
    [ -n "$hs_dir" ] || continue
    mkdir -p "$hs_dir"
    chown -R debian-tor:debian-tor "$hs_dir"
  done
  chown -R debian-tor:debian-tor /var/lib/tor /var/log/tor /etc/lucid-proxy
  chmod 700 /var/lib/tor
  touch /var/run/tor.pid
  chown debian-tor:debian-tor /var/run/tor.pid
  printf '%s\n' "$dest"
}

start_tor() {
  if tor_up; then
    return 0
  fi
  if ! id debian-tor >/dev/null 2>&1; then
    echo "debian-tor user missing — tor package did not install" >&2
    return 1
  fi
  torrc="$(write_container_torrc)"
  : > /var/log/tor/stdout.log
  chown debian-tor:debian-tor /var/log/tor/stdout.log
  tor -f "$torrc" >>/var/log/tor/stdout.log 2>&1 &
  i=0
  while [ "$i" -lt 30 ]; do
    if tor_up; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.5
  done
  echo "tor did not open 127.0.0.1:9050" >&2
  if [ -s /var/log/tor/stdout.log ]; then
    cat /var/log/tor/stdout.log >&2
  fi
  if [ -s /var/log/tor/notices.log ]; then
    cat /var/log/tor/notices.log >&2
  fi
  return 1
}

stop_tor() {
  if [ -f /var/run/tor.pid ]; then
    kill "$(cat /var/run/tor.pid)" 2>/dev/null || true
    rm -f /var/run/tor.pid
  fi
}

start_nginx() {
  conf="$(secret_value NGINX_CONF_PATH)"
  if [ -n "$conf" ] && [ -f "$conf" ]; then
    nginx -t -c "$conf"
    if [ -f /run/nginx.pid ] && kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; then
      nginx -s reload
      return 0
    fi
    nginx -c "$conf"
    return 0
  fi
  nginx
}

case "$cmd" in
  list-unit-files)
    printf '%s\n' "tor@default.service enabled" "nginx.service enabled"
    ;;
  list-units)
    if tor_up; then
      printf '%s\n' "tor@default.service loaded active running Tor"
    else
      printf '%s\n' "tor@default.service loaded inactive dead Tor"
    fi
    ;;
  is-active)
    case "$unit" in
      tor@default|tor)
        if tor_up; then printf '%s\n' active; else printf '%s\n' inactive; fi
        ;;
      nginx)
        if [ -f /run/nginx.pid ] && kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; then
          printf '%s\n' active
        else
          printf '%s\n' inactive
        fi
        ;;
      *)
        printf '%s\n' inactive
        ;;
    esac
    ;;
  start)
    case "$unit" in
      tor@default|tor) start_tor ;;
      nginx) start_nginx ;;
      *) echo "unsupported unit ${unit}" >&2; exit 1 ;;
    esac
    ;;
  stop)
    case "$unit" in
      tor@default|tor) stop_tor ;;
      nginx) nginx -s quit || true ;;
    esac
    ;;
  restart)
    case "$unit" in
      tor@default|tor) stop_tor; start_tor ;;
      nginx) start_nginx ;;
      *) echo "unsupported unit ${unit}" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "unsupported systemctl command: $*" >&2
    exit 1
    ;;
esac
EOF
RUN chmod 0755 /usr/local/bin/systemctl \
 && systemctl list-unit-files tor@default.service | grep -q tor@default \
 && systemctl is-active tor@default | grep -q inactive

# -----------------------------------------------------------------------------
# Pip wheel installer + requirements (literal COPY — no ARG in source path)
# -----------------------------------------------------------------------------
COPY proxy/requirements.txt /app/proxy/requirements.txt
RUN set -eu; \
    test -s /app/proxy/requirements.txt; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else echo "python interpreter missing — fix BASE_IMAGE / APT_PACKAGES" >&2; exit 1; fi; \
    "${PY}" -m pip install --no-cache-dir --upgrade ${PIP_WHEEL_PACKAGES}; \
    "${PY}" -m pip install --no-cache-dir -r /app/proxy/requirements.txt; \
    if [ -n "${PIP_PACKAGES}" ]; then \
      "${PY}" -m pip install --no-cache-dir ${PIP_PACKAGES}; \
    fi; \
    "${PY}" -c "import fastapi, uvicorn, httpx, pydantic, socks"

# -----------------------------------------------------------------------------
# Copy entire proxy package, then validate required modules (§16.2 / §16.3)
# -----------------------------------------------------------------------------
COPY proxy/ /app/proxy/

RUN set -eu; \
    test -f /app/proxy/Bootstrap.py; \
    test -f /app/proxy/pull_information.py; \
    test -f /app/proxy/RunProxy.py; \
    test -f /app/proxy/ProxyRoutes.py; \
    test -f /app/proxy/ProxyGate.py; \
    test -f /app/proxy/buildsecrets.py; \
    test -f /app/proxy/SetDeamon.py; \
    test -f /app/proxy/Clearnet-package.py; \
    test -s /app/proxy/requirements.txt; \
    test -f /app/proxy/proxy.dockerfile; \
    test -d /app/proxy/run; \
    test -d /app/proxy/configs; \
    test -d /app/proxy/logs; \
    test -L "${PROXY_SECRETS_LINK}"; \
    test -d "${SECRETS_DIR}"; \
    chmod +x /app/proxy/Bootstrap.py /app/proxy/RunProxy.py /app/proxy/pull_information.py

# -----------------------------------------------------------------------------
# Runtime environment
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app/proxy
ENV PYTHONUNBUFFERED=1
ENV LUCID_PROJECT_ROOT=/app
ENV LUCID_TOPS_ROOT=${LUCID_TOPS_ROOT}
ENV SECRETS_DIR=${SECRETS_DIR}
ENV PROXY_SECRETS_FILE=${PROXY_SECRETS_FILE}
ENV MASTER_SECRETS_FILE=${MASTER_SECRETS_FILE}
ENV PROXY_SECRETS_LINK=${PROXY_SECRETS_LINK}
ENV PROXY_CONFIGS_DIR=${PROXY_CONFIGS_DIR}
ENV CONTAINER_ONION_DIR=${CONTAINER_ONION_DIR}

# Optional bootstrap at build (default false — secrets on host / first start)
RUN set -eu; \
    if [ "${RUN_BOOTSTRAP_ON_BUILD}" = "true" ]; then \
      python3 /app/proxy/pull_information.py; \
      test -f "${PROXY_SECRETS_FILE}"; \
    fi

WORKDIR /app/proxy
ENTRYPOINT ["python3", "RunProxy.py"]
CMD ["run"]
