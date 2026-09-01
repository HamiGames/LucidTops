"""The link between the javascript frontend and the python backend via Tor *.onion routes.

All API routes resolve against the master server onion base URL when configured.
"""

from __future__ import annotations

from config import API_PREFIX, GUI_PREFIX, format_tor_onion_service, resolve_master_server_onion

FRONTEND_TO_API_ROUTE: dict[str, str] = {
    "register.js": "/register",
    "login.js": "/login",
    "logout.js": "/logout",
    "node-registration.js": "/node-registration",
    "tier-select.js": "/tier-select",
    "connect-handshake.js": "/connect-handshake",
    "find-peer.js": "/user-session-find",
    "find-Peer.js": "/user-session-find",
    "home_page.js": "/user-connect",
    "dashboard.js": "/user-connect",
    "settings.js": "/user-control",
    "LucidLedger.js": "/user-LucidLedger-read",
    "LucidMarket.js": "/billing-information",
    "RemoteView.js": "/session-connect",
}

FRONTEND_TO_GUI_ROUTE: dict[str, str] = {
    "register.js": "/register",
    "login.js": "/login",
    "logout.js": "/logout",
    "home_page.js": "/home",
    "dashboard.js": "/home",
    "settings.js": "/settings",
    "find-peer.js": "/find-peer",
    "LucidLedger.js": "/LucidLedger",
    "LucidMarket.js": "/LucidMarket",
    "connect-handshake.js": "/connect-handshake",
    "node-registration.js": "/node-registration",
    "tier-select.js": "/tier-select",
    "RemoteView.js": "/home",
}

API_ROUTE_TO_FRONTEND: dict[str, str] = {
    api_path: javascript for javascript, api_path in FRONTEND_TO_API_ROUTE.items()
}

API_ROUTE_TO_FRONTEND.update(
    {
        "/session-create": "find-peer.js",
        "/session-find": "find-peer.js",
        "/session-connect": "connect-handshake.js",
        "/session-disconnect": "RemoteView.js",
        "/session-end": "RemoteView.js",
        "/session-record": "RemoteView.js",
        "/session-transfer": "RemoteView.js",
        "/session-control": "settings.js",
        "/user-session-create": "find-peer.js",
        "/user-session-find": "find-peer.js",
        "/user-session-connect": "connect-handshake.js",
        "/user-session-disconnect": "RemoteView.js",
        "/user-session-end": "RemoteView.js",
        "/user-session-record": "RemoteView.js",
        "/user-session-report": "RemoteView.js",
        "/user-session-transfer": "RemoteView.js",
        "/user-session-control": "settings.js",
        "/user-create": "register.js",
        "/user-find": "login.js",
        "/user-connect": "home_page.js",
        "/user-disconnect": "login.js",
        "/user-end": "login.js",
        "/user-record": "home_page.js",
        "/user-report": "home_page.js",
        "/user-transfer": "home_page.js",
        "/user-control": "settings.js",
        "/user-LucidLedger-read": "LucidLedger.js",
        "/LucidLedger": "LucidLedger.js",
        "/LucidMarket": "LucidMarket.js",
        "/home": "home_page.js",
        "/find-peer": "find-peer.js",
        "/settings": "settings.js",
    }
)


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _frontend_path(javascript: str) -> str:
    return f"frontend/{_normalize_source(javascript)}"


def api_path_for_route(route: str) -> str:
    """Return API path segment for an operations route (e.g. /session-find)."""
    route_path = route if route.startswith("/") else f"/{route}"
    mapped = API_ROUTE_TO_FRONTEND.get(route_path)
    if mapped and mapped in FRONTEND_TO_API_ROUTE:
        return FRONTEND_TO_API_ROUTE[mapped]
    return route_path


def gui_path_for_javascript(javascript: str) -> str | None:
    return FRONTEND_TO_GUI_ROUTE.get(_normalize_source(javascript))


def frontend_source_for_api_route(route: str) -> str | None:
    route_path = route if route.startswith("/") else f"/{route}"
    javascript = API_ROUTE_TO_FRONTEND.get(route_path)
    if javascript is None:
        return None
    return _frontend_path(javascript)


def javascript_for_api_route(route: str) -> str | None:
    route_path = route if route.startswith("/") else f"/{route}"
    return API_ROUTE_TO_FRONTEND.get(route_path)


def frontend_link_for_api_route(route: str) -> dict[str, str | None]:
    """Resolve javascript frontend source and route paths for an API route."""
    route_path = route if route.startswith("/") else f"/{route}"
    javascript = API_ROUTE_TO_FRONTEND.get(route_path)
    if javascript is None:
        return {
            "frontend": None,
            "javascript": None,
            "api_path": api_path_for_route(route_path),
            "gui_path": None,
        }
    api_segment = FRONTEND_TO_API_ROUTE.get(javascript, route_path)
    return {
        "frontend": _frontend_path(javascript),
        "javascript": javascript,
        "api_path": api_segment,
        "gui_path": FRONTEND_TO_GUI_ROUTE.get(javascript),
    }


def resolve_api_path(source: str) -> str | None:
    return FRONTEND_TO_API_ROUTE.get(_normalize_source(source))


def resolve_gui_path(source: str) -> str | None:
    return FRONTEND_TO_GUI_ROUTE.get(_normalize_source(source))


def _tor_service_path(api_path: str) -> str:
    return api_path if api_path.startswith(API_PREFIX) else f"{API_PREFIX}{api_path}"


def resolve_tor_api_route(source: str) -> str | None:
    """Tor *.onion service path for a javascript source (not clearnet)."""
    path = resolve_api_path(source)
    if path is None:
        return None
    onion = resolve_master_server_onion()
    if onion is None:
        return _tor_service_path(path)
    return format_tor_onion_service(onion, _tor_service_path(path))


def resolve_tor_gui_route(source: str) -> str | None:
    path = resolve_gui_path(source)
    if path is None:
        return None
    onion = resolve_master_server_onion()
    gui_path = path if path.startswith(GUI_PREFIX) else f"{GUI_PREFIX}{path}"
    if onion is None:
        return gui_path
    return format_tor_onion_service(onion, gui_path)


def resolve_api_route(source: str) -> str | None:
    return resolve_tor_api_route(source)


def resolve_gui_route(source: str) -> str | None:
    return resolve_tor_gui_route(source)


def resolve_web_page_link(source: str) -> dict[str, str | None]:
    normalized = _normalize_source(source)
    api_path = resolve_api_path(normalized)
    gui_path = resolve_gui_path(normalized)
    return {
        "source": normalized,
        "frontend": _frontend_path(normalized),
        "javascript": normalized,
        "api_path": api_path,
        "gui_path": gui_path,
        "tor_api_route": resolve_tor_api_route(normalized),
        "tor_gui_route": resolve_tor_gui_route(normalized),
        "api_route": resolve_tor_api_route(normalized),
        "gui_route": resolve_tor_gui_route(normalized),
        "network": "tor",
        "tor_only": "true",
    }


def validate_web_page_link(source: str) -> bool:
    normalized = _normalize_source(source)
    return normalized in FRONTEND_TO_API_ROUTE or normalized in FRONTEND_TO_GUI_ROUTE
