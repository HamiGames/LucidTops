""" this is the script that builds the configuration files for the Backend container (MasterServer)
[Path]: mnt/myssd/LucidTops/secrets
[File]: backend.secrets
[Content]: backend container configurational requirements, for the backend container to operate correctly.
Requirements:
- the backend secrets file will be written to the host machine (hardward using a configurable Path)
- the backend secrets file will be written to the backend secrets file (backend.secrets) on the host machine (hardward using a configurable Path)
- NO Hardcoded values, all values are created at time of operation.
- No place holder values, all values are created at time of operation.

inclusions:
- writes the API public Route information to the backend secrets file (backend.secrets) on the host machine (hardward using a configurable Path)
- writes the API private Route information to the backend secrets file (backend.secrets) on the host machine (hardward using a configurable Path)
- writes the MongoDB connection information to the backend secrets file (backend.secrets) on the host machine (hardward using a configurable Path)
- write all required connection path information used by the backend container to operate correctly.
- tests all created information for correctness and validity.
- all code will be configurable from outside the container (via the DockerfileDNS) and stored on the Host Machine (hardward using a configurable Path)

"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config import (
    SECRETS_DIR,
    get_api_public_base_url,
    get_config_value,
    get_config_value_optional,
    get_gui_public_base_url,
    get_master_server_public_url,
    parse_secrets_file,
    require_env,
    resolve_master_server_onion,
    utc_now,
)
from MasterServerRoutes import (
    ADMIN_ROUTES,
    BLOCKCHAIN_ROUTES,
    DATABASE_ROUTES,
    GUI_ROUTES,
    MASTER_API_ROUTES,
    MASTER_CLASS_ROUTES,
    NODE_ROUTES,
    SESSION_ROUTES,
    USER_ROUTES,
)

DEFAULT_BACKEND_SECRETS_NAME = "backend.secrets"
BACKEND_SECRETS_FILE_ENV = "BACKEND_SECRETS_FILE"
BACKEND_SECRETS_NAME_ENV = "BACKEND_SECRETS_NAME"

BACKEND_SECRETS_KEYS: tuple[str, ...] = (
    "LUCID_TOPS_ROOT",
    "SECRETS_DIR",
    "BACKEND_SECRETS_FILE",
    "API_BASE_PATH",
    "GUI_PREFIX",
    "API_PUBLIC_ROUTES",
    "API_PRIVATE_ROUTES",
    "GUI_ROUTES",
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_MAIN_DATABASE_NAME",
    "MONGODB_URL",
    "LUCID_MONGODB_URL",
    "MASTER_SERVER_BIND_HOST",
    "MASTER_SERVER_HOST",
    "MASTER_SERVER_PORT",
    "MASTER_SERVER_ID",
    "MASTER_SERVER_ONION",
    "FRONTEND_ONION",
    "NODEUSER_ONION",
    "TOR_API_SERVICE",
    "TOR_GUI_SERVICE",
    "MASTER_SERVER_TOR_SERVICE",
    "CLIENT_REQUEST_TOR_SERVICE",
    "FRONTEND_SOURCE_PREFIX",
    "CONNECTION_PROTOCOL_NAME",
    "CONNECTION_PROTOCOL",
    "CONNECTION_TORRENT_LAYER",
    "CONNECTION_NETWORK",
    "HIDDEN_SERVICE_PORT",
    "TOR_SOCKS_HOST",
    "TOR_SOCKS_PORT",
    "MONGODB_VIA_SOCKS5",
    "PROXY_GATE_HEADER_VALUE",
)


def backend_secrets_path(secrets_dir: Path | None = None) -> Path:
    override = os.environ.get(BACKEND_SECRETS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    name = os.environ.get(BACKEND_SECRETS_NAME_ENV, "").strip()
    if not name:
        name = get_config_value_optional(BACKEND_SECRETS_NAME_ENV) or DEFAULT_BACKEND_SECRETS_NAME
    base = secrets_dir or SECRETS_DIR
    return base / name


def _join_routes(routes: tuple[str, ...] | list[str]) -> str:
    cleaned = [route.strip() for route in routes if route and route.strip()]
    if not cleaned:
        raise RuntimeError("route list must not be empty at time of operation")
    return ",".join(cleaned)


def _public_api_routes() -> str:
    return _join_routes(
        list(MASTER_API_ROUTES)
        + list(USER_ROUTES)
        + list(NODE_ROUTES)
        + list(SESSION_ROUTES)
        + list(GUI_ROUTES)
    )


def _private_api_routes() -> str:
    return _join_routes(
        list(ADMIN_ROUTES)
        + list(MASTER_CLASS_ROUTES)
        + list(DATABASE_ROUTES)
        + list(BLOCKCHAIN_ROUTES)
    )


def build_backend_secrets_values() -> dict[str, str]:
    """Assemble backend.secrets values from env/config at operation time."""
    mongodb_host = get_config_value("MONGODB_HOST")
    mongodb_port = get_config_value("MONGODB_PORT")
    mongodb_db = get_config_value("MONGODB_MAIN_DATABASE_NAME")
    mongodb_url = get_config_value_optional("MONGODB_URL") or (
        f"mongodb://{mongodb_host}:{mongodb_port}/{mongodb_db}"
    )
    lucid_mongodb_url = get_config_value_optional("LUCID_MONGODB_URL") or (
        f"mongodb://{mongodb_host}:{mongodb_port}"
    )
    master_onion = (
        get_config_value_optional("MASTER_SERVER_ONION") or resolve_master_server_onion() or ""
    )
    values: dict[str, str] = {
        "LUCID_TOPS_ROOT": require_env("LUCID_TOPS_ROOT"),
        "SECRETS_DIR": require_env("SECRETS_DIR"),
        "BACKEND_SECRETS_FILE": backend_secrets_path().as_posix(),
        "API_BASE_PATH": get_config_value("API_BASE_PATH"),
        "GUI_PREFIX": get_config_value("GUI_PREFIX"),
        "API_PUBLIC_ROUTES": _public_api_routes(),
        "API_PRIVATE_ROUTES": _private_api_routes(),
        "GUI_ROUTES": _join_routes(list(GUI_ROUTES)),
        "MONGODB_HOST": mongodb_host,
        "MONGODB_PORT": mongodb_port,
        "MONGODB_MAIN_DATABASE_NAME": mongodb_db,
        "MONGODB_URL": mongodb_url,
        "LUCID_MONGODB_URL": lucid_mongodb_url,
        "MASTER_SERVER_BIND_HOST": get_config_value("MASTER_SERVER_BIND_HOST"),
        "MASTER_SERVER_HOST": get_config_value("MASTER_SERVER_HOST"),
        "MASTER_SERVER_PORT": get_config_value("MASTER_SERVER_PORT"),
        "MASTER_SERVER_ID": get_config_value_optional("MASTER_SERVER_ID"),
        "MASTER_SERVER_ONION": master_onion,
        "FRONTEND_ONION": get_config_value_optional("FRONTEND_ONION"),
        "NODEUSER_ONION": get_config_value_optional("NODEUSER_ONION"),
        "TOR_API_SERVICE": get_api_public_base_url(),
        "TOR_GUI_SERVICE": get_gui_public_base_url(),
        "MASTER_SERVER_TOR_SERVICE": get_master_server_public_url(),
        "CLIENT_REQUEST_TOR_SERVICE": get_config_value_optional("CLIENT_REQUEST_TOR_SERVICE"),
        "FRONTEND_SOURCE_PREFIX": get_config_value("FRONTEND_SOURCE_PREFIX"),
        "CONNECTION_PROTOCOL_NAME": get_config_value("CONNECTION_PROTOCOL_NAME"),
        "CONNECTION_PROTOCOL": get_config_value("CONNECTION_PROTOCOL"),
        "CONNECTION_TORRENT_LAYER": get_config_value("CONNECTION_TORRENT_LAYER"),
        "CONNECTION_NETWORK": get_config_value("CONNECTION_NETWORK"),
        "HIDDEN_SERVICE_PORT": get_config_value("HIDDEN_SERVICE_PORT"),
        "TOR_SOCKS_HOST": get_config_value_optional("TOR_SOCKS_HOST"),
        "TOR_SOCKS_PORT": get_config_value_optional("TOR_SOCKS_PORT"),
        "MONGODB_VIA_SOCKS5": get_config_value_optional("MONGODB_VIA_SOCKS5") or "true",
        "PROXY_GATE_HEADER_VALUE": get_config_value_optional("PROXY_GATE_HEADER_VALUE"),
    }
    return values


def validate_backend_secrets_values(values: dict[str, str]) -> None:
    required = (
        "API_BASE_PATH",
        "GUI_PREFIX",
        "API_PUBLIC_ROUTES",
        "API_PRIVATE_ROUTES",
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_MAIN_DATABASE_NAME",
        "MONGODB_URL",
        "MASTER_SERVER_BIND_HOST",
        "MASTER_SERVER_PORT",
        "FRONTEND_SOURCE_PREFIX",
        "HIDDEN_SERVICE_PORT",
    )
    missing = [key for key in required if not str(values.get(key, "")).strip()]
    if missing:
        raise RuntimeError(
            f"backend.secrets validation failed; missing keys: {', '.join(missing)}"
        )
    try:
        int(values["MONGODB_PORT"])
        int(values["MASTER_SERVER_PORT"])
        int(values["HIDDEN_SERVICE_PORT"])
    except ValueError as exc:
        raise RuntimeError("backend.secrets ports must be integers") from exc


def write_backend_secrets(
    secrets_dir: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Write backend.secrets on the host secrets path (operation time)."""
    target_dir = secrets_dir or SECRETS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = backend_secrets_path(target_dir)
    if path.exists() and not force:
        existing = parse_secrets_file(path)
        validate_backend_secrets_values(existing)
        return path

    values = build_backend_secrets_values()
    values["BACKEND_SECRETS_FILE"] = path.as_posix()
    validate_backend_secrets_values(values)

    lines = [
        "# LucidTops backend.secrets - written by backend/BuildConfigs.py",
        f"# Generated: {utc_now()}",
        "# Host-mounted secrets for MasterServer / frontend tunnel consumers.",
        "",
    ]
    for key in BACKEND_SECRETS_KEYS:
        value = str(values.get(key, "")).strip()
        if value:
            lines.append(f"{key}={value}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def backend_secrets_status(*, secrets_dir: Path | None = None) -> dict[str, Any]:
    path = backend_secrets_path(secrets_dir)
    loaded = parse_secrets_file(path) if path.exists() else {}
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "keys_loaded": len(loaded),
        "mongodb_url_configured": bool(loaded.get("MONGODB_URL", "").strip()),
        "api_public_routes_configured": bool(loaded.get("API_PUBLIC_ROUTES", "").strip()),
    }


if __name__ == "__main__":
    written = write_backend_secrets(force=True)
    print(written.as_posix())
