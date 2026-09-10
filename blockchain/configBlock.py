"""Blockchain configuration: one-time genesis block creation and blockchain initialization.
Creates genesis BlockID (SHA-512), inserts into LucidTops_LedgerDB ledger, mints LucidTokens,
writes Tokens.log on the creator console. Creator ID and previous hash come from hardware pull
at time of operation (never placeholders).

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:  # pragma: no cover
    MongoClient = None  # type: ignore[misc, assignment]
    PyMongoError = Exception  # type: ignore[misc, assignment]

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BLOCKCHAIN_DIR.parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import BLOCKCHAIN_BLOCKS_COLLECTION, GENESIS_STATE_ID  # noqa: E402
from blockchain_secrets import (  # noqa: E402
    ensure_blockchain_secrets,
    require_secret,
    resolve_genesis_creator_id,
    resolve_lucid_tops_root,
    resolve_mongodb_server_selection_timeout_ms,
    resolve_mongodb_url,
    resolve_node_min_memory_gb,
)
from pull_information import pull_blockchain_hardware  # noqa: E402

GENESIS_IMAGE_SCHEMA_PROFILE = "genesisTokens"
GENESIS_LOCK_FILENAME = ".genesis_initialized"
GENESIS_MANIFEST_FILENAME = "genesis_manifest.json"
TOKENS_LOG_FILENAME = "Tokens.log"
LUCID_IMAGE_SCHEMA_PROFILE_ENV = "LUCID_IMAGE_SCHEMA_PROFILE"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_operation_secrets(*, force: bool = False) -> Path:
    """Pull hardware facts and ensure blockchain.secrets before any genesis work."""
    pull_blockchain_hardware(bind_environ=True)
    return ensure_blockchain_secrets(force=force)


def _resolve_blockchain_db_name() -> str:
    return require_secret("MONGODB_MAIN_DATABASE_NAME")


def get_mongo_client() -> Any | None:
    if MongoClient is None:
        return None
    try:
        client = MongoClient(
            resolve_mongodb_url(),
            serverSelectionTimeoutMS=resolve_mongodb_server_selection_timeout_ms(),
        )
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None


def get_blockchain_db(client: Any) -> Any:
    """Return LucidTops_LedgerDB (or configured main blockchain/ledger database)."""
    return client[_resolve_blockchain_db_name()]


def _load_blockchain_core() -> Any:
    """Load Blockchain-core.py (hyphenated module name)."""
    module_path = BLOCKCHAIN_DIR / "Blockchain-core.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Blockchain core module not found: {module_path}")
    module_name = "blockchain_core"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lucidtoken_root_dir() -> Path:
    """Resolve Lucidtoken output root (Dockerfile-compatible via LUCID_TOPS_ROOT)."""
    return resolve_lucid_tops_root() / "Lucidtoken"


def tokens_log_path(*, owner_id: str | None = None) -> Path:
    """Tokens.log on the creator_id console (Blockchain.txt)."""
    creator_id = owner_id or resolve_genesis_creator_id()
    return lucidtoken_root_dir() / creator_id / TOKENS_LOG_FILENAME


def write_tokens_log(*, owner_id: str, lucid_token_ids: list[str]) -> Path:
    """Append one LucidTokenID per line to Tokens.log."""
    path = tokens_log_path(owner_id=owner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for token_id in lucid_token_ids:
            handle.write(f"{token_id}\n")
    return path


def genesis_lock_path() -> Path:
    return lucidtoken_root_dir() / GENESIS_LOCK_FILENAME


def genesis_token_output_path(*, lucid_token_id: str, token_index: int = 0) -> Path:
    """Return LucidToken-<CREATOR_ID>.png path under the Lucidtoken folder."""
    root = lucidtoken_root_dir()
    creator_id = resolve_genesis_creator_id()
    if token_index <= 0:
        return root / f"LucidToken-{creator_id}.png"
    suffix = lucid_token_id[:8]
    return root / f"LucidToken-{creator_id}-{suffix}.png"


def _genesis_state_collection(client: Any) -> Any:
    core = _load_blockchain_core()
    return get_blockchain_db(client)[core.BLOCKCHAIN_STATE_COLLECTION]


def is_genesis_initialized(*, client: Any | None = None) -> bool:
    """Return True when genesis setup has already completed."""
    if genesis_lock_path().exists():
        return True

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return False
    owns_client = client is None
    try:
        if (
            get_blockchain_db(mongo)[BLOCKCHAIN_BLOCKS_COLLECTION].find_one({"status": "genesis"})
            is not None
        ):
            return True
        core = _load_blockchain_core()
        record = _genesis_state_collection(mongo).find_one({"state_id": GENESIS_STATE_ID})
        return bool(record and record.get("initialized"))
    finally:
        if owns_client:
            mongo.close()


def _write_genesis_manifest(*, block: dict[str, Any], token_outputs: list[dict[str, Any]]) -> Path:
    root = lucidtoken_root_dir()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / GENESIS_MANIFEST_FILENAME
    creator_id = resolve_genesis_creator_id()
    manifest = {
        "creator_id": creator_id,
        "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
        "blockID": block.get("blockID"),
        "New_BlockID": block.get("New_BlockID"),
        "chainID": block.get("chainID"),
        "block_hash": block.get("block_hash"),
        "lucid_tokens_minted": len(token_outputs),
        "token_outputs": token_outputs,
        "tokens_log_path": tokens_log_path(owner_id=creator_id).as_posix(),
        "initialized_at": utc_now(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def _mark_genesis_initialized(*, client: Any, block: dict[str, Any]) -> None:
    now = utc_now()
    creator_id = resolve_genesis_creator_id()
    _genesis_state_collection(client).update_one(
        {"state_id": GENESIS_STATE_ID},
        {
            "$set": {
                "state_id": GENESIS_STATE_ID,
                "initialized": True,
                "creator_id": creator_id,
                "blockID": block.get("blockID"),
                "chainID": block.get("chainID"),
                "block_hash": block.get("block_hash"),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    lock_path = genesis_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "initialized": True,
                "creator_id": creator_id,
                "blockID": block.get("blockID"),
                "timestamp": now,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _publish_genesis_token_outputs(
    core: Any,
    *,
    minted_tokens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Copy genesis reward PNGs to Lucidtoken/LucidToken-<CREATOR_ID>.png paths."""
    outputs: list[dict[str, Any]] = []
    creator_id = resolve_genesis_creator_id()
    for index, token in enumerate(minted_tokens):
        lucid_token_id = str(token.get("LucidTokenID") or "")
        source_path = Path(str(token.get("image_path") or ""))
        target_path = genesis_token_output_path(lucid_token_id=lucid_token_id, token_index=index)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path.exists():
            shutil.copy2(source_path, target_path)
        else:
            png_bytes = core._render_lucid_token_png(
                lucid_token_id=lucid_token_id,
                owner_id=creator_id,
            )
            target_path.write_bytes(png_bytes)

        outputs.append(
            {
                "LucidTokenID": lucid_token_id,
                "creator_id": creator_id,
                "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
                "output_path": target_path.as_posix(),
                "source_path": source_path.as_posix() if source_path.exists() else None,
            }
        )
    return outputs


