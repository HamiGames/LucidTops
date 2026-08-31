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
    BLOCKCHAIN_BLOCKS_COLLECTION,
    COLLECTION_SCHEMAS,
    LEDGER_RECORDS_COLLECTION,
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
    from pymongo.errors import PyMongoError
except ImportError:  # pragma: no cover
    PyMongoError = Exception  # type: ignore[misc, assignment]

BACKEND_DIR = Path(__file__).resolve().parent
BUILD_MANIFEST_PATH = BACKEND_DIR / "master_server_build_manifest.json"

ROOT_DIR = LUCID_TOPS_ROOT
API_GATEWAY_PORT = int(os.environ.get("API_GATEWAY_PORT", "8080"))
GUI_BRIDGE_PORT = int(os.environ.get("GUI_API_BRIDGE_PORT", "8105"))


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


def _build_server_env(generated: dict[str, str]) -> str:
    lines = [
        "# =============================================================================",
        "# LucidTops master server - server.env (non-secret runtime configuration)",
        f"# Generated: {utc_now()}",
        "# Compatible with Dockerfile-layout.txt / master-env-config.txt container mounts",
        "# =============================================================================",
        "",
        f"LUCID_TOPS_ROOT={ROOT_DIR.as_posix()}",
        "LUCID_PROJECT_ROOT=/app",
        "BUILD_ARCH=arm64",
        "BIND_ADDRESS=0.0.0.0",
        "",
        "# Host-side paths (Pi SSD mount -> container volume mounts)",
        f"HOST_TOR_CONFIG_TORRC={TORRC_PATH.as_posix()}",
        f"HOST_TOR_DATA={ROOT_DIR.as_posix()}/data/tor",
        f"HOST_TOR_LOG={ROOT_DIR.as_posix()}/logs",
        f"HOST_TOR_DIR=/app/var/lib/tor",
        f"HOST_TOR_ETC_DIR=/app/etc/tor",
        f"HOST_TOR_LUCID_SERVER_DIR=/app/var/lib/tor/lucid_server",
        f"HOST_TOR_LUCID_PORTAL_DIR=/app/var/lib/tor/lucid_portal",
        f"HOST_TOR_LUCID_DEV_DIR=/app/var/lib/tor/lucid_node",
        f"HOST_TOR_LUCID_BLOCKCHAIN_DIR=/app/var/lib/tor/lucid_blockchain",
        f"HOST_TOR_LUCID_ADMIN_DIR=/app/var/lib/tor/lucid_admin",
        f"CONTAINER_ONION_DIR=/app/run/lucid/onion",
        f"CONFIG_STORAGE_PATH=/app/config",
        f"SECRETS_DIR={SECRETS_DIR.as_posix()}",
        "",
        "# Docker DNS service names (infrastructure/containers/* Dockerfiles)",
        f"MONGODB_HOST={MONGODB_HOST}",
        f"MONGODB_PORT={MONGODB_PORT}",
        f"MONGODB_MAIN_DATABASE_NAME={MASTER_DB_NAME}",
        "MONGODB_HOST_CONTAINER=lucid-mongodb",
        f"MONGODB_URL=mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{MASTER_DB_NAME}",
        f"LUCID_MONGODB_URL=mongodb://{MONGODB_HOST}:{MONGODB_PORT}",
        "REDIS_HOST=lucid-redis",
        "REDIS_PORT=6379",
        "TOR_HOST=tor-proxy",
        "TOR_SOCKS_HOST=tor-proxy",
        "TOR_SOCKS_PORT=9050",
        "TOR_CONTROL_PORT=9051",
        "API_GATEWAY_HOST=api-gateway",
        f"API_GATEWAY_PORT={API_GATEWAY_PORT}",
        f"API_GATEWAY_URL=http://api-gateway:{API_GATEWAY_PORT}",
        "AUTH_SERVICE_HOST=lucid-auth-service",
        "AUTH_SERVICE_PORT=8089",
        "BLOCKCHAIN_ENGINE_HOST=blockchain-engine",
        "BLOCKCHAIN_ENGINE_PORT=8084",
        "BLOCK_MANAGER_HOST=block-manager",
        "BLOCK_MANAGER_PORT=8086",
        "SESSION_API_HOST=session-api",
        "SESSION_API_PORT=8113",
        "GUI_API_BRIDGE_HOST=gui-api-bridge",
        f"GUI_API_BRIDGE_PORT={GUI_BRIDGE_PORT}",
        "",
        "# Master server FastAPI — Tor-only (bind localhost; HS forwards *.onion)",
        "MASTER_SERVER_TOR_ONLY=true",
        "MASTER_SERVER_BIND_HOST=127.0.0.1",
        "MASTER_SERVER_HOST=127.0.0.1",
        f"MASTER_SERVER_PORT={MASTER_SERVER_PORT}",
        "MASTER_SERVER_SERVICE_NAME=lucid-server-default",
        "MASTER_SERVER_HEALTH_PATH=/health",
        f"MASTER_SERVER_HEALTH_URL=http://127.0.0.1:{MASTER_SERVER_PORT}/health",
        "MASTER_SERVER_PUBLIC_URL=http://${MASTER_SERVER_ONION}",
        "API_PUBLIC_BASE_URL=http://${MASTER_SERVER_ONION}/api/v1",
        "GUI_PUBLIC_BASE_URL=http://${MASTER_SERVER_ONION}/gui",
        "# Internal Docker DNS (container mesh only — not public API surface)",
        f"MASTER_SERVER_INTERNAL_URL=http://lucid-server-default:{MASTER_SERVER_PORT}",
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
        "SERVER_ENV_FILE=" + SERVER_ENV_PATH.as_posix(),
        "SECRETS_ENV_FILE=" + SECRETS_ENV_PATH.as_posix(),
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


def _build_secrets_env(generated: dict[str, str]) -> str:
    lines = [
        "# =============================================================================",
        "# LucidTops master server - secrets.env (NEVER commit to version control)",
        f"# Generated: {utc_now()}",
        "# Mount into containers as configs/.env.secrets (Dockerfile-layout.txt step 11)",
        "# =============================================================================",
        "",
        f"MONGODB_HOST={MONGODB_HOST}",
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


def _build_torrc() -> str:
    return "\n".join(
        [
            "# LucidTops master torrc - generated by backend/builderMasterServer.py",
            f"# Host mount: {TORRC_PATH.as_posix()} -> container /app/var/lib/tor/torrc",
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
            f"HiddenServicePort 80 127.0.0.1:{MASTER_SERVER_PORT}",
            "",
            "# Frontend GUI hidden service",
            "HiddenServiceDir /app/var/lib/tor/lucid_portal",
            "HiddenServiceVersion 3",
            f"HiddenServicePort 80 127.0.0.1:{GUI_BRIDGE_PORT}",
            "",
            "# NodeUser hidden service",
            "HiddenServiceDir /app/var/lib/tor/lucid_node",
            "HiddenServiceVersion 3",
            f"HiddenServicePort 80 127.0.0.1:{MASTER_SERVER_PORT}",
            "",
        ]
    )



def _create_master_database(client: Any, generated: dict[str, str]) -> dict[str, Any]:
    db = client[MASTER_DB_NAME]

    collections: dict[str, dict[str, Any]] = {
        "master_credentials": schema_template(MASTER_CREDENTIALS_FIELDS),
        "users": schema_template(USER_SCHEMA_FIELDS),
        "node_users": schema_template(NODE_USER_SCHEMA_FIELDS),
        "admin_users": schema_template(ADMIN_USER_SCHEMA_FIELDS),
        "master_class_users": schema_template(MASTER_CLASS_USER_SCHEMA_FIELDS),
        "node_hosted_databases": schema_template(NODE_DB_SCHEMA_FIELDS),
        "ledger_records": {
            "ledger_id": None,
            "block_hash": None,
            "previous_hash": None,
            "record_payload": None,
            "created_at": None,
        },
        "blockchain_blocks": {
            "block_id": None,
            "ledger_record_id": None,
            "merkle_root": None,
            "created_at": None,
        },
    }

    for collection_name, template in collections.items():
        col = db[collection_name]
        col.create_index("_id")
        if collection_name == "users":
            col.create_index("UserID", unique=True, sparse=True)
            col.create_index("email", unique=True, sparse=True)
        if collection_name == "node_users":
            col.create_index("NodeUserID", unique=True, sparse=True)
        if collection_name == "admin_users":
            col.create_index("adminUserID", unique=True, sparse=True)
        if collection_name == "master_class_users":
            col.create_index("MasterClassUserID", unique=True, sparse=True)
        if not col.find_one({"_schema_template": True}):
            col.insert_one(
                {
                    "_schema_template": True,
                    "fields": list(template.keys()),
                    "admin_only": True,
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
) -> None:
    manifest = {
        "generated_at": utc_now(),
        "root_dir": ROOT_DIR.as_posix(),
        "secrets_dir": SECRETS_DIR.as_posix(),
        "files": {
            "server_env": SERVER_ENV_PATH.as_posix(),
            "secrets_env": SECRETS_ENV_PATH.as_posix(),
            "torrc": TORRC_PATH.as_posix(),
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
        },
        "api_key_fingerprint": generated["API_KEY"][:8],
    }
    BUILD_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_master_server() -> dict[str, Any]:
    """Run all 20 builder steps and write container-compatible host config files."""
    _ensure_directories()
    generated = _build_generated_secrets()

    server_env = _build_server_env(generated)
    secrets_env = _build_secrets_env(generated)
    torrc = _build_torrc()

    SERVER_ENV_PATH.write_text(server_env, encoding="utf-8")
    SECRETS_ENV_PATH.write_text(secrets_env, encoding="utf-8")
    TORRC_PATH.write_text(torrc, encoding="utf-8")

    (SECRETS_DIR / "api_key.txt").write_text(generated["API_KEY"], encoding="utf-8")
    (SECRETS_DIR / "api_secret.txt").write_text(generated["API_SECRET"], encoding="utf-8")

    db_result: dict[str, Any] | None = None
    connection_layers: list[dict[str, str]] | None = None
    client = get_mongo_client()
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

    _write_manifest(generated, db_result, connection_layers)

    return {
        "root_dir": ROOT_DIR.as_posix(),
        "server_env": SERVER_ENV_PATH.as_posix(),
        "secrets_env": SECRETS_ENV_PATH.as_posix(),
        "torrc": TORRC_PATH.as_posix(),
        "manifest": BUILD_MANIFEST_PATH.as_posix(),
        "database_initialized": db_result is not None,
        "fastapi_app_ready": app_ready,
        "steps_completed": 20,
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
