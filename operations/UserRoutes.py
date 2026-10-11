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

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

"""

from __future__ import annotations

import hashlib
from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    OperatorAuthPayload,
    get_mongo_client,
    handle_operations_error,
    model_validator,
    operator_kwargs_from_payload,
    require_operations_operator,
    tor_envelope,
    user_accounts_collection,
    utc_now,
    verify_user_id_token,
)
from UserHandler import verify_user_credentials
from operations_secrets import (
    resolve_blockchain_hash_algorithm,
    resolve_blockchain_onion,
    resolve_lucid_ledger_collection,
    resolve_lucidtops_ledger_db_name,
    resolve_operations_api_prefix,
    resolve_operations_ledger_read_limit,
    resolve_secret,
    resolve_session_id_length,
    resolve_user_register_javascript_source,
    resolve_user_session_transfer_default_target,
)
from session import (
    connect_session,
    create_session,
    disconnect_session,
    find_session,
    mark_session_complete,
    record_session_event,
    transfer_session_metadata,
)
from session_to_block import process_complete_session_to_block
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

    class UserAuthPayload(OperatorAuthPayload):
        user_id: str = Field(..., alias="UserID")
        user_token_id: str = Field(..., alias="UserTokenID")

        model_config = {"populate_by_name": True}

    class LucidLedgerReadPayload(BaseModel):
        """Public ledger read — UserID + TokenID only (no operator gate)."""

        user_id: str = Field(..., alias="UserID")
        user_token_id: str | None = Field(default=None, alias="TokenID")
        token_id_alias: str | None = Field(default=None, alias="UserTokenID")

        model_config = {"populate_by_name": True}

        if model_validator is not None:

            @model_validator(mode="after")
            def _resolve_token(self) -> Any:
                resolved = (self.user_token_id or self.token_id_alias or "").strip()
                if not resolved:
                    raise ValueError("TokenID or UserTokenID required for LucidLedger read")
                object.__setattr__(self, "user_token_id", resolved)
                return self

    class UserCreatePayload(OperatorAuthPayload):
        email: str = Field(..., min_length=3)  # type: ignore[reportIncompatibleVariableOverride]
        password: str = Field(..., min_length=8)
        source: str = Field(default_factory=resolve_user_register_javascript_source)
        tier_selected: int | None = Field(default=None, alias="Tier_selected")
        max_sessions: int | None = Field(default=None, alias="max-sessions")

        model_config = {"populate_by_name": True}

    class UserFindPayload(OperatorAuthPayload):
        user_id: str = Field(..., alias="UserID")
        user_token_id: str = Field(..., alias="UserTokenID")

        model_config = {"populate_by_name": True}

    class UserSessionConnectPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        session_key: str | None = Field(default=None, alias="sessionKey")

        model_config = {"populate_by_name": True}

    class UserSessionPayload(UserAuthPayload):
        session_id: str = Field(
            ...,
            alias="sessionID",
            min_length=resolve_session_id_length(),
            max_length=resolve_session_id_length(),
        )
        session_settings: dict[str, Any] | None = Field(default=None, alias="Session_settings")

        model_config = {"populate_by_name": True}

    class UserSessionReportPayload(UserSessionPayload):
        report: str = Field(default_factory=str)


def _hash_user_value(value: str) -> str:
    return hashlib.new(resolve_blockchain_hash_algorithm(), value.encode("utf-8")).hexdigest()


def _attach_frontend_link(result: dict[str, Any], route: str) -> None:
    """GUI linkage uses FRONTEND_GUI_PREFIX. Page files are not appended here."""
    del route
    gui_prefix = resolve_secret("FRONTEND_GUI_PREFIX") or resolve_secret("GUI_PREFIX")
    if gui_prefix:
        result["gui_prefix"] = gui_prefix


def _user_handler(route: str, payload: Any) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        # Public ledger read: UserID/TokenID only — no operations operator gate.
        if route == "/user-LucidLedger-read":
            token_id = getattr(payload, "user_token_id", None) or getattr(
                payload, "token_id_alias", None
            )
            if not verify_user_id_token(
                user_id=payload.user_id,
                token_id=token_id,
                client=client,
            ):
                raise PermissionError("UserID / TokenID verification failed")
            ledger_db = client.ledger()
            ledger_collection = resolve_lucid_ledger_collection()
            records = list(
                ledger_db[ledger_collection]
                .find({}, {"_id": 0})
                .sort("creation_timestamp", -1)
                .limit(resolve_operations_ledger_read_limit())
            )
            result = {
                "UserID": payload.user_id,
                "blocks": records,
                "records": records,
                "count": len(records),
                "surface": "public_ledger",
                "read_only": True,
                "LucidTops_LedgerDB": resolve_lucidtops_ledger_db_name(),
                "ledger_collection": ledger_collection,
                "blockchain_onion": resolve_blockchain_onion() or None,
            }
            _attach_frontend_link(result, route)
            return tor_envelope(route=route, subsystem="user-system", payload=result)

        operator = require_operations_operator(
            client=client,
            **operator_kwargs_from_payload(payload),
        )
        users = user_accounts_collection(client)

        if route == "/user-create":
            email_hash = _hash_user_value(payload.email)
            existing = users.find_one({"$or": [{"Email": email_hash}, {"email": payload.email}]})
            if existing:
                raise ValueError("User already exists")
            import secrets as _secrets

            user_id = _secrets.token_hex(8)
            token_id = _secrets.token_urlsafe(32)
            now = utc_now()
            tier = getattr(payload, "tier_selected", None)
            users.insert_one(
                {
                    "UserID": user_id,
                    "TokenID": token_id,
                    "Email": email_hash,
                    "Password": _hash_user_value(payload.password),
                    "Tier_selected": tier,
                    "session-count": 0,
                    "max-sessions": getattr(payload, "max_sessions", None),
                    "created_at": now,
                    "updated_at": now,
                    "source": payload.source,
                    "created_by": {
                        operator["id_type"]: operator["operator_id"],
                    },
                }
            )
            result = {"UserID": user_id, "TokenID": token_id, "status": "created"}
        elif route == "/user-find":
            verified = verify_user_credentials(
                user_id=payload.user_id,
                token_id=payload.user_token_id,
                client=client,
            )
            result = {
                **verified,
                "operator_id": operator["operator_id"],
                "id_type": operator["id_type"],
            }
        elif route in {"/user-connect", "/user-record", "/user-report", "/user-transfer", "/user-control"}:
            if not verify_user_id_token(
                user_id=payload.user_id,
                token_id=payload.user_token_id,
                client=client,
            ):
                raise PermissionError("UserID / TokenID verification failed")
            result = {
                "UserID": payload.user_id,
                "action": route.lstrip("/"),
                "status": "ok",
                "operator_id": operator["operator_id"],
            }
        elif route in {"/user-disconnect", "/user-end"}:
            result = {
                "UserID": payload.user_id,
                "action": route.lstrip("/"),
                "status": "disconnected",
                "operator_id": operator["operator_id"],
            }
        elif route == "/user-session-create":
            if not verify_user_id_token(
                user_id=payload.user_id,
                token_id=payload.user_token_id,
                client=client,
            ):
                raise PermissionError("UserID / TokenID verification failed")
            result = create_session(
                host_user_id=payload.user_id,
                id_token=payload.user_token_id,
                client=client,
            )
        elif route == "/user-session-find":
            result = find_session(session_id=payload.session_id, client=client)
        elif route == "/user-session-connect":
            result = connect_session(
                session_id=payload.session_id,
                session_key=payload.session_key,
                user_id=payload.user_id,
                id_token=payload.user_token_id,
                client=client,
            )
        elif route == "/user-session-disconnect":
            result = disconnect_session(
                session_id=payload.session_id,
                user_id=payload.user_id,
                id_token=payload.user_token_id,
                client=client,
            )
        elif route == "/user-session-end":
            mark_session_complete(session_id=payload.session_id, client=client)
            result = process_complete_session_to_block(
                session_id=payload.session_id,
                client=client,
                **operator_kwargs_from_payload(payload),
            )
        elif route == "/user-session-record":
            result = record_session_event(
                session_id=payload.session_id,
                user_id=payload.user_id,
                action="user-session-record",
                client=client,
            )
        elif route == "/user-session-report":
            result = record_session_event(
                session_id=payload.session_id,
                user_id=payload.user_id,
                action=f"report:{getattr(payload, 'report', '')}",
                client=client,
            )
        elif route == "/user-session-transfer":
            result = transfer_session_metadata(
                session_id=payload.session_id,
                target=resolve_user_session_transfer_default_target(),
                client=client,
            )
        elif route == "/user-session-control":
            result = get_session_control_for_route(
                session_id=payload.session_id,
                host_user_id=payload.user_id,
                initial_settings=getattr(payload, "session_settings", None),
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
    def user_lucid_ledger_read(payload: LucidLedgerReadPayload) -> dict[str, Any]:
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
