"""Import facade for the LucidTops blockchain container.
Exports:
- pull_information / secrets bootstrap
- configBlock genesis initialization
- image_schema LucidToken rendering
- legder append-only ledger API
- Blockchain-core hashing, create_block, mint/transfer
- ConnectBlockRoutes FastAPI connection helpers
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

for path in (BLOCKCHAIN_DIR,):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_blockchain_module(filename: str) -> ModuleType:
    """Load blockchain modules whose filenames contain hyphens or non-standard names."""
    module_path = BLOCKCHAIN_DIR / filename
    if not module_path.exists():
        raise FileNotFoundError(f"Blockchain module not found: {module_path}")
    module_name = filename.replace("-", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_core = load_blockchain_module("Blockchain-core.py")

from blockchain_schema import (  # noqa: E402
    COLLECTION_SCHEMAS,
    LEDGER_RECORDS_COLLECTION,
    LEDGER_RECORDS_FIELDS,
    schema_template,
)
from blockchain_secrets import (  # noqa: E402
    blockchain_secrets_status,
    ensure_blockchain_secrets,
    load_blockchain_secrets,
    resolve_genesis_creator_id,
    resolve_master_server_id,
    write_blockchain_secrets_from_pull,
    write_blockchain_secrets_template,
)
from configBlock import (  # noqa: E402
    GENESIS_IMAGE_SCHEMA_PROFILE,
    GENESIS_MANIFEST_FILENAME,
    GENESIS_STATE_ID,
    genesis_lock_path,
    genesis_token_output_path,
    initialize_blockchain_genesis,
    is_genesis_initialized,
    lucidtoken_root_dir,
    setup_blockchain_config,
    tokens_log_path,
    write_tokens_log,
)
from image_schema import (  # noqa: E402
    CHARACTER_PERSONALITY_PROFILES,
    GENESIS_SCHEMA_PROFILE,
    SCHEMA_PROFILES,
    STANDARD_SCHEMA_PROFILE,
    build_generation_prompt,
    render_token_image,
    resolve_schema_profile,
    schema_metadata,
    select_character_profile,
)
from pull_information import (  # noqa: E402
    bind_operation_environ,
    live_primary_ip,
    live_primary_mac,
    pull_blockchain_hardware,
    pull_realworld_information,
)

DEFAULT_STANDARD_PROFILE = STANDARD_SCHEMA_PROFILE

# Blockchain-core.py — block creation, hashing, governance
HASH_ALGORITHM = _core.HASH_ALGORITHM
GENESIS_PREVIOUS_HASH = _core.GENESIS_PREVIOUS_HASH
TOTAL_TOKEN_SUPPLY = _core.TOTAL_TOKEN_SUPPLY
INITIAL_BLOCK_REWARD = _core.INITIAL_BLOCK_REWARD
HALVING_MINTED_FRACTION = _core.HALVING_MINTED_FRACTION
BURN_DIVISOR = _core.BURN_DIVISOR
MAX_TOKEN_IMAGE_BYTES = _core.MAX_TOKEN_IMAGE_BYTES
MAX_BLOCK_BYTES = _core.MAX_BLOCK_BYTES
MAX_SESSIONS_PER_BLOCK = _core.MAX_SESSIONS_PER_BLOCK
MIN_BLOCK_INTERVAL_SECONDS = _core.MIN_BLOCK_INTERVAL_SECONDS
LUCID_TOKEN_DIR_NAME = _core.LUCID_TOKEN_DIR_NAME
LUCID_TOKEN_FILE_PREFIX = _core.LUCID_TOKEN_FILE_PREFIX
LUCID_TOKENS_COLLECTION = _core.LUCID_TOKENS_COLLECTION
BLOCKCHAIN_STATE_COLLECTION = _core.BLOCKCHAIN_STATE_COLLECTION
BLOCKCHAIN_SUPPLY_STATE_ID = _core.BLOCKCHAIN_SUPPLY_STATE_ID
BLOCK_STATUSES = _core.BLOCK_STATUSES
LEDGER_RECORD_TYPES = _core.LEDGER_RECORD_TYPES

sha512_hex = _core.sha512_hex
compute_block_hash = _core.compute_block_hash
block_reward_for_minted = _core.block_reward_for_minted
calculate_transfer_burn = _core.calculate_transfer_burn
create_block = _core.create_block
validate_blockchain_governance = _core.validate_blockchain_governance
select_tally_winner = _core.select_tally_winner

# legder.py — ledger system recording
append_ledger_record = _core.append_ledger_record
get_ledger_last_hash = _core.get_ledger_last_hash
record_session_history = _core.record_session_history

# LucidToken generation and transfers
generate_lucid_token_id = _core.generate_lucid_token_id
lucid_token_storage_dir = _core.lucid_token_storage_dir
lucid_token_image_path = _core.lucid_token_image_path
save_lucid_token_image = _core.save_lucid_token_image
mint_lucid_tokens = _core.mint_lucid_tokens
transfer_lucid_tokens = _core.transfer_lucid_tokens
get_token_supply_state = _core.get_token_supply_state


class _MasterServerIdentity:
    """Lazy identity string: GENESIS_CREATOR_ID is MASTER_SERVER_ID."""

    __slots__ = ()

    def __str__(self) -> str:
        return resolve_master_server_id()

    def __repr__(self) -> str:
        return resolve_master_server_id()

    def __eq__(self, other: object) -> bool:
        value = str(self)
        if isinstance(other, str):
            return value == other
        return value == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    def __bool__(self) -> bool:
        return bool(str(self))

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)


# GENESIS_CREATOR_ID = MASTER_SERVER_ID (same MasterServer identity)
MASTER_SERVER_ID = _MasterServerIdentity()
GENESIS_CREATOR_ID = MASTER_SERVER_ID


def __getattr__(name: str) -> Any:
    if name in {"GENESIS_CREATOR_ID", "MASTER_SERVER_ID"}:
        return resolve_master_server_id()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "BLOCKCHAIN_STATE_COLLECTION",
    "BLOCKCHAIN_SUPPLY_STATE_ID",
    "BLOCK_STATUSES",
    "BURN_DIVISOR",
    "COLLECTION_SCHEMAS",
    "LEDGER_RECORDS_COLLECTION",
    "LEDGER_RECORDS_FIELDS",
    "DEFAULT_STANDARD_PROFILE",
    "GENESIS_CREATOR_ID",
    "MASTER_SERVER_ID",
    "GENESIS_IMAGE_SCHEMA_PROFILE",
    "GENESIS_MANIFEST_FILENAME",
    "GENESIS_PREVIOUS_HASH",
    "GENESIS_SCHEMA_PROFILE",
    "GENESIS_STATE_ID",
    "HALVING_MINTED_FRACTION",
    "HASH_ALGORITHM",
    "INITIAL_BLOCK_REWARD",
    "LEDGER_RECORD_TYPES",
    "LUCID_TOKEN_DIR_NAME",
    "LUCID_TOKEN_FILE_PREFIX",
    "LUCID_TOKENS_COLLECTION",
    "MAX_BLOCK_BYTES",
    "MAX_SESSIONS_PER_BLOCK",
    "MAX_TOKEN_IMAGE_BYTES",
    "MIN_BLOCK_INTERVAL_SECONDS",
    "SCHEMA_PROFILES",
    "TOTAL_TOKEN_SUPPLY",
    "append_ledger_record",
    "bind_operation_environ",
    "block_reward_for_minted",
    "blockchain_secrets_status",
    "build_generation_prompt",
    "calculate_transfer_burn",
    "connect_blockchain_routes",
    "compute_block_hash",
    "create_block",
    "ensure_blockchain_secrets",
    "generate_lucid_token_id",
    "genesis_lock_path",
    "genesis_token_output_path",
    "get_ledger_last_hash",
    "get_token_supply_state",
    "initialize_blockchain_container",
    "initialize_blockchain_genesis",
    "is_genesis_initialized",
    "live_primary_ip",
    "live_primary_mac",
    "load_blockchain_module",
    "load_blockchain_secrets",
    "lucid_token_image_path",
    "lucid_token_storage_dir",
    "lucidtoken_root_dir",
    "mint_lucid_tokens",
    "pull_blockchain_hardware",
    "pull_realworld_information",
    "record_session_history",
    "render_token_image",
    "resolve_genesis_creator_id",
    "resolve_master_server_id",
    "resolve_schema_profile",
    "save_lucid_token_image",
    "schema_template",
    "schema_metadata",
    "select_character_profile",
    "select_tally_winner",
    "setup_blockchain_config",
    "sha512_hex",
    "tokens_log_path",
    "transfer_lucid_tokens",
    "write_blockchain_secrets_from_pull",
    "write_blockchain_secrets_template",
    "write_tokens_log",
    "validate_blockchain_governance",
)


def connect_blockchain_routes(*, client: Any | None = None) -> dict[str, Any]:
    module = load_blockchain_module("ConnectBlockRoutes.py")
    return module.connect_blockchain_routes(client=client)


def initialize_blockchain_container(*, force: bool = False) -> dict[str, Any]:
    """Bootstrap blockchain container: pull, secrets, genesis when required."""
    pull_blockchain_hardware(bind_environ=True)
    ensure_blockchain_secrets(force=False)
    if is_genesis_initialized() and not force:
        return {
            "skipped": True,
            "reason": "blockchain genesis already initialized",
            "creator_id": resolve_master_server_id(),
            "MASTER_SERVER_ID": resolve_master_server_id(),
            "GENESIS_CREATOR_ID": resolve_master_server_id(),
            "lock_file": genesis_lock_path().as_posix(),
        }
    return setup_blockchain_config(force=force)
