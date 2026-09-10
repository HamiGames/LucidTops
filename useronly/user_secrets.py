"""Load useronly launch/install configuration from registration.secrets / ID.secrets.


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


REGISTRATION_SECRETS_FILE_ENV = "REGISTRATION_SECRETS_FILE"
REGISTRATION_SECRETS_NAME_ENV = "REGISTRATION_SECRETS_NAME"
ID_SECRETS_FILE_ENV = "ID_SECRETS_FILE"
ID_SECRETS_NAME_ENV = "ID_SECRETS_NAME"
USER_SECRETS_FILE_ENV = "USER_SECRETS_FILE"
USER_SECRETS_NAME_ENV = "USER_SECRETS_NAME"
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


def _resolve_named_secrets(file_env: str, name_env: str) -> Path:
    override = _env(file_env)
    if override:
        return Path(override).expanduser()
    name = _env(name_env)
    if not name:
        raise RuntimeError(
            f"{file_env} or {name_env} missing — must be set at time of operation"
        )
    return secrets_dir() / name


def user_secrets_path() -> Path:
    try:
        return _resolve_named_secrets(USER_SECRETS_FILE_ENV, USER_SECRETS_NAME_ENV)
    except RuntimeError:
        return _resolve_named_secrets(REGISTRATION_SECRETS_FILE_ENV, REGISTRATION_SECRETS_NAME_ENV)


def registration_secrets_path() -> Path:
    return _resolve_named_secrets(REGISTRATION_SECRETS_FILE_ENV, REGISTRATION_SECRETS_NAME_ENV)


def id_secrets_path() -> Path:
    return _resolve_named_secrets(ID_SECRETS_FILE_ENV, ID_SECRETS_NAME_ENV)


@lru_cache(maxsize=1)
def _load_user_secrets_cached() -> dict[str, str]:
    merged: dict[str, str] = {}
    for resolver in (user_secrets_path, registration_secrets_path, id_secrets_path):
        try:
            path = resolver()
        except RuntimeError:
            continue
        if path.exists():
            merged.update(parse_secrets_file(path))
    if not merged:
        raise RuntimeError(
            "user/registration/ID secrets missing — create at time of operation"
        )
    for key, value in merged.items():
        if not _env(key):
            os.environ[key] = value
    return merged


def load_user_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_user_secrets_cached.cache_clear()
    return _load_user_secrets_cached()


def get_user_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    return load_user_secrets().get(key.upper(), "").strip()


def require_user_secret(key: str) -> str:
    value = get_user_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/user secrets — "
            "value must be created at time of operation"
        )
    return value


def user_status() -> dict[str, Any]:
    return {
        "frontend_onion_configured": bool(get_user_secret("FRONTEND_ONION")),
        "home_page_path": get_user_secret("FRONTEND_HOME_PAGE_PATH"),
        "register_path": get_user_secret("FRONTEND_REGISTER_PATH"),
    }
