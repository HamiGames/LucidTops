"""Session complete → chunks → New_BlockID → dual ledger update.

Transforms SessionID_status:"complete" session-data into chunks for packeting
into New_BlockID, then updates LucidTops_LedgerDB and {ID}_LedgerDB LastBlockID.

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
    BLOCKCHAIN_COLLECTION,
    LUCID_LEDGER_COLLECTION,
    chunk_session_data,
    get_master_db,
    require_operations_operator,
    utc_now,
    verify_chunk_hashes,
    with_mongo,
)
from operations_secrets import (
    node_ledger_db_name_for_id,
    resolve_blockchain_hash_algorithm,
    resolve_lucid_ledger_collection,
    resolve_lucidtops_ledger_db_name,
    resolve_lucidtops_sessions_collection,
    resolve_lucidtops_sessions_db_name,
    resolve_node_ledger_last_block_field,
    resolve_session_complete_status,
)


def _hash_new_block_id(material: bytes, *, algorithm: str) -> str:
    try:
        return hashlib.new(algorithm, material).hexdigest()
    except ValueError as exc:
        raise RuntimeError(
            f"BLOCKCHAIN_HASH_ALGORITHM unsupported at time of operation: {algorithm}"
        ) from exc


def _sessions_collection(client: Any) -> Any:
    return client[resolve_lucidtops_sessions_db_name()][
        resolve_lucidtops_sessions_collection()
    ]


def _ledger_db(client: Any) -> Any:
    return client[resolve_lucidtops_ledger_db_name()]


def _find_complete_session(client: Any, session_id: str) -> dict[str, Any]:
    complete = resolve_session_complete_status()
    collection = _sessions_collection(client)
    record = collection.find_one(
        {
            "$or": [
                {"SessionID": session_id},
                {"sessionID": session_id},
            ]
        }
    )
    if not record:
        # Fall back to master session records collection name from secrets.
        master = get_master_db(client)
        record = master[resolve_lucidtops_sessions_collection()].find_one(
            {
                "$or": [
                    {"SessionID": session_id},
                    {"sessionID": session_id},
                ]
            }
        )
    if not record:
        raise LookupError(f"SessionID not found: {session_id}")

    status_value = str(
        record.get("SessionID_status")
        or record.get("session_status")
        or record.get("status")
        or ""
    ).strip()
    if status_value != complete:
        raise ValueError(
            f"SessionID_status must be {complete!r} before chunking "
            f"(got {status_value!r})"
        )
    return record


def _session_payload_for_chunking(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload.pop("_id", None)
    return payload


@with_mongo
def convert_complete_session_to_chunks(
    *,
    session_id: str,
    client: Any,
) -> dict[str, Any]:
    record = _find_complete_session(client, session_id)
    chunked = chunk_session_data(_session_payload_for_chunking(record))
    if not verify_chunk_hashes(chunked):
        raise RuntimeError("session chunk hash verification failed")
    return {
        "SessionID": session_id,
        "SessionID_status": resolve_session_complete_status(),
        "chunked": chunked,
    }


@with_mongo
def create_new_block_from_session(
    *,
    session_id: str,
    operator: dict[str, Any],
    client: Any,
) -> dict[str, Any]:
    """
    Load complete session chunks into New_BlockID creation, write LucidTops_LedgerDB,
    and update {operator_id}_LedgerDB LastBlockID.
    """
    chunk_result = convert_complete_session_to_chunks(session_id=session_id, client=client)
    chunked = chunk_result["chunked"]
    algorithm = resolve_blockchain_hash_algorithm()
    now = utc_now()
    creator_id = {
        operator["id_type"]: operator["operator_id"],
    }
    material = (
        f"{session_id}:{chunked['aggregate_hash']}:{operator['operator_id']}:{now}"
    ).encode("utf-8")
    new_block_id = _hash_new_block_id(material, algorithm=algorithm)

    block_doc = {
        "New_BlockID": new_block_id,
        "BlockID": new_block_id,
        "SessionID": session_id,
        "SessionID_status": resolve_session_complete_status(),
        "creator_id": creator_id,
        "chunks": chunked,
        "aggregate_hash": chunked["aggregate_hash"],
        "hash_algorithm": algorithm,
        "created_at": now,
        "status": "ledger_pending",
    }

    ledger_db = _ledger_db(client)
    ledger_collection = ledger_db[resolve_lucid_ledger_collection()]
    ledger_collection.update_one(
        {"BlockID": new_block_id},
        {
            "$set": {
                **block_doc,
                "status": "committed",
                "committed_at": now,
            }
        },
        upsert=True,
    )

    # Also mirror into master DB ledger collection when configured separately.
    master = get_master_db(client)
    master[LUCID_LEDGER_COLLECTION].update_one(
        {"BlockID": new_block_id},
        {"$set": {**block_doc, "status": "committed", "committed_at": now}},
        upsert=True,
    )
    master[BLOCKCHAIN_COLLECTION].update_one(
        {"BlockID": new_block_id},
        {"$set": {**block_doc, "status": "committed", "committed_at": now}},
        upsert=True,
    )

    last_field = resolve_node_ledger_last_block_field()
    node_ledger_name = node_ledger_db_name_for_id(operator["operator_id"])
    node_ledger = client[node_ledger_name]
    node_meta = node_ledger["ledger_meta"]
    node_meta.update_one(
        {"_meta": True},
        {
            "$set": {
                last_field: new_block_id,
                "LastBlockID": new_block_id,
                "creator_id": creator_id,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    node_ledger["blocks"].update_one(
        {"BlockID": new_block_id},
        {"$set": {**block_doc, "status": "committed", "committed_at": now}},
        upsert=True,
    )

    return {
        "New_BlockID": new_block_id,
        "BlockID": new_block_id,
        "SessionID": session_id,
        "creator_id": creator_id,
        "NodeID_LedgerDB": node_ledger_name,
        last_field: new_block_id,
        "chunk_count": chunked.get("chunk_count"),
        "aggregate_hash": chunked.get("aggregate_hash"),
        "status": "committed",
        "created_at": now,
    }


@with_mongo
def process_complete_session_to_block(
    *,
    session_id: str,
    node_id: str | None = None,
    admin_id: str | None = None,
    master_user_id: str | None = None,
    master_server_id: str | None = None,
    token_id: str,
    email: str | None = None,
    client: Any,
) -> dict[str, Any]:
    operator = require_operations_operator(
        node_id=node_id,
        admin_id=admin_id,
        master_user_id=master_user_id,
        master_server_id=master_server_id,
        token_id=token_id,
        email=email,
        client=client,
    )
    return create_new_block_from_session(
        session_id=session_id,
        operator=operator,
        client=client,
    )
