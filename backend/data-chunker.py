"""Data chunker for integrating session data into the blockchain system using SHA-512,
included data in the data-chunker:
-sessionID
(participant required data)
- SessionData-hash(excludes Mp4, only text operation logs)
- SessionID-hash
- SessionID-Duration: int
- SessionID-Start-Timestamp: datetime
- SessionID-End-Timestamp: datetime
- SessionID-Processing-ID: str
- SessionID-Processing-Timestamp: datetime
- SessionID-Processing-Duration: int
- SessionID-Processing-Status: str
- SessionID-Processing-Result: str
- SessionID-Processing-Error: str
- SessionID-Processing-Error-Code: int
- SessionID-Processing-Error-Message: str
- SessionID-Processing-Error-Trace: str
all session data processed by this module will be less than 1mb in size.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from config import CHUNK_SIZE_BYTES

HASH_ALGORITHM = "sha512"


def _sha512_hex(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def chunk_session_data(
    session_data: dict[str, Any] | bytes | str,
    *,
    chunk_size: int = CHUNK_SIZE_BYTES,
) -> dict[str, Any]:
    """Split session data into chunks and attach SHA-512 hashes for blockchain inclusion."""
    if isinstance(session_data, dict):
        payload = json.dumps(session_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(session_data, str):
        payload = session_data.encode("utf-8")
    else:
        payload = session_data

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    chunks: list[dict[str, Any]] = []
    for index, offset in enumerate(range(0, len(payload), chunk_size)):
        piece = payload[offset : offset + chunk_size]
        chunk_hash = _sha512_hex(piece)
        chunks.append(
            {
                "index": index,
                "offset": offset,
                "size": len(piece),
                "hash": chunk_hash,
                "hash_algorithm": HASH_ALGORITHM,
                "data_hex": piece.hex(),
            }
        )

    merkle_input = "".join(chunk["hash"] for chunk in chunks).encode("utf-8")
    aggregate_hash = _sha512_hex(merkle_input if chunks else payload)

    return {
        "hash_algorithm": HASH_ALGORITHM,
        "chunk_size": chunk_size,
        "total_size": len(payload),
        "chunk_count": len(chunks),
        "aggregate_hash": aggregate_hash,
        "previous_hash_field": "ledger_last_hash",
        "chunks": chunks,
    }


def verify_chunk_hashes(chunked: dict[str, Any]) -> bool:
    """Verify all chunk SHA-512 hashes in a chunked session payload."""
    for chunk in chunked.get("chunks", []):
        data = bytes.fromhex(chunk["data_hex"])
        if _sha512_hex(data) != chunk["hash"]:
            return False
    return True
