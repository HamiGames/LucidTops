"""Pull real-world hardware and runtime content at time of operation for AdminGui.

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

ADMINGUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADMINGUI_DIR.parent

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
        try:
            for child in mount.iterdir():
                if child.is_dir() and child.name.lower() == "lucidtops":
                    return child.resolve()
        except OSError:
            continue
    for parent in [ADMINGUI_DIR, *ADMINGUI_DIR.parents]:
        if (parent / "secrets").is_dir() or (parent / "Secrets").is_dir():
            return parent.resolve()
        if (parent / "proxy").is_dir() and (parent / "backend").is_dir():
            data = parent / "LucidTops"
            data.mkdir(parents=True, exist_ok=True)
            return data.resolve()
    created = Path.home() / "LucidTops"
    created.mkdir(parents=True, exist_ok=True)
    return created.resolve()


def _pull_admingui_secrets_dir(lucid_root: Path) -> Path:
    """AdminGui secrets live under /mnt/myssd/LucidTops/AdminGui/secrets (§16.1)."""
    env_dir = _env("SECRETS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    for candidate in (
        Path("/mnt/myssd/LucidTops/AdminGui/secrets"),
        lucid_root / "AdminGui" / "secrets",
        ADMINGUI_DIR / "secrets",
        lucid_root / "secrets" / "AdminGui",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    for candidate in (
        Path("/mnt/myssd/LucidTops/AdminGui/secrets"),
        lucid_root / "AdminGui" / "secrets",
        ADMINGUI_DIR / "secrets",
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        except OSError:
            continue
    target = lucid_root / "AdminGui" / "secrets"
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _pull_lucid_secrets_dir(lucid_root: Path) -> Path:
    env_dir = _env("LUCID_SECRETS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    for candidate in (
        lucid_root / "secrets",
        lucid_root / "Secrets",
        lucid_root / "Server" / "Secrets",
        Path("/mnt/myssd/LucidTops/secrets"),
        Path("/mnt/myssd/LucidTops/Server/Secrets"),
    ):
        if candidate.is_dir():
            return candidate.resolve()
    target = lucid_root / "secrets"
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


def _pull_onion_from_secrets(secrets_dirs: list[Path]) -> dict[str, str]:
    onions = {"frontend": "", "master_server": "", "node_user": ""}
    for secrets_dir in secrets_dirs:
        for name in (
            "frontend.secrets",
            "proxy.secrets",
            "backend.secrets",
            "admin.secrets",
            "admingui.secrets",
            "user.secrets",
        ):
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


def _pull_onion_addresses(
    lucid_root: Path, secrets_dirs: list[Path]
) -> dict[str, str]:
    onions = _pull_onion_from_secrets(secrets_dirs)
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
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                if "tor" not in child.name.lower():
                    continue
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


def _discover_shell_binaries() -> dict[str, str]:
    shells: dict[str, str] = {"bash": "", "sh": ""}
    for name in ("bash", "sh"):
        path = _which(name)
        if path:
            shells[name] = path
    return shells


def _discover_webpage_admin_paths(lucid_root: Path) -> dict[str, str]:
    pages: dict[str, str] = {"admin_home": "", "login": "", "scheme": ""}
    search_roots = [
        PROJECT_ROOT / "frontend" / "webpage",
        lucid_root / "frontend" / "webpage",
        lucid_root / "webpage",
        ADMINGUI_DIR.parent / "frontend" / "webpage",
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        for name in ("AdminHome.html", "adminHome.html", "admin-home.html"):
            candidate = root / name
            if candidate.is_file() and not pages["admin_home"]:
                pages["admin_home"] = name
                break
        for name in ("login.html",):
            candidate = root / name
            if candidate.is_file() and not pages["login"]:
                pages["login"] = name
    return pages


def _pull_page_paths_from_secrets(secrets_dirs: list[Path]) -> dict[str, str]:
    pages = {"admin_home": "", "login": "", "scheme": ""}
    for secrets_dir in secrets_dirs:
        for name in (
            "frontend.secrets",
            "admin.secrets",
            "admingui.secrets",
            "user.secrets",
        ):
            parsed = _parse_secrets_file(secrets_dir / name)
            if not pages["admin_home"]:
                pages["admin_home"] = (
                    parsed.get("FRONTEND_ADMIN_HOME_PATH")
                    or parsed.get("ADMIN_HOME_PAGE_PATH")
                    or ""
                )
            if not pages["login"]:
                pages["login"] = parsed.get("FRONTEND_LOGIN_PATH") or ""
            if not pages["scheme"]:
                pages["scheme"] = (
                    parsed.get("ADMIN_FRONTEND_SCHEME")
                    or parsed.get("USER_FRONTEND_SCHEME")
                    or parsed.get("FRONTEND_TUNNEL_SCHEME")
                    or ""
                )
    return pages


def _pull_accounts_admin_secrets(lucid_root: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for candidate in (
        lucid_root / "accounts" / "AdminID.secrets",
        Path("/mnt/myssd/LucidTops/accounts/AdminID.secrets"),
    ):
        if candidate.is_file():
            merged.update(_parse_secrets_file(candidate))
    return merged


def _detect_master_server_colocated(lucid_root: Path) -> dict[str, Any]:
    """Detect whether this console hosts the self-hosted MasterServer container."""
    docker = _which("docker")
    evidence: list[str] = []
    colocated = False

    socket_paths = [
        Path("/var/run/docker.sock"),
        Path("//./pipe/docker_engine"),
    ]
    for sock in socket_paths:
        if sock.exists():
            evidence.append(f"docker_socket:{sock.as_posix()}")

    if docker:
        for args in (
            ["ps", "--format", "{{.Names}} {{.Image}}"],
            ["ps", "-a", "--format", "{{.Names}} {{.Image}}"],
        ):
            result = _run([docker, *args])
            if result.returncode != 0 or not result.stdout.strip():
                continue
            text = result.stdout.lower()
            markers = (
                "masterserver",
                "master-server",
                "lucid-server",
                "lucidtops/server",
                "backend",
            )
            for marker in markers:
                if marker in text:
                    colocated = True
                    evidence.append(f"docker_ps:{marker}")
                    break
            if colocated:
                break

    backend_dir = PROJECT_ROOT / "backend"
    if backend_dir.is_dir() and (lucid_root.is_dir() or Path("/mnt/myssd/LucidTops").is_dir()):
        evidence.append("backend_tree_present")
        if platform.system().lower() == "linux" and Path("/mnt/myssd/LucidTops").is_dir():
            colocated = True
            evidence.append("linux_myssd_lucidtops")

    return {
        "colocated": colocated,
        "docker_bin": docker,
        "evidence": evidence,
    }


def _pull_validation_and_smtp_from_secrets(
    secrets_dirs: list[Path], accounts: dict[str, str]
) -> dict[str, str]:
    found: dict[str, str] = {}
    keys = (
        "ADMIN_DOWNLOAD_AUTH_EMAIL",
        "ADMIN_SMTP_HOST",
        "ADMIN_SMTP_PORT",
        "ADMIN_SMTP_USER",
        "ADMIN_SMTP_PASSWORD",
        "ADMIN_SMTP_USE_TLS",
        "ADMIN_USERDB_VALIDATE_URL",
        "ADMIN_SOCKS_HOST",
        "ADMIN_SOCKS_PORT",
        "ADMIN_SOCKS_PROXY",
        "ADMIN_ACCEPTED_AUTH_EMAIL",
    )
    for key in keys:
        env_val = _env(key)
        if env_val:
            found[key] = env_val
    for secrets_dir in secrets_dirs:
        for name in (
            "admingui.secrets",
            "admin.secrets",
            "admin_auth.secrets",
            "ID.secrets",
            "frontend.secrets",
            "backend.secrets",
        ):
            parsed = _parse_secrets_file(secrets_dir / name)
            for key in keys:
                if key not in found and parsed.get(key):
                    found[key] = parsed[key]
    for key in keys:
        if key not in found and accounts.get(key):
            found[key] = accounts[key]
    return found


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
    admin_secrets_dir = _pull_admingui_secrets_dir(lucid_root)
    lucid_secrets_dir = _pull_lucid_secrets_dir(lucid_root)
    secrets_dirs = [admin_secrets_dir, lucid_secrets_dir]
    machine_id = _pull_machine_id()
    tor_bins = _discover_tor_binaries()
    shells = _discover_shell_binaries()
    onions = _pull_onion_addresses(lucid_root, secrets_dirs)
    page_secrets = _pull_page_paths_from_secrets(secrets_dirs)
    page_files = _discover_webpage_admin_paths(lucid_root)
    accounts = _pull_accounts_admin_secrets(lucid_root)
    colocated = _detect_master_server_colocated(lucid_root)
    smtp_validate = _pull_validation_and_smtp_from_secrets(secrets_dirs, accounts)

    admin_home = page_secrets["admin_home"] or page_files.get("admin_home") or ""
    login_page = page_secrets["login"] or page_files.get("login") or ""
    scheme = page_secrets["scheme"] or ""

    session_state_path = admin_secrets_dir / "admingui_session.state"
    id_name = _env("ID_SECRETS_NAME") or "ID.secrets"
    admin_name = _env("ADMIN_SECRETS_NAME") or "admingui.secrets"
    auth_name = _env("ADMIN_AUTH_SECRETS_NAME") or "admin_auth.secrets"

    pulled: dict[str, Any] = {
        "pulled_at": utc_now(),
        "hostname": hostname,
        "machine_id": machine_id,
        "primary_ip": primary_ip,
        "primary_mac": primary_mac,
        "primary_iface": primary.get("name", ""),
        "interfaces": interfaces,
        "lucid_tops_root": lucid_root.as_posix(),
        "secrets_dir": admin_secrets_dir.as_posix(),
        "lucid_secrets_dir": lucid_secrets_dir.as_posix(),
        "session_state_path": session_state_path.as_posix(),
        "tor_bin": tor_bins.get("tor") or "",
        "tor_browser_bin": tor_bins.get("tor_browser") or "",
        "tor_browser_launcher": tor_bins.get("tor_browser_launcher") or "",
        "shell_bash": shells.get("bash") or "",
        "shell_sh": shells.get("sh") or "",
        "onions": onions,
        "admin_home_page_path": admin_home,
        "login_page_path": login_page,
        "frontend_scheme": scheme,
        "id_secrets_name": id_name,
        "admin_secrets_name": admin_name,
        "admin_auth_secrets_name": auth_name,
        "master_server_colocated": bool(colocated.get("colocated")),
        "master_server_colocation_evidence": colocated.get("evidence") or [],
        "docker_bin": colocated.get("docker_bin") or "",
        "accounts_admin": accounts,
        "smtp_validate": smtp_validate,
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
        "LUCID_SECRETS_DIR": str(info["lucid_secrets_dir"]),
        "HOST_PRIMARY_IP": str(info["primary_ip"]),
        "HOST_PRIMARY_MAC": str(info["primary_mac"]),
        "HOST_MACHINE_ID": str(info["machine_id"]),
        "HOST_HOSTNAME": str(info["hostname"]),
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "ID_SECRETS_NAME": str(info["id_secrets_name"]),
        "ADMIN_SECRETS_NAME": str(info["admin_secrets_name"]),
        "ADMIN_AUTH_SECRETS_NAME": str(info["admin_auth_secrets_name"]),
        "ID_SECRETS_FILE": (secrets_dir / str(info["id_secrets_name"])).as_posix(),
        "ADMIN_SECRETS_FILE": (secrets_dir / str(info["admin_secrets_name"])).as_posix(),
        "ADMIN_AUTH_SECRETS_FILE": (
            secrets_dir / str(info["admin_auth_secrets_name"])
        ).as_posix(),
        "ADMINGUI_SESSION_STATE_FILE": str(info["session_state_path"]),
        "MASTER_SERVER_COLOCATED": "1" if info.get("master_server_colocated") else "0",
    }
    onions = info.get("onions") or {}
    if onions.get("frontend"):
        mapping["FRONTEND_ONION"] = str(onions["frontend"])
    if onions.get("master_server"):
        mapping["MASTER_SERVER_ONION"] = str(onions["master_server"])
    if info.get("tor_bin"):
        mapping["ADMIN_TOR_BIN"] = str(info["tor_bin"])
    if info.get("tor_browser_bin"):
        mapping["ADMIN_TOR_BROWSER_BIN"] = str(info["tor_browser_bin"])
    if info.get("admin_home_page_path"):
        mapping["FRONTEND_ADMIN_HOME_PATH"] = str(info["admin_home_page_path"])
    if info.get("frontend_scheme"):
        mapping["ADMIN_FRONTEND_SCHEME"] = str(info["frontend_scheme"])
    if info.get("shell_bash"):
        mapping["ADMIN_SHELL_BASH"] = str(info["shell_bash"])
    if info.get("shell_sh"):
        mapping["ADMIN_SHELL_SH"] = str(info["shell_sh"])
    smtp_validate = info.get("smtp_validate") or {}
    if isinstance(smtp_validate, dict):
        for key, value in smtp_validate.items():
            if value:
                mapping[str(key)] = str(value)

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


def _build_tor_commands(info: dict[str, Any], existing: dict[str, str]) -> dict[str, str]:
    tor_bin = (
        _env("ADMIN_TOR_BIN")
        or existing.get("ADMIN_TOR_BIN")
        or str(info.get("tor_bin") or "")
    )
    browser_bin = (
        _env("ADMIN_TOR_BROWSER_BIN")
        or existing.get("ADMIN_TOR_BROWSER_BIN")
        or str(info.get("tor_browser_bin") or "")
        or str(info.get("tor_browser_launcher") or "")
    )
    start_cmd = _env("ADMIN_TOR_START_COMMAND") or existing.get("ADMIN_TOR_START_COMMAND", "")
    browser_cmd = (
        _env("ADMIN_TOR_BROWSER_COMMAND") or existing.get("ADMIN_TOR_BROWSER_COMMAND", "")
    )

    if not start_cmd and tor_bin:
        start_cmd = f'"{tor_bin}"'
    if not browser_cmd and browser_bin:
        browser_cmd = f'"{browser_bin}" "{{url}}"'

    return {
        "ADMIN_TOR_BIN": tor_bin,
        "ADMIN_TOR_BROWSER_BIN": browser_bin,
        "ADMIN_TOR_START_COMMAND": start_cmd,
        "ADMIN_TOR_BROWSER_COMMAND": browser_cmd,
    }


def build_admingui_secrets(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create admingui.secrets from hardware pull at time of operation."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    secrets_path = Path(
        _env("ADMIN_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["admin_secrets_name"])
    )
    prior = _merge_existing_secrets(secrets_path)
    lucid_prior = _merge_existing_secrets(
        Path(str(info["lucid_secrets_dir"])) / "frontend.secrets"
    )
    accounts = info.get("accounts_admin") or {}
    if not isinstance(accounts, dict):
        accounts = {}
    smtp_validate = info.get("smtp_validate") or {}
    if not isinstance(smtp_validate, dict):
        smtp_validate = {}

    def from_any(*keys: str, factory: Callable[[], str] | None = None) -> str:
        for key in keys:
            value = _env(key) or prior.get(key, "") or lucid_prior.get(key, "")
            if not value and key in accounts:
                value = str(accounts.get(key) or "")
            if not value and key in smtp_validate:
                value = str(smtp_validate.get(key) or "")
            if value:
                return value
        if factory is not None:
            return factory()
        return ""

    tor_cmds = _build_tor_commands(info, {**prior, **lucid_prior})
    onions = info.get("onions") or {}

    scheme = from_any(
        "ADMIN_FRONTEND_SCHEME",
        "USER_FRONTEND_SCHEME",
        "FRONTEND_TUNNEL_SCHEME",
        factory=lambda: str(info.get("frontend_scheme") or ""),
    )
    if not scheme and onions.get("frontend"):
        scheme = from_any("ADMIN_FRONTEND_SCHEME", factory=lambda: "http")

    frontend_onion = from_any(
        "FRONTEND_ONION",
        factory=lambda: str(onions.get("frontend") or ""),
    )
    admin_home = from_any(
        "FRONTEND_ADMIN_HOME_PATH",
        "ADMIN_HOME_PAGE_PATH",
        factory=lambda: str(info.get("admin_home_page_path") or ""),
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
        "LUCID_SECRETS_DIR": str(info["lucid_secrets_dir"]),
        "ID_SECRETS_NAME": str(info["id_secrets_name"]),
        "ADMIN_SECRETS_NAME": str(info["admin_secrets_name"]),
        "ADMIN_AUTH_SECRETS_NAME": str(info["admin_auth_secrets_name"]),
        "ID_SECRETS_FILE": (
            Path(str(info["secrets_dir"])) / str(info["id_secrets_name"])
        ).as_posix(),
        "ADMIN_SECRETS_FILE": secrets_path.as_posix(),
        "ADMIN_AUTH_SECRETS_FILE": (
            Path(str(info["secrets_dir"])) / str(info["admin_auth_secrets_name"])
        ).as_posix(),
        "ADMINGUI_SESSION_STATE_FILE": str(info["session_state_path"]),
        "FRONTEND_ONION": frontend_onion,
        "MASTER_SERVER_ONION": from_any(
            "MASTER_SERVER_ONION",
            factory=lambda: str(onions.get("master_server") or ""),
        ),
        "ADMIN_FRONTEND_SCHEME": scheme,
        "FRONTEND_ADMIN_HOME_PATH": admin_home,
        "FRONTEND_LOGIN_PATH": from_any(
            "FRONTEND_LOGIN_PATH",
            factory=lambda: str(info.get("login_page_path") or ""),
        ),
        "ADMIN_TOR_BIN": tor_cmds["ADMIN_TOR_BIN"],
        "ADMIN_TOR_BROWSER_BIN": tor_cmds["ADMIN_TOR_BROWSER_BIN"],
        "ADMIN_TOR_START_COMMAND": tor_cmds["ADMIN_TOR_START_COMMAND"],
        "ADMIN_TOR_BROWSER_COMMAND": tor_cmds["ADMIN_TOR_BROWSER_COMMAND"],
        "ADMIN_SHELL_BASH": from_any(
            "ADMIN_SHELL_BASH", factory=lambda: str(info.get("shell_bash") or "")
        ),
        "ADMIN_SHELL_SH": from_any(
            "ADMIN_SHELL_SH", factory=lambda: str(info.get("shell_sh") or "")
        ),
        "MASTER_SERVER_COLOCATED": "1" if info.get("master_server_colocated") else "0",
        "ADMIN_SYSTEM": str(info["system"]),
        "ADMIN_PLATFORM": str(info["platform"]),
        "ADMIN_FIREWALL_RULE_NAME": from_any("ADMIN_FIREWALL_RULE_NAME"),
        "ADMIN_DOWNLOAD_AUTH_EMAIL": from_any("ADMIN_DOWNLOAD_AUTH_EMAIL"),
        "ADMIN_ACCEPTED_AUTH_EMAIL": from_any(
            "ADMIN_ACCEPTED_AUTH_EMAIL", "ADMIN_DOWNLOAD_AUTH_EMAIL"
        ),
        "ADMIN_SMTP_HOST": from_any("ADMIN_SMTP_HOST"),
        "ADMIN_SMTP_PORT": from_any("ADMIN_SMTP_PORT"),
        "ADMIN_SMTP_USER": from_any("ADMIN_SMTP_USER"),
        "ADMIN_SMTP_PASSWORD": from_any("ADMIN_SMTP_PASSWORD"),
        "ADMIN_SMTP_USE_TLS": from_any("ADMIN_SMTP_USE_TLS"),
        "ADMIN_USERDB_VALIDATE_URL": from_any("ADMIN_USERDB_VALIDATE_URL"),
        "ADMIN_SOCKS_HOST": from_any("ADMIN_SOCKS_HOST"),
        "ADMIN_SOCKS_PORT": from_any("ADMIN_SOCKS_PORT"),
        "ADMIN_SOCKS_PROXY": from_any("ADMIN_SOCKS_PROXY"),
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
                f"{key} missing after hardware pull — cannot create admingui.secrets"
            )

    _write_secrets_file(secrets_path, built, label="admingui.secrets")
    return built


def build_id_secrets_shell(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create or refresh ID.secrets shell from hardware pull; preserve AdminID/TokenID."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    path = Path(
        _env("ID_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["id_secrets_name"])
    )
    prior = _merge_existing_secrets(path)
    accounts = info.get("accounts_admin") or {}
    if not isinstance(accounts, dict):
        accounts = {}

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
        "ADMIN_ID",
        "TOKEN_ID",
        "USER_ID",
        "NODE_ID",
        "MASTER_USER_ID",
        "MASTER_SERVER_ID",
        "TIER_SELECTED",
        "USER_ROLE",
    ):
        value = _env(key) or prior.get(key, "") or str(accounts.get(key) or "")
        # AdminID.secrets may use alternate labels
        if not value and key == "ADMIN_ID":
            value = (
                prior.get("ADMINID", "")
                or str(accounts.get("ADMINID") or "")
                or str(accounts.get("AdminID") or "")
            )
        if value:
            built[key] = value

    if built.get("ADMIN_ID"):
        built["USER_ROLE"] = built.get("USER_ROLE") or "admin"
    for key, value in prior.items():
        if key not in built:
            built[key] = value
    _write_secrets_file(path, built, label="ID.secrets")
    return built


def build_admin_auth_secrets_shell(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Ensure admin_auth.secrets exists; preserve SMTP/challenge keys from prior pull."""
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    path = Path(
        _env("ADMIN_AUTH_SECRETS_FILE")
        or Path(str(info["secrets_dir"])) / str(info["admin_auth_secrets_name"])
    )
    prior = _merge_existing_secrets(path)
    admin_built = build_admingui_secrets(info)
    built: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": str(info["primary_ip"]),
        "HARDWARE_PRIMARY_MAC": str(info["primary_mac"]),
        "SECRETS_DIR": str(info["secrets_dir"]),
        "ADMIN_DOWNLOAD_AUTH_EMAIL": admin_built.get("ADMIN_DOWNLOAD_AUTH_EMAIL", ""),
        "ADMIN_ACCEPTED_AUTH_EMAIL": admin_built.get("ADMIN_ACCEPTED_AUTH_EMAIL", ""),
        "ADMIN_SMTP_HOST": admin_built.get("ADMIN_SMTP_HOST", ""),
        "ADMIN_SMTP_PORT": admin_built.get("ADMIN_SMTP_PORT", ""),
        "ADMIN_SMTP_USER": admin_built.get("ADMIN_SMTP_USER", ""),
        "ADMIN_SMTP_PASSWORD": admin_built.get("ADMIN_SMTP_PASSWORD", ""),
        "ADMIN_SMTP_USE_TLS": admin_built.get("ADMIN_SMTP_USE_TLS", ""),
        "PULLED_AT": str(info["pulled_at"]),
    }
    for key, value in prior.items():
        if key.startswith("ADMIN_AUTH_") or key in built:
            if not built.get(key) and value:
                built[key] = value
        elif key not in built:
            built[key] = value
    _write_secrets_file(path, built, label="admin_auth.secrets")
    return built


def build_all_admingui_secrets(
    pull: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    info = pull if pull is not None else pull_realworld_information()
    bind_operation_environ(info)
    return {
        "admin": build_admingui_secrets(info),
        "id": build_id_secrets_shell(info),
        "auth": build_admin_auth_secrets_shell(info),
    }


def main() -> int:
    info = pull_realworld_information()
    built = build_all_admingui_secrets(info)
    print(
        json.dumps(
            {
                "pulled_at": info["pulled_at"],
                "primary_ip": info["primary_ip"],
                "primary_mac": info["primary_mac"],
                "secrets_dir": info["secrets_dir"],
                "frontend_onion": built["admin"].get("FRONTEND_ONION", ""),
                "admin_home": built["admin"].get("FRONTEND_ADMIN_HOME_PATH", ""),
                "master_server_colocated": built["admin"].get(
                    "MASTER_SERVER_COLOCATED", "0"
                ),
                "tor_bin": built["admin"].get("ADMIN_TOR_BIN", ""),
                "tor_browser_bin": built["admin"].get("ADMIN_TOR_BROWSER_BIN", ""),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
