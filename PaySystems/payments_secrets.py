"""Load PaySystems runtime configuration from payments.secrets / clearnetPay.secrets.


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


PAYMENTS_SECRETS_FILE_ENV = "PAYMENTS_SECRETS_FILE"
PAYMENTS_SECRETS_NAME_ENV = "PAYMENTS_SECRETS_NAME"
CLEARNET_PAY_SECRETS_FILE_ENV = "CLEARNET_PAY_SECRETS_FILE"
CLEARNET_PAY_SECRETS_NAME_ENV = "CLEARNET_PAY_SECRETS_NAME"
SECRETS_DIR_ENV = "SECRETS_DIR"
LUCID_TOPS_ROOT_ENV = "LUCID_TOPS_ROOT"


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def require_env(key: str) -> str:
    value = _env(key)
    if not value:
        raise RuntimeError(f"{key} missing — must be set at time of operation")
    return value


def secrets_dir() -> Path:
    configured = _env(SECRETS_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    root = _env(LUCID_TOPS_ROOT_ENV)
    if not root:
        raise RuntimeError(
            f"{SECRETS_DIR_ENV} or {LUCID_TOPS_ROOT_ENV} missing — must be set at time of operation"
        )
    name = _env("SECRETS_DIR_NAME")
    if not name:
        raise RuntimeError(
            "SECRETS_DIR_NAME missing — must be set at time of operation when SECRETS_DIR is unset"
        )
    return Path(root).expanduser() / name


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def payments_secrets_path() -> Path:
    override = _env(PAYMENTS_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    name = _env(PAYMENTS_SECRETS_NAME_ENV)
    if not name:
        raise RuntimeError(
            f"{PAYMENTS_SECRETS_FILE_ENV} or {PAYMENTS_SECRETS_NAME_ENV} missing — "
            "must be set at time of operation"
        )
    return secrets_dir() / name


def clearnet_pay_secrets_path() -> Path:
    override = _env(CLEARNET_PAY_SECRETS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    loaded = load_payments_secrets()
    from_file = loaded.get(CLEARNET_PAY_SECRETS_FILE_ENV, "").strip()
    if from_file:
        return Path(from_file).expanduser()
    name = _env(CLEARNET_PAY_SECRETS_NAME_ENV) or loaded.get(CLEARNET_PAY_SECRETS_NAME_ENV, "").strip()
    if not name:
        raise RuntimeError(
            f"{CLEARNET_PAY_SECRETS_FILE_ENV} or {CLEARNET_PAY_SECRETS_NAME_ENV} missing — "
            "must be set at time of operation"
        )
    return secrets_dir() / name


@lru_cache(maxsize=1)
def _load_payments_secrets_cached() -> dict[str, str]:
    path = payments_secrets_path()
    if not path.exists():
        raise RuntimeError(
            f"payments secrets file missing at {path.as_posix()} — create at time of operation"
        )
    values = parse_secrets_file(path)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return values


@lru_cache(maxsize=1)
def _load_clearnet_pay_secrets_cached() -> dict[str, str]:
    path = clearnet_pay_secrets_path()
    if not path.exists():
        raise RuntimeError(
            f"clearnetPay secrets file missing at {path.as_posix()} — create at time of operation"
        )
    values = parse_secrets_file(path)
    for key, value in values.items():
        if not _env(key):
            os.environ[key] = value
    return values


def load_payments_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_payments_secrets_cached.cache_clear()
    return _load_payments_secrets_cached()


def load_clearnet_pay_secrets(*, reload: bool = False) -> dict[str, str]:
    if reload:
        _load_clearnet_pay_secrets_cached.cache_clear()
    return _load_clearnet_pay_secrets_cached()


def get_payment_secret(key: str) -> str:
    env_value = _env(key)
    if env_value:
        return env_value
    file_value = load_payments_secrets().get(key.upper(), "").strip()
    if file_value:
        return file_value
    clearnet_value = load_clearnet_pay_secrets().get(key.upper(), "").strip()
    if clearnet_value:
        return clearnet_value
    return ""


def require_payment_secret(key: str) -> str:
    value = get_payment_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from environment/payments.secrets/clearnetPay.secrets — "
            "value must be created at time of operation"
        )
    return value


def require_payment_secret_int(key: str) -> int:
    raw = require_payment_secret(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be an integer — got {raw!r}") from exc


def require_payment_secret_float(key: str) -> float:
    raw = require_payment_secret(key)
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be a float — got {raw!r}") from exc


def wallet_address_keys() -> tuple[str, ...]:
    raw = require_payment_secret("WALLET_ADDRESS_KEYS")
    keys = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not keys:
        raise RuntimeError("WALLET_ADDRESS_KEYS empty — must be set at time of operation")
    return keys


def require_wallet_address() -> str:
    load_payments_secrets()
    for key in wallet_address_keys():
        value = get_payment_secret(key)
        if value:
            return value
    raise RuntimeError(
        "wallet address missing — set one of WALLET_ADDRESS_KEYS in payments.secrets "
        "at time of operation"
    )


def payments_status() -> dict[str, Any]:
    path = payments_secrets_path()
    return {
        "payments_secrets_file": path.as_posix(),
        "payments_secrets_exists": path.exists(),
        "wallet_configured": bool(get_payment_secret("WALLET_ADDRESS") or get_payment_secret("PAYMENTS_WALLET_ADDRESS")),
        "api_prefix": get_payment_secret("PAYMENTS_API_PREFIX"),
    }
