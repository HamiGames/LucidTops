"""the API routes for the blockchain system (using FastAPI)
BlockchainRoutes:
- /blockchain-create: create a new blockchain
- /blockchain-find: find a blockchain
- /blockchain-connect: connect to a blockchain
- /blockchain-disconnect: disconnect from a blockchain
- /blockchain-end: end a blockchain
- /blockchain-record: record a blockchain
- /blockchain-report: report a blockchain
- /blockchain-transfer: transfer a blockchain
- /blockchain-control: control a blockchain
- /LucidLedger: create a new block in the LucidLedger system
- /LucidLedger-find: find a block in the LucidLedger system
- /LucidLedger-connect: connect to a block in the LucidLedger system
- /LucidLedger-disconnect: disconnect from a block in the LucidLedger system
- /LucidLedger-end: end a block in the LucidLedger system
- /LucidLedger-record: record a block in the LucidLedger system
- /LucidLedger-report: report a block in the LucidLedger system
- /LucidLedger-transfer: transfer a block in the LucidLedger system
- /LucidLedger-control: control a block in the LucidLedger system
"""

from __future__ import annotations

import secrets
from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    BLOCKCHAIN_COLLECTION,
    Field,
    LUCID_LEDGER_COLLECTION,
    get_master_db,
    get_mongo_client,
    handle_operations_error,
    tor_envelope,
    utc_now,
)
from session import compress_session
from operations_secrets import (
    resolve_blockchain_hash_algorithm,
    resolve_operations_api_prefix,
    resolve_operations_ledger_read_limit,
    resolve_operations_query_limit,
)

BLOCKCHAIN_ROUTES: tuple[str, ...] = (
    "/blockchain-create",
    "/blockchain-find",
    "/blockchain-connect",
    "/blockchain-disconnect",
    "/blockchain-end",
    "/blockchain-record",
    "/blockchain-report",
    "/blockchain-transfer",
    "/blockchain-control",
    "/LucidLedger",
    "/LucidLedger-find",
    "/LucidLedger-connect",
    "/LucidLedger-disconnect",
    "/LucidLedger-end",
    "/LucidLedger-record",
    "/LucidLedger-report",
    "/LucidLedger-transfer",
    "/LucidLedger-control",
)

LUCID_LEDGER_ROUTES = tuple(route for route in BLOCKCHAIN_ROUTES if "LucidLedger" in route)


if BaseModel is not object:

    class BlockchainPayload(BaseModel):
        session_id: str | None = Field(default=None, alias="sessionID")
        block_id: str | None = Field(default=None, alias="blockID")
        payload: dict[str, Any] | None = None

        model_config = {"populate_by_name": True}


def _blockchain_handler(route: str, payload: BlockchainPayload) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        db = get_master_db(client)
        now = utc_now()
        collection = (
            LUCID_LEDGER_COLLECTION if "LucidLedger" in route else BLOCKCHAIN_COLLECTION
        )

        if route == "/blockchain-create":
            chain_id = secrets.token_hex(8)
            record = {
                "chainID": chain_id,
                "status": "active",
                "hash_algorithm": resolve_blockchain_hash_algorithm(),
                "created_at": now,
            }
            db[collection].insert_one(record)
            record.pop("_id", None)
            result = record
        elif route == "/blockchain-find":
            if payload.block_id:
                record = db[collection].find_one({"blockID": payload.block_id}, {"_id": 0})
                if not record:
                    record = db[collection].find_one({"chainID": payload.block_id}, {"_id": 0})
                if not record:
                    raise LookupError("Blockchain record not found")
                result = record
            else:
                records = list(
                    db[collection].find({}, {"_id": 0}).limit(resolve_operations_query_limit())
                )
                result = {"records": records, "count": len(records)}
        elif route == "/blockchain-end" and payload.session_id:
            result = compress_session(session_id=payload.session_id, client=client)
        elif route == "/LucidLedger":
            block_id = payload.block_id or secrets.token_hex(8)
            record = {
                "blockID": block_id,
                "payload": payload.payload or {},
                "hash_algorithm": resolve_blockchain_hash_algorithm(),
                "created_at": now,
            }
            db[LUCID_LEDGER_COLLECTION].insert_one(record)
            record.pop("_id", None)
            result = record
        elif route in LUCID_LEDGER_ROUTES and route != "/LucidLedger":
            suffix = route.split("/LucidLedger-")[-1]
            if suffix == "find" and payload.block_id:
                record = db[LUCID_LEDGER_COLLECTION].find_one(
                    {"blockID": payload.block_id}, {"_id": 0}
                )
                if not record:
                    raise LookupError("LucidLedger block not found")
                result = record
            else:
                result = {
                    "blockID": payload.block_id,
                    "action": suffix,
                    "status": "ok",
                    "timestamp": now,
                }
        else:
            result = {
                "action": route.lstrip("/"),
                "sessionID": payload.session_id,
                "blockID": payload.block_id,
                "status": "ok",
                "timestamp": now,
            }
        return tor_envelope(route=route, subsystem="blockchain-system", payload=result)
    finally:
        client.close()


def create_blockchain_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create blockchain routes")
    router = APIRouter(prefix=prefix, tags=["blockchain-system"])

    def _wrap(route: str, payload: BlockchainPayload) -> dict[str, Any]:
        try:
            return _blockchain_handler(route, payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    for route in BLOCKCHAIN_ROUTES:
        router.add_api_route(
            route,
            (lambda r: (lambda payload: _wrap(r, payload)))(route),
            methods=["GET", "POST"],
        )

    return router


def register_blockchain_routes(app: Any, *, api_prefix: str | None = None) -> None:
    prefix = api_prefix if api_prefix is not None else resolve_operations_api_prefix()
    app.include_router(create_blockchain_router(prefix=prefix))
