""" the protocol for creating a new block in the blockchain system
create block protocol:
- the create block is used to create a new block in the blockchain system
- the create block is used to create a new block in the blockchain system by the master server
- the create block is used to create a new block in the blockchain system by the NodeUser
- the create block is used to create a new block in the blockchain system by the User
- the create block is used to create a new block in the blockchain system by the administrator
- the create block is used to create a new block in the blockchain system by the system
- the create block is used to create a new block in the blockchain system by the network
- the create block function will return a new block hash id that is included in the next block in the blockchain system
- a NodeUser or master server must be present in the blockchain system to create a new block

limitations:
- the selection for block creation is determined by the number of taskTokens present in the tally record system and the corrisponding NodeUser or master server
- the block creation process will be performed on the master server database or NodeUser
- the block creation must add the block hash id to the blockchain ledger system
- the block creation must follow the blockchain governance protocol
- the validation of the block creation is determined by the blockchain governance protocol
- the block creation returns a value of LucidTokens that are distributed to the NodeUser or master server
- the selection process for the block creation must be validated by the tally system (tally.py)
- the block creation must be validated by the blockchain governance protocol (blockGov.py)
- the new block must be added to the blockchain system and ledger system

"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Literal

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    BLOCKCHAIN_BLOCKS_COLLECTION,
    LEDGER_RECORDS_COLLECTION,
)
from configBlock import get_blockchain_db, get_mongo_client  # noqa: E402

BlockCreatorActor = Literal["master_server", "node_user"]
InvokerActor = Literal[
    "master_server",
    "node_user",
    "user",
    "administrator",
    "system",
    "network",
]

BLOCK_CREATOR_ACTORS: tuple[str, ...] = ("master_server", "node_user")
INVOKER_ACTORS: tuple[str, ...] = (
    "master_server",
    "node_user",
    "user",
    "administrator",
    "system",
    "network",
)


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


def _validate_actor_present(*, actor_type: str, node_user_id: str | None) -> None:
    """Require a NodeUser or master server actor before block creation."""
    if actor_type not in BLOCK_CREATOR_ACTORS:
        raise PermissionError(
            "Block creation requires a NodeUser or master server actor; "
            f"received actor_type={actor_type!r}"
        )
    if actor_type == "node_user" and not (node_user_id and node_user_id.strip()):
        raise ValueError("node_user_id is required when actor_type is node_user")


def _is_genesis_pending(*, client: Any) -> bool:
    db = get_blockchain_db(client)
    existing = db[BLOCKCHAIN_BLOCKS_COLLECTION].find_one(
        {
            "status": {"$in": ["confirmed", "genesis"]},
            "block_hash": {"$exists": True, "$ne": None},
        },
        sort=[("created_at", -1)],
    )
    return existing is None


def validate_tally_selection(*, client: Any, core: Any, is_genesis: bool) -> dict[str, Any]:
    """Validate block creator selection via the tally system (select_tally_winner)."""
    winner = core.select_tally_winner(client=client)
    task_tokens = winner.get("taskTokens") or []
    token_count = len(task_tokens) if isinstance(task_tokens, list) else 0
    tally_points = int(winner.get("tally_points") or 0)

    if not is_genesis and not winner.get("tally_verified"):
        raise PermissionError("Tally winner must be verified against sessionID log")

    if not is_genesis and token_count <= 0 and tally_points <= 0:
        winner_type = str(winner.get("winner_entity_type") or "")
        if winner_type != "master_server":
            raise PermissionError(
                "Block creation requires taskTokens in the tally record system "
                "for the corresponding NodeUser or master server"
            )

    return {
        "winner_entity_type": winner.get("winner_entity_type"),
        "winner_entity_id": winner.get("winner_entity_id"),
        "tally_verified": bool(winner.get("tally_verified")),
        "tally_points": tally_points,
        "taskTokens": list(task_tokens) if isinstance(task_tokens, list) else [],
        "taskToken_count": token_count,
        "sessionID": winner.get("sessionID"),
    }


def validate_block_governance(
    *,
    client: Any,
    core: Any,
    node_user_id: str | None,
    reported_memory_gb: int | None,
) -> dict[str, Any]:
    """Validate block creation via the blockchain governance protocol (blockGov.py)."""
    return core.validate_blockchain_governance(
        node_user_id=node_user_id,
        operation="blockchain_create",
        reported_memory_gb=reported_memory_gb,
        client=client,
    )


def _verify_blockchain_and_ledger_writes(
    *,
    client: Any,
    core: Any,
    block_hash: str,
) -> dict[str, Any]:
    """Confirm the new block exists in blockchain_blocks and ledger_records."""
    db = get_blockchain_db(client)
    block_record = db[BLOCKCHAIN_BLOCKS_COLLECTION].find_one(
        {"block_hash": block_hash},
        {"_id": 0},
    )
    if block_record is None:
        raise RuntimeError("New block was not written to the blockchain system")

    ledger_record = db[LEDGER_RECORDS_COLLECTION].find_one(
        {"aggregate_hash": block_hash, "record_type": "block"},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if ledger_record is None:
        raise RuntimeError("New block hash was not written to the blockchain ledger system")

    ledger_last_hash = core.get_ledger_last_hash(client=client)
    return {
        "blockchain_collection": BLOCKCHAIN_BLOCKS_COLLECTION,
        "ledger_collection": LEDGER_RECORDS_COLLECTION,
        "block_record": block_record,
        "ledger_record": ledger_record,
        "ledger_last_hash": ledger_last_hash,
    }


def create_new_block(
    *,
    actor_type: BlockCreatorActor = "master_server",
    invoker: InvokerActor | None = None,
    node_user_id: str | None = None,
    chain_id: str | None = None,
    reported_memory_gb: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run the create-block protocol: tally, governance, block + ledger writes, LucidToken reward."""
    _validate_actor_present(actor_type=actor_type, node_user_id=node_user_id)
    if invoker is not None and invoker not in INVOKER_ACTORS:
        raise ValueError(f"Unsupported invoker actor: {invoker}")

    resolved_node_user_id = node_user_id.strip() if node_user_id else None
    if actor_type == "master_server":
        resolved_node_user_id = None

    core = _load_blockchain_core()
    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Blockchain database is unavailable")

    try:
        is_genesis = _is_genesis_pending(client=mongo)
        tally = validate_tally_selection(client=mongo, core=core, is_genesis=is_genesis)
        governance = validate_block_governance(
            client=mongo,
            core=core,
            node_user_id=resolved_node_user_id,
            reported_memory_gb=reported_memory_gb,
        )

        creation = core.create_block(
            chain_id=chain_id,
            node_user_id=resolved_node_user_id,
            reported_memory_gb=reported_memory_gb,
            client=mongo,
        )

        block = creation.get("block") or {}
        block_hash = str(block.get("block_hash") or "")
        if not block_hash:
            raise RuntimeError("Block creation did not return a block_hash")

        writes = _verify_blockchain_and_ledger_writes(
            client=mongo,
            core=core,
            block_hash=block_hash,
        )
        minted_tokens = list(creation.get("minted_tokens") or [])

        return {
            "block_hash": block_hash,
            "blockID": block.get("blockID"),
            "previous_block_hash": block.get("previous_block_hash"),
            "chainID": block.get("chainID"),
            "actor_type": actor_type,
            "invoker": invoker or actor_type,
            "node_user_id": resolved_node_user_id,
            "tally": tally,
            "governance": governance,
            "lucid_tokens_minted": len(minted_tokens),
            "minted_tokens": minted_tokens,
            "block": block,
            "supply": creation.get("supply"),
            "blockchain": {
                "collection": writes["blockchain_collection"],
                "status": block.get("status"),
                "record": writes["block_record"],
            },
            "ledger": {
                "collection": writes["ledger_collection"],
                "record_type": "block",
                "aggregate_hash": block_hash,
                "record": writes["ledger_record"],
                "ledger_last_hash": writes["ledger_last_hash"],
            },
        }
    finally:
        if owns_client and mongo is not None:
            mongo.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops create-block protocol")
    parser.add_argument(
        "--actor-type",
        choices=list(BLOCK_CREATOR_ACTORS),
        default="master_server",
        help="Block creator actor (NodeUser or master server)",
    )
    parser.add_argument(
        "--invoker",
        choices=list(INVOKER_ACTORS),
        default=None,
        help="Optional invoking actor (user, administrator, system, network, etc.)",
    )
    parser.add_argument("--node-user-id", default=None, help="NodeUserID when actor-type is node_user")
    parser.add_argument("--chain-id", default=None, help="Optional chainID override")
    parser.add_argument(
        "--reported-memory-gb",
        type=int,
        default=None,
        help="Reported NodeUser console memory in GB (required for node_user block creation)",
    )
    args = parser.parse_args()

    print(f"CreateBlock: actor_type={args.actor_type}")
    if args.invoker:
        print(f"CreateBlock: invoker={args.invoker}")
    if args.node_user_id:
        print(f"CreateBlock: node_user_id={args.node_user_id}")

    result = create_new_block(
        actor_type=args.actor_type,  # type: ignore[arg-type]
        invoker=args.invoker,  # type: ignore[arg-type]
        node_user_id=args.node_user_id,
        chain_id=args.chain_id,
        reported_memory_gb=args.reported_memory_gb,
    )
    print("LucidTops create-block protocol complete.")
    print(f"  block_hash: {result.get('block_hash')}")
    print(f"  blockID: {result.get('blockID')}")
    print(f"  lucid_tokens_minted: {result.get('lucid_tokens_minted')}")
    for key in ("tally", "governance", "block", "minted_tokens", "supply", "ledger", "blockchain"):
        value = result.get(key)
        if value is not None:
            print(f"  {key}: {json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
