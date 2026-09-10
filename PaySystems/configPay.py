""" this is the configuration file for the payment system only
this will ensure that the Zero-block architecture for payments are implemented correctly
includes:
- the clearnet configurations (mnt/myssd/LucidTops/secrets/clearnetPay.secrets)
- is connected to the selected payment system (NowPayments.io) via the API routes (FastAPI)
- is connected to the MasterServer (uvicorn server) via SOCKS5 connection (Proxy/Clearnet-package.py)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_paysystems_{module_name}"
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


_payments_secrets = _load_local("payments_secrets")
require_payment_secret = _payments_secrets.require_payment_secret
require_payment_secret_int = _payments_secrets.require_payment_secret_int
require_payment_secret_float = _payments_secrets.require_payment_secret_float
get_payment_secret = _payments_secrets.get_payment_secret
load_payments_secrets = _payments_secrets.load_payments_secrets
load_clearnet_pay_secrets = _payments_secrets.load_clearnet_pay_secrets
require_wallet_address = _payments_secrets.require_wallet_address
payments_status = _payments_secrets.payments_status

from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_payment_configuration(*, reload: bool = False) -> dict[str, str]:
    """Load Zero-block payment + clearnet configuration from secrets files."""
    payments = load_payments_secrets(reload=reload)
    clearnet = load_clearnet_pay_secrets(reload=reload)
    merged = dict(payments)
    merged.update(clearnet)
    return merged


def require_clearnet_api_url() -> str:
    load_payment_configuration()
    return (
        get_payment_secret("PAYMENTS_CLEARNET_API_URL")
        or require_payment_secret("NOWPAYMENTS_API_URL")
    )


def require_payments_api_key() -> str:
    load_payment_configuration()
    return (
        get_payment_secret("PAYMENTS_API_KEY")
        or require_payment_secret("NOWPAYMENTS_API_KEY")
    )


def socks5_endpoint() -> tuple[str, int]:
    load_payment_configuration()
    host = require_payment_secret("TOR_SOCKS_HOST")
    port = require_payment_secret_int("TOR_SOCKS_PORT")
    return host, port


def payment_configuration_status() -> dict[str, Any]:
    load_payment_configuration()
    host, port = socks5_endpoint()
    return {
        **payments_status(),
        "clearnet_api_configured": bool(
            get_payment_secret("PAYMENTS_CLEARNET_API_URL")
            or get_payment_secret("NOWPAYMENTS_API_URL")
        ),
        "api_key_configured": bool(
            get_payment_secret("PAYMENTS_API_KEY")
            or get_payment_secret("NOWPAYMENTS_API_KEY")
        ),
        "socks5_host": host,
        "socks5_port": port,
        "checked_at": utc_now(),
    }
