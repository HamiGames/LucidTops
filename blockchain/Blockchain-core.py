""" the core functions of the blockchain system, including the requirements and limitations for the blockchain system
blockchain core functions:
- sha512 hash function
- block creation (local chain DB only post-genesis)
- LucidToken generation
- chain ledger_records recording
- ledger_doc payload for operations Master/Node transport (no Master write after genesis)
- blockchain governance protocol
- blockchain session history recording

limitations:
- the Blockchain system is only used for the session system
- the produced LucidTokens are usable in the LucidToken marketplace, and other applications that accept LucidTokens
- the Blockchain system is not used for any other application
- the Blockchain system is not used for any other system
- the Blockchain system is not used for any other network
- the Blockchain system is not used for any other internet
- the Blockchain system is not used for any other world
- the Blockchain system is not used for any other universe

requirements:
- the Blockchain system must be used for the session system
- the Blockchain system must be used for the LucidToken generation


design factors: 
- the number of tokens that can be minted is limited to the total from blockchain.secrets (Blockchain.txt: 42,000,000 LucidTokens)
- the starting number of tokens per block comes from blockchain.secrets (Blockchain.txt: 50 LucidTokens)
- every fraction of total supply minted (Blockchain.txt: 2%), the block reward is halved
- all transfers of tokens will burn per BURN_DIVISOR from secrets (default 1 per 10000)
- all tokens are worth the same value in the jackpot system (LucidTokens)
- all burnt tokens are removed from circulating supply but accounted in total minted
- all tokens are stored on the owners console in a LucidToken folder (LucidToken-<UserID>.png) in a Lucidtoken folder
- LucidCoins are also written to Tokens.log on the creator_id console (newline per coin)
- all tokens will have a unique LucidTokenID (LucidTokenID) imbedded in a randomly generated image
- all images will be unique and random generated
- all images will be based on the image schema (image_schema.py)
- all images will not be more than 1mb in size

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.

"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import secrets
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Callable

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BLOCKCHAIN_DIR.parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockGov import validate_node_operation  # noqa: E402
from blockchain_schema import (  # noqa: E402
    BLOCK_STATUSES,
    BLOCKCHAIN_BLOCKS_COLLECTION,
    BLOCKCHAIN_STATE_COLLECTION,
    BLOCKCHAIN_SUPPLY_STATE_ID,
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
    LEDGER_RECORDS_COLLECTION,
    LEDGER_RECORD_TYPES,
    LUCID_TOKENS_COLLECTION,
    SESSION_ID_LOG_COLLECTION,
    SESSION_RECORDS_COLLECTION,
    TALLY_ENTITY_TYPES,
    TALLY_RECORDS_COLLECTION,
)
from blockchain_secrets import (  # noqa: E402
    resolve_burn_divisor,
    resolve_halving_minted_fraction,
    resolve_initial_block_reward,
    resolve_lucid_image_height,
    resolve_lucid_image_width,
    resolve_lucid_tops_root,
    resolve_max_block_bytes,
    resolve_max_sessions_per_block,
    resolve_max_token_image_bytes,
    resolve_min_block_interval_seconds,
    resolve_total_token_supply,
)
from configBlock import (  # noqa: E402
    get_blockchain_db,
    get_mongo_client,
    utc_now,
)

LUCID_TOKEN_DIR_NAME = "Lucidtoken"
LUCID_TOKEN_FILE_PREFIX = "LucidToken"


def __getattr__(name: str) -> Any:
    getters = {
        "TOTAL_TOKEN_SUPPLY": resolve_total_token_supply,
        "INITIAL_BLOCK_REWARD": resolve_initial_block_reward,
        "HALVING_MINTED_FRACTION": resolve_halving_minted_fraction,
        "BURN_DIVISOR": resolve_burn_divisor,
        "MAX_TOKEN_IMAGE_BYTES": resolve_max_token_image_bytes,
        "MAX_BLOCK_BYTES": resolve_max_block_bytes,
        "MAX_SESSIONS_PER_BLOCK": resolve_max_sessions_per_block,
        "MIN_BLOCK_INTERVAL_SECONDS": resolve_min_block_interval_seconds,
        "LUCID_TOPS_ROOT": resolve_lucid_tops_root,
    }
    if name in getters:
        return getters[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def sha512_hex(data: bytes | str) -> str:
    """Return a SHA-512 digest for blockchain hashing."""
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha512(payload).hexdigest()


def compute_block_hash(
    *,
    previous_block_hash: str,
    block_id: str,
    chain_id: str,
    session_payload: list[dict[str, Any]],
    ledger_last_hash: str,
    winner_entity_type: str,
    winner_entity_id: str,
    timestamp: str,
) -> str:
    """Compute the SHA-512 block hash from ordered block components."""
    canonical = json.dumps(
        {
            "previous_block_hash": previous_block_hash,
            "blockID": block_id,
            "chainID": chain_id,
            "session_payload": session_payload,
            "ledger_last_hash": ledger_last_hash,
            "winner_entity_type": winner_entity_type,
            "winner_entity_id": winner_entity_id,
            "timestamp": timestamp,
            "hash_algorithm": HASH_ALGORITHM,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha512_hex(canonical)


def block_reward_for_minted(minted_total: int) -> float:
    """Halve block reward every HALVING_MINTED_FRACTION of TOTAL_TOKEN_SUPPLY minted."""
    initial_reward = resolve_initial_block_reward()
    if minted_total <= 0:
        return float(initial_reward)
    threshold = int(resolve_total_token_supply() * resolve_halving_minted_fraction())
    if threshold <= 0:
        return float(initial_reward)
    halvings = minted_total // threshold
    return float(initial_reward) / (2**halvings)


def calculate_transfer_burn(amount: float) -> tuple[float, float]:
    """Burn 1 LucidToken per 10,000 transferred; return (net_amount, burn_amount)."""
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")
    burn_amount = float(int(amount) // resolve_burn_divisor())
    return amount - burn_amount, burn_amount


def lucid_token_storage_dir(*, owner_id: str) -> Path:
    """Resolve owner LucidToken folder (DockerDNS-compatible via LUCID_TOPS_ROOT)."""
    return resolve_lucid_tops_root() / LUCID_TOKEN_DIR_NAME / owner_id.strip()


def lucid_token_image_path(*, owner_id: str, lucid_token_id: str) -> Path:
    """Return LucidToken-<LucidTokenID>.png path under the owner console folder."""
    return lucid_token_storage_dir(owner_id=owner_id) / f"{LUCID_TOKEN_FILE_PREFIX}-{lucid_token_id}.png"


def _load_image_schema_module() -> Any | None:
    schema_path = BLOCKCHAIN_DIR / "image_schema.py"
    if not schema_path.exists():
        return None
    module_name = "image_schema"
    spec = importlib.util.spec_from_file_location(module_name, schema_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _render_lucid_token_png(
    *,
    lucid_token_id: str,
    owner_id: str,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    """Generate a unique PNG (<=1MB) with embedded LucidTokenID metadata."""
    max_bytes = resolve_max_token_image_bytes()
    render_width = resolve_lucid_image_width() if width is None else width
    render_height = resolve_lucid_image_height() if height is None else height
    image_schema = _load_image_schema_module()
    if image_schema is not None and hasattr(image_schema, "render_token_image"):
        png_bytes = image_schema.render_token_image(
            lucid_token_id=lucid_token_id,
            owner_id=owner_id,
            max_bytes=max_bytes,
        )
        if isinstance(png_bytes, bytes) and 0 < len(png_bytes) <= max_bytes:
            return png_bytes

    seed = sha512_hex(f"{lucid_token_id}:{owner_id}:{secrets.token_hex(8)}")
    pixels = bytearray()
    for y in range(render_height):
        row_seed = sha512_hex(f"{seed}:{y}")
        for x in range(render_width):
            index = (int(row_seed[(x * 2) % len(row_seed) : (x * 2) % len(row_seed) + 2], 16) + x + y) % 256
            pixels.extend((index, (index * 3) % 256, (index * 7) % 256))

    raw_rows = b"".join(
        b"\x00" + bytes(pixels[y * render_width * 3 : (y + 1) * render_width * 3])
        for y in range(render_height)
    )
    compressed = zlib.compress(raw_rows, 9)
    ihdr = struct.pack(">IIBBBBB", render_width, render_height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"tEXt", b"LucidTokenID\x00" + lucid_token_id.encode("utf-8"))
        + _png_chunk(b"tEXt", b"OwnerID\x00" + owner_id.encode("utf-8"))
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    if len(png) > max_bytes:
        raise RuntimeError("Generated LucidToken image exceeds 1MB limit")
    return png


def generate_lucid_token_id(*, block_id: str, owner_id: str, token_index: int) -> str:
    """Create a unique LucidTokenID derived from block context and owner."""
    seed = f"{block_id}:{owner_id}:{token_index}:{secrets.token_hex(8)}"
    return sha512_hex(seed)[:32]


def save_lucid_token_image(*, owner_id: str, lucid_token_id: str) -> Path:
    """Persist LucidToken PNG on the owner console under Lucidtoken/."""
    target_dir = lucid_token_storage_dir(owner_id=owner_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = lucid_token_image_path(owner_id=owner_id, lucid_token_id=lucid_token_id)
    png_bytes = _render_lucid_token_png(lucid_token_id=lucid_token_id, owner_id=owner_id)
    target_path.write_bytes(png_bytes)
    return target_path


def with_mongo(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Run a database handler with an auto-closing Mongo client when needed."""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        client = kwargs.pop("client", None)
        owns_client = client is None
        if owns_client:
            client = get_mongo_client()
            if client is None:
                raise RuntimeError("Master server database is unavailable")
        try:
            return handler(*args, client=client, **kwargs)
        finally:
            if owns_client and client is not None:
                client.close()

    return wrapper


