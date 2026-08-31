""" the API routes for all the databases systems used by the LucidTops system
DatabaseRoutes:
- /database-create: create a new database (master server restricted access only)
- /database-find: find a database (master server restricted access only)
- /database-connect: connect to a database (master server restricted access only)
- /database-disconnect: disconnect from a database (master server restricted access only)
- /database-end: end a database (master server restricted access only)
- /database-record: record a database (master server restricted access only)
- /database-transfer: transfer a database (master server restricted access only)
- /database-control: control a database (master server restricted access only)
- /database-seed: the creation of a NodeUserID hosted database
- /database-seed-find: find a NodeUserID hosted database
- /database-seed-connect: connect to a NodeUserID hosted database
- /database-seed-disconnect: disconnect from a NodeUserID hosted database
- /database-seed-end: end a NodeUserID hosted database
- /database-seed-record: record a NodeUserID hosted database
- /database-seed-transfer: transfer a NodeUserID hosted database
- /database-seed-control: control a NodeUserID hosted database
- /database-seed-upload: upload a file to a NodeUserID hosted database
- /database-seed-download: download a file from a NodeUserID hosted database (admin restricted access only)
- /database-seed-delete: delete a file from a NodeUserID hosted database (admin restricted access only)
- /database-seed-rename: rename a file in a NodeUserID hosted database (admin restricted access only)
- /database-seed-sync: sync all NodeUserID hosted databases to each other (required information only)
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    get_master_db,
    get_mongo_client,
    handle_operations_error,
    require_admin_access,
    require_master_access,
    tor_envelope,
    utc_now,
    verify_id_token,
)
from NodeDbSchema import NODE_HOSTED_DB_COLLECTION, NODE_SEED_COLLECTION

DATABASE_ROUTES: tuple[str, ...] = (
    "/database-create",
    "/database-find",
    "/database-connect",
    "/database-disconnect",
    "/database-end",
    "/database-record",
    "/database-transfer",
    "/database-control",
    "/database-seed",
    "/database-seed-find",
    "/database-seed-connect",
    "/database-seed-disconnect",
    "/database-seed-end",
    "/database-seed-record",
    "/database-seed-transfer",
    "/database-seed-control",
    "/database-seed-upload",
    "/database-seed-download",
    "/database-seed-delete",
    "/database-seed-rename",
    "/database-seed-sync",
)

MASTER_DATABASE_ROUTES = tuple(
    route for route in DATABASE_ROUTES if not route.startswith("/database-seed")
)
SEED_DATABASE_ROUTES = tuple(
    route for route in DATABASE_ROUTES if route.startswith("/database-seed")
)
ADMIN_SEED_ROUTES = frozenset(
    {
        "/database-seed-download",
        "/database-seed-delete",
        "/database-seed-rename",
    }
)

NODE_SEED_FILES_COLLECTION = "node_seed_files"


if BaseModel is not object:

    class MasterDatabasePayload(BaseModel):
        id_token: str = Field(..., alias="IDToken")
        database_id: str | None = Field(default=None, alias="databaseID")
        payload: dict[str, Any] | None = None

        model_config = {"populate_by_name": True}

    class SeedDatabasePayload(BaseModel):
        node_user_id: str = Field(..., alias="NodeUserID")
        id_token: str = Field(..., alias="IDToken")
        database_id: str | None = Field(default=None, alias="NodeDatabaseID")
        filename: str | None = None
        new_filename: str | None = None
        content_base64: str | None = None

        model_config = {"populate_by_name": True}


def _database_handler(route: str, payload: Any) -> dict[str, Any]:
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        db = get_master_db(client)
        now = utc_now()

        if route in MASTER_DATABASE_ROUTES:
            require_master_access(id_token=payload.id_token, client=client)
            if route == "/database-create":
                database_id = secrets.token_hex(16)
                record = {
                    "databaseID": database_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                db.master_credentials.update_one(
                    {"databaseID": database_id},
                    {"$set": record},
                    upsert=True,
                )
                result = record
            elif route == "/database-find":
                if payload.database_id:
                    record = db.master_credentials.find_one(
                        {"databaseID": payload.database_id}, {"_id": 0}
                    )
                    if not record:
                        raise LookupError("Database not found")
                    result = record
                else:
                    records = list(
                        db.master_credentials.find(
                            {"databaseID": {"$exists": True}}, {"_id": 0}
                        ).limit(50)
                    )
                    result = {"records": records, "count": len(records)}
            else:
                result = {
                    "databaseID": payload.database_id,
                    "action": route.lstrip("/"),
                    "status": "ok",
                    "timestamp": now,
                }
        else:
            if route in ADMIN_SEED_ROUTES:
                require_admin_access(id_token=payload.id_token, client=client)
            elif not verify_id_token(
                node_user_id=payload.node_user_id,
                id_token=payload.id_token,
                client=client,
            ):
                raise PermissionError("NodeUser authentication failed")

            if route == "/database-seed":
                node_database_id = secrets.token_hex(16)
                record = {
                    "NodeUserID": payload.node_user_id,
                    "NodeDatabaseID": node_database_id,
                    "IDToken": payload.id_token,
                    "status": "seeded",
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
                result = record
            elif route == "/database-seed-find":
                query = {"NodeUserID": payload.node_user_id}
                if payload.database_id:
                    query["NodeDatabaseID"] = payload.database_id
                record = db[NODE_SEED_COLLECTION].find_one(query, {"_id": 0})
                if not record:
                    raise LookupError("NodeUserID hosted database not found")
                result = record
            elif route == "/database-seed-upload":
                if not payload.filename or not payload.content_base64:
                    raise ValueError("filename and content_base64 are required")
                content = base64.b64decode(payload.content_base64.encode("utf-8"))
                file_record = {
                    "NodeUserID": payload.node_user_id,
                    "NodeDatabaseID": payload.database_id,
                    "filename": payload.filename,
                    "size_bytes": len(content),
                    "content_base64": payload.content_base64,
                    "updated_at": now,
                }
                db[NODE_SEED_FILES_COLLECTION].update_one(
                    {
                        "NodeUserID": payload.node_user_id,
                        "filename": payload.filename,
                    },
                    {"$set": file_record},
                    upsert=True,
                )
                result = {
                    "filename": payload.filename,
                    "size_bytes": len(content),
                    "status": "uploaded",
                }
            elif route == "/database-seed-download":
                if not payload.filename:
                    raise ValueError("filename is required")
                record = db[NODE_SEED_FILES_COLLECTION].find_one(
                    {
                        "NodeUserID": payload.node_user_id,
                        "filename": payload.filename,
                    },
                    {"_id": 0},
                )
                if not record:
                    raise LookupError("File not found")
                result = record
            elif route == "/database-seed-delete":
                if not payload.filename:
                    raise ValueError("filename is required")
                db[NODE_SEED_FILES_COLLECTION].delete_one(
                    {
                        "NodeUserID": payload.node_user_id,
                        "filename": payload.filename,
                    }
                )
                result = {"filename": payload.filename, "status": "deleted"}
            elif route == "/database-seed-rename":
                if not payload.filename or not payload.new_filename:
                    raise ValueError("filename and new_filename are required")
                record = db[NODE_SEED_FILES_COLLECTION].find_one_and_update(
                    {
                        "NodeUserID": payload.node_user_id,
                        "filename": payload.filename,
                    },
                    {"$set": {"filename": payload.new_filename, "updated_at": now}},
                )
                if not record:
                    raise LookupError("File not found")
                result = {
                    "old_filename": payload.filename,
                    "new_filename": payload.new_filename,
                    "status": "renamed",
                }
            elif route == "/database-seed-sync":
                seeds = list(db[NODE_SEED_COLLECTION].find({}, {"_id": 0}))
                sync_payload = [
                    {
                        "NodeUserID": seed.get("NodeUserID"),
                        "NodeDatabaseID": seed.get("NodeDatabaseID"),
                        "status": seed.get("status"),
                    }
                    for seed in seeds
                ]
                result = {"synced": sync_payload, "count": len(sync_payload)}
            else:
                result = {
                    "NodeUserID": payload.node_user_id,
                    "NodeDatabaseID": payload.database_id,
                    "action": route.lstrip("/"),
                    "status": "ok",
                    "timestamp": now,
                }

        return tor_envelope(route=route, subsystem="database-system", payload=result)
    finally:
        client.close()


def create_database_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create database routes")
    router = APIRouter(prefix=prefix, tags=["database-system"])

    def _wrap_master(route: str, payload: MasterDatabasePayload) -> dict[str, Any]:
        try:
            return _database_handler(route, payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    def _wrap_seed(route: str, payload: SeedDatabasePayload) -> dict[str, Any]:
        try:
            return _database_handler(route, payload)
        except Exception as exc:
            handle_operations_error(exc)
            raise

    for route in MASTER_DATABASE_ROUTES:
        router.add_api_route(
            route,
            (lambda r: (lambda payload: _wrap_master(r, payload)))(route),
            methods=["GET", "POST"],
        )

    for route in SEED_DATABASE_ROUTES:
        router.add_api_route(
            route,
            (lambda r: (lambda payload: _wrap_seed(r, payload)))(route),
            methods=["GET", "POST"],
        )

    return router


def register_database_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    app.include_router(create_database_router(prefix=api_prefix))
