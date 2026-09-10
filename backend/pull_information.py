"""Pull real-world hardware and runtime content at time of operation for MasterServer.

At time of operation = when this script/module is run.
Values (IP, MAC, hostname, mounts, DockerDNS, listeners) MUST come from live hardware —
never placeholders, never git, never baked image defaults.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

_LAST_PULL: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _allocate_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _pull_linux_interfaces() -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    sys_net = Path("/sys/class/net")
    if not sys_net.is_dir():
        return interfaces
    for iface in sorted(sys_net.iterdir()):
        name = iface.name
        if name.startswith("lo"):
            continue
        mac = ""
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


def _pull_windows_interfaces() -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    ps = _which("powershell") or _which("pwsh")
    if not ps:
        return interfaces
    script = (
        "Get-NetIPConfiguration | ForEach-Object {"
        " $mac=$_.NetAdapter.MacAddress; $ip=$_.IPv4Address.IPAddress;"
        " if($mac -and $ip){"
        "  [PSCustomObject]@{name=$_.InterfaceAlias;mac=$mac;ipv4=$ip}"
        " } } | ConvertTo-Json -Compress"
    )
    result = _run([ps, "-NoProfile", "-Command", script])
    if result.returncode != 0 or not result.stdout.strip():
        return interfaces
    try:
        loaded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return interfaces
    rows = loaded if isinstance(loaded, list) else [loaded]
    for row in rows:
        if not isinstance(row, dict):
            continue
        mac = str(row.get("mac") or "").strip().lower().replace("-", ":")
        ipv4 = str(row.get("ipv4") or "").strip()
        name = str(row.get("name") or "").strip()
        if mac and ipv4:
            interfaces.append({"name": name, "mac": mac, "ipv4": ipv4})
    return interfaces


def _pull_interfaces() -> list[dict[str, str]]:
    system = platform.system().lower()
    if system == "windows":
        pulled = _pull_windows_interfaces()
    else:
        pulled = _pull_linux_interfaces()
    if pulled:
        return pulled
    ip_addr = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((socket.gethostbyname(socket.gethostname()), 1))
            ip_addr = sock.getsockname()[0]
    except OSError:
        try:
            ip_addr = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip_addr = ""
    node = uuid.getnode()
    mac = ":".join(f"{(node >> ele) & 0xFF:02x}" for ele in range(40, -1, -8))
    if ip_addr or mac:
        return [{"name": "primary", "mac": mac, "ipv4": ip_addr}]
    return []


def _pull_machine_id() -> str:
    for candidate in (
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
    ):
        try:
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return uuid.uuid4().hex


def _pull_mount_roots() -> list[Path]:
    roots: list[Path] = []
    if Path("/proc/mounts").exists():
        try:
            for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount = Path(parts[1])
                if mount.is_dir():
                    roots.append(mount)
        except OSError:
            pass
    if platform.system().lower() == "windows":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:/")
            if drive.exists():
                roots.append(drive)
    roots.append(Path.home())
    roots.append(PROJECT_ROOT)
    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        key = root.as_posix()
        if key not in seen:
            seen.add(key)
            ordered.append(root)
    return ordered


def _pull_lucid_tops_root() -> Path:
    """Discover LucidTops root on mounted hardware / existing tree at operation time."""
    env_root = _env("LUCID_TOPS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    for mount in _pull_mount_roots():
        for candidate in (
            mount / "LucidTops",
            mount / "myssd" / "LucidTops",
            mount / "Server" / "LucidTops",
            mount / "LucidTops" / "Server",
        ):
            if candidate.is_dir():
                return candidate.resolve()
        try:
            for child in mount.iterdir():
                if child.is_dir() and child.name.lower() == "lucidtops":
                    return child.resolve()
        except OSError:
            continue

    for parent in [BACKEND_DIR, *BACKEND_DIR.parents]:
        secrets_probe = parent / "Secrets"
        secrets_probe_alt = parent / "Server" / "Secrets"
        lucid_probe = parent / "LucidTops"
        if secrets_probe.is_dir() or secrets_probe_alt.is_dir():
            return parent.resolve()
        if lucid_probe.is_dir():
            return lucid_probe.resolve()
        if (parent / "proxy").is_dir() and (parent / "backend").is_dir():
            data = parent / "LucidTops"
            data.mkdir(parents=True, exist_ok=True)
            return data.resolve()

    created = Path.home() / "LucidTops"
    created.mkdir(parents=True, exist_ok=True)
    return created.resolve()


def _pull_secrets_dir(lucid_root: Path) -> Path:
    env_secrets = _env("SECRETS_DIR")
    if env_secrets:
        return Path(env_secrets).expanduser().resolve()
    candidates = [
        lucid_root / "Server" / "Secrets",
        lucid_root / "secrets",
        lucid_root / "Secrets",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    chosen = candidates[0]
    chosen.mkdir(parents=True, exist_ok=True)
    return chosen.resolve()


def _pull_databases_dir(lucid_root: Path) -> Path:
    env_db = _env("MONGODB_DATA_MOUNT") or _env("LUCID_DATABASES_DIR")
    if env_db:
        path = Path(env_db).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    candidates = [
        lucid_root / "Server" / "Databases",
        lucid_root / "Databases",
        lucid_root / "data" / "mongodb",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    chosen = candidates[0]
    chosen.mkdir(parents=True, exist_ok=True)
    return chosen.resolve()


def _pull_listening_by_process() -> dict[str, list[tuple[str, int]]]:
    mapping: dict[str, list[tuple[str, int]]] = {}
    ss_bin = _which("ss")
    if ss_bin:
        result = _run([ss_bin, "-lntup"])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "LISTEN" not in line.upper() and "tcp" not in line.lower():
                    continue
                addr_match = re.search(r"([0-9a-fA-F\.:]+|\*):([0-9]+)\s", line)
                proc_match = re.search(r'"([^"]+)"', line) or re.search(
                    r"users:\(\(([^,]+)", line
                )
                if not addr_match:
                    continue
                host, port_s = addr_match.group(1), addr_match.group(2)
                try:
                    port = int(port_s)
                except ValueError:
                    continue
                if host in {"*", "::", "[::]"}:
                    host = ""
                proc = (proc_match.group(1) if proc_match else "").lower()
                proc = proc.replace('"', "").split("/")[-1]
                if not proc:
                    continue
                mapping.setdefault(proc, []).append((host, port))
            return mapping

    if platform.system().lower() == "windows":
        ps = _which("powershell") or _which("pwsh")
        if ps:
            script = (
                "Get-NetTCPConnection -State Listen | ForEach-Object {"
                " $p=Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;"
                " if($p){[PSCustomObject]@{proc=$p.ProcessName;addr=$_.LocalAddress;port=$_.LocalPort}}"
                "} | ConvertTo-Json -Compress"
            )
            result = _run([ps, "-NoProfile", "-Command", script])
            if result.returncode == 0 and result.stdout.strip():
                try:
                    loaded = json.loads(result.stdout)
                except json.JSONDecodeError:
                    loaded = []
                rows = loaded if isinstance(loaded, list) else [loaded]
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    proc = str(row.get("proc") or "").lower()
                    addr = str(row.get("addr") or "")
                    port_raw = row.get("port")
                    if port_raw is None:
                        continue
                    try:
                        port = int(port_raw)
                    except (TypeError, ValueError):
                        continue
                    if proc:
                        mapping.setdefault(proc, []).append((addr, port))
    return mapping


def _first_listen(
    listening: dict[str, list[tuple[str, int]]], *proc_names: str
) -> tuple[str, int] | None:
    for name in proc_names:
        for key, entries in listening.items():
            if name in key:
                for host, port in entries:
                    return (host, port)
    return None


def _pull_docker_state(docker_bin: str) -> dict[str, Any]:
    networks: list[dict[str, str]] = []
    containers: dict[str, dict[str, str]] = {}
    if not docker_bin:
        return {"networks": networks, "containers": containers}

    net_ls = _run([docker_bin, "network", "ls", "--format", "{{.Name}}\t{{.Driver}}\t{{.ID}}"])
    if net_ls.returncode == 0:
        for line in net_ls.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0]:
                networks.append(
                    {"name": parts[0], "driver": parts[1], "id": parts[2] if len(parts) > 2 else ""}
                )

    ps = _run([docker_bin, "ps", "-a", "--format", "{{.Names}}\t{{.ID}}"])
    if ps.returncode != 0:
        return {"networks": networks, "containers": containers}

    for line in ps.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 1 or not parts[0].strip():
            continue
        name = parts[0].strip()
        inspect = _run(
            [
                docker_bin,
                "inspect",
                "-f",
                "{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}};{{end}}",
                name,
            ]
        )
        ip_addr = ""
        net_name = ""
        if inspect.returncode == 0 and inspect.stdout.strip():
            for chunk in inspect.stdout.strip().split(";"):
                if "=" not in chunk:
                    continue
                net_name, _, ip_addr = chunk.partition("=")
                if ip_addr.strip():
                    ip_addr = ip_addr.strip()
                    break
        containers[name.lower()] = {
            "name": name,
            "ip": ip_addr,
            "network": net_name.strip(),
        }
    return {"networks": networks, "containers": containers}


def _match_container(
    containers: dict[str, dict[str, str]], *needles: str
) -> dict[str, str] | None:
    for needle in needles:
        needle_l = needle.lower()
        for key, meta in containers.items():
            if needle_l in key:
                return meta
    return None


def pull_realworld_information() -> dict[str, Any]:
    """
    Pull real-world hardware and runtime content at time of operation.
    Source of truth for IP, MAC, hostname, DockerDNS endpoints, listeners, binaries, paths.
    """
    hostname = socket.gethostname()
    interfaces = _pull_interfaces()
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

    docker_bin = _which("docker")
    nginx_bin = _which("nginx")
    tor_bin = _which("tor")
    systemctl_bin = _which("systemctl")

    listening = _pull_listening_by_process()
    docker_state = _pull_docker_state(docker_bin)
    lucid_root = _pull_lucid_tops_root()
    secrets_dir = _pull_secrets_dir(lucid_root)
    databases_dir = _pull_databases_dir(lucid_root)
    machine_id = _pull_machine_id()
    cpu_count = os.cpu_count() or 1

    tor_listen = _first_listen(listening, "tor")
    nginx_listen = _first_listen(listening, "nginx")
    uvicorn_listen = _first_listen(listening, "uvicorn", "python")
    mongo_listen = _first_listen(listening, "mongod", "mongo")

    containers = docker_state.get("containers", {})
    mongo_ctr = _match_container(containers, "mongo", "mongodb")
    master_ctr = _match_container(containers, "master", "backend", "lucid-server")
    proxy_ctr = _match_container(containers, "proxy", "lucid-proxy")

    networks = docker_state.get("networks", [])
    docker_network_name = _env("DOCKER_NETWORK_NAME")
    if not docker_network_name:
        for net in networks:
            name = str(net.get("name") or "")
            if "lucid" in name.lower():
                docker_network_name = name
                break
        if not docker_network_name and networks:
            docker_network_name = str(networks[0].get("name") or "")

    mongodb_host = _env("MONGODB_HOST")
    if not mongodb_host and mongo_ctr:
        mongodb_host = mongo_ctr.get("name") or mongo_ctr.get("ip") or ""
    mongodb_port = _env("MONGODB_PORT")
    if not mongodb_port and mongo_listen:
        mongodb_port = str(mongo_listen[1])

    master_bind_host = _env("MASTER_SERVER_BIND_HOST") or primary_ip
    master_port = _env("MASTER_SERVER_PORT")
    if not master_port and uvicorn_listen:
        master_port = str(uvicorn_listen[1])
    if not master_port:
        master_port = str(_allocate_ephemeral_port())

    proxy_backend_dns = _env("PROXY_BACKEND_DNS")
    if not proxy_backend_dns and master_ctr:
        proxy_backend_dns = master_ctr.get("name") or ""

    pulled: dict[str, Any] = {
        "pulled_at": utc_now(),
        "hostname": hostname,
        "machine_id": machine_id,
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "cpu_count": cpu_count,
        "bins": {
            "docker": docker_bin,
            "nginx": nginx_bin,
            "tor": tor_bin,
            "systemctl": systemctl_bin,
        },
        "listening": listening,
        "tor_listen": tor_listen,
        "nginx_listen": nginx_listen,
        "uvicorn_listen": uvicorn_listen,
        "mongo_listen": mongo_listen,
        "docker_networks": networks,
        "docker_containers": containers,
        "docker_network_name": docker_network_name,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": secrets_dir.as_posix(),
        "databases_dir": databases_dir.as_posix(),
        "mongodb_host": mongodb_host,
        "mongodb_port": mongodb_port,
        "master_server_bind_host": master_bind_host,
        "master_server_port": master_port,
        "proxy_backend_dns": proxy_backend_dns,
        "proxy_container": proxy_ctr,
        "platform": platform.platform(),
        "system": platform.system(),
    }
    global _LAST_PULL
    _LAST_PULL = pulled
    return pulled


def get_last_pull() -> dict[str, Any]:
    return dict(_LAST_PULL) if _LAST_PULL else pull_realworld_information()


def bind_operation_environ(pull: dict[str, Any] | None = None, *, overwrite: bool = False) -> dict[str, str]:
    """
    Configure os.environ from pulled hardware facts at time of operation.
    Only fills missing keys unless overwrite=True. Never invents placeholders.
    """
    info = pull if pull is not None else pull_realworld_information()
    bound: dict[str, str] = {}

    mapping: dict[str, str] = {
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "SERVER_ENV_FILE": str(Path(str(info["lucid_tops_root"])) / "server.env"),
        "SECRETS_ENV_FILE": str(Path(str(info["lucid_tops_root"])) / "secrets.env"),
        "MONGODB_DATA_MOUNT": str(info["databases_dir"]),
        "LUCID_DATABASES_DIR": str(info["databases_dir"]),
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "HOST_HOSTNAME": str(info["hostname"]),
    }

    if info.get("master_server_bind_host"):
        mapping["MASTER_SERVER_BIND_HOST"] = str(info["master_server_bind_host"])
        mapping["MASTER_SERVER_HOST"] = str(info["master_server_bind_host"])
    if info.get("master_server_port"):
        mapping["MASTER_SERVER_PORT"] = str(info["master_server_port"])
    if info.get("mongodb_host"):
        mapping["MONGODB_HOST"] = str(info["mongodb_host"])
    if info.get("mongodb_port"):
        mapping["MONGODB_PORT"] = str(info["mongodb_port"])
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
    if info.get("proxy_backend_dns"):
        mapping["PROXY_BACKEND_DNS"] = str(info["proxy_backend_dns"])
        mapping["MASTER_SERVER_INTERNAL_HOST"] = str(info["proxy_backend_dns"])
        mapping["DNS_BACKEND_SERVICE_NAME"] = str(info["proxy_backend_dns"])

    secrets_dir = Path(str(info["secrets_dir"]))
    file_map = {
        "SERVER_SECRETS_FILE": secrets_dir / "server.secrets",
        "CONFIG_SECRETS_FILE": secrets_dir / "config.secrets",
        "OPERATIONS_SECRETS_FILE": secrets_dir / "operations.secrets",
        "MONGODB_SECRETS_FILE": secrets_dir / "mongodb.secrets",
        "DATABASES_SECRETS_FILE": secrets_dir / "databases.secrets",
        "BLOCKCHAIN_SECRETS_FILE": secrets_dir / "blockchain.secrets",
        "PAYMENTS_SECRETS_FILE": secrets_dir / "payments.secrets",
        "BACKEND_SECRETS_FILE": secrets_dir / "backend.secrets",
        "MASTER_SECRETS_FILE": secrets_dir / "Master.secrets",
    }
    for key, path in file_map.items():
        mapping[key] = path.as_posix()

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        if overwrite or not _env(key):
            os.environ[key] = str(value).strip()
            bound[key] = str(value).strip()
    return bound


def export_shell_env(pull: dict[str, Any] | None = None) -> str:
    """Emit POSIX export lines for entrypoint sourcing at operation time."""
    bound = bind_operation_environ(pull)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    info = pull_realworld_information()
    bind_operation_environ(info)
    print(export_shell_env(info), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
