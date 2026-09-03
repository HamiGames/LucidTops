f"""The schema for the NodeUserID hosted database (mongodb database design), this uses a FastAPI connection system.
each NodeUserID will have a unique DatabaseID for the NodeUserID hosted database.
each NodeDB is synchronized with the MasterServer (LucidTopsDB) via the FastAPI connection system.
each NodeDB will have a synchronised version of the LedgerDB (BlockchainDB) via the FastAPI connection system.
A NodeUser Can Not manually modify the NodeDB, only the MasterServer (LucidTopsDB) can modify the NodeDB.
all sessionID's are Live updated from the CreateSession API route.(via the FastAPI, MasterServer)

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

NODE_HOSTED_DB_COLLECTION = "node_hosted_databases"
NODE_SEED_COLLECTION = "node_seeds"

NODE_DB_SCHEMA_FIELDS: tuple[str, ...] = (
    "UserID",
    "IDToken",
    "current_session_ID",
    "current_session_peer",
    "current_session_status",
)

NODE_SEED_FIELDS: tuple[str, ...] = (
    "NodeUserID",
    "NodeDatabaseID",
    "UserID",
    "IDToken",
    "created_at",
    "updated_at",
)


def schema_template(fields: tuple[str, ...]) -> dict[str, None]:
    return {field: None for field in fields}
