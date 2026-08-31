""" this is a script that will allow future development in the lucid system
including: 
-the development of new features and the improvement of existing features
- the creation of new applications in the lucid system
- the cross over for the LucidToken system to the crypto world (crypto wallet address)
- the cross over for the LucidToken system to the blockchain world (blockchain address)
- the cross over for the LucidToken system to the NFT world (NFT address)
- the cross over for the LucidToken system to the game world (game address)
- the cross over for the LucidToken system to the social media world (social media address)
- the cross over for the LucidToken system to the news world (news address)
- the cross over for the LucidToken system to the education world (education address)
- the cross over for the LucidToken system to the health world (health address)
- the cross over for the LucidToken system to the finance world (finance address)
- the cross over for the LucidToken system to the real estate world (real estate address)
- the cross over for the LucidToken system to the travel world (travel address)
- the cross over for the LucidToken system to the food and drink world (food and drink address)
- the cross over for the LucidToken system to the art world (art address)
- the cross over for the LucidToken system to the music world (music address)
- the cross over for the LucidToken system to the video world (video address)
- the cross over for the LucidToken system to the photography world (photography address)
- the cross over for the LucidToken system to the writing world (writing address)
- the cross over for the LucidToken system to the programming world (programming address)
- the cross over for the LucidToken system to the design world (design address)
- the cross over for the LucidToken system to the marketing world (marketing address)
- the cross over for the LucidToken system to the sales world (sales address)
- the cross over for the LucidToken system to the customer service world (customer service address)
- and more...

needs to include:
- potential API routes to be created for the chip-in system
- create a script to handle the chip-in system

"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from _common import (
    APIRouter,
    BaseModel,
    Field,
    LUCID_LEDGER_COLLECTION,
    get_master_db,
    get_mongo_client,
    handle_operations_error,
    tor_envelope,
    utc_now,
    verify_id_token,
    with_mongo,
)
from config import LUCID_TOPS_ROOT, SECRETS_DIR

CHIP_IN_COLLECTION = "chip_in_records"
CHIP_IN_CROSSOVER_COLLECTION = "chip_in_crossovers"

CHIP_IN_ROUTES: tuple[str, ...] = (
    "/chip-in-create",
    "/chip-in-find",
    "/chip-in-connect",
    "/chip-in-register",
    "/chip-in-list",
    "/chip-in-status",
    "/chip-in-record",
    "/chip-in-transfer",
    "/chip-in-control",
)

CROSSOVER_WORLDS: tuple[str, ...] = (
    "crypto_wallet",
    "blockchain",
    "nft",
    "game",
    "social_media",
    "news",
    "education",
    "health",
    "finance",
    "real_estate",
    "travel",
    "food_and_drink",
    "art",
    "music",
    "video",
    "photography",
    "writing",
    "programming",
    "design",
    "marketing",
    "sales",
    "customer_service",
)

CHIP_IN_STATUSES: frozenset[str] = frozenset(
    {"draft", "active", "connected", "archived"}
)

PAYMENTS_SECRETS_FILE = Path(
    os.environ.get("PAYMENTS_SECRETS_FILE", SECRETS_DIR / "payments.secrets")
)


def _generate_chip_in_id() -> str:
    return secrets.token_hex(6)


def _normalize_world(world: str) -> str:
    normalized = world.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in CROSSOVER_WORLDS:
        return normalized
    aliases = {
        "crypto": "crypto_wallet",
        "wallet": "crypto_wallet",
        "social": "social_media",
        "food": "food_and_drink",
        "customer_service_world": "customer_service",
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"Unsupported crossover world: {world}")


def load_payments_wallet_address() -> str | None:
    """Load wallet address from payments.secrets (Connect_wallet.py alignment)."""
    if PAYMENTS_SECRETS_FILE.exists():
        for line in PAYMENTS_SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, value = stripped.split("=", 1)
                if key.strip().upper() in {
                    "WALLET_ADDRESS",
                    "CRYPTO_WALLET_ADDRESS",
                    "TRON_WALLET_ADDRESS",
                    "XRP_WALLET_ADDRESS",
                }:
                    address = value.strip()
                    if address:
                        return address
    env_address = os.environ.get("PAYMENTS_WALLET_ADDRESS", "").strip()
    return env_address or None


@with_mongo
def create_chip_in(
    *,
    user_id: str,
    id_token: str,
    title: str,
    description: str,
    crossover_world: str,
    feature_tags: list[str] | None = None,
    client: Any,
) -> dict[str, Any]:
    if not verify_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")
    world = _normalize_world(crossover_world)
    chip_in_id = _generate_chip_in_id()
    now = utc_now()
    record = {
        "chipInID": chip_in_id,
        "UserID": user_id,
        "title": title.strip(),
        "description": description.strip(),
        "crossover_world": world,
        "feature_tags": feature_tags or [],
        "status": "draft",
        "external_address": None,
        "created_at": now,
        "updated_at": now,
    }
    get_master_db(client)[CHIP_IN_COLLECTION].insert_one(record)
    return {
        "chipInID": chip_in_id,
        "UserID": user_id,
        "crossover_world": world,
        "status": "draft",
    }


@with_mongo
def find_chip_in(*, chip_in_id: str, client: Any) -> dict[str, Any]:
    record = get_master_db(client)[CHIP_IN_COLLECTION].find_one(
        {"chipInID": chip_in_id.strip()}, {"_id": 0}
    )
    if not record:
        raise LookupError("Chip-in record not found")
    return record


@with_mongo
def connect_chip_in(
    *,
    chip_in_id: str,
    user_id: str,
    id_token: str,
    external_address: str,
    client: Any,
) -> dict[str, Any]:
    if not verify_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")
    if not external_address or not external_address.strip():
        raise ValueError("external_address is required")
    record = get_master_db(client)[CHIP_IN_COLLECTION].find_one(
        {"chipInID": chip_in_id.strip()}
    )
    if not record:
        raise LookupError("Chip-in record not found")
    if record.get("UserID") != user_id:
        raise PermissionError("Only the chip-in owner may connect an address")
    now = utc_now()
    address = external_address.strip()
    get_master_db(client)[CHIP_IN_COLLECTION].update_one(
        {"chipInID": chip_in_id.strip()},
        {
            "$set": {
                "external_address": address,
                "status": "connected",
                "updated_at": now,
            }
        },
    )
    crossover = {
        "chipInID": chip_in_id.strip(),
        "crossover_world": record.get("crossover_world"),
        "external_address": address,
        "UserID": user_id,
        "verified": False,
        "created_at": now,
        "updated_at": now,
    }
    get_master_db(client)[CHIP_IN_CROSSOVER_COLLECTION].update_one(
        {"chipInID": chip_in_id.strip()},
        {"$set": crossover},
        upsert=True,
    )
    return {"chipInID": chip_in_id.strip(), "status": "connected", "external_address": address}


@with_mongo
def register_crossover_address(
    *,
    user_id: str,
    id_token: str,
    crossover_world: str,
    external_address: str,
    client: Any,
) -> dict[str, Any]:
    if not verify_id_token(user_id=user_id, id_token=id_token, client=client):
        raise PermissionError("User authentication failed")
    world = _normalize_world(crossover_world)
    now = utc_now()
    record = {
        "UserID": user_id,
        "crossover_world": world,
        "external_address": external_address.strip(),
        "address_type": world,
        "entity_type": "user",
        "entity_id": user_id,
        "verified": False,
        "created_at": now,
        "updated_at": now,
    }
    get_master_db(client)[CHIP_IN_CROSSOVER_COLLECTION].update_one(
        {"UserID": user_id, "crossover_world": world},
        {"$set": record},
        upsert=True,
    )
    return record


def list_crossover_worlds() -> dict[str, Any]:
    return {
        "worlds": list(CROSSOVER_WORLDS),
        "count": len(CROSSOVER_WORLDS),
    }


@with_mongo
def chip_in_status(*, chip_in_id: str, client: Any) -> dict[str, Any]:
    record = find_chip_in(chip_in_id=chip_in_id, client=client)
    crossover = get_master_db(client)[CHIP_IN_CROSSOVER_COLLECTION].find_one(
        {"chipInID": chip_in_id.strip()}, {"_id": 0}
    )
    return {
        "chipInID": chip_in_id.strip(),
        "status": record.get("status"),
        "crossover_world": record.get("crossover_world"),
        "external_address": record.get("external_address"),
        "crossover": crossover,
    }


@with_mongo
def record_chip_in_event(
    *,
    chip_in_id: str,
    user_id: str,
    action: str,
    client: Any,
) -> dict[str, Any]:
    record = get_master_db(client)[CHIP_IN_COLLECTION].find_one(
        {"chipInID": chip_in_id.strip()}
    )
    if not record:
        raise LookupError("Chip-in record not found")
    events = list(record.get("events") or [])
    event = {"action": action, "userID": user_id, "timestamp": utc_now()}
    events.append(event)
    get_master_db(client)[CHIP_IN_COLLECTION].update_one(
        {"chipInID": chip_in_id.strip()},
        {"$set": {"events": events, "updated_at": utc_now()}},
    )
    return {"chipInID": chip_in_id.strip(), "event_count": len(events)}


@with_mongo
def transfer_chip_in_to_ledger(*, chip_in_id: str, client: Any) -> dict[str, Any]:
    record = find_chip_in(chip_in_id=chip_in_id, client=client)
    if record.get("status") != "connected":
        raise ValueError("Chip-in must be connected before ledger transfer")
    payload = {
        "chipInID": chip_in_id.strip(),
        "crossover_world": record.get("crossover_world"),
        "external_address": record.get("external_address"),
        "record_type": "chip_in_crossover",
        "created_at": utc_now(),
    }
    get_master_db(client)[LUCID_LEDGER_COLLECTION].insert_one(payload)
    return payload


@with_mongo
def get_chip_in_control(*, chip_in_id: str, user_id: str, client: Any) -> dict[str, Any]:
    record = find_chip_in(chip_in_id=chip_in_id, client=client)
    if record.get("UserID") != user_id:
        raise PermissionError("Only the chip-in owner may view control settings")
    wallet = load_payments_wallet_address()
    return {
        "chipInID": chip_in_id.strip(),
        "immutable": True,
        "crossover_world": record.get("crossover_world"),
        "payments_wallet_configured": wallet is not None,
        "tor_only": True,
        "development_ready": True,
    }


def handle_chip_in(
    action: str,
    *,
    user_id: str | None = None,
    id_token: str | None = None,
    chip_in_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    crossover_world: str | None = None,
    external_address: str | None = None,
    feature_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Main chip-in script handler for Tor-hosted master server operations."""
    if action == "list-worlds":
        return list_crossover_worlds()
    if action == "wallet-config":
        address = load_payments_wallet_address()
        return {
            "payments_secrets_file": str(PAYMENTS_SECRETS_FILE.as_posix()),
            "wallet_configured": address is not None,
            "lucid_tops_root": str(LUCID_TOPS_ROOT.as_posix()),
        }
    if not user_id or not id_token:
        raise ValueError("UserID and IDToken are required for chip-in actions")

    if action == "create":
        if not title or not description or not crossover_world:
            raise ValueError("title, description, and crossover_world are required")
        return create_chip_in(
            user_id=user_id,
            id_token=id_token,
            title=title,
            description=description,
            crossover_world=crossover_world,
            feature_tags=feature_tags,
        )
    if not chip_in_id:
        raise ValueError("chipInID is required")

    if action == "find":
        return find_chip_in(chip_in_id=chip_in_id)
    if action == "connect":
        if not external_address:
            raise ValueError("external_address is required")
        return connect_chip_in(
            chip_in_id=chip_in_id,
            user_id=user_id,
            id_token=id_token,
            external_address=external_address,
        )
    if action == "register":
        if not crossover_world or not external_address:
            raise ValueError("crossover_world and external_address are required")
        return register_crossover_address(
            user_id=user_id,
            id_token=id_token,
            crossover_world=crossover_world,
            external_address=external_address,
        )
    if action == "status":
        return chip_in_status(chip_in_id=chip_in_id)
    if action == "record":
        return record_chip_in_event(
            chip_in_id=chip_in_id,
            user_id=user_id,
            action="chip-in-record",
        )
    if action == "transfer":
        return transfer_chip_in_to_ledger(chip_in_id=chip_in_id)
    if action == "control":
        return get_chip_in_control(chip_in_id=chip_in_id, user_id=user_id)
    raise ValueError(f"Unsupported chip-in action: {action}")


