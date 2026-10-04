"""MongoDB collection field schemas for LucidTops named Databases.

Field contracts from documentation/Databases.txt:
- LucidTops_SessionsDB collections: SessionID, session-data, session-data-chunk,
  block-data-queue, block-queue-ID
- LucidTopsUserDB collection UserID (includes session-count, max-sessions)
- LucidTopsNodeDB collection {NodeID}
- LucidTopsLedgerDB / LucidTops_LedgerDB collection BlockID
- LucidTopsPaySystemsDB collection {UserID}_{timestamp}

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

from Dns_databases import (
    container_name,
    resolve_main_database_name,
    schema_db_containers,
    secret_key_prefix,
)

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
    "SessionID_status",
    "session-data-ref",
    "block-queue-ID",
)

# --- LucidTops_SessionsDB collection schema: collection name:"session-data" ---
SESSION_DATA_FIELDS: tuple[str, ...] = (
    "SessionID",
    "Host_UserID",
    "Viewer_UserID",
    "payload",
    "Status",
    "created_at",
    "aggregate_hash",
)

# --- LucidTops_SessionsDB collection schema: collection name:"session-data-chunk" ---
SESSION_DATA_CHUNK_FIELDS: tuple[str, ...] = (
    "chunk_id",
    "SessionID",
    "session-data-ref",
    "chunk_index",
    "compressed_payload",
    "chunk_hash",
    "created_at",
)

# --- LucidTops_SessionsDB collection schema: collection name:"block-data-queue" ---
BLOCK_DATA_QUEUE_FIELDS: tuple[str, ...] = (
    "block-queue-ID",
    "chunk_refs",
    "chunk_count",
    "status",
    "created_at",
    "updated_at",
)

# --- LucidTops_SessionsDB collection schema: collection name:"block-queue-ID" ---
BLOCK_QUEUE_ID_FIELDS: tuple[str, ...] = (
    "block-queue-ID",
    "block-data-queue-ref",
    "awaiting_block",
    "target_BlockID",
    "created_at",
)

# Canonical LucidTops_SessionsDB collection names (documentation/Databases.txt).
SESSIONS_DB_COLLECTION_SESSION_ID = "SessionID"
SESSIONS_DB_COLLECTION_SESSION_DATA = "session-data"
SESSIONS_DB_COLLECTION_SESSION_DATA_CHUNK = "session-data-chunk"
SESSIONS_DB_COLLECTION_BLOCK_DATA_QUEUE = "block-data-queue"
SESSIONS_DB_COLLECTION_BLOCK_QUEUE_ID = "block-queue-ID"

# Cap: block-data-queue holds less than 100 session-data-chunks.
BLOCK_DATA_QUEUE_MAX_CHUNKS = 99

# --- LucidTopsUserDB collection schema: collection name: "UserID" ---
USER_ID_FIELDS: tuple[str, ...] = (
    "UserID",
    "TokenID",
    "Email",
    "Password",
    "Tier_selected",
    "session-count",
    "max-sessions",
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


def _collection_spec(
    name: str,
    fields: tuple[str, ...],
    indexes: tuple[tuple[str, dict[str, Any]], ...] = (),
) -> dict[str, Any]:
    return {
        "name": name,
        "fields": fields,
        "indexes": indexes,
    }


def _sessions_db_collections() -> list[dict[str, Any]]:
    """LucidTops_SessionsDB multi-collection contract (Databases.txt)."""
    session_id_name = resolve_collection_name(
        "SESSIONS_DB_COLLECTION", SESSIONS_DB_COLLECTION_SESSION_ID
    )
    return [
        _collection_spec(
            session_id_name,
            SESSION_ID_FIELDS,
            (("SessionID", {"unique": True, "sparse": True}),),
        ),
        _collection_spec(
            resolve_collection_name(
                "SESSIONS_DB_SESSION_DATA_COLLECTION",
                SESSIONS_DB_COLLECTION_SESSION_DATA,
            ),
            SESSION_DATA_FIELDS,
            (("SessionID", {"unique": True, "sparse": True}),),
        ),
        _collection_spec(
            resolve_collection_name(
                "SESSIONS_DB_SESSION_DATA_CHUNK_COLLECTION",
                SESSIONS_DB_COLLECTION_SESSION_DATA_CHUNK,
            ),
            SESSION_DATA_CHUNK_FIELDS,
            (("chunk_id", {"unique": True, "sparse": True}),),
        ),
        _collection_spec(
            resolve_collection_name(
                "SESSIONS_DB_BLOCK_DATA_QUEUE_COLLECTION",
                SESSIONS_DB_COLLECTION_BLOCK_DATA_QUEUE,
            ),
            BLOCK_DATA_QUEUE_FIELDS,
            (("block-queue-ID", {"unique": True, "sparse": True}),),
        ),
        _collection_spec(
            resolve_collection_name(
                "SESSIONS_DB_BLOCK_QUEUE_ID_COLLECTION",
                SESSIONS_DB_COLLECTION_BLOCK_QUEUE_ID,
            ),
            BLOCK_QUEUE_ID_FIELDS,
            (("block-queue-ID", {"unique": True, "sparse": True}),),
        ),
    ]


def database_schema_map() -> dict[str, dict[str, Any]]:
    """
    Map DockerDNS database container -> collection contract(s).
    Single-collection DBs keep collection/fields; SessionsDB uses collections[].
    """
    sessions_collections = _sessions_db_collections()
    primary = sessions_collections[0]
    main = resolve_main_database_name()
    sessions_name = container_name(main, "_SessionsDB")
    user_name = container_name(main, "_UserDB")
    node_name = container_name(main, "_NodeDB")
    ledger_name = container_name(main, "__LedgerDB")
    payment_name = container_name(main, "_PaymentDB")
    return {
        sessions_name: {
            "collection": primary["name"],
            "fields": primary["fields"],
            "indexes": primary["indexes"],
            "collections": sessions_collections,
            "omit_fields_on_replica": (),
        },
        user_name: {
            "collection": resolve_collection_name("USER_DB_COLLECTION", "UserID"),
            "fields": USER_ID_FIELDS,
            "indexes": (
                ("UserID", {"unique": True, "sparse": True}),
                ("Email", {"unique": True, "sparse": True}),
            ),
            "omit_fields_on_replica": (),
        },
        node_name: {
            "collection": resolve_collection_name("NODE_DB_COLLECTION", "NodeID"),
            "fields": NODE_ID_FIELDS,
            "indexes": (("NodeID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
        ledger_name: {
            "collection": resolve_collection_name("LEDGER_DB_COLLECTION", "BlockID"),
            "fields": BLOCK_ID_FIELDS,
            "indexes": (("BlockID", {"unique": True, "sparse": True}),),
            "omit_fields_on_replica": (),
        },
        payment_name: {
            "collection": resolve_collection_name(
                "PAYSYSTEMS_DB_COLLECTION", "{UserID}_{timestamp}"
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


def collections_for_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize single- or multi-collection schema specs to a list."""
    multi = spec.get("collections")
    if multi:
        return list(multi)
    return [
        {
            "name": str(spec["collection"]),
            "fields": tuple(spec["fields"]),
            "indexes": tuple(spec.get("indexes") or ()),
        }
    ]


