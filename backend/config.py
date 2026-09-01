"""Tor-only runtime settings and URL helpers for the master server API."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:  # pragma: no cover
    MongoClient = None  # type: ignore[misc, assignment]
    PyMongoError = Exception  # type: ignore[misc, assignment]

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

DEFAULT_LUCID_TOPS_ROOT = Path("/mnt/myssd/LucidTops")
LUCID_TOPS_ROOT = Path(os.environ.get("LUCID_TOPS_ROOT", DEFAULT_LUCID_TOPS_ROOT)).expanduser()
SECRETS_DIR = Path(os.environ.get("SECRETS_DIR", LUCID_TOPS_ROOT / "secrets"))
SERVER_ENV_PATH = Path(os.environ.get("SERVER_ENV_FILE", LUCID_TOPS_ROOT / "server.env"))
SECRETS_ENV_PATH = Path(os.environ.get("SECRETS_ENV_FILE", LUCID_TOPS_ROOT / "secrets.env"))
TORRC_PATH = Path(os.environ.get("HOST_TOR_CONFIG_TORRC", LUCID_TOPS_ROOT / "torrc"))

MASTER_DB_NAME = os.environ.get("MONGODB_MAIN_DATABASE_NAME", "lucid_master")
MONGODB_HOST = os.environ.get("MONGODB_HOST", "lucid-mongodb")
MONGODB_PORT = int(os.environ.get("MONGODB_PORT", "27017"))
MONGODB_URL = os.environ.get(
    "MONGODB_URL",
    f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{MASTER_DB_NAME}",
)

# Master server listens on localhost; Tor hidden service forwards *.onion -> 127.0.0.1:PORT
MASTER_SERVER_TOR_ONLY = os.environ.get("MASTER_SERVER_TOR_ONLY", "true").lower() in {
    "1",
    "true",
    "yes",
}
MASTER_SERVER_BIND_HOST = os.environ.get(
    "MASTER_SERVER_BIND_HOST",
    "127.0.0.1" if MASTER_SERVER_TOR_ONLY else "0.0.0.0",
)
MASTER_SERVER_HOST = os.environ.get("MASTER_SERVER_HOST", MASTER_SERVER_BIND_HOST)
MASTER_SERVER_PORT = int(os.environ.get("MASTER_SERVER_PORT", "8080"))
API_PREFIX = os.environ.get("API_BASE_PATH", "/api/v1")
GUI_PREFIX = os.environ.get("GUI_PREFIX", "/gui")

CONTAINER_ONION_DIR = Path(
    os.environ.get("CONTAINER_ONION_DIR", "/app/run/lucid/onion")
)
TOR_HIDDEN_SERVICE_DIRS = {
    "master_server": Path(
        os.environ.get("HOST_TOR_LUCID_SERVER_DIR", "/app/var/lib/tor/lucid_server")
    ),
    "frontend": Path(
        os.environ.get("HOST_TOR_LUCID_PORTAL_DIR", "/app/var/lib/tor/lucid_portal")
    ),
    "node_user": Path(
        os.environ.get("HOST_TOR_LUCID_DEV_DIR", "/app/var/lib/tor/lucid_node")
    ),
}

TOR_HOST = os.environ.get("TOR_HOST", "127.0.0.1")
TOR_SOCKS_HOST = os.environ.get("TOR_SOCKS_HOST", TOR_HOST)
TOR_SOCKS_PORT = int(os.environ.get("TOR_SOCKS_PORT", "9050"))
TOR_CONTROL_PORT = int(os.environ.get("TOR_CONTROL_PORT", "9051"))
MASTER_SERVER_ONION = os.environ.get("MASTER_SERVER_ONION", "").strip()
FRONTEND_ONION = os.environ.get("FRONTEND_ONION", "").strip()
NODEUSER_ONION = os.environ.get("NODEUSER_ONION", "").strip()

NODE_MIN_MEMORY_GB = int(os.environ.get("NODE_MIN_MEMORY_GB", "50"))
CHUNK_SIZE_BYTES = int(os.environ.get("SESSION_CHUNK_SIZE_BYTES", "1048576"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_secret_file(name: str) -> str | None:
    path = SECRETS_DIR / name
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def get_env_secret(key: str, *, filename: str | None = None) -> str | None:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    if filename:
        return read_secret_file(filename)
    return None


def read_onion_from_hidden_service_dir(service_key: str) -> str | None:
    hidden_dir = TOR_HIDDEN_SERVICE_DIRS.get(service_key)
    if hidden_dir is not None:
        hostname_file = hidden_dir / "hostname"
        try:
            value = hostname_file.read_text(encoding="utf-8").strip().lower()
            if value.endswith(".onion"):
                return value.split("/")[0]
        except OSError:
            pass

    container_file = CONTAINER_ONION_DIR / f"{service_key}.onion"
    try:
        value = container_file.read_text(encoding="utf-8").strip().lower()
        if value.endswith(".onion"):
            return value.split("/")[0]
    except OSError:
        pass
    return None


def resolve_master_server_onion() -> str | None:
    if MASTER_SERVER_ONION:
        return MASTER_SERVER_ONION.lower()
    return read_onion_from_hidden_service_dir("master_server")


def format_tor_onion_service(onion: str, path: str = "") -> str:
    """Tor hidden service reference (*.onion + path). Not clearnet."""
    host = onion.strip().lower().split("/")[0]
    if not path:
        return host
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{host}{normalized}"


def get_api_public_base_url() -> str:
    onion = resolve_master_server_onion()
    if onion:
        return format_tor_onion_service(onion, API_PREFIX)
    return API_PREFIX


def get_gui_public_base_url() -> str:
    onion = resolve_master_server_onion()
    if onion:
        return format_tor_onion_service(onion, GUI_PREFIX)
    return GUI_PREFIX


def get_master_server_public_url() -> str:
    onion = resolve_master_server_onion()
    if onion:
        return format_tor_onion_service(onion)
    return ""


def get_tor_api_service() -> str:
    return get_api_public_base_url()


def get_tor_gui_service() -> str:
    return get_gui_public_base_url()


def get_master_server_tor_service() -> str:
    return get_master_server_public_url()


def get_mongo_client() -> Any | None:
    if MongoClient is None:
        return None
    try:
        client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None


def get_master_db(client: Any) -> Any:
    return client[MASTER_DB_NAME]
