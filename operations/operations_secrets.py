"""Load operations runtime configuration from operations.secrets (Tor + javascript frontend).


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

LUCID_TOPS_ROOT: Path
SECRETS_DIR: Path
OPERATIONS_SECRETS_FILE: Path

OPERATIONS_SECRETS_FILE_ENV = "OPERATIONS_SECRETS_FILE"

OPERATIONS_SECRETS_KEYS: tuple[str, ...] = (
    "OPERATIONS_API_PREFIX",
    "OPERATIONS_TOR_ONLY",
    "MASTER_SERVER_ONION",
    "FRONTEND_ONION",
    "NODEUSER_ONION",
    "BLOCKCHAIN_ONION",
    "BLOCKCHAIN_DOCKER_DNS_NAME",
    "BLOCKCHAIN_BIND_PORT",
    "BLOCKCHAIN_API_PREFIX",
    "BLOCKCHAIN_SECRET",
    "BLOCKCHAIN_SECRET_KEY",
    "SESSION_CONTROL_JAVASCRIPT_SOURCE",
    "USER_REGISTER_JAVASCRIPT_SOURCE",
    "LUCID_PROGRAM_DIR",
    "LUCID_USER_PROGRAM_DIR",
    "HISTORY_DIR_NAME",
    "RECORDING_FORMAT",
    "SESSION_RECORDS_COLLECTION",
    "LUCID_LEDGER_COLLECTION",
    "BLOCKCHAIN_COLLECTION",
    "CHIP_IN_COLLECTION",
    "CHIP_IN_CROSSOVER_COLLECTION",
    "NODE_SEED_FILES_COLLECTION",
    "OPERATIONS_LEDGER_READ_LIMIT",
    "OPERATIONS_QUERY_LIMIT",
    "BLOCKCHAIN_HASH_ALGORITHM",
    "SESSION_TRANSFER_DEFAULT_TARGET",
    "USER_SESSION_TRANSFER_DEFAULT_TARGET",
    "CHIP_IN_CROSSOVER_WORLDS",
    "CHIP_IN_STATUSES",
    "CHIP_IN_INITIAL_STATUS",
    "CHIP_IN_CONNECTED_STATUS",
    "CHIP_IN_WORLD_ALIASES",
    "SESSION_ID_LENGTH",
    "SESSION_KEY_MIN_LENGTH",
    "SESSION_RECORD_DEFAULT_ACTION",
    "SESSION_REQUIRED_FIELDS",
    "SESSION_STATUSES",
    "SESSION_CONTROL_SETTING_KEYS",
    "PAYMENTS_SECRETS_FILE",
    "PAYMENTS_WALLET_ADDRESS_KEYS",
    "OPERATIONS_SERVICE_NAME",
    "OPERATIONS_NETWORK_NAME",
    "FRONTEND_GUI_PREFIX",
    "LUCIDTOPS_NODE_DB_NAME",
    "LUCIDTOPS_NODE_DB_COLLECTION",
    "LUCIDTOPS_USER_DB_NAME",
    "LUCIDTOPS_USER_DB_COLLECTION",
    "LUCIDTOPS_SESSIONS_DB_NAME",
    "LUCIDTOPS_SESSIONS_COLLECTION",
    "LUCIDTOPS_LEDGER_DB_NAME",
    "EMAIL_MAC_LIMIT",
    "ID_SECRETS_DIR",
    "ACCOUNTS_DIR",
    "REGISTRATION_APPROVED_STATUS",
    "SESSION_COMPLETE_STATUS",
    "NODE_LEDGER_LAST_BLOCK_FIELD",
    "OPERATIONS_BIND_HOST",
    "OPERATIONS_BIND_PORT",
    "OPERATIONS_DOCKER_DNS_NAME",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip().upper()
            if key:
                values[key] = value.strip()
    except OSError:
        return {}
    return values


def _bind_paths_from_operation() -> None:
    """Bind path constants exclusively from env / already-loaded secrets file path."""
    global LUCID_TOPS_ROOT, SECRETS_DIR, OPERATIONS_SECRETS_FILE

    root_raw = _env("LUCID_TOPS_ROOT")
    secrets_raw = _env("SECRETS_DIR")
    operations_secrets_raw = _env(OPERATIONS_SECRETS_FILE_ENV)

    prior: dict[str, str] = {}
    if operations_secrets_raw:
        prior = parse_secrets_file(Path(operations_secrets_raw).expanduser())
    elif _env("SECRETS_DIR") and _env("OPERATIONS_SECRETS_NAME"):
        candidate = Path(_env("SECRETS_DIR")).expanduser() / _env("OPERATIONS_SECRETS_NAME")
        prior = parse_secrets_file(candidate)
        if candidate.exists():
            operations_secrets_raw = candidate.as_posix()

    if not root_raw:
        root_raw = prior.get("LUCID_TOPS_ROOT", "").strip()
    if not secrets_raw:
        secrets_raw = prior.get("SECRETS_DIR", "").strip()
    if not operations_secrets_raw:
        operations_secrets_raw = prior.get("OPERATIONS_SECRETS_FILE", "").strip()

    if not root_raw:
        raise RuntimeError("LUCID_TOPS_ROOT missing — must be set at time of operation")
    if not secrets_raw:
        raise RuntimeError("SECRETS_DIR missing — must be set at time of operation")
    if not operations_secrets_raw:
        name = (
            _env("OPERATIONS_SECRETS_NAME")
            or prior.get("OPERATIONS_SECRETS_NAME", "").strip()
            or "operations.secrets"
        )
        operations_secrets_raw = str(Path(secrets_raw).expanduser() / name)

    LUCID_TOPS_ROOT = Path(root_raw).expanduser()
    SECRETS_DIR = Path(secrets_raw).expanduser()
    OPERATIONS_SECRETS_FILE = Path(operations_secrets_raw).expanduser()


def _ensure_path_globals() -> None:
    try:
        _ = OPERATIONS_SECRETS_FILE
        if not isinstance(OPERATIONS_SECRETS_FILE, Path) or not str(OPERATIONS_SECRETS_FILE):
            _bind_paths_from_operation()
    except NameError:
        _bind_paths_from_operation()


def _init_paths_lazy() -> None:
    global LUCID_TOPS_ROOT, SECRETS_DIR, OPERATIONS_SECRETS_FILE
    try:
        _ = OPERATIONS_SECRETS_FILE
    except NameError:
        LUCID_TOPS_ROOT = Path()
        SECRETS_DIR = Path()
        OPERATIONS_SECRETS_FILE = Path()


_init_paths_lazy()


def operations_secrets_path() -> Path:
    _ensure_path_globals()
    override = _env(OPERATIONS_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return OPERATIONS_SECRETS_FILE


@lru_cache(maxsize=1)
def _load_operations_secrets_cached() -> dict[str, str]:
    """Parse operations.secrets key=value entries (comments and blank lines ignored)."""
    return parse_secrets_file(operations_secrets_path())


def load_operations_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_operations_secrets_cached.cache_clear()
    return _load_operations_secrets_cached()


def resolve_secret(key: str) -> str:
    """Resolve one config value: env var > operations.secrets (empty if missing)."""
    env_value = _env(key)
    if env_value:
        return env_value
    return load_operations_secrets().get(key.upper(), "").strip()


def require_secret(key: str, *, existing: dict[str, str] | None = None) -> str:
    """Value must exist in env or operations.secrets — created at time of operation."""
    value = _env(key)
    if not value and existing is not None:
        value = existing.get(key, "").strip() or existing.get(key.upper(), "").strip()
    if not value:
        value = load_operations_secrets().get(key.upper(), "").strip()
    if not value:
        raise RuntimeError(
            f"{key} missing — must be set in the environment or operations.secrets "
            "at time of operation"
        )
    return value


def require_secret_int(key: str, *, existing: dict[str, str] | None = None) -> int:
    raw = require_secret(key, existing=existing)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{key} must be an integer created at time of operation (got {raw!r})"
        ) from exc


def require_secret_bool(key: str, *, existing: dict[str, str] | None = None) -> bool:
    raw = require_secret(key, existing=existing)
    return raw.lower() in {"1", "true", "yes"}


def require_secret_list(key: str, *, existing: dict[str, str] | None = None) -> tuple[str, ...]:
    raw = require_secret(key, existing=existing)
    items = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not items:
        raise RuntimeError(
            f"{key} missing — must contain at least one value at time of operation"
        )
    return items


def resolve_operations_api_prefix() -> str:
    prefix = require_secret("OPERATIONS_API_PREFIX")
    return prefix if prefix.startswith("/") else f"/{prefix}"


def resolve_operations_tor_only() -> bool:
    return require_secret_bool("OPERATIONS_TOR_ONLY")


def resolve_master_server_onion() -> str:
    return require_secret("MASTER_SERVER_ONION")


def resolve_frontend_onion() -> str:
    return require_secret("FRONTEND_ONION")


def resolve_nodeuser_onion() -> str:
    return require_secret("NODEUSER_ONION")


def resolve_session_control_javascript_source() -> str:
    return require_secret("SESSION_CONTROL_JAVASCRIPT_SOURCE")


def resolve_user_register_javascript_source() -> str:
    return require_secret("USER_REGISTER_JAVASCRIPT_SOURCE")


def resolve_lucid_program_dir() -> Path:
    return Path(require_secret("LUCID_PROGRAM_DIR")).expanduser()


def resolve_lucid_user_program_dir() -> Path:
    return Path(require_secret("LUCID_USER_PROGRAM_DIR")).expanduser()


def resolve_history_dir_name() -> str:
    return require_secret("HISTORY_DIR_NAME")


def resolve_recording_format() -> str:
    return require_secret("RECORDING_FORMAT")


def resolve_session_records_collection() -> str:
    return require_secret("SESSION_RECORDS_COLLECTION")


def resolve_lucid_ledger_collection() -> str:
    return require_secret("LUCID_LEDGER_COLLECTION")


def resolve_blockchain_collection() -> str:
    return require_secret("BLOCKCHAIN_COLLECTION")


def resolve_chip_in_collection() -> str:
    return require_secret("CHIP_IN_COLLECTION")


def resolve_chip_in_crossover_collection() -> str:
    return require_secret("CHIP_IN_CROSSOVER_COLLECTION")


def resolve_node_seed_files_collection() -> str:
    return require_secret("NODE_SEED_FILES_COLLECTION")


def resolve_operations_ledger_read_limit() -> int:
    return max(1, require_secret_int("OPERATIONS_LEDGER_READ_LIMIT"))


def resolve_operations_query_limit() -> int:
    return max(1, require_secret_int("OPERATIONS_QUERY_LIMIT"))


def resolve_blockchain_hash_algorithm() -> str:
    return require_secret("BLOCKCHAIN_HASH_ALGORITHM")


def resolve_session_transfer_default_target() -> str:
    return require_secret("SESSION_TRANSFER_DEFAULT_TARGET")


def resolve_user_session_transfer_default_target() -> str:
    return require_secret("USER_SESSION_TRANSFER_DEFAULT_TARGET")


def resolve_chip_in_crossover_worlds() -> tuple[str, ...]:
    return require_secret_list("CHIP_IN_CROSSOVER_WORLDS")


def resolve_chip_in_statuses() -> frozenset[str]:
    return frozenset(require_secret_list("CHIP_IN_STATUSES"))


def resolve_chip_in_initial_status() -> str:
    status = require_secret("CHIP_IN_INITIAL_STATUS")
    allowed = resolve_chip_in_statuses()
    if status not in allowed:
        raise RuntimeError(
            f"CHIP_IN_INITIAL_STATUS={status!r} is not in CHIP_IN_STATUSES"
        )
    return status


def resolve_chip_in_connected_status() -> str:
    status = require_secret("CHIP_IN_CONNECTED_STATUS")
    allowed = resolve_chip_in_statuses()
    if status not in allowed:
        raise RuntimeError(
            f"CHIP_IN_CONNECTED_STATUS={status!r} is not in CHIP_IN_STATUSES"
        )
    return status


def resolve_chip_in_world_aliases() -> dict[str, str]:
    """Parse CHIP_IN_WORLD_ALIASES as alias:canonical pairs (comma-separated)."""
    raw = require_secret("CHIP_IN_WORLD_ALIASES")
    aliases: dict[str, str] = {}
    for item in raw.split(","):
        pair = item.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise RuntimeError(
                f"CHIP_IN_WORLD_ALIASES entry {pair!r} must be alias:canonical"
            )
        alias, _, canonical = pair.partition(":")
        alias = alias.strip().lower()
        canonical = canonical.strip().lower()
        if not alias or not canonical:
            raise RuntimeError(
                f"CHIP_IN_WORLD_ALIASES entry {pair!r} must be alias:canonical"
            )
        aliases[alias] = canonical
    if not aliases:
        raise RuntimeError(
            "CHIP_IN_WORLD_ALIASES missing — must contain alias:canonical pairs "
            "at time of operation"
        )
    return aliases


def resolve_session_id_length() -> int:
    return max(1, require_secret_int("SESSION_ID_LENGTH"))


def resolve_session_key_min_length() -> int:
    return max(1, require_secret_int("SESSION_KEY_MIN_LENGTH"))


def resolve_session_record_default_action() -> str:
    return require_secret("SESSION_RECORD_DEFAULT_ACTION")


def resolve_session_required_fields() -> tuple[str, ...]:
    return require_secret_list("SESSION_REQUIRED_FIELDS")


def resolve_session_statuses() -> frozenset[str]:
    return frozenset(require_secret_list("SESSION_STATUSES"))


def resolve_session_control_setting_keys() -> tuple[str, ...]:
    return require_secret_list("SESSION_CONTROL_SETTING_KEYS")


def resolve_payments_secrets_file() -> Path:
    return Path(require_secret("PAYMENTS_SECRETS_FILE")).expanduser()


def resolve_payments_wallet_address_keys() -> frozenset[str]:
    return frozenset(
        key.upper() for key in require_secret_list("PAYMENTS_WALLET_ADDRESS_KEYS")
    )


def resolve_lucidtops_node_db_name() -> str:
    return require_secret("LUCIDTOPS_NODE_DB_NAME")


def resolve_lucidtops_node_db_collection() -> str:
    return require_secret("LUCIDTOPS_NODE_DB_COLLECTION")


def resolve_lucidtops_user_db_name() -> str:
    return require_secret("LUCIDTOPS_USER_DB_NAME")


def resolve_lucidtops_user_db_collection() -> str:
    return require_secret("LUCIDTOPS_USER_DB_COLLECTION")


def resolve_lucidtops_sessions_db_name() -> str:
    return require_secret("LUCIDTOPS_SESSIONS_DB_NAME")


def resolve_lucidtops_sessions_collection() -> str:
    return require_secret("LUCIDTOPS_SESSIONS_COLLECTION")


def resolve_lucidtops_ledger_db_name() -> str:
    return require_secret("LUCIDTOPS_LEDGER_DB_NAME")


def resolve_email_mac_limit() -> int:
    limit = require_secret_int("EMAIL_MAC_LIMIT")
    if limit < 1:
        raise RuntimeError("EMAIL_MAC_LIMIT must be a positive integer at time of operation")
    return limit


def resolve_id_secrets_dir() -> Path:
    return Path(require_secret("ID_SECRETS_DIR")).expanduser()


def resolve_accounts_dir() -> Path:
    return Path(require_secret("ACCOUNTS_DIR")).expanduser()


def resolve_registration_approved_status() -> str:
    return require_secret("REGISTRATION_APPROVED_STATUS")


def resolve_session_complete_status() -> str:
    return require_secret("SESSION_COMPLETE_STATUS")


def resolve_node_ledger_last_block_field() -> str:
    return require_secret("NODE_LEDGER_LAST_BLOCK_FIELD")


def resolve_operations_bind_host() -> str:
    return require_secret("OPERATIONS_BIND_HOST")


def resolve_operations_bind_port() -> int:
    return require_secret_int("OPERATIONS_BIND_PORT")


def resolve_operations_docker_dns_name() -> str:
    return require_secret("OPERATIONS_DOCKER_DNS_NAME")


def resolve_blockchain_onion() -> str:
    return resolve_secret("BLOCKCHAIN_ONION")


def resolve_blockchain_docker_dns_name() -> str:
    return require_secret("BLOCKCHAIN_DOCKER_DNS_NAME")


def resolve_blockchain_bind_port() -> int:
    return require_secret_int("BLOCKCHAIN_BIND_PORT")


def resolve_blockchain_api_prefix() -> str:
    value = require_secret("BLOCKCHAIN_API_PREFIX")
    if not value.startswith("/"):
        return f"/{value}"
    return value.rstrip("/") or "/blockchain"


def resolve_blockchain_secret() -> str:
    return require_secret("BLOCKCHAIN_SECRET")


def resolve_blockchain_secret_key() -> str:
    return require_secret("BLOCKCHAIN_SECRET_KEY")


def confirm_operations_blockchain_targets() -> dict[str, Any]:
    """
    Confirm operations.secrets blockchain DockerDNS targets match Master/blockchain seed.
    Refuse serve when blockchain.secrets is present but required keys are still missing.
    When blockchain.secrets is present after genesis, refuse if MASTER_LEDGER_WRITE_ALLOWED
    is still true (ops verifies revoke only — does not perform genesis or revoke).
    """
    lucid_root_raw = resolve_secret("LUCID_TOPS_ROOT")
    lucid_root = Path(lucid_root_raw).expanduser() if lucid_root_raw else None
    blockchain_secrets = (
        (lucid_root / "blockchain" / "secrets" / "blockchain.secrets")
        if lucid_root
        else None
    )
    required = (
        "BLOCKCHAIN_DOCKER_DNS_NAME",
        "BLOCKCHAIN_BIND_PORT",
        "BLOCKCHAIN_API_PREFIX",
        "BLOCKCHAIN_SECRET",
        "BLOCKCHAIN_SECRET_KEY",
        "LUCIDTOPS_LEDGER_DB_NAME",
        "LUCID_LEDGER_COLLECTION",
    )
    missing = [key for key in required if not resolve_secret(key)]
    if missing and blockchain_secrets and blockchain_secrets.exists():
        raise RuntimeError(
            "operations blockchain DockerDNS targets incomplete after seed — missing: "
            + ", ".join(missing)
        )
    if missing:
        return {
            "confirmed": False,
            "warning": "blockchain.secrets not yet available; governance create will fail until seeded",
            "missing": missing,
            "BLOCKCHAIN_ONION": resolve_blockchain_onion() or None,
        }

    master_ledger_write_revoked: bool | None = None
    master_ledger_write_allowed_raw: str | None = None
    genesis_initialized = False
    if blockchain_secrets and blockchain_secrets.exists():
        chain_secrets = parse_secrets_file(blockchain_secrets)
        write_raw = (
            chain_secrets.get("MASTER_LEDGER_WRITE_ALLOWED")
            or _env("MASTER_LEDGER_WRITE_ALLOWED")
            or ""
        ).strip()
        if not write_raw:
            raise RuntimeError(
                "blockchain.secrets present but MASTER_LEDGER_WRITE_ALLOWED missing — "
                "ops cannot confirm Master ledger write revoke"
            )
        write_norm = write_raw.lower()
        if write_norm not in {"0", "1", "true", "false", "yes", "no"}:
            raise RuntimeError(
                f"MASTER_LEDGER_WRITE_ALLOWED must be boolean (got {write_raw!r})"
            )
        master_ledger_write_allowed_raw = write_raw
        write_allowed = write_norm in {"1", "true", "yes"}
        genesis_lock = (
            lucid_root / "Lucidtoken" / ".genesis_initialized" if lucid_root else None
        )
        genesis_initialized = bool(genesis_lock and genesis_lock.exists())
        if genesis_initialized and write_allowed:
            raise RuntimeError(
                "MASTER_LEDGER_WRITE_ALLOWED still true after genesis — "
                "refuse ops serve until blockchain Master ledger write is revoked"
            )
        master_ledger_write_revoked = not write_allowed

    result: dict[str, Any] = {
        "confirmed": True,
        "BLOCKCHAIN_DOCKER_DNS_NAME": resolve_blockchain_docker_dns_name(),
        "BLOCKCHAIN_BIND_PORT": resolve_blockchain_bind_port(),
        "BLOCKCHAIN_API_PREFIX": resolve_blockchain_api_prefix(),
        "BLOCKCHAIN_ONION": resolve_blockchain_onion() or None,
        "LUCIDTOPS_LEDGER_DB_NAME": resolve_lucidtops_ledger_db_name(),
        "LUCID_LEDGER_COLLECTION": resolve_lucid_ledger_collection(),
        "genesis_initialized": genesis_initialized,
    }
    if master_ledger_write_allowed_raw is not None:
        result["MASTER_LEDGER_WRITE_ALLOWED"] = master_ledger_write_allowed_raw
    if master_ledger_write_revoked is not None:
        result["master_ledger_write_revoked"] = master_ledger_write_revoked
    return result



def resolve_operations_service_name() -> str:
    return require_secret("OPERATIONS_SERVICE_NAME")


def resolve_operations_network_name() -> str:
    return require_secret("OPERATIONS_NETWORK_NAME")


def node_ledger_db_name_for_id(operator_id: str) -> str:
    """Build {ID}_LedgerDB from the live operator ID (fixes.txt §12.1)."""
    cleaned = str(operator_id or "").strip()
    if not cleaned:
        raise ValueError("operator_id required to resolve NodeID_LedgerDB name")
    return f"{cleaned}_LedgerDB"


def operations_secrets_status() -> dict[str, Any]:
    """Return non-sensitive operations.secrets resolution status."""
    path = operations_secrets_path()
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "operations_api_prefix": resolve_operations_api_prefix(),
        "operations_tor_only": resolve_operations_tor_only(),
        "master_server_onion_configured": bool(resolve_master_server_onion()),
        "session_control_javascript_source": resolve_session_control_javascript_source(),
        "lucid_program_dir": resolve_lucid_program_dir().as_posix(),
        "session_id_length": resolve_session_id_length(),
        "session_key_min_length": resolve_session_key_min_length(),
        "lucidtops_node_db_name": resolve_lucidtops_node_db_name(),
        "email_mac_limit": resolve_email_mac_limit(),
        "id_secrets_dir": resolve_id_secrets_dir().as_posix(),
    }


def write_secrets_file(path: Path, values: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops operations.secrets - loaded by operations/operations_secrets.py",
        f"# Generated: {utc_now()}",
        "# Tor *.onion values are inserted after container / hidden-service creation.",
        "# Javascript frontend paths reference frontend/*.js (Tor-only, not clearnet).",
        "# key=value — values created at time of operation",
        "",
    ]
    for key in OPERATIONS_SECRETS_KEYS:
        if key in values:
            lines.append(f"{key}={values[key]}")
    for key in sorted(values):
        if key not in OPERATIONS_SECRETS_KEYS:
            lines.append(f"{key}={values[key]}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def _pick(existing: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _env(key)
        if value:
            return value
        value = existing.get(key, "").strip() or existing.get(key.upper(), "").strip()
        if value:
            return value
    return ""


def _seed_prior_from_server_secrets(
    lucid_root: Path, prior: dict[str, str]
) -> dict[str, str]:
    """Reuse MasterServer-written operations.secrets under Server/Secrets when present."""
    server_path = lucid_root / "Server" / "Secrets" / "operations.secrets"
    if not server_path.exists():
        return prior
    seeded = parse_secrets_file(server_path)
    merged = dict(seeded)
    for key, value in prior.items():
        if value:
            merged[key] = value
    return merged


def _seed_blockchain_targets_from_master(
    lucid_root: Path, prior: dict[str, str]
) -> dict[str, str]:
    """Seed BLOCKCHAIN_ONION / DockerDNS / API auth from Master.secrets + blockchain.secrets."""
    merged = dict(prior)
    master_path = lucid_root / "Server" / "Secrets" / "Master.secrets"
    blockchain_path = lucid_root / "blockchain" / "secrets" / "blockchain.secrets"
    seed: dict[str, str] = {}
    if master_path.exists():
        seed.update(parse_secrets_file(master_path))
    if blockchain_path.exists():
        seed.update(parse_secrets_file(blockchain_path))

    for key in (
        "BLOCKCHAIN_ONION",
        "BLOCKCHAIN_DOCKER_DNS_NAME",
        "BLOCKCHAIN_CONTAINER_NAME",
        "BLOCKCHAIN_BIND_PORT",
        "BLOCKCHAIN_API_PREFIX",
        "BLOCKCHAIN_SECRET",
        "BLOCKCHAIN_SECRET_KEY",
        "DOCKER_NETWORK_NAME",
    ):
        if not merged.get(key, "").strip():
            value = seed.get(key, "").strip()
            if value:
                merged[key] = value

    if not merged.get("BLOCKCHAIN_DOCKER_DNS_NAME", "").strip():
        container = (
            seed.get("BLOCKCHAIN_CONTAINER_NAME", "").strip()
            or seed.get("BLOCKCHAIN_DOCKER_DNS_NAME", "").strip()
            or "lucid-blockchain"
        )
        merged["BLOCKCHAIN_DOCKER_DNS_NAME"] = container
    if not merged.get("BLOCKCHAIN_BIND_PORT", "").strip():
        merged["BLOCKCHAIN_BIND_PORT"] = (
            seed.get("BLOCKCHAIN_BIND_PORT", "").strip() or "38421"
        )
    if not merged.get("BLOCKCHAIN_API_PREFIX", "").strip():
        merged["BLOCKCHAIN_API_PREFIX"] = (
            seed.get("BLOCKCHAIN_API_PREFIX", "").strip() or "/blockchain"
        )
    return merged


def apply_pull_to_operations_configuration(
    *,
    pull: dict[str, Any] | None = None,
    prior: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve operations.secrets keys from live pull + prior/env at time of operation."""
    from ops_pull_information import pull_operations_hardware

    info = pull if pull is not None else pull_operations_hardware(bind_environ=True)
    existing = prior if prior is not None else {}

    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip or not primary_mac:
        raise RuntimeError(
            "apply_pull_to_operations_configuration failed — HARDWARE primary IP/MAC required"
        )

    lucid_root = Path(
        str(info.get("lucid_tops_root") or _env("LUCID_TOPS_ROOT") or "")
    ).expanduser()
    if not str(lucid_root):
        raise RuntimeError("LUCID_TOPS_ROOT missing — must be set at time of operation")

    secrets_dir = Path(
        str(info.get("secrets_dir") or _env("SECRETS_DIR") or "")
    ).expanduser()
    if not str(secrets_dir):
        secrets_dir = lucid_root / "operations" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    existing = _seed_prior_from_server_secrets(lucid_root, existing)
    existing = _seed_blockchain_targets_from_master(lucid_root, existing)

    bind_host = (
        _pick(existing, "OPERATIONS_BIND_HOST")
        or str(info.get("operations_bind_host") or primary_ip)
    )
    bind_port = (
        _pick(existing, "OPERATIONS_BIND_PORT")
        or str(info.get("operations_bind_port") or "")
    )
    if not bind_port:
        raise RuntimeError(
            "OPERATIONS_BIND_PORT missing — must be pulled/allocated at time of operation"
        )

    docker_dns = (
        _pick(existing, "OPERATIONS_DOCKER_DNS_NAME")
        or str(info.get("operations_docker_dns_name") or primary_ip)
    )
    network_name = (
        _pick(existing, "OPERATIONS_NETWORK_NAME", "DOCKER_NETWORK_NAME")
        or str(info.get("docker_network_name") or "")
    )
    if not network_name:
        machine_id = str(info.get("machine_id") or "").strip()
        hostname = str(info.get("hostname") or "").strip()
        if machine_id:
            network_name = f"lucid-{machine_id[:12].lower()}"
        elif hostname:
            network_name = f"lucid-{hostname.lower()}"
        else:
            raise RuntimeError(
                "OPERATIONS_NETWORK_NAME missing — must be pulled from Docker or machine_id "
                "at time of operation"
            )

    service_name = _pick(existing, "OPERATIONS_SERVICE_NAME") or str(
        (info.get("operations_container") or {}).get("name")
        or _env("OPERATIONS_CONTAINER_NAME")
        or "operations"
    )

    id_secrets_dir = (
        _pick(existing, "ID_SECRETS_DIR")
        or (secrets_dir / "id").as_posix()
    )
    accounts_dir = (
        _pick(existing, "ACCOUNTS_DIR")
        or (lucid_root / "accounts").as_posix()
    )
    payments_secrets = (
        _pick(existing, "PAYMENTS_SECRETS_FILE")
        or (lucid_root / "Server" / "Secrets" / "payments.secrets").as_posix()
    )
    program_dir = (
        _pick(existing, "LUCID_PROGRAM_DIR")
        or (lucid_root / "program").as_posix()
    )
    user_program_dir = (
        _pick(existing, "LUCID_USER_PROGRAM_DIR")
        or (lucid_root / "user_program").as_posix()
    )

    # Tor onions: prefer env/prior/Server seed; empty until Master/Proxy patch is valid.
    master_onion = _pick(existing, "MASTER_SERVER_ONION")
    frontend_onion = _pick(existing, "FRONTEND_ONION")
    nodeuser_onion = _pick(existing, "NODEUSER_ONION")
    blockchain_onion = _pick(existing, "BLOCKCHAIN_ONION")

    resolved: dict[str, str] = {
        "GENERATED_AT": utc_now(),
        "LUCID_TOPS_ROOT": lucid_root.as_posix(),
        "SECRETS_DIR": secrets_dir.as_posix(),
        "OPERATIONS_SECRETS_NAME": _pick(existing, "OPERATIONS_SECRETS_NAME")
        or "operations.secrets",
        "OPERATIONS_API_PREFIX": _pick(existing, "OPERATIONS_API_PREFIX") or "/operations",
        "OPERATIONS_TOR_ONLY": _pick(existing, "OPERATIONS_TOR_ONLY")
        or ("true" if info.get("tor_available") else "true"),
        "MASTER_SERVER_ONION": master_onion,
        "FRONTEND_ONION": frontend_onion,
        "NODEUSER_ONION": nodeuser_onion,
        "BLOCKCHAIN_ONION": blockchain_onion,
        "BLOCKCHAIN_DOCKER_DNS_NAME": _pick(existing, "BLOCKCHAIN_DOCKER_DNS_NAME")
        or "lucid-blockchain",
        "BLOCKCHAIN_BIND_PORT": _pick(existing, "BLOCKCHAIN_BIND_PORT") or "38421",
        "BLOCKCHAIN_API_PREFIX": _pick(existing, "BLOCKCHAIN_API_PREFIX") or "/blockchain",
        "BLOCKCHAIN_SECRET": _pick(existing, "BLOCKCHAIN_SECRET"),
        "BLOCKCHAIN_SECRET_KEY": _pick(existing, "BLOCKCHAIN_SECRET_KEY"),
        "SESSION_CONTROL_JAVASCRIPT_SOURCE": _pick(
            existing, "SESSION_CONTROL_JAVASCRIPT_SOURCE"
        )
        or "frontend/webpage/settings.js",
        "USER_REGISTER_JAVASCRIPT_SOURCE": _pick(
            existing, "USER_REGISTER_JAVASCRIPT_SOURCE"
        )
        or "frontend/webpage/register.js",
        "LUCID_PROGRAM_DIR": program_dir,
        "LUCID_USER_PROGRAM_DIR": user_program_dir,
        "HISTORY_DIR_NAME": _pick(existing, "HISTORY_DIR_NAME") or "history",
        "RECORDING_FORMAT": _pick(existing, "RECORDING_FORMAT") or "webm",
        "SESSION_RECORDS_COLLECTION": _pick(existing, "SESSION_RECORDS_COLLECTION")
        or "session_records",
        "LUCID_LEDGER_COLLECTION": _pick(existing, "LUCID_LEDGER_COLLECTION")
        or "BlockID",
        "BLOCKCHAIN_COLLECTION": _pick(existing, "BLOCKCHAIN_COLLECTION") or "Blockchain",
        "CHIP_IN_COLLECTION": _pick(existing, "CHIP_IN_COLLECTION") or "chip_in",
        "CHIP_IN_CROSSOVER_COLLECTION": _pick(existing, "CHIP_IN_CROSSOVER_COLLECTION")
        or "chip_in_crossover",
        "NODE_SEED_FILES_COLLECTION": _pick(existing, "NODE_SEED_FILES_COLLECTION")
        or "node_seed_files",
        "OPERATIONS_LEDGER_READ_LIMIT": _pick(existing, "OPERATIONS_LEDGER_READ_LIMIT")
        or "100",
        "OPERATIONS_QUERY_LIMIT": _pick(existing, "OPERATIONS_QUERY_LIMIT") or "100",
        "BLOCKCHAIN_HASH_ALGORITHM": _pick(existing, "BLOCKCHAIN_HASH_ALGORITHM")
        or "sha512",
        "SESSION_TRANSFER_DEFAULT_TARGET": _pick(
            existing, "SESSION_TRANSFER_DEFAULT_TARGET"
        )
        or "operations",
        "USER_SESSION_TRANSFER_DEFAULT_TARGET": _pick(
            existing, "USER_SESSION_TRANSFER_DEFAULT_TARGET"
        )
        or "operations",
        "CHIP_IN_CROSSOVER_WORLDS": _pick(existing, "CHIP_IN_CROSSOVER_WORLDS")
        or "lucid,tron,xrp",
        "CHIP_IN_STATUSES": _pick(existing, "CHIP_IN_STATUSES")
        or "pending,connected,complete",
        "CHIP_IN_INITIAL_STATUS": _pick(existing, "CHIP_IN_INITIAL_STATUS") or "pending",
        "CHIP_IN_CONNECTED_STATUS": _pick(existing, "CHIP_IN_CONNECTED_STATUS")
        or "connected",
        "CHIP_IN_WORLD_ALIASES": _pick(existing, "CHIP_IN_WORLD_ALIASES")
        or "lucid:LUCID,tron:TRON,xrp:XRP",
        "SESSION_ID_LENGTH": _pick(existing, "SESSION_ID_LENGTH") or "10",
        "SESSION_KEY_MIN_LENGTH": _pick(existing, "SESSION_KEY_MIN_LENGTH")
        or str(max(16, int(info.get("cpu_count") or 1) * 8)),
        "SESSION_RECORD_DEFAULT_ACTION": _pick(existing, "SESSION_RECORD_DEFAULT_ACTION")
        or "start",
        "SESSION_REQUIRED_FIELDS": _pick(existing, "SESSION_REQUIRED_FIELDS")
        or "sessionID,UserID,TokenID",
        "SESSION_STATUSES": _pick(existing, "SESSION_STATUSES")
        or "pending,active,complete,ended,compressed",
        "SESSION_CONTROL_SETTING_KEYS": _pick(existing, "SESSION_CONTROL_SETTING_KEYS")
        or "audio,video,input,clipboard",
        "PAYMENTS_SECRETS_FILE": payments_secrets,
        "PAYMENTS_WALLET_ADDRESS_KEYS": _pick(existing, "PAYMENTS_WALLET_ADDRESS_KEYS")
        or "WALLET_ADDRESS,TRON_WALLET,XRP_WALLET",
        "OPERATIONS_SERVICE_NAME": service_name,
        "OPERATIONS_NETWORK_NAME": network_name,
        "FRONTEND_GUI_PREFIX": _pick(existing, "FRONTEND_GUI_PREFIX") or "/gui",
        "LUCIDTOPS_NODE_DB_NAME": _pick(existing, "LUCIDTOPS_NODE_DB_NAME")
        or "LucidTopsNodeDB",
        "LUCIDTOPS_NODE_DB_COLLECTION": _pick(existing, "LUCIDTOPS_NODE_DB_COLLECTION")
        or "nodes",
        "LUCIDTOPS_USER_DB_NAME": _pick(existing, "LUCIDTOPS_USER_DB_NAME")
        or "LucidTopsUserDB",
        "LUCIDTOPS_USER_DB_COLLECTION": _pick(existing, "LUCIDTOPS_USER_DB_COLLECTION")
        or "users",
        "LUCIDTOPS_SESSIONS_DB_NAME": _pick(existing, "LUCIDTOPS_SESSIONS_DB_NAME")
        or "LucidTops_SessionsDB",
        "LUCIDTOPS_SESSIONS_COLLECTION": _pick(existing, "LUCIDTOPS_SESSIONS_COLLECTION")
        or "session_records",
        "LUCIDTOPS_LEDGER_DB_NAME": _pick(existing, "LUCIDTOPS_LEDGER_DB_NAME")
        or "LucidTops_LedgerDB",
        "EMAIL_MAC_LIMIT": _pick(existing, "EMAIL_MAC_LIMIT") or "3",
        "ID_SECRETS_DIR": id_secrets_dir,
        "ACCOUNTS_DIR": accounts_dir,
        "REGISTRATION_APPROVED_STATUS": _pick(existing, "REGISTRATION_APPROVED_STATUS")
        or "approved",
        "SESSION_COMPLETE_STATUS": _pick(existing, "SESSION_COMPLETE_STATUS")
        or "complete",
        "NODE_LEDGER_LAST_BLOCK_FIELD": _pick(existing, "NODE_LEDGER_LAST_BLOCK_FIELD")
        or "LastBlockID",
        "OPERATIONS_BIND_HOST": bind_host,
        "OPERATIONS_BIND_PORT": bind_port,
        "OPERATIONS_DOCKER_DNS_NAME": docker_dns,
        "DOCKER_NETWORK_NAME": network_name,
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "HOST_PRIMARY_IP": primary_ip,
        "HOST_PRIMARY_MAC": primary_mac,
    }

    secrets_file = Path(
        str(
            info.get("operations_secrets_file")
            or _env("OPERATIONS_SECRETS_FILE")
            or (secrets_dir / resolved["OPERATIONS_SECRETS_NAME"]).as_posix()
        )
    ).expanduser()
    resolved["OPERATIONS_SECRETS_FILE"] = secrets_file.as_posix()

    # Preserve any extra prior keys (onion patches, operator fields) not listed above.
    for key, value in existing.items():
        if key not in resolved and value:
            resolved[key] = value

    return resolved


