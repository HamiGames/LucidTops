#!/usr/bin/env python3
"""The builder script for the master server.

Steps:
1. create a new master server database
2. create a new master server database schema
3. create a new master server database connection
4. create a new master server database connection schema
5. create a new master server database connection connection
6. create a new master server database connection connection schema
7. create a new master server database connection connection connection
8. create a new master server database connection connection connection schema
9. create a new master server database connection connection connection connection
10. create a new master server database connection connection connection connection schema
11. set API routes for the master server (using FastAPI)
12. set GUI routes for the master server (using FastAPI)
13. set ledger system for the master server (using FastAPI)
14. set blockchain system for the master server (using FastAPI)
15. set session system for the master server (using FastAPI)
16. set user system for the master server (using FastAPI)
17. set node system for the master server (using FastAPI)
18. set admin system for the master server (using FastAPI)
19. set master class system for the master server (using FastAPI)
20. set master class user system for the master server (using FastAPI)

mongodb database design: (MasterDBSchema.py)
tor *.onion address: to be generated during the launch script (LaunchServer.py)
api connection protocol: (connection.py)

required factors:
- a server.env file must generated from this script using the console that is running the script
  (saved in the project root directory)
root directory: mnt/myssd/LucidTops
secrets directory: mnt/myssd/LucidTops/secrets

must generate a new torrc to be used by other containers that require the tor daemon to be running
torrc file: mnt/myssd/LucidTops/torrc

must generate a new server.env file to be used by other containers that require the server to be running
server.env file: mnt/myssd/LucidTops/server.env

must generate a new secrets.env file to be used by other containers that require the secrets to be running
secrets.env file: mnt/myssd/LucidTops/secrets.env

operationals: (Backend = MasterServer[includes the following containers])
- runs as a Uvicorn server
- runs as a FastAPI server
- runs as a MongoDB server
- runs as a Tor server
- runs as a Clearnet server
- runs as a Node container Host (Node container)
- runs as a Blockchain container Host (Blockchain container)
- runs as a Sessions container Host (Sessions container)
- runs as a Operations container Host (Operations container)
- runs as a PaySystems container Host (PaySystems container)
- runs as a Frontend container Host (Frontend container)
critical information:
ubuntu server version: 24.04 LTS
hardware: 4 core CPU, 8GB RAM, 100GB SSD raspberry pi 5
network: 100Mbps internet connection
security: ufw firewall, tor hidden service, clearnet connection

"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from config import (
    API_PREFIX,
    DEFAULT_CONFIG_SECRETS_NAME,
    GUI_PREFIX,
    LUCID_TOPS_ROOT,
    MASTER_DB_NAME,
    MASTER_SERVER_PORT,
    MONGODB_HOST,
    MONGODB_PORT,
    SECRETS_DIR,
    SECRETS_ENV_PATH,
    SERVER_ENV_PATH,
    TORRC_PATH,
    get_mongo_client,
    utc_now,
)
from mongodb_secrets import (
    DEFAULT_MONGODB_SECRETS_NAME,
    verify_mongodb_creation,
    write_mongodb_secrets_verified,
)
from container_secrets import (
    CONTAINER_SECRETS_SPECS,
    DEFAULT_SERVER_SECRETS_NAME,
    container_secrets_env_lines,
    container_secrets_status,
)
from MasterDBSchema import (
    ADMIN_USER_SCHEMA_FIELDS,
    COLLECTION_SCHEMAS,
    MASTER_CLASS_USER_SCHEMA_FIELDS,
    MASTER_CREDENTIALS_FIELDS,
    NODE_USERS_COLLECTION,
    NODE_USER_SCHEMA_FIELDS,
    schema_template,
    USER_SCHEMA_FIELDS,
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
from NodeDbSchema import NODE_DB_SCHEMA_FIELDS

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:  # pragma: no cover
    MongoClient = None  # type: ignore[misc, assignment]
    PyMongoError = Exception  # type: ignore[misc, assignment]

BACKEND_DIR = Path(__file__).resolve().parent
BUILD_MANIFEST_PATH = BACKEND_DIR / "master_server_build_manifest.json"

ROOT_DIR = LUCID_TOPS_ROOT
API_GATEWAY_PORT = int(os.environ.get("API_GATEWAY_PORT", "8080"))
GUI_BRIDGE_PORT = int(os.environ.get("GUI_API_BRIDGE_PORT", "8105"))


SECRET_KEYS: tuple[str, ...] = (
    "API_KEY",
    "API_SECRET",
    "MONGODB_PASSWORD",
    "MONGODB_ADMIN_PASSWORD",
    "JWT_SECRET_KEY",
    "SESSION_SECRET",
    "ENCRYPTION_KEY",
    "TOR_CONTROL_PASSWORD",
    "TOR_SOCKS_PASSWORD",
    "TOR_PASSWORD",
    "BLOCKCHAIN_SECRET",
    "BLOCKCHAIN_SECRET_KEY",
    "ADMIN_SECRET",
    "MASTER_CLASS_SECRET",
    "LUCID_TOKENS_HOLDING_ACCOUNT",
)

DEFAULT_ALLOWED_ONGOING_SOURCES = (
    "register.js,node-registration.js,login.js,tier-select.js,connect-handshake.js,"
    "find-peer.js,find-Peer.js,home_page.js,dashboard.js,settings.js,"
    "LucidLedger.js,LucidMarket.js,RemoteView.js"
)

DEFAULT_INITIAL_HANDSHAKE_SOURCES = (
    "register.js,login.js,node-registration.js,tier-select.js"
)

DEFAULT_DOCKER_SERVICES: tuple[str, ...] = (
    "lucid-mongodb",
    "lucid-server-default",
    "lucid-blockchain",
    "lucid-sessions",
    "lucid-operations",
    "lucid-paysystems",
    "lucid-frontend",
)

# Target host / security profile written to server.secrets at operation time
# (values match the critical-information block in this module's docstring).
SERVER_CRITICAL_PROFILE: dict[str, str] = {
    "UBUNTU_SERVER_VERSION": "24.04 LTS",
    "HARDWARE_CPU_CORES": "4",
    "HARDWARE_RAM_GB": "8",
    "HARDWARE_STORAGE": "100GB SSD",
    "HARDWARE_PLATFORM": "raspberry_pi_5",
    "NETWORK_BANDWIDTH": "100Mbps",
    "SECURITY_FIREWALL": "ufw",
    "SECURITY_TOR_HIDDEN_SERVICE": "true",
    "SECURITY_CLEARNET_CONNECTION": "true",
}

SERVER_OPERATIONAL_FLAGS: dict[str, str] = {
    "OPERATIONAL_UVICORN": "true",
    "OPERATIONAL_FASTAPI": "true",
    "OPERATIONAL_MONGODB": "true",
    "OPERATIONAL_TOR": "true",
    "OPERATIONAL_CLEARNET": "true",
    "OPERATIONAL_NODE_CONTAINER_HOST": "true",
    "OPERATIONAL_BLOCKCHAIN_CONTAINER_HOST": "true",
    "OPERATIONAL_SESSIONS_CONTAINER_HOST": "true",
    "OPERATIONAL_OPERATIONS_CONTAINER_HOST": "true",
    "OPERATIONAL_PAYSYSTEMS_CONTAINER_HOST": "true",
    "OPERATIONAL_FRONTEND_CONTAINER_HOST": "true",
}

CONNECTION_LAYER_SPECS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "master_connection",
        "master_connection_schema",
        {
            "protocol": "master_database_connection",
            "source": "MasterDBSchema.py",
            "database": MASTER_DB_NAME,
            "host": MONGODB_HOST,
            "port": MONGODB_PORT,
            "admin_only": True,
        },
    ),
    (
        "master_connection_connection",
        "master_connection_connection_schema",
        {
            "protocol": "connection",
            "source": "connection.py",
            "transport": "tor-hidden-service",
            "network": "tor",
            "returns": "IDToken",
            "persistent": True,
        },
    ),
    (
        "master_connection_connection_connection",
        "master_connection_connection_connection_schema",
        {
            "protocol": "handshake",
            "source": "handshake.py",
            "requires_api_key": True,
            "returns": "IDToken",
            "id_length": 8,
        },
    ),
    (
        "master_connection_connection_connection_connection",
        "master_connection_connection_connection_connection_schema",
        {
            "protocol": "client_handler",
            "source": "ClientHandler.py",
            "origin": "frontend",
            "requires_handshake": True,
            "client_request_route": f"{API_PREFIX}/client-request",
            "client_request_tor_config": f"{API_PREFIX}/client-request/tor-config",
        },
    ),
)

TOR_ROUTES_MANIFEST_FILENAME = "tor-routes.json"

CORE_PROTOCOL_ROUTES: tuple[str, ...] = (
    "/client-request",
    "/client-request/tor-config",
    "/handshake",
    "/connection",
    "/connection/tor-config",
    "/connection/validate-onion",
)

ONION_ENV_KEYS: dict[str, str] = {
    "master_server": "MASTER_SERVER_ONION",
    "frontend": "FRONTEND_ONION",
    "node_user": "NODEUSER_ONION",
}

ONION_FILE_MAP: dict[str, str] = {
    "lucid_server.onion": "master_server",
    "lucid_portal.onion": "frontend",
    "lucid_node.onion": "node_user",
}


def _format_tor_http_service(onion: str | None, path: str) -> str:
    """Return http://<onion><path> when onion is known, otherwise the API/GUI path."""
    normalized = path if path.startswith("/") else f"/{path}"
    if onion and onion.strip():
        host = onion.strip().lower().split("/")[0]
        return f"http://{host}{normalized}"
    return normalized


