"""DockerDNS mapping for the six LucidTops Databases containers.

Canonical inventory from documentation/Databases.txt (prefix = MONGODB_MAIN_DATABASE_NAME):
- {prefix}_SessionsDB
- {prefix}__LedgerDB
- {prefix}_UserDB
- {prefix}_NodeDB
- {prefix}_ChainDB
- {prefix}_PaymentDB

MONGODB_MAIN_DATABASE_NAME is the prefix (LucidTops), not a seventh container.
Host data dirs are DB_ROOT/<container name>. mongo:7.0 writes to /data/db.

Content mounts from documentation/containers.txt section 4:
- ROOT=/mnt/myssd/LucidTops
- DB_ROOT=/mnt/myssd/LucidTops/DATA

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Console paths from documentation/containers.txt section 4.
ROOT = "/mnt/myssd/LucidTops"
DB_ROOT = "/mnt/myssd/LucidTops/DATA"

# Path inside every mongo:7.0 container. Host side is DB_ROOT/<container name>.
MONGO_DATA_PATH_IN_CONTAINER = "/data/db"

# suffix, zone, has collection schema. ChainDB is created and pinged only.
# Ledger uses two underscores, matching documentation/Databases.txt.
CONTAINER_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("_SessionsDB", "tor", True),
    ("__LedgerDB", "tor", True),
    ("_UserDB", "nontor", True),
    ("_NodeDB", "nontor", True),
    ("_ChainDB", "nontor", False),
    ("_PaymentDB", "nontor", True),
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _console_secret_value(key: str) -> str:
    """Read one key from console secrets without importing the secrets writer."""
    root = Path(ROOT)
    files = (
        root / "Server" / "Secrets" / "databases.secrets",
        root / "Server" / "Secrets" / "Master.secrets",
        root / "Server" / "Secrets" / "proxy.secrets",
        root / "Server" / "Secrets" / "Proxy.secrets",
    )
    wanted = key.strip().upper()
    for path in files:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            found, value = stripped.split("=", 1)
            if found.strip().upper() == wanted and value.strip():
                return value.strip()
    return ""


def require_main_database_name(name: str) -> str:
    """Prefix for the six containers. Empty is refused. This is not a container name."""
    value = (name or "").strip()
    if not value:
        raise RuntimeError(
            "MONGODB_MAIN_DATABASE_NAME missing — must be set in Master.secrets or proxy.secrets"
        )
    if any(ch in value for ch in ("/", "\\", " ")):
        raise RuntimeError(
            f"MONGODB_MAIN_DATABASE_NAME {value!r} is not a container-name prefix"
        )
    return value


def resolve_main_database_name(candidate: str = "") -> str:
    value = (candidate or "").strip() or _env("MONGODB_MAIN_DATABASE_NAME")
    if not value:
        value = _console_secret_value("MONGODB_MAIN_DATABASE_NAME")
    return require_main_database_name(value)


def container_name(main_database_name: str, suffix: str) -> str:
    """One container: prefix plus a Databases.txt suffix (Ledger keeps two underscores)."""
    main = require_main_database_name(main_database_name)
    if suffix not in {item[0] for item in CONTAINER_SPECS}:
        raise RuntimeError(f"unknown database suffix {suffix!r}")
    return f"{main}{suffix}"


def named_db_containers(main_database_name: str) -> tuple[str, ...]:
    """Six containers derived from MONGODB_MAIN_DATABASE_NAME. The prefix is not a container."""
    main = require_main_database_name(main_database_name)
    names = tuple(f"{main}{suffix}" for suffix, _zone, _schema in CONTAINER_SPECS)
    if main in names or len(set(names)) != len(names):
        raise RuntimeError(
            "MONGODB_MAIN_DATABASE_NAME "
            f"{main!r} does not produce six distinct container names"
        )
    return names


def _resolved_main(candidate: str = "") -> str:
    value = (candidate or "").strip() or _env("MONGODB_MAIN_DATABASE_NAME")
    if not value:
        value = _console_secret_value("MONGODB_MAIN_DATABASE_NAME")
    return value.strip()


def all_named_db_containers() -> tuple[str, ...]:
    """Six containers when the prefix is known; otherwise empty."""
    candidate = _resolved_main()
    if not candidate:
        return ()
    try:
        return named_db_containers(candidate)
    except RuntimeError:
        return ()


def tor_db_containers(main_database_name: str = "") -> tuple[str, ...]:
    main = _resolved_main(main_database_name)
    if not main:
        return ()
    try:
        names = named_db_containers(main)
    except RuntimeError:
        return ()
    return tuple(
        name
        for name, (_suffix, zone, _schema) in zip(names, CONTAINER_SPECS)
        if zone == "tor"
    )


def nontor_db_containers(main_database_name: str = "") -> tuple[str, ...]:
    main = _resolved_main(main_database_name)
    if not main:
        return ()
    try:
        names = named_db_containers(main)
    except RuntimeError:
        return ()
    return tuple(
        name
        for name, (_suffix, zone, _schema) in zip(names, CONTAINER_SPECS)
        if zone == "nontor"
    )


def schema_db_containers(main_database_name: str = "") -> tuple[str, ...]:
    """Five schema containers. ChainDB is omitted (ping only)."""
    main = _resolved_main(main_database_name)
    if not main:
        return ()
    try:
        names = named_db_containers(main)
    except RuntimeError:
        return ()
    return tuple(
        name
        for name, (_suffix, _zone, has_schema) in zip(names, CONTAINER_SPECS)
        if has_schema
    )


def chain_db_container(main_database_name: str = "") -> str:
    main = _resolved_main(main_database_name)
    if not main:
        raise RuntimeError(
            "MONGODB_MAIN_DATABASE_NAME missing — must be set in Master.secrets or proxy.secrets"
        )
    return container_name(main, "_ChainDB")


# Importers that expect a tuple (backend write_container_secrets) see the six
# once MONGODB_MAIN_DATABASE_NAME is in the console secrets.
ALL_NAMED_DB_CONTAINERS: tuple[str, ...] = all_named_db_containers()


def secret_key_prefix(db_name: str) -> str:
    """Normalize a DockerDNS DB name into an UPPER_SNAKE secrets key prefix."""
    cleaned = db_name.strip().replace("-", "_")
    parts: list[str] = []
    buf = ""
    for ch in cleaned:
        if ch == "_":
            if buf:
                parts.append(buf)
                buf = ""
            continue
        buf += ch
    if buf:
        parts.append(buf)
    return "_".join(part.upper() for part in parts if part)


def zone_for(db_name: str, *, main_database_name: str = "") -> str:
    name = db_name.strip()
    main = _resolved_main(main_database_name)
    if main:
        for suffix, zone, _schema in CONTAINER_SPECS:
            if name == f"{main}{suffix}":
                return zone
    raise RuntimeError(f"unknown database container {db_name!r} — not in the six-container inventory")


def data_subdir_for(db_name: str) -> str:
    """Host subdirectory under DB_ROOT. One directory per container name."""
    name = db_name.strip()
    if not name:
        raise RuntimeError("database container name missing")
    return name


def db_data_mount(db_name: str, db_root: str = DB_ROOT) -> str:
    root = (db_root or "").strip() or DB_ROOT
    return (Path(root) / data_subdir_for(db_name)).as_posix()


def _normalize(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def allows_master_dns_link(name: str) -> bool:
    """MasterServer may open DockerDNS links to the six named database containers."""
    key = _normalize(name)
    named = {_normalize(item) for item in all_named_db_containers()}
    return key in named


def network_env_key_for_zone(zone: str) -> str:
    if zone == "tor":
        return "DOCKER_NETWORK_TOR_DB"
    if zone == "nontor":
        return "DOCKER_NETWORK_NONTOR_DB"
    raise RuntimeError(f"unknown zone {zone!r}")


def network_for_zone(zone: str, values: dict[str, str]) -> str:
    """Zone network from seed when present; otherwise DOCKER_NETWORK_NAME."""
    lucid = str(values.get("DOCKER_NETWORK_NAME", "")).strip()
    if zone == "tor":
        chosen = str(values.get("DOCKER_NETWORK_TOR_DB", "")).strip()
    elif zone == "nontor":
        chosen = str(values.get("DOCKER_NETWORK_NONTOR_DB", "")).strip()
    else:
        raise RuntimeError(f"unknown zone {zone!r}")
    return chosen or lucid


def dns_databases_status() -> dict[str, Any]:
    return {
        "root": ROOT,
        "db_root": DB_ROOT,
        "mongo_data_path_in_container": MONGO_DATA_PATH_IN_CONTAINER,
        "tor": list(tor_db_containers()),
        "nontor": list(nontor_db_containers()),
        "schema": list(schema_db_containers()),
        "all": list(all_named_db_containers()),
    }
