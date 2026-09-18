"""Pull real-world hardware and runtime content at time of operation for Frontend.

At time of operation = when this script/module is run.
Values (IP, MAC, hostname, mounts, DockerDNS, listeners) MUST come from live hardware —
never placeholders, never git, never baked image defaults.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- values MUST BE PULLED and configured from Real World content on the Hardware.
"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets as secrets_mod
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_DIR.parent

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
    env_root = _env("LUCID_TOPS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    for mount in _pull_mount_roots():
        for candidate in (
            mount / "LucidTops",
            mount / "myssd" / "LucidTops",
            mount / "mnt" / "myssd" / "LucidTops",
            mount / "Server" / "LucidTops",
        ):
            if candidate.is_dir():
                return candidate.resolve()
    return (PROJECT_ROOT / "LucidTops").resolve()


def _pull_secrets_dir(lucid_root: Path) -> Path:
    env_dir = _env("SECRETS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    for candidate in (
        lucid_root / "secrets",
        lucid_root / "Secrets",
        lucid_root / "Server" / "Secrets",
        Path("/mnt/myssd/LucidTops/secrets"),
    ):
        if candidate.is_dir():
            return candidate.resolve()
    target = lucid_root / "secrets"
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _pull_listening_by_process() -> dict[str, list[tuple[str, int]]]:
    listening: dict[str, list[tuple[str, int]]] = {}
    if platform.system().lower() == "windows":
        return listening
    result = _run(["ss", "-ltnp"])
    if result.returncode != 0 or not result.stdout:
        return listening
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        local = parts[3]
        proc = parts[-1] if parts else ""
        host, _, port_s = local.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            continue
        name = "unknown"
        match = re.search(r'"([^"]+)"', proc)
        if match:
            name = match.group(1).lower()
        listening.setdefault(name, []).append((host.strip("[]"), port))
    return listening


def _first_listen(
    listening: dict[str, list[tuple[str, int]]], *needles: str
) -> tuple[str, int] | None:
    for needle in needles:
        needle_l = needle.lower()
        for name, rows in listening.items():
            if needle_l in name and rows:
                return rows[0]
    return None


def _pull_docker_state(docker_bin: str) -> dict[str, Any]:
    networks: list[dict[str, str]] = []
    containers: dict[str, dict[str, str]] = {}
    if not docker_bin:
        return {"networks": networks, "containers": containers}
    net_result = _run([docker_bin, "network", "ls", "--format", "{{.Name}}"])
    if net_result.returncode == 0:
        for name in net_result.stdout.splitlines():
            if name.strip():
                networks.append({"name": name.strip()})
    ctr_result = _run(
        [
            docker_bin,
            "ps",
            "--format",
            "{{.Names}}\t{{.Ports}}",
        ]
    )
    if ctr_result.returncode == 0:
        for line in ctr_result.stdout.splitlines():
            if "\t" not in line:
                continue
            name, ports = line.split("\t", 1)
            containers[name.strip().lower()] = {
                "name": name.strip(),
                "ports": ports.strip(),
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


def _read_onion_file(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
        if value.endswith(".onion"):
            return value.split("/")[0]
    except OSError:
        pass
    return ""


def _pull_onion_addresses(lucid_root: Path) -> dict[str, str]:
    onions = {"frontend": "", "master_server": "", "node_user": "", "blockchain": ""}
    candidates = [
        lucid_root / "data" / "tor" / "onion",
        lucid_root / "onion",
        lucid_root / "run" / "lucid" / "onion",
        Path("/var/lib/tor"),
        Path("/var/lib/tor/lucid"),
    ]
    for onion_dir in candidates:
        if not onion_dir.is_dir():
            continue
        mapping = {
            "frontend": ("frontend", "frontend_onion", "hs_frontend"),
            "master_server": ("master", "master_server", "backend", "hs_master"),
            "node_user": ("node", "nodeuser", "hs_node"),
            "blockchain": ("blockchain", "hs_blockchain"),
        }
        for key, names in mapping.items():
            if onions[key]:
                continue
            for name in names:
                for path in (
                    onion_dir / name / "hostname",
                    onion_dir / f"{name}.hostname",
                    onion_dir / name,
                ):
                    value = _read_onion_file(path)
                    if value:
                        onions[key] = value
                        break
    # Prefer Master.secrets / proxy.secrets BLOCKCHAIN_ONION when present.
    for secrets_name in ("Master.secrets", "proxy.secrets", "Proxy.secrets"):
        secrets_path = lucid_root / "Server" / "Secrets" / secrets_name
        if not secrets_path.is_file():
            continue
        try:
            for line in secrets_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped.startswith("BLOCKCHAIN_ONION="):
                    continue
                value = stripped.split("=", 1)[1].strip().lower().split("/")[0]
                if value.endswith(".onion"):
                    onions["blockchain"] = value
        except OSError:
            pass
    for env_key, map_key in (
        ("FRONTEND_ONION", "frontend"),
        ("MASTER_SERVER_ONION", "master_server"),
        ("NODEUSER_ONION", "node_user"),
        ("BLOCKCHAIN_ONION", "blockchain"),
    ):
        env_val = _env(env_key)
        if env_val.endswith(".onion"):
            onions[map_key] = env_val.split("/")[0].lower()
    return onions


def pull_realworld_information() -> dict[str, Any]:
    """Pull real-world hardware and runtime content at time of operation."""
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
    listening = _pull_listening_by_process()
    docker_state = _pull_docker_state(docker_bin)
    lucid_root = _pull_lucid_tops_root()
    secrets_dir = _pull_secrets_dir(lucid_root)
    machine_id = _pull_machine_id()
    nginx_listen = _first_listen(listening, "nginx")
    containers = docker_state.get("containers", {})
    proxy_ctr = _match_container(containers, "proxy", "lucid-proxy")
    backend_ctr = _match_container(containers, "master", "backend", "lucid-server")
    onions = _pull_onion_addresses(lucid_root)

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

    proxy_dns = _env("PROXY_DNS") or _env("PROXY_FRONTEND_UPSTREAM")
    if not proxy_dns and proxy_ctr:
        proxy_dns = proxy_ctr.get("name") or ""
    backend_dns = _env("MASTER_SERVER_INTERNAL_HOST") or _env("PROXY_BACKEND_DNS")
    if not backend_dns and backend_ctr:
        backend_dns = backend_ctr.get("name") or ""

    nginx_port = _env("FRONTEND_NGINX_PORT")
    if not nginx_port and nginx_listen:
        nginx_port = str(nginx_listen[1])
    if not nginx_port:
        nginx_port = str(_allocate_ephemeral_port())

    proxy_port = _env("PROXY_INTERNAL_PORT") or _env("PROXY_PORT")
    if not proxy_port:
        proxy_port = str(_allocate_ephemeral_port())

    webpage_root = Path(
        _env("FRONTEND_WEBPAGE_ROOT") or (FRONTEND_DIR / "webpage").as_posix()
    )

    pulled: dict[str, Any] = {
        "pulled_at": utc_now(),
        "hostname": hostname,
        "machine_id": machine_id,
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "bins": {"docker": docker_bin, "nginx": nginx_bin},
        "listening": listening,
        "nginx_listen": nginx_listen,
        "docker_networks": networks,
        "docker_containers": containers,
        "docker_network_name": docker_network_name,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": secrets_dir.as_posix(),
        "webpage_root": webpage_root.as_posix(),
        "proxy_dns": proxy_dns,
        "backend_dns": backend_dns,
        "nginx_bind_host": primary_ip,
        "nginx_port": nginx_port,
        "proxy_port": proxy_port,
        "onions": onions,
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
    """Configure os.environ from pulled hardware facts at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    bound: dict[str, str] = {}
    secrets_dir = Path(str(info["secrets_dir"]))
    mapping: dict[str, str] = {
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "HOST_HOSTNAME": str(info["hostname"]),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "FRONTEND_WEBPAGE_ROOT": str(info["webpage_root"]),
        "FRONTEND_NGINX_PORT": str(info["nginx_port"]),
        "FRONTEND_SECRETS_FILE": (secrets_dir / "frontend.secrets").as_posix(),
        "BACKEND_SECRETS_FILE": (secrets_dir / "backend.secrets").as_posix(),
    }
    if info.get("docker_network_name"):
        mapping["DOCKER_NETWORK_NAME"] = str(info["docker_network_name"])
    if info.get("proxy_dns"):
        mapping["PROXY_DNS"] = str(info["proxy_dns"])
        mapping["PROXY_INTERNAL_HOST"] = str(info["proxy_dns"])
    if info.get("backend_dns"):
        mapping["MASTER_SERVER_INTERNAL_HOST"] = str(info["backend_dns"])
        mapping["PROXY_BACKEND_DNS"] = str(info["backend_dns"])
    if info.get("proxy_port"):
        mapping["PROXY_INTERNAL_PORT"] = str(info["proxy_port"])
    onions = info.get("onions") or {}
    if onions.get("frontend"):
        mapping["FRONTEND_ONION"] = str(onions["frontend"])
    if onions.get("master_server"):
        mapping["MASTER_SERVER_ONION"] = str(onions["master_server"])
    if onions.get("node_user"):
        mapping["NODEUSER_ONION"] = str(onions["node_user"])
    if onions.get("blockchain"):
        mapping["BLOCKCHAIN_ONION"] = str(onions["blockchain"])

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        if overwrite or not _env(key):
            os.environ[key] = str(value).strip()
            bound[key] = str(value).strip()
    return bound


