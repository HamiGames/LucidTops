""" the system for recording the Blocks in the blockchain system
ledger system:
- chain ledger_records live in the local chain DB (governance hashing only)
- public BlockID rows live in Master LucidTops_LedgerDB — genesis-only write from blockchain
- after genesis, Master/Node ledger append is owned by operations via ledger_doc transport
- the ledger can never be deleted or modified, it is a permanent record of the blockchain system
- the ledger will be visible to the public via the LucidLedger website (Master read-only)

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    BLOCK_ID_LEDGER_FIELDS,
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
    LEDGER_BLOCK_ID_COLLECTION,
    LEDGER_RECORDS_COLLECTION,
    LEDGER_RECORD_TYPES,
    LEDGER_RECORDS_FIELDS,
    schema_template,
)
from blockchain_secrets import resolve_lucid_ledger_list_limit  # noqa: E402
from configBlock import (  # noqa: E402
    assert_master_ledger_write_allowed,
    get_blockchain_db,
    get_master_ledger_db,
    get_mongo_client,
    utc_now,
)


class LedgerImmutableError(PermissionError):
    """Raised when a caller attempts to modify or delete ledger records."""


def _reject_ledger_mutation(operation: str) -> None:
    raise LedgerImmutableError(
        f"Ledger records cannot be {operation}; the ledger is a permanent append-only record"
    )


def ledger_record_template() -> dict[str, None]:
    """Return empty ledger record template from blockchain_schema."""
    return schema_template(LEDGER_RECORDS_FIELDS)


def block_id_ledger_template() -> dict[str, None]:
    """Return empty LucidTops_LedgerDB.BlockID document template."""
    return schema_template(BLOCK_ID_LEDGER_FIELDS)


def append_ledger_record(
    *,
    client: Any,
    session_id: str | None,
    aggregate_hash: str,
    record_type: str,
    block_id: str | None = None,
    new_block_id: str | None = None,
    creator_id: str | None = None,
) -> dict[str, Any]:
    """Append an immutable ledger_records row in the local chain DB."""
    if record_type not in LEDGER_RECORD_TYPES:
        raise ValueError(f"Unsupported ledger record_type: {record_type}")
    if not aggregate_hash or not str(aggregate_hash).strip():
        raise ValueError("aggregate_hash is required for ledger records")

    now = utc_now()
    record = {
        "sessionID": session_id,
        "BlockID": block_id,
        "New_BlockID": new_block_id,
        "creator_id": creator_id,
        "aggregate_hash": str(aggregate_hash).strip(),
        "hash_algorithm": HASH_ALGORITHM,
        "record_type": record_type,
        "created_at": now,
    }
    get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION].insert_one(record)
    record.pop("_id", None)
    return record


def build_block_id_ledger_doc(
    *,
    block_id: str,
    creator_id: str,
    creation_timestamp: str,
    rewards: int,
    last_block_id: str | None,
    session_data_count: int,
    new_block_id: str | None = None,
    session_id: str | None = None,
    status: str = "committed",
) -> dict[str, Any]:
    """Build Master/Node ledger payload without writing Mongo (ops transports post-genesis)."""
    if not block_id or not str(block_id).strip():
        raise ValueError("BlockID is required for ledger_doc")
    if not creator_id or not str(creator_id).strip():
        raise ValueError("creator_id is required for ledger_doc")
    return {
        "BlockID": str(block_id).strip(),
        "creator_id": str(creator_id).strip(),
        "creation_timestamp": str(creation_timestamp).strip(),
        "Rewards": int(rewards),
        "LastBlockID": last_block_id,
        "Session-data-count": int(session_data_count),
        "New_BlockID": new_block_id,
        "SessionID": session_id,
        "status": status,
        "committed_at": creation_timestamp,
    }


def append_block_id_ledger_master(
    *,
    client: Any,
    block_id: str,
    creator_id: str,
    creation_timestamp: str,
    rewards: int,
    last_block_id: str | None,
    session_data_count: int,
    new_block_id: str | None = None,
    session_id: str | None = None,
    status: str = "committed",
) -> dict[str, Any]:
    """
    Append BlockID to Master LucidTops_LedgerDB — genesis only.
    Raises if Master ledger write has been revoked.
    """
    assert_master_ledger_write_allowed(client=client)
    doc = build_block_id_ledger_doc(
        block_id=block_id,
        creator_id=creator_id,
        creation_timestamp=creation_timestamp,
        rewards=rewards,
        last_block_id=last_block_id,
        session_data_count=session_data_count,
        new_block_id=new_block_id,
        session_id=session_id,
        status=status,
    )
    collection = get_master_ledger_db(client)[LEDGER_BLOCK_ID_COLLECTION]
    existing = collection.find_one({"BlockID": doc["BlockID"]}, {"_id": 0})
    if existing is not None:
        return dict(existing)
    collection.insert_one(dict(doc))
    return doc


def append_block_id_ledger(
    *,
    client: Any,
    block_id: str,
    creator_id: str,
    creation_timestamp: str,
    rewards: int,
    last_block_id: str | None,
    session_data_count: int,
    new_block_id: str | None = None,
    session_id: str | None = None,
    status: str = "committed",
) -> dict[str, Any]:
    """
    Compatibility wrapper: builds ledger_doc only (no Master write).
    Post-genesis callers must not write Master ledger from blockchain.
    """
    del client  # payload-only; ops owns Master append
    return build_block_id_ledger_doc(
        block_id=block_id,
        creator_id=creator_id,
        creation_timestamp=creation_timestamp,
        rewards=rewards,
        last_block_id=last_block_id,
        session_data_count=session_data_count,
        new_block_id=new_block_id,
        session_id=session_id,
        status=status,
    )


def record_session_history(
    *,
    client: Any,
    session_id: str,
    aggregate_hash: str,
) -> dict[str, Any]:
    """Record compressed session history in the local chain ledger_records."""
    return append_ledger_record(
        client=client,
        session_id=session_id,
        aggregate_hash=aggregate_hash,
        record_type="session_history",
    )


def get_ledger_last_hash(*, client: Any) -> str:
    """Return the most recent chain ledger aggregate hash for the next block."""
    latest = (
        get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION]
        .find({}, {"aggregate_hash": 1, "_id": 0})
        .sort("created_at", -1)
        .limit(1)
    )
    for record in latest:
        value = record.get("aggregate_hash")
        if isinstance(value, str) and value:
            return value
    return str(GENESIS_PREVIOUS_HASH)


def get_ledger_record_for_block_creation(*, client: Any) -> dict[str, Any]:
    """Return chain ledger context required to create the next block."""
    ledger_last_hash = get_ledger_last_hash(client=client)
    latest = get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION].find_one(
        {},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    return {
        "ledger_last_hash": ledger_last_hash,
        "latest_record": latest,
        "hash_algorithm": HASH_ALGORITHM,
        "collection": LEDGER_RECORDS_COLLECTION,
    }


def get_ledger_records(
    *,
    client: Any,
    limit: int | None = None,
    record_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return chain ledger_records rows (internal audit)."""
    resolved_limit = resolve_lucid_ledger_list_limit() if limit is None else limit
    if resolved_limit <= 0:
        raise ValueError("limit must be positive")

    query: dict[str, Any] = {}
    if record_type:
        if record_type not in LEDGER_RECORD_TYPES:
            raise ValueError(f"Unsupported ledger record_type: {record_type}")
        query["record_type"] = record_type

    return list(
        get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(resolved_limit)
    )


