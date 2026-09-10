"""Tor-only runtime settings and URL helpers for the master server API.
requrements:
- all code will be configurable from outside the container (via the DockerfileDNS) and stored on the Host Machine (hardward using a configurable Path)
- no place holder values, all values are created at time of operation.
- no hardcoded values, all values are created at time of operation.
- all code will be compatible with the MasterServer (uvicorn server and FastAPI system)
- all code will be compatible with all containers in the DockerDNS system (LucidTops system)

includes:
- all the configurational content required to build the MasterServer[server.Dockerfile] (DockerDNS compatible)
- all the connection content required to build the MasterServer[server.Dockerfile] (DockerDNS compatible)

operational requirements:
- compatible with the MasterServer (uvicorn server and FastAPI system)
- compatible with all containers in the DockerDNS system (LucidTops system)
- compatible with the Tor Hidden Service and Docker Network
- compatible with MongoDB 7.0.0 or higher
- compatible with nginx reverse proxy system
- compatible with the MasterServer (uvicorn server and FastAPI system)
- Code will be operational via Tor Hidden Service and Docker Network

"""

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

DEFAULT_CONFIG_SECRETS_NAME = "config.secrets"

_RUNTIME_ATTRS = frozenset(
    {
        "MASTER_DB_NAME",
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_URL",
        "MASTER_SERVER_TOR_ONLY",
        "MASTER_SERVER_BIND_HOST",
        "MASTER_SERVER_HOST",
        "MASTER_SERVER_PORT",
        "MASTER_SERVER_ID",
        "API_PREFIX",
        "GUI_PREFIX",
        "CONTAINER_ONION_DIR",
        "TOR_HIDDEN_SERVICE_DIRS",
        "TOR_HOST",
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "TOR_CONTROL_PORT",
        "MASTER_SERVER_ONION",
        "FRONTEND_ONION",
        "NODEUSER_ONION",
        "CLIENT_REQUEST_TOR_SERVICE",
        "TOR_ROUTES_MANIFEST",
        "NODE_MIN_MEMORY_GB",
        "CHUNK_SIZE_BYTES",
        "PROXY_GATE_HEADER_VALUE",
        "PROXY_NGINX_UPSTREAM_TOKEN",
        "MONGODB_VIA_SOCKS5",
    }
)

_runtime_loaded = False
_paths_bound = False


def require_env(key: str) -> str:
    """Return a required environment value or raise RuntimeError."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable {key} is missing")
    return value


def optional_env(key: str) -> str:
    """Return an optional environment value (empty string when unset)."""
    return os.environ.get(key, "").strip()


def require_env_int(key: str) -> int:
    raw = require_env(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"environment variable {key} must be an integer") from exc


def require_env_path(key: str) -> Path:
    return Path(require_env(key)).expanduser()


def _ensure_paths_from_hardware_pull() -> None:
    """Bind path env from live hardware pull when missing (time of operation)."""
    global _paths_bound
    if _paths_bound:
        return
    needed = ("LUCID_TOPS_ROOT", "SECRETS_DIR", "SERVER_ENV_FILE", "SECRETS_ENV_FILE")
    if all(optional_env(key) for key in needed):
        _paths_bound = True
        return
    from pull_information import bind_operation_environ, pull_realworld_information

    bind_operation_environ(pull_realworld_information())
    _paths_bound = True


def _resolve_lucid_paths() -> tuple[Path, Path, Path, Path, Path, Path]:
    _ensure_paths_from_hardware_pull()
    lucid_tops_root = Path(require_env("LUCID_TOPS_ROOT")).expanduser()
    secrets_dir = Path(require_env("SECRETS_DIR")).expanduser()
    server_env_path = Path(require_env("SERVER_ENV_FILE")).expanduser()
    secrets_env_path = Path(require_env("SECRETS_ENV_FILE")).expanduser()
    config_override = optional_env("CONFIG_SECRETS_FILE")
    config_secrets_file = Path(
        config_override if config_override else (secrets_dir / DEFAULT_CONFIG_SECRETS_NAME)
    ).expanduser()
    torrc_raw = optional_env("HOST_TOR_CONFIG_TORRC")
    if torrc_raw:
        torrc_path = Path(torrc_raw).expanduser()
    else:
        torrc_path = lucid_tops_root / "torrc"
    return (
        lucid_tops_root,
        secrets_dir,
        server_env_path,
        secrets_env_path,
        config_secrets_file,
        torrc_path,
    )


def _bind_module_paths() -> None:
    global LUCID_TOPS_ROOT, SECRETS_DIR, SERVER_ENV_PATH, SECRETS_ENV_PATH
    global CONFIG_SECRETS_FILE, TORRC_PATH
    (
        LUCID_TOPS_ROOT,
        SECRETS_DIR,
        SERVER_ENV_PATH,
        SECRETS_ENV_PATH,
        CONFIG_SECRETS_FILE,
        TORRC_PATH,
    ) = _resolve_lucid_paths()


_bind_module_paths()


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


def get_config_value(key: str) -> str:
    """Resolve a configurable value: os.environ, then config.secrets; raise if missing."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    secrets_value = load_config_secrets().get(key, "").strip()
    if secrets_value:
        return secrets_value
    raise RuntimeError(
        f"required configuration {key} is missing from environment and config.secrets"
    )


