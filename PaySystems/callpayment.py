""" this is the script that links to the frontend payment system (Frontend/Payment.js) and calls to the Masterserver via an API route.
the server will then call to a clearnet API route to continue the payment process.
this payment process will be performed via a intermediate payment system (NowPayments.io) using the API routes provided by the NowPayments.io API.
this payment process will be operational in a clearnet version of the payments.js script (Frontend/Payment.js) that is EMV 3DS compliant.
the payment information will be stored in a seperate database (payment_system.db) on the console Hosting the MasterServer container.
- calls the the Proxy/Clearnet-package.py script to access the clearnet for payment processing.
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

_configPay = _load_local("configPay")
_Connect_wallet = _load_local("Connect_wallet")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_clearnet_package() -> Any:
    proxy_dir = _DIR.parent / "proxy"
    path = proxy_dir / "Clearnet-package.py"
    if not path.exists():
        raise RuntimeError(
            f"Clearnet-package.py missing at {path.as_posix()} — required for clearnet payment egress"
        )
    if str(proxy_dir) not in sys.path:
        sys.path.insert(0, str(proxy_dir))
    registry = "lucid_proxy_clearnet_package_from_paysystems"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    spec.loader.exec_module(module)
    return module


def call_payment(*, payment_payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke clearnet payment processing via Proxy/Clearnet-package.py."""
    _configPay.load_payment_configuration()
    wallet = _Connect_wallet.connect_wallet_address()
    payload = dict(payment_payload)
    payload.setdefault("wallet_address", wallet["wallet_address"])
    payload.setdefault("currency", wallet["payment_currency"])
    clearnet = _load_clearnet_package()
    result = clearnet.request_clearnet_payment(payment_payload=payload)
    return {
        "payment_result": result,
        "called_at": utc_now(),
        "wallet_address": wallet["wallet_address"],
        "source": "callpayment",
    }
