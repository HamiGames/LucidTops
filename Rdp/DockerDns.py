"""DockerDNS client from the Rdp container to sessions and the backend.

purpose (documentation/RDP.txt):
- sessions is the only DNS-selected container.
- outbound calls go to the sessions container and the backend container.
- Rdp does not write LucidTops_SessionsDB or LucidTopsUserDB.
- peer media uses Tor; this module's HTTP client is coordination only.

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
require_rdp_secret_int = _rdp_secrets.require_rdp_secret_int
get_rdp_secret = _rdp_secrets.get_rdp_secret
load_rdp_secrets = _rdp_secrets.load_rdp_secrets

_VIEWER_LOGGERS: set[str] = set()
_HOST_LOGGERS: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _join(prefix: str, path: str) -> str:
    left = prefix.strip()
    right = path.strip()
    if not right.startswith("/"):
        right = f"/{right}"
    if not left or left == "/":
        return right
    return f"{left.rstrip('/')}{right}"


def assert_dns_configured() -> dict[str, str]:
    """Refuse peer routing when sessions Docker DNS is empty."""
    load_rdp_secrets()
    sessions_dns = require_rdp_secret("RDP_SESSIONS_DNS").strip()
    sessions_port = require_rdp_secret("RDP_SESSIONS_PORT").strip()
    if not sessions_dns:
        raise RuntimeError("Rdp DockerDNS name is empty — RDP_SESSIONS_DNS is required")
    if not sessions_port:
        raise RuntimeError("Rdp DockerDNS port is empty — RDP_SESSIONS_PORT is required")
    return {"sessions_dns": sessions_dns, "sessions_port": sessions_port}


def assert_backend_configured() -> dict[str, str]:
    """Refuse backend calls when backend Docker DNS is empty."""
    load_rdp_secrets()
    backend_dns = require_rdp_secret("RDP_BACKEND_DNS").strip()
    backend_port = require_rdp_secret("RDP_BACKEND_PORT").strip()
    if not backend_dns:
        raise RuntimeError("Rdp backend DNS is empty — RDP_BACKEND_DNS is required")
    if not backend_port:
        raise RuntimeError("Rdp backend port is empty — RDP_BACKEND_PORT is required")
    return {"backend_dns": backend_dns, "backend_port": backend_port}


def sessions_base_url() -> str:
    assert_dns_configured()
    scheme = require_rdp_secret("RDP_SESSIONS_SCHEME")
    host = require_rdp_secret("RDP_SESSIONS_DNS")
    port = require_rdp_secret_int("RDP_SESSIONS_PORT")
    return f"{scheme}://{host}:{port}"


def backend_base_url() -> str:
    assert_backend_configured()
    scheme = require_rdp_secret("RDP_BACKEND_SCHEME")
    host = require_rdp_secret("RDP_BACKEND_DNS")
    port = require_rdp_secret_int("RDP_BACKEND_PORT")
    return f"{scheme}://{host}:{port}"


def _timeout() -> float:
    raw = get_rdp_secret("RDP_HTTP_TIMEOUT")
    if raw and raw.replace(".", "", 1).isdigit():
        return float(raw)
    return float(require_rdp_secret_int("RDP_HTTP_TIMEOUT"))


def _request(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    import httpx

    timeout = _timeout()
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                response = client.get(url)
            else:
                response = client.post(url, json=payload or {})
    except httpx.HTTPError as exc:
        raise RuntimeError(f"DockerDNS request failed: {url}: {exc}") from exc
    body_text = response.text
    parsed: Any
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = {"raw": body_text[:500]}
    if response.status_code >= 400:
        detail = parsed if isinstance(parsed, dict) else body_text[:300]
        raise RuntimeError(f"DockerDNS HTTP {response.status_code} {url}: {detail}")
    if not isinstance(parsed, dict):
        return {"body": parsed, "status_code": response.status_code, "url": url}
    parsed.setdefault("status_code", response.status_code)
    parsed.setdefault("url", url)
    return parsed


def link_health(*, target: str) -> dict[str, Any]:
    """Probe sessions or backend /health over DockerDNS."""
    if target == "sessions":
        base = sessions_base_url()
        health_path = get_rdp_secret("RDP_SESSIONS_HEALTH_PATH") or "/health"
    elif target == "backend":
        base = backend_base_url()
        health_path = get_rdp_secret("RDP_BACKEND_HEALTH_PATH") or "/health"
    else:
        raise RuntimeError(f"unknown DockerDNS target: {target}")
    url = f"{base.rstrip('/')}/{health_path.lstrip('/')}"
    try:
        body = _request("GET", url)
        return {
            "reachable": True,
            "target": target,
            "url": url,
            "body": body,
            "checked_at": utc_now(),
        }
    except RuntimeError as exc:
        return {
            "reachable": False,
            "target": target,
            "url": url,
            "error": str(exc),
            "checked_at": utc_now(),
        }


def _sessions_path(secret_key: str) -> str:
    prefix = require_rdp_secret("RDP_SESSIONS_API_PREFIX")
    return _join(prefix, require_rdp_secret(secret_key))


def _backend_path(secret_key: str) -> str:
    prefix = require_rdp_secret("RDP_BACKEND_API_PREFIX")
    return _join(prefix, require_rdp_secret(secret_key))


def post_sessions(path_secret: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{sessions_base_url().rstrip('/')}{_sessions_path(path_secret)}"
    return _request("POST", url, payload)


def post_backend(path_secret: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{backend_base_url().rstrip('/')}{_backend_path(path_secret)}"
    return _request("POST", url, payload)


def require_tor_peer() -> dict[str, Any]:
    """Peer media refuses to run when the pulled Tor SOCKS endpoint is missing."""
    load_rdp_secrets()
    host = get_rdp_secret("TOR_SOCKS_HOST").strip()
    port_raw = get_rdp_secret("TOR_SOCKS_PORT").strip()
    onion = get_rdp_secret("RDP_ONION").strip()
    if not host or not port_raw or not onion:
        raise RuntimeError(
            "Tor SOCKS endpoint missing — peer media requires TOR_SOCKS_HOST, "
            "TOR_SOCKS_PORT, and RDP_ONION from the hardware pull"
        )
    if not port_raw.isdigit() or int(port_raw) < 1:
        raise RuntimeError("TOR_SOCKS_PORT is not a pulled Tor SOCKS port")
    return {"socks_host": host, "socks_port": int(port_raw), "rdp_onion": onion}


def confirm_user_access(*, user_id: str, id_token: str) -> dict[str, Any]:
    """Backend confirms login, registration, limitations, and Tier_selected."""
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/TokenID missing")
    body = post_backend(
        "RDP_BACKEND_ACCESS_PATH",
        {"UserID": user_id.strip(), "TokenID": id_token.strip()},
    )
    if not _flag(body.get("login_complete")):
        raise RuntimeError("login must be complete to use the Rdp container")
    if not _flag(body.get("registered")):
        raise RuntimeError("MasterServer has not confirmed registration for this UserID")
    tier_raw = body.get("Tier_selected", body.get("tier", 0))
    try:
        tier = int(tier_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Select_tier count is missing") from exc
    if tier <= 0:
        raise RuntimeError("Select_tier count must be more than 0")
    body["Tier_selected"] = tier
    return body


def fetch_validation(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    """POST sessions /session-validate. Does not accept an offline SessionID."""
    if not str(session_id).strip():
        raise RuntimeError("SessionID missing — required to operate Rdp inside a session")
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/TokenID missing for SessionID validation")
    body = post_sessions(
        "RDP_SESSION_VALIDATE_PATH",
        {
            "session_id": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
        },
    )
    body["session_id"] = str(body.get("session_id") or body.get("sessionID") or session_id).strip()
    body["user_id"] = str(body.get("user_id") or body.get("UserID") or user_id)
    return body


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def require_active_session(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    """Peer media runs only inside an active, agreed SessionID."""
    validation = fetch_validation(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    if not _flag(validation.get("is_participant")):
        raise RuntimeError("UserID is not a participant in this SessionID")
    status = str(
        validation.get("SessionID_status") or validation.get("sessionStatus") or ""
    ).strip()
    if status != "active":
        raise RuntimeError(f"SessionID is not active ({status or 'missing'})")
    if not _flag(validation.get("all_agreed")):
        raise RuntimeError("Viewer_UserID has not been accepted by the Host_UserID")
    if not _flag(validation.get("can_commence")):
        raise RuntimeError("SessionID cannot commence")
    return validation


def controls_from_body(body: dict[str, Any]) -> dict[str, Any]:
    for key in ("controls", "Session_settings", "settings"):
        value = body.get(key)
        if isinstance(value, dict):
            return value
    return {}


def load_host_controls(
    *, session_id: str, user_id: str, id_token: str, host_user_id: str
) -> dict[str, Any]:
    """Read Host_UserID Session_settings frozen on the SessionID."""
    validation = fetch_validation(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    stored_host = str(validation.get("hostUserID") or "")
    if host_user_id and stored_host and host_user_id != stored_host:
        raise RuntimeError("hostUserID does not own this SessionID")
    controls = controls_from_body(validation)
    return {
        "controls": controls,
        "Session_settings": controls,
        "hostUserID": stored_host,
        "session_id": str(session_id).strip(),
    }


def apply_host_controls(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Freeze settings.js onto the SessionID once. Later writes are rejected by sessions."""
    return post_sessions(
        "RDP_SESSION_SETTINGS_PATH",
        {
            "session_id": str(session_id).strip(),
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
            "Session_settings": settings,
        },
    )


