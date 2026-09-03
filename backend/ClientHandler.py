"""API connection protocol for handling client requests from the frontend (FastAPI).

Requirements:
- request must originate from an allowed frontend/*.js file
- handshake protocol must be followed
- required data fields must be present and correctly formatted
- uses uvicorn server and FastAPI systems for cross container communication
- uses MongoDB for storage of data (userDB, NodeDB, BlockchainDB, SessionsDB, OperationsDB, PaySystemsDB, etc.)
- uses DockerfileDNS for network communication
- uses Tor (*.onion) for external communication (To the Tor Hosted server) via the Tor Hidden Service
- uses Clearnet for internal communication (To the Docker Network) via the Docker Network
- only handles client requests from the frontend (javascript) via the API routes (FastAPI)
- only handles client requests from the backend (python) via the API routes (FastAPI)
- only handles client requests to join the UserDB or NodeDB (mongodb) via the API routes (FastAPI)
- is operated by the MasterServer (uvicorn server and FastAPI system) for initial handshake and connection validation

"""

from __future__ import annotations

from typing import Any

from config import (
    API_PREFIX,
    MASTER_SERVER_TOR_ONLY,
    format_tor_onion_service,
    get_client_request_tor_service,
    get_config_list,
    get_config_value,
    get_local_tor_forward_hosts,
    load_tor_routes_manifest,
    resolve_master_server_onion,
    utc_now,
)
from connection import (
    ConnectionType,
    establish_connection,
    get_tor_connection_config,
    normalize_onion_address,
    resolve_onion_for_entity,
    validate_connection_source,
)
from handshake import (
    perform_connect_handshake,
    perform_handshake,
    validate_api_key_format,
    validate_handshake_source,
)
from WebPageLink import resolve_web_page_link, validate_web_page_link

ALLOWED_REGISTER_SOURCE = get_config_value("REGISTER_SOURCE", "register.js")

_DEFAULT_INITIAL_HANDSHAKE_SOURCES = frozenset(
    {
        "register.js",
        "login.js",
        "node-registration.js",
        "tier-select.js",
    }
)


def get_initial_handshake_sources() -> frozenset[str]:
    return get_config_list("INITIAL_HANDSHAKE_SOURCES", _DEFAULT_INITIAL_HANDSHAKE_SOURCES)


def get_allowed_ongoing_sources() -> frozenset[str]:
    return get_config_list(
        "ALLOWED_ONGOING_SOURCES",
        frozenset(
            {
                "register.js",
                "node-registration.js",
                "login.js",
                "tier-select.js",
                "connect-handshake.js",
                "find-peer.js",
                "find-Peer.js",
                "home_page.js",
                "dashboard.js",
                "settings.js",
                "LucidLedger.js",
                "LucidMarket.js",
                "RemoteView.js",
            }
        ),
    )

CLIENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "source",
    "api_key",
    "payload",
)

