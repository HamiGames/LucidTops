"""The schema for the NodeUserID hosted database (mongodb database design).

Each file will have the following fields:
- UserID (only readable with admin credentials)
- IDToken (only readable with admin credentials)
- current_session_ID (only readable with admin credentials)
- current_session_peer (only readable with admin credentials)
- current_session_status (only readable with admin credentials)

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
