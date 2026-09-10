""" the distribution of the blockchain system 

Each need NodeDB created will host a updated (5 minute cycle) copy of the Ledger all block hashes in the ledger must align

this will ensure that the blockchain system is always up to date and that the blockchain system is always operational

the distribution of the blockchain system will be performed by the master server and the NodeUser

the core blockchain system will not be edited or changed after the initial setup.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    BLOCKCHAIN_BLOCKS_COLLECTION,
    LEDGER_RECORDS_COLLECTION,
)
from blockchain_secrets import (  # noqa: E402
    resolve_ledger_distribution_sync_seconds,
    resolve_ledger_replica_dir,
)
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402
from legder import get_ledger_last_hash  # noqa: E402

_DISTRIBUTION_STOP = threading.Event()
_DISTRIBUTION_THREAD: threading.Thread | None = None


def resolve_replica_dir() -> Path:
    path = resolve_ledger_replica_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_ledger_slice(*, client: Any, limit: int = 10_000) -> dict[str, Any]:
    """Export ledger records + confirmed block hashes for external replica."""
    db = get_blockchain_db(client)
    records = list(
        db[LEDGER_RECORDS_COLLECTION]
        .find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    blocks = list(
        db[BLOCKCHAIN_BLOCKS_COLLECTION]
        .find(
            {"status": {"$in": ["confirmed", "genesis"]}, "blockID": {"$ne": None}},
            {
                "_id": 0,
                "blockID": 1,
                "New_BlockID": 1,
                "block_hash": 1,
                "creator_id": 1,
                "status": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    last_hash = get_ledger_last_hash(client=client)
    last_block = blocks[0] if blocks else None
    return {
        "exported_at": utc_now(),
        "ledger_last_hash": last_hash,
        "LastBlockID": (last_block or {}).get("blockID"),
        "ledger_records": list(reversed(records)),
        "blocks": list(reversed(blocks)),
        "record_count": len(records),
        "block_count": len(blocks),
    }


def write_external_ledger_replica(*, client: Any) -> dict[str, Any]:
    """
    Write ledger slice to external LucidTopsBlockchain_Ledger path
    (from hardware pull / blockchain.secrets LEDGER_REPLICA_DIR).
    """
    replica_dir = resolve_replica_dir()
    payload = export_ledger_slice(client=client)
    ledger_file = replica_dir / "ledger_snapshot.json"
    last_block_file = replica_dir / "LastBlockID.txt"
    hashes_file = replica_dir / "block_hashes.jsonl"

    ledger_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    last_block_id = str(payload.get("LastBlockID") or "")
    last_block_file.write_text(last_block_id + ("\n" if last_block_id else ""), encoding="utf-8")

    with hashes_file.open("w", encoding="utf-8") as handle:
        for block in payload.get("blocks") or []:
            handle.write(json.dumps(block, sort_keys=True) + "\n")

    return {
        "synced": True,
        "replica_dir": replica_dir.as_posix(),
        "ledger_file": ledger_file.as_posix(),
        "last_block_file": last_block_file.as_posix(),
        "hashes_file": hashes_file.as_posix(),
        "LastBlockID": last_block_id,
        "ledger_last_hash": payload.get("ledger_last_hash"),
        "synced_at": payload.get("exported_at"),
    }


def sync_ledger_distribution(*, client: Any | None = None) -> dict[str, Any]:
    owns = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")
    try:
        return write_external_ledger_replica(client=mongo)
    finally:
        if owns and mongo is not None:
            mongo.close()


def _distribution_loop() -> None:
    interval = resolve_ledger_distribution_sync_seconds()
    while not _DISTRIBUTION_STOP.wait(interval):
        try:
            sync_ledger_distribution()
        except Exception:
            continue


def start_distribution_daemon() -> dict[str, Any]:
    """Start background ledger replica sync (interval from secrets, typically 300s)."""
    global _DISTRIBUTION_THREAD
    if _DISTRIBUTION_THREAD and _DISTRIBUTION_THREAD.is_alive():
        return {
            "started": False,
            "reason": "distribution daemon already running",
            "interval_seconds": resolve_ledger_distribution_sync_seconds(),
        }
    _DISTRIBUTION_STOP.clear()
    _DISTRIBUTION_THREAD = threading.Thread(
        target=_distribution_loop,
        name="blockchain-ledger-distribution",
        daemon=True,
    )
    _DISTRIBUTION_THREAD.start()
    return {
        "started": True,
        "interval_seconds": resolve_ledger_distribution_sync_seconds(),
        "replica_dir": resolve_replica_dir().as_posix(),
    }


def stop_distribution_daemon() -> dict[str, Any]:
    _DISTRIBUTION_STOP.set()
    return {"stopped": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops ledger distribution")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Write one external ledger replica snapshot")
    sub.add_parser("start", help="Start distribution daemon")
    sub.add_parser("stop", help="Stop distribution daemon")
    args = parser.parse_args()

    if args.command == "sync":
        result = sync_ledger_distribution()
    elif args.command == "start":
        result = start_distribution_daemon()
        # keep process alive briefly so daemon can be observed in CLI usage
        time.sleep(0.1)
    elif args.command == "stop":
        result = stop_distribution_daemon()
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