def get_config_value_optional(key: str) -> str:
    """Resolve an optional configurable value; empty string when unset."""
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    return load_config_secrets().get(key, "").strip()


def get_config_int(key: str) -> int:
    raw = get_config_value(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"configuration {key} must be an integer") from exc


def get_config_list(key: str) -> frozenset[str]:
    """Resolve a comma-separated list from config.secrets or os.environ; raise if missing."""
    raw = get_config_value(key)
    items = frozenset(item.strip() for item in raw.split(",") if item.strip())
    if not items:
        raise RuntimeError(f"required configuration list {key} is empty")
    return items


def get_local_tor_forward_hosts() -> frozenset[str]:
    return get_config_list("LOCAL_TOR_FORWARD_HOSTS")


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


def _load_runtime_settings() -> None:
    """Apply secrets then bind module-level runtime settings from env/secrets only."""
    global MASTER_DB_NAME, MONGODB_HOST, MONGODB_PORT, MONGODB_URL
    global MASTER_SERVER_TOR_ONLY, MASTER_SERVER_BIND_HOST, MASTER_SERVER_HOST
    global MASTER_SERVER_PORT, MASTER_SERVER_ID, API_PREFIX, GUI_PREFIX
    global CONTAINER_ONION_DIR, TOR_HIDDEN_SERVICE_DIRS
    global TOR_HOST, TOR_SOCKS_HOST, TOR_SOCKS_PORT, TOR_CONTROL_PORT
    global MASTER_SERVER_ONION, FRONTEND_ONION, NODEUSER_ONION
    global CLIENT_REQUEST_TOR_SERVICE, TOR_ROUTES_MANIFEST
    global NODE_MIN_MEMORY_GB, CHUNK_SIZE_BYTES
    global PROXY_GATE_HEADER_VALUE, PROXY_NGINX_UPSTREAM_TOKEN, MONGODB_VIA_SOCKS5
    global _runtime_loaded

    _ensure_paths_from_hardware_pull()
    _bind_module_paths()

    if CONFIG_SECRETS_FILE.exists():
        apply_secrets_file(CONFIG_SECRETS_FILE)

    from container_secrets import apply_all_container_secrets  # noqa: E402

    apply_all_container_secrets()
    load_config_secrets.cache_clear()

    MASTER_DB_NAME = get_config_value("MONGODB_MAIN_DATABASE_NAME")
    MONGODB_HOST = get_config_value("MONGODB_HOST")
    MONGODB_PORT = get_config_int("MONGODB_PORT")
    MONGODB_URL = get_config_value_optional("MONGODB_URL") or (
        f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{MASTER_DB_NAME}"
    )

    tor_only_raw = get_config_value("MASTER_SERVER_TOR_ONLY").lower()
    MASTER_SERVER_TOR_ONLY = tor_only_raw in {"1", "true", "yes"}
    MASTER_SERVER_BIND_HOST = get_config_value("MASTER_SERVER_BIND_HOST")
    MASTER_SERVER_HOST = get_config_value("MASTER_SERVER_HOST")
    MASTER_SERVER_PORT = get_config_int("MASTER_SERVER_PORT")
    MASTER_SERVER_ID = get_config_value_optional("MASTER_SERVER_ID")
    API_PREFIX = get_config_value("API_BASE_PATH")
    GUI_PREFIX = get_config_value("GUI_PREFIX")

    onion_dir_raw = get_config_value_optional("CONTAINER_ONION_DIR")
    CONTAINER_ONION_DIR = Path(onion_dir_raw).expanduser() if onion_dir_raw else Path()
    server_hs = get_config_value_optional("HOST_TOR_LUCID_SERVER_DIR")
    portal_hs = get_config_value_optional("HOST_TOR_LUCID_PORTAL_DIR")
    node_hs = get_config_value_optional("HOST_TOR_LUCID_DEV_DIR")
    TOR_HIDDEN_SERVICE_DIRS = {}
    if server_hs:
        TOR_HIDDEN_SERVICE_DIRS["master_server"] = Path(server_hs).expanduser()
    if portal_hs:
        TOR_HIDDEN_SERVICE_DIRS["frontend"] = Path(portal_hs).expanduser()
    if node_hs:
        TOR_HIDDEN_SERVICE_DIRS["node_user"] = Path(node_hs).expanduser()

    TOR_HOST = get_config_value_optional("TOR_HOST") or get_config_value_optional("TOR_SOCKS_HOST")
    TOR_SOCKS_HOST = get_config_value("TOR_SOCKS_HOST")
    TOR_SOCKS_PORT = get_config_int("TOR_SOCKS_PORT")
    control_raw = get_config_value_optional("TOR_CONTROL_PORT")
    TOR_CONTROL_PORT = int(control_raw) if control_raw else 0
    MASTER_SERVER_ONION = get_config_value_optional("MASTER_SERVER_ONION")
    FRONTEND_ONION = get_config_value_optional("FRONTEND_ONION")
    NODEUSER_ONION = get_config_value_optional("NODEUSER_ONION")
    CLIENT_REQUEST_TOR_SERVICE = get_config_value_optional("CLIENT_REQUEST_TOR_SERVICE")
    TOR_ROUTES_MANIFEST = get_config_value_optional("TOR_ROUTES_MANIFEST")

    NODE_MIN_MEMORY_GB = get_config_int("NODE_MIN_MEMORY_GB")
    CHUNK_SIZE_BYTES = get_config_int("SESSION_CHUNK_SIZE_BYTES")
    PROXY_GATE_HEADER_VALUE = get_config_value_optional("PROXY_GATE_HEADER_VALUE")
    PROXY_NGINX_UPSTREAM_TOKEN = get_config_value_optional("PROXY_NGINX_UPSTREAM_TOKEN")
    socks_flag = get_config_value_optional("MONGODB_VIA_SOCKS5").lower()
    MONGODB_VIA_SOCKS5 = socks_flag in {"1", "true", "yes"} or not socks_flag
    _runtime_loaded = True


