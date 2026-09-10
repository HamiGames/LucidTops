""" creates a tunnel to the MasterServer[server.Dockerfile] (DockerDNS compatible)
includes:
- attaches all handshake content to the request for access to the MasterServer[server.Dockerfile] (DockerDNS compatible)
- is the binding for the Website access point to the LucidTops system via the Tor Hidden Service (@*.onion)
operational requirements:
- uses nginx reverse proxy system
- uses DockerDNS for network communication
- uses Tor Hidden Service and Docker Network for network communications as a fallback
- uses MongoDB 7.0.0 or higher for database storage
- requires registration with the MasterServer (uvicorn server and FastAPI system) to be operational
- stabalizes connection to the MasterServer (uvicorn server and FastAPI system)
- ensures the connection is secure and encrypted
- uses (mnt/myssd/LucidTops/secrets/backend.secrets) for authentication and encryption requirements
Flexability:
- used to acces the Node network (NodeNet [DockerDNS]), if a TokenID and UserID are provided in the request.
- used for the Node network to synchronize with the MasterServer (UserDB [LucidTopsDB]),for UserID and TokenID validation.

"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_frontend_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_frontend_secrets = _load_local("frontend_secrets")
require_frontend_secret = _frontend_secrets.require_frontend_secret
get_frontend_secret = _frontend_secrets.get_frontend_secret
load_frontend_secrets = _frontend_secrets.load_frontend_secrets
frontend_status = _frontend_secrets.frontend_status
ensure_frontend_secrets_from_pull = _frontend_secrets.ensure_frontend_secrets_from_pull


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def master_tunnel_endpoint() -> str:
    ensure_frontend_secrets_from_pull()
    base_path = require_frontend_secret("API_BASE_PATH")
    scheme = require_frontend_secret("FRONTEND_TUNNEL_SCHEME")
    onion = get_frontend_secret("MASTER_SERVER_ONION") or get_frontend_secret(
        "FRONTEND_MASTER_ONION"
    )
    if onion:
        return f"{scheme}://{onion}{base_path}"
    host = require_frontend_secret("MASTER_SERVER_INTERNAL_HOST")
    port = require_frontend_secret("MASTER_SERVER_INTERNAL_PORT")
    return f"{scheme}://{host}:{port}{base_path}"


def _handshake_headers(*, user_id: str | None, token_id: str | None) -> dict[str, str]:
    ensure_frontend_secrets_from_pull()
    key = require_frontend_secret("FRONTEND_TUNNEL_HMAC_KEY").encode("utf-8")
    stamp = utc_now()
    material = f"{stamp}:{user_id or ''}:{token_id or ''}".encode("utf-8")
    signature = hmac.new(key, material, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Lucid-Tunnel-Timestamp": stamp,
        "X-Lucid-Tunnel-HMAC": signature,
        "X-Lucid-Proxy-Source": require_frontend_secret("FRONTEND_PROXY_SOURCE"),
    }
    if user_id:
        headers["X-Lucid-UserID"] = user_id
    if token_id:
        headers["X-Lucid-TokenID"] = token_id
    return headers


def open_master_tunnel(
    *,
    path: str,
    payload: bytes | None = None,
    user_id: str | None = None,
    token_id: str | None = None,
) -> dict[str, Any]:
    """Open a handshake-authenticated tunnel to the MasterServer."""
    if not path.strip():
        raise RuntimeError("tunnel path missing")
    ensure_frontend_secrets_from_pull()
    endpoint = urljoin(master_tunnel_endpoint().rstrip("/") + "/", path.lstrip("/"))
    headers = _handshake_headers(user_id=user_id, token_id=token_id)
    method = "POST" if payload is not None else "GET"
    request = Request(endpoint, data=payload, headers=headers, method=method)
    timeout = float(require_frontend_secret("FRONTEND_TUNNEL_TIMEOUT"))
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 — URL from secrets
        body = response.read()
        return {
            "status_code": getattr(response, "status", None),
            "endpoint": endpoint,
            "body": body.decode("utf-8", errors="replace"),
            "checked_at": utc_now(),
            **frontend_status(),
        }


def tunnel_status() -> dict[str, Any]:
    ensure_frontend_secrets_from_pull()
    return {
        "endpoint": master_tunnel_endpoint(),
        **frontend_status(),
        "checked_at": utc_now(),
    }
