"""Sessions hardware pull at time of operation.

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
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


def _first_listen_port(info: dict[str, Any], *process_names: str) -> int | None:
    listening = info.get("listening") or {}
    for name in process_names:
        entries = listening.get(name) or []
        for host, port in entries:
            if port:
                return int(port)
    return None


def enrich_sessions_pull(info: dict[str, Any]) -> dict[str, Any]:
    """Attach sessions/Rdp/operations DockerDNS facts from the live pull."""
    containers = info.get("docker_containers") or {}
    sessions_ctr = _match_container(
        containers, "sessions", "lucid-sessions", "lucidtops-sessions"
    )
    rdp_ctr = _match_container(containers, "rdp", "lucid-rdp", "lucidtops-rdp")
    operations_ctr = _match_container(
        containers, "operations", "lucid-operations", "ops", "lucidtops-operations"
    )
    master_ctr = _match_container(
        containers, "master", "backend", "lucid-server", "masterserver"
    )

    sessions_dns = (
        _env("SESSIONS_DOCKER_DNS_NAME")
        or _container_ip_or_name(sessions_ctr)
        or str(info.get("primary_ip") or "").strip()
    )
    sessions_port = _env("SESSIONS_BIND_PORT")
    if not sessions_port:
        uvicorn_port = _first_listen_port(info, "uvicorn", "python")
        sessions_port = str(uvicorn_port) if uvicorn_port else str(_allocate_ephemeral_port())

    rdp_dns = _env("RDP_DOCKER_DNS_NAME") or _container_ip_or_name(rdp_ctr)
    operations_dns = (
        _env("OPERATIONS_DOCKER_DNS_NAME") or _container_ip_or_name(operations_ctr)
    )
    master_dns = (
        _env("MASTER_SERVER_INTERNAL_HOST")
        or str(info.get("proxy_backend_dns") or "").strip()
        or _container_ip_or_name(master_ctr)
        or str(info.get("master_server_bind_host") or "").strip()
        or str(info.get("primary_ip") or "").strip()
    )
    master_port = (
        _env("MASTER_SERVER_INTERNAL_PORT")
        or str(info.get("master_server_port") or "").strip()
    )
    if not master_port:
        master_port = str(_allocate_ephemeral_port())

    operations_port = _env("OPERATIONS_BIND_PORT")
    if not operations_port and operations_ctr:
        # Prefer live uvicorn listen when present; else allocate at operation time.
        uvicorn_port = _first_listen_port(info, "uvicorn", "python")
        operations_port = str(uvicorn_port) if uvicorn_port else str(_allocate_ephemeral_port())
    if not operations_port:
        operations_port = str(_allocate_ephemeral_port())

    enriched = dict(info)
    enriched.update(
        {
            "sessions_container": sessions_ctr or {},
            "rdp_container": rdp_ctr or {},
            "operations_container": operations_ctr or {},
            "master_container": master_ctr or {},
            "sessions_docker_dns_name": sessions_dns,
            "sessions_bind_host": str(info.get("primary_ip") or "").strip(),
            "sessions_bind_port": str(sessions_port),
            "rdp_docker_dns_name": rdp_dns,
            "operations_docker_dns_name": operations_dns,
            "operations_bind_port": str(operations_port),
            "master_server_internal_host": master_dns,
            "master_server_internal_port": str(master_port),
            "tor_available": bool(info.get("bins", {}).get("tor"))
            or bool(info.get("tor_listen")),
            "docker_network_available": bool(str(info.get("docker_network_name") or "").strip()),
            "hostname_resolved": socket.gethostname(),
        }
    )
    return enriched


def pull_sessions_hardware(
    *, bind_environ: bool = True, overwrite: bool = False
) -> dict[str, Any]:
    """
    Pull live hardware facts (IP, MAC, paths, DockerDNS) at script/container run.
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
    """Bind os.environ from pulled hardware for the sessions container."""
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=False)
    bound = bind_operation_environ(info, overwrite=overwrite)

    mapping: dict[str, str] = {
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_PRIMARY_MAC_NORMALIZED": _normalize_mac(str(info["primary_mac"])),
        "SESSIONS_BIND_HOST": str(info.get("sessions_bind_host") or info["primary_ip"]),
        "SESSIONS_BIND_PORT": str(info.get("sessions_bind_port") or ""),
        "SESSIONS_DOCKER_DNS_NAME": str(info.get("sessions_docker_dns_name") or ""),
        "MASTER_SERVER_INTERNAL_HOST": str(info.get("master_server_internal_host") or ""),
        "MASTER_SERVER_INTERNAL_PORT": str(info.get("master_server_internal_port") or ""),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
    }
    if info.get("rdp_docker_dns_name"):
        mapping["RDP_DOCKER_DNS_NAME"] = str(info["rdp_docker_dns_name"])
    if info.get("operations_docker_dns_name"):
        mapping["OPERATIONS_DOCKER_DNS_NAME"] = str(info["operations_docker_dns_name"])
    if info.get("operations_bind_port"):
        mapping["OPERATIONS_BIND_PORT"] = str(info["operations_bind_port"])
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
    if info.get("secrets_dir"):
        mapping["SECRETS_DIR"] = str(info["secrets_dir"])
        mapping["SESSIONS_SECRETS_FILE"] = str(
            Path(str(info["secrets_dir"])) / (
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
        raise RuntimeError("HOST_PRIMARY_MAC missing — must be pulled at time of operation")
    return mac


def live_primary_ip() -> str:
    info = get_sessions_pull()
    ip_addr = str(info.get("primary_ip") or _env("HOST_PRIMARY_IP")).strip()
    if not ip_addr:
        raise RuntimeError("HOST_PRIMARY_IP missing — must be pulled at time of operation")
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
