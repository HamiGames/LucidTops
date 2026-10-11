"""Session records on LucidTops sessions database. No sessions package import.

session requirements:
- sessionID: 10 characters (unique)
- 2 or more UserID's must be present in the session data
-2 or more session records must be present in the session 
- the session data must be compressed using a sha512 hash function
- the session must have ended before compression can occur
- SessionID_status:"complete" is required before session-data chunking into New_BlockID
- the session must have a valid sessionID
- the session must have a valid sessionKey 
- all fields in the session must be complete and valid
- the session will not comence without an agreement from all participants
- the session will not comence without a valid sessionID
- the entering of a session must use a sessionID via the search peer function

limitations:
- the session will not comence without a valid sessionID
- the session will not comence without a valid sessionKey
- the session will not comence without a valid sessionData
- the session will not comence without a valid sessionStatus
- the session will not comence without a valid sessionType
- the session will not comence without a valid sessionTime
- the session will not comence without a valid sessionDate
- the session will not comence without 2 or more UserID's
- New_BlockID creation requires SessionID_status complete (operations/session_to_block.py)

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

"""

from __future__ import annotations

import secrets
from typing import Any

from _common import utc_now, with_mongo
from operations_secrets import (
    resolve_session_complete_status,
    resolve_session_id_length,
    resolve_session_key_min_length,
    resolve_session_required_fields,
    resolve_session_statuses,
    resolve_lucidtops_sessions_collection,
)

SESSION_ID_LENGTH = 0
SESSION_KEY_MIN_LENGTH = 0


def _session_id_length() -> int:
    return resolve_session_id_length()


def _key_min_length() -> int:
    return resolve_session_key_min_length()


def session_records(client: Any) -> Any:
    return client.sessions()[resolve_lucidtops_sessions_collection()]


def session_query(session_id: str) -> dict[str, Any]:
    text = str(session_id).strip()
    clauses: list[dict[str, Any]] = [{"sessionID": text}, {"SessionID": text}]
    if text.isdigit():
        clauses.append({"SessionID": int(text)})
    return {"$or": clauses}


def session_status_value(record: dict[str, Any]) -> str:
    return str(
        record.get("SessionID_status")
        or record.get("sessionStatus")
        or record.get("session_status")
        or record.get("status")
        or ""
    ).strip()


def host_user_id(record: dict[str, Any]) -> str:
    return str(
        record.get("Host_UserID") or record.get("hostUserID") or record.get("UserID") or ""
    ).strip()


def validate_session_id(session_id: str) -> bool:
    text = str(session_id or "").strip()
    return text.isdigit() and len(text) == _session_id_length()


def generate_session_id() -> str:
    length = _session_id_length()
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_session_key() -> str:
    return secrets.token_urlsafe(_key_min_length())


def validate_session_key(session_key: str) -> bool:
    return len(str(session_key or "")) >= _key_min_length()


def _public_session(record: dict[str, Any]) -> dict[str, Any]:
    session_id = str(record.get("sessionID") or record.get("SessionID") or "")
    status = session_status_value(record)
    body = {key: value for key, value in record.items() if key != "_id"}
    body["sessionID"] = session_id
    body["SessionID"] = session_id
    body["sessionStatus"] = status
    body["SessionID_status"] = status
    body["Host_UserID"] = host_user_id(record)
    body["hostUserID"] = host_user_id(record)
    return body


