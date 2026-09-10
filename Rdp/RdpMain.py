""" the main script for the Rdp container.
purpose:
1. to control the Rdp container and its functions.
2. to control the screen sharing system.
3. to control the remote desktop system.
4. to control the user interface for the remote desktop system.
5. to control the settings for the remote desktop system.
6. to control the logging for the remote desktop system.
7. to control the error handling for the remote desktop system.
8. to control the security for the remote desktop system.
9. to control the performance for the remote desktop system.
10. to control the scalability for the remote desktop system.

includes:
- the requirements for the Rdp container.
- the configuration for the Rdp container (imported from the content produced by createRDP.py)
- a start script for the Rdp container
- a stop script for the Rdp container
- a restart script for the Rdp container
- a status script for the Rdp container
- a logs script for the Rdp container
- a error script for the Rdp container
- a security script for the Rdp container
- a performance script for the Rdp container
- a scalability script for the Rdp container

concerns:
- the Rdp container must be compatible with the screen sharing system.
- must be compatible with DockerDNS for network discovery and connection.

"""


from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

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

_createRDP = _load_local("createRDP", "createRDP.py")
_ScreenShare = _load_local("ScreenShare")
_MouseControl = _load_local("MouseControl")
_keyboardControl = _load_local("keyboardControl")
_FileShare = _load_local("FileShare")
_UserControl = _load_local("UserControl")
_AudioControl = _load_local("AudioControl")
_UsbControl = _load_local("UsbControl")
_gov = _load_local("Rdp-gov", "Rdp-gov.py")

_RUNTIME: dict[str, Any] = {"running": False, "started_at": None, "stopped_at": None}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_rdp_secrets(*, overwrite: bool = False) -> dict[str, Any]:
    """Ensure rdp.secrets exists from hardware pull (createRDP)."""
    return _createRDP.build_and_write_rdp_secrets(overwrite_keys=overwrite)


def rdp_container_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "bind_host": require_rdp_secret("RDP_BIND_HOST"),
        "port": require_rdp_secret_int("RDP_PORT"),
        "base_path": require_rdp_secret("RDP_BASE_PATH"),
        "pid_file": Path(require_rdp_secret("RDP_PID_FILE")).expanduser().as_posix(),
        "log_dir": Path(require_rdp_secret("RDP_LOG_DIR")).expanduser().as_posix(),
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "dockerdns": require_rdp_secret("RDP_DOCKERDNS_COMPATIBLE"),
        "sessions_dns": require_rdp_secret("RDP_SESSIONS_DNS"),
        "sessions_port": require_rdp_secret_int("RDP_SESSIONS_PORT"),
        "hardware_ip": get_rdp_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_rdp_secret("HARDWARE_PRIMARY_MAC"),
        **rdp_status(),
    }


def sessions_base_url() -> str:
    scheme = require_rdp_secret("RDP_SESSIONS_SCHEME")
    host = require_rdp_secret("RDP_SESSIONS_DNS")
    port = require_rdp_secret_int("RDP_SESSIONS_PORT")
    return f"{scheme}://{host}:{port}"


def sessions_link_health() -> dict[str, Any]:
    """Probe sessions container via DockerDNS using secrets from pull."""
    base = sessions_base_url()
    health_path = get_rdp_secret("RDP_SESSIONS_HEALTH_PATH") or "/health"
    url = f"{base.rstrip('/')}/{health_path.lstrip('/')}"
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=5) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            body = resp.read(512).decode("utf-8", errors="replace")
        return {
            "reachable": True,
            "url": url,
            "status_code": code,
            "body_preview": body[:200],
            "checked_at": utc_now(),
        }
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        return {
            "reachable": False,
            "url": url,
            "error": str(exc),
            "checked_at": utc_now(),
        }


