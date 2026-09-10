""" the protocol for how the data from the compressed session record is added to the next block in the blockchain system 
limitations:
- the first 100 comressed session records are added to the next block in the blockchain system
- each session record generates a session key to view the compressed session record
- a session key is valid for 2 years after the session record is added to the blockchain system
- the session key only allows access to the userID involved in the session record
- a copy of the session key is added to the blockchain within the created block
- the total size of a block is limited to 1MB

requirements:
- the session record must be in a compressed state
- the session record must be in a valid state
- the session record must be in a unique state
- the session record must be in the correct format
- the session record must be in the correct location (the compressed database) 

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import zlib
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    SESSION_KEYS_COLLECTION,
    SESSION_RECORDS_COLLECTION,
)
from blockchain_secrets import (  # noqa: E402
    resolve_blockchain_hash_algorithm,
    resolve_max_block_bytes,
    resolve_max_sessions_per_block,
    resolve_session_key_validity_seconds,
)
from chunker import chunk_session_payload  # noqa: E402
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402


def _sha(payload: bytes | str) -> str:
    algo = resolve_blockchain_hash_algorithm()
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.new(algo, data).hexdigest()


def generate_session_key(*, session_id: str, user_ids: list[str]) -> str:
    """Create a session view key at operation time (valid for SESSION_KEY_VALIDITY_SECONDS)."""
    material = (
        f"{session_id}:{','.join(sorted(u.strip() for u in user_ids if u))}:"
        f"{utc_now()}:{secrets.token_hex(16)}"
    )
    return _sha(material)


def compress_session_record(record: dict[str, Any]) -> bytes:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return zlib.compress(raw, 9)


def build_data_insert_packet(
    *,
    client: Any,
    session_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compress/pack session chunks into a block packet.
    Enforces max sessions and max block bytes from blockchain.secrets.
    """
    db = get_blockchain_db(client)
    max_sessions = resolve_max_sessions_per_block()
    max_bytes = resolve_max_block_bytes()
    validity = resolve_session_key_validity_seconds()

    if session_records is None:
        session_records = list(
            db[SESSION_RECORDS_COLLECTION]
            .find(
                {
                    "compressed": True,
                    "sessionStatus": {"$in": ["compressed", "complete", "ended"]},
                },
                {"_id": 0},
            )
            .sort("updated_at", 1)
            .limit(max_sessions)
        )

    packet: list[dict[str, Any]] = []
    session_keys: list[dict[str, Any]] = []
    total_bytes = 0
    now = utc_now()

    for record in session_records[:max_sessions]:
        session_id = str(record.get("sessionID") or "").strip()
        if not session_id:
            continue

        user_ids = list(record.get("userIDs") or [])
        host = record.get("hostUserID")
        viewer = record.get("viewerUserID")
        for uid in (host, viewer):
            if uid and uid not in user_ids:
                user_ids.append(uid)

        compressed = compress_session_record(record)
        chunked = chunk_session_payload(compressed, session_id=session_id)
        entry = {
            "sessionID": session_id,
            "aggregate_hash": chunked["aggregate_hash"],
            "chunks": chunked["chunks"],
            "chunk_count": chunked["chunk_count"],
            "compressed_bytes": len(compressed),
            "sessionKey": generate_session_key(session_id=session_id, user_ids=[str(u) for u in user_ids]),
            "userIDs": user_ids,
            "session_key_validity_seconds": validity,
            "created_at": now,
        }
        encoded = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if total_bytes + len(encoded) > max_bytes:
            break
        total_bytes += len(encoded)
        packet.append(entry)

        key_record = {
            "sessionID": session_id,
            "sessionKey": entry["sessionKey"],
            "aggregate_hash": entry["aggregate_hash"],
            "DataInsert": entry["aggregate_hash"],
            "awaiting_block": True,
            "hash_algorithm": resolve_blockchain_hash_algorithm(),
            "userIDs": user_ids,
            "validity_seconds": validity,
            "created_at": now,
            "updated_at": now,
        }
        db[SESSION_KEYS_COLLECTION].update_one(
            {"sessionID": session_id},
            {"$set": key_record},
            upsert=True,
        )
        db[SESSION_RECORDS_COLLECTION].update_one(
            {"sessionID": session_id},
            {
                "$set": {
                    "chunked_payload": chunked,
                    "DataInsert": entry["aggregate_hash"],
                    "aggregate_hash": entry["aggregate_hash"],
                    "sessionKey": entry["sessionKey"],
                    "sessionStatus": "compressed",
                    "updated_at": now,
                }
            },
        )
        session_keys.append(key_record)

    return {
        "packet": packet,
        "session_count": len(packet),
        "total_bytes": total_bytes,
        "max_block_bytes": max_bytes,
        "max_sessions_per_block": max_sessions,
        "session_keys": session_keys,
        "created_at": now,
    }


def prepare_block_data_insert(*, client: Any | None = None) -> dict[str, Any]:
    owns = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")
    try:
        return build_data_insert_packet(client=mongo)
    finally:
        if owns and mongo is not None:
            mongo.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops DataInsert packet builder")
    parser.add_argument("--prepare", action="store_true", help="Build packet from compressed sessions")
    args = parser.parse_args()
    if args.prepare:
        result = prepare_block_data_insert()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
