"""
this is the protocol for creating a unique session ID for the session system using the Session API route
session ID protocol:
- the session ID will be created using a sha512 hash function to produce a 10 digit session id consisting of 0-9 and a-z
- the session ID will be returned to the user via the API route
- the session ID will be used to find a peer to peer remote desktop sharing session via the API route using the find-peer GUI
- the session ID will be used to create a new session connection via the API route using the connect-handshake GUI

the sessionID will be generated for every new session creation request (new session creation request will be recorded in the sessionID log (sessionID.log) on the master server database)
all un-finalised sessions will be recorded in the sessionID log (sessionID.log) on the master server database and removed after 15 days of inactivity
all inactive sessionID's found in the tally system will flag the NodeUserID as fraudulent (NodeGov.py)
sends all sessionID creation requests to the MasterServer (uvicorn server) via the API route (FastAPI)

compatibility requirements:
- mongodb 7.0.0 or higher
- python 3.10 or higher
- FastAPI 0.105.0 or higher
- uvicorn 0.24.0 or higher
- nginx 1.24.0 or higher
- docker 24.0.0 or higher
- docker-compose 24.0.0 or higher
- Tor Hidden Services and Docker Network

other:
- no place holder values, all values are created at time of operation.
- all code will be configurable from outside the container (via the DockerfileDNS) and stored on the Host Machine (hardward using a configurable Path)
- all configuration files names will use the Path (mnt/myssd/LucidTops/secrets) and the file name will be the container name (sessions.secrets)

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from ._common import (
    get_master_db,
    resolve_sessions_secret,
    resolve_sessions_secret_bool,
    resolve_sessions_secret_int,
    session_id_log_collection,
    session_records_collection,
    utc_now,
    with_mongo,
)

SESSIONS_SECRETS_FILE_ENV = "SESSIONS_SECRETS_FILE"

# Keys written by Config_sessions.apply_pull_to_sessions_configuration at operation time.
SESSIONS_SECRETS_REQUIRED_KEYS: tuple[str, ...] = (
    "SESSION_ID_LENGTH",
    "SESSION_ID_ALPHABET",
    "SESSION_ID_LOG_SOURCE",
    "SESSION_INACTIVITY_DAYS",
    "SESSION_FINALISED_STATUSES",
    "SESSION_COMPLETE_STATUS",
    "SESSION_API_PREFIX",
    "SESSION_CREATE_API_ROUTE",
    "SESSION_FIND_PEER_GUI_ROUTE",
    "SESSION_CONNECT_HANDSHAKE_GUI_ROUTE",
    "SESSION_VALIDATE_PATH",
    "SESSION_HEALTH_PATH",
    "MASTER_SERVER_INTERNAL_HOST",
    "MASTER_SERVER_INTERNAL_PORT",
    "MASTER_SERVER_URL_SCHEME",
    "TOR_HIDDEN_SERVICES_ENABLED",
    "DOCKER_NETWORK_ENABLED",
    "SESSION_KEY_MIN_LENGTH",
    "SESSION_KEY_URLSAFE_BYTES",
    "SESSION_TYPE",
    "TALLY_ENTITY_TYPE_MASTER",
    "TALLY_ENTITY_ID_MASTER",
    "PEER_USER_ID_MASK_PREFIX",
    "PEER_USER_ID_MASK_HEX_LEN",
    "PEER_SEARCH_LABEL",
    "SESSIONS_BIND_HOST",
    "SESSIONS_BIND_PORT",
    "SESSIONS_DOCKER_DNS_NAME",
    "SESSIONS_SERVICE_NAME",
    "SESSIONS_NETWORK_NAME",
    "LUCIDTOPS_SESSIONS_DB_NAME",
    "LUCIDTOPS_SESSIONS_COLLECTION",
    "LUCIDTOPS_SESSIONS_ID_LOG_COLLECTION",
    "HARDWARE_PRIMARY_IP",
    "HARDWARE_PRIMARY_MAC",
    "OPERATIONS_DOCKER_DNS_NAME",
    "OPERATIONS_BIND_PORT",
    "OPERATIONS_URL_SCHEME",
    "OPERATIONS_SESSION_HANDOFF_PATH",
)

COMPATIBILITY_REQUIREMENTS: dict[str, str] = {
    "mongodb": "7.0.0",
    "python": "3.10",
    "fastapi": "0.105.0",
    "uvicorn": "0.24.0",
    "nginx": "1.24.0",
    "docker": "24.0.0",
    "docker-compose": "24.0.0",
    "tor_hidden_services": "required",
    "docker_network": "required",
}


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _require_env(key: str) -> str:
    value = _env(key)
    if not value:
        raise RuntimeError(f"{key} missing — must be set at time of operation")
    return value


def lucid_tops_root() -> Path:
    override = _env("LUCID_TOPS_ROOT")
    if override:
        return Path(override).expanduser()
    return Path(resolve_sessions_secret("LUCID_TOPS_ROOT")).expanduser()


def secrets_dir() -> Path:
    override = _env("SECRETS_DIR")
    if override:
        return Path(override).expanduser()
    return Path(resolve_sessions_secret("SECRETS_DIR")).expanduser()


def sessions_secrets_name() -> str:
    name = _env("SESSIONS_SECRETS_NAME")
    if name:
        return name
    container = _env("SESSIONS_CONTAINER_NAME")
    if container:
        return f"{container}.secrets"
    return "sessions.secrets"


def sessions_secrets_path() -> Path:
    """Host-mounted sessions.secrets path (DockerfileDNS / LucidTops SECRETS_DIR)."""
    override = _env(SESSIONS_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return secrets_dir() / sessions_secrets_name()


@lru_cache(maxsize=1)
def _load_sessions_secrets_cached() -> dict[str, str]:
    values: dict[str, str] = {}
    path = sessions_secrets_path()
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def load_sessions_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_sessions_secrets_cached.cache_clear()
    return _load_sessions_secrets_cached()


def resolve_session_secret(key: str) -> str:
    return resolve_sessions_secret(key)


def resolve_session_secret_int(key: str) -> int:
    return resolve_sessions_secret_int(key)


def resolve_session_secret_bool(key: str) -> bool:
    return resolve_sessions_secret_bool(key)


def _normalize_route(route: str) -> str:
    cleaned = route.strip()
    if not cleaned:
        raise RuntimeError("route value missing — must be set at time of operation")
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def _normalize_api_prefix(prefix: str) -> str:
    cleaned = prefix.strip()
    if not cleaned:
        raise RuntimeError("SESSION_API_PREFIX missing — must be set at time of operation")
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    normalized = cleaned.rstrip("/")
    if not normalized:
        raise RuntimeError("SESSION_API_PREFIX invalid — must be set at time of operation")
    return normalized


def resolve_session_id_length() -> int:
    length = resolve_session_secret_int("SESSION_ID_LENGTH")
    if length != 10:
        raise RuntimeError(
            "SESSION_ID_LENGTH must be 10 (unique int(10) per fixes.txt) at time of operation"
        )
    return length


def resolve_session_id_alphabet() -> str:
    alphabet = resolve_session_secret("SESSION_ID_ALPHABET")
    if not alphabet:
        raise RuntimeError("SESSION_ID_ALPHABET missing — must be set at time of operation")
    if set(alphabet) - set("0123456789"):
        raise RuntimeError(
            "SESSION_ID_ALPHABET must be digits only for SessionID int(10) at time of operation"
        )
    return alphabet


def resolve_session_id_log_source() -> str:
    return resolve_session_secret("SESSION_ID_LOG_SOURCE")


def resolve_session_inactivity_days() -> int:
    days = resolve_session_secret_int("SESSION_INACTIVITY_DAYS")
    if days < 1:
        raise RuntimeError("SESSION_INACTIVITY_DAYS must be >= 1")
    return days


def resolve_finalised_statuses() -> frozenset[str]:
    raw = resolve_session_secret("SESSION_FINALISED_STATUSES")
    statuses = frozenset(item.strip() for item in raw.split(",") if item.strip())
    if not statuses:
        raise RuntimeError(
            "SESSION_FINALISED_STATUSES missing — must be set at time of operation"
        )
    return statuses


def resolve_session_api_prefix() -> str:
    return _normalize_api_prefix(resolve_session_secret("SESSION_API_PREFIX"))


def resolve_session_create_api_route() -> str:
    return _normalize_route(resolve_session_secret("SESSION_CREATE_API_ROUTE"))


def resolve_find_peer_gui_route() -> str:
    return _normalize_route(resolve_session_secret("SESSION_FIND_PEER_GUI_ROUTE"))


def resolve_connect_handshake_gui_route() -> str:
    return _normalize_route(resolve_session_secret("SESSION_CONNECT_HANDSHAKE_GUI_ROUTE"))


def resolve_session_validate_path() -> str:
    return _normalize_route(resolve_session_secret("SESSION_VALIDATE_PATH"))


def resolve_session_health_path() -> str:
    return _normalize_route(resolve_session_secret("SESSION_HEALTH_PATH"))


def resolve_master_server_internal_host() -> str:
    return resolve_session_secret("MASTER_SERVER_INTERNAL_HOST")


def resolve_master_server_internal_port() -> int:
    port = resolve_session_secret_int("MASTER_SERVER_INTERNAL_PORT")
    if port < 1:
        raise RuntimeError("MASTER_SERVER_INTERNAL_PORT must be >= 1")
    return port


def resolve_master_server_url_scheme() -> str:
    return resolve_session_secret("MASTER_SERVER_URL_SCHEME")


def resolve_session_key_min_length() -> int:
    length = resolve_session_secret_int("SESSION_KEY_MIN_LENGTH")
    if length < 1:
        raise RuntimeError("SESSION_KEY_MIN_LENGTH must be >= 1")
    return length


def resolve_session_key_urlsafe_bytes() -> int:
    size = resolve_session_secret_int("SESSION_KEY_URLSAFE_BYTES")
    if size < 1:
        raise RuntimeError("SESSION_KEY_URLSAFE_BYTES must be >= 1")
    return size


def resolve_session_type() -> str:
    return resolve_session_secret("SESSION_TYPE")


def resolve_tally_entity_type_master() -> str:
    return resolve_session_secret("TALLY_ENTITY_TYPE_MASTER")


def resolve_tally_entity_id_master() -> str:
    return resolve_session_secret("TALLY_ENTITY_ID_MASTER")


def resolve_peer_user_id_mask_prefix() -> str:
    return resolve_session_secret("PEER_USER_ID_MASK_PREFIX")


def resolve_peer_user_id_mask_hex_len() -> int:
    length = resolve_session_secret_int("PEER_USER_ID_MASK_HEX_LEN")
    if length < 1:
        raise RuntimeError("PEER_USER_ID_MASK_HEX_LEN must be >= 1")
    return length


def resolve_peer_search_label() -> str:
    return resolve_session_secret("PEER_SEARCH_LABEL")


def resolve_sessions_bind_host() -> str:
    return resolve_session_secret("SESSIONS_BIND_HOST")


def resolve_sessions_bind_port() -> int:
    port = resolve_session_secret_int("SESSIONS_BIND_PORT")
    if port < 1:
        raise RuntimeError("SESSIONS_BIND_PORT must be >= 1")
    return port


def resolve_sessions_docker_dns_name() -> str:
    return resolve_session_secret("SESSIONS_DOCKER_DNS_NAME")


def resolve_sessions_service_name() -> str:
    return resolve_session_secret("SESSIONS_SERVICE_NAME")


def resolve_sessions_network_name() -> str:
    return resolve_session_secret("SESSIONS_NETWORK_NAME")


def resolve_operations_handoff_url() -> str:
    scheme = resolve_session_secret("OPERATIONS_URL_SCHEME")
    host = resolve_session_secret("OPERATIONS_DOCKER_DNS_NAME")
    port = resolve_session_secret_int("OPERATIONS_BIND_PORT")
    path = _normalize_route(resolve_session_secret("OPERATIONS_SESSION_HANDOFF_PATH"))
    return f"{scheme}://{host}:{port}{path}"


def session_create_api_path() -> str:
    """Full FastAPI path for sessionID creation requests to the MasterServer."""
    return f"{resolve_session_api_prefix()}{resolve_session_create_api_route()}"


def master_server_session_create_url() -> str:
    """Docker-network URL used to send sessionID creation requests to uvicorn/FastAPI."""
    scheme = resolve_master_server_url_scheme()
    host = resolve_master_server_internal_host()
    port = resolve_master_server_internal_port()
    return f"{scheme}://{host}:{port}{session_create_api_path()}"


def session_id_pattern() -> re.Pattern[str]:
    length = resolve_session_id_length()
    return re.compile(rf"^\d{{{length}}}$")


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in version.replace("-", ".").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            parts.append(int(digits))
        if len(parts) >= 3:
            break
    return tuple(parts) if parts else (0,)


def _version_meets_minimum(installed: str, minimum: str) -> bool:
    return _parse_version_tuple(installed) >= _parse_version_tuple(minimum)


def _package_version(distribution_name: str) -> str | None:
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return None


def compatibility_status() -> dict[str, Any]:
    """Report compatibility against comment requirements (packages + Tor/Docker flags)."""
    python_min = COMPATIBILITY_REQUIREMENTS["python"]
    python_ok = sys.version_info >= tuple(int(p) for p in python_min.split("."))

    fastapi_ver = _package_version("fastapi")
    uvicorn_ver = _package_version("uvicorn")
    pymongo_ver = _package_version("pymongo")

    tor_enabled = resolve_session_secret_bool("TOR_HIDDEN_SERVICES_ENABLED")
    docker_network_enabled = resolve_session_secret_bool("DOCKER_NETWORK_ENABLED")

    checks: dict[str, Any] = {
        "python": {
            "required": f"{python_min}+",
            "installed": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "ok": python_ok,
        },
        "fastapi": {
            "required": f"{COMPATIBILITY_REQUIREMENTS['fastapi']}+",
            "installed": fastapi_ver,
            "ok": bool(
                fastapi_ver
                and _version_meets_minimum(fastapi_ver, COMPATIBILITY_REQUIREMENTS["fastapi"])
            ),
        },
        "uvicorn": {
            "required": f"{COMPATIBILITY_REQUIREMENTS['uvicorn']}+",
            "installed": uvicorn_ver,
            "ok": bool(
                uvicorn_ver
                and _version_meets_minimum(uvicorn_ver, COMPATIBILITY_REQUIREMENTS["uvicorn"])
            ),
        },
        "mongodb": {
            "required": f"{COMPATIBILITY_REQUIREMENTS['mongodb']}+",
            "installed": pymongo_ver,
            "ok": pymongo_ver is not None,
            "note": "Runtime MongoDB server version is validated by the MasterServer / mongodb container.",
        },
        "tor_hidden_services": {
            "required": COMPATIBILITY_REQUIREMENTS["tor_hidden_services"],
            "enabled": tor_enabled,
            "ok": tor_enabled,
        },
        "docker_network": {
            "required": COMPATIBILITY_REQUIREMENTS["docker_network"],
            "enabled": docker_network_enabled,
            "ok": docker_network_enabled,
        },
        "sessions_secrets_path": sessions_secrets_path().as_posix(),
        "sessions_secrets_loaded": bool(load_sessions_secrets()),
        "hardware_primary_ip": resolve_session_secret("HARDWARE_PRIMARY_IP"),
        "hardware_primary_mac": resolve_session_secret("HARDWARE_PRIMARY_MAC"),
    }
    return checks


def assert_runtime_compatibility() -> None:
    """Enforce in-process compatibility requirements for this module."""
    status = compatibility_status()
    if not status["python"]["ok"]:
        raise RuntimeError(
            f"Python {COMPATIBILITY_REQUIREMENTS['python']}+ is required "
            f"(found {status['python']['installed']})"
        )
    if status["fastapi"]["installed"] is not None and not status["fastapi"]["ok"]:
        raise RuntimeError(
            f"FastAPI {COMPATIBILITY_REQUIREMENTS['fastapi']}+ is required "
            f"(found {status['fastapi']['installed']})"
        )
    if status["uvicorn"]["installed"] is not None and not status["uvicorn"]["ok"]:
        raise RuntimeError(
            f"uvicorn {COMPATIBILITY_REQUIREMENTS['uvicorn']}+ is required "
            f"(found {status['uvicorn']['installed']})"
        )
    if not status["tor_hidden_services"]["ok"]:
        raise RuntimeError("Tor Hidden Services must be enabled for sessionID operations")
    if not status["docker_network"]["ok"]:
        raise RuntimeError("Docker Network must be enabled for sessionID operations")


def collect_sessions_secret_values(*, existing: dict[str, str] | None = None) -> dict[str, str]:
    """Collect sessions.secrets via pull-derived Config at operation time."""
    from .Config_sessions import apply_pull_to_sessions_configuration
    from .sessions_pull_information import get_sessions_pull

    prior = existing if existing is not None else load_sessions_secrets()
    return apply_pull_to_sessions_configuration(pull=get_sessions_pull(), prior=prior)


def write_sessions_secrets(
    secrets_dir_path: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    from .Config_sessions import write_session_secrets

    return write_session_secrets(secrets_dir=secrets_dir_path, force=force)


def write_sessions_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    if not populate_from_env:
        raise RuntimeError(
            "populate_from_env=False is not allowed — values must come from "
            "hardware pull / sessions.secrets at time of operation"
        )
    return write_sessions_secrets(secrets_dir, force=force)


def generate_session_id(*, host_user_id: str, nonce: str | None = None) -> str:
    """
    Create a unique SessionID as int(10) digit string (fixes.txt §12.7).
    Digits are derived from SHA-512 of operation-time material (UserID + nonce + time + hardware).
    """
    assert_runtime_compatibility()
    if not host_user_id or not str(host_user_id).strip():
        raise ValueError("host_user_id is required to generate a sessionID")

    length = resolve_session_id_length()
    alphabet = resolve_session_id_alphabet()
    hardware_ip = resolve_session_secret("HARDWARE_PRIMARY_IP")
    hardware_mac = resolve_session_secret("HARDWARE_PRIMARY_MAC")
    operation_nonce = nonce if nonce is not None else secrets.token_hex(16)
    seed = (
        f"{host_user_id.strip()}:{operation_nonce}:{utc_now()}:"
        f"{hardware_ip}:{hardware_mac}:{secrets.token_hex(8)}"
    )
    digest = hashlib.sha512(seed.encode("utf-8")).hexdigest()
    value = int(digest, 16)
    chars: list[str] = []
    base = len(alphabet)
    for _ in range(length):
        value, index = divmod(value, base)
        chars.append(alphabet[index])
    session_id = "".join(chars)
    # Ensure first digit is non-zero so the value is a true 10-digit integer.
    if session_id[0] == "0":
        session_id = alphabet[(int(digest[-2:], 16) % (base - 1)) + 1] + session_id[1:]
    return session_id


def validate_session_id(session_id: str) -> bool:
    if not session_id:
        return False
    cleaned = session_id.strip()
    if not session_id_pattern().fullmatch(cleaned):
        return False
    try:
        as_int = int(cleaned)
    except ValueError:
        return False
    return as_int >= 10 ** (resolve_session_id_length() - 1)


@with_mongo
def log_session_id(
    *,
    session_id: str,
    host_user_id: str,
    user_ids: list[str] | None = None,
    status: str = "pending",
    source: str | None = None,
    client: Any,
) -> dict[str, Any]:
    """Record a sessionID in LucidTops_SessionsDB session_id_log (Tor)."""
    if not validate_session_id(session_id):
        raise ValueError("sessionID must be a valid unique int(10)")
    now = utc_now()
    entry = {
        "sessionID": session_id.strip(),
        "SessionID": int(session_id.strip()),
        "hostUserID": host_user_id,
        "userIDs": list(user_ids or [host_user_id]),
        "source": source or resolve_session_id_log_source(),
        "status": status,
        "SessionID_status": status,
        "created_at": now,
        "recorded_at": now,
        "updated_at": now,
        "api_route": session_create_api_path(),
        "find_peer_route": resolve_find_peer_gui_route(),
        "connect_handshake_route": resolve_connect_handshake_gui_route(),
        "master_server_url": master_server_session_create_url(),
        "hardware_primary_ip": resolve_session_secret("HARDWARE_PRIMARY_IP"),
        "hardware_primary_mac": resolve_session_secret("HARDWARE_PRIMARY_MAC"),
    }
    session_id_log_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": entry},
        upsert=True,
    )
    return entry


@with_mongo
def touch_session_id_log(
    *,
    session_id: str,
    status: str | None = None,
    user_ids: list[str] | None = None,
    client: Any,
) -> dict[str, Any]:
    updates: dict[str, Any] = {"updated_at": utc_now()}
    if status is not None:
        updates["status"] = status
        updates["SessionID_status"] = status
    if user_ids is not None:
        updates["userIDs"] = list(user_ids)
    session_id_log_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": updates},
    )
    return {"sessionID": session_id.strip(), **updates}


@with_mongo
def create_session_id_request(
    *,
    host_user_id: str,
    user_ids: list[str] | None = None,
    client: Any,
) -> dict[str, Any]:
    """
    MasterServer-only SessionID creation for a UserID (fixes.txt §5.10).
    Inserts into LucidTops_SessionsDB; no chunk/blockchain side effects.
    """
    if not host_user_id or not str(host_user_id).strip():
        raise ValueError("host_user_id is required")

    session_id = generate_session_id(host_user_id=host_user_id)
    while session_id_log_collection(client).find_one(
        {"sessionID": session_id}
    ) or session_records_collection(client).find_one({"sessionID": session_id}):
        session_id = generate_session_id(host_user_id=host_user_id)

    ids = list(user_ids or [host_user_id.strip()])
    if host_user_id.strip() not in ids:
        ids.insert(0, host_user_id.strip())

    entry = log_session_id(
        session_id=session_id,
        host_user_id=host_user_id.strip(),
        user_ids=ids,
        status="pending",
        client=client,
    )
    return {
        "sessionID": session_id,
        "SessionID": int(session_id),
        "hostUserID": host_user_id.strip(),
        "userIDs": ids,
        "status": "pending",
        "SessionID_status": "pending",
        "log": entry,
    }


@with_mongo
def remove_stale_session_ids(*, client: Any) -> dict[str, Any]:
    """Remove un-finalised sessionID log entries past inactivity window."""
    days = resolve_session_inactivity_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    finalised = resolve_finalised_statuses()
    col = session_id_log_collection(client)
    stale = list(
        col.find(
            {
                "status": {"$nin": list(finalised)},
                "updated_at": {"$lt": cutoff.isoformat()},
            }
        )
    )
    removed: list[str] = []
    for doc in stale:
        sid = str(doc.get("sessionID") or "")
        if not sid:
            continue
        col.delete_one({"sessionID": sid})
        session_records_collection(client).delete_one({"sessionID": sid})
        removed.append(sid)
    return {"removed_count": len(removed), "removed_sessionIDs": removed, "cutoff_days": days}


@with_mongo
def audit_inactive_tally_session_ids(*, client: Any) -> dict[str, Any]:
    """Flag NodeUserIDs linked to inactive tally sessionIDs (NodeGov.py)."""
    db = get_master_db(client)
    finalised = resolve_finalised_statuses()
    flagged: list[dict[str, Any]] = []
    for doc in session_id_log_collection(client).find(
        {"status": {"$nin": list(finalised)}}
    ):
        entity_id = doc.get("hostUserID")
        session_id = doc.get("sessionID")
        if not entity_id or not session_id:
            continue
        if db.node_users.find_one({"NodeUserID": entity_id}) or db.node_users.find_one(
            {"NodeID": entity_id}
        ):
            db.node_users.update_one(
                {"$or": [{"NodeUserID": entity_id}, {"NodeID": entity_id}]},
                {
                    "$set": {
                        "fraud_flag": True,
                        "fraud_reason": "inactive_sessionID",
                        "sessionID": session_id,
                        "updated_at": utc_now(),
                    }
                },
            )
            flagged.append({"NodeUserID": str(entity_id), "sessionID": session_id})
    return {"flagged_count": len(flagged), "flagged": flagged}
