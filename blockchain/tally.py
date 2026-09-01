""" the rules and regulations for the tally system in the blockchain system
tally system:
- the tally system is used to determine the winner of the block creation process
- the tally system is used to determine the winner of the block creation process by the master server
- the tally system is used to determine the winner of the block creation process by the NodeUser
- the tally system is used to determine the winner of the block creation process by the User
- the tally system is used to determine the winner of the block creation process by the administrator
- the tally system is used to determine the winner of the block creation process by the system
- the tally system is used to determine the winner of the block creation process by the network
- the tally system is used to determine the winner of the block creation process by the internet
- the tally system is used to determine the winner of the block creation process by the world
- the tally system is used to determine the winner of the block creation process by the universe

- the tally is found in the shared database (seeded every 30seconds to all NodeUsers and MasterServer)
- each session data processed will add a tally point to the tally (tally.py) for the NodeUser, master server, AdminUser, and MasterClassUser who processed the session data
- each win in the tally system will reset the tally for the ID that created the block (block-smash.py)
- the tally system will be used to determine the winner of the block creation process by the master server ( must be verified against a sessionID log)
- 
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    SESSION_ID_LOG_COLLECTION,
    TALLY_ENTITY_TYPES,
    TALLY_RECORDS_COLLECTION,
    TALLY_RECORDS_FIELDS,
    TALLY_SYNC_COLLECTION,
    TALLY_SYNC_INTERVAL_SECONDS,
    schema_template,
)
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402

TALLY_PROCESSOR_ENTITY_TYPES: tuple[str, ...] = TALLY_ENTITY_TYPES
DEFAULT_TALLY_TARGET = "all"


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def verify_tally_session_id(*, client: Any, session_id: str | None) -> bool:
    """Verify tally winner sessionID against the sessionID log."""
    if not session_id or not str(session_id).strip():
        return False
    record = get_blockchain_db(client)[SESSION_ID_LOG_COLLECTION].find_one(
        {"sessionID": str(session_id).strip()}
    )
    return record is not None


def add_tally_point(
    *,
    entity_type: str,
    entity_id: str,
    session_id: str | None = None,
    session_id_verified: bool | None = None,
    client: Any,
) -> dict[str, Any]:
    """Add one tally point for an entity that processed session data."""
    if entity_type not in TALLY_PROCESSOR_ENTITY_TYPES:
        raise ValueError(f"Unsupported tally entity_type: {entity_type}")

    now = utc_now()
    verified = session_id_verified
    if verified is None and session_id:
        verified = verify_tally_session_id(client=client, session_id=session_id)

    update_doc: dict[str, Any] = {
        "$set": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "updated_at": now,
        },
        "$inc": {"tally_points": 1},
        "$setOnInsert": {
            "created_at": now,
            "taskTokens": [],
            "last_win_at": None,
            "last_reset_at": None,
        },
    }
    if session_id:
        update_doc["$set"]["sessionID"] = str(session_id).strip()
    if verified is not None:
        update_doc["$set"]["sessionID_verified"] = verified

    get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        update_doc,
        upsert=True,
    )
    record = get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].find_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0},
    )
    return dict(record or {})


def add_task_token_to_tally(
    *,
    entity_type: str,
    entity_id: str,
    session_id: str,
    task_token: str,
    client: Any,
) -> dict[str, Any]:
    """Add a TaskToken and tally point for session processing (compress / block pipeline)."""
    if entity_type not in TALLY_PROCESSOR_ENTITY_TYPES:
        raise ValueError(f"Unsupported tally entity_type: {entity_type}")

    now = utc_now()
    verified = verify_tally_session_id(client=client, session_id=session_id)
    get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {
            "$set": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "sessionID": str(session_id).strip(),
                "sessionID_verified": verified,
                "updated_at": now,
            },
            "$inc": {"tally_points": 1},
            "$addToSet": {"taskTokens": task_token},
            "$setOnInsert": {
                "created_at": now,
                "last_win_at": None,
                "last_reset_at": None,
            },
        },
        upsert=True,
    )
    record = get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].find_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0},
    )
    return dict(record or {})


def record_session_processing_tally(
    *,
    processors: list[dict[str, str]],
    session_id: str,
    task_token: str | None = None,
    client: Any,
) -> list[dict[str, Any]]:
    """Add tally points for each NodeUser, master server, AdminUser, or MasterClassUser processor."""
    if not processors:
        raise ValueError("At least one session processor is required")

    results: list[dict[str, Any]] = []
    for processor in processors:
        entity_type = str(processor.get("entity_type") or "").strip()
        entity_id = str(processor.get("entity_id") or "").strip()
        if not entity_type or not entity_id:
            raise ValueError("Each processor requires entity_type and entity_id")
        if task_token:
            record = add_task_token_to_tally(
                entity_type=entity_type,
                entity_id=entity_id,
                session_id=session_id,
                task_token=task_token,
                client=client,
            )
        else:
            record = add_tally_point(
                entity_type=entity_type,
                entity_id=entity_id,
                session_id=session_id,
                client=client,
            )
        results.append(record)
    return results


def get_tally_snapshot(*, client: Any) -> list[dict[str, Any]]:
    """Return current tally records from the shared database."""
    return list(
        get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].find({}, {"_id": 0})
    )


def seed_tally_sync(
    *,
    client: Any,
    target: str = DEFAULT_TALLY_TARGET,
    force: bool = False,
) -> dict[str, Any]:
    """Seed tally snapshot to NodeUsers and MasterServer (every 30 seconds)."""
    db = get_blockchain_db(client)
    now = utc_now()

    if not force:
        latest = db[TALLY_SYNC_COLLECTION].find_one({}, sort=[("seeded_at", -1)])
        if latest and isinstance(latest.get("seeded_at"), str):
            seeded_at = _parse_iso_timestamp(latest["seeded_at"])
            if seeded_at is not None:
                elapsed = datetime.now(timezone.utc) - seeded_at.astimezone(timezone.utc)
                if elapsed.total_seconds() < TALLY_SYNC_INTERVAL_SECONDS:
                    latest.pop("_id", None)
                    return {
                        "skipped": True,
                        "reason": (
                            f"Tally sync interval is {TALLY_SYNC_INTERVAL_SECONDS}s; "
                            "use force=True to seed immediately"
                        ),
                        "last_sync": latest,
                    }

    snapshot = get_tally_snapshot(client=client)
    sync_record = {
        "sync_batch_id": secrets.token_hex(8),
        "seeded_at": now,
        "seed_interval_seconds": TALLY_SYNC_INTERVAL_SECONDS,
        "tally_snapshot": snapshot,
        "target": target,
        "created_at": now,
    }
    db[TALLY_SYNC_COLLECTION].insert_one(sync_record)
    sync_record.pop("_id", None)
    return {
        "skipped": False,
        "sync_batch_id": sync_record["sync_batch_id"],
        "seeded_at": now,
        "seed_interval_seconds": TALLY_SYNC_INTERVAL_SECONDS,
        "target": target,
        "record_count": len(snapshot),
        "sync_record": sync_record,
    }


def _tally_score(record: dict[str, Any]) -> tuple[int, int]:
    task_tokens = record.get("taskTokens") or []
    token_count = len(task_tokens) if isinstance(task_tokens, list) else 0
    points = int(record.get("tally_points") or 0)
    return points, token_count


def select_tally_winner(*, client: Any) -> dict[str, Any]:
    """Select block creation winner from tally_points and taskTokens."""
    db = get_blockchain_db(client)
    candidates = list(
        db[TALLY_RECORDS_COLLECTION].find(
            {"entity_type": {"$in": list(TALLY_ENTITY_TYPES)}},
            {"_id": 0},
        )
    )
    if not candidates:
        return {
            "winner_entity_type": "master_server",
            "winner_entity_id": "master_server",
            "tally_verified": True,
            "tally_points": 0,
            "taskTokens": [],
            "sessionID": None,
        }

    winner = max(candidates, key=_tally_score)
    session_id = winner.get("sessionID")
    verified = bool(winner.get("sessionID_verified")) and verify_tally_session_id(
        client=client,
        session_id=session_id if isinstance(session_id, str) else None,
    )
    return {
        "winner_entity_type": winner.get("entity_type") or "master_server",
        "winner_entity_id": winner.get("entity_id") or "master_server",
        "tally_verified": verified,
        "tally_points": int(winner.get("tally_points") or 0),
        "taskTokens": list(winner.get("taskTokens") or []),
        "sessionID": session_id,
    }


def reset_tally_for_winner(
    *,
    entity_type: str,
    entity_id: str,
    client: Any,
) -> dict[str, Any]:
    """Reset tally for the ID that created the block (block-smash.py win reset)."""
    now = utc_now()
    get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {
            "$set": {
                "tally_points": 0,
                "taskTokens": [],
                "last_win_at": now,
                "last_reset_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    record = get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].find_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0},
    )
    return dict(record or {})


def validate_tally_for_block_creation(*, client: Any, is_genesis: bool = False) -> dict[str, Any]:
    """Validate tally winner for block creation (sessionID log + taskTokens)."""
    winner = select_tally_winner(client=client)
    task_tokens = winner.get("taskTokens") or []
    token_count = len(task_tokens) if isinstance(task_tokens, list) else 0
    tally_points = int(winner.get("tally_points") or 0)

    if not is_genesis and not winner.get("tally_verified"):
        raise PermissionError("Tally winner must be verified against sessionID log")

    if not is_genesis and token_count <= 0 and tally_points <= 0:
        winner_type = str(winner.get("winner_entity_type") or "")
        if winner_type != "master_server":
            raise PermissionError(
                "Block creation requires taskTokens in the tally record system "
                "for the corresponding NodeUser or master server"
            )

    return {
        "winner_entity_type": winner.get("winner_entity_type"),
        "winner_entity_id": winner.get("winner_entity_id"),
        "tally_verified": bool(winner.get("tally_verified")),
        "tally_points": tally_points,
        "taskTokens": list(task_tokens) if isinstance(task_tokens, list) else [],
        "taskToken_count": token_count,
        "sessionID": winner.get("sessionID"),
    }


def tally_record_template() -> dict[str, None]:
    """Return empty tally record template from blockchain_schema."""
    return schema_template(TALLY_RECORDS_FIELDS)


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops tally system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed tally snapshot to NodeUsers and MasterServer")
    seed_parser.add_argument("--target", default=DEFAULT_TALLY_TARGET)
    seed_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("snapshot", help="Print current tally snapshot")
    subparsers.add_parser("winner", help="Select and print tally winner")
    subparsers.add_parser("validate", help="Validate tally for block creation")
    reset_parser = subparsers.add_parser("reset", help="Reset tally for block winner")
    reset_parser.add_argument("--entity-type", required=True)
    reset_parser.add_argument("--entity-id", required=True)

    args = parser.parse_args()
    mongo = get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")

    try:
        if args.command == "seed":
            result = seed_tally_sync(client=mongo, target=args.target, force=args.force)
        elif args.command == "snapshot":
            records = get_tally_snapshot(client=mongo)
            result = {"records": records, "count": len(records)}
        elif args.command == "winner":
            result = select_tally_winner(client=mongo)
        elif args.command == "validate":
            result = validate_tally_for_block_creation(client=mongo)
        elif args.command == "reset":
            result = reset_tally_for_winner(
                entity_type=args.entity_type,
                entity_id=args.entity_id,
                client=mongo,
            )
        else:
            raise ValueError(f"Unsupported command: {args.command}")

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        mongo.close()


if __name__ == "__main__":
    raise SystemExit(main())
