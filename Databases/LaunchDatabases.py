"""CLI launcher for LucidTops Databases bootstrap at time of operation.

Run on Windows build console or Raspberry Pi (SSH) to:
1. pull hardware facts
2. write secrets
3. start six separate MongoDB containers
4. apply schemas and verify

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
from pathlib import Path

_DATABASES_DIR = Path(__file__).resolve().parent
if str(_DATABASES_DIR) not in sys.path:
    sys.path.insert(0, str(_DATABASES_DIR))

from BootstrapDatabases import bootstrap_databases
from databases_secrets import databases_secrets_status
from pull_information import bind_operation_environ, pull_realworld_information


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch LucidTops separate MongoDB database containers at operation time"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild secrets keys even when databases.secrets already exists",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Pull hardware, bind env, print secrets status without starting containers",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON result",
    )
    args = parser.parse_args(argv)

    pull = pull_realworld_information()
    bind_operation_environ(pull)

    if args.status_only:
        payload = {
            "pull": {
                "pulled_at": pull.get("pulled_at"),
                "hostname": pull.get("hostname"),
                "primary_ip": pull.get("primary_ip"),
                "primary_mac": pull.get("primary_mac"),
                "databases_dir": pull.get("databases_dir"),
                "secrets_dir": pull.get("secrets_dir"),
                "docker_network_tor_db": pull.get("docker_network_tor_db"),
                "docker_network_nontor_db": pull.get("docker_network_nontor_db"),
            },
            "secrets": databases_secrets_status(),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"databases_dir={payload['pull']['databases_dir']}")
            print(f"secrets_dir={payload['pull']['secrets_dir']}")
            print(f"primary_ip={payload['pull']['primary_ip']}")
            print(f"primary_mac={payload['pull']['primary_mac']}")
            print(f"secrets_exists={payload['secrets']['secrets_file_exists']}")
            print(f"verified={payload['secrets']['databases_verified']}")
        return 0

    force = args.force or _env("DATABASES_BOOTSTRAP_FORCE").lower() in {
        "1",
        "true",
        "yes",
    }
    result = bootstrap_databases(force=force)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"databases_dir={result['databases_dir']}")
        print(f"databases_secrets={result['databases_secrets']}")
        print(f"mongodb_secrets={result['mongodb_secrets']}")
        print(f"compose_file={result['compose_file']}")
        print(f"verified={result['verified']}")
        for name, status in (result.get("health") or {}).items():
            print(f"container {name}={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
