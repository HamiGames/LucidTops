"""Registry of container-loadable *.secrets files produced by builderMasterServer.py."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config import DEFAULT_CONFIG_SECRETS_NAME, SECRETS_DIR, apply_secrets_file, parse_secrets_file

DEFAULT_SERVER_SECRETS_NAME = "server.secrets"
DEFAULT_OPERATIONS_SECRETS_NAME = "operations.secrets"
DEFAULT_MONGODB_SECRETS_NAME = "mongodb.secrets"
DEFAULT_BLOCKCHAIN_SECRETS_NAME = "blockchain.secrets"
DEFAULT_PAYMENTS_SECRETS_NAME = "payments.secrets"

CONTAINER_SECRETS_SPECS: tuple[tuple[str, str], ...] = (
    ("SERVER_SECRETS_FILE", DEFAULT_SERVER_SECRETS_NAME),
    ("CONFIG_SECRETS_FILE", DEFAULT_CONFIG_SECRETS_NAME),
    ("OPERATIONS_SECRETS_FILE", DEFAULT_OPERATIONS_SECRETS_NAME),
    ("MONGODB_SECRETS_FILE", DEFAULT_MONGODB_SECRETS_NAME),
    ("BLOCKCHAIN_SECRETS_FILE", DEFAULT_BLOCKCHAIN_SECRETS_NAME),
    ("PAYMENTS_SECRETS_FILE", DEFAULT_PAYMENTS_SECRETS_NAME),
)


def resolve_container_secrets_paths(secrets_dir: Path | None = None) -> dict[str, Path]:
    base = secrets_dir or SECRETS_DIR
    resolved: dict[str, Path] = {}
    for env_key, filename in CONTAINER_SECRETS_SPECS:
        override = os.environ.get(env_key, "").strip()
        if override:
            resolved[env_key] = Path(override).expanduser()
        else:
            resolved[env_key] = base / filename
    return resolved


def container_secrets_env_lines(secrets_dir: Path) -> list[str]:
    paths = resolve_container_secrets_paths(secrets_dir)
    return [f"{env_key}={path.as_posix()}" for env_key, path in paths.items()]


def container_secrets_load_order() -> tuple[str, ...]:
    return tuple(env_key for env_key, _ in CONTAINER_SECRETS_SPECS)


def apply_all_container_secrets(*, secrets_dir: Path | None = None) -> dict[str, dict[str, str]]:
    loaded: dict[str, dict[str, str]] = {}
    for env_key, path in resolve_container_secrets_paths(secrets_dir).items():
        if path.exists():
            loaded[env_key] = apply_secrets_file(path)
    return loaded


def container_secrets_status(*, secrets_dir: Path | None = None) -> dict[str, Any]:
    paths = resolve_container_secrets_paths(secrets_dir)
    return {
        env_key: {
            "path": path.as_posix(),
            "exists": path.exists(),
            "keys_loaded": len(parse_secrets_file(path)) if path.exists() else 0,
        }
        for env_key, path in paths.items()
    }
