"""FastAPI routes (uvicorn server and FastAPI system) for the Tor-only master server connection protocol for the LucidTops system.

All master server Internal Network logic for API access to all containers within the LucidTops system (excluding the payment system container)
this includes the connection routes to all containers within the LucidTops system.
this is an internal network based connection protocol for the LucidTops system.
all connections are made via the Docker Network and the Tor Hidden Service.
all connections are made via the API routes (FastAPI) and the uvicorn server (MasterServer).
only AdminUser will have access to the connection routes from an external portal.
connection operations:
- validate the onion address for the entity
- establish a connection to the entity
- get the connection status
- get the connection configuration
- get the connection logs
- check registrations
- check userID and nodeID status
- check userID and nodeID registration
- check userID and nodeID connection status
- check userID and nodeID connection configuration
- check userID and nodeID connection logs
"""

from __future__ import annotations

from typing import Annotated, Any

from connection import (
    ConnectionType,
    establish_connection,
    get_connection_status,
    get_tor_connection_config,
    normalize_onion_address,
    resolve_onion_for_entity,
    validate_onion_address,
    validate_tor_endpoint,
)
from config import (
    API_PREFIX,
    get_master_db,
    get_mongo_client,
    get_tor_api_service,
    get_tor_gui_service,
    get_master_server_tor_service,
    resolve_master_server_onion,
    utc_now,
)
from MasterDBSchema import (
    ADMIN_USERS_COLLECTION,
    ID_TOKENS_COLLECTION,
    NODE_USERS_COLLECTION,
    SESSION_ID_LOG_COLLECTION,
    USERS_COLLECTION,
)

try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    ConfigDict = dict  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]
    field_validator = model_validator = lambda *args, **kwargs: (lambda fn: fn)  # type: ignore

CONNECTION_ROUTES: tuple[str, ...] = (
    "/connection",
    "/connection/status/{session_key}",
    "/connection/validate-onion",
    "/connection/tor-config",
    "/connection/logs/{session_key}",
    "/connection/registrations",
    "/connection/ids/status",
    "/connection/ids/registration",
    "/connection/ids/connection-status",
    "/connection/ids/connection-configuration",
    "/connection/ids/connection-logs",
)

MASTER_CONNECTION_COLLECTION = "master_connection"
CONNECTION_LOGS_COLLECTION = "connection_logs"
CONNECTION_LOG_LIMIT = 100


if BaseModel is not object:

    class ConnectionRequest(BaseModel):  # pyright: ignore[reportGeneralTypeIssues]
        api_key: Annotated[str, Field(min_length=1)]
        id_token: Annotated[str, Field(min_length=1, alias="IDToken")]
        source: Annotated[str, Field(min_length=1)]
        connection_type: ConnectionType = "initial"
        entity: str = "master"
        onion_address: str | None = None
        model_config = ConfigDict(populate_by_name=True)

        @field_validator("api_key", "id_token", "source")
        @classmethod
        def _strip_required(cls, value: str) -> str:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("field must not be empty")
            return cleaned

        @field_validator("onion_address")
        @classmethod
        def _normalize_onion(cls, value: str | None) -> str | None:
            if value is None or not value.strip():
                return None
            return normalize_onion_address(value)

        @model_validator(mode="after")
        def _default_master_onion(self) -> "ConnectionRequest":
            if not self.onion_address:
                self.onion_address = resolve_onion_for_entity(self.entity)
            return self

    class ValidateOnionRequest(BaseModel):  # pyright: ignore[reportGeneralTypeIssues]
        onion_address: Annotated[str, Field(min_length=1)]
        entity: str = "master"

        @field_validator("onion_address")
        @classmethod
        def _normalize_onion(cls, value: str) -> str:
            cleaned = normalize_onion_address(value)
            if not validate_onion_address(cleaned):
                raise ValueError("onion_address must be a valid v3 *.onion hostname")
            return cleaned

    class AdminPortalRequest(BaseModel):  # pyright: ignore[reportGeneralTypeIssues]
        admin_id_token: Annotated[str, Field(min_length=1, alias="IDToken")]
        model_config = ConfigDict(populate_by_name=True)

        @field_validator("admin_id_token")
        @classmethod
        def _strip_admin_token(cls, value: str) -> str:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("admin_id_token must not be empty")
            return cleaned

    class EntityIdRequest(AdminPortalRequest):
        userID: Annotated[str | None, Field(default=None, alias="UserID")] = None
        nodeID: Annotated[str | None, Field(default=None, alias="NodeUserID")] = None
        api_key: Annotated[str | None, Field(default=None)] = None
        model_config = ConfigDict(populate_by_name=True)

        @field_validator("userID", "nodeID", "api_key")
        @classmethod
        def _strip_optional(cls, value: str | None) -> str | None:
            if value is None:
                return None
            cleaned = value.strip()
            return cleaned or None

        @model_validator(mode="after")
        def _require_identity(self) -> "EntityIdRequest":
            if self.api_key:
                return self
            if self.userID and self.nodeID:
                return self
            raise ValueError(
                "provide api_key, or both userID and nodeID, to resolve entity identity"
            )


