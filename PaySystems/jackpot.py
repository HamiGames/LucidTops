""" the jackpot system for the lucid projects
values:
- the first jackpot must be more than $2000 USD (minimum payout value for entire system)
- all jackpot goals will increase by 5% of the previous jackpot goal (1000% is the maximum increase)
- all none collected will not be added to the jackpot value (income) the uncollected jackpot value will stay in holding until the jackpot is collected.
- each token will have a unique LucidTokenID (LucidTokenID) that is used to identify the token and its owner.
- if token is not readable from the blockchain, it will be removed from the jackpot value (income) and the lucidTokenID will be listed in the uncollected archive on the master server database
- the payout value recieved is soley dependent on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the lucidTokens balance is calculated based on the LucidLedger system and LucidWallet system
- the balance excludes the account starting balance (of set amount of crypto currency)
- the payout value will never exceed the starting balance of the account (to prevent overpaying)

the jackpot function is not a winner takes all system, it is a shared payout system where the payout value is divided among the top 100 users based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
the payout value is calculated based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID

all tier payments will add to the jackpot value (income)
all jackpot payouts will be deducted from the jackpot value (expense)
all jackpot goal va
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


def jackpot_rules() -> dict[str, Any]:
    load_payments_secrets()
    return {
        "minimum_payout_usd": require_payment_secret_float("JACKPOT_MIN_PAYOUT_USD"),
        "goal_increase_percent": require_payment_secret_float("JACKPOT_GOAL_INCREASE_PERCENT"),
        "max_increase_percent": require_payment_secret_float("JACKPOT_MAX_INCREASE_PERCENT"),
        "top_users": require_payment_secret_int("JACKPOT_TOP_USERS"),
    }


def next_jackpot_goal(previous_goal: float) -> float:
    rules = jackpot_rules()
    increase = previous_goal * (rules["goal_increase_percent"] / 100.0)
    max_increase = previous_goal * (rules["max_increase_percent"] / 100.0)
    capped = min(increase, max_increase)
    nxt = previous_goal + capped
    if nxt < rules["minimum_payout_usd"]:
        raise RuntimeError(
            "computed jackpot goal below JACKPOT_MIN_PAYOUT_USD — check payments.secrets"
        )
    return nxt


def calculate_shared_payout(
    *,
    jackpot_value: float,
    token_balances: dict[str, float],
) -> dict[str, Any]:
    rules = jackpot_rules()
    if jackpot_value < rules["minimum_payout_usd"]:
        raise RuntimeError("jackpot_value below JACKPOT_MIN_PAYOUT_USD")
    ranked = sorted(
        ((uid, float(bal)) for uid, bal in token_balances.items() if float(bal) > 0),
        key=lambda item: item[1],
        reverse=True,
    )[: rules["top_users"]]
    total_tokens = sum(bal for _, bal in ranked)
    if total_tokens <= 0:
        raise RuntimeError("no positive LucidToken balances for jackpot payout")
    payouts = {
        uid: jackpot_value * (bal / total_tokens)
        for uid, bal in ranked
    }
    return {
        "jackpot_value": jackpot_value,
        "top_users": rules["top_users"],
        "payouts": payouts,
        "calculated_at": utc_now(),
    }
