"""
Shared helpers for LucidTops operations modules (Tor-only, Docker-compatible)

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

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
from operations_secrets import (  # noqa: E402
    require_secret,
    resolve_blockchain_collection,
    resolve_email_mac_limit,
    resolve_lucid_ledger_collection,
    resolve_lucidtops_node_db_collection,
    resolve_lucidtops_node_db_name,
    resolve_lucidtops_user_db_collection,
    resolve_lucidtops_user_db_name,
    resolve_registration_approved_status,
    resolve_session_records_collection,
)
from ops_pull_information import (  # noqa: E402
    live_primary_mac,
    live_primary_mac_normalized,
    pull_operations_hardware,
)
from id_secrets import resolve_operator_from_id_secrets  # noqa: E402

_data_chunker = load_backend_module("data-chunker.py")
chunk_session_data = _data_chunker.chunk_session_data
verify_chunk_hashes = _data_chunker.verify_chunk_hashes

try:
    from fastapi import APIRouter, HTTPException, status
    from pydantic import BaseModel, Field, model_validator
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    status = None  # type: ignore[misc, assignment]
    BaseModel = object  # type: ignore[misc, assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[misc, assignment]
    model_validator = None  # type: ignore[misc, assignment]

SESSION_RECORDS_COLLECTION: str
LUCID_LEDGER_COLLECTION: str
BLOCKCHAIN_COLLECTION: str


def __getattr__(name: str) -> Any:
    """Resolve collection names from secrets at first access (time of operation)."""
    if name == "SESSION_RECORDS_COLLECTION":
        return resolve_session_records_collection()
    if name == "LUCID_LEDGER_COLLECTION":
        return resolve_lucid_ledger_collection()
    if name == "BLOCKCHAIN_COLLECTION":
        return resolve_blockchain_collection()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


OPERATOR_ID_TYPES: tuple[str, ...] = (
    "NodeID",
    "AdminID",
    "MasterUserID",
    "MasterServerID",
)


def _normalize_mac(mac: str) -> str:
    return "".join(ch for ch in str(mac).upper() if ch.isalnum())


def get_node_db(client: Any) -> Any:
    return client[resolve_lucidtops_node_db_name()]


def get_user_db(client: Any) -> Any:
    return client[resolve_lucidtops_user_db_name()]


def node_operators_collection(client: Any) -> Any:
    return get_node_db(client)[resolve_lucidtops_node_db_collection()]


def user_accounts_collection(client: Any) -> Any:
    return get_user_db(client)[resolve_lucidtops_user_db_collection()]


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
    gui_prefix = require_secret("FRONTEND_GUI_PREFIX")
    body: dict[str, Any] = {
        "route": route,
        "subsystem": subsystem,
        "service": require_secret("OPERATIONS_SERVICE_NAME"),
        "network": require_secret("OPERATIONS_NETWORK_NAME"),
        "tor_only": True,
        "master_server_onion": onion,
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
            gui_full = (
                gui_path
                if gui_path.startswith(gui_prefix)  # pyright: ignore[reportOptionalMemberAccess]
                else f"{gui_prefix}{gui_path}"
            )
            body["tor_gui_service"] = format_tor_onion_service(onion, str(gui_full))
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


def _extract_mac_list(record: dict[str, Any]) -> list[str]:
    raw = (
        record.get("mac_ids")
        or record.get("MAC_IDs")
        or record.get("MAC_IDS")
        or record.get("mac_id_list")
        or []
    )
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(item).strip() for item in raw if str(item).strip()]
    else:
        items = []
    return items


def find_node_registration(
    client: Any,
    *,
    id_type: str,
    operator_id: str,
) -> dict[str, Any]:
    collection = node_operators_collection(client)
    query = {id_type: operator_id}
    record = collection.find_one(query)
    if not record:
        raise PermissionError(
            f"{id_type}={operator_id} is not registered in LucidTopsNodeDB"
        )
    return record


def require_operations_operator(
    *,
    node_id: str | None = None,
    admin_id: str | None = None,
    master_user_id: str | None = None,
    master_server_id: str | None = None,
    token_id: str,
    client: Any,
    email: str | None = None,
    load_id_secrets_file: bool = False,
) -> dict[str, Any]:
    """
    Gate operations: exactly one of NodeID|AdminID|MasterUserID|MasterServerID,
    TokenID match, LucidTopsNodeDB registration approved, live MAC in email MAC set (≤ EMAIL_MAC_LIMIT).
    """
    pull_operations_hardware(bind_environ=True)

    presented: list[tuple[str, str]] = []
    if node_id and str(node_id).strip():
        presented.append(("NodeID", str(node_id).strip()))
    if admin_id and str(admin_id).strip():
        presented.append(("AdminID", str(admin_id).strip()))
    if master_user_id and str(master_user_id).strip():
        presented.append(("MasterUserID", str(master_user_id).strip()))
    if master_server_id and str(master_server_id).strip():
        presented.append(("MasterServerID", str(master_server_id).strip()))

    secrets_binding: dict[str, Any] | None = None
    if load_id_secrets_file or not presented:
        secrets_binding = resolve_operator_from_id_secrets(
            operator_id=presented[0][1] if presented else None
        )
        presented = [(str(secrets_binding["id_type"]), str(secrets_binding["operator_id"]))]
        token_id = str(secrets_binding["TokenID"])
        email = str(secrets_binding["email"])

    if len(presented) != 1:
        raise PermissionError(
            "operations require exactly one of NodeID, AdminID, MasterUserID, or MasterServerID"
        )

    id_type, operator_id = presented[0]
    if id_type not in OPERATOR_ID_TYPES:
        raise PermissionError(f"unsupported operator id type: {id_type}")

    token = str(token_id or "").strip()
    if not token:
        raise PermissionError("TokenID is required")

    record = find_node_registration(client, id_type=id_type, operator_id=operator_id)

    record_token = str(
        record.get("TokenID")
        or record.get("IDToken")
        or record.get("token_id")
        or ""
    ).strip()
    if not record_token or record_token != token:
        raise PermissionError("TokenID does not match LucidTopsNodeDB registration")

    approved = resolve_registration_approved_status()
    status_value = str(
        record.get("registration_status")
        or record.get("status")
        or record.get("approval_status")
        or ""
    ).strip()
    if status_value != approved:
        raise PermissionError(
            "operator registration is not approved by MasterServer in LucidTopsNodeDB"
        )

    record_email = str(record.get("email") or record.get("Email") or "").strip()
    if email and record_email and email.strip().lower() != record_email.lower():
        raise PermissionError("email does not match LucidTopsNodeDB registration")
    if not record_email:
        raise PermissionError("email missing on LucidTopsNodeDB registration document")

    mac_ids = _extract_mac_list(record)
    mac_limit = resolve_email_mac_limit()
    if len(mac_ids) > mac_limit:
        raise PermissionError(
            f"LucidTopsNodeDB registration exceeds EMAIL_MAC_LIMIT={mac_limit} for email"
        )
    if not mac_ids:
        raise PermissionError("no MAC_IDs registered for this email in LucidTopsNodeDB")

    live_mac = live_primary_mac()
    live_norm = live_primary_mac_normalized()
    registered_norms = {_normalize_mac(mac) for mac in mac_ids}
    if live_norm not in registered_norms:
        raise PermissionError(
            "live hardware MAC is not in the registered MAC_IDs for this email "
            f"(limit {mac_limit}; concurrent online of registered MACs is allowed)"
        )

    return {
        "id_type": id_type,
        "operator_id": operator_id,
        "TokenID": token,
        "email": record_email,
        "mac": live_mac,
        "mac_ids": mac_ids,
        "registration": {k: v for k, v in record.items() if k != "_id"},
    }


def require_admin_operator(*, token_id: str, client: Any, **ids: Any) -> dict[str, Any]:
    operator = require_operations_operator(token_id=token_id, client=client, **ids)
    if operator["id_type"] not in {"AdminID", "MasterServerID", "MasterUserID"}:
        raise PermissionError("AdminID, MasterUserID, or MasterServerID required")
    return operator


def require_master_server_operator(*, token_id: str, client: Any, **ids: Any) -> dict[str, Any]:
    operator = require_operations_operator(token_id=token_id, client=client, **ids)
    if operator["id_type"] not in {"MasterServerID", "AdminID", "MasterUserID"}:
        raise PermissionError("MasterServer / Admin / MasterUser restricted access only")
    return operator


def verify_user_id_token(
    *,
    user_id: str,
    token_id: str,
    client: Any,
) -> bool:
    """Validate UserID + TokenID against LucidTopsUserDB."""
    if not user_id or not token_id or not str(token_id).strip():
        return False
    collection = user_accounts_collection(client)
    record = collection.find_one(
        {
            "UserID": user_id,
            "$or": [
                {"TokenID": token_id.strip()},
                {"IDToken": token_id.strip()},
            ],
        }
    )
    return record is not None


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

    class OperatorAuthPayload(BaseModel):  # type: ignore[reportIncompatibleMethodOverride]
        node_id: str | None = Field(default=None, alias="NodeID")
        admin_id: str | None = Field(default=None, alias="AdminID")
        master_user_id: str | None = Field(default=None, alias="MasterUserID")
        master_server_id: str | None = Field(default=None, alias="MasterServerID")
        token_id: str = Field(..., alias="TokenID", min_length=1)  # type: ignore[reportUnknownReturnType]
        email: str | None = Field(default=None, alias="email")

        model_config = {"populate_by_name": True}

        if model_validator is not None:

            @model_validator(mode="after")
            def _exactly_one_operator_id(self) -> Any:
                present = [
                    value
                    for value in (
                        self.node_id,
                        self.admin_id,
                        self.master_user_id,
                        self.master_server_id,
                    )
                    if value and str(value).strip()
                ]
                if len(present) != 1:
                    raise ValueError(
                        "exactly one of NodeID, AdminID, MasterUserID, or MasterServerID is required"
                    )
                return self

    # Backward-compatible alias used by older route modules during rebuild.
    AuthPayload = OperatorAuthPayload


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


def operator_kwargs_from_payload(payload: Any) -> dict[str, Any]:
    return {
        "node_id": getattr(payload, "node_id", None),
        "admin_id": getattr(payload, "admin_id", None),
        "master_user_id": getattr(payload, "master_user_id", None),
        "master_server_id": getattr(payload, "master_server_id", None),
        "token_id": getattr(payload, "token_id", None)
        or getattr(payload, "id_token", None)
        or "",
        "email": getattr(payload, "email", None),
    }
