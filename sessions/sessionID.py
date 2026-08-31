"""
this is the protocol for creating a unique session ID for the session system using the Session API route
session ID protocol:
- the session ID will be created using a sha512 hash function to produce a 10 digit session id consisting of 0-9 and a-z
- the session ID will be returned to the user via the API route
- the session ID will be used to find a peer to peer remote desktop sharing session via the API route using the find-peer GUI
- the session ID will be used to create a new session connection via the API route using the connect-handshake GUI

the sessionID will be generated for every new session creation request (new session creation request will be recorded in the sessionID log (sessionID.log) on the master server database)
all un-finalised sessions will be recorded in the sessionID log (sessionID.log) on the master server database and removed after 15 days of inactivity
all inactive sessionID's found in the tally system will flag the NodeUserID as fraudulent (NodeGov.py)

"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sessions._common import (
    SESSION_STATUSES,
    TALLY_RECORDS_COLLECTION,
    get_master_db,
    session_id_log_collection,
    utc_now,
    with_mongo,
)

SESSION_ID_LENGTH = 10
SESSION_ID_PATTERN = re.compile(r"^[0-9a-z]{10}$")
SESSION_ID_LOG_SOURCE = "sessionID.log"
SESSION_INACTIVITY_DAYS = 15
FINALISED_STATUSES = frozenset({"ended", "compressed"})


def generate_session_id(*, host_user_id: str, nonce: str | None = None) -> str:
    """Create a 10-character sessionID (0-9, a-z) from SHA-512."""
    seed = f"{host_user_id}:{nonce or secrets.token_hex(16)}:{utc_now()}"
    digest = hashlib.sha512(seed.encode("utf-8")).hexdigest()
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    value = int(digest, 16)
    chars: list[str] = []
    for _ in range(SESSION_ID_LENGTH):
        value, index = divmod(value, len(alphabet))
        chars.append(alphabet[index])
    return "".join(chars)


def validate_session_id(session_id: str) -> bool:
    return bool(session_id and SESSION_ID_PATTERN.fullmatch(session_id.strip()))


@with_mongo
def log_session_id(
    *,
    session_id: str,
    host_user_id: str,
    user_ids: list[str] | None = None,
    status: str = "pending",
    source: str = SESSION_ID_LOG_SOURCE,
    client: Any,
) -> dict[str, Any]:
    """Record a sessionID in the master server session_id_log collection."""
    if not validate_session_id(session_id):
        raise ValueError("sessionID must be a valid 10-character identifier")
    now = utc_now()
    entry = {
        "sessionID": session_id.strip(),
        "hostUserID": host_user_id,
        "userIDs": list(user_ids or [host_user_id]),
        "source": source,
        "status": status,
        "created_at": now,
        "recorded_at": now,
    }
    session_id_log_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": entry},
        upsert=True,
    )
    return entry


@with_mongo
def touch_session_id_log(
    *,
    session_id: str,
    status: str | None = None,
    user_ids: list[str] | None = None,
    client: Any,
) -> None:
    """Update activity timestamp for an existing sessionID log entry."""
    updates: dict[str, Any] = {"recorded_at": utc_now()}
    if status is not None:
        updates["status"] = status
    if user_ids is not None:
        updates["userIDs"] = user_ids
    session_id_log_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {"$set": updates},
    )


@with_mongo
def remove_stale_session_ids(*, client: Any) -> dict[str, Any]:
    """Remove un-finalised sessionID log entries inactive for 15 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=SESSION_INACTIVITY_DAYS)
    cutoff_iso = cutoff.isoformat()
    result = session_id_log_collection(client).delete_many(
        {
            "status": {"$nin": list(FINALISED_STATUSES)},
            "recorded_at": {"$lt": cutoff_iso},
        }
    )
    return {
        "removed_count": result.deleted_count,
        "inactivity_days": SESSION_INACTIVITY_DAYS,
        "cutoff": cutoff_iso,
    }


@with_mongo
def audit_inactive_tally_session_ids(*, client: Any) -> dict[str, Any]:
    """Flag NodeUserIDs linked to inactive tally sessionIDs (NodeGov.py)."""
    from NodeGov import NODE_GOV_AUDIT_COLLECTION, ban_node_user

    db = get_master_db(client)
    tally_col = db[TALLY_RECORDS_COLLECTION]
    flagged: list[dict[str, str]] = []

    for tally_record in tally_col.find({"sessionID": {"$exists": True, "$ne": None}}):
        session_id = str(tally_record.get("sessionID", "")).strip()
        if not validate_session_id(session_id):
            continue
        log_entry = session_id_log_collection(client).find_one({"sessionID": session_id})
        session_record = db.session_records.find_one({"sessionID": session_id})
        inactive = False
        if log_entry is None and session_record is None:
            inactive = True
        elif log_entry is not None:
            recorded_at = log_entry.get("recorded_at") or log_entry.get("created_at")
            if recorded_at:
                try:
                    recorded_dt = datetime.fromisoformat(str(recorded_at))
                    if recorded_dt.tzinfo is None:
                        recorded_dt = recorded_dt.replace(tzinfo=timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(days=SESSION_INACTIVITY_DAYS)
                    inactive = recorded_dt < cutoff
                except ValueError:
                    inactive = True
        elif session_record is not None:
            status = str(session_record.get("sessionStatus", ""))
            inactive = status not in SESSION_STATUSES or status == "pending"

        if not inactive:
            continue

        entity_type = tally_record.get("entity_type")
        entity_id = tally_record.get("entity_id")
        if entity_type == "node_user" and entity_id:
            reason = f"Inactive sessionID in tally system: {session_id}"
            db[NODE_GOV_AUDIT_COLLECTION].insert_one(
                {
                    "NodeUserID": entity_id,
                    "action": "fraud_flag",
                    "reason": reason,
                    "sessionID": session_id,
                    "timestamp": utc_now(),
                }
            )
            tally_col.update_one(
                {"_id": tally_record["_id"]},
                {"$set": {"sessionID_verified": False, "updated_at": utc_now()}},
            )
            flagged.append({"NodeUserID": str(entity_id), "sessionID": session_id})
            if tally_record.get("sessionID_verified") is False:
                ban_node_user(entity_id, reason, client=client)

    return {"flagged_count": len(flagged), "flagged": flagged}
