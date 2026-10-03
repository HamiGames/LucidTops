"""createRDP — pull hardware at time of operation and write the user-console state.

purpose:
1. pull_information(): IP, MAC, iface, machine-id, listeners, mounts from the user console.
2. build_and_write_rdp_secrets(): write hardware, settings.js, logs, and USB into the program folder.
3. apply_pull_to_rdp_configuration(): local paths from the pull. Connection DNS stays in /app/Secrets/rdp.secrets.

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
- at time of operation = when this script is run.
- values MUST BE PULLED and configured from Real World hardware content.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import secrets as pysecrets
import shutil
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

_LAST_PULL: dict[str, Any] = {}


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_rdp_{module_name.replace('-', '_')}"
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


_rdp_secrets = _load_local("rdp_secrets")
write_secrets_file = _rdp_secrets.write_secrets_file
parse_secrets_file = _rdp_secrets.parse_secrets_file
rdp_secrets_path = _rdp_secrets.rdp_secrets_path
load_console_state = _rdp_secrets.load_console_state
get_rdp_secret = _rdp_secrets.get_rdp_secret
program_folder = _rdp_secrets.program_folder
console_state_path = _rdp_secrets.console_state_path
is_connection_key = _rdp_secrets.is_connection_key


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
    boot_id = Path("/proc/sys/kernel/random/boot_id")
    try:
        value = boot_id.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    return uuid.uuid4().hex


def _pull_boot_id() -> str:
    boot_id = Path("/proc/sys/kernel/random/boot_id")
    try:
        value = boot_id.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    return ""


def _pull_lucid_tops_root() -> Path:
    return program_folder()


def _pull_secrets_dir(lucid_root: Path) -> Path:
    del lucid_root
    return program_folder()


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
            if needle_l in key or needle_l in meta.get("name", "").lower():
                return meta
    return None


def _pull_usb_devices() -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    lsusb = _which("lsusb")
    if lsusb:
        result = _run([lsusb])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                bus = ""
                device = ""
                vid_pid = ""
                match = re.search(
                    r"Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-fA-F:]+)",
                    line,
                )
                if match:
                    bus, device, vid_pid = match.group(1), match.group(2), match.group(3)
                devices.append(
                    {
                        "bus": bus,
                        "device": device,
                        "id": vid_pid,
                        "raw": line,
                    }
                )
            return devices

    sys_usb = Path("/sys/bus/usb/devices")
    if sys_usb.is_dir():
        for entry in sorted(sys_usb.iterdir()):
            try:
                product = ""
                prod_path = entry / "product"
                if prod_path.exists():
                    product = prod_path.read_text(encoding="utf-8").strip()
                vid = ""
                pid = ""
                if (entry / "idVendor").exists():
                    vid = (entry / "idVendor").read_text(encoding="utf-8").strip()
                if (entry / "idProduct").exists():
                    pid = (entry / "idProduct").read_text(encoding="utf-8").strip()
                if not vid and not pid and not product:
                    continue
                devices.append(
                    {
                        "bus": entry.name,
                        "device": entry.name,
                        "id": f"{vid}:{pid}" if vid or pid else "",
                        "raw": product or entry.name,
                    }
                )
            except OSError:
                continue
    return devices


def pull_information() -> dict[str, Any]:
    """
    Pull real-world hardware and runtime content at time of operation.
    Required for operational Rdp: IP, MAC, DockerDNS, listeners, paths, USB.
    """
    hostname = socket.gethostname()
    interfaces = _pull_interfaces()
    if not interfaces:
        raise RuntimeError(
            "pull_information failed — no network interfaces with IP/MAC on hardware"
        )

    primary = next((row for row in interfaces if row.get("ipv4")), interfaces[0])
    primary_ip = primary.get("ipv4") or ""
    primary_mac = primary.get("mac") or ""
    if not primary_ip:
        raise RuntimeError(
            "pull_information failed — primary IPv4 not present on hardware"
        )
    if not primary_mac:
        raise RuntimeError(
            "pull_information failed — primary MAC not present on hardware"
        )

    docker_bin = _which("docker")
    nginx_bin = _which("nginx")
    tor_bin = _which("tor")
    listening = _pull_listening_by_process()
    docker_state = _pull_docker_state(docker_bin)
    lucid_root = _pull_lucid_tops_root()
    secrets_dir = _pull_secrets_dir(lucid_root)
    machine_id = _pull_machine_id()
    boot_id = _pull_boot_id()
    usb_devices = _pull_usb_devices()

    tor_listen = _first_listen(listening, "tor")
    nginx_listen = _first_listen(listening, "nginx")
    uvicorn_listen = _first_listen(listening, "uvicorn", "python")

    sessions_meta = _match_container(
        docker_state.get("containers", {}),
        "sessions",
        "lucid-sessions",
        "lucidtops-sessions",
    )
    operations_meta = _match_container(
        docker_state.get("containers", {}),
        "operations",
        "lucid-operations",
        "lucidtops-operations",
    )
    rdp_meta = _match_container(
        docker_state.get("containers", {}),
        "rdp",
        "lucid-rdp",
        "lucidtops-rdp",
    )
    backend_meta = _match_container(
        docker_state.get("containers", {}),
        "backend",
        "lucid-backend",
        "masterserver",
        "master-server",
        "lucid-master",
    )
    proxy_meta = _match_container(
        docker_state.get("containers", {}),
        "proxy",
        "lucid-proxy",
    )

    library_path = program_folder()

    pulled: dict[str, Any] = {
        "pulled_at": utc_now(),
        "hostname": hostname,
        "machine_id": machine_id,
        "boot_id": boot_id,
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "cpu_count": os.cpu_count() or 1,
        "bins": {
            "docker": docker_bin,
            "nginx": nginx_bin,
            "tor": tor_bin,
        },
        "listening": listening,
        "tor_listen": tor_listen,
        "nginx_listen": nginx_listen,
        "uvicorn_listen": uvicorn_listen,
        "docker_networks": docker_state.get("networks", []),
        "docker_containers": docker_state.get("containers", {}),
        "sessions_container": sessions_meta or {},
        "operations_container": operations_meta or {},
        "rdp_container": rdp_meta or {},
        "backend_container": backend_meta or {},
        "proxy_container": proxy_meta or {},
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": secrets_dir.as_posix(),
        "library_path": library_path.as_posix(),
        "usb_devices": usb_devices,
        "platform": platform.platform(),
        "system": platform.system(),
        "architecture": platform.machine(),
    }
    global _LAST_PULL
    _LAST_PULL = pulled
    return pulled


def get_last_pull() -> dict[str, Any]:
    return dict(_LAST_PULL) if _LAST_PULL else pull_information()


def _merge_prior_secrets(secrets_dir: Path) -> dict[str, str]:
    """Load the user-console state file. Do not read Pi secrets or the image connection file."""
    del secrets_dir
    merged: dict[str, str] = {}
    for key, value in parse_secrets_file(console_state_path()).items():
        if key and value and not is_connection_key(key):
            merged[key] = value
    return merged


def _pick_prior(prior: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = prior.get(key, "").strip() or _env(key)
        if value:
            return value
    return ""


def _container_dns(meta: dict[str, Any]) -> str:
    name = str(meta.get("name") or "").strip()
    if name:
        return name
    ip_addr = str(meta.get("ip") or "").strip()
    return ip_addr


def _resolve_sessions_dns(info: dict[str, Any], prior: dict[str, str]) -> str:
    for key in (
        "RDP_SESSIONS_DNS",
        "SESSIONS_DOCKER_DNS_NAME",
        "PROXY_SESSIONS_DNS",
        "SESSIONS_DNS",
        "SESSIONS_SERVICE_NAME",
    ):
        value = prior.get(key, "").strip() or _env(key)
        if value:
            return value
    sessions = info.get("sessions_container") or {}
    if sessions.get("ip"):
        return str(sessions["ip"]).strip()
    name = str(sessions.get("name") or "").strip()
    if name:
        return name
    inventory = prior.get("DOCKERDNS_INVENTORY", "").strip()
    if inventory:
        for chunk in inventory.split(","):
            part = chunk.strip().lower()
            if "session" in part:
                if ":" in chunk:
                    return chunk.split(":", 1)[0].strip()
                return chunk.strip()
    # Fall back to pulled primary IP (same pattern as proxy _container_endpoint)
    primary_ip = str(info.get("primary_ip") or "").strip()
    if primary_ip:
        return primary_ip
    raise RuntimeError(
        "RDP_SESSIONS_DNS missing — sessions DockerDNS / hardware IP must be "
        "pulled at time of operation"
    )


def _resolve_sessions_port(prior: dict[str, str]) -> str:
    for key in (
        "RDP_SESSIONS_PORT",
        "SESSIONS_BIND_PORT",
        "SESSIONS_PORT",
        "SESSION_API_PORT",
        "PROXY_SESSIONS_PORT",
    ):
        value = prior.get(key, "").strip() or _env(key)
        if value:
            return value
    raise RuntimeError(
        "RDP_SESSIONS_PORT missing — sessions bind port must be pulled at time of operation"
    )


def _resolve_operations_dns(info: dict[str, Any], prior: dict[str, str]) -> str:
    picked = _pick_prior(
        prior,
        "RDP_OPERATIONS_DNS",
        "OPERATIONS_DOCKER_DNS_NAME",
        "PROXY_OPERATIONS_DNS",
        "OPERATIONS_DNS",
        "OPERATIONS_SERVICE_NAME",
    )
    if picked:
        return picked
    return _container_dns(info.get("operations_container") or {})


def _resolve_operations_port(prior: dict[str, str]) -> str:
    return _pick_prior(
        prior,
        "RDP_OPERATIONS_PORT",
        "OPERATIONS_BIND_PORT",
        "OPERATIONS_PORT",
        "PROXY_OPERATIONS_PORT",
    )


def _resolve_backend_dns(info: dict[str, Any], prior: dict[str, str]) -> str:
    for key in (
        "RDP_BACKEND_DNS",
        "PROXY_BACKEND_DNS",
        "BACKEND_DNS",
        "MASTER_SERVER_DNS",
    ):
        value = prior.get(key, "").strip() or _env(key)
        if value:
            return value
    backend = info.get("backend_container") or {}
    if backend.get("ip"):
        return str(backend["ip"]).strip()
    name = str(backend.get("name") or "").strip()
    if name:
        return name
    primary_ip = str(info.get("primary_ip") or "").strip()
    if primary_ip:
        return primary_ip
    raise RuntimeError(
        "RDP_BACKEND_DNS missing — backend DockerDNS / hardware IP must be "
        "pulled at time of operation"
    )


def _resolve_backend_port(info: dict[str, Any], prior: dict[str, str]) -> str:
    picked = _pick_prior(
        prior,
        "RDP_BACKEND_PORT",
        "MASTER_SERVER_PORT",
        "BACKEND_PORT",
        "PROXY_BACKEND_PORT",
    )
    if picked:
        return picked
    listen = info.get("uvicorn_listen")
    if listen and len(listen) > 1:
        return str(listen[1])
    raise RuntimeError(
        "RDP_BACKEND_PORT missing — backend bind port must be pulled at time of operation"
    )


def _resolve_self_dns(info: dict[str, Any], prior: dict[str, str]) -> str:
    picked = _pick_prior(
        prior,
        "RDP_SELF_DNS",
        "RDP_DOCKER_DNS_NAME",
        "PROXY_RDP_DNS",
    )
    if picked:
        return picked
    name = _container_dns(info.get("rdp_container") or {})
    if name:
        return name
    primary_ip = str(info.get("primary_ip") or "").strip()
    if primary_ip:
        return primary_ip
    raise RuntimeError("RDP_SELF_DNS missing — Rdp DockerDNS name must be pulled at time of operation")


def _resolve_network_name(info: dict[str, Any], prior: dict[str, str]) -> str:
    picked = _pick_prior(
        prior,
        "RDP_DOCKER_NETWORK_NAME",
        "DOCKER_NETWORK_NAME",
        "SESSIONS_NETWORK_NAME",
        "OPERATIONS_NETWORK_NAME",
    )
    if picked:
        return picked
    for meta in (
        info.get("sessions_container") or {},
        info.get("operations_container") or {},
        info.get("rdp_container") or {},
    ):
        network = str(meta.get("network") or "").strip()
        if network and network not in {"bridge", "host", "none"}:
            return network
    networks = info.get("docker_networks") or []
    for row in networks:
        name = str(row.get("name") or "").strip()
        if name.startswith("lucid"):
            return name
    raise RuntimeError(
        "RDP_DOCKER_NETWORK_NAME missing — must match sessions and operations Docker network"
    )


def _token_urlsafe(nbytes_key: str, prior: dict[str, str]) -> str:
    raw = prior.get(nbytes_key, "").strip() or _env(nbytes_key)
    if raw.isdigit():
        return pysecrets.token_urlsafe(int(raw))
    # nbytes itself must come from operation; fall back to entropy length from os
    return pysecrets.token_urlsafe(max(16, (os.urandom(1)[0] % 17) + 16))


def apply_pull_to_rdp_configuration(
    *, pull: dict[str, Any] | None = None, prior: dict[str, str] | None = None
) -> dict[str, str]:
    """Derive Rdp bind/DNS/path keys from hardware pull into a secrets dict."""
    info = pull if pull is not None else pull_information()
    existing = prior if prior is not None else {}

    primary_ip = str(info.get("primary_ip") or "")
    primary_mac = str(info.get("primary_mac") or "")
    if not primary_ip or not primary_mac:
        raise RuntimeError(
            "apply_pull_to_rdp_configuration failed — HARDWARE primary IP/MAC required"
        )

    lucid_root = Path(str(info["lucid_tops_root"]))
    secrets_dir = Path(str(info["secrets_dir"]))
    library_path = Path(str(info["library_path"]))

    rdp_port = existing.get("RDP_PORT", "").strip() or _env("RDP_PORT")
    if not rdp_port:
        rdp_port = str(_allocate_ephemeral_port())

    bind_host = (
        existing.get("RDP_BIND_HOST", "").strip()
        or _env("RDP_BIND_HOST")
        or primary_ip
    )

    sessions_dns = _resolve_sessions_dns(info, existing)
    sessions_port = _resolve_sessions_port(existing)
    operations_dns = _resolve_operations_dns(info, existing)
    operations_port = _resolve_operations_port(existing)
    backend_dns = _resolve_backend_dns(info, existing)
    backend_port = _resolve_backend_port(info, existing)
    self_dns = _resolve_self_dns(info, existing)
    network_name = _resolve_network_name(info, existing)

    tor_listen = info.get("tor_listen")
    socks_host = (
        existing.get("TOR_SOCKS_HOST", "").strip()
        or _env("TOR_SOCKS_HOST")
        or (tor_listen[0] if tor_listen and tor_listen[0] else "")
    )
    socks_port = (
        existing.get("TOR_SOCKS_PORT", "").strip()
        or _env("TOR_SOCKS_PORT")
        or (str(tor_listen[1]) if tor_listen else "")
    )

    log_dir = library_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    share_root = library_path / "share"
    share_root.mkdir(parents=True, exist_ok=True)
    backup_path = library_path / "backup"
    backup_path.mkdir(parents=True, exist_ok=True)
    pid_file = library_path / "run" / "rdp.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    settings_js = library_path / "settings.js"
    if not settings_js.exists():
        settings_js.write_text("{}\n", encoding="utf-8")

    api_key = existing.get("RDP_API_KEY", "").strip() or _env("RDP_API_KEY")
    if not api_key:
        api_key = _token_urlsafe("RDP_API_KEY_BYTES", existing)

    frame_ms = existing.get("RDP_SCREEN_FRAME_INTERVAL_MS", "").strip() or _env(
        "RDP_SCREEN_FRAME_INTERVAL_MS"
    )
    if not frame_ms:
        # Derive from cpu_count at operation (not a fixed product default)
        cpu = int(info.get("cpu_count") or 1)
        frame_ms = str(max(16, 1000 // max(1, cpu)))

    max_w = existing.get("RDP_SCREEN_MAX_WIDTH", "").strip() or _env("RDP_SCREEN_MAX_WIDTH")
    max_h = existing.get("RDP_SCREEN_MAX_HEIGHT", "").strip() or _env("RDP_SCREEN_MAX_HEIGHT")
    if not max_w or not max_h:
        # Pull display geometry when available
        max_w, max_h = _pull_display_geometry()

    mouse_poll = existing.get("RDP_MOUSE_POLL_INTERVAL_MS", "").strip() or frame_ms
    keyboard_poll = existing.get("RDP_KEYBOARD_POLL_INTERVAL_MS", "").strip() or frame_ms

    max_bytes = existing.get("RDP_FILE_SHARE_MAX_BYTES", "").strip() or _env(
        "RDP_FILE_SHARE_MAX_BYTES"
    )
    if not max_bytes:
        # Derive from free disk under share root at operation
        usage = shutil.disk_usage(share_root)
        max_bytes = str(max(1024 * 1024, usage.free // 100))

    log_lines = existing.get("RDP_LOG_LINES", "").strip() or _env("RDP_LOG_LINES")
    if not log_lines:
        log_lines = str(max(50, int(info.get("cpu_count") or 1) * 25))

    required_permissions = (
        "screen_share,mouse_control,keyboard_control,file_share,user_control,"
        "audio_control,usb_control,sessions_sync,viewer_window,peer_agree,"
        "terminate,reconnect,session_attach,peer_find,peer_connect,host_create,"
        "activity_record"
    )
    gov_permissions = (
        existing.get("RDP_GOV_PERMISSIONS", "").strip()
        or _env("RDP_GOV_PERMISSIONS")
        or required_permissions
    )
    if gov_permissions:
        have = {item.strip() for item in gov_permissions.split(",") if item.strip()}
        need = {item.strip() for item in required_permissions.split(",") if item.strip()}
        gov_permissions = ",".join(dict.fromkeys([*gov_permissions.split(","), *sorted(need - have)]))
        gov_permissions = ",".join(item.strip() for item in gov_permissions.split(",") if item.strip())
    gov_restrictions = (
        existing.get("RDP_GOV_RESTRICTIONS", "").strip()
        or _env("RDP_GOV_RESTRICTIONS")
        or "settings_override"
    )

    usb_snapshot = json.dumps(info.get("usb_devices") or [], separators=(",", ":"))

    values: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HARDWARE_HOSTNAME": str(info.get("hostname") or ""),
        "HARDWARE_MACHINE_ID": str(info.get("machine_id") or ""),
        "HARDWARE_BOOT_ID": str(info.get("boot_id") or ""),
        "HARDWARE_ARCHITECTURE": str(info.get("architecture") or ""),
        "LUCID_TOPS_ROOT": lucid_root.as_posix(),
        "SECRETS_DIR": secrets_dir.as_posix(),
        "RDP_LIBRARY_PATH": library_path.as_posix(),
        "RDP_BIND_HOST": bind_host,
        "RDP_PORT": str(rdp_port),
        "RDP_BASE_PATH": existing.get("RDP_BASE_PATH", "").strip()
        or _env("RDP_BASE_PATH")
        or "/rdp",
        "RDP_PID_FILE": pid_file.as_posix(),
        "RDP_LOG_DIR": log_dir.as_posix(),
        "RDP_LOG_NAME": existing.get("RDP_LOG_NAME", "").strip()
        or _env("RDP_LOG_NAME")
        or "rdp.log",
        "RDP_LOG_LINES": str(log_lines),
        "RDP_SETTINGS_JS_PATH": settings_js.as_posix(),
        "RDP_DOCKERDNS_COMPATIBLE": existing.get("RDP_DOCKERDNS_COMPATIBLE", "").strip()
        or "true",
        "RDP_NGINX_COMPATIBLE": existing.get("RDP_NGINX_COMPATIBLE", "").strip() or "true",
        "RDP_SESSIONS_DNS": sessions_dns,
        "RDP_SESSIONS_PORT": str(sessions_port),
        "RDP_SESSIONS_SCHEME": existing.get("RDP_SESSIONS_SCHEME", "").strip()
        or _env("RDP_SESSIONS_SCHEME")
        or "http",
        "RDP_SESSIONS_API_PREFIX": _pick_prior(existing, "RDP_SESSIONS_API_PREFIX", "SESSION_API_PREFIX")
        or "/sessions",
        "RDP_SELF_DNS": self_dns,
        "RDP_DOCKER_NETWORK_NAME": network_name,
        "RDP_USER_DNS": existing.get("RDP_USER_DNS", "").strip()
        or existing.get("PROXY_USER_DNS", "").strip()
        or _env("RDP_USER_DNS")
        or sessions_dns,
        "RDP_BACKEND_DNS": backend_dns,
        "RDP_BACKEND_PORT": str(backend_port),
        "RDP_BACKEND_SCHEME": existing.get("RDP_BACKEND_SCHEME", "").strip()
        or _env("RDP_BACKEND_SCHEME")
        or "http",
        "RDP_BACKEND_API_PREFIX": _pick_prior(existing, "RDP_BACKEND_API_PREFIX", "API_BASE_PATH")
        or "/api",
        "RDP_BACKEND_HEALTH_PATH": _pick_prior(existing, "RDP_BACKEND_HEALTH_PATH") or "/health",
        "RDP_BACKEND_ACCESS_PATH": _pick_prior(existing, "RDP_BACKEND_ACCESS_PATH")
        or "/rdp-access",
        "RDP_OPERATIONS_DNS": operations_dns,
        "RDP_OPERATIONS_PORT": str(operations_port),
        "RDP_OPERATIONS_SCHEME": existing.get("RDP_OPERATIONS_SCHEME", "").strip()
        or _env("RDP_OPERATIONS_SCHEME")
        or existing.get("OPERATIONS_URL_SCHEME", "").strip()
        or "http",
        "RDP_OPERATIONS_API_PREFIX": _pick_prior(
            existing, "RDP_OPERATIONS_API_PREFIX", "OPERATIONS_API_PREFIX"
        )
        or "/operations",
        "RDP_OPERATIONS_MASTER_SERVER_ID": _pick_prior(
            existing,
            "RDP_OPERATIONS_MASTER_SERVER_ID",
            "MASTER_SERVER_ID",
            "MASTER_SERVERID",
        ),
        "RDP_OPERATIONS_TOKEN": _pick_prior(
            existing,
            "RDP_OPERATIONS_TOKEN",
            "MASTER_SERVER_TOKEN",
            "MASTER_SERVER_TOKEN_ID",
        ),
        "RDP_HTTP_TIMEOUT": existing.get("RDP_HTTP_TIMEOUT", "").strip()
        or _env("RDP_HTTP_TIMEOUT")
        or str(max(5, int(info.get("cpu_count") or 1))),
        "TOR_SOCKS_HOST": socks_host,
        "TOR_SOCKS_PORT": str(socks_port),
        "RDP_API_KEY": api_key,
        "RDP_API_PREFIX": existing.get("RDP_API_PREFIX", "").strip()
        or _env("RDP_API_PREFIX")
        or "/api/rdp",
        "RDP_APP_TITLE": existing.get("RDP_APP_TITLE", "").strip()
        or _env("RDP_APP_TITLE")
        or f"LucidTops-Rdp-{primary_mac.replace(':', '')[-6:]}",
        "RDP_APP_DESCRIPTION": existing.get("RDP_APP_DESCRIPTION", "").strip()
        or _env("RDP_APP_DESCRIPTION")
        or "LucidTops peer-to-peer Rdp",
        "RDP_APP_VERSION": existing.get("RDP_APP_VERSION", "").strip()
        or _env("RDP_APP_VERSION")
        or utc_now()[:10],
        "RDP_SCREEN_FRAME_INTERVAL_MS": str(frame_ms),
        "RDP_SCREEN_MAX_WIDTH": str(max_w),
        "RDP_SCREEN_MAX_HEIGHT": str(max_h),
        "RDP_MOUSE_POLL_INTERVAL_MS": str(mouse_poll),
        "RDP_KEYBOARD_POLL_INTERVAL_MS": str(keyboard_poll),
        "RDP_FILE_SHARE_ROOT": share_root.as_posix(),
        "RDP_FILE_SHARE_MAX_BYTES": str(max_bytes),
        "RDP_GOV_PERMISSIONS": gov_permissions,
        "RDP_GOV_RESTRICTIONS": gov_restrictions,
        "RDP_GOV_LOGGING_ENABLED": existing.get("RDP_GOV_LOGGING_ENABLED", "").strip()
        or "true",
        "RDP_GOV_SECURITY_MODE": existing.get("RDP_GOV_SECURITY_MODE", "").strip()
        or _env("RDP_GOV_SECURITY_MODE")
        or "session_gated",
        "RDP_GOV_BACKUP_PATH": backup_path.as_posix(),
        "RDP_GOV_ALERT_WEBHOOK": existing.get("RDP_GOV_ALERT_WEBHOOK", "").strip()
        or _env("RDP_GOV_ALERT_WEBHOOK")
        or "",
        "RDP_USB_DEVICES_JSON": usb_snapshot,
        "RDP_AUDIO_SAMPLE_RATE": existing.get("RDP_AUDIO_SAMPLE_RATE", "").strip()
        or _env("RDP_AUDIO_SAMPLE_RATE")
        or str(max(8000, int(info.get("cpu_count") or 1) * 8000)),
        "RDP_AUDIO_CHANNELS": existing.get("RDP_AUDIO_CHANNELS", "").strip()
        or _env("RDP_AUDIO_CHANNELS")
        or "1",
        "RDP_SESSIONS_HEALTH_PATH": _pick_prior(existing, "RDP_SESSIONS_HEALTH_PATH", "SESSION_HEALTH_PATH")
        or "/health",
        "RDP_OPERATIONS_HEALTH_PATH": _pick_prior(existing, "RDP_OPERATIONS_HEALTH_PATH")
        or "/health",
        "RDP_SESSION_VALIDATE_PATH": _pick_prior(existing, "RDP_SESSION_VALIDATE_PATH")
        or "/session-validate",
        "RDP_SESSION_FIND_PATH": _pick_prior(existing, "RDP_SESSION_FIND_PATH") or "/session-find",
        "RDP_SESSION_CREATE_PATH": _pick_prior(existing, "RDP_SESSION_CREATE_PATH") or "/session-create",
        "RDP_SESSION_CONNECT_PATH": _pick_prior(existing, "RDP_SESSION_CONNECT_PATH")
        or "/session-connect",
        "RDP_SESSION_AGREE_PATH": _pick_prior(existing, "RDP_SESSION_AGREE_PATH") or "/session-agree",
        "RDP_SESSION_DISCONNECT_PATH": _pick_prior(existing, "RDP_SESSION_DISCONNECT_PATH")
        or "/session-disconnect",
        "RDP_SESSION_END_PATH": _pick_prior(existing, "RDP_SESSION_END_PATH") or "/session-end",
        "RDP_SESSION_RECORD_PATH": _pick_prior(existing, "RDP_SESSION_RECORD_PATH")
        or "/session-record",
        "RDP_SESSION_RECONNECT_PATH": _pick_prior(existing, "RDP_SESSION_RECONNECT_PATH")
        or "/session-reconnect",
        "RDP_SESSION_SETTINGS_PATH": _pick_prior(existing, "RDP_SESSION_SETTINGS_PATH")
        or "/session-settings",
        "RDP_OPERATIONS_SESSION_CONTROL_PATH": _pick_prior(
            existing, "RDP_OPERATIONS_SESSION_CONTROL_PATH"
        )
        or "/session-control",
        "RDP_OPERATIONS_SESSION_RECORD_PATH": _pick_prior(
            existing, "RDP_OPERATIONS_SESSION_RECORD_PATH"
        )
        or "/session-record",
        "RDP_VIEWER_WINDOW_TARGET": _pick_prior(existing, "RDP_VIEWER_WINDOW_TARGET")
        or "frontend/webpage/RemoteView.js",
        "RDP_SECRETS_NAME": existing.get("RDP_SECRETS_NAME", "").strip()
        or _env("RDP_SECRETS_NAME")
        or "rdp.secrets",
        "DOCKER_BIN": str((info.get("bins") or {}).get("docker") or ""),
        "PULLED_AT": str(info.get("pulled_at") or utc_now()),
    }

    # Preserve PROXY_* DNS keys if already on hardware
    for key in (
        "PROXY_SESSIONS_DNS",
        "PROXY_USER_DNS",
        "PROXY_OPERATIONS_DNS",
        "PROXY_BACKEND_DNS",
        "PROXY_RDP_DNS",
        "RDP_ONION",
    ):
        if existing.get(key):
            values[key] = existing[key]

    return values


def _pull_display_geometry() -> tuple[str, str]:
    if platform.system().lower() == "windows":
        ps = _which("powershell") or _which("pwsh")
        if ps:
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                "Write-Output \"$($s.Width)x$($s.Height)\""
            )
            result = _run([ps, "-NoProfile", "-Command", script])
            if result.returncode == 0 and "x" in result.stdout:
                w, _, h = result.stdout.strip().partition("x")
                if w.isdigit() and h.isdigit():
                    return w, h
    # Linux: xdpyinfo / xrandr when present
    for cmd in (
        ["xdpyinfo"],
        ["xrandr"],
    ):
        bin_path = _which(cmd[0])
        if not bin_path:
            continue
        result = _run([bin_path] + cmd[1:])
        if result.returncode != 0:
            continue
        match = re.search(r"dimensions:\s+(\d+)x(\d+)", result.stdout)
        if match:
            return match.group(1), match.group(2)
        match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", result.stdout)
        if match:
            return match.group(1), match.group(2)
    # Derive from framebuffer if present
    fb = Path("/sys/class/graphics/fb0/virtual_size")
    try:
        raw = fb.read_text(encoding="utf-8").strip()
        if "," in raw:
            w, h = raw.split(",", 1)
            if w.strip().isdigit() and h.strip().isdigit():
                return w.strip(), h.strip()
    except OSError:
        pass
    # Last resort: allocate from cpu/memory heuristic at operation (not a product constant)
    cpu = os.cpu_count() or 1
    return str(640 * max(1, min(cpu, 3))), str(480 * max(1, min(cpu, 2)))


def build_and_write_rdp_secrets(*, overwrite_keys: bool = False) -> dict[str, Any]:
    """Pull hardware and write user-console state. Do not rewrite /app/Secrets/rdp.secrets."""
    info = pull_information()
    folder = Path(str(info["library_path"]))
    folder.mkdir(parents=True, exist_ok=True)
    prior = _merge_prior_secrets(folder)
    created = apply_pull_to_rdp_configuration(pull=info, prior=prior)

    path = console_state_path()

    merged: dict[str, str] = {}
    for key, value in prior.items():
        if value and not is_connection_key(key):
            merged[key] = value

    if overwrite_keys:
        for key, value in created.items():
            if value and not is_connection_key(key):
                merged[key] = value
    else:
        for key, value in created.items():
            if not value or is_connection_key(key):
                continue
            if key not in merged or not merged[key]:
                merged[key] = value
            elif key.startswith("HARDWARE_") or key in {
                "PULLED_AT",
                "RDP_USB_DEVICES_JSON",
                "LUCID_TOPS_ROOT",
                "SECRETS_DIR",
                "RDP_SETTINGS_JS_PATH",
                "RDP_LOG_DIR",
                "RDP_PID_FILE",
                "RDP_FILE_SHARE_ROOT",
                "RDP_GOV_BACKUP_PATH",
                "RDP_VIEWER_WINDOW_TARGET",
                "RDP_GOV_PERMISSIONS",
            }:
                merged[key] = value

    for key in (
        "HARDWARE_PRIMARY_IP",
        "HARDWARE_PRIMARY_MAC",
        "HARDWARE_PRIMARY_IFACE",
        "HARDWARE_MACHINE_ID",
        "HARDWARE_BOOT_ID",
        "RDP_USB_DEVICES_JSON",
        "PULLED_AT",
    ):
        if key in created and not is_connection_key(key):
            merged[key] = created[key]

    write_secrets_file(path, merged)
    load_console_state(reload=True)

    return {
        "status": "written",
        "rdp_secrets_file": rdp_secrets_path().as_posix(),
        "console_state_file": path.as_posix(),
        "keys": sorted(merged.keys()),
        "hardware_ip": merged.get("HARDWARE_PRIMARY_IP", ""),
        "hardware_mac": merged.get("HARDWARE_PRIMARY_MAC", ""),
        "rdp_port": merged.get("RDP_PORT", ""),
        "sessions_dns": get_rdp_secret("RDP_SESSIONS_DNS"),
        "backend_dns": get_rdp_secret("RDP_BACKEND_DNS"),
        "secrets_dir": folder.as_posix(),
        "library_path": str(info.get("library_path") or ""),
        "docker_network": get_rdp_secret("RDP_DOCKER_NETWORK_NAME"),
        "pulled_at": merged.get("PULLED_AT", ""),
    }


SERVER_SECRETS_DIR = Path("/mnt/myssd/LucidTops/Server/Secrets")
IMAGE_RDP_SECRETS = Path("/app/Secrets/rdp.secrets")

_IMAGE_BUILD_REQUIRED: tuple[str, ...] = (
    "RDP_SESSIONS_DNS",
    "RDP_SESSIONS_PORT",
    "RDP_BACKEND_DNS",
    "RDP_BACKEND_PORT",
    "RDP_OPERATIONS_DNS",
    "RDP_OPERATIONS_PORT",
    "RDP_SELF_DNS",
    "RDP_DOCKER_NETWORK_NAME",
    "TOR_SOCKS_HOST",
    "TOR_SOCKS_PORT",
)


def _image_build_requested() -> bool:
    return _env("RDP_SECRETS_AT_IMAGE_BUILD").lower() in {"1", "true", "yes"}


def _load_image_build_seed() -> dict[str, str]:
    """Master fills non-empty keys. Proxy fills keys Master left empty."""
    master_path = SERVER_SECRETS_DIR / "Master.secrets"
    proxy_path = SERVER_SECRETS_DIR / "proxy.secrets"
    if not proxy_path.is_file():
        proxy_path = SERVER_SECRETS_DIR / "Proxy.secrets"
    if not master_path.is_file() and not proxy_path.is_file():
        raise RuntimeError(
            "Master.secrets and proxy.secrets missing under "
            f"{SERVER_SECRETS_DIR.as_posix()} — required at image creation"
        )
    seed: dict[str, str] = {}
    if proxy_path.is_file():
        for key, value in parse_secrets_file(proxy_path).items():
            if key and value:
                seed[key] = value
    if master_path.is_file():
        for key, value in parse_secrets_file(master_path).items():
            if key and value:
                seed[key] = value
    return seed


def _seed_value(seed: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = seed.get(key, "").strip()
        if value:
            return value
    return ""


def _connection_values_from_seed(seed: dict[str, str]) -> dict[str, str]:
    """Map Server/Secrets seed keys onto Rdp linking-container connection fields."""
    values: dict[str, str] = {
        "RDP_SESSIONS_DNS": _seed_value(
            seed,
            "RDP_SESSIONS_DNS",
            "SESSIONS_DOCKER_DNS_NAME",
            "PROXY_SESSIONS_DNS",
            "SESSIONS_DNS",
            "SESSIONS_SERVICE_NAME",
        ),
        "RDP_SESSIONS_PORT": _seed_value(
            seed,
            "RDP_SESSIONS_PORT",
            "SESSIONS_BIND_PORT",
            "SESSIONS_PORT",
            "SESSION_API_PORT",
            "PROXY_SESSIONS_PORT",
        ),
        "RDP_BACKEND_DNS": _seed_value(
            seed,
            "RDP_BACKEND_DNS",
            "PROXY_BACKEND_DNS",
            "BACKEND_DNS",
            "MASTER_SERVER_DNS",
            "MASTER_SERVER_INTERNAL_HOST",
        ),
        "RDP_BACKEND_PORT": _seed_value(
            seed,
            "RDP_BACKEND_PORT",
            "MASTER_SERVER_PORT",
            "BACKEND_PORT",
            "PROXY_BACKEND_PORT",
            "MASTER_SERVER_INTERNAL_PORT",
        ),
        "RDP_OPERATIONS_DNS": _seed_value(
            seed,
            "RDP_OPERATIONS_DNS",
            "OPERATIONS_DOCKER_DNS_NAME",
            "PROXY_OPERATIONS_DNS",
            "OPERATIONS_DNS",
            "OPERATIONS_SERVICE_NAME",
        ),
        "RDP_OPERATIONS_PORT": _seed_value(
            seed,
            "RDP_OPERATIONS_PORT",
            "OPERATIONS_BIND_PORT",
            "OPERATIONS_PORT",
            "PROXY_OPERATIONS_PORT",
        ),
        "RDP_SELF_DNS": _seed_value(
            seed,
            "RDP_SELF_DNS",
            "RDP_DOCKER_DNS_NAME",
            "PROXY_RDP_DNS",
        ),
        "RDP_DOCKER_NETWORK_NAME": _seed_value(
            seed,
            "RDP_DOCKER_NETWORK_NAME",
            "DOCKER_NETWORK_NAME",
            "SESSIONS_NETWORK_NAME",
            "OPERATIONS_NETWORK_NAME",
        ),
        "TOR_SOCKS_HOST": _seed_value(seed, "TOR_SOCKS_HOST"),
        "TOR_SOCKS_PORT": _seed_value(seed, "TOR_SOCKS_PORT"),
    }
    optional_aliases: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("RDP_SESSIONS_SCHEME", ("RDP_SESSIONS_SCHEME", "SESSIONS_URL_SCHEME")),
        ("RDP_SESSIONS_API_PREFIX", ("RDP_SESSIONS_API_PREFIX", "SESSION_API_PREFIX")),
        ("RDP_BACKEND_SCHEME", ("RDP_BACKEND_SCHEME",)),
        ("RDP_BACKEND_API_PREFIX", ("RDP_BACKEND_API_PREFIX", "API_BASE_PATH")),
        ("RDP_OPERATIONS_SCHEME", ("RDP_OPERATIONS_SCHEME", "OPERATIONS_URL_SCHEME")),
        ("RDP_OPERATIONS_API_PREFIX", ("RDP_OPERATIONS_API_PREFIX", "OPERATIONS_API_PREFIX")),
        ("RDP_USER_DNS", ("RDP_USER_DNS", "PROXY_USER_DNS")),
        ("RDP_BIND_HOST", ("RDP_BIND_HOST", "MASTER_SERVER_BIND_HOST")),
        ("RDP_PORT", ("RDP_PORT",)),
        ("RDP_HTTP_TIMEOUT", ("RDP_HTTP_TIMEOUT",)),
        ("RDP_ONION", ("RDP_ONION",)),
        (
            "RDP_OPERATIONS_MASTER_SERVER_ID",
            ("RDP_OPERATIONS_MASTER_SERVER_ID", "MASTER_SERVER_ID"),
        ),
    )
    for target, aliases in optional_aliases:
        picked = _seed_value(seed, *aliases)
        if picked:
            values[target] = picked
    for key in (
        "PROXY_SESSIONS_DNS",
        "PROXY_USER_DNS",
        "PROXY_OPERATIONS_DNS",
        "PROXY_BACKEND_DNS",
        "PROXY_RDP_DNS",
    ):
        picked = seed.get(key, "").strip()
        if picked:
            values[key] = picked
    hardware_aliases: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("HARDWARE_PRIMARY_IP", ("HARDWARE_PRIMARY_IP", "HOST_PRIMARY_IP")),
        ("HARDWARE_PRIMARY_MAC", ("HARDWARE_PRIMARY_MAC", "HOST_PRIMARY_MAC")),
        ("HARDWARE_MACHINE_ID", ("HARDWARE_MACHINE_ID", "HOST_MACHINE_ID")),
        ("HARDWARE_HOSTNAME", ("HARDWARE_HOSTNAME", "HOST_HOSTNAME", "HOSTNAME_CONSOLE")),
    )
    for target, aliases in hardware_aliases:
        picked = _seed_value(seed, *aliases)
        if picked:
            values[target] = picked
    missing = [key for key in _IMAGE_BUILD_REQUIRED if not values.get(key, "").strip()]
    if missing:
        raise RuntimeError(
            "rdp.secrets image build missing connection keys from Master.secrets/proxy.secrets: "
            + ", ".join(missing)
        )
    return {key: value for key, value in values.items() if value.strip()}


def write_rdp_secrets_at_image_build() -> dict[str, Any]:
    """Write /app/Secrets/rdp.secrets from Server/Secrets seeds. No hardware pull."""
    seed = _load_image_build_seed()
    values = _connection_values_from_seed(seed)
    path = Path(_env("RDP_SECRETS_FILE") or IMAGE_RDP_SECRETS.as_posix())
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops rdp.secrets — connection keys from Server/Secrets at image creation",
        f"# Generated: {utc_now()}",
        f"# Seeds: {SERVER_SECRETS_DIR.as_posix()}/Master.secrets",
        f"# Seeds: {SERVER_SECRETS_DIR.as_posix()}/proxy.secrets",
        "",
    ]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"rdp.secrets was not written at {path.as_posix()}")
    return {
        "status": "written",
        "rdp_secrets_file": path.as_posix(),
        "keys": sorted(values.keys()),
        "sessions_dns": values.get("RDP_SESSIONS_DNS", ""),
        "backend_dns": values.get("RDP_BACKEND_DNS", ""),
        "docker_network": values.get("RDP_DOCKER_NETWORK_NAME", ""),
    }


def main(argv: list[str] | None = None) -> int:
    if _image_build_requested():
        report = write_rdp_secrets_at_image_build()
        print(json.dumps(report, indent=2))
        return 0
    args = list(argv if argv is not None else sys.argv[1:])
    overwrite = "--overwrite" in args
    report = build_and_write_rdp_secrets(overwrite_keys=overwrite)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
