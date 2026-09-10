"""Shared helpers for LucidTops session modules (Tor-only, Docker-compatible).
uses Documents/fixes.txt for correction requirements.

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

SESSIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SESSIONS_DIR) not in sys.path:
    sys.path.insert(0, str(SESSIONS_DIR))

from config import get_mongo_client, utc_now  # noqa: E402


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def resolve_sessions_secret(key: str) -> str:
    """Resolve one config value: env > sessions.secrets; raise if missing."""
    env_value = _env(key)
    if env_value:
        return env_value
    path_raw = _env("SESSIONS_SECRETS_FILE")
    if not path_raw:
        secrets_dir = _env("SECRETS_DIR")
        name = _env("SESSIONS_SECRETS_NAME")
        if not name:
            container = _env("SESSIONS_CONTAINER_NAME")
            name = f"{container}.secrets" if container else "sessions.secrets"
        if secrets_dir:
            path_raw = str(Path(secrets_dir) / name)
    if path_raw:
        path = Path(path_raw).expanduser()
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    file_key, _, value = stripped.partition("=")
                    if file_key.strip().upper() == key.upper():
                        file_value = value.strip()
                        if file_value:
                            return file_value
            except OSError:
                pass
    raise RuntimeError(
        f"{key} missing from environment/sessions.secrets — "
        "value must be created at time of operation"
    )


def resolve_sessions_secret_int(key: str) -> int:
    raw = resolve_sessions_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{key} must be an integer in environment/sessions.secrets"
        ) from exc


def resolve_sessions_secret_bool(key: str) -> bool:
    raw = resolve_sessions_secret(key).lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{key} must be a boolean in environment/sessions.secrets")


def get_sessions_db(client: Any) -> Any:
    """Tor-hosted LucidTops_SessionsDB (name from secrets at time of operation)."""
    return client[resolve_sessions_secret("LUCIDTOPS_SESSIONS_DB_NAME")]


def get_master_db(client: Any) -> Any:
    """MasterServer DB for UserID/TokenID verification (outside sessions records)."""
    from config import get_master_db as _get_master_db

    return _get_master_db(client)


def session_records_collection(client: Any) -> Any:
    return get_sessions_db(client)[
        resolve_sessions_secret("LUCIDTOPS_SESSIONS_COLLECTION")
    ]


def session_id_log_collection(client: Any) -> Any:
    return get_sessions_db(client)[
        resolve_sessions_secret("LUCIDTOPS_SESSIONS_ID_LOG_COLLECTION")
    ]


def with_mongo(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Run a database handler with an auto-closing Mongo client when needed."""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        client = kwargs.pop("client", None)
        owns_client = client is None
        if owns_client:
            client = get_mongo_client()
            if client is None:
                raise RuntimeError("Master server database is unavailable")
        try:
            return handler(*args, client=client, **kwargs)
        finally:
            if owns_client and client is not None:
                client.close()

    return wrapper


def verify_user_id_token(
    *,
    user_id: str,
    id_token: str,
    client: Any,
) -> bool:
    if not id_token or not id_token.strip():
        return False
    db = get_master_db(client)
    token = id_token.strip()
    if db.id_tokens.find_one({"entity": "user", "UserID": user_id, "IDToken": token}):
        return True
    if db.id_tokens.find_one({"entity": "user", "UserID": user_id, "TokenID": token}):
        return True
    if db.users.find_one({"UserID": user_id, "IDToken": token}):
        return True
    if db.users.find_one({"UserID": user_id, "TokenID": token}):
        return True
    # MasterUserID / AdminID used as UserID unless Node_mode (fixes.txt §5.11–12)
    if db.id_tokens.find_one(
        {"entity": "master_user", "MasterUserID": user_id, "TokenID": token}
    ):
        return True
    if db.id_tokens.find_one({"entity": "admin", "AdminID": user_id, "TokenID": token}):
        return True
    return False


def verify_node_id_token(
    *,
    node_user_id: str,
    id_token: str,
    client: Any,
) -> bool:
    if not id_token or not id_token.strip():
        return False
    db = get_master_db(client)
    token = id_token.strip()
    if db.id_tokens.find_one(
        {"entity": "node", "NodeUserID": node_user_id, "IDToken": token}
    ):
        return True
    if db.id_tokens.find_one(
        {"entity": "node", "NodeID": node_user_id, "TokenID": token}
    ):
        return True
    return db.node_users.find_one({"NodeUserID": node_user_id, "IDToken": token}) is not None


def session_statuses() -> frozenset[str]:
    raw = resolve_sessions_secret("SESSION_FINALISED_STATUSES")
    base = {"pending", "active", "ended", "complete", "compressed"}
    extra = {item.strip() for item in raw.split(",") if item.strip()}
    return frozenset(base | extra)


def complete_status_value() -> str:
    return resolve_sessions_secret("SESSION_COMPLETE_STATUS")
