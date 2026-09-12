"""Operations hardware pull at time of operation.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

OPERATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPERATIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, OPERATIONS_DIR, BACKEND_DIR):
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


def _first_listen_port(info: dict[str, Any], *process_names: str) -> int | None:
    listening = info.get("listening") or {}
    for name in process_names:
        entries = listening.get(name) or []
        for _host, port in entries:
            if port:
                return int(port)
    return None


def _operations_secrets_name() -> str:
    name = _env("OPERATIONS_SECRETS_NAME")
    if name:
        return name
    container = _env("OPERATIONS_CONTAINER_NAME")
    return f"{container}.secrets" if container else "operations.secrets"


def enrich_operations_pull(info: dict[str, Any]) -> dict[str, Any]:
    """Attach operations DockerDNS / bind facts from the live pull."""
    containers = info.get("docker_containers") or {}
    operations_ctr = _match_container(
        containers, "operations", "lucid-operations", "ops", "lucidtops-operations"
    )
    master_ctr = _match_container(
        containers, "master", "backend", "lucid-server", "masterserver"
    )
    sessions_ctr = _match_container(
        containers, "sessions", "lucid-sessions", "lucidtops-sessions"
    )

    primary_ip = str(info.get("primary_ip") or "").strip()
    operations_dns = (
        _env("OPERATIONS_DOCKER_DNS_NAME")
        or _container_ip_or_name(operations_ctr)
        or primary_ip
    )
    operations_port = _env("OPERATIONS_BIND_PORT")
    if not operations_port:
        uvicorn_port = _first_listen_port(info, "uvicorn", "python")
        operations_port = (
            str(uvicorn_port) if uvicorn_port else str(_allocate_ephemeral_port())
        )

    operations_host = (
        _env("OPERATIONS_BIND_HOST")
        or str(info.get("operations_bind_host") or "").strip()
        or primary_ip
    )

    master_dns = (
        _env("MASTER_SERVER_INTERNAL_HOST")
        or str(info.get("proxy_backend_dns") or "").strip()
        or _container_ip_or_name(master_ctr)
        or str(info.get("master_server_bind_host") or "").strip()
        or primary_ip
    )

    # Prefer env SECRETS_DIR (Ops.dockerfile / dockercmd); else keep pull secrets_dir.
    secrets_dir = Path(
        _env("SECRETS_DIR") or str(info.get("secrets_dir") or "")
    ).expanduser()
    if not str(secrets_dir):
        lucid_root = Path(str(info.get("lucid_tops_root") or "")).expanduser()
        secrets_dir = lucid_root / "operations" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    secrets_name = _operations_secrets_name()
    operations_secrets_file = Path(
        _env("OPERATIONS_SECRETS_FILE") or (secrets_dir / secrets_name).as_posix()
    ).expanduser()

    enriched = dict(info)
    enriched.update(
        {
            "operations_container": operations_ctr or {},
            "master_container": master_ctr or {},
            "sessions_container": sessions_ctr or {},
            "operations_docker_dns_name": operations_dns,
            "operations_bind_host": operations_host,
            "operations_bind_port": str(operations_port),
            "master_server_internal_host": master_dns,
            "secrets_dir": secrets_dir.as_posix(),
            "operations_secrets_file": operations_secrets_file.as_posix(),
            "operations_secrets_name": secrets_name,
            "tor_available": bool(info.get("bins", {}).get("tor"))
            or bool(info.get("tor_listen")),
            "docker_network_available": bool(
                str(info.get("docker_network_name") or "").strip()
            ),
        }
    )
    return enriched


def bind_operations_environ(
    pull: dict[str, Any] | None = None, *, overwrite: bool = False
) -> dict[str, str]:
    """Bind os.environ from pulled hardware for the operations container."""
    info = pull if pull is not None else pull_operations_hardware(bind_environ=False)
    bound = bind_operation_environ(info, overwrite=overwrite)

    mapping: dict[str, str] = {
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_PRIMARY_MAC_NORMALIZED": _normalize_mac(str(info["primary_mac"])),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "OPERATIONS_BIND_HOST": str(
            info.get("operations_bind_host") or info["primary_ip"]
        ),
        "OPERATIONS_BIND_PORT": str(info.get("operations_bind_port") or ""),
        "OPERATIONS_DOCKER_DNS_NAME": str(info.get("operations_docker_dns_name") or ""),
        "SECRETS_DIR": str(info.get("secrets_dir") or ""),
        "OPERATIONS_SECRETS_FILE": str(info.get("operations_secrets_file") or ""),
        "OPERATIONS_SECRETS_NAME": str(info.get("operations_secrets_name") or ""),
        "MASTER_SERVER_INTERNAL_HOST": str(
            info.get("master_server_internal_host") or ""
        ),
    }
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
        mapping["OPERATIONS_NETWORK_NAME"] = str(info["docker_network_name"])

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        if overwrite or not _env(key):
            os.environ[key] = str(value).strip()
            bound[key] = str(value).strip()
    return bound


def pull_operations_hardware(*, bind_environ: bool = True, overwrite: bool = False) -> dict[str, Any]:
    """
    Pull live hardware facts (IP, MAC, paths, DockerDNS) at script/container run.
    Fails if primary IP or MAC cannot be read from hardware.
    """
    info = enrich_operations_pull(pull_realworld_information())
    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip:
        raise RuntimeError(
            "operations pull failed — primary IPv4 not present on hardware at time of operation"
        )
    if not primary_mac:
        raise RuntimeError(
            "operations pull failed — primary MAC not present on hardware at time of operation"
        )

    if bind_environ:
        bind_operations_environ(info, overwrite=overwrite)

    return info


def get_operations_pull() -> dict[str, Any]:
    last = get_last_pull()
    if last.get("primary_ip") and last.get("primary_mac"):
        return enrich_operations_pull(last)
    return pull_operations_hardware(bind_environ=True)


def live_primary_mac() -> str:
    info = get_operations_pull()
    mac = str(info.get("primary_mac") or "").strip()
    if not mac:
        raise RuntimeError("HOST_PRIMARY_MAC missing — must be pulled at time of operation")
    return mac


def live_primary_mac_normalized() -> str:
    env_mac = os.environ.get("HOST_PRIMARY_MAC_NORMALIZED", "").strip()
    if env_mac:
        return env_mac
    return _normalize_mac(live_primary_mac())


def live_primary_ip() -> str:
    info = get_operations_pull()
    ip_addr = str(info.get("primary_ip") or os.environ.get("HOST_PRIMARY_IP", "")).strip()
    if not ip_addr:
        raise RuntimeError("HOST_PRIMARY_IP missing — must be pulled at time of operation")
    return ip_addr


def operations_shell_env() -> str:
    info = pull_operations_hardware(bind_environ=True, overwrite=True)
    bound = bind_operations_environ(info, overwrite=True)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    info = pull_operations_hardware(bind_environ=True, overwrite=True)
    bound = bind_operations_environ(info, overwrite=True)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    print("\n".join(lines) + ("\n" if lines else ""), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
