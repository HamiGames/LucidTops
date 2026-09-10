"""FastAPI middleware enforcing Tor-only access for the master server API.

Applies LucidTops Tor connection protocols (connection.py) and javascript frontend
linkage (WebPageLink.py) for all API traffic over *.onion hidden services.
includes:
- the backend support required for a self hosted website on the Tor network (@*.onion)
- the backend support required for a self hosted website on the Clearnet network (https://*)

operational requirements:
- uses nginx reverse proxy system
- uses DockerDNS for network communication
- uses Tor Hidden Service and Docker Network for network communications as a fallback
- uses MongoDB 7.0.0 or higher for database storage
- requires registration with the MasterServer (uvicorn server and FastAPI system) to be operational
- stabalizes connection to the MasterServer (uvicorn server and FastAPI system)
- ensures the connection is secure and encrypted
- uses (mnt/myssd/LucidTops/secrets/backend.secrets) for authentication and encryption requirements


clearnet requirements:
- HMAC-SHA256 for authentication, to enter the clearnet connection
- EMV 3D Secure for payment processing.

"""

from __future__ import annotations

from typing import Any, Callable

from config import (
    API_PREFIX,
    FRONTEND_ONION,
    GUI_PREFIX,
    MASTER_SERVER_TOR_ONLY,
    format_tor_onion_service,
    get_config_value,
    get_config_value_optional,
    get_local_tor_forward_hosts,
    get_tor_api_service,
    get_tor_gui_service,
    resolve_master_server_onion,
    utc_now,
)
from connection import (
    normalize_onion_address,
    resolve_connection_network,
    resolve_connection_protocol,
    resolve_torrent_layer_protocol,
    resolve_transport_protocol,
    validate_onion_address,
)
from WebPageLink import (
    frontend_link_for_api_route,
    resolve_api_path,
    resolve_gui_path,
    resolve_tor_api_route,
    resolve_tor_gui_route,
    validate_web_page_link,
)

try:
    from fastapi import Request, Response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response as StarletteResponse
except ImportError:  # pragma: no cover
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    Request = Response = JSONResponse = StarletteResponse = object  # type: ignore[misc, assignment]

TOR_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        f"{API_PREFIX}/connection/tor-config",
        f"{API_PREFIX}/client-request/tor-config",
    }
)

TOR_EXEMPT_PREFIXES: tuple[str, ...] = (
    GUI_PREFIX,
    "/docs",
    "/openapi.json",
    "/redoc",
)

LUCID_JAVASCRIPT_HEADERS: tuple[str, ...] = (
    "x-lucid-javascript",
    "x-lucid-source",
    "x-javascript-source",
)

LUCID_CORS_ALLOW_HEADERS: str = (
    "Content-Type, Authorization, X-API-Key, X-IDToken, "
    "X-Lucid-Source, X-Lucid-JavaScript, X-Javascript-Source, "
    "X-Connection-Type, X-Onion-Address, "
    "X-Lucid-Proxy-Gate, X-Lucid-Proxy-Source, X-Lucid-Proxy-Target, "
    "X-Lucid-Upstream-Token, X-Lucid-Proxy-Token, X-Lucid-Hmac-Sha256"
)

LUCID_CORS_ALLOW_METHODS: str = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


def _cors_max_age() -> str:
    return get_config_value("CORS_MAX_AGE")


def _frontend_source_prefix() -> str:
    return get_config_value("FRONTEND_SOURCE_PREFIX").strip().strip("/")


def _hostname_from_host(host: str) -> str:
    return host.split(":")[0].strip().lower()


def _host_is_tor(host: str) -> bool:
    return _hostname_from_host(host).endswith(".onion")


def _host_is_local_tor_forward(host: str) -> bool:
    try:
        return _hostname_from_host(host) in get_local_tor_forward_hosts()
    except RuntimeError:
        return False


def _proxy_gate_authorized(request: Any) -> bool:
    """Accept traffic forwarded by ProxyGate using secrets created at operation time."""
    expected_gate = get_config_value_optional("PROXY_GATE_HEADER_VALUE")
    if not expected_gate:
        return False
    gate = request.headers.get("x-lucid-proxy-gate", "").strip()
    if gate != expected_gate:
        return False
    expected_token = get_config_value_optional("PROXY_NGINX_UPSTREAM_TOKEN")
    if expected_token:
        upstream = request.headers.get("x-lucid-upstream-token", "").strip()
        if upstream != expected_token:
            return False
    return True


