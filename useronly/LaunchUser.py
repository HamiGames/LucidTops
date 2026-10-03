""" launch the connection to the frontend/home_page.js via the *.onion address created from the master server launch script
steps:
1. start tor connection on the user's device
2. connect to the frontend/home_page.js via the *.onion address or api route
3. authenticate the user via the api route
4. authorize the user via the api route
5. transfer the user to the frontend/home_page.js
6. display the user's dashboard
7. display the user's settings
8. display the user's profile
9. display the user's messages
10. display the user's notifications
11. display the user's alerts
12. display the user's errors
13. display the user's logs
14. display the user's alerts
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
    registry = f"lucid_useronly_{module_name}"
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


_user_secrets = _load_local("user_secrets")
require_user_secret = _user_secrets.require_user_secret
get_user_secret = _user_secrets.get_user_secret
load_user_secrets = _user_secrets.load_user_secrets
user_status = _user_secrets.user_status
ensure_user_secrets_from_pull = _user_secrets.ensure_user_secrets_from_pull

_install = _load_local("install")
_access = _load_local("frontend_access")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_state_path() -> Path:
    configured = get_user_secret("USERONLY_SESSION_STATE_FILE")
    if configured:
        return Path(configured).expanduser()
    secrets_dir = get_user_secret("SECRETS_DIR")
    if not secrets_dir:
        raise RuntimeError(
            "USERONLY_SESSION_STATE_FILE or SECRETS_DIR missing — create at time of operation"
        )
    return Path(secrets_dir) / "useronly_session.state"


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
    user_id = get_user_secret("USER_ID")
    node_id = get_user_secret("NODE_ID")
    token_id = get_user_secret("TOKEN_ID")
    role = get_user_secret("USER_ROLE")
    if not role:
        if node_id:
            role = "node"
        elif user_id:
            role = "user"
    return {
        "user_id": user_id,
        "node_id": node_id,
        "token_id": token_id,
        "role": role,
        "active_id": node_id or user_id,
    }


def frontend_onion_url() -> str:
    ensure_user_secrets_from_pull()
    load_user_secrets(reload=True)
    onion = require_user_secret("FRONTEND_ONION")
    home = require_user_secret("FRONTEND_HOME_PAGE_PATH")
    scheme = require_user_secret("USER_FRONTEND_SCHEME")
    if not onion.endswith(".onion"):
        raise RuntimeError(
            "FRONTEND_ONION is not a valid onion address — must be pulled from console secrets"
        )
    return f"{scheme}://{onion}/{home.lstrip('/')}"


def _refuse_nodeuser() -> None:
    if get_user_secret("NODEUSER").lower() == "true":
        raise RuntimeError("User route refused — NodeUser uses LaunchNodeUser")


def _hardware() -> dict[str, str]:
    ensure_user_secrets_from_pull()
    return {
        "hostname": get_user_secret("HOSTNAME_CONSOLE"),
        "machine_id": get_user_secret("HOST_MACHINE_ID"),
        "primary_mac": get_user_secret("HARDWARE_PRIMARY_MAC"),
        "primary_ip": get_user_secret("HARDWARE_PRIMARY_IP"),
        "primary_iface": get_user_secret("HARDWARE_PRIMARY_IFACE"),
    }


def _hardware_fields(hardware: dict[str, str]) -> dict[str, str]:
    return {
        "HOSTNAME_CONSOLE": hardware.get("hostname", ""),
        "HOST_MACHINE_ID": hardware.get("machine_id", ""),
        "HARDWARE_PRIMARY_MAC": hardware.get("primary_mac", ""),
        "HARDWARE_PRIMARY_IP": hardware.get("primary_ip", ""),
        "HARDWARE_PRIMARY_IFACE": hardware.get("primary_iface", ""),
    }


def _driver_dir() -> Path:
    raw = get_user_secret("DRIVER_DIR")
    if not raw:
        raise RuntimeError("DRIVER_DIR missing — run Install before choosing User or NodeUser")
    return Path(raw)


def _require_install() -> None:
    if not _install.install_is_complete():
        raise RuntimeError("Install has not finished on this console")


def start_tor_background() -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    cmd = require_user_secret("USER_TOR_START_COMMAND")
    from frontend_access import start_tor_background as _start

    return _start(cmd)


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


def _register_body(*, email: str, password: str, hardware: dict[str, str]) -> dict[str, Any]:
    return {
        "action": "register",
        "account_type": "user",
        "Email": email,
        "Password": password,
        **_hardware_fields(hardware),
    }


def _login_body(*, email: str, password: str) -> dict[str, Any]:
    identity = _identity_from_secrets()
    token_id = identity.get("token_id") or ""
    return {
        "action": "login",
        "account_type": "user",
        "Email": email,
        "Password": password,
        "UserID": identity.get("user_id") or "",
        "TokenID": token_id,
        "api_key": token_id,
    }


def _frontend_page(routes: dict[str, str], *keys: str, fallback: str) -> str:
    for key in keys:
        value = str(routes.get(key) or "").strip()
        if value.startswith("/") or value.endswith(".html"):
            return value
    return fallback


def _finish_frontend(
    routes: dict[str, str],
    *,
    branch: str,
    reply: dict[str, Any],
    post_file: str,
    page: str,
    tor: dict[str, Any],
) -> Path:
    """Handshake, then validation, then the Proxy foreground onion window."""
    token_id = get_user_secret("TOKEN_ID")
    session_id = str(
        reply.get("SessionID") or reply.get("session_id") or get_user_secret("SESSION_ID") or ""
    ).strip()
    if token_id and session_id:
        handshake_reply = _access.handshake(
            routes,
            branch=branch,
            hardware=_hardware(),
            token_id=token_id,
            session_id=session_id,
        )
        _access.validate_selected_files(routes, handshake_reply, [post_file])
    window = _access.open_foreground_window(
        routes,
        page=page,
        browser_command=require_user_secret("USER_TOR_BROWSER_COMMAND"),
    )
    return _access.write_session_state(
        {
            "status": "connected",
            "branch": branch,
            "tor_pid": tor.get("pid"),
            "browser_pid": window.get("pid"),
            "launched_at": utc_now(),
        }
    )


def register_user(*, email: str, password: str) -> dict[str, Any]:
    """User branch: Tor background, registration post, then the Frontend onion window."""
    _require_install()
    ensure_user_secrets_from_pull()
    if not email.strip() or not password:
        raise RuntimeError("Email and password are required to register as a User")
    routes = _access.routes_for(False)
    tor = start_tor_background()
    try:
        hardware = _hardware()
        submitted = _access.submit_validation(
            routes,
            path=_access.registration_path(routes, nodeuser=False),
            body=_register_body(email=email.strip(), password=password, hardware=hardware),
            driver_dir=_driver_dir(),
            file_name="registration_user.post.json",
        )
        stored = _user_secrets.apply_master_identity(submitted["reply"], nodeuser=False)
        state_path = _finish_frontend(
            routes,
            branch="user",
            reply=submitted["reply"],
            post_file=submitted["post_file"],
            page=_frontend_page(
                routes, "FRONTEND_REGISTER_PATH", "FRONTEND_HOME_PAGE_PATH", fallback="/register.html"
            ),
            tor=tor,
        )
    except Exception:
        if tor.get("pid"):
            _access.terminate_pid(int(tor["pid"]))
        raise
    return {
        "status": "registered",
        "branch": "user",
        "user_id_returned": bool(stored.get("USER_ID")),
        "token_id_returned": bool(stored.get("TOKEN_ID")),
        "session_state": state_path.as_posix(),
        "launched_at": utc_now(),
    }


def connect_user(*, email: str, password: str) -> dict[str, Any]:
    """User branch login over Tor, then handshake and Frontend validation."""
    _require_install()
    ensure_user_secrets_from_pull()
    _refuse_nodeuser()
    if not get_user_secret("TOKEN_ID"):
        raise RuntimeError("Login without a TokenID is rejected")
    if not get_user_secret("USER_ID"):
        raise RuntimeError("Register as a User before connecting")
    if not password:
        raise RuntimeError("Password is required to connect as a User")
    routes = _access.routes_for(False)
    tor = start_tor_background()
    try:
        _user_secrets.verify_id_secrets()
        submitted = _access.submit_validation(
            routes,
            path=_access.login_path(routes, nodeuser=False),
            body=_login_body(email=email.strip(), password=password),
            driver_dir=_driver_dir(),
            file_name="login_user.post.json",
        )
        stored = _user_secrets.apply_master_identity(submitted["reply"], nodeuser=False)
        _user_secrets.verify_id_secrets()
        state_path = _finish_frontend(
            routes,
            branch="user",
            reply=submitted["reply"],
            post_file=submitted["post_file"],
            page=_frontend_page(routes, "FRONTEND_HOME_PAGE_PATH", fallback="/home.html"),
            tor=tor,
        )
    except Exception:
        if tor.get("pid"):
            _access.terminate_pid(int(tor["pid"]))
        raise
    return {
        "status": "connected",
        "branch": "user",
        "user_id_returned": bool(stored.get("USER_ID")),
        "session_state": state_path.as_posix(),
        "launched_at": utc_now(),
    }


def launch_user_session(
    *, user_id: str | None = None, id_token: str | None = None
) -> dict[str, Any]:
    """Connect as User. Password is read from USER_PASSWORD when the GUI is not used."""
    del user_id, id_token
    return connect_user(email=get_user_secret("USER_EMAIL"), password=get_user_secret("USER_PASSWORD"))


def disconnect_user_session() -> dict[str, Any]:
    """Stop the Tor process started by Connect or Register."""
    ensure_user_secrets_from_pull()
    report = _access.disconnect_session()
    report.update(user_status())
    return report


def connection_status() -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    state = _read_session_state()
    return {
        "connected": state.get("status") == "connected" and bool(state.get("tor_pid")),
        "session": state,
        **user_status(),
        "checked_at": utc_now(),
    }
