"""Main entry point for the LucidTops master server backend (uvicorn server and FastAPI system).
this is the the overal run program for the MasterServer (uvicorn server and FastAPI system) for the LucidTops system.
all contentent required to operate inside a Docker Network container, will be included in this file
- all links to the containers within the LucidTops system will be included in this file
- no API route will be Directly written in this file ( will call API routes from the other files)
- No direct MongoDB access will be made in this file ( will call MongoDB from the other files)
- No direct Tor Hidden Service access will be made in this file ( will call Tor Hidden Service from the other files)
- No direct Docker Network access will be made in this file ( will call Docker Network from the other files)
- No direct Clearnet access will be made in this file ( will call Clearnet from the other files)
- NO container content will be directly written in this file ( will call container content from the other files)
this file will include a command to start the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to stop the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to restart the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the status of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the logs of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the configuration of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the registration of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the connection status of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the connection configuration of the uvicorn server (master server) and the FastAPI system (master server)
this file will include a command to check the connection logs of the uvicorn server (master server) and the FastAPI system (master server)
All configuration requirements will be imported from a set of *.secrets files (server.secrets, mongodb.secrets, tor.secrets, docker.secrets, clearnet.secrets, frontend.secrets, backend.secrets, operations.secrets, paysystems.secrets)
All configuration data is pulled from outside the container (via the DockerfileDNS) and stored on the Host Machine (hardward using a configurable Path)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ClientHandler import register_client_handler_routes
from config import (
    API_PREFIX,
    GUI_PREFIX,
    MASTER_SERVER_BIND_HOST,
    MASTER_SERVER_PORT,
    MASTER_SERVER_TOR_ONLY,
    get_tor_api_service,
    get_tor_gui_service,
    get_master_server_tor_service,
    resolve_master_server_onion,
)
from ConnectionRoutes import register_connection_routes
from handshake import register_handshake_routes
from MasterServerRoutes import register_master_server_routes
from operations import register_operations_routes
from tor_middleware import register_tor_middleware

try:
    from fastapi import FastAPI
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fastapi is required to run the master server") from exc


def create_app() -> FastAPI:
    """Assemble the Tor-only master server FastAPI application."""
    onion = resolve_master_server_onion()
    tor_service = get_master_server_tor_service()

    servers = []
    if tor_service:
        servers.append({"url": tor_service, "description": "Tor hidden service (*.onion)"})

    app = FastAPI(
        title="LucidTops Master Server",
        version="1.0.0",
        description=(
            "Tor-only master server for LucidTops. All API and GUI routes are "
            "reachable exclusively via the *.onion hidden service."
        ),
        servers=servers,
    )

    register_tor_middleware(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "master_server",
            "network": "tor",
            "tor_only": str(MASTER_SERVER_TOR_ONLY).lower(),
            "master_server_onion": onion or "",
            "tor_api_service": get_tor_api_service(),
            "tor_gui_service": get_tor_gui_service(),
        }

    register_handshake_routes(app, api_prefix=API_PREFIX, gui_prefix=GUI_PREFIX)
    register_connection_routes(app, api_prefix=API_PREFIX)
    register_client_handler_routes(app, api_prefix=API_PREFIX)
    register_master_server_routes(app)
    register_operations_routes(app, api_prefix=API_PREFIX)
    return app


def run_server() -> None:
    """Run uvicorn bound to localhost; Tor hidden service forwards *.onion traffic."""
    import uvicorn

    app_path = os.environ.get("MASTER_SERVER_APP", "main:create_app")
    uvicorn.run(
        app_path,
        factory=True,
        host=MASTER_SERVER_BIND_HOST,
        port=MASTER_SERVER_PORT,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    run_server()
