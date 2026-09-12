"""Validate AdminID TokenID against LucidTopsUserDB at time of operation.

Restriction: uses a generated TokenID stored in the LucidTopsUserDB to compare to for validation.
Validation URL and SOCKS/proxy settings are pulled from secrets — never hardcoded.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_admingui_{module_name}"
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


_admin_secrets = _load_local("admin_secrets")
get_admin_secret = _admin_secrets.get_admin_secret
require_admin_secret = _admin_secrets.require_admin_secret
ensure_admin_secrets_from_pull = _admin_secrets.ensure_admin_secrets_from_pull
load_admin_secrets = _admin_secrets.load_admin_secrets


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identity_from_secrets() -> dict[str, str]:
    admin_id = get_admin_secret("ADMIN_ID") or get_admin_secret("ADMINID")
    token_id = get_admin_secret("TOKEN_ID")
    if not admin_id:
        raise RuntimeError(
            "ADMIN_ID missing from ID.secrets — must exist at time of operation"
        )
    if not token_id:
        raise RuntimeError(
            "TOKEN_ID missing from ID.secrets — must exist at time of operation"
        )
    return {"admin_id": admin_id, "token_id": token_id}


def _socks_proxy_url() -> str:
    explicit = get_admin_secret("ADMIN_SOCKS_PROXY")
    if explicit:
        return explicit
    host = get_admin_secret("ADMIN_SOCKS_HOST")
    port = get_admin_secret("ADMIN_SOCKS_PORT")
    if host and port:
        return f"socks5h://{host}:{port}"
    return ""


def _install_socks_opener(proxy_url: str) -> None:
    """Bind SOCKS via PySocks + process proxy env when proxy URL is configured."""
    if not proxy_url:
        return
    try:
        import socks  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ADMIN_SOCKS_PROXY configured but PySocks is not installed — "
            "add PySocks to AdminGui requirements and rebuild"
        ) from exc
    import os

    os.environ["ALL_PROXY"] = proxy_url
    os.environ["all_proxy"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["HTTP_PROXY"] = proxy_url


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 45.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(
            f"LucidTopsUserDB validation HTTP {exc.code}: {detail[:400]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"LucidTopsUserDB validation unreachable: {exc.reason}"
        ) from exc

    if not raw.strip():
        return {"status": status, "ok": status < 400}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "LucidTopsUserDB validation returned non-JSON — check ADMIN_USERDB_VALIDATE_URL"
        ) from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("LucidTopsUserDB validation payload must be an object")
    loaded.setdefault("http_status", status)
    return loaded


def validate_admin_token(*, reload: bool = True) -> dict[str, Any]:
    """Compare AdminID + TokenID from ID.secrets to LucidTopsUserDB via operation-time URL."""
    ensure_admin_secrets_from_pull(reload=reload)
    load_admin_secrets(reload=True)
    identity = _identity_from_secrets()
    validate_url = require_admin_secret("ADMIN_USERDB_VALIDATE_URL")

    proxy = _socks_proxy_url()
    if proxy:
        _install_socks_opener(proxy)

    payload = {
        "AdminID": identity["admin_id"],
        "TOKEN_ID": identity["token_id"],
        "TokenID": identity["token_id"],
    }
    result = _post_json(validate_url, payload)

    ok = bool(
        result.get("ok")
        or result.get("valid")
        or result.get("authenticated")
        or result.get("match")
        or str(result.get("status", "")).lower() in {"ok", "valid", "matched", "success"}
    )
    # Explicit false flags win
    for key in ("ok", "valid", "authenticated", "match"):
        if key in result and result[key] is False:
            ok = False
    if not ok:
        raise RuntimeError(
            "AdminID TokenID failed LucidTopsUserDB validation — "
            "ID.secrets must match the generated TokenID stored in LucidTopsUserDB"
        )

    return {
        "status": "validated",
        "admin_id": identity["admin_id"],
        "token_present": True,
        "validate_url_configured": True,
        "socks_used": bool(proxy),
        "response": {
            k: result[k]
            for k in ("status", "ok", "valid", "authenticated", "match", "http_status")
            if k in result
        },
        "validated_at": utc_now(),
    }


def require_validated_admin() -> dict[str, Any]:
    return validate_admin_token(reload=True)
