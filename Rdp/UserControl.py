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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_settings_js() -> dict[str, Any]:
    path = Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def user_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "user_dns": get_rdp_secret("PROXY_USER_DNS") or require_rdp_secret("RDP_USER_DNS"),
        "sessions_dns": get_rdp_secret("PROXY_SESSIONS_DNS") or require_rdp_secret("RDP_SESSIONS_DNS"),
        "operations_dns": get_rdp_secret("PROXY_OPERATIONS_DNS")
        or get_rdp_secret("RDP_OPERATIONS_DNS"),
        "sessions_port": require_rdp_secret_int("RDP_SESSIONS_PORT"),
        "checked_at": utc_now(),
    }


def enforce_user_controls(
    *, user_id: str, id_token: str, settings: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/IDToken missing for user control")
    cfg = user_control_config()
    applied = dict(_load_settings_js())
    if settings:
        applied.update(settings)
    return {
        "status": "enforced",
        "user_id": user_id,
        "token_id_present": bool(id_token.strip()),
        "settings_applied": applied,
        "config": cfg,
        "enforced_at": utc_now(),
    }