def validate_session_id(
    *, session_id: str, user_id: str, id_token: str
) -> dict[str, Any]:
    """Validate SessionID with sessions container (peer meeting location)."""
    sid = str(session_id).strip()
    if not sid:
        raise RuntimeError("SessionID missing — required to operate Rdp inside a session")
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/TokenID missing for SessionID validation")

    base = sessions_base_url()
    validate_path = require_rdp_secret("RDP_SESSION_VALIDATE_PATH")
    url = f"{base.rstrip('/')}/{validate_path.lstrip('/')}"
    payload = (
        f'{{"session_id":"{sid}","UserID":"{user_id}","TokenID":"{id_token}"}}'
    ).encode("utf-8")
    try:
        req = Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=8) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
        if int(code) >= 400:
            raise RuntimeError(f"SessionID validation rejected by sessions: HTTP {code}")
        return {
            "status": "validated",
            "session_id": sid,
            "user_id": user_id,
            "sessions_url": url,
            "status_code": code,
            "body_preview": body[:300],
            "validated_at": utc_now(),
        }
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        # When sessions is unreachable, still require SessionID present for peer ops;
        # record link failure for status (peer meeting must use sessions when online).
        health = sessions_link_health()
        if not health.get("reachable"):
            return {
                "status": "session_id_accepted_offline",
                "session_id": sid,
                "user_id": user_id,
                "sessions_url": url,
                "sessions_error": str(exc),
                "sessions_health": health,
                "validated_at": utc_now(),
            }
        raise RuntimeError(f"SessionID validation failed: {exc}") from exc


def start_rdp_container() -> dict[str, Any]:
    ensure_rdp_secrets(overwrite=False)
    load_rdp_secrets(reload=True)
    cfg = rdp_container_config()
    _gov.governance_policy()
    _RUNTIME["running"] = True
    _RUNTIME["started_at"] = utc_now()
    _RUNTIME["stopped_at"] = None
    pid_path = Path(cfg["pid_file"])
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    return {
        "status": "started",
        "config": cfg,
        "sessions_link": sessions_link_health(),
        "started_at": _RUNTIME["started_at"],
    }


def stop_rdp_container() -> dict[str, Any]:
    cfg = rdp_container_config()
    _RUNTIME["running"] = False
    _RUNTIME["stopped_at"] = utc_now()
    pid_path = Path(cfg["pid_file"])
    if pid_path.exists():
        pid_path.unlink()
    return {"status": "stopped", "stopped_at": _RUNTIME["stopped_at"], "config": cfg}


def restart_rdp_container() -> dict[str, Any]:
    stopped = stop_rdp_container()
    started = start_rdp_container()
    return {"status": "restarted", "stopped": stopped, "started": started}


def status_rdp_container() -> dict[str, Any]:
    return {
        "running": bool(_RUNTIME.get("running")),
        "started_at": _RUNTIME.get("started_at"),
        "stopped_at": _RUNTIME.get("stopped_at"),
        "config": rdp_container_config(),
        "screen": _ScreenShare.screen_share_config(),
        "mouse": _MouseControl.mouse_control_config(),
        "keyboard": _keyboardControl.keyboard_control_config(),
        "files": _FileShare.file_share_config(),
        "user_control": _UserControl.user_control_config(),
        "audio": _AudioControl.audio_control_config(),
        "usb": _UsbControl.usb_control_config(),
        "governance": _gov.governance_policy(),
        "sessions_link": sessions_link_health(),
        "checked_at": utc_now(),
    }


def logs_rdp_container(*, lines: int | None = None) -> dict[str, Any]:
    cfg = rdp_container_config()
    log_dir = Path(cfg["log_dir"])
    log_name = require_rdp_secret("RDP_LOG_NAME")
    log_path = log_dir / log_name
    line_count: int = (
        int(lines) if lines is not None else int(require_rdp_secret_int("RDP_LOG_LINES"))
    )
    if line_count < 1:
        raise RuntimeError("RDP log line count must be a positive integer")
    if not log_path.exists():
        return {"log_path": log_path.as_posix(), "lines": [], "exists": False}
    content = log_path.read_text(encoding="utf-8").splitlines()[-line_count:]
    return {"log_path": log_path.as_posix(), "lines": content, "exists": True}
