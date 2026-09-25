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
_dns = _load_local("DockerDns")

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
        "operations_dns": require_rdp_secret("RDP_OPERATIONS_DNS"),
        "operations_port": require_rdp_secret_int("RDP_OPERATIONS_PORT"),
        "self_dns": require_rdp_secret("RDP_SELF_DNS"),
        "docker_network": require_rdp_secret("RDP_DOCKER_NETWORK_NAME"),
        "hardware_ip": get_rdp_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_rdp_secret("HARDWARE_PRIMARY_MAC"),
        **rdp_status(),
    }


def sessions_base_url() -> str:
    return _dns.sessions_base_url()


def operations_base_url() -> str:
    return _dns.operations_base_url()


def sessions_link_health() -> dict[str, Any]:
    """Probe sessions container via DockerDNS using secrets from pull."""
    return _dns.link_health(target="sessions")


def operations_link_health() -> dict[str, Any]:
    """Probe operations container via DockerDNS using secrets from pull."""
    return _dns.link_health(target="operations")


def validate_session_id(
    *, session_id: str, user_id: str, id_token: str
) -> dict[str, Any]:
    """Validate an active agreed SessionID with the sessions container."""
    validation = _dns.require_active_session(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    validation["status"] = "validated"
    validation["validated_at"] = utc_now()
    return validation


def stop_peer_channels(*, session_id: str) -> dict[str, Any]:
    """Stop screen, audio, mouse, keyboard, USB, and file state for a SessionID."""
    sid = str(session_id).strip()
    return {
        "session_id": sid,
        "screen": _ScreenShare.stop_screen_share(session_id=sid),
        "audio": _AudioControl.stop_audio(session_id=sid),
        "mouse": _MouseControl.clear_mouse_session(session_id=sid),
        "keyboard": _keyboardControl.clear_keyboard_session(session_id=sid),
        "usb": _UsbControl.detach_usb(session_id=sid),
        "files": _FileShare.clear_file_share(session_id=sid),
        "stopped_at": utc_now(),
    }


def start_rdp_container() -> dict[str, Any]:
    ensure_rdp_secrets(overwrite=False)
    load_rdp_secrets(reload=True)
    _dns.assert_dns_configured()
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
        "operations_link": operations_link_health(),
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
        "operations_link": operations_link_health(),
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
