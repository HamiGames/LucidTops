"""Load frontend tunnel configuration from backend.secrets (env at time of operation).


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


BACKEND_SECRETS_FILE_ENV = "BACKEND_SECRETS_FILE"
BACKEND_SECRETS_NAME_ENV = "BACKEND_SECRETS_NAME"
FRONTEND_SECRETS_FILE_ENV = "FRONTEND_SECRETS_FILE"
FRONTEND_SECRETS_NAME_ENV = "FRONTEND_SECRETS_NAME"
SECRETS_DIR_ENV = "SECRETS_DIR"
LUCID_TOPS_ROOT_ENV = "LUCID_TOPS_ROOT"


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


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


def frontend_secrets_path() -> Path:
    for env_key in (FRONTEND_SECRETS_FILE_ENV, BACKEND_SECRETS_FILE_ENV):
        override = _env(env_key)
        if override:
            return Path(override).expanduser()
    name = _env(FRONTEND_SECRETS_NAME_ENV) or _env(BACKEND_SECRETS_NAME_ENV)
    if not name:
        raise RuntimeError(
            f"{FRONTEND_SECRETS_FILE_ENV}/{BACKEND_SECRETS_FILE_ENV} or "
            f"{FRONTEND_SECRETS_NAME_ENV}/{BACKEND_SECRETS_NAME_ENV} missing — "
            "must be set at time of operation"
        )
    return secrets_dir() / name


@lru_cache(maxsize=1)
def _load_frontend_secrets_cached() -> dict[str, str]:
    path = frontend_secrets_path()
    if not path.exists():
        raise RuntimeError(
            f"frontend/backend secrets file missing at {path.as_posix()} — create at time of operation"
        )
    values = parse_secrets_file(path)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return values


def load_frontend_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_frontend_secrets_cached.cache_clear()
    return _load_frontend_secrets_cached()


def get_frontend_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    return load_frontend_secrets().get(key.upper(), "").strip()


def require_frontend_secret(key: str) -> str:
    value = get_frontend_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/frontend secrets — "
            "value must be created at time of operation"
        )
    return value


def frontend_status() -> dict[str, Any]:
    path = frontend_secrets_path()
    return {
        "secrets_file": path.as_posix(),
        "secrets_exists": path.exists(),
        "master_onion_configured": bool(
            get_frontend_secret("MASTER_SERVER_ONION")
            or get_frontend_secret("FRONTEND_ONION")
        ),
        "hardware_ip": get_frontend_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_frontend_secret("HARDWARE_PRIMARY_MAC"),
        "proxy_backend_path": get_frontend_secret("FRONTEND_PROXY_BACKEND_PATH"),
    }


def ensure_frontend_secrets_from_pull(*, reload: bool = True) -> dict[str, str]:
    """Pull hardware + build secrets when missing; then load into process env."""
    path_ready = False
    try:
        path_ready = frontend_secrets_path().exists()
    except RuntimeError:
        path_ready = False
    if not path_ready:
        from pull_information import build_frontend_secrets, pull_realworld_information

        build_frontend_secrets(pull_realworld_information())
    return load_frontend_secrets(reload=reload)
