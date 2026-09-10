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
        name = _env("OPERATIONS_SECRETS_NAME") or prior.get("OPERATIONS_SECRETS_NAME", "").strip()
        if not name:
            raise RuntimeError(
                "OPERATIONS_SECRETS_FILE or OPERATIONS_SECRETS_NAME must be set at time of operation"
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


def build_operations_secret_values(
    *, existing: dict[str, str] | None = None
) -> dict[str, str]:
    """Collect operations.secrets values exclusively from env / prior file at operation time."""
    _bind_paths_from_operation()
    prior = existing if existing is not None else parse_secrets_file(OPERATIONS_SECRETS_FILE)
    values: dict[str, str] = {
        "GENERATED_AT": utc_now(),
        "LUCID_TOPS_ROOT": LUCID_TOPS_ROOT.as_posix(),
        "SECRETS_DIR": SECRETS_DIR.as_posix(),
        "OPERATIONS_SECRETS_FILE": OPERATIONS_SECRETS_FILE.as_posix(),
    }
    name = _env("OPERATIONS_SECRETS_NAME") or prior.get("OPERATIONS_SECRETS_NAME", "").strip()
    if name:
        values["OPERATIONS_SECRETS_NAME"] = name

    for key in OPERATIONS_SECRETS_KEYS:
        values[key] = require_secret(key, existing=prior)
    return values


def write_operations_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write operations.secrets from env / existing values created at time of operation."""
    _bind_paths_from_operation()
    if secrets_dir is not None:
        target_dir = secrets_dir
        name = _env("OPERATIONS_SECRETS_NAME")
        if not name:
            raise RuntimeError(
                "OPERATIONS_SECRETS_NAME missing — must be set at time of operation"
            )
        path = target_dir / name
    else:
        path = OPERATIONS_SECRETS_FILE
        target_dir = path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path

    if not populate_from_env:
        raise RuntimeError(
            "operations.secrets values must be created at time of operation "
            "(populate_from_env cannot be false)"
        )

    existing = parse_secrets_file(path) if path.exists() else {}
    values = build_operations_secret_values(existing=existing)
    write_secrets_file(path, values)
    load_operations_secrets(reload=True)
    return path
