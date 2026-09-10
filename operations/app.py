"""LucidTops operations FastAPI application (standalone container entry).

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

OPERATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPERATIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, OPERATIONS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def bootstrap_operations_runtime() -> dict[str, Any]:
    """Pull hardware and bind env before secrets / route imports resolve values."""
    from ops_pull_information import pull_operations_hardware

    return pull_operations_hardware(bind_environ=True, overwrite=False)


def create_app() -> Any:
    bootstrap_operations_runtime()

    try:
        from fastapi import FastAPI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("fastapi is required for the operations container") from exc

    from operations_secrets import (
        resolve_operations_api_prefix,
        resolve_operations_docker_dns_name,
        resolve_operations_network_name,
        resolve_operations_service_name,
        resolve_operations_tor_only,
    )
    from id_secrets import load_id_secrets, resolve_operator_from_id_secrets
    from _common import get_mongo_client, require_operations_operator

    # Validate ID.secrets exists after registration approval (fail fast at operation time).
    operator_binding = resolve_operator_from_id_secrets(load_id_secrets())

    client = get_mongo_client()
    if client is None:
        raise RuntimeError(
            "LucidTopsNodeDB unavailable — MongoDB must be reachable at time of operation"
        )
    try:
        require_operations_operator(
            node_id=operator_binding["operator_id"]
            if operator_binding["id_type"] == "NodeID"
            else None,
            admin_id=operator_binding["operator_id"]
            if operator_binding["id_type"] == "AdminID"
            else None,
            master_user_id=operator_binding["operator_id"]
            if operator_binding["id_type"] == "MasterUserID"
            else None,
            master_server_id=operator_binding["operator_id"]
            if operator_binding["id_type"] == "MasterServerID"
            else None,
            token_id=operator_binding["TokenID"],
            email=operator_binding["email"],
            client=client,
        )
    finally:
        client.close()

    app = FastAPI(
        title=resolve_operations_service_name(),
        docs_url=None,
        redoc_url=None,
    )
    app.state.operations_docker_dns = resolve_operations_docker_dns_name()
    app.state.operations_network = resolve_operations_network_name()
    app.state.tor_only = resolve_operations_tor_only()
    app.state.operator_id_type = operator_binding["id_type"]
    app.state.operator_id = operator_binding["operator_id"]

    from NodeRoutes import register_node_routes
    from BlockRoutes import register_blockchain_routes
    from SessionRoutes import register_session_routes
    from UserRoutes import register_user_routes
    from DatabaseRoutes import register_database_routes
    import importlib.util

    prefix = resolve_operations_api_prefix()
    register_user_routes(app, api_prefix=prefix)
    register_node_routes(app, api_prefix=prefix)
    register_blockchain_routes(app, api_prefix=prefix)
    register_session_routes(app, api_prefix=prefix)
    register_database_routes(app, api_prefix=prefix)

    chip_spec = importlib.util.spec_from_file_location(
        "chip_in_app", OPERATIONS_DIR / "chip-in.py"
    )
    if chip_spec is None or chip_spec.loader is None:
        raise ImportError("Unable to load operations/chip-in.py")
    chip_mod = importlib.util.module_from_spec(chip_spec)
    chip_spec.loader.exec_module(chip_mod)
    chip_mod.register_chip_in_routes(app, api_prefix=prefix)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": resolve_operations_service_name(),
            "docker_dns": resolve_operations_docker_dns_name(),
            "network": resolve_operations_network_name(),
            "tor_only": resolve_operations_tor_only(),
            "operator_id_type": app.state.operator_id_type,
        }

    return app
