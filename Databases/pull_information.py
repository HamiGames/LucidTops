"""Pull real-world hardware and runtime content at time of operation for Databases.

At time of operation = when this script/module is run.
Values (IP, MAC, hostname, mounts, DockerDNS, listeners) MUST come from live hardware —
never placeholders, never git, never baked image defaults.

Seed sources (Proxy Bootstrap → Server/Secrets, read-only for Databases):
- /mnt/myssd/LucidTops/Server/Secrets/Master.secrets
- /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets (also Proxy.secrets)

Write target (Databases container secrets):
- /mnt/myssd/LucidTops/Databases/secrets/databases.secrets
- /mnt/myssd/LucidTops/Databases/secrets/mongodb.secrets

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
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

DATABASES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DATABASES_DIR.parent

_LAST_PULL: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def require_env(key: str) -> str:
    value = _env(key)
    if not value:
        raise RuntimeError(
            f"{key} missing — must be set at time of operation from hardware pull or secrets"
        )
    return value


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
    for name in ("proxy.secrets", "Proxy.secrets"):
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve()
    return (directory / "proxy.secrets").resolve()


def databases_write_secrets_dir(lucid_root: Path | None = None) -> Path:
    """Databases write target — never Server/Secrets."""
    root = lucid_root if lucid_root is not None else resolve_lucid_tops_root()
    override = _env("SECRETS_DIR")
    if override:
        path = Path(override).expanduser().resolve()
        parts_lower = {part.lower() for part in path.parts}
        if "server" in parts_lower and path.name.lower() == "secrets":
            return (root / "Databases" / "secrets").resolve()
        return path
    return (root / "Databases" / "secrets").resolve()


def load_master_and_proxy_seed(lucid_root: Path | None = None) -> dict[str, str]:
    """
    Load DockerDNS / network / master / Tor facts from Server/Secrets.

    Master.secrets is the Proxy-synced canonical set; proxy.secrets fills gaps.
    """
    root = lucid_root if lucid_root is not None else resolve_lucid_tops_root()
    proxy_loaded = _parse_secrets_file(proxy_secrets_path(root))
    master_loaded = _parse_secrets_file(master_secrets_path(root))
    merged: dict[str, str] = dict(proxy_loaded)
    for key, value in master_loaded.items():
        if value:
            merged[key] = value
    for key, value in proxy_loaded.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def map_seed_to_databases_keys(seed: dict[str, str]) -> dict[str, str]:
    """Map Master/proxy keys onto Databases secrets key names."""
    mapped = dict(seed)
    aliases: tuple[tuple[str, str], ...] = (
        ("PROXY_BACKEND_DNS", "MASTER_SERVER_INTERNAL_HOST"),
        ("MASTER_SERVER_PORT", "MASTER_SERVER_INTERNAL_PORT"),
        ("HARDWARE_PRIMARY_IP", "HOST_PRIMARY_IP"),
        ("HARDWARE_PRIMARY_MAC", "HOST_PRIMARY_MAC"),
        ("HARDWARE_MACHINE_ID", "HOST_MACHINE_ID"),
        ("HOSTNAME_CONSOLE", "HOST_HOSTNAME"),
        ("DOCKER_NETWORK_NAME", "DOCKER_NETWORK_NAME"),
        ("DOCKER_NETWORK_TOR_DB", "DOCKER_NETWORK_TOR_DB"),
        ("DOCKER_NETWORK_NONTOR_DB", "DOCKER_NETWORK_NONTOR_DB"),
        ("TOR_SOCKS_HOST", "TOR_SOCKS_HOST"),
        ("TOR_SOCKS_PORT", "TOR_SOCKS_PORT"),
        ("TOR_SOCKS_USERNAME", "TOR_SOCKS_USERNAME"),
        ("TOR_SOCKS_PASSWORD", "TOR_SOCKS_PASSWORD"),
        ("MONGODB_IMAGE", "MONGODB_IMAGE"),
        ("MONGODB_PORT", "MONGODB_CONTAINER_PORT"),
        ("MONGODB_DATA_MOUNT", "MONGODB_DATA_MOUNT"),
        ("LUCID_DATABASES_DIR", "LUCID_DATABASES_DIR"),
    )
    for src, dst in aliases:
        value = seed.get(src, "").strip()
        if value and not mapped.get(dst):
            mapped[dst] = value
    return mapped


def resolve_db_networks_from_seed(
    seed: dict[str, str],
    *,
    machine_id: str,
    hostname: str,
    existing: list[dict[str, str]],
) -> tuple[str, str, str]:
    """
    Resolve primary LucidDNS + tor/nontor DB networks from Master/proxy seed.

    Prefer explicit TOR/NONTOR keys, then DOCKER_NETWORK_NAMES hints, then
    DOCKER_NETWORK_NAME for both zones so DB containers join Proxy's network.
    """
    primary = (
        _env("DOCKER_NETWORK_NAME")
        or seed.get("DOCKER_NETWORK_NAME", "").strip()
    )
    tor = (
        _env("DOCKER_NETWORK_TOR_DB")
        or seed.get("DOCKER_NETWORK_TOR_DB", "").strip()
    )
    nontor = (
        _env("DOCKER_NETWORK_NONTOR_DB")
        or seed.get("DOCKER_NETWORK_NONTOR_DB", "").strip()
    )
    extras = [
        item.strip()
        for item in (seed.get("DOCKER_NETWORK_NAMES", "") or "").split(",")
        if item.strip()
    ]
    for name in extras:
        compact = name.lower().replace("-", "").replace("_", "")
        if not tor and ("tordb" in compact or "torzone" in compact):
            tor = name
        if not nontor and ("nontor" in compact or "cleardb" in compact):
            nontor = name
    if not primary:
        raise RuntimeError(
            "DOCKER_NETWORK_NAME missing from Server/Secrets/Master.secrets "
            "(or proxy.secrets) — run Proxy/Bootstrap.py before Databases"
        )
    if not tor:
        tor = primary
    if not nontor:
        nontor = primary
    # If env forced invent-style names earlier, still prefer seed primary for empty.
    if not tor:
        tor = _network_name_from_hardware(
            prefix_env="DOCKER_NETWORK_TOR_DB",
            machine_id=machine_id,
            hostname=hostname,
            existing=existing,
        )
    if not nontor:
        nontor = _network_name_from_hardware(
            prefix_env="DOCKER_NETWORK_NONTOR_DB",
            machine_id=machine_id,
            hostname=hostname,
            existing=existing,
        )
    return primary, tor, nontor


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


def allocate_ephemeral_port() -> int:
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

    for parent in [DATABASES_DIR, *DATABASES_DIR.parents]:
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
                    {
                        "name": parts[0],
                        "driver": parts[1],
                        "id": parts[2] if len(parts) > 2 else "",
                    }
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


def _network_name_from_hardware(
    *,
    prefix_env: str,
    machine_id: str,
    hostname: str,
    existing: list[dict[str, str]],
) -> str:
    """Resolve Docker network name from env or existing lucid nets; else create from hardware ids."""
    configured = _env(prefix_env)
    if configured:
        return configured
    for net in existing:
        name = str(net.get("name") or "")
        needle = prefix_env.lower().replace("docker_network_", "").replace("_", "")
        if needle and needle in name.lower().replace("-", "").replace("_", ""):
            return name
    short = (machine_id or hostname or uuid.uuid4().hex)[:12].lower()
    suffix = prefix_env.lower().replace("docker_network_", "").replace("_", "-")
    return f"lucid-{suffix}-{short}"


def pull_realworld_information() -> dict[str, Any]:
    """
    Pull real-world hardware and runtime content at time of operation.
    Seeds DockerDNS / network / master / Tor endpoints from Master.secrets + proxy.secrets.
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
    listening = _pull_listening_by_process()
    docker_state = _pull_docker_state(docker_bin)
    lucid_root = _pull_lucid_tops_root()
    seed = map_seed_to_databases_keys(load_master_and_proxy_seed(lucid_root))
    write_secrets_dir = databases_write_secrets_dir(lucid_root)
    write_secrets_dir.mkdir(parents=True, exist_ok=True)
    databases_dir = _pull_databases_dir(lucid_root)
    machine_id = _pull_machine_id()
    cpu_count = os.cpu_count() or 1

    tor_listen = _first_listen(listening, "tor")
    nginx_listen = _first_listen(listening, "nginx")
    uvicorn_listen = _first_listen(listening, "uvicorn", "python")
    mongo_listen = _first_listen(listening, "mongod", "mongo")

    containers = docker_state.get("containers", {})
    networks = docker_state.get("networks", [])
    master_ctr = _match_container(containers, "master", "backend", "lucid-server")

    docker_network_name, tor_db_network, nontor_db_network = resolve_db_networks_from_seed(
        seed,
        machine_id=machine_id,
        hostname=hostname,
        existing=networks,
    )

    master_bind_host = (
        _env("MASTER_SERVER_BIND_HOST")
        or seed.get("MASTER_SERVER_INTERNAL_HOST", "").strip()
        or seed.get("PROXY_BACKEND_DNS", "").strip()
        or primary_ip
    )
    master_port = (
        _env("MASTER_SERVER_PORT")
        or _env("MASTER_SERVER_INTERNAL_PORT")
        or seed.get("MASTER_SERVER_INTERNAL_PORT", "").strip()
        or seed.get("MASTER_SERVER_PORT", "").strip()
    )
    if not master_port and uvicorn_listen:
        master_port = str(uvicorn_listen[1])
    if not master_port:
        raise RuntimeError(
            "MASTER_SERVER_PORT / MASTER_SERVER_INTERNAL_PORT missing from "
            "Server/Secrets/Master.secrets (or proxy.secrets) — run Proxy/Bootstrap.py first"
        )

    proxy_backend_dns = (
        _env("PROXY_BACKEND_DNS")
        or seed.get("PROXY_BACKEND_DNS", "").strip()
        or seed.get("MASTER_SERVER_INTERNAL_HOST", "").strip()
    )
    if not proxy_backend_dns and master_ctr:
        proxy_backend_dns = master_ctr.get("name") or ""

    mongodb_image = (
        _env("MONGODB_IMAGE")
        or seed.get("MONGODB_IMAGE", "").strip()
    )
    mongodb_container_port = (
        _env("MONGODB_CONTAINER_PORT")
        or seed.get("MONGODB_CONTAINER_PORT", "").strip()
        or seed.get("MONGODB_PORT", "").strip()
    )
    if not mongodb_container_port and mongo_listen:
        mongodb_container_port = str(mongo_listen[1])

    compose_dir = Path(databases_dir) / "compose"
    compose_dir.mkdir(parents=True, exist_ok=True)

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
            "nginx": _which("nginx"),
            "tor": _which("tor"),
            "systemctl": _which("systemctl"),
            "docker_compose": _which("docker-compose") or "",
        },
        "listening": listening,
        "tor_listen": tor_listen,
        "nginx_listen": nginx_listen,
        "uvicorn_listen": uvicorn_listen,
        "mongo_listen": mongo_listen,
        "docker_networks": networks,
        "docker_containers": containers,
        "docker_network_name": docker_network_name,
        "docker_network_tor_db": tor_db_network,
        "docker_network_nontor_db": nontor_db_network,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": write_secrets_dir.as_posix(),
        "server_secrets_dir": server_secrets_dir(lucid_root).as_posix(),
        "master_secrets_file": master_secrets_path(lucid_root).as_posix(),
        "proxy_secrets_file": proxy_secrets_path(lucid_root).as_posix(),
        "master_proxy_seed": seed,
        "databases_dir": databases_dir.as_posix(),
        "compose_dir": compose_dir.as_posix(),
        "mongodb_image": mongodb_image,
        "mongodb_container_port": mongodb_container_port,
        "master_server_bind_host": master_bind_host,
        "master_server_port": master_port,
        "proxy_backend_dns": proxy_backend_dns,
        "platform": platform.platform(),
        "system": platform.system(),
    }
    global _LAST_PULL
    _LAST_PULL = pulled
    return pulled


