"""UsbControl — USB port use for the Rdp container.

purpose (documentation/fixes.txt §4 criterion 8):
- allows USB port use inside an active SessionID.
- device inventory is pulled from hardware at time of operation (createRDP.pull_information).

requirements:
- compatible with DockerDNS / FastAPI (RdpRoutes.py)
- SessionID mandatory
- no hardcoded device lists

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
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
get_rdp_secret = _rdp_secrets.get_rdp_secret
load_rdp_secrets = _rdp_secrets.load_rdp_secrets

_ATTACHED: dict[str, dict[str, Any]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _devices_from_secrets() -> list[dict[str, str]]:
    raw = get_rdp_secret("RDP_USB_DEVICES_JSON")
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [row for row in loaded if isinstance(row, dict)]


def refresh_usb_from_hardware() -> list[dict[str, str]]:
    """Re-pull USB inventory from hardware and update rdp.secrets."""
    create_rdp = _load_local("createRDP", "createRDP.py")
    info = create_rdp.pull_information()
    devices = list(info.get("usb_devices") or [])
    path = _rdp_secrets.rdp_secrets_path()
    current = _rdp_secrets.parse_secrets_file(path) if path.exists() else {}
    current["RDP_USB_DEVICES_JSON"] = json.dumps(devices, separators=(",", ":"))
    current["PULLED_AT"] = str(info.get("pulled_at") or utc_now())
    if info.get("primary_ip"):
        current["HARDWARE_PRIMARY_IP"] = str(info["primary_ip"])
    if info.get("primary_mac"):
        current["HARDWARE_PRIMARY_MAC"] = str(info["primary_mac"])
    _rdp_secrets.write_secrets_file(path, current)
    load_rdp_secrets(reload=True)
    return devices


def usb_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    devices = _devices_from_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "device_count": len(devices),
        "devices": devices,
        "hardware_ip": get_rdp_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_rdp_secret("HARDWARE_PRIMARY_MAC"),
        "checked_at": utc_now(),
    }


def list_usb_devices(*, session_id: str, refresh: bool = False, control_on: bool = False) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control usb is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for USB")
    if refresh:
        devices = refresh_usb_from_hardware()
    else:
        devices = _devices_from_secrets()
        if not devices:
            devices = refresh_usb_from_hardware()
    return {
        "status": "listed",
        "session_id": str(session_id).strip(),
        "devices": devices,
        "config": usb_control_config(),
        "listed_at": utc_now(),
    }


def attach_usb(
    *, session_id: str, device_id: str, user_id: str, control_on: bool
) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control usb is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for USB attach")
    if not device_id.strip():
        raise RuntimeError("device_id missing")
    if not user_id.strip():
        raise RuntimeError("UserID missing")
    devices = _devices_from_secrets()
    if not devices:
        devices = refresh_usb_from_hardware()
    match = next(
        (
            d
            for d in devices
            if str(d.get("id") or "") == device_id
            or str(d.get("device") or "") == device_id
            or str(d.get("bus") or "") == device_id
        ),
        None,
    )
    if match is None:
        raise RuntimeError("USB device not present on hardware inventory")
    sid = str(session_id).strip()
    _ATTACHED[sid] = {
        "device": match,
        "user_id": user_id,
        "attached_at": utc_now(),
    }
    return {
        "status": "attached",
        "session_id": sid,
        "device": match,
        "user_id": user_id,
        "attached_at": _ATTACHED[sid]["attached_at"],
    }


def detach_usb(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    if not sid:
        raise RuntimeError("session_id missing")
    previous = _ATTACHED.pop(sid, None)
    return {
        "status": "detached",
        "session_id": sid,
        "previous": previous,
        "detached_at": utc_now(),
    }


def usb_control_status(*, session_id: str | None = None) -> dict[str, Any]:
    return {
        "attached": _ATTACHED.get(str(session_id).strip()) if session_id else dict(_ATTACHED),
        "config": usb_control_config(),
        "checked_at": utc_now(),
    }
