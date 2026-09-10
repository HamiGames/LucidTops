""" the protocol for chunking the session data into smaller blocks for the blockchain system
chunker protocol:
- the chunker is used to chunk the session data into smaller blocks for the blockchain system
- the chunker is used to chunk the session data into smaller blocks for the blockchain system by the master server
- the chunker is used to chunk the session data into smaller blocks for the blockchain system by the NodeUser
- the chunker will return a chunked data string that is used to create a new block in the blockchain system
- the chunked data string will be included in the next block in the blockchain system
- the chunked sessionKey will be returned to the UserID's that participated in the session

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_secrets import resolve_blockchain_hash_algorithm, resolve_chunk_size_bytes  # noqa: E402


def _hash_bytes(payload: bytes, *, algorithm: str | None = None) -> str:
    algo = (algorithm or resolve_blockchain_hash_algorithm()).lower()
    return hashlib.new(algo, payload).hexdigest()


def chunk_session_payload(
    payload: bytes | str | dict[str, Any] | list[Any],
    *,
    session_id: str | None = None,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    """
    Split completed session payload into ordered chunks for block packets.
    Chunk size comes from blockchain.secrets at operation time.
    """
    size = resolve_chunk_size_bytes() if chunk_size is None else int(chunk_size)
    if size < 1:
        raise ValueError("chunk_size must be >= 1")

    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = payload

    chunks: list[dict[str, Any]] = []
    offset = 0
    index = 0
    while offset < len(raw):
        piece = raw[offset : offset + size]
        chunk_hash = _hash_bytes(piece)
        chunks.append(
            {
                "index": index,
                "offset": offset,
                "size": len(piece),
                "chunk_hash": chunk_hash,
                "data_b64": base64.b64encode(piece).decode("ascii"),
            }
        )
        offset += size
        index += 1

    aggregate = _hash_bytes(raw)
    return {
        "sessionID": session_id,
        "chunk_count": len(chunks),
        "total_bytes": len(raw),
        "chunk_size": size,
        "aggregate_hash": aggregate,
        "hash_algorithm": resolve_blockchain_hash_algorithm(),
        "chunks": chunks,
    }


def reassemble_chunks(chunked: dict[str, Any]) -> bytes:
    """Reassemble chunked payload and verify aggregate hash."""
    chunks = list(chunked.get("chunks") or [])
    chunks.sort(key=lambda row: int(row.get("index") or 0))
    raw = b"".join(base64.b64decode(str(row.get("data_b64") or "")) for row in chunks)
    expected = str(chunked.get("aggregate_hash") or "")
    actual = _hash_bytes(raw, algorithm=str(chunked.get("hash_algorithm") or None))
    if expected and actual != expected:
        raise ValueError("chunk aggregate_hash mismatch on reassemble")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops session chunker")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--payload-file", required=True, help="Path to session payload file")
    args = parser.parse_args()
    data = Path(args.payload_file).read_bytes()
    result = chunk_session_payload(data, session_id=args.session_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
