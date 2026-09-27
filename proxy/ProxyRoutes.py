""" this script builds the FastAPI routing system for the Proxy container.
includes:
- one Frontend → MasterServer (backend) forward through ProxyGate
- nginx reverse proxy remains the container framework; this app is the uvicorn surface it forwards into
- bind/title/prefix/timeouts from proxy.secrets created by hardware pull at operation

purpose:
1. transport Frontend requests to MasterServer (the backend container)
2. support MasterServer hosting the frontend by forwarding those requests
3. carry MasterServer request paths, including a request that starts the RDP container
4. refuse routes to none-linking containers

selected containers:
- frontend (transport to backend only)
- MasterServer (backend)

none-linking (no route from this file):
- sessions
- operations
- blockchain
- node
- RDP
- PaySystems

only the backend links directly to the proxy.
login and registration checks stay on MasterServer.

restrictions:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- at time of operation = when pull → proxy.secrets was written (Bootstrap/buildsecrets).
- No sensitive data, all data is stored in the secrets file.

"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

_PROXY_DIR = Path(__file__).resolve().parent
if str(_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(_PROXY_DIR))

_MASTER_SERVER_TARGETS = frozenset({"backend", "masterserver"})


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
_ProxyGate = _load_local("ProxyGate")
load_proxy_secrets = _buildsecrets.load_proxy_secrets
require_proxy_secret = _buildsecrets.require_proxy_secret
get_none_linking_containers = _ProxyGate.get_none_linking_containers
get_selected_containers = _ProxyGate.get_selected_containers
get_proxy_gate = _ProxyGate.get_proxy_gate
NONE_LINKING_CONTAINERS = _ProxyGate.NONE_LINKING_CONTAINERS
SELECTED_CONTAINERS = _ProxyGate.SELECTED_CONTAINERS

PROXY_DIR = _PROXY_DIR


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _assert_frontend_to_masterserver(*, source: str, target: str) -> None:
    """Allow only Frontend → MasterServer. None-linking targets stay closed."""
    src = _normalize_name(source)
    dst = _normalize_name(target)
    if src == "frontend" and dst in _MASTER_SERVER_TARGETS:
        return
    none_linking = {_normalize_name(item) for item in get_none_linking_containers()}
    if dst in none_linking:
        raise HTTPException(
            status_code=403,
            detail={
                "allowed": False,
                "reason": "none_linking_or_blocked",
                "source": src,
                "target": dst,
            },
        )
    raise HTTPException(
        status_code=403,
        detail={
            "allowed": False,
            "reason": "route_denied",
            "source": src,
            "target": dst,
        },
    )


def create_proxy_app() -> FastAPI:
    load_proxy_secrets()
    api_prefix = require_proxy_secret("PROXY_API_PREFIX")
    app = FastAPI(
        title=require_proxy_secret("PROXY_APP_TITLE"),
        description=require_proxy_secret("PROXY_APP_DESCRIPTION"),
        version=require_proxy_secret("PROXY_APP_VERSION"),
    )
    gate = get_proxy_gate()

    @app.on_event("startup")
    async def _startup() -> None:
        load_proxy_secrets(reload=True)
        gate.dns.refresh()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "selected": sorted(get_selected_containers()),
            "none_linking": sorted(get_none_linking_containers()),
            "gate": gate.status(),
        }

    @app.get(f"{api_prefix}/status")
    async def proxy_status() -> dict[str, Any]:
        return gate.status()

    @app.get(f"{api_prefix}/dns")
    async def proxy_dns_map() -> dict[str, Any]:
        selected = {
            name: url
            for name, url in gate.dns.selected_map().items()
            if _normalize_name(name) in _MASTER_SERVER_TARGETS
        }
        return {
            "selected": selected,
            "none_linking": sorted(get_none_linking_containers()),
        }

    async def _forward(
        *,
        request: Request,
        source: str,
        target: str,
        upstream_path: str,
        x_lucid_proxy_token: str | None,
        x_lucid_hmac_sha256: str | None,
    ) -> Response:
        _assert_frontend_to_masterserver(source=source, target=target)
        body = await request.body()
        decision = gate.authorize_request(
            source=source,
            target=target,
            token=x_lucid_proxy_token,
            signature=x_lucid_hmac_sha256,
            body=body,
        )
        if not decision.get("allowed"):
            raise HTTPException(status_code=403, detail=decision)

        upstream_url = gate.build_upstream_url(target, upstream_path)
        if not upstream_url:
            raise HTTPException(status_code=502, detail="upstream_unresolved")

        dropped = {
            "host",
            "content-length",
            "x-lucid-proxy-token",
            "x-lucid-hmac-sha256",
        }
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in dropped
        }
        headers.update(gate.gate_headers(source=source, target=target))

        timeout = httpx.Timeout(
            float(require_proxy_secret("PROXY_HTTP_TIMEOUT")),
            connect=float(require_proxy_secret("PROXY_HTTP_CONNECT_TIMEOUT")),
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                content=body,
                headers=headers,
                params=request.query_params,
            )

        excluded = {"content-encoding", "transfer-encoding", "connection"}
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in excluded
        }
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=upstream.headers.get("content-type"),
        )

    @app.api_route(
        f"{api_prefix}/frontend/backend/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def frontend_to_backend(
        path: str,
        request: Request,
        x_lucid_proxy_token: str | None = Header(default=None),
        x_lucid_hmac_sha256: str | None = Header(default=None),
    ) -> Response:
        """Frontend → MasterServer. Page hosting and RDP start are paths on this forward."""
        return await _forward(
            request=request,
            source="frontend",
            target="backend",
            upstream_path=path,
            x_lucid_proxy_token=x_lucid_proxy_token,
            x_lucid_hmac_sha256=x_lucid_hmac_sha256,
        )

    @app.get(f"{api_prefix}/gate/authorize")
    async def authorize_probe(
        source: str,
        target: str,
        x_lucid_proxy_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _assert_frontend_to_masterserver(source=source, target=target)
        return gate.authorize_request(
            source=source,
            target=target,
            token=x_lucid_proxy_token,
        )

    return app


app = create_proxy_app()
