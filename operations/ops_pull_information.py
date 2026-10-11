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
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

OPERATIONS_DIR = Path(__file__).resolve().parent

_LAST_PULL: dict[str, Any] = {}


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _which(name: str) -> str:
    found = shutil.which(name)
    return found or ""


def secrets_dir_path() -> Path:
    root = _env("LUCID_TOPS_ROOT")
    if root:
        return Path(root).expanduser() / "Server" / "Secrets"
    return Path("/mnt/myssd/LucidTops/Server/Secrets")


SECRETS_DIR_PATH = secrets_dir_path()


def _allocate_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _normalize_mac(mac: str) -> str:
    return "".join(ch for ch in mac.upper() if ch.isalnum())


def _pull_linux_interfaces() -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    sys_net = Path("/sys/class/net")
    if not sys_net.is_dir():
        return interfaces
    for iface in sorted(sys_net.iterdir()):
        name = iface.name
        if name.startswith("lo"):
            continue
        try:
            mac = (iface / "address").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if not mac or mac == "00:00:00:00:00:00":
            continue
        ipv4 = ""
        result = _run(["ip", "-4", "-o", "addr", "show", "dev", name])
        if result.returncode == 0 and result.stdout:
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                ipv4 = match.group(1)
        interfaces.append({"name": name, "mac": mac, "ipv4": ipv4})
    return interfaces


def _match_container(
    containers: dict[str, dict[str, str]], *needles: str
) -> dict[str, str] | None:
    for needle in needles:
        needle_l = needle.lower()
        for key, meta in containers.items():
            if needle_l in key:
                return meta
    return None


def _pull_docker_containers() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    docker_bin = _which("docker")
    if not docker_bin:
        return [], {}
    networks: list[dict[str, str]] = []
    net_result = _run([docker_bin, "network", "ls", "--format", "{{.Name}}"])
    if net_result.returncode == 0:
        for line in net_result.stdout.splitlines():
            name = line.strip()
            if name:
                networks.append({"name": name})
    containers: dict[str, dict[str, str]] = {}
    ps_result = _run([docker_bin, "ps", "--format", "{{.Names}}"])
    if ps_result.returncode != 0:
        return networks, containers
    for name in ps_result.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        inspect_result = _run(
            [
                docker_bin,
                "inspect",
                "-f",
                "{{range $net, $conf := .NetworkSettings.Networks}}{{$net}}={{$conf.IPAddress}} {{end}}",
                name,
            ]
        )
        ip_addr = ""
        net_name = ""
        if inspect_result.returncode == 0:
            chunk = inspect_result.stdout.strip().split()
            if chunk:
                net_name, _, ip_addr = chunk[0].partition("=")
        containers[name.lower()] = {
            "name": name,
            "ip": ip_addr.strip(),
            "network": net_name.strip(),
        }
    return networks, containers


def _secret_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    prefix = f"{key}="
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped.split("=", 1)[1].strip()
    except OSError:
        return ""
    return ""


def pull_realworld_information() -> dict[str, Any]:
    """Pull IP and MAC from the live interfaces. Docker facts are included when docker is present."""
    interfaces = _pull_linux_interfaces()
    if not interfaces:
        raise RuntimeError(
            "pull_realworld_information failed — no network interfaces with IP/MAC on hardware"
        )
    primary = next((row for row in interfaces if row.get("ipv4")), interfaces[0])
    primary_ip = primary.get("ipv4") or ""
    primary_mac = primary.get("mac") or ""
    if not primary_ip:
        raise RuntimeError(
            "pull_realworld_information failed — primary IPv4 not present on hardware"
        )
    if not primary_mac:
        raise RuntimeError(
            "pull_realworld_information failed — primary MAC not present on hardware"
        )

    lucid_root = Path(_env("LUCID_TOPS_ROOT") or "/mnt/myssd/LucidTops").expanduser()
    secrets_dir = secrets_dir_path()
    operations_secrets = Path(
        _env("OPERATIONS_SECRETS_FILE") or (secrets_dir / "operations.secrets").as_posix()
    ).expanduser()
    networks, containers = _pull_docker_containers()
    docker_network_name = _env("DOCKER_NETWORK_NAME") or _secret_value(
        operations_secrets, "DOCKER_NETWORK_NAME"
    )
    if not docker_network_name:
        for net in networks:
            name = str(net.get("name") or "")
            if "lucid" in name.lower():
                docker_network_name = name
                break

    pulled: dict[str, Any] = {
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "bins": {"docker": _which("docker"), "tor": _which("tor")},
        "listening": {},
        "docker_networks": networks,
        "docker_containers": containers,
        "docker_network_name": docker_network_name,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": secrets_dir.as_posix(),
        "proxy_backend_dns": _secret_value(operations_secrets, "PROXY_BACKEND_DNS"),
        "master_server_bind_host": _env("OPERATIONS_BIND_HOST") or primary_ip,
    }
    global _LAST_PULL
    _LAST_PULL = pulled
    return pulled


def get_last_pull() -> dict[str, Any]:
    return dict(_LAST_PULL) if _LAST_PULL else pull_realworld_information()


def bind_operation_environ(
    pull: dict[str, Any] | None = None, *, overwrite: bool = False
) -> dict[str, str]:
    """Bind pulled host facts. Caller restores the in-image SECRETS_DIR afterwards."""
    info = pull if pull is not None else pull_realworld_information()
    bound: dict[str, str] = {}
    mapping: dict[str, str] = {
        "LUCID_TOPS_ROOT": str(info.get("lucid_tops_root") or ""),
        "SECRETS_DIR": str(info.get("secrets_dir") or ""),
        "HOST_PRIMARY_IP": str(info.get("primary_ip") or ""),
        "HOST_PRIMARY_MAC": str(info.get("primary_mac") or ""),
    }
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
    if info.get("proxy_backend_dns"):
        mapping["PROXY_BACKEND_DNS"] = str(info["proxy_backend_dns"])
    for key, value in mapping.items():
        if not value:
            continue
        if overwrite or not _env(key):
            os.environ[key] = value
            bound[key] = value
    return bound


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

    secrets_dir = Path(
        _env("SECRETS_DIR") or str(info.get("secrets_dir") or "")
    ).expanduser()
    if not str(secrets_dir):
        lucid_root = Path(str(info.get("lucid_tops_root") or "")).expanduser()
        secrets_dir = lucid_root / "Server" / "Secrets"
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
            "tor_available": bool(info.get("bins", {}).get("tor")),
            "docker_network_available": bool(
                str(info.get("docker_network_name") or "").strip()
            ),
        }
    )
    return enriched


def bind_operations_environ(
    pull: dict[str, Any] | None = None, *, overwrite: bool = False
) -> dict[str, str]:
    """Bind hardware env. Never relocates OPERATIONS_SECRETS_FILE off the in-image path."""
    info = pull if pull is not None else pull_operations_hardware(bind_environ=False)
    preserved_dir = _env("SECRETS_DIR")
    preserved_file = _env("OPERATIONS_SECRETS_FILE")
    parent_info = dict(info)
    parent_info["secrets_dir"] = secrets_dir_path().as_posix()
    bound = bind_operation_environ(parent_info, overwrite=overwrite)
    if preserved_dir:
        os.environ["SECRETS_DIR"] = preserved_dir
        bound["SECRETS_DIR"] = preserved_dir
    if preserved_file:
        os.environ["OPERATIONS_SECRETS_FILE"] = preserved_file
        bound["OPERATIONS_SECRETS_FILE"] = preserved_file

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
        if key in {"SECRETS_DIR", "OPERATIONS_SECRETS_FILE"}:
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
