#!/usr/bin/env python3
"""One-time script to launch and set up the LucidTops master server for the first time."""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path
from typing import Any

from builderMasterServer import build_master_server
from config import (
    CONTAINER_ONION_DIR,
    LUCID_TOPS_ROOT,
    SECRETS_DIR,
    SERVER_ENV_PATH,
    TOR_HIDDEN_SERVICE_DIRS,
    get_master_db,
    get_mongo_client,
    utc_now,
)
from MasterDBSchema import ADMIN_USERS_COLLECTION, MASTER_CLASS_USERS_COLLECTION

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
ADMIN_USER_DIR = PROJECT_ROOT / "AdminUser"
MASTER_CLASS_USER_DIR = PROJECT_ROOT / "MasterClassUser"


def _read_onion_address(hidden_service_dir: Path) -> str | None:
    hostname_file = hidden_service_dir / "hostname"
    try:
        return hostname_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _collect_onion_addresses() -> dict[str, str | None]:
    addresses = {}
    for name, path in TOR_HIDDEN_SERVICE_DIRS.items():
        addresses[name] = _read_onion_address(path)
    container_dir = CONTAINER_ONION_DIR
    if container_dir.exists():
        for item in container_dir.glob("*.onion"):
            addresses[item.stem] = item.read_text(encoding="utf-8").strip()
    return addresses


def _update_server_env_onions(addresses: dict[str, str | None]) -> None:
    if not SERVER_ENV_PATH.exists():
        return
    lines = SERVER_ENV_PATH.read_text(encoding="utf-8").splitlines()
    mapping = {
        "MASTER_SERVER_ONION": addresses.get("master_server"),
        "FRONTEND_ONION": addresses.get("frontend"),
        "NODEUSER_ONION": addresses.get("node_user"),
    }
    updated: list[str] = []
    seen: set[str] = set()
    for line in lines:
        replaced = False
        for key, value in mapping.items():
            if line.startswith(f"{key}="):
                if value:
                    updated.append(f"{key}={value}")
                else:
                    updated.append(line)
                seen.add(key)
                replaced = True
                break
        if not replaced:
            updated.append(line)
    for key, value in mapping.items():
        if key not in seen and value:
            updated.append(f"{key}={value}")
    SERVER_ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _write_account_file(
    directory: Path,
    filename: str,
    accounts: list[dict[str, str]],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    lines = [
        "# LucidTops bootstrap credentials - store securely",
        f"# Generated: {utc_now()}",
        "",
    ]
    for index, account in enumerate(accounts, start=1):
        lines.append(f"[Account {index}]")
        for key, value in account.items():
            lines.append(f"{key}={value}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _create_admin_user(client: Any) -> Path:
    db = get_master_db(client)
    admin_id = secrets.token_hex(4)
    password = secrets.token_urlsafe(16)
    id_token = secrets.token_urlsafe(32)
    now = utc_now()
    record = {
        "adminUserID": admin_id,
        "IDToken": id_token,
        "access_level": "admin",
        "access_type": "bootstrap",
        "admin_registration_timestamp": now,
        "password": password,
        "created_at": now,
        "updated_at": now,
    }
    db[ADMIN_USERS_COLLECTION].update_one(
        {"adminUserID": admin_id},
        {"$set": record},
        upsert=True,
    )
    return _write_account_file(
        ADMIN_USER_DIR,
        "admin.txt",
        [{"adminUserID": admin_id, "password": password, "IDToken": id_token}],
    )


def _create_master_class_users(client: Any) -> Path:
    db = get_master_db(client)
    accounts: list[dict[str, str]] = []
    now = utc_now()
    for index in range(1, 4):
        mc_id = secrets.token_hex(4)
        password = secrets.token_urlsafe(16)
        id_token = secrets.token_urlsafe(32)
        db[MASTER_CLASS_USERS_COLLECTION].update_one(
            {"MasterClassUserID": mc_id},
            {
                "$set": {
                    "MasterClassUserID": mc_id,
                    "IDToken": id_token,
                    "access_level": "master_class",
                    "access_type": f"bootstrap_{index}",
                    "masterclass_registration_timestamp": now,
                    "password": password,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        accounts.append(
            {
                "MasterClassUserID": mc_id,
                "password": password,
                "IDToken": id_token,
            }
        )
    return _write_account_file(MASTER_CLASS_USER_DIR, "master.txt", accounts)


def launch_server(*, run_uvicorn: bool = False) -> dict[str, Any]:
    """Run builder, onion setup, bootstrap accounts, and optionally start the server."""
    build_result = build_master_server()
    onion_addresses = _collect_onion_addresses()
    _update_server_env_onions(onion_addresses)

    admin_file: str | None = None
    master_file: str | None = None
    client = get_mongo_client()
    if client is not None:
        try:
            admin_path = _create_admin_user(client)
            master_path = _create_master_class_users(client)
            admin_file = str(admin_path)
            master_file = str(master_path)
        finally:
            client.close()

    result = {
        **build_result,
        "onion_addresses": {k: v for k, v in onion_addresses.items() if v},
        "admin_credentials_file": admin_file,
        "master_class_credentials_file": master_file,
        "launch_complete": True,
    }

    if run_uvicorn:
        from main import run_server

        run_server()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LucidTops master server")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start uvicorn after setup (Docker container runtime)",
    )
    args = parser.parse_args()

    print(f"LaunchServer: root={LUCID_TOPS_ROOT} secrets={SECRETS_DIR}")
    result = launch_server(run_uvicorn=args.serve)
    print("LucidTops LaunchServer complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")
    if not result.get("onion_addresses"):
        print(
            "  note: No *.onion hostnames found yet. Start tor daemon and re-run LaunchServer.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
