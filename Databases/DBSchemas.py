"""MongoDB collection field schemas for LucidTops named Databases.

Field contracts from documentation/Databases.txt:
- LucidTops_SessionsDB collection SessionID
- LucidTopsUserDB collection UserID
- LucidTopsNodeDB collection {NodeID}
- LucidTopsLedgerDB / LucidTops_LedgerDB collection BlockID
- LucidTopsPaySystemsDB collection {UserID}_{timestamp}
- LucidTopsBlockchain_LedgerDB is a replica of LucidTops_LedgerDB (creator_id omitted on replica)

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
from typing import Any

from Dns_databases import ALL_NAMED_DB_CONTAINERS, secret_key_prefix

# --- LucidTops_SessionsDB collection schema: collection name:"SessionID" ---
SESSION_ID_FIELDS: tuple[str, ...] = (
    "SessionID",
    "Host_UserID",
    "Viewer_UserID",
    "creation_timestamp",
    "join_timestamp_start",
    "Viewer_log",
    "Host_log",
    "Session_End_timestamp",
    "Session_settings",
)

# --- LucidTopsUserDB collection schema: collection name: "UserID" ---
USER_ID_FIELDS: tuple[str, ...] = (
    "UserID",
    "TokenID",
    "Email",
    "Password",
    "Tier_selected",
    "Payment_API",
    "purchase_date",
    "renwal_date",
    "registration_docs",
)

# --- LucidTopsNodeDB collection schema: collection name: "{NodeID}" ---
NODE_ID_FIELDS: tuple[str, ...] = (
    "NodeID",
    "UserID",
    "TokenID",
    "Email",
    "timestamp",
    "NodeID_UserDB_name",
    "NodeID_LedgerDB_name",
    "NodeID_LucidTokens",
    "Registered_MAC_IDs",
    "status",
    "registration_docs",
)

# --- LucidTopsLedgerDB collection schema: collection name: "BlockID" ---
BLOCK_ID_FIELDS: tuple[str, ...] = (
    "BlockID",
    "creator_id",
    "creation_timestamp",
    "Rewards",
    "LastBlockID",
    "Session-data-count",
)

# Replica omits creator visibility (Blockchain.txt / fixes.txt external copy).
BLOCK_ID_REPLICA_FIELDS: tuple[str, ...] = tuple(
    field for field in BLOCK_ID_FIELDS if field != "creator_id"
)

# --- LucidTopsPaySystemsDB collection schema: collection_name: "{UserID}_{timestamp}" ---
PAY_SYSTEMS_FIELDS: tuple[str, ...] = (
    "UserID",
    "Payment_Amount",
    "Payment_timestamp",
    "payment_status",
    "reciept_ID",
    "reciept_address",
)

# Node-hosted User/Ledger collections (NodeDbSchema comment contracts).
NODE_HOSTED_USER_FIELDS: tuple[str, ...] = (
    "userID",
    "idToken",
    "SessionID",
    "SessionID-hash",
    "SessionData-hash",
)

NODE_HOSTED_SESSIONS_FIELDS: tuple[str, ...] = (
    "SessionID",
    "SessionID-hash",
    "SessionData-hash",
)

NODE_HOSTED_BLOCKCHAIN_FIELDS: tuple[str, ...] = (
    "LedgerID",
    "LedgerData-hash",
    "Last-BlockID",
    "last-block-timestamp",
    "lastblock-creator",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def resolve_collection_name(secret_key: str, fallback: str) -> str:
    """Resolve collection name from secrets/env at operation time; fallback is structural doc name."""
    value = _env(secret_key)
    if value:
        return value
    try:
        from databases_secrets import get_secret

        value = get_secret(secret_key)
    except Exception:
        value = ""
    return value.strip() or fallback


def schema_template(fields: tuple[str, ...]) -> dict[str, None]:
    return {field: None for field in fields}


def database_schema_map() -> dict[str, dict[str, Any]]:
    """
    Map DockerDNS database container -> primary collection contract.
    Collection names resolve from secrets when overridden.
    """
    return {
        "LucidTops_SessionsDB": {
            "collection": resolve_collection_name("SESSIONS_DB_COLLECTION", "SessionID"),
            "fields": SESSION_ID_FIELDS,
            "indexes": (("SessionID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
        "LucidTopsUserDB": {
            "collection": resolve_collection_name("USER_DB_COLLECTION", "UserID"),
            "fields": USER_ID_FIELDS,
            "indexes": (
                ("UserID", {"unique": True, "sparse": True}),
                ("Email", {"unique": True, "sparse": True}),
            ),
            "omit_fields_on_replica": (),
        },
        "LucidTopsNodeDB": {
            "collection": resolve_collection_name("NODE_DB_COLLECTION", "NodeID"),
            "fields": NODE_ID_FIELDS,
            "indexes": (("NodeID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
        "LucidTops_LedgerDB": {
            "collection": resolve_collection_name("LEDGER_DB_COLLECTION", "BlockID"),
            "fields": BLOCK_ID_FIELDS,
            "indexes": (("BlockID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
        "LucidTopsBlockchain_LedgerDB": {
            "collection": resolve_collection_name(
                "BLOCKCHAIN_LEDGER_DB_COLLECTION", "BlockID"
            ),
            "fields": BLOCK_ID_REPLICA_FIELDS,
            "indexes": (("BlockID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": ("creator_id",),
        },
        "LucidTopsPaySystemsDB": {
            "collection": resolve_collection_name(
                "PAYSYSTEMS_DB_COLLECTION", "PaySystemsReceipt"
            ),
            "fields": PAY_SYSTEMS_FIELDS,
            "indexes": (("reciept_ID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
    }


def schema_for_database(db_name: str) -> dict[str, Any]:
    mapping = database_schema_map()
    if db_name not in mapping:
        raise RuntimeError(f"no schema contract for database {db_name!r}")
    return mapping[db_name]


def apply_schema_to_database(db: Any, db_name: str, *, created_at: str) -> dict[str, Any]:
    """Insert schema template + indexes into a live pymongo Database object."""
    spec = schema_for_database(db_name)
    collection_name = str(spec["collection"])
    fields: tuple[str, ...] = tuple(spec["fields"])
    col = db[collection_name]
    col.create_index("_id")
    for field, options in spec.get("indexes") or ():
        col.create_index(field, **options)
    if not col.find_one({"_schema_template": True}):
        col.insert_one(
            {
                "_schema_template": True,
                "fields": list(fields),
                "database": db_name,
                "created_at": created_at,
            }
        )
    return {
        "database": db_name,
        "collection": collection_name,
        "fields": list(fields),
    }


def schemas_status() -> dict[str, Any]:
    return {
        "databases": list(ALL_NAMED_DB_CONTAINERS),
        "contracts": {
            name: {
                "collection": spec["collection"],
                "field_count": len(spec["fields"]),
            }
            for name, spec in database_schema_map().items()
        },
        "secret_prefixes": {
            name: secret_key_prefix(name) for name in ALL_NAMED_DB_CONTAINERS
        },
    }
