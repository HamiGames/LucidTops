"""The schema for the NodeUserID hosted database (mongodb database design), this uses a FastAPI connection system.
each NodeUserID will have a unique DatabaseID for the NodeUserID hosted database.
each NodeDB is synchronized with the MasterServer (LucidTopsDB) via the FastAPI connection system.
each NodeDB will have a synchronised version of the LedgerDB (BlockchainDB) via the FastAPI connection system.
A NodeUser Can Not manually modify the NodeDB, only the MasterServer (LucidTopsDB) can modify the NodeDB.
all sessionID's are Live updated from the CreateSession API route.(via the FastAPI, MasterServer)

Collection Content:

User:[userID: str,
idToken: str,
SessionID: str,
SessionID-hash: str,
SessionData-hash: str ]

Sessions:[SessionID: str,
SessionID-hash: str,
SessionData-hash: str ]

Blockchain:[LedgerID: str,
LedgerData-hash: str, 
Last-BlockID: str,
last-block-timestamp: datetime,
lastblock-creator: str,
]
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import SECRETS_DIR, require_env

DEFAULT_DATABASES_SECRETS_NAME = "databases.secrets"
DATABASES_SECRETS_FILE_ENV = "DATABASES_SECRETS_FILE"

# Host-mounted databases.secrets keys (Server container reads SECRETS_DIR from LucidTops).
DATABASES_SECRETS_KEYS: tuple[str, ...] = (
    "NODE_HOSTED_DB_COLLECTION",
    "NODE_SEED_COLLECTION",
    "NODE_USER_COLLECTION",
    "NODE_SESSIONS_COLLECTION",
    "NODE_BLOCKCHAIN_COLLECTION",
    "NODE_DB_API_PREFIX",
    "NODE_CREATE_SESSION_ROUTE",
    "NODE_DATABASE_SEED_ROUTE",
    "NODE_DATABASE_SEED_FIND_ROUTE",
    "NODE_DATABASE_SEED_CONNECT_ROUTE",
    "NODE_DATABASE_SEED_DISCONNECT_ROUTE",
    "NODE_DATABASE_SEED_END_ROUTE",
    "NODE_DATABASE_SEED_RECORD_ROUTE",
    "NODE_DATABASE_SEED_TRANSFER_ROUTE",
    "NODE_DATABASE_SEED_CONTROL_ROUTE",
    "NODE_DATABASE_SEED_UPLOAD_ROUTE",
    "NODE_DATABASE_SEED_DOWNLOAD_ROUTE",
    "NODE_DATABASE_SEED_DELETE_ROUTE",
    "NODE_DATABASE_SEED_RENAME_ROUTE",
    "NODE_DATABASE_SEED_SYNC_ROUTE",
    "MASTER_SERVER_INTERNAL_HOST",
    "MASTER_SERVER_INTERNAL_PORT",
    "MONGODB_SECRETS_FILE",
)


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def databases_secrets_path() -> Path:
    override = os.environ.get(DATABASES_SECRETS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return SECRETS_DIR / DEFAULT_DATABASES_SECRETS_NAME


@lru_cache(maxsize=1)
def _load_databases_secrets_cached() -> dict[str, str]:
    values: dict[str, str] = {}
    path = databases_secrets_path()
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def load_databases_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_databases_secrets_cached.cache_clear()
    return _load_databases_secrets_cached()


def resolve_secret(key: str) -> str:
    """Resolve one config value: env var > databases.secrets; raise if missing."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    file_value = load_databases_secrets().get(key.upper(), "").strip()
    if file_value:
        return file_value
    raise RuntimeError(
        f"required databases secret {key} is missing from environment and databases.secrets"
    )


def resolve_secret_optional(key: str) -> str:
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    return load_databases_secrets().get(key.upper(), "").strip()


def resolve_secret_int(key: str) -> int:
    raw = resolve_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"databases secret {key} must be an integer") from exc


def _normalize_route(route: str) -> str:
    cleaned = route.strip()
    if not cleaned:
        raise RuntimeError("route value must not be empty")
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def _normalize_api_prefix(prefix: str) -> str:
    cleaned = prefix.strip()
    if not cleaned:
        raise RuntimeError("NODE_DB_API_PREFIX must not be empty")
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    normalized = cleaned.rstrip("/")
    if not normalized:
        raise RuntimeError("NODE_DB_API_PREFIX must not be empty")
    return normalized


def resolve_node_db_api_prefix() -> str:
    return _normalize_api_prefix(resolve_secret("NODE_DB_API_PREFIX"))


def resolve_route(key: str) -> str:
    return _normalize_route(resolve_secret(key))


