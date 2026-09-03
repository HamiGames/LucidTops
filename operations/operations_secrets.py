"""Load operations runtime configuration from operations.secrets (Tor + javascript frontend)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LUCID_TOPS_ROOT = Path("/mnt/myssd/LucidTops")
LUCID_TOPS_ROOT = Path(os.environ.get("LUCID_TOPS_ROOT", DEFAULT_LUCID_TOPS_ROOT)).expanduser()
SECRETS_DIR = Path(os.environ.get("SECRETS_DIR", LUCID_TOPS_ROOT / "secrets"))

DEFAULT_OPERATIONS_SECRETS_NAME = "operations.secrets"
OPERATIONS_SECRETS_FILE_ENV = "OPERATIONS_SECRETS_FILE"

DEFAULT_CHIP_IN_CROSSOVER_WORLDS = (
    "crypto_wallet,blockchain,nft,game,social_media,news,education,health,finance,"
    "real_estate,travel,food_and_drink,art,music,video,photography,writing,"
    "programming,design,marketing,sales,customer_service"
)

OPERATIONS_SECRETS_TEMPLATE_KEYS: tuple[tuple[str, str], ...] = (
    ("OPERATIONS_API_PREFIX", "/api/v1"),
    ("OPERATIONS_TOR_ONLY", "true"),
    ("MASTER_SERVER_ONION", ""),
    ("FRONTEND_ONION", ""),
    ("NODEUSER_ONION", ""),
    ("SESSION_CONTROL_JAVASCRIPT_SOURCE", "frontend/settings.js"),
    ("USER_REGISTER_JAVASCRIPT_SOURCE", "frontend/register.js"),
    ("LUCID_PROGRAM_DIR", "/mnt/myssd/LucidTops"),
    ("LUCID_USER_PROGRAM_DIR", ""),
    ("HISTORY_DIR_NAME", "History"),
    ("RECORDING_FORMAT", "mp4"),
    ("SESSION_RECORDS_COLLECTION", "session_records"),
    ("LUCID_LEDGER_COLLECTION", "ledger_records"),
    ("BLOCKCHAIN_COLLECTION", "blockchain_blocks"),
    ("CHIP_IN_COLLECTION", "chip_in_records"),
    ("CHIP_IN_CROSSOVER_COLLECTION", "chip_in_crossovers"),
    ("NODE_SEED_FILES_COLLECTION", "node_seed_files"),
    ("OPERATIONS_LEDGER_READ_LIMIT", "100"),
    ("OPERATIONS_QUERY_LIMIT", "50"),
    ("BLOCKCHAIN_HASH_ALGORITHM", "sha512"),
    ("SESSION_TRANSFER_DEFAULT_TARGET", "history_ledger"),
    ("USER_SESSION_TRANSFER_DEFAULT_TARGET", "user_history_ledger"),
    ("CHIP_IN_CROSSOVER_WORLDS", DEFAULT_CHIP_IN_CROSSOVER_WORLDS),
    ("CHIP_IN_STATUSES", "draft,active,connected,archived"),
    ("SESSION_ID_LENGTH", "10"),
    ("SESSION_KEY_MIN_LENGTH", "16"),
    ("PAYMENTS_SECRETS_FILE", ""),
)


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def operations_secrets_path() -> Path:
    override = os.environ.get(OPERATIONS_SECRETS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return SECRETS_DIR / DEFAULT_OPERATIONS_SECRETS_NAME


@lru_cache(maxsize=1)
def _load_operations_secrets_cached() -> dict[str, str]:
    """Parse operations.secrets key=value entries (comments and blank lines ignored)."""
    values: dict[str, str] = {}
    path = operations_secrets_path()
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


def load_operations_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_operations_secrets_cached.cache_clear()
    return _load_operations_secrets_cached()


def resolve_secret(key: str, *, default: str = "") -> str:
    """Resolve one config value: env var > operations.secrets > default."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    file_value = load_operations_secrets().get(key.upper(), "").strip()
    if file_value:
        return file_value
    return default


def resolve_secret_int(key: str, *, default: int) -> int:
    raw = resolve_secret(key, default=str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_secret_bool(key: str, *, default: bool) -> bool:
    raw = resolve_secret(key, default="true" if default else "false")
    return raw.lower() in {"1", "true", "yes"}


def resolve_secret_list(key: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = resolve_secret(key, default="")
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def resolve_operations_api_prefix() -> str:
    prefix = resolve_secret("OPERATIONS_API_PREFIX", default="/api/v1")
    return prefix if prefix.startswith("/") else f"/{prefix}"


def resolve_operations_tor_only() -> bool:
    return resolve_secret_bool("OPERATIONS_TOR_ONLY", default=True)


def resolve_master_server_onion() -> str:
    return resolve_secret("MASTER_SERVER_ONION", default="")


def resolve_frontend_onion() -> str:
    return resolve_secret("FRONTEND_ONION", default="")


def resolve_nodeuser_onion() -> str:
    return resolve_secret("NODEUSER_ONION", default="")


def resolve_session_control_javascript_source() -> str:
    return resolve_secret("SESSION_CONTROL_JAVASCRIPT_SOURCE", default="frontend/settings.js")


def resolve_user_register_javascript_source() -> str:
    return resolve_secret("USER_REGISTER_JAVASCRIPT_SOURCE", default="frontend/register.js")


def resolve_lucid_program_dir() -> Path:
    return Path(resolve_secret("LUCID_PROGRAM_DIR", default="/mnt/myssd/LucidTops")).expanduser()


def resolve_lucid_user_program_dir() -> Path:
    override = resolve_secret("LUCID_USER_PROGRAM_DIR", default="")
    if override:
        return Path(override).expanduser()
    return resolve_lucid_program_dir()


def resolve_history_dir_name() -> str:
    return resolve_secret("HISTORY_DIR_NAME", default="History")


def resolve_recording_format() -> str:
    return resolve_secret("RECORDING_FORMAT", default="mp4")


def resolve_session_records_collection() -> str:
    return resolve_secret("SESSION_RECORDS_COLLECTION", default="session_records")


def resolve_lucid_ledger_collection() -> str:
    return resolve_secret("LUCID_LEDGER_COLLECTION", default="ledger_records")


def resolve_blockchain_collection() -> str:
    return resolve_secret("BLOCKCHAIN_COLLECTION", default="blockchain_blocks")


def resolve_chip_in_collection() -> str:
    return resolve_secret("CHIP_IN_COLLECTION", default="chip_in_records")


def resolve_chip_in_crossover_collection() -> str:
    return resolve_secret("CHIP_IN_CROSSOVER_COLLECTION", default="chip_in_crossovers")


def resolve_node_seed_files_collection() -> str:
    return resolve_secret("NODE_SEED_FILES_COLLECTION", default="node_seed_files")


def resolve_operations_ledger_read_limit() -> int:
    return max(1, resolve_secret_int("OPERATIONS_LEDGER_READ_LIMIT", default=100))


def resolve_operations_query_limit() -> int:
    return max(1, resolve_secret_int("OPERATIONS_QUERY_LIMIT", default=50))


def resolve_blockchain_hash_algorithm() -> str:
    return resolve_secret("BLOCKCHAIN_HASH_ALGORITHM", default="sha512")


def resolve_session_transfer_default_target() -> str:
    return resolve_secret("SESSION_TRANSFER_DEFAULT_TARGET", default="history_ledger")


def resolve_user_session_transfer_default_target() -> str:
    return resolve_secret(
        "USER_SESSION_TRANSFER_DEFAULT_TARGET",
        default="user_history_ledger",
    )


def resolve_chip_in_crossover_worlds() -> tuple[str, ...]:
    return resolve_secret_list(
        "CHIP_IN_CROSSOVER_WORLDS",
        default=tuple(DEFAULT_CHIP_IN_CROSSOVER_WORLDS.split(",")),
    )


def resolve_chip_in_statuses() -> frozenset[str]:
    return frozenset(
        resolve_secret_list("CHIP_IN_STATUSES", default=("draft", "active", "connected", "archived"))
    )


def resolve_session_id_length() -> int:
    return max(1, resolve_secret_int("SESSION_ID_LENGTH", default=10))


def resolve_session_key_min_length() -> int:
    return max(1, resolve_secret_int("SESSION_KEY_MIN_LENGTH", default=16))


def resolve_payments_secrets_file() -> Path:
    override = resolve_secret("PAYMENTS_SECRETS_FILE", default="")
    if override:
        return Path(override).expanduser()
    env_override = os.environ.get("PAYMENTS_SECRETS_FILE", "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return SECRETS_DIR / "payments.secrets"


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
    }


def write_operations_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write operations.secrets template for later build-stage population."""
    target_dir = secrets_dir or SECRETS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / DEFAULT_OPERATIONS_SECRETS_NAME
    if path.exists() and not force:
        return path

    resolved: dict[str, str] = {}
    for key, default in OPERATIONS_SECRETS_TEMPLATE_KEYS:
        if populate_from_env:
            value = resolve_secret(key, default=default)
        else:
            value = default
        resolved[key] = value

    lines = [
        "# LucidTops operations.secrets - loaded by operations/operations_secrets.py",
        f"# Generated: {utc_now()}",
        "# Tor *.onion values are inserted after container / hidden-service creation.",
        "# Javascript frontend paths reference frontend/*.js (Tor-only, not clearnet).",
        "",
    ]
    for key, default in OPERATIONS_SECRETS_TEMPLATE_KEYS:
        value = resolved.get(key, default)
        lines.append(f"{key}={value}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    load_operations_secrets(reload=True)
    return path
