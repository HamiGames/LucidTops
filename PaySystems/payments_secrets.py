"""Load PaySystems runtime configuration from payments.secrets / clearnetPay.secrets.


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
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


PAYMENT_SECRET_KEYS: tuple[str, ...] = (
    "WALLET_ADDRESS_KEYS",
    "NOWPAYMENTS_API_KEY",
    "NOWPAYMENTS_API_URL",
    "JACKPOT_MIN_PAYOUT_USD",
    "JACKPOT_GOAL_INCREASE_PERCENT",
    "JACKPOT_MAX_INCREASE_PERCENT",
    "JACKPOT_TOP_USERS",
    "SUBSCRIPTION_PERIOD_DAYS",
    "PAYMENTS_API_PREFIX",
    "PAYMENTS_APP_TITLE",
    "PAYMENTS_APP_DESCRIPTION",
    "PAYMENTS_APP_VERSION",
    "PAYMENTS_CONTAINER_APP_TITLE",
    "PAYMENTS_CURRENCY",
    "PAYMENTS_METHOD",
    "FREE_TIER_NAME",
    "TOR_SOCKS_HOST",
    "TOR_SOCKS_PORT",
)

PAYMENT_RUNTIME_KEYS: tuple[str, ...] = (
    "PAYMENTS_SECRETS_FILE",
    "SECRETS_DIR",
    "LUCID_TOPS_ROOT",
    "PAYMENTS_CONTAINER_NAME",
    "PAYMENTS_DOCKER_DNS_NAME",
    "PAYSYSTEMS_BIND_HOST",
    "PAYSYSTEMS_BIND_PORT",
    "PAYMENTS_NETWORK_NAME",
    "HOST_PRIMARY_IP",
    "HOST_PRIMARY_MAC",
    "HOST_HOSTNAME",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _env_list_to_map(env_list: list[str] | None) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in env_list or []:
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        if key:
            mapped[key] = value.strip()
    return mapped


def _payments_container_name(docker_bin: str) -> str:
    result = _run([docker_bin, "ps", "--format", "{{.Names}}"])
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise RuntimeError(
            "docker ps failed — PaySystems container inspect requires a running daemon"
            + (f" ({detail})" if detail else "")
        )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    override = _env("PAYMENTS_CONTAINER_NAME")
    if override and override in names:
        return override
    matches = [
        name
        for name in names
        if "paysystem" in name.lower() or name.lower() in {"lucid-paysystems", "pay"}
    ]
    if not matches:
        raise RuntimeError("PaySystems container is not running")
    preferred = [
        name
        for name in matches
        if name.lower() in {"lucid-paysystems", "paysystems"}
    ]
    if len(preferred) == 1:
        return preferred[0]
    if len(matches) == 1:
        return matches[0]
    raise RuntimeError(f"multiple PaySystems containers are running — {matches}")


def pull_active_payments_container(docker_bin: str = "") -> dict[str, Any]:
    """Read the running PaySystems container. Does not invent wallet or API keys."""
    binary = docker_bin.strip() or shutil.which("docker") or ""
    if not binary:
        raise RuntimeError("docker missing — cannot read the PaySystems container")
    name = _payments_container_name(binary)
    result = _run([binary, "inspect", name])
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or "").strip()
        raise RuntimeError(
            f"{name} inspect failed" + (f" — {detail}" if detail else "")
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} inspect output is not JSON") from exc
    row = payload[0] if isinstance(payload, list) else payload
    if not isinstance(row, dict):
        raise RuntimeError(f"{name} inspect payload is empty")
    status = str((row.get("State") or {}).get("Status") or "").strip()
    if status != "running":
        raise RuntimeError(f"{name} status is {status or 'missing'} — container must be running")
    config = row.get("Config") or {}
    host_config = row.get("HostConfig") or {}
    env_map = _env_list_to_map(config.get("Env"))
    port_bindings = host_config.get("PortBindings") or {}
    if not isinstance(port_bindings, dict):
        port_bindings = {}
    published: list[tuple[str, str, str]] = []
    for key, binding in port_bindings.items():
        if not str(key).endswith("/tcp") or not binding:
            continue
        host_port = str((binding[0] or {}).get("HostPort") or "").strip()
        host_ip = str((binding[0] or {}).get("HostIp") or "").strip()
        container_port = str(key).split("/")[0]
        if host_port:
            published.append((container_port, host_port, host_ip))
    if len(published) != 1:
        raise RuntimeError(
            f"{name} must publish exactly one tcp port — got {list(port_bindings)}"
        )
    networks = list(((row.get("NetworkSettings") or {}).get("Networks") or {}).keys())
    if len(networks) != 1 or not networks[0].strip():
        raise RuntimeError(
            f"{name} must be attached to exactly one Docker network — got {networks}"
        )
    return {
        "name": name,
        "status": status,
        "container_port": published[0][0],
        "host_port": published[0][1],
        "host_ip": published[0][2],
        "network": networks[0].strip(),
        "env": env_map,
    }


def write_payments_secrets(
    pull: dict[str, Any] | None = None,
    *,
    secrets_dir: Path | None = None,
    container: dict[str, Any] | None = None,
) -> Path:
    """
    Write payments.secrets from the running PaySystems container plus keys already
    present in that container's environment or the existing payments.secrets file.
    """
    info = pull or {}
    target_dir = secrets_dir or Path(
        str(info.get("secrets_dir") or _env(SECRETS_DIR_ENV) or "")
    ).expanduser()
    if not str(target_dir):
        raise RuntimeError("SECRETS_DIR missing — payments.secrets path is Server/Secrets")
    path = target_dir / (
        _env(PAYMENTS_SECRETS_NAME_ENV) or "payments.secrets"
    )
    os.environ[PAYMENTS_SECRETS_FILE_ENV] = path.as_posix()
    os.environ["SECRETS_DIR"] = target_dir.as_posix()

    active = container if isinstance(container, dict) and container.get("name") else None
    if active is None:
        docker_bin = str((info.get("bins") or {}).get("docker") or "")
        active = pull_active_payments_container(docker_bin)
    container_env = active.get("env") if isinstance(active.get("env"), dict) else {}
    existing = parse_secrets_file(path)

    values: dict[str, str] = {}
    for key, value in existing.items():
        if value:
            values[key] = value
    for key, value in container_env.items():
        if value and not values.get(key):
            values[key] = value

    bind_host = str(active.get("host_ip") or "").strip()
    if bind_host in {"", "0.0.0.0", "::", "[::]"}:
        bind_host = str(info.get("primary_ip") or _env("HOST_PRIMARY_IP") or "").strip()
    if not bind_host:
        raise RuntimeError("PaySystems bind host missing from the running container and hardware pull")
    bind_port = str(active.get("host_port") or "").strip()
    if not bind_port:
        raise RuntimeError("PaySystems bind port missing from the running container")
    container_name = str(active.get("name") or "").strip()
    network_name = str(active.get("network") or "").strip()
    lucid_root = str(info.get("lucid_tops_root") or _env(LUCID_TOPS_ROOT_ENV) or "").strip()
    runtime = {
        "PAYMENTS_SECRETS_FILE": path.as_posix(),
        "SECRETS_DIR": target_dir.as_posix(),
        "LUCID_TOPS_ROOT": lucid_root,
        "PAYMENTS_CONTAINER_NAME": container_name,
        "PAYMENTS_DOCKER_DNS_NAME": container_name,
        "PAYSYSTEMS_BIND_HOST": bind_host,
        "PAYSYSTEMS_BIND_PORT": bind_port,
        "PAYMENTS_NETWORK_NAME": network_name,
        "HOST_PRIMARY_IP": str(info.get("primary_ip") or "").strip(),
        "HOST_PRIMARY_MAC": str(info.get("primary_mac") or "").strip(),
        "HOST_HOSTNAME": str(info.get("hostname") or "").strip(),
    }
    for key, value in runtime.items():
        if not value and key in {"LUCID_TOPS_ROOT", "HOST_PRIMARY_IP", "HOST_PRIMARY_MAC", "HOST_HOSTNAME"}:
            continue
        if not value:
            raise RuntimeError(f"{key} missing from the running PaySystems container")
        values[key] = value

    for key in ("TOR_SOCKS_HOST", "TOR_SOCKS_PORT"):
        if not values.get(key) and _env(key):
            values[key] = _env(key)

    missing = [key for key in PAYMENT_SECRET_KEYS if not str(values.get(key, "")).strip()]
    if missing:
        raise RuntimeError(
            "payments.secrets refused — missing wallet or processor keys from the "
            "running container or existing payments.secrets: " + ", ".join(missing)
        )
    wallet_keys = tuple(
        item.strip() for item in values["WALLET_ADDRESS_KEYS"].split(",") if item.strip()
    )
    if not wallet_keys or not any(str(values.get(key, "")).strip() for key in wallet_keys):
        raise RuntimeError(
            "wallet address missing — set one of WALLET_ADDRESS_KEYS in the running "
            "PaySystems container or the existing payments.secrets file"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops payments.secrets — written from the running PaySystems container",
        f"# Generated: {_utc_now()}",
        f"# Container: {container_name}",
        "",
    ]
    written_keys = list(PAYMENT_RUNTIME_KEYS) + list(PAYMENT_SECRET_KEYS)
    seen: set[str] = set()
    for key in written_keys:
        value = str(values.get(key, "")).strip()
        if value:
            lines.append(f"{key}={value}")
            seen.add(key)
    for key in sorted(values):
        if key in seen:
            continue
        value = str(values[key]).strip()
        if value:
            lines.append(f"{key}={value}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _load_payments_secrets_cached.cache_clear()
    for key, value in values.items():
        if value and not _env(key):
            os.environ[key] = value
    return path


def payments_status() -> dict[str, Any]:
    path = payments_secrets_path()
    return {
        "payments_secrets_file": path.as_posix(),
        "payments_secrets_exists": path.exists(),
        "wallet_configured": bool(get_payment_secret("WALLET_ADDRESS") or get_payment_secret("PAYMENTS_WALLET_ADDRESS")),
        "api_prefix": get_payment_secret("PAYMENTS_API_PREFIX"),
    }
