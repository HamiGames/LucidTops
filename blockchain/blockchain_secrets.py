"""Load and create blockchain runtime configuration from blockchain.secrets at operation time.
RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
Values (IP, MAC, machine_id, paths, DockerDNS) MUST be pulled from hardware via pull_information.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
from functools import lru_cache
from pathlib import Path
from typing import Any

BLOCKCHAIN_SECRETS_FILE_ENV = "BLOCKCHAIN_SECRETS_FILE"
BLOCKCHAIN_SECRETS_NAME_ENV = "BLOCKCHAIN_SECRETS_NAME"

BLOCKCHAIN_SECRETS_KEYS: tuple[str, ...] = (
    "LUCID_TOPS_ROOT",
    "SECRETS_DIR",
    "MASTER_SERVER_ID",
    "GENESIS_CREATOR_ID",
    "BLOCKCHAIN_ONION",
    "MASTER_SERVER_ONION",
    "NODEUSER_ONION",
    "ADMIN_ONION",
    "BLOCKCHAIN_SECRET",
    "BLOCKCHAIN_SECRET_KEY",
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_MAIN_DATABASE_NAME",
    "MONGODB_URL",
    "MONGODB_SERVER_SELECTION_TIMEOUT_MS",
    "MASTER_SERVER_INTERNAL_HOST",
    "MASTER_SERVER_INTERNAL_PORT",
    "BLOCKCHAIN_CONTAINER_NAME",
    "BLOCKCHAIN_BIND_HOST",
    "BLOCKCHAIN_BIND_PORT",
    "IMAGE_GENERATOR_URL",
    "UNIVERSE_SEARCH_URL",
    "IMAGE_GENERATOR_ENABLED",
    "UNIVERSE_SEARCH_ENABLED",
    "IMAGE_GENERATOR_HOST",
    "IMAGE_GENERATOR_PORT",
    "IMAGE_GENERATOR_TIMEOUT_SECONDS",
    "UNIVERSE_SEARCH_HOST",
    "UNIVERSE_SEARCH_PORT",
    "LUCID_TOKEN_NSFW_RATIO",
    "LUCID_IMAGE_WIDTH",
    "LUCID_IMAGE_HEIGHT",
    "LUCID_IMAGE_SCHEMA_PROFILE",
    "LEDGER_DISTRIBUTION_SYNC_SECONDS",
    "LEDGER_REPLICA_DIR",
    "BLOCKCHAIN_API_PREFIX",
    "NODE_MIN_MEMORY_GB",
    "BLOCKCHAIN_MONGODB_WAIT_SECONDS",
    "BLOCKCHAIN_MONGODB_POLL_SECONDS",
    "LUCID_LEDGER_LIST_LIMIT",
    "TALLY_SYNC_TARGET",
    "TALLY_SYNC_INTERVAL_SECONDS",
    "TOTAL_TOKEN_SUPPLY",
    "INITIAL_BLOCK_REWARD",
    "HALVING_MINTED_FRACTION",
    "BURN_DIVISOR",
    "MAX_TOKEN_IMAGE_BYTES",
    "MAX_BLOCK_BYTES",
    "MAX_SESSIONS_PER_BLOCK",
    "MIN_BLOCK_INTERVAL_SECONDS",
    "BLOCKCHAIN_HASH_ALGORITHM",
    "GENESIS_PREVIOUS_HASH",
    "HOST_PRIMARY_IP",
    "HOST_PRIMARY_MAC",
    "HOST_MACHINE_ID",
    "HOST_HOSTNAME",
    "CHUNK_SIZE_BYTES",
    "SESSION_KEY_VALIDITY_SECONDS",
)

# One-time identity keys — never regenerated once present on disk.
_ONE_TIME_KEYS: frozenset[str] = frozenset(
    {
        "MASTER_SERVER_ID",
        "GENESIS_CREATOR_ID",
        "GENESIS_PREVIOUS_HASH",
        "BLOCKCHAIN_SECRET",
        "BLOCKCHAIN_SECRET_KEY",
    }
)


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def blockchain_secrets_path() -> Path:
    override = _env(BLOCKCHAIN_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    secrets_dir = _env("SECRETS_DIR")
    name = _env(BLOCKCHAIN_SECRETS_NAME_ENV) or "blockchain.secrets"
    if not secrets_dir:
        raise RuntimeError(
            "SECRETS_DIR missing — must be set at time of operation via pull_information"
        )
    return Path(secrets_dir).expanduser() / name


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


def get_secret(key: str) -> str:
    """Resolve one config value: env var > blockchain.secrets (empty if unset)."""
    env_value = _env(key)
    if env_value:
        return env_value
    try:
        return load_blockchain_secrets().get(key.upper(), "").strip()
    except RuntimeError:
        return ""


def require_secret(key: str) -> str:
    """Resolve env then blockchain.secrets; raise if missing at operation time."""
    value = get_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing — must be set in environment or blockchain.secrets "
            "at time of operation"
        )
    return value


def resolve_secret(key: str) -> str:
    """Resolve one config value: env var > blockchain.secrets; raise if missing."""
    return require_secret(key)


def require_secret_int(key: str) -> int:
    raw = require_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{key} must be an integer at time of operation (got {raw!r})"
        ) from exc


def require_secret_float(key: str) -> float:
    raw = require_secret(key)
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{key} must be a float at time of operation (got {raw!r})"
        ) from exc


def require_secret_bool(key: str) -> bool:
    raw = require_secret(key).lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise RuntimeError(
        f"{key} must be a boolean at time of operation (got {raw!r})"
    )


def _sha512_hex(material: str) -> str:
    return hashlib.sha512(material.encode("utf-8")).hexdigest()


def _allocate_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _read_onion_if_present(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def _load_master_server_id_from_disk(secrets_dir: Path) -> str:
    """Pull existing MasterServerID written at MasterServer operation time."""
    candidates = [
        secrets_dir / "MasterServerID.txt",
        secrets_dir / "Master.secrets",
        secrets_dir / "server.secrets",
        secrets_dir / "MasterID.secrets",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if path.suffix.lower() == ".txt":
            value = text.strip()
            if value:
                return value
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip().upper() in {"MASTER_SERVER_ID", "MASTERSERVERID"}:
                found = value.strip()
                if found:
                    return found
    return ""


def _resolve_master_server_id_for_pull(
    *,
    pull: dict[str, Any],
    prior: dict[str, str],
    secrets_dir: str,
) -> str:
    """
    Resolve MASTER_SERVER_ID at operation time.
    Prefer existing MasterServer identity; GENESIS_CREATOR_ID must equal this value.
    """
    for source in (
        prior.get("MASTER_SERVER_ID", ""),
        prior.get("GENESIS_CREATOR_ID", ""),
        _env("MASTER_SERVER_ID"),
        _env("GENESIS_CREATOR_ID"),
        _load_master_server_id_from_disk(Path(secrets_dir)),
    ):
        value = str(source or "").strip()
        if value:
            return value

    machine_id = str(pull.get("machine_id") or "").strip()
    primary_mac = str(pull.get("primary_mac") or "").strip()
    primary_ip = str(pull.get("primary_ip") or "").strip()
    if not machine_id or not primary_mac or not primary_ip:
        raise RuntimeError(
            "MASTER_SERVER_ID / GENESIS_CREATOR_ID require machine_id, primary_mac, "
            "and primary_ip from hardware pull (or existing MasterServerID on disk)"
        )
    return _sha512_hex(
        f"{machine_id}:{primary_mac}:{primary_ip}:{secrets.token_hex(32)}"
    )


def build_blockchain_secrets_values(
    pull: dict[str, Any] | None = None,
    *,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Build blockchain.secrets values from hardware pull at time of operation.
    Never invents placeholders. Never regenerates one-time keys already on disk.
    GENESIS_CREATOR_ID is always MASTER_SERVER_ID.
    """
    from pull_information import pull_realworld_information

    info = pull if pull is not None else pull_realworld_information()
    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    machine_id = str(info.get("machine_id") or "").strip()
    hostname = str(info.get("hostname") or "").strip()
    lucid_root = str(info.get("lucid_tops_root") or "").strip()
    secrets_dir = str(info.get("secrets_dir") or "").strip()
    databases_dir = str(info.get("databases_dir") or "").strip()

    if not primary_ip or not primary_mac or not machine_id:
        raise RuntimeError(
            "build_blockchain_secrets_values requires primary_ip, primary_mac, "
            "and machine_id from hardware pull"
        )
    if not lucid_root or not secrets_dir or not databases_dir:
        raise RuntimeError(
            "build_blockchain_secrets_values requires lucid_tops_root, secrets_dir, "
            "and databases_dir from hardware pull"
        )

    prior = dict(existing or {})
    if not prior:
        try:
            prior = dict(load_blockchain_secrets(reload=True))
        except RuntimeError:
            prior = {}

    def keep_or_create(key: str, factory) -> str:
        current = (prior.get(key) or _env(key) or "").strip()
        if key in _ONE_TIME_KEYS and current:
            return current
        created = factory()
        if not created:
            raise RuntimeError(f"{key} could not be created at time of operation")
        return str(created).strip()

    master_server_id = _resolve_master_server_id_for_pull(
        pull=info, prior=prior, secrets_dir=secrets_dir
    )
    # GENESIS_CREATOR_ID = MASTER_SERVER_ID
    genesis_prev = keep_or_create(
        "GENESIS_PREVIOUS_HASH",
        lambda: _sha512_hex(
            f"genesis-prev:{machine_id}:{primary_mac}:{primary_ip}:{secrets.token_hex(32)}"
        ),
    )
    blockchain_secret = keep_or_create(
        "BLOCKCHAIN_SECRET",
        lambda: secrets.token_urlsafe(32),
    )
    blockchain_secret_key = keep_or_create(
        "BLOCKCHAIN_SECRET_KEY",
        lambda: secrets.token_hex(32),
    )

    mongodb_host = (
        str(info.get("mongodb_host") or "").strip()
        or prior.get("MONGODB_HOST", "").strip()
        or _env("MONGODB_HOST")
    )
    mongodb_port = (
        str(info.get("mongodb_port") or "").strip()
        or prior.get("MONGODB_PORT", "").strip()
        or _env("MONGODB_PORT")
    )
    mongo_listen = info.get("mongo_listen")
    if not mongodb_port and isinstance(mongo_listen, (tuple, list)) and len(mongo_listen) >= 2:
        mongodb_port = str(mongo_listen[1])
    # When DockerDNS Mongo is not yet linked, bind to the live hardware primary IP
    # only if a Mongo listener/port was pulled from this host at operation time.
    if not mongodb_host and primary_ip and mongodb_port:
        mongodb_host = primary_ip
    if not mongodb_host:
        raise RuntimeError(
            "MONGODB_HOST missing — DockerDNS Mongo host or live Mongo listener "
            "must be present in hardware pull"
        )
    if not mongodb_port:
        raise RuntimeError(
            "MONGODB_PORT missing — must be present from hardware pull listeners or env"
        )

    master_host = (
        str(info.get("proxy_backend_dns") or "").strip()
        or prior.get("MASTER_SERVER_INTERNAL_HOST", "").strip()
        or _env("MASTER_SERVER_INTERNAL_HOST")
        or hostname
    )
    master_port = (
        str(info.get("master_server_port") or "").strip()
        or prior.get("MASTER_SERVER_INTERNAL_PORT", "").strip()
        or _env("MASTER_SERVER_INTERNAL_PORT")
        or str(_allocate_ephemeral_port())
    )

    ledger_replica = (
        str(info.get("ledger_replica_dir") or "").strip()
        or str(Path(databases_dir) / "LucidTopsBlockchain_Ledger")
    )
    Path(ledger_replica).mkdir(parents=True, exist_ok=True)

    blockchain_ctr = info.get("blockchain_container")
    container_name = ""
    if isinstance(blockchain_ctr, dict):
        container_name = str(blockchain_ctr.get("name") or "").strip()
    container_name = (
        container_name
        or prior.get("BLOCKCHAIN_CONTAINER_NAME", "").strip()
        or _env("BLOCKCHAIN_CONTAINER_NAME")
        or hostname
    )

    bind_host = primary_ip
    bind_port = prior.get("BLOCKCHAIN_BIND_PORT", "").strip() or _env("BLOCKCHAIN_BIND_PORT")
    if not bind_port:
        bind_port = str(_allocate_ephemeral_port())

    onion_export = Path(lucid_root) / "onions"
    blockchain_onion = (
        prior.get("BLOCKCHAIN_ONION", "").strip()
        or _env("BLOCKCHAIN_ONION")
        or _read_onion_if_present(onion_export / "blockchain" / "hostname")
    )
    master_onion = (
        prior.get("MASTER_SERVER_ONION", "").strip()
        or _env("MASTER_SERVER_ONION")
        or _read_onion_if_present(onion_export / "master" / "hostname")
    )
    node_onion = (
        prior.get("NODEUSER_ONION", "").strip()
        or _env("NODEUSER_ONION")
        or _read_onion_if_present(onion_export / "nodeuser" / "hostname")
    )
    admin_onion = (
        prior.get("ADMIN_ONION", "").strip()
        or _env("ADMIN_ONION")
        or _read_onion_if_present(onion_export / "admin" / "hostname")
    )

    # Blockchain.txt reward design applied at operation time (not baked as code constants consumers read).
    total_supply = prior.get("TOTAL_TOKEN_SUPPLY") or _env("TOTAL_TOKEN_SUPPLY") or "42000000"
    initial_reward = prior.get("INITIAL_BLOCK_REWARD") or _env("INITIAL_BLOCK_REWARD") or "50"
    halving_fraction = (
        prior.get("HALVING_MINTED_FRACTION") or _env("HALVING_MINTED_FRACTION") or "0.02"
    )
    tally_interval = (
        prior.get("TALLY_SYNC_INTERVAL_SECONDS")
        or _env("TALLY_SYNC_INTERVAL_SECONDS")
        or "180"
    )
    hash_algo = prior.get("BLOCKCHAIN_HASH_ALGORITHM") or _env("BLOCKCHAIN_HASH_ALGORITHM") or "sha512"
    burn_divisor = prior.get("BURN_DIVISOR") or _env("BURN_DIVISOR") or "10000"
    max_token_image = (
        prior.get("MAX_TOKEN_IMAGE_BYTES") or _env("MAX_TOKEN_IMAGE_BYTES") or str(1024 * 1024)
    )
    max_block_bytes = prior.get("MAX_BLOCK_BYTES") or _env("MAX_BLOCK_BYTES") or str(1024 * 1024)
    max_sessions = prior.get("MAX_SESSIONS_PER_BLOCK") or _env("MAX_SESSIONS_PER_BLOCK") or "100"
    min_interval = prior.get("MIN_BLOCK_INTERVAL_SECONDS") or _env("MIN_BLOCK_INTERVAL_SECONDS") or "180"
    ledger_sync = (
        prior.get("LEDGER_DISTRIBUTION_SYNC_SECONDS")
        or _env("LEDGER_DISTRIBUTION_SYNC_SECONDS")
        or "300"
    )
    api_prefix = prior.get("BLOCKCHAIN_API_PREFIX") or _env("BLOCKCHAIN_API_PREFIX") or "/blockchain"
    node_min_mem = prior.get("NODE_MIN_MEMORY_GB") or _env("NODE_MIN_MEMORY_GB") or "4"
    mongo_wait = (
        prior.get("BLOCKCHAIN_MONGODB_WAIT_SECONDS")
        or _env("BLOCKCHAIN_MONGODB_WAIT_SECONDS")
        or "120"
    )
    mongo_poll = (
        prior.get("BLOCKCHAIN_MONGODB_POLL_SECONDS")
        or _env("BLOCKCHAIN_MONGODB_POLL_SECONDS")
        or "2"
    )
    ledger_limit = prior.get("LUCID_LEDGER_LIST_LIMIT") or _env("LUCID_LEDGER_LIST_LIMIT") or "100"
    image_w = prior.get("LUCID_IMAGE_WIDTH") or _env("LUCID_IMAGE_WIDTH") or "256"
    image_h = prior.get("LUCID_IMAGE_HEIGHT") or _env("LUCID_IMAGE_HEIGHT") or "256"
    image_profile = (
        prior.get("LUCID_IMAGE_SCHEMA_PROFILE")
        or _env("LUCID_IMAGE_SCHEMA_PROFILE")
        or "genesisTokens"
    )
    nsfw_ratio = prior.get("LUCID_TOKEN_NSFW_RATIO") or _env("LUCID_TOKEN_NSFW_RATIO") or "0"
    chunk_size = prior.get("CHUNK_SIZE_BYTES") or _env("CHUNK_SIZE_BYTES") or "65536"
    session_key_validity = (
        prior.get("SESSION_KEY_VALIDITY_SECONDS")
        or _env("SESSION_KEY_VALIDITY_SECONDS")
        or str(63_072_000)  # 2 years
    )
    mongo_timeout = (
        prior.get("MONGODB_SERVER_SELECTION_TIMEOUT_MS")
        or _env("MONGODB_SERVER_SELECTION_TIMEOUT_MS")
        or "5000"
    )

    db_name = (
        prior.get("MONGODB_MAIN_DATABASE_NAME")
        or _env("MONGODB_MAIN_DATABASE_NAME")
        or "LucidTops_LedgerDB"
    )
    mongodb_url = (
        prior.get("MONGODB_URL")
        or _env("MONGODB_URL")
        or f"mongodb://{mongodb_host}:{mongodb_port}/{db_name}"
    )

    img_host = prior.get("IMAGE_GENERATOR_HOST") or _env("IMAGE_GENERATOR_HOST") or ""
    img_port = prior.get("IMAGE_GENERATOR_PORT") or _env("IMAGE_GENERATOR_PORT") or ""
    uni_host = prior.get("UNIVERSE_SEARCH_HOST") or _env("UNIVERSE_SEARCH_HOST") or ""
    uni_port = prior.get("UNIVERSE_SEARCH_PORT") or _env("UNIVERSE_SEARCH_PORT") or ""
    img_url = prior.get("IMAGE_GENERATOR_URL") or _env("IMAGE_GENERATOR_URL") or ""
    uni_url = prior.get("UNIVERSE_SEARCH_URL") or _env("UNIVERSE_SEARCH_URL") or ""
    if img_host and img_port and not img_url:
        img_url = f"http://{img_host}:{img_port}"
    if uni_host and uni_port and not uni_url:
        uni_url = f"http://{uni_host}:{uni_port}"
    img_enabled = (
        prior.get("IMAGE_GENERATOR_ENABLED")
        or _env("IMAGE_GENERATOR_ENABLED")
        or ("true" if img_url else "false")
    )
    uni_enabled = (
        prior.get("UNIVERSE_SEARCH_ENABLED")
        or _env("UNIVERSE_SEARCH_ENABLED")
        or ("true" if uni_url else "false")
    )
    img_timeout = (
        prior.get("IMAGE_GENERATOR_TIMEOUT_SECONDS")
        or _env("IMAGE_GENERATOR_TIMEOUT_SECONDS")
        or "30"
    )

    tally_target = (
        prior.get("TALLY_SYNC_TARGET")
        or _env("TALLY_SYNC_TARGET")
        or master_host
    )

    values: dict[str, str] = {
        "LUCID_TOPS_ROOT": lucid_root,
        "SECRETS_DIR": secrets_dir,
        "MASTER_SERVER_ID": master_server_id,
        "GENESIS_CREATOR_ID": master_server_id,
        "BLOCKCHAIN_ONION": blockchain_onion,
        "MASTER_SERVER_ONION": master_onion,
        "NODEUSER_ONION": node_onion,
        "ADMIN_ONION": admin_onion,
        "BLOCKCHAIN_SECRET": blockchain_secret,
        "BLOCKCHAIN_SECRET_KEY": blockchain_secret_key,
        "MONGODB_HOST": mongodb_host,
        "MONGODB_PORT": str(mongodb_port),
        "MONGODB_MAIN_DATABASE_NAME": db_name,
        "MONGODB_URL": mongodb_url,
        "MONGODB_SERVER_SELECTION_TIMEOUT_MS": str(mongo_timeout),
        "MASTER_SERVER_INTERNAL_HOST": master_host,
        "MASTER_SERVER_INTERNAL_PORT": str(master_port),
        "BLOCKCHAIN_CONTAINER_NAME": container_name,
        "BLOCKCHAIN_BIND_HOST": bind_host,
        "BLOCKCHAIN_BIND_PORT": str(bind_port),
        "IMAGE_GENERATOR_URL": img_url,
        "UNIVERSE_SEARCH_URL": uni_url,
        "IMAGE_GENERATOR_ENABLED": str(img_enabled).lower(),
        "UNIVERSE_SEARCH_ENABLED": str(uni_enabled).lower(),
        "IMAGE_GENERATOR_HOST": img_host,
        "IMAGE_GENERATOR_PORT": str(img_port) if img_port else "",
        "IMAGE_GENERATOR_TIMEOUT_SECONDS": str(img_timeout),
        "UNIVERSE_SEARCH_HOST": uni_host,
        "UNIVERSE_SEARCH_PORT": str(uni_port) if uni_port else "",
        "LUCID_TOKEN_NSFW_RATIO": str(nsfw_ratio),
        "LUCID_IMAGE_WIDTH": str(image_w),
        "LUCID_IMAGE_HEIGHT": str(image_h),
        "LUCID_IMAGE_SCHEMA_PROFILE": image_profile,
        "LEDGER_DISTRIBUTION_SYNC_SECONDS": str(ledger_sync),
        "LEDGER_REPLICA_DIR": ledger_replica,
        "BLOCKCHAIN_API_PREFIX": api_prefix if str(api_prefix).startswith("/") else f"/{api_prefix}",
        "NODE_MIN_MEMORY_GB": str(node_min_mem),
        "BLOCKCHAIN_MONGODB_WAIT_SECONDS": str(mongo_wait),
        "BLOCKCHAIN_MONGODB_POLL_SECONDS": str(mongo_poll),
        "LUCID_LEDGER_LIST_LIMIT": str(ledger_limit),
        "TALLY_SYNC_TARGET": tally_target,
        "TALLY_SYNC_INTERVAL_SECONDS": str(tally_interval),
        "TOTAL_TOKEN_SUPPLY": str(total_supply),
        "INITIAL_BLOCK_REWARD": str(initial_reward),
        "HALVING_MINTED_FRACTION": str(halving_fraction),
        "BURN_DIVISOR": str(burn_divisor),
        "MAX_TOKEN_IMAGE_BYTES": str(max_token_image),
        "MAX_BLOCK_BYTES": str(max_block_bytes),
        "MAX_SESSIONS_PER_BLOCK": str(max_sessions),
        "MIN_BLOCK_INTERVAL_SECONDS": str(min_interval),
        "BLOCKCHAIN_HASH_ALGORITHM": hash_algo,
        "GENESIS_PREVIOUS_HASH": genesis_prev,
        "HOST_PRIMARY_IP": primary_ip,
        "HOST_PRIMARY_MAC": primary_mac,
        "HOST_MACHINE_ID": machine_id,
        "HOST_HOSTNAME": hostname,
        "CHUNK_SIZE_BYTES": str(chunk_size),
        "SESSION_KEY_VALIDITY_SECONDS": str(session_key_validity),
    }
    return values


