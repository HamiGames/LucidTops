""" this script is the architecture for the tier system in the LucidTops system.
purpose:
1. to define the tiers and the requirements for each tier.
2. to define how the tiers are selected by the User.
3. to define how the tiers are stored in the database.
4. to define how the tiers are retrieved from the database.
5. to define the costs of each tier.

tiers:
- Tier 1: $0/month [free tier][int: 1]
- Tier 2: $10/month [basic tier][int: 2]
- Tier 3: $20/month [premium tier][int: 3]
- Tier 4: $30/month [enterprise tier][int: 4]
- Tier 5: $40/month [multi-console access][int: 5]
- Tier 6: $70/month [enterprise tier][int: 6]
- Tier 7: $150/month [ultimate tier][int: 7]
- Tier 8: $0/month [MasterUser tier][int: 8]

tier 1 limitations: [no billing]
- 5 sessions per month
- single console access

tier 2 limitations: [billed monthly]
- 15 sessions per month
- single console access

tier 3 limitations: [billed monthly]
- 30 sessions per month
- single console access

tier 4 limitations: [billed monthly]
- 50 sessions per month
- single console access

tier 5 limitations: [billed monthly]
- 100 sessions per month
- multi-console access [1-5 consoles]

tier 6 limitations: [billed monthly]
- unlimited sessions
- multi-console access [1-5 consoles]

tier 7 limitations: [billed monthly]
- unlimited sessions
- multi-console access [1-10 consoles]

tier 8 limitations: [no billing]
- unlimited sessions
- max of 5 users can hold this tier
- only a single console can hold this tier
- this tier is granted by the AdminUser.
- this tier requires a special Tier_ID (creates by MasterServer, MasterUser_ID.txt) 

"""

from __future__ import annotations

from typing import Any

from config import (
    get_config_int,
    get_config_list,
    get_config_value,
    get_config_value_optional,
    get_master_db,
    get_mongo_client,
    utc_now,
)


def tier_ids() -> tuple[int, ...]:
    raw = get_config_list("TIER_IDS")
    ids: list[int] = []
    for item in sorted(raw, key=lambda value: int(value)):
        try:
            ids.append(int(item))
        except ValueError as exc:
            raise RuntimeError(f"TIER_IDS entry must be an integer: {item}") from exc
    if not ids:
        raise RuntimeError("TIER_IDS is empty")
    return tuple(ids)


def tiers_collection_name() -> str:
    return get_config_value("TIER_USERS_COLLECTION")


def master_user_tier_id_file() -> str:
    return get_config_value("MASTER_USER_TIER_ID_FILE")


def _tier_key(tier: int, suffix: str) -> str:
    return f"TIER_{tier}_{suffix}"


def load_tier_definition(tier: int) -> dict[str, Any]:
    """Load one tier definition exclusively from env / config.secrets."""
    if tier not in tier_ids():
        raise ValueError(f"tier {tier} is not configured in TIER_IDS")

    sessions_raw = get_config_value(_tier_key(tier, "SESSIONS_PER_MONTH"))
    unlimited = sessions_raw.strip().lower() in {"unlimited", "-1"}
    max_holders_raw = get_config_value_optional(_tier_key(tier, "MAX_HOLDERS"))
    max_holders = int(max_holders_raw) if max_holders_raw else None

    return {
        "tier": tier,
        "name": get_config_value(_tier_key(tier, "NAME")),
        "price_monthly": get_config_value(_tier_key(tier, "PRICE_MONTHLY")),
        "currency": get_config_value(_tier_key(tier, "CURRENCY")),
        "billing": get_config_value(_tier_key(tier, "BILLING")),
        "sessions_per_month": None if unlimited else int(sessions_raw),
        "unlimited_sessions": unlimited,
        "max_consoles": get_config_int(_tier_key(tier, "MAX_CONSOLES")),
        "admin_granted": get_config_value(_tier_key(tier, "ADMIN_GRANTED")).lower()
        in {"1", "true", "yes"},
        "max_holders": max_holders,
        "requires_master_tier_id": get_config_value(
            _tier_key(tier, "REQUIRES_MASTER_TIER_ID")
        ).lower()
        in {"1", "true", "yes"},
    }


def list_tier_definitions() -> list[dict[str, Any]]:
    return [load_tier_definition(tier) for tier in tier_ids()]


def get_tier_cost(tier: int) -> dict[str, str]:
    definition = load_tier_definition(tier)
    return {
        "tier": str(definition["tier"]),
        "price_monthly": str(definition["price_monthly"]),
        "currency": str(definition["currency"]),
        "billing": str(definition["billing"]),
    }


def validate_tier_selection(tier: int, *, admin_granted: bool = False) -> dict[str, Any]:
    definition = load_tier_definition(tier)
    if definition["admin_granted"] and not admin_granted:
        raise PermissionError(f"tier {tier} requires AdminUser grant")
    if definition["requires_master_tier_id"]:
        path = master_user_tier_id_file()
        if not path:
            raise RuntimeError("MASTER_USER_TIER_ID_FILE missing at time of operation")
    return definition


def store_user_tier(
    *,
    user_id: str,
    tier: int,
    admin_granted: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    cleaned_user = user_id.strip()
    if not cleaned_user:
        raise ValueError("user_id must not be empty")
    definition = validate_tier_selection(tier, admin_granted=admin_granted)

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        db = get_master_db(mongo)
        collection = tiers_collection_name()
        if definition.get("max_holders") is not None:
            holders = db[collection].count_documents({"tier": tier, "active": True})
            existing = db[collection].find_one({"UserID": cleaned_user, "tier": tier})
            if holders >= int(definition["max_holders"]) and existing is None:
                raise PermissionError(
                    f"tier {tier} max holders reached ({definition['max_holders']})"
                )

        record = {
            "UserID": cleaned_user,
            "tier": tier,
            "tier_name": definition["name"],
            "price_monthly": definition["price_monthly"],
            "currency": definition["currency"],
            "billing": definition["billing"],
            "sessions_per_month": definition["sessions_per_month"],
            "unlimited_sessions": definition["unlimited_sessions"],
            "max_consoles": definition["max_consoles"],
            "admin_granted": bool(definition["admin_granted"]),
            "active": True,
            "updated_at": utc_now(),
        }
        db[collection].update_one(
            {"UserID": cleaned_user},
            {"$set": record, "$setOnInsert": {"created_at": utc_now()}},
            upsert=True,
        )
        return record
    finally:
        if client is None:
            mongo.close()


def retrieve_user_tier(
    user_id: str,
    *,
    client: Any | None = None,
) -> dict[str, Any] | None:
    cleaned_user = user_id.strip()
    if not cleaned_user:
        raise ValueError("user_id must not be empty")

    mongo = client if client is not None else get_mongo_client()
    if mongo is None:
        raise RuntimeError("Master server database is unavailable")

    try:
        record = get_master_db(mongo)[tiers_collection_name()].find_one(
            {"UserID": cleaned_user}
        )
        if not record:
            return None
        payload = dict(record)
        payload.pop("_id", None)
        return payload
    finally:
        if client is None:
            mongo.close()


def select_tier_for_user(
    *,
    user_id: str,
    tier: int,
    admin_granted: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    """User-facing tier selection — validates limits then persists selection."""
    return store_user_tier(
        user_id=user_id,
        tier=tier,
        admin_granted=admin_granted,
        client=client,
    )
