"""Tor-only runtime settings and URL helpers for the master server API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
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
DEFAULT_CONFIG_SECRETS_NAME = "config.secrets"
CONFIG_SECRETS_FILE = Path(
    os.environ.get("CONFIG_SECRETS_FILE", SECRETS_DIR / DEFAULT_CONFIG_SECRETS_NAME)
)
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
CLIENT_REQUEST_TOR_SERVICE = os.environ.get("CLIENT_REQUEST_TOR_SERVICE", "").strip()
TOR_ROUTES_MANIFEST = os.environ.get("TOR_ROUTES_MANIFEST", "").strip()

NODE_MIN_MEMORY_GB = int(os.environ.get("NODE_MIN_MEMORY_GB", "50"))
CHUNK_SIZE_BYTES = int(os.environ.get("SESSION_CHUNK_SIZE_BYTES", "1048576"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_secrets_file(path: Path) -> dict[str, str]:
    """Parse a *.secrets file (key=value lines, # comments) — same format as payments.secrets."""
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


def apply_secrets_file(path: Path, *, overwrite: bool = False) -> dict[str, str]:
    """Load a *.secrets file into os.environ (entrypoint may have done this already)."""
    loaded = parse_secrets_file(path)
    for key, value in loaded.items():
        if overwrite or not os.environ.get(key, "").strip():
            os.environ[key] = value
    return loaded


@lru_cache(maxsize=1)
def load_config_secrets() -> dict[str, str]:
    """Return parsed config.secrets; empty dict when file is absent."""
    if CONFIG_SECRETS_FILE.exists():
        return parse_secrets_file(CONFIG_SECRETS_FILE)
    return {}


def get_config_value(key: str, default: str = "") -> str:
    """Resolve a configurable value: os.environ, then config.secrets, then default."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    secrets_value = load_config_secrets().get(key, "").strip()
    if secrets_value:
        return secrets_value
    return default


def get_config_int(key: str, default: int) -> int:
    raw = get_config_value(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def get_config_list(key: str, default: frozenset[str] | tuple[str, ...] = ()) -> frozenset[str]:
    """Resolve a comma-separated list from config.secrets or os.environ."""
    raw = get_config_value(key, "")
    if not raw:
        return frozenset(default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


_DEFAULT_LOCAL_TOR_FORWARD_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def get_local_tor_forward_hosts() -> frozenset[str]:
    return get_config_list("LOCAL_TOR_FORWARD_HOSTS", _DEFAULT_LOCAL_TOR_FORWARD_HOSTS)


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


def get_client_request_tor_service() -> str:
    """Return ClientHandler Tor endpoint (http://<master-onion>/api/v1/client-request)."""
    if CLIENT_REQUEST_TOR_SERVICE:
        return CLIENT_REQUEST_TOR_SERVICE
    onion = resolve_master_server_onion()
    client_path = f"{API_PREFIX}/client-request"
    if onion:
        host = onion.strip().lower().split("/")[0]
        return f"http://{host}{client_path}"
    return client_path


def load_tor_routes_manifest() -> dict[str, Any]:
    """Load builder-generated tor-routes.json when available."""
    manifest_path = Path(TOR_ROUTES_MANIFEST) if TOR_ROUTES_MANIFEST else None
    if manifest_path is None or not manifest_path.exists():
        default_path = LUCID_TOPS_ROOT / "configs" / "tor-routes.json"
        manifest_path = default_path if default_path.exists() else None
    if manifest_path is None or not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


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


def refresh_mongodb_settings_from_env() -> None:
    global MASTER_DB_NAME, MONGODB_HOST, MONGODB_PORT, MONGODB_URL
    MASTER_DB_NAME = os.environ.get("MONGODB_MAIN_DATABASE_NAME", MASTER_DB_NAME)
    MONGODB_HOST = os.environ.get("MONGODB_HOST", MONGODB_HOST)
    MONGODB_PORT = int(os.environ.get("MONGODB_PORT", str(MONGODB_PORT)))
    MONGODB_URL = os.environ.get(
        "MONGODB_URL",
        f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{MASTER_DB_NAME}",
    )


from container_secrets import apply_all_container_secrets  # noqa: E402

if CONFIG_SECRETS_FILE.exists():
    apply_secrets_file(CONFIG_SECRETS_FILE)
apply_all_container_secrets()
refresh_mongodb_settings_from_env()
