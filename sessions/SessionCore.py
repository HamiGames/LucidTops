""" The core functions of the session system, including the purpose of the session system (peer to peer remote desktop sharing)
limitations:
- the session system is only used for peer to peer remote desktop sharing
- the session system is not used for any other purpose
- the session system is not used for any other application
- the session system is not used for any other system
- the session system is not used for any other network
- the session system is not used for any other internet
- the session system is not used for any other world
- the session system is not used for any other universe
- the Master server will only store the session records for the user and node respectively
- the session records will be stored in the blockchain system
- the session records will be stored in the history ledger system
- session keys will be created once the session record has bee compressed and awaiting DataInsert field for the next block in the blockchain system

- requirements:
- each session must have a unique session key (sessionID)
- the sessionID will be used to identify the session record in the blockchain system
- the sessionID will be used to identify the session record in the history ledger system
- the sessionID will be stored in node-operation-database and the master server database
- the sessionID must be valid and secure
- the sessionID will be shared between 2 or more users
- all sessionID's created will be recorded in the sessionID log (sessionID.log) on the master server database


 """ 

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sessions._common import (
    LEDGER_RECORDS_COLLECTION,
    SESSION_STATUSES,
    get_master_db,
    session_records_collection,
    utc_now,
    verify_user_id_token,
    with_mongo,
)
from sessions.sessionID import (
    generate_session_id,
    log_session_id,
    touch_session_id_log,
    validate_session_id,
)

SESSION_KEY_MIN_LENGTH = 16
SESSION_TYPE = "peer_remote_desktop"

SESSION_REQUIRED_FIELDS: tuple[str, ...] = (
    "sessionID",
    "sessionKey",
    "sessionData",
    "sessionStatus",
    "sessionType",
    "sessionTime",
    "sessionDate",
)


def _session_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _session_time() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def generate_session_key() -> str:
    return secrets.token_urlsafe(24)


def validate_session_key(session_key: str) -> bool:
    return bool(session_key and len(session_key.strip()) >= SESSION_KEY_MIN_LENGTH)


def _empty_session_record(
    *,
    session_id: str,
    session_key: str,
    host_user_id: str,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "sessionID": session_id,
        "sessionKey": session_key,
        "sessionData": {},
        "sessionStatus": "pending",
        "sessionType": SESSION_TYPE,
        "sessionTime": _session_time(),
        "sessionDate": _session_date(),
        "hostUserID": host_user_id,
        "viewerUserID": None,
        "userIDs": [host_user_id],
        "session_records": [
            {
                "record_index": 0,
                "userID": host_user_id,
                "role": "host",
                "action": "session-create",
                "timestamp": now,
            }
        ],
        "participant_agreements": {host_user_id: True},
        "all_agreed": False,
        "compressed": False,
        "aggregate_hash": None,
        "chunked_payload": None,
        "DataInsert": None,
        "created_at": now,
        "updated_at": now,
        "ended_at": None,
    }


def _validate_session_fields(record: dict[str, Any]) -> None:
    for field in SESSION_REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "":
            raise ValueError(f"Session field '{field}' is required and must be valid")
    if not validate_session_id(str(record["sessionID"])):
        raise ValueError("sessionID must be a valid 10-character identifier")
    if not validate_session_key(str(record["sessionKey"])):
        raise ValueError("sessionKey must be valid")
    if str(record.get("sessionStatus", "")) not in SESSION_STATUSES:
        raise ValueError("sessionStatus must be valid")
    user_ids = record.get("userIDs") or []
    if len(user_ids) < 2:
        raise ValueError("At least 2 UserIDs must be present in the session")
    session_records = record.get("session_records") or []
    if len(session_records) < 2:
        raise ValueError("At least 2 session records must be present in the session")


def can_commence_session(record: dict[str, Any]) -> bool:
    try:
        _validate_session_fields(record)
    except ValueError:
        return False
    agreements = record.get("participant_agreements") or {}
    user_ids = record.get("userIDs") or []
    return all(agreements.get(user_id) for user_id in user_ids)


@with_mongo
def create_session(*, host_user_id: str, id_token: str, client: Any) -> dict[str, Any]:
    if not host_user_id or not id_token:
        raise ValueError("host UserID and IDToken are required")
    if not verify_user_id_token(user_id=host_user_id, id_token=id_token, client=client):
        raise PermissionError("Host UserID authentication failed")

    session_id = generate_session_id(host_user_id=host_user_id)
    while session_records_collection(client).find_one({"sessionID": session_id}):
        session_id = generate_session_id(host_user_id=host_user_id)

    session_key = generate_session_key()
    record = _empty_session_record(
        session_id=session_id,
        session_key=session_key,
        host_user_id=host_user_id,
    )
    session_records_collection(client).insert_one(record)
    log_session_id(
        session_id=session_id,
        host_user_id=host_user_id,
        user_ids=record["userIDs"],
        status=record["sessionStatus"],
        client=client,
    )
    get_master_db(client).users.update_one(
        {"UserID": host_user_id},
        {"$set": {"last_session_ID": session_id, "updated_at": utc_now()}},
    )
    return {
        "sessionID": session_id,
        "sessionKey": session_key,
        "hostUserID": host_user_id,
        "sessionStatus": record["sessionStatus"],
    }


