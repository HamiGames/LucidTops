"""The schema for the master server database.

MasterDBSchema:
- UserID (only readable with admin credentials)
- IDToken (only readable with admin credentials)
- API key (only readable with admin credentials)
- API secret (only readable with admin credentials)
- userID schema (only readable with admin credentials)
- NodeUser schema (only readable with admin credentials)
- adminUser schema (only readable with admin credentials)
- MasterClassUser schema (only readable with admin credentials)
"""

from __future__ import annotations

MASTER_CREDENTIALS_COLLECTION = "master_credentials"
USERS_COLLECTION = "users"
NODE_USERS_COLLECTION = "node_users"
ADMIN_USERS_COLLECTION = "admin_users"
MASTER_CLASS_USERS_COLLECTION = "master_class_users"
ID_TOKENS_COLLECTION = "id_tokens"
LEDGER_RECORDS_COLLECTION = "ledger_records"
BLOCKCHAIN_BLOCKS_COLLECTION = "blockchain_blocks"
SESSION_RECORDS_COLLECTION = "session_records"
SESSION_ID_LOG_COLLECTION = "session_id_log"
SESSION_KEYS_COLLECTION = "session_keys"
TALLY_RECORDS_COLLECTION = "tally_records"
TALLY_SYNC_COLLECTION = "tally_sync"
TASK_TOKENS_COLLECTION = "task_tokens"

MASTER_CREDENTIALS_FIELDS: tuple[str, ...] = (
    "UserID",
    "IDToken",
    "API_key",
    "API_secret",
    "userID_schema",
    "NodeUser_schema",
    "adminUser_schema",
    "MasterClassUser_schema",
)

USER_SCHEMA_FIELDS: tuple[str, ...] = (
    "UserID",
    "IDToken",
    "email",
    "password",
    "created_at",
    "updated_at",
    "deleted_at",
    "tier",
    "last_session_ID",
    "last_session_peer",
    "payment_method",
    "payment_status",
    "payment_amount",
    "payment_currency",
    "payment_date",
    "payment_time",
    "payment_timezone",
    "last_login_ip",
)

NODE_USER_SCHEMA_FIELDS: tuple[str, ...] = (
    "NodeUserID",
    "IDToken",
    "email",
    "password",
    "created_at",
    "updated_at",
    "deleted_at",
    "tier",
    "name",
    "node_registration_timestamp",
    "last_login_timestamp",
    "payment_method",
    "payment_status",
    "payment_amount",
    "payment_currency",
    "payment_date",
    "payment_time",
    "payment_timezone",
    "last_login_ip",
)

ADMIN_USER_SCHEMA_FIELDS: tuple[str, ...] = (
    "adminUserID",
    "IDToken",
    "access_level",
    "access_type",
    "admin_registration_timestamp",
    "last_login_timestamp",
    "payment_method",
    "payment_status",
    "payment_amount",
    "payment_currency",
    "payment_date",
    "payment_time",
    "payment_timezone",
    "last_login_ip",
)

MASTER_CLASS_USER_SCHEMA_FIELDS: tuple[str, ...] = (
    "MasterClassUserID",
    "IDToken",
    "access_level",
    "access_type",
    "masterclass_registration_timestamp",
    "last_login_timestamp",
    "payment_method",
    "payment_status",
    "payment_amount",
    "payment_currency",
    "payment_date",
    "payment_time",
    "payment_timezone",
    "last_login_ip",
)

# --- SessionCore.py (sessions/SessionCore.py) ---

SESSION_ID_LENGTH = 10
SESSION_STATUSES: tuple[str, ...] = ("pending", "active", "ended", "compressed")

SESSION_RECORDS_FIELDS: tuple[str, ...] = (
    "sessionID",
    "sessionKey",
    "sessionData",
    "sessionStatus",
    "sessionType",
    "sessionTime",
    "sessionDate",
    "hostUserID",
    "viewerUserID",
    "userIDs",
    "session_records",
    "participant_agreements",
    "all_agreed",
    "compressed",
    "aggregate_hash",
    "chunked_payload",
    "DataInsert",
    "created_at",
    "updated_at",
    "ended_at",
)

SESSION_ID_LOG_FIELDS: tuple[str, ...] = (
    "sessionID",
    "hostUserID",
    "userIDs",
    "source",
    "status",
    "created_at",
    "recorded_at",
)

SESSION_KEY_FIELDS: tuple[str, ...] = (
    "sessionID",
    "sessionKey",
    "aggregate_hash",
    "DataInsert",
    "awaiting_block",
    "hash_algorithm",
    "created_at",
    "updated_at",
)

LEDGER_RECORDS_FIELDS: tuple[str, ...] = (
    "sessionID",
    "aggregate_hash",
    "hash_algorithm",
    "record_type",
    "created_at",
)

BLOCKCHAIN_BLOCKS_FIELDS: tuple[str, ...] = (
    "blockID",
    "chainID",
    "sessionID",
    "aggregate_hash",
    "hash_algorithm",
    "DataInsert",
    "previous_block_hash",
    "block_hash",
    "status",
    "winner_entity_type",
    "winner_entity_id",
    "tally_verified",
    "created_at",
    "updated_at",
)

# --- tally.py (blockchain/tally.py) + sessions/compress.py + CreateBlock.py ---

TALLY_ENTITY_TYPES: tuple[str, ...] = (
    "node_user",
    "master_server",
    "admin_user",
    "master_class_user",
)

TALLY_SYNC_INTERVAL_SECONDS = 30

TALLY_RECORDS_FIELDS: tuple[str, ...] = (
    "entity_type",
    "entity_id",
    "tally_points",
    "taskTokens",
    "sessionID",
    "sessionID_verified",
    "last_win_at",
    "last_reset_at",
    "created_at",
    "updated_at",
)

TALLY_SYNC_FIELDS: tuple[str, ...] = (
    "sync_batch_id",
    "seeded_at",
    "seed_interval_seconds",
    "tally_snapshot",
    "target",
    "created_at",
)

TASK_TOKEN_FIELDS: tuple[str, ...] = (
    "taskToken",
    "sessionID",
    "entity_type",
    "entity_id",
    "aggregate_hash",
    "created_at",
)

COLLECTION_SCHEMAS: dict[str, tuple[str, ...]] = {
    MASTER_CREDENTIALS_COLLECTION: MASTER_CREDENTIALS_FIELDS,
    USERS_COLLECTION: USER_SCHEMA_FIELDS,
    NODE_USERS_COLLECTION: NODE_USER_SCHEMA_FIELDS,
    ADMIN_USERS_COLLECTION: ADMIN_USER_SCHEMA_FIELDS,
    MASTER_CLASS_USERS_COLLECTION: MASTER_CLASS_USER_SCHEMA_FIELDS,
    SESSION_RECORDS_COLLECTION: SESSION_RECORDS_FIELDS,
    SESSION_ID_LOG_COLLECTION: SESSION_ID_LOG_FIELDS,
    SESSION_KEYS_COLLECTION: SESSION_KEY_FIELDS,
    LEDGER_RECORDS_COLLECTION: LEDGER_RECORDS_FIELDS,
    BLOCKCHAIN_BLOCKS_COLLECTION: BLOCKCHAIN_BLOCKS_FIELDS,
    TALLY_RECORDS_COLLECTION: TALLY_RECORDS_FIELDS,
    TALLY_SYNC_COLLECTION: TALLY_SYNC_FIELDS,
    TASK_TOKENS_COLLECTION: TASK_TOKEN_FIELDS,
}


def schema_template(fields: tuple[str, ...]) -> dict[str, None]:
    return {field: None for field in fields}
