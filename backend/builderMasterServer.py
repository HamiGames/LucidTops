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
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from config import (
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
)

DEFAULT_DOCKER_SERVICES: tuple[str, ...] = ("lucid-mongodb", "lucid-server-default")

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
        },
    ),
)


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
        "docker_network_name": network_name,
        "enabled_services": enabled_services,
    }


def _build_server_env(
    generated: dict[str, str],
    *,
    launch_values: dict[str, Any] | None = None,
) -> str:
    values = launch_values or _resolve_launch_values(None)
    root_dir = values["root_dir"]
    secrets_dir = values["secrets_dir"]
    master_port = values["master_server_port"]
    gui_port = values["gui_bridge_port"]
    mongodb_host = values["mongodb_host"]
    mongodb_port = values["mongodb_port"]
    network_name = values["docker_network_name"]
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
        "MASTER_SERVER_PUBLIC_ONION=${MASTER_SERVER_ONION}",
        "API_PUBLIC_PATH=/api/v1",
        "GUI_PUBLIC_PATH=/gui",
        "# Internal Docker DNS (container mesh only — not Tor public surface)",
        f"MASTER_SERVER_INTERNAL_HOST=lucid-server-default",
        f"MASTER_SERVER_INTERNAL_PORT={master_port}",
        "",
        "# Tor hidden service hostnames (filled by LaunchServer.py)",
        "MASTER_SERVER_ONION=",
        "FRONTEND_ONION=",
        "NODEUSER_ONION=",
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
        "",
        "# Secret placeholders resolved from secrets.env at container runtime",
        "API_KEY=${API_KEY}",
        "API_SECRET=${API_SECRET}",
        "MONGODB_PASSWORD=${MONGODB_PASSWORD}",
        "JWT_SECRET_KEY=${JWT_SECRET_KEY}",
        "SESSION_SECRET=${SESSION_SECRET}",
        "ENCRYPTION_KEY=${ENCRYPTION_KEY}",
        "TOR_CONTROL_PASSWORD=${TOR_CONTROL_PASSWORD}",
        "TOR_SOCKS_PASSWORD=${TOR_SOCKS_PASSWORD}",
        "TOR_PASSWORD=${TOR_PASSWORD}",
        "BLOCKCHAIN_SECRET=${BLOCKCHAIN_SECRET}",
        "ADMIN_SECRET=${ADMIN_SECRET}",
        "MASTER_CLASS_SECRET=${MASTER_CLASS_SECRET}",
    ]
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
                "    container_name: lucid-server-default",
                "    restart: unless-stopped",
                f"    networks:",
                f"      - {network_name}",
                "    env_file:",
                f"      - {root_dir.as_posix()}/server.env",
                "    environment:",
                "      MONGODB_HOST: lucid-mongodb",
                f"      LUCID_TOPS_ROOT: {root_dir.as_posix()}",
                f"      SECRETS_DIR: {root_dir.as_posix()}/secrets",
                f"      SERVER_ENV_FILE: {root_dir.as_posix()}/server.env",
                f"      SECRETS_ENV_FILE: {root_dir.as_posix()}/secrets.env",
                f"      HOST_TOR_CONFIG_TORRC: {root_dir.as_posix()}/torrc",
                "    volumes:",
                f"      - {root_dir.as_posix()}:{root_dir.as_posix()}",
                "      - lucid-tor-data:/app/var/lib/tor",
                "      - lucid-onion-data:/app/run/lucid/onion",
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
    torrc_path: Path | None = None,
) -> None:
    values = launch_values or _resolve_launch_values(None)
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
        "files": {
            "server_env": (server_env_path or values["root_dir"] / "server.env").as_posix(),
            "secrets_env": (secrets_env_path or values["root_dir"] / "secrets.env").as_posix(),
            "torrc": (torrc_path or values["root_dir"] / "torrc").as_posix(),
            "docker_dns_env": (docker_dns_path or values["root_dir"] / "configs" / "docker-dns.env").as_posix(),
            "docker_network_yml": (
                docker_network_path or values["root_dir"] / "configs" / "docker-network.yml"
            ).as_posix(),
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
        },
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
    torrc_path = root_dir / "torrc"

    root_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / "data" / "tor").mkdir(parents=True, exist_ok=True)
    (root_dir / "logs").mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)

    generated = _resolve_generated_secrets(secrets_env_path)

    server_env = _build_server_env(generated, launch_values=launch_values)
    secrets_env = _build_secrets_env(generated, launch_values=launch_values)
    torrc = _build_torrc(launch_values=launch_values)
    docker_dns_env = _build_docker_dns_env(launch_values=launch_values)
    docker_network_yml = _build_docker_network_yml(launch_values=launch_values)

    server_env_path.write_text(server_env, encoding="utf-8")
    secrets_env_path.write_text(secrets_env, encoding="utf-8")
    torrc_path.write_text(torrc, encoding="utf-8")
    docker_dns_path.write_text(docker_dns_env, encoding="utf-8")
    docker_network_path.write_text(docker_network_yml, encoding="utf-8")

    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "api_key.txt").write_text(generated["API_KEY"], encoding="utf-8")
    (secrets_dir / "api_secret.txt").write_text(generated["API_SECRET"], encoding="utf-8")

    db_result: dict[str, Any] | None = None
    connection_layers: list[dict[str, str]] | None = None
    client = _get_mongo_client_for_launch(launch_values)
    if client is not None:
        db_result = _create_master_database(client, generated)
        connection_layers = _create_connection_layers(client)

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
        torrc_path=torrc_path,
    )

    return {
        "root_dir": root_dir.as_posix(),
        "server_env": server_env_path.as_posix(),
        "secrets_env": secrets_env_path.as_posix(),
        "torrc": torrc_path.as_posix(),
        "docker_dns_env": docker_dns_path.as_posix(),
        "docker_network_yml": docker_network_path.as_posix(),
        "manifest": BUILD_MANIFEST_PATH.as_posix(),
        "database_initialized": db_result is not None,
        "fastapi_app_ready": app_ready,
        "steps_completed": 20,
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