def get_last_pull() -> dict[str, Any]:
    return dict(_LAST_PULL) if _LAST_PULL else pull_realworld_information()


def bind_operation_environ(
    pull: dict[str, Any] | None = None, *, overwrite: bool = False
) -> dict[str, str]:
    """
    Configure os.environ from Master/proxy seed + pulled hardware facts.
    Only fills missing keys unless overwrite=True. Never invents placeholders.
    """
    info = pull if pull is not None else pull_realworld_information()
    bound: dict[str, str] = {}
    seed = map_seed_to_databases_keys(
        info.get("master_proxy_seed")
        if isinstance(info.get("master_proxy_seed"), dict)
        else load_master_and_proxy_seed(resolve_lucid_tops_root(info))
    )

    mapping: dict[str, str] = {
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "SERVER_SECRETS_DIR": str(
            info.get("server_secrets_dir") or server_secrets_dir(resolve_lucid_tops_root(info))
        ),
        "SERVER_ENV_FILE": str(Path(str(info["lucid_tops_root"])) / "server.env"),
        "SECRETS_ENV_FILE": str(Path(str(info["lucid_tops_root"])) / "secrets.env"),
        "MONGODB_DATA_MOUNT": str(info["databases_dir"]),
        "LUCID_DATABASES_DIR": str(info["databases_dir"]),
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "HOST_HOSTNAME": str(info["hostname"]),
        "DOCKER_NETWORK_TOR_DB": str(info["docker_network_tor_db"]),
        "DOCKER_NETWORK_NONTOR_DB": str(info["docker_network_nontor_db"]),
        "DATABASES_COMPOSE_DIR": str(info["compose_dir"]),
        "MASTER_SECRETS_FILE": str(
            info.get("master_secrets_file") or master_secrets_path(resolve_lucid_tops_root(info))
        ),
        "PROXY_SECRETS_FILE": str(
            info.get("proxy_secrets_file") or proxy_secrets_path(resolve_lucid_tops_root(info))
        ),
    }

    if info.get("master_server_bind_host"):
        mapping["MASTER_SERVER_BIND_HOST"] = str(info["master_server_bind_host"])
        mapping["MASTER_SERVER_HOST"] = str(info["master_server_bind_host"])
        mapping["MASTER_SERVER_INTERNAL_HOST"] = str(info["master_server_bind_host"])
    if info.get("master_server_port"):
        mapping["MASTER_SERVER_PORT"] = str(info["master_server_port"])
        mapping["MASTER_SERVER_INTERNAL_PORT"] = str(info["master_server_port"])
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
    if info.get("proxy_backend_dns"):
        mapping["PROXY_BACKEND_DNS"] = str(info["proxy_backend_dns"])
        mapping["MASTER_SERVER_INTERNAL_HOST"] = str(info["proxy_backend_dns"])
        mapping["DNS_BACKEND_SERVICE_NAME"] = str(info["proxy_backend_dns"])
    if info.get("mongodb_image"):
        mapping["MONGODB_IMAGE"] = str(info["mongodb_image"])
    if info.get("mongodb_container_port"):
        mapping["MONGODB_CONTAINER_PORT"] = str(info["mongodb_container_port"])

    for key in (
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "TOR_SOCKS_USERNAME",
        "TOR_SOCKS_PASSWORD",
        "DOCKER_NETWORK_NAMES",
        "MONGODB_URL",
        "MONGODB_MAIN_DATABASE_NAME",
        "MASTER_SERVER_ONION",
    ):
        value = seed.get(key, "").strip()
        if value:
            mapping[key] = value

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
    }
    for key, path in file_map.items():
        mapping[key] = path.as_posix()

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        resolved = str(value).strip()
        if overwrite or not _env(key):
            os.environ[key] = resolved
        # Always include resolved value for shell export (even if env already set).
        bound[key] = _env(key) or resolved
    return bound


def export_shell_env(
    pull: dict[str, Any] | None = None, *, overwrite: bool = True
) -> str:
    """Emit POSIX export lines for entrypoint sourcing at operation time."""
    bound = bind_operation_environ(pull, overwrite=overwrite)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    info = pull_realworld_information()
    print(export_shell_env(info, overwrite=True), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
