""" the API route to load the userID's settings prferances from the Fontend/settings.js file
the sessionControl API route:
- the sessionControl API route is used to load the userID's settings prferances from the Fontend/settings.js file
- will block all attempts of modification from connected userID
- will block all attempts of modification from connected NodeUser
- will block all attempts of modification from connected master server
- will block all attempts of modification from connected system
- will block all attempts of modification from connected network
- will block all attempts of modification from connected internet
- will block all attempts of modification from connected world
- will block all attempts of modification from connected universe
- will create an absolute selection of control related settings for the session system and peer to peer remote desktop sharing session

controls include (session control settings):
- mouse control
- keyboard control
- audio control
- video control
- screen control
- file transfer control
- file download control
- file upload control
- file delete control
- file rename control
- file move control
- file copy control
- file paste control
- file zip control
- file unzip control
- file sync control
- file transfer location control
- peer to peer remote desktop sharing session control

must include:
- the ability to edit the settings based on the selections in the settings.js
- the control settings must be absolute in the session system
- the viewers controls will not modify the controls of the host
- the host will maintain the superior functions and controls while in the sessionID in the session system
- the session control settings will not be force removed while in a sessionID

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import copy
from typing import Any

from _common import SESSION_RECORDS_COLLECTION, get_master_db, utc_now, with_mongo
from operations_secrets import (
    resolve_session_control_javascript_source,
    resolve_session_control_setting_keys,
)

IMMUTABLE_MESSAGE = (
    "Session control settings are read-only; modification is blocked for all connected entities"
)


def default_control_settings() -> dict[str, bool]:
    """Build control schema keys from operations.secrets; all start disabled until host loads settings.js."""
    return {key: False for key in resolve_session_control_setting_keys()}


def _freeze_settings(settings: dict[str, bool]) -> dict[str, bool]:
    return copy.deepcopy(settings)


@with_mongo
def load_session_control(
    *,
    session_id: str,
    host_user_id: str,
    client: Any,
) -> dict[str, Any]:
    """Load immutable session control settings for the host (settings.js schema)."""
    record = get_master_db(client)[SESSION_RECORDS_COLLECTION].find_one(
        {"sessionID": session_id.strip()}
    )
    if not record:
        raise LookupError("Session not found")
    if record.get("hostUserID") != host_user_id:
        raise PermissionError("Only the session host may load session control settings")

    stored = record.get("session_control_settings")
    settings = _freeze_settings(stored if isinstance(stored, dict) else default_control_settings())
    if not stored:
        get_master_db(client)[SESSION_RECORDS_COLLECTION].update_one(
            {"sessionID": session_id.strip()},
            {
                "$set": {
                    "session_control_settings": settings,
                    "updated_at": utc_now(),
                }
            },
        )
    return {
        "sessionID": session_id.strip(),
        "hostUserID": host_user_id,
        "source": resolve_session_control_javascript_source(),
        "immutable": True,
        "controls": settings,
    }


def block_modification_attempt(*, actor: str, requested_changes: dict[str, Any]) -> dict[str, Any]:
    """Reject any attempt to modify session control settings."""
    if requested_changes:
        raise PermissionError(IMMUTABLE_MESSAGE)
    return {
        "status": "blocked",
        "actor": actor,
        "message": IMMUTABLE_MESSAGE,
        "timestamp": utc_now(),
    }


@with_mongo
def get_session_control_for_route(
    *,
    session_id: str,
    host_user_id: str,
    modification_request: dict[str, Any] | None = None,
    client: Any,
) -> dict[str, Any]:
    if modification_request:
        block_modification_attempt(actor=host_user_id, requested_changes=modification_request)
    return load_session_control(
        session_id=session_id,
        host_user_id=host_user_id,
        client=client,
    )
