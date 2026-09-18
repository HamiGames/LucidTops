"""MongoDB schema for the LucidTops blockchain and immutable ledger system.

Ledger system requirements (legder.py):
- record blocks, session history, LucidToken mint/transfer/burn events
- append-only: ledger records are never deleted or modified
- ledger last aggregate_hash chains into the next block hash
- ledger records are included in block creation (session_payload + block record)
- visible publicly via the LucidLedger website
- written by master server and NodeUser under blockGov governance rules
RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

# --- collection names ---

LEDGER_RECORDS_COLLECTION = "ledger_records"
# Canonical public ledger collection in LucidTops_LedgerDB (Databases/DBSchemas.py)
LEDGER_BLOCK_ID_COLLECTION = "BlockID"
BLOCKCHAIN_BLOCKS_COLLECTION = "blockchain_blocks"
BLOCKCHAIN_STATE_COLLECTION = "blockchain_state"
LUCID_TOKENS_COLLECTION = "lucid_tokens"
SESSION_RECORDS_COLLECTION = "session_records"
SESSION_ID_LOG_COLLECTION = "session_id_log"
SESSION_KEYS_COLLECTION = "session_keys"
TALLY_RECORDS_COLLECTION = "tally_records"
TALLY_SYNC_COLLECTION = "tally_sync"
TASK_TOKENS_COLLECTION = "task_tokens"

# --- ledger hashing ---

def resolve_hash_algorithm() -> str:
    from blockchain_secrets import resolve_blockchain_hash_algorithm

    return resolve_blockchain_hash_algorithm()


def resolve_genesis_previous_hash() -> str:
    from blockchain_secrets import require_secret

    return require_secret("GENESIS_PREVIOUS_HASH")


def resolve_tally_sync_interval() -> int:
    from blockchain_secrets import resolve_tally_sync_interval_seconds

    return resolve_tally_sync_interval_seconds()


def __getattr__(name: str):
    if name == "TALLY_SYNC_INTERVAL_SECONDS":
        return resolve_tally_sync_interval()
    if name == "HASH_ALGORITHM":
        return resolve_hash_algorithm()
    if name == "GENESIS_PREVIOUS_HASH":
        return resolve_genesis_previous_hash()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --- ledger record types (append_ledger_record / LucidLedger) ---

LEDGER_RECORD_TYPES: tuple[str, ...] = (
    "session_history",
    "block",
    "lucid_token",
    "token_transfer",
    "token_burn",
)

# --- block lifecycle statuses ---
# awaiting_block / new_block = New_BlockID stage; confirmed / genesis = BlockID stage

BLOCK_STATUSES: tuple[str, ...] = (
    "awaiting_block",
    "new_block",
    "confirmed",
    "genesis",
)

# --- blockchain state identifiers ---

BLOCKCHAIN_SUPPLY_STATE_ID = "lucid_token_supply"
GENESIS_STATE_ID = "blockchain_genesis_initialized"
MASTER_LEDGER_WRITE_STATE_ID = "master_ledger_write_revoked"

# --- tally / block-winner selection ---

TALLY_ENTITY_TYPES: tuple[str, ...] = (
    "node_user",
    "master_server",
    "admin_user",
    "master_class_user",
)

# --- session statuses referenced by ledger block creation ---

SESSION_STATUSES: tuple[str, ...] = (
    "pending",
    "active",
    "ended",
    "compressed",
    "blockchain_recorded",
)

# --- field schemas ---

LEDGER_RECORDS_FIELDS: tuple[str, ...] = (
    "sessionID",
    "BlockID",
    "New_BlockID",
    "creator_id",
    "aggregate_hash",
    "hash_algorithm",
    "record_type",
    "created_at",
)

# Public LucidTops_LedgerDB.BlockID fields (matches Databases/DBSchemas.BLOCK_ID_FIELDS)
BLOCK_ID_LEDGER_FIELDS: tuple[str, ...] = (
    "BlockID",
    "creator_id",
    "creation_timestamp",
    "Rewards",
    "LastBlockID",
    "Session-data-count",
)

BLOCKCHAIN_BLOCKS_FIELDS: tuple[str, ...] = (
    "blockID",
    "New_BlockID",
    "chainID",
    "sessionID",
    "aggregate_hash",
    "hash_algorithm",
    "DataInsert",
    "previous_block_hash",
    "block_hash",
    "status",
    "creator_id",
    "winner_entity_type",
    "winner_entity_id",
    "tally_verified",
    "session_payload",
    "chunk_count",
    "packet",
    "lucid_tokens_minted",
    "block_reward",
    "tokens_log_path",
    "image_schema_profile",
    "created_at",
    "updated_at",
    "confirmed_at",
)

BLOCKCHAIN_STATE_FIELDS: tuple[str, ...] = (
    "state_id",
    "initialized",
    "creator_id",
    "blockID",
    "chainID",
    "block_hash",
    "total_minted",
    "total_burnt",
    "created_at",
    "updated_at",
)

LUCID_TOKEN_FIELDS: tuple[str, ...] = (
    "LucidTokenID",
    "owner_id",
    "blockID",
    "image_path",
    "tokens_log_path",
    "hash_algorithm",
    "status",
    "created_at",
    "updated_at",
)

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

TALLY_RECORDS_FIELDS: tuple[str, ...] = (
    "entity_type",
    "entity_id",
    "tally_points",
    "taskTokens",
    "chunk_count",
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
    LEDGER_RECORDS_COLLECTION: LEDGER_RECORDS_FIELDS,
    LEDGER_BLOCK_ID_COLLECTION: BLOCK_ID_LEDGER_FIELDS,
    BLOCKCHAIN_BLOCKS_COLLECTION: BLOCKCHAIN_BLOCKS_FIELDS,
    BLOCKCHAIN_STATE_COLLECTION: BLOCKCHAIN_STATE_FIELDS,
    LUCID_TOKENS_COLLECTION: LUCID_TOKEN_FIELDS,
    SESSION_RECORDS_COLLECTION: SESSION_RECORDS_FIELDS,
    SESSION_ID_LOG_COLLECTION: SESSION_ID_LOG_FIELDS,
    SESSION_KEYS_COLLECTION: SESSION_KEY_FIELDS,
    TALLY_RECORDS_COLLECTION: TALLY_RECORDS_FIELDS,
    TALLY_SYNC_COLLECTION: TALLY_SYNC_FIELDS,
    TASK_TOKENS_COLLECTION: TASK_TOKEN_FIELDS,
}


def schema_template(fields: tuple[str, ...]) -> dict[str, None]:
    """Return an empty document template for a ledger/blockchain collection."""
    return {field: None for field in fields}