if BaseModel is not object:

    class ChipInAuthPayload(BaseModel):
        user_id: str = Field(..., alias="UserID")
        id_token: str = Field(..., alias="IDToken")

        model_config = {"populate_by_name": True}

    class ChipInCreatePayload(ChipInAuthPayload):
        title: str = Field(..., min_length=1)
        description: str = Field(..., min_length=1)
        crossover_world: str = Field(..., min_length=1)
        feature_tags: list[str] | None = None

    class ChipInScopedPayload(ChipInAuthPayload):
        chip_in_id: str = Field(..., alias="chipInID", min_length=1)

        model_config = {"populate_by_name": True}

    class ChipInConnectPayload(ChipInScopedPayload):
        external_address: str = Field(..., min_length=1)

    class ChipInRegisterPayload(ChipInAuthPayload):
        crossover_world: str = Field(..., min_length=1)
        external_address: str = Field(..., min_length=1)

    class ChipInFindPayload(BaseModel):
        chip_in_id: str = Field(..., alias="chipInID", min_length=1)

        model_config = {"populate_by_name": True}


def _route_handler(route: str, payload: Any) -> dict[str, Any]:
    try:
        if route == "/chip-in-create":
            result = create_chip_in(
                user_id=payload.user_id,
                id_token=payload.id_token,
                title=payload.title,
                description=payload.description,
                crossover_world=payload.crossover_world,
                feature_tags=payload.feature_tags,
            )
        elif route == "/chip-in-find":
            result = find_chip_in(chip_in_id=payload.chip_in_id)
        elif route == "/chip-in-connect":
            result = connect_chip_in(
                chip_in_id=payload.chip_in_id,
                user_id=payload.user_id,
                id_token=payload.id_token,
                external_address=payload.external_address,
            )
        elif route == "/chip-in-register":
            result = register_crossover_address(
                user_id=payload.user_id,
                id_token=payload.id_token,
                crossover_world=payload.crossover_world,
                external_address=payload.external_address,
            )
        elif route == "/chip-in-list":
            result = list_crossover_worlds()
        elif route == "/chip-in-status":
            result = chip_in_status(chip_in_id=payload.chip_in_id)
        elif route == "/chip-in-record":
            result = record_chip_in_event(
                chip_in_id=payload.chip_in_id,
                user_id=payload.user_id,
                action="chip-in-record",
            )
        elif route == "/chip-in-transfer":
            result = transfer_chip_in_to_ledger(chip_in_id=payload.chip_in_id)
        elif route == "/chip-in-control":
            result = get_chip_in_control(
                chip_in_id=payload.chip_in_id,
                user_id=payload.user_id,
            )
        else:
            raise ValueError(f"Unsupported chip-in route: {route}")
        return tor_envelope(route=route, subsystem="chip-in-system", payload=result)
    except Exception as exc:
        handle_operations_error(exc)
        raise


