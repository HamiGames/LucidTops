""" this is the UserHandler for the LucidTops system, used by the NodeUser for existing UserID's in the UserDB
operations:
- accepts if a UserID and correct IDToken for the UserID is provided
- allows the UserID access to the Sessions system via the API routes (FastAPI)
- allows the UserID access to the Operations system via the API routes (FastAPI)(selected operations only)
- allows the UserID access to the PaySystems system via the API routes (FastAPI)(incoming payments only)
- allows the UserID access to the Blockchain system via the API routes (FastAPI)(ledger operations only)
- is accessed via the Frontend (javascript) via the API routes (FastAPI)
RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from _common import (
    get_mongo_client,
    operator_kwargs_from_payload,
    require_operations_operator,
    user_accounts_collection,
    verify_user_id_token,
    with_mongo,
)
from operations_secrets import resolve_operations_query_limit


@with_mongo
def verify_user_credentials(
    *,
    user_id: str,
    token_id: str,
    client: Any,
) -> dict[str, Any]:
    """Check LucidTopsUserDB for UserID and TokenID (fixes.txt §7.5)."""
    if not verify_user_id_token(user_id=user_id, token_id=token_id, client=client):
        raise PermissionError("UserID / TokenID verification failed against LucidTopsUserDB")
    collection = user_accounts_collection(client)
    record = collection.find_one({"UserID": user_id}, {"_id": 0, "password": 0})
    if not record:
        raise LookupError("UserID not found in LucidTopsUserDB")
    return {
        "UserID": user_id,
        "TokenID_valid": True,
        "email": record.get("email"),
        "tier": record.get("tier") or record.get("Tier_selected"),
        "status": "verified",
    }


@with_mongo
def require_node_operator_user_check(
    *,
    operator_payload: Any,
    user_id: str,
    token_id: str,
    client: Any,
) -> dict[str, Any]:
    """
    NodeUsers (and other registered operators) must pass LucidTopsNodeDB gate,
    then verify the target UserID+TokenID in LucidTopsUserDB.
    """
    operator = require_operations_operator(
        client=client,
        **operator_kwargs_from_payload(operator_payload),
    )
    user = verify_user_credentials(
        user_id=user_id,
        token_id=token_id,
        client=client,
    )
    return {"operator": operator, "user": user}


@with_mongo
def find_user_by_id(
    *,
    operator_payload: Any,
    user_id: str,
    client: Any,
) -> dict[str, Any]:
    require_operations_operator(
        client=client,
        **operator_kwargs_from_payload(operator_payload),
    )
    collection = user_accounts_collection(client)
    record = collection.find_one({"UserID": user_id}, {"_id": 0, "password": 0})
    if not record:
        raise LookupError("UserID not found in LucidTopsUserDB")
    return record


@with_mongo
def list_users_for_operator(
    *,
    operator_payload: Any,
    client: Any,
) -> dict[str, Any]:
    require_operations_operator(
        client=client,
        **operator_kwargs_from_payload(operator_payload),
    )
    collection = user_accounts_collection(client)
    records = list(
        collection.find({}, {"_id": 0, "password": 0}).limit(resolve_operations_query_limit())
    )
    return {"records": records, "count": len(records)}


def verify_user_id_and_token(*, user_id: str, token_id: str) -> dict[str, Any]:
    """Standalone UserID+TokenID check used by session/user routes."""
    client = get_mongo_client()
    if client is None:
        raise RuntimeError("Master server database is unavailable")
    try:
        return verify_user_credentials(user_id=user_id, token_id=token_id, client=client)
    finally:
        client.close()
