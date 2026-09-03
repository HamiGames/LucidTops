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
"""

from __future__ import annotations

import copy
from typing import Any

from _common import SESSION_RECORDS_COLLECTION, get_master_db, utc_now, with_mongo
from operations_secrets import resolve_session_control_javascript_source

SESSION_CONTROL_SETTINGS: dict[str, bool] = {
    "mouse_control": False,
    "keyboard_control": False,
    "audio_control": False,
    "video_control": False,
    "screen_control": False,
    "file_transfer_control": False,
    "file_download_control": False,
    "file_upload_control": False,
    "file_delete_control": False,
    "file_rename_control": False,
    "file_move_control": False,
    "file_copy_control": False,
    "file_paste_control": False,
    "file_zip_control": False,
    "file_unzip_control": False,
    "file_sync_control": False,
    "file_transfer_location_control": False,
    "peer_to_peer_remote_desktop_sharing_session_control": False,
}

IMMUTABLE_MESSAGE = (
    "Session control settings are read-only; modification is blocked for all connected entities"
)


def default_control_settings() -> dict[str, bool]:
    return copy.deepcopy(SESSION_CONTROL_SETTINGS)


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