def _supply_state_collection(client: Any) -> Any:
    return get_blockchain_db(client)[BLOCKCHAIN_STATE_COLLECTION]


def get_token_supply_state(*, client: Any) -> dict[str, Any]:
    """Return minted, burnt, and circulating LucidToken supply counters."""
    record = _supply_state_collection(client).find_one({"state_id": BLOCKCHAIN_SUPPLY_STATE_ID})
    if not record:
        return {
            "state_id": BLOCKCHAIN_SUPPLY_STATE_ID,
            "total_minted": 0,
            "total_burnt": 0,
            "circulating": 0,
            "block_reward": float(resolve_initial_block_reward()),
        }
    minted = int(record.get("total_minted") or 0)
    burnt = int(record.get("total_burnt") or 0)
    return {
        "state_id": BLOCKCHAIN_SUPPLY_STATE_ID,
        "total_minted": minted,
        "total_burnt": burnt,
        "circulating": max(minted - burnt, 0),
        "block_reward": block_reward_for_minted(minted),
    }


def _update_supply_state(
    *,
    client: Any,
    minted_delta: int = 0,
    burnt_delta: int = 0,
) -> dict[str, Any]:
    now = utc_now()
    col = _supply_state_collection(client)
    col.update_one(
        {"state_id": BLOCKCHAIN_SUPPLY_STATE_ID},
        {
            "$inc": {
                "total_minted": minted_delta,
                "total_burnt": burnt_delta,
            },
            "$set": {"updated_at": now},
            "$setOnInsert": {"state_id": BLOCKCHAIN_SUPPLY_STATE_ID, "created_at": now},
        },
        upsert=True,
    )
    return get_token_supply_state(client=client)


