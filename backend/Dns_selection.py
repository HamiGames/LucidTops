""" this script defines the Dns-selected containers for the Backend container.
purpose:
1. to define the limitations of the Dns-selected containers for use by the Backend container.

dns-selected containers:
- operations
- LucidTops_SessionsDB
- LucidTopsNodeDB
- LucidTopsUserDB
- LucidTopsLedgerDB
- LucidTopsPaySystemsDB
- PaySystems

none-direct containers:
- blockchain
- frontend
- user
- Node, MasterUser, AdminUser
- sessions
- Proxy
- Rdp

proxy interactions:
- frontend

ProxyGate interactions:
- between frontend and backend

ProxyGate limitations:
- does not allow for direct connection to the backend container [MasterServer]
- does not allow for direct connection to the operations container
- does not allow for direct connection to the blockchain container
- does not allow for direct connection to the PaySystems container
"""

from __future__ import annotations

from typing import Any

from config import get_config_list, get_config_value


def dns_selected_containers() -> frozenset[str]:
    return get_config_list("DNS_SELECTED_CONTAINERS")


def dns_none_direct_containers() -> frozenset[str]:
    return get_config_list("DNS_NONE_DIRECT_CONTAINERS")


def dns_proxy_interactions() -> frozenset[str]:
    return get_config_list("DNS_PROXY_INTERACTIONS")


def dns_proxygate_interactions() -> frozenset[str]:
    return get_config_list("DNS_PROXYGATE_INTERACTIONS")


def dns_proxygate_direct_blocked() -> frozenset[str]:
    return get_config_list("DNS_PROXYGATE_DIRECT_BLOCKED")


def dns_backend_service_name() -> str:
    return get_config_value("DNS_BACKEND_SERVICE_NAME")


def _normalize(name: str) -> str:
    return name.strip().lower()


def is_dns_selected(container: str) -> bool:
    key = _normalize(container)
    return key in {_normalize(item) for item in dns_selected_containers()}


def is_none_direct(container: str) -> bool:
    key = _normalize(container)
    return key in {_normalize(item) for item in dns_none_direct_containers()}


def allows_backend_dns_link(container: str) -> bool:
    """Backend may open DockerDNS links only to dns-selected, non-blocked containers."""
    if is_none_direct(container):
        return False
    return is_dns_selected(container)


def allows_proxygate_direct(source: str, target: str) -> bool:
    """ProxyGate direct access rules driven by operation-time lists."""
    src = _normalize(source)
    dst = _normalize(target)
    interactions = {_normalize(item) for item in dns_proxygate_interactions()}
    blocked = {_normalize(item) for item in dns_proxygate_direct_blocked()}
    if dst in blocked:
        return False
    pair = f"{src}->{dst}"
    if pair in interactions:
        return True
    return src in {_normalize(item) for item in dns_proxy_interactions()} and allows_backend_dns_link(
        target
    )


def dns_selection_status() -> dict[str, Any]:
    return {
        "backend_service": dns_backend_service_name(),
        "dns_selected": sorted(dns_selected_containers()),
        "none_direct": sorted(dns_none_direct_containers()),
        "proxy_interactions": sorted(dns_proxy_interactions()),
        "proxygate_interactions": sorted(dns_proxygate_interactions()),
        "proxygate_direct_blocked": sorted(dns_proxygate_direct_blocked()),
    }
