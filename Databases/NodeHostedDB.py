"""Create NodeID-hosted databases at time of operation (seed path).

Given a live NodeID (never a placeholder), create:
- {NodeID}_UserDB
- {NodeID}_LedgerDB

Register names on LucidTopsNodeDB and extend databases.secrets.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import re
from typing import Any

from DBSchemas import (
    NODE_HOSTED_BLOCKCHAIN_FIELDS,
    NODE_HOSTED_SESSIONS_FIELDS,
    NODE_HOSTED_USER_FIELDS,
    NODE_ID_FIELDS,
    resolve_collection_name,
)
from connection import get_database, get_mongo_client
from databases_secrets import (
    databases_secrets_path,
    load_databases_secrets,
    parse_secrets_file,
    utc_now,
    write_secrets_file,
)
from pull_information import pull_realworld_information, bind_operation_environ

_NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{16}$")


def validate_node_id(node_id: str) -> str:
    value = (node_id or "").strip()
    if not value:
        raise RuntimeError("NodeID missing — must be supplied at time of operation")
    if value.lower() in {"nodeid", "placeholder", "todo", "tbd", "null", "none"}:
        raise RuntimeError("NodeID must not be a placeholder — supply live NodeID")
    # Prefer 16-digit/char IDs from fixes.txt context; allow alphanumeric hashes of same length.
    if not _NODE_ID_PATTERN.match(value):
        raise RuntimeError(
            "NodeID must be a unique 16 character alphanumeric string created at operation time"
        )
    return value


def node_user_db_name(node_id: str) -> str:
    return f"{validate_node_id(node_id)}_UserDB"


def node_ledger_db_name(node_id: str) -> str:
    return f"{validate_node_id(node_id)}_LedgerDB"


def _apply_node_hosted_schemas(client: Any, *, user_db: str, ledger_db: str, stamp: str) -> dict[str, Any]:
    user = client[user_db]
    ledger = client[ledger_db]

    specs = (
        (user, "User", NODE_HOSTED_USER_FIELDS),
        (user, "Sessions", NODE_HOSTED_SESSIONS_FIELDS),
        (user, "Blockchain", NODE_HOSTED_BLOCKCHAIN_FIELDS),
        (ledger, "Blockchain", NODE_HOSTED_BLOCKCHAIN_FIELDS),
        (ledger, "BlockID", ("BlockID", "creation_timestamp", "Rewards", "LastBlockID", "Session-data-count")),
    )
    created: list[dict[str, str]] = []
    for db, collection_name, fields in specs:
        col = db[collection_name]
        col.create_index("_id")
        if not col.find_one({"_schema_template": True}):
            col.insert_one(
                {
                    "_schema_template": True,
                    "fields": list(fields),
                    "created_at": stamp,
                }
            )
        created.append({"database": db.name, "collection": collection_name})
    return {"collections": created}


def _register_on_node_db(
    *,
    node_id: str,
    user_db: str,
    ledger_db: str,
    registration: dict[str, Any],
) -> dict[str, Any]:
    db = get_database("LucidTopsNodeDB", prefer_host_publish=True)
    collection_name = resolve_collection_name("NODE_DB_COLLECTION", "NodeID")
    col = db[collection_name]
    stamp = utc_now()
    doc = {
        "NodeID": node_id,
        "UserID": str(registration.get("UserID") or "").strip(),
        "TokenID": str(registration.get("TokenID") or "").strip(),
        "Email": str(registration.get("Email") or "").strip(),
        "timestamp": stamp,
        "NodeID_UserDB_name": user_db,
        "NodeID_LedgerDB_name": ledger_db,
        "NodeID_LucidTokens": int(registration.get("NodeID_LucidTokens") or 0),
        "Registered_MAC_IDs": str(
            registration.get("Registered_MAC_IDs")
            or registration.get("HOST_PRIMARY_MAC")
            or ""
        ).strip(),
        "status": str(registration.get("status") or "active").strip(),
        "registration_docs": str(registration.get("registration_docs") or "").strip(),
        "updated_at": stamp,
    }
    for field in NODE_ID_FIELDS:
        doc.setdefault(field, None)
    col.update_one({"NodeID": node_id}, {"$set": doc, "$setOnInsert": {"created_at": stamp}}, upsert=True)
    return doc


def _extend_secrets(node_id: str, user_db: str, ledger_db: str) -> None:
    path = databases_secrets_path()
    values = parse_secrets_file(path) if path.exists() else load_databases_secrets(reload=True)
    values = dict(values)
    key = f"NODE_{node_id.upper()}_USER_DB"
    key_l = f"NODE_{node_id.upper()}_LEDGER_DB"
    values[key] = user_db
    values[key_l] = ledger_db
    values[f"{key}_CREATED_AT"] = utc_now()
    write_secrets_file(
        path,
        values,
        header="# LucidTops databases.secrets - written at time of operation",
    )
    load_databases_secrets(reload=True)


def create_node_hosted_databases(
    node_id: str,
    *,
    registration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create {NodeID}_UserDB and {NodeID}_LedgerDB on the LucidTopsNodeDB Mongo host
    (same non-Tor MongoDB process as LucidTopsNodeDB container — logical DBs).
    """
    pull = pull_realworld_information()
    bind_operation_environ(pull)

    node_id = validate_node_id(node_id)
    registration = dict(registration or {})
    if not registration.get("Registered_MAC_IDs") and not registration.get("HOST_PRIMARY_MAC"):
        registration["Registered_MAC_IDs"] = str(pull.get("primary_mac") or "")

    user_db = node_user_db_name(node_id)
    ledger_db = node_ledger_db_name(node_id)
    stamp = utc_now()

    # Logical DBs live on the LucidTopsNodeDB container instance.
    client = get_mongo_client("LucidTopsNodeDB", prefer_host_publish=True)
    try:
        schema_info = _apply_node_hosted_schemas(
            client, user_db=user_db, ledger_db=ledger_db, stamp=stamp
        )
    finally:
        client.close()

    registry_doc = _register_on_node_db(
        node_id=node_id,
        user_db=user_db,
        ledger_db=ledger_db,
        registration=registration,
    )
    _extend_secrets(node_id, user_db, ledger_db)

    return {
        "NodeID": node_id,
        "NodeID_UserDB_name": user_db,
        "NodeID_LedgerDB_name": ledger_db,
        "schemas": schema_info,
        "registry": registry_doc,
        "created_at": stamp,
    }


def node_hosted_status(node_id: str) -> dict[str, Any]:
    node_id = validate_node_id(node_id)
    user_db = node_user_db_name(node_id)
    ledger_db = node_ledger_db_name(node_id)
    client = get_mongo_client("LucidTopsNodeDB", prefer_host_publish=True)
    try:
        names = set(client.list_database_names())
        return {
            "NodeID": node_id,
            "user_db": user_db,
            "ledger_db": ledger_db,
            "user_db_exists": user_db in names,
            "ledger_db_exists": ledger_db in names,
        }
    finally:
        client.close()
