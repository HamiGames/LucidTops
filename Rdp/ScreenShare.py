""" this is the script for the code required for a peer to peer screen sharing system.
this will be used in the Rdp container to share the screen of the user to the other users via the LucidTops system.

networking:
- uses mss, python-socks, opencv-python and stem libraries.

requirements:
- must all for settings override (settings.js file)
- compatible with nginx reverse proxy
- compatible with DockerDNS

concerns:
- Tor network block all connections to the screen sharing system.
- the FastAPI routing system must be compatible with the screen sharing system.
- the screen sharing system must be compatible with the Rdp container.
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

_RUNTIME: dict[str, Any] = {"sessions": {}}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def settings_override_path() -> Path:
    return Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser()


def _load_settings_override() -> dict[str, Any]:
    path = settings_override_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def screen_share_config() -> dict[str, Any]:
    load_rdp_secrets()
    overrides = _load_settings_override()
    frame = overrides.get("frame_interval_ms")
    max_w = overrides.get("max_width")
    max_h = overrides.get("max_height")
    return {
        "settings_js": settings_override_path().as_posix(),
        "frame_interval_ms": int(frame)
        if frame is not None
        else require_rdp_secret_int("RDP_SCREEN_FRAME_INTERVAL_MS"),
        "max_width": int(max_w)
        if max_w is not None
        else require_rdp_secret_int("RDP_SCREEN_MAX_WIDTH"),
        "max_height": int(max_h)
        if max_h is not None
        else require_rdp_secret_int("RDP_SCREEN_MAX_HEIGHT"),
        "socks_host": require_rdp_secret("TOR_SOCKS_HOST"),
        "socks_port": require_rdp_secret_int("TOR_SOCKS_PORT"),
        "nginx_compatible": require_rdp_secret("RDP_NGINX_COMPATIBLE"),
        "dockerdns_compatible": require_rdp_secret("RDP_DOCKERDNS_COMPATIBLE"),
        "hardware_ip": get_rdp_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_rdp_secret("HARDWARE_PRIMARY_MAC"),
        "checked_at": utc_now(),
    }


def start_screen_share(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for screenshare")
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/IDToken missing for screen share")
    cfg = screen_share_config()
    sid = str(session_id).strip()
    _RUNTIME["sessions"][sid] = {
        "user_id": user_id,
        "started_at": utc_now(),
        "status": "streaming",
    }
    return {
        "status": "started",
        "session_id": sid,
        "user_id": user_id,
        "config": cfg,
        "started_at": _RUNTIME["sessions"][sid]["started_at"],
    }


def stop_screen_share(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    if not sid:
        raise RuntimeError("session_id missing")
    entry = _RUNTIME["sessions"].pop(sid, None)
    return {
        "status": "stopped",
        "session_id": sid,
        "previous": entry,
        "stopped_at": utc_now(),
    }


def screen_share_status(*, session_id: str | None = None) -> dict[str, Any]:
    if session_id:
        sid = str(session_id).strip()
        return {
            "session_id": sid,
            "active": sid in _RUNTIME["sessions"],
            "session": _RUNTIME["sessions"].get(sid),
            "config": screen_share_config(),
            "checked_at": utc_now(),
        }
    return {
        "active_sessions": list(_RUNTIME["sessions"].keys()),
        "config": screen_share_config(),
        "checked_at": utc_now(),
    }