def _connection_error_handler(exc: Exception) -> None:
    if HTTPException is None or status is None:
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    raise exc


def _serialize_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    payload = dict(document)
    object_id = payload.pop("_id", None)
    if object_id is not None:
        payload["id"] = str(object_id)
    return payload


def _with_master_db(handler: Any) -> Any:
    mongo = get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        return handler(get_master_db(mongo))
    finally:
        mongo.close()


def _require_admin_access(*, admin_id_token: str, db: Any) -> dict[str, Any]:
    record = db[ADMIN_USERS_COLLECTION].find_one({"IDToken": admin_id_token.strip()})
    if not record:
        raise PermissionError("AdminUser credentials are required for this connection route")
    return {
        "adminUserID": record.get("adminUserID"),
        "access_level": record.get("access_level", "admin"),
        "access_type": record.get("access_type", "external_portal"),
    }


def _resolve_entity_ids(
    *,
    user_id: str | None,
    node_id: str | None,
    api_key: str | None,
) -> dict[str, str]:
    if api_key:
        from handshake import derive_user_and_node_ids

        return derive_user_and_node_ids(api_key)
    if user_id and node_id:
        return {"userID": user_id, "nodeID": node_id}
    raise ValueError("userID and nodeID could not be resolved")


def _find_user_token(db: Any, user_id: str) -> dict[str, Any] | None:
    return db[ID_TOKENS_COLLECTION].find_one({"entity": "user", "UserID": user_id})


def _find_node_token(db: Any, node_id: str) -> dict[str, Any] | None:
    return db[ID_TOKENS_COLLECTION].find_one({"entity": "node", "NodeUserID": node_id})


def _find_user_registration(db: Any, user_id: str) -> dict[str, Any] | None:
    return db[USERS_COLLECTION].find_one({"UserID": user_id})


def _find_node_registration(db: Any, node_id: str) -> dict[str, Any] | None:
    return db[NODE_USERS_COLLECTION].find_one({"NodeUserID": node_id})


def _connection_records_for_ids(db: Any, *, user_id: str, node_id: str) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = [
        {"entity": "user", "userID": user_id},
        {"entity": "user", "UserID": user_id},
        {"entity": "node", "nodeID": node_id},
        {"entity": "node", "NodeUserID": node_id},
        {"userID": user_id},
        {"nodeID": node_id},
    ]

    user_token = _find_user_token(db, user_id) or {}
    node_token = _find_node_token(db, node_id) or {}
    for token in (user_token, node_token):
        session_id = token.get("session_id")
        session_key = token.get("session_key")
        if isinstance(session_id, str) and session_id.strip():
            cleaned = session_id.strip()
            clauses.append({"session_id": cleaned})
            clauses.append({"session_key": cleaned})
        if isinstance(session_key, str) and session_key.strip():
            clauses.append({"session_key": session_key.strip()})

    cursor = (
        db[MASTER_CONNECTION_COLLECTION]
        .find({"$or": clauses})
        .sort("updated_at", -1)
        .limit(CONNECTION_LOG_LIMIT)
    )
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for document in cursor:
        key = str(document.get("session_key") or document.get("_id"))
        if key in seen:
            continue
        seen.add(key)
        records.append(document)
    return records


