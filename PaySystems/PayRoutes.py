""" this the API routes for the payment system container for the LucidTops system.
only the master server and the AdminUser will have access to the payment system container for outgoing payments.
the incoming payments will be handled by the payment system container via the API routes (From User or NodeUser)

this container will be useable via the API routes.(FastAPI)
the master server is a Uvicorn server and the AdminUser is an external user Portal for payments.
payment operations:
- update billing information for the user or node
- process a payment for the user or node
- payout to NodeUser, MasterServer, AdminUser, MasterClassUser, and User via the API routes.
- transfer of funds between wallet address and third party intermediaries via the API routes, using Clearnet protocols(NowPayments, Stripe, PayPal, etc.)
- No transactions will be performed directly from the Tor system, all transactions will be performed via the Clearnet protocols.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

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


_PaymentRoutes = _load_local("PaymentRoutes")
_payments_secrets = _load_local("payments_secrets")
require_payment_secret = _payments_secrets.require_payment_secret
load_payments_secrets = _payments_secrets.load_payments_secrets


def create_pay_container_app() -> FastAPI:
    """Payment container FastAPI app (master/AdminUser outgoing + incoming routes)."""
    load_payments_secrets()
    app = _PaymentRoutes.create_payment_app()
    app.title = require_payment_secret("PAYMENTS_CONTAINER_APP_TITLE")
    return app


