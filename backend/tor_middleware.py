"""FastAPI middleware enforcing Tor-only access for the master server API."""

from __future__ import annotations

from typing import Callable

from config import MASTER_SERVER_TOR_ONLY, resolve_master_server_onion

try:
    from fastapi import Request, Response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
except ImportError:  # pragma: no cover
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    Request = Response = JSONResponse = object  # type: ignore[misc, assignment]

TOR_HEALTH_PATHS = frozenset({"/health", "/api/v1/connection/tor-config"})


def _host_is_tor(host: str) -> bool:
    hostname = host.split(":")[0].lower()
    return hostname.endswith(".onion")


def _host_is_local_tor_forward(host: str) -> bool:
    hostname = host.split(":")[0].lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def register_tor_middleware(app: object) -> None:
    """Reject non-Tor API access when MASTER_SERVER_TOR_ONLY is enabled."""
    if not MASTER_SERVER_TOR_ONLY or BaseHTTPMiddleware is object:
        return

    expected_onion = resolve_master_server_onion()

    class TorOnlyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            path = request.url.path
            if path in TOR_HEALTH_PATHS:
                return await call_next(request)

            host = request.headers.get("host", "")
            if _host_is_tor(host):
                if expected_onion and host.split(":")[0].lower() != expected_onion:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Host *.onion does not match master server hidden service",
                            "expected_onion": expected_onion,
                        },
                    )
                return await call_next(request)

            if _host_is_local_tor_forward(host):
                # Tor HiddenServicePort forwards to 127.0.0.1 inside the container.
                return await call_next(request)

            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Master server API is Tor-only; connect via *.onion hidden service",
                    "master_server_onion": expected_onion,
                },
            )

    app.add_middleware(TorOnlyMiddleware)  # type: ignore[attr-defined]
