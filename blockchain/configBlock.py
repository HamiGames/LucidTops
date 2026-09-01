""" this is the blockchain configuration file the LucidTops blockchain system
this is where the genesis block is created and the blockchain is initialized
this will be a one time operation and not be changed after the initial setup 
this will input the genesis block into the ledger system (Ledger.py)
this will output the first LucidTokens to the LucidToken system (LucidToken.py)
the out put file will be located in a LucidToken folder (LucidToken-<CREATOR_ID>.png) in a Lucidtoken folder
[CREATOR_ID = Pickme-LucidTops]
each image generated as the reward tokens will use the image schema (image_schema.py=[genesisTokens])

"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
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

DEFAULT_LUCID_TOPS_ROOT = Path("/mnt/myssd/LucidTops")
LUCID_TOPS_ROOT = Path(os.environ.get("LUCID_TOPS_ROOT", DEFAULT_LUCID_TOPS_ROOT)).expanduser()

BLOCKCHAIN_DB_NAME = os.environ.get("MONGODB_MAIN_DATABASE_NAME", "lucid_master")
MONGODB_HOST = os.environ.get("MONGODB_HOST", "lucid-mongodb")
MONGODB_PORT = int(os.environ.get("MONGODB_PORT", "27017"))
MONGODB_URL = os.environ.get(
    "MONGODB_URL",
    f"mongodb://{MONGODB_HOST}:{MONGODB_PORT}/{BLOCKCHAIN_DB_NAME}",
)
NODE_MIN_MEMORY_GB = int(os.environ.get("NODE_MIN_MEMORY_GB", "50"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_mongo_client() -> Any | None:
    if MongoClient is None:
        return None
    try:
        client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client
    except PyMongoError:
        return None


def get_blockchain_db(client: Any) -> Any:
    return client[BLOCKCHAIN_DB_NAME]

GENESIS_CREATOR_ID = "Pickme-LucidTops"
GENESIS_IMAGE_SCHEMA_PROFILE = "genesisTokens"
GENESIS_LOCK_FILENAME = ".genesis_initialized"
GENESIS_MANIFEST_FILENAME = "genesis_manifest.json"
LUCID_IMAGE_SCHEMA_PROFILE_ENV = "LUCID_IMAGE_SCHEMA_PROFILE"


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
    return LUCID_TOPS_ROOT / "Lucidtoken"


def genesis_lock_path() -> Path:
    return lucidtoken_root_dir() / GENESIS_LOCK_FILENAME


def genesis_token_output_path(*, lucid_token_id: str, token_index: int = 0) -> Path:
    """Return LucidToken-<CREATOR_ID>.png path under the Lucidtoken folder."""
    root = lucidtoken_root_dir()
    if token_index <= 0:
        return root / f"LucidToken-{GENESIS_CREATOR_ID}.png"
    suffix = lucid_token_id[:8]
    return root / f"LucidToken-{GENESIS_CREATOR_ID}-{suffix}.png"


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
    manifest = {
        "creator_id": GENESIS_CREATOR_ID,
        "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
        "blockID": block.get("blockID"),
        "chainID": block.get("chainID"),
        "block_hash": block.get("block_hash"),
        "lucid_tokens_minted": len(token_outputs),
        "token_outputs": token_outputs,
        "initialized_at": utc_now(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def _mark_genesis_initialized(*, client: Any, block: dict[str, Any]) -> None:
    now = utc_now()
    _genesis_state_collection(client).update_one(
        {"state_id": GENESIS_STATE_ID},
        {
            "$set": {
                "state_id": GENESIS_STATE_ID,
                "initialized": True,
                "creator_id": GENESIS_CREATOR_ID,
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
                "creator_id": GENESIS_CREATOR_ID,
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
                owner_id=GENESIS_CREATOR_ID,
            )
            target_path.write_bytes(png_bytes)

        outputs.append(
            {
                "LucidTokenID": lucid_token_id,
                "creator_id": GENESIS_CREATOR_ID,
                "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
                "output_path": target_path.as_posix(),
                "source_path": source_path.as_posix() if source_path.exists() else None,
            }
        )
    return outputs


def initialize_blockchain_genesis(*, force: bool = False, client: Any | None = None) -> dict[str, Any]:
    """One-time genesis block setup: ledger insert, LucidToken output, immutable lock."""
    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        if is_genesis_initialized(client=mongo) and not force:
            return {
                "skipped": True,
                "reason": "blockchain genesis already initialized; use --force to regenerate",
                "creator_id": GENESIS_CREATOR_ID,
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

        chain_id = secrets.token_hex(8)
        block_id = secrets.token_hex(16)
        now = utc_now()
        ledger_last_hash = core.get_ledger_last_hash(client=mongo)
        block_hash = core.compute_block_hash(
            previous_block_hash=core.GENESIS_PREVIOUS_HASH,
            block_id=block_id,
            chain_id=chain_id,
            session_payload=[],
            ledger_last_hash=ledger_last_hash,
            winner_entity_type="genesis_creator",
            winner_entity_id=GENESIS_CREATOR_ID,
            timestamp=now,
        )

        reward_count = int(core.INITIAL_BLOCK_REWARD)
        minted_tokens = core.mint_lucid_tokens(
            client=mongo,
            owner_id=GENESIS_CREATOR_ID,
            count=reward_count,
            block_id=block_id,
        )

        block_record = {
            "blockID": block_id,
            "chainID": chain_id,
            "sessionID": None,
            "aggregate_hash": ledger_last_hash,
            "hash_algorithm": core.HASH_ALGORITHM,
            "DataInsert": [],
            "previous_block_hash": core.GENESIS_PREVIOUS_HASH,
            "block_hash": block_hash,
            "status": "genesis",
            "winner_entity_type": "genesis_creator",
            "winner_entity_id": GENESIS_CREATOR_ID,
            "tally_verified": True,
            "session_payload": [],
            "lucid_tokens_minted": len(minted_tokens),
            "block_reward": reward_count,
            "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
            "created_at": now,
            "updated_at": now,
        }
        db[BLOCKCHAIN_BLOCKS_COLLECTION].insert_one(block_record)

        core.append_ledger_record(
            client=mongo,
            session_id=None,
            aggregate_hash=block_hash,
            record_type="block",
        )

        token_outputs = _publish_genesis_token_outputs(core, minted_tokens=minted_tokens)
        manifest_path = _write_genesis_manifest(block=block_record, token_outputs=token_outputs)
        _mark_genesis_initialized(client=mongo, block=block_record)

        block_record.pop("_id", None)
        return {
            "skipped": False,
            "setup_complete": True,
            "creator_id": GENESIS_CREATOR_ID,
            "image_schema_profile": GENESIS_IMAGE_SCHEMA_PROFILE,
            "block": block_record,
            "minted_tokens": minted_tokens,
            "token_outputs": token_outputs,
            "manifest_path": manifest_path.as_posix(),
            "lucidtoken_root": lucidtoken_root_dir().as_posix(),
            "lock_file": genesis_lock_path().as_posix(),
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

    print(f"configBlock: creator_id={GENESIS_CREATOR_ID}")
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


if __name__ == "__main__":
    raise SystemExit(main())
