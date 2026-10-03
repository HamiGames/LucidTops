""" import all required programs and files for the user system to be able to use the LucidTops system
install protocol:
- check for all required programs and files
- install all required programs and files
- verify all required programs and files are installed
- verify all required programs and files are working
- launch required programs in background
- open fontend/home_page.js in a new tor browser window
- open fontend/register.js in a new tor browser window
- use content from fontend/register.js to register to send request to the master server to create a new userID
- use content from fontend/login.js to login to the master server to access the user's dashboard


"""


from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_useronly_{module_name}"
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


_user_secrets = _load_local("user_secrets")
require_user_secret = _user_secrets.require_user_secret
get_user_secret = _user_secrets.get_user_secret
load_user_secrets = _user_secrets.load_user_secrets
registration_secrets_path = _user_secrets.registration_secrets_path
id_secrets_path = _user_secrets.id_secrets_path
ensure_user_secrets_from_pull = _user_secrets.ensure_user_secrets_from_pull

_pull = _load_local("pull_information")


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


def required_programs() -> list[str]:
    raw = require_user_secret("USER_REQUIRED_PROGRAMS")
    programs = [item.strip() for item in raw.split(",") if item.strip()]
    if not programs:
        raise RuntimeError("USER_REQUIRED_PROGRAMS empty — set at time of operation")
    return programs


def required_files() -> list[Path]:
    raw = require_user_secret("USER_REQUIRED_FILES")
    files = [Path(item.strip()).expanduser() for item in raw.split(",") if item.strip()]
    if not files:
        raise RuntimeError("USER_REQUIRED_FILES empty — set at time of operation")
    return files


def verify_required_programs() -> dict[str, Any]:
    missing: list[str] = []
    for name in required_programs():
        as_path = Path(name)
        if as_path.exists():
            continue
        if shutil.which(name) is None and shutil.which(as_path.name) is None:
            missing.append(name)
    if missing:
        raise RuntimeError(f"required programs missing: {', '.join(missing)}")
    return {"programs": required_programs(), "verified_at": utc_now()}


def verify_required_files() -> dict[str, Any]:
    missing = [path.as_posix() for path in required_files() if not path.exists()]
    if missing:
        raise RuntimeError(f"required files missing: {', '.join(missing)}")
    return {"files": [p.as_posix() for p in required_files()], "verified_at": utc_now()}


def ensure_user_secrets_present() -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    reg = registration_secrets_path()
    ident = id_secrets_path()
    if not reg.exists():
        raise RuntimeError(f"registration.secrets missing at {reg.as_posix()}")
    if not ident.exists():
        raise RuntimeError(f"ID.secrets missing at {ident.as_posix()}")
    return {
        "registration_secrets": reg.as_posix(),
        "id_secrets": ident.as_posix(),
        "checked_at": utc_now(),
    }


def _discover_install_command(info: dict[str, Any]) -> list[str]:
    """Resolve an OS-native Tor install command from live package managers."""
    managers: dict[str, str] = dict(info.get("package_managers") or {})
    system = str(info.get("system") or platform.system()).lower()
    prior = get_user_secret("USER_TOR_INSTALL_COMMAND")
    if prior:
        return [part for part in prior.split(" ") if part]

    if system == "windows":
        if managers.get("winget"):
            return [managers["winget"], "install", "-e", "--id", "TorProject.TorBrowser"]
        if managers.get("choco"):
            return [managers["choco"], "install", "tor-browser", "-y"]
        if managers.get("scoop"):
            return [managers["scoop"], "install", "tor-browser"]
    elif system == "darwin":
        if managers.get("brew"):
            return [managers["brew"], "install", "--cask", "tor-browser"]
    else:
        if managers.get("apt-get"):
            return [
                managers["apt-get"],
                "install",
                "-y",
                "tor",
                "torbrowser-launcher",
            ]
        if managers.get("apt"):
            return [managers["apt"], "install", "-y", "tor", "torbrowser-launcher"]
        if managers.get("dnf"):
            return [managers["dnf"], "install", "-y", "tor", "torbrowser-launcher"]
        if managers.get("pacman"):
            return [managers["pacman"], "-S", "--noconfirm", "tor", "torbrowser-launcher"]
        if managers.get("zypper"):
            return [managers["zypper"], "install", "-y", "tor", "torbrowser-launcher"]
        if managers.get("brew"):
            return [managers["brew"], "install", "tor"]
    return []