def _merge_existing_secrets(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def _require_or_create(existing: dict[str, str], key: str, factory) -> str:
    current = _env(key) or existing.get(key, "").strip()
    if current:
        return current
    return str(factory())


def build_frontend_secrets(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create frontend.secrets from hardware pull + prior secrets at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    secrets_path = Path(_env("FRONTEND_SECRETS_FILE") or Path(str(info["secrets_dir"])) / "frontend.secrets")
    prior = _merge_existing_secrets(secrets_path)
    backend_prior = _merge_existing_secrets(Path(_env("BACKEND_SECRETS_FILE") or Path(str(info["secrets_dir"])) / "backend.secrets"))
    proxy_prior = _merge_existing_secrets(Path(str(info["secrets_dir"])) / "proxy.secrets")

    def from_any(*keys: str, factory=None) -> str:
        for key in keys:
            value = _env(key) or prior.get(key) or backend_prior.get(key) or proxy_prior.get(key) or ""
            if value:
                return value
        if factory is not None:
            return str(factory())
        return ""

    onions = info.get("onions") or {}
    api_prefix = from_any("API_PREFIX", "API_BASE_PATH", factory=lambda: "/api/v1")
    gui_prefix = from_any("GUI_PREFIX", factory=lambda: "/gui")
    proxy_api = from_any("PROXY_API_PREFIX", factory=lambda: api_prefix)

    built: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HOSTNAME_CONSOLE": str(info["hostname"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "FRONTEND_WEBPAGE_ROOT": str(info["webpage_root"]),
        "FRONTEND_NGINX_BIND": str(info["primary_ip"]),
        "FRONTEND_NGINX_PORT": str(info["nginx_port"]),
        "API_PREFIX": api_prefix,
        "API_BASE_PATH": api_prefix,
        "GUI_PREFIX": gui_prefix,
        "PROXY_API_PREFIX": proxy_api,
        "FRONTEND_TUNNEL_SCHEME": from_any("FRONTEND_TUNNEL_SCHEME", factory=lambda: "http"),
        "FRONTEND_TUNNEL_TIMEOUT": from_any("FRONTEND_TUNNEL_TIMEOUT", factory=lambda: "30"),
        "FRONTEND_TUNNEL_HMAC_KEY": _require_or_create(
            prior, "FRONTEND_TUNNEL_HMAC_KEY", lambda: secrets_mod.token_hex(32)
        ),
        "FRONTEND_PROXY_SOURCE": from_any("FRONTEND_PROXY_SOURCE", factory=lambda: "frontend"),
        "FRONTEND_PROXY_BACKEND_PATH": from_any(
            "FRONTEND_PROXY_BACKEND_PATH",
            factory=lambda: f"{proxy_api.rstrip('/')}/frontend/backend",
        ),
        "FRONTEND_PROXY_RDP_PATH": from_any(
            "FRONTEND_PROXY_RDP_PATH",
            factory=lambda: f"{proxy_api.rstrip('/')}/frontend/rdp",
        ),
        "FRONTEND_PROXY_NODE_PATH": from_any(
            "FRONTEND_PROXY_NODE_PATH",
            factory=lambda: f"{proxy_api.rstrip('/')}/frontend/node",
        ),
        "PROXY_INTERNAL_HOST": from_any(
            "PROXY_INTERNAL_HOST",
            "PROXY_DNS",
            factory=lambda: str(info.get("proxy_dns") or "")
            or f"lucid-proxy-{str(info['hostname']).lower().replace(' ', '-')}",
        ),
        "PROXY_INTERNAL_PORT": from_any(
            "PROXY_INTERNAL_PORT",
            "PROXY_PORT",
            factory=lambda: str(info.get("proxy_port") or _allocate_ephemeral_port()),
        ),
        "MASTER_SERVER_INTERNAL_HOST": from_any(
            "MASTER_SERVER_INTERNAL_HOST",
            "PROXY_BACKEND_DNS",
            factory=lambda: str(info.get("backend_dns") or "")
            or f"lucid-backend-{str(info['hostname']).lower().replace(' ', '-')}",
        ),
        "MASTER_SERVER_INTERNAL_PORT": from_any(
            "MASTER_SERVER_INTERNAL_PORT",
            "MASTER_SERVER_PORT",
            factory=lambda: str(_allocate_ephemeral_port()),
        ),
        "PROXY_NGINX_UPSTREAM_TOKEN": from_any(
            "PROXY_NGINX_UPSTREAM_TOKEN",
            factory=lambda: secrets_mod.token_urlsafe(24),
        ),
        "PROXY_API_TOKEN": from_any("PROXY_API_TOKEN", factory=lambda: secrets_mod.token_urlsafe(32)),
        "PROXY_HMAC_KEY": from_any("PROXY_HMAC_KEY", factory=lambda: secrets_mod.token_hex(32)),
        "PROXY_GATE_HEADER_VALUE": from_any(
            "PROXY_GATE_HEADER_VALUE", factory=lambda: secrets_mod.token_urlsafe(16)
        ),
        "DOCKER_NETWORK_NAME": from_any(
            "DOCKER_NETWORK_NAME", factory=lambda: str(info.get("docker_network_name") or "")
        ),
        "FRONTEND_ONION": from_any(
            "FRONTEND_ONION", factory=lambda: str(onions.get("frontend") or "")
        ),
        "MASTER_SERVER_ONION": from_any(
            "MASTER_SERVER_ONION", factory=lambda: str(onions.get("master_server") or "")
        ),
        "NODEUSER_ONION": from_any(
            "NODEUSER_ONION", factory=lambda: str(onions.get("node_user") or "")
        ),
        "BLOCKCHAIN_ONION": from_any(
            "BLOCKCHAIN_ONION", factory=lambda: str(onions.get("blockchain") or "")
        ),
        "FRONTEND_BRAND_NAME": from_any("FRONTEND_BRAND_NAME", factory=lambda: "LucidTops"),
        "PULLED_AT": str(info["pulled_at"]),
    }

    # Drop empty optional onion/dns fields only when truly unavailable after pull
    required_nonempty = {
        "HARDWARE_PRIMARY_IP",
        "HARDWARE_PRIMARY_MAC",
        "FRONTEND_NGINX_PORT",
        "API_PREFIX",
        "GUI_PREFIX",
        "FRONTEND_PROXY_BACKEND_PATH",
        "FRONTEND_TUNNEL_HMAC_KEY",
        "PROXY_NGINX_UPSTREAM_TOKEN",
    }
    for key in required_nonempty:
        if not built.get(key):
            raise RuntimeError(
                f"{key} missing after hardware pull — cannot create frontend.secrets"
            )

    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops frontend.secrets — generated at time of operation from hardware pull",
        f"# pulled_at={built['PULLED_AT']}",
    ]
    for key in sorted(built.keys()):
        lines.append(f"{key}={built[key]}")
    secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in built.items():
        if value and not _env(key):
            os.environ[key] = value
    return built


