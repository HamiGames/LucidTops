""" this is the script that will connect the blockchain system to the blockchain routes (BlockRoutes.py), 
for cross container communication between the NodeUser, MasterServer, AdminUser, MasterClassUser, and User with the blockchain system.
this will ensure that the blockchain system is always up to date and that the blockchain system is always operational.
operations:
- cross container communication
- blockchain system up to date
- ledger system up to date
- blockchain system operations via API routes
- tally system operations via API routes
- ledger system operations via API routes
TOR network compatible using *.onion address as required (inserted after container creation blockchain.secrets file)


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
    resolve_blockchain_onion,
    resolve_blockchain_secret,
    resolve_blockchain_secret_key,
    resolve_master_server_internal_host,
    resolve_master_server_internal_port,
    resolve_master_server_onion,
    resolve_nodeuser_onion,
    write_blockchain_secrets_template,
)
from blockchain_schema import BLOCKCHAIN_STATE_COLLECTION  # noqa: E402
from configBlock import get_blockchain_db, get_mongo_client, utc_now  # noqa: E402

BLOCKCHAIN_ROUTES_STATE_ID = "blockchain_routes_connected"

BLOCKCHAIN_ROUTE_PATHS: tuple[str, ...] = (
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


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops blockchain route connector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("connect", help="Connect blockchain routes via blockchain.secrets")
    subparsers.add_parser("manifest", help="Print route connection manifest")
    subparsers.add_parser("status", help="Print persisted route connection status")

    write_parser = subparsers.add_parser(
        "write-secrets-template",
        help="Write blockchain.secrets template for build-stage population",
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
    elif args.command == "write-secrets-template":
        secrets_dir = Path(args.secrets_dir) if args.secrets_dir else None
        path = write_blockchain_secrets_template(secrets_dir=secrets_dir, force=args.force)
        result = {"secrets_file": path.as_posix(), "written": True}
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