def _origin_is_tor(origin: str) -> bool:
    cleaned = origin.strip().lower()
    for prefix in ("http://", "https://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    hostname = cleaned.split("/")[0].split(":")[0]
    return hostname.endswith(".onion")


def _resolve_request_host(request: Any) -> str:
    for header in ("host", "x-forwarded-host", "x-original-host"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return ""


def _resolve_request_onion(request: Any) -> str | None:
    host = _resolve_request_host(request)
    if not host:
        return None
    hostname = _hostname_from_host(host)
    if validate_onion_address(hostname):
        return normalize_onion_address(hostname)
    return None


def _path_is_exempt(path: str) -> bool:
    if path in TOR_EXEMPT_PATHS:
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in TOR_EXEMPT_PREFIXES)


def _normalize_javascript_source(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _resolve_javascript_source(request: Any) -> str | None:
    for header in LUCID_JAVASCRIPT_HEADERS:
        value = request.headers.get(header, "").strip()
        if value:
            return _normalize_javascript_source(value)
    return None


def _frontend_link_for_javascript(javascript: str) -> dict[str, str | None]:
    normalized = _normalize_javascript_source(javascript)
    return {
        "frontend": f"{_frontend_source_prefix()}/{normalized}",
        "javascript": normalized,
        "api_path": resolve_api_path(normalized),
        "gui_path": resolve_gui_path(normalized),
        "tor_api_route": resolve_tor_api_route(normalized),
        "tor_gui_route": resolve_tor_gui_route(normalized),
    }


def _allowed_cors_origins() -> set[str]:
    origins: set[str] = set()
    for onion in (resolve_master_server_onion(), FRONTEND_ONION):
        if onion and validate_onion_address(onion):
            normalized = normalize_onion_address(onion)
            origins.add(f"http://{normalized}")
            origins.add(f"https://{normalized}")
    return origins


def _resolve_cors_origin(request: Any) -> str | None:
    origin = request.headers.get("origin", "").strip()
    if not origin or not _origin_is_tor(origin):
        return None

    if origin in _allowed_cors_origins():
        return origin

    cleaned = origin.lower()
    for prefix in ("http://", "https://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    if cleaned.split("/")[0].split(":")[0].endswith(".onion"):
        return origin
    return None


def _build_tor_protocol_headers(*, master_onion: str | None) -> dict[str, str]:
    headers = {
        "X-Lucid-Network": resolve_connection_network(),
        "X-Lucid-Tor-Only": "true",
        "X-Lucid-Protocol": resolve_connection_protocol(),
        "X-Lucid-Transport": resolve_transport_protocol(),
        "X-Lucid-Torrent-Layer": resolve_torrent_layer_protocol(),
        "X-Lucid-Tor-Api-Service": get_tor_api_service(),
        "X-Lucid-Tor-Gui-Service": get_tor_gui_service(),
    }
    if master_onion:
        headers["X-Lucid-Master-Onion"] = master_onion
    return headers


def _build_cors_headers(request: Any) -> dict[str, str]:
    origin = _resolve_cors_origin(request)
    if not origin:
        return {}

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": LUCID_CORS_ALLOW_METHODS,
        "Access-Control-Allow-Headers": LUCID_CORS_ALLOW_HEADERS,
        "Access-Control-Expose-Headers": (
            "X-Lucid-Network, X-Lucid-Tor-Only, X-Lucid-Protocol, "
            "X-Lucid-Transport, X-Lucid-Master-Onion, X-Lucid-Javascript, "
            "X-Lucid-Frontend, X-Lucid-Tor-Api-Service, X-Lucid-Tor-Gui-Service"
        ),
        "Access-Control-Max-Age": _cors_max_age(),
        "Vary": "Origin",
    }


def _attach_response_headers(response: Any, headers: dict[str, str]) -> Any:
    for key, value in headers.items():
        if value:
            response.headers[key] = value
    return response


def _tor_denied_response(
    *,
    detail: str,
    master_onion: str | None,
    frontend_onion: str | None = None,
    path: str = "",
) -> Any:
    link = frontend_link_for_api_route(path) if path else {}
    body: dict[str, Any] = {
        "detail": detail,
        "service": "master_server",
        "network": resolve_connection_network(),
        "tor_only": True,
        "protocol": resolve_connection_protocol(),
        "transport": resolve_transport_protocol(),
        "torrent_layer": resolve_torrent_layer_protocol(),
        "master_server_onion": master_onion or "",
        "frontend_onion": frontend_onion or FRONTEND_ONION or "",
        "tor_api_service": get_tor_api_service(),
        "tor_gui_service": get_tor_gui_service(),
        "timestamp": utc_now(),
    }
    if link.get("javascript"):
        body["javascript"] = link["javascript"]
        body["frontend"] = link["frontend"]
    api_segment = link.get("api_path")
    if master_onion and isinstance(api_segment, str) and api_segment:
        api_path = (
            api_segment
            if api_segment.startswith(API_PREFIX)
            else f"{API_PREFIX}{api_segment if api_segment.startswith('/') else f'/{api_segment}'}"
        )
        body["tor_service"] = format_tor_onion_service(master_onion, api_path)

    response = JSONResponse(status_code=403, content=body)  # pyright: ignore[reportCallIssue]
    return _attach_response_headers(
        response,
        _build_tor_protocol_headers(master_onion=master_onion),
    )


def _validate_javascript_source_header(request: Any) -> str | None:
    """Return error detail when a javascript source header is present but not permitted."""
    javascript = _resolve_javascript_source(request)
    if not javascript:
        return None
    if validate_web_page_link(javascript):
        return None
    return f"javascript source not permitted: {javascript}"


def register_tor_middleware(app: object) -> None:
    """Register Tor-only middleware for API systems and javascript frontend connections."""
    if not MASTER_SERVER_TOR_ONLY or BaseHTTPMiddleware is object or JSONResponse is object:
        return

    expected_onion = resolve_master_server_onion()
    frontend_onion = FRONTEND_ONION if validate_onion_address(FRONTEND_ONION) else None

    class TorOnlyMiddleware(BaseHTTPMiddleware):  # pyright: ignore[reportGeneralTypeIssues]
        async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:  # pyright: ignore[reportInvalidTypeForm]
            path = request.url.path
            master_onion = expected_onion or _resolve_request_onion(request)
            protocol_headers = _build_tor_protocol_headers(master_onion=master_onion)
            cors_headers = _build_cors_headers(request)

            if request.method == "OPTIONS":
                response = StarletteResponse(status_code=204)  # pyright: ignore[reportCallIssue]
                _attach_response_headers(response, protocol_headers)
                _attach_response_headers(response, cors_headers)
                return response

            if _path_is_exempt(path):
                response = await call_next(request)
                _attach_response_headers(response, protocol_headers)
                _attach_response_headers(response, cors_headers)
                return response

            host = _resolve_request_host(request)
            request_onion = _resolve_request_onion(request)

            js_error = _validate_javascript_source_header(request)
            if js_error:
                denied = _tor_denied_response(
                    detail=js_error,
                    master_onion=master_onion,
                    frontend_onion=frontend_onion,
                    path=path,
                )
                _attach_response_headers(denied, cors_headers)
                return denied

            if _host_is_tor(host):
                if master_onion and request_onion and request_onion != master_onion:
                    denied = _tor_denied_response(
                        detail="Host *.onion does not match master server hidden service",
                        master_onion=master_onion,
                        frontend_onion=frontend_onion,
                        path=path,
                    )
                    _attach_response_headers(denied, cors_headers)
                    return denied

                response = await call_next(request)
                _attach_response_headers(response, protocol_headers)
                _attach_response_headers(response, cors_headers)
                javascript = _resolve_javascript_source(request)
                if javascript and validate_web_page_link(javascript):
                    link = _frontend_link_for_javascript(javascript)
                    response.headers["X-Lucid-Javascript"] = javascript
                    if link.get("frontend"):
                        response.headers["X-Lucid-Frontend"] = str(link["frontend"])
                return response

            if _proxy_gate_authorized(request) or _host_is_local_tor_forward(host):
                response = await call_next(request)
                _attach_response_headers(response, protocol_headers)
                _attach_response_headers(response, cors_headers)
                response.headers["X-Lucid-Proxy-Mediated"] = "true"
                return response

            denied = _tor_denied_response(
                detail="Master server API is Tor-only; connect via *.onion hidden service",
                master_onion=master_onion,
                frontend_onion=frontend_onion,
                path=path,
            )
            _attach_response_headers(denied, cors_headers)
            return denied

    app.add_middleware(TorOnlyMiddleware)  # type: ignore[attr-defined]
