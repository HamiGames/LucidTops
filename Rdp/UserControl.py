""" this is the script for the code required for a peer to peer user control system.
scope: 
this script ensures the data from the settings.js file is implemented and reinforced while using the Rdp container.
this script ensures the user interface for the remote desktop system is controlled and secure.

requirements:
- must all for settings override (settings.js file)
- compatible with nginx reverse proxy
- compatible with DockerDNS
- compatible with FastAPI routing system(RdpRoutes.py)
- compatible with the User container (via DockerDNS and FastAPI routing system)
- compatible with the Sessions container (via DockerDNS and FastAPI routing system)
- compatible with the Operations container (via DockerDNS and FastAPI routing system)

"""


from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_rdp_{module_name.replace('-', '_')}"
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


_rdp_secrets = _load_local("rdp_secrets")
require_rdp_secret = _rdp_secrets.require_rdp_secret
require_rdp_secret_int = _rdp_secrets.require_rdp_secret_int
get_rdp_secret = _rdp_secrets.get_rdp_secret
load_rdp_secrets = _rdp_secrets.load_rdp_secrets
rdp_status = _rdp_secrets.rdp_status
_dns = _load_local("DockerDns")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def controls_from_operations(body: dict[str, Any]) -> dict[str, Any]:
    """Session_settings object. Name kept for existing callers."""
    return _dns.controls_from_body(body)


def control_enabled(controls: dict[str, Any], key: str) -> bool:
    value = controls.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def require_control(
    *,
    validation: dict[str, Any],
    user_id: str,
    id_token: str,
    key: str,
) -> dict[str, Any]:
    """Host settings.js controls frozen on the SessionID. Viewer cannot change them."""
    session_id = str(validation.get("session_id") or validation.get("sessionID") or "")
    host_user_id = str(validation.get("hostUserID") or "")
    if not session_id or not host_user_id:
        raise RuntimeError("host control requires an active SessionID and hostUserID")
    loaded = _dns.load_host_controls(
        session_id=session_id,
        user_id=user_id,
        id_token=id_token,
        host_user_id=host_user_id,
    )
    controls = controls_from_operations(loaded)
    if not control_enabled(controls, key):
        raise RuntimeError(f"host control disabled: {key}")
    return {"controls": controls, "operations": loaded}


def user_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "user_dns": get_rdp_secret("PROXY_USER_DNS") or require_rdp_secret("RDP_USER_DNS"),
        "sessions_dns": get_rdp_secret("PROXY_SESSIONS_DNS") or require_rdp_secret("RDP_SESSIONS_DNS"),
        "backend_dns": require_rdp_secret("RDP_BACKEND_DNS"),
        "sessions_port": require_rdp_secret_int("RDP_SESSIONS_PORT"),
        "checked_at": utc_now(),
    }


def settings_from_file() -> dict[str, Any]:
    """Host settings.js written on the user console at container start."""
    path = Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _settings_same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("mouse", "keyboard", "audio", "video", "screen", "usb", "transfer", "transfer_paths")
    for key in keys:
        if key not in left and key not in right:
            continue
        if left.get(key) != right.get(key):
            return False
    return True


def enforce_user_controls(
    *,
    user_id: str,
    id_token: str,
    session_id: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/IDToken missing for user control")
    if not str(session_id).strip():
        raise RuntimeError("SessionID missing for user control")
    cfg = user_control_config()
    validation = _dns.fetch_validation(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    host_user_id = str(validation.get("hostUserID") or "")
    if user_id != host_user_id:
        raise RuntimeError(
            "attempt to override the Host_UserID settings is a breach of container use"
        )
    loaded = _dns.load_host_controls(
        session_id=session_id,
        user_id=user_id,
        id_token=id_token,
        host_user_id=host_user_id,
    )
    existing = controls_from_operations(loaded)
    if settings:
        if existing and not _settings_same(existing, settings):
            raise RuntimeError(
                "attempt to override the Host_UserID settings is a breach of container use"
            )
        if not existing:
            applied = _dns.apply_host_controls(
                session_id=session_id,
                user_id=user_id,
                id_token=id_token,
                settings=settings,
            )
            existing = controls_from_operations(applied) or settings
    return {
        "status": "enforced",
        "user_id": user_id,
        "session_id": str(session_id).strip(),
        "token_id_present": bool(id_token.strip()),
        "settings_applied": existing,
        "frozen": bool(existing),
        "config": cfg,
        "enforced_at": utc_now(),
    }
