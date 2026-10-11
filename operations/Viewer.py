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
for path in (_PROJECT_ROOT, _OPERATIONS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from _common import with_mongo
from session import find_session, host_user_id, session_query, session_records, validate_session_id


@with_mongo
def resolve_viewer(*, session_id: str, client: Any) -> dict[str, Any]:
    """Return the current viewer (last joiner) for a session."""
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required")
    record = session_records(client).find_one(session_query(session_id))
    if not record:
        raise LookupError("Session not found")
    return {
        "sessionID": session_id.strip(),
        "hostUserID": host_user_id(record),
        "Host_UserID": host_user_id(record),
        "viewerUserID": record.get("viewerUserID") or record.get("Viewer_UserID"),
        "role": "viewer" if record.get("viewerUserID") else None,
    }


def peer_search(*, session_id: str, searcher_user_id: str) -> dict[str, Any]:
    found = find_session(session_id=session_id)
    found["searcherUserID"] = searcher_user_id
    return found


def host_controls_session(*, session_id: str, acting_user_id: str, record: dict[str, Any]) -> bool:
    """Host retains full session control via sessionControl settings."""
    return host_user_id(record) == acting_user_id
