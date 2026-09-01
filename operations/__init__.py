"""LucidTops operations package — Tor-only FastAPI route implementations."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

OPERATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPERATIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, OPERATIONS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from BlockRoutes import BLOCKCHAIN_ROUTES, create_blockchain_router, register_blockchain_routes
from NodeDbSchema import (
    NODE_DB_SCHEMA_FIELDS,
    NODE_HOSTED_DB_COLLECTION,
    NODE_SEED_COLLECTION,
    NODE_SEED_FIELDS,
    schema_template as node_db_schema_template,
)
from DatabaseRoutes import DATABASE_ROUTES, create_database_router, register_database_routes
from NodeRoutes import NODE_ROUTES, create_node_router, register_node_routes
from SessionRoutes import SESSION_ROUTES, create_session_router, register_session_routes
from UserRoutes import USER_ROUTES, create_user_router, register_user_routes

_chip_in_spec = importlib.util.spec_from_file_location(
    "chip_in", OPERATIONS_DIR / "chip-in.py"
)
if _chip_in_spec is None or _chip_in_spec.loader is None:
    raise ImportError("Unable to load operations/chip-in.py")
_chip_in = importlib.util.module_from_spec(_chip_in_spec)
_chip_in_spec.loader.exec_module(_chip_in)
CHIP_IN_ROUTES = _chip_in.CHIP_IN_ROUTES
register_chip_in_routes = _chip_in.register_chip_in_routes
create_chip_in_router = _chip_in.create_chip_in_router
handle_chip_in = _chip_in.handle_chip_in

__all__ = (
    "BLOCKCHAIN_ROUTES",
    "CHIP_IN_ROUTES",
    "DATABASE_ROUTES",
    "NODE_DB_SCHEMA_FIELDS",
    "NODE_HOSTED_DB_COLLECTION",
    "NODE_ROUTES",
    "NODE_SEED_COLLECTION",
    "NODE_SEED_FIELDS",
    "SESSION_ROUTES",
    "USER_ROUTES",
    "create_blockchain_router",
    "create_chip_in_router",
    "create_database_router",
    "create_node_router",
    "create_session_router",
    "create_user_router",
    "handle_chip_in",
    "node_db_schema_template",
    "register_chip_in_routes",
    "register_operations_routes",
    "register_blockchain_routes",
    "register_database_routes",
    "register_node_routes",
    "register_session_routes",
    "register_user_routes",
)


def register_operations_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    """Attach all operations subsystem routers to the master server FastAPI app."""
    register_user_routes(app, api_prefix=api_prefix)
    register_node_routes(app, api_prefix=api_prefix)
    register_blockchain_routes(app, api_prefix=api_prefix)
    register_session_routes(app, api_prefix=api_prefix)
    register_database_routes(app, api_prefix=api_prefix)
    register_chip_in_routes(app, api_prefix=api_prefix)