def create_chip_in_router(*, prefix: str = "") -> Any:
    if APIRouter is None:
        raise RuntimeError("fastapi is required to create chip-in routes")
    router = APIRouter(prefix=prefix, tags=["chip-in-system"])

    @router.post("/chip-in-create")
    def chip_in_create(payload: ChipInCreatePayload) -> dict[str, Any]:
        return _route_handler("/chip-in-create", payload)

    @router.post("/chip-in-find")
    def chip_in_find(payload: ChipInFindPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-find", payload)

    @router.post("/chip-in-connect")
    def chip_in_connect(payload: ChipInConnectPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-connect", payload)

    @router.post("/chip-in-register")
    def chip_in_register(payload: ChipInRegisterPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-register", payload)

    @router.get("/chip-in-list")
    @router.post("/chip-in-list")
    def chip_in_list() -> dict[str, Any]:
        return _route_handler("/chip-in-list", None)

    @router.post("/chip-in-status")
    def chip_in_status_route(payload: ChipInFindPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-status", payload)

    @router.post("/chip-in-record")
    def chip_in_record(payload: ChipInScopedPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-record", payload)

    @router.post("/chip-in-transfer")
    def chip_in_transfer(payload: ChipInFindPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-transfer", payload)

    @router.post("/chip-in-control")
    def chip_in_control(payload: ChipInScopedPayload) -> dict[str, Any]:
        return _route_handler("/chip-in-control", payload)

    return router


def register_chip_in_routes(app: Any, *, api_prefix: str = "/api/v1") -> None:
    app.include_router(create_chip_in_router(prefix=api_prefix))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LucidTops chip-in system handler")
    parser.add_argument(
        "action",
        choices=[
            "list-worlds",
            "wallet-config",
            "create",
            "find",
            "connect",
            "register",
            "status",
            "record",
            "transfer",
            "control",
        ],
    )
    parser.add_argument("--user-id", dest="user_id", default=None)
    parser.add_argument("--id-token", dest="id_token", default=None)
    parser.add_argument("--chip-in-id", dest="chip_in_id", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--crossover-world", dest="crossover_world", default=None)
    parser.add_argument("--external-address", dest="external_address", default=None)
    parser.add_argument("--feature-tag", dest="feature_tags", action="append", default=None)
    args = parser.parse_args(argv)

    try:
        result = handle_chip_in(
            args.action,
            user_id=args.user_id,
            id_token=args.id_token,
            chip_in_id=args.chip_in_id,
            title=args.title,
            description=args.description,
            crossover_world=args.crossover_world,
            external_address=args.external_address,
            feature_tags=args.feature_tags,
        )
    except (ValueError, PermissionError, LookupError, RuntimeError) as exc:
        print(f"chip-in error: {exc}", file=sys.stderr)
        return 1

    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