def resolve_create_session_route() -> str:
    return resolve_route("NODE_CREATE_SESSION_ROUTE")


def resolve_database_seed_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_ROUTE")


def resolve_database_seed_find_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_FIND_ROUTE")


def resolve_database_seed_connect_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_CONNECT_ROUTE")


def resolve_database_seed_disconnect_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_DISCONNECT_ROUTE")


def resolve_database_seed_end_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_END_ROUTE")


def resolve_database_seed_record_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_RECORD_ROUTE")


def resolve_database_seed_transfer_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_TRANSFER_ROUTE")


def resolve_database_seed_control_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_CONTROL_ROUTE")


def resolve_database_seed_upload_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_UPLOAD_ROUTE")


def resolve_database_seed_download_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_DOWNLOAD_ROUTE")


def resolve_database_seed_delete_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_DELETE_ROUTE")


def resolve_database_seed_rename_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_RENAME_ROUTE")


def resolve_database_seed_sync_route() -> str:
    return resolve_route("NODE_DATABASE_SEED_SYNC_ROUTE")


def resolve_master_server_internal_host() -> str:
    return resolve_secret("MASTER_SERVER_INTERNAL_HOST")


def resolve_master_server_internal_port() -> int:
    return resolve_secret_int("MASTER_SERVER_INTERNAL_PORT")


def resolve_mongodb_secrets_file() -> Path:
    override = resolve_secret_optional("MONGODB_SECRETS_FILE")
    if override:
        return Path(override).expanduser()
    env_override = os.environ.get("MONGODB_SECRETS_FILE", "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return SECRETS_DIR / "mongodb.secrets"


def resolve_node_hosted_db_collection() -> str:
    return resolve_secret("NODE_HOSTED_DB_COLLECTION")


def resolve_node_seed_collection() -> str:
    return resolve_secret("NODE_SEED_COLLECTION")


def resolve_node_user_collection() -> str:
    return resolve_secret("NODE_USER_COLLECTION")


def resolve_node_sessions_collection() -> str:
    return resolve_secret("NODE_SESSIONS_COLLECTION")


def resolve_node_blockchain_collection() -> str:
    return resolve_secret("NODE_BLOCKCHAIN_COLLECTION")


def node_create_session_path() -> str:
    """Full FastAPI CreateSession path used for live SessionID sync into NodeDB."""
    return f"{resolve_node_db_api_prefix()}{resolve_create_session_route()}"


def node_database_seed_routes() -> tuple[str, ...]:
    """Externally configurable NodeDB seed routes (from databases.secrets)."""
    return (
        resolve_database_seed_route(),
        resolve_database_seed_find_route(),
        resolve_database_seed_connect_route(),
        resolve_database_seed_disconnect_route(),
        resolve_database_seed_end_route(),
        resolve_database_seed_record_route(),
        resolve_database_seed_transfer_route(),
        resolve_database_seed_control_route(),
        resolve_database_seed_upload_route(),
        resolve_database_seed_download_route(),
        resolve_database_seed_delete_route(),
        resolve_database_seed_rename_route(),
        resolve_database_seed_sync_route(),
    )


def _resolve_collection_constants() -> tuple[str, str, str, str, str]:
    return (
        resolve_node_hosted_db_collection(),
        resolve_node_seed_collection(),
        resolve_node_user_collection(),
        resolve_node_sessions_collection(),
        resolve_node_blockchain_collection(),
    )


# Comment Collection Content — User
NODE_USER_FIELDS: tuple[str, ...] = (
    "userID",
    "idToken",
    "SessionID",
    "SessionID-hash",
    "SessionData-hash",
)

# Comment Collection Content — Sessions
NODE_SESSIONS_FIELDS: tuple[str, ...] = (
    "SessionID",
    "SessionID-hash",
    "SessionData-hash",
)

# Comment Collection Content — Blockchain
NODE_BLOCKCHAIN_FIELDS: tuple[str, ...] = (
    "LedgerID",
    "LedgerData-hash",
    "Last-BlockID",
    "last-block-timestamp",
    "lastblock-creator",
)

# Primary NodeDB schema fields (User collection — comment contract).
NODE_DB_SCHEMA_FIELDS: tuple[str, ...] = NODE_USER_FIELDS

# Master-side seed / hosted-registry metadata (node-seed.py, DatabaseRoutes).
NODE_SEED_FIELDS: tuple[str, ...] = (
    "NodeUserID",
    "NodeDatabaseID",
    "UserID",
    "IDToken",
    "created_at",
    "updated_at",
)

NODE_HOSTED_DB_FIELDS: tuple[str, ...] = (
    "NodeUserID",
    "NodeDatabaseID",
    "IDToken",
    "status",
    "created_at",
    "updated_at",
)

_COLLECTION_ATTRS = frozenset(
    {
        "NODE_HOSTED_DB_COLLECTION",
        "NODE_SEED_COLLECTION",
        "NODE_USER_COLLECTION",
        "NODE_SESSIONS_COLLECTION",
        "NODE_BLOCKCHAIN_COLLECTION",
        "NODE_DB_COLLECTION_SCHEMAS",
        "COLLECTION_SCHEMAS",
    }
)


def refresh_node_db_collection_constants() -> None:
    global NODE_HOSTED_DB_COLLECTION, NODE_SEED_COLLECTION, NODE_USER_COLLECTION
    global NODE_SESSIONS_COLLECTION, NODE_BLOCKCHAIN_COLLECTION
    global NODE_DB_COLLECTION_SCHEMAS, COLLECTION_SCHEMAS
    (
        NODE_HOSTED_DB_COLLECTION,
        NODE_SEED_COLLECTION,
        NODE_USER_COLLECTION,
        NODE_SESSIONS_COLLECTION,
        NODE_BLOCKCHAIN_COLLECTION,
    ) = _resolve_collection_constants()
    NODE_DB_COLLECTION_SCHEMAS = {
        NODE_USER_COLLECTION: NODE_USER_FIELDS,
        NODE_SESSIONS_COLLECTION: NODE_SESSIONS_FIELDS,
        NODE_BLOCKCHAIN_COLLECTION: NODE_BLOCKCHAIN_FIELDS,
    }
    COLLECTION_SCHEMAS = {
        NODE_HOSTED_DB_COLLECTION: NODE_HOSTED_DB_FIELDS,
        NODE_SEED_COLLECTION: NODE_SEED_FIELDS,
        **NODE_DB_COLLECTION_SCHEMAS,
    }


def __getattr__(name: str):
    if name in _COLLECTION_ATTRS:
        refresh_node_db_collection_constants()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def schema_template(fields: tuple[str, ...]) -> dict[str, None]:
    return {field: None for field in fields}


def node_db_schema_templates() -> dict[str, dict[str, None]]:
    """Templates for the three NodeDB collections defined in the module comment."""
    refresh_node_db_collection_constants()
    return {
        collection: schema_template(fields)
        for collection, fields in NODE_DB_COLLECTION_SCHEMAS.items()
    }


def databases_secrets_status() -> dict[str, Any]:
    refresh_node_db_collection_constants()
    path = databases_secrets_path()
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "node_hosted_db_collection": NODE_HOSTED_DB_COLLECTION,
        "node_seed_collection": NODE_SEED_COLLECTION,
        "node_user_collection": NODE_USER_COLLECTION,
        "node_sessions_collection": NODE_SESSIONS_COLLECTION,
        "node_blockchain_collection": NODE_BLOCKCHAIN_COLLECTION,
        "node_db_api_prefix": resolve_node_db_api_prefix(),
        "create_session_path": node_create_session_path(),
        "database_seed_routes": list(node_database_seed_routes()),
        "master_server_internal_host": resolve_master_server_internal_host(),
        "master_server_internal_port": resolve_master_server_internal_port(),
        "mongodb_secrets_file": resolve_mongodb_secrets_file().as_posix(),
    }


