""" the API routes specific to the NodeUser system (using FastAPI)
NodeRoutes:
- /node-create: create a new node
- /node-find: find a node
- /node-connect: connect to a node
- /node-disconnect: disconnect from a node
- /node-end: end a node
- /node-record: record a node
- /node-report: report a node
- /node-transfer: transfer a node
- /node-control: control a node
- /node-LucidLedger-read: read the LucidLedger system
- /node-LucidLedger-write: write to the LucidLedger system
- /node-LucidLedger-update: update the LucidLedger system
- /node-LucidLedger-delete: delete from the LucidLedger system
- /node-LucidLedger-create: create a new block in the LucidLedger system
- /node-LucidLedger-find: find a block in the LucidLedger system
- /node-LucidLedger-connect: connect to a block in the LucidLedger system
- /node-LucidLedger-disconnect: disconnect from a block in the LucidLedger system
- /node-LucidLedger-end: end a block in the LucidLedger system
- /node-LucidLedger-record: record a block in the LucidLedger system
- /node-LucidLedger-report: report a block in the LucidLedger system
- /node-Blockchain-read: read the Blockchain system
- /node-Blockchain-create: create a new block in the Blockchain system
- /node-Blockchain-find: find a block in the Blockchain system
- /node-Blockchain-connect: connect to a block in the Blockchain system
- /node-Blockchain-disconnect: disconnect from a block in the Blockchain system

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.


this API routes file is hosted on the MasterServer container
the API routes are used to access the lucid projects NodeUser system
the API routes are used to access the lucid projects LucidLedger system

"""

from __future__ import annotations

from typing import Any

from _common import (
    APIRouter,
    BLOCKCHAIN_COLLECTION,
    Field,
    LUCID_LEDGER_COLLECTION,
    OperatorAuthPayload,
    BaseModel,
    get_master_db,
    get_mongo_client,
    handle_operations_error,
    operator_kwargs_from_payload,
    require_operations_operator,
    tor_envelope,
    utc_now,
)
from NodeDbSchema import NODE_HOSTED_DB_COLLECTION, NODE_SEED_COLLECTION
from operations_secrets import (
    node_ledger_db_name_for_id,
    resolve_node_ledger_last_block_field,
    resolve_operations_api_prefix,
    resolve_operations_ledger_read_limit,
)
from session_to_block import process_complete_session_to_block

NODE_ROUTES: tuple[str, ...] = (
    "/node-create",
    "/node-find",
    "/node-connect",
    "/node-disconnect",
    "/node-end",
    "/node-record",
    "/node-report",
    "/node-transfer",
    "/node-control",
    "/node-LucidLedger-read",
    "/node-LucidLedger-write",
    "/node-LucidLedger-update",
    "/node-LucidLedger-delete",
    "/node-LucidLedger-create",
    "/node-LucidLedger-find",
    "/node-LucidLedger-connect",
    "/node-LucidLedger-disconnect",
    "/node-LucidLedger-end",
    "/node-LucidLedger-record",
    "/node-LucidLedger-report",
    "/node-Blockchain-read",
    "/node-Blockchain-create",
    "/node-Blockchain-find",
    "/node-Blockchain-connect",
    "/node-Blockchain-disconnect",
)

LUCID_LEDGER_NODE_ROUTES = tuple(
    route for route in NODE_ROUTES if "LucidLedger" in route
)
BLOCKCHAIN_NODE_ROUTES = tuple(route for route in NODE_ROUTES if "Blockchain" in route)


if BaseModel is not object:

    class NodeAuthPayload(OperatorAuthPayload):
        pass

    class NodeCreatePayload(OperatorAuthPayload):
        user_id: str = Field(..., alias="UserID")

        model_config = {"populate_by_name": True}

    class NodeLedgerPayload(OperatorAuthPayload):
        block_id: str | None = Field(default=None, alias="blockID")
        session_id: str | None = Field(default=None, alias="sessionID")
        payload: dict[str, Any] | None = None

        model_config = {"populate_by_name": True}


