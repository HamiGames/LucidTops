"""DockerDNS and Tor/non-Tor zone mapping for LucidTops Databases containers.

Canonical inventory from documentation/fixes.txt section 11:
- Tor: LucidTops_SessionsDB, LucidTops_LedgerDB
- Non-Tor: LucidTopsUserDB, LucidTopsNodeDB, LucidTopsPaySystemsDB,
  LucidTopsBlockchain_LedgerDB

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

# Structural inventory names (documentation contracts) — not operational secrets.
TOR_DB_CONTAINERS: tuple[str, ...] = (
    "LucidTops_SessionsDB",
    "LucidTops_LedgerDB",
)

NONTOR_DB_CONTAINERS: tuple[str, ...] = (
    "LucidTopsUserDB",
    "LucidTopsNodeDB",
    "LucidTopsPaySystemsDB",
    "LucidTopsBlockchain_LedgerDB",
)

ALL_NAMED_DB_CONTAINERS: tuple[str, ...] = TOR_DB_CONTAINERS + NONTOR_DB_CONTAINERS

DB_ZONE: dict[str, str] = {
    **{name: "tor" for name in TOR_DB_CONTAINERS},
    **{name: "nontor" for name in NONTOR_DB_CONTAINERS},
}

# Host data subdirectory names under pulled databases_dir (fixes.txt external ledger path).
DB_DATA_SUBDIR: dict[str, str] = {
    "LucidTops_SessionsDB": "LucidTops_SessionsDB",
    "LucidTops_LedgerDB": "LucidTops_LedgerDB",
    "LucidTopsUserDB": "LucidTopsUserDB",
    "LucidTopsNodeDB": "LucidTopsNodeDB",
    "LucidTopsPaySystemsDB": "LucidTopsPaySystemsDB",
    "LucidTopsBlockchain_LedgerDB": "LucidTopsBlockchain_Ledger",
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


def all_named_db_containers() -> tuple[str, ...]:
    return ALL_NAMED_DB_CONTAINERS


def zone_for(db_name: str) -> str:
    zone = DB_ZONE.get(db_name.strip())
    if not zone:
        raise RuntimeError(f"unknown database container {db_name!r} — not in Tor/non-Tor inventory")
    return zone


def data_subdir_for(db_name: str) -> str:
    sub = DB_DATA_SUBDIR.get(db_name.strip())
    if not sub:
        raise RuntimeError(f"no data subdirectory mapping for {db_name!r}")
    return sub


def _normalize(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def allows_master_dns_link(name: str) -> bool:
    """MasterServer may open DockerDNS links to dns-selected named DBs."""
    key = _normalize(name)
    selected = {_normalize(item) for item in MASTER_DNS_SELECTED_DBS}
    named = {_normalize(item) for item in ALL_NAMED_DB_CONTAINERS}
    return key in selected or key in named


def network_env_key_for_zone(zone: str) -> str:
    if zone == "tor":
        return "DOCKER_NETWORK_TOR_DB"
    if zone == "nontor":
        return "DOCKER_NETWORK_NONTOR_DB"
    raise RuntimeError(f"unknown zone {zone!r}")


def dns_databases_status() -> dict[str, Any]:
    return {
        "tor": list(TOR_DB_CONTAINERS),
        "nontor": list(NONTOR_DB_CONTAINERS),
        "all": list(ALL_NAMED_DB_CONTAINERS),
        "master_dns_selected": sorted(MASTER_DNS_SELECTED_DBS),
    }
