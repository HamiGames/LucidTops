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


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    OperatorAuthPayload,
    get_mongo_client,
    handle_operations_error,
    operator_kwargs_from_payload,
    require_operations_operator,
    tor_envelope,
)
from UserHandler import verify_user_credentials
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
from session_to_block import process_complete_session_to_block
from Viewer import peer_search, resolve_viewer
from operations_secrets import (
    resolve_operations_api_prefix,
    resolve_session_key_min_length,
    resolve_session_id_length,
    resolve_session_record_default_action,
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

    class SessionAuthPayload(OperatorAuthPayload):
        user_id: str = Field(..., alias="UserID")
        user_token_id: str = Field(..., alias="UserTokenID")

        model_config = {"populate_by_name": True}

    class SessionCreatePayload(SessionAuthPayload):
        pass

    class SessionFindPayload(OperatorAuthPayload):
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
        action: str = Field(default_factory=resolve_session_record_default_action)

    class SessionTransferPayload(OperatorAuthPayload):
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


def _require_operator_and_user(payload: Any, client: Any) -> dict[str, Any]:
    operator = require_operations_operator(
        client=client,
        **operator_kwargs_from_payload(payload),
    )
    user_id = getattr(payload, "user_id", None)
    user_token = getattr(payload, "user_token_id", None)
    user = None
    if user_id and user_token:
        user = verify_user_credentials(
            user_id=user_id,
            token_id=user_token,
            client=client,
        )
    return {"operator": operator, "user": user}


def _dispatch(route: str) -> Any:
    def handler(payload: Any = None) -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            raise RuntimeError("Master server database is unavailable")
        try:
            auth = _require_operator_and_user(payload, client)
            if route == "/session-create":
                result = create_session(
                    host_user_id=payload.user_id,
                    id_token=payload.user_token_id,
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
                    id_token=payload.user_token_id,
                )
                agree_session(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    id_token=payload.user_token_id,
                )
            elif route == "/session-disconnect":
                result = disconnect_session(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    id_token=payload.user_token_id,
                )
            elif route == "/session-end":
                result = end_session(
                    session_id=payload.session_id,
                    host_user_id=payload.user_id,
                    id_token=payload.user_token_id,
                )
                result["compression"] = compress_session(session_id=payload.session_id)
                try:
                    result["new_block"] = process_complete_session_to_block(
                        session_id=payload.session_id,
                        client=client,
                        **operator_kwargs_from_payload(payload),
                    )
                except ValueError:
                    # Session may not yet be marked complete in DB; compression still returned.
                    result["new_block"] = None
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
            result["operator_id"] = auth["operator"]["operator_id"]
            result["id_type"] = auth["operator"]["id_type"]
            return tor_envelope(route=route, subsystem="session-system", payload=result)
        except Exception as exc:
            handle_operations_error(exc)
            raise
        finally:
            client.close()

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
