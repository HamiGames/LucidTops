"""LucidTops sessions FastAPI application (standalone container entry).

RULES:
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

SESSIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SESSIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, SESSIONS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def bootstrap_sessions_runtime() -> dict[str, Any]:
    """Pull hardware, bind env, write sessions.secrets before route imports resolve values."""
    from sessions.sessions_pull_information import pull_sessions_hardware
    from sessions.Config_sessions import write_session_secrets

    info = pull_sessions_hardware(bind_environ=True, overwrite=False)
    write_session_secrets(force=False, pull=info)
    return info


def create_app() -> Any:
    bootstrap_sessions_runtime()

    try:
        from fastapi import FastAPI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("fastapi is required for the sessions container") from exc

    from sessions.sessionID import (
        load_sessions_secrets,
        resolve_session_api_prefix,
        resolve_session_health_path,
        resolve_sessions_docker_dns_name,
        resolve_sessions_network_name,
        resolve_sessions_service_name,
        resolve_session_secret,
    )
    from sessions.SessionRoutes import register_session_routes
    from sessions._common import get_mongo_client

    load_sessions_secrets(reload=True)

    client = get_mongo_client()
    if client is None:
        raise RuntimeError(
            "LucidTops_SessionsDB unavailable — MongoDB must be reachable at time of operation"
        )
    client.close()

    app = FastAPI(
        title=resolve_sessions_service_name(),
        docs_url=None,
        redoc_url=None,
    )
    app.state.sessions_docker_dns = resolve_sessions_docker_dns_name()
    app.state.sessions_network = resolve_sessions_network_name()
    app.state.hardware_primary_ip = resolve_session_secret("HARDWARE_PRIMARY_IP")
    app.state.hardware_primary_mac = resolve_session_secret("HARDWARE_PRIMARY_MAC")

    prefix = resolve_session_api_prefix()
    register_session_routes(app, api_prefix=prefix)

    health = resolve_session_health_path()

    @app.get(health)
    @app.get("/health")
    def health_check() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": resolve_sessions_service_name(),
            "docker_dns": resolve_sessions_docker_dns_name(),
            "network": resolve_sessions_network_name(),
            "hardware_primary_ip": app.state.hardware_primary_ip,
            "hardware_primary_mac": app.state.hardware_primary_mac,
        }

    return app
