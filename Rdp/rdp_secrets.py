"""Load Rdp connection configuration from /app/Secrets/rdp.secrets.

The connection file is copied into the image at build. DockerDns reads that file
only. User-console material is stored in the LucidTops program folder.


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


DRIVER_DIR_ENV = "DRIVER_DIR"
CONNECTION_SECRETS_FILE = Path("/app/Secrets/rdp.secrets")
CONSOLE_STATE_NAME = "rdp.console"
_PI_ROOT = "/mnt/myssd"

_CONNECTION_KEYS = {
    "RDP_HTTP_TIMEOUT",
    "RDP_ONION",
    "RDP_SELF_DNS",
    "RDP_USER_DNS",
    "RDP_DOCKER_NETWORK_NAME",
    "TOR_SOCKS_HOST",
    "TOR_SOCKS_PORT",
    "PROXY_USER_DNS",
    "PROXY_SESSIONS_DNS",
    "PROXY_OPERATIONS_DNS",
    "PROXY_BACKEND_DNS",
    "PROXY_RDP_DNS",
}
_CONNECTION_PREFIXES = (
    "RDP_SESSIONS_",
    "RDP_BACKEND_",
    "RDP_SESSION_",
    "RDP_OPERATIONS_",
    "PROXY_",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _under_pi(path: Path) -> bool:
    posix = path.expanduser().as_posix().rstrip("/")
    return posix == _PI_ROOT or posix.startswith(_PI_ROOT + "/")


def is_connection_key(key: str) -> bool:
    upper = key.upper()
    if upper in _CONNECTION_KEYS:
        return True
    return any(upper.startswith(prefix) for prefix in _CONNECTION_PREFIXES)


def program_folder() -> Path:
    """LucidTops program folder on the console that started this container."""
    raw = _env(DRIVER_DIR_ENV)
    if raw:
        chosen = Path(raw).expanduser()
        if not _under_pi(chosen):
            chosen.mkdir(parents=True, exist_ok=True)
            return chosen.resolve()
    folder = Path.home() / "LucidTops"
    if _under_pi(folder):
        raise RuntimeError(
            "LucidTops program folder resolved under /mnt/myssd — "
            "set DRIVER_DIR to the user console program folder"
        )
    folder.mkdir(parents=True, exist_ok=True)
    return folder.resolve()


def console_state_path() -> Path:
    return program_folder() / CONSOLE_STATE_NAME


def secrets_dir() -> Path:
    """User-console program folder. Not the Pi secrets directory."""
    return program_folder()


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def write_secrets_file(path: Path, values: dict[str, str]) -> Path:
    """Write key=value secrets created at time of operation (no placeholders)."""
    if path.expanduser().as_posix().rstrip("/") == CONNECTION_SECRETS_FILE.as_posix():
        raise RuntimeError(
            "/app/Secrets/rdp.secrets is the image connection file and is not rewritten"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# LucidTops user-console state generated at {utc_now()}",
        "# key=value — hardware and local paths from the user console",
    ]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def rdp_secrets_path() -> Path:
    """In-container connection file. Not SECRETS_DIR and not a Pi path."""
    return CONNECTION_SECRETS_FILE


@lru_cache(maxsize=1)
def _load_rdp_secrets_cached() -> dict[str, str]:
    path = rdp_secrets_path()
    if not path.is_file():
        raise RuntimeError(
            f"rdp secrets file missing at {path.as_posix()} — "
            "image build must read /mnt/myssd/LucidTops/Server/Secrets/Master.secrets "
            "and proxy.secrets"
        )
    return parse_secrets_file(path)


def load_rdp_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_rdp_secrets_cached.cache_clear()
    return _load_rdp_secrets_cached()


@lru_cache(maxsize=1)
def _load_console_state_cached() -> dict[str, str]:
    path = console_state_path()
    if not path.is_file():
        return {}
    values = parse_secrets_file(path)
    return {key: value for key, value in values.items() if not is_connection_key(key)}


def load_console_state(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_console_state_cached.cache_clear()
    return _load_console_state_cached()


def update_console_state(values: dict[str, str]) -> Path:
    """Merge user-console keys into the program-folder state file."""
    path = console_state_path()
    current = parse_secrets_file(path) if path.is_file() else {}
    for key, value in values.items():
        upper = key.upper()
        if not upper or not value or is_connection_key(upper):
            continue
        current[upper] = value
    write_secrets_file(path, current)
    _load_console_state_cached.cache_clear()
    return path


def get_rdp_secret(key: str) -> str:
    upper = key.upper()
    if is_connection_key(upper):
        try:
            return load_rdp_secrets().get(upper, "").strip()
        except RuntimeError:
            return ""
    return load_console_state().get(upper, "").strip()


def require_rdp_secret(key: str) -> str:
    value = get_rdp_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/rdp.secrets — "
            "value must be created at time of operation"
        )
    return value


def require_rdp_secret_int(key: str) -> int:
    raw = require_rdp_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be an integer — got {raw!r}") from exc


def rdp_status() -> dict[str, Any]:
    path = rdp_secrets_path()
    return {
        "rdp_secrets_file": path.as_posix(),
        "rdp_secrets_exists": path.exists(),
        "rdp_port_configured": bool(get_rdp_secret("RDP_PORT")),
        "settings_js": get_rdp_secret("RDP_SETTINGS_JS_PATH"),
        "hardware_ip": get_rdp_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_rdp_secret("HARDWARE_PRIMARY_MAC"),
    }
