"""FastAPI routes for the Tor-only master server connection protocol.

All master server APIs are hosted on *.onion; routes use connection.py logic.
"""

from __future__ import annotations

from typing import Any

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
from config import get_api_public_base_url, resolve_master_server_onion

try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, Field, field_validator, model_validator
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]
    field_validator = model_validator = lambda *args, **kwargs: (lambda fn: fn)  # type: ignore

CONNECTION_ROUTES: tuple[str, ...] = (
    "/connection",
    "/connection/status/{session_key}",
    "/connection/validate-onion",
    "/connection/tor-config",
)


if BaseModel is not object:

    class ConnectionRequest(BaseModel):
        api_key: str = Field(..., min_length=1)
        id_token: str = Field(..., min_length=1)
        source: str = Field(..., min_length=1)
        connection_type: ConnectionType = "initial"
        entity: str = "master"
        onion_address: str | None = None

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

    class ValidateOnionRequest(BaseModel):
        onion_address: str = Field(..., min_length=1)
        entity: str = "master"

        @field_validator("onion_address")
        @classmethod
        def _normalize_onion(cls, value: str) -> str:
            cleaned = normalize_onion_address(value)
            if not validate_onion_address(cleaned):
                raise ValueError("onion_address must be a valid v3 *.onion hostname")
            return cleaned


def _connection_error_handler(exc: Exception) -> None:
    if HTTPException is None or status is None:
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    raise exc


def create_connection_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create connection routes")

    router = APIRouter(prefix=prefix, tags=["connection"])

    @router.get("/connection/tor-config")
    def tor_config_endpoint() -> dict[str, Any]:
        config = get_tor_connection_config()
        config["master_server_onion"] = resolve_master_server_onion()
        config["api_public_base_url"] = get_api_public_base_url()
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
        }

    @router.get("/connection/status/{session_key}")
    def connection_status_endpoint(session_key: str) -> dict[str, Any]:
        try:
            return get_connection_status(session_key)
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


def register_connection_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    app.include_router(create_connection_router(prefix=api_prefix))
