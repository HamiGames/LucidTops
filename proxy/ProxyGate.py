""" this is the script that provides the connection between the frontend and the backend via the Proxy container.
scope:
ensures secure connection between public access points (User, Node, Frontend, Rdp) and
limited access points (backend [MasterServer]). Public points use nginx reverse proxy;
internals resolve via ProxyDNS using hosts/ports from proxy.secrets.

operation-time values:
- does not pull hardware itself; consumes proxy.secrets written by Bootstrap/buildsecrets
  after pull_realworld_information (IP/MAC → PROXY_*_DNS, ports, selected/blocked sets, tokens).
- ProxyDNS upstreams: PROXY_BACKEND_DNS, PROXY_FRONTEND_DNS, PROXY_RDP_DNS, PROXY_NODE_DNS + ports.
- route policy CSVs: PROXY_SELECTED_CONTAINERS, PROXY_NONE_LINKING_CONTAINERS,
  PROXY_DIRECT_BLOCKED_TARGETS, PROXY_PUBLIC_ACCESS_POINTS.
- auth: PROXY_HMAC_KEY, PROXY_API_TOKEN, PROXY_NGINX_UPSTREAM_TOKEN, PROXY_GATE_HEADER_VALUE.

purpose:
1. establish Frontend → MasterServer (backend) via the Proxy container (never direct).
2. keep the connection secure and private.
3. support User → Frontend paths through the gate surface.
4. support Node → Frontend paths through the gate surface.
5. support Frontend → Rdp paths through the gate surface.

concerns:
- exposure of private data to the public.
- security, performance, reliability, compatibility, and scalability of gated routes.

ProxyGate interactions:
- frontend, User, Node, MasterUser, AdminUser, Rdp

ProxyGate inclusions:
- used directly by the Frontend container
- used between Frontend and Rdp / Node / MasterServer

ProxyGate limitations:
- no direct connection to backend [MasterServer], operations, blockchain, or PaySystems

restrictions:
- No hardcoded values, all values are created at time of operation (via pull → secrets).
- No placeholder values, all values are created at time of operation.
- at time of operation = when Bootstrap/buildsecrets ran the hardware pull that filled secrets.
- No sensitive data, all data is stored in the secrets file.

"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROXY_DIR = Path(__file__).resolve().parent
if str(_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(_PROXY_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _PROXY_DIR / file_name
    registry = f"lucid_proxy_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_buildsecrets = _load_local("buildsecrets")
get_proxy_secret = _buildsecrets.get_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
require_proxy_secret = _buildsecrets.require_proxy_secret


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "").replace("_", "")


def _csv_frozenset(secret_key: str) -> frozenset[str]:
    load_proxy_secrets()
    raw = require_proxy_secret(secret_key)
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def get_selected_containers() -> frozenset[str]:
    return _csv_frozenset("PROXY_SELECTED_CONTAINERS")


def get_none_linking_containers() -> frozenset[str]:
    return _csv_frozenset("PROXY_NONE_LINKING_CONTAINERS")


def get_direct_blocked_targets() -> frozenset[str]:
    return _csv_frozenset("PROXY_DIRECT_BLOCKED_TARGETS")


def get_public_access_points() -> frozenset[str]:
    return _csv_frozenset("PROXY_PUBLIC_ACCESS_POINTS")


# Lazy compatibility aliases — resolved from proxy.secrets at access time
class _SecretsFrozensetProxy:
    def __init__(self, loader) -> None:
        self._loader = loader

    def __iter__(self):
        return iter(self._loader())

    def __contains__(self, item: object) -> bool:
        return item in self._loader()

    def __len__(self) -> int:
        return len(self._loader())

    def __repr__(self) -> str:
        return repr(self._loader())


SELECTED_CONTAINERS = _SecretsFrozensetProxy(get_selected_containers)
NONE_LINKING_CONTAINERS = _SecretsFrozensetProxy(get_none_linking_containers)
DIRECT_BLOCKED_TARGETS = _SecretsFrozensetProxy(get_direct_blocked_targets)
PUBLIC_ACCESS_POINTS = _SecretsFrozensetProxy(get_public_access_points)


@dataclass(frozen=True)
class UpstreamTarget:
    name: str
    dns_host: str
    port: int
    base_path: str

    @property
    def base_url(self) -> str:
        path = self.base_path if self.base_path.startswith("/") else f"/{self.base_path}"
        root_path = require_proxy_secret("FRONTEND_BASE_PATH")
        if path == root_path or path == "/":
            return f"http://{self.dns_host}:{self.port}"
        return f"http://{self.dns_host}:{self.port}{path.rstrip('/')}"


class ProxyDNS:
    """Internal DockerDNS resolver used by ProxyGate for selected containers only."""

    def __init__(self) -> None:
        load_proxy_secrets()
        self._targets = self._build_targets()

    def _build_targets(self) -> dict[str, UpstreamTarget]:
        backend = UpstreamTarget(
            name="backend",
            dns_host=require_proxy_secret("PROXY_BACKEND_DNS"),
            port=int(require_proxy_secret("MASTER_SERVER_PORT")),
            base_path=require_proxy_secret("API_BASE_PATH"),
        )
        return {
            "backend": backend,
            "masterserver": backend,
            "frontend": UpstreamTarget(
                name="frontend",
                dns_host=require_proxy_secret("PROXY_FRONTEND_DNS"),
                port=int(require_proxy_secret("FRONTEND_PORT")),
                base_path=require_proxy_secret("FRONTEND_BASE_PATH"),
            ),
            "rdp": UpstreamTarget(
                name="rdp",
                dns_host=require_proxy_secret("PROXY_RDP_DNS"),
                port=int(require_proxy_secret("RDP_PORT")),
                base_path=require_proxy_secret("RDP_BASE_PATH"),
            ),
            "node": UpstreamTarget(
                name="node",
                dns_host=require_proxy_secret("PROXY_NODE_DNS"),
                port=int(require_proxy_secret("NODE_PORT")),
                base_path=require_proxy_secret("NODE_BASE_PATH"),
            ),
        }

    def refresh(self) -> None:
        load_proxy_secrets(reload=True)
        self._targets = self._build_targets()

    def resolve(self, container: str) -> UpstreamTarget | None:
        key = _normalize_name(container)
        if key in {_normalize_name(n) for n in get_none_linking_containers()}:
            return None
        return self._targets.get(key)

    def selected_map(self) -> dict[str, str]:
        return {name: target.base_url for name, target in self._targets.items()}


class ProxyGate:
    """Secure nginx-compatible gate: Frontend reaches MasterServer / Rdp / Node via ProxyDNS."""

    def __init__(self, dns: ProxyDNS | None = None) -> None:
        load_proxy_secrets()
        self.dns = dns or ProxyDNS()
        self.hmac_key = require_proxy_secret("PROXY_HMAC_KEY").encode("utf-8")
        self.api_token = require_proxy_secret("PROXY_API_TOKEN")
        self.upstream_token = require_proxy_secret("PROXY_NGINX_UPSTREAM_TOKEN")

    def is_selected(self, container: str) -> bool:
        return _normalize_name(container) in {
            _normalize_name(n) for n in get_selected_containers()
        }

    def is_none_linking(self, container: str) -> bool:
        return _normalize_name(container) in {
            _normalize_name(n) for n in get_none_linking_containers()
        }

    def is_public_access_point(self, source: str) -> bool:
        return _normalize_name(source) in {
            _normalize_name(n) for n in get_public_access_points()
        }

    def allows_route(self, *, source: str, target: str) -> bool:
        """Enforce ProxyGate inclusions and limitations."""
        src = _normalize_name(source)
        dst = _normalize_name(target)
        selected = {_normalize_name(n) for n in get_selected_containers()}
        public = {_normalize_name(n) for n in get_public_access_points()}
        blocked = {_normalize_name(n) for n in get_direct_blocked_targets()}

        if self.is_none_linking(dst):
            return False
        if dst in blocked and src != "frontend":
            # Direct public access to blocked/limited targets denied; Frontend may via gate.
            if dst in {_normalize_name(n) for n in ("backend", "masterserver")}:
                return False
            return False
        if dst in {_normalize_name(n) for n in ("backend", "masterserver")}:
            return src == "frontend" and (
                "backend" in selected or "masterserver" in selected
            )
        if dst == "rdp":
            return src == "frontend" and "rdp" in selected
        if dst == "node":
            return src in public and "node" in selected and src in {
                "frontend",
                "node",
                "masteruser",
                "adminuser",
            }
        if dst == "frontend":
            return src in public and "frontend" in selected
        return False

    def authorize_request(
        self,
        *,
        source: str,
        target: str,
        token: str | None = None,
        signature: str | None = None,
        body: bytes = b"",
    ) -> dict[str, Any]:
        if not self.allows_route(source=source, target=target):
            return {
                "allowed": False,
                "reason": "route_denied",
                "source": source,
                "target": target,
                "timestamp": utc_now(),
            }

        if self.api_token and token is not None and token != self.api_token:
            return {
                "allowed": False,
                "reason": "invalid_api_token",
                "source": source,
                "target": target,
                "timestamp": utc_now(),
            }

        if signature and self.hmac_key:
            expected = hmac.new(self.hmac_key, body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature.strip().lower()):
                return {
                    "allowed": False,
                    "reason": "invalid_hmac",
                    "source": source,
                    "target": target,
                    "timestamp": utc_now(),
                }

        upstream = self.dns.resolve(target)
        if upstream is None:
            return {
                "allowed": False,
                "reason": "upstream_unresolved",
                "source": source,
                "target": target,
                "timestamp": utc_now(),
            }

        return {
            "allowed": True,
            "reason": "ok",
            "source": source,
            "target": target,
            "upstream": upstream.base_url,
            "upstream_host": upstream.dns_host,
            "upstream_port": upstream.port,
            "timestamp": utc_now(),
        }

    def build_upstream_url(self, target: str, path: str = "") -> str | None:
        upstream = self.dns.resolve(target)
        if upstream is None:
            return None
        base = upstream.base_url.rstrip("/")
        normalized = path.strip().lstrip("/")
        if not normalized:
            return base
        return f"{base}/{normalized}"

    def gate_headers(self, *, source: str, target: str) -> dict[str, str]:
        return {
            "X-Lucid-Proxy-Gate": require_proxy_secret("PROXY_GATE_HEADER_VALUE"),
            "X-Lucid-Proxy-Source": source,
            "X-Lucid-Proxy-Target": target,
            "X-Lucid-Upstream-Token": self.upstream_token,
            "X-Lucid-Proxy-Timestamp": utc_now(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "selected_containers": sorted(get_selected_containers()),
            "none_linking_containers": sorted(get_none_linking_containers()),
            "direct_blocked_targets": sorted(get_direct_blocked_targets()),
            "dns_map": self.dns.selected_map(),
            "timestamp": utc_now(),
        }


_GATE: ProxyGate | None = None


def get_proxy_gate() -> ProxyGate:
    global _GATE
    if _GATE is None:
        _GATE = ProxyGate()
    return _GATE
