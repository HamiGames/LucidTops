"""Sessions hardware pull at time of operation.

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

Seed sources (Server/Secrets, read-only for sessions):
- /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets
- /mnt/myssd/LucidTops/Server/Secrets/Master.secrets
- /mnt/myssd/LucidTops/Server/Secrets/databases.secrets
- /mnt/myssd/LucidTops/Server/Secrets/backend.secrets

Write target (Pi console — not inside the image):
- /mnt/myssd/LucidTops/Server/Secrets/sessions.secrets
- Torrc: /mnt/myssd/LucidTops/torrc
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, SESSIONS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pull_information import (  # noqa: E402
    _allocate_ephemeral_port,
    _match_container,
    bind_operation_environ,
    export_shell_env,
    get_last_pull,
    pull_realworld_information,
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _normalize_mac(mac: str) -> str:
    return "".join(ch for ch in mac.upper() if ch.isalnum())


def _container_ip_or_name(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    ip_addr = str(meta.get("ip") or "").strip()
    if ip_addr:
        return ip_addr
    return str(meta.get("name") or "").strip()


_PLACEHOLDER_VALUES = frozenset({"invalid ip", "your_collection_name"})
_RESERVED_PORT_KEYS = (
    "MASTER_SERVER_PORT",
    "MASTER_SERVER_INTERNAL_PORT",
    "MONGODB_PORT",
    "PROXY_PORT",
    "PROXY_NGINX_LISTEN_PORT",
    "FRONTEND_PORT",
    "NODE_PORT",
    "HIDDEN_SERVICE_PORT",
)


def usable_secret_value(value: str) -> bool:
    """Reject empty values and known placeholder tokens from secrets files."""
    text = (value or "").strip()
    if not text:
        return False
    return text.lower() not in _PLACEHOLDER_VALUES


def _parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def resolve_lucid_tops_root(info: dict[str, Any] | None = None) -> Path:
    raw = ""
    if info is not None:
        raw = str(info.get("lucid_tops_root") or "").strip()
    raw = raw or _env("LUCID_TOPS_ROOT")
    if not raw:
        raise RuntimeError(
            "LUCID_TOPS_ROOT missing — must be set at time of operation "
            "(expected /mnt/myssd/LucidTops)"
        )
    return Path(raw).expanduser().resolve()


def server_secrets_dir(lucid_root: Path | None = None) -> Path:
    """Canonical Server/Secrets path (Master.secrets + proxy.secrets)."""
    override = _env("MASTER_SECRETS_DIR") or _env("SERVER_SECRETS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    root = lucid_root if lucid_root is not None else resolve_lucid_tops_root()
    return (root / "Server" / "Secrets").resolve()


def master_secrets_path(lucid_root: Path | None = None) -> Path:
    override = _env("MASTER_SECRETS_FILE")
    if override:
        return Path(override).expanduser().resolve()
    directory = server_secrets_dir(lucid_root)
    for name in ("Master.secrets", "master.secrets"):
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve()
    return (directory / "Master.secrets").resolve()


def proxy_secrets_path(lucid_root: Path | None = None) -> Path:
    override = _env("PROXY_SECRETS_FILE")
    if override:
        return Path(override).expanduser().resolve()
    directory = server_secrets_dir(lucid_root)
    return (directory / "proxy.secrets").resolve()


def _secrets_file(lucid_root: Path, name: str) -> Path:
    return (server_secrets_dir(lucid_root) / name).resolve()


def sessions_secrets_dir(lucid_root: Path | None = None) -> Path:
    """Sessions secrets are read from the Pi console Server/Secrets directory."""
    return server_secrets_dir(lucid_root)


def load_master_and_proxy_seed(lucid_root: Path | None = None) -> dict[str, str]:
    """
    Load Server/Secrets for the sessions container.

    proxy.secrets wins over Master.secrets when both have a value and they differ,
    and placeholder values are dropped. databases.secrets and backend.secrets fill
    keys the connection files do not have. The sessions database URL comes from
    databases.secrets. The master database URL and MASTER_SERVER_ID come from
    backend.secrets.
    """
    root = lucid_root if lucid_root is not None else resolve_lucid_tops_root()
    directory = server_secrets_dir(root)
    loaded: dict[str, dict[str, str]] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.secrets")):
            loaded[path.name] = _parse_secrets_file(path)

    proxy_loaded = loaded.get("proxy.secrets") or _parse_secrets_file(proxy_secrets_path(root))
    master_loaded = loaded.get("Master.secrets") or _parse_secrets_file(master_secrets_path(root))
    databases_loaded = loaded.get("databases.secrets") or _parse_secrets_file(
        _secrets_file(root, "databases.secrets")
    )
    backend_loaded = loaded.get("backend.secrets") or _parse_secrets_file(
        _secrets_file(root, "backend.secrets")
    )

    merged: dict[str, str] = {}
    for key in set(proxy_loaded) | set(master_loaded):
        proxy_value = proxy_loaded.get(key, "").strip()
        master_value = master_loaded.get(key, "").strip()
        proxy_ok = usable_secret_value(proxy_value)
        master_ok = usable_secret_value(master_value)
        if proxy_ok and master_ok and proxy_value != master_value:
            merged[key] = proxy_value
        elif proxy_ok:
            merged[key] = proxy_value
        elif master_ok:
            merged[key] = master_value

    for extra in (databases_loaded, backend_loaded):
        for key, value in extra.items():
            if usable_secret_value(value) and not usable_secret_value(merged.get(key, "")):
                merged[key] = value.strip()

    for key, value in databases_loaded.items():
        if not usable_secret_value(value):
            continue
        if key.endswith("_SESSIONSDB_URL"):
            merged["LUCIDTOPS_SESSIONS_DB_URL"] = value.strip()
        elif key.endswith("_SESSIONSDB_DATABASE"):
            merged["LUCIDTOPS_SESSIONS_DB_NAME"] = value.strip()
    if not usable_secret_value(merged.get("LUCIDTOPS_SESSIONS_DB_NAME", "")):
        service_name = merged.get("MONGODB_SERVICE", "").strip()
        if usable_secret_value(service_name):
            merged["LUCIDTOPS_SESSIONS_DB_NAME"] = service_name

    backend_url = backend_loaded.get("MONGODB_URL", "").strip()
    if usable_secret_value(backend_url):
        merged["MASTER_MONGODB_URL"] = backend_url
        merged["MONGODB_URL"] = backend_url
    backend_db = backend_loaded.get("MONGODB_MAIN_DATABASE_NAME", "").strip()
    if usable_secret_value(backend_db):
        merged["MASTER_MONGODB_DATABASE"] = backend_db
        merged["MONGODB_MAIN_DATABASE_NAME"] = backend_db
    backend_host = backend_loaded.get("MONGODB_HOST", "").strip()
    if usable_secret_value(backend_host):
        merged["MONGODB_HOST"] = backend_host
    backend_port = backend_loaded.get("MONGODB_PORT", "").strip()
    if usable_secret_value(backend_port):
        merged["MONGODB_PORT"] = backend_port
    master_server_id = backend_loaded.get("MASTER_SERVER_ID", "").strip()
    if usable_secret_value(master_server_id):
        merged["MASTER_SERVER_ID"] = master_server_id
        merged["TALLY_ENTITY_ID_MASTER"] = master_server_id
    return merged


def _reserved_ports(seed: dict[str, str]) -> set[int]:
    reserved: set[int] = set()
    for key in _RESERVED_PORT_KEYS:
        raw = seed.get(key, "").strip()
        if raw.isdigit():
            reserved.add(int(raw))
    return reserved


def allocate_sessions_bind_port(seed: dict[str, str]) -> str:
    """Pick an ephemeral port that is not a port already published in Server/Secrets."""
    reserved = _reserved_ports(seed)
    for _ in range(32):
        port = _allocate_ephemeral_port()
        if port not in reserved and port > 0:
            return str(port)
    raise RuntimeError(
        "SESSIONS_BIND_PORT could not be allocated without colliding with Server/Secrets ports"
    )


def map_seed_to_sessions_keys(seed: dict[str, str]) -> dict[str, str]:
    """Map Server/Secrets keys onto sessions.secrets key names used at runtime."""
    mapped = {key: value for key, value in seed.items() if usable_secret_value(value)}
    aliases: tuple[tuple[str, str], ...] = (
        ("PROXY_BACKEND_DNS", "MASTER_SERVER_INTERNAL_HOST"),
        ("PROXY_SESSIONS_DNS", "SESSIONS_DOCKER_DNS_NAME"),
        ("PROXY_SESSIONS_DNS", "SESSIONS_BIND_HOST"),
        ("PROXY_OPERATIONS_DNS", "OPERATIONS_DOCKER_DNS_NAME"),
        ("MASTER_SERVER_PORT", "MASTER_SERVER_INTERNAL_PORT"),
        ("SESSION_RECORDS_COLLECTION", "LUCIDTOPS_SESSIONS_COLLECTION"),
        ("NODE_CREATE_SESSION_ROUTE", "SESSION_CREATE_API_ROUTE"),
        ("MASTER_SERVER_ID", "TALLY_ENTITY_ID_MASTER"),
        ("SESSION_STATUSES", "SESSION_FINALISED_STATUSES"),
    )
    for src, dst in aliases:
        value = seed.get(src, "").strip()
        if usable_secret_value(value):
            mapped[dst] = value.strip()
    public_routes = [
        item.strip()
        for item in seed.get("API_PUBLIC_ROUTES", "").split(",")
        if item.strip()
    ]
    if "/session-end" in public_routes:
        mapped["OPERATIONS_SESSION_HANDOFF_PATH"] = "/session-end"
    return mapped


def enrich_sessions_pull(info: dict[str, Any]) -> dict[str, Any]:
    """Attach sessions/Rdp/operations DockerDNS facts from seed + live pull."""
    lucid_root = resolve_lucid_tops_root(info)
    seed = map_seed_to_sessions_keys(load_master_and_proxy_seed(lucid_root))
    write_secrets_dir = sessions_secrets_dir(lucid_root)

    containers = info.get("docker_containers") or {}
    sessions_ctr = _match_container(
        containers, "sessions", "lucid-sessions", "lucidtops-sessions"
    )
    operations_ctr = _match_container(
        containers, "operations", "lucid-operations", "ops", "lucidtops-operations"
    )
    master_ctr = _match_container(
        containers, "master", "backend", "lucid-server", "masterserver"
    )

    docker_network_name = (
        _env("DOCKER_NETWORK_NAME")
        or seed.get("DOCKER_NETWORK_NAME", "").strip()
        or str(info.get("docker_network_name") or "").strip()
    )

    sessions_dns = (
        _env("SESSIONS_DOCKER_DNS_NAME")
        or seed.get("SESSIONS_DOCKER_DNS_NAME", "").strip()
        or seed.get("PROXY_SESSIONS_DNS", "").strip()
        or _container_ip_or_name(sessions_ctr)
    )
    if not usable_secret_value(sessions_dns):
        sessions_dns = ""
    sessions_port = _env("SESSIONS_BIND_PORT") or seed.get("SESSIONS_BIND_PORT", "").strip()
    if not sessions_port:
        sessions_port = allocate_sessions_bind_port(seed)

    operations_dns = (
        _env("OPERATIONS_DOCKER_DNS_NAME")
        or seed.get("OPERATIONS_DOCKER_DNS_NAME", "").strip()
        or seed.get("PROXY_OPERATIONS_DNS", "").strip()
        or _container_ip_or_name(operations_ctr)
    )
    if not usable_secret_value(operations_dns):
        operations_dns = ""
    master_dns = (
        _env("MASTER_SERVER_INTERNAL_HOST")
        or seed.get("MASTER_SERVER_INTERNAL_HOST", "").strip()
        or seed.get("PROXY_BACKEND_DNS", "").strip()
        or str(info.get("proxy_backend_dns") or "").strip()
        or _container_ip_or_name(master_ctr)
    )
    if not usable_secret_value(master_dns):
        master_dns = ""
    master_port = (
        _env("MASTER_SERVER_INTERNAL_PORT")
        or seed.get("MASTER_SERVER_INTERNAL_PORT", "").strip()
        or seed.get("MASTER_SERVER_PORT", "").strip()
    )
    if master_port and not master_port.isdigit():
        master_port = ""

    operations_port = (
        _env("OPERATIONS_BIND_PORT") or seed.get("OPERATIONS_BIND_PORT", "").strip()
    )
    if operations_port and not operations_port.isdigit():
        operations_port = ""

    enriched = dict(info)
    enriched.update(
        {
            "lucid_tops_root": lucid_root.as_posix(),
            "secrets_dir": write_secrets_dir.as_posix(),
            "server_secrets_dir": server_secrets_dir(lucid_root).as_posix(),
            "master_secrets_file": master_secrets_path(lucid_root).as_posix(),
            "proxy_secrets_file": proxy_secrets_path(lucid_root).as_posix(),
            "master_proxy_seed": seed,
            "docker_network_name": docker_network_name,
            "sessions_container": sessions_ctr or {},
            "operations_container": operations_ctr or {},
            "master_container": master_ctr or {},
            "sessions_docker_dns_name": sessions_dns,
            "sessions_bind_host": sessions_dns,
            "sessions_bind_port": str(sessions_port),
            "operations_docker_dns_name": operations_dns,
            "operations_bind_port": str(operations_port),
            "master_server_internal_host": master_dns,
            "master_server_internal_port": str(master_port),
            "tor_available": bool(info.get("bins", {}).get("tor"))
            or bool(info.get("tor_listen"))
            or bool(seed.get("TOR_SOCKS_HOST")),
            "docker_network_available": bool(docker_network_name),
            "hostname_resolved": socket.gethostname(),
        }
    )
    return enriched


def pull_sessions_hardware(
    *, bind_environ: bool = True, overwrite: bool = False
) -> dict[str, Any]:
    """
    Pull live hardware facts (IP, MAC, paths, DockerDNS) at script/container run.
    Seeds Docker network / master / peer DNS from Master.secrets + proxy.secrets.
    Fails if primary IP or MAC cannot be read from hardware.
    """
    info = enrich_sessions_pull(pull_realworld_information())
    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip:
        raise RuntimeError(
            "sessions pull failed — primary IPv4 not present on hardware at time of operation"
        )
    if not primary_mac:
        raise RuntimeError(
            "sessions pull failed — primary MAC not present on hardware at time of operation"
        )

    if bind_environ:
        bind_sessions_environ(info, overwrite=overwrite)

    return info


def bind_sessions_environ(
    pull: dict[str, Any] | None = None, *, overwrite: bool = False
) -> dict[str, str]:
    """Bind os.environ from Master/proxy seed + pulled hardware for the sessions container."""
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=False)
    bound = bind_operation_environ(info, overwrite=overwrite)
    seed = map_seed_to_sessions_keys(
        info.get("master_proxy_seed")
        if isinstance(info.get("master_proxy_seed"), dict)
        else load_master_and_proxy_seed(resolve_lucid_tops_root(info))
    )

    mapping: dict[str, str] = {
        "LUCID_TOPS_ROOT": str(info.get("lucid_tops_root") or ""),
        "SESSIONS_BIND_HOST": str(info.get("sessions_bind_host") or ""),
        "SESSIONS_BIND_PORT": str(info.get("sessions_bind_port") or ""),
        "SESSIONS_DOCKER_DNS_NAME": str(info.get("sessions_docker_dns_name") or ""),
        "MASTER_SERVER_INTERNAL_HOST": str(info.get("master_server_internal_host") or ""),
        "MASTER_SERVER_INTERNAL_PORT": str(info.get("master_server_internal_port") or ""),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_MAC_NORMALIZED": _normalize_mac(str(info["primary_mac"])),
        "MASTER_SECRETS_FILE": str(info.get("master_secrets_file") or ""),
        "PROXY_SECRETS_FILE": str(info.get("proxy_secrets_file") or ""),
        "SERVER_SECRETS_DIR": str(info.get("server_secrets_dir") or ""),
    }
    if info.get("operations_docker_dns_name"):
        mapping["OPERATIONS_DOCKER_DNS_NAME"] = str(info["operations_docker_dns_name"])
    if info.get("operations_bind_port"):
        mapping["OPERATIONS_BIND_PORT"] = str(info["operations_bind_port"])
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])

    for key in (
        "PROXY_BACKEND_DNS",
        "PROXY_SESSIONS_DNS",
        "PROXY_OPERATIONS_DNS",
        "MASTER_SERVER_PORT",
        "MASTER_SERVER_ONION",
        "MASTER_SERVER_ID",
        "TALLY_ENTITY_ID_MASTER",
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_URL",
        "MONGODB_MAIN_DATABASE_NAME",
        "MASTER_MONGODB_URL",
        "MASTER_MONGODB_DATABASE",
        "LUCIDTOPS_SESSIONS_DB_URL",
        "LUCIDTOPS_SESSIONS_DB_NAME",
        "LUCIDTOPS_SESSIONS_COLLECTION",
        "SESSION_RECORDS_COLLECTION",
        "SESSION_STATUSES",
        "SESSION_FINALISED_STATUSES",
        "SESSION_ID_LENGTH",
        "SESSION_KEY_MIN_LENGTH",
        "SESSION_HASH_ALGORITHM",
        "SESSION_CHUNK_SIZE_BYTES",
        "SESSION_CREATE_API_ROUTE",
        "NODE_CREATE_SESSION_ROUTE",
        "OPERATIONS_SESSION_HANDOFF_PATH",
        "API_PUBLIC_ROUTES",
    ):
        value = seed.get(key, "").strip()
        if usable_secret_value(value):
            mapping[key] = value

    secrets_dir = str(info.get("secrets_dir") or sessions_secrets_dir(resolve_lucid_tops_root(info)))
    mapping["SECRETS_DIR"] = secrets_dir
    mapping["SESSIONS_SECRETS_FILE"] = str(
        Path(secrets_dir)
        / (
            _env("SESSIONS_SECRETS_NAME")
            or (
                f"{_env('SESSIONS_CONTAINER_NAME')}.secrets"
                if _env("SESSIONS_CONTAINER_NAME")
                else "sessions.secrets"
            )
        )
    )

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        if overwrite or not _env(key):
            os.environ[key] = str(value).strip()
            bound[key] = str(value).strip()
    return bound


def get_sessions_pull() -> dict[str, Any]:
    last = get_last_pull()
    if last.get("primary_ip") and last.get("primary_mac"):
        return enrich_sessions_pull(last)
    return pull_sessions_hardware(bind_environ=True)


def live_primary_mac() -> str:
    info = get_sessions_pull()
    mac = str(info.get("primary_mac") or "").strip()
    if not mac:
        raise RuntimeError("HARDWARE_PRIMARY_MAC missing — must be pulled at time of operation")
    return mac


def live_primary_ip() -> str:
    info = get_sessions_pull()
    ip_addr = str(info.get("primary_ip") or _env("HARDWARE_PRIMARY_IP")).strip()
    if not ip_addr:
        raise RuntimeError("HARDWARE_PRIMARY_IP missing — must be pulled at time of operation")
    return ip_addr


def sessions_shell_env() -> str:
    info = pull_sessions_hardware(bind_environ=True, overwrite=True)
    return export_shell_env(info)


def main() -> int:
    info = pull_sessions_hardware(bind_environ=True, overwrite=True)
    # Emit full bound env for entrypoint sourcing (includes sessions-specific keys).
    bound = bind_sessions_environ(info, overwrite=True)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    print("\n".join(lines) + ("\n" if lines else ""), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