def ensure_tor_installed(info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure Tor / TorBrowser exist on the console; install via discovered package manager."""
    pull = info if info is not None else _pull.pull_realworld_information()
    _pull.bind_operation_environ(pull)
    tor_bin = str(pull.get("tor_bin") or "")
    browser_bin = str(pull.get("tor_browser_bin") or pull.get("tor_browser_launcher") or "")
    if tor_bin and Path(tor_bin).exists() and browser_bin and Path(browser_bin).exists():
        return {
            "status": "present",
            "tor_bin": tor_bin,
            "tor_browser_bin": browser_bin,
            "checked_at": utc_now(),
        }

    install_cmd = _discover_install_command(pull)
    if not install_cmd:
        raise RuntimeError(
            "Tor/TorBrowser missing and no package manager discovered on this console — "
            "install Tor Browser on the hardware, then re-run install"
        )

    result = _run(install_cmd)
    refreshed = _pull.pull_realworld_information()
    _pull.bind_operation_environ(refreshed, overwrite=True)
    _pull.build_all_useronly_secrets(refreshed)
    load_user_secrets(reload=True)

    tor_bin = str(refreshed.get("tor_bin") or get_user_secret("USER_TOR_BIN") or "")
    browser_bin = str(
        refreshed.get("tor_browser_bin")
        or refreshed.get("tor_browser_launcher")
        or get_user_secret("USER_TOR_BROWSER_BIN")
        or ""
    )
    if not browser_bin or not Path(browser_bin).exists():
        raise RuntimeError(
            "TorBrowser still missing after install attempt — "
            f"command={' '.join(install_cmd)} exit={result.returncode} "
            f"stderr={result.stderr.strip()[:400]}"
        )

    os.environ["USER_TOR_INSTALL_COMMAND"] = " ".join(install_cmd)
    _pull.build_user_secrets(refreshed)

    return {
        "status": "installed",
        "tor_bin": tor_bin,
        "tor_browser_bin": browser_bin,
        "install_command": install_cmd,
        "install_exit": result.returncode,
        "checked_at": utc_now(),
    }


def allowlist_tor_browser_firewall(browser_bin: str | None = None) -> dict[str, Any]:
    """Register discovered TorBrowser binary with the OS firewall allowlist."""
    path = (browser_bin or get_user_secret("USER_TOR_BROWSER_BIN") or "").strip()
    if not path:
        raise RuntimeError(
            "USER_TOR_BROWSER_BIN missing — cannot configure firewall allowlist"
        )
    binary = Path(path)
    if not binary.exists():
        raise RuntimeError(
            f"TorBrowser binary missing at {binary.as_posix()} — cannot allowlist"
        )

    system = (get_user_secret("USER_SYSTEM") or platform.system()).lower()
    rule_name = get_user_secret("USER_FIREWALL_RULE_NAME")
    if not rule_name:
        rule_name = f"LucidTops-TorBrowser-{binary.stem}"
        os.environ["USER_FIREWALL_RULE_NAME"] = rule_name

    actions: list[dict[str, Any]] = []
    if system == "windows":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            raise RuntimeError("powershell missing — cannot configure Windows firewall")
        script = (
            f"$name='{rule_name}'; $path='{binary.as_posix()}';"
            " if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {"
            " New-NetFirewallRule -DisplayName $name -Direction Outbound -Program $path"
            " -Action Allow -Profile Any | Out-Null };"
            " if (-not (Get-NetFirewallRule -DisplayName ($name+'-in') -ErrorAction SilentlyContinue)) {"
            " New-NetFirewallRule -DisplayName ($name+'-in') -Direction Inbound -Program $path"
            " -Action Allow -Profile Any | Out-Null }"
        )
        result = _run([ps, "-NoProfile", "-Command", script])
        actions.append(
            {
                "system": "windows",
                "exit": result.returncode,
                "stderr": result.stderr.strip()[:300],
            }
        )
        if result.returncode != 0:
            netsh = shutil.which("netsh")
            if netsh:
                out = _run(
                    [
                        netsh,
                        "advfirewall",
                        "firewall",
                        "add",
                        "rule",
                        f"name={rule_name}",
                        "dir=out",
                        "action=allow",
                        f"program={binary}",
                        "enable=yes",
                    ]
                )
                actions.append({"system": "windows-netsh", "exit": out.returncode})
    elif system == "darwin":
        # macOS Application Firewall: add unsigned/allow path via socketfilterfw when present.
        sockfw = Path("/usr/libexec/ApplicationFirewall/socketfilterfw")
        if sockfw.exists():
            result = _run([sockfw.as_posix(), "--add", binary.as_posix()])
            actions.append({"system": "darwin", "exit": result.returncode})
            _run([sockfw.as_posix(), "--unblockapp", binary.as_posix()])
        else:
            actions.append({"system": "darwin", "status": "socketfilterfw_absent"})
    else:
        ufw = shutil.which("ufw")
        firewall_cmd = shutil.which("firewall-cmd")
        if ufw:
            result = _run([ufw, "allow", "out", "from", "any", "to", "any"])
            actions.append(
                {
                    "system": "linux-ufw",
                    "exit": result.returncode,
                    "note": "egress allow; binary path recorded in secrets",
                }
            )
        elif firewall_cmd:
            result = _run([firewall_cmd, "--permanent", "--add-service=https"])
            actions.append({"system": "linux-firewalld", "exit": result.returncode})
            _run([firewall_cmd, "--reload"])
        else:
            actions.append(
                {
                    "system": "linux",
                    "status": "no_firewall_tool",
                    "binary": binary.as_posix(),
                }
            )

    return {
        "status": "allowlisted",
        "binary": binary.as_posix(),
        "rule_name": rule_name,
        "actions": actions,
        "configured_at": utc_now(),
    }


RDP_OPERATING_IMAGES = ("pickme/lucidtops_rdp:v1.0.0",)


def _import_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:  # noqa: BLE001 — presence check only
        return False
    return True


def _install_with_manager(info: dict[str, Any], packages: list[str]) -> list[str]:
    managers: dict[str, str] = dict(info.get("package_managers") or {})
    system = str(info.get("system") or platform.system()).lower()
    if system == "windows":
        if managers.get("winget"):
            command = [managers["winget"], "install", "-e", "--id", packages[0]]
        elif managers.get("choco"):
            command = [managers["choco"], "install", packages[0], "-y"]
        else:
            return []
    elif system == "darwin":
        if not managers.get("brew"):
            return []
        command = [managers["brew"], "install", *packages]
    else:
        manager = managers.get("apt-get") or managers.get("apt") or managers.get("dnf")
        if manager:
            command = [manager, "install", "-y", *packages]
        elif managers.get("pacman"):
            command = [managers["pacman"], "-S", "--noconfirm", *packages]
        elif managers.get("brew"):
            command = [managers["brew"], "install", *packages]
        else:
            return []
    _run(command)
    return command


def ensure_docker_installed(info: dict[str, Any]) -> dict[str, Any]:
    docker = str(info.get("docker_bin") or "") or (
        shutil.which("docker") or shutil.which("docker.exe") or ""
    )
    if docker and Path(docker).exists() or shutil.which("docker") or shutil.which("docker.exe"):
        found = docker or shutil.which("docker") or shutil.which("docker.exe") or ""
        return {"status": "present", "docker_bin": found, "checked_at": utc_now()}
    system = str(info.get("system") or platform.system()).lower()
    packages = ["Docker.DockerDesktop"] if system == "windows" else ["docker.io"]
    if system == "darwin":
        packages = ["--cask", "docker"]
    command = _install_with_manager(info, packages)
    found = shutil.which("docker") or shutil.which("docker.exe") or ""
    if not found:
        raise RuntimeError(
            "Docker missing after install attempt — install Docker on this console and re-run Install"
        )
    return {
        "status": "installed",
        "docker_bin": found,
        "install_command": command,
        "checked_at": utc_now(),
    }


def ensure_python_installed(info: dict[str, Any]) -> dict[str, Any]:
    found = str(info.get("python_bin") or "") or (
        shutil.which("python3") or shutil.which("python") or shutil.which("python.exe") or ""
    )
    if found:
        return {"status": "present", "python_bin": found, "checked_at": utc_now()}
    system = str(info.get("system") or platform.system()).lower()
    packages = ["Python.Python.3.12"] if system == "windows" else ["python3"]
    command = _install_with_manager(info, packages)
    found = shutil.which("python3") or shutil.which("python") or shutil.which("python.exe") or ""
    if not found:
        raise RuntimeError("Python interpreter missing on this console")
    return {
        "status": "installed",
        "python_bin": found,
        "install_command": command,
        "checked_at": utc_now(),
    }


def ensure_node_installed(info: dict[str, Any]) -> dict[str, Any]:
    found = str(info.get("node_bin") or "") or (
        shutil.which("node") or shutil.which("node.exe") or ""
    )
    if found:
        return {"status": "present", "node_bin": found, "checked_at": utc_now()}
    system = str(info.get("system") or platform.system()).lower()
    packages = ["OpenJS.NodeJS"] if system == "windows" else ["nodejs"]
    command = _install_with_manager(info, packages)
    found = shutil.which("node") or shutil.which("node.exe") or ""
    if not found:
        raise RuntimeError("JavaScript interpreter (node) missing on this console")
    return {
        "status": "installed",
        "node_bin": found,
        "install_command": command,
        "checked_at": utc_now(),
    }


def ensure_tk_installed(info: dict[str, Any]) -> dict[str, Any]:
    if _import_tkinter():
        return {"status": "present", "checked_at": utc_now()}
    system = str(info.get("system") or platform.system()).lower()
    packages = ["python3-tk"] if system not in {"windows", "darwin"} else ["python-tk"]
    if system == "windows":
        raise RuntimeError(
            "tkinter missing from this Python install — reinstall Python with Tcl/Tk"
        )
    command = _install_with_manager(info, packages)
    if not _import_tkinter():
        raise RuntimeError("tkinter still missing after install attempt")
    return {"status": "installed", "install_command": command, "checked_at": utc_now()}


def ensure_driver_directory(info: dict[str, Any]) -> dict[str, Any]:
    raw = str(info.get("driver_dir") or "")
    if not raw:
        raise RuntimeError("driver directory path missing from the console pull")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError(f"driver directory was not created at {path.as_posix()}")
    return {"status": "ready", "driver_dir": path.as_posix(), "checked_at": utc_now()}


def _docker_bin() -> str:
    found = shutil.which("docker") or shutil.which("docker.exe") or ""
    if not found:
        raise RuntimeError("docker binary missing — Install must finish before image checks")
    return found


def ensure_image(tag: str) -> dict[str, Any]:
    docker = _docker_bin()
    inspect = _run([docker, "image", "inspect", tag])
    if inspect.returncode == 0:
        return {"image": tag, "status": "present", "checked_at": utc_now()}
    pulled = _run([docker, "pull", tag])
    if pulled.returncode != 0:
        raise RuntimeError(
            f"image {tag} missing and pull failed (exit {pulled.returncode})"
        )
    return {"image": tag, "status": "installed", "checked_at": utc_now()}


def ensure_operating_images() -> dict[str, Any]:
    """Pull the RDP image. The Node image is pulled only after a verified NodeID."""
    reports = [ensure_image(tag) for tag in RDP_OPERATING_IMAGES]
    return {"images": reports, "checked_at": utc_now()}


def install_marker_path(info: dict[str, Any] | None = None) -> Path:
    raw = ""
    if info is not None:
        raw = str(info.get("driver_dir") or "")
    if not raw:
        raw = _env("DRIVER_DIR")
    if not raw:
        raise RuntimeError("DRIVER_DIR missing — run Install on this console")
    return Path(raw) / "install.state"


def install_is_complete() -> bool:
    try:
        path = install_marker_path()
    except RuntimeError:
        return False
    if not path.is_file():
        return False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(loaded, dict) and loaded.get("status") == "installed")


def install_user_environment() -> dict[str, Any]:
    """Check and install UserDesign prerequisites, then RDP and operations content.

    Runs to completion before the GUI offers User or NodeUser.
    Does not start the Proxy container and does not open a Frontend window.
    """
    pull = _pull.pull_realworld_information()
    _pull.bind_operation_environ(pull)
    secrets_built = _pull.build_all_useronly_secrets(pull)
    load_user_secrets(reload=True)

    driver = ensure_driver_directory(pull)
    tor_report = ensure_tor_installed(pull)
    docker_report = ensure_docker_installed(pull)
    python_report = ensure_python_installed(pull)
    node_report = ensure_node_installed(pull)
    tk_report = ensure_tk_installed(pull)

    pull = _pull.pull_realworld_information()
    _pull.bind_operation_environ(pull, overwrite=True)
    secrets_built = _pull.build_all_useronly_secrets(pull)
    load_user_secrets(reload=True)
    firewall = allowlist_tor_browser_firewall(
        tor_report.get("tor_browser_bin") or get_user_secret("USER_TOR_BROWSER_BIN")
    )
    secrets = ensure_user_secrets_present()
    hardware = {
        "HOSTNAME_CONSOLE": str(pull.get("hostname") or ""),
        "HOST_MACHINE_ID": str(pull.get("machine_id") or ""),
        "HARDWARE_PRIMARY_MAC": str(pull.get("primary_mac") or ""),
        "HARDWARE_PRIMARY_IP": str(pull.get("primary_ip") or ""),
        "HARDWARE_PRIMARY_IFACE": str(pull.get("primary_iface") or ""),
    }
    request_posts = {
        role: _user_secrets.write_request_posts(
            Path(str(driver["driver_dir"])), role=role, hardware=hardware
        )
        for role in ("user", "nodeuser")
    }
    images = ensure_operating_images()

    marker = install_marker_path(pull)
    marker.write_text(
        json.dumps({"status": "installed", "installed_at": utc_now()}, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "installed",
        "secrets": secrets,
        "secrets_built": {
            "user": secrets_built["user"].get("USER_SECRETS_FILE", ""),
            "registration": secrets_built["registration"].get(
                "REGISTRATION_SECRETS_FILE",
                registration_secrets_path().as_posix(),
            ),
            "id": id_secrets_path().as_posix(),
        },
        "driver": driver,
        "tor": tor_report,
        "firewall": firewall,
        "request_posts": request_posts,
        "docker": docker_report,
        "python": python_report,
        "javascript": node_report,
        "tk": tk_report,
        "images": images,
        "installed_at": utc_now(),
    }
