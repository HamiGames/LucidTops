"""Session complete → chunks → blockchain governance create → ops-only ledger append.

Transforms SessionID_status:"complete" session-data into chunks for packeting
into New_BlockID via the blockchain container (DockerDNS). Blockchain writes
the local chain only and returns ledger_doc. Operations alone appends
ledger_doc into LucidTops_LedgerDB and {ID}_LedgerDB with parity validation
(no overwrite; post-genesis Master/Node append is ops-only).

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
    chunk_session_data,
    get_master_db,
    require_operations_operator,
    utc_now,
    verify_chunk_hashes,
    with_mongo,
)
from blockchain_client import call_blockchain_create
from operations_secrets import (
    node_ledger_db_name_for_id,
    resolve_blockchain_hash_algorithm,
    resolve_blockchain_onion,
    resolve_lucid_ledger_collection,
    resolve_lucidtops_ledger_db_name,
    resolve_lucidtops_sessions_collection,
    resolve_lucidtops_sessions_db_name,
    resolve_node_ledger_last_block_field,
    resolve_session_complete_status,
)

# Fields that must match between Master LucidTops_LedgerDB and NodeID_LedgerDB.
_LEDGER_PARITY_FIELDS: tuple[str, ...] = (
    "BlockID",
    "creator_id",
    "creation_timestamp",
    "Rewards",
    "LastBlockID",
    "Session-data-count",
)


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


def _actor_for_operator(operator: dict[str, Any]) -> tuple[str, str | None]:
    """Map operations operator to blockchain create actor_type / node_user_id."""
    id_type = str(operator.get("id_type") or "").strip().lower()
    operator_id = str(operator.get("operator_id") or "").strip()
    if id_type in {"nodeid", "node_id", "node_user", "nodeuser"}:
        return "node_user", operator_id
    return "master_server", None


def _ledger_doc_from_create_result(
    *,
    creation: dict[str, Any],
    session_id: str,
    chunked: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    ledger_doc = creation.get("ledger_doc")
    if isinstance(ledger_doc, dict) and ledger_doc.get("BlockID"):
        doc = dict(ledger_doc)
        doc.setdefault("SessionID", session_id)
        doc.setdefault("Session-data-count", int(chunked.get("chunk_count") or 0))
        return doc

    block_id = str(creation.get("BlockID") or creation.get("blockID") or "")
    if not block_id:
        raise RuntimeError("blockchain create did not return BlockID for ledger transport")
    block = creation.get("block") or {}
    return {
        "BlockID": block_id,
        "New_BlockID": creation.get("New_BlockID") or block.get("New_BlockID"),
        "creator_id": creation.get("creator_id") or block.get("creator_id"),
        "creation_timestamp": block.get("confirmed_at")
        or block.get("created_at")
        or now,
        "Rewards": int(
            block.get("block_reward")
            or creation.get("lucid_tokens_minted")
            or 0
        ),
        "LastBlockID": block.get("previous_block_hash"),
        "Session-data-count": int(chunked.get("chunk_count") or 0),
        "SessionID": session_id,
        "status": "committed",
        "committed_at": now,
    }


def _parity_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for field in _LEDGER_PARITY_FIELDS:
        value = doc.get(field)
        if field == "creator_id" and isinstance(value, dict):
            # Normalize ops-style creator maps to a stable string for compare.
            snap[field] = sorted(f"{k}:{v}" for k, v in value.items())
        else:
            snap[field] = value
    return snap


def _validate_master_node_ledger_match(
    *,
    master_doc: dict[str, Any],
    node_doc: dict[str, Any],
) -> None:
    master_snap = _parity_snapshot(master_doc)
    node_snap = _parity_snapshot(node_doc)
    mismatches = [
        field
        for field in _LEDGER_PARITY_FIELDS
        if master_snap.get(field) != node_snap.get(field)
    ]
    if mismatches:
        raise RuntimeError(
            "LucidTops_LedgerDB and NodeID_LedgerDB parity validation failed for fields: "
            + ", ".join(mismatches)
        )


def _refuse_if_block_id_exists(collection: Any, *, block_id: str, store_label: str) -> None:
    existing = collection.find_one(
        {"$or": [{"BlockID": block_id}, {"blockID": block_id}]},
        {"_id": 1},
    )
    if existing:
        raise RuntimeError(
            f"BlockID already exists in {store_label} — append refused (no overwrite): "
            f"{block_id}"
        )


def transport_ledger_to_master_and_node(
    *,
    client: Any,
    ledger_doc: dict[str, Any],
    operator: dict[str, Any],
) -> dict[str, Any]:
    """
    Ops-only append of blockchain ledger_doc into Master LucidTops_LedgerDB and
    {ID}_LedgerDB (insert only; refuse if BlockID already present), then validate
    the two copies match. Does not write MasterServer LucidLedger/Blockchain
    collections — LucidTops_LedgerDB is the canonical Master ledger.
    """
    block_id = str(ledger_doc.get("BlockID") or "").strip()
    if not block_id:
        raise ValueError("ledger_doc.BlockID required for transport")

    now = utc_now()
    transport_doc = {
        **ledger_doc,
        "BlockID": block_id,
        "status": ledger_doc.get("status") or "committed",
        "committed_at": ledger_doc.get("committed_at") or now,
        "transported_at": now,
        "blockchain_onion": resolve_blockchain_onion() or None,
    }

    ledger_collection_name = resolve_lucid_ledger_collection()
    master_ledger = _ledger_db(client)[ledger_collection_name]
    _refuse_if_block_id_exists(
        master_ledger,
        block_id=block_id,
        store_label="LucidTops_LedgerDB",
    )
    master_ledger.insert_one(dict(transport_doc))

    last_field = resolve_node_ledger_last_block_field()
    node_ledger_name = node_ledger_db_name_for_id(operator["operator_id"])
    node_ledger = client[node_ledger_name]
    node_blocks = node_ledger["blocks"]
    node_block_id_coll = node_ledger[ledger_collection_name]
    _refuse_if_block_id_exists(
        node_blocks,
        block_id=block_id,
        store_label=f"{node_ledger_name}.blocks",
    )
    _refuse_if_block_id_exists(
        node_block_id_coll,
        block_id=block_id,
        store_label=f"{node_ledger_name}.{ledger_collection_name}",
    )
    node_blocks.insert_one(dict(transport_doc))
    node_block_id_coll.insert_one(dict(transport_doc))
    # LastBlockID pointer only — not BlockID history.
    node_ledger["ledger_meta"].update_one(
        {"_meta": True},
        {
            "$set": {
                last_field: block_id,
                "LastBlockID": block_id,
                "creator_id": transport_doc.get("creator_id"),
                "updated_at": now,
            }
        },
        upsert=True,
    )

    master_written = master_ledger.find_one({"BlockID": block_id}, {"_id": 0})
    node_written = node_block_id_coll.find_one({"BlockID": block_id}, {"_id": 0})
    if not master_written or not node_written:
        raise RuntimeError(
            "ledger transport incomplete — missing Master or NodeID_LedgerDB BlockID doc"
        )
    _validate_master_node_ledger_match(master_doc=master_written, node_doc=node_written)

    return {
        "BlockID": block_id,
        "LucidTops_LedgerDB": resolve_lucidtops_ledger_db_name(),
        "ledger_collection": ledger_collection_name,
        "NodeID_LedgerDB": node_ledger_name,
        "parity_validated": True,
        "ledger_doc": master_written,
        "append_only": True,
    }


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
    reported_memory_gb: int | None = None,
) -> dict[str, Any]:
    """
    Chunk complete session → blockchain governance create (DockerDNS local chain) →
    ops-only append ledger_doc to LucidTops_LedgerDB + {operator_id}_LedgerDB with
    parity validation.
    """
    chunk_result = convert_complete_session_to_chunks(session_id=session_id, client=client)
    chunked = chunk_result["chunked"]
    now = utc_now()
    actor_type, node_user_id = _actor_for_operator(operator)

    packet = [
        {
            "sessionID": session_id,
            "aggregate_hash": chunked.get("aggregate_hash"),
            "chunks": chunked.get("chunks") or [],
            "chunk_count": chunked.get("chunk_count"),
        }
    ]

    creation = call_blockchain_create(
        actor_type=actor_type,
        node_user_id=node_user_id,
        invoker=actor_type,
        reported_memory_gb=reported_memory_gb,
        packet=packet,
    )

    ledger_doc = _ledger_doc_from_create_result(
        creation=creation,
        session_id=session_id,
        chunked=chunked,
        now=now,
    )
    transport = transport_ledger_to_master_and_node(
        client=client,
        ledger_doc=ledger_doc,
        operator=operator,
    )

    block_id = transport["BlockID"]
    last_field = resolve_node_ledger_last_block_field()
    return {
        "New_BlockID": creation.get("New_BlockID"),
        "BlockID": block_id,
        "SessionID": session_id,
        "creator_id": ledger_doc.get("creator_id"),
        "NodeID_LedgerDB": transport["NodeID_LedgerDB"],
        last_field: block_id,
        "chunk_count": chunked.get("chunk_count"),
        "aggregate_hash": chunked.get("aggregate_hash"),
        "hash_algorithm": resolve_blockchain_hash_algorithm(),
        "status": "committed",
        "created_at": now,
        "parity_validated": True,
        "blockchain_onion": resolve_blockchain_onion() or None,
        "blockchain_create": {
            "block_hash": creation.get("block_hash"),
            "lucid_tokens_minted": creation.get("lucid_tokens_minted"),
            "actor_type": creation.get("actor_type"),
        },
        "ledger_doc": transport["ledger_doc"],
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
    reported_memory_gb: int | None = None,
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
        reported_memory_gb=reported_memory_gb,
    )
