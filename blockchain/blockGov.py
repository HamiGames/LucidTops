"""Blockchain-local NodeUser governance checks (no backend imports).

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Any, Literal

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_secrets import resolve_node_min_memory_gb  # noqa: E402
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402

NodeOperation = Literal[
    "session",
    "blockchain_read",
    "blockchain_create",
    "ledger_read",
    "ledger_write",
    "database_seed",
    "database_modify",
    "session_modify",
    "block_modify",
    "ledger_modify_past",
]

BANNED_OPERATIONS_COLLECTION = "node_governance_bans"
NODE_GOV_AUDIT_COLLECTION = "node_governance_audit"

RESTRICTED_NODE_OPERATIONS: frozenset[NodeOperation] = frozenset(
    {
        "database_modify",
        "session_modify",
        "block_modify",
        "ledger_modify_past",
    }
)

BLOCKCHAIN_ALLOWED: frozenset[NodeOperation] = frozenset(
    {"blockchain_read", "blockchain_create", "ledger_read", "ledger_write"}
)


def verify_node_memory_requirement(reported_memory_gb: int | None) -> bool:
    if reported_memory_gb is None:
        return False
    return reported_memory_gb >= resolve_node_min_memory_gb()


def is_node_banned(node_user_id: str, *, client: Any | None = None) -> bool:
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return True
    try:
        record = get_blockchain_db(mongo)[BANNED_OPERATIONS_COLLECTION].find_one(
            {"NodeUserID": node_user_id, "banned": True}
        )
        return record is not None
    finally:
        if client is None:
            mongo.close()


def ban_node_user(node_user_id: str, reason: str, *, client: Any | None = None) -> None:
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")
    try:
        db = get_blockchain_db(mongo)
        db[BANNED_OPERATIONS_COLLECTION].update_one(
            {"NodeUserID": node_user_id},
            {
                "$set": {
                    "NodeUserID": node_user_id,
                    "banned": True,
                    "reason": reason,
                    "lucid_tokens_holding_account": secrets.token_hex(16),
                    "updated_at": utc_now(),
                },
                "$setOnInsert": {"created_at": utc_now()},
            },
            upsert=True,
        )
        db[NODE_GOV_AUDIT_COLLECTION].insert_one(
            {
                "NodeUserID": node_user_id,
                "action": "ban",
                "reason": reason,
                "timestamp": utc_now(),
            }
        )
    finally:
        if client is None:
            mongo.close()


def validate_node_operation(
    *,
    node_user_id: str,
    operation: NodeOperation,
    is_latest_block_creator: bool = False,
    reported_memory_gb: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    if is_node_banned(node_user_id, client=client):
        raise PermissionError("NodeUser is banned from all operations")

    if operation in RESTRICTED_NODE_OPERATIONS:
        if operation == "ledger_write" and is_latest_block_creator:
            # Latest block creator may perform ledger_write; do not ban.
            pass
        else:
            ban_node_user(
                node_user_id,
                f"Attempted restricted operation: {operation}",
                client=client,
            )
            raise PermissionError(f"Operation not permitted for NodeUser: {operation}")

    if operation == "ledger_write":
        if not is_latest_block_creator:
            raise PermissionError(
                "NodeUser may update ledger only when creator of latest block"
            )
        return {
            "NodeUserID": node_user_id,
            "operation": operation,
            "permitted": True,
            "memory_requirement_gb": resolve_node_min_memory_gb(),
            "memory_verified": verify_node_memory_requirement(reported_memory_gb),
        }

    if operation in BLOCKCHAIN_ALLOWED and operation == "blockchain_create":
        if not verify_node_memory_requirement(reported_memory_gb):
            raise PermissionError(
                f"NodeUser console must meet {resolve_node_min_memory_gb()}GB memory requirement"
            )

    return {
        "NodeUserID": node_user_id,
        "operation": operation,
        "permitted": True,
        "memory_requirement_gb": resolve_node_min_memory_gb(),
        "memory_verified": verify_node_memory_requirement(reported_memory_gb),
    }