def _ledger_action(
    *,
    route: str,
    payload: Any,
) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        operator = require_operations_operator(
            client=client,
            **operator_kwargs_from_payload(payload),
        )
        db = get_master_db(client)
        collection = (
            LUCID_LEDGER_COLLECTION
            if "LucidLedger" in route
            else BLOCKCHAIN_COLLECTION
        )
        now = utc_now()
        block_id = getattr(payload, "block_id", None)
        session_id = getattr(payload, "session_id", None)

        if route.endswith("-create"):
            if not session_id:
                raise ValueError(
                    "sessionID is required — New_BlockID is created only from "
                    "SessionID_status complete session-data chunks"
                )
            return process_complete_session_to_block(
                session_id=session_id,
                client=client,
                **operator_kwargs_from_payload(payload),
            )

        if route.endswith("-read"):
            records = list(
                db[collection].find({}, {"_id": 0}).limit(resolve_operations_ledger_read_limit())
            )
            node_ledger = client[node_ledger_db_name_for_id(operator["operator_id"])]
            last_field = resolve_node_ledger_last_block_field()
            meta = node_ledger["ledger_meta"].find_one({"_meta": True}, {"_id": 0}) or {}
            return {
                "records": records,
                "count": len(records),
                "operator_id": operator["operator_id"],
                "id_type": operator["id_type"],
                last_field: meta.get(last_field) or meta.get("LastBlockID"),
            }

        if route.endswith("-find") and block_id:
            record = db[collection].find_one({"BlockID": block_id}, {"_id": 0})
            if not record:
                record = db[collection].find_one({"blockID": block_id}, {"_id": 0})
            if not record:
                raise LookupError("Block not found")
            return record

        if route.endswith("-write") or route.endswith("-update"):
            if not block_id:
                raise ValueError("blockID is required")
            db[collection].update_one(
                {"$or": [{"BlockID": block_id}, {"blockID": block_id}]},
                {
                    "$set": {
                        "payload": getattr(payload, "payload", None) or {},
                        "updated_at": now,
                        "creator_id": {operator["id_type"]: operator["operator_id"]},
                    }
                },
                upsert=True,
            )
            return {"BlockID": block_id, "status": "updated"}

        if route.endswith("-delete") and block_id:
            db[collection].delete_one(
                {"$or": [{"BlockID": block_id}, {"blockID": block_id}]}
            )
            return {"BlockID": block_id, "status": "deleted"}

        return {
            "operator_id": operator["operator_id"],
            "id_type": operator["id_type"],
            "action": route,
            "BlockID": block_id,
            "status": "ok",
            "timestamp": now,
        }
    finally:
        client.close()


def _node_handler(route: str, payload: Any) -> dict[str, Any]:
    if "LucidLedger" in route or "Blockchain" in route:
        result = _ledger_action(route=route, payload=payload)
        return tor_envelope(route=route, subsystem="node-system", payload=result)

    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        operator = require_operations_operator(
            client=client,
            **operator_kwargs_from_payload(payload),
        )
        db = get_master_db(client)
        now = utc_now()
        if route == "/node-create":
            node_database_id = operator["operator_id"]
            record = {
                "NodeID": operator["operator_id"],
                "id_type": operator["id_type"],
                "UserID": getattr(payload, "user_id", None),
                "TokenID": operator["TokenID"],
                "NodeDatabaseID": node_database_id,
                "email": operator["email"],
                "mac": operator["mac"],
                "created_at": now,
                "updated_at": now,
            }
            db[NODE_SEED_COLLECTION].update_one(
                {"NodeID": operator["operator_id"]},
                {"$set": record},
                upsert=True,
            )
            db[NODE_HOSTED_DB_COLLECTION].update_one(
                {"NodeID": operator["operator_id"]},
                {"$set": record},
                upsert=True,
            )
            result = {"status": "created", **record}
        elif route == "/node-find":
            record = db[NODE_SEED_COLLECTION].find_one(
                {"NodeID": operator["operator_id"]}, {"_id": 0}
            )
            if not record:
                raise LookupError("Node not found")
            result = record
        else:
            result = {
                "NodeID": operator["operator_id"],
                "id_type": operator["id_type"],
                "action": route.lstrip("/"),
                "status": "ok",
                "timestamp": now,
            }
        return tor_envelope(route=route, subsystem="node-system", payload=result)
    finally:
        client.close()


def create_node_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create node routes")
    router = APIRouter(prefix=prefix, tags=["node-system"])

    def _wrap(route: str, payload: Any) -> dict[str, Any]:
        try:
            return _node_handler(route, payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    @router.post("/node-create")
    def node_create(payload: NodeCreatePayload) -> dict[str, Any]:
        return _wrap("/node-create", payload)

    @router.post("/node-find")
    def node_find(payload: NodeAuthPayload) -> dict[str, Any]:
        return _wrap("/node-find", payload)

    for route in (
        "/node-connect",
        "/node-disconnect",
        "/node-end",
        "/node-record",
        "/node-report",
        "/node-transfer",
        "/node-control",
    ):
        router.add_api_route(
            route,
            lambda payload, route=route: _wrap(route, payload),
            methods=["POST"],
            response_model=None,
        )

    for route in LUCID_LEDGER_NODE_ROUTES + BLOCKCHAIN_NODE_ROUTES:
        router.add_api_route(
            route,
            lambda payload, route=route: _wrap(route, payload),
            methods=["POST"],
            response_model=None,
        )

    return router


def register_node_routes(app: Any, *, api_prefix: str | None = None) -> None:
    prefix = api_prefix if api_prefix is not None else resolve_operations_api_prefix()
    app.include_router(create_node_router(prefix=prefix))
