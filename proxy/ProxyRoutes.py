""" this script builds the FastAPI routing system for the Proxy container.
includes:
- ProxyGate for public Frontend → backend / rdp / node forwards
- internal DockerDNS routes limited to ProxyGate-selected containers
- clearnet payment-result path via Clearnet-package (SOCKS5 from secrets)
- bind/title/prefix/timeouts from proxy.secrets created by hardware pull at operation

purpose:
1. gateway for public access to internal containers via ProxyGate
2. gateway for internal containers via DockerDNS under gate policy
3. maintain Proxy protocols for internal and public use
4. increase security and limit external access to internal containers

concerns:
1. security of the internal containers and public use
2. security of the DockerDNS surface
3. connection compatibility across containers (DockerDNS + FastAPI)

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
from fastapi.responses import JSONResponse

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
_ProxyGate = _load_local("ProxyGate")
get_proxy_secret = _buildsecrets.get_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
require_proxy_secret = _buildsecrets.require_proxy_secret
get_none_linking_containers = _ProxyGate.get_none_linking_containers
get_selected_containers = _ProxyGate.get_selected_containers
get_proxy_gate = _ProxyGate.get_proxy_gate
NONE_LINKING_CONTAINERS = _ProxyGate.NONE_LINKING_CONTAINERS
SELECTED_CONTAINERS = _ProxyGate.SELECTED_CONTAINERS

PROXY_DIR = _PROXY_DIR


def _load_clearnet_package() -> Any:
    return _load_local("clearnet_package", "Clearnet-package.py")


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
        return {
            "selected": gate.dns.selected_map(),
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

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            not in {
                "host",
                "content-length",
                "x-lucid-proxy-token",
                "x-lucid-hmac-sha256",
            }
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
        """Public Frontend → MasterServer via ProxyGate (never direct)."""
        return await _forward(
            request=request,
            source="frontend",
            target="backend",
            upstream_path=path,
            x_lucid_proxy_token=x_lucid_proxy_token,
            x_lucid_hmac_sha256=x_lucid_hmac_sha256,
        )

    @app.api_route(
        f"{api_prefix}/frontend/rdp/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def frontend_to_rdp(
        path: str,
        request: Request,
        x_lucid_proxy_token: str | None = Header(default=None),
        x_lucid_hmac_sha256: str | None = Header(default=None),
    ) -> Response:
        return await _forward(
            request=request,
            source="frontend",
            target="rdp",
            upstream_path=path,
            x_lucid_proxy_token=x_lucid_proxy_token,
            x_lucid_hmac_sha256=x_lucid_hmac_sha256,
        )

    @app.api_route(
        f"{api_prefix}/frontend/node/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def frontend_to_node(
        path: str,
        request: Request,
        x_lucid_proxy_token: str | None = Header(default=None),
        x_lucid_hmac_sha256: str | None = Header(default=None),
    ) -> Response:
        return await _forward(
            request=request,
            source="frontend",
            target="node",
            upstream_path=path,
            x_lucid_proxy_token=x_lucid_proxy_token,
            x_lucid_hmac_sha256=x_lucid_hmac_sha256,
        )

    @app.api_route(
        f"{api_prefix}/internal/{{target}}/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def internal_dockerdns(
        target: str,
        path: str,
        request: Request,
        x_lucid_proxy_token: str | None = Header(default=None),
        x_lucid_hmac_sha256: str | None = Header(default=None),
        x_lucid_proxy_source: str | None = Header(default=None),
    ) -> Response:
        """DockerDNS internal routing limited to ProxyGate-selected containers."""
        source = x_lucid_proxy_source or require_proxy_secret(
            "PROXY_DEFAULT_INTERNAL_SOURCE"
        )
        normalized = target.strip().lower()
        none_linking = get_none_linking_containers()
        selected = get_selected_containers()
        if normalized in none_linking:
            raise HTTPException(
                status_code=403,
                detail={
                    "allowed": False,
                    "reason": "none_linking_or_blocked",
                    "target": normalized,
                },
            )
        if normalized not in selected and normalized != "masterserver":
            raise HTTPException(
                status_code=404,
                detail={"allowed": False, "reason": "unknown_target", "target": normalized},
            )
        return await _forward(
            request=request,
            source=source,
            target=normalized,
            upstream_path=path,
            x_lucid_proxy_token=x_lucid_proxy_token,
            x_lucid_hmac_sha256=x_lucid_hmac_sha256,
        )

    @app.post(f"{api_prefix}/clearnet/payment-result")
    async def clearnet_payment_result(
        request: Request,
        x_lucid_hmac_sha256: str | None = Header(default=None),
    ) -> JSONResponse:
        """
        Accept payment payloads from PaySystems; egress via Clearnet-package.
        Only valid/invalid results are returned toward MasterServer.
        """
        clearnet = _load_clearnet_package()
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="payment payload must be an object")
        result = clearnet.request_clearnet_payment(
            payment_payload=payload,
            signature=x_lucid_hmac_sha256,
        )
        return JSONResponse(result)

    @app.get(f"{api_prefix}/gate/authorize")
    async def authorize_probe(
        source: str,
        target: str,
        x_lucid_proxy_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return gate.authorize_request(
            source=source,
            target=target,
            token=x_lucid_proxy_token,
        )

    return app


app = create_proxy_app()
