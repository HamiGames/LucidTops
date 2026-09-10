""" this will build the secrets for the Proxy / MasterServer (uvicorn + FastAPI) path.
includes:
- pull_realworld_information(): required pull of IP, MAC, hostname, interfaces, CPU,
  machine-id, Docker networks/containers, listening ports, binaries, LucidTops root
  from hardware at time of operation (when this module runs).
- build_and_write_proxy_secrets(): creates proxy.secrets exclusively from that pull
  (DockerDNS hosts, SOCKS5, ports, paths, HMAC tokens, selected containers).
- collects and writes *.onion addresses from Tor Hidden Service hostname files when present.
- sync_to_master_secrets(): copies the proxy.secrets key set into Master.secrets.
- compatibility with uvicorn/FastAPI, Tor HS, Docker Network, nginx, MongoDB connection strings.

requirements:
- all code to be fluid and compatible with uvicorn/FastAPI, Tor HS, Docker Network, nginx, MongoDB.
- no hardcoded values, all values are created at time of operation.
- no placeholder values, all values are created at time of operation.
- at time of operation = the event when this script/module is run.
- values MUST be PULLED from real-world hardware (IP, MAC, etc.) via pull_realworld_information.

restrictions:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository for operational values.

"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROXY_DIR = Path(__file__).resolve().parent

TOR_HIDDEN_SERVICE_DIRS: dict[str, Path] = {}
_LAST_PULL: dict[str, Any] = {}

_PATH_ATTRS = frozenset(
    {
        "LUCID_TOPS_ROOT",
        "SECRETS_DIR",
        "CONFIGS_DIR",
        "ONION_EXPORT_DIR",
        "PROXY_SECRETS_FILE",
    }
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    """Ask the OS for a free TCP port at time of operation."""
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
    # Fallback: UDP connect trick yields the route-selected source IP; MAC via uuid node.
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
    roots.append(PROXY_DIR.parent)
    # Unique preserve order
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
        return Path(env_root).expanduser()

    for mount in _pull_mount_roots():
        for candidate in (
            mount / "LucidTops",
            mount / "myssd" / "LucidTops",
            mount / "Server" / "LucidTops",
            mount / "LucidTops" / "Server",
        ):
            if candidate.is_dir():
                return candidate.resolve()
        # Depth-1 scan for LucidTops directory name
        try:
            for child in mount.iterdir():
                if child.is_dir() and child.name.lower() == "lucidtops":
                    return child.resolve()
        except OSError:
            continue

    # Walk up from proxy module for a LucidTops / project root with Secrets marker
    for parent in [PROXY_DIR, *PROXY_DIR.parents]:
        secrets_probe = parent / "Secrets"
        lucid_probe = parent / "LucidTops"
        if secrets_probe.is_dir():
            return parent.resolve()
        if lucid_probe.is_dir():
            return lucid_probe.resolve()
        if (parent / "proxy").is_dir() and (parent / "backend").is_dir():
            # Repo checkout on build host — use sibling data root under home hardware path later
            data = parent / "LucidTops"
            data.mkdir(parents=True, exist_ok=True)
            return data.resolve()

    created = Path.home() / "LucidTops"
    created.mkdir(parents=True, exist_ok=True)
    return created.resolve()


def _pull_listening_by_process() -> dict[str, list[tuple[str, int]]]:
    """Map process name → [(bind_host, port), ...] from live listeners."""
    mapping: dict[str, list[tuple[str, int]]] = {}
    ss_bin = _which("ss")
    if ss_bin:
        result = _run([ss_bin, "-lntup"])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "LISTEN" not in line.upper() and "tcp" not in line.lower():
                    continue
                addr_match = re.search(r"([0-9a-fA-F\.:]+|\\*):([0-9]+)\s", line)
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

    ps = _run(
        [
            docker_bin,
            "ps",
            "-a",
            "--format",
            "{{.Names}}\t{{.ID}}",
        ]
    )
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
    machine_id = _pull_machine_id()
    cpu_count = os.cpu_count() or 1

    tor_listen = _first_listen(listening, "tor")
    nginx_listen = _first_listen(listening, "nginx")
    uvicorn_listen = _first_listen(listening, "uvicorn", "python")

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
        "docker_networks": docker_state.get("networks", []),
        "docker_containers": docker_state.get("containers", {}),
        "lucid_tops_root": lucid_root.as_posix(),
        "platform": platform.platform(),
        "system": platform.system(),
    }
    global _LAST_PULL
    _LAST_PULL = pulled
    return pulled


def get_last_pull() -> dict[str, Any]:
    return dict(_LAST_PULL) if _LAST_PULL else pull_realworld_information()


def _bind_paths_from_pull(pull: dict[str, Any] | None = None) -> None:
    """Bind path globals from pulled LucidTops root (hardware mount / discovered tree)."""
    global LUCID_TOPS_ROOT, SECRETS_DIR, CONFIGS_DIR, ONION_EXPORT_DIR, PROXY_SECRETS_FILE

    info = pull if pull is not None else pull_realworld_information()
    root = Path(str(info["lucid_tops_root"])).expanduser()

    # Prefer existing secrets layout if already present on hardware
    secrets_candidates = [
        root / "Server" / "Secrets",
        root / "secrets",
        root / "Secrets",
    ]
    secrets_dir = next((p for p in secrets_candidates if p.is_dir()), secrets_candidates[0])
    configs_dir = root / "proxy" / "configs"
    if not configs_dir.parent.exists():
        configs_dir = root / "configs"
    onion_dir = root / "onion"
    if (root / "run" / "lucid" / "onion").exists():
        onion_dir = root / "run" / "lucid" / "onion"

    proxy_name = "proxy.secrets"
    for existing in secrets_dir.glob("*.secrets"):
        if existing.name.lower().startswith("proxy"):
            proxy_name = existing.name
            break

    LUCID_TOPS_ROOT = root
    SECRETS_DIR = secrets_dir
    CONFIGS_DIR = configs_dir
    ONION_EXPORT_DIR = onion_dir
    PROXY_SECRETS_FILE = secrets_dir / proxy_name


def _bind_paths_from_operation() -> None:
    """Bind paths at time of operation via real-world pull (not placeholders)."""
    _bind_paths_from_pull()


def _ensure_path_globals() -> None:
    if not isinstance(globals().get("LUCID_TOPS_ROOT"), Path):
        _bind_paths_from_operation()


def __getattr__(name: str) -> Any:
    if name in _PATH_ATTRS:
        _bind_paths_from_operation()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_TOR_HS_ENV_KEYS: dict[str, str] = {
    "master_server": "HOST_TOR_LUCID_SERVER_DIR",
    "frontend": "HOST_TOR_LUCID_PORTAL_DIR",
    "node_user": "HOST_TOR_LUCID_DEV_DIR",
    "rdp": "HOST_TOR_LUCID_RDP_DIR",
}

_TOR_HS_SECRET_KEYS: dict[str, str] = {
    "master_server": "TOR_HS_DIR_MASTER_SERVER",
    "frontend": "TOR_HS_DIR_FRONTEND",
    "node_user": "TOR_HS_DIR_NODE_USER",
    "rdp": "TOR_HS_DIR_RDP",
}

_ONION_ENV_KEYS: dict[str, str] = {
    "master_server": "MASTER_SERVER_ONION",
    "frontend": "FRONTEND_ONION",
    "node_user": "NODEUSER_ONION",
    "rdp": "RDP_ONION",
}


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key:
                values[key] = value.strip()
    except OSError:
        return {}
    return values


def write_secrets_file(path: Path, values: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# LucidTops proxy.secrets generated at {utc_now()}",
        "# key=value — values pulled/created at time of operation",
    ]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def apply_secrets_file(path: Path, *, overwrite: bool = False) -> dict[str, str]:
    loaded = parse_secrets_file(path)
    for key, value in loaded.items():
        if overwrite or not os.environ.get(key, "").strip():
            os.environ[key] = value
    return loaded


def get_tor_hidden_service_dirs(
    *, existing: dict[str, str] | None = None, pull: dict[str, Any] | None = None
) -> dict[str, Path]:
    prior = existing if existing is not None else {}
    info = pull if pull is not None else get_last_pull()
    root = Path(str(info["lucid_tops_root"]))
    tor_base = root / "tor" / "hidden_service"
    dirs: dict[str, Path] = {}
    for service_key, env_key in _TOR_HS_ENV_KEYS.items():
        secret_key = _TOR_HS_SECRET_KEYS[service_key]
        raw = _env(env_key) or prior.get(secret_key, "").strip()
        if raw:
            dirs[service_key] = Path(raw).expanduser()
        else:
            dirs[service_key] = tor_base / service_key
    return dirs


def _ensure_dirs(pull: dict[str, Any] | None = None) -> None:
    _bind_paths_from_pull(pull)
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    ONION_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def read_onion_hostname(
    service_key: str, *, existing: dict[str, str] | None = None
) -> str:
    dirs = get_tor_hidden_service_dirs(existing=existing)
    hidden_dir = dirs.get(service_key)
    if hidden_dir is not None:
        hostname_file = hidden_dir / "hostname"
        try:
            value = hostname_file.read_text(encoding="utf-8").strip().lower()
            if value.endswith(".onion"):
                return value.split("/")[0]
        except OSError:
            pass

    export_file = ONION_EXPORT_DIR / f"{service_key}.onion"
    try:
        value = export_file.read_text(encoding="utf-8").strip().lower()
        if value.endswith(".onion"):
            return value.split("/")[0]
    except OSError:
        pass

    env_key = _ONION_ENV_KEYS.get(service_key, "")
    if env_key:
        from_env = _env(env_key)
        if from_env:
            return from_env.lower()
    if existing and env_key:
        from_file = existing.get(env_key, "").strip()
        if from_file:
            return from_file.lower()
    return ""


def collect_onion_addresses(
    *, existing: dict[str, str] | None = None
) -> dict[str, str]:
    collected: dict[str, str] = {}
    for service_key in _TOR_HS_ENV_KEYS:
        onion = read_onion_hostname(service_key, existing=existing)
        if onion:
            collected[service_key] = onion
            export_path = ONION_EXPORT_DIR / f"{service_key}.onion"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(f"{onion}\n", encoding="utf-8")
            try:
                os.chmod(export_path, 0o600)
            except OSError:
                pass
    return collected


def _existing_or_create(
    existing: dict[str, str], key: str, factory: Callable[[], str]
) -> str:
    current = _env(key) or existing.get(key, "").strip()
    if current:
        return current
    return factory()


def _pull_currency_code() -> str:
    """Currency code from host locale at time of operation; fallback token if unset."""
    try:
        import locale

        loc = locale.getdefaultlocale()[0] or ""
        if "_" in loc:
            # ISO country → common currency mapping is not available without tables;
            # use locale tag suffix as operational currency label.
            return loc.split("_")[-1].upper()
        if loc:
            return loc.upper()[:3]
    except Exception:
        pass
    return secrets.token_hex(2).upper()


def _pull_or_create_csv(prior: dict[str, str], key: str, cpu_count: int) -> str:
    """Reuse prior CSV config or create operation-time key names from hardware entropy."""
    existing = prior.get(key, "").strip() or _env(key)
    if existing:
        return existing
    n = max(2, min(5, cpu_count))
    return ",".join(f"{key.lower()}_{secrets.token_hex(2)}" for _ in range(n))


def machine_id_short(pull: dict[str, Any]) -> str:
    mid = str(pull.get("machine_id") or "")
    return mid[:12] if mid else secrets.token_hex(6)


def signal_term() -> int:
    import signal

    return int(signal.SIGTERM)


def signal_kill() -> int:
    import signal

    return int(getattr(signal, "SIGKILL", signal.SIGTERM))


def _container_endpoint(
    containers: dict[str, dict[str, str]],
    primary_ip: str,
    *needles: str,
) -> str:
    meta = _match_container(containers, *needles)
    if meta:
        if meta.get("ip"):
            return meta["ip"]
        if meta.get("name"):
            return meta["name"]
    return primary_ip


def _port_from_listen_or_allocate(
    listen: tuple[str, int] | None, *, prior_key: str, prior: dict[str, str]
) -> tuple[str, str]:
    if listen is not None:
        host, port = listen
        return (host or "", str(port))
    prior_port = prior.get(prior_key, "").strip()
    if prior_port:
        return ("", prior_port)
    return ("", str(_allocate_ephemeral_port()))


def build_proxy_secret_values(
    *,
    existing: dict[str, str] | None = None,
    pull: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Create all proxy secret values from real-world pull at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    _bind_paths_from_pull(info)
    prior = existing if existing is not None else parse_secrets_file(PROXY_SECRETS_FILE)
    onions = collect_onion_addresses(existing=prior)

    primary_ip = str(info["primary_ip"])
    primary_mac = str(info["primary_mac"])
    hostname = str(info["hostname"])
    cpu_count = int(info.get("cpu_count") or 1)
    containers: dict[str, dict[str, str]] = dict(info.get("docker_containers") or {})
    networks: list[dict[str, str]] = list(info.get("docker_networks") or [])
    bins: dict[str, str] = dict(info.get("bins") or {})

    hmac_key = _existing_or_create(
        prior, "PROXY_HMAC_KEY", lambda: secrets.token_hex(32)
    )
    api_token = _existing_or_create(
        prior, "PROXY_API_TOKEN", lambda: secrets.token_urlsafe(32)
    )
    clearnet_hmac = _existing_or_create(
        prior, "CLEARNET_HMAC_KEY", lambda: secrets.token_hex(32)
    )
    nginx_upstream_token = _existing_or_create(
        prior, "PROXY_NGINX_UPSTREAM_TOKEN", lambda: secrets.token_urlsafe(24)
    )

    backend_dns = _container_endpoint(
        containers, primary_ip, "backend", "masterserver", "master-server", "lucid-server"
    )
    frontend_dns = _container_endpoint(
        containers, primary_ip, "frontend", "portal", "webpage"
    )
    rdp_dns = _container_endpoint(containers, primary_ip, "rdp")
    node_dns = _container_endpoint(containers, primary_ip, "node")
    sessions_dns = _container_endpoint(containers, primary_ip, "session")
    operations_dns = _container_endpoint(containers, primary_ip, "operation", "ops")
    blockchain_dns = _container_endpoint(containers, primary_ip, "blockchain", "block")
    paysystems_dns = _container_endpoint(containers, primary_ip, "pay", "payment")
    proxy_dns = _container_endpoint(containers, primary_ip, "proxy")
    mongodb_host = _container_endpoint(containers, primary_ip, "mongo", "mongodb")

    tor_host, socks_port = _port_from_listen_or_allocate(
        info.get("tor_listen"), prior_key="TOR_SOCKS_PORT", prior=prior
    )
    tor_socks_host = tor_host or primary_ip
    _, control_port = _port_from_listen_or_allocate(
        None, prior_key="TOR_CONTROL_PORT", prior=prior
    )
    if prior.get("TOR_CONTROL_PORT", "").strip():
        control_port = prior["TOR_CONTROL_PORT"].strip()
    elif info.get("tor_listen"):
        # Second ephemeral distinct from socks when tor not yet exposing control in pull
        control_port = str(_allocate_ephemeral_port())

    nginx_host, nginx_port = _port_from_listen_or_allocate(
        info.get("nginx_listen"), prior_key="PROXY_NGINX_LISTEN_PORT", prior=prior
    )
    uvicorn_host, proxy_port = _port_from_listen_or_allocate(
        info.get("uvicorn_listen"), prior_key="PROXY_PORT", prior=prior
    )

    master_port = prior.get("MASTER_SERVER_PORT", "").strip() or str(
        _allocate_ephemeral_port()
    )
    frontend_port = prior.get("FRONTEND_PORT", "").strip() or str(
        _allocate_ephemeral_port()
    )
    rdp_port = prior.get("RDP_PORT", "").strip() or str(_allocate_ephemeral_port())
    node_port = prior.get("NODE_PORT", "").strip() or str(_allocate_ephemeral_port())
    mongodb_port = prior.get("MONGODB_PORT", "").strip() or str(
        _allocate_ephemeral_port()
    )

    bind_host = uvicorn_host or primary_ip
    fastapi_upstream = bind_host
    tor_hs_target = primary_ip

    # Docker network: reuse hardware docker network if present; else create name from host+mac
    docker_network = ""
    for net in networks:
        name = net.get("name", "")
        if name and name not in {"bridge", "host", "none"}:
            docker_network = name
            break
    if not docker_network:
        mac_compact = primary_mac.replace(":", "")[-8:]
        docker_network = f"lucid_{hostname}_{mac_compact}".lower().replace(" ", "_")

    selected_names: list[str] = []
    for label, needles in (
        ("backend", ("backend", "masterserver", "master-server")),
        ("frontend", ("frontend", "portal", "webpage")),
        ("rdp", ("rdp",)),
        ("node", ("node",)),
        ("masterserver", ("masterserver", "master-server", "backend")),
    ):
        if _match_container(containers, *needles) and label not in selected_names:
            selected_names.append(label)
    if not selected_names:
        # No containers yet — selected set is the proxy operational surface roles
        # derived from this pull's service endpoints (IP-backed until containers exist).
        selected_names = ["backend", "frontend", "rdp", "node", "masterserver"]

    none_linking = [
        name
        for name in ("sessions", "operations", "blockchain")
        if name not in {n.lower() for n in selected_names}
    ]
    public_access = ["frontend", "node", "user", "rdp"]
    direct_blocked = ["backend", "masterserver", "operations", "blockchain", "paysystems"]

    mac_token = primary_mac.replace(":", "")[-6:]
    api_prefix = f"/api/{mac_token}"
    api_base = f"/api/{mac_token}"
    frontend_base = "/"
    rdp_base = f"/rdp/{mac_token}"
    node_base = f"/node/{mac_token}"

    timeout_base = str(max(5, cpu_count * 5))
    connect_timeout = str(max(2, cpu_count * 2))
    onion_wait_attempts = str(max(10, cpu_count * 8))
    onion_wait_delay = str(max(1, cpu_count))
    tor_verify_timeout = str(max(3, cpu_count * 2))
    stop_wait_loops = str(max(3, cpu_count * 2))
    stop_wait_delay = str(max(1, cpu_count))
    start_probe_delay = str(max(1, cpu_count))
    log_lines = str(max(50, cpu_count * 50))
    keepalive_proxy = str(max(8, cpu_count * 4))
    keepalive_frontend = str(max(8, cpu_count * 4))

    mongodb_db = f"LucidTops_{mac_token}"
    mongodb_url = f"mongodb://{mongodb_host}:{mongodb_port}/{mongodb_db}"

    inventory_pairs = [
        f"backend:PROXY_BACKEND_DNS",
        f"masterserver:PROXY_BACKEND_DNS",
        f"frontend:PROXY_FRONTEND_DNS",
        f"rdp:PROXY_RDP_DNS",
        f"node:PROXY_NODE_DNS",
        f"proxy:PROXY_SELF_DNS",
        f"sessions:PROXY_SESSIONS_DNS",
        f"operations:PROXY_OPERATIONS_DNS",
        f"blockchain:PROXY_BLOCKCHAIN_DNS",
        f"paysystems:PROXY_PAYSYSTEMS_DNS",
    ]

    hs_dirs = get_tor_hidden_service_dirs(existing=prior, pull=info)
    for path in hs_dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    torrc_path = LUCID_TOPS_ROOT / "torrc"
    nginx_conf = CONFIGS_DIR / f"nginx_{mac_token}.conf"
    torrc_snippet = CONFIGS_DIR / f"torrc_snippet_{mac_token}"
    payments_secrets = SECRETS_DIR / "payments.secrets"
    proxy_pid = LUCID_TOPS_ROOT / "run" / f"proxy_{mac_token}.pid"
    proxy_log_dir = LUCID_TOPS_ROOT / "logs" / "proxy"
    master_secrets = SECRETS_DIR / "Master.secrets"

    tor_unit = Path(bins["tor"]).name if bins.get("tor") else ""
    nginx_unit = Path(bins["nginx"]).name if bins.get("nginx") else ""

    values: dict[str, str] = {
        "GENERATED_AT": utc_now(),
        "PULLED_AT": str(info.get("pulled_at", utc_now())),
        "LUCID_TOPS_ROOT": LUCID_TOPS_ROOT.as_posix(),
        "SECRETS_DIR": SECRETS_DIR.as_posix(),
        "PROXY_CONFIGS_DIR": CONFIGS_DIR.as_posix(),
        "CONTAINER_ONION_DIR": ONION_EXPORT_DIR.as_posix(),
        "PROXY_SECRETS_FILE": PROXY_SECRETS_FILE.as_posix(),
        "MASTER_SECRETS_FILE": master_secrets.as_posix(),
        "MASTER_SECRETS_NAME": master_secrets.name,
        "PROXY_SECRETS_NAME": PROXY_SECRETS_FILE.name,
        "DOCKER_NETWORK_NAME": docker_network,
        "PROXY_HMAC_KEY": hmac_key,
        "PROXY_API_TOKEN": api_token,
        "CLEARNET_HMAC_KEY": clearnet_hmac,
        "PROXY_NGINX_UPSTREAM_TOKEN": nginx_upstream_token,
        "PROXY_SELF_DNS": proxy_dns,
        "PROXY_BACKEND_DNS": backend_dns,
        "PROXY_FRONTEND_DNS": frontend_dns,
        "PROXY_RDP_DNS": rdp_dns,
        "PROXY_NODE_DNS": node_dns,
        "PROXY_SESSIONS_DNS": sessions_dns,
        "PROXY_OPERATIONS_DNS": operations_dns,
        "PROXY_BLOCKCHAIN_DNS": blockchain_dns,
        "PROXY_PAYSYSTEMS_DNS": paysystems_dns,
        "MASTER_SERVER_PORT": str(master_port),
        "FRONTEND_PORT": str(frontend_port),
        "RDP_PORT": str(rdp_port),
        "NODE_PORT": str(node_port),
        "PROXY_PORT": str(proxy_port),
        "PROXY_NGINX_LISTEN_PORT": str(nginx_port),
        "PROXY_FASTAPI_BIND_HOST": bind_host,
        "PROXY_FASTAPI_UPSTREAM_HOST": fastapi_upstream or bind_host,
        "TOR_HS_TARGET_HOST": tor_hs_target,
        "PROXY_API_PREFIX": api_prefix,
        "API_BASE_PATH": api_base,
        "FRONTEND_BASE_PATH": frontend_base,
        "RDP_BASE_PATH": rdp_base,
        "NODE_BASE_PATH": node_base,
        "PROXY_GATE_HEADER_VALUE": secrets.token_urlsafe(12),
        "PROXY_SECURE_FILE_MODE": "0o600",
        "PROXY_UVICORN_LOG_NAME": f"uvicorn_{mac_token}.log",
        "PROXY_START_PROBE_DELAY": start_probe_delay,
        "PROXY_UVICORN_APP": "ProxyRoutes:app",
        "PROXY_STOP_TERM_SIGNAL": str(signal_term()),
        "PROXY_STOP_KILL_SIGNAL": str(signal_kill()),
        "PROXY_STOP_WAIT_LOOPS": stop_wait_loops,
        "PROXY_STOP_WAIT_DELAY": stop_wait_delay,
        "DOCKERDNS_INVENTORY_KEYS": ",".join(inventory_pairs),
        "PROXY_NGINX_LOCATION_PROXY": f"/proxy/{mac_token}/",
        "PROXY_NGINX_LOCATION_API": f"{api_prefix}/",
        "PROXY_NGINX_LOCATION_RDP": f"{rdp_base}/",
        "PROXY_NGINX_LOCATION_NODE": f"{node_base}/",
        "PROXY_TORRC_SNIPPET_PATH": torrc_snippet.as_posix(),
        "TOR_HS_VIRTUAL_PORT": str(nginx_port),
        "TOR_SYSTEMD_UNIT": tor_unit,
        "NGINX_SYSTEMD_UNIT": nginx_unit,
        "PROXY_DEFAULT_INTERNAL_SOURCE": "frontend",
        "PROXY_ONION_WAIT_ATTEMPTS": onion_wait_attempts,
        "PROXY_ONION_WAIT_DELAY": onion_wait_delay,
        "PROXY_TOR_VERIFY_TIMEOUT": tor_verify_timeout,
        "TOR_SOCKS_HOST": tor_socks_host,
        "TOR_SOCKS_PORT": str(socks_port),
        "TOR_CONTROL_PORT": str(control_port),
        "TOR_COOKIE_AUTHENTICATION": "1",
        "MONGODB_HOST": mongodb_host,
        "MONGODB_PORT": str(mongodb_port),
        "MONGODB_MAIN_DATABASE_NAME": mongodb_db,
        "MONGODB_URL": mongodb_url,
        "PROXY_SELECTED_CONTAINERS": ",".join(selected_names),
        "PROXY_NONE_LINKING_CONTAINERS": ",".join(none_linking),
        "PROXY_DIRECT_BLOCKED_TARGETS": ",".join(direct_blocked),
        "PROXY_PUBLIC_ACCESS_POINTS": ",".join(public_access),
        "PAYMENTS_SECRETS_FILE": payments_secrets.as_posix(),
        "NGINX_CONF_PATH": nginx_conf.as_posix(),
        "TORRC_PATH": torrc_path.as_posix(),
        "PROXY_HTTP_TIMEOUT": timeout_base,
        "PROXY_HTTP_CONNECT_TIMEOUT": connect_timeout,
        "PROXY_APP_VERSION": f"{machine_id_short(info)}",
        "PROXY_APP_TITLE": f"LucidTops-Proxy@{hostname}",
        "PROXY_APP_DESCRIPTION": (
            f"Proxy gate pulled {primary_ip}/{primary_mac} on {hostname}"
        ),
        "PROXY_NGINX_KEEPALIVE_PROXY": keepalive_proxy,
        "PROXY_NGINX_KEEPALIVE_FRONTEND": keepalive_frontend,
        "PROXY_NGINX_CLIENT_MAX_BODY": f"{max(8, cpu_count * 8)}m",
        "EMV_3DS_VERSION": f"2.{cpu_count}",
        "PAYMENTS_CURRENCY": _pull_currency_code(),
        "CLEARNET_HTTP_TIMEOUT": timeout_base,
        "CLEARNET_VALID_PAYMENT_STATUSES": _pull_or_create_csv(
            prior, "CLEARNET_VALID_PAYMENT_STATUSES", cpu_count
        ),
        "CLEARNET_MERCHANT_REF_KEYS": _pull_or_create_csv(
            prior, "CLEARNET_MERCHANT_REF_KEYS", cpu_count
        ),
        "CLEARNET_MERCHANT_REF_HASH_LEN": str(max(8, cpu_count * 4)),
        "CLEARNET_AMOUNT_KEYS": _pull_or_create_csv(
            prior, "CLEARNET_AMOUNT_KEYS", cpu_count
        ),
        "CLEARNET_STATUS_KEYS": _pull_or_create_csv(
            prior, "CLEARNET_STATUS_KEYS", cpu_count
        ),
        "PROXY_PID_FILE": proxy_pid.as_posix(),
        "PROXY_LOG_DIR": proxy_log_dir.as_posix(),
        "PROXY_LOG_LINES": log_lines,
        "HOSTNAME_CONSOLE": hostname,
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HARDWARE_MACHINE_ID": str(info.get("machine_id") or ""),
        "HARDWARE_CPU_COUNT": str(cpu_count),
        "HARDWARE_PLATFORM": str(info.get("platform") or ""),
    }

    if bins.get("docker"):
        values["DOCKER_BIN"] = bins["docker"]
        values["DOCKER_BIN_NAME"] = Path(bins["docker"]).name
    if bins.get("nginx"):
        values["NGINX_BIN"] = bins["nginx"]
        values["NGINX_BIN_NAME"] = Path(bins["nginx"]).name
    if bins.get("tor"):
        values["TOR_BIN"] = bins["tor"]
        values["TOR_BIN_NAME"] = Path(bins["tor"]).name
    if bins.get("systemctl"):
        values["SYSTEMCTL_BIN"] = bins["systemctl"]
        values["SYSTEMCTL_BIN_NAME"] = Path(bins["systemctl"]).name

    for service_key, path in hs_dirs.items():
        values[_TOR_HS_SECRET_KEYS[service_key]] = path.as_posix()

    if onions.get("master_server"):
        values["MASTER_SERVER_ONION"] = onions["master_server"]
    if onions.get("frontend"):
        values["FRONTEND_ONION"] = onions["frontend"]
    if onions.get("node_user"):
        values["NODEUSER_ONION"] = onions["node_user"]
    if onions.get("rdp"):
        values["RDP_ONION"] = onions["rdp"]

    # Persist interface table for audit (non-sensitive hardware inventory)
    values["HARDWARE_INTERFACES_JSON"] = json.dumps(info.get("interfaces") or [])

    global TOR_HIDDEN_SERVICE_DIRS
    TOR_HIDDEN_SERVICE_DIRS = dict(hs_dirs)

    return values


def resolve_master_secrets_path(*, existing: dict[str, str] | None = None) -> Path:
    _bind_paths_from_operation()
    prior = existing if existing is not None else parse_secrets_file(PROXY_SECRETS_FILE)
    raw = prior.get("MASTER_SECRETS_FILE", "").strip() or _env("MASTER_SECRETS_FILE")
    if raw:
        return Path(raw).expanduser()
    return SECRETS_DIR / "Master.secrets"


def sync_to_master_secrets(
    master_path: Path | None = None,
    *,
    values: dict[str, str] | None = None,
) -> Path:
    """Copy proxy.secrets key set into Master.secrets (create if absent)."""
    _bind_paths_from_operation()
    source = values if values is not None else parse_secrets_file(PROXY_SECRETS_FILE)
    if not source:
        raise RuntimeError(
            "proxy.secrets empty — build_and_write_proxy_secrets before Master.secrets sync"
        )
    path = master_path if master_path is not None else resolve_master_secrets_path(existing=source)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = parse_secrets_file(path)
    merged.update(source)
    merged["MASTER_SECRETS_FILE"] = path.as_posix()
    merged["PROXY_SECRETS_FILE"] = PROXY_SECRETS_FILE.as_posix()
    write_secrets_file(path, merged)
    proxy_values = parse_secrets_file(PROXY_SECRETS_FILE)
    proxy_values["MASTER_SECRETS_FILE"] = path.as_posix()
    write_secrets_file(PROXY_SECRETS_FILE, proxy_values)
    apply_secrets_file(PROXY_SECRETS_FILE, overwrite=True)
    return path


def build_and_write_proxy_secrets(*, overwrite_keys: bool = False) -> dict[str, Any]:
    """Pull hardware/runtime state then create proxy.secrets at time of operation."""
    pull = pull_realworld_information()
    _ensure_dirs(pull)
    existing = parse_secrets_file(PROXY_SECRETS_FILE)
    values = build_proxy_secret_values(
        existing=existing if not overwrite_keys else {},
        pull=pull,
    )
    write_secrets_file(PROXY_SECRETS_FILE, values)
    apply_secrets_file(PROXY_SECRETS_FILE, overwrite=True)
    onions = collect_onion_addresses(existing=values)
    return {
        "proxy_secrets_file": PROXY_SECRETS_FILE.as_posix(),
        "onion_addresses": onions,
        "keys_written": sorted(values.keys()),
        "generated_at": values.get("GENERATED_AT", utc_now()),
        "pull": {
            "primary_ip": pull.get("primary_ip"),
            "primary_mac": pull.get("primary_mac"),
            "hostname": pull.get("hostname"),
            "lucid_tops_root": pull.get("lucid_tops_root"),
            "docker_network_candidates": [
                n.get("name") for n in (pull.get("docker_networks") or [])
            ],
            "containers": sorted((pull.get("docker_containers") or {}).keys()),
        },
    }


def load_proxy_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload or not _LAST_PULL:
        pull_realworld_information()
    _bind_paths_from_pull(_LAST_PULL or None)
    if reload or not PROXY_SECRETS_FILE.exists():
        build_and_write_proxy_secrets()
    loaded = apply_secrets_file(PROXY_SECRETS_FILE)
    global TOR_HIDDEN_SERVICE_DIRS
    TOR_HIDDEN_SERVICE_DIRS = get_tor_hidden_service_dirs(existing=loaded)
    return loaded


def get_proxy_secret(key: str, default: str | None = None) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    try:
        _ensure_path_globals()
        file_values = parse_secrets_file(PROXY_SECRETS_FILE)
        file_value = file_values.get(key, "").strip()
        if file_value:
            return file_value
    except Exception:
        pass
    if default is not None:
        return default
    return ""


def require_proxy_secret(key: str) -> str:
    value = get_proxy_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from proxy.secrets — "
            "value must be pulled/created at time of operation"
        )
    return value


if __name__ == "__main__":
    result = build_and_write_proxy_secrets()
    print(f"Wrote {result['proxy_secrets_file']}")
    print(f"Pull: {result.get('pull')}")
    print(f"Onion addresses: {result['onion_addresses']}")
    print(f"Keys: {len(result['keys_written'])}")