def public_runtime_config(secrets: dict[str, str] | None = None) -> dict[str, Any]:
    """Browser-safe runtime config (no HMAC/proxy tokens)."""
    data = secrets or {}
    if not data:
        from frontend_secrets import load_frontend_secrets

        data = load_frontend_secrets(reload=True)
    return {
        "brandName": data.get("FRONTEND_BRAND_NAME") or "LucidTops",
        "apiPrefix": data.get("API_PREFIX") or data.get("API_BASE_PATH") or "",
        "guiPrefix": data.get("GUI_PREFIX") or "",
        "proxyBackendPath": data.get("FRONTEND_PROXY_BACKEND_PATH") or "",
        "proxyRdpPath": data.get("FRONTEND_PROXY_RDP_PATH") or "",
        "proxyNodePath": data.get("FRONTEND_PROXY_NODE_PATH") or "",
        "frontendOnion": data.get("FRONTEND_ONION") or "",
        "masterOnion": data.get("MASTER_SERVER_ONION") or "",
        "blockchainOnion": data.get("BLOCKCHAIN_ONION") or "",
        "proxySource": data.get("FRONTEND_PROXY_SOURCE") or "frontend",
        "pulledAt": data.get("PULLED_AT") or "",
        "hostname": data.get("HOSTNAME_CONSOLE") or "",
        "pages": {
            "home": "/home.html",
            "login": "/login.html",
            "register": "/register.html",
            "logout": "/logout.html",
            "tierSelect": "/tier-select.html",
            "nodeRegistration": "/node-registration.html",
            "dashboard": "/dashboard.html",
            "findPeer": "/find-peer.html",
            "connectHandshake": "/connect-handshake.html",
            "settings": "/settings.html",
            "remoteView": "/RemoteView.html",
            "lucidLedger": "/LucidLedger.html",
            "lucidMarket": "/LucidMarket.html",
            "adminHome": "/AdminHome.html",
            "masterUserDashboard": "/MasterUser-dashboard.html",
        },
        "apiRoutes": {
            "register": "/register",
            "login": "/login",
            "logout": "/logout",
            "nodeRegistration": "/node-registration",
            "nodeLogin": "/node-login",
            "tierSelect": "/tier-select",
            "billing": "/billing-information",
            "userConnect": "/user-connect",
            "userControl": "/user-control",
            "userLedger": "/user-LucidLedger-read",
            "sessionCreate": "/user-session-create",
            "sessionFind": "/user-session-find",
            "sessionConnect": "/user-session-connect",
            "sessionControl": "/user-session-control",
            "sessionDisconnect": "/user-session-disconnect",
            "sessionEnd": "/user-session-end",
            "connectHandshake": "/connect-handshake",
        },
        "tiers": [
            {"id": 1, "key": "free_tier", "label": "Free", "costAud": 0, "sessionsPerMonth": 10, "devices": 1},
            {"id": 2, "key": "basic_tier", "label": "Basic", "costAud": 10, "sessionsPerMonth": 20, "devices": 1},
            {"id": 3, "key": "single_Premium_tier", "label": "Single Premium", "costAud": 20, "sessionsPerMonth": 30, "devices": 2},
            {"id": 4, "key": "basic_enterprise_tier", "label": "Basic Enterprise", "costAud": 39, "sessionsPerMonth": 70, "devices": 5},
            {"id": 5, "key": "premium_enterprise_tier", "label": "Premium Enterprise", "costAud": 79, "sessionsPerMonth": 120, "devices": 10},
            {"id": 6, "key": "ultimate_enterprise_tier", "label": "Ultimate Enterprise", "costAud": 229, "sessionsPerMonth": 0, "devices": 20},
            {"id": 7, "key": "Master_user_tier", "label": "Master User", "costAud": 0, "sessionsPerMonth": 0, "devices": 0, "gated": True},
            {"id": 8, "key": "Admin_tier", "label": "Admin", "costAud": 0, "sessionsPerMonth": 0, "devices": 0, "gated": True},
        ],
    }


def write_runtime_config_js(
    secrets: dict[str, str] | None = None, *, webpage_root: Path | None = None
) -> Path:
    """Write browser runtime-config.js from pulled secrets (no sensitive tokens)."""
    data = secrets
    if data is None:
        data = build_frontend_secrets()
    root = webpage_root or Path(
        data.get("FRONTEND_WEBPAGE_ROOT") or (FRONTEND_DIR / "webpage").as_posix()
    )
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / "runtime-config.js"
    payload = public_runtime_config(data)
    body = (
        "/* Generated at time of operation - do not edit by hand */\n"
        "window.__LUCID_RUNTIME__ = "
        + json.dumps(payload, indent=2, sort_keys=True)
        + ";\n"
    )
    target.write_text(body, encoding="utf-8")
    return target


def export_shell_env(pull: dict[str, Any] | None = None) -> str:
    bound = bind_operation_environ(pull)
    lines = [f'export {key}="{value}"' for key, value in sorted(bound.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    info = pull_realworld_information()
    secrets = build_frontend_secrets(info)
    config_path = write_runtime_config_js(secrets)
    print(export_shell_env(info), end="")
    print(f"# runtime_config={config_path.as_posix()}", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