def append_ledger_record(
    *,
    client: Any,
    session_id: str | None,
    aggregate_hash: str,
    record_type: str,
    block_id: str | None = None,
    new_block_id: str | None = None,
    creator_id: str | None = None,
) -> dict[str, Any]:
    """Append an immutable ledger record (ledger system recording)."""
    if record_type not in LEDGER_RECORD_TYPES:
        raise ValueError(f"Unsupported ledger record_type: {record_type}")
    now = utc_now()
    record = {
        "sessionID": session_id,
        "BlockID": block_id,
        "New_BlockID": new_block_id,
        "creator_id": creator_id,
        "aggregate_hash": aggregate_hash,
        "hash_algorithm": HASH_ALGORITHM,
        "record_type": record_type,
        "created_at": now,
    }
    get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION].insert_one(record)
    record.pop("_id", None)
    return record


def write_tokens_log_for_owner(*, owner_id: str, lucid_token_ids: list[str]) -> Path:
    """Append LucidTokenIDs to Tokens.log on the owner console."""
    from configBlock import write_tokens_log

    return write_tokens_log(owner_id=owner_id, lucid_token_ids=lucid_token_ids)


def record_session_history(*, client: Any, session_id: str, aggregate_hash: str) -> dict[str, Any]:
    """Record compressed session history in the immutable ledger."""
    return append_ledger_record(
        client=client,
        session_id=session_id,
        aggregate_hash=aggregate_hash,
        record_type="session_history",
    )


