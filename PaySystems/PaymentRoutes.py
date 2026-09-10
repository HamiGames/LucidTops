""" this is the API routes for the PaySystems module (using FastAPI)
PayRoutes:
- /payment-create: create a new payment
- /payment-find: find a payment
- /payment-receipt: generate a receipt for a payment
- /payment-update: update a payment
- /payment-accept: accept a payment
- /payment-reject: reject a payment
- /payment-cancel: cancel a payment
- /payment-account: view the payment account details
- /jackpot-read: read the jackpot system
- /jackpot-create: create a new jackpot
- /jackpot-update: update a jackpot
- /jackpot-calculate: calculate the jackpot's payout value based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
- /jackpot-payout: payout the the jackpot-calculate value to the UserID, NodeUserID, MasterClassUserID, or AdminUserID

limitations:
- the PayRoutes use the selected payment method from master server (eg. tron, xrp, or USD)
- all payments will only be made to a verified payment account (paypal, stripe, or crypto wallet address)
- all payments will be recorded in the master server database and LucidLedger system
- the PayRoutes are only used by the master server API routes
- the PayRoutes are hosted on the MasterServer container
- the PayRoutes are used to access billing and payment data in the master server database
- the PayRoutes require a valid IDToken for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid API key for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid source for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment method for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment currency for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment amount for the UserID, NodeUserID, MasterClassUserID, or AdminUserID

-payments are limited to jackpot senario only (no other outgoing payments are allowed from the master server)
-all payments will be recorded in the master server database and LucidLedger system

"""


from __future__ import annotations

import importlib.util
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

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
get_payment_secret = _payments_secrets.get_payment_secret
load_payments_secrets = _payments_secrets.load_payments_secrets

_configPay = _load_local("configPay")
_Connect_wallet = _load_local("Connect_wallet")
_IncomingPayments = _load_local("IncomingPayments")
_jackpot = _load_local("jackpot")
_callpayment = _load_local("callpayment")

_PAYMENT_STORE: dict[str, dict[str, Any]] = {}
_JACKPOT_STORE: dict[str, dict[str, Any]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthPayload(BaseModel):
    UserID: str | None = None
    NodeUserID: str | None = None
    MasterClassUserID: str | None = None
    AdminUserID: str | None = None
    IDToken: str
    source: str
    payment_method: str | None = None
    payment_currency: str | None = None
    payment_amount: float | None = None


class PaymentCreatePayload(AuthPayload):
    payment_method: str
    payment_currency: str
    payment_amount: float


class PaymentIdPayload(AuthPayload):
    payment_id: str


class JackpotCreatePayload(AuthPayload):
    jackpot_goal: float


class JackpotCalculatePayload(AuthPayload):
    jackpot_id: str
    token_balances: dict[str, float] = Field(default_factory=dict)


def _actor_id(payload: AuthPayload) -> str:
    for field in ("UserID", "NodeUserID", "MasterClassUserID", "AdminUserID"):
        value = getattr(payload, field)
        if value and str(value).strip():
            return str(value).strip()
    raise HTTPException(status_code=400, detail="actor id missing")


def _require_api_key(x_lucid_api_key: str | None) -> None:
    expected = (
        get_payment_secret("PAYMENTS_API_KEY")
        or require_payment_secret("NOWPAYMENTS_API_KEY")
    )
    if not x_lucid_api_key or x_lucid_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="invalid API key")


def _require_id_token(payload: AuthPayload) -> None:
    if not payload.IDToken or not payload.IDToken.strip():
        raise HTTPException(status_code=401, detail="IDToken missing")
    if not payload.source or not payload.source.strip():
        raise HTTPException(status_code=400, detail="source missing")


