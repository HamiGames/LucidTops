""" the viewer system for the lucid projects
defining the viewer in a SessionID context:
the viewer is the peer that last joins the session (SessionID)
the viewer will use the peer-search system to find the peer.
the UserID who requests the creation of a session id is the Host in the session (SessionID)
the Host will have complete control over the actions during a session (SessionID)
this is via the session control settings (settings.js)

features:
- determines and lables the peer who is the viewer in a SessionID context. (peer to use peer-search system with manual input of SessionID)
- is all the sharescreen code required to view the screen of the peer who is the viewer in a SessionID context.
- is limited by the UserHost control settings (settings.js)
- the UserHost is the peer who created the SessionID and has complete control over the actions during a session (SessionID).
- the UserHost is required to accept the share screen request from the viewer.
- the UserHost is required to accept all actions from the viewer.


RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_OPERATIONS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _OPERATIONS_DIR.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
for path in (_PROJECT_ROOT, _OPERATIONS_DIR, _BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

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
