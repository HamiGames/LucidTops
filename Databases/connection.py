"""Resolve MongoDB clients for LucidTops named Databases from secrets at operation time.

Tor-zone DBs: MasterServer on tor DB network uses DockerDNS hostnames directly.
ClearNet operators may require SOCKS5 settings from mongodb.secrets
(MONGODB_VIA_SOCKS5, TOR_SOCKS_*).

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote_plus

from Dns_databases import ALL_NAMED_DB_CONTAINERS, zone_for, secret_key_prefix
from databases_secrets import (
    get_secret,
    load_databases_secrets,
    parse_secrets_file,
    mongodb_secrets_path,
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _mongo_secrets() -> dict[str, str]:
    path = mongodb_secrets_path()
    if path.exists():
        return parse_secrets_file(path)
    return {}


def resolve_db_host(db_name: str, *, prefer_host_publish: bool = False) -> str:
    prefix = secret_key_prefix(db_name)
    if prefer_host_publish:
        primary = get_secret("HOST_PRIMARY_IP") or _env("HOST_PRIMARY_IP")
        if primary:
            return primary
    host = get_secret(f"{prefix}_HOST")
    if host:
        return host
    raise RuntimeError(
        f"{prefix}_HOST missing — create databases.secrets at time of operation"
    )


def resolve_db_port(db_name: str, *, prefer_host_publish: bool = False) -> int:
    prefix = secret_key_prefix(db_name)
    if prefer_host_publish:
        host_port = get_secret(f"{prefix}_HOST_PORT")
        if host_port:
            return int(host_port)
    port = get_secret(f"{prefix}_PORT")
    if not port:
        raise RuntimeError(
            f"{prefix}_PORT missing — create databases.secrets at time of operation"
        )
    return int(port)


def resolve_db_url(db_name: str, *, prefer_host_publish: bool = False) -> str:
    prefix = secret_key_prefix(db_name)
    if not prefer_host_publish:
        url = get_secret(f"{prefix}_URL")
        if url:
            return url
    host = resolve_db_host(db_name, prefer_host_publish=prefer_host_publish)
    port = resolve_db_port(db_name, prefer_host_publish=prefer_host_publish)
    return f"mongodb://{host}:{port}"


def _auth_uri(base_url: str) -> str:
    user = get_secret("MONGODB_ADMIN_USER")
    password = get_secret("MONGODB_ADMIN_PASSWORD")
    if not user or not password:
        return base_url
    if "://" not in base_url:
        raise RuntimeError(f"invalid mongodb url {base_url!r}")
    scheme, rest = base_url.split("://", 1)
    if "@" in rest.split("/")[0]:
        uri = base_url
    else:
        cred = f"{quote_plus(user)}:{quote_plus(password)}@"
        uri = f"{scheme}://{cred}{rest}"
    if "authSource=" in uri:
        return uri
    sep = "&" if "?" in uri else "?"
    return f"{uri}{sep}authSource=admin"


def _socks_kwargs() -> dict[str, Any]:
    mongo = _mongo_secrets()
    via = (
        _env("MONGODB_VIA_SOCKS5")
        or mongo.get("MONGODB_VIA_SOCKS5", "")
        or get_secret("MONGODB_VIA_SOCKS5")
    ).lower()
    if via not in {"1", "true", "yes"}:
        return {}
    host = _env("TOR_SOCKS_HOST") or mongo.get("TOR_SOCKS_HOST", "")
    port_raw = _env("TOR_SOCKS_PORT") or mongo.get("TOR_SOCKS_PORT", "")
    if not host or not port_raw:
        raise RuntimeError(
            "MONGODB_VIA_SOCKS5 enabled but TOR_SOCKS_HOST/PORT missing at operation time"
        )
    kwargs: dict[str, Any] = {
        "proxyHost": host,
        "proxyPort": int(port_raw),
    }
    user = (
        _env("TOR_SOCKS_USERNAME")
        or _env("TOR_SOCKS_USER")
        or mongo.get("TOR_SOCKS_USERNAME", "")
    )
    password = _env("TOR_SOCKS_PASSWORD") or mongo.get("TOR_SOCKS_PASSWORD", "")
    if user:
        kwargs["proxyUsername"] = user
    if password:
        kwargs["proxyPassword"] = password
    return kwargs


def get_mongo_client(
    db_name: str,
    *,
    prefer_host_publish: bool = False,
    use_socks_for_tor_zone: bool = False,
) -> Any:
    """
    Return a pymongo MongoClient for the named database container.
    When use_socks_for_tor_zone and the DB is Tor-zoned, apply SOCKS5 from secrets.
    """
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("pymongo required — install Databases/requirements.txt") from exc

    load_databases_secrets(reload=False)
    base = resolve_db_url(db_name, prefer_host_publish=prefer_host_publish)
    uri = _auth_uri(base)

    client_kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 8000}
    if use_socks_for_tor_zone and zone_for(db_name) == "tor":
        socks = _socks_kwargs()
        if socks:
            # PyMongo SOCKS via PySocks when installed.
            client_kwargs.update(
                {
                    "proxyHost": socks["proxyHost"],
                    "proxyPort": socks["proxyPort"],
                }
            )
            if "proxyUsername" in socks:
                client_kwargs["proxyUsername"] = socks["proxyUsername"]
            if "proxyPassword" in socks:
                client_kwargs["proxyPassword"] = socks["proxyPassword"]

    return MongoClient(uri, **client_kwargs)


def get_database(
    db_name: str,
    *,
    prefer_host_publish: bool = False,
    use_socks_for_tor_zone: bool = False,
) -> Any:
    client = get_mongo_client(
        db_name,
        prefer_host_publish=prefer_host_publish,
        use_socks_for_tor_zone=use_socks_for_tor_zone,
    )
    return client[db_name]


def ping_database(db_name: str, **kwargs: Any) -> dict[str, Any]:
    client = get_mongo_client(db_name, **kwargs)
    try:
        result = client.admin.command("ping")
        return {
            "database": db_name,
            "ok": bool(result.get("ok")),
            "host": resolve_db_host(
                db_name, prefer_host_publish=bool(kwargs.get("prefer_host_publish"))
            ),
            "port": resolve_db_port(
                db_name, prefer_host_publish=bool(kwargs.get("prefer_host_publish"))
            ),
            "zone": zone_for(db_name),
        }
    finally:
        client.close()


def connection_status() -> dict[str, Any]:
    load_databases_secrets(reload=True)
    return {
        "databases": list(ALL_NAMED_DB_CONTAINERS),
        "hosts": {
            name: {
                "host": get_secret(f"{secret_key_prefix(name)}_HOST"),
                "port": get_secret(f"{secret_key_prefix(name)}_PORT"),
                "zone": get_secret(f"{secret_key_prefix(name)}_ZONE"),
            }
            for name in ALL_NAMED_DB_CONTAINERS
        },
        "mongodb_via_socks5": bool(get_secret("MONGODB_VIA_SOCKS5") or _env("MONGODB_VIA_SOCKS5")),
    }