def _resolve_onion_addresses(
    root_dir: Path,
    *,
    launch_config: dict[str, Any] | None = None,
    server_env_path: Path | None = None,
) -> dict[str, str]:
    """Resolve *.onion hostnames from launch config, server.env, or LaunchServer onion files."""
    addresses: dict[str, str] = {
        "master_server": "",
        "frontend": "",
        "node_user": "",
    }
    cfg = launch_config or {}
    cfg_map = {
        "master_server": "master_server_onion",
        "frontend": "frontend_onion",
        "node_user": "nodeuser_onion",
    }
    for key, cfg_key in cfg_map.items():
        value = str(cfg.get(cfg_key, "")).strip().lower()
        if value.endswith(".onion"):
            addresses[key] = value.split("/")[0]

    env_path = server_env_path or root_dir / "server.env"
    if env_path.exists():
        env_values = _parse_env_file(env_path)
        for key, env_key in ONION_ENV_KEYS.items():
            if addresses[key]:
                continue
            value = env_values.get(env_key, "").strip().lower()
            if value.endswith(".onion"):
                addresses[key] = value.split("/")[0]

    onion_dir = root_dir / "data" / "tor" / "onion"
    for filename, key in ONION_FILE_MAP.items():
        if addresses[key]:
            continue
        path = onion_dir / filename
        if not path.exists():
            continue
        value = path.read_text(encoding="utf-8").strip().lower()
        if value.endswith(".onion"):
            addresses[key] = value.split("/")[0]

    return addresses


def _collect_all_api_routes() -> tuple[str, ...]:
    """Collect every FastAPI route registered on the master server (operations + core)."""
    combined: set[str] = set(CORE_PROTOCOL_ROUTES)
    combined.update(MASTER_API_ROUTES)
    combined.update(USER_ROUTES)
    combined.update(NODE_ROUTES)
    combined.update(BLOCKCHAIN_ROUTES)
    combined.update(SESSION_ROUTES)
    combined.update(DATABASE_ROUTES)
    try:
        from operations import CHIP_IN_ROUTES

        combined.update(CHIP_IN_ROUTES)
    except ImportError:
        pass
    return tuple(sorted(combined))


def build_tor_route_registry(
    *,
    master_onion: str | None,
    frontend_onion: str | None = None,
    node_onion: str | None = None,
    api_prefix: str = API_PREFIX,
    gui_prefix: str = GUI_PREFIX,
) -> dict[str, Any]:
    """Build configurable http://<master-onion>/api/v1/... tor service URLs for all routes."""
    master = (master_onion or "").strip().lower().split("/")[0] or None
    frontend = (frontend_onion or "").strip().lower().split("/")[0] or None
    node = (node_onion or "").strip().lower().split("/")[0] or None
    gui_host = frontend or master

    api_routes = _collect_all_api_routes()
    route_entries: dict[str, dict[str, str]] = {}
    for route in api_routes:
        api_path = route if route.startswith(api_prefix) else f"{api_prefix}{route}"
        route_entries[route] = {
            "api_path": api_path,
            "tor_service": _format_tor_http_service(master, api_path),
            "master_onion": master or "",
        }

    gui_entries: dict[str, dict[str, str]] = {}
    for route in GUI_ROUTES:
        gui_path = route if route.startswith(gui_prefix) else f"{gui_prefix}{route}"
        gui_entries[route] = {
            "gui_path": gui_path,
            "tor_service": _format_tor_http_service(gui_host, gui_path),
            "frontend_onion": frontend or master or "",
        }

    client_request_path = f"{api_prefix}/client-request"
    connect_handshake_path = f"{gui_prefix}/connect-handshake"

    return {
        "generated_at": utc_now(),
        "network": "tor",
        "tor_only": True,
        "api_prefix": api_prefix,
        "gui_prefix": gui_prefix,
        "master_server_onion": master or "",
        "frontend_onion": frontend or "",
        "nodeuser_onion": node or "",
        "tor_api_base": _format_tor_http_service(master, api_prefix),
        "tor_gui_base": _format_tor_http_service(gui_host, gui_prefix),
        "master_server_tor_service": _format_tor_http_service(master, ""),
        "client_request_route": client_request_path,
        "client_request_tor_service": _format_tor_http_service(master, client_request_path),
        "client_request_tor_config": _format_tor_http_service(
            master, f"{api_prefix}/client-request/tor-config"
        ),
        "handshake_tor_service": _format_tor_http_service(master, f"{api_prefix}/handshake"),
        "connection_tor_service": _format_tor_http_service(master, f"{api_prefix}/connection"),
        "connection_tor_config": _format_tor_http_service(
            master, f"{api_prefix}/connection/tor-config"
        ),
        "connect_handshake_tor_service": _format_tor_http_service(gui_host, connect_handshake_path),
        "routes": route_entries,
        "gui_routes": gui_entries,
    }


def _tor_service_env_lines(tor_registry: dict[str, Any]) -> list[str]:
    """Return server.env lines for resolved Tor service URLs (not empty placeholders)."""
    return [
        "",
        "# Tor hidden service URLs (http://<onion>/path — filled when onion hostname is known)",
        f"MASTER_SERVER_ONION={tor_registry.get('master_server_onion', '')}",
        f"FRONTEND_ONION={tor_registry.get('frontend_onion', '')}",
        f"NODEUSER_ONION={tor_registry.get('nodeuser_onion', '')}",
        f"API_BASE_PATH={tor_registry.get('api_prefix', API_PREFIX)}",
        f"GUI_PREFIX={tor_registry.get('gui_prefix', GUI_PREFIX)}",
        f"MASTER_SERVER_TOR_SERVICE={tor_registry.get('master_server_tor_service', '')}",
        f"TOR_API_SERVICE={tor_registry.get('tor_api_base', '')}",
        f"TOR_GUI_SERVICE={tor_registry.get('tor_gui_base', '')}",
        f"CLIENT_REQUEST_ROUTE={tor_registry.get('client_request_route', f'{API_PREFIX}/client-request')}",
        f"CLIENT_REQUEST_TOR_SERVICE={tor_registry.get('client_request_tor_service', '')}",
        f"CLIENT_REQUEST_TOR_CONFIG={tor_registry.get('client_request_tor_config', '')}",
        f"HANDSHAKE_TOR_SERVICE={tor_registry.get('handshake_tor_service', '')}",
        f"CONNECTION_TOR_SERVICE={tor_registry.get('connection_tor_service', '')}",
        f"CONNECTION_TOR_CONFIG={tor_registry.get('connection_tor_config', '')}",
        f"CONNECT_HANDSHAKE_TOR_SERVICE={tor_registry.get('connect_handshake_tor_service', '')}",
    ]


