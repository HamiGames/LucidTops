"""Bootstrap Frontend container at time of operation.

Flow: hardware pull → frontend.secrets → runtime-config.js → nginx.conf → nginx.
Proxy auth tokens stay in nginx (not browser config).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from pull_information import (  # noqa: E402
    bind_operation_environ,
    build_frontend_secrets,
    pull_realworld_information,
    write_runtime_config_js,
)
from frontend_secrets import (  # noqa: E402
    get_frontend_secret,
    load_frontend_secrets,
    require_frontend_secret,
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def render_nginx_conf(*, secrets: dict[str, str], out_path: Path) -> Path:
    """Render nginx config with operation-time upstream + proxy headers from secrets."""
    bind_host = secrets.get("FRONTEND_NGINX_BIND") or require_frontend_secret("HARDWARE_PRIMARY_IP")
    listen_port = secrets.get("FRONTEND_NGINX_PORT") or require_frontend_secret("FRONTEND_NGINX_PORT")
    webpage = secrets.get("FRONTEND_WEBPAGE_ROOT") or (_DIR / "webpage").as_posix()
    proxy_host = secrets.get("PROXY_INTERNAL_HOST") or ""
    proxy_port = secrets.get("PROXY_INTERNAL_PORT") or ""
    if not proxy_host or not proxy_port:
        raise RuntimeError(
            "PROXY_INTERNAL_HOST/PROXY_INTERNAL_PORT missing — pull/build secrets at time of operation"
        )
    upstream_token = secrets.get("PROXY_NGINX_UPSTREAM_TOKEN") or ""
    api_token = secrets.get("PROXY_API_TOKEN") or ""
    gate_value = secrets.get("PROXY_GATE_HEADER_VALUE") or ""
    proxy_source = secrets.get("FRONTEND_PROXY_SOURCE") or "frontend"
    api_prefix = (secrets.get("PROXY_API_PREFIX") or secrets.get("API_PREFIX") or "/api/v1").rstrip(
        "/"
    )

    conf = f"""# Generated at time of operation - LucidTops Frontend onion webpage
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /tmp/nginx-frontend.pid;

events {{
    worker_connections 1024;
}}

http {{
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;
    server_tokens off;

    upstream lucid_proxy {{
        server {proxy_host}:{proxy_port};
    }}

    server {{
        # Port from secrets at time of operation; bind all interfaces for Tor/nginx publish.
        # Hardware IP recorded separately as HARDWARE_PRIMARY_IP ({bind_host}).
        listen {listen_port};
        server_name _;

        root {webpage};
        index index.html home.html;

        location /assets/ {{
            try_files $uri =404;
            add_header Cache-Control "no-store";
        }}

        location / {{
            try_files $uri $uri.html /index.html;
        }}

        location {api_prefix}/ {{
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Lucid-Proxy-Source {proxy_source};
            proxy_set_header X-Lucid-Proxy-Token {upstream_token};
            proxy_set_header X-Lucid-Proxy-Gate {gate_value};
            proxy_set_header X-Lucid-API-Token {api_token};
            proxy_pass http://lucid_proxy;
        }}
    }}
}}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(conf, encoding="utf-8")
    return out_path


def bootstrap(*, start_nginx: bool = False) -> dict[str, Any]:
    info = pull_realworld_information()
    bind_operation_environ(info)
    secrets = build_frontend_secrets(info)
    load_frontend_secrets(reload=True)
    runtime = write_runtime_config_js(secrets)
    conf_dir = Path(_env("FRONTEND_NGINX_CONF_DIR") or (_DIR / "nginx"))
    conf_path = render_nginx_conf(
        secrets=secrets, out_path=conf_dir / "frontend.conf"
    )
    report: dict[str, Any] = {
        "pulled_at": info.get("pulled_at"),
        "primary_ip": info.get("primary_ip"),
        "primary_mac": info.get("primary_mac"),
        "secrets_file": _env("FRONTEND_SECRETS_FILE"),
        "runtime_config": runtime.as_posix(),
        "nginx_conf": conf_path.as_posix(),
        "webpage_root": secrets.get("FRONTEND_WEBPAGE_ROOT"),
        "frontend_onion": get_frontend_secret("FRONTEND_ONION"),
    }
    if start_nginx:
        nginx_bin = shutil.which("nginx")
        if not nginx_bin:
            raise RuntimeError("nginx binary missing on hardware at time of operation")
        result = subprocess.run(
            [nginx_bin, "-c", conf_path.as_posix()],
            check=False,
            capture_output=True,
            text=True,
        )
        report["nginx_start"] = {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.returncode != 0:
            raise RuntimeError(f"nginx failed to start: {result.stderr or result.stdout}")
    return report


def main() -> int:
    start = "--start-nginx" in sys.argv
    report = bootstrap(start_nginx=start)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
