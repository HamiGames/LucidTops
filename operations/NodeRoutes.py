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


this API routes file is hosted on the MasterServer container
the API routes are used to access the lucid projects NodeUser system
the API routes are used to access the lucid projects LucidLedger system
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
    verify_id_token,
)
from Backend.NodeDbSchema import NODE_HOSTED_DB_COLLECTION, NODE_SEED_COLLECTION  # pyright: ignore[reportMissingImports]

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

    class NodeAuthPayload(BaseModel):
        node_user_id: str = Field(..., alias="NodeUserID")
        id_token: str = Field(..., alias="IDToken")

        model_config = {"populate_by_name": True}

    class NodeCreatePayload(NodeAuthPayload):
        user_id: str = Field(..., alias="UserID")

        model_config = {"populate_by_name": True}

    class NodeLedgerPayload(NodeAuthPayload):
        block_id: str | None = Field(default=None, alias="blockID")
        payload: dict[str, Any] | None = None

        model_config = {"populate_by_name": True}


def _ledger_action(
    *,
    route: str,
    node_user_id: str,
    id_token: str,
    block_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        if not verify_id_token(
            node_user_id=node_user_id, id_token=id_token, client=client
        ):
            raise PermissionError("NodeUser authentication failed")
        db = get_master_db(client)
        collection = (
            LUCID_LEDGER_COLLECTION
            if "LucidLedger" in route
            else BLOCKCHAIN_COLLECTION
        )
        now = utc_now()
        if route.endswith("-read"):
            records = list(db[collection].find({}, {"_id": 0}).limit(100))
            return {"records": records, "count": len(records)}
        if route.endswith("-create"):
            block = {
                "blockID": block_id or secrets.token_hex(8),
                "NodeUserID": node_user_id,
                "payload": payload or {},
                "created_at": now,
            }
            db[collection].insert_one(block)
            block.pop("_id", None)
            return block
        if route.endswith("-find") and block_id:
            record = db[collection].find_one({"blockID": block_id}, {"_id": 0})
            if not record:
                raise LookupError("Block not found")
            return record
        if route.endswith("-write") or route.endswith("-update"):
            if not block_id:
                raise ValueError("blockID is required")
            db[collection].update_one(
                {"blockID": block_id},
                {"$set": {"payload": payload or {}, "updated_at": now}},
                upsert=True,
            )
            return {"blockID": block_id, "status": "updated"}
        if route.endswith("-delete") and block_id:
            db[collection].delete_one({"blockID": block_id})
            return {"blockID": block_id, "status": "deleted"}
        return {
            "NodeUserID": node_user_id,
            "action": route,
            "blockID": block_id,
            "status": "ok",
            "timestamp": now,
        }
    finally:
        client.close()


def _node_handler(route: str, payload: Any) -> dict[str, Any]:
    if "LucidLedger" in route or "Blockchain" in route:
        result = _ledger_action(
            route=route,
            node_user_id=payload.node_user_id,
            id_token=payload.id_token,
            block_id=getattr(payload, "block_id", None),
            payload=getattr(payload, "payload", None),
        )
        return tor_envelope(route=route, subsystem="node-system", payload=result)

    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        db = get_master_db(client)
        now = utc_now()
        if route == "/node-create":
            if not verify_id_token(
                node_user_id=payload.node_user_id,
                id_token=payload.id_token,
                client=client,
            ):
                raise PermissionError("NodeUser authentication failed")
            node_database_id = secrets.token_hex(16)
            record = {
                "NodeUserID": payload.node_user_id,
                "UserID": payload.user_id,
                "IDToken": payload.id_token,
                "NodeDatabaseID": node_database_id,
                "created_at": now,
                "updated_at": now,
            }
            db[NODE_SEED_COLLECTION].update_one(
                {"NodeUserID": payload.node_user_id},
                {"$set": record},
                upsert=True,
            )
            db[NODE_HOSTED_DB_COLLECTION].update_one(
                {"NodeUserID": payload.node_user_id},
                {"$set": record},
                upsert=True,
            )
            result = {"status": "created", **record}
        elif route == "/node-find":
            record = db.node_users.find_one(
                {"NodeUserID": payload.node_user_id}, {"_id": 0}
            )
            if not record:
                raise LookupError("Node not found")
            result = record
        else:
            if not verify_id_token(
                node_user_id=payload.node_user_id,
                id_token=payload.id_token,
                client=client,
            ):
                raise PermissionError("NodeUser authentication failed")
            result = {
                "NodeUserID": payload.node_user_id,
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


def register_node_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    app.include_router(create_node_router(prefix=api_prefix))