def apply_tor_service_env_updates(
    *,
    server_env_path: Path,
    onions: dict[str, str | None],
    tor_routes_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Update server.env with resolved http://*.onion route URLs (LaunchServer.py post-Tor step)."""
    normalized = {
        "master_server": str(onions.get("master_server") or "").strip().lower().split("/")[0],
        "frontend": str(onions.get("frontend") or "").strip().lower().split("/")[0],
        "node_user": str(onions.get("node_user") or "").strip().lower().split("/")[0],
    }
    tor_registry = build_tor_route_registry(
        master_onion=normalized["master_server"] or None,
        frontend_onion=normalized["frontend"] or None,
        node_onion=normalized["node_user"] or None,
    )
    if tor_routes_manifest_path is not None:
        tor_routes_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tor_routes_manifest_path.write_text(
            json.dumps(tor_registry, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if not server_env_path.exists():
        return tor_registry

    tor_env_map = {
        key: value
        for line in _tor_service_env_lines(tor_registry)
        if line and "=" in line and not line.startswith("#")
        for key, value in [line.split("=", 1)]
    }
    tor_env_map["MASTER_SERVER_PUBLIC_ONION"] = normalized["master_server"]
    if tor_routes_manifest_path is not None:
        tor_env_map["TOR_ROUTES_MANIFEST"] = tor_routes_manifest_path.as_posix()
    for key, env_key in ONION_ENV_KEYS.items():
        tor_env_map[env_key] = normalized.get(key, "")

    lines = server_env_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            updated.append(line)
            continue
        key = line.split("=", 1)[0]
        if key in tor_env_map:
            updated.append(f"{key}={tor_env_map[key]}")
            tor_env_map.pop(key, None)
        else:
            updated.append(line)

    for key, value in tor_env_map.items():
        updated.append(f"{key}={value}")

    server_env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return tor_registry


def _generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _generate_hex_secret(length: int = 32) -> str:
    return secrets.token_hex(length)


def _ensure_directories() -> None:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "data" / "tor").mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "configs").mkdir(parents=True, exist_ok=True)


def _build_generated_secrets() -> dict[str, str]:
    return {
        "API_KEY": _generate_secret(24),
        "API_SECRET": _generate_secret(48),
        "MONGODB_PASSWORD": _generate_secret(24),
        "MONGODB_ADMIN_PASSWORD": _generate_secret(24),
        "JWT_SECRET_KEY": _generate_secret(32),
        "SESSION_SECRET": _generate_secret(24),
        "ENCRYPTION_KEY": _generate_hex_secret(32),
        "TOR_CONTROL_PASSWORD": _generate_secret(24),
        "TOR_SOCKS_PASSWORD": _generate_secret(24),
        "TOR_PASSWORD": _generate_secret(24),
        "BLOCKCHAIN_SECRET": _generate_secret(32),
        "BLOCKCHAIN_SECRET_KEY": _generate_secret(32),
        "ADMIN_SECRET": _generate_secret(24),
        "MASTER_CLASS_SECRET": _generate_secret(24),
        "LUCID_TOKENS_HOLDING_ACCOUNT": _generate_hex_secret(16),
    }


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _resolve_generated_secrets(secrets_env_path: Path | None = None) -> dict[str, str]:
    path = secrets_env_path or SECRETS_ENV_PATH
    if path.exists():
        existing = _parse_env_file(path)
        loaded = {key: existing[key] for key in SECRET_KEYS if existing.get(key)}
        if len(loaded) == len(SECRET_KEYS):
            return loaded
    return _build_generated_secrets()


def _resolve_launch_values(launch_config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = launch_config or {}
    master_port = int(cfg.get("master_server_port", MASTER_SERVER_PORT))
    gui_port = int(cfg.get("gui_bridge_port", GUI_BRIDGE_PORT))
    mongodb_host = str(cfg.get("mongodb_host", MONGODB_HOST))
    mongodb_port = int(cfg.get("mongodb_port", MONGODB_PORT))
    mongodb_service = str(cfg.get("mongodb_service", "")).strip()
    network_name = str(cfg.get("docker_network_name", "lucid-stack"))
    enabled_services = tuple(cfg.get("enabled_services", DEFAULT_DOCKER_SERVICES))
    root_dir = Path(cfg.get("lucid_tops_root", ROOT_DIR))
    secrets_dir = Path(cfg.get("secrets_dir", root_dir / "secrets"))
    return {
        "root_dir": root_dir,
        "secrets_dir": secrets_dir,
        "master_server_port": master_port,
        "gui_bridge_port": gui_port,
        "mongodb_host": mongodb_host,
        "mongodb_port": mongodb_port,
        "mongodb_service": mongodb_service,
        "docker_network_name": network_name,
        "enabled_services": enabled_services,
    }


def _build_server_env(
    generated: dict[str, str],
    *,
    launch_values: dict[str, Any] | None = None,
    tor_registry: dict[str, Any] | None = None,
) -> str:
    values = launch_values or _resolve_launch_values(None)
    root_dir = values["root_dir"]
    secrets_dir = values["secrets_dir"]
    master_port = values["master_server_port"]
    gui_port = values["gui_bridge_port"]
    mongodb_host = values["mongodb_host"]
    mongodb_port = values["mongodb_port"]
    network_name = values["docker_network_name"]

    if tor_registry is None:
        onions = _resolve_onion_addresses(root_dir)
        tor_registry = build_tor_route_registry(
            master_onion=onions.get("master_server") or None,
            frontend_onion=onions.get("frontend") or None,
            node_onion=onions.get("node_user") or None,
        )

    lines = [
        "# =============================================================================",
        "# LucidTops master server - server.env (non-secret runtime configuration)",
        f"# Generated: {utc_now()}",
        "# Compatible with Dockerfile-layout.txt / master-env-config.txt container mounts",
        "# =============================================================================",
        "",
        f"LUCID_TOPS_ROOT={root_dir.as_posix()}",
        "LUCID_PROJECT_ROOT=/app",
        "BUILD_ARCH=arm64",
        "BIND_ADDRESS=127.0.0.1",
        "",
        "# Host-side paths (Pi SSD mount -> container volume mounts)",
        f"HOST_TOR_CONFIG_TORRC={(root_dir / 'torrc').as_posix()}",
        f"HOST_TOR_DATA={root_dir.as_posix()}/data/tor",
        f"HOST_TOR_LOG={root_dir.as_posix()}/logs",
        f"HOST_TOR_DIR=/app/var/lib/tor",
        f"HOST_TOR_ETC_DIR=/app/etc/tor",
        f"HOST_TOR_LUCID_SERVER_DIR=/app/var/lib/tor/lucid_server",
        f"HOST_TOR_LUCID_PORTAL_DIR=/app/var/lib/tor/lucid_portal",
        f"HOST_TOR_LUCID_DEV_DIR=/app/var/lib/tor/lucid_node",
        f"HOST_TOR_LUCID_BLOCKCHAIN_DIR=/app/var/lib/tor/lucid_blockchain",
        f"HOST_TOR_LUCID_ADMIN_DIR=/app/var/lib/tor/lucid_admin",
        f"CONTAINER_ONION_DIR=/app/run/lucid/onion",
        f"CONFIG_STORAGE_PATH=/app/config",
        f"SECRETS_DIR={secrets_dir.as_posix()}",
        "",
        "# Docker DNS service names (infrastructure/containers/* Dockerfiles)",
        f"DOCKER_NETWORK_NAME={network_name}",
        f"MONGODB_HOST={mongodb_host}",
        f"MONGODB_PORT={mongodb_port}",
        f"MONGODB_MAIN_DATABASE_NAME={MASTER_DB_NAME}",
        "MONGODB_HOST_CONTAINER=lucid-mongodb",
        f"MONGODB_URL=mongodb://{mongodb_host}:{mongodb_port}/{MASTER_DB_NAME}",
        f"LUCID_MONGODB_URL=mongodb://{mongodb_host}:{mongodb_port}",
        "",
        "# Tor daemon runs inside lucid-server-default (no tor-proxy sidecar)",
        "TOR_HOST=127.0.0.1",
        "TOR_SOCKS_HOST=127.0.0.1",
        "TOR_SOCKS_PORT=9050",
        "TOR_CONTROL_PORT=9051",
        "",
        "# Master server FastAPI + session routes (operations/SessionRoutes.py) — Tor-only",
        f"GUI_API_BRIDGE_PORT={gui_port}",
        "MASTER_SERVER_TOR_ONLY=true",
        "MASTER_SERVER_BIND_HOST=127.0.0.1",
        "MASTER_SERVER_HOST=127.0.0.1",
        f"MASTER_SERVER_PORT={master_port}",
        "MASTER_SERVER_SERVICE_NAME=lucid-server-default",
        "MASTER_SERVER_HEALTH_PATH=/health",
        "MASTER_SERVER_INTERNAL_HEALTH_HOST=127.0.0.1",
        f"MASTER_SERVER_PUBLIC_ONION={tor_registry.get('master_server_onion', '')}",
        "API_PUBLIC_PATH=/api/v1",
        "GUI_PUBLIC_PATH=/gui",
        "# Internal Docker DNS (container mesh only — not Tor public surface)",
        f"MASTER_SERVER_INTERNAL_HOST=lucid-server-default",
        f"MASTER_SERVER_INTERNAL_PORT={master_port}",
        *[
            line
            for line in _tor_service_env_lines(tor_registry)
            if not line.startswith("TOR_ROUTES_MANIFEST=")
        ],
        f"TOR_ROUTES_MANIFEST={(root_dir / 'configs' / TOR_ROUTES_MANIFEST_FILENAME).as_posix()}",
        "CONNECTION_PROTOCOL=tor-hidden-service",
        "CONNECTION_TORRENT_LAYER=torrent-over-tor",
        "CONNECTION_NETWORK=tor",
        "CONNECTION_TOR_ONLY=true",
        "CONNECTION_RETURNS=IDToken",
        "",
        "# Schema registry references",
        "MASTER_DB_SCHEMA=MasterDBSchema.py",
        "NODE_DB_SCHEMA=NodeDbSchema.py",
        "CONNECTION_PROTOCOL_FILE=connection.py",
        "HANDSHAKE_PROTOCOL_FILE=handshake.py",
        "CLIENT_HANDLER_FILE=ClientHandler.py",
        "",
        "# Route manifest",
        f"MASTER_BUILD_MANIFEST={BUILD_MANIFEST_PATH.as_posix()}",
        "SERVER_ENV_FILE=" + (root_dir / "server.env").as_posix(),
        "SECRETS_ENV_FILE=" + (root_dir / "secrets.env").as_posix(),
        *container_secrets_env_lines(secrets_dir),
        "",
        "# Runtime secrets: secrets.env (sourced by container entrypoint before uvicorn)",
        "# Critical operation profile: server.secrets (generated at container operation time)",
        "# Runtime configuration: config.secrets (editable without code changes)",
        "# Operations routes: operations.secrets (editable without code changes)",
    ]
    return "\n".join(lines) + "\n"


def _patch_operations_secrets_onions(
    operations_secrets_path: Path,
    *,
    master_onion: str | None,
    frontend_onion: str | None,
    node_onion: str | None,
) -> None:
    if not operations_secrets_path.exists():
        return
    lines = operations_secrets_path.read_text(encoding="utf-8").splitlines()
    replacements = {
        "MASTER_SERVER_ONION": (master_onion or "").strip(),
        "FRONTEND_ONION": (frontend_onion or "").strip(),
        "NODEUSER_ONION": (node_onion or "").strip(),
    }
    patched: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in replacements and replacements[key]:
                patched.append(f"{key}={replacements[key]}")
                continue
        patched.append(line)
    operations_secrets_path.write_text("\n".join(patched) + "\n", encoding="utf-8")


def _build_config_secrets_defaults(*, launch_values: dict[str, Any]) -> dict[str, str]:
    master_port = launch_values["master_server_port"]
    gui_port = launch_values["gui_bridge_port"]
    return {
        "LOCAL_TOR_FORWARD_HOSTS": "127.0.0.1,localhost,::1",
        "TOR_HOST": "127.0.0.1",
        "TOR_SOCKS_HOST": "127.0.0.1",
        "TOR_SOCKS_PORT": "9050",
        "TOR_CONTROL_PORT": "9051",
        "HIDDEN_SERVICE_FORWARD_HOST": "127.0.0.1",
        "MASTER_SERVER_BIND_HOST": "127.0.0.1",
        "MASTER_SERVER_HOST": "127.0.0.1",
        "MASTER_SERVER_PORT": str(master_port),
        "GUI_API_BRIDGE_PORT": str(gui_port),
        "ALLOWED_ONGOING_SOURCES": DEFAULT_ALLOWED_ONGOING_SOURCES,
        "INITIAL_HANDSHAKE_SOURCES": DEFAULT_INITIAL_HANDSHAKE_SOURCES,
        "REGISTER_SOURCE": "register.js",
        "NODE_MIN_MEMORY_GB": "50",
        "SESSION_CHUNK_SIZE_BYTES": "1048576",
        "MAX_MASTER_CLASS_USERS": "5",
        "MAX_CONSOLES_PER_NODE_USER": "5",
        "HANDSHAKE_ID_LENGTH": "8",
        "HANDSHAKE_ID_TOKEN_BYTES": "32",
        "HANDSHAKE_API_KEY_MIN_LENGTH": "24",
        "HANDSHAKE_API_KEY_GENERATION_LENGTH": "24",
        "NODE_GOV_BANNED_COLLECTION": "node_governance_bans",
        "NODE_GOV_AUDIT_COLLECTION": "node_governance_audit",
    }


def _resolve_config_secrets(
    config_secrets_path: Path,
    *,
    launch_values: dict[str, Any],
) -> dict[str, str]:
    defaults = _build_config_secrets_defaults(launch_values=launch_values)
    if config_secrets_path.exists():
        existing = _parse_env_file(config_secrets_path)
        merged = dict(defaults)
        merged.update(existing)
        return merged
    return defaults


def _build_config_secrets(
    values: dict[str, str],
    *,
    launch_values: dict[str, Any],
) -> str:
    secrets_dir = launch_values["secrets_dir"]
    lines = [
        "# =============================================================================",
        "# LucidTops config.secrets — editable runtime configuration",
        f"# Generated: {utc_now()}",
        f"# Path: {(secrets_dir / DEFAULT_CONFIG_SECRETS_NAME).as_posix()}",
        "# Edit this file to change behaviour without modifying Python source code.",
        "# Format: KEY=value (same as payments.secrets / secrets.env)",
        "# =============================================================================",
        "",
        "# Tor / bind addresses",
    ]
    tor_keys = (
        "LOCAL_TOR_FORWARD_HOSTS",
        "TOR_HOST",
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "TOR_CONTROL_PORT",
        "HIDDEN_SERVICE_FORWARD_HOST",
        "MASTER_SERVER_BIND_HOST",
        "MASTER_SERVER_HOST",
        "MASTER_SERVER_PORT",
        "GUI_API_BRIDGE_PORT",
    )
    for key in tor_keys:
        lines.append(f"{key}={values[key]}")
    lines.extend(["", "# Frontend javascript sources permitted for handshake/connection"])
    for key in ("ALLOWED_ONGOING_SOURCES", "INITIAL_HANDSHAKE_SOURCES", "REGISTER_SOURCE"):
        lines.append(f"{key}={values[key]}")
    lines.extend(["", "# Governance and handshake tuning"])
    for key in (
        "NODE_MIN_MEMORY_GB",
        "SESSION_CHUNK_SIZE_BYTES",
        "MAX_MASTER_CLASS_USERS",
        "MAX_CONSOLES_PER_NODE_USER",
        "HANDSHAKE_ID_LENGTH",
        "HANDSHAKE_ID_TOKEN_BYTES",
        "HANDSHAKE_API_KEY_MIN_LENGTH",
        "HANDSHAKE_API_KEY_GENERATION_LENGTH",
        "NODE_GOV_BANNED_COLLECTION",
        "NODE_GOV_AUDIT_COLLECTION",
    ):
        lines.append(f"{key}={values[key]}")
    return "\n".join(lines) + "\n"


def _build_secrets_env(
    generated: dict[str, str],
    *,
    launch_values: dict[str, Any] | None = None,
) -> str:
    values = launch_values or _resolve_launch_values(None)
    mongodb_host = values["mongodb_host"]
    lines = [
        "# =============================================================================",
        "# LucidTops master server - secrets.env (NEVER commit to version control)",
        f"# Generated: {utc_now()}",
        "# Mount into containers as configs/.env.secrets (Dockerfile-layout.txt step 11)",
        "# =============================================================================",
        "",
        f"MONGODB_HOST={mongodb_host}",
    ]
    for key, value in generated.items():
        if not value:
            raise ValueError(f"secret {key} must be produced at operation time (empty value)")
        lines.append(f"{key}={value}")
    lines.extend(
        [
            "",
            "# Master server bootstrap credentials written by LaunchServer.py",
            "ADMIN_USER_BOOTSTRAP_FILE=AdminUser/admin.txt",
            "MASTER_CLASS_USER_BOOTSTRAP_FILE=MasterClassUser/master.txt",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_server_secrets(
    generated: dict[str, str],
    *,
    launch_values: dict[str, Any],
    tor_registry: dict[str, Any] | None = None,
) -> str:
    """Write critical operational information + generated secrets (no placeholders)."""
    root_dir = launch_values["root_dir"]
    secrets_dir = launch_values["secrets_dir"]
    registry = tor_registry or {}
    for key, value in generated.items():
        if not value:
            raise ValueError(f"secret {key} must be produced at operation time (empty value)")

    lines = [
        "# =============================================================================",
        "# LucidTops server.secrets — critical information produced at operation time",
        f"# Generated: {utc_now()}",
        f"# Path: {(secrets_dir / DEFAULT_SERVER_SECRETS_NAME).as_posix()}",
        "# Produced by backend/builderMasterServer.py inside the Server.dockerfile container",
        "# =============================================================================",
        "",
        "# Critical host / security profile",
    ]
    for key, value in SERVER_CRITICAL_PROFILE.items():
        lines.append(f"{key}={value}")

    lines.extend(["", "# Operational roles (Backend = MasterServer container host)"])
    for key, value in SERVER_OPERATIONAL_FLAGS.items():
        lines.append(f"{key}={value}")

    lines.extend(
        [
            "",
            "# Runtime paths (LucidTops SSD mount)",
            f"LUCID_TOPS_ROOT={root_dir.as_posix()}",
            f"SECRETS_DIR={secrets_dir.as_posix()}",
            f"SERVER_ENV_FILE={(root_dir / 'server.env').as_posix()}",
            f"SECRETS_ENV_FILE={(root_dir / 'secrets.env').as_posix()}",
            f"SERVER_SECRETS_FILE={(secrets_dir / DEFAULT_SERVER_SECRETS_NAME).as_posix()}",
            f"TORRC_FILE={(root_dir / 'torrc').as_posix()}",
            f"DOCKER_NETWORK_NAME={launch_values['docker_network_name']}",
            f"ENABLED_SERVICES={','.join(launch_values['enabled_services'])}",
            f"MASTER_SERVER_PORT={launch_values['master_server_port']}",
            f"GUI_API_BRIDGE_PORT={launch_values['gui_bridge_port']}",
            f"MONGODB_HOST={launch_values['mongodb_host']}",
            f"MONGODB_PORT={launch_values['mongodb_port']}",
            f"MONGODB_MAIN_DATABASE_NAME={MASTER_DB_NAME}",
            "",
            "# Cryptographic / auth secrets (generated at operation time)",
        ]
    )
    for key in SECRET_KEYS:
        lines.append(f"{key}={generated[key]}")

    onion_lines: list[str] = []
    for env_key, registry_key in (
        ("MASTER_SERVER_ONION", "master_server_onion"),
        ("FRONTEND_ONION", "frontend_onion"),
        ("NODEUSER_ONION", "nodeuser_onion"),
        ("CLIENT_REQUEST_TOR_SERVICE", "client_request_tor_service"),
        ("TOR_API_SERVICE", "tor_api_base"),
        ("TOR_GUI_SERVICE", "tor_gui_base"),
    ):
        value = str(registry.get(registry_key, "")).strip()
        if value:
            onion_lines.append(f"{env_key}={value}")
    if onion_lines:
        lines.extend(["", "# Tor hidden-service endpoints (only written when resolved)"])
        lines.extend(onion_lines)

    return "\n".join(lines) + "\n"


def _build_torrc(*, launch_values: dict[str, Any] | None = None) -> str:
    values = launch_values or _resolve_launch_values(None)
    master_port = values["master_server_port"]
    gui_port = values["gui_bridge_port"]
    return "\n".join(
        [
            "# LucidTops master torrc - generated by backend/builderMasterServer.py",
            f"# Host mount: {(values['root_dir'] / 'torrc').as_posix()} -> container /app/var/lib/tor/torrc",
            f"# Generated: {utc_now()}",
            "Log notice stdout",
            "SocksPort 0.0.0.0:9050",
            "ControlPort 0.0.0.0:9051",
            "CookieAuthentication 1",
            "CookieAuthFile /app/var/lib/tor/control_auth_cookie",
            "CookieAuthFileGroupReadable 1",
            "DataDirectory /app/var/lib/tor",
            "RunAsDaemon 0",
            "AvoidDiskWrites 0",
            "",
            "# Master server hidden service (LaunchServer.py writes hostname to CONTAINER_ONION_DIR)",
            "HiddenServiceDir /app/var/lib/tor/lucid_server",
            "HiddenServiceVersion 3",
            f"HiddenServicePort 80 127.0.0.1:{master_port}",
            "",
            "# Frontend GUI hidden service",
            "HiddenServiceDir /app/var/lib/tor/lucid_portal",
            "HiddenServiceVersion 3",
            f"HiddenServicePort 80 127.0.0.1:{gui_port}",
            "",
            "# NodeUser hidden service",
            "HiddenServiceDir /app/var/lib/tor/lucid_node",
            "HiddenServiceVersion 3",
            f"HiddenServicePort 80 127.0.0.1:{master_port}",
            "",
        ]
    )


def _build_docker_dns_env(*, launch_values: dict[str, Any]) -> str:
    root_dir = launch_values["root_dir"]
    network_name = launch_values["docker_network_name"]
    mongodb_host = launch_values["mongodb_host"]
    mongodb_port = launch_values["mongodb_port"]
    master_port = launch_values["master_server_port"]
    gui_port = launch_values["gui_bridge_port"]
    enabled = launch_values["enabled_services"]
    lines = [
        "# LucidTops Docker DNS registry - generated by backend/builderMasterServer.py",
        f"# Generated: {utc_now()}",
        f"DOCKER_NETWORK_NAME={network_name}",
        f"LUCID_TOPS_ROOT={root_dir.as_posix()}",
        f"ENABLED_SERVICES={','.join(enabled)}",
        "",
        f"MONGODB_HOST={mongodb_host}",
        f"MONGODB_PORT={mongodb_port}",
        "MONGODB_SERVICE=lucid-mongodb",
        "",
        "MASTER_SERVER_SERVICE=lucid-server-default",
        f"MASTER_SERVER_PORT={master_port}",
        f"MASTER_SERVER_INTERNAL_HOST=lucid-server-default",
        f"MASTER_SERVER_INTERNAL_PORT={master_port}",
        "",
        f"GUI_API_BRIDGE_PORT={gui_port}",
        "GUI_API_BRIDGE_HOST=gui-api-bridge",
        "",
        "TOR_HOST=127.0.0.1",
        "TOR_SOCKS_HOST=127.0.0.1",
        "TOR_SOCKS_PORT=9050",
        "TOR_CONTROL_PORT=9051",
    ]
    return "\n".join(lines) + "\n"


def _build_docker_network_yml(*, launch_values: dict[str, Any]) -> str:
    root_dir = launch_values["root_dir"]
    secrets_dir = launch_values["secrets_dir"]
    network_name = launch_values["docker_network_name"]
    enabled = set(launch_values["enabled_services"])
    lines = [
        "# LucidTops Docker network overlay - generated by backend/builderMasterServer.py",
        f"# Generated: {utc_now()}",
        f"# Host root: {root_dir.as_posix()}",
        "networks:",
        f"  {network_name}:",
        f"    name: {network_name}",
        "    driver: bridge",
        "",
        "volumes:",
        "  lucid-mongo-data:",
        "  lucid-tor-data:",
        "  lucid-onion-data:",
        "",
        "services:",
    ]
    if "lucid-mongodb" in enabled:
        lines.extend(
            [
                "  lucid-mongodb:",
                "    image: mongo:7",
                "    container_name: lucid-mongodb",
                "    restart: unless-stopped",
                f"    networks:",
                f"      - {network_name}",
                "    volumes:",
                "      - lucid-mongo-data:/data/db",
            ]
        )
    if "lucid-server-default" in enabled:
        lines.extend(
            [
                "  lucid-server-default:",
                "    build:",
                "      context: ..",
                "      dockerfile: backend/Server.dockerfile",
                "    container_name: lucid-server-default",
                "    restart: unless-stopped",
                f"    networks:",
                f"      - {network_name}",
                "    env_file:",
                f"      - {root_dir.as_posix()}/server.env",
                "    environment:",
                *[
                    f"      {env_key}: {secrets_dir.as_posix()}/{filename}"
                    for env_key, filename in CONTAINER_SECRETS_SPECS
                ],
                f"      LUCID_TOPS_ROOT: {root_dir.as_posix()}",
                f"      SECRETS_DIR: {secrets_dir.as_posix()}",
                f"      SERVER_ENV_FILE: {root_dir.as_posix()}/server.env",
                f"      SECRETS_ENV_FILE: {root_dir.as_posix()}/secrets.env",
                f"      HOST_TOR_CONFIG_TORRC: {root_dir.as_posix()}/torrc",
                "    volumes:",
                f"      - {root_dir.as_posix()}:{root_dir.as_posix()}",
                "      - lucid-tor-data:/app/var/lib/tor",
                "      - lucid-onion-data:/app/run/lucid/onion",
            ]
        )
    service_image_map = (
        ("lucid-blockchain", "lucid-blockchain", "blockchain/Blockchain.dockerfile"),
        ("lucid-sessions", "lucid-sessions", "sessions/sessions.dockerfile"),
        ("lucid-operations", "lucid-operations", "operations/Ops.dockerfile"),
        ("lucid-paysystems", "lucid-paysystems", "paysystems/Pay.dockerfile"),
        ("lucid-frontend", "lucid-frontend", "frontend/webpage.dockerfile"),
    )
    for service_key, container_name, dockerfile in service_image_map:
        if service_key not in enabled:
            continue
        lines.extend(
            [
                f"  {service_key}:",
                "    build:",
                "      context: ..",
                f"      dockerfile: {dockerfile}",
                f"    container_name: {container_name}",
                "    restart: unless-stopped",
                "    networks:",
                f"      - {network_name}",
                "    env_file:",
                f"      - {root_dir.as_posix()}/server.env",
                "    environment:",
                f"      LUCID_TOPS_ROOT: {root_dir.as_posix()}",
                f"      SECRETS_DIR: {secrets_dir.as_posix()}",
                f"      SERVER_SECRETS_FILE: {secrets_dir.as_posix()}/{DEFAULT_SERVER_SECRETS_NAME}",
                "    volumes:",
                f"      - {root_dir.as_posix()}:{root_dir.as_posix()}",
            ]
        )
    return "\n".join(lines) + "\n"



def _create_master_database(client: Any, generated: dict[str, str]) -> dict[str, Any]:
    db = client[MASTER_DB_NAME]

    id_token_fields: tuple[str, ...] = (
        "entity",
        "UserID",
        "NodeUserID",
        "IDToken",
        "created_at",
        "updated_at",
    )
    node_gov_ban_fields: tuple[str, ...] = (
        "NodeUserID",
        "banned",
        "reason",
        "lucid_tokens_holding_account",
        "created_at",
        "updated_at",
    )
    node_gov_audit_fields: tuple[str, ...] = (
        "NodeUserID",
        "action",
        "reason",
        "sessionID",
        "timestamp",
    )

    collections: dict[str, dict[str, Any]] = {
        collection_name: schema_template(fields)
        for collection_name, fields in COLLECTION_SCHEMAS.items()
    }
    collections["node_hosted_databases"] = schema_template(NODE_DB_SCHEMA_FIELDS)
    collections["id_tokens"] = schema_template(id_token_fields)
    collections["node_governance_bans"] = schema_template(node_gov_ban_fields)
    collections["node_governance_audit"] = schema_template(node_gov_audit_fields)

    index_specs: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "users": [("UserID", {"unique": True, "sparse": True}), ("email", {"unique": True, "sparse": True})],
        NODE_USERS_COLLECTION: [("NodeUserID", {"unique": True, "sparse": True})],
        "admin_users": [("adminUserID", {"unique": True, "sparse": True})],
        "master_class_users": [("MasterClassUserID", {"unique": True, "sparse": True})],
        "session_records": [("sessionID", {"unique": True, "sparse": True})],
        "session_id_log": [("sessionID", {"unique": True, "sparse": True})],
        "session_keys": [("sessionID", {"unique": True, "sparse": True})],
        "id_tokens": [
            ("UserID", {"sparse": True}),
            ("NodeUserID", {"sparse": True}),
            ("IDToken", {"sparse": True}),
        ],
        "tally_records": [
            ("entity_type", {"sparse": True}),
            ("entity_id", {"sparse": True}),
        ],
        "task_tokens": [("taskToken", {"unique": True, "sparse": True})],
        "node_governance_bans": [("NodeUserID", {"unique": True, "sparse": True})],
    }

    for collection_name, template in collections.items():
        col = db[collection_name]
        col.create_index("_id")
        for field, options in index_specs.get(collection_name, []):
            col.create_index(field, **options)
        if not col.find_one({"_schema_template": True}):
            col.insert_one(
                {
                    "_schema_template": True,
                    "fields": list(template.keys()),
                    "admin_only": collection_name not in {
                        "users",
                        NODE_USERS_COLLECTION,
                        "session_records",
                        "session_id_log",
                    },
                    "created_at": utc_now(),
                }
            )

    db.master_credentials.update_one(
        {"bootstrap": True},
        {
            "$set": {
                "bootstrap": True,
                "API_key": generated["API_KEY"],
                "API_secret": generated["API_SECRET"],
                "userID_schema": list(USER_SCHEMA_FIELDS),
                "NodeUser_schema": list(NODE_USER_SCHEMA_FIELDS),
                "adminUser_schema": list(ADMIN_USER_SCHEMA_FIELDS),
                "MasterClassUser_schema": list(MASTER_CLASS_USER_SCHEMA_FIELDS),
                "updated_at": utc_now(),
            }
        },
        upsert=True,
    )

    return {"database": MASTER_DB_NAME, "collections": list(collections.keys())}


def _create_connection_layers(client: Any) -> list[dict[str, str]]:
    db = client[MASTER_DB_NAME]
    created: list[dict[str, str]] = []
    for connection_col, schema_col, spec in CONNECTION_LAYER_SPECS:
        db[connection_col].update_one(
            {"layer": connection_col},
            {"$set": {"layer": connection_col, "active": True, "updated_at": utc_now(), **spec}},
            upsert=True,
        )
        db[schema_col].update_one(
            {"layer": schema_col},
            {
                "$set": {
                    "layer": schema_col,
                    "spec": spec,
                    "fields_required": list(spec.keys()),
                    "updated_at": utc_now(),
                }
            },
            upsert=True,
        )
        created.append({"connection": connection_col, "schema": schema_col})
    return created



def _write_manifest(
    generated: dict[str, str],
    db_result: dict[str, Any] | None,
    connection_layers: list[dict[str, str]] | None,
    *,
    launch_values: dict[str, Any] | None = None,
    docker_dns_path: Path | None = None,
    docker_network_path: Path | None = None,
    server_env_path: Path | None = None,
    secrets_env_path: Path | None = None,
    mongodb_secrets_path: Path | None = None,
    torrc_path: Path | None = None,
    tor_registry: dict[str, Any] | None = None,
    tor_routes_path: Path | None = None,
    server_secrets_path: Path | None = None,
) -> None:
    values = launch_values or _resolve_launch_values(None)
    if tor_registry is None:
        onions = _resolve_onion_addresses(values["root_dir"], server_env_path=server_env_path)
        tor_registry = build_tor_route_registry(
            master_onion=onions.get("master_server") or None,
            frontend_onion=onions.get("frontend") or None,
            node_onion=onions.get("node_user") or None,
        )
    manifest = {
        "generated_at": utc_now(),
        "root_dir": values["root_dir"].as_posix(),
        "secrets_dir": values["secrets_dir"].as_posix(),
        "launch_config": {
            "master_server_port": values["master_server_port"],
            "gui_bridge_port": values["gui_bridge_port"],
            "mongodb_host": values["mongodb_host"],
            "mongodb_port": values["mongodb_port"],
            "docker_network_name": values["docker_network_name"],
            "enabled_services": list(values["enabled_services"]),
        },
        "critical_profile": dict(SERVER_CRITICAL_PROFILE),
        "operational_flags": dict(SERVER_OPERATIONAL_FLAGS),
        "files": {
            "server_env": (server_env_path or values["root_dir"] / "server.env").as_posix(),
            "secrets_env": (secrets_env_path or values["root_dir"] / "secrets.env").as_posix(),
            "server_secrets": (
                server_secrets_path or values["secrets_dir"] / DEFAULT_SERVER_SECRETS_NAME
            ).as_posix(),
            "mongodb_secrets": (
                mongodb_secrets_path or values["secrets_dir"] / DEFAULT_MONGODB_SECRETS_NAME
            ).as_posix(),
            "torrc": (torrc_path or values["root_dir"] / "torrc").as_posix(),
            "docker_dns_env": (docker_dns_path or values["root_dir"] / "configs" / "docker-dns.env").as_posix(),
            "docker_network_yml": (
                docker_network_path or values["root_dir"] / "configs" / "docker-network.yml"
            ).as_posix(),
            "tor_routes": (
                tor_routes_path or values["root_dir"] / "configs" / TOR_ROUTES_MANIFEST_FILENAME
            ).as_posix(),
            **{
                spec[0].lower(): (values["secrets_dir"] / spec[1]).as_posix()
                for spec in CONTAINER_SECRETS_SPECS
            },
        },
        "container_secrets": container_secrets_status(secrets_dir=values["secrets_dir"]),
        "tor_services": {
            "master_server_onion": tor_registry.get("master_server_onion", ""),
            "frontend_onion": tor_registry.get("frontend_onion", ""),
            "client_request_tor_service": tor_registry.get("client_request_tor_service", ""),
            "handshake_tor_service": tor_registry.get("handshake_tor_service", ""),
            "connection_tor_service": tor_registry.get("connection_tor_service", ""),
            "tor_api_base": tor_registry.get("tor_api_base", ""),
            "tor_gui_base": tor_registry.get("tor_gui_base", ""),
        },
        "database": db_result,
        "connection_layers": connection_layers or [],
        "routes": {
            "master_api": list(MASTER_API_ROUTES),
            "user": list(USER_ROUTES),
            "node": list(NODE_ROUTES),
            "blockchain": list(BLOCKCHAIN_ROUTES),
            "session": list(SESSION_ROUTES),
            "database": list(DATABASE_ROUTES),
            "gui": list(GUI_ROUTES),
            "admin": list(ADMIN_ROUTES),
            "master_class": list(MASTER_CLASS_ROUTES),
            "core_protocol": list(CORE_PROTOCOL_ROUTES),
        },
        "tor_routes": tor_registry,
        "schemas": {
            "master_credentials": list(MASTER_CREDENTIALS_FIELDS),
            "users": list(USER_SCHEMA_FIELDS),
            "node_users": list(NODE_USER_SCHEMA_FIELDS),
            "admin_users": list(ADMIN_USER_SCHEMA_FIELDS),
            "master_class_users": list(MASTER_CLASS_USER_SCHEMA_FIELDS),
            "node_hosted_databases": list(NODE_DB_SCHEMA_FIELDS),
            **{name: list(fields) for name, fields in COLLECTION_SCHEMAS.items()},
        },
        "api_key_fingerprint": generated["API_KEY"][:8],
    }
    BUILD_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _get_mongo_client_for_launch(launch_values: dict[str, Any]) -> Any | None:
    if MongoClient is None:
        return None
    url = (
        f"mongodb://{launch_values['mongodb_host']}:"
        f"{launch_values['mongodb_port']}/{MASTER_DB_NAME}"
    )
    try:
        client = MongoClient(url, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None


def build_master_server(launch_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run all 20 builder steps and write container-compatible host config files."""
    launch_values = _resolve_launch_values(launch_config)
    root_dir = launch_values["root_dir"]
    secrets_dir = launch_values["secrets_dir"]
    configs_dir = root_dir / "configs"
    docker_dns_path = configs_dir / "docker-dns.env"
    docker_network_path = configs_dir / "docker-network.yml"
    server_env_path = root_dir / "server.env"
    secrets_env_path = root_dir / "secrets.env"
    config_secrets_path = secrets_dir / DEFAULT_CONFIG_SECRETS_NAME
    operations_secrets_path = secrets_dir / "operations.secrets"
    server_secrets_path = secrets_dir / DEFAULT_SERVER_SECRETS_NAME
    mongodb_secrets_path = secrets_dir / DEFAULT_MONGODB_SECRETS_NAME
    torrc_path = root_dir / "torrc"

    root_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / "data" / "tor").mkdir(parents=True, exist_ok=True)
    (root_dir / "logs").mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)

    generated = _resolve_generated_secrets(secrets_env_path)
    config_secrets_values = _resolve_config_secrets(
        config_secrets_path,
        launch_values=launch_values,
    )

    onions = _resolve_onion_addresses(root_dir, launch_config=launch_config)
    tor_routes_path = configs_dir / TOR_ROUTES_MANIFEST_FILENAME
    tor_registry = build_tor_route_registry(
        master_onion=onions.get("master_server") or None,
        frontend_onion=onions.get("frontend") or None,
        node_onion=onions.get("node_user") or None,
    )
    tor_routes_path.write_text(json.dumps(tor_registry, indent=2, sort_keys=True), encoding="utf-8")

    server_env = _build_server_env(
        generated,
        launch_values=launch_values,
        tor_registry=tor_registry,
    )
    secrets_env = _build_secrets_env(generated, launch_values=launch_values)
    server_secrets = _build_server_secrets(
        generated,
        launch_values=launch_values,
        tor_registry=tor_registry,
    )
    config_secrets = _build_config_secrets(
        config_secrets_values,
        launch_values=launch_values,
    )
    torrc = _build_torrc(launch_values=launch_values)
    docker_dns_env = _build_docker_dns_env(launch_values=launch_values)
    docker_network_yml = _build_docker_network_yml(launch_values=launch_values)

    server_env_path.write_text(server_env, encoding="utf-8")
    secrets_env_path.write_text(secrets_env, encoding="utf-8")
    server_secrets_path.write_text(server_secrets, encoding="utf-8")
    config_secrets_path.write_text(config_secrets, encoding="utf-8")
    try:
        from operations.operations_secrets import write_operations_secrets_template

        write_operations_secrets_template(secrets_dir, populate_from_env=True, force=False)
    except ImportError:
        pass
    for env_key, value in (
        ("BLOCKCHAIN_SECRET", generated.get("BLOCKCHAIN_SECRET", "")),
        ("BLOCKCHAIN_SECRET_KEY", generated.get("BLOCKCHAIN_SECRET_KEY", "")),
    ):
        if value:
            os.environ[env_key] = value
    try:
        from blockchain.blockchain_secrets import write_blockchain_secrets_template

        write_blockchain_secrets_template(secrets_dir, populate_from_env=True, force=False)
    except ImportError:
        pass
    _patch_operations_secrets_onions(
        operations_secrets_path,
        master_onion=onions.get("master_server"),
        frontend_onion=onions.get("frontend"),
        node_onion=onions.get("node_user"),
    )
    torrc_path.write_text(torrc, encoding="utf-8")
    docker_dns_path.write_text(docker_dns_env, encoding="utf-8")
    docker_network_path.write_text(docker_network_yml, encoding="utf-8")

    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "api_key.txt").write_text(generated["API_KEY"], encoding="utf-8")
    (secrets_dir / "api_secret.txt").write_text(generated["API_SECRET"], encoding="utf-8")
    (secrets_dir / "lucid_tokens_holding_account.txt").write_text(
        generated["LUCID_TOKENS_HOLDING_ACCOUNT"],
        encoding="utf-8",
    )

    db_result: dict[str, Any] | None = None
    connection_layers: list[dict[str, str]] | None = None
    mongodb_verification: dict[str, Any] | None = None
    mongodb_secrets_written: Path | None = None
    client = _get_mongo_client_for_launch(launch_values)
    if client is not None:
        db_result = _create_master_database(client, generated)
        connection_layers = _create_connection_layers(client)
        mongodb_verification = verify_mongodb_creation(
            client,
            launch_values=launch_values,
            db_result=db_result,
        )
        if mongodb_verification.get("verified"):
            mongodb_secrets_written = write_mongodb_secrets_verified(
                secrets_dir,
                launch_values=launch_values,
                generated=generated,
                verification=mongodb_verification,
            )
            verified_env = {
                "MONGODB_HOST": str(mongodb_verification["mongodb_host"]),
                "MONGODB_PORT": str(mongodb_verification["mongodb_port"]),
                "MONGODB_MAIN_DATABASE_NAME": str(mongodb_verification["database"]),
                "MONGODB_URL": (
                    f"mongodb://{mongodb_verification['mongodb_host']}:"
                    f"{mongodb_verification['mongodb_port']}/{mongodb_verification['database']}"
                ),
                "LUCID_MONGODB_URL": (
                    f"mongodb://{mongodb_verification['mongodb_host']}:"
                    f"{mongodb_verification['mongodb_port']}"
                ),
            }
            service_name = str(mongodb_verification.get("mongodb_service", "")).strip()
            if service_name:
                verified_env["MONGODB_SERVICE"] = service_name
            for env_key, env_value in verified_env.items():
                if env_value:
                    os.environ[env_key] = env_value
            try:
                from blockchain.blockchain_secrets import write_blockchain_secrets_template

                write_blockchain_secrets_template(
                    secrets_dir,
                    populate_from_env=True,
                    force=True,
                )
            except ImportError:
                pass
        client.close()

    app_ready = False
    try:
        from main import create_app

        create_app()
        app_ready = True
    except Exception:
        app_ready = False

    _write_manifest(
        generated,
        db_result,
        connection_layers,
        launch_values=launch_values,
        docker_dns_path=docker_dns_path,
        docker_network_path=docker_network_path,
        server_env_path=server_env_path,
        secrets_env_path=secrets_env_path,
        mongodb_secrets_path=mongodb_secrets_written,
        torrc_path=torrc_path,
        tor_registry=tor_registry,
        tor_routes_path=tor_routes_path,
        server_secrets_path=server_secrets_path,
    )

    return {
        "root_dir": root_dir.as_posix(),
        "server_env": server_env_path.as_posix(),
        "secrets_env": secrets_env_path.as_posix(),
        "server_secrets": server_secrets_path.as_posix(),
        "config_secrets": config_secrets_path.as_posix(),
        "operations_secrets": operations_secrets_path.as_posix(),
        "mongodb_secrets": (
            mongodb_secrets_written.as_posix()
            if mongodb_secrets_written is not None
            else mongodb_secrets_path.as_posix()
        ),
        "mongodb_secrets_written": mongodb_secrets_written is not None,
        "mongodb_verified": bool(mongodb_verification and mongodb_verification.get("verified")),
        "container_secrets": container_secrets_status(secrets_dir=secrets_dir),
        "torrc": torrc_path.as_posix(),
        "docker_dns_env": docker_dns_path.as_posix(),
        "docker_network_yml": docker_network_path.as_posix(),
        "tor_routes": tor_routes_path.as_posix(),
        "manifest": BUILD_MANIFEST_PATH.as_posix(),
        "client_request_tor_service": tor_registry.get("client_request_tor_service", ""),
        "master_server_onion": tor_registry.get("master_server_onion", ""),
        "database_initialized": db_result is not None,
        "fastapi_app_ready": app_ready,
        "steps_completed": 20,
        "critical_profile": dict(SERVER_CRITICAL_PROFILE),
        "launch_config": {
            "master_server_port": launch_values["master_server_port"],
            "gui_bridge_port": launch_values["gui_bridge_port"],
            "mongodb_host": launch_values["mongodb_host"],
            "docker_network_name": launch_values["docker_network_name"],
            "enabled_services": list(launch_values["enabled_services"]),
        },
    }


def main() -> int:
    result = build_master_server()
    print("LucidTops master server builder complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")
    if not result["database_initialized"]:
        print(
            "  note: MongoDB was not reachable; env/tor/manifest written. "
            "Re-run on Pi after lucid-mongodb container is up.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
