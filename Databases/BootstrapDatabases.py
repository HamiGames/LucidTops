"""Bootstrap LucidTops separate MongoDB database containers at time of operation.

includes:
- pull_realworld_information(): hardware IP, MAC, mounts, Docker state
- seed DockerDNS / network / master / Tor from Server/Secrets/Master.secrets + proxy.secrets
- write databases.secrets / mongodb.secrets from seed + pull
- generate compose for six separate containers (Tor vs non-Tor networks)
- start containers, apply DBSchemas, verify, mark secrets verified
- configure ledger replica metadata (LucidTops_LedgerDB -> LucidTopsBlockchain_LedgerDB)

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

_DATABASES_DIR = Path(__file__).resolve().parent
if str(_DATABASES_DIR) not in sys.path:
    sys.path.insert(0, str(_DATABASES_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DATABASES_DIR / file_name
    registry = f"lucid_databases_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_pull = _load_local("pull_information")
_secrets = _load_local("databases_secrets")
_dns = _load_local("Dns_databases")
_schemas = _load_local("DBSchemas")
_compose = _load_local("BuildCompose")

pull_realworld_information = _pull.pull_realworld_information
bind_operation_environ = _pull.bind_operation_environ
utc_now = _pull.utc_now
_run = _pull._run
_which = _pull._which
_env = _pull._env
master_secrets_path = _pull.master_secrets_path
proxy_secrets_path = _pull.proxy_secrets_path
load_master_and_proxy_seed = _pull.load_master_and_proxy_seed
resolve_lucid_tops_root = _pull.resolve_lucid_tops_root

write_databases_secrets = _secrets.write_databases_secrets
mark_databases_verified = _secrets.mark_databases_verified
databases_secrets_status = _secrets.databases_secrets_status

ALL_NAMED_DB_CONTAINERS = _dns.ALL_NAMED_DB_CONTAINERS
DB_DATA_SUBDIR = _dns.DB_DATA_SUBDIR
secret_key_prefix = _dns.secret_key_prefix

apply_schema_to_database = _schemas.apply_schema_to_database
write_databases_compose = _compose.write_databases_compose


def _require_proxy_bootstrap_seed(pull: dict[str, Any]) -> dict[str, str]:
    """Fail closed unless Proxy Bootstrap Master/proxy secrets are present."""
    lucid_root = resolve_lucid_tops_root(pull)
    master_path = master_secrets_path(lucid_root)
    proxy_path = proxy_secrets_path(lucid_root)
    if not master_path.is_file() and not proxy_path.is_file():
        raise RuntimeError(
            "Proxy Bootstrap seed missing — expected Master.secrets and/or proxy.secrets under "
            f"{lucid_root.as_posix()}/Server/Secrets "
            f"(checked: {master_path.as_posix()}, {proxy_path.as_posix()})"
        )
    seed = load_master_and_proxy_seed(lucid_root)
    if not seed.get("DOCKER_NETWORK_NAME", "").strip():
        raise RuntimeError(
            "DOCKER_NETWORK_NAME missing from Server/Secrets/Master.secrets "
            "(or proxy.secrets) — run Proxy/Bootstrap.py before Databases"
        )
    return seed


def _ensure_data_dirs(databases_dir: Path) -> list[str]:
    created: list[str] = []
    for db_name, subdir in DB_DATA_SUBDIR.items():
        path = databases_dir / subdir
        path.mkdir(parents=True, exist_ok=True)
        created.append(path.as_posix())
    return created


def _docker_bin(pull: dict[str, Any]) -> str:
    docker_bin = str((pull.get("bins") or {}).get("docker") or "").strip() or _which("docker")
    if not docker_bin:
        raise RuntimeError(
            "docker binary not found on hardware — required at time of operation"
        )
    return docker_bin


def _compose_command(docker_bin: str, compose_file: Path) -> list[str]:
    # Prefer `docker compose` plugin; fall back to docker-compose binary if present.
    probe = _run([docker_bin, "compose", "version"])
    if probe.returncode == 0:
        return [docker_bin, "compose", "-f", compose_file.as_posix()]
    compose_bin = _which("docker-compose")
    if compose_bin:
        return [compose_bin, "-f", compose_file.as_posix()]
    raise RuntimeError(
        "docker compose / docker-compose not available — required at time of operation"
    )


def _ensure_networks(docker_bin: str, values: dict[str, str]) -> list[str]:
    """Ensure Proxy LucidDNS network + tor/nontor DB networks exist (create if missing)."""
    created: list[str] = []
    names: list[str] = []
    for key in (
        "DOCKER_NETWORK_NAME",
        "DOCKER_NETWORK_TOR_DB",
        "DOCKER_NETWORK_NONTOR_DB",
    ):
        name = values.get(key, "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        raise RuntimeError(
            "no Docker network names in secrets — DOCKER_NETWORK_NAME must come from "
            "Master.secrets/proxy.secrets"
        )
    for name in names:
        inspect = _run([docker_bin, "network", "inspect", name])
        if inspect.returncode != 0:
            result = _run([docker_bin, "network", "create", "--driver", "bridge", name])
            if result.returncode != 0:
                raise RuntimeError(
                    f"failed to create docker network {name}: {result.stderr.strip()}"
                )
            created.append(name)
        else:
            created.append(name)
    return created


def _compose_up(docker_bin: str, compose_file: Path) -> None:
    cmd = _compose_command(docker_bin, compose_file) + ["up", "-d"]
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(
            f"docker compose up failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def _wait_healthy(
    docker_bin: str,
    *,
    timeout_seconds: int | None = None,
) -> dict[str, str]:
    if timeout_seconds is None:
        raw = _env("DATABASES_HEALTH_TIMEOUT_SECONDS")
        if not raw:
            raise RuntimeError(
                "DATABASES_HEALTH_TIMEOUT_SECONDS missing — must be set at time of operation"
            )
        timeout_seconds = int(raw)
    deadline = time.time() + timeout_seconds
    statuses: dict[str, str] = {}
    while time.time() < deadline:
        all_ok = True
        for db_name in ALL_NAMED_DB_CONTAINERS:
            inspect = _run(
                [
                    docker_bin,
                    "inspect",
                    "-f",
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                    db_name,
                ]
            )
            status = (inspect.stdout or "").strip().lower() if inspect.returncode == 0 else "missing"
            statuses[db_name] = status
            if status not in {"healthy", "running"}:
                all_ok = False
        if all_ok:
            return statuses
        time.sleep(3)
    raise RuntimeError(f"database containers not healthy before timeout: {statuses}")


def _mongo_client_for(db_name: str, values: dict[str, str]) -> Any:
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("pymongo required — install Databases/requirements.txt") from exc

    prefix = secret_key_prefix(db_name)
    # From orchestration host, use published host port + primary IP when not on DockerDNS net.
    host_port = values.get(f"{prefix}_HOST_PORT", "").strip()
    primary_ip = values.get("HOST_PRIMARY_IP", "").strip() or _env("HOST_PRIMARY_IP")
    container_port = values.get(f"{prefix}_PORT", "").strip()
    admin_user = values.get("MONGODB_ADMIN_USER", "").strip()
    admin_password = values.get("MONGODB_ADMIN_PASSWORD", "").strip()

    if primary_ip and host_port:
        host = primary_ip
        port = host_port
    else:
        host = values.get(f"{prefix}_HOST", db_name)
        port = container_port

    if not host or not port:
        raise RuntimeError(
            f"connection host/port missing for {db_name} — secrets incomplete at operation time"
        )

    if admin_user and admin_password:
        uri = f"mongodb://{admin_user}:{admin_password}@{host}:{port}/?authSource=admin"
    else:
        uri = f"mongodb://{host}:{port}"

    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return client


def _apply_all_schemas(values: dict[str, str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    stamp = utc_now()
    for db_name in ALL_NAMED_DB_CONTAINERS:
        client = _mongo_client_for(db_name, values)
        try:
            db = client[db_name]
            results.append(apply_schema_to_database(db, db_name, created_at=stamp))
            # Replica metadata document for ledger sync configuration.
            if db_name == "LucidTopsBlockchain_LedgerDB":
                source = values.get("LEDGER_REPLICA_SOURCE", "").strip()
                target = values.get("LEDGER_REPLICA_TARGET", "").strip()
                db["_replica_meta"].update_one(
                    {"role": "blockchain_ledger_replica"},
                    {
                        "$set": {
                            "role": "blockchain_ledger_replica",
                            "source": source,
                            "target": target,
                            "omit_fields": ["creator_id"],
                            "updated_at": stamp,
                        }
                    },
                    upsert=True,
                )
        finally:
            client.close()
    return results


def bootstrap_databases(*, force: bool = False) -> dict[str, Any]:
    """
    One-shot bootstrap at time of operation:
    require Master/proxy seed → pull → dirs → secrets → networks → compose → up → schemas → verify.
    """
    pull = pull_realworld_information()
    bind_operation_environ(pull)
    seed = _require_proxy_bootstrap_seed(pull)

    # Require image/port/data-path from env/seed at operation time before writing secrets.
    if (
        not _env("MONGODB_IMAGE")
        and not str(pull.get("mongodb_image") or "").strip()
        and not seed.get("MONGODB_IMAGE", "").strip()
    ):
        raise RuntimeError("MONGODB_IMAGE must be set at time of operation")
    if (
        not _env("MONGODB_CONTAINER_PORT")
        and not str(pull.get("mongodb_container_port") or "").strip()
        and not seed.get("MONGODB_CONTAINER_PORT", "").strip()
        and not seed.get("MONGODB_PORT", "").strip()
    ):
        raise RuntimeError(
            "MONGODB_CONTAINER_PORT must be set at time of operation "
            "(or mongod must be listening so pull can capture it)"
        )
    if not _env("MONGODB_DATA_PATH_IN_CONTAINER") and not seed.get(
        "MONGODB_DATA_PATH_IN_CONTAINER", ""
    ).strip():
        raise RuntimeError(
            "MONGODB_DATA_PATH_IN_CONTAINER must be set at time of operation"
        )
    if not _env("DATABASES_HEALTH_TIMEOUT_SECONDS"):
        raise RuntimeError(
            "DATABASES_HEALTH_TIMEOUT_SECONDS must be set at time of operation"
        )

    databases_dir = Path(str(pull["databases_dir"]))
    data_dirs = _ensure_data_dirs(databases_dir)

    db_secrets_path, mongo_secrets_path, values = write_databases_secrets(
        pull, force=force, verified=False
    )

    docker_bin = _docker_bin(pull)
    networks = _ensure_networks(docker_bin, values)
    compose_path = write_databases_compose(values)
    _compose_up(docker_bin, compose_path)
    health = _wait_healthy(docker_bin)
    schema_results = _apply_all_schemas(values)
    mark_databases_verified(values)

    return {
        "pulled_at": pull.get("pulled_at"),
        "databases_dir": databases_dir.as_posix(),
        "data_dirs": data_dirs,
        "databases_secrets": db_secrets_path.as_posix(),
        "mongodb_secrets": mongo_secrets_path.as_posix(),
        "compose_file": compose_path.as_posix(),
        "networks": networks,
        "health": health,
        "schemas": schema_results,
        "verified": True,
        "master_secrets_file": values.get("MASTER_SECRETS_FILE", ""),
        "proxy_secrets_file": values.get("PROXY_SECRETS_FILE", ""),
        "docker_network_name": values.get("DOCKER_NETWORK_NAME", ""),
        "status": databases_secrets_status(),
    }


def main() -> int:
    force = _env("DATABASES_BOOTSTRAP_FORCE").lower() in {"1", "true", "yes"}
    result = bootstrap_databases(force=force)
    print(f"databases_dir={result['databases_dir']}")
    print(f"databases_secrets={result['databases_secrets']}")
    print(f"mongodb_secrets={result['mongodb_secrets']}")
    print(f"compose_file={result['compose_file']}")
    print(f"master_secrets_file={result.get('master_secrets_file', '')}")
    print(f"proxy_secrets_file={result.get('proxy_secrets_file', '')}")
    print(f"docker_network_name={result.get('docker_network_name', '')}")
    print(f"verified={result['verified']}")
    for name, status in (result.get("health") or {}).items():
        print(f"container {name}={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
