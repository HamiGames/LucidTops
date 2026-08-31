"""API connection protocol for handling client requests from the frontend (FastAPI).

Requirements:
- request must originate from an allowed frontend/*.js file
- handshake protocol must be followed
- required data fields must be present and correctly formatted
"""

from __future__ import annotations

from typing import Any

from connection import establish_connection, resolve_onion_for_entity
from handshake import perform_handshake, validate_api_key_format
from WebPageLink import resolve_web_page_link, validate_web_page_link

ALLOWED_REGISTER_SOURCE = "register.js"

CLIENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "source",
    "api_key",
    "payload",
)


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def validate_client_request(
    *,
    source: str,
    api_key: str,
    payload: dict[str, Any] | None,
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

    if payload is None or not isinstance(payload, dict):
        raise ValueError("Client request payload must be a dictionary")


def handle_client_request(
    *,
    source: str,
    api_key: str,
    payload: dict[str, Any],
    connection_type: str = "ongoing",
    perform_initial_handshake: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    """Handle a frontend client request after handshake/connection validation."""
    validate_client_request(source=source, api_key=api_key, payload=payload)

    link = resolve_web_page_link(source)
    result: dict[str, Any] = {
        "source": _normalize_source(source),
        "api_route": link["api_route"],
        "gui_route": link["gui_route"],
        "payload_keys": sorted(payload.keys()),
        "status": "accepted",
    }

    if perform_initial_handshake:
        handshake = perform_handshake(
            api_key=api_key,
            source=source,
            connection_type="initial" if connection_type == "initial" else "ongoing",
            client=client,
        )
        result["handshake"] = handshake
        id_token = handshake["user_IDToken"]
    else:
        id_token = str(payload.get("id_token", payload.get("IDToken", "")))
        if not id_token:
            raise ValueError("id_token is required when perform_initial_handshake is false")

    entity = str(payload.get("entity", "master"))
    onion_address = payload.get("onion_address") or resolve_onion_for_entity(entity)

    connection = establish_connection(
        api_key=api_key,
        id_token=id_token,
        source=source,
        connection_type="ongoing" if connection_type != "initial" else "initial",
        entity=entity,
        onion_address=onion_address,
        client=client,
    )
    result["connection"] = connection
    return result


try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]


if BaseModel is not object:

    class ClientRequest(BaseModel):
        source: str = Field(..., min_length=1)
        api_key: str = Field(..., min_length=1)
        payload: dict[str, Any] = Field(default_factory=dict)
        connection_type: str = "ongoing"
        perform_initial_handshake: bool = False


def register_client_handler_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    """Register client handler endpoint on the FastAPI app."""
    if APIRouter is None or HTTPException is None:
        raise RuntimeError("fastapi is required to register client handler routes")

    router = APIRouter(prefix=api_prefix, tags=["client-handler"])

    @router.post("/client-request")
    def client_request_endpoint(payload: ClientRequest) -> dict[str, Any]:
        try:
            return handle_client_request(
                source=payload.source,
                api_key=payload.api_key,
                payload=payload.payload,
                connection_type=payload.connection_type,
                perform_initial_handshake=payload.perform_initial_handshake,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

    app.include_router(router)
