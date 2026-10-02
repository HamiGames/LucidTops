"""Specific API routes used by the master server container (FastAPI)."""

from __future__ import annotations

from typing import Any, Callable

from config import API_PREFIX, format_tor_onion_service, get_master_db, get_mongo_client, resolve_master_server_onion, utc_now
from WebPageLink import frontend_link_for_api_route

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
    link = frontend_link_for_api_route(route_path)

    def handler() -> dict[str, Any]:
        onion = resolve_master_server_onion()
        api_segment = link.get("api_path") or route_path
        api_path = (
            api_segment
            if api_segment.startswith(API_PREFIX)
            else f"{API_PREFIX}{api_segment if api_segment.startswith('/') else f'/{api_segment}'}"
        )
        response: dict[str, Any] = {
            "route": route_path,
            "subsystem": subsystem,
            "status": "registered",
            "service": "master_server",
            "network": "tor",
            "tor_only": True,
            "master_server_onion": onion or "",
            "timestamp": utc_now(),
        }
        if link.get("frontend"):
            response["frontend"] = link["frontend"]
            response["javascript"] = link["javascript"]
        response["api_path"] = api_path
        if link.get("gui_path"):
            response["gui_path"] = link["gui_path"]
        if onion:
            response["tor_service"] = format_tor_onion_service(onion, api_path)
        return response

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


_PUBLIC_AUTH_PATHS = frozenset(
    {"/register", "/login", "/node-registration", "/node-login"}
)


def _register_routes(router: Any, routes: tuple[str, ...], tag: str) -> None:
    public_post = tag in {"master-api", "gui"}
    for route in routes:
        path = route if route.startswith("/") else f"/{route}"
        if path.startswith("/server-") and path.endswith("-sync"):
            handler = _sync_handler(path.lstrip("/"))
        else:
            handler = _route_handler(path, tag)
        methods = ["GET"] if public_post and path in _PUBLIC_AUTH_PATHS else ["GET", "POST"]
        router.add_api_route(path, handler, methods=methods, tags=[tag])


def _attach_public_auth(router: Any) -> None:
    """POST /register and /login create or accept a per-user TokenID. GET stays the stub."""
    from public_registration import (
        public_login_endpoint,
        public_node_login_endpoint,
        public_node_register_endpoint,
        public_register_endpoint,
    )

    router.add_api_route("/register", public_register_endpoint, methods=["POST"], tags=["public-auth"])
    router.add_api_route("/login", public_login_endpoint, methods=["POST"], tags=["public-auth"])
    router.add_api_route(
        "/node-registration",
        public_node_register_endpoint,
        methods=["POST"],
        tags=["public-auth"],
    )
    router.add_api_route(
        "/node-login",
        public_node_login_endpoint,
        methods=["POST"],
        tags=["public-auth"],
    )


def create_master_server_routers() -> dict[str, Any]:
    """Create all master-server FastAPI routers grouped by subsystem."""
    from fastapi import APIRouter

    from config import get_config_value

    api_prefix = get_config_value("API_BASE_PATH")
    gui_prefix = get_config_value("GUI_PREFIX")
    admin_prefix = get_config_value("ADMIN_API_PREFIX")
    master_class_prefix = get_config_value("MASTER_CLASS_API_PREFIX")

    return {
        "api": _build_api_router(APIRouter(prefix=api_prefix)),
        "gui": _build_gui_router(APIRouter(prefix=gui_prefix)),
        "admin": _build_simple_router(APIRouter(prefix=admin_prefix), ADMIN_ROUTES, "admin-system"),
        "master_class": _build_simple_router(
            APIRouter(prefix=master_class_prefix), MASTER_CLASS_ROUTES, "master-class-system"
        ),
    }


def _build_api_router(router: Any) -> Any:
    _register_routes(router, MASTER_API_ROUTES, "master-api")
    _attach_public_auth(router)
    return router


def _build_gui_router(router: Any) -> Any:
    _register_routes(router, GUI_ROUTES, "gui")
    _attach_public_auth(router)
    return router


def _build_simple_router(router: Any, routes: tuple[str, ...], tag: str) -> Any:
    _register_routes(router, routes, tag)
    return router


def register_master_server_routes(app: Any) -> None:
    """Attach all master-server route groups to a FastAPI application."""
    routers = create_master_server_routers()
    for router in routers.values():
        app.include_router(router)
