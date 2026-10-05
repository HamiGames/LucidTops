#!/usr/bin/env python3
"""Write the eight operational *.secrets files from a live hardware and container pull.

Path: /mnt/myssd/LucidTops/Server/Secrets
Run on the Pi from the SSD mount:

    cd /mnt/myssd/LucidTops
    python backend/write_container_secrets.py

No git. No remote fetch. Database image, port, dbPath, binds, networks, and
admin credentials come from the running named Mongo containers. If any of
those containers is not running, databases.secrets and mongodb.secrets
content is skipped and the files are left unchanged.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
CANONICAL_SECRETS_DIR = Path("/mnt/myssd/LucidTops/Server/Secrets")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OPERATIONAL_FILES: tuple[str, ...] = (
    "server.secrets",
    "config.secrets",
    "operations.secrets",
    "mongodb.secrets",
    "databases.secrets",
    "blockchain.secrets",
    "payments.secrets",
    "backend.secrets",
)

SERVER_REQUIRED_KEYS: tuple[str, ...] = (
    "MASTER_SERVER_ID",
    "LUCID_TOPS_ROOT",
    "SECRETS_DIR",
    "DOCKER_NETWORK_NAME",
    "MASTER_SERVER_PORT",
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_ADMIN_PASSWORD",
    "API_KEY",
    "ENABLED_SERVICES",
)

CONFIG_REQUIRED_KEYS: tuple[str, ...] = (
    "MASTER_SERVER_PORT",
    "MASTER_SERVER_BIND_HOST",
    "API_BASE_PATH",
    "GUI_PREFIX",
    "HIDDEN_SERVICE_PORT",
)

OPERATIONS_REQUIRED_KEYS: tuple[str, ...] = (
    "OPERATIONS_BIND_HOST",
    "OPERATIONS_BIND_PORT",
)

BLOCKCHAIN_REQUIRED_KEYS: tuple[str, ...] = (
    "LUCID_TOPS_ROOT",
    "SECRETS_DIR",
    "MASTER_SERVER_ID",
    "GENESIS_CREATOR_ID",
    "DOCKER_NETWORK_NAME",
    "MONGODB_HOST",
    "MONGODB_PORT",
)

BACKEND_REQUIRED_KEYS: tuple[str, ...] = (
    "API_BASE_PATH",
    "GUI_PREFIX",
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_MAIN_DATABASE_NAME",
    "MONGODB_URL",
    "MASTER_SERVER_BIND_HOST",
    "MASTER_SERVER_PORT",
    "FRONTEND_SOURCE_PREFIX",
    "HIDDEN_SERVICE_PORT",
)


def _load_file(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load {path.as_posix()}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _chmod_secret(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _parse_secrets(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _require_keys(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    if path.resolve().parent != CANONICAL_SECRETS_DIR.resolve():
        raise RuntimeError(f"{path.name} is not under {CANONICAL_SECRETS_DIR.as_posix()}")
    if not path.is_file():
        raise RuntimeError(f"{path.name} was not written")
    loaded = _parse_secrets(path)
    missing = [key for key in keys if not loaded.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"{path.name} missing required keys: {', '.join(missing)}")
    return loaded


def _ensure_databases_path() -> None:
    db_dir = PROJECT_ROOT / "Databases"
    if str(db_dir) not in sys.path:
        sys.path.insert(0, str(db_dir))


def _sessions_container_name() -> str:
    """DockerDNS name of the Sessions container from MONGODB_MAIN_DATABASE_NAME."""
    _ensure_databases_path()
    from Dns_databases import container_name, resolve_main_database_name

    return container_name(resolve_main_database_name(), "_SessionsDB")


def _database_containers_not_running(docker_bin: str) -> list[str]:
    """Named Mongo containers that are not status=running. Empty when all are up."""
    from Dns_databases import ALL_NAMED_DB_CONTAINERS

    binary = docker_bin.strip()
    if not binary:
        return list(ALL_NAMED_DB_CONTAINERS)
    stopped: list[str] = []
    for name in ALL_NAMED_DB_CONTAINERS:
        result = subprocess.run(
            [binary, "inspect", "-f", "{{.State.Status}}", name],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        status = (result.stdout or "").strip()
        if result.returncode != 0 or status != "running":
            stopped.append(name)
    return stopped


def _bind_mongo_from_snapshot(snapshot: dict[str, Any]) -> None:
    host = _sessions_container_name()
    sessions = (snapshot.get("containers") or {}).get(host) or {}
    port = str(snapshot.get("container_port") or "").strip()
    if not port:
        raise RuntimeError("active Mongo snapshot has no container port")
    os.environ["MONGODB_HOST"] = host
    os.environ["MONGODB_PORT"] = port
    os.environ["MONGODB_ADMIN_USER"] = str(snapshot.get("admin_user") or "")
    os.environ["MONGODB_ADMIN_PASSWORD"] = str(snapshot.get("admin_password") or "")
    os.environ["MONGODB_PASSWORD"] = str(snapshot.get("mongodb_password") or "")
    # Prefix stays MONGODB_MAIN_DATABASE_NAME. init_database is the Mongo
    # database inside the Sessions container, not the container-name prefix.
    prefix = os.environ.get("MONGODB_MAIN_DATABASE_NAME", "").strip()
    init_database = str(sessions.get("init_database") or "").strip()
    url_database = init_database or prefix
    if url_database:
        os.environ["MONGODB_URL"] = f"mongodb://{host}:{port}/{url_database}"
    os.environ["LUCID_MONGODB_URL"] = f"mongodb://{host}:{port}"


def _write_server_and_config(snapshot: dict[str, Any] | None) -> tuple[Path, Path]:
    import builderMasterServer as builder

    launch_values = builder._resolve_launch_values(None)
    secrets_dir = Path(launch_values["secrets_dir"]).expanduser().resolve()
    if secrets_dir != CANONICAL_SECRETS_DIR.resolve():
        raise RuntimeError(
            f"server.secrets path {secrets_dir.as_posix()} is not {CANONICAL_SECRETS_DIR.as_posix()}"
        )
    secrets_dir.mkdir(parents=True, exist_ok=True)
    builder._apply_master_secrets_from_proxy(secrets_dir)
    root_dir = Path(launch_values["root_dir"])
    generated = builder._resolve_generated_secrets(root_dir / "secrets.env")
    if snapshot is not None:
        generated["MONGODB_ADMIN_PASSWORD"] = str(snapshot["admin_password"])
        generated["MONGODB_PASSWORD"] = str(snapshot["mongodb_password"])
    generated["MASTER_SERVER_ID"] = builder._resolve_or_create_master_server_id(
        secrets_dir=secrets_dir,
        pull=launch_values["hardware_pull"],
        existing=generated,
    )
    os.environ["MASTER_SERVER_ID"] = generated["MASTER_SERVER_ID"]
    config_path = secrets_dir / "config.secrets"
    config_values = builder._resolve_config_secrets(
        config_path,
        launch_values=launch_values,
    )
    onions = builder._resolve_onion_addresses(root_dir)
    tor_registry = builder.build_tor_route_registry(
        master_onion=onions.get("master_server") or None,
        frontend_onion=onions.get("frontend") or None,
        node_onion=onions.get("node_user") or None,
    )
    server_text = builder._build_server_secrets(
        generated,
        launch_values=launch_values,
        tor_registry=tor_registry,
    )
    config_text = builder._build_config_secrets(
        config_values,
        launch_values=launch_values,
    )
    server_path = secrets_dir / "server.secrets"
    server_path.write_text(server_text, encoding="utf-8")
    config_path.write_text(config_text, encoding="utf-8")
    _chmod_secret(server_path)
    _chmod_secret(config_path)
    return server_path, config_path


def _load_databases(backend_pull: ModuleType) -> tuple[ModuleType, ModuleType]:
    db_dir = PROJECT_ROOT / "Databases"
    if str(db_dir) not in sys.path:
        sys.path.insert(0, str(db_dir))
    _load_file("Dns_databases", db_dir / "Dns_databases.py")
    db_pull = _load_file("databases_pull_information", db_dir / "pull_information.py")
    saved = sys.modules.get("pull_information")
    sys.modules["pull_information"] = db_pull
    try:
        db_secrets = _load_file("databases_secrets_writer", db_dir / "databases_secrets.py")
    finally:
        if saved is not None:
            sys.modules["pull_information"] = saved
        else:
            sys.modules["pull_information"] = backend_pull
    return db_pull, db_secrets


def _verify_database_files(
    db_secrets: ModuleType,
    snapshot: dict[str, Any],
    databases_path: Path,
    mongodb_path: Path,
) -> None:
    expected = db_secrets.active_database_secret_fields(snapshot)
    databases_loaded = _require_keys(databases_path, tuple(expected.keys()))
    for key, value in expected.items():
        if databases_loaded.get(key, "") != value:
            raise RuntimeError(
                f"databases.secrets {key}={databases_loaded.get(key, '')!r} "
                f"does not match the running container {value!r}"
            )
    mongo_keys = (
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_IMAGE",
        "MONGODB_CONTAINER_PORT",
        "MONGODB_DATA_PATH_IN_CONTAINER",
        "MONGODB_ADMIN_USER",
        "MONGODB_ADMIN_PASSWORD",
        "MONGODB_PASSWORD",
        "DOCKER_NETWORK_TOR_DB",
        "DOCKER_NETWORK_NONTOR_DB",
    )
    mongo_loaded = _require_keys(mongodb_path, mongo_keys)
    sessions_host = _sessions_container_name()
    if mongo_loaded["MONGODB_HOST"] != sessions_host:
        raise RuntimeError(
            f"mongodb.secrets MONGODB_HOST is not {sessions_host}"
        )
    if mongo_loaded["MONGODB_PORT"] != str(snapshot["container_port"]):
        raise RuntimeError("mongodb.secrets MONGODB_PORT does not match the running container")
    for key in (
        "MONGODB_IMAGE",
        "MONGODB_CONTAINER_PORT",
        "MONGODB_DATA_PATH_IN_CONTAINER",
        "MONGODB_ADMIN_USER",
        "MONGODB_ADMIN_PASSWORD",
        "MONGODB_PASSWORD",
        "DOCKER_NETWORK_TOR_DB",
        "DOCKER_NETWORK_NONTOR_DB",
    ):
        if mongo_loaded.get(key, "") != expected[key]:
            raise RuntimeError(
                f"mongodb.secrets {key}={mongo_loaded.get(key, '')!r} "
                f"does not match the running container {expected[key]!r}"
            )
    from Dns_databases import ALL_NAMED_DB_CONTAINERS, secret_key_prefix

    for db_name in ALL_NAMED_DB_CONTAINERS:
        prefix = secret_key_prefix(db_name)
        for suffix in ("HOST", "PORT", "HOST_PORT", "DATA_MOUNT", "NETWORK"):
            key = f"{prefix}_{suffix}"
            if mongo_loaded.get(key, "") != expected[key]:
                raise RuntimeError(
                    f"mongodb.secrets {key} does not match the running container"
                )


def _bind_backend_mongo(db_values: dict[str, str]) -> None:
    from Dns_databases import secret_key_prefix

    prefix = secret_key_prefix(_sessions_container_name())
    host = db_values.get(f"{prefix}_HOST", "").strip()
    port = db_values.get(f"{prefix}_PORT", "").strip()
    database = db_values.get("MONGODB_MAIN_DATABASE_NAME", "").strip() or os.environ.get(
        "MONGODB_MAIN_DATABASE_NAME", ""
    ).strip()
    if not host or not port or not database:
        raise RuntimeError(
            "backend.secrets requires SessionsDB host, port, and database from the running container"
        )
    os.environ["MONGODB_HOST"] = host
    os.environ["MONGODB_PORT"] = port
    os.environ["MONGODB_MAIN_DATABASE_NAME"] = database
    os.environ["MONGODB_URL"] = f"mongodb://{host}:{port}/{database}"
    os.environ["LUCID_MONGODB_URL"] = f"mongodb://{host}:{port}"
    os.environ["SECRETS_DIR"] = CANONICAL_SECRETS_DIR.as_posix()
    os.environ["LUCID_TOPS_ROOT"] = os.environ.get("LUCID_TOPS_ROOT", "/mnt/myssd/LucidTops")


def main() -> int:
    from pull_information import bind_operation_environ, pull_realworld_information

    backend_pull = sys.modules["pull_information"]
    info = pull_realworld_information()
    bind_operation_environ(info, overwrite=True)
    secrets_dir = Path(str(info["secrets_dir"])).expanduser().resolve()
    if secrets_dir != CANONICAL_SECRETS_DIR.resolve():
        raise RuntimeError(
            f"secrets_dir {secrets_dir.as_posix()} is not {CANONICAL_SECRETS_DIR.as_posix()}"
        )
    os.environ["SECRETS_DIR"] = CANONICAL_SECRETS_DIR.as_posix()
    os.environ["LUCID_TOPS_ROOT"] = str(info["lucid_tops_root"])

    db_pull, db_secrets = _load_databases(backend_pull)
    docker_bin = str((info.get("bins") or {}).get("docker") or "")
    not_running = _database_containers_not_running(docker_bin)
    snapshot: dict[str, Any] | None = None
    databases_path: Path | None = None
    mongodb_path: Path | None = None
    db_values: dict[str, str] = {}
    if not_running:
        print(
            "skipped databases.secrets and mongodb.secrets content — not running: "
            + ", ".join(not_running),
            file=sys.stderr,
        )
    else:
        snapshot = db_pull.pull_active_mongodb_containers(docker_bin)
        _bind_mongo_from_snapshot(snapshot)
        info["mongodb_host"] = _sessions_container_name()
        info["mongodb_port"] = str(snapshot["container_port"])

    server_path, config_path = _write_server_and_config(snapshot)

    os.environ["DATABASES_SECRETS_FILE"] = (CANONICAL_SECRETS_DIR / "databases.secrets").as_posix()
    os.environ["MONGODB_SECRETS_FILE"] = (CANONICAL_SECRETS_DIR / "mongodb.secrets").as_posix()
    os.environ["SECRETS_DIR"] = CANONICAL_SECRETS_DIR.as_posix()
    if snapshot is not None:
        db_info = db_pull.pull_realworld_information()
        db_info["active_mongodb"] = snapshot
        databases_path, mongodb_path, db_values = db_secrets.write_databases_secrets(
            db_info,
            force=True,
            verified=True,
        )

    operations_dir = PROJECT_ROOT / "operations"
    if str(operations_dir) not in sys.path:
        sys.path.insert(0, str(operations_dir))
    sys.modules["pull_information"] = backend_pull
    operations = _load_file(
        "operations_secrets_writer",
        operations_dir / "operations_secrets.py",
    )
    operations_path = operations.write_operations_secrets(
        secrets_dir=CANONICAL_SECRETS_DIR,
        force=True,
    )

    blockchain_dir = PROJECT_ROOT / "blockchain"
    if str(blockchain_dir) not in sys.path:
        sys.path.insert(0, str(blockchain_dir))
    chain_pull = _load_file(
        "blockchain_pull_information",
        blockchain_dir / "pull_information.py",
    )
    blockchain = _load_file(
        "blockchain_secrets_writer",
        blockchain_dir / "blockchain_secrets.py",
    )
    sys.modules["pull_information"] = chain_pull
    try:
        blockchain_path = blockchain.write_blockchain_secrets_from_pull(
            info,
            secrets_dir=CANONICAL_SECRETS_DIR,
            force=False,
        )
    finally:
        sys.modules["pull_information"] = backend_pull
    _chmod_secret(blockchain_path)

    payments = _load_file(
        "payments_secrets_writer",
        PROJECT_ROOT / "PaySystems" / "payments_secrets.py",
    )
    payments_path = payments.write_payments_secrets(info, secrets_dir=CANONICAL_SECRETS_DIR)

    if db_values:
        _bind_backend_mongo(db_values)
    from BuildConfigs import write_backend_secrets

    backend_path = write_backend_secrets(CANONICAL_SECRETS_DIR, force=True)
    _chmod_secret(backend_path)

    written = {
        "server.secrets": server_path,
        "config.secrets": config_path,
        "operations.secrets": Path(operations_path),
        "mongodb.secrets": Path(mongodb_path) if mongodb_path is not None else None,
        "databases.secrets": Path(databases_path) if databases_path is not None else None,
        "blockchain.secrets": Path(blockchain_path),
        "payments.secrets": Path(payments_path),
        "backend.secrets": Path(backend_path),
    }
    _require_keys(written["server.secrets"], SERVER_REQUIRED_KEYS)
    server_loaded = _parse_secrets(written["server.secrets"])
    if snapshot is not None:
        sessions_host = _sessions_container_name()
        if server_loaded.get("MONGODB_HOST") != sessions_host:
            raise RuntimeError(
                f"server.secrets MONGODB_HOST is not {sessions_host}"
            )
        if server_loaded.get("MONGODB_PORT") != str(snapshot["container_port"]):
            raise RuntimeError("server.secrets MONGODB_PORT does not match the running container")
        if server_loaded.get("MONGODB_ADMIN_PASSWORD") != str(snapshot["admin_password"]):
            raise RuntimeError("server.secrets admin password does not match the running container")
        if databases_path is None or mongodb_path is None:
            raise RuntimeError("databases.secrets and mongodb.secrets were not written")
        _verify_database_files(db_secrets, snapshot, databases_path, mongodb_path)
    _require_keys(written["config.secrets"], CONFIG_REQUIRED_KEYS)
    _require_keys(written["operations.secrets"], OPERATIONS_REQUIRED_KEYS)
    _require_keys(written["blockchain.secrets"], BLOCKCHAIN_REQUIRED_KEYS)
    _require_keys(
        written["payments.secrets"],
        payments.PAYMENT_SECRET_KEYS
        + (
            "PAYMENTS_SECRETS_FILE",
            "SECRETS_DIR",
            "LUCID_TOPS_ROOT",
            "PAYMENTS_CONTAINER_NAME",
            "PAYMENTS_DOCKER_DNS_NAME",
            "PAYSYSTEMS_BIND_HOST",
            "PAYSYSTEMS_BIND_PORT",
            "PAYMENTS_NETWORK_NAME",
        ),
    )
    backend_loaded = _require_keys(written["backend.secrets"], BACKEND_REQUIRED_KEYS)
    if snapshot is not None:
        sessions_host = _sessions_container_name()
        if backend_loaded.get("MONGODB_HOST") != sessions_host:
            raise RuntimeError(
                f"backend.secrets MONGODB_HOST is not {sessions_host}"
            )

    for name in OPERATIONAL_FILES:
        path = written[name]
        if path is None:
            print(f"skipped {name}")
            continue
        print(path.resolve().as_posix())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"write_container_secrets failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
