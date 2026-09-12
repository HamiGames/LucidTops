"""Launch AdminGui connection to frontend/AdminHome via the *.onion address.

steps:
1. start tor connection on the admin console
2. connect to the frontend AdminHome page via the *.onion address
3. authenticate the AdminID via TokenID validation (caller responsibility)
4. open TorBrowser to AdminHome
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
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
require_admin_secret = _admin_secrets.require_admin_secret
get_admin_secret = _admin_secrets.get_admin_secret
load_admin_secrets = _admin_secrets.load_admin_secrets
admin_status = _admin_secrets.admin_status
ensure_admin_secrets_from_pull = _admin_secrets.ensure_admin_secrets_from_pull

_firewall = _load_local("firewall_allow")
_download_auth = _load_local("download_auth")
_validate = _load_local("validate_admin")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_state_path() -> Path:
    configured = get_admin_secret("ADMINGUI_SESSION_STATE_FILE")
    if configured:
        return Path(configured).expanduser()
    secrets_dir = get_admin_secret("SECRETS_DIR")
    if not secrets_dir:
        raise RuntimeError(
            "ADMINGUI_SESSION_STATE_FILE or SECRETS_DIR missing — create at time of operation"
        )
    return Path(secrets_dir) / "admingui_session.state"


def _read_session_state() -> dict[str, Any]:
    path = session_state_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_session_state(state: dict[str, Any]) -> Path:
    path = session_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clear_session_state() -> None:
    path = session_state_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            path.write_text("{}\n", encoding="utf-8")


def _identity_from_secrets() -> dict[str, str]:
    admin_id = get_admin_secret("ADMIN_ID") or get_admin_secret("ADMINID")
    token_id = get_admin_secret("TOKEN_ID")
    role = get_admin_secret("USER_ROLE") or ("admin" if admin_id else "")
    return {
        "admin_id": admin_id,
        "token_id": token_id,
        "role": role,
    }


def frontend_admin_url() -> str:
    ensure_admin_secrets_from_pull()
    load_admin_secrets(reload=True)
    onion = require_admin_secret("FRONTEND_ONION")
    home = require_admin_secret("FRONTEND_ADMIN_HOME_PATH")
    scheme = require_admin_secret("ADMIN_FRONTEND_SCHEME")
    if not onion.endswith(".onion"):
        raise RuntimeError(
            "FRONTEND_ONION is not a valid onion address — must be pulled from console secrets"
        )
    return f"{scheme}://{onion}/{home.lstrip('/')}"


def start_tor_background() -> dict[str, Any]:
    ensure_admin_secrets_from_pull()
    cmd = require_admin_secret("ADMIN_TOR_START_COMMAND")
    proc = subprocess.Popen(cmd, shell=True)  # noqa: S602 — command from secrets
    return {"status": "started", "command": cmd, "pid": proc.pid, "started_at": utc_now()}


def _terminate_pid(pid: int) -> dict[str, Any]:
    if pid <= 0:
        return {"pid": pid, "status": "invalid"}
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "pid": pid,
                "status": "terminated" if result.returncode == 0 else "taskkill_failed",
                "exit": result.returncode,
            }
        os.kill(pid, signal.SIGTERM)
        return {"pid": pid, "status": "terminated"}
    except ProcessLookupError:
        return {"pid": pid, "status": "not_running"}
    except OSError as exc:
        return {"pid": pid, "status": "error", "error": str(exc)}


def launch_admin_session() -> dict[str, Any]:
    ensure_admin_secrets_from_pull()
    _download_auth.require_download_auth_verified()
    validation = _validate.require_validated_admin()
    identity = _identity_from_secrets()

    firewall = _firewall.allowlist_tor_browser_firewall()
    tor = start_tor_background()
    url = frontend_admin_url()
    browser_cmd_template = require_admin_secret("ADMIN_TOR_BROWSER_COMMAND")
    if "{url}" not in browser_cmd_template:
        raise RuntimeError(
            "ADMIN_TOR_BROWSER_COMMAND missing {url} token — recreate secrets at time of operation"
        )
    browser_cmd = browser_cmd_template.replace("{url}", url)
    proc = subprocess.Popen(browser_cmd, shell=True)  # noqa: S602 — command from secrets

    state = {
        "status": "connected",
        "url": url,
        "tor_pid": tor.get("pid"),
        "browser_pid": proc.pid,
        "admin_id": identity.get("admin_id") or "",
        "token_id": identity.get("token_id") or "",
        "role": identity.get("role") or "",
        "launched_at": utc_now(),
    }
    state_path = _write_session_state(state)

    return {
        "status": "launched",
        "url": url,
        "tor": tor,
        "firewall": firewall,
        "browser_pid": proc.pid,
        "admin_id": identity.get("admin_id") or "",
        "token_id": identity.get("token_id") or "",
        "role": identity.get("role") or "",
        "validated": validation,
        "session_state": state_path.as_posix(),
        **admin_status(),
        "launched_at": utc_now(),
    }


def disconnect_admin_session() -> dict[str, Any]:
    """Exit Frontend TorBrowser window and stop Tor subprocesses started by Connect."""
    ensure_admin_secrets_from_pull()
    state = _read_session_state()
    results: list[dict[str, Any]] = []

    browser_pid = int(state.get("browser_pid") or 0)
    tor_pid = int(state.get("tor_pid") or 0)
    if browser_pid:
        results.append({"target": "tor_browser", **_terminate_pid(browser_pid)})
    if tor_pid and tor_pid != browser_pid:
        results.append({"target": "tor", **_terminate_pid(tor_pid)})

    _clear_session_state()
    return {
        "status": "disconnected",
        "terminated": results,
        "previous": {
            "url": state.get("url", ""),
            "admin_id": state.get("admin_id", ""),
            "role": state.get("role", ""),
        },
        "disconnected_at": utc_now(),
        **admin_status(),
    }


def connection_status() -> dict[str, Any]:
    ensure_admin_secrets_from_pull()
    state = _read_session_state()
    return {
        "connected": bool(state.get("browser_pid")),
        "session": state,
        **admin_status(),
        "download_auth_verified": _download_auth.is_download_auth_verified(),
        "checked_at": utc_now(),
    }
