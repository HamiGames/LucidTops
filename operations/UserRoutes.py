""" the API routes for the user system (using FastAPI)
UserRoutes:
- /user-create: create a new user (links to frontend/register.js)
- /user-find: find a user (links to frontend/login.js)
- /user-connect: connect to a user (links to frontend/home_page.js)
- /user-disconnect: disconnect from a user (links to frontend/logout.js)
- /user-end: end a user (links to frontend/logout.js)
- /user-record: record a user (links to frontend/home_page.js)
- /user-report: report a user (links to frontend/home_page.js)
- /user-transfer: transfer a user (links to frontend/home_page.js)
- /user-control: control a user (links to frontend/home_page.js)
- /user-LucidLedger-read: read the LucidLedger system (links to frontend/home_page.js)
- /user-session-create: create a new session (links frontend/find-Peer.js to sessionRoutes.py)
- /user-session-find: find a session (links to sessionRoutes.py)
- /user-session-connect: connect to a session (links to sessionRoutes.py)
- /user-session-disconnect: disconnect from a session (links to sessionRoutes.py)
- /user-session-end: end a session (links to sessionRoutes.py)
- /user-session-record: record a session (links to sessionRoutes.py)
- /user-session-report: report a session (links to sessionRoutes.py)
- /user-session-transfer: transfer a session (links to sessionRoutes.py)
- /user-session-control: control a session (links to sessionRoutes.py)
- 
"""

from __future__ import annotations

import secrets
from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    LUCID_LEDGER_COLLECTION,
    get_master_db,
    get_mongo_client,
    handle_operations_error,
    tor_envelope,
    utc_now,
    verify_id_token,
)
from WebPageLink import frontend_link_for_api_route
from operations_secrets import (
    resolve_operations_api_prefix,
    resolve_operations_ledger_read_limit,
    resolve_session_id_length,
    resolve_session_key_min_length,
    resolve_user_register_javascript_source,
    resolve_user_session_transfer_default_target,
)
from session import (
    connect_session,
    create_session,
    disconnect_session,
    end_session,
    find_session,
    record_session_event,
    transfer_session_metadata,
)
from sessionControl import get_session_control_for_route

USER_ROUTES: tuple[str, ...] = (
    "/user-create",
    "/user-find",
    "/user-connect",
    "/user-disconnect",
    "/user-end",
    "/user-record",
    "/user-report",
    "/user-transfer",
    "/user-control",
    "/user-LucidLedger-read",
    "/user-session-create",
    "/user-session-find",
    "/user-session-connect",
    "/user-session-disconnect",
    "/user-session-end",
    "/user-session-record",
    "/user-session-report",
    "/user-session-transfer",
    "/user-session-control",
)


if BaseModel is not object:

    class UserAuthPayload(BaseModel):
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="IDToken")

        model_config = {"populate_by_name": True}

    class UserCreatePayload(BaseModel):
        email: str = Field(..., min_length=3)
        password: str = Field(..., min_length=8)
        source: str = Field(default_factory=resolve_user_register_javascript_source)

    class UserFindPayload(BaseModel):
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="IDToken")

        model_config = {"populate_by_name": True}

    class UserSessionConnectPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        session_key: str = Field(..., alias="sessionKey", min_length=resolve_session_key_min_length())

        model_config = {"populate_by_name": True}

    class UserSessionPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )

        model_config = {"populate_by_name": True}

    class UserSessionReportPayload(UserSessionPayload):
        report: str = Field(default="")


def _attach_frontend_link(result: dict[str, Any], route: str) -> None:
    """Attach Tor-compatible javascript frontend linkage when mapped for this route."""
    link = frontend_link_for_api_route(route)
    frontend = link.get("frontend")
    if frontend:
        result["frontend"] = frontend
    javascript = link.get("javascript")
    if javascript:
        result["javascript"] = javascript