def ensure_runtime_settings() -> None:
    if not _runtime_loaded:
        _load_runtime_settings()


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_ATTRS:
        ensure_runtime_settings()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def resolve_master_server_id() -> str:
    ensure_runtime_settings()
    value = (MASTER_SERVER_ID or "").strip()
    if not value:
        raise RuntimeError("MASTER_SERVER_ID missing from secrets — run builder at operation time")
    return value


def read_onion_from_hidden_service_dir(service_key: str) -> str | None:
    ensure_runtime_settings()
    hidden_dir = TOR_HIDDEN_SERVICE_DIRS.get(service_key)
    if hidden_dir is not None:
        hostname_file = hidden_dir / "hostname"
        try:
            value = hostname_file.read_text(encoding="utf-8").strip().lower()
            if value.endswith(".onion"):
                return value.split("/")[0]
        except OSError:
            pass

    if CONTAINER_ONION_DIR and CONTAINER_ONION_DIR.as_posix():
        container_file = CONTAINER_ONION_DIR / f"{service_key}.onion"
        try:
            value = container_file.read_text(encoding="utf-8").strip().lower()
            if value.endswith(".onion"):
                return value.split("/")[0]
        except OSError:
            pass
    return None


def resolve_master_server_onion() -> str | None:
    ensure_runtime_settings()
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
    ensure_runtime_settings()
    onion = resolve_master_server_onion()
    if onion:
        return format_tor_onion_service(onion, API_PREFIX)
    return API_PREFIX


def get_gui_public_base_url() -> str:
    ensure_runtime_settings()
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
    ensure_runtime_settings()
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
    ensure_runtime_settings()
    manifest_path = Path(TOR_ROUTES_MANIFEST) if TOR_ROUTES_MANIFEST else None
    if manifest_path is None or not manifest_path.exists():
        configs_name = get_config_value_optional("TOR_ROUTES_CONFIG_RELATIVE")
        if configs_name:
            default_path = LUCID_TOPS_ROOT / configs_name
            manifest_path = default_path if default_path.exists() else None
        else:
            manifest_path = None
    if manifest_path is None or not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _mongo_client_kwargs() -> dict[str, Any]:
    ensure_runtime_settings()
    kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 3000}
    if not MONGODB_VIA_SOCKS5:
        return kwargs
    socks_host = (TOR_SOCKS_HOST or "").strip()
    if not socks_host or not TOR_SOCKS_PORT:
        return kwargs
    kwargs["proxyHost"] = socks_host
    kwargs["proxyPort"] = int(TOR_SOCKS_PORT)
    socks_user = get_config_value_optional("TOR_SOCKS_USERNAME") or get_config_value_optional(
        "TOR_SOCKS_USER"
    )
    socks_pass = get_config_value_optional("TOR_SOCKS_PASSWORD")
    if socks_user:
        kwargs["proxyUsername"] = socks_user
    if socks_pass:
        kwargs["proxyPassword"] = socks_pass
    return kwargs


def get_mongo_client() -> Any | None:
    ensure_runtime_settings()
    if MongoClient is None:
        return None
    try:
        client = MongoClient(MONGODB_URL, **_mongo_client_kwargs())
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None
    except Exception:
        return None


def get_master_db(client: Any) -> Any:
    ensure_runtime_settings()
    return client[MASTER_DB_NAME]


def refresh_mongodb_settings_from_env() -> None:
    global MASTER_DB_NAME, MONGODB_HOST, MONGODB_PORT, MONGODB_URL
    ensure_runtime_settings()
    MASTER_DB_NAME = get_config_value("MONGODB_MAIN_DATABASE_NAME")
    MONGODB_HOST = get_config_value("MONGODB_HOST")
    MONGODB_PORT = get_config_int("MONGODB_PORT")
    MONGODB_URL = get_config_value_optional("MONGODB_URL") or (
        f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{MASTER_DB_NAME}"
    )
