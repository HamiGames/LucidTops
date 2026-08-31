"""The link between the javascript frontend and the python backend via Tor *.onion routes.

All API routes resolve against the master server onion base URL when configured.
"""

from __future__ import annotations

from config import get_api_public_base_url, get_gui_public_base_url

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


def _normalize_source(source: str) -> str:
    normalized = source.strip().replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def resolve_api_route(source: str) -> str | None:
    path = FRONTEND_TO_API_ROUTE.get(_normalize_source(source))
    if path is None:
        return None
    return f"{get_api_public_base_url()}{path}"


def resolve_gui_route(source: str) -> str | None:
    path = FRONTEND_TO_GUI_ROUTE.get(_normalize_source(source))
    if path is None:
        return None
    return f"{get_gui_public_base_url()}{path}"


def resolve_web_page_link(source: str) -> dict[str, str | None]:
    normalized = _normalize_source(source)
    return {
        "source": normalized,
        "api_route": resolve_api_route(normalized),
        "gui_route": resolve_gui_route(normalized),
        "network": "tor",
    }


def validate_web_page_link(source: str) -> bool:
    normalized = _normalize_source(source)
    return normalized in FRONTEND_TO_API_ROUTE or normalized in FRONTEND_TO_GUI_ROUTE
