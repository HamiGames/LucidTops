""" this is the script for the code required for a peer to peer mouse control system.
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


def mouse_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "poll_interval_ms": require_rdp_secret_int("RDP_MOUSE_POLL_INTERVAL_MS"),
        "socks_host": require_rdp_secret("TOR_SOCKS_HOST"),
        "socks_port": require_rdp_secret_int("TOR_SOCKS_PORT"),
        "max_width": require_rdp_secret_int("RDP_SCREEN_MAX_WIDTH"),
        "max_height": require_rdp_secret_int("RDP_SCREEN_MAX_HEIGHT"),
        "checked_at": utc_now(),
    }


def _inject_mouse(*, x: int, y: int, button: str, action: str) -> None:
    try:
        from pynput.mouse import Button, Controller
    except ImportError as exc:
        raise RuntimeError(f"mouse control library missing: {exc}") from exc
    name = button.strip().lower()
    if name in {"left", "1"}:
        btn = Button.left
    elif name in {"right", "2"}:
        btn = Button.right
    else:
        btn = Button.middle
    mouse = Controller()
    mouse.position = (x, y)
    act = action.strip().lower()
    if act in {"press", "down"}:
        mouse.press(btn)
    elif act in {"release", "up"}:
        mouse.release(btn)
    elif act == "click":
        mouse.click(btn)
    elif act != "move":
        raise RuntimeError(f"unsupported mouse action: {action}")


def apply_mouse_event(
    *,
    session_id: str,
    x: int,
    y: int,
    button: str,
    action: str,
    control_on: bool,
    caller_is_host: bool,
) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control mouse is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for mouse control")
    if not button.strip() or not action.strip():
        raise RuntimeError("button/action missing for mouse event")
    if caller_is_host:
        raise RuntimeError("host mouse is local — viewer events are the remote control path")
    cfg = mouse_control_config()
    max_w = int(cfg["max_width"])
    max_h = int(cfg["max_height"])
    if x < 0 or y < 0 or x > max_w or y > max_h:
        raise RuntimeError("mouse coordinates outside pulled screen geometry")
    _inject_mouse(x=x, y=y, button=button, action=action)
    event = {
        "status": "applied",
        "session_id": str(session_id).strip(),
        "x": x,
        "y": y,
        "button": button,
        "action": action,
        "applied_at": utc_now(),
    }
    _LAST_EVENT[str(session_id).strip()] = event
    return event


def clear_mouse_session(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    previous = _LAST_EVENT.pop(sid, None)
    return {"status": "cleared", "session_id": sid, "previous": previous, "cleared_at": utc_now()}


def mouse_control_status(*, session_id: str | None = None) -> dict[str, Any]:
    return {
        "last_event": _LAST_EVENT.get(str(session_id).strip()) if session_id else dict(_LAST_EVENT),
        "config": mouse_control_config(),
        "checked_at": utc_now(),
    }
