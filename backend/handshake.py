"""The handshake protocol for connection to the server from the frontend.

handshake protocol:
- data fields must be present in the handshake request
- API key must be present in the handshake request
- API key must be valid
- API key must be in the correct format

limitations:
- the handshake protocol is only required for the initial connection to the server
- ongoing handshakes to server will not exist outside of user registration from the
  frontend/register.js file, node registration from the frontend/node-registration.js
  file, or user login from the frontend/login.js file, and the frontend/tier-select.js
  file
- the API key will generate a userID and a nodeID for the user and node respectively
  consisting of 8 characters each
- the successful handshake will return an IDToken for the user and node respectively
- the IDToken will be the proof of authentication for the user and node respectively
- all IDTokens will be stored on the Master server database

includes:
- the process of generating the API key
- the process of validating the API key
- the process of deriving the userID and nodeID from the API key
- the creation of the IDTokens
- the process of validating the handshake source
- the process of performing the handshake

- the process of storing the IDTokens in the Master server database

"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, Field, field_validator
except ImportError:  # pragma: no cover - importable without FastAPI during image build
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]
    field_validator = lambda *args, **kwargs: (lambda fn: fn)  # type: ignore[misc, assignment]

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:  # pragma: no cover
    MongoClient = None  # type: ignore[misc, assignment]
    PyMongoError = Exception  # type: ignore[misc, assignment]

HANDSHAKE_PROTOCOL = "handshake"
ID_LENGTH = int(os.environ.get("HANDSHAKE_ID_LENGTH", "8"))
ID_TOKEN_BYTES = int(os.environ.get("HANDSHAKE_ID_TOKEN_BYTES", "32"))

MASTER_DB_NAME = os.environ.get("MONGODB_MAIN_DATABASE_NAME", "lucid_master")
MONGODB_HOST = os.environ.get("MONGODB_HOST", "lucid-mongodb")
MONGODB_PORT = int(os.environ.get("MONGODB_PORT", "27017"))
ID_TOKENS_COLLECTION = os.environ.get("HANDSHAKE_ID_TOKENS_COLLECTION", "id_tokens")

API_KEY_MIN_LENGTH = int(os.environ.get("HANDSHAKE_API_KEY_MIN_LENGTH", "24"))
API_KEY_GENERATION_LENGTH = int(os.environ.get("HANDSHAKE_API_KEY_GENERATION_LENGTH", "24"))
API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

HANDSHAKE_REQUIRED_FIELDS: tuple[str, ...] = (
    "api_key",
    "source",
    "connection_type",
)

ALLOWED_ONGOING_SOURCES: frozenset[str] = frozenset(
    {
        "register.js",
        "node-registration.js",
        "login.js",
        "tier-select.js",
        "connect-handshake.js",
    }
)

ConnectionType = Literal["initial", "ongoing"]

__all__ = (
    "generate_api_key",
    "validate_api_key",
    "validate_api_key_format",
    "derive_user_and_node_ids",
    "create_id_tokens",
    "validate_handshake_source",
    "perform_handshake",
    "perform_connect_handshake",
    "store_id_tokens_in_master_database",
    "create_handshake_router",
    "register_handshake_routes",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- includes: the process of generating the API key ---


def generate_api_key(length: int = API_KEY_GENERATION_LENGTH) -> str:
    """Generate a URL-safe API key compatible with builderMasterServer.py secrets."""
    if length < API_KEY_MIN_LENGTH:
        raise ValueError(
            f"API key generation length must be at least {API_KEY_MIN_LENGTH} characters"
        )
    return secrets.token_urlsafe(length)


# --- includes: the process of validating the API key ---


def validate_api_key_format(api_key: str) -> bool:
    """Validate that an API key matches the required handshake format."""
    if not api_key or not isinstance(api_key, str):
        return False
    if len(api_key) < API_KEY_MIN_LENGTH:
        return False
    return API_KEY_PATTERN.fullmatch(api_key) is not None


def is_api_key_format_valid(api_key: str) -> bool:
    """Backward-compatible alias for validate_api_key_format."""
    return validate_api_key_format(api_key)


def _resolve_api_key() -> str | None:
    env_key = os.environ.get("API_KEY", "").strip()
    if env_key:
        return env_key

    secrets_file = os.environ.get("API_KEY_FILE", "").strip()
    if secrets_file:
        try:
            return Path(secrets_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    default_root = os.environ.get("LUCID_TOPS_ROOT", "/mnt/myssd/LucidTops")
    fallback = os.path.join(default_root, "secrets", "api_key.txt")
    try:
        return Path(fallback).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _mongo_client() -> Any | None:
    if MongoClient is None:
        return None

    uri = os.environ.get(
        "MONGODB_URL",
        f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}",
    )
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None


def _load_api_key_from_database(client: Any) -> str | None:
    try:
        record = client[MASTER_DB_NAME].master_credentials.find_one({"bootstrap": True})
    except PyMongoError:
        return None
    if not record:
        return None
    api_key = record.get("API_key")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def validate_api_key(api_key: str, *, client: Any | None = None) -> bool:
    """Validate an API key against configured secrets and the master database."""
    if not validate_api_key_format(api_key):
        return False

    expected = _resolve_api_key()
    if expected and secrets.compare_digest(api_key, expected):
        return True

    mongo = client if client is not None else _mongo_client()
    if mongo is None:
        return False

    try:
        db_key = _load_api_key_from_database(mongo)
    finally:
        if client is None:
            mongo.close()

    if not db_key:
        return False
    return secrets.compare_digest(api_key, db_key)


# --- includes: the process of deriving the userID and nodeID from the API key ---


def _derive_entity_id(api_key: str, entity: str, length: int = ID_LENGTH) -> str:
    digest = hashlib.sha256(f"{api_key}:{entity}".encode("utf-8")).digest()
    alphabet = string.digits + string.ascii_lowercase
    value = int.from_bytes(digest, "big")
    chars: list[str] = []
    for _ in range(length):
        value, index = divmod(value, len(alphabet))
        chars.append(alphabet[index])
    return "".join(chars)


def derive_user_and_node_ids(api_key: str) -> dict[str, str]:
    """Derive 8-character userID and nodeID values from a validated API key."""
    if not validate_api_key_format(api_key):
        raise ValueError("API key must be in the correct format before deriving IDs")
    return {
        "userID": _derive_entity_id(api_key, "user", ID_LENGTH),
        "nodeID": _derive_entity_id(api_key, "node", ID_LENGTH),
    }


# --- includes: the creation of the IDTokens ---


def create_id_tokens() -> tuple[str, str]:
    """Create proof-of-authentication IDTokens for the user and node."""
    return secrets.token_urlsafe(ID_TOKEN_BYTES), secrets.token_urlsafe(ID_TOKEN_BYTES)


# --- includes: the process of validating the handshake source ---


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def validate_handshake_source(source: str, connection_type: ConnectionType) -> bool:
    """Validate the frontend source file for initial or ongoing handshake requests."""
    normalized = _normalize_source(source)
    if connection_type == "initial":
        return bool(normalized)
    return normalized in ALLOWED_ONGOING_SOURCES


# --- includes: the process of storing the IDTokens in the Master server database ---


def _id_tokens_collection(client: Any) -> Any:
    return client[MASTER_DB_NAME][ID_TOKENS_COLLECTION]


def store_id_tokens_in_master_database(
    client: Any,
    *,
    user_id: str,
    node_id: str,
    user_id_token: str,
    node_id_token: str,
    api_key_fingerprint: str,
    source: str,
    connection_type: ConnectionType,
    session_id: str | None = None,
    digital_signature: str | None = None,
) -> None:
    """Persist user and node IDTokens on the master server database."""
    collection = _id_tokens_collection(client)
    now = _utc_now()
    base_record = {
        "api_key_fingerprint": api_key_fingerprint,
        "source": _normalize_source(source),
        "connection_type": connection_type,
        "updated_at": now,
    }
    if session_id:
        base_record["session_id"] = session_id
    if digital_signature:
        base_record["digital_signature"] = digital_signature

    collection.update_one(
        {"entity": "user", "UserID": user_id},
        {
            "$set": {
                **base_record,
                "entity": "user",
                "UserID": user_id,
                "IDToken": user_id_token,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    collection.update_one(
        {"entity": "node", "NodeUserID": node_id},
        {
            "$set": {
                **base_record,
                "entity": "node",
                "NodeUserID": node_id,
                "IDToken": node_id_token,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


# --- includes: the process of performing the handshake ---


def perform_handshake(
    *,
    api_key: str,
    source: str,
    connection_type: ConnectionType,
    client: Any | None = None,
) -> dict[str, str]:
    """Run the full handshake protocol and persist IDTokens on the master database."""
    missing = [
        field
        for field in HANDSHAKE_REQUIRED_FIELDS
        if not (api_key if field == "api_key" else source if field == "source" else connection_type)
    ]
    if missing:
        raise ValueError(f"Missing required handshake fields: {', '.join(missing)}")

    if not validate_api_key_format(api_key):
        raise ValueError("API key must be in the correct format")

    mongo = client if client is not None else _mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        if not validate_api_key(api_key, client=mongo):
            raise PermissionError("API key must be valid")

        if not validate_handshake_source(source, connection_type):
            raise PermissionError(
                "Handshake source is not permitted for ongoing connections"
            )

        ids = derive_user_and_node_ids(api_key)
        user_id = ids["userID"]
        node_id = ids["nodeID"]
        user_id_token, node_id_token = create_id_tokens()

        store_id_tokens_in_master_database(
            mongo,
            user_id=user_id,
            node_id=node_id,
            user_id_token=user_id_token,
            node_id_token=node_id_token,
            api_key_fingerprint=api_key[:8],
            source=source,
            connection_type=connection_type,
        )
    finally:
        if client is None:
            mongo.close()

    return {
        "protocol": HANDSHAKE_PROTOCOL,
        "userID": user_id,
        "nodeID": node_id,
        "user_IDToken": user_id_token,
        "node_IDToken": node_id_token,
        "connection_type": connection_type,
        "source": _normalize_source(source),
    }


def perform_connect_handshake(
    *,
    api_key: str,
    source: str,
    session_id: str,
    connection_type: ConnectionType = "ongoing",
    client: Any | None = None,
) -> dict[str, str]:
    """Create a connect-handshake digital signature for session authentication."""
    if not session_id or not session_id.strip():
        raise ValueError("session_id is required for connect-handshake")

    result = perform_handshake(
        api_key=api_key,
        source=source,
        connection_type=connection_type,
        client=client,
    )

    signature_payload = (
        f"{result['userID']}:{result['nodeID']}:{session_id.strip()}:"
        f"{result['user_IDToken']}:{result['node_IDToken']}"
    )
    digital_signature = hashlib.sha512(signature_payload.encode("utf-8")).hexdigest()

    mongo = client if client is not None else _mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        store_id_tokens_in_master_database(
            mongo,
            user_id=result["userID"],
            node_id=result["nodeID"],
            user_id_token=result["user_IDToken"],
            node_id_token=result["node_IDToken"],
            api_key_fingerprint=api_key[:8],
            source=source,
            connection_type=connection_type,
            session_id=session_id.strip(),
            digital_signature=digital_signature,
        )
    finally:
        if client is None:
            mongo.close()

    return {
        **result,
        "session_id": session_id.strip(),
        "digital_signature": digital_signature,
    }


if BaseModel is not object:

    class HandshakeRequest(BaseModel):
        api_key: str = Field(..., min_length=1)
        source: str = Field(..., min_length=1)
        connection_type: ConnectionType = "initial"

        @field_validator("api_key", "source")
        @classmethod
        def _strip_required_fields(cls, value: str) -> str:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("field must not be empty")
            return cleaned

    class ConnectHandshakeRequest(HandshakeRequest):
        session_id: str = Field(..., min_length=1)
        connection_type: ConnectionType = "ongoing"

        @field_validator("session_id")
        @classmethod
        def _strip_session_id(cls, value: str) -> str:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("session_id must not be empty")
            return cleaned


def create_handshake_router() -> Any:
    """Return a FastAPI router for handshake and connect-handshake endpoints."""
    if APIRouter is None or HTTPException is None:
        raise RuntimeError("fastapi is required to create handshake routes")

    router = APIRouter(tags=["handshake"])

    @router.post("/handshake")
    def handshake_endpoint(payload: HandshakeRequest) -> dict[str, str]:
        return _handle_handshake(payload)

    @router.post("/connect-handshake")
    def connect_handshake_endpoint(payload: ConnectHandshakeRequest) -> dict[str, str]:
        return _handle_connect_handshake(payload)

    return router


def register_handshake_routes(app: Any, *, api_prefix: str = "/api/v1", gui_prefix: str = "/gui") -> None:
    """Attach handshake routes to a FastAPI application (Docker master-server container)."""
    if APIRouter is None or HTTPException is None:
        raise RuntimeError("fastapi is required to register handshake routes")

    api_router = APIRouter(tags=["handshake"])

    @api_router.post("/handshake")
    def api_handshake_endpoint(payload: HandshakeRequest) -> dict[str, str]:
        return _handle_handshake(payload)

    app.include_router(api_router, prefix=api_prefix)

    gui_router = APIRouter(tags=["gui"])

    @gui_router.post("/connect-handshake")
    def gui_connect_handshake_endpoint(payload: ConnectHandshakeRequest) -> dict[str, str]:
        return _handle_connect_handshake(payload)

    app.include_router(gui_router, prefix=gui_prefix)


def _handle_handshake(payload: HandshakeRequest) -> dict[str, str]:
    try:
        return perform_handshake(
            api_key=payload.api_key,
            source=payload.source,
            connection_type=payload.connection_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _handle_connect_handshake(payload: ConnectHandshakeRequest) -> dict[str, str]:
    try:
        return perform_connect_handshake(
            api_key=payload.api_key,
            source=payload.source,
            session_id=payload.session_id,
            connection_type=payload.connection_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
