"""Load and write LucidTops databases.secrets / mongodb.secrets at time of operation.

Seed sources (Proxy Bootstrap → Server/Secrets, read-only):
- /mnt/myssd/LucidTops/Server/Secrets/Master.secrets
- /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets (also Proxy.secrets)

Write target:
- /mnt/myssd/LucidTops/Server/Secrets/databases.secrets
- /mnt/myssd/LucidTops/Server/Secrets/mongodb.secrets

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from Dns_databases import (
    DB_ROOT,
    MONGO_DATA_PATH_IN_CONTAINER,
    secret_key_prefix,
    named_db_containers,
    network_for_zone,
    require_main_database_name,
    tor_db_containers,
    nontor_db_containers,
    zone_for,
    db_data_mount,
)
from pull_information import (
    load_master_and_proxy_seed,
    map_seed_to_databases_keys,
    master_secrets_path,
    proxy_secrets_path,
    read_torrc,
    resolve_lucid_tops_root,
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
    "DOCKER_NETWORK_NAME",
    "DOCKER_NETWORK_TOR_DB",
    "DOCKER_NETWORK_NONTOR_DB",
    "MONGODB_ADMIN_USER",
    "MONGODB_ADMIN_PASSWORD",
    "MONGODB_PASSWORD",
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
    return Path(root).expanduser() / "Server" / "Secrets"


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


def _seed_prior_from_master_and_proxy(
    lucid_root: Path, prior: dict[str, str]
) -> dict[str, str]:
    """
    Seed databases.secrets from Server/Secrets/Master.secrets + proxy.secrets.

    Precedence for non-empty values: existing databases.secrets (prior) > Master > proxy.
    """
    seed = map_seed_to_databases_keys(load_master_and_proxy_seed(lucid_root))
    if not seed:
        raise RuntimeError(
            "Master.secrets / proxy.secrets empty or missing under "
            f"{lucid_root.as_posix()}/Server/Secrets — run Proxy/Bootstrap.py first"
        )
    if not seed.get("DOCKER_NETWORK_NAME", "").strip():
        raise RuntimeError(
            "DOCKER_NETWORK_NAME missing from Server/Secrets/Master.secrets "
            "(or proxy.secrets) — run Proxy/Bootstrap.py before Databases"
        )
    merged = dict(seed)
    for key, value in prior.items():
        if value:
            merged[key] = value
    merged.setdefault("MASTER_SECRETS_FILE", master_secrets_path(lucid_root).as_posix())
    merged.setdefault("PROXY_SECRETS_FILE", proxy_secrets_path(lucid_root).as_posix())
    return merged


def write_secrets_file(path: Path, values: dict[str, str], *, header: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        header,
        f"# Generated: {utc_now()}",
        "# key=value — values seeded from Master/proxy + pulled/created at time of operation",
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
            "DOCKER_NETWORK_NAME",
            "DOCKER_NETWORK_TOR_DB",
            "DOCKER_NETWORK_NONTOR_DB",
            "MASTER_SERVER_INTERNAL_HOST",
            "MASTER_SERVER_INTERNAL_PORT",
            "MASTER_SECRETS_FILE",
            "PROXY_SECRETS_FILE",
            "TOR_SOCKS_HOST",
            "TOR_SOCKS_PORT",
        }:
            merged[key] = value
    return merged


def _active_mongodb_snapshot(pull: dict[str, Any]) -> dict[str, Any]:
    snapshot = pull.get("active_mongodb")
    if isinstance(snapshot, dict) and snapshot.get("containers"):
        return snapshot
    from pull_information import pull_active_mongodb_containers

    docker_bin = str((pull.get("bins") or {}).get("docker") or "")
    loaded = pull_active_mongodb_containers(docker_bin)
    pull["active_mongodb"] = loaded
    return loaded


def active_database_secret_fields(snapshot: dict[str, Any]) -> dict[str, str]:
    """Map a live Mongo inspect snapshot onto databases.secrets keys."""
    containers = snapshot.get("containers")
    if not isinstance(containers, dict) or not containers:
        raise RuntimeError("active Mongo snapshot has no containers")
    image = str(snapshot.get("image") or "").strip()
    container_port = str(snapshot.get("container_port") or "").strip()
    data_path = str(snapshot.get("data_path_in_container") or "").strip()
    admin_user = str(snapshot.get("admin_user") or "").strip()
    admin_password = str(snapshot.get("admin_password") or "").strip()
    mongo_password = str(snapshot.get("mongodb_password") or "").strip()
    tor_net = str(snapshot.get("docker_network_tor_db") or "").strip()
    nontor_net = str(snapshot.get("docker_network_nontor_db") or "").strip()
    required = {
        "MONGODB_IMAGE": image,
        "MONGODB_CONTAINER_PORT": container_port,
        "MONGODB_DATA_PATH_IN_CONTAINER": data_path,
        "MONGODB_ADMIN_USER": admin_user,
        "MONGODB_ADMIN_PASSWORD": admin_password,
        "MONGODB_PASSWORD": mongo_password,
        "DOCKER_NETWORK_TOR_DB": tor_net,
        "DOCKER_NETWORK_NONTOR_DB": nontor_net,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "active Mongo snapshot missing " + ", ".join(missing)
        )
    fields = dict(required)
    data_parents: set[str] = set()
    main_name = require_main_database_name(
        str(snapshot.get("main_database_name") or "").strip()
        or os.environ.get("MONGODB_MAIN_DATABASE_NAME", "").strip()
    )
    expected = named_db_containers(main_name)
    missing_names = [name for name in expected if name not in containers]
    if missing_names:
        raise RuntimeError(
            "active Mongo snapshot missing containers: " + ", ".join(missing_names)
        )
    fields["MONGODB_MAIN_DATABASE_NAME"] = main_name
    for db_name in named_db_containers(main_name):
        row = containers.get(db_name)
        if not isinstance(row, dict):
            raise RuntimeError(f"{db_name} missing from active Mongo snapshot")
        prefix = secret_key_prefix(db_name)
        host_port = str(row.get("host_port") or "").strip()
        data_mount = str(row.get("data_mount") or "").strip()
        network = str(row.get("network") or "").strip()
        zone = str(row.get("zone") or "").strip()
        row_port = str(row.get("container_port") or "").strip()
        if not data_mount or not network or not zone or not row_port:
            raise RuntimeError(f"{db_name} active config is incomplete")
        fields[f"{prefix}_HOST"] = db_name
        fields[f"{prefix}_PORT"] = row_port
        if host_port:
            fields[f"{prefix}_HOST_PORT"] = host_port
        fields[f"{prefix}_DATA_MOUNT"] = data_mount
        fields[f"{prefix}_NETWORK"] = network
        fields[f"{prefix}_ZONE"] = zone
        fields[f"{prefix}_URL"] = f"mongodb://{db_name}:{row_port}"
        bind_ip = str(row.get("bind_ip") or "").strip()
        if bind_ip:
            fields[f"{prefix}_BIND_IP"] = bind_ip
        db_path = str(row.get("data_path_in_container") or "").strip()
        if db_path:
            fields[f"{prefix}_STORAGE_DBPATH"] = db_path
        data_parents.add(Path(data_mount).parent.as_posix())
        init_database = str(row.get("init_database") or "").strip()
        if init_database:
            fields[f"{prefix}_DATABASE"] = init_database
    if len(data_parents) == 1:
        fields["MONGODB_DATA_MOUNT"] = next(iter(data_parents))
        fields["LUCID_DATABASES_DIR"] = next(iter(data_parents))
    bind_ips = {
        str(row.get("bind_ip") or "").strip()
        for row in containers.values()
        if str(row.get("bind_ip") or "").strip()
    }
    if len(bind_ips) == 1:
        fields["MONGODB_BIND_IP"] = next(iter(bind_ips))
    authorizations = {
        str(row.get("security_authorization") or "").strip()
        for row in containers.values()
        if str(row.get("security_authorization") or "").strip()
    }
    if len(authorizations) == 1:
        fields["MONGODB_SECURITY_AUTHORIZATION"] = next(iter(authorizations))
    replicas = {
        str(row.get("replication") or "").strip()
        for row in containers.values()
        if str(row.get("replication") or "").strip()
    }
    if len(replicas) == 1:
        fields["MONGODB_REPLICA_SET"] = next(iter(replicas))
    return fields


def _data_path_in_container(seed: dict[str, str]) -> str:
    """In-container mongod path. Host directories under DB_ROOT are not this value."""
    value = str(seed.get("MONGODB_DATA_PATH_IN_CONTAINER", "")).strip()
    root = DB_ROOT.rstrip("/")
    if value and value != root and not value.startswith(root + "/"):
        return value
    return MONGO_DATA_PATH_IN_CONTAINER


def _required_from_seed(seed: dict[str, str], *keys: str) -> str:
    """Connection constants come only from Master.secrets or proxy.secrets."""
    for key in keys:
        value = str(seed.get(key, "")).strip()
        if value:
            return value
    joined = " / ".join(keys)
    raise RuntimeError(f"{joined} missing from Master.secrets and proxy.secrets")


def build_databases_secrets_values(
    pull: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, str]:
    """Build databases.secrets from Master/proxy seed and the hardware pull."""
    lucid_root = resolve_lucid_tops_root(pull)
    secrets_path = databases_secrets_path()
    mongo_path = mongodb_secrets_path()
    raw_seed = pull.get("master_proxy_seed")
    if not isinstance(raw_seed, dict) or not raw_seed:
        raw_seed = load_master_and_proxy_seed(lucid_root)
    seed = map_seed_to_databases_keys({str(k): str(v) for k, v in raw_seed.items()})
    # Open torrc only when the seed already has both SOCKS keys. Do not parse the file.
    torrc_text = read_torrc(lucid_root, seed)

    prior = parse_secrets_file(secrets_path) if secrets_path.exists() and not force else {}
    existing = _seed_prior_from_master_and_proxy(lucid_root, prior)

    image = _required_from_seed(seed, "MONGODB_IMAGE")
    container_port = _required_from_seed(seed, "MONGODB_CONTAINER_PORT", "MONGODB_PORT")
    data_in_container = _data_path_in_container(seed)
    admin_user = _required_from_seed(seed, "MONGODB_ADMIN_USER")
    admin_password = _required_from_seed(seed, "MONGODB_ADMIN_PASSWORD", "MONGODB_PASSWORD")
    mongo_password = str(seed.get("MONGODB_PASSWORD", "")).strip() or admin_password
    network_name = _required_from_seed(seed, "DOCKER_NETWORK_NAME")
    main_name = require_main_database_name(
        _required_from_seed(seed, "MONGODB_MAIN_DATABASE_NAME")
    )
    os.environ["MONGODB_MAIN_DATABASE_NAME"] = main_name
    tor_net = str(seed.get("DOCKER_NETWORK_TOR_DB", "")).strip() or network_name
    nontor_net = str(seed.get("DOCKER_NETWORK_NONTOR_DB", "")).strip() or network_name

    compose_file = Path(str(pull["compose_dir"])) / "databases.compose.yml"
    data_root = DB_ROOT
    zone_values = {
        "DOCKER_NETWORK_NAME": network_name,
        "DOCKER_NETWORK_TOR_DB": tor_net,
        "DOCKER_NETWORK_NONTOR_DB": nontor_net,
    }

    values: dict[str, str] = {
        "MONGODB_IMAGE": image,
        "MONGODB_CONTAINER_PORT": container_port,
        "MONGODB_PORT": container_port,
        "MONGODB_DATA_PATH_IN_CONTAINER": data_in_container,
        "DOCKER_NETWORK_NAME": network_name,
        "DOCKER_NETWORK_TOR_DB": tor_net,
        "DOCKER_NETWORK_NONTOR_DB": nontor_net,
        "MONGODB_ADMIN_USER": admin_user,
        "MONGODB_ADMIN_PASSWORD": admin_password,
        "MONGODB_PASSWORD": mongo_password,
        "MONGODB_MAIN_DATABASE_NAME": main_name,
        "DATABASES_COMPOSE_FILE": compose_file.as_posix(),
        "HOST_PRIMARY_IP": str(pull["primary_ip"]),
        "HOST_PRIMARY_MAC": str(pull["primary_mac"]),
        "HOST_MACHINE_ID": str(pull["machine_id"]),
        "HOST_HOSTNAME": str(pull["hostname"]),
        "MONGODB_DATA_MOUNT": data_root,
        "LUCID_DATABASES_DIR": data_root,
        "DB_ROOT": data_root,
        "ROOT": lucid_root.as_posix(),
        "MONGODB_SECRETS_FILE": mongo_path.as_posix(),
        "MASTER_SECRETS_FILE": existing.get("MASTER_SECRETS_FILE", "")
        or master_secrets_path(lucid_root).as_posix(),
        "PROXY_SECRETS_FILE": existing.get("PROXY_SECRETS_FILE", "")
        or proxy_secrets_path(lucid_root).as_posix(),
        "SECRETS_DIR": secrets_dir().as_posix(),
        "LUCID_TOPS_ROOT": lucid_root.as_posix(),
    }
    if torrc_text:
        values["HOST_TOR_CONFIG_TORRC"] = (lucid_root / "torrc").as_posix()

    per_db: dict[str, str] = {}
    for db_name in named_db_containers(main_name):
        zone = zone_for(db_name, main_database_name=main_name)
        prefix = secret_key_prefix(db_name)
        data_mount = db_data_mount(db_name, data_root)
        per_db[f"{prefix}_HOST"] = db_name
        per_db[f"{prefix}_PORT"] = container_port
        per_db[f"{prefix}_URL"] = f"mongodb://{db_name}:{container_port}"
        per_db[f"{prefix}_DATA_MOUNT"] = data_mount
        per_db[f"{prefix}_NETWORK"] = network_name
        per_db[f"{prefix}_ZONE"] = zone
        per_db[f"{prefix}_DATABASE"] = db_name
        zone_net = network_for_zone(zone, zone_values)
        if zone_net and zone_net != network_name:
            per_db[f"{prefix}_ZONE_NETWORK"] = zone_net
    values.update(per_db)

    for key in NODE_DB_SCHEMA_KEYS:
        if key == "MONGODB_SECRETS_FILE":
            continue
        value = existing.get(key, "").strip()
        if value:
            values[key] = value

    master_host = (
        str(seed.get("MASTER_SERVER_INTERNAL_HOST", "")).strip()
        or str(seed.get("PROXY_BACKEND_DNS", "")).strip()
    )
    master_port = (
        str(seed.get("MASTER_SERVER_INTERNAL_PORT", "")).strip()
        or str(seed.get("MASTER_SERVER_PORT", "")).strip()
    )
    if not master_host:
        raise RuntimeError(
            "MASTER_SERVER_INTERNAL_HOST / PROXY_BACKEND_DNS missing — "
            "must be seeded from Master.secrets/proxy.secrets"
        )
    if not master_port:
        raise RuntimeError(
            "MASTER_SERVER_INTERNAL_PORT / MASTER_SERVER_PORT missing — "
            "must be seeded from Master.secrets/proxy.secrets"
        )
    values["MASTER_SERVER_INTERNAL_HOST"] = master_host
    values["MASTER_SERVER_INTERNAL_PORT"] = master_port
    values["MASTER_SERVER_PORT"] = str(seed.get("MASTER_SERVER_PORT", "")).strip() or master_port
    values["PROXY_BACKEND_DNS"] = str(seed.get("PROXY_BACKEND_DNS", "")).strip() or master_host

    for carry_key in (
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "TOR_SOCKS_USERNAME",
        "TOR_SOCKS_PASSWORD",
        "DOCKER_NETWORK_NAMES",
        "MASTER_SERVER_ONION",
    ):
        value = str(seed.get(carry_key, "")).strip()
        if value:
            values[carry_key] = value

    merged = _merge_existing(secrets_path, values, force=force)
    for key, value in per_db.items():
        merged[key] = value
    for key in (
        "MONGODB_IMAGE",
        "MONGODB_CONTAINER_PORT",
        "MONGODB_DATA_PATH_IN_CONTAINER",
        "MONGODB_ADMIN_USER",
        "MONGODB_ADMIN_PASSWORD",
        "MONGODB_PASSWORD",
        "MONGODB_MAIN_DATABASE_NAME",
        "DOCKER_NETWORK_NAME",
        "DOCKER_NETWORK_TOR_DB",
        "DOCKER_NETWORK_NONTOR_DB",
        "MONGODB_DATA_MOUNT",
        "LUCID_DATABASES_DIR",
        "DB_ROOT",
        "HOST_TOR_CONFIG_TORRC",
    ):
        if values.get(key):
            merged[key] = values[key]
    drop = {"LEDGER_REPLICA_SOURCE", "LEDGER_REPLICA_TARGET"}
    if not torrc_text:
        drop.add("HOST_TOR_CONFIG_TORRC")
    return {
        key: value
        for key, value in merged.items()
        if key not in drop and not key.startswith("LUCIDTOPSBLOCKCHAIN_")
    }


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
        "MONGODB_ADMIN_USER": databases_values.get("MONGODB_ADMIN_USER", ""),
        "MONGODB_ADMIN_PASSWORD": databases_values.get("MONGODB_ADMIN_PASSWORD", ""),
        "MONGODB_DATA_MOUNT": databases_values.get("MONGODB_DATA_MOUNT", ""),
        "MONGODB_DATA_PATH_IN_CONTAINER": databases_values.get(
            "MONGODB_DATA_PATH_IN_CONTAINER", ""
        ),
        "MONGODB_CONTAINER_PORT": databases_values.get("MONGODB_CONTAINER_PORT", ""),
        "MONGODB_IMAGE": databases_values.get("MONGODB_IMAGE", ""),
        "DOCKER_NETWORK_NAME": databases_values.get("DOCKER_NETWORK_NAME", ""),
        "DOCKER_NETWORK_TOR_DB": databases_values.get("DOCKER_NETWORK_TOR_DB", ""),
        "DOCKER_NETWORK_NONTOR_DB": databases_values.get("DOCKER_NETWORK_NONTOR_DB", ""),
        "MONGODB_MAIN_DATABASE_NAME": databases_values.get("MONGODB_MAIN_DATABASE_NAME", ""),
        "DB_ROOT": databases_values.get("DB_ROOT", ""),
        "HOST_TOR_CONFIG_TORRC": databases_values.get("HOST_TOR_CONFIG_TORRC", ""),
        "MASTER_SECRETS_FILE": databases_values.get("MASTER_SECRETS_FILE", ""),
        "PROXY_SECRETS_FILE": databases_values.get("PROXY_SECRETS_FILE", ""),
    }
    socks_host = (
        _env("TOR_SOCKS_HOST") or databases_values.get("TOR_SOCKS_HOST", "")
    )
    socks_port = (
        _env("TOR_SOCKS_PORT") or databases_values.get("TOR_SOCKS_PORT", "")
    )
    if socks_host and socks_port:
        values["TOR_SOCKS_HOST"] = socks_host
        values["TOR_SOCKS_PORT"] = socks_port
        values["MONGODB_VIA_SOCKS5"] = _env("MONGODB_VIA_SOCKS5") or "true"
    socks_user = (
        _env("TOR_SOCKS_USERNAME")
        or _env("TOR_SOCKS_USER")
        or databases_values.get("TOR_SOCKS_USERNAME", "")
    )
    socks_pass = _env("TOR_SOCKS_PASSWORD") or databases_values.get(
        "TOR_SOCKS_PASSWORD", ""
    )
    if socks_user:
        values["TOR_SOCKS_USERNAME"] = socks_user
    if socks_pass:
        values["TOR_SOCKS_PASSWORD"] = socks_pass

    main_name = databases_values.get("MONGODB_MAIN_DATABASE_NAME", "").strip()
    if main_name:
        container_names = named_db_containers(main_name)
    else:
        container_names = ()
    for db_name in container_names:
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
        header="# LucidTops databases.secrets - seeded from Master/proxy + operation pull",
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
        header="# LucidTops databases.secrets - seeded from Master/proxy + operation pull",
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
        "master_secrets_file": loaded.get("MASTER_SECRETS_FILE", ""),
        "proxy_secrets_file": loaded.get("PROXY_SECRETS_FILE", ""),
        "docker_network_name": loaded.get("DOCKER_NETWORK_NAME", ""),
    }