def create_payment_app() -> FastAPI:
    load_payments_secrets()
    api_prefix = require_payment_secret("PAYMENTS_API_PREFIX")
    app = FastAPI(
        title=require_payment_secret("PAYMENTS_APP_TITLE"),
        description=require_payment_secret("PAYMENTS_APP_DESCRIPTION"),
        version=require_payment_secret("PAYMENTS_APP_VERSION"),
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "checked_at": utc_now(), **_configPay.payment_configuration_status()}

    @app.post(f"{api_prefix}/payment-create")
    def payment_create(
        payload: PaymentCreatePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        payment_id = secrets.token_hex(16)
        record = {
            "payment_id": payment_id,
            "actor_id": _actor_id(payload),
            "payment_method": payload.payment_method,
            "payment_currency": payload.payment_currency,
            "payment_amount": payload.payment_amount,
            "status": "created",
            "created_at": utc_now(),
        }
        _PAYMENT_STORE[payment_id] = record
        return record

    @app.post(f"{api_prefix}/payment-find")
    def payment_find(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        return record

    @app.post(f"{api_prefix}/payment-receipt")
    def payment_receipt(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        wallet = _Connect_wallet.connect_wallet_address()
        return {
            "receipt_id": secrets.token_hex(12),
            "payment": record,
            "wallet_address": wallet["wallet_address"],
            "issued_at": utc_now(),
        }

    @app.post(f"{api_prefix}/payment-update")
    def payment_update(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        if payload.payment_amount is not None:
            record["payment_amount"] = payload.payment_amount
        if payload.payment_currency:
            record["payment_currency"] = payload.payment_currency
        if payload.payment_method:
            record["payment_method"] = payload.payment_method
        record["updated_at"] = utc_now()
        return record

    @app.post(f"{api_prefix}/payment-accept")
    def payment_accept(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        incoming = _IncomingPayments.process_incoming_payment(
            payment_payload={
                "UserID": _actor_id(payload),
                "IDToken": payload.IDToken,
                "payment_amount": record["payment_amount"],
                "currency": record["payment_currency"],
                "payment_id": payload.payment_id,
            }
        )
        record["status"] = "accepted" if incoming["accepted"] else "rejected"
        record["incoming"] = incoming
        record["updated_at"] = utc_now()
        return record

    @app.post(f"{api_prefix}/payment-reject")
    def payment_reject(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        record["status"] = "rejected"
        record["updated_at"] = utc_now()
        return record

    @app.post(f"{api_prefix}/payment-cancel")
    def payment_cancel(
        payload: PaymentIdPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _PAYMENT_STORE.get(payload.payment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="payment not found")
        record["status"] = "cancelled"
        record["updated_at"] = utc_now()
        return record

    @app.post(f"{api_prefix}/payment-account")
    def payment_account(
        payload: AuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        return {
            "actor_id": _actor_id(payload),
            **_Connect_wallet.wallet_connection_status(),
            **_configPay.payment_configuration_status(),
        }

    @app.post(f"{api_prefix}/jackpot-read")
    def jackpot_read(
        payload: AuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        return {"jackpots": list(_JACKPOT_STORE.values()), "rules": _jackpot.jackpot_rules()}

    @app.post(f"{api_prefix}/jackpot-create")
    def jackpot_create(
        payload: JackpotCreatePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        jackpot_id = secrets.token_hex(12)
        record = {
            "jackpot_id": jackpot_id,
            "jackpot_goal": payload.jackpot_goal,
            "jackpot_value": 0.0,
            "created_by": _actor_id(payload),
            "created_at": utc_now(),
        }
        _JACKPOT_STORE[jackpot_id] = record
        return record

    @app.post(f"{api_prefix}/jackpot-update")
    def jackpot_update(
        payload: JackpotCalculatePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _JACKPOT_STORE.get(payload.jackpot_id)
        if record is None:
            raise HTTPException(status_code=404, detail="jackpot not found")
        record["jackpot_goal"] = _jackpot.next_jackpot_goal(float(record["jackpot_goal"]))
        record["updated_at"] = utc_now()
        return record

    @app.post(f"{api_prefix}/jackpot-calculate")
    def jackpot_calculate(
        payload: JackpotCalculatePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _JACKPOT_STORE.get(payload.jackpot_id)
        if record is None:
            raise HTTPException(status_code=404, detail="jackpot not found")
        calc = _jackpot.calculate_shared_payout(
            jackpot_value=float(record.get("jackpot_value") or record["jackpot_goal"]),
            token_balances=payload.token_balances,
        )
        record["last_calculation"] = calc
        return calc

    @app.post(f"{api_prefix}/jackpot-payout")
    def jackpot_payout(
        payload: JackpotCalculatePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        _require_id_token(payload)
        record = _JACKPOT_STORE.get(payload.jackpot_id)
        if record is None:
            raise HTTPException(status_code=404, detail="jackpot not found")
        calc = record.get("last_calculation") or _jackpot.calculate_shared_payout(
            jackpot_value=float(record.get("jackpot_value") or record["jackpot_goal"]),
            token_balances=payload.token_balances,
        )
        actor = _actor_id(payload)
        amount = calc["payouts"].get(actor)
        if amount is None:
            raise HTTPException(status_code=400, detail="actor not in jackpot payout set")
        egress = _callpayment.call_payment(
            payment_payload={
                "UserID": actor,
                "IDToken": payload.IDToken,
                "amount": amount,
                "currency": require_payment_secret("PAYMENTS_CURRENCY"),
                "jackpot_id": payload.jackpot_id,
                "direction": "jackpot_payout",
            }
        )
        record["jackpot_value"] = float(record.get("jackpot_value") or record["jackpot_goal"]) - float(amount)
        record["last_payout"] = {"actor_id": actor, "amount": amount, "egress": egress, "at": utc_now()}
        return record["last_payout"]

    return app


