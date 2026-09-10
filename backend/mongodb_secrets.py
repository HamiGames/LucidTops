"""Load MongoDB runtime configuration from mongodb.secrets (post-bootstrap injection)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import SECRETS_DIR, ensure_runtime_settings, require_env, utc_now

DEFAULT_MONGODB_SECRETS_NAME = "mongodb.secrets"
MONGODB_SECRETS_FILE_ENV = "MONGODB_SECRETS_FILE"

MONGODB_SECRETS_KEYS: tuple[str, ...] = (
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_MAIN_DATABASE_NAME",
    "MONGODB_URL",
    "MONGODB_SERVICE",
    "MONGODB_PASSWORD",
    "MONGODB_ADMIN_PASSWORD",
    "MONGODB_VERIFIED",
    "MONGODB_VERIFIED_AT",
    "MONGODB_COLLECTIONS",
    "LUCID_MONGODB_URL",
    "MONGODB_VIA_SOCKS5",
    "TOR_SOCKS_HOST",
    "TOR_SOCKS_PORT",
    "TOR_SOCKS_USERNAME",
    "TOR_SOCKS_PASSWORD",
    "MONGODB_DATA_MOUNT",
)


def mongodb_secrets_path() -> Path:
    override = os.environ.get(MONGODB_SECRETS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return SECRETS_DIR / DEFAULT_MONGODB_SECRETS_NAME


@lru_cache(maxsize=1)
def _load_mongodb_secrets_cached() -> dict[str, str]:
    values: dict[str, str] = {}
    path = mongodb_secrets_path()
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def load_mongodb_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_mongodb_secrets_cached.cache_clear()
    return _load_mongodb_secrets_cached()


def resolve_secret(key: str) -> str:
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    file_value = load_mongodb_secrets().get(key.upper(), "").strip()
    if file_value:
        return file_value
    raise RuntimeError(
        f"required MongoDB secret {key} is missing from environment and mongodb.secrets"
    )


def resolve_secret_optional(key: str) -> str:
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    return load_mongodb_secrets().get(key.upper(), "").strip()


def resolve_mongodb_host() -> str:
    return resolve_secret("MONGODB_HOST")


def resolve_mongodb_port() -> int:
    raw = resolve_secret("MONGODB_PORT")
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError("MONGODB_PORT must be an integer") from exc


def resolve_mongodb_url() -> str:
    return resolve_secret("MONGODB_URL")


def resolve_mongodb_service() -> str:
    return resolve_secret_optional("MONGODB_SERVICE")


def resolve_mongodb_verified() -> bool:
    return resolve_secret_optional("MONGODB_VERIFIED").lower() in {"1", "true", "yes"}


def mongodb_secrets_status() -> dict[str, Any]:
    path = mongodb_secrets_path()
    host = resolve_secret_optional("MONGODB_HOST")
    port_raw = resolve_secret_optional("MONGODB_PORT")
    port = int(port_raw) if port_raw.isdigit() else 0
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "mongodb_verified": resolve_mongodb_verified(),
        "mongodb_host": host,
        "mongodb_port": port,
        "mongodb_url_configured": bool(resolve_secret_optional("MONGODB_URL")),
        "mongodb_service": resolve_mongodb_service(),
    }


def _resolve_mongodb_service_name(launch_values: dict[str, Any]) -> str:
    configured = str(launch_values.get("mongodb_service", "")).strip()
    if configured:
        return configured
    for service in launch_values.get("enabled_services", ()):
        name = str(service).strip()
        if name and "mongodb" in name.lower():
            return name
    return require_env("MONGODB_SERVICE")


def verify_mongodb_creation(
    client: Any,
    *,
    launch_values: dict[str, Any],
    db_result: dict[str, Any] | None,
) -> dict[str, Any]:
    ensure_runtime_settings()
    from config import MASTER_DB_NAME

    host = str(launch_values["mongodb_host"])
    port = int(launch_values["mongodb_port"])
    database = MASTER_DB_NAME
    base = {
        "mongodb_host": host,
        "mongodb_port": port,
        "database": database,
    }

    try:
        ping = client.admin.command("ping")
        ping_ok = bool(ping.get("ok"))
    except Exception as exc:
        return {**base, "verified": False, "reason": str(exc), "ping_ok": False}

    if not ping_ok:
        return {**base, "verified": False, "reason": "MongoDB ping failed", "ping_ok": False}

    if not db_result:
        return {
            **base,
            "verified": False,
            "reason": "database bootstrap did not complete",
            "ping_ok": ping_ok,
        }

    db = client[database]
    bootstrap = db.master_credentials.find_one({"bootstrap": True})
    if bootstrap is None:
        return {
            **base,
            "verified": False,
            "reason": "master_credentials bootstrap record missing",
            "ping_ok": ping_ok,
        }

    expected_collections = set(db_result.get("collections") or [])
    existing_collections = set(db.list_collection_names())
    missing = sorted(expected_collections - existing_collections)
    if missing:
        return {
            **base,
            "verified": False,
            "reason": f"missing collections: {missing}",
            "ping_ok": ping_ok,
            "missing_collections": missing,
        }

    return {
        **base,
        "verified": True,
        "ping_ok": ping_ok,
        "collections": sorted(expected_collections),
        "mongodb_service": _resolve_mongodb_service_name(launch_values),
    }


def build_verified_mongodb_secrets(
    *,
    launch_values: dict[str, Any],
    generated: dict[str, str],
    verification: dict[str, Any],
) -> dict[str, str]:
    if not verification.get("verified"):
        raise ValueError("MongoDB verification failed; cannot build mongodb.secrets")

    host = str(verification["mongodb_host"])
    port = str(verification["mongodb_port"])
    database = str(verification["database"])
    service = str(verification.get("mongodb_service") or _resolve_mongodb_service_name(launch_values))
    collections = verification.get("collections") or []

    values: dict[str, str] = {
        "MONGODB_HOST": host,
        "MONGODB_PORT": port,
        "MONGODB_MAIN_DATABASE_NAME": database,
        "MONGODB_URL": f"mongodb://{host}:{port}/{database}",
        "LUCID_MONGODB_URL": f"mongodb://{host}:{port}",
        "MONGODB_VERIFIED": "true",
        "MONGODB_VERIFIED_AT": utc_now(),
        "MONGODB_COLLECTIONS": ",".join(collections),
    }
    if service:
        values["MONGODB_SERVICE"] = service

    for secret_key in ("MONGODB_PASSWORD", "MONGODB_ADMIN_PASSWORD"):
        secret_value = str(generated.get(secret_key, "")).strip()
        if secret_value:
            values[secret_key] = secret_value

    socks_host = os.environ.get("TOR_SOCKS_HOST", "").strip()
    socks_port = os.environ.get("TOR_SOCKS_PORT", "").strip()
    if socks_host and socks_port:
        values["TOR_SOCKS_HOST"] = socks_host
        values["TOR_SOCKS_PORT"] = socks_port
        values["MONGODB_VIA_SOCKS5"] = os.environ.get("MONGODB_VIA_SOCKS5", "true").strip() or "true"
    socks_user = os.environ.get("TOR_SOCKS_USERNAME", "").strip() or os.environ.get(
        "TOR_SOCKS_USER", ""
    ).strip()
    socks_pass = os.environ.get("TOR_SOCKS_PASSWORD", "").strip() or str(
        generated.get("TOR_SOCKS_PASSWORD", "")
    ).strip()
    if socks_user:
        values["TOR_SOCKS_USERNAME"] = socks_user
    if socks_pass:
        values["TOR_SOCKS_PASSWORD"] = socks_pass
    data_mount = os.environ.get("MONGODB_DATA_MOUNT", "").strip() or str(
        launch_values.get("databases_dir", "")
    ).strip()
    if data_mount:
        values["MONGODB_DATA_MOUNT"] = data_mount

    return values


def write_mongodb_secrets_verified(
    secrets_dir: Path,
    *,
    launch_values: dict[str, Any],
    generated: dict[str, str],
    verification: dict[str, Any],
) -> Path:
    values = build_verified_mongodb_secrets(
        launch_values=launch_values,
        generated=generated,
        verification=verification,
    )
    secrets_dir.mkdir(parents=True, exist_ok=True)
    path = secrets_dir / DEFAULT_MONGODB_SECRETS_NAME

    lines = [
        "# LucidTops mongodb.secrets - written after verified MongoDB bootstrap",
        f"# Generated: {utc_now()}",
        "",
    ]
    for key in MONGODB_SECRETS_KEYS:
        value = values.get(key, "").strip()
        if value:
            lines.append(f"{key}={value}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    load_mongodb_secrets(reload=True)
    return path
