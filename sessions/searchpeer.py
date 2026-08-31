""" using the session ID to search for the peer to peer remote desktop sharing session, before entering the session system
requirements:
- the search peer is used to search for the peer to peer remote desktop sharing session before entering the session
- the search peer is used to search for the peer to peer remote desktop sharing session by the session ID
- the user ID must not be viewable to the peer
- the session ID must be valid and secure
- a IDtoken from each peer must be present in the node-operation-database and the master server database
- the IDtoken must be valid and secure
- the IDtoken must be in the correct format
- the IDtoken must be in the correct location
- the IDtoken must be in the correct state

 """

from __future__ import annotations

import hashlib
from typing import Any

from sessions._common import (
    get_master_db,
    session_records_collection,
    utc_now,
    verify_node_id_token,
    verify_user_id_token,
    with_mongo,
)
from sessions.SessionCore import find_session
from sessions.sessionID import validate_session_id


def _mask_user_id(user_id: str) -> str:
    """Return unreadable masked UserID for peer-facing responses."""
    digest = hashlib.sha512(user_id.encode("utf-8")).hexdigest()
    return f"MASKED:{digest[:16]}"


def _verify_participant_tokens(record: dict[str, Any], client: Any) -> bool:
    db = get_master_db(client)
    for user_id in record.get("userIDs") or []:
        user_token = db.id_tokens.find_one({"entity": "user", "UserID": user_id})
        if user_token is None:
            user_token = db.users.find_one({"UserID": user_id})
        if user_token is None or not user_token.get("IDToken"):
            return False
    return True


@with_mongo
def search_peer(
    *,
    session_id: str,
    searcher_user_id: str,
    searcher_id_token: str | None = None,
    client: Any,
) -> dict[str, Any]:
    """Search for a peer session by sessionID; peer UserIDs are masked."""
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required for peer search")
    if searcher_id_token and not verify_user_id_token(
        user_id=searcher_user_id,
        id_token=searcher_id_token,
        client=client,
    ):
        raise PermissionError("Searcher IDToken authentication failed")

    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")
    if not _verify_participant_tokens(record, client):
        raise PermissionError("Participant IDTokens are missing or invalid")

    session_info = find_session(session_id=session_id, client=client)
    return {
        "sessionID": session_info["sessionID"],
        "sessionStatus": session_info.get("sessionStatus"),
        "participant_count": session_info.get("participant_count"),
        "all_agreed": session_info.get("all_agreed", False),
        "hostUserID": _mask_user_id(str(session_info.get("hostUserID", ""))),
        "viewerUserID": (
            _mask_user_id(str(session_info["viewerUserID"]))
            if session_info.get("viewerUserID")
            else None
        ),
        "userIDs": [_mask_user_id(str(uid)) for uid in session_info.get("userIDs", [])],
        "searcherUserID": _mask_user_id(searcher_user_id),
        "peer_search": "session-find",
        "id_tokens_verified": True,
        "timestamp": utc_now(),
    }


@with_mongo
def peer_search(*, session_id: str, searcher_user_id: str, client: Any) -> dict[str, Any]:
    """Alias for search_peer used by session-find API routes."""
    return search_peer(
        session_id=session_id,
        searcher_user_id=searcher_user_id,
        client=client,
    )


@with_mongo
def verify_peer_id_token(
    *,
    user_id: str | None = None,
    node_user_id: str | None = None,
    id_token: str,
    client: Any,
) -> dict[str, Any]:
    """Validate an IDToken against master server and node-operation-database records."""
    if user_id:
        valid = verify_user_id_token(user_id=user_id, id_token=id_token, client=client)
        entity = "user"
        entity_id = user_id
    elif node_user_id:
        valid = verify_node_id_token(
            node_user_id=node_user_id, id_token=id_token, client=client
        )
        entity = "node"
        entity_id = node_user_id
    else:
        raise ValueError("UserID or NodeUserID is required")

    return {
        "entity": entity,
        "entity_id": entity_id,
        "IDToken_valid": valid,
        "timestamp": utc_now(),
    }
