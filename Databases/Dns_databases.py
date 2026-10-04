"""DockerDNS mapping for the six LucidTops Databases containers.

Canonical inventory from documentation/Databases.txt:
- LucidTops_LedgerDB
- LucidTops_SessionsDB
- LucidTopsUserDB
- LucidTopsNodeDB
- LucidTopsPaySystemsDB
- sixth container name = MONGODB_MAIN_DATABASE_NAME (Master.secrets or proxy.secrets)

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

# Fixed five containers. The sixth name is MONGODB_MAIN_DATABASE_NAME.
TOR_DB_CONTAINERS: tuple[str, ...] = (
    "LucidTops_SessionsDB",
    "LucidTops_LedgerDB",
)

NONTOR_DB_CONTAINERS: tuple[str, ...] = (
    "LucidTopsUserDB",
    "LucidTopsNodeDB",
    "LucidTopsPaySystemsDB",
)

FIXED_DB_CONTAINERS: tuple[str, ...] = TOR_DB_CONTAINERS + NONTOR_DB_CONTAINERS

# Schemas in Databases.txt apply to these five. The sixth container is ping-only.
SCHEMA_DB_CONTAINERS: tuple[str, ...] = FIXED_DB_CONTAINERS

DB_ZONE: dict[str, str] = {
    **{name: "tor" for name in TOR_DB_CONTAINERS},
    **{name: "nontor" for name in NONTOR_DB_CONTAINERS},
}

# DNS-selected names MasterServer may link (aligns with backend/Dns_selection.py comments).
MASTER_DNS_SELECTED_DBS: frozenset[str] = frozenset(
    {
        "LucidTops_SessionsDB",
        "LucidTopsNodeDB",
        "LucidTopsUserDB",
        "LucidTopsLedgerDB",
        "LucidTops_LedgerDB",
        "LucidTopsPaySystemsDB",
    }
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
    """Sixth container name. Empty or a collision with the fixed five is refused."""
    value = (name or "").strip()
    if not value:
        raise RuntimeError(
            "MONGODB_MAIN_DATABASE_NAME missing — must be set in Master.secrets or proxy.secrets"
        )
    if value in FIXED_DB_CONTAINERS:
        raise RuntimeError(
            "MONGODB_MAIN_DATABASE_NAME "
            f"{value!r} collides with a fixed database container"
        )
    return value


def resolve_main_database_name(candidate: str = "") -> str:
    value = (candidate or "").strip() or _env("MONGODB_MAIN_DATABASE_NAME")
    if not value:
        value = _console_secret_value("MONGODB_MAIN_DATABASE_NAME")
    return require_main_database_name(value)


def named_db_containers(main_database_name: str) -> tuple[str, ...]:
    """Five fixed containers plus the container named by MONGODB_MAIN_DATABASE_NAME."""
    main = require_main_database_name(main_database_name)
    return FIXED_DB_CONTAINERS + (main,)


def all_named_db_containers() -> tuple[str, ...]:
    """Six containers when the main name is known; otherwise the fixed five."""
    candidate = _env("MONGODB_MAIN_DATABASE_NAME") or _console_secret_value(
        "MONGODB_MAIN_DATABASE_NAME"
    )
    if not candidate:
        return FIXED_DB_CONTAINERS
    try:
        return named_db_containers(candidate)
    except RuntimeError:
        return FIXED_DB_CONTAINERS


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


def tor_db_containers() -> tuple[str, ...]:
    return TOR_DB_CONTAINERS


def nontor_db_containers() -> tuple[str, ...]:
    return NONTOR_DB_CONTAINERS


def schema_db_containers() -> tuple[str, ...]:
    return SCHEMA_DB_CONTAINERS


def zone_for(db_name: str, *, main_database_name: str = "") -> str:
    name = db_name.strip()
    zone = DB_ZONE.get(name)
    if zone:
        return zone
    main = (main_database_name or "").strip() or _env("MONGODB_MAIN_DATABASE_NAME")
    if not main:
        main = _console_secret_value("MONGODB_MAIN_DATABASE_NAME")
    if main and name == main and name not in FIXED_DB_CONTAINERS:
        return "nontor"
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
    """MasterServer may open DockerDNS links to the named database containers."""
    key = _normalize(name)
    selected = {_normalize(item) for item in MASTER_DNS_SELECTED_DBS}
    named = {_normalize(item) for item in all_named_db_containers()}
    return key in selected or key in named


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
        "tor": list(TOR_DB_CONTAINERS),
        "nontor": list(NONTOR_DB_CONTAINERS),
        "fixed": list(FIXED_DB_CONTAINERS),
        "all": list(all_named_db_containers()),
        "master_dns_selected": sorted(MASTER_DNS_SELECTED_DBS),
    }
