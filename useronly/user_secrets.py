"""Load useronly launch/install configuration from registration.secrets / ID.secrets.
the ID.secrets stores the UserID, NodeID, MasterUserID, MasterServerID and AdminID once the user has been authenticated and verified.
this file also holds a TokenID as proof of authentication and verification.
this file must be verified against the MasterServer's LucidTops_UserDB, to ensure no modifications have been made to the file since the last verification.

"""

from __future__ import annotations

import hashlib
import json
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
    role = get_user_secret("USER_ROLE")
    if not role:
        if get_user_secret("NODE_ID"):
            role = "node"
        elif get_user_secret("USER_ID"):
            role = "user"
    return {
        "frontend_onion_configured": bool(get_user_secret("FRONTEND_ONION")),
        "home_page_path": get_user_secret("FRONTEND_HOME_PAGE_PATH"),
        "register_path": get_user_secret("FRONTEND_REGISTER_PATH"),
        "hardware_ip": get_user_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_user_secret("HARDWARE_PRIMARY_MAC"),
        "session_state_file": get_user_secret("USERONLY_SESSION_STATE_FILE"),
        "user_id": get_user_secret("USER_ID"),
        "node_id": get_user_secret("NODE_ID"),
        "token_id": get_user_secret("TOKEN_ID"),
        "user_role": role,
        "tor_bin": get_user_secret("USER_TOR_BIN"),
        "tor_browser_bin": get_user_secret("USER_TOR_BROWSER_BIN"),
    }


_IDENTITY_KEYS = ("USER_ID", "NODE_ID", "TOKEN_ID", "USER_ROLE", "NODEUSER")


def identity_digest(values: dict[str, str]) -> str:
    material = "|".join(f"{key}={values.get(key, '')}" for key in _IDENTITY_KEYS)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _write_id_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# LucidTops ID.secrets — identity values come from the MasterServer"]
    for key in sorted(values):
        if values[key] == "":
            continue
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _load_user_secrets_cached.cache_clear()


def node_branch_allowed() -> bool:
    """True when ID.secrets holds a MasterServer identity that has not been edited locally."""
    try:
        path = id_secrets_path()
    except RuntimeError:
        return False
    if not path.is_file():
        return False
    current = parse_secrets_file(path)
    if not current.get("USER_ID") or not current.get("TOKEN_ID"):
        return False
    if not current.get("ID_SECRETS_STAMP"):
        return False
    return current.get("ID_SECRETS_DIGEST", "") == identity_digest(current)


def verify_id_secrets() -> None:
    """Refuse the session when ID.secrets does not match LucidTops_UserDB."""
    try:
        path = id_secrets_path()
    except RuntimeError:
        return
    if not path.exists():
        return
    current = parse_secrets_file(path)
    has_identity = any(current.get(key) for key in ("USER_ID", "NODE_ID", "TOKEN_ID"))
    if not has_identity:
        return
    digest = identity_digest(current)
    stamp = current.get("ID_SECRETS_STAMP", "")
    recorded = current.get("ID_SECRETS_DIGEST", "")
    if not stamp or recorded != digest:
        raise RuntimeError(
            "ID.secrets no longer matches the last MasterServer verification stamp"
        )
    from frontend_access import routes_for, verify_userdb

    nodeuser = current.get("NODEUSER", "").lower() == "true" or bool(current.get("NODE_ID"))
    verify_userdb(routes_for(nodeuser), current)


def apply_master_identity(response: dict[str, Any], *, nodeuser: bool) -> dict[str, str]:
    """Store UserID, TokenID, and NodeID only when the MasterServer returned them."""
    path = id_secrets_path()
    current = parse_secrets_file(path) if path.exists() else {}
    returned = {
        "USER_ID": str(response.get("UserID") or response.get("userId") or "").strip(),
        "TOKEN_ID": str(
            response.get("TokenID") or response.get("IDToken") or response.get("tokenId") or ""
        ).strip(),
        "NODE_ID": str(response.get("NodeID") or response.get("nodeId") or "").strip(),
        "MASTER_USER_ID": str(
            response.get("MasterUserID") or response.get("MASTER_USER_ID") or ""
        ).strip(),
        "MASTER_SERVER_ID": str(
            response.get("MasterServerID") or response.get("MASTER_SERVER_ID") or ""
        ).strip(),
        "ADMIN_ID": str(response.get("AdminID") or response.get("ADMIN_ID") or "").strip(),
    }
    stamp = str(
        response.get("verification_stamp") or response.get("ID_SECRETS_STAMP") or ""
    ).strip()
    if not any(returned.values()) and not stamp:
        raise RuntimeError(
            "MasterServer response did not include UserID, TokenID, NodeID, or a verification stamp"
        )
    for key, value in returned.items():
        if value:
            current[key] = value
    current["NODEUSER"] = "true" if nodeuser else "false"
    if current.get("NODE_ID") and nodeuser:
        current["USER_ROLE"] = "node"
    elif current.get("USER_ID"):
        current["USER_ROLE"] = "user"
    digest = identity_digest(current)
    current["ID_SECRETS_DIGEST"] = digest
    current["ID_SECRETS_STAMP"] = stamp or digest
    _write_id_file(path, current)
    return current


def write_request_posts(driver_dir: Path, *, role: str, hardware: dict[str, str]) -> dict[str, str]:
    """Build registration and login post files. UserID and TokenID stay empty until the MasterServer replies."""
    account = "node" if role.strip().lower() in {"node", "nodeuser"} else "user"
    base = {
        "Email": "",
        "Password": "",
        "USER_ID": "",
        "TOKEN_ID": "",
        "account_type": account,
        "HOSTNAME_CONSOLE": hardware.get("HOSTNAME_CONSOLE", hardware.get("hostname", "")),
        "HOST_MACHINE_ID": hardware.get("HOST_MACHINE_ID", hardware.get("machine_id", "")),
        "HARDWARE_PRIMARY_MAC": hardware.get("HARDWARE_PRIMARY_MAC", hardware.get("primary_mac", "")),
        "HARDWARE_PRIMARY_IP": hardware.get("HARDWARE_PRIMARY_IP", hardware.get("primary_ip", "")),
        "HARDWARE_PRIMARY_IFACE": hardware.get(
            "HARDWARE_PRIMARY_IFACE", hardware.get("primary_iface", "")
        ),
    }
    driver_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for action in ("registration", "login"):
        body = {**base, "action": "register" if action == "registration" else "login"}
        path = driver_dir / f"{action}_{account}.post.json"
        path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[action] = path.as_posix()
    return written


def ensure_user_secrets_from_pull(*, reload: bool = True) -> dict[str, str]:
    """Pull hardware + build secrets when missing; then load into process env."""
    path_ready = False
    try:
        path_ready = (
            user_secrets_path().exists()
            or registration_secrets_path().exists()
        )
    except RuntimeError:
        path_ready = False
    if not path_ready:
        from pull_information import build_all_useronly_secrets, pull_realworld_information

        build_all_useronly_secrets(pull_realworld_information())
    else:
        # Refresh bind paths / hardware when env not yet configured for this process.
        try:
            id_path = id_secrets_path()
            reg_path = registration_secrets_path()
        except RuntimeError:
            from pull_information import build_all_useronly_secrets, pull_realworld_information

            build_all_useronly_secrets(pull_realworld_information())
        else:
            if not id_path.exists() or not reg_path.exists():
                from pull_information import (
                    build_all_useronly_secrets,
                    pull_realworld_information,
                )

                build_all_useronly_secrets(pull_realworld_information())
    return load_user_secrets(reload=reload)
