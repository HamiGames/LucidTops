""" this is the script for the code required for a peer to peer keyboard control system.
libraries:
- pynput
- opencv-python
- mss
- python-socks
- torpy
- stem

requirements:
- must all for settings override (settings.js file)
- compatible with nginx reverse proxy
- compatible with DockerDNS
- uses FastAPI routing system(RdpRoutes.py)
"""


from __future__ import annotations

import importlib.util
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

_LAST_EVENT: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def keyboard_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "poll_interval_ms": require_rdp_secret_int("RDP_KEYBOARD_POLL_INTERVAL_MS"),
        "socks_host": require_rdp_secret("TOR_SOCKS_HOST"),
        "socks_port": require_rdp_secret_int("TOR_SOCKS_PORT"),
        "checked_at": utc_now(),
    }


def _inject_key(*, key: str, action: str) -> None:
    try:
        from pynput.keyboard import Controller, Key
    except ImportError as exc:
        raise RuntimeError(f"keyboard control library missing: {exc}") from exc
    controller = Controller()
    named = getattr(Key, key.strip().lower(), None)
    target = named if named is not None else key
    act = action.strip().lower()
    if act in {"press", "down"}:
        controller.press(target)
    elif act in {"release", "up"}:
        controller.release(target)
    elif act in {"type", "tap"}:
        controller.tap(target) if hasattr(controller, "tap") else controller.press(target)
        if not hasattr(controller, "tap"):
            controller.release(target)
    else:
        raise RuntimeError(f"unsupported keyboard action: {action}")


def apply_keyboard_event(
    *,
    session_id: str,
    key: str,
    action: str,
    control_on: bool,
    caller_is_host: bool,
) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control keyboard is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for keyboard control")
    if not key.strip():
        raise RuntimeError("key missing")
    if not action.strip():
        raise RuntimeError("action missing")
    if caller_is_host:
        raise RuntimeError("host keyboard is local — viewer events are the remote control path")
    _inject_key(key=key, action=action)
    event = {
        "status": "applied",
        "session_id": str(session_id).strip(),
        "key": key,
        "action": action,
        "applied_at": utc_now(),
    }
    _LAST_EVENT[str(session_id).strip()] = event
    return event


def clear_keyboard_session(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    previous = _LAST_EVENT.pop(sid, None)
    return {"status": "cleared", "session_id": sid, "previous": previous, "cleared_at": utc_now()}


def keyboard_control_status(*, session_id: str | None = None) -> dict[str, Any]:
    return {
        "last_event": _LAST_EVENT.get(str(session_id).strip()) if session_id else dict(_LAST_EVENT),
        "config": keyboard_control_config(),
        "checked_at": utc_now(),
    }
