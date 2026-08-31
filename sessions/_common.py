"""Shared helpers for LucidTops session modules (Tor-only, Docker-compatible)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

SESSIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import get_master_db, get_mongo_client, utc_now  # noqa: E402
from load_module import load_backend_module  # noqa: E402
from MasterDBSchema import (  # noqa: E402
    BLOCKCHAIN_BLOCKS_COLLECTION,
    LEDGER_RECORDS_COLLECTION,
    SESSION_ID_LOG_COLLECTION,
    SESSION_KEYS_COLLECTION,
    SESSION_RECORDS_COLLECTION,
    SESSION_STATUSES,
    TALLY_RECORDS_COLLECTION,
    TASK_TOKENS_COLLECTION,
)

_data_chunker = load_backend_module("data-chunker.py")
chunk_session_data = _data_chunker.chunk_session_data
verify_chunk_hashes = _data_chunker.verify_chunk_hashes
HASH_ALGORITHM = _data_chunker.HASH_ALGORITHM


def with_mongo(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Run a database handler with an auto-closing Mongo client when needed."""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        client = kwargs.pop("client", None)
        owns_client = client is None
        if owns_client:
            client = get_mongo_client()
            if client is None:
                raise RuntimeError("Master server database is unavailable")
        try:
            return handler(*args, client=client, **kwargs)
        finally:
            if owns_client and client is not None:
                client.close()

    return wrapper


def verify_user_id_token(
    *,
    user_id: str,
    id_token: str,
    client: Any,
) -> bool:
    if not id_token or not id_token.strip():
        return False
    db = get_master_db(client)
    token = id_token.strip()
    if db.id_tokens.find_one({"entity": "user", "UserID": user_id, "IDToken": token}):
        return True
    return db.users.find_one({"UserID": user_id, "IDToken": token}) is not None


def verify_node_id_token(
    *,
    node_user_id: str,
    id_token: str,
    client: Any,
) -> bool:
    if not id_token or not id_token.strip():
        return False
    db = get_master_db(client)
    token = id_token.strip()
    if db.id_tokens.find_one(
        {"entity": "node", "NodeUserID": node_user_id, "IDToken": token}
    ):
        return True
    return db.node_users.find_one({"NodeUserID": node_user_id, "IDToken": token}) is not None


def session_records_collection(client: Any) -> Any:
    return get_master_db(client)[SESSION_RECORDS_COLLECTION]


def session_id_log_collection(client: Any) -> Any:
    return get_master_db(client)[SESSION_ID_LOG_COLLECTION]
