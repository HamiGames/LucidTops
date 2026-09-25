"""DockerDNS client from the Rdp container to sessions and operations.

purpose (documentation/fixes.txt §4.9, §4.11, §5.5, §7.6):
- sessions and operations are reached by the Docker DNS names those containers publish.
- Rdp does not write LucidTops_SessionsDB.
- peer routes require both DNS names to be present.

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
    """Refuse peer routing when sessions or operations Docker DNS is empty."""
    load_rdp_secrets()
    sessions_dns = require_rdp_secret("RDP_SESSIONS_DNS").strip()
    operations_dns = require_rdp_secret("RDP_OPERATIONS_DNS").strip()
    sessions_port = require_rdp_secret("RDP_SESSIONS_PORT").strip()
    operations_port = require_rdp_secret("RDP_OPERATIONS_PORT").strip()
    if not sessions_dns or not operations_dns:
        raise RuntimeError(
            "Rdp DockerDNS names are empty — RDP_SESSIONS_DNS and "
            "RDP_OPERATIONS_DNS are required"
        )
    if not sessions_port or not operations_port:
        raise RuntimeError(
            "Rdp DockerDNS ports are empty — RDP_SESSIONS_PORT and "
            "RDP_OPERATIONS_PORT are required"
        )
    return {
        "sessions_dns": sessions_dns,
        "operations_dns": operations_dns,
        "sessions_port": sessions_port,
        "operations_port": operations_port,
    }


def sessions_base_url() -> str:
    assert_dns_configured()
    scheme = require_rdp_secret("RDP_SESSIONS_SCHEME")
    host = require_rdp_secret("RDP_SESSIONS_DNS")
    port = require_rdp_secret_int("RDP_SESSIONS_PORT")
    return f"{scheme}://{host}:{port}"


def operations_base_url() -> str:
    assert_dns_configured()
    scheme = require_rdp_secret("RDP_OPERATIONS_SCHEME")
    host = require_rdp_secret("RDP_OPERATIONS_DNS")
    port = require_rdp_secret_int("RDP_OPERATIONS_PORT")
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
    """Probe sessions or operations /health over DockerDNS."""
    if target == "sessions":
        base = sessions_base_url()
        health_path = get_rdp_secret("RDP_SESSIONS_HEALTH_PATH") or "/health"
    elif target == "operations":
        base = operations_base_url()
        health_path = get_rdp_secret("RDP_OPERATIONS_HEALTH_PATH") or "/health"
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


def _operations_path(secret_key: str) -> str:
    prefix = require_rdp_secret("RDP_OPERATIONS_API_PREFIX")
    return _join(prefix, require_rdp_secret(secret_key))


def post_sessions(path_secret: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{sessions_base_url().rstrip('/')}{_sessions_path(path_secret)}"
    return _request("POST", url, payload)


def _operations_identity(user_id: str, id_token: str) -> dict[str, str]:
    master_id = require_rdp_secret("RDP_OPERATIONS_MASTER_SERVER_ID")
    master_token = require_rdp_secret("RDP_OPERATIONS_TOKEN")
    return {
        "MasterServerID": master_id,
        "TokenID": master_token,
        "UserID": user_id,
        "UserTokenID": id_token,
    }


def post_operations(
    path_secret: str, *, user_id: str, id_token: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    url = f"{operations_base_url().rstrip('/')}{_operations_path(path_secret)}"
    body = _operations_identity(user_id, id_token)
    if extra:
        body.update(extra)
    return _request("POST", url, body)


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
        raise RuntimeError("SessionID is not agreed by every participant")
    if not _flag(validation.get("can_commence")):
        raise RuntimeError("SessionID cannot commence")
    return validation


def load_host_controls(
    *, session_id: str, user_id: str, id_token: str, host_user_id: str
) -> dict[str, Any]:
    """Read host settings.js controls from operations /session-control."""
    return post_operations(
        "RDP_OPERATIONS_SESSION_CONTROL_PATH",
        user_id=user_id,
        id_token=id_token,
        extra={
            "sessionID": str(session_id).strip(),
            "hostUserID": host_user_id,
        },
    )


def apply_host_controls(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Host one-time load of settings.js into operations session-control."""
    return post_operations(
        "RDP_OPERATIONS_SESSION_CONTROL_PATH",
        user_id=user_id,
        id_token=id_token,
        extra={
            "sessionID": str(session_id).strip(),
            "hostUserID": user_id,
            "Session_settings": settings,
        },
    )


def record_activity(
    *, session_id: str, user_id: str, id_token: str, action: str
) -> dict[str, Any]:
    """sessions /session-record and operations recorder /session-record."""
    sessions_result = post_sessions(
        "RDP_SESSION_RECORD_PATH",
        {
            "sessionID": str(session_id).strip(),
            "UserID": user_id,
            "TokenID": id_token,
            "action": action,
        },
    )
    operations_result = post_operations(
        "RDP_OPERATIONS_SESSION_RECORD_PATH",
        user_id=user_id,
        id_token=id_token,
        extra={"sessionID": str(session_id).strip(), "action": action},
    )
    _append_local_log(
        f"{utc_now()} session={session_id} user={user_id} action={action}"
    )
    return {
        "sessions": sessions_result,
        "operations": operations_result,
        "recorded_at": utc_now(),
    }


def _append_local_log(line: str) -> None:
    log_dir = Path(require_rdp_secret("RDP_LOG_DIR")).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / require_rdp_secret("RDP_LOG_NAME")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


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


def create_host_session(*, user_id: str, id_token: str) -> dict[str, Any]:
    """Forward SessionID creation to the sessions container."""
    return post_sessions(
        "RDP_SESSION_CREATE_PATH",
        {"UserID": user_id, "TokenID": id_token},
    )


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