def write_databases_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write databases.secrets for Server-container host mount (LucidTops/secrets)."""
    target_dir = secrets_dir or SECRETS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / DEFAULT_DATABASES_SECRETS_NAME
    if path.exists() and not force:
        return path

    resolved: dict[str, str] = {}
    for key in DATABASES_SECRETS_KEYS:
        if key == "MONGODB_SECRETS_FILE":
            value = resolve_secret_optional(key) if populate_from_env else ""
        elif populate_from_env:
            value = resolve_secret(key)
        else:
            value = require_env(key)
        resolved[key] = value

    if not resolved.get("MONGODB_SECRETS_FILE"):
        resolved["MONGODB_SECRETS_FILE"] = (target_dir / "mongodb.secrets").as_posix()

    lines = [
        "# LucidTops databases.secrets - loaded by backend/NodeDbSchema.py",
        f"# Generated: {utc_now()}",
        "# Mounted into lucid-server-default via SECRETS_DIR (/mnt/myssd/LucidTops/secrets).",
        "# Collection names and FastAPI routes are externally configurable — no placeholders.",
        "",
    ]
    for key in DATABASES_SECRETS_KEYS:
        value = resolved[key]
        lines.append(f"{key}={value}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    load_databases_secrets(reload=True)
    refresh_node_db_collection_constants()
    return path
