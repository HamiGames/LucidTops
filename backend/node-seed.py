f"""Fundamental functions to create NodeUserID and configure node database with NodeDatabaseID, 
uses the MasterServer (LucidTopsDB) as the seed source for the NodeDB (NodeUser)
information inclusions:
UserID=True
User-TokenID= True
UserProfileData=False
ReadOnly= True
WriteOnly= False
UserId-SessionID=current only
UserID-SessionData-raw= False
UserID-SessionData-hash= True

Collection Content:

User:[userID: str,
idToken: str,
SessionID: str,
SessionID-hash: str,
SessionData-hash: str ]

Sessions:[SessionID: str,
SessionID-hash: str,
SessionData-hash: str ]

Blockchain:[LedgerID: str,
LedgerData-hash: str, 
Last-BlockID: str,
last-block-timestamp: datetime,
lastblock-creator: str,
]

"""

from __future__ import annotations

import secrets
from typing import Any

from config import get_master_db, get_mongo_client, utc_now
from NodeDbSchema import NODE_SEED_COLLECTION, NODE_SEED_FIELDS
from NodeGov import classify_required_node_credentials, verify_node_account

NODE_SEED_REQUIRED_FIELDS: tuple[str, ...] = (
    "NodeUserID",
    "UserID",
    "IDToken",
)


def _generate_node_database_id() -> str:
    return secrets.token_hex(16)


def create_node_seed(
    *,
    node_user_id: str,
    user_id: str,
    id_token: str,
    api_key: str,
    api_secret: str,
    client: Any | None = None,
) -> dict[str, str]:
    """Create a node seed record and return NodeDatabaseID proof."""
    if not node_user_id or not user_id or not id_token:
        raise ValueError(
            f"All node-seed fields required: {', '.join(NODE_SEED_REQUIRED_FIELDS)}"
        )

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        db = get_master_db(mongo)
        existing = db[NODE_SEED_COLLECTION].find_one({"NodeUserID": node_user_id})
        if existing and existing.get("NodeDatabaseID"):
            return {
                "NodeUserID": node_user_id,
                "NodeDatabaseID": existing["NodeDatabaseID"],
                "status": "existing",
            }

        if not verify_node_account(node_user_id=node_user_id, id_token=id_token, client=mongo):
            # Allow seed during registration when id_tokens collection holds the token
            token_ok = db.id_tokens.find_one(
                {"entity": "node", "NodeUserID": node_user_id, "IDToken": id_token}
            )
            if not token_ok:
                raise PermissionError("NodeUser account verification failed")

        node_database_id = _generate_node_database_id()
        now = utc_now()
        record = {
            "NodeUserID": node_user_id,
            "NodeDatabaseID": node_database_id,
            "UserID": user_id,
            "IDToken": id_token,
            "credentials": classify_required_node_credentials(
                user_id=user_id,
                id_token=id_token,
                api_key=api_key,
                api_secret=api_secret,
            ),
            "created_at": now,
            "updated_at": now,
        }
        db[NODE_SEED_COLLECTION].update_one(
            {"NodeUserID": node_user_id},
            {"$set": record},
            upsert=True,
        )
        db.node_users.update_one(
            {"NodeUserID": node_user_id},
            {
                "$set": {
                    "NodeUserID": node_user_id,
                    "UserID": user_id,
                    "IDToken": id_token,
                    "NodeDatabaseID": node_database_id,
                    "node_registration_timestamp": now,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return {
            "NodeUserID": node_user_id,
            "NodeDatabaseID": node_database_id,
            "UserID": user_id,
            "status": "created",
            "fields": str(list(NODE_SEED_FIELDS)), 
        }
    finally:
        if client is None:
            mongo.close()