@with_mongo
def find_session(*, session_id: str, client: Any) -> dict[str, Any]:
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required for peer search")
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    return {
        "sessionID": record["sessionID"],
        "sessionStatus": record.get("sessionStatus"),
        "hostUserID": record.get("hostUserID"),
        "viewerUserID": record.get("viewerUserID"),
        "userIDs": record.get("userIDs", []),
        "participant_count": len(record.get("userIDs", [])),
        "all_agreed": record.get("all_agreed", False),
    }


@with_mongo
def connect_session(
    *,
    session_id: str,
    session_key: str,
    user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    if not validate_session_id(session_id) or not validate_session_key(session_key):
        raise ValueError("Valid sessionID and sessionKey are required")
    if not verify_user_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")

    record = session_records_collection(client).find_one(
        {"sessionID": session_id.strip(), "sessionKey": session_key.strip()}
    )
    if not record:
        raise LookupError("Session not found or sessionKey mismatch")

    user_ids = list(record.get("userIDs") or [])
    if user_id not in user_ids:
        user_ids.append(user_id)
    agreements = dict(record.get("participant_agreements") or {})
    agreements[user_id] = agreements.get(user_id, False)

    session_records = list(record.get("session_records") or [])
    session_records.append(
        {
            "record_index": len(session_records),
            "userID": user_id,
            "role": "participant",
            "action": "session-connect",
            "timestamp": utc_now(),
        }
    )

    viewer_user_id = user_id
    status_value = record.get("sessionStatus", "pending")
    if len(user_ids) >= 2:
        status_value = "active"

    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "userIDs": user_ids,
                "viewerUserID": viewer_user_id,
                "session_records": session_records,
                "participant_agreements": agreements,
                "sessionStatus": status_value,
                "updated_at": utc_now(),
            }
        },
    )
    touch_session_id_log(
        session_id=session_id,
        status=status_value,
        user_ids=user_ids,
        client=client,
    )
    updated = session_records_collection(client).find_one({"sessionID": session_id.strip()}) or {}
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "viewerUserID": viewer_user_id,
        "userIDs": updated.get("userIDs", user_ids),
        "sessionStatus": updated.get("sessionStatus", status_value),
        "can_commence": can_commence_session(updated),
    }


@with_mongo
def agree_session(*, session_id: str, user_id: str, id_token: str, client: Any) -> dict[str, Any]:
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if user_id not in (record.get("userIDs") or []):
        raise PermissionError("User is not a session participant")
    if not verify_user_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")

    agreements = dict(record.get("participant_agreements") or {})
    agreements[user_id] = True
    all_agreed = all(agreements.get(uid) for uid in record.get("userIDs") or [])
    status_value = (
        "active"
        if all_agreed and len(record.get("userIDs") or []) >= 2
        else record.get("sessionStatus", "pending")
    )

    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "participant_agreements": agreements,
                "all_agreed": all_agreed,
                "sessionStatus": status_value,
                "updated_at": utc_now(),
            }
        },
    )
    touch_session_id_log(session_id=session_id, status=status_value, client=client)
    updated = session_records_collection(client).find_one({"sessionID": session_id.strip()}) or record
    if all_agreed:
        _validate_session_fields(updated)
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "all_agreed": all_agreed,
        "can_commence": can_commence_session(updated),
        "sessionStatus": status_value,
    }


@with_mongo
def disconnect_session(
    *, session_id: str, user_id: str, id_token: str, client: Any
) -> dict[str, Any]:
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if not verify_user_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")

    user_ids = [uid for uid in (record.get("userIDs") or []) if uid != user_id]
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": {"userIDs": user_ids, "updated_at": utc_now()}},
    )
    touch_session_id_log(session_id=session_id, user_ids=user_ids, client=client)
    return {"sessionID": session_id.strip(), "userID": user_id, "disconnected": True}


@with_mongo
def end_session(*, session_id: str, host_user_id: str, id_token: str, client: Any) -> dict[str, Any]:
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if record.get("hostUserID") != host_user_id:
        raise PermissionError("Only the session host may end the session")
    if not verify_user_id_token(user_id=host_user_id, id_token=id_token, client=client):
        raise PermissionError("Host authentication failed")

    ended_at = utc_now()
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "sessionStatus": "ended",
                "ended_at": ended_at,
                "updated_at": ended_at,
            }
        },
    )
    touch_session_id_log(session_id=session_id, status="ended", client=client)
    return {"sessionID": session_id.strip(), "sessionStatus": "ended", "ended_at": ended_at}


@with_mongo
def record_session_event(
    *, session_id: str, user_id: str, action: str, client: Any
) -> dict[str, Any]:
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    session_records = list(record.get("session_records") or [])
    session_records.append(
        {
            "record_index": len(session_records),
            "userID": user_id,
            "action": action,
            "timestamp": utc_now(),
        }
    )
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": {"session_records": session_records, "updated_at": utc_now()}},
    )
    touch_session_id_log(session_id=session_id, client=client)
    return {"sessionID": session_id.strip(), "record_count": len(session_records)}


@with_mongo
def transfer_session_metadata(
    *, session_id: str, target: str, client: Any
) -> dict[str, Any]:
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if record.get("sessionStatus") != "compressed":
        raise ValueError("Session must be compressed before transfer")
    payload = {
        "sessionID": record.get("sessionID"),
        "aggregate_hash": record.get("aggregate_hash"),
        "target": target,
        "transferred_at": utc_now(),
    }
    get_master_db(client)[LEDGER_RECORDS_COLLECTION].insert_one(payload)
    return payload
