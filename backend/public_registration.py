"""Public User and NodeUser registration and login.

Registration accepts email, password, and console hardware. It does not accept a
TokenID and it does not call derive_user_and_node_ids. The MasterServer creates
UserID and TokenID and stores them in LucidTopsUserDB. Login rejects a request
that has no TokenID. A presented TokenID is the API key and is looked up in
LucidTopsUserDB.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from config import get_config_value_optional, get_mongo_client, utc_now
from fastapi import HTTPException, Request, status

_HARDWARE_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("HOSTNAME_CONSOLE", ("HOSTNAME_CONSOLE", "hostname")),
    ("HOST_MACHINE_ID", ("HOST_MACHINE_ID", "machine_id")),
    ("HARDWARE_PRIMARY_MAC", ("HARDWARE_PRIMARY_MAC", "mac", "primary_mac")),
    ("HARDWARE_PRIMARY_IP", ("HARDWARE_PRIMARY_IP", "primary_ip", "ip")),
    ("HARDWARE_PRIMARY_IFACE", ("HARDWARE_PRIMARY_IFACE", "iface", "primary_iface")),
)


def _user_db_name() -> str:
    return (
        get_config_value_optional("LUCIDTOPS_USER_DB_NAME")
        or get_config_value_optional("LUCIDTOPSUSERDB_NAME")
        or "LucidTopsUserDB"
    )


def _user_collection_name() -> str:
    return get_config_value_optional("USER_DB_COLLECTION") or "UserID"


def _node_db_name() -> str:
    return (
        get_config_value_optional("LUCIDTOPS_NODE_DB_NAME")
        or get_config_value_optional("LUCIDTOPSNODEDB_NAME")
        or "LucidTopsNodeDB"
    )


def _node_collection_name() -> str:
    return get_config_value_optional("NODE_DB_COLLECTION") or "NodeID"


def user_accounts(client: Any) -> Any:
    return client[_user_db_name()][_user_collection_name()]


def node_accounts(client: Any) -> Any:
    return client[_node_db_name()][_node_collection_name()]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _field(body: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = body.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _hardware(body: dict[str, Any]) -> dict[str, str]:
    pulled: dict[str, str] = {}
    missing: list[str] = []
    for canonical, aliases in _HARDWARE_FIELDS:
        value = _field(body, *aliases)
        if not value:
            missing.append(canonical)
        else:
            pulled[canonical] = value
    if missing:
        raise ValueError(
            "registration criteria are not satisfied; missing "
            + ", ".join(missing)
        )
    return pulled


def _registration_docs(email_hash: str, password_hash: str, hardware: dict[str, str]) -> str:
    document = {
        "Email": email_hash,
        "Password": password_hash,
        **hardware,
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return _sha256(encoded)


def find_user_by_email(client: Any, email: str) -> dict[str, Any] | None:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    email_hash = _sha256(normalized)
    record = user_accounts(client).find_one(
        {
            "$or": [
                {"Email": email_hash},
                {"Email": normalized},
                {"email": normalized},
            ]
        }
    )
    return record if isinstance(record, dict) else None


def find_user_by_token(client: Any, token_id: str) -> dict[str, Any] | None:
    token = str(token_id or "").strip()
    if not token:
        return None
    record = user_accounts(client).find_one(
        {"$or": [{"TokenID": token}, {"IDToken": token}]}
    )
    if not isinstance(record, dict):
        return None
    stored = str(record.get("TokenID") or record.get("IDToken") or "")
    if not stored or not secrets.compare_digest(token, stored):
        return None
    return record


def find_node_by_token(client: Any, token_id: str) -> dict[str, Any] | None:
    token = str(token_id or "").strip()
    if not token:
        return None
    record = node_accounts(client).find_one(
        {"$or": [{"TokenID": token}, {"IDToken": token}]}
    )
    if not isinstance(record, dict):
        return None
    stored = str(record.get("TokenID") or record.get("IDToken") or "")
    if not stored or not secrets.compare_digest(token, stored):
        return None
    return record


def find_node_for_user(client: Any, user_id: str) -> dict[str, Any] | None:
    cleaned = str(user_id or "").strip()
    if not cleaned:
        return None
    record = node_accounts(client).find_one({"UserID": cleaned})
    return record if isinstance(record, dict) else None


def _password_matches(record: dict[str, Any], password: str) -> bool:
    stored = str(record.get("Password") or record.get("password") or "")
    if not stored:
        return False
    hashed = _sha256(password)
    if secrets.compare_digest(hashed, stored):
        return True
    return secrets.compare_digest(password, stored)


def _require_email_password(body: dict[str, Any]) -> tuple[str, str]:
    email = _normalize_email(_field(body, "Email", "email"))
    password = _field(body, "Password", "password")
    if "@" not in email or len(email) < 3:
        raise ValueError("registration criteria are not satisfied; Email is required")
    if len(password) < 8:
        raise ValueError("registration criteria are not satisfied; Password is required")
    return email, password


def _mint_ids() -> tuple[str, str]:
    """Create a UserID and TokenID at time of operation. Never derived from API_KEY."""
    return secrets.token_hex(8), secrets.token_urlsafe(32)


def _insert_user(
    client: Any,
    *,
    email: str,
    password: str,
    hardware: dict[str, str],
) -> dict[str, str]:
    email_hash = _sha256(email)
    password_hash = _sha256(password)
    user_id, token_id = _mint_ids()
    now = utc_now()
    user_accounts(client).insert_one(
        {
            "UserID": user_id,
            "TokenID": token_id,
            "Email": email_hash,
            "Password": password_hash,
            "registration_docs": _registration_docs(email_hash, password_hash, hardware),
            **hardware,
            "created_at": now,
            "updated_at": now,
        }
    )
    return {"UserID": user_id, "TokenID": token_id}


def _insert_node(
    client: Any,
    *,
    user_id: str,
    token_id: str,
    email: str,
    hardware: dict[str, str],
    password_hash: str,
) -> str:
    node_id = secrets.token_hex(8)
    now = utc_now()
    email_hash = _sha256(email)
    node_accounts(client).insert_one(
        {
            "NodeID": node_id,
            "UserID": user_id,
            "TokenID": token_id,
            "Email": email_hash,
            "timestamp": now,
            "NodeID_UserDB_name": f"{node_id}_UserDB",
            "NodeID_LedgerDB_name": f"{node_id}_LedgerDB",
            "NodeID_LucidTokens": 0,
            "Registered_MAC_IDs": hardware["HARDWARE_PRIMARY_MAC"],
            "status": "registered",
            "registration_docs": _registration_docs(email_hash, password_hash, hardware),
        }
    )
    return node_id


def register_public_user(body: dict[str, Any], *, client: Any | None = None) -> dict[str, str]:
    """Create a UserID and TokenID when the email is not already in LucidTopsUserDB."""
    email, password = _require_email_password(body)
    hardware = _hardware(body)
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        if find_user_by_email(mongo, email):
            raise ValueError("User already exists")
        created = _insert_user(mongo, email=email, password=password, hardware=hardware)
        return {**created, "status": "created"}
    finally:
        if client is None:
            mongo.close()


def register_public_node(body: dict[str, Any], *, client: Any | None = None) -> dict[str, str]:
    """Create a NodeID. Mint UserID and TokenID only when that person is not already stored."""
    email, password = _require_email_password(body)
    hardware = _hardware(body)
    linked_user_id = _field(body, "UserID", "user_id")
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        existing = find_user_by_email(mongo, email)
        if existing:
            user_id = str(existing.get("UserID") or "").strip()
            token_id = str(existing.get("TokenID") or existing.get("IDToken") or "").strip()
            if not user_id or not token_id:
                raise ValueError("registration criteria are not satisfied")
            if linked_user_id and linked_user_id != user_id:
                raise ValueError("UserID does not match the registered email")
            if not _password_matches(existing, password):
                raise PermissionError("Password does not match the registered User")
            if find_node_for_user(mongo, user_id):
                raise ValueError("NodeUser already exists")
            password_hash = _sha256(password)
            node_id = _insert_node(
                mongo,
                user_id=user_id,
                token_id=token_id,
                email=email,
                hardware=hardware,
                password_hash=password_hash,
            )
            return {
                "UserID": user_id,
                "TokenID": token_id,
                "NodeID": node_id,
                "status": "created",
            }
        created = _insert_user(mongo, email=email, password=password, hardware=hardware)
        node_id = _insert_node(
            mongo,
            user_id=created["UserID"],
            token_id=created["TokenID"],
            email=email,
            hardware=hardware,
            password_hash=_sha256(password),
        )
        return {**created, "NodeID": node_id, "status": "created"}
    finally:
        if client is None:
            mongo.close()


def _presented_token(body: dict[str, Any]) -> str:
    token = _field(body, "api_key", "apiKey", "TokenID", "IDToken", "tokenId")
    if not token:
        raise PermissionError("login without a TokenID is rejected")
    return token


def login_public_user(body: dict[str, Any], *, client: Any | None = None) -> dict[str, str]:
    """Accept login only when TokenID matches a LucidTopsUserDB document."""
    token = _presented_token(body)
    password = _field(body, "Password", "password")
    if not password:
        raise ValueError("Password is required")
    email = _normalize_email(_field(body, "Email", "email"))
    claimed_user = _field(body, "UserID", "user_id")
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        from handshake import validate_api_key

        if not validate_api_key(token, client=mongo):
            raise PermissionError("TokenID was not accepted")
        user = find_user_by_token(mongo, token)
        if user is None:
            raise PermissionError("TokenID was not found in LucidTopsUserDB")
        user_id = str(user.get("UserID") or "").strip()
        if claimed_user and claimed_user != user_id:
            raise PermissionError("UserID does not match TokenID")
        if email:
            stored_email = str(user.get("Email") or user.get("email") or "")
            if stored_email and stored_email not in {email, _sha256(email)}:
                raise PermissionError("Email does not match TokenID")
        if not _password_matches(user, password):
            raise PermissionError("Password does not match the registered User")
        return {"UserID": user_id, "TokenID": token, "status": "accepted"}
    finally:
        if client is None:
            mongo.close()


def login_public_node(body: dict[str, Any], *, client: Any | None = None) -> dict[str, str]:
    """Accept NodeUser login only when TokenID is already stored for that NodeID."""
    token = _presented_token(body)
    password = _field(body, "Password", "password")
    if not password:
        raise ValueError("Password is required")
    claimed_node = _field(body, "NodeID", "node_id")
    if not claimed_node:
        raise PermissionError("login without a NodeID is rejected")
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        from handshake import validate_api_key

        if not validate_api_key(token, client=mongo):
            raise PermissionError("TokenID was not accepted")
        user = find_user_by_token(mongo, token)
        if user is None:
            raise PermissionError("TokenID was not found in LucidTopsUserDB")
        if not _password_matches(user, password):
            raise PermissionError("Password does not match the registered User")
        node = node_accounts(mongo).find_one({"NodeID": claimed_node})
        if not isinstance(node, dict):
            raise PermissionError("NodeID was not found")
        stored = str(node.get("TokenID") or node.get("IDToken") or "")
        if not stored or not secrets.compare_digest(token, stored):
            raise PermissionError("TokenID does not match NodeID")
        user_id = str(user.get("UserID") or "").strip()
        return {
            "UserID": user_id,
            "TokenID": token,
            "NodeID": claimed_node,
            "status": "accepted",
        }
    finally:
        if client is None:
            mongo.close()


def _json_body(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be an object")
    return payload


def _public_error(exc: Exception) -> None:
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


async def public_register_endpoint(request: Request) -> dict[str, str]:
    try:
        return register_public_user(_json_body(await request.json()))
    except Exception as exc:
        _public_error(exc)
        raise


async def public_node_register_endpoint(request: Request) -> dict[str, str]:
    try:
        return register_public_node(_json_body(await request.json()))
    except Exception as exc:
        _public_error(exc)
        raise


async def public_login_endpoint(request: Request) -> dict[str, str]:
    try:
        return login_public_user(_json_body(await request.json()))
    except Exception as exc:
        _public_error(exc)
        raise


async def public_node_login_endpoint(request: Request) -> dict[str, str]:
    try:
        return login_public_node(_json_body(await request.json()))
    except Exception as exc:
        _public_error(exc)
        raise