def get_ledger_last_hash(*, client: Any) -> str:
    """Return the most recent ledger aggregate hash for block chaining."""
    latest = (
        get_blockchain_db(client)[LEDGER_RECORDS_COLLECTION]
        .find({}, {"aggregate_hash": 1, "_id": 0})
        .sort("created_at", -1)
        .limit(1)
    )
    for record in latest:
        value = record.get("aggregate_hash")
        if isinstance(value, str) and value:
            return value
    return str(GENESIS_PREVIOUS_HASH)


def validate_blockchain_governance(
    *,
    node_user_id: str | None,
    operation: str = "blockchain_create",
    is_latest_block_creator: bool = False,
    reported_memory_gb: int | None = None,
    client: Any,
) -> dict[str, Any]:
    """Apply blockchain governance protocol via blockGov rules."""
    if node_user_id:
        return validate_node_operation(
            node_user_id=node_user_id,
            operation=operation,  # type: ignore[arg-type]
            is_latest_block_creator=is_latest_block_creator,
            reported_memory_gb=reported_memory_gb,
            client=client,
        )
    return {
        "NodeUserID": None,
        "operation": operation,
        "permitted": True,
        "actor": "master_server",
    }


def _verify_tally_session_id(*, client: Any, session_id: str | None) -> bool:
    if not session_id:
        return False
    record = get_blockchain_db(client)[SESSION_ID_LOG_COLLECTION].find_one({"sessionID": session_id.strip()})
    return record is not None


def select_tally_winner(*, client: Any) -> dict[str, Any]:
    """Select block creator from tally records (highest session-data-chunk / taskTokens)."""
    db = get_blockchain_db(client)
    candidates = list(
        db[TALLY_RECORDS_COLLECTION].find(
            {"entity_type": {"$in": list(TALLY_ENTITY_TYPES)}},
            {"_id": 0},
        )
    )
    if not candidates:
        return {
            "winner_entity_type": None,
            "winner_entity_id": None,
            "tally_verified": False,
            "tally_points": 0,
            "taskTokens": [],
            "empty_tally": True,
        }

    def _score(record: dict[str, Any]) -> tuple[int, int]:
        task_tokens = record.get("taskTokens") or []
        token_count = len(task_tokens) if isinstance(task_tokens, list) else 0
        chunk_count = int(record.get("chunk_count") or 0)
        points = int(record.get("tally_points") or 0)
        # Prefer session-data-chunk contribution, then points, then taskTokens
        return chunk_count or points, token_count

    winner = max(candidates, key=_score)
    entity_id = str(winner.get("entity_id") or "").strip()
    entity_type = str(winner.get("entity_type") or "").strip()
    if not entity_id or not entity_type:
        return {
            "winner_entity_type": None,
            "winner_entity_id": None,
            "tally_verified": False,
            "tally_points": 0,
            "taskTokens": [],
            "empty_tally": True,
        }

    session_id = winner.get("sessionID")
    verified = bool(winner.get("sessionID_verified")) and _verify_tally_session_id(
        client=client,
        session_id=session_id if isinstance(session_id, str) else None,
    )
    return {
        "winner_entity_type": entity_type,
        "winner_entity_id": entity_id,
        "tally_verified": verified,
        "tally_points": int(winner.get("tally_points") or 0),
        "taskTokens": list(winner.get("taskTokens") or []),
        "sessionID": session_id,
        "chunk_count": int(winner.get("chunk_count") or 0),
        "empty_tally": False,
    }