def _role_log_path(*, user_id: str, session_id: str) -> Path:
    log_dir = Path(require_rdp_secret("RDP_LOG_DIR")).expanduser()
    safe_user = str(user_id).strip().replace("/", "_").replace("\\", "_")
    safe_session = str(session_id).strip().replace("/", "_").replace("\\", "_")
    return log_dir / f"{safe_user}_{safe_session}.log"


def start_role_logger(*, session_id: str, user_id: str, role: str) -> dict[str, Any]:
    """Open Host_log or Viewer_log and mark that logger in use."""
    sid = str(session_id).strip()
    uid = str(user_id).strip()
    if role not in {"host", "viewer"}:
        raise RuntimeError("logger role must be host or viewer")
    if not sid or not uid:
        raise RuntimeError("SessionID and UserID are required to start the logger")
    path = _role_log_path(user_id=uid, session_id=sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now()} role={role} session={sid} user={uid} logger=started"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if role == "viewer":
        _VIEWER_LOGGERS.add(sid)
    else:
        _HOST_LOGGERS.add(sid)
    return {
        "status": "logging",
        "role": role,
        "session_id": sid,
        "user_id": uid,
        "log_path": path.as_posix(),
        "log_name": path.name,
        "started_at": utc_now(),
    }


def viewer_logger_in_use(*, session_id: str, viewer_user_id: str) -> bool:
    """True when the Viewer_UserID log file is being written for this SessionID."""
    sid = str(session_id).strip()
    viewer = str(viewer_user_id).strip()
    if not sid or not viewer:
        return False
    path = _role_log_path(user_id=viewer, session_id=sid)
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if sid not in _VIEWER_LOGGERS:
        _VIEWER_LOGGERS.add(sid)
    return True


