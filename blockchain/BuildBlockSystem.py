""" this will build all the necessary content for the operation required by the blockchain container.
includes:
- hardware pull at time of operation (pull_information.py)
- blockchain.secrets creation from pull (blockchain_secrets.py)
- the genesis block creation (configBlock.py)
- the insertion of the genesis block into the ledger system (legder.py / LucidTops_LedgerDB)
- the creation of the blockchain system governance protocol (blockGov.py)
- the creation of the blockchain system tally system (tally.py)
- FastAPI route connection (ConnectBlockRoutes.py)

this script will all the starting/ running of the blockchain system via the starting of the blockchain container.
this will allow the stopping/ restarting of the blockchain system via the stopping of the blockchain container.
this will allow for a opretional state (finalized) where the blockchain system is no longer able to be modified or changed.
finalized is when all containers are linked and functioning correctly defined by a container naming resolved at operation time
(default finalize marker name from secrets/env; historically blockchain-finalized).
once naming of container is defined as finalized the blockchain system is no longer able to be modified or changed.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_schema import (  # noqa: E402
    BLOCKCHAIN_BLOCKS_COLLECTION,
    BLOCKCHAIN_STATE_COLLECTION,
    COLLECTION_SCHEMAS,
    LEDGER_RECORDS_COLLECTION,
)
from blockchain_secrets import (  # noqa: E402
    blockchain_secrets_status,
    ensure_blockchain_secrets,
    resolve_blockchain_container_name,
    resolve_blockchain_mongodb_poll_seconds,
    resolve_blockchain_mongodb_wait_seconds,
    resolve_master_server_internal_host,
    resolve_master_server_internal_port,
    resolve_mongodb_host,
    resolve_mongodb_port,
    resolve_node_min_memory_gb,
)
from blockGov import (  # noqa: E402
    BANNED_OPERATIONS_COLLECTION,
    NODE_GOV_AUDIT_COLLECTION,
)
from configBlock import (  # noqa: E402
    GENESIS_CREATOR_ID,
    get_blockchain_db,
    get_mongo_client,
    initialize_blockchain_genesis,
    is_genesis_initialized,
    lucidtoken_root_dir,
    utc_now,
)
from legder import get_ledger_last_hash  # noqa: E402
from pull_information import pull_blockchain_hardware  # noqa: E402
from tally import seed_tally_sync  # noqa: E402

try:
    from ConnectBlockRoutes import connect_blockchain_routes
except ImportError:  # pragma: no cover
    connect_blockchain_routes = None  # type: ignore[misc, assignment]

BLOCKCHAIN_FINALIZED_LOCK_FILENAME = ".blockchain_finalized"
BLOCKCHAIN_BUILD_STATE_ID = "blockchain_system_build"
BLOCKCHAIN_GOVERNANCE_STATE_ID = "blockchain_governance_initialized"
BLOCKCHAIN_TALLY_STATE_ID = "blockchain_tally_initialized"


def resolve_finalized_container_name() -> str:
    """Finalize marker name from secrets/env at operation time."""
    configured = resolve_blockchain_container_name()
    marker = os.environ.get("BLOCKCHAIN_FINALIZED_CONTAINER_NAME", "").strip()
    if marker:
        return marker
    if configured and configured.endswith("-finalized"):
        return configured
    return f"{configured or 'blockchain'}-finalized"


class BlockchainFinalizedError(PermissionError):
    """Raised when a mutation is attempted on a finalized blockchain system."""


def resolve_container_name() -> str:
    """Resolve the running container name (Docker sets HOSTNAME to container_name)."""
    configured = resolve_blockchain_container_name()
    if configured:
        return configured
    for key in ("BLOCKCHAIN_CONTAINER_NAME", "CONTAINER_NAME", "HOSTNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def finalized_lock_path() -> Path:
    return lucidtoken_root_dir() / BLOCKCHAIN_FINALIZED_LOCK_FILENAME


def bootstrap_operation_environ() -> dict[str, Any]:
    """Pull hardware and write blockchain.secrets before any other build step."""
    pull = pull_blockchain_hardware(bind_environ=True)
    secrets_path = ensure_blockchain_secrets(force=False)
    return {
        "pull": {
            "primary_ip": pull.get("primary_ip"),
            "primary_mac": pull.get("primary_mac"),
            "machine_id": pull.get("machine_id"),
            "hostname": pull.get("hostname"),
            "mongodb_host": pull.get("mongodb_host"),
            "databases_dir": pull.get("databases_dir"),
            "ledger_replica_dir": pull.get("ledger_replica_dir"),
        },
        "secrets_file": secrets_path.as_posix(),
    }


def _blockchain_state_collection(client: Any) -> Any:
    return get_blockchain_db(client)[BLOCKCHAIN_STATE_COLLECTION]


def _read_finalized_state(*, client: Any | None = None) -> dict[str, Any] | None:
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return None
    owns_client = client is None
    try:
        record = _blockchain_state_collection(mongo).find_one({"state_id": BLOCKCHAIN_BUILD_STATE_ID})
        if record is None:
            return None
        record.pop("_id", None)
        return dict(record)
    finally:
        if owns_client:
            mongo.close()


def is_blockchain_finalized(*, client: Any | None = None) -> bool:
    """Return True when the blockchain system is immutable (finalized container or lock)."""
    if resolve_container_name() == resolve_finalized_container_name():
        return True
    if finalized_lock_path().exists():
        return True
    state = _read_finalized_state(client=client)
    return bool(state and state.get("finalized"))


def assert_blockchain_modifiable(*, force: bool = False, client: Any | None = None) -> None:
    """Reject mutations when the blockchain system is finalized."""
    finalized_name = resolve_finalized_container_name()
    if force and is_blockchain_finalized(client=client):
        raise BlockchainFinalizedError(
            "Blockchain system is finalized and cannot be modified; "
            f"container naming [{finalized_name}] is immutable"
        )
    if is_blockchain_finalized(client=client):
        raise BlockchainFinalizedError(
            "Blockchain system is finalized and cannot be modified or changed"
        )


def wait_for_mongodb(
    *,
    timeout_seconds: int | None = None,
    poll_seconds: float | None = None,
) -> Any:
    """Wait for MongoDB via Docker DNS host from blockchain.secrets."""
    wait_timeout = (
        resolve_blockchain_mongodb_wait_seconds()
        if timeout_seconds is None
        else timeout_seconds
    )
    wait_poll = (
        resolve_blockchain_mongodb_poll_seconds()
        if poll_seconds is None
        else poll_seconds
    )
    mongodb_host = resolve_mongodb_host()
    mongodb_port = resolve_mongodb_port()
    deadline = time.time() + wait_timeout
    last_error = "unknown"
    while time.time() < deadline:
        client = get_mongo_client()
        if client is not None:
            return client
        last_error = f"{mongodb_host}:{mongodb_port}"
        time.sleep(wait_poll)
    raise RuntimeError(
        "Blockchain database is unavailable "
        f"(Docker DNS host={mongodb_host}, last_target={last_error})"
    )


def _resolve_docker_dns_host(host: str, *, port: int) -> bool:
    """Return True when a Docker DNS service name resolves."""
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def verify_linked_containers(*, client: Any) -> dict[str, Any]:
    """Verify linked stack containers are reachable via Docker DNS."""
    mongodb_host = resolve_mongodb_host()
    master_host = resolve_master_server_internal_host()
    master_port = resolve_master_server_internal_port()
    checks = {
        "mongodb": client is not None,
        "mongodb_host": mongodb_host,
        "master_server_dns": _resolve_docker_dns_host(
            master_host,
            port=master_port,
        ),
        "master_server_host": master_host,
        "master_server_port": master_port,
    }
    return {
        "linked": all(
            (
                checks["mongodb"],
                checks["master_server_dns"],
            )
        ),
        "checks": checks,
        "container_name": resolve_container_name(),
    }


def ensure_blockchain_collections(*, client: Any) -> dict[str, Any]:
    """Ensure blockchain MongoDB collections exist (schema-aligned indexes)."""
    db = get_blockchain_db(client)
    ensured: list[str] = []
    for collection_name in COLLECTION_SCHEMAS:
        db[collection_name].create_index("created_at")
        ensured.append(collection_name)
    db[BLOCKCHAIN_BLOCKS_COLLECTION].create_index(
        "blockID", unique=True, sparse=True
    )
    db[BLOCKCHAIN_BLOCKS_COLLECTION].create_index(
        "New_BlockID", unique=True, sparse=True
    )
    db[BLOCKCHAIN_BLOCKS_COLLECTION].create_index("status")
    db[LEDGER_RECORDS_COLLECTION].create_index([("created_at", -1)])
    db[LEDGER_RECORDS_COLLECTION].create_index("record_type")
    db[LEDGER_RECORDS_COLLECTION].create_index("BlockID", sparse=True)
    return {"collections_ensured": ensured}


def verify_genesis_ledger_insertion(*, client: Any) -> dict[str, Any]:
    """Verify genesis block and immutable ledger record alignment (legder.py / Ledger.py)."""
    db = get_blockchain_db(client)
    genesis_block = db[BLOCKCHAIN_BLOCKS_COLLECTION].find_one({"status": "genesis"}, {"_id": 0})
    if genesis_block is None:
        return {
            "aligned": False,
            "reason": "genesis block missing from blockchain_blocks",
        }

    block_hash = str(genesis_block.get("block_hash") or "").strip()
    if not block_hash:
        return {
            "aligned": False,
            "reason": "genesis block_hash missing",
            "blockID": genesis_block.get("blockID"),
        }

    ledger_record = db[LEDGER_RECORDS_COLLECTION].find_one(
        {"record_type": "block", "aggregate_hash": block_hash},
        {"_id": 0},
    )
    if ledger_record is None:
        return {
            "aligned": False,
            "reason": "genesis ledger record missing",
            "block_hash": block_hash,
        }

    return {
        "aligned": True,
        "blockID": genesis_block.get("blockID"),
        "chainID": genesis_block.get("chainID"),
        "block_hash": block_hash,
        "ledger_last_hash": get_ledger_last_hash(client=client),
        "ledger_record": ledger_record,
    }


def initialize_blockchain_governance(*, client: Any, force: bool = False) -> dict[str, Any]:
    """Initialize blockchain governance protocol collections (blockGov.py)."""
    assert_blockchain_modifiable(force=force, client=client)

    db = get_blockchain_db(client)
    state_col = _blockchain_state_collection(client)
    existing = state_col.find_one({"state_id": BLOCKCHAIN_GOVERNANCE_STATE_ID})
    if existing and existing.get("initialized") and not force:
        existing.pop("_id", None)
        return {
            "skipped": True,
            "reason": "blockchain governance already initialized",
            "state": dict(existing),
        }

    db[BANNED_OPERATIONS_COLLECTION].create_index("NodeUserID", unique=True)
    db[NODE_GOV_AUDIT_COLLECTION].create_index([("NodeUserID", 1), ("timestamp", -1)])

    now = utc_now()
    state_col.update_one(
        {"state_id": BLOCKCHAIN_GOVERNANCE_STATE_ID},
        {
            "$set": {
                "state_id": BLOCKCHAIN_GOVERNANCE_STATE_ID,
                "initialized": True,
                "node_min_memory_gb": resolve_node_min_memory_gb(),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    record = state_col.find_one({"state_id": BLOCKCHAIN_GOVERNANCE_STATE_ID}, {"_id": 0})
    return {
        "skipped": False,
        "governance_initialized": True,
        "collections": [BANNED_OPERATIONS_COLLECTION, NODE_GOV_AUDIT_COLLECTION],
        "state": dict(record or {}),
    }


def initialize_blockchain_tally(*, client: Any, force: bool = False) -> dict[str, Any]:
    """Initialize blockchain tally system and seed sync snapshot (tally.py)."""
    assert_blockchain_modifiable(force=force, client=client)

    state_col = _blockchain_state_collection(client)
    existing = state_col.find_one({"state_id": BLOCKCHAIN_TALLY_STATE_ID})
    if existing and existing.get("initialized") and not force:
        existing.pop("_id", None)
        return {
            "skipped": True,
            "reason": "blockchain tally already initialized",
            "state": dict(existing),
        }

    sync_result = seed_tally_sync(client=client, force=True)
    now = utc_now()
    state_col.update_one(
        {"state_id": BLOCKCHAIN_TALLY_STATE_ID},
        {
            "$set": {
                "state_id": BLOCKCHAIN_TALLY_STATE_ID,
                "initialized": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    record = state_col.find_one({"state_id": BLOCKCHAIN_TALLY_STATE_ID}, {"_id": 0})
    return {
        "skipped": False,
        "tally_initialized": True,
        "tally_sync": sync_result,
        "state": dict(record or {}),
    }


def mark_blockchain_finalized(*, client: Any) -> dict[str, Any]:
    """Mark blockchain system immutable once container naming is blockchain-finalized."""
    now = utc_now()
    container_name = resolve_container_name()
    lock_path = finalized_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_payload = {
        "finalized": True,
        "container_name": container_name,
        "creator_id": GENESIS_CREATOR_ID,
        "finalized_at": now,
    }
    lock_path.write_text(json.dumps(lock_payload, indent=2, sort_keys=True), encoding="utf-8")

    _blockchain_state_collection(client).update_one(
        {"state_id": BLOCKCHAIN_BUILD_STATE_ID},
        {
            "$set": {
                "state_id": BLOCKCHAIN_BUILD_STATE_ID,
                "finalized": True,
                "container_name": container_name,
                "finalized_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {
        "finalized": True,
        "container_name": container_name,
        "lock_file": lock_path.as_posix(),
        "finalized_at": now,
    }


def _mark_build_complete(
    *,
    client: Any,
    genesis_result: dict[str, Any],
    ledger_result: dict[str, Any],
    governance_result: dict[str, Any],
    tally_result: dict[str, Any],
    containers_result: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    _blockchain_state_collection(client).update_one(
        {"state_id": BLOCKCHAIN_BUILD_STATE_ID},
        {
            "$set": {
                "state_id": BLOCKCHAIN_BUILD_STATE_ID,
                "build_complete": True,
                "genesis_initialized": is_genesis_initialized(client=client),
                "ledger_aligned": bool(ledger_result.get("aligned")),
                "governance_initialized": not governance_result.get("skipped", False)
                or bool(governance_result.get("governance_initialized")),
                "tally_initialized": not tally_result.get("skipped", False)
                or bool(tally_result.get("tally_initialized")),
                "containers_linked": bool(containers_result.get("linked")),
                "container_name": resolve_container_name(),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    record = _blockchain_state_collection(client).find_one(
        {"state_id": BLOCKCHAIN_BUILD_STATE_ID},
        {"_id": 0},
    )
    return dict(record or {})


def get_blockchain_runtime_status(*, client: Any | None = None) -> dict[str, Any]:
    """Return current blockchain container runtime status."""
    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return {
            "operational": False,
            "reason": "Blockchain database is unavailable",
            "mongodb_host": resolve_mongodb_host(),
            "container_name": resolve_container_name(),
        }

    try:
        containers_result = verify_linked_containers(client=mongo)
        ledger_result = verify_genesis_ledger_insertion(client=mongo)
        build_state = _read_finalized_state(client=mongo) or {}
        finalized = is_blockchain_finalized(client=mongo)
        return {
            "operational": bool(
                is_genesis_initialized(client=mongo)
                and ledger_result.get("aligned")
                and containers_result.get("linked")
            ),
            "finalized": finalized,
            "modifiable": not finalized,
            "container_name": resolve_container_name(),
            "genesis_initialized": is_genesis_initialized(client=mongo),
            "ledger": ledger_result,
            "containers": containers_result,
            "build_state": build_state,
            "mongodb_host": resolve_mongodb_host(),
            "lucidtoken_root": lucidtoken_root_dir().as_posix(),
            "blockchain_secrets": blockchain_secrets_status(),
        }
    finally:
        if owns_client:
            mongo.close()


def build_block_system(*, force: bool = False, wait_for_db: bool = True) -> dict[str, Any]:
    """Build all blockchain container content: pull, secrets, genesis, ledger, governance, tally."""
    bootstrap = bootstrap_operation_environ()

    if is_blockchain_finalized() and not force:
        status = get_blockchain_runtime_status()
        status["build_complete"] = True
        status["skipped"] = True
        status["reason"] = "blockchain system is finalized; build is read-only"
        status["hardware_pull"] = bootstrap.get("pull")
        return status

    assert_blockchain_modifiable(force=force)

    mongo = wait_for_mongodb() if wait_for_db else get_mongo_client()
    if mongo is None:
        raise RuntimeError(
            "Blockchain database is unavailable "
            f"(Docker DNS host={resolve_mongodb_host()})"
        )

    try:
        if is_blockchain_finalized(client=mongo) and not force:
            status = get_blockchain_runtime_status(client=mongo)
            status["build_complete"] = True
            status["skipped"] = True
            status["reason"] = "blockchain system is finalized; build is read-only"
            return status

        collections_result = ensure_blockchain_collections(client=mongo)
        genesis_result = initialize_blockchain_genesis(force=force, client=mongo)
        ledger_result = verify_genesis_ledger_insertion(client=mongo)

        if is_genesis_initialized(client=mongo) and not ledger_result.get("aligned"):
            raise RuntimeError(
                "Genesis ledger alignment failed: "
                f"{ledger_result.get('reason', 'unknown')}"
            )

        governance_result = initialize_blockchain_governance(client=mongo, force=force)
        tally_result = initialize_blockchain_tally(client=mongo, force=force)
        containers_result = verify_linked_containers(client=mongo)

        finalize_result: dict[str, Any] | None = None
        if (
            resolve_container_name() == resolve_finalized_container_name()
            and containers_result.get("linked")
        ):
            finalize_result = mark_blockchain_finalized(client=mongo)

        build_state = _mark_build_complete(
            client=mongo,
            genesis_result=genesis_result,
            ledger_result=ledger_result,
            governance_result=governance_result,
            tally_result=tally_result,
            containers_result=containers_result,
        )

        routes_result: dict[str, Any] | None = None
        if connect_blockchain_routes is not None:
            try:
                routes_result = connect_blockchain_routes(client=mongo)
            except Exception as exc:
                routes_result = {"connected": False, "error": str(exc)}

        return {
            "build_complete": True,
            "skipped": False,
            "finalized": is_blockchain_finalized(client=mongo),
            "modifiable": not is_blockchain_finalized(client=mongo),
            "container_name": resolve_container_name(),
            "collections": collections_result,
            "genesis": genesis_result,
            "ledger": ledger_result,
            "governance": governance_result,
            "tally": tally_result,
            "containers": containers_result,
            "finalize": finalize_result,
            "build_state": build_state,
            "lucidtoken_root": lucidtoken_root_dir().as_posix(),
            "mongodb_host": resolve_mongodb_host(),
            "blockchain_secrets": blockchain_secrets_status(),
            "blockchain_secrets_file": bootstrap.get("secrets_file"),
            "hardware_pull": bootstrap.get("pull"),
            "blockchain_routes": routes_result,
        }
    finally:
        mongo.close()


def run_blockchain_system(*, force: bool = False) -> dict[str, Any]:
    """Container entrypoint: build blockchain system when the container starts."""
    print(f"BuildBlockSystem: container={resolve_container_name() or 'unknown'}")
    print(f"BuildBlockSystem: mongodb_host={resolve_mongodb_host()}")
    print(f"BuildBlockSystem: lucidtoken_root={lucidtoken_root_dir().as_posix()}")
    result = build_block_system(force=force, wait_for_db=True)
    print("BuildBlockSystem: blockchain system build complete.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops blockchain container build system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build blockchain container content")
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild (blocked when blockchain system is finalized)",
    )
    build_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for MongoDB Docker DNS host",
    )

    subparsers.add_parser("run", help="Run blockchain system build (container start)")
    run_parser = subparsers.add_parser("start", help="Alias for run")
    run_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("status", help="Print blockchain container runtime status")
    subparsers.add_parser("verify", help="Verify genesis ledger alignment")

    args = parser.parse_args()

    if args.command == "build":
        result = build_block_system(force=args.force, wait_for_db=not args.no_wait)
    elif args.command in {"run", "start"}:
        force = getattr(args, "force", False)
        result = run_blockchain_system(force=force)
    elif args.command == "status":
        result = get_blockchain_runtime_status()
    elif args.command == "verify":
        mongo = wait_for_mongodb()
        try:
            result = verify_genesis_ledger_insertion(client=mongo)
        finally:
            mongo.close()
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
