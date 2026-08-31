"""Specific API routes used by the master server container (FastAPI)."""

from __future__ import annotations

from typing import Any, Callable

from config import get_api_public_base_url, get_master_server_public_url, resolve_master_server_onion
from config import get_master_db, get_mongo_client, utc_now

MASTER_API_ROUTES: tuple[str, ...] = (
    "/register",
    "/login",
    "/logout",
    "/node-registration",
    "/node-login",
    "/node-logout",
    "/tier-select",
    "/billing-information",
    "/payment-processing",
    "/server-blockchain-sync",
    "/server-ledger-sync",
    "/server-database-sync",
    "/server-IDToken-sync",
    "/server-API-key-sync",
)

USER_ROUTES: tuple[str, ...] = (
    "/user-create",
    "/user-find",
    "/user-connect",
    "/user-disconnect",
    "/user-end",
    "/user-record",
    "/user-report",
    "/user-transfer",
    "/user-control",
    "/user-LucidLedger-read",
    "/user-session-create",
    "/user-session-find",
    "/user-session-connect",
    "/user-session-disconnect",
    "/user-session-end",
    "/user-session-record",
    "/user-session-report",
    "/user-session-transfer",
    "/user-session-control",
)

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

SESSION_ROUTES: tuple[str, ...] = (
    "/session-create",
    "/session-find",
    "/session-connect",
    "/session-disconnect",
    "/session-end",
    "/session-record",
    "/session-transfer",
    "/session-control",
)

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

GUI_ROUTES: tuple[str, ...] = (
    "/register",
    "/login",
    "/logout",
    "/home",
    "/settings",
    "/find-peer",
    "/LucidLedger",
    "/LucidMarket",
    "/node-registration",
    "/tier-select",
    "/connect-handshake",
)

ADMIN_ROUTES: tuple[str, ...] = (
    "/login",
    "/dashboard",
    "/users",
    "/nodes",
    "/sessions",
    "/blockchain",
    "/ledger",
    "/database",
)

MASTER_CLASS_ROUTES: tuple[str, ...] = (
    "/login",
    "/dashboard",
    "/users",
    "/nodes",
    "/sessions",
    "/blockchain",
    "/ledger",
)


def _route_handler(route_path: str, subsystem: str) -> Callable[..., dict[str, Any]]:
    tor_url = f"{get_api_public_base_url()}{route_path}"

    def handler() -> dict[str, Any]:
        return {
            "route": route_path,
            "tor_url": tor_url,
            "subsystem": subsystem,
            "status": "registered",
            "service": "master_server",
            "network": "tor",
            "tor_only": True,
            "master_server_onion": resolve_master_server_onion(),
            "master_server_public_url": get_master_server_public_url(),
            "timestamp": utc_now(),
        }

    return handler


def _sync_handler(sync_type: str) -> Callable[..., dict[str, Any]]:
    def handler() -> dict[str, Any]:
        client = get_mongo_client()
        if client is None:
            return {"sync_type": sync_type, "status": "database_unavailable"}
        try:
            db = get_master_db(client)
            collection_map = {
                "blockchain": "blockchain_blocks",
                "ledger": "ledger_records",
                "database": "master_credentials",
                "IDToken": "id_tokens",
                "API-key": "master_credentials",
            }
            key = sync_type.replace("server-", "").replace("-sync", "")
            collection = collection_map.get(key, "master_credentials")
            count = db[collection].count_documents({})
            return {
                "sync_type": sync_type,
                "collection": collection,
                "record_count": count,
                "status": "ok",
                "timestamp": utc_now(),
            }
        finally:
            client.close()

    return handler


def _register_routes(router: Any, routes: tuple[str, ...], tag: str) -> None:
    for route in routes:
        path = route if route.startswith("/") else f"/{route}"
        if path.startswith("/server-") and path.endswith("-sync"):
            handler = _sync_handler(path.lstrip("/"))
        else:
            handler = _route_handler(path, tag)
        router.add_api_route(path, handler, methods=["GET", "POST"], tags=[tag])


def create_master_server_routers() -> dict[str, Any]:
    """Create all master-server FastAPI routers grouped by subsystem."""
    from fastapi import APIRouter

    return {
        "api": _build_api_router(APIRouter(prefix="/api/v1")),
        "gui": _build_gui_router(APIRouter(prefix="/gui")),
        "admin": _build_simple_router(APIRouter(prefix="/admin"), ADMIN_ROUTES, "admin-system"),
        "master_class": _build_simple_router(
            APIRouter(prefix="/master-class"), MASTER_CLASS_ROUTES, "master-class-system"
        ),
    }


def _build_api_router(router: Any) -> Any:
    _register_routes(router, MASTER_API_ROUTES, "master-api")
    return router


def _build_gui_router(router: Any) -> Any:
    _register_routes(router, GUI_ROUTES, "gui")
    return router


def _build_simple_router(router: Any, routes: tuple[str, ...], tag: str) -> Any:
    _register_routes(router, routes, tag)
    return router


def register_master_server_routes(app: Any) -> None:
    """Attach all master-server route groups to a FastAPI application."""
    routers = create_master_server_routers()
    for router in routers.values():
        app.include_router(router)