def _append_role_log(*, session_id: str, user_id: str, role: str, action: str) -> str:
    path = _role_log_path(user_id=user_id, session_id=session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now()} role={role} session={session_id} user={user_id} action={action}"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if role == "viewer":
        _VIEWER_LOGGERS.add(str(session_id).strip())
    else:
        _HOST_LOGGERS.add(str(session_id).strip())
    return path.as_posix()


def record_activity(
    *, session_id: str, user_id: str, id_token: str, action: str
) -> dict[str, Any]:
    """Write the role log and POST sessions /session-record."""
    validation = fetch_validation(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    host = str(validation.get("hostUserID") or "")
    role = "host" if user_id == host else "viewer"
    log_path = _append_role_log(
        session_id=str(session_id).strip(),
        user_id=user_id,
        role=role,
        action=action,
    )
    sessions_result = post_sessions(
        "RDP_SESSION_RECORD_PATH",
        {
            "sessionID": str(session_id).strip(),
            "session_id": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
            "action": action,
        },
    )
    return {
        "sessions": sessions_result,
        "role": role,
        "log_path": log_path,
        "recorded_at": utc_now(),
    }


def find_peer(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    return post_sessions(
        "RDP_SESSION_FIND_PATH",
        {
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
        },
    )


def connect_peer(
    *, session_id: str, session_key: str, user_id: str, id_token: str
) -> dict[str, Any]:
    return post_sessions(
        "RDP_SESSION_CONNECT_PATH",
        {
            "sessionID": str(session_id).strip(),
            "sessionKey": session_key,
            "UserID": user_id,
            "TokenID": id_token,
        },
    )


def attach_existing_session(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    """Attach Rdp to a SessionID sessions already wrote. Does not create a SessionID."""
    if not str(session_id).strip():
        raise RuntimeError(
            "SessionID missing — Rdp attaches only after the sessions container has written the SessionID"
        )
    validation = fetch_validation(
        session_id=session_id, user_id=user_id, id_token=id_token
    )
    if not str(validation.get("session_id") or "").strip():
        raise RuntimeError("Valid SessionID must exist in LucidTops_SessionsDB")
    if not _flag(validation.get("is_participant")) and user_id != str(validation.get("hostUserID") or ""):
        raise RuntimeError("UserID is not a SessionID participant")
    validation["attached"] = True
    validation["created_by_rdp"] = False
    return validation


def agree_connection(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    multi_connection: bool = False,
) -> dict[str, Any]:
    return post_sessions(
        "RDP_SESSION_AGREE_PATH",
        {
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
            "multi_connection": bool(multi_connection),
        },
    )


def terminate_participant(
    *, session_id: str, user_id: str, id_token: str, mode: str
) -> dict[str, Any]:
    path_secret = (
        "RDP_SESSION_END_PATH" if mode == "end" else "RDP_SESSION_DISCONNECT_PATH"
    )
    return post_sessions(
        path_secret,
        {
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
        },
    )


def reconnect_session(*, session_id: str, user_id: str, id_token: str) -> dict[str, Any]:
    """New SessionID seeded by the last SessionID (sessions container)."""
    return post_sessions(
        "RDP_SESSION_RECONNECT_PATH",
        {
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
        },
    )
