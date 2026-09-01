""" The compression protocol and requuirements for the process of compressing the session data and transferring it to the blockchain system
compression protocol:
- session data must be compressed using a sha512 hash function
- all session fields must be valid and present in the session data
- the compression process will be performed on the master server database or NodeUser
- the completion of a compression will generate a TaskToken and added to the tally record system
- the sessionID is the returned value recieved by the UserID's that participated in the session

limitations:
- the compression process is only used for the session system
- the compression process is not used for any other purpose
- the compression process is not used for any other application
- the compression process is not used for any other system
- the compression process is not used for any other network
- the compression process is not used for any other internet
- the compression process is not used for any other world
- the compression process is not used for any other universe

"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from ._common import (
    BLOCKCHAIN_BLOCKS_COLLECTION,
    HASH_ALGORITHM,
    LEDGER_RECORDS_COLLECTION,
    SESSION_KEYS_COLLECTION,
    TALLY_RECORDS_COLLECTION,
    TASK_TOKENS_COLLECTION,
    chunk_session_data,
    get_master_db,
    session_records_collection,
    utc_now,
    verify_chunk_hashes,
    with_mongo,
)
from .sessionID import touch_session_id_log, validate_session_id

TALLY_ENTITY_MASTER = "master_server"


def _generate_task_token(*, session_id: str, aggregate_hash: str) -> str:
    seed = f"{session_id}:{aggregate_hash}:{secrets.token_hex(16)}"
    return hashlib.sha512(seed.encode("utf-8")).hexdigest()


def _upsert_tally_task_token(
    *,
    db: Any,
    entity_type: str,
    entity_id: str,
    session_id: str,
    task_token: str,
) -> None:
    tally_col = db[TALLY_RECORDS_COLLECTION]
    tally_col.update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {
            "$set": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "sessionID": session_id,
                "sessionID_verified": True,
                "updated_at": utc_now(),
            },
            "$inc": {"tally_points": 1},
            "$addToSet": {"taskTokens": task_token},
            "$setOnInsert": {
                "created_at": utc_now(),
                "last_win_at": None,
                "last_reset_at": None,
            },
        },
        upsert=True,
    )


@with_mongo
def compress_session(
    *,
    session_id: str,
    entity_type: str = TALLY_ENTITY_MASTER,
    entity_id: str = "master_server",
    client: Any,
) -> dict[str, Any]:
    """Compress ended session data (SHA-512), issue TaskToken, and queue blockchain insert."""
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required for compression")

    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if record.get("sessionStatus") != "ended":
        raise ValueError("Session must have ended before compression can occur")
    if record.get("compressed"):
        return {
            "sessionID": session_id.strip(),
            "compressed": True,
            "aggregate_hash": record.get("aggregate_hash"),
            "sessionKey": record.get("sessionKey"),
        }

    record.pop("_id", None)
    chunked = chunk_session_data(record)
    if not verify_chunk_hashes(chunked):
        raise RuntimeError("Session compression verification failed")

    aggregate_hash = chunked["aggregate_hash"]
    now = utc_now()
    task_token = _generate_task_token(session_id=session_id.strip(), aggregate_hash=aggregate_hash)
    session_key = record.get("sessionKey")

    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "compressed": True,
                "sessionStatus": "compressed",
                "aggregate_hash": aggregate_hash,
                "chunked_payload": chunked,
                "DataInsert": aggregate_hash,
                "updated_at": now,
            }
        },
    )

    db = get_master_db(client)
    db[LEDGER_RECORDS_COLLECTION].insert_one(
        {
            "sessionID": session_id.strip(),
            "aggregate_hash": aggregate_hash,
            "hash_algorithm": HASH_ALGORITHM,
            "record_type": "session_history",
            "created_at": now,
        }
    )
    db[BLOCKCHAIN_BLOCKS_COLLECTION].insert_one(
        {
            "sessionID": session_id.strip(),
            "aggregate_hash": aggregate_hash,
            "hash_algorithm": HASH_ALGORITHM,
            "DataInsert": aggregate_hash,
            "status": "awaiting_block",
            "created_at": now,
        }
    )
    db[TASK_TOKENS_COLLECTION].insert_one(
        {
            "taskToken": task_token,
            "sessionID": session_id.strip(),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "aggregate_hash": aggregate_hash,
            "created_at": now,
        }
    )
    _upsert_tally_task_token(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        session_id=session_id.strip(),
        task_token=task_token,
    )
    db[SESSION_KEYS_COLLECTION].update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "sessionID": session_id.strip(),
                "sessionKey": session_key,
                "aggregate_hash": aggregate_hash,
                "DataInsert": aggregate_hash,
                "awaiting_block": True,
                "hash_algorithm": HASH_ALGORITHM,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    touch_session_id_log(session_id=session_id, status="compressed", client=client)

    return {
        "sessionID": session_id.strip(),
        "compressed": True,
        "aggregate_hash": aggregate_hash,
        "hash_algorithm": HASH_ALGORITHM,
        "taskToken": task_token,
        "sessionKey": session_key,
        "participantUserIDs": list(record.get("userIDs") or []),
    }
