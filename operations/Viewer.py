""" the viewer system for the lucid projects
defining the viewer in a SessionID context:
the viewer is the peer that last joins the session (SessionID)
the viewer will use the peer-search system to find the peer.

the UserID who requests the creation of a session id is the Host in the session (SessionID)
the Host will have complete control over the actions during a session (SessionID)
this is via the session control settings (settings.js)
"""

from __future__ import annotations

from typing import Any

from _common import SESSION_RECORDS_COLLECTION, get_master_db, with_mongo
from sessions.searchpeer import peer_search
from sessions.SessionCore import find_session, validate_session_id


@with_mongo
def resolve_viewer(*, session_id: str, client: Any) -> dict[str, Any]:
    """Return the current viewer (last joiner) for a session."""
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required")
    record = get_master_db(client)[SESSION_RECORDS_COLLECTION].find_one(
        {"sessionID": session_id.strip()}
    )
    if not record:
        raise LookupError("Session not found")
    return {
        "sessionID": session_id.strip(),
        "hostUserID": record.get("hostUserID"),
        "viewerUserID": record.get("viewerUserID"),
        "role": "viewer" if record.get("viewerUserID") else None,
    }


def host_controls_session(*, session_id: str, acting_user_id: str, record: dict[str, Any]) -> bool:
    """Host retains full session control via sessionControl settings."""
    return record.get("hostUserID") == acting_user_id