def apply_collection_schema(
    db: Any,
    db_name: str,
    collection_spec: dict[str, Any],
    *,
    created_at: str,
    update_template_fields: bool = False,
) -> dict[str, Any]:
    """Ensure indexes + _schema_template for one collection (idempotent)."""
    collection_name = str(collection_spec["name"])
    fields: tuple[str, ...] = tuple(collection_spec["fields"])
    col = db[collection_name]
    col.create_index("_id")
    for field, options in collection_spec.get("indexes") or ():
        col.create_index(field, **options)
    existing = col.find_one({"_schema_template": True})
    if not existing:
        col.insert_one(
            {
                "_schema_template": True,
                "fields": list(fields),
                "database": db_name,
                "collection": collection_name,
                "created_at": created_at,
            }
        )
        action = "inserted"
    elif update_template_fields and list(existing.get("fields") or []) != list(fields):
        col.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "fields": list(fields),
                    "collection": collection_name,
                    "updated_at": created_at,
                }
            },
        )
        action = "updated"
    else:
        action = "unchanged"
    return {
        "database": db_name,
        "collection": collection_name,
        "fields": list(fields),
        "action": action,
    }


def apply_schema_to_database(
    db: Any,
    db_name: str,
    *,
    created_at: str,
    update_template_fields: bool = False,
) -> dict[str, Any]:
    """Insert schema template + indexes for all collections on a live pymongo Database."""
    spec = schema_for_database(db_name)
    applied: list[dict[str, Any]] = []
    for collection_spec in collections_for_spec(spec):
        applied.append(
            apply_collection_schema(
                db,
                db_name,
                collection_spec,
                created_at=created_at,
                update_template_fields=update_template_fields,
            )
        )
    primary = applied[0] if applied else {}
    return {
        "database": db_name,
        "collection": primary.get("collection"),
        "fields": primary.get("fields", []),
        "collections": applied,
    }


def schemas_status() -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for name, spec in database_schema_map().items():
        cols = collections_for_spec(spec)
        contracts[name] = {
            "collection": cols[0]["name"] if cols else spec.get("collection"),
            "field_count": len(cols[0]["fields"]) if cols else len(spec.get("fields") or ()),
            "collections": [
                {"name": c["name"], "field_count": len(c["fields"])} for c in cols
            ],
        }
    return {
        "databases": list(schema_db_containers()),
        "contracts": contracts,
        "secret_prefixes": {
            name: secret_key_prefix(name) for name in schema_db_containers()
        },
    }