def write_blockchain_secrets_from_pull(
    pull: dict[str, Any] | None = None,
    *,
    secrets_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """
    Create/update blockchain.secrets from hardware pull at time of operation.
    Preserves existing one-time keys. Raises if required pull facts are missing.
    """
    from pull_information import bind_operation_environ, pull_realworld_information

    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)

    if secrets_dir is not None:
        os.environ["SECRETS_DIR"] = str(secrets_dir)
        os.environ.setdefault("BLOCKCHAIN_SECRETS_NAME", "blockchain.secrets")

    path = blockchain_secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if path.exists() and not force:
        existing = dict(load_blockchain_secrets(reload=True))

    values = build_blockchain_secrets_values(info, existing=existing)

    # Merge: never blank out existing one-time keys; keep GENESIS_CREATOR_ID == MASTER_SERVER_ID
    for key in _ONE_TIME_KEYS:
        if existing.get(key) and not force and key != "GENESIS_CREATOR_ID":
            values[key] = existing[key]
    master_id = (
        values.get("MASTER_SERVER_ID")
        or existing.get("MASTER_SERVER_ID")
        or values.get("GENESIS_CREATOR_ID")
        or existing.get("GENESIS_CREATOR_ID")
        or ""
    ).strip()
    if master_id:
        values["MASTER_SERVER_ID"] = master_id
        values["GENESIS_CREATOR_ID"] = master_id

    lines = [
        "# LucidTops blockchain.secrets - created at time of operation from hardware pull",
        f"# Generated: {utc_now()}",
        "# Tor *.onion values are inserted after container / hidden-service creation when present.",
        "",
    ]
    for key in BLOCKCHAIN_SECRETS_KEYS:
        lines.append(f"{key}={values.get(key, '')}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    load_blockchain_secrets(reload=True)

    for key, value in values.items():
        if value and not _env(key):
            os.environ[key] = value
    return path


def write_blockchain_secrets_template(
    secrets_dir: Path | None = None,
    *,
    populate_from_env: bool = True,
    force: bool = False,
) -> Path:
    """Write blockchain.secrets from hardware pull (no empty-key stubs)."""
    del populate_from_env  # retained for call-site compatibility; values come from pull
    return write_blockchain_secrets_from_pull(secrets_dir=secrets_dir, force=force)


def resolve_lucid_tops_root() -> Path:
    return Path(require_secret("LUCID_TOPS_ROOT")).expanduser()


def resolve_secrets_dir() -> Path:
    return Path(require_secret("SECRETS_DIR")).expanduser()


def resolve_master_server_id() -> str:
    """Resolve MasterServerID; GENESIS_CREATOR_ID is this same value."""
    for key in ("MASTER_SERVER_ID", "GENESIS_CREATOR_ID"):
        value = get_secret(key)
        if value:
            return value
    secrets_dir = get_secret("SECRETS_DIR") or _env("SECRETS_DIR")
    if secrets_dir:
        from_disk = _load_master_server_id_from_disk(Path(secrets_dir))
        if from_disk:
            return from_disk
    raise RuntimeError(
        "MASTER_SERVER_ID missing — must be set in environment, blockchain.secrets, "
        "or MasterServerID.txt at time of operation"
    )


def resolve_genesis_creator_id() -> str:
    """Genesis creator_id is MASTER_SERVER_ID."""
    return resolve_master_server_id()


def resolve_blockchain_onion() -> str:
    return get_secret("BLOCKCHAIN_ONION")


def resolve_master_server_onion() -> str:
    return get_secret("MASTER_SERVER_ONION")


def resolve_nodeuser_onion() -> str:
    return get_secret("NODEUSER_ONION")


def resolve_admin_onion() -> str:
    return get_secret("ADMIN_ONION")


def resolve_blockchain_secret() -> str:
    return get_secret("BLOCKCHAIN_SECRET")


def resolve_blockchain_secret_key() -> str:
    return get_secret("BLOCKCHAIN_SECRET_KEY")


def resolve_mongodb_host() -> str:
    return require_secret("MONGODB_HOST")


def resolve_mongodb_port() -> int:
    return require_secret_int("MONGODB_PORT")


def resolve_mongodb_main_database_name() -> str:
    return require_secret("MONGODB_MAIN_DATABASE_NAME")


def resolve_mongodb_url() -> str:
    configured = get_secret("MONGODB_URL")
    if configured:
        return configured
    host = resolve_mongodb_host()
    port = resolve_mongodb_port()
    database = resolve_mongodb_main_database_name()
    return f"mongodb://{host}:{port}/{database}"


def resolve_mongodb_server_selection_timeout_ms() -> int:
    return require_secret_int("MONGODB_SERVER_SELECTION_TIMEOUT_MS")


def resolve_master_server_internal_host() -> str:
    return require_secret("MASTER_SERVER_INTERNAL_HOST")


def resolve_master_server_internal_port() -> int:
    return require_secret_int("MASTER_SERVER_INTERNAL_PORT")


def resolve_blockchain_container_name() -> str:
    return get_secret("BLOCKCHAIN_CONTAINER_NAME")


def resolve_blockchain_bind_host() -> str:
    return require_secret("BLOCKCHAIN_BIND_HOST")


def resolve_blockchain_bind_port() -> int:
    return require_secret_int("BLOCKCHAIN_BIND_PORT")


def resolve_image_generator_url() -> str:
    return get_secret("IMAGE_GENERATOR_URL")


def resolve_universe_search_url() -> str:
    return get_secret("UNIVERSE_SEARCH_URL")


def resolve_image_generator_enabled() -> bool:
    return require_secret_bool("IMAGE_GENERATOR_ENABLED")


def resolve_universe_search_enabled() -> bool:
    return require_secret_bool("UNIVERSE_SEARCH_ENABLED")


def resolve_image_generator_host() -> str:
    return get_secret("IMAGE_GENERATOR_HOST")


def resolve_image_generator_port() -> str:
    return get_secret("IMAGE_GENERATOR_PORT")


def resolve_image_generator_timeout_seconds() -> float:
    return require_secret_float("IMAGE_GENERATOR_TIMEOUT_SECONDS")


def resolve_universe_search_host() -> str:
    return get_secret("UNIVERSE_SEARCH_HOST")


def resolve_universe_search_port() -> str:
    return get_secret("UNIVERSE_SEARCH_PORT")


def resolve_lucid_token_nsfw_ratio() -> float:
    ratio = require_secret_float("LUCID_TOKEN_NSFW_RATIO")
    return max(0.0, min(1.0, ratio))


def resolve_lucid_image_width() -> int:
    return require_secret_int("LUCID_IMAGE_WIDTH")


def resolve_lucid_image_height() -> int:
    return require_secret_int("LUCID_IMAGE_HEIGHT")


def resolve_lucid_image_schema_profile() -> str:
    return require_secret("LUCID_IMAGE_SCHEMA_PROFILE")


def resolve_ledger_distribution_sync_seconds() -> int:
    value = require_secret_int("LEDGER_DISTRIBUTION_SYNC_SECONDS")
    if value < 1:
        raise RuntimeError(
            "LEDGER_DISTRIBUTION_SYNC_SECONDS must be >= 1 at time of operation"
        )
    return value


def resolve_ledger_replica_dir() -> Path:
    return Path(require_secret("LEDGER_REPLICA_DIR")).expanduser()


def resolve_blockchain_api_prefix() -> str:
    prefix = require_secret("BLOCKCHAIN_API_PREFIX")
    return prefix if prefix.startswith("/") else f"/{prefix}"


def resolve_node_min_memory_gb() -> int:
    return require_secret_int("NODE_MIN_MEMORY_GB")


def resolve_blockchain_mongodb_wait_seconds() -> int:
    return require_secret_int("BLOCKCHAIN_MONGODB_WAIT_SECONDS")


def resolve_blockchain_mongodb_poll_seconds() -> float:
    return require_secret_float("BLOCKCHAIN_MONGODB_POLL_SECONDS")


def resolve_lucid_ledger_list_limit() -> int:
    value = require_secret_int("LUCID_LEDGER_LIST_LIMIT")
    if value < 1:
        raise RuntimeError(
            "LUCID_LEDGER_LIST_LIMIT must be >= 1 at time of operation"
        )
    return value


def resolve_tally_sync_target() -> str:
    return require_secret("TALLY_SYNC_TARGET")


def resolve_tally_sync_interval_seconds() -> int:
    return require_secret_int("TALLY_SYNC_INTERVAL_SECONDS")


def resolve_total_token_supply() -> int:
    return require_secret_int("TOTAL_TOKEN_SUPPLY")


def resolve_initial_block_reward() -> int:
    return require_secret_int("INITIAL_BLOCK_REWARD")


def resolve_halving_minted_fraction() -> float:
    return require_secret_float("HALVING_MINTED_FRACTION")


def resolve_burn_divisor() -> int:
    return require_secret_int("BURN_DIVISOR")


def resolve_max_token_image_bytes() -> int:
    return require_secret_int("MAX_TOKEN_IMAGE_BYTES")


def resolve_max_block_bytes() -> int:
    return require_secret_int("MAX_BLOCK_BYTES")


def resolve_max_sessions_per_block() -> int:
    return require_secret_int("MAX_SESSIONS_PER_BLOCK")


def resolve_min_block_interval_seconds() -> int:
    return require_secret_int("MIN_BLOCK_INTERVAL_SECONDS")


def resolve_blockchain_hash_algorithm() -> str:
    return require_secret("BLOCKCHAIN_HASH_ALGORITHM")


def resolve_chunk_size_bytes() -> int:
    return require_secret_int("CHUNK_SIZE_BYTES")


def resolve_session_key_validity_seconds() -> int:
    return require_secret_int("SESSION_KEY_VALIDITY_SECONDS")


def format_tor_onion_service(onion: str, path: str = "") -> str:
    host = onion.strip().lower().split("/")[0]
    if not path:
        return host
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{host}{normalized}"


def blockchain_secrets_status() -> dict[str, Any]:
    """Return non-sensitive blockchain.secrets resolution status."""
    path = blockchain_secrets_path()
    status: dict[str, Any] = {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
    }
    try:
        status["genesis_creator_id"] = resolve_genesis_creator_id()
    except RuntimeError:
        status["genesis_creator_id"] = None
    status["blockchain_onion_configured"] = bool(resolve_blockchain_onion())
    status["master_server_onion_configured"] = bool(resolve_master_server_onion())
    status["blockchain_secret_configured"] = bool(resolve_blockchain_secret())
    try:
        status["mongodb_host"] = resolve_mongodb_host()
    except RuntimeError:
        status["mongodb_host"] = None
    try:
        status["master_server_internal_host"] = resolve_master_server_internal_host()
    except RuntimeError:
        status["master_server_internal_host"] = None
    try:
        status["ledger_distribution_sync_seconds"] = (
            resolve_ledger_distribution_sync_seconds()
        )
    except RuntimeError:
        status["ledger_distribution_sync_seconds"] = None
    try:
        status["blockchain_api_prefix"] = resolve_blockchain_api_prefix()
    except RuntimeError:
        status["blockchain_api_prefix"] = None
    try:
        status["ledger_replica_dir"] = resolve_ledger_replica_dir().as_posix()
    except RuntimeError:
        status["ledger_replica_dir"] = None
    return status


def ensure_blockchain_secrets(*, force: bool = False) -> Path:
    """Pull hardware and ensure blockchain.secrets exists before other blockchain ops."""
    return write_blockchain_secrets_from_pull(force=force)


def __getattr__(name: str) -> Any:
    if name == "LUCID_TOPS_ROOT":
        return resolve_lucid_tops_root()
    if name == "SECRETS_DIR":
        return resolve_secrets_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
