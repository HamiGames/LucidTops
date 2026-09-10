"""Connect blockchain FastAPI routes for cross-container communication
(NodeUser, MasterServer, AdminUser, MasterClassUser, User).
Hosts/ports/onions come from blockchain.secrets created at operation time via hardware pull.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from blockchain_secrets import (  # noqa: E402
    format_tor_onion_service,
    resolve_blockchain_api_prefix,
    resolve_blockchain_bind_host,
    resolve_blockchain_bind_port,
    resolve_blockchain_onion,
    resolve_blockchain_secret,
    resolve_blockchain_secret_key,
    resolve_master_server_internal_host,
    resolve_master_server_internal_port,
    resolve_master_server_onion,
    resolve_nodeuser_onion,
    write_blockchain_secrets_from_pull,
)
from blockchain_schema import BLOCKCHAIN_STATE_COLLECTION  # noqa: E402
from configBlock import (  # noqa: E402
    get_blockchain_db,
    get_mongo_client,
    is_genesis_initialized,
    utc_now,
)

BLOCKCHAIN_ROUTES_STATE_ID = "blockchain_routes_connected"

BLOCKCHAIN_ROUTE_PATHS: tuple[str, ...] = (
    "/health",
    "/genesis-status",
    "/blockchain-create",
    "/blockchain-find",
    "/blockchain-connect",
    "/blockchain-disconnect",
    "/blockchain-end",
    "/blockchain-record",
    "/blockchain-report",
    "/blockchain-transfer",
    "/blockchain-control",
    "/LucidLedger",
    "/LucidLedger-find",
    "/LucidLedger-connect",
    "/LucidLedger-disconnect",
    "/LucidLedger-end",
    "/LucidLedger-record",
    "/LucidLedger-report",
    "/LucidLedger-transfer",
    "/LucidLedger-control",
    "/server-blockchain-sync",
    "/tally-winner",
)


def _internal_base_url(*, host: str, port: int, prefix: str) -> str:
    return f"http://{host}:{port}{prefix}"


def _tor_http_base(*, onion: str, prefix: str) -> str:
    host = format_tor_onion_service(onion)
    return f"http://{host}{prefix}"


def resolve_blockchain_route_targets() -> dict[str, str]:
    """Resolve Tor and internal Docker DNS route targets from blockchain.secrets."""
    prefix = resolve_blockchain_api_prefix()
    targets: dict[str, str] = {
        "master_server_internal": _internal_base_url(
            host=resolve_master_server_internal_host(),
            port=resolve_master_server_internal_port(),
            prefix=prefix,
        ),
        "blockchain_bind": _internal_base_url(
            host=resolve_blockchain_bind_host(),
            port=resolve_blockchain_bind_port(),
            prefix=prefix,
        ),
    }

    blockchain_onion = resolve_blockchain_onion()
    master_onion = resolve_master_server_onion()
    node_onion = resolve_nodeuser_onion()

    if blockchain_onion:
        targets["blockchain_tor"] = _tor_http_base(onion=blockchain_onion, prefix=prefix)
    if master_onion:
        targets["master_server_tor"] = _tor_http_base(onion=master_onion, prefix=prefix)
    if node_onion:
        targets["node_user_tor"] = _tor_http_base(onion=node_onion, prefix=prefix)

    return targets


def verify_blockchain_api_secret(provided: str | None) -> bool:
    expected = resolve_blockchain_secret()
    if not expected:
        return False
    return (provided or "").strip() == expected


def verify_blockchain_api_secret_key(provided: str | None) -> bool:
    expected = resolve_blockchain_secret_key()
    if not expected:
        return False
    return (provided or "").strip() == expected


def build_route_connection_manifest() -> dict[str, Any]:
    """Build cross-container blockchain route manifest from blockchain.secrets."""
    prefix = resolve_blockchain_api_prefix()
    targets = resolve_blockchain_route_targets()
    routes = {
        route: {
            "api_path": f"{prefix}{route}",
            "tor_service": f"{prefix}{route}",
            "network": "tor",
            "tor_only": True,
        }
        for route in BLOCKCHAIN_ROUTE_PATHS
    }
    return {
        "subsystem": "blockchain-system",
        "network": "tor",
        "tor_only": True,
        "targets": targets,
        "routes": routes,
        "blockchain_onion": resolve_blockchain_onion() or None,
        "master_server_onion": resolve_master_server_onion() or None,
        "secrets_configured": bool(resolve_blockchain_secret()),
    }


def connect_blockchain_routes(*, client: Any | None = None) -> dict[str, Any]:
    """Persist blockchain route connectivity metadata (blockchain.secrets driven)."""
    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        manifest = build_route_connection_manifest()
        now = utc_now()
        record = {
            "state_id": BLOCKCHAIN_ROUTES_STATE_ID,
            "connected": True,
            "manifest": manifest,
            "updated_at": now,
        }
        get_blockchain_db(mongo)[BLOCKCHAIN_STATE_COLLECTION].update_one(
            {"state_id": BLOCKCHAIN_ROUTES_STATE_ID},
            {
                "$set": record,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return {
            "connected": True,
            "state_id": BLOCKCHAIN_ROUTES_STATE_ID,
            "manifest": manifest,
            "timestamp": now,
        }
    finally:
        if owns_client and mongo is not None:
            mongo.close()


def get_blockchain_route_connection(*, client: Any | None = None) -> dict[str, Any] | None:
    owns_client = client is None
    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        return None
    try:
        record = get_blockchain_db(mongo)[BLOCKCHAIN_STATE_COLLECTION].find_one(
            {"state_id": BLOCKCHAIN_ROUTES_STATE_ID},
            {"_id": 0},
        )
        return dict(record) if record else None
    finally:
        if owns_client and mongo is not None:
            mongo.close()


def create_blockchain_fastapi_app() -> Any:
    """Build FastAPI app serving blockchain operations (DockerDNS / Tor compatible)."""
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError(
            "fastapi is required to serve blockchain routes at operation time"
        ) from exc

    from CreateBlock import create_new_block
    from distribution import sync_ledger_distribution
    from legder import get_ledger_last_hash, get_ledger_records
    from tally import select_tally_winner

    prefix = resolve_blockchain_api_prefix()
    app = FastAPI(title="LucidTops Blockchain", docs_url=f"{prefix}/docs")

    def _auth(x_blockchain_secret: str | None, x_blockchain_secret_key: str | None) -> None:
        if not verify_blockchain_api_secret(x_blockchain_secret):
            raise HTTPException(status_code=401, detail="Invalid blockchain secret")
        if not verify_blockchain_api_secret_key(x_blockchain_secret_key):
            raise HTTPException(status_code=401, detail="Invalid blockchain secret key")

    @app.get(f"{prefix}/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "subsystem": "blockchain",
            "genesis_initialized": is_genesis_initialized(),
            "timestamp": utc_now(),
        }

    @app.get(f"{prefix}/genesis-status")
    def genesis_status() -> dict[str, Any]:
        return {
            "genesis_initialized": is_genesis_initialized(),
            "timestamp": utc_now(),
        }

    @app.post(f"{prefix}/blockchain-create")
    def blockchain_create(
        payload: dict[str, Any] | None = None,
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> JSONResponse:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        body = payload or {}
        result = create_new_block(
            actor_type=body.get("actor_type") or "master_server",
            invoker=body.get("invoker"),
            node_user_id=body.get("node_user_id"),
            chain_id=body.get("chain_id"),
            reported_memory_gb=body.get("reported_memory_gb"),
        )
        return JSONResponse(result)

    @app.get(f"{prefix}/LucidLedger")
    def lucid_ledger(
        limit: int | None = None,
        record_type: str | None = None,
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        mongo = get_mongo_client()
        if mongo is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            records = get_ledger_records(
                client=mongo, limit=limit, record_type=record_type
            )
            return {
                "records": records,
                "count": len(records),
                "ledger_last_hash": get_ledger_last_hash(client=mongo),
            }
        finally:
            mongo.close()

    @app.get(f"{prefix}/LucidLedger-find")
    def lucid_ledger_find(
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        mongo = get_mongo_client()
        if mongo is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            return {"ledger_last_hash": get_ledger_last_hash(client=mongo)}
        finally:
            mongo.close()

    @app.get(f"{prefix}/tally-winner")
    def tally_winner(
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        mongo = get_mongo_client()
        if mongo is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            return select_tally_winner(client=mongo)
        finally:
            mongo.close()

    @app.post(f"{prefix}/server-blockchain-sync")
    def server_blockchain_sync(
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        return sync_ledger_distribution()

    @app.post(f"{prefix}/blockchain-connect")
    def blockchain_connect(
        x_blockchain_secret: str | None = Header(default=None),
        x_blockchain_secret_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(x_blockchain_secret, x_blockchain_secret_key)
        return connect_blockchain_routes()

    return app


def serve_blockchain_api() -> None:
    """Run uvicorn on bind host/port resolved at operation time from secrets."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required to serve blockchain FastAPI") from exc

    host = resolve_blockchain_bind_host()
    port = resolve_blockchain_bind_port()
    uvicorn.run(
        "ConnectBlockRoutes:create_blockchain_fastapi_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops blockchain route connector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("connect", help="Connect blockchain routes via blockchain.secrets")
    subparsers.add_parser("manifest", help="Print route connection manifest")
    subparsers.add_parser("status", help="Print persisted route connection status")
    subparsers.add_parser("serve", help="Serve FastAPI blockchain routes via uvicorn")

    write_parser = subparsers.add_parser(
        "write-secrets",
        help="Write blockchain.secrets from hardware pull at operation time",
    )
    write_parser.add_argument("--secrets-dir", default=None)
    write_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.command == "connect":
        result = connect_blockchain_routes()
    elif args.command == "manifest":
        result = build_route_connection_manifest()
    elif args.command == "status":
        result = get_blockchain_route_connection() or {"connected": False}
    elif args.command == "serve":
        serve_blockchain_api()
        return 0
    elif args.command == "write-secrets":
        secrets_dir = Path(args.secrets_dir) if args.secrets_dir else None
        path = write_blockchain_secrets_from_pull(secrets_dir=secrets_dir, force=args.force)
        result = {"secrets_file": path.as_posix(), "written": True}
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