@with_mongo
def create_session(
    *,
    host_user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    del id_token
    collection = session_records(client)
    session_id = generate_session_id()
    while collection.find_one(session_query(session_id), {"_id": 1}):
        session_id = generate_session_id()
    session_key = generate_session_key()
    now = utc_now()
    record = {
        "sessionID": session_id,
        "SessionID": session_id,
        "sessionKey": session_key,
        "sessionData": "",
        "sessionStatus": "pending",
        "SessionID_status": "pending",
        "sessionType": "peer_remote_desktop",
        "sessionTime": now,
        "sessionDate": now,
        "hostUserID": host_user_id,
        "Host_UserID": host_user_id,
        "UserID": host_user_id,
        "userIDs": [host_user_id],
        "created_at": now,
        "updated_at": now,
    }
    missing = [field for field in resolve_session_required_fields() if not record.get(field)]
    if missing:
        raise ValueError("session record missing required fields: " + ", ".join(missing))
    collection.insert_one(dict(record))
    return _public_session(record)


@with_mongo
def find_session(*, session_id: str, client: Any) -> dict[str, Any]:
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required")
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    return _public_session(record)


@with_mongo
def connect_session(
    *,
    session_id: str,
    session_key: str | None,
    user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    del id_token
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    stored_key = str(record.get("sessionKey") or "")
    if stored_key:
        if not session_key or session_key != stored_key or not validate_session_key(session_key):
            raise PermissionError("sessionKey does not match the session record")
    participants = list(record.get("userIDs") or [])
    if user_id and user_id not in participants:
        participants.append(user_id)
    now = utc_now()
    session_records(client).update_one(
        session_query(session_id),
        {
            "$set": {
                "userIDs": participants,
                "viewerUserID": user_id if user_id != host_user_id(record) else record.get("viewerUserID"),
                "Viewer_UserID": user_id if user_id != host_user_id(record) else record.get("Viewer_UserID"),
                "sessionStatus": "active",
                "SessionID_status": "active",
                "updated_at": now,
            }
        },
    )
    updated = session_records(client).find_one(session_query(session_id)) or record
    return _public_session(updated)


@with_mongo
def agree_session(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    del id_token
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    agreed = list(record.get("agreed_userIDs") or [])
    if user_id and user_id not in agreed:
        agreed.append(user_id)
    session_records(client).update_one(
        session_query(session_id),
        {"$set": {"agreed_userIDs": agreed, "updated_at": utc_now()}},
    )
    return {"sessionID": session_id.strip(), "SessionID": session_id.strip(), "agreed_userIDs": agreed}


@with_mongo
def disconnect_session(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    del id_token
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    ended = list(record.get("ended_peers") or [])
    if user_id and user_id not in ended:
        ended.append(user_id)
    session_records(client).update_one(
        session_query(session_id),
        {"$set": {"ended_peers": ended, "updated_at": utc_now()}},
    )
    return {
        "sessionID": session_id.strip(),
        "SessionID": session_id.strip(),
        "status": "disconnected",
        "userID": user_id,
    }


def handoff_status_allowed(status: str) -> bool:
    complete = resolve_session_complete_status()
    configured = set(resolve_session_statuses())
    configured.add(complete)
    if status in {"pending", "active"}:
        return False
    return status in configured


@with_mongo
def mark_session_complete(*, session_id: str, client: Any) -> dict[str, Any]:
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    complete = resolve_session_complete_status()
    now = utc_now()
    session_records(client).update_one(
        session_query(session_id),
        {
            "$set": {
                "sessionStatus": complete,
                "SessionID_status": complete,
                "updated_at": now,
            }
        },
    )
    updated = session_records(client).find_one(session_query(session_id)) or record
    return _public_session(updated)


@with_mongo
def record_session_event(
    *,
    session_id: str,
    user_id: str,
    action: str,
    client: Any,
) -> dict[str, Any]:
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    events = list(record.get("events") or [])
    events.append({"userID": user_id, "action": action, "timestamp": utc_now()})
    session_records(client).update_one(
        session_query(session_id),
        {"$set": {"events": events, "updated_at": utc_now()}},
    )
    return {"sessionID": session_id.strip(), "SessionID": session_id.strip(), "event_count": len(events)}


@with_mongo
def transfer_session_metadata(
    *,
    session_id: str,
    target: str,
    client: Any,
) -> dict[str, Any]:
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    session_records(client).update_one(
        session_query(session_id),
        {"$set": {"transfer_target": target, "updated_at": utc_now()}},
    )
    return {
        "sessionID": session_id.strip(),
        "SessionID": session_id.strip(),
        "target": target,
        "status": "transferred",
    }


def can_commence_session(record: dict[str, Any]) -> bool:
    required = resolve_session_required_fields()
    if any(not record.get(field) for field in required):
        return False
    participants = list(record.get("userIDs") or [])
    return len(participants) >= 2 and session_status_value(record) in set(resolve_session_statuses())


def end_session(*, session_id: str, host_user_id: str, id_token: str, client: Any | None = None) -> dict[str, Any]:
    """Local status update. Does not POST back to operations."""
    del host_user_id, id_token
    return mark_session_complete(session_id=session_id, client=client)


def compress_session(*, session_id: str, client: Any | None = None, **_ignored: Any) -> dict[str, Any]:
    """Compatibility name. Chunking is session_to_block, not a second handoff POST."""
    del client, _ignored
    return {
        "sessionID": str(session_id).strip(),
        "SessionID": str(session_id).strip(),
        "compressed": False,
        "note": "chunk/New_BlockID performed by operations session_to_block only",
    }


__all__ = (
    "agree_session",
    "can_commence_session",
    "compress_session",
    "connect_session",
    "create_session",
    "disconnect_session",
    "end_session",
    "find_session",
    "generate_session_id",
    "generate_session_key",
    "handoff_status_allowed",
    "host_user_id",
    "mark_session_complete",
    "record_session_event",
    "session_query",
    "session_records",
    "session_status_value",
    "transfer_session_metadata",
    "validate_session_id",
    "validate_session_key",
)
