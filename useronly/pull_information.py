"""Pull real-world hardware and runtime content at time of operation for UsersOnly.

At time of operation = when this script/module is run.
Values (IP, MAC, hostname, Tor binaries, onion, mounts) MUST come from live hardware —
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
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

USERONLY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = USERONLY_DIR.parent

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


def _pull_macos_interfaces() -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    result = _run(["ifconfig"])
    if result.returncode != 0 or not result.stdout:
        return interfaces
    current = ""
    mac = ""
    ipv4 = ""
    for line in result.stdout.splitlines():
        if line and not line.startswith("\t") and not line.startswith(" "):
            if current and mac:
                interfaces.append({"name": current, "mac": mac, "ipv4": ipv4})
            current = line.split(":", 1)[0].strip()
            mac = ""
            ipv4 = ""
            continue
        mac_match = re.search(r"ether\s+([0-9a-f:]+)", line, re.I)
        if mac_match:
            mac = mac_match.group(1).lower()
        ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
        if ip_match and not ip_match.group(1).startswith("127."):
            ipv4 = ip_match.group(1)
    if current and mac:
        interfaces.append({"name": current, "mac": mac, "ipv4": ipv4})
    return [row for row in interfaces if row.get("mac") and row["mac"] != "00:00:00:00:00:00"]


def _pull_interfaces() -> list[dict[str, str]]:
    system = platform.system().lower()
    if system == "windows":
        pulled = _pull_windows_interfaces()
    elif system == "darwin":
        pulled = _pull_macos_interfaces()
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
    if platform.system().lower() == "windows":
        ps = _which("powershell") or _which("pwsh")
        if ps:
            result = _run(
                [
                    ps,
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID",
                ]
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().replace("-", "").lower()
    if platform.system().lower() == "darwin":
        result = _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout or "")
        if match:
            return match.group(1).replace("-", "").lower()
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
    system = platform.system().lower()
    if system == "windows":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:/")
            if drive.exists():
                roots.append(drive)
    elif system == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            try:
                for child in volumes.iterdir():
                    if child.is_dir():
                        roots.append(child)
            except OSError:
                pass
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
        try:
            for child in mount.iterdir():
                if child.is_dir() and child.name.lower() == "lucidtops":
                    return child.resolve()
        except OSError:
            continue
    for parent in [USERONLY_DIR, *USERONLY_DIR.parents]:
        if (parent / "secrets").is_dir() or (parent / "Secrets").is_dir():
            return parent.resolve()
        if (parent / "proxy").is_dir() and (parent / "backend").is_dir():
            data = parent / "LucidTops"
            data.mkdir(parents=True, exist_ok=True)
            return data.resolve()
    created = Path.home() / "LucidTops"
    created.mkdir(parents=True, exist_ok=True)
    return created.resolve()


def _pull_secrets_dir(lucid_root: Path) -> Path:
    """UserOnly secrets live under /mnt/myssd/LucidTops/useronly/secrets (§16.1)."""
    env_dir = _env("SECRETS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    for candidate in (
        Path("/mnt/myssd/LucidTops/useronly/secrets"),
        lucid_root / "useronly" / "secrets",
        lucid_root / "secrets",
        lucid_root / "Secrets",
        lucid_root / "Server" / "Secrets",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    target = lucid_root / "useronly" / "secrets"
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def _read_onion_file(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
        if value.endswith(".onion"):
            return value.split("/")[0]
    except OSError:
        pass
    return ""


def _pull_onion_from_secrets(secrets_dir: Path) -> dict[str, str]:
    onions = {"frontend": "", "master_server": "", "node_user": ""}
    for name in ("frontend.secrets", "proxy.secrets", "backend.secrets", "user.secrets"):
        parsed = _parse_secrets_file(secrets_dir / name)
        for key, map_key in (
            ("FRONTEND_ONION", "frontend"),
            ("MASTER_SERVER_ONION", "master_server"),
            ("NODEUSER_ONION", "node_user"),
        ):
            raw = parsed.get(key, "")
            if raw.endswith(".onion") and not onions[map_key]:
                onions[map_key] = raw.split("/")[0].lower()
    return onions


def _pull_onion_addresses(lucid_root: Path, secrets_dir: Path) -> dict[str, str]:
    onions = _pull_onion_from_secrets(secrets_dir)
    candidates = [
        lucid_root / "data" / "tor" / "onion",
        lucid_root / "onion",
        lucid_root / "run" / "lucid" / "onion",
        Path("/var/lib/tor"),
    ]
    for onion_dir in candidates:
        if not onion_dir.is_dir():
            continue
        mapping = {
            "frontend": ("frontend", "frontend_onion", "hs_frontend"),
            "master_server": ("master", "master_server", "backend", "hs_master"),
            "node_user": ("node", "nodeuser", "hs_node"),
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
    for env_key, map_key in (
        ("FRONTEND_ONION", "frontend"),
        ("MASTER_SERVER_ONION", "master_server"),
        ("NODEUSER_ONION", "node_user"),
    ):
        env_val = _env(env_key)
        if env_val.endswith(".onion"):
            onions[map_key] = env_val.split("/")[0].lower()
    return onions


def _candidate_search_roots() -> list[Path]:
    """Limited roots only — never walk entire system drives."""
    roots: list[Path] = [Path.home(), PROJECT_ROOT]
    system = platform.system().lower()
    if system == "windows":
        for key in ("LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            value = _env(key)
            if value:
                roots.append(Path(value))
        desktop = Path.home() / "Desktop"
        if desktop.is_dir():
            roots.append(desktop)
        downloads = Path.home() / "Downloads"
        if downloads.is_dir():
            roots.append(downloads)
    elif system == "darwin":
        roots.extend([Path("/Applications"), Path.home() / "Applications"])
    else:
        roots.extend(
            [
                Path("/usr/bin"),
                Path("/usr/local/bin"),
                Path("/opt"),
                Path.home() / ".local" / "share",
                Path.home() / "Downloads",
                Path.home() / "Desktop",
            ]
        )
    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = resolved.as_posix()
        if key not in seen and resolved.exists():
            seen.add(key)
            ordered.append(resolved)
    return ordered


def _discover_tor_binaries() -> dict[str, str]:
    found: dict[str, str] = {
        "tor": "",
        "tor_browser": "",
        "tor_browser_launcher": "",
    }
    for name in ("tor", "tor.exe"):
        path = _which(name)
        if path:
            found["tor"] = path
            break
    for name in (
        "start-tor-browser",
        "start-tor-browser.desktop",
        "tor-browser",
        "torbrowser-launcher",
    ):
        path = _which(name)
        if path:
            if "launcher" in name:
                found["tor_browser_launcher"] = path
            else:
                found["tor_browser"] = path
    for name in ("torbrowser-launcher", "tor-browser-launcher"):
        path = _which(name)
        if path:
            found["tor_browser_launcher"] = path
            break

    # Probe known relative install layouts under limited roots (no deep drive walks).
    relative_probes = (
        Path("Tor Browser") / "Browser" / "firefox.exe",
        Path("Tor Browser") / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
        Path("TorBrowser") / "Browser" / "firefox.exe",
        Path("tor-browser") / "Browser" / "firefox",
        Path("tor-browser") / "start-tor-browser",
        Path("tor-browser_en-US") / "Browser" / "firefox",
        Path("tor-browser_en-US") / "start-tor-browser.desktop",
        Path("TorBrowser-Data") / "Tor" / "tor.exe",
    )
    for root in _candidate_search_roots():
        for rel in relative_probes:
            candidate = root / rel
            if not candidate.is_file():
                continue
            name_l = candidate.name.lower()
            if name_l in {"tor", "tor.exe"} and not found["tor"]:
                found["tor"] = candidate.as_posix()
            elif not found["tor_browser"]:
                found["tor_browser"] = candidate.as_posix()
        # One-level scan for Tor-named directories only.
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                if "tor" not in child.name.lower():
                    continue
                for rel in relative_probes:
                    # rel may already include Tor Browser prefix; also try basename probes
                    for probe in (
                        child / "Browser" / "firefox.exe",
                        child / "Browser" / "firefox",
                        child / "start-tor-browser",
                        child / "start-tor-browser.desktop",
                        child / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
                        child / "Tor" / "tor.exe",
                        child / "tor.exe",
                        child / "tor",
                    ):
                        if not probe.is_file():
                            continue
                        name_l = probe.name.lower()
                        if name_l in {"tor", "tor.exe"} and not found["tor"]:
                            found["tor"] = probe.as_posix()
                        elif not found["tor_browser"]:
                            found["tor_browser"] = probe.as_posix()
        except OSError:
            continue
        if found["tor"] and (found["tor_browser"] or found["tor_browser_launcher"]):
            break
    return found


def _discover_package_managers() -> dict[str, str]:
    managers: dict[str, str] = {}
    for name in ("apt-get", "apt", "dnf", "yum", "pacman", "zypper", "brew", "winget", "choco", "scoop"):
        path = _which(name)
        if path:
            managers[name] = path
    return managers


def _discover_webpage_paths(lucid_root: Path) -> dict[str, str]:
    pages: dict[str, str] = {"home": "", "register": "", "login": ""}
    search_roots = [
        PROJECT_ROOT / "frontend" / "webpage",
        lucid_root / "frontend" / "webpage",
        lucid_root / "webpage",
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        mapping = {
            "home": ("home.html", "home_page.html", "index.html"),
            "register": ("register.html",),
            "login": ("login.html",),
        }
        for key, names in mapping.items():
            if pages[key]:
                continue
            for name in names:
                candidate = root / name
                if candidate.is_file():
                    pages[key] = name
                    break
    return pages


def _pull_page_paths_from_secrets(secrets_dir: Path) -> dict[str, str]:
    pages = {"home": "", "register": "", "login": "", "scheme": ""}
    for name in ("frontend.secrets", "user.secrets", "registration.secrets"):
        parsed = _parse_secrets_file(secrets_dir / name)
        if not pages["home"]:
            pages["home"] = (
                parsed.get("FRONTEND_HOME_PAGE_PATH")
                or parsed.get("FRONTEND_HOME_PATH")
                or ""
            )
        if not pages["register"]:
            pages["register"] = parsed.get("FRONTEND_REGISTER_PATH") or ""
        if not pages["login"]:
            pages["login"] = parsed.get("FRONTEND_LOGIN_PATH") or ""
        if not pages["scheme"]:
            pages["scheme"] = (
                parsed.get("USER_FRONTEND_SCHEME")
                or parsed.get("FRONTEND_TUNNEL_SCHEME")
                or parsed.get("FRONTEND_SCHEME")
                or ""
            )
    return pages


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

    lucid_root = _pull_lucid_tops_root()
    secrets_dir = _pull_secrets_dir(lucid_root)
    machine_id = _pull_machine_id()
    tor_bins = _discover_tor_binaries()
    package_managers = _discover_package_managers()
    onions = _pull_onion_addresses(lucid_root, secrets_dir)
    page_secrets = _pull_page_paths_from_secrets(secrets_dir)
    page_files = _discover_webpage_paths(lucid_root)

    home_page = page_secrets["home"] or page_files.get("home") or ""
    register_page = page_secrets["register"] or page_files.get("register") or ""
    login_page = page_secrets["login"] or page_files.get("login") or ""
    scheme = page_secrets["scheme"] or ""

    session_state_path = secrets_dir / "useronly_session.state"
    registration_name = _env("REGISTRATION_SECRETS_NAME") or "registration.secrets"
    id_name = _env("ID_SECRETS_NAME") or "ID.secrets"
    user_name = _env("USER_SECRETS_NAME") or "user.secrets"

    pulled: dict[str, Any] = {
        "pulled_at": utc_now(),
        "hostname": hostname,
        "machine_id": machine_id,
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": secrets_dir.as_posix(),
        "session_state_path": session_state_path.as_posix(),
        "tor_bin": tor_bins.get("tor") or "",
        "tor_browser_bin": tor_bins.get("tor_browser") or "",
        "tor_browser_launcher": tor_bins.get("tor_browser_launcher") or "",
        "package_managers": package_managers,
        "onions": onions,
        "home_page_path": home_page,
        "register_page_path": register_page,
        "login_page_path": login_page,
        "frontend_scheme": scheme,
        "registration_secrets_name": registration_name,
        "id_secrets_name": id_name,
        "user_secrets_name": user_name,
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
        "SECRETS_DIR_NAME": secrets_dir.name,
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "HOST_HOSTNAME": str(info["hostname"]),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "REGISTRATION_SECRETS_NAME": str(info["registration_secrets_name"]),
        "ID_SECRETS_NAME": str(info["id_secrets_name"]),
        "USER_SECRETS_NAME": str(info["user_secrets_name"]),
        "REGISTRATION_SECRETS_FILE": (
            secrets_dir / str(info["registration_secrets_name"])
        ).as_posix(),
        "ID_SECRETS_FILE": (secrets_dir / str(info["id_secrets_name"])).as_posix(),
        "USER_SECRETS_FILE": (secrets_dir / str(info["user_secrets_name"])).as_posix(),
        "USERONLY_SESSION_STATE_FILE": str(info["session_state_path"]),
    }
    onions = info.get("onions") or {}
    if onions.get("frontend"):
        mapping["FRONTEND_ONION"] = str(onions["frontend"])
    if onions.get("master_server"):
        mapping["MASTER_SERVER_ONION"] = str(onions["master_server"])
    if onions.get("node_user"):
        mapping["NODEUSER_ONION"] = str(onions["node_user"])
    if info.get("tor_bin"):
        mapping["USER_TOR_BIN"] = str(info["tor_bin"])
    if info.get("tor_browser_bin"):
        mapping["USER_TOR_BROWSER_BIN"] = str(info["tor_browser_bin"])
    if info.get("home_page_path"):
        mapping["FRONTEND_HOME_PAGE_PATH"] = str(info["home_page_path"])
    if info.get("register_page_path"):
        mapping["FRONTEND_REGISTER_PATH"] = str(info["register_page_path"])
    if info.get("frontend_scheme"):
        mapping["USER_FRONTEND_SCHEME"] = str(info["frontend_scheme"])

    for key, value in mapping.items():
        if not value or not str(value).strip():
            continue
        if overwrite or not _env(key):
            os.environ[key] = str(value).strip()
            bound[key] = str(value).strip()
    return bound


def _merge_existing_secrets(path: Path) -> dict[str, str]:
    return _parse_secrets_file(path)


def _write_secrets_file(path: Path, values: dict[str, str], *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# LucidTops {label} — generated at time of operation from hardware pull",
        f"# pulled_at={values.get('PULLED_AT', utc_now())}",
    ]
    for key in sorted(values.keys()):
        if values[key] == "":
            continue
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in values.items():
        if value and not _env(key):
            os.environ[key] = value


def _require_or_create(existing: dict[str, str], key: str, factory: Callable[[], str]) -> str:
    current = _env(key) or existing.get(key, "").strip()
    if current:
        return current
    return str(factory())


def _build_tor_commands(info: dict[str, Any], existing: dict[str, str]) -> dict[str, str]:
    tor_bin = (
        _env("USER_TOR_BIN")
        or existing.get("USER_TOR_BIN")
        or str(info.get("tor_bin") or "")
    )
    browser_bin = (
        _env("USER_TOR_BROWSER_BIN")
        or existing.get("USER_TOR_BROWSER_BIN")
        or str(info.get("tor_browser_bin") or "")
        or str(info.get("tor_browser_launcher") or "")
    )
    start_cmd = _env("USER_TOR_START_COMMAND") or existing.get("USER_TOR_START_COMMAND", "")
    browser_cmd = (
        _env("USER_TOR_BROWSER_COMMAND") or existing.get("USER_TOR_BROWSER_COMMAND", "")
    )
    background_cmd = (
        _env("USER_BACKGROUND_LAUNCH_COMMAND")
        or existing.get("USER_BACKGROUND_LAUNCH_COMMAND", "")
    )

    if not start_cmd and tor_bin:
        start_cmd = f'"{tor_bin}"'
    if not browser_cmd and browser_bin:
        browser_cmd = f'"{browser_bin}" "{{url}}"'
    if not background_cmd and start_cmd:
        background_cmd = start_cmd

    return {
        "USER_TOR_BIN": tor_bin,
        "USER_TOR_BROWSER_BIN": browser_bin,
        "USER_TOR_START_COMMAND": start_cmd,
        "USER_TOR_BROWSER_COMMAND": browser_cmd,
        "USER_BACKGROUND_LAUNCH_COMMAND": background_cmd,
    }


def _build_required_lists(info: dict[str, Any], existing: dict[str, str]) -> dict[str, str]:
    programs: list[str] = []
    files: list[str] = []
    # Always rebuild from live discovered binaries when present.
    for path in (info.get("tor_bin"), info.get("tor_browser_bin"), info.get("tor_browser_launcher")):
        if path and Path(str(path)).exists():
            programs.append(str(path))
            files.append(str(path))
    programs = list(dict.fromkeys(programs))
    files = list(dict.fromkeys(files))

    if not programs:
        raw_programs = _env("USER_REQUIRED_PROGRAMS") or existing.get("USER_REQUIRED_PROGRAMS", "")
        programs = [item.strip() for item in raw_programs.split(",") if item.strip()]
    if not files:
        raw_files = _env("USER_REQUIRED_FILES") or existing.get("USER_REQUIRED_FILES", "")
        files = [item.strip() for item in raw_files.split(",") if item.strip()]
    return {
        "USER_REQUIRED_PROGRAMS": ",".join(programs),
        "USER_REQUIRED_FILES": ",".join(files),
    }


def build_user_secrets(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create user.secrets from hardware pull + prior secrets at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    secrets_path = Path(
        _env("USER_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["user_secrets_name"])
    )
    prior = _merge_existing_secrets(secrets_path)
    frontend_prior = _merge_existing_secrets(Path(str(info["secrets_dir"])) / "frontend.secrets")
    proxy_prior = _merge_existing_secrets(Path(str(info["secrets_dir"])) / "proxy.secrets")
    onions = info.get("onions") or {}

    def from_any(*keys: str, factory: Callable[[], str] | None = None) -> str:
        for key in keys:
            value = (
                _env(key)
                or prior.get(key)
                or frontend_prior.get(key)
                or proxy_prior.get(key)
                or ""
            )
            if value:
                return value
        if factory is not None:
            return str(factory())
        return ""

    tor_cmds = _build_tor_commands(info, {**prior, **frontend_prior})
    required = _build_required_lists(info, prior)

    home_page = from_any(
        "FRONTEND_HOME_PAGE_PATH",
        factory=lambda: str(info.get("home_page_path") or ""),
    )
    register_page = from_any(
        "FRONTEND_REGISTER_PATH",
        factory=lambda: str(info.get("register_page_path") or ""),
    )
    scheme = from_any(
        "USER_FRONTEND_SCHEME",
        "FRONTEND_TUNNEL_SCHEME",
        factory=lambda: str(info.get("frontend_scheme") or ""),
    )
    if not scheme and onions.get("frontend"):
        # Onion Hidden Services speak HTTP on the client TorBrowser path.
        scheme = from_any("USER_FRONTEND_SCHEME", factory=lambda: "http")

    frontend_onion = from_any(
        "FRONTEND_ONION",
        factory=lambda: str(onions.get("frontend") or ""),
    )

    built: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HOSTNAME_CONSOLE": str(info["hostname"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "SECRETS_DIR_NAME": Path(str(info["secrets_dir"])).name,
        "REGISTRATION_SECRETS_NAME": str(info["registration_secrets_name"]),
        "ID_SECRETS_NAME": str(info["id_secrets_name"]),
        "USER_SECRETS_NAME": str(info["user_secrets_name"]),
        "REGISTRATION_SECRETS_FILE": (
            Path(str(info["secrets_dir"])) / str(info["registration_secrets_name"])
        ).as_posix(),
        "ID_SECRETS_FILE": (
            Path(str(info["secrets_dir"])) / str(info["id_secrets_name"])
        ).as_posix(),
        "USER_SECRETS_FILE": secrets_path.as_posix(),
        "USERONLY_SESSION_STATE_FILE": str(info["session_state_path"]),
        "FRONTEND_ONION": frontend_onion,
        "USER_FRONTEND_SCHEME": scheme,
        "FRONTEND_HOME_PAGE_PATH": home_page,
        "FRONTEND_REGISTER_PATH": register_page,
        "FRONTEND_LOGIN_PATH": from_any(
            "FRONTEND_LOGIN_PATH",
            factory=lambda: str(info.get("login_page_path") or ""),
        ),
        "USER_TOR_BIN": tor_cmds["USER_TOR_BIN"],
        "USER_TOR_BROWSER_BIN": tor_cmds["USER_TOR_BROWSER_BIN"],
        "USER_TOR_START_COMMAND": tor_cmds["USER_TOR_START_COMMAND"],
        "USER_TOR_BROWSER_COMMAND": tor_cmds["USER_TOR_BROWSER_COMMAND"],
        "USER_BACKGROUND_LAUNCH_COMMAND": tor_cmds["USER_BACKGROUND_LAUNCH_COMMAND"],
        "USER_REQUIRED_PROGRAMS": required["USER_REQUIRED_PROGRAMS"],
        "USER_REQUIRED_FILES": required["USER_REQUIRED_FILES"],
        "USER_SYSTEM": str(info["system"]),
        "USER_PLATFORM": str(info["platform"]),
        "USER_TOR_INSTALL_COMMAND": from_any("USER_TOR_INSTALL_COMMAND"),
        "USER_FIREWALL_RULE_NAME": from_any("USER_FIREWALL_RULE_NAME"),
        "PULLED_AT": str(info["pulled_at"]),
    }

    for key in (
        "HARDWARE_PRIMARY_IP",
        "HARDWARE_PRIMARY_MAC",
        "SECRETS_DIR",
        "LUCID_TOPS_ROOT",
    ):
        if not built.get(key):
            raise RuntimeError(
                f"{key} missing after hardware pull — cannot create user.secrets"
            )

    _write_secrets_file(secrets_path, built, label="user.secrets")
    return built


def build_registration_secrets(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create registration.secrets from hardware pull at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    path = Path(
        _env("REGISTRATION_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["registration_secrets_name"])
    )
    prior = _merge_existing_secrets(path)
    user_built = build_user_secrets(info)
    built = {
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HOSTNAME_CONSOLE": str(info["hostname"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "FRONTEND_ONION": user_built.get("FRONTEND_ONION", ""),
        "USER_FRONTEND_SCHEME": user_built.get("USER_FRONTEND_SCHEME", ""),
        "FRONTEND_HOME_PAGE_PATH": user_built.get("FRONTEND_HOME_PAGE_PATH", ""),
        "FRONTEND_REGISTER_PATH": user_built.get("FRONTEND_REGISTER_PATH", ""),
        "FRONTEND_LOGIN_PATH": user_built.get("FRONTEND_LOGIN_PATH", ""),
        "USER_TOR_START_COMMAND": user_built.get("USER_TOR_START_COMMAND", ""),
        "USER_TOR_BROWSER_COMMAND": user_built.get("USER_TOR_BROWSER_COMMAND", ""),
        "USER_BACKGROUND_LAUNCH_COMMAND": user_built.get(
            "USER_BACKGROUND_LAUNCH_COMMAND", ""
        ),
        "USER_REQUIRED_PROGRAMS": user_built.get("USER_REQUIRED_PROGRAMS", ""),
        "USER_REQUIRED_FILES": user_built.get("USER_REQUIRED_FILES", ""),
        "USERONLY_SESSION_STATE_FILE": user_built.get("USERONLY_SESSION_STATE_FILE", ""),
        "PULLED_AT": str(info["pulled_at"]),
    }
    for key, value in prior.items():
        if key not in built or not built[key]:
            built[key] = value
    _write_secrets_file(path, built, label="registration.secrets")
    return built


def build_id_secrets(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create or refresh ID.secrets shell from hardware pull; preserve existing IDs."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    path = Path(
        _env("ID_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["id_secrets_name"])
    )
    prior = _merge_existing_secrets(path)
    built: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HOSTNAME_CONSOLE": str(info["hostname"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "LUCID_TOPS_ROOT": str(info["lucid_tops_root"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "PULLED_AT": str(info["pulled_at"]),
    }
    for key in (
        "USER_ID",
        "NODE_ID",
        "TOKEN_ID",
        "ADMIN_ID",
        "MASTER_USER_ID",
        "TIER_SELECTED",
    ):
        value = _env(key) or prior.get(key, "")
        if value:
            built[key] = value
    role = ""
    if built.get("NODE_ID"):
        role = "node"
    elif built.get("USER_ID"):
        role = "user"
    elif prior.get("USER_ROLE"):
        role = prior["USER_ROLE"]
    if role:
        built["USER_ROLE"] = role
    for key, value in prior.items():
        if key not in built:
            built[key] = value
    _write_secrets_file(path, built, label="ID.secrets")
    return built


def build_all_useronly_secrets(pull: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    return {
        "user": build_user_secrets(info),
        "registration": build_registration_secrets(info),
        "id": build_id_secrets(info),
    }


def main() -> int:
    info = pull_realworld_information()
    built = build_all_useronly_secrets(info)
    print(
        json.dumps(
            {
                "pulled_at": info["pulled_at"],
                "primary_ip": info["primary_ip"],
                "primary_mac": info["primary_mac"],
                "secrets_dir": info["secrets_dir"],
                "frontend_onion": built["user"].get("FRONTEND_ONION", ""),
                "tor_bin": built["user"].get("USER_TOR_BIN", ""),
                "tor_browser_bin": built["user"].get("USER_TOR_BROWSER_BIN", ""),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
