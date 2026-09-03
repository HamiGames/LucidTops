""" the API routes for the session system (using FastAPI)
SessionRoutes:
- /session-create: create a new session
- /session-find: find a peer to peer remote desktop sharing session
- /session-connect: connect to a peer to peer remote desktop sharing session
- /session-disconnect: disconnect from a peer to peer remote desktop sharing session
- /session-end: end a peer to peer remote desktop sharing session
- /session-record: record a peer to peer remote desktop sharing session
- /session-transfer: transfer a peer to peer remote desktop sharing session
- /session-control: control a peer to peer remote desktop sharing session

"""

from __future__ import annotations

from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    handle_operations_error,
    tor_envelope,
)
from recorder import list_recordings, start_recording
from session import (
    agree_session,
    compress_session,
    connect_session,
    create_session,
    disconnect_session,
    end_session,
    find_session,
    record_session_event,
    transfer_session_metadata,
)
from sessionControl import get_session_control_for_route
from Viewer import peer_search, resolve_viewer
from operations_secrets import (
    resolve_operations_api_prefix,
    resolve_session_key_min_length,
    resolve_session_id_length,
    resolve_session_transfer_default_target,
)

SESSION_ROUTES: tuple[str, ...] = (
    "/session-create",
    "/session-find",
    "/session-connect",
    "/session-disconnect",
    "/session-end",
    "/session-record",
    "/session-transfer",
    "/session-control",
)

if BaseModel is not object:

    class SessionAuthPayload(BaseModel):
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="IDToken")

        model_config = {"populate_by_name": True}

    class SessionCreatePayload(SessionAuthPayload):
        pass

    class SessionFindPayload(BaseModel):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        user_id: str | None = Field(default=None, alias="UserID")

        model_config = {"populate_by_name": True}

    class SessionConnectPayload(SessionAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        session_key: str = Field(..., alias="sessionKey", min_length=resolve_session_key_min_length())

        model_config = {"populate_by_name": True}

    class SessionScopedPayload(SessionAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )

        model_config = {"populate_by_name": True}

    class SessionRecordPayload(SessionScopedPayload):
        action: str = Field(default="session-record")

    class SessionTransferPayload(BaseModel):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        target: str = Field(default_factory=resolve_session_transfer_default_target)

        model_config = {"populate_by_name": True}

    class SessionControlPayload(SessionScopedPayload):
        host_user_id: str | None = Field(default=None, alias="hostUserID")
        modification_request: dict[str, Any] | None = None


def _dispatch(route: str) -> Any:
    def handler(payload: Any = None) -> dict[str, Any]:
        try:
            if route == "/session-create":
                result = create_session(
                    host_user_id=payload.user_id,
                    id_token=payload.id_token,
                )
            elif route == "/session-find":
                if payload.user_id:
                    result = peer_search(
                        session_id=payload.session_id,
                        searcher_user_id=payload.user_id,
                    )
                else:
                    result = find_session(session_id=payload.session_id)
            elif route == "/session-connect":
                result = connect_session(
                    session_id=payload.session_id,
                    session_key=payload.session_key,
                    user_id=payload.user_id,
                    id_token=payload.id_token,
                )
                agree_session(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    id_token=payload.id_token,
                )
            elif route == "/session-disconnect":
                result = disconnect_session(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    id_token=payload.id_token,
                )
            elif route == "/session-end":
                result = end_session(
                    session_id=payload.session_id,
                    host_user_id=payload.user_id,
                    id_token=payload.id_token,
                )
                result["compression"] = compress_session(session_id=payload.session_id)
            elif route == "/session-record":
                record_session_event(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    action=payload.action,
                )
                recording = start_recording(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                )
                result = {
                    **recording,
                    "history_files": list_recordings(user_id=payload.user_id),
                }
            elif route == "/session-transfer":
                result = transfer_session_metadata(
                    session_id=payload.session_id,
                    target=payload.target,
                )
            elif route == "/session-control":
                host_id = payload.host_user_id or payload.user_id
                result = get_session_control_for_route(
                    session_id=payload.session_id,
                    host_user_id=host_id,
                    modification_request=payload.modification_request,
                )
                viewer = resolve_viewer(session_id=payload.session_id)
                result["viewer"] = viewer
            else:
                raise ValueError(f"Unsupported session route: {route}")
            return tor_envelope(route=route, subsystem="session-system", payload=result)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    return handler


def create_session_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create session routes")
    router = APIRouter(prefix=prefix, tags=["session-system"])

    @router.post("/session-create")
    def session_create(payload: SessionCreatePayload) -> dict[str, Any]:
        return _dispatch("/session-create")(payload)

    @router.post("/session-find")
    def session_find(payload: SessionFindPayload) -> dict[str, Any]:
        return _dispatch("/session-find")(payload)

    @router.post("/session-connect")
    def session_connect(payload: SessionConnectPayload) -> dict[str, Any]:
        return _dispatch("/session-connect")(payload)

    @router.post("/session-disconnect")
    def session_disconnect(payload: SessionScopedPayload) -> dict[str, Any]:
        return _dispatch("/session-disconnect")(payload)

    @router.post("/session-end")
    def session_end(payload: SessionScopedPayload) -> dict[str, Any]:
        return _dispatch("/session-end")(payload)

    @router.post("/session-record")
    def session_record(payload: SessionRecordPayload) -> dict[str, Any]:
        return _dispatch("/session-record")(payload)

    @router.post("/session-transfer")
    def session_transfer(payload: SessionTransferPayload) -> dict[str, Any]:
        return _dispatch("/session-transfer")(payload)

    @router.post("/session-control")
    def session_control(payload: SessionControlPayload) -> dict[str, Any]:
        return _dispatch("/session-control")(payload)

    return router


def register_session_routes(app: Any, *, api_prefix: str | None = None) -> None:
    prefix = api_prefix if api_prefix is not None else resolve_operations_api_prefix()
    app.include_router(create_session_router(prefix=prefix))