def build_operations_secret_values(
    *, existing: dict[str, str] | None = None
) -> dict[str, str]:
    """Collect operations.secrets values from pull / env / prior file at operation time."""
    return apply_pull_to_operations_configuration(prior=existing)


def write_operations_secrets(
    *,
    secrets_dir: Path | None = None,
    force: bool = False,
    pull: dict[str, Any] | None = None,
) -> Path:
    """Write operations.secrets on the host from operation-time pull (sessions pattern)."""
    from ops_pull_information import pull_operations_hardware

    info = pull if pull is not None else pull_operations_hardware(bind_environ=True)
    name = (
        _env("OPERATIONS_SECRETS_NAME")
        or str(info.get("operations_secrets_name") or "").strip()
        or "operations.secrets"
    )
    if secrets_dir is not None:
        path = Path(secrets_dir).expanduser() / name
    else:
        override = _env("OPERATIONS_SECRETS_FILE") or str(
            info.get("operations_secrets_file") or ""
        ).strip()
        if override:
            path = Path(override).expanduser()
        else:
            target = Path(
                str(info.get("secrets_dir") or _env("SECRETS_DIR") or "")
            ).expanduser()
            if not str(target):
                raise RuntimeError(
                    "SECRETS_DIR missing — must be set at time of operation"
                )
            path = target / name

    path.parent.mkdir(parents=True, exist_ok=True)
    prior = parse_secrets_file(path) if path.exists() else {}
    resolved = apply_pull_to_operations_configuration(pull=info, prior=prior)

    if path.exists() and not force:
        existing_keys = set(prior.keys())
        needs_fill = any(
            (k not in existing_keys) or (not prior.get(k)) for k in resolved if resolved[k]
        )
        if not needs_fill:
            os.environ["OPERATIONS_SECRETS_FILE"] = path.as_posix()
            os.environ["SECRETS_DIR"] = path.parent.as_posix()
            for key in (
                "OPERATIONS_BIND_HOST",
                "OPERATIONS_BIND_PORT",
                "OPERATIONS_DOCKER_DNS_NAME",
                "OPERATIONS_NETWORK_NAME",
            ):
                if resolved.get(key) and not _env(key):
                    os.environ[key] = resolved[key]
            return path

    write_secrets_file(path, resolved)
    os.environ["OPERATIONS_SECRETS_FILE"] = path.as_posix()
    os.environ["SECRETS_DIR"] = path.parent.as_posix()
    os.environ["OPERATIONS_SECRETS_NAME"] = name
    for key, value in resolved.items():
        if value and not _env(key):
            os.environ[key] = value
    load_operations_secrets(reload=True)
    _bind_paths_from_operation()
    return path


def write_operations_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write operations.secrets from env / pull values created at time of operation."""
    if not populate_from_env:
        raise RuntimeError(
            "operations.secrets values must be created at time of operation "
            "(populate_from_env cannot be false)"
        )
    if secrets_dir is not None and not _env("OPERATIONS_SECRETS_NAME"):
        os.environ["OPERATIONS_SECRETS_NAME"] = "operations.secrets"
    return write_operations_secrets(secrets_dir=secrets_dir, force=force)