def initialize_blockchain_genesis(*, force: bool = False, client: Any | None = None) -> dict[str, Any]:
    """One-time genesis: pull hardware, secrets, SHA-512 BlockID, ledger, Tokens.log."""
    ensure_operation_secrets(force=False)

    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    creator_id = resolve_genesis_creator_id()

    try:
        if is_genesis_initialized(client=mongo) and not force:
            return {
                "skipped": True,
                "reason": "blockchain genesis already initialized; use --force to regenerate",
                "creator_id": creator_id,
                "lock_file": genesis_lock_path().as_posix(),
            }

        os.environ[LUCID_IMAGE_SCHEMA_PROFILE_ENV] = GENESIS_IMAGE_SCHEMA_PROFILE
        core = _load_blockchain_core()
        db = get_blockchain_db(mongo)

        if force:
            db[BLOCKCHAIN_BLOCKS_COLLECTION].delete_many({"status": "genesis"})
            _genesis_state_collection(mongo).delete_one({"state_id": GENESIS_STATE_ID})
            lock_path = genesis_lock_path()
            if lock_path.exists():
                lock_path.unlink()

        existing_genesis = db[BLOCKCHAIN_BLOCKS_COLLECTION].find_one({"status": "genesis"})
        if existing_genesis and not force:
            return {
                "skipped": True,
                "reason": "genesis block already present in ledger",
                "blockID": existing_genesis.get("blockID"),
            }

        now = utc_now()
        ledger_last_hash = core.get_ledger_last_hash(client=mongo)
        previous_hash = str(core.GENESIS_PREVIOUS_HASH)

        # chainID and New_BlockID derived at operation time from hardware-bound creator + entropy
        chain_material = f"chain:{creator_id}:{now}:{core.sha512_hex(creator_id)[:16]}"
        chain_id = core.sha512_hex(chain_material)[:16]
        new_block_material = (
            f"New_BlockID:genesis:{creator_id}:{previous_hash}:{ledger_last_hash}:{now}"
        )
        new_block_id = core.sha512_hex(new_block_material)

        block_hash = core.compute_block_hash(
            previous_block_hash=previous_hash,
            block_id=new_block_id,
            chain_id=chain_id,
            session_payload=[],
            ledger_last_hash=ledger_last_hash,
            winner_entity_type="genesis_creator",
            winner_entity_id=creator_id,
            timestamp=now,
        )
        # BlockID is the SHA-512 block identity (Blockchain.txt)
        block_id = block_hash

        reward_count = int(core.INITIAL_BLOCK_REWARD)
        minted_tokens = core.mint_lucid_tokens(
            client=mongo,
            owner_id=creator_id,
            count=reward_count,
            block_id=block_id,
        )
        token_ids = [str(t.get("LucidTokenID") or "") for t in minted_tokens if t.get("LucidTokenID")]
        tokens_log = write_tokens_log(owner_id=creator_id, lucid_token_ids=token_ids)

        block_record = {
            "blockID": block_id,
            "New_BlockID": new_block_id,
            "chainID": chain_id,
            "sessionID": None,
            "aggregate_hash": ledger_last_hash,
            "hash_algorithm": core.HASH_ALGORITHM,
            "DataInsert": [],
            "previous_block_hash": previous_hash,
            "block_hash": block_hash,
            "status": "genesis",
            "creator_id": creator_id,
            "winner_entity_type": "genesis_creator",
            "winner_entity_id": creator_id,
            "tally_verified": True,
            "session_payload": [],
            "chunk_count": 0,
            "packet": [],
            "lucid_tokens_minted": len(minted_tokens),
            "block_reward": reward_count,
            "tokens_log_path": tokens_log.as_posix(),
            "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
            "created_at": now,
            "updated_at": now,
            "confirmed_at": now,
        }
        db[BLOCKCHAIN_BLOCKS_COLLECTION].insert_one(block_record)

        core.append_ledger_record(
            client=mongo,
            session_id=None,
            aggregate_hash=block_hash,
            record_type="block",
            block_id=block_id,
            new_block_id=new_block_id,
            creator_id=creator_id,
        )

        token_outputs = _publish_genesis_token_outputs(core, minted_tokens=minted_tokens)
        manifest_path = _write_genesis_manifest(block=block_record, token_outputs=token_outputs)
        _mark_genesis_initialized(client=mongo, block=block_record)

        block_record.pop("_id", None)
        return {
            "skipped": False,
            "setup_complete": True,
            "creator_id": creator_id,
            "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
            "block": block_record,
            "minted_tokens": minted_tokens,
            "token_outputs": token_outputs,
            "tokens_log_path": tokens_log.as_posix(),
            "manifest_path": manifest_path.as_posix(),
            "lucidtoken_root": lucidtoken_root_dir().as_posix(),
            "lock_file": genesis_lock_path().as_posix(),
            "database": _resolve_blockchain_db_name(),
            "supply": core.get_token_supply_state(client=mongo),
        }
    finally:
        if owns_client and mongo is not None:
            mongo.close()


