"""Load AdminGui launch/auth configuration from admingui.secrets / ID.secrets / admin_auth.secrets.

the ID.secrets stores the UserID, NodeID, MasterUserID, MasterServerID and AdminID once the user has been authenticated and verified.
this file also holds a TokenID as proof of authentication and verification.
this file must be verified against the MasterServer's LucidTops_UserDB, to ensure no modifications have been made to the file since the last verification.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


ADMIN_SECRETS_FILE_ENV = "ADMIN_SECRETS_FILE"
ADMIN_SECRETS_NAME_ENV = "ADMIN_SECRETS_NAME"
ADMIN_AUTH_SECRETS_FILE_ENV = "ADMIN_AUTH_SECRETS_FILE"
ADMIN_AUTH_SECRETS_NAME_ENV = "ADMIN_AUTH_SECRETS_NAME"
ID_SECRETS_FILE_ENV = "ID_SECRETS_FILE"
ID_SECRETS_NAME_ENV = "ID_SECRETS_NAME"
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


def admin_secrets_path() -> Path:
    return _resolve_named_secrets(ADMIN_SECRETS_FILE_ENV, ADMIN_SECRETS_NAME_ENV)


def admin_auth_secrets_path() -> Path:
    return _resolve_named_secrets(ADMIN_AUTH_SECRETS_FILE_ENV, ADMIN_AUTH_SECRETS_NAME_ENV)


def id_secrets_path() -> Path:
    return _resolve_named_secrets(ID_SECRETS_FILE_ENV, ID_SECRETS_NAME_ENV)


@lru_cache(maxsize=1)
def _load_admin_secrets_cached() -> dict[str, str]:
    merged: dict[str, str] = {}
    for resolver in (admin_secrets_path, admin_auth_secrets_path, id_secrets_path):
        try:
            path = resolver()
        except RuntimeError:
            continue
        if path.exists():
            merged.update(parse_secrets_file(path))
    if not merged:
        raise RuntimeError(
            "admin/admin_auth/ID secrets missing — create at time of operation"
        )
    for key, value in merged.items():
        if not _env(key):
            os.environ[key] = value
    return merged


def load_admin_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_admin_secrets_cached.cache_clear()
    return _load_admin_secrets_cached()


def get_admin_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    return load_admin_secrets().get(key.upper(), "").strip()


def require_admin_secret(key: str) -> str:
    value = get_admin_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/admin secrets — "
            "value must be created at time of operation"
        )
    return value


def admin_status() -> dict[str, Any]:
    role = get_admin_secret("USER_ROLE")
    if not role and get_admin_secret("ADMIN_ID"):
        role = "admin"
    colocated_raw = get_admin_secret("MASTER_SERVER_COLOCATED")
    return {
        "frontend_onion_configured": bool(get_admin_secret("FRONTEND_ONION")),
        "admin_home_path": get_admin_secret("FRONTEND_ADMIN_HOME_PATH"),
        "hardware_ip": get_admin_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_admin_secret("HARDWARE_PRIMARY_MAC"),
        "session_state_file": get_admin_secret("ADMINGUI_SESSION_STATE_FILE"),
        "admin_id": get_admin_secret("ADMIN_ID"),
        "token_id": get_admin_secret("TOKEN_ID"),
        "user_role": role,
        "tor_bin": get_admin_secret("ADMIN_TOR_BIN"),
        "tor_browser_bin": get_admin_secret("ADMIN_TOR_BROWSER_BIN"),
        "master_server_colocated": colocated_raw in {"1", "true", "True", "yes"},
        "download_auth_email_configured": bool(
            get_admin_secret("ADMIN_DOWNLOAD_AUTH_EMAIL")
        ),
        "userdb_validate_url_configured": bool(
            get_admin_secret("ADMIN_USERDB_VALIDATE_URL")
        ),
    }


def ensure_admin_secrets_from_pull(*, reload: bool = True) -> dict[str, str]:
    """Pull hardware + build secrets when missing; then load into process env."""
    path_ready = False
    try:
        path_ready = admin_secrets_path().exists()
    except RuntimeError:
        path_ready = False
    if not path_ready:
        from pull_information import (
            build_all_admingui_secrets,
            pull_realworld_information,
        )

        build_all_admingui_secrets(pull_realworld_information())
    else:
        try:
            id_path = id_secrets_path()
            auth_path = admin_auth_secrets_path()
        except RuntimeError:
            from pull_information import (
                build_all_admingui_secrets,
                pull_realworld_information,
            )

            build_all_admingui_secrets(pull_realworld_information())
        else:
            if not id_path.exists() or not auth_path.exists():
                from pull_information import (
                    build_all_admingui_secrets,
                    pull_realworld_information,
                )

                build_all_admingui_secrets(pull_realworld_information())
    return load_admin_secrets(reload=reload)