def _reset_tally_for_winner(*, client: Any, entity_type: str, entity_id: str) -> None:
    now = utc_now()
    get_blockchain_db(client)[TALLY_RECORDS_COLLECTION].update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {
            "$set": {
                "tally_points": 0,
                "taskTokens": [],
                "chunk_count": 0,
                "last_win_at": now,
                "last_reset_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )


def _latest_confirmed_block(*, client: Any) -> dict[str, Any] | None:
    return get_blockchain_db(client)[BLOCKCHAIN_BLOCKS_COLLECTION].find_one(
        {"status": {"$in": ["confirmed", "genesis"]}, "block_hash": {"$exists": True, "$ne": None}},
        sort=[("created_at", -1)],
    )


def _enforce_block_interval(*, client: Any) -> None:
    latest = _latest_confirmed_block(client=client)
    if not latest:
        return
    created_at = latest.get("created_at")
    if not isinstance(created_at, str):
        return
    from datetime import datetime

    try:
        previous = datetime.fromisoformat(created_at)
        elapsed = datetime.now(previous.tzinfo) - previous
    except ValueError:
        return
    if elapsed.total_seconds() < resolve_min_block_interval_seconds():
        raise ValueError(
            f"Block creation interval must be at least {resolve_min_block_interval_seconds()} seconds"
        )


def _fetch_pending_sessions(*, client: Any) -> list[dict[str, Any]]:
    db = get_blockchain_db(client)
    pending = list(
        db[SESSION_RECORDS_COLLECTION]
        .find(
            {
                "compressed": True,
                "DataInsert": {"$exists": True, "$ne": None},
                "sessionStatus": "compressed",
            },
            {"_id": 0},
        )
        .sort("updated_at", 1)
        .limit(resolve_max_sessions_per_block())
    )
    selected: list[dict[str, Any]] = []
    total_bytes = 0
    max_block_bytes = resolve_max_block_bytes()
    for record in pending:
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if total_bytes + len(payload) > max_block_bytes:
            break
        selected.append(record)
        total_bytes += len(payload)
    return selected


def mint_lucid_tokens(
    *,
    client: Any,
    owner_id: str,
    count: int,
    block_id: str,
) -> list[dict[str, Any]]:
    """Mint LucidTokens for a block winner, respecting the supply cap from secrets."""
    if count <= 0:
        return []
    supply = get_token_supply_state(client=client)
    remaining = resolve_total_token_supply() - int(supply["total_minted"])
    if remaining <= 0:
        raise RuntimeError("LucidToken supply cap reached")
    mint_count = min(count, remaining)

    minted: list[dict[str, Any]] = []
    now = utc_now()
    token_col = get_blockchain_db(client)[LUCID_TOKENS_COLLECTION]
    for index in range(mint_count):
        lucid_token_id = generate_lucid_token_id(
            block_id=block_id,
            owner_id=owner_id,
            token_index=index,
        )
        image_path = save_lucid_token_image(owner_id=owner_id, lucid_token_id=lucid_token_id)
        token_record = {
            "LucidTokenID": lucid_token_id,
            "owner_id": owner_id,
            "blockID": block_id,
            "image_path": image_path.as_posix(),
            "tokens_log_path": None,
            "hash_algorithm": HASH_ALGORITHM,
            "status": "active",
            "created_at": now,
        }
        token_col.insert_one(token_record)
        token_record.pop("_id", None)
        append_ledger_record(
            client=client,
            session_id=None,
            aggregate_hash=sha512_hex(lucid_token_id),
            record_type="lucid_token",
            block_id=block_id,
            creator_id=owner_id,
        )
        minted.append(token_record)

    if minted:
        log_path = write_tokens_log_for_owner(
            owner_id=owner_id,
            lucid_token_ids=[str(t["LucidTokenID"]) for t in minted],
        )
        for token in minted:
            token["tokens_log_path"] = log_path.as_posix()
            token_col.update_one(
                {"LucidTokenID": token["LucidTokenID"]},
                {"$set": {"tokens_log_path": log_path.as_posix()}},
            )

    _update_supply_state(client=client, minted_delta=len(minted))
    return minted


def transfer_lucid_tokens(
    *,
    client: Any,
    lucid_token_ids: list[str],
    from_owner_id: str,
    to_owner_id: str,
) -> dict[str, Any]:
    """Transfer LucidTokens with burn applied (1 per 10,000 tokens transferred)."""
    if not lucid_token_ids:
        raise ValueError("At least one LucidTokenID is required")
    amount = float(len(lucid_token_ids))
    net_amount, burn_amount = calculate_transfer_burn(amount)
    if net_amount <= 0:
        raise ValueError("Transfer amount too small after burn")

    db = get_blockchain_db(client)
    token_col = db[LUCID_TOKENS_COLLECTION]
    now = utc_now()
    moved: list[str] = []
    burned: list[str] = []
    for token_id in lucid_token_ids[: int(net_amount)]:
        record = token_col.find_one({"LucidTokenID": token_id, "owner_id": from_owner_id})
        if not record:
            raise LookupError(f"LucidToken not found for owner: {token_id}")
        image_path = save_lucid_token_image(owner_id=to_owner_id, lucid_token_id=token_id)
        token_col.update_one(
            {"LucidTokenID": token_id},
            {
                "$set": {
                    "owner_id": to_owner_id,
                    "image_path": image_path.as_posix(),
                    "updated_at": now,
                }
            },
        )
        moved.append(token_id)
        append_ledger_record(
            client=client,
            session_id=None,
            aggregate_hash=sha512_hex(f"transfer:{token_id}:{to_owner_id}"),
            record_type="token_transfer",
        )

    if burn_amount > 0:
        burn_ids = lucid_token_ids[int(net_amount) : int(net_amount) + int(burn_amount)]
        for token_id in burn_ids:
            token_col.update_one(
                {"LucidTokenID": token_id, "owner_id": from_owner_id},
                {"$set": {"status": "burnt", "updated_at": now}},
            )
            append_ledger_record(
                client=client,
                session_id=None,
                aggregate_hash=sha512_hex(f"burn:{token_id}"),
                record_type="token_burn",
            )
            burned.append(token_id)
        _update_supply_state(client=client, burnt_delta=len(burned))

    return {
        "transferred": moved,
        "burned": burned,
        "burn_amount": burn_amount,
        "net_amount": net_amount,
    }


@with_mongo
def create_block(
    *,
    chain_id: str | None = None,
    node_user_id: str | None = None,
    reported_memory_gb: int | None = None,
    packet: list[dict[str, Any]] | None = None,
    client: Any,
) -> dict[str, Any]:
    """Create a block: New_BlockID -> confirmed BlockID (SHA-512) with LucidToken rewards."""
    db = get_blockchain_db(client)
    validate_blockchain_governance(
        node_user_id=node_user_id,
        operation="blockchain_create",
        reported_memory_gb=reported_memory_gb,
        client=client,
    )

    previous = _latest_confirmed_block(client=client)
    is_genesis = previous is None
    if not is_genesis:
        _enforce_block_interval(client=client)

    winner = select_tally_winner(client=client)
    if is_genesis:
        from blockchain_secrets import resolve_genesis_creator_id

        winner_type = "genesis_creator"
        winner_id = resolve_genesis_creator_id()
    else:
        if winner.get("empty_tally") or not winner.get("winner_entity_id"):
            raise PermissionError(
                "Block creation requires a tally winner with a real creator_id "
                "(NodeID, MasterServerID, AdminID, or MasterUserID)"
            )
        if not winner.get("tally_verified"):
            raise PermissionError("Tally winner must be verified against sessionID log")
        winner_type = str(winner["winner_entity_type"])
        winner_id = str(winner["winner_entity_id"])

    if packet is not None:
        session_payload = list(packet)
        pending_sessions = []
    else:
        pending_sessions = _fetch_pending_sessions(client=client)
        session_payload = []
        for session in pending_sessions:
            session_id = str(session.get("sessionID") or "")
            aggregate_hash = str(session.get("aggregate_hash") or session.get("DataInsert") or "")
            if session_id and aggregate_hash:
                record_session_history(
                    client=client, session_id=session_id, aggregate_hash=aggregate_hash
                )
                session_payload.append(
                    {
                        "sessionID": session_id,
                        "aggregate_hash": aggregate_hash,
                        "sessionKey": session.get("sessionKey"),
                        "chunks": session.get("chunked_payload") or session.get("chunks") or [],
                    }
                )

    previous_block_hash = (
        str(previous.get("block_hash"))
        if previous and previous.get("block_hash")
        else GENESIS_PREVIOUS_HASH
    )
    ledger_last_hash = get_ledger_last_hash(client=client)
    now = utc_now()
    resolved_chain_id = chain_id or (
        str(previous.get("chainID")) if previous else sha512_hex(f"chain:{winner_id}:{now}")[:16]
    )

    # New_BlockID stage (pre-confirm) — SHA-512 of pending material
    new_block_material = json.dumps(
        {
            "previous_block_hash": previous_block_hash,
            "chainID": resolved_chain_id,
            "session_payload": session_payload,
            "ledger_last_hash": ledger_last_hash,
            "creator_id": winner_id,
            "timestamp": now,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    new_block_id = sha512_hex(new_block_material)

    # Persist New_BlockID as awaiting / new_block before promotion
    awaiting_record = {
        "blockID": None,
        "New_BlockID": new_block_id,
        "chainID": resolved_chain_id,
        "sessionID": winner.get("sessionID"),
        "aggregate_hash": ledger_last_hash,
        "hash_algorithm": HASH_ALGORITHM,
        "DataInsert": [entry.get("aggregate_hash") for entry in session_payload],
        "previous_block_hash": previous_block_hash,
        "block_hash": None,
        "status": "new_block",
        "creator_id": winner_id,
        "winner_entity_type": winner_type,
        "winner_entity_id": winner_id,
        "tally_verified": bool(winner.get("tally_verified")) if not is_genesis else True,
        "session_payload": session_payload,
        "chunk_count": sum(
            len(entry.get("chunks") or []) if isinstance(entry.get("chunks"), list) else 0
            for entry in session_payload
        ),
        "packet": session_payload,
        "created_at": now,
        "updated_at": now,
    }
    db[BLOCKCHAIN_BLOCKS_COLLECTION].insert_one(dict(awaiting_record))

    block_hash = compute_block_hash(
        previous_block_hash=str(previous_block_hash),
        block_id=new_block_id,
        chain_id=resolved_chain_id,
        session_payload=session_payload,
        ledger_last_hash=ledger_last_hash,
        winner_entity_type=winner_type,
        winner_entity_id=winner_id,
        timestamp=now,
    )
    # Promote New_BlockID -> BlockID (SHA-512 identity per Blockchain.txt)
    block_id = block_hash

    supply = get_token_supply_state(client=client)
    reward_count = int(supply["block_reward"])
    owner_id = winner_id
    minted_tokens = mint_lucid_tokens(
        client=client,
        owner_id=owner_id,
        count=reward_count,
        block_id=block_id,
    )
    tokens_log = None
    if minted_tokens:
        tokens_log = minted_tokens[0].get("tokens_log_path")

    confirmed_at = utc_now()
    status = "genesis" if is_genesis else "confirmed"
    db[BLOCKCHAIN_BLOCKS_COLLECTION].update_one(
        {"New_BlockID": new_block_id, "status": "new_block"},
        {
            "$set": {
                "blockID": block_id,
                "block_hash": block_hash,
                "status": status,
                "lucid_tokens_minted": len(minted_tokens),
                "block_reward": reward_count,
                "tokens_log_path": tokens_log,
                "updated_at": confirmed_at,
                "confirmed_at": confirmed_at,
            }
        },
    )

    append_ledger_record(
        client=client,
        session_id=winner.get("sessionID") if isinstance(winner.get("sessionID"), str) else None,
        aggregate_hash=block_hash,
        record_type="block",
        block_id=block_id,
        new_block_id=new_block_id,
        creator_id=winner_id,
    )

    from legder import build_block_id_ledger_doc

    last_block_id = (
        str(previous.get("blockID") or previous.get("block_hash"))
        if previous
        else str(GENESIS_PREVIOUS_HASH)
    )
    session_id_value = (
        winner.get("sessionID") if isinstance(winner.get("sessionID"), str) else None
    )
    chunk_count = int(awaiting_record.get("chunk_count") or 0)
    # Payload only — ops appends Master LucidTops_LedgerDB + NodeID_LedgerDB.
    ledger_doc = build_block_id_ledger_doc(
        block_id=block_id,
        creator_id=winner_id,
        creation_timestamp=confirmed_at,
        rewards=reward_count,
        last_block_id=last_block_id,
        session_data_count=chunk_count,
        new_block_id=new_block_id,
        session_id=session_id_value,
        status="committed",
    )

    for session in pending_sessions[: len(session_payload)]:
        db[SESSION_RECORDS_COLLECTION].update_one(
            {"sessionID": session.get("sessionID")},
            {"$set": {"sessionStatus": "blockchain_recorded", "updated_at": confirmed_at}},
        )
        db[BLOCKCHAIN_BLOCKS_COLLECTION].update_many(
            {
                "sessionID": session.get("sessionID"),
                "status": "awaiting_block",
            },
            {
                "$set": {
                    "status": "confirmed",
                    "blockID": block_id,
                    "New_BlockID": new_block_id,
                    "updated_at": confirmed_at,
                }
            },
        )

    if not is_genesis:
        _reset_tally_for_winner(client=client, entity_type=winner_type, entity_id=winner_id)

    block_record = db[BLOCKCHAIN_BLOCKS_COLLECTION].find_one(
        {"blockID": block_id},
        {"_id": 0},
    )
    return {
        "block": block_record,
        "New_BlockID": new_block_id,
        "BlockID": block_id,
        "minted_tokens": minted_tokens,
        "supply": get_token_supply_state(client=client),
        "ledger_doc": ledger_doc,
    }