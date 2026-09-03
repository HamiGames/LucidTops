"""Load blockchain runtime configuration from blockchain.secrets (build-stage injection)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LUCID_TOPS_ROOT = Path("/mnt/myssd/LucidTops")
LUCID_TOPS_ROOT = Path(os.environ.get("LUCID_TOPS_ROOT", DEFAULT_LUCID_TOPS_ROOT)).expanduser()
SECRETS_DIR = Path(os.environ.get("SECRETS_DIR", LUCID_TOPS_ROOT / "secrets"))

DEFAULT_BLOCKCHAIN_SECRETS_NAME = "blockchain.secrets"
BLOCKCHAIN_SECRETS_FILE_ENV = "BLOCKCHAIN_SECRETS_FILE"

BLOCKCHAIN_SECRETS_TEMPLATE_KEYS: tuple[tuple[str, str], ...] = (
    ("GENESIS_CREATOR_ID", ""),
    ("BLOCKCHAIN_ONION", ""),
    ("MASTER_SERVER_ONION", ""),
    ("NODEUSER_ONION", ""),
    ("ADMIN_ONION", ""),
    ("BLOCKCHAIN_SECRET", ""),
    ("BLOCKCHAIN_SECRET_KEY", ""),
    ("MONGODB_HOST", "lucid-mongodb"),
    ("MONGODB_PORT", "27017"),
    ("MASTER_SERVER_INTERNAL_HOST", "lucid-server-default"),
    ("MASTER_SERVER_INTERNAL_PORT", "8080"),
    ("BLOCKCHAIN_CONTAINER_NAME", ""),
    ("IMAGE_GENERATOR_URL", ""),
    ("UNIVERSE_SEARCH_URL", ""),
    ("IMAGE_GENERATOR_ENABLED", "false"),
    ("UNIVERSE_SEARCH_ENABLED", "true"),
    ("LEDGER_DISTRIBUTION_SYNC_SECONDS", "300"),
    ("BLOCKCHAIN_API_PREFIX", "/api/v1"),
)


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def blockchain_secrets_path() -> Path:
    override = os.environ.get(BLOCKCHAIN_SECRETS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return SECRETS_DIR / DEFAULT_BLOCKCHAIN_SECRETS_NAME


@lru_cache(maxsize=1)
def _load_blockchain_secrets_cached() -> dict[str, str]:
    """Parse blockchain.secrets key=value entries (comments and blank lines ignored)."""
    values: dict[str, str] = {}
    path = blockchain_secrets_path()
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


def load_blockchain_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_blockchain_secrets_cached.cache_clear()
    return _load_blockchain_secrets_cached()


def resolve_secret(key: str, *, default: str = "") -> str:
    """Resolve one config value: env var > blockchain.secrets > default."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    file_value = load_blockchain_secrets().get(key.upper(), "").strip()
    if file_value:
        return file_value
    return default


def resolve_genesis_creator_id() -> str:
    return resolve_secret("GENESIS_CREATOR_ID", default="Pickme-LucidTops")


def resolve_blockchain_onion() -> str:
    return resolve_secret("BLOCKCHAIN_ONION", default="")


def resolve_master_server_onion() -> str:
    return resolve_secret("MASTER_SERVER_ONION", default="")


def resolve_nodeuser_onion() -> str:
    return resolve_secret("NODEUSER_ONION", default="")


def resolve_admin_onion() -> str:
    return resolve_secret("ADMIN_ONION", default="")


def resolve_blockchain_secret() -> str:
    return resolve_secret("BLOCKCHAIN_SECRET", default="")


def resolve_blockchain_secret_key() -> str:
    return resolve_secret("BLOCKCHAIN_SECRET_KEY", default="")


def resolve_mongodb_host() -> str:
    return resolve_secret("MONGODB_HOST", default="lucid-mongodb")


def resolve_mongodb_port() -> int:
    raw = resolve_secret("MONGODB_PORT", default="27017")
    try:
        return int(raw)
    except ValueError:
        return 27017


def resolve_master_server_internal_host() -> str:
    return resolve_secret("MASTER_SERVER_INTERNAL_HOST", default="lucid-server-default")


def resolve_master_server_internal_port() -> int:
    raw = resolve_secret("MASTER_SERVER_INTERNAL_PORT", default="8080")
    try:
        return int(raw)
    except ValueError:
        return 8080


def resolve_blockchain_container_name() -> str:
    return resolve_secret("BLOCKCHAIN_CONTAINER_NAME", default="")


def resolve_image_generator_url() -> str:
    return resolve_secret("IMAGE_GENERATOR_URL", default="")


def resolve_universe_search_url() -> str:
    return resolve_secret("UNIVERSE_SEARCH_URL", default="")


def resolve_image_generator_enabled() -> bool:
    return resolve_secret("IMAGE_GENERATOR_ENABLED", default="false").lower() in {
        "1",
        "true",
        "yes",
    }


def resolve_universe_search_enabled() -> bool:
    return resolve_secret("UNIVERSE_SEARCH_ENABLED", default="true").lower() in {
        "1",
        "true",
        "yes",
    }


def resolve_ledger_distribution_sync_seconds() -> int:
    raw = resolve_secret("LEDGER_DISTRIBUTION_SYNC_SECONDS", default="300")
    try:
        return max(60, int(raw))
    except ValueError:
        return 300


def resolve_blockchain_api_prefix() -> str:
    prefix = resolve_secret("BLOCKCHAIN_API_PREFIX", default="/api/v1")
    return prefix if prefix.startswith("/") else f"/{prefix}"


def format_tor_onion_service(onion: str, path: str = "") -> str:
    host = onion.strip().lower().split("/")[0]
    if not path:
        return host
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{host}{normalized}"


def blockchain_secrets_status() -> dict[str, Any]:
    """Return non-sensitive blockchain.secrets resolution status."""
    path = blockchain_secrets_path()
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "genesis_creator_id": resolve_genesis_creator_id(),
        "blockchain_onion_configured": bool(resolve_blockchain_onion()),
        "master_server_onion_configured": bool(resolve_master_server_onion()),
        "blockchain_secret_configured": bool(resolve_blockchain_secret()),
        "mongodb_host": resolve_mongodb_host(),
        "master_server_internal_host": resolve_master_server_internal_host(),
        "ledger_distribution_sync_seconds": resolve_ledger_distribution_sync_seconds(),
        "blockchain_api_prefix": resolve_blockchain_api_prefix(),
    }


def write_blockchain_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write blockchain.secrets template for later build-stage population."""
    target_dir = secrets_dir or SECRETS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / DEFAULT_BLOCKCHAIN_SECRETS_NAME
    if path.exists() and not force:
        return path

    resolved: dict[str, str] = {}
    for key, default in BLOCKCHAIN_SECRETS_TEMPLATE_KEYS:
        if populate_from_env:
            value = resolve_secret(key, default=default)
        else:
            value = default
        resolved[key] = value

    lines = [
        "# LucidTops blockchain.secrets - loaded by blockchain/blockchain_secrets.py",
        f"# Generated: {utc_now()}",
        "# Tor *.onion values are inserted after container / hidden-service creation.",
        "# BLOCKCHAIN_SECRET / BLOCKCHAIN_SECRET_KEY are also mirrored in secrets.env.",
        "",
    ]
    for key, default in BLOCKCHAIN_SECRETS_TEMPLATE_KEYS:
        value = resolved.get(key, default)
        lines.append(f"{key}={value}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    load_blockchain_secrets(reload=True)
    return path