CLIENT_REQUEST_ROUTE = "/client-request"


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _coalesce_mapping(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_client_body(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize javascript/Tor Browser JSON (camelCase + nested payload) into handler fields."""
    nested = body.get("payload")
    payload = dict(nested) if isinstance(nested, dict) else {}
    merged: dict[str, Any] = {**payload}
    for key, value in body.items():
        if key != "payload" and value not in (None, ""):
            merged[key] = value

    source = _coalesce_mapping(merged, "source", "Source", "javascript")
    api_key = _coalesce_mapping(merged, "api_key", "apiKey", "API_key", "APIKey")
    connection_type = _coalesce_mapping(merged, "connection_type", "connectionType") or "ongoing"
    perform_initial_handshake = bool(
        _coalesce_mapping(
            merged,
            "perform_initial_handshake",
            "performInitialHandshake",
        )
    )
    entity = str(_coalesce_mapping(merged, "entity", "Entity") or "master")
    onion_address = _coalesce_mapping(
        merged,
        "onion_address",
        "onionAddress",
        "onion",
    )
    id_token = _coalesce_mapping(
        merged,
        "id_token",
        "idToken",
        "IDToken",
        "user_IDToken",
        "userIDToken",
        "node_IDToken",
        "nodeIDToken",
    )
    session_id = _coalesce_mapping(merged, "session_id", "sessionID", "sessionId")

    if onion_address:
        onion_address = normalize_onion_address(str(onion_address))

    return {
        "source": str(source or "").strip(),
        "api_key": str(api_key or "").strip(),
        "payload": payload if isinstance(nested, dict) else merged,
        "connection_type": str(connection_type).strip(),
        "perform_initial_handshake": perform_initial_handshake,
        "entity": entity,
        "onion_address": onion_address,
        "id_token": str(id_token).strip() if id_token else "",
        "session_id": str(session_id).strip() if session_id else "",
    }


def _resolve_connection_type(
    *,
    source: str,
    connection_type: str,
    perform_initial_handshake: bool,
) -> ConnectionType:
    normalized = _normalize_source(source)
    if perform_initial_handshake or normalized in get_initial_handshake_sources():
        return "initial"
    if connection_type == "initial":
        return "initial"
    return "ongoing"


def _request_is_tor_compatible(host: str) -> bool:
    hostname = host.split(":")[0].lower()
    if hostname.endswith(".onion"):
        return True
    if hostname in get_local_tor_forward_hosts():
        return True
    return not MASTER_SERVER_TOR_ONLY


def _client_tor_envelope(*, source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach Tor-only metadata for javascript frontend consumers (*.onion, not clearnet)."""
    link = resolve_web_page_link(source)
    onion = resolve_master_server_onion()
    api_segment = link.get("api_path") or CLIENT_REQUEST_ROUTE
    api_path = (
        api_segment
        if api_segment.startswith(API_PREFIX)
        else f"{API_PREFIX}{api_segment if api_segment.startswith('/') else f'/{api_segment}'}"
    )
    body: dict[str, Any] = {
        "route": CLIENT_REQUEST_ROUTE,
        "subsystem": "client-handler",
        "service": "master_server",
        "network": "tor",
        "tor_only": True,
        "master_server_onion": onion or "",
        "timestamp": utc_now(),
        "source": _normalize_source(source),
        "frontend": link.get("frontend"),
        "javascript": link.get("javascript"),
        "api_path": api_path,
        "tor_api_route": link.get("tor_api_route"),
        "tor_gui_route": link.get("tor_gui_route"),
    }
    if onion:
        body["tor_service"] = format_tor_onion_service(onion, api_path)
        gui_path = link.get("gui_path")
        if isinstance(gui_path, str) and gui_path:
            gui_full = gui_path if gui_path.startswith("/gui") else f"/gui{gui_path}"
            body["tor_gui_service"] = format_tor_onion_service(onion, gui_full)
    body.update(payload)
    return body


def validate_client_request(
    *,
    source: str,
    api_key: str,
    payload: dict[str, Any] | None,
    connection_type: ConnectionType = "ongoing",
    require_register: bool = False,
) -> None:
    """Validate client request origin, format, and required fields."""
    if not source or not api_key:
        raise ValueError("source and api_key are required")

    normalized = _normalize_source(source)
    if require_register and normalized != ALLOWED_REGISTER_SOURCE:
        raise PermissionError("Request must originate from frontend/register.js")

    if not validate_web_page_link(normalized):
        raise PermissionError(f"Request source not permitted: {normalized}")

    if not validate_api_key_format(api_key):
        raise ValueError("Client request API key format is invalid")

    if not validate_handshake_source(normalized, connection_type):
        raise PermissionError(
            f"Handshake source {normalized} is not permitted for {connection_type} connections"
        )

    if not validate_connection_source(normalized, connection_type):
        raise PermissionError(
            f"Connection source {normalized} is not permitted for {connection_type} connections"
        )

    if payload is None or not isinstance(payload, dict):
        raise ValueError("Client request payload must be a dictionary")


def _resolve_id_token(
    *,
    payload: dict[str, Any],
    explicit_id_token: str,
    handshake: dict[str, Any] | None,
    entity: str,
) -> str:
    if handshake:
        if entity == "node":
            token = handshake.get("node_IDToken") or handshake.get("nodeIDToken")
        else:
            token = handshake.get("user_IDToken") or handshake.get("userIDToken")
        if token:
            return str(token).strip()

    for key in (
        "id_token",
        "idToken",
        "IDToken",
        "user_IDToken",
        "userIDToken",
        "node_IDToken",
        "nodeIDToken",
    ):
        value = payload.get(key)
        if value:
            return str(value).strip()

    if explicit_id_token:
        return explicit_id_token.strip()
    return ""


def handle_client_request(
    *,
    source: str,
    api_key: str,
    payload: dict[str, Any],
    connection_type: str = "ongoing",
    perform_initial_handshake: bool = False,
    entity: str = "master",
    onion_address: str | None = None,
    id_token: str = "",
    session_id: str = "",
    client: Any | None = None,
) -> dict[str, Any]:
    """Handle a frontend client request after handshake/connection validation."""
    resolved_connection_type = _resolve_connection_type(
        source=source,
        connection_type=connection_type,
        perform_initial_handshake=perform_initial_handshake,
    )
    validate_client_request(
        source=source,
        api_key=api_key,
        payload=payload,
        connection_type=resolved_connection_type,
    )

    link = resolve_web_page_link(source)
    normalized_source = _normalize_source(source)
    handshake_result: dict[str, Any] | None = None

    if perform_initial_handshake or normalized_source in get_initial_handshake_sources():
        if session_id:
            handshake_result = perform_connect_handshake(
                api_key=api_key,
                source=source,
                session_id=session_id,
                connection_type=resolved_connection_type,
                client=client,
            )
        else:
            handshake_result = perform_handshake(
                api_key=api_key,
                source=source,
                connection_type=resolved_connection_type,
                client=client,
            )

    resolved_id_token = _resolve_id_token(
        payload=payload,
        explicit_id_token=id_token,
        handshake=handshake_result,
        entity=entity,
    )
    if not resolved_id_token:
        raise ValueError(
            "id_token is required when perform_initial_handshake is false; "
            "provide IDToken/id_token in payload or enable performInitialHandshake"
        )

    resolved_onion = onion_address or resolve_onion_for_entity(entity)
    connection = establish_connection(
        api_key=api_key,
        id_token=resolved_id_token,
        source=source,
        connection_type=resolved_connection_type,
        entity=entity,
        onion_address=resolved_onion,
        client=client,
    )

    tor_config = get_tor_connection_config()
    result_payload: dict[str, Any] = {
        "status": "accepted",
        "source": normalized_source,
        "api_route": link.get("tor_api_route"),
        "gui_route": link.get("tor_gui_route"),
        "frontend": link.get("frontend"),
        "javascript": link.get("javascript"),
        "payload_keys": sorted(payload.keys()),
        "connection_type": resolved_connection_type,
        "entity": entity,
        "id_token": resolved_id_token,
        "IDToken": resolved_id_token,
        "connection": connection,
        "tor": tor_config,
    }

    if handshake_result:
        result_payload["handshake"] = handshake_result
        result_payload["userID"] = handshake_result.get("userID")
        result_payload["nodeID"] = handshake_result.get("nodeID")
        result_payload["user_IDToken"] = handshake_result.get("user_IDToken")
        result_payload["node_IDToken"] = handshake_result.get("node_IDToken")
        if handshake_result.get("digital_signature"):
            result_payload["digital_signature"] = handshake_result["digital_signature"]
        if handshake_result.get("session_id"):
            result_payload["session_id"] = handshake_result["session_id"]
            result_payload["sessionID"] = handshake_result["session_id"]

    return _client_tor_envelope(source=source, payload=result_payload)


def get_client_handler_tor_config() -> dict[str, Any]:
    """Return Tor config for javascript frontend bootstrap over *.onion."""
    config = get_tor_connection_config()
    tor_manifest = load_tor_routes_manifest()
    client_request_path = f"{API_PREFIX}{CLIENT_REQUEST_ROUTE}"
    config["client_request_route"] = client_request_path
    config["client_request_tor_service"] = get_client_request_tor_service()
    config["client_request_tor_config"] = tor_manifest.get(
        "client_request_tor_config",
        f"{API_PREFIX}{CLIENT_REQUEST_ROUTE}/tor-config",
    )
    if tor_manifest.get("routes"):
        config["tor_routes"] = tor_manifest["routes"]
    config["allowed_sources"] = sorted(get_allowed_ongoing_sources())
    return config


try:
    from fastapi import APIRouter, HTTPException, Request, status
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]


def _client_handler_error(exc: Exception) -> None:
    if HTTPException is None or status is None:
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    raise exc


def register_client_handler_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    """Register client handler endpoints on the FastAPI app (Tor-only, javascript compatible)."""
    if APIRouter is None or HTTPException is None or status is None or Request is None:
        raise RuntimeError("fastapi is required to register client handler routes")

    router = APIRouter(prefix=api_prefix, tags=["client-handler"])

    @router.get("/client-request/tor-config")
    def client_tor_config_endpoint() -> dict[str, Any]:
        return get_client_handler_tor_config()

    @router.post("/client-request")
    async def client_request_endpoint(request: Request) -> dict[str, Any]:  # pyright: ignore[reportInvalidTypeForm]
        if not _request_is_tor_compatible(request.headers.get("host", "")):
            raise HTTPException(  # pyright: ignore[reportOptionalCall]
                status_code=status.HTTP_403_FORBIDDEN,  # pyright: ignore[reportOptionalMemberAccess]
                detail="Client requests must originate via the master server *.onion hidden service",
            )

        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(  # pyright: ignore[reportOptionalCall]
                status_code=status.HTTP_400_BAD_REQUEST,  # pyright: ignore[reportOptionalMemberAccess]
                detail="Request body must be valid JSON",
            ) from exc

        if not isinstance(body, dict):
            raise HTTPException(  # pyright: ignore[reportOptionalCall]
                status_code=status.HTTP_400_BAD_REQUEST,  # pyright: ignore[reportOptionalMemberAccess]
                detail="Request body must be a JSON object",
            )

        normalized = normalize_client_body(body)
        try:
            return handle_client_request(
                source=normalized["source"],
                api_key=normalized["api_key"],
                payload=normalized["payload"],
                connection_type=normalized["connection_type"],
                perform_initial_handshake=normalized["perform_initial_handshake"],
                entity=normalized["entity"],
                onion_address=normalized["onion_address"],
                id_token=normalized["id_token"],
                session_id=normalized["session_id"],
            )
        except Exception as exc:
            _client_handler_error(exc)
            raise

    app.include_router(router)
