""" the incoming payments system for the lucid projects
objectives:
- to handle all incoming payments via the master server
- all payments will be deposited into a crypto wallet address (tron node wallet address or xrp wallet address)
- all payments will recieve a reciept of the payment details ( lucidTops reciept system)
- all payments will extend the access and usage of the session system
- all payments will be recorded in the master server database and LucidLedger system
- all payments will be validated by the master server API routes

failure to process the incoming payment will result in the UserID being returned to the free tier (super low access)
LucidTokens can be used by a NodeUser to pay for the tier system for use of the session system (session.py)(value of a token is based on the jackpot system (jackpot.py))
the payment system is a monthly subscription system (monthly subscription is based on the selected tier system (tier.py))
the monthly subcription transfers the funds in local currency based on the set values in the tier system (tier.py) to the selected wallet address (tron node wallet address or xrp wallet address)
the monthly subscription will be a direct deposit to the selected wallet address (tron node wallet address or xrp wallet address)
30 day period starts from the date of the first payment (first payment will be the start date)
the monthly subscription will be renewed automatically unless the UserID cancels the subscription
the monthly subscription can be cancelled at any time by the UserID by selecting cancel subscription in tier system (tier.py)
A UserID may ask to change the tier in the middle of the month by selecting change tier in tier system (tier.py) the purchase about will only be the difference in value between the new tier and the old tier
a user may request a refund at any time by selecting refund in tier system (tier.py) once subscription is cancelled, this is subject to balance of use left in the month and the value of the new tier.

all payments will be recorded in the master server database and LucidLedger system
all payments will be validated by the master server API routes
all payments will be recorded in the master server database and LucidLedger system

no hardcoded addresses for the payment system will be in this file. all information will be created and developed using (payment_system_setup.py)
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

from datetime import datetime, timezone, timedelta
from typing import Any

_Connect_wallet = _load_local("Connect_wallet")
_callpayment = _load_local("callpayment")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def subscription_period_days() -> int:
    return require_payment_secret_int("SUBSCRIPTION_PERIOD_DAYS")


def process_incoming_payment(*, payment_payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and record an incoming payment; extends session access on success."""
    load_payments_secrets()
    user_id = str(payment_payload.get("UserID") or payment_payload.get("user_id") or "").strip()
    if not user_id:
        raise RuntimeError("UserID missing from incoming payment payload")
    id_token = str(payment_payload.get("IDToken") or payment_payload.get("id_token") or "").strip()
    if not id_token:
        raise RuntimeError("IDToken missing from incoming payment payload")
    amount = payment_payload.get("payment_amount") or payment_payload.get("amount")
    if amount is None:
        raise RuntimeError("payment_amount missing from incoming payment payload")

    wallet = _Connect_wallet.connect_wallet_address()
    result = _callpayment.call_payment(payment_payload=payment_payload)
    status = str(result.get("payment_result", {}).get("payment_status", "")).lower()
    period_days = subscription_period_days()
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=period_days)
    accepted = status in {"valid", "ok", "paid", "finished", "confirmed"}
    return {
        "UserID": user_id,
        "accepted": accepted,
        "payment_status": status or "unknown",
        "wallet_address": wallet["wallet_address"],
        "subscription_start": start.isoformat(),
        "subscription_end": end.isoformat(),
        "subscription_period_days": period_days,
        "tier_fallback": None if accepted else require_payment_secret("FREE_TIER_NAME"),
        "receipt": {
            "amount": str(amount),
            "currency": wallet["payment_currency"],
            "recorded_at": utc_now(),
        },
        "processor": result,
    }