def _user_handler(route: str, payload: Any) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        db = get_master_db(client)
        if route == "/user-create":
            existing = db.users.find_one({"email": payload.email})
            if existing:
                raise ValueError("User already exists")
            user_id = secrets.token_hex(4)
            id_token = secrets.token_urlsafe(32)
            now = utc_now()
            db.users.insert_one(
                {
                    "UserID": user_id,
                    "IDToken": id_token,
                    "email": payload.email,
                    "password": payload.password,
                    "created_at": now,
                    "updated_at": now,
                    "source": payload.source,
                }
            )
            result = {"UserID": user_id, "IDToken": id_token, "status": "created"}
        elif route == "/user-find":
            if not verify_id_token(
                user_id=payload.user_id, id_token=payload.id_token, client=client
            ):
                raise PermissionError("User authentication failed")
            user = db.users.find_one({"UserID": payload.user_id}) or {}
            result = {
                "UserID": payload.user_id,
                "email": user.get("email"),
                "tier": user.get("tier"),
                "status": "found",
            }
        elif route in {"/user-connect", "/user-record", "/user-report", "/user-transfer", "/user-control"}:
            if not verify_id_token(
                user_id=payload.user_id, id_token=payload.id_token, client=client
            ):
                raise PermissionError("User authentication failed")
            result = {
                "UserID": payload.user_id,
                "action": route.lstrip("/"),
                "status": "ok",
            }
        elif route in {"/user-disconnect", "/user-end"}:
            result = {
                "UserID": payload.user_id,
                "action": route.lstrip("/"),
                "status": "disconnected",
            }
        elif route == "/user-LucidLedger-read":
            if not verify_id_token(
                user_id=payload.user_id, id_token=payload.id_token, client=client
            ):
                raise PermissionError("User authentication failed")
            records = list(
                db[LUCID_LEDGER_COLLECTION].find({}, {"_id": 0}).limit(
                    resolve_operations_ledger_read_limit()
                )
            )
            result = {"UserID": payload.user_id, "records": records, "count": len(records)}
        elif route == "/user-session-create":
            result = create_session(
                host_user_id=payload.user_id,
                id_token=payload.id_token,
            )
        elif route == "/user-session-find":
            result = find_session(session_id=payload.session_id)
        elif route == "/user-session-connect":
            result = connect_session(
                session_id=payload.session_id,
                session_key=payload.session_key,
                user_id=payload.user_id,
                id_token=payload.id_token,
            )
        elif route == "/user-session-disconnect":
            result = disconnect_session(
                session_id=payload.session_id,
                user_id=payload.user_id,
                id_token=payload.id_token,
            )
        elif route == "/user-session-end":
            result = end_session(
                session_id=payload.session_id,
                host_user_id=payload.user_id,
                id_token=payload.id_token,
            )
        elif route == "/user-session-record":
            result = record_session_event(
                session_id=payload.session_id,
                user_id=payload.user_id,
                action="user-session-record",
            )
        elif route == "/user-session-report":
            result = record_session_event(
                session_id=payload.session_id,
                user_id=payload.user_id,
                action=f"report:{getattr(payload, 'report', '')}",
            )
        elif route == "/user-session-transfer":
            result = transfer_session_metadata(
                session_id=payload.session_id,
                target=resolve_user_session_transfer_default_target(),
            )
        elif route == "/user-session-control":
            result = get_session_control_for_route(
                session_id=payload.session_id,
                host_user_id=payload.user_id,
            )
        else:
            raise ValueError(f"Unsupported user route: {route}")

        _attach_frontend_link(result, route)
        return tor_envelope(route=route, subsystem="user-system", payload=result)
    finally:
        client.close()


def create_user_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create user routes")
    router = APIRouter(prefix=prefix, tags=["user-system"])

    @router.post("/user-create")
    def user_create(payload: UserCreatePayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-create", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-find")
    def user_find(payload: UserFindPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-find", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-connect")
    def user_connect(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-connect", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-disconnect")
    def user_disconnect(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-disconnect", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-end")
    def user_end(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-end", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-record")
    def user_record(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-record", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-report")
    def user_report(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-report", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-transfer")
    def user_transfer(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-transfer", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-control")
    def user_control(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-control", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-LucidLedger-read")
    def user_lucid_ledger_read(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-LucidLedger-read", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-create")
    def user_session_create(payload: UserAuthPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-create", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-find")
    def user_session_find(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-find", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-connect")
    def user_session_connect(payload: UserSessionConnectPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-connect", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-disconnect")
    def user_session_disconnect(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-disconnect", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-end")
    def user_session_end(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-end", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-record")
    def user_session_record(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-record", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-report")
    def user_session_report(payload: UserSessionReportPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-report", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-transfer")
    def user_session_transfer(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-transfer", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/user-session-control")
    def user_session_control(payload: UserSessionPayload) -> dict[str, Any]:
        try:
            return _user_handler("/user-session-control", payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    return router


def register_user_routes(app: Any, *, api_prefix: str | None = None) -> None:
    prefix = api_prefix if api_prefix is not None else resolve_operations_api_prefix()
    app.include_router(create_user_router(prefix=prefix))