def get_public_block_id_records(
    *,
    client: Any,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return public read-only Master LucidTops_LedgerDB.BlockID documents."""
    resolved_limit = resolve_lucid_ledger_list_limit() if limit is None else limit
    if resolved_limit <= 0:
        raise ValueError("limit must be positive")

    return list(
        get_master_ledger_db(client)[LEDGER_BLOCK_ID_COLLECTION]
        .find({}, {"_id": 0})
        .sort("creation_timestamp", -1)
        .limit(resolved_limit)
    )


def get_public_block_id_record(
    *,
    client: Any,
    block_id: str,
) -> dict[str, Any] | None:
    """Return one public Master BlockID ledger document (read-only)."""
    if not block_id or not str(block_id).strip():
        return None
    record = get_master_ledger_db(client)[LEDGER_BLOCK_ID_COLLECTION].find_one(
        {"BlockID": str(block_id).strip()},
        {"_id": 0},
    )
    return dict(record) if record else None


def update_ledger_record(*args: Any, **kwargs: Any) -> None:
    """Disallowed: ledger records are permanent and cannot be modified."""
    _reject_ledger_mutation("modified")


def delete_ledger_record(*args: Any, **kwargs: Any) -> None:
    """Disallowed: ledger records are permanent and cannot be deleted."""
    _reject_ledger_mutation("deleted")


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops immutable ledger system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser("append", help="Append a chain ledger record")
    append_parser.add_argument("--session-id", default=None)
    append_parser.add_argument("--aggregate-hash", required=True)
    append_parser.add_argument("--record-type", choices=list(LEDGER_RECORD_TYPES), required=True)

    subparsers.add_parser("last-hash", help="Print ledger last hash for block chaining")
    subparsers.add_parser("block-context", help="Print ledger context for next block creation")

    list_parser = subparsers.add_parser("list", help="List chain ledger_records")
    list_parser.add_argument("--limit", type=int, default=None)
    list_parser.add_argument("--record-type", choices=list(LEDGER_RECORD_TYPES), default=None)

    public_parser = subparsers.add_parser(
        "public-list", help="List Master LucidTops_LedgerDB.BlockID public ledger"
    )
    public_parser.add_argument("--limit", type=int, default=None)

    session_parser = subparsers.add_parser("session-history", help="Record session history")
    session_parser.add_argument("--session-id", required=True)
    session_parser.add_argument("--aggregate-hash", required=True)

    args = parser.parse_args()
    mongo = get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")

    try:
        if args.command == "append":
            result = append_ledger_record(
                client=mongo,
                session_id=args.session_id,
                aggregate_hash=args.aggregate_hash,
                record_type=args.record_type,
            )
        elif args.command == "last-hash":
            result = {"ledger_last_hash": get_ledger_last_hash(client=mongo)}
        elif args.command == "block-context":
            result = get_ledger_record_for_block_creation(client=mongo)
        elif args.command == "list":
            records = get_ledger_records(
                client=mongo,
                limit=args.limit,
                record_type=args.record_type,
            )
            result = {"records": records, "count": len(records)}
        elif args.command == "public-list":
            records = get_public_block_id_records(client=mongo, limit=args.limit)
            result = {"blocks": records, "records": records, "count": len(records)}
        elif args.command == "session-history":
            result = record_session_history(
                client=mongo,
                session_id=args.session_id,
                aggregate_hash=args.aggregate_hash,
            )
        else:
            raise ValueError(f"Unsupported command: {args.command}")

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        mongo.close()


if __name__ == "__main__":
    raise SystemExit(main())
