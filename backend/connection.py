"""Master server connection protocol — Tor-only (backend ↔ frontend via *.onion).

The master server API operates inside the Tor network at all times.
All connections require a validated v3 *.onion address; there is no clearnet path.

Protocol logic only — FastAPI routes live in ConnectionRoutes.py.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from config import (
    FRONTEND_ONION,
    MASTER_SERVER_BIND_HOST,
    MASTER_SERVER_ONION,
    MASTER_SERVER_PORT,
    MASTER_SERVER_TOR_ONLY,
    NODEUSER_ONION,
    TOR_CONTROL_PORT,
    TOR_HOST,
    TOR_SOCKS_HOST,
    TOR_SOCKS_PORT,
    get_api_public_base_url,
    get_gui_public_base_url,
    get_master_db,
    get_master_server_public_url,
    get_mongo_client,
    read_onion_from_hidden_service_dir,
    resolve_master_server_onion,
    utc_now,
)
from handshake import (
    get_allowed_ongoing_sources,
    validate_api_key,
    validate_api_key_format,
    validate_handshake_source,
)
from WebPageLink import resolve_web_page_link, validate_web_page_link

CONNECTION_PROTOCOL = "connection"
TRANSPORT_PROTOCOL = "tor-hidden-service"
TORRENT_LAYER_PROTOCOL = "torrent-over-tor"
ConnectionType = Literal["initial", "ongoing"]
ConnectionEntity = Literal["user", "node", "frontend", "master", "api"]

ONION_V3_PATTERN = re.compile(r"^[a-z2-7]{56}\.onion$", re.IGNORECASE)

CONNECTION_REQUIRED_FIELDS: tuple[str, ...] = (
    "api_key",
    "id_token",
    "source",
    "connection_type",
    "onion_address",
)

def get_ongoing_connection_sources() -> frozenset[str]:
    return get_allowed_ongoing_sources()

ENTITY_HIDDEN_SERVICE_KEY: dict[str, str] = {
    "user": "frontend",
    "frontend": "frontend",
    "node": "node_user",
    "master": "master_server",
    "api": "master_server",
}

__all__ = (
    "CONNECTION_PROTOCOL",
    "TRANSPORT_PROTOCOL",
    "TORRENT_LAYER_PROTOCOL",
    "ConnectionType",
    "ConnectionEntity",
    "CONNECTION_REQUIRED_FIELDS",
    "MASTER_SERVER_TOR_ONLY",
    "validate_onion_address",
    "normalize_onion_address",
    "resolve_onion_for_entity",
    "get_tor_connection_config",
    "validate_tor_endpoint",
    "validate_id_token",
    "validate_connection_source",
    "confirm_handshake_successful",
    "establish_connection",
    "get_connection_status",
)


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def normalize_onion_address(onion: str) -> str:
    value = onion.strip().lower()
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value.split("/")[0]


def validate_onion_address(onion: str) -> bool:
    if not onion:
        return False
    return ONION_V3_PATTERN.fullmatch(normalize_onion_address(onion)) is not None


def resolve_onion_for_entity(entity: str) -> str | None:
    """Resolve expected *.onion for user, node, frontend, or master-server API."""
    env_map = {
        "user": FRONTEND_ONION,
        "frontend": FRONTEND_ONION,
        "node": NODEUSER_ONION,
        "master": MASTER_SERVER_ONION,
        "api": MASTER_SERVER_ONION,
    }
    entity_key = entity if entity in env_map else "master"
    configured = env_map.get(entity_key, "")
    if configured and validate_onion_address(configured):
        return normalize_onion_address(configured)

    if entity_key in {"master", "api"}:
        return resolve_master_server_onion()

    service_key = ENTITY_HIDDEN_SERVICE_KEY.get(entity_key, "frontend")
    return read_onion_from_hidden_service_dir(service_key)


def get_tor_connection_config() -> dict[str, Any]:
    master_onion = resolve_master_server_onion()
    return {
        "protocol": CONNECTION_PROTOCOL,
        "transport": TRANSPORT_PROTOCOL,
        "torrent_layer": TORRENT_LAYER_PROTOCOL,
        "network": "tor",
        "tor_only": MASTER_SERVER_TOR_ONLY,
        "tor_host": TOR_HOST,
        "tor_socks_host": TOR_SOCKS_HOST,
        "tor_socks_port": TOR_SOCKS_PORT,
        "tor_control_port": TOR_CONTROL_PORT,
        "master_server_onion": master_onion,
        "master_server_tor_service": get_master_server_public_url(),
        "tor_api_service": get_api_public_base_url(),
        "tor_gui_service": get_gui_public_base_url(),
        "frontend_onion": resolve_onion_for_entity("frontend"),
        "node_onion": resolve_onion_for_entity("node"),
        "master_server_port": MASTER_SERVER_PORT,
        "hidden_service_port": 80,
        "internal_bind_host": MASTER_SERVER_BIND_HOST,
    }


def validate_tor_endpoint(onion_address: str, *, entity: str = "master") -> bool:
    if not validate_onion_address(onion_address):
        return False

    normalized = normalize_onion_address(onion_address)
    expected = resolve_onion_for_entity(entity)
    if expected:
        return normalized == expected
    return True


def validate_id_token(id_token: str, *, entity: str, client: Any | None = None) -> bool:
    if not id_token or not id_token.strip():
        return False

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return False

    try:
        db = get_master_db(mongo)
        if entity == "node":
            record = db.id_tokens.find_one({"entity": "node", "IDToken": id_token.strip()})
        else:
            record = db.id_tokens.find_one({"entity": "user", "IDToken": id_token.strip()})
        return record is not None
    finally:
        if client is None:
            mongo.close()


def validate_connection_source(source: str, connection_type: ConnectionType) -> bool:
    normalized = _normalize_source(source)
    if connection_type == "initial":
        return bool(normalized)
    if normalized not in get_ongoing_connection_sources():
        return False
    return validate_web_page_link(normalized)  # pyright: ignore[reportUndefinedVariable]


def confirm_handshake_successful(
    *,
    api_key: str,
    source: str,
    connection_type: ConnectionType,
    client: Any | None = None,
) -> bool:
    if not validate_api_key_format(api_key):
        return False
    if not validate_api_key(api_key, client=client):
        return False
    if not validate_handshake_source(source, connection_type):
        return False
    if not validate_connection_source(source, connection_type):
        return False
    return True


def _resolve_required_onion(onion_address: str | None, entity: str) -> str:
    if onion_address and validate_onion_address(onion_address):
        normalized = normalize_onion_address(onion_address)
    else:
        normalized = resolve_onion_for_entity(entity)
        if not normalized:
            raise ValueError(
                "onion_address is required; master server *.onion not configured yet "
                "(run LaunchServer.py after Tor daemon starts)"
            )

    if not validate_tor_endpoint(normalized, entity=entity):
        raise PermissionError("Selected *.onion address is not valid or secure for this entity")
    return normalized


def establish_connection(
    *,
    api_key: str,
    id_token: str,
    source: str,
    connection_type: ConnectionType = "initial",
    entity: str = "master",
    onion_address: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run full Tor-only connection protocol and return session metadata."""
    normalized_onion = _resolve_required_onion(onion_address, entity)

    missing = [
        field
        for field in CONNECTION_REQUIRED_FIELDS
        if not (
            api_key
            if field == "api_key"
            else id_token
            if field == "id_token"
            else source
            if field == "source"
            else connection_type
            if field == "connection_type"
            else normalized_onion
            if field == "onion_address"
            else False
        )
    ]
    if missing:
        raise ValueError(f"Missing required connection fields: {', '.join(missing)}")

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        if not confirm_handshake_successful(
            api_key=api_key,
            source=source,
            connection_type=connection_type,
            client=mongo,
        ):
            raise PermissionError("Handshake validation failed")

        if not validate_id_token(id_token, entity=entity, client=mongo):
            raise PermissionError("IDToken validation failed")

        db = get_master_db(mongo)
        session_key = hashlib.sha256(
            f"{api_key}:{id_token}:{source}:{normalized_onion}".encode("utf-8")
        ).hexdigest()

        tor_config = get_tor_connection_config()
        normalized_source = _normalize_source(source)
        page_link = resolve_web_page_link(normalized_source)
        record = {
            "session_key": session_key,
            "protocol": CONNECTION_PROTOCOL,
            "transport": TRANSPORT_PROTOCOL,
            "torrent_layer": TORRENT_LAYER_PROTOCOL,
            "network": "tor",
            "tor_only": True,
            "source": normalized_source,
            "frontend": page_link.get("frontend"),
            "javascript": page_link.get("javascript"),
            "connection_type": connection_type,
            "entity": entity,
            "onion_address": normalized_onion,
            "tor_api_service": tor_config["tor_api_service"],
            "tor_api_route": page_link.get("tor_api_route"),
            "tor_socks_host": TOR_SOCKS_HOST,
            "tor_socks_port": TOR_SOCKS_PORT,
            "active": True,
            "updated_at": utc_now(),
        }
        db.master_connection.update_one(
            {"session_key": session_key},
            {"$set": record, "$setOnInsert": {"created_at": utc_now()}},
            upsert=True,
        )

        token_entity = "node" if entity == "node" else "user"
        token_record = db.id_tokens.find_one(
            {"entity": token_entity, "IDToken": id_token.strip()}
        )
        if not token_record:
            raise PermissionError("IDToken not found after validation")

        return {
            "protocol": CONNECTION_PROTOCOL,
            "transport": TRANSPORT_PROTOCOL,
            "torrent_layer": TORRENT_LAYER_PROTOCOL,
            "network": "tor",
            "tor_only": True,
            "status": "connected",
            "session_key": session_key,
            "IDToken": id_token.strip(),
            "entity": entity,
            "source": normalized_source,
            "frontend": page_link.get("frontend"),
            "javascript": page_link.get("javascript"),
            "connection_type": connection_type,
            "onion_address": normalized_onion,
            "tor_api_service": tor_config["tor_api_service"],
            "tor_api_route": page_link.get("tor_api_route"),
            "tor_gui_route": page_link.get("tor_gui_route"),
            "persistent": True,
            "tor": tor_config,
        }
    finally:
        if client is None:
            mongo.close()


def get_connection_status(session_key: str, *, client: Any | None = None) -> dict[str, Any]:
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        record = get_master_db(mongo).master_connection.find_one({"session_key": session_key})
        if not record:
            raise ValueError("Connection session not found")
        return {
            "session_key": session_key,
            "status": "connected" if record.get("active") else "inactive",
            "protocol": record.get("protocol"),
            "transport": record.get("transport"),
            "network": "tor",
            "tor_only": True,
            "onion_address": record.get("onion_address"),
            "tor_api_service": record.get("tor_api_service") or record.get("api_public_base_url"),
            "tor_api_route": record.get("tor_api_route"),
            "frontend": record.get("frontend"),
            "javascript": record.get("javascript"),
            "source": record.get("source"),
            "entity": record.get("entity"),
            "updated_at": record.get("updated_at"),
        }
    finally:
        if client is None:
            mongo.close()