def setup_blockchain_config(*, force: bool = False) -> dict[str, Any]:
    """Public entry point for blockchain one-time configuration."""
    return initialize_blockchain_genesis(force=force)


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops blockchain genesis configuration")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate genesis block even if already initialized",
    )
    args = parser.parse_args()

    ensure_operation_secrets()
    creator_id = resolve_genesis_creator_id()
    print(f"configBlock: creator_id={creator_id}")
    print(f"configBlock: image_schema_profile={GENESIS_IMAGE_SCHEMA_PROFILE}")
    print(f"configBlock: lucidtoken_root={lucidtoken_root_dir().as_posix()}")

    result = setup_blockchain_config(force=args.force)
    print("LucidTops blockchain genesis configuration complete.")
    for key, value in result.items():
        if key in {"block", "minted_tokens", "token_outputs", "supply"}:
            print(f"  {key}: {json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value}")
        else:
            print(f"  {key}: {value}")
    return 0


def __getattr__(name: str) -> Any:
    if name == "LUCID_TOPS_ROOT":
        return resolve_lucid_tops_root()
    if name == "GENESIS_CREATOR_ID":
        return resolve_genesis_creator_id()
    if name == "MASTER_SERVER_ID":
        from blockchain_secrets import resolve_master_server_id

        return resolve_master_server_id()
    if name == "BLOCKCHAIN_DB_NAME":
        return _resolve_blockchain_db_name()
    if name == "MONGODB_URL":
        return resolve_mongodb_url()
    if name == "NODE_MIN_MEMORY_GB":
        return resolve_node_min_memory_gb()
    if name == "MONGODB_HOST":
        from blockchain_secrets import resolve_mongodb_host

        return resolve_mongodb_host()
    if name == "MONGODB_PORT":
        from blockchain_secrets import resolve_mongodb_port

        return resolve_mongodb_port()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
