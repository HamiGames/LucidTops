#!/usr/bin/env python3
"""Idempotent schema patch for already-created LucidTops Mongo Databases.

Heals LucidTops_SessionsDB multi-collection contract and LucidTopsUserDB
session-count / max-sessions fields without dropping data.

Targets (Databases.txt / DBSchemas.py):
  LucidTops_SessionsDB: SessionID, session-data, session-data-chunk,
                        block-data-queue, block-queue-ID
  LucidTopsUserDB: UserID (+ session-count, max-sessions on template and docs)

Flags:
  --dry-run  (default) report planned actions only
  --apply    write indexes / _schema_template updates / UserID field defaults

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATABASES_DIR = Path(__file__).resolve().parent
if str(DATABASES_DIR) not in sys.path:
    sys.path.insert(0, str(DATABASES_DIR))

from DBSchemas import (  # noqa: E402
    USER_ID_FIELDS,
    apply_schema_to_database,
    collections_for_spec,
    schema_for_database,
)
from Dns_databases import secret_key_prefix  # noqa: E402
from databases_secrets import (  # noqa: E402
    databases_secrets_path,
    load_databases_secrets,
    parse_secrets_file,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _load_values() -> dict[str, str]:
    path = databases_secrets_path()
    if path.exists():
        return parse_secrets_file(path)
    try:
        return load_databases_secrets()
    except Exception as exc:
        raise RuntimeError(
            f"databases.secrets missing — create via BootstrapDatabases at operation time ({exc})"
        ) from exc


def _mongo_client_for(db_name: str, values: dict[str, str]) -> Any:
    from pymongo import MongoClient
    from urllib.parse import quote_plus

    prefix = secret_key_prefix(db_name)
    host_port = values.get(f"{prefix}_HOST_PORT", "").strip()
    primary_ip = values.get("HOST_PRIMARY_IP", "").strip() or _env("HOST_PRIMARY_IP")
    container_port = values.get(f"{prefix}_PORT", "").strip() or values.get(
        "MONGODB_CONTAINER_PORT", ""
    ).strip()
    dns_host = values.get(f"{prefix}_HOST", "").strip() or db_name
    admin_user = values.get("MONGODB_ADMIN_USER", "").strip()
    admin_password = values.get("MONGODB_ADMIN_PASSWORD", "").strip()

    in_container = Path("/.dockerenv").exists() or bool(_env("HOSTNAME"))
    if in_container and Path("/.dockerenv").exists():
        host = dns_host
        port = container_port
    elif primary_ip and host_port:
        host = primary_ip
        port = host_port
    else:
        host = dns_host
        port = container_port

    if not host or not port:
        raise RuntimeError(
            f"connection host/port missing for {db_name} — secrets incomplete at operation time"
        )

    if admin_user and admin_password:
        uri = (
            f"mongodb://{quote_plus(admin_user)}:{quote_plus(admin_password)}"
            f"@{host}:{port}/?authSource=admin"
        )
    else:
        uri = f"mongodb://{host}:{port}"

    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    client.admin.command("ping")
    return client


def _plan_collection(
    db: Any, db_name: str, collection_spec: dict[str, Any]
) -> dict[str, Any]:
    name = str(collection_spec["name"])
    fields = list(collection_spec["fields"])
    col = db[name]
    existing = col.find_one({"_schema_template": True})
    if not existing:
        action = "insert_template"
    elif list(existing.get("fields") or []) != fields:
        action = "update_template_fields"
    else:
        action = "unchanged"
    return {
        "database": db_name,
        "collection": name,
        "action": action,
        "field_count": len(fields),
        "indexes": [idx[0] for idx in (collection_spec.get("indexes") or ())],
    }


def patch_sessionsdb(*, apply: bool) -> dict[str, Any]:
    values = _load_values()
    stamp = utc_now()
    report: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "started_at": stamp,
        "sessions": [],
        "userdb": {},
        "user_docs_backfill": {},
    }

    # --- LucidTops_SessionsDB ---
    sessions_name = "LucidTops_SessionsDB"
    sessions_client = _mongo_client_for(sessions_name, values)
    try:
        sessions_db = sessions_client[sessions_name]
        spec = schema_for_database(sessions_name)
        plans = [
            _plan_collection(sessions_db, sessions_name, c)
            for c in collections_for_spec(spec)
        ]
        report["sessions"] = plans
        if apply:
            result = apply_schema_to_database(
                sessions_db,
                sessions_name,
                created_at=stamp,
                update_template_fields=True,
            )
            report["sessions_applied"] = result
    finally:
        sessions_client.close()

    # --- LucidTopsUserDB ---
    user_name = "LucidTopsUserDB"
    user_client = _mongo_client_for(user_name, values)
    try:
        user_db = user_client[user_name]
        user_spec = schema_for_database(user_name)
        user_plans = [
            _plan_collection(user_db, user_name, c)
            for c in collections_for_spec(user_spec)
        ]
        report["userdb"] = {"plans": user_plans, "fields": list(USER_ID_FIELDS)}
        if apply:
            report["userdb_applied"] = apply_schema_to_database(
                user_db,
                user_name,
                created_at=stamp,
                update_template_fields=True,
            )
            col_name = str(user_spec["collection"])
            col = user_db[col_name]
            set_count = col.update_many(
                {
                    "_schema_template": {"$ne": True},
                    "session-count": {"$exists": False},
                },
                {"$set": {"session-count": 0, "updated_at": stamp}},
            )
            set_max = col.update_many(
                {
                    "_schema_template": {"$ne": True},
                    "max-sessions": {"$exists": False},
                },
                {"$set": {"max-sessions": None, "updated_at": stamp}},
            )
            report["user_docs_backfill"] = {
                "session_count_matched": set_count.matched_count,
                "session_count_modified": set_count.modified_count,
                "max_sessions_matched": set_max.matched_count,
                "max_sessions_modified": set_max.modified_count,
            }
        else:
            col_name = str(user_spec["collection"])
            col = user_db[col_name]
            need_count = col.count_documents(
                {
                    "_schema_template": {"$ne": True},
                    "$or": [
                        {"session-count": {"$exists": False}},
                        {"max-sessions": {"$exists": False}},
                    ],
                }
            )
            report["user_docs_backfill"] = {
                "would_touch_docs": need_count,
            }
    finally:
        user_client.close()

    report["finished_at"] = utc_now()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Patch LucidTops_SessionsDB + LucidTopsUserDB schemas on live Mongo"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply indexes, template updates, and UserID field defaults",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned actions only (default when --apply is omitted)",
    )
    args = parser.parse_args(argv)
    apply = bool(args.apply)
    try:
        report = patch_sessionsdb(apply=apply)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
