""" the API routes for the sessions container (using FastAPI)
SessionRoutes:
- /session-create: create a new session (MasterServer SessionID create)
- /session-find: find a peer to peer remote desktop sharing session
- /session-connect: connect to a peer to peer remote desktop sharing session
- /session-disconnect: disconnect from a peer to peer remote desktop sharing session
- /session-end: end a peer to peer remote desktop sharing session
- /session-record: record a peer to peer remote desktop sharing session
- /session-validate: Rdp SessionID + UserID + TokenID validation
- /session-transfer: mark transfer metadata for operations

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from ._common import get_mongo_client
from .compress import compress_session
from .searchpeer import peer_search
from .SessionCore import (
    agree_session,
    connect_session,
    create_session,
    disconnect_session,
    end_session,
    find_session,
    record_session_event,
    transfer_session_metadata,
    validate_session_for_rdp,
)
from .sessionID import (
    resolve_session_api_prefix,
    resolve_session_id_length,
    resolve_session_key_min_length,
)

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment, misc]
    HTTPException = None  # type: ignore[assignment, misc]
    BaseModel = object  # type: ignore[assignment, misc]
    Field = None  # type: ignore[assignment]


SESSION_ROUTES: tuple[str, ...] = (
    "/session-create",
    "/session-find",
    "/session-connect",
    "/session-disconnect",
    "/session-end",
    "/session-record",
    "/session-transfer",
    "/session-validate",
)


if BaseModel is not object and Field is not None:

    class UserAuthPayload(BaseModel):
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="TokenID")

        model_config = {"populate_by_name": True}

    class SessionCreatePayload(UserAuthPayload):
        pass

    class SessionFindPayload(BaseModel):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="TokenID")

        model_config = {"populate_by_name": True}

    class SessionConnectPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        session_key: str = Field(
            ..., alias="sessionKey", min_length=resolve_session_key_min_length()
        )

        model_config = {"populate_by_name": True}

    class SessionScopedPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )

        model_config = {"populate_by_name": True}

    class SessionRecordPayload(SessionScopedPayload):
        action: str = Field(...)

    class SessionTransferPayload(BaseModel):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        target: str = Field(...)

        model_config = {"populate_by_name": True}

    class SessionValidatePayload(BaseModel):
        """Matches Rdp/RdpMain.validate_session_id JSON shape."""

        session_id: str = Field(..., alias="session_id")
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="TokenID")

        model_config = {"populate_by_name": True}

else:
    UserAuthPayload = Any  # type: ignore[misc, assignment]
    SessionCreatePayload = Any  # type: ignore[misc, assignment]
    SessionFindPayload = Any  # type: ignore[misc, assignment]
    SessionConnectPayload = Any  # type: ignore[misc, assignment]
    SessionScopedPayload = Any  # type: ignore[misc, assignment]
    SessionRecordPayload = Any  # type: ignore[misc, assignment]
    SessionTransferPayload = Any  # type: ignore[misc, assignment]
    SessionValidatePayload = Any  # type: ignore[misc, assignment]


def _raise_http(exc: Exception) -> None:
    if HTTPException is None:
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def create_session_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create session routes")
    router = APIRouter(prefix=prefix, tags=["sessions"])

    @router.post("/session-create")
    def session_create(payload: SessionCreatePayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return create_session(
                host_user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-find")
    def session_find(payload: SessionFindPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return peer_search(
                session_id=payload.session_id,
                searcher_user_id=payload.user_id,
                searcher_id_token=payload.id_token,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-connect")
    def session_connect(payload: SessionConnectPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            result = connect_session(
                session_id=payload.session_id,
                session_key=payload.session_key,
                user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
            agree_session(
                session_id=payload.session_id,
                user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
            return result
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-disconnect")
    def session_disconnect(payload: SessionScopedPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return disconnect_session(
                session_id=payload.session_id,
                user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-end")
    def session_end(payload: SessionScopedPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            result = end_session(
                session_id=payload.session_id,
                host_user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
            # If complete already handed off inside end_session; else allow explicit compress.
            if result.get("SessionID_status") == "complete" and not result.get(
                "operations_handoff"
            ):
                result["operations_handoff"] = compress_session(
                    session_id=payload.session_id,
                    client=client,
                )
            return result
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-record")
    def session_record(payload: SessionRecordPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return record_session_event(
                session_id=payload.session_id,
                user_id=payload.user_id,
                action=payload.action,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-transfer")
    def session_transfer(payload: SessionTransferPayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return transfer_session_metadata(
                session_id=payload.session_id,
                target=payload.target,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    @router.post("/session-validate")
    def session_validate(payload: SessionValidatePayload) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Master server database unavailable")
        try:
            return validate_session_for_rdp(
                session_id=payload.session_id,
                user_id=payload.user_id,
                id_token=payload.id_token,
                client=client,
            )
        except Exception as exc:
            _raise_http(exc)
            raise
        finally:
            client.close()

    return router


def register_session_routes(app: Any, *, api_prefix: str | None = None) -> None:
    prefix = api_prefix if api_prefix is not None else resolve_session_api_prefix()
    app.include_router(create_session_router(prefix=prefix))
