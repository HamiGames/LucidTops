"""Shared helpers for LucidTops operations modules (Tor-only, Docker-compatible)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

OPERATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPERATIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(OPERATIONS_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATIONS_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import (  # noqa: E402
    API_PREFIX,
    format_tor_onion_service,
    get_master_db,
    get_mongo_client,
    resolve_master_server_onion,
    utc_now,
)
from WebPageLink import frontend_link_for_api_route  # noqa: E402
from load_module import load_backend_module  # noqa: E402

_data_chunker = load_backend_module("data-chunker.py")
chunk_session_data = _data_chunker.chunk_session_data
verify_chunk_hashes = _data_chunker.verify_chunk_hashes

try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]

SESSION_RECORDS_COLLECTION = "session_records"
LUCID_LEDGER_COLLECTION = "ledger_records"
BLOCKCHAIN_COLLECTION = "blockchain_blocks"


def tor_envelope(
    *,
    route: str,
    subsystem: str,
    payload: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Attach Tor-only metadata and javascript frontend linkage (not clearnet)."""
    link = frontend_link_for_api_route(route)
    onion = resolve_master_server_onion()
    api_segment = link.get("api_path") or route
    api_path = (
        api_segment
        if api_segment.startswith(API_PREFIX)
        else f"{API_PREFIX}{api_segment if api_segment.startswith('/') else f'/{api_segment}'}"
    )
    body: dict[str, Any] = {
        "route": route,
        "subsystem": subsystem,
        "service": "master_server",
        "network": "tor",
        "tor_only": True,
        "master_server_onion": onion or "",
        "timestamp": utc_now(),
    }
    if link.get("frontend"):
        body["frontend"] = link["frontend"]
        body["javascript"] = link["javascript"]
    body["api_path"] = api_path
    if link.get("gui_path"):
        body["gui_path"] = link["gui_path"]
    if onion:
        body["tor_service"] = format_tor_onion_service(onion, api_path)
        if link.get("gui_path"):
            gui_path = link["gui_path"]
            gui_full = gui_path if gui_path.startswith("/gui") else f"/gui{gui_path}"
            body["tor_gui_service"] = format_tor_onion_service(onion, gui_full)
    if payload:
        body.update(payload)
    body.update(extra)
    return body


def with_mongo(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Run a database handler with an auto-closing Mongo client when needed."""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        client = kwargs.pop("client", None)
        owns_client = client is None
        if owns_client:
            client = get_mongo_client()
            if client is None:
                raise RuntimeError("Master server database is unavailable")
        try:
            return handler(*args, client=client, **kwargs)
        finally:
            if owns_client and client is not None:
                client.close()

    return wrapper


def verify_id_token(
    *,
    user_id: str | None = None,
    node_user_id: str | None = None,
    id_token: str,
    client: Any,
) -> bool:
    """Validate a user or node IDToken against the master database."""
    if not id_token or not id_token.strip():
        return False
    db = get_master_db(client)
    if user_id:
        record = db.id_tokens.find_one(
            {"entity": "user", "UserID": user_id, "IDToken": id_token.strip()}
        )
        if record:
            return True
        record = db.users.find_one({"UserID": user_id, "IDToken": id_token.strip()})
        return record is not None
    if node_user_id:
        record = db.id_tokens.find_one(
            {
                "entity": "node",
                "NodeUserID": node_user_id,
                "IDToken": id_token.strip(),
            }
        )
        if record:
            return True
        record = db.node_users.find_one(
            {"NodeUserID": node_user_id, "IDToken": id_token.strip()}
        )
        return record is not None
    return False


def require_master_access(*, id_token: str, client: Any) -> None:
    """Restrict database master routes to admin or master-class credentials."""
    db = get_master_db(client)
    token = id_token.strip()
    if db.admin_users.find_one({"IDToken": token}):
        return
    if db.master_class_users.find_one({"IDToken": token}):
        return
    raise PermissionError("Master server restricted access only")


def require_admin_access(*, id_token: str, client: Any) -> None:
    """Restrict sensitive seed routes to admin credentials."""
    db = get_master_db(client)
    if db.admin_users.find_one({"IDToken": id_token.strip()}):
        return
    raise PermissionError("Admin restricted access only")


def handle_operations_error(exc: Exception) -> None:
    if HTTPException is None or status is None:
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    raise exc


if BaseModel is not object:

    class AuthPayload(BaseModel):
        user_id: str | None = Field(default=None, alias="UserID")
        node_user_id: str | None = Field(default=None, alias="NodeUserID")
        id_token: str = Field(..., alias="IDToken", min_length=1)

        model_config = {"populate_by_name": True}


def register_route_paths(
    router: Any,
    routes: tuple[str, ...],
    *,
    tag: str,
    handler_factory: Callable[[str], Callable[..., dict[str, Any]]],
) -> Any:
    """Attach GET/POST handlers for a route tuple to a FastAPI router."""
    for route in routes:
        path = route if route.startswith("/") else f"/{route}"
        handler = handler_factory(path)
        router.add_api_route(path, handler, methods=["GET", "POST"], tags=[tag])
    return router
