"""Load and write LucidTops databases.secrets / mongodb.secrets at time of operation.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from Dns_databases import (
    ALL_NAMED_DB_CONTAINERS,
    DB_DATA_SUBDIR,
    DB_ZONE,
    secret_key_prefix,
    tor_db_containers,
    nontor_db_containers,
)

DATABASES_SECRETS_FILE_ENV = "DATABASES_SECRETS_FILE"
DATABASES_SECRETS_NAME_ENV = "DATABASES_SECRETS_NAME"
MONGODB_SECRETS_FILE_ENV = "MONGODB_SECRETS_FILE"
SECRETS_DIR_ENV = "SECRETS_DIR"
LUCID_TOPS_ROOT_ENV = "LUCID_TOPS_ROOT"

# Keys expected by backend/NodeDbSchema.py — preserved when present at operation time.
NODE_DB_SCHEMA_KEYS: tuple[str, ...] = (
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

SHARED_OPERATION_KEYS: tuple[str, ...] = (
    "MONGODB_IMAGE",
    "MONGODB_CONTAINER_PORT",
    "MONGODB_DATA_PATH_IN_CONTAINER",
    "DOCKER_NETWORK_TOR_DB",
    "DOCKER_NETWORK_NONTOR_DB",
    "MONGODB_ADMIN_USER",
    "MONGODB_ADMIN_PASSWORD",
    "MONGODB_PASSWORD",
    "LEDGER_REPLICA_SOURCE",
    "LEDGER_REPLICA_TARGET",
    "DATABASES_VERIFIED",
    "DATABASES_VERIFIED_AT",
    "DATABASES_COMPOSE_FILE",
    "HOST_PRIMARY_IP",
    "HOST_PRIMARY_MAC",
    "HOST_MACHINE_ID",
    "HOST_HOSTNAME",
    "MONGODB_DATA_MOUNT",
    "LUCID_DATABASES_DIR",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def secrets_dir() -> Path:
    configured = _env(SECRETS_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    root = _env(LUCID_TOPS_ROOT_ENV)
    if not root:
        raise RuntimeError(
            f"{SECRETS_DIR_ENV} or {LUCID_TOPS_ROOT_ENV} missing — must be set at time of operation"
        )
    name = _env("SECRETS_DIR_NAME")
    if not name:
        raise RuntimeError(
            "SECRETS_DIR_NAME missing — must be set at time of operation when SECRETS_DIR is unset"
        )
    return Path(root).expanduser() / name


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def write_secrets_file(path: Path, values: dict[str, str], *, header: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        header,
        f"# Generated: {utc_now()}",
        "# key=value — values pulled/created at time of operation",
        "",
    ]
    for key in sorted(values):
        value = str(values[key]).strip()
        if value:
            lines.append(f"{key}={value}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def databases_secrets_path() -> Path:
    override = _env(DATABASES_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    name = _env(DATABASES_SECRETS_NAME_ENV)
    if name:
        return secrets_dir() / name
    return secrets_dir() / "databases.secrets"


def mongodb_secrets_path() -> Path:
    override = _env(MONGODB_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return secrets_dir() / "mongodb.secrets"


@lru_cache(maxsize=1)
def _load_databases_secrets_cached() -> dict[str, str]:
    path = databases_secrets_path()
    if not path.exists():
        return {}
    values = parse_secrets_file(path)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return values


def load_databases_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_databases_secrets_cached.cache_clear()
    return dict(_load_databases_secrets_cached())


def get_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    return load_databases_secrets().get(key.upper(), "").strip()


def require_secret(key: str) -> str:
    value = get_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/databases.secrets — "
            "value must be created at time of operation"
        )
    return value


def require_secret_int(key: str) -> int:
    raw = require_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be an integer — got {raw!r}") from exc


def _generate_password() -> str:
    return secrets.token_urlsafe(32)


def _resolve_mongodb_image(pull: dict[str, Any]) -> str:
    image = _env("MONGODB_IMAGE") or str(pull.get("mongodb_image") or "").strip()
    if not image:
        raise RuntimeError(
            "MONGODB_IMAGE missing — must be set at time of operation (env or pull)"
        )
    return image


def _resolve_container_port(pull: dict[str, Any]) -> str:
    port = _env("MONGODB_CONTAINER_PORT") or str(
        pull.get("mongodb_container_port") or ""
    ).strip()
    if not port:
        raise RuntimeError(
            "MONGODB_CONTAINER_PORT missing — must be set at time of operation "
            "(env, mongo listener pull, or secrets)"
        )
    try:
        int(port)
    except ValueError as exc:
        raise RuntimeError(f"MONGODB_CONTAINER_PORT must be an integer — got {port!r}") from exc
    return port


def _resolve_data_path_in_container() -> str:
    path = _env("MONGODB_DATA_PATH_IN_CONTAINER")
    if not path:
        raise RuntimeError(
            "MONGODB_DATA_PATH_IN_CONTAINER missing — must be set at time of operation"
        )
    return path


def _merge_existing(path: Path, built: dict[str, str], *, force: bool) -> dict[str, str]:
    if force or not path.exists():
        return built
    existing = parse_secrets_file(path)
    merged = dict(existing)
    for key, value in built.items():
        if key not in merged or not merged[key]:
            merged[key] = value
        elif key.endswith("_VERIFIED") or key.endswith("_VERIFIED_AT"):
            merged[key] = value
        elif key in {
            "DATABASES_COMPOSE_FILE",
            "HOST_PRIMARY_IP",
            "HOST_PRIMARY_MAC",
            "HOST_MACHINE_ID",
            "HOST_HOSTNAME",
            "MONGODB_DATA_MOUNT",
            "LUCID_DATABASES_DIR",
            "DOCKER_NETWORK_TOR_DB",
            "DOCKER_NETWORK_NONTOR_DB",
        }:
            merged[key] = value
    return merged


def build_databases_secrets_values(
    pull: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, str]:
    """Build databases.secrets values from hardware pull + generated credentials."""
    databases_dir = Path(str(pull["databases_dir"]))
    secrets_path = databases_secrets_path()
    mongo_path = mongodb_secrets_path()

    existing = parse_secrets_file(secrets_path) if secrets_path.exists() and not force else {}

    admin_user = _env("MONGODB_ADMIN_USER") or existing.get("MONGODB_ADMIN_USER", "")
    if not admin_user:
        admin_user = f"admin_{str(pull['machine_id'])[:8]}"
    admin_password = (
        _env("MONGODB_ADMIN_PASSWORD")
        or existing.get("MONGODB_ADMIN_PASSWORD", "")
        or _generate_password()
    )
    mongo_password = (
        _env("MONGODB_PASSWORD")
        or existing.get("MONGODB_PASSWORD", "")
        or _generate_password()
    )

    container_port = _resolve_container_port(pull)
    data_in_container = _resolve_data_path_in_container()
    image = _resolve_mongodb_image(pull)

    tor_net = str(pull["docker_network_tor_db"])
    nontor_net = str(pull["docker_network_nontor_db"])
    compose_file = Path(str(pull["compose_dir"])) / "databases.compose.yml"

    values: dict[str, str] = {
        "MONGODB_IMAGE": image,
        "MONGODB_CONTAINER_PORT": container_port,
        "MONGODB_DATA_PATH_IN_CONTAINER": data_in_container,
        "DOCKER_NETWORK_TOR_DB": tor_net,
        "DOCKER_NETWORK_NONTOR_DB": nontor_net,
        "MONGODB_ADMIN_USER": admin_user,
        "MONGODB_ADMIN_PASSWORD": admin_password,
        "MONGODB_PASSWORD": mongo_password,
        "LEDGER_REPLICA_SOURCE": "LucidTops_LedgerDB",
        "LEDGER_REPLICA_TARGET": "LucidTopsBlockchain_LedgerDB",
        "DATABASES_COMPOSE_FILE": compose_file.as_posix(),
        "HOST_PRIMARY_IP": str(pull["primary_ip"]),
        "HOST_PRIMARY_MAC": str(pull["primary_mac"]),
        "HOST_MACHINE_ID": str(pull["machine_id"]),
        "HOST_HOSTNAME": str(pull["hostname"]),
        "MONGODB_DATA_MOUNT": databases_dir.as_posix(),
        "LUCID_DATABASES_DIR": databases_dir.as_posix(),
        "MONGODB_SECRETS_FILE": mongo_path.as_posix(),
    }

    for db_name in ALL_NAMED_DB_CONTAINERS:
        prefix = secret_key_prefix(db_name)
        zone = DB_ZONE[db_name]
        network = tor_net if zone == "tor" else nontor_net
        subdir = DB_DATA_SUBDIR[db_name]
        data_mount = (databases_dir / subdir).as_posix()
        host_port_key = f"{prefix}_HOST_PORT"
        host_port = _env(host_port_key) or existing.get(host_port_key, "")
        if not host_port:
            from pull_information import allocate_ephemeral_port

            host_port = str(allocate_ephemeral_port())

        values[f"{prefix}_HOST"] = db_name
        values[f"{prefix}_PORT"] = container_port
        values[f"{prefix}_HOST_PORT"] = host_port
        values[f"{prefix}_DATA_MOUNT"] = data_mount
        values[f"{prefix}_NETWORK"] = network
        values[f"{prefix}_ZONE"] = zone
        values[f"{prefix}_URL"] = f"mongodb://{db_name}:{container_port}"

    for key in NODE_DB_SCHEMA_KEYS:
        if key == "MONGODB_SECRETS_FILE":
            continue
        value = _env(key) or existing.get(key, "")
        if value:
            values[key] = value

    master_host = (
        _env("MASTER_SERVER_INTERNAL_HOST")
        or str(pull.get("proxy_backend_dns") or "")
        or existing.get("MASTER_SERVER_INTERNAL_HOST", "")
    )
    master_port = (
        _env("MASTER_SERVER_INTERNAL_PORT")
        or str(pull.get("master_server_port") or "")
        or existing.get("MASTER_SERVER_INTERNAL_PORT", "")
    )
    if master_host:
        values["MASTER_SERVER_INTERNAL_HOST"] = master_host
    if master_port:
        values["MASTER_SERVER_INTERNAL_PORT"] = master_port

    return _merge_existing(secrets_path, values, force=force)


def build_mongodb_secrets_values(
    databases_values: dict[str, str],
    *,
    verified: bool = False,
) -> dict[str, str]:
    """Coordinate mongodb.secrets with per-DB hosts from databases.secrets."""
    sessions_prefix = secret_key_prefix("LucidTops_SessionsDB")
    host = databases_values.get(f"{sessions_prefix}_HOST", "")
    port = databases_values.get(f"{sessions_prefix}_PORT", "")
    values: dict[str, str] = {
        "MONGODB_HOST": host,
        "MONGODB_PORT": port,
        "MONGODB_URL": databases_values.get(f"{sessions_prefix}_URL", ""),
        "LUCID_MONGODB_URL": f"mongodb://{host}:{port}" if host and port else "",
        "MONGODB_PASSWORD": databases_values.get("MONGODB_PASSWORD", ""),
        "MONGODB_ADMIN_PASSWORD": databases_values.get("MONGODB_ADMIN_PASSWORD", ""),
        "MONGODB_DATA_MOUNT": databases_values.get("MONGODB_DATA_MOUNT", ""),
        "MONGODB_IMAGE": databases_values.get("MONGODB_IMAGE", ""),
        "DOCKER_NETWORK_TOR_DB": databases_values.get("DOCKER_NETWORK_TOR_DB", ""),
        "DOCKER_NETWORK_NONTOR_DB": databases_values.get("DOCKER_NETWORK_NONTOR_DB", ""),
        "LEDGER_REPLICA_SOURCE": databases_values.get("LEDGER_REPLICA_SOURCE", ""),
        "LEDGER_REPLICA_TARGET": databases_values.get("LEDGER_REPLICA_TARGET", ""),
    }
    socks_host = _env("TOR_SOCKS_HOST")
    socks_port = _env("TOR_SOCKS_PORT")
    if socks_host and socks_port:
        values["TOR_SOCKS_HOST"] = socks_host
        values["TOR_SOCKS_PORT"] = socks_port
        values["MONGODB_VIA_SOCKS5"] = _env("MONGODB_VIA_SOCKS5") or "true"
    socks_user = _env("TOR_SOCKS_USERNAME") or _env("TOR_SOCKS_USER")
    socks_pass = _env("TOR_SOCKS_PASSWORD")
    if socks_user:
        values["TOR_SOCKS_USERNAME"] = socks_user
    if socks_pass:
        values["TOR_SOCKS_PASSWORD"] = socks_pass

    for db_name in ALL_NAMED_DB_CONTAINERS:
        prefix = secret_key_prefix(db_name)
        for suffix in ("HOST", "PORT", "HOST_PORT", "URL", "ZONE", "NETWORK", "DATA_MOUNT"):
            key = f"{prefix}_{suffix}"
            if key in databases_values:
                values[key] = databases_values[key]

    if verified:
        values["MONGODB_VERIFIED"] = "true"
        values["MONGODB_VERIFIED_AT"] = utc_now()
        values["DATABASES_VERIFIED"] = "true"
        values["DATABASES_VERIFIED_AT"] = utc_now()

    return {k: v for k, v in values.items() if v}


def write_databases_secrets(
    pull: dict[str, Any],
    *,
    force: bool = False,
    verified: bool = False,
) -> tuple[Path, Path, dict[str, str]]:
    values = build_databases_secrets_values(pull, force=force)
    if verified:
        values["DATABASES_VERIFIED"] = "true"
        values["DATABASES_VERIFIED_AT"] = utc_now()
    db_path = write_secrets_file(
        databases_secrets_path(),
        values,
        header="# LucidTops databases.secrets - written at time of operation",
    )
    mongo_values = build_mongodb_secrets_values(values, verified=verified)
    mongo_path = write_secrets_file(
        mongodb_secrets_path(),
        mongo_values,
        header="# LucidTops mongodb.secrets - coordinated from Databases bootstrap",
    )
    load_databases_secrets(reload=True)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return db_path, mongo_path, values


def mark_databases_verified(values: dict[str, str]) -> tuple[Path, Path]:
    values = dict(values)
    values["DATABASES_VERIFIED"] = "true"
    values["DATABASES_VERIFIED_AT"] = utc_now()
    db_path = write_secrets_file(
        databases_secrets_path(),
        values,
        header="# LucidTops databases.secrets - written at time of operation",
    )
    mongo_values = build_mongodb_secrets_values(values, verified=True)
    mongo_path = write_secrets_file(
        mongodb_secrets_path(),
        mongo_values,
        header="# LucidTops mongodb.secrets - coordinated from Databases bootstrap",
    )
    load_databases_secrets(reload=True)
    return db_path, mongo_path


def databases_secrets_status() -> dict[str, Any]:
    path = databases_secrets_path()
    loaded = load_databases_secrets() if path.exists() else {}
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "mongodb_secrets_file": mongodb_secrets_path().as_posix(),
        "databases_verified": loaded.get("DATABASES_VERIFIED", "").lower()
        in {"1", "true", "yes"},
        "tor_db_containers": list(tor_db_containers()),
        "nontor_db_containers": list(nontor_db_containers()),
        "compose_file": loaded.get("DATABASES_COMPOSE_FILE", ""),
        "data_mount": loaded.get("MONGODB_DATA_MOUNT", ""),
    }
