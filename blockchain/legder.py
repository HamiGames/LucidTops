""" the system for recording the Blocks in the blockchain system
ledger system:
- the ledger system is used to record the Blocks in the blockchain system
- the ledger system is used to record the Blocks in the blockchain system by the master server
- the ledger system is used to record the Blocks in the blockchain system by the NodeUser
- the ledger system will return a ledger record that is used to create a new block in the blockchain system
- the ledger record will be included in the next block in the blockchain system
- the ledger last hash inserted into the will be use to create the next block in the blockchain system
- the ledger can never be deleted or modified, it is a permanent record of the blockchain system
- the ledger will be visible to the public via the LucidLedger website

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
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
    LEDGER_RECORDS_COLLECTION,
    LEDGER_RECORD_TYPES,
    LEDGER_RECORDS_FIELDS,
    schema_template,
)
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402

DEFAULT_LUCID_LEDGER_LIMIT = 100


class LedgerImmutableError(PermissionError):
    """Raised when a caller attempts to modify or delete ledger records."""


def _reject_ledger_mutation(operation: str) -> None:
    raise LedgerImmutableError(
        f"Ledger records cannot be {operation}; the ledger is a permanent append-only record"
    )


def ledger_record_template() -> dict[str, None]:
    """Return empty ledger record template from blockchain_schema."""
    return schema_template(LEDGER_RECORDS_FIELDS)


def append_ledger_record(
    *,
    client: Any,
    session_id: str | None,
    aggregate_hash: str,
    record_type: str,
) -> dict[str, Any]:
    """Append an immutable ledger record (append-only; never updated or deleted)."""
    if record_type not in LEDGER_RECORD_TYPES:
        raise ValueError(f"Unsupported ledger record_type: {record_type}")
    if not aggregate_hash or not str(aggregate_hash).strip():
        raise ValueError("aggregate_hash is required for ledger records")

    now = utc_now()
    record = {
        "sessionID": session_id,
        "aggregate_hash": str(aggregate_hash).strip(),
        "hash_algorithm": HASH_ALGORITHM,
        "record_type": record_type,
        "created_at": now,
    }
    get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION].insert_one(record)
    record.pop("_id", None)
    return record


def record_session_history(
    *,
    client: Any,
    session_id: str,
    aggregate_hash: str,
) -> dict[str, Any]:
    """Record compressed session history in the immutable ledger."""
    return append_ledger_record(
        client=client,
        session_id=session_id,
        aggregate_hash=aggregate_hash,
        record_type="session_history",
    )


def get_ledger_last_hash(*, client: Any) -> str:
    """Return the most recent ledger aggregate hash used to create the next block."""
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
    return GENESIS_PREVIOUS_HASH


def get_ledger_record_for_block_creation(*, client: Any) -> dict[str, Any]:
    """Return ledger context required to create the next block in the blockchain system."""
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
    limit: int = DEFAULT_LUCID_LEDGER_LIMIT,
    record_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return ledger records for public LucidLedger visibility."""
    if limit <= 0:
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
        .limit(limit)
    )


def update_ledger_record(*args: Any, **kwargs: Any) -> None:
    """Disallowed: ledger records are permanent and cannot be modified."""
    _reject_ledger_mutation("modified")


def delete_ledger_record(*args: Any, **kwargs: Any) -> None:
    """Disallowed: ledger records are permanent and cannot be deleted."""
    _reject_ledger_mutation("deleted")


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops immutable ledger system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser("append", help="Append a ledger record")
    append_parser.add_argument("--session-id", default=None)
    append_parser.add_argument("--aggregate-hash", required=True)
    append_parser.add_argument("--record-type", choices=list(LEDGER_RECORD_TYPES), required=True)

    subparsers.add_parser("last-hash", help="Print ledger last hash for block chaining")
    subparsers.add_parser("block-context", help="Print ledger context for next block creation")

    list_parser = subparsers.add_parser("list", help="List ledger records (LucidLedger public view)")
    list_parser.add_argument("--limit", type=int, default=DEFAULT_LUCID_LEDGER_LIMIT)
    list_parser.add_argument("--record-type", choices=list(LEDGER_RECORD_TYPES), default=None)

    session_parser = subparsers.add_parser("session-history", help="Record session history in the ledger")
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
