"""the API routes for the blockchain system (using FastAPI)
BlockchainRoutes (operations mediation — DockerDNS to blockchain governance):
- /blockchain-create: chunk complete session → blockchain local-chain create →
  ops-only append to LucidTops_LedgerDB + {NodeID}_LedgerDB
- /blockchain-find: find a BlockID in LucidTops_LedgerDB
- /blockchain-connect: connect to a blockchain
- /blockchain-disconnect: disconnect from a blockchain
- /blockchain-end: end a blockchain
- /blockchain-record: record via same create → ops append path
- /blockchain-report: report a blockchain
- /blockchain-transfer: transfer a blockchain
- /blockchain-control: control / read LucidTops_LedgerDB
- /LucidLedger: create → ops append via transport (same create path)
- /LucidLedger-find: find a block in LucidTops_LedgerDB
- /LucidLedger-connect: connect to a block in the LucidLedger system
- /LucidLedger-disconnect: disconnect from a block in the LucidLedger system
- /LucidLedger-end: end a block in the LucidLedger system
- /LucidLedger-record: record via create → ops append
- /LucidLedger-report: report a block in the LucidLedger system
- /LucidLedger-transfer: transfer a block in the LucidLedger system
- /LucidLedger-control: control a block in the LucidLedger system
RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    OperatorAuthPayload,
    get_mongo_client,
    handle_operations_error,
    operator_kwargs_from_payload,
    require_operations_operator,
    tor_envelope,
    utc_now,
)
from session import compress_session
from session_to_block import process_complete_session_to_block
from operations_secrets import (
    resolve_blockchain_hash_algorithm,
    resolve_lucid_ledger_collection,
    resolve_lucidtops_ledger_db_name,
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

    class BlockchainPayload(OperatorAuthPayload):
        session_id: str | None = Field(default=None, alias="sessionID")
        block_id: str | None = Field(default=None, alias="blockID")
        payload: dict[str, Any] | None = None

        model_config = {"populate_by_name": True}


def _lucidtops_ledger_collection(client: Any) -> Any:
    return client[resolve_lucidtops_ledger_db_name()][resolve_lucid_ledger_collection()]


def _blockchain_handler(route: str, payload: BlockchainPayload) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        operator = require_operations_operator(
            client=client,
            **operator_kwargs_from_payload(payload),
        )
        ledger = _lucidtops_ledger_collection(client)
        now = utc_now()

        if route == "/blockchain-create":
            if not payload.session_id:
                raise ValueError(
                    "sessionID required — blockchain block creation uses complete session chunks"
                )
            result = process_complete_session_to_block(
                session_id=payload.session_id,
                client=client,
                **operator_kwargs_from_payload(payload),
            )
            result["hash_algorithm"] = resolve_blockchain_hash_algorithm()
        elif route == "/blockchain-find":
            if payload.block_id:
                record = ledger.find_one(
                    {"$or": [{"BlockID": payload.block_id}, {"blockID": payload.block_id}]},
                    {"_id": 0},
                )
                if not record:
                    record = ledger.find_one(
                        {"chainID": payload.block_id}, {"_id": 0}
                    )
                if not record:
                    raise LookupError("Blockchain record not found")
                result = record
            else:
                records = list(
                    ledger.find({}, {"_id": 0}).limit(resolve_operations_query_limit())
                )
                result = {
                    "records": records,
                    "count": len(records),
                    "LucidTops_LedgerDB": resolve_lucidtops_ledger_db_name(),
                    "ledger_collection": resolve_lucid_ledger_collection(),
                }
        elif route == "/blockchain-end" and payload.session_id:
            result = compress_session(session_id=payload.session_id, client=client)
        elif route == "/blockchain-record":
            if not payload.session_id:
                raise ValueError(
                    "sessionID required — blockchain record uses complete session chunks"
                )
            result = process_complete_session_to_block(
                session_id=payload.session_id,
                client=client,
                **operator_kwargs_from_payload(payload),
            )
        elif route == "/LucidLedger":
            if not payload.session_id:
                raise ValueError(
                    "sessionID required — LucidLedger New_BlockID is created only from "
                    "SessionID_status complete session-data"
                )
            result = process_complete_session_to_block(
                session_id=payload.session_id,
                client=client,
                **operator_kwargs_from_payload(payload),
            )
        elif route in LUCID_LEDGER_ROUTES and route != "/LucidLedger":
            suffix = route.split("/LucidLedger-")[-1]
            if suffix == "find" and payload.block_id:
                record = ledger.find_one(
                    {
                        "$or": [
                            {"BlockID": payload.block_id},
                            {"blockID": payload.block_id},
                        ]
                    },
                    {"_id": 0},
                )
                if not record:
                    raise LookupError("LucidLedger block not found")
                result = record
            elif suffix == "record" and payload.session_id:
                result = process_complete_session_to_block(
                    session_id=payload.session_id,
                    client=client,
                    **operator_kwargs_from_payload(payload),
                )
            else:
                result = {
                    "BlockID": payload.block_id,
                    "action": suffix,
                    "operator_id": operator["operator_id"],
                    "id_type": operator["id_type"],
                    "status": "ok",
                    "timestamp": now,
                    "LucidTops_LedgerDB": resolve_lucidtops_ledger_db_name(),
                }
                if suffix in {"control", "report"} or route.endswith("-read"):
                    records = list(
                        ledger.find({}, {"_id": 0}).limit(
                            resolve_operations_ledger_read_limit()
                        )
                    )
                    result["records"] = records
                    result["count"] = len(records)
        else:
            result = {
                "action": route.lstrip("/"),
                "sessionID": payload.session_id,
                "BlockID": payload.block_id,
                "operator_id": operator["operator_id"],
                "id_type": operator["id_type"],
                "status": "ok",
                "timestamp": now,
                "LucidTops_LedgerDB": resolve_lucidtops_ledger_db_name(),
            }
            if route.endswith("-read") or route == "/blockchain-control":
                records = list(
                    ledger.find({}, {"_id": 0}).limit(
                        resolve_operations_ledger_read_limit()
                    )
                )
                result["records"] = records
                result["count"] = len(records)
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