def _build_connection_logs(
    db: Any,
    *,
    session_key: str | None = None,
    user_id: str | None = None,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []

    if session_key:
        dedicated = list(
            db[CONNECTION_LOGS_COLLECTION]
            .find({"session_key": session_key})
            .sort("recorded_at", -1)
            .limit(CONNECTION_LOG_LIMIT)
        )
        for entry in dedicated:
            serialized = _serialize_document(entry)
            if serialized:
                logs.append(serialized)

        connection = db[MASTER_CONNECTION_COLLECTION].find_one({"session_key": session_key})
        if connection:
            serialized = _serialize_document(connection)
            if serialized:
                logs.append(
                    {
                        "log_type": "master_connection",
                        "session_key": session_key,
                        "status": "connected" if connection.get("active") else "inactive",
                        "recorded_at": connection.get("updated_at") or connection.get("created_at"),
                        "record": serialized,
                    }
                )

        session_logs = list(
            db[SESSION_ID_LOG_COLLECTION]
            .find({"sessionKey": session_key})
            .sort("recorded_at", -1)
            .limit(CONNECTION_LOG_LIMIT)
        )
        for entry in session_logs:
            serialized = _serialize_document(entry)
            if serialized:
                serialized["log_type"] = "session_id_log"
                logs.append(serialized)

    if user_id and node_id:
        for connection in _connection_records_for_ids(db, user_id=user_id, node_id=node_id):
            serialized = _serialize_document(connection)
            if not serialized:
                continue
            logs.append(
                {
                    "log_type": "master_connection",
                    "session_key": connection.get("session_key"),
                    "status": "connected" if connection.get("active") else "inactive",
                    "recorded_at": connection.get("updated_at") or connection.get("created_at"),
                    "record": serialized,
                }
            )

        token_user = _serialize_document(_find_user_token(db, user_id))
        token_node = _serialize_document(_find_node_token(db, node_id))
        if token_user:
            logs.append(
                {
                    "log_type": "id_token",
                    "entity": "user",
                    "userID": user_id,
                    "recorded_at": token_user.get("updated_at") or token_user.get("created_at"),
                    "record": {
                        "UserID": token_user.get("UserID"),
                        "source": token_user.get("source"),
                        "connection_type": token_user.get("connection_type"),
                        "updated_at": token_user.get("updated_at"),
                        "created_at": token_user.get("created_at"),
                    },
                }
            )
        if token_node:
            logs.append(
                {
                    "log_type": "id_token",
                    "entity": "node",
                    "nodeID": node_id,
                    "recorded_at": token_node.get("updated_at") or token_node.get("created_at"),
                    "record": {
                        "NodeUserID": token_node.get("NodeUserID"),
                        "source": token_node.get("source"),
                        "connection_type": token_node.get("connection_type"),
                        "updated_at": token_node.get("updated_at"),
                        "created_at": token_node.get("created_at"),
                    },
                }
            )

    return logs[:CONNECTION_LOG_LIMIT]


def get_connection_logs(session_key: str) -> dict[str, Any]:
    cleaned = session_key.strip()
    if not cleaned:
        raise ValueError("session_key must not be empty")

    def _query(db: Any) -> dict[str, Any]:
        connection = db[MASTER_CONNECTION_COLLECTION].find_one({"session_key": cleaned})
        if not connection:
            raise LookupError("Connection session not found")
        logs = _build_connection_logs(db, session_key=cleaned)
        return {
            "session_key": cleaned,
            "status": "connected" if connection.get("active") else "inactive",
            "network": "tor",
            "tor_only": True,
            "log_count": len(logs),
            "logs": logs,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_registrations(*, admin_id_token: str) -> dict[str, Any]:
    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        user_count = db[USERS_COLLECTION].count_documents({})
        node_count = db[NODE_USERS_COLLECTION].count_documents({})
        token_user_count = db[ID_TOKENS_COLLECTION].count_documents({"entity": "user"})
        token_node_count = db[ID_TOKENS_COLLECTION].count_documents({"entity": "node"})
        active_connections = db[MASTER_CONNECTION_COLLECTION].count_documents({"active": True})
        return {
            "adminUserID": admin.get("adminUserID"),
            "registrations": {
                "users": user_count,
                "node_users": node_count,
                "id_tokens_user": token_user_count,
                "id_tokens_node": token_node_count,
                "active_connections": active_connections,
            },
            "network": "tor",
            "tor_only": True,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_user_and_node_status(
    *,
    admin_id_token: str,
    user_id: str | None = None,
    node_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    ids = _resolve_entity_ids(user_id=user_id, node_id=node_id, api_key=api_key)

    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        user_token = _find_user_token(db, ids["userID"])
        node_token = _find_node_token(db, ids["nodeID"])
        user_reg = _find_user_registration(db, ids["userID"])
        node_reg = _find_node_registration(db, ids["nodeID"])
        return {
            "adminUserID": admin.get("adminUserID"),
            "userID": ids["userID"],
            "nodeID": ids["nodeID"],
            "user": {
                "registered": user_reg is not None,
                "id_token_present": user_token is not None,
                "status": "active" if user_reg and not user_reg.get("deleted_at") else "inactive",
                "tier": (user_reg or {}).get("tier"),
                "updated_at": (user_reg or user_token or {}).get("updated_at"),
            },
            "node": {
                "registered": node_reg is not None,
                "id_token_present": node_token is not None,
                "status": "active" if node_reg and not node_reg.get("deleted_at") else "inactive",
                "tier": (node_reg or {}).get("tier"),
                "updated_at": (node_reg or node_token or {}).get("updated_at"),
            },
            "network": "tor",
            "tor_only": True,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_user_and_node_registration(
    *,
    admin_id_token: str,
    user_id: str | None = None,
    node_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    ids = _resolve_entity_ids(user_id=user_id, node_id=node_id, api_key=api_key)

    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        user_reg = _serialize_document(_find_user_registration(db, ids["userID"]))
        node_reg = _serialize_document(_find_node_registration(db, ids["nodeID"]))
        user_token = _serialize_document(_find_user_token(db, ids["userID"]))
        node_token = _serialize_document(_find_node_token(db, ids["nodeID"]))

        safe_user = None
        if user_reg:
            safe_user = {
                "UserID": user_reg.get("UserID"),
                "tier": user_reg.get("tier"),
                "created_at": user_reg.get("created_at"),
                "updated_at": user_reg.get("updated_at"),
                "deleted_at": user_reg.get("deleted_at"),
                "payment_status": user_reg.get("payment_status"),
            }
        safe_node = None
        if node_reg:
            safe_node = {
                "NodeUserID": node_reg.get("NodeUserID"),
                "name": node_reg.get("name"),
                "tier": node_reg.get("tier"),
                "node_registration_timestamp": node_reg.get("node_registration_timestamp"),
                "created_at": node_reg.get("created_at"),
                "updated_at": node_reg.get("updated_at"),
                "deleted_at": node_reg.get("deleted_at"),
                "payment_status": node_reg.get("payment_status"),
            }

        return {
            "adminUserID": admin.get("adminUserID"),
            "userID": ids["userID"],
            "nodeID": ids["nodeID"],
            "user_registered": safe_user is not None,
            "node_registered": safe_node is not None,
            "user_registration": safe_user,
            "node_registration": safe_node,
            "user_id_token_recorded": user_token is not None,
            "node_id_token_recorded": node_token is not None,
            "network": "tor",
            "tor_only": True,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_user_and_node_connection_status(
    *,
    admin_id_token: str,
    user_id: str | None = None,
    node_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    ids = _resolve_entity_ids(user_id=user_id, node_id=node_id, api_key=api_key)

    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        records = _connection_records_for_ids(db, user_id=ids["userID"], node_id=ids["nodeID"])
        active = [record for record in records if record.get("active")]
        latest = _serialize_document(records[0]) if records else None
        return {
            "adminUserID": admin.get("adminUserID"),
            "userID": ids["userID"],
            "nodeID": ids["nodeID"],
            "connection_count": len(records),
            "active_connection_count": len(active),
            "status": "connected" if active else "inactive",
            "latest_connection": latest,
            "network": "tor",
            "tor_only": True,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_user_and_node_connection_configuration(
    *,
    admin_id_token: str,
    user_id: str | None = None,
    node_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    ids = _resolve_entity_ids(user_id=user_id, node_id=node_id, api_key=api_key)

    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        tor_config = get_tor_connection_config()
        records = _connection_records_for_ids(db, user_id=ids["userID"], node_id=ids["nodeID"])
        latest = records[0] if records else {}
        return {
            "adminUserID": admin.get("adminUserID"),
            "userID": ids["userID"],
            "nodeID": ids["nodeID"],
            "configuration": {
                "protocol": latest.get("protocol") or tor_config.get("protocol"),
                "transport": latest.get("transport") or tor_config.get("transport"),
                "torrent_layer": latest.get("torrent_layer") or tor_config.get("torrent_layer"),
                "network": "tor",
                "tor_only": True,
                "onion_address": latest.get("onion_address") or tor_config.get("master_server_onion"),
                "tor_api_service": latest.get("tor_api_service") or tor_config.get("tor_api_service"),
                "tor_gui_service": tor_config.get("tor_gui_service"),
                "frontend_onion": tor_config.get("frontend_onion"),
                "node_onion": tor_config.get("node_onion"),
                "source": latest.get("source"),
                "entity": latest.get("entity"),
                "session_key": latest.get("session_key"),
            },
            "tor": tor_config,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def check_user_and_node_connection_logs(
    *,
    admin_id_token: str,
    user_id: str | None = None,
    node_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    ids = _resolve_entity_ids(user_id=user_id, node_id=node_id, api_key=api_key)

    def _query(db: Any) -> dict[str, Any]:
        admin = _require_admin_access(admin_id_token=admin_id_token, db=db)
        logs = _build_connection_logs(db, user_id=ids["userID"], node_id=ids["nodeID"])
        return {
            "adminUserID": admin.get("adminUserID"),
            "userID": ids["userID"],
            "nodeID": ids["nodeID"],
            "log_count": len(logs),
            "logs": logs,
            "network": "tor",
            "tor_only": True,
            "timestamp": utc_now(),
        }

    return _with_master_db(_query)


def create_connection_router(*, api_prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create connection routes")

    router = APIRouter(prefix=api_prefix, tags=["connection"])

    @router.get("/connection/tor-config")
    def tor_config_endpoint() -> dict[str, Any]:
        config = get_tor_connection_config()
        config["master_server_onion"] = resolve_master_server_onion()
        config["master_server_tor_service"] = get_master_server_tor_service()
        config["tor_api_service"] = get_tor_api_service()
        config["tor_gui_service"] = get_tor_gui_service()
        config["network"] = "tor"
        config["tor_only"] = True
        return config

    @router.post("/connection/validate-onion")
    def validate_onion_endpoint(payload: ValidateOnionRequest) -> dict[str, Any]:
        valid = validate_tor_endpoint(payload.onion_address, entity=payload.entity)
        return {
            "onion_address": payload.onion_address,
            "entity": payload.entity,
            "valid": valid,
            "format_valid": validate_onion_address(payload.onion_address),
            "tor_only": True,
            "network": "tor",
        }

    @router.get("/connection/status/{session_key}")
    def connection_status_endpoint(session_key: str) -> dict[str, Any]:
        try:
            return get_connection_status(session_key)
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.get("/connection/logs/{session_key}")
    def connection_logs_endpoint(session_key: str) -> dict[str, Any]:
        try:
            return get_connection_logs(session_key)
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/registrations")
    def registrations_endpoint(payload: AdminPortalRequest) -> dict[str, Any]:
        try:
            return check_registrations(admin_id_token=payload.admin_id_token)
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/ids/status")
    def ids_status_endpoint(payload: EntityIdRequest) -> dict[str, Any]:
        try:
            return check_user_and_node_status(
                admin_id_token=payload.admin_id_token,
                user_id=payload.userID,
                node_id=payload.nodeID,
                api_key=payload.api_key,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/ids/registration")
    def ids_registration_endpoint(payload: EntityIdRequest) -> dict[str, Any]:
        try:
            return check_user_and_node_registration(
                admin_id_token=payload.admin_id_token,
                user_id=payload.userID,
                node_id=payload.nodeID,
                api_key=payload.api_key,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/ids/connection-status")
    def ids_connection_status_endpoint(payload: EntityIdRequest) -> dict[str, Any]:
        try:
            return check_user_and_node_connection_status(
                admin_id_token=payload.admin_id_token,
                user_id=payload.userID,
                node_id=payload.nodeID,
                api_key=payload.api_key,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/ids/connection-configuration")
    def ids_connection_configuration_endpoint(payload: EntityIdRequest) -> dict[str, Any]:
        try:
            return check_user_and_node_connection_configuration(
                admin_id_token=payload.admin_id_token,
                user_id=payload.userID,
                node_id=payload.nodeID,
                api_key=payload.api_key,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection/ids/connection-logs")
    def ids_connection_logs_endpoint(payload: EntityIdRequest) -> dict[str, Any]:
        try:
            return check_user_and_node_connection_logs(
                admin_id_token=payload.admin_id_token,
                user_id=payload.userID,
                node_id=payload.nodeID,
                api_key=payload.api_key,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    @router.post("/connection")
    def connection_endpoint(payload: ConnectionRequest) -> dict[str, Any]:
        try:
            return establish_connection(
                api_key=payload.api_key,
                id_token=payload.id_token,
                source=payload.source,
                connection_type=payload.connection_type,
                entity=payload.entity,
                onion_address=payload.onion_address,
            )
        except Exception as exc:
            _connection_error_handler(exc)
            raise

    return router


def register_connection_routes(app: Any, *, api_prefix: str | None = None) -> None:
    """Attach connection routes for main.create_app (api_prefix=API_PREFIX)."""
    prefix = api_prefix if api_prefix is not None else API_PREFIX
    app.include_router(create_connection_router(api_prefix=prefix))
