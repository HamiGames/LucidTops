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

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

 """ 

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from ._common import (
    complete_status_value,
    get_master_db,
    session_records_collection,
    session_statuses,
    utc_now,
    verify_user_id_token,
    with_mongo,
)
from .sessionID import (
    generate_session_id,
    log_session_id,
    resolve_session_key_min_length,
    resolve_session_key_urlsafe_bytes,
    resolve_session_type,
    touch_session_id_log,
    validate_session_id,
)

SESSION_REQUIRED_FIELDS: tuple[str, ...] = (
    "sessionID",
    "sessionKey",
    "sessionData",
    "sessionStatus",
    "sessionType",
    "sessionTime",
    "sessionDate",
)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_unlimited_max_sessions(max_sessions: Any) -> bool:
    if max_sessions is None:
        return True
    if isinstance(max_sessions, str) and max_sessions.strip().lower() in {
        "unlimited",
        "-1",
        "",
    }:
        return True
    try:
        return int(max_sessions) < 0
    except (TypeError, ValueError):
        return False


def _load_user_session_quota(*, user_id: str, client: Any) -> dict[str, Any]:
    """
    Resolve Tier_selected / session-count / max-sessions for UserID.
    Prefers LucidTopsUserDB.UserID, falls back to master users + tiers.
    """
    profile: dict[str, Any] = {}
    try:
        from config import get_config_value_optional

        user_db_name = get_config_value_optional("LUCIDTOPS_USER_DB_NAME") or (
            get_config_value_optional("LUCIDTOPSUSERDB_NAME") or "LucidTopsUserDB"
        )
        user_col_name = get_config_value_optional("USER_DB_COLLECTION") or "UserID"
        doc = client[user_db_name][user_col_name].find_one({"UserID": user_id})
        if doc:
            profile = dict(doc)
    except Exception:
        profile = {}

    master = get_master_db(client)
    user_doc = master.users.find_one({"UserID": user_id}) or {}
    if not profile:
        profile = dict(user_doc)

    tier_selected = profile.get("Tier_selected")
    if tier_selected is None:
        tier_selected = profile.get("tier")
    if tier_selected is None:
        tier_selected = user_doc.get("Tier_selected", user_doc.get("tier"))

    session_count = profile.get("session-count")
    if session_count is None:
        session_count = user_doc.get("session-count", 0)

    max_sessions = profile.get("max-sessions")
    if max_sessions is None:
        max_sessions = user_doc.get("max-sessions")

    if max_sessions is None or tier_selected is None:
        try:
            from Select_tier import retrieve_user_tier

            tier_rec = retrieve_user_tier(user_id, client=client) or {}
        except Exception:
            tier_rec = {}
        if tier_selected is None and tier_rec.get("tier") is not None:
            tier_selected = tier_rec.get("tier")
        if max_sessions is None:
            if tier_rec.get("unlimited_sessions"):
                max_sessions = None
            elif tier_rec.get("sessions_per_month") is not None:
                max_sessions = tier_rec.get("sessions_per_month")

    return {
        "Tier_selected": tier_selected,
        "session-count": _coerce_int(session_count, 0),
        "max-sessions": max_sessions,
    }


def _assert_session_create_auto_pass(*, user_id: str, client: Any) -> dict[str, Any]:
    """Auto-pass when Tier_selected is set and session-count < max-sessions."""
    quota = _load_user_session_quota(user_id=user_id, client=client)
    tier_selected = quota.get("Tier_selected")
    if tier_selected is None or str(tier_selected).strip() == "":
        raise PermissionError(
            "SessionID create requires Tier_selected on UserID profile (LucidTopsUserDB)"
        )
    session_count = _coerce_int(quota.get("session-count"), 0)
    max_sessions = quota.get("max-sessions")
    if not _is_unlimited_max_sessions(max_sessions):
        max_int = _coerce_int(max_sessions, 0)
        if session_count >= max_int:
            raise PermissionError(
                f"session-count {session_count} reached max-sessions {max_int} for UserID"
            )
    return quota


def _increment_user_session_count(*, user_id: str, client: Any) -> None:
    master = get_master_db(client)
    master.users.update_one(
        {"UserID": user_id},
        {
            "$inc": {"session-count": 1},
            "$set": {"updated_at": utc_now()},
            "$setOnInsert": {"UserID": user_id, "created_at": utc_now()},
        },
        upsert=True,
    )
    try:
        from config import get_config_value_optional

        user_db_name = get_config_value_optional("LUCIDTOPS_USER_DB_NAME") or (
            get_config_value_optional("LUCIDTOPSUSERDB_NAME") or "LucidTopsUserDB"
        )
        user_col_name = get_config_value_optional("USER_DB_COLLECTION") or "UserID"
        client[user_db_name][user_col_name].update_one(
            {"UserID": user_id},
            {
                "$inc": {"session-count": 1},
                "$set": {"updated_at": utc_now()},
            },
        )
    except Exception:
        pass


def _session_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _session_time() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def generate_session_key() -> str:
    return secrets.token_urlsafe(resolve_session_key_urlsafe_bytes())


def validate_session_key(session_key: str) -> bool:
    return bool(session_key and len(session_key.strip()) >= resolve_session_key_min_length())


def _empty_session_record(
    *,
    session_id: str,
    session_key: str,
    host_user_id: str,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "sessionID": session_id,
        "SessionID": int(session_id),
        "sessionKey": session_key,
        "sessionData": {},
        "sessionStatus": "pending",
        "SessionID_status": "pending",
        "sessionType": resolve_session_type(),
        "sessionTime": _session_time(),
        "sessionDate": _session_date(),
        "hostUserID": host_user_id,
        "viewerUserID": None,
        "userIDs": [host_user_id],
        "ended_peers": [],
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
        "operations_handoff": None,
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
        raise ValueError("sessionID must be a valid unique int(10)")
    if not validate_session_key(str(record["sessionKey"])):
        raise ValueError("sessionKey must be valid")
    status = str(record.get("sessionStatus", ""))
    if status not in session_statuses():
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
    """
    MasterServer creates SessionID for a UserID and inserts into LucidTops_SessionsDB.
    Allowed without Rdp (RDP.txt: creation-only exception).
    Auto-passes when Tier_selected is set and session-count < max-sessions.
    """
    if not host_user_id or not id_token:
        raise ValueError("host UserID and IDToken/TokenID are required")
    if not verify_user_id_token(user_id=host_user_id, id_token=id_token, client=client):
        raise PermissionError("Host UserID authentication failed")

    _assert_session_create_auto_pass(user_id=host_user_id, client=client)

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
    _increment_user_session_count(user_id=host_user_id, client=client)
    get_master_db(client).users.update_one(
        {"UserID": host_user_id},
        {"$set": {"last_session_ID": session_id, "updated_at": utc_now()}},
    )
    return {
        "sessionID": session_id,
        "SessionID": int(session_id),
        "sessionKey": session_key,
        "hostUserID": host_user_id,
        "sessionStatus": record["sessionStatus"],
        "SessionID_status": record["SessionID_status"],
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
        "SessionID": record.get("SessionID", int(record["sessionID"])),
        "sessionStatus": record.get("sessionStatus"),
        "SessionID_status": record.get("SessionID_status", record.get("sessionStatus")),
        "hostUserID": record.get("hostUserID"),
        "viewerUserID": record.get("viewerUserID"),
        "userIDs": record.get("userIDs", []),
        "participant_count": len(record.get("userIDs", [])),
        "all_agreed": record.get("all_agreed", False),
    }


@with_mongo
def validate_session_for_rdp(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    """Rdp validate path: SessionID + UserID + TokenID from Rdp container."""
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required")
    if not user_id.strip() or not id_token.strip():
        raise ValueError("UserID/TokenID missing for SessionID validation")
    if not verify_user_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("UserID/TokenID authentication failed")

    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")

    user_ids = list(record.get("userIDs") or [])
    is_participant = user_id in user_ids or user_id == record.get("hostUserID")
    return {
        "status": "validated",
        "session_id": session_id.strip(),
        "sessionID": session_id.strip(),
        "SessionID": int(session_id.strip()),
        "user_id": user_id,
        "UserID": user_id,
        "is_participant": is_participant,
        "sessionStatus": record.get("sessionStatus"),
        "SessionID_status": record.get("SessionID_status", record.get("sessionStatus")),
        "validated_at": utc_now(),
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
    """Peer connect — UserID/TokenID must be supplied via Rdp."""
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
    is_new_join = user_id not in user_ids
    if is_new_join:
        _assert_session_create_auto_pass(user_id=user_id, client=client)
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
                "SessionID_status": status_value,
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
    if is_new_join:
        _increment_user_session_count(user_id=user_id, client=client)
    updated = session_records_collection(client).find_one({"sessionID": session_id.strip()}) or {}
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "viewerUserID": viewer_user_id,
        "userIDs": updated.get("userIDs", user_ids),
        "sessionStatus": updated.get("sessionStatus", status_value),
        "SessionID_status": updated.get("SessionID_status", status_value),
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
                "SessionID_status": status_value,
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
        "SessionID_status": status_value,
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

    ended_peers = list(record.get("ended_peers") or [])
    if user_id not in ended_peers:
        ended_peers.append(user_id)

    user_ids = list(record.get("userIDs") or [])
    session_records = list(record.get("session_records") or [])
    session_records.append(
        {
            "record_index": len(session_records),
            "userID": user_id,
            "action": "session-disconnect",
            "timestamp": utc_now(),
        }
    )

    complete = complete_status_value()
    status_value = record.get("sessionStatus", "active")
    if user_ids and all(uid in ended_peers for uid in user_ids):
        status_value = complete
    elif user_id == record.get("hostUserID"):
        status_value = "ended"

    now = utc_now()
    updates: dict[str, Any] = {
        "ended_peers": ended_peers,
        "session_records": session_records,
        "sessionStatus": status_value,
        "SessionID_status": status_value,
        "updated_at": now,
    }
    if status_value in {complete, "ended"}:
        updates["ended_at"] = now

    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": updates},
    )
    touch_session_id_log(
        session_id=session_id,
        status=status_value,
        user_ids=user_ids,
        client=client,
    )
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "disconnected": True,
        "sessionStatus": status_value,
        "SessionID_status": status_value,
        "ended_peers": ended_peers,
    }


@with_mongo
def end_session(*, session_id: str, host_user_id: str, id_token: str, client: Any) -> dict[str, Any]:
    """
    End participation for the calling peer (host or viewer).
    SessionID_status becomes complete when all peers in userIDs have ended (fixes.txt §12.17).
    """
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if host_user_id not in (record.get("userIDs") or []) and record.get("hostUserID") != host_user_id:
        raise PermissionError("User is not a session participant")
    if not verify_user_id_token(user_id=host_user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")

    ended_peers = list(record.get("ended_peers") or [])
    if host_user_id not in ended_peers:
        ended_peers.append(host_user_id)

    user_ids = list(record.get("userIDs") or [])
    complete = complete_status_value()
    if user_ids and all(uid in ended_peers for uid in user_ids):
        status_value = complete
    else:
        status_value = "ended"

    ended_at = utc_now()
    session_records = list(record.get("session_records") or [])
    session_records.append(
        {
            "record_index": len(session_records),
            "userID": host_user_id,
            "action": "session-end",
            "timestamp": ended_at,
        }
    )
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "ended_peers": ended_peers,
                "session_records": session_records,
                "sessionStatus": status_value,
                "SessionID_status": status_value,
                "ended_at": ended_at,
                "updated_at": ended_at,
            }
        },
    )
    touch_session_id_log(session_id=session_id, status=status_value, client=client)
    result: dict[str, Any] = {
        "sessionID": session_id.strip(),
        "sessionStatus": status_value,
        "SessionID_status": status_value,
        "ended_at": ended_at,
        "ended_peers": ended_peers,
    }
    if status_value == complete:
        from .compress import handoff_complete_session_to_operations

        result["operations_handoff"] = handoff_complete_session_to_operations(
            session_id=session_id.strip(),
            client=client,
        )
    return result


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
    """
    Mark session metadata ready for operations transfer.
    Does not write ledger/blockchain (non-standard — operations only).
    """
    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    status = record.get("SessionID_status") or record.get("sessionStatus")
    complete = complete_status_value()
    if status not in {complete, "compressed"}:
        raise ValueError(
            f"Session must be {complete} before transfer metadata handoff to operations"
        )
    payload = {
        "sessionID": record.get("sessionID"),
        "SessionID": record.get("SessionID"),
        "target": target,
        "SessionID_status": status,
        "transferred_at": utc_now(),
        "operations_required": True,
    }
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": {"transfer_metadata": payload, "updated_at": utc_now()}},
    )
    return payload
