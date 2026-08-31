"""Governance system for NodeUser operations and access classification.
includes:
- the rules and regulations for the NodeUser
- the rules and regulations for the NodeUser's operations
- the rules and regulations for the NodeUser's access to the master server database
- the rules and regulations for the NodeUser's access to the blockchain system
- the rules and regulations for the NodeUser's access to the LucidLedger system
- the rules and regulations for the NodeUser's access to the LucidMarket system
- the rules and regulations for the NodeUser's access to the LucidToken system
- the rules and regulations for the NodeUser's access to the LucidToken system

Rules for the NodeUser:
- if a NodeUser is found to be fraudulent or malicious, they will be banned from all operations and their LucidTokens will be transferred to a holding account after 3 flags in any of the systems (blockchain, LucidLedger, LucidMarket, LucidToken)
- if a NodeUser is banned the first ban is 5 days, the second is 30 days, the third time is permanent ban and their LucidTokens will be transferred to a holding account.
- if a jackot is initiated during a banned period, the NodeUserID will not recieve any earnings from the jackpot system (all earnings will be transferred to a holding account)
- all funds in the holding account will be forfeited to the AdminUserID during the ban period (all earnings will be transferred to the AdminUserID)
- all attempts to access the system during a banned period will be denied and the NodeUserID will be flagged as fraudulent (NodeGov.py)
- all misconduct is subject to the rules and regulations of the lucid system
- all attempts to corrupt of edit data related to sessionID, blockID, ledgerID, or any other data related to the system will be subject to an immediate ban (audited and logged, subject to administrative review)
- no NodeUser is permitted to harrass, abuse, or harass any other NodeUser, User, MasterClassUser, or AdminUser. (manual reporting system will be implemented)
- A NodeUser is permitted to be online for 24 hours per day, 7 days per week
- A NodeUser is permitted to be on up to 5 consoles at a time (5 consoles per NodeUserID)
- A NodeUser is subject to the tier system for use of the session system (session.py)
- A NodeUser may trade LucidTokens for other currencies (USD, XRP, Tron) at the LucidMarket system (LucidMarket.py)
- A NodeUser may use the LucidToken to pay for the tier system for use of the session system (session.py)(value of a token is based on the jackpot system (jackpot.py))


"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Literal

from config import NODE_MIN_MEMORY_GB, get_master_db, get_mongo_client, utc_now

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

SESSION_ALLOWED: frozenset[NodeOperation] = frozenset({"session", "session_modify"})
BLOCKCHAIN_ALLOWED: frozenset[NodeOperation] = frozenset(
    {"blockchain_read", "blockchain_create", "ledger_read", "ledger_write"}
)


def _mask_credential(value: str) -> str:
    """Return unreadable masked representation for governance logs."""
    digest = hashlib.sha512(value.encode("utf-8")).hexdigest()
    return f"UNREADABLE:{digest[:16]}"


def classify_required_node_credentials(
    *,
    user_id: str,
    id_token: str,
    api_key: str,
    api_secret: str,
) -> dict[str, str]:
    """Classify required NodeUser credentials as unreadable strings for API access."""
    return {
        "UserID": _mask_credential(user_id),
        "IDToken": _mask_credential(id_token),
        "API_key": _mask_credential(api_key),
        "API_secret": _mask_credential(api_secret),
    }


def verify_node_memory_requirement(reported_memory_gb: int | None) -> bool:
    """Minimum recommended NodeUser console memory is 50 GB."""
    if reported_memory_gb is None:
        return False
    return reported_memory_gb >= NODE_MIN_MEMORY_GB


def is_node_banned(node_user_id: str, *, client: Any | None = None) -> bool:
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return True
    try:
        record = get_master_db(mongo)[BANNED_OPERATIONS_COLLECTION].find_one(
            {"NodeUserID": node_user_id, "banned": True}
        )
        return record is not None
    finally:
        if client is None:
            mongo.close()


def ban_node_user(node_user_id: str, reason: str, *, client: Any | None = None) -> None:
    """Ban NodeUser operations and mark LucidTokens for holding transfer."""
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        db = get_master_db(mongo)
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
    """Validate whether a NodeUser may perform an operation under governance rules."""
    if is_node_banned(node_user_id, client=client):
        raise PermissionError("NodeUser is banned from all operations")

    if operation in RESTRICTED_NODE_OPERATIONS:
        if operation == "ledger_write" and is_latest_block_creator:
            pass
        else:
            ban_node_user(
                node_user_id,
                f"Attempted restricted operation: {operation}",
                client=client,
            )
            raise PermissionError(f"Operation not permitted for NodeUser: {operation}")

    if operation in SESSION_ALLOWED and operation == "session_modify":
        raise PermissionError("NodeUser cannot modify session data")

    if operation in BLOCKCHAIN_ALLOWED and operation == "blockchain_create":
        if not verify_node_memory_requirement(reported_memory_gb):
            raise PermissionError(
                f"NodeUser console must meet {NODE_MIN_MEMORY_GB}GB memory requirement"
            )

    if operation == "ledger_write" and not is_latest_block_creator:
        raise PermissionError(
            "NodeUser may update ledger only when creator of latest block"
        )

    return {
        "NodeUserID": node_user_id,
        "operation": operation,
        "permitted": True,
        "memory_requirement_gb": NODE_MIN_MEMORY_GB,
        "memory_verified": verify_node_memory_requirement(reported_memory_gb),
    }


def verify_node_account(
    *,
    node_user_id: str,
    id_token: str,
    client: Any | None = None,
) -> bool:
    """Verify NodeUser account against master server database."""
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return False
    try:
        record = get_master_db(mongo).node_users.find_one(
            {"NodeUserID": node_user_id, "IDToken": id_token}
        )
        if record is None:
            record = get_master_db(mongo).id_tokens.find_one(
                {"entity": "node", "NodeUserID": node_user_id, "IDToken": id_token}
            )
        return record is not None
    finally:
        if client is None:
            mongo.close()
