"""Load Rdp runtime configuration from rdp.secrets (env at time of operation).


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


RDP_SECRETS_FILE_ENV = "RDP_SECRETS_FILE"
RDP_SECRETS_NAME_ENV = "RDP_SECRETS_NAME"
SECRETS_DIR_ENV = "SECRETS_DIR"
LUCID_TOPS_ROOT_ENV = "LUCID_TOPS_ROOT"


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def secrets_dir() -> Path:
    configured = _env(SECRETS_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    root = _env(LUCID_TOPS_ROOT_ENV)
    if not root:
        raise RuntimeError(
            f"{SECRETS_DIR_ENV} or {LUCID_TOPS_ROOT_ENV} missing — must be set at time of operation"
        )
    name = _env("SECRETS_DIR_NAME")
    if not name:
        raise RuntimeError(
            "SECRETS_DIR_NAME missing — must be set at time of operation when SECRETS_DIR is unset"
        )
    return Path(root).expanduser() / name


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
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# LucidTops rdp.secrets generated at {utc_now()}",
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
        if overwrite or not _env(key):
            os.environ[key] = value
    return loaded


def rdp_secrets_path() -> Path:
    override = _env(RDP_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    name = _env(RDP_SECRETS_NAME_ENV)
    if name:
        return secrets_dir() / name
    # Prefer existing rdp*.secrets on hardware secrets dir when name env unset
    try:
        sdir = secrets_dir()
    except RuntimeError:
        raise RuntimeError(
            f"{RDP_SECRETS_FILE_ENV} or {RDP_SECRETS_NAME_ENV} missing — "
            "must be set at time of operation"
        ) from None
    for existing in sorted(sdir.glob("*.secrets")):
        if existing.name.lower().startswith("rdp"):
            return existing
    return sdir / "rdp.secrets"


@lru_cache(maxsize=1)
def _load_rdp_secrets_cached() -> dict[str, str]:
    path = rdp_secrets_path()
    if not path.exists():
        raise RuntimeError(
            f"rdp secrets file missing at {path.as_posix()} — create at time of operation"
        )
    values = parse_secrets_file(path)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return values


def load_rdp_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_rdp_secrets_cached.cache_clear()
    return _load_rdp_secrets_cached()


def get_rdp_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    try:
        return load_rdp_secrets().get(key.upper(), "").strip()
    except RuntimeError:
        return ""


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
