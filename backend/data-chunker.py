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

from config import CHUNK_SIZE_BYTES, get_config_value


def resolve_hash_algorithm() -> str:
    return get_config_value("SESSION_HASH_ALGORITHM")


def resolve_previous_hash_field() -> str:
    return get_config_value("LEDGER_PREVIOUS_HASH_FIELD")


def __getattr__(name: str) -> Any:
    if name == "HASH_ALGORITHM":
        return resolve_hash_algorithm()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _digest_hex(data: bytes, *, algorithm: str) -> str:
    try:
        return hashlib.new(algorithm, data).hexdigest()
    except ValueError as exc:
        raise RuntimeError(f"unsupported hash algorithm: {algorithm}") from exc


def chunk_session_data(
    session_data: dict[str, Any] | bytes | str,
    *,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    """Split session data into chunks and attach SHA-512 hashes for blockchain inclusion."""
    if isinstance(session_data, dict):
        payload = json.dumps(session_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(session_data, str):
        payload = session_data.encode("utf-8")
    else:
        payload = session_data

    resolved_chunk_size = chunk_size if chunk_size is not None else CHUNK_SIZE_BYTES
    if resolved_chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    algorithm = resolve_hash_algorithm()
    chunks: list[dict[str, Any]] = []
    for index, offset in enumerate(range(0, len(payload), resolved_chunk_size)):
        piece = payload[offset : offset + resolved_chunk_size]
        chunk_hash = _digest_hex(piece, algorithm=algorithm)
        chunks.append(
            {
                "index": index,
                "offset": offset,
                "size": len(piece),
                "hash": chunk_hash,
                "hash_algorithm": algorithm,
                "data_hex": piece.hex(),
            }
        )

    merkle_input = "".join(chunk["hash"] for chunk in chunks).encode("utf-8")
    aggregate_hash = _digest_hex(merkle_input if chunks else payload, algorithm=algorithm)

    return {
        "hash_algorithm": algorithm,
        "chunk_size": resolved_chunk_size,
        "total_size": len(payload),
        "chunk_count": len(chunks),
        "aggregate_hash": aggregate_hash,
        "previous_hash_field": resolve_previous_hash_field(),
        "chunks": chunks,
    }


def verify_chunk_hashes(chunked: dict[str, Any]) -> bool:
    """Verify all chunk SHA-512 hashes in a chunked session payload."""
    algorithm = str(chunked.get("hash_algorithm") or resolve_hash_algorithm())
    for chunk in chunked.get("chunks", []):
        data = bytes.fromhex(chunk["data_hex"])
        if _digest_hex(data, algorithm=algorithm) != chunk["hash"]:
            return False
    return True
