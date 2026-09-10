""" to connect a selected wallet address to the lucid projects
objectives:
- to correctly connect the allocated wallet address to the lucid projects
- to ensure all payments can be routed via the wallet address
- to ensure all security measures are in place to protect the wallet address
- to configure the payment system routes to the selected wallet address
- to ensure all transactions are recorded in the master server database and LucidLedger system
- to ensure all transactions are validated by payment system routes (PaymentRoutes.py)
- to ensure the configuration between the Tor hosted master server and the selected wallet address is correct and secure

ADDRESS:
will be loaded via payments.secrets file (payments.secrets) on the master server database

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
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_wallet_address(*, wallet_address: str | None = None) -> dict[str, Any]:
    """Bind the operational wallet address from payments.secrets (no hardcoded ADDRESS)."""
    load_payments_secrets()
    address = (wallet_address or "").strip() or require_wallet_address()
    currency = require_payment_secret("PAYMENTS_CURRENCY")
    method = require_payment_secret("PAYMENTS_METHOD")
    return {
        "wallet_address": address,
        "payment_currency": currency,
        "payment_method": method,
        "connected_at": utc_now(),
        "source": "payments.secrets",
    }


def wallet_connection_status() -> dict[str, Any]:
    connected = connect_wallet_address()
    return {
        "wallet_configured": True,
        "payment_currency": connected["payment_currency"],
        "payment_method": connected["payment_method"],
        "checked_at": utc_now(),
    }
