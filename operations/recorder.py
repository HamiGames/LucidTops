"""
this is the protocol for the recording and storage of session data on the local console of the UserID's and NodeUser's
recorder protocol:
- all actions and workings are recorded in the format of a mp4 video file
- all mp4 video files are stored on the UserId's console in a History folder, within the lucid program folder
- all mp4 video files are named with the sessionID and the creation date
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import utc_now
from session import validate_session_id

DEFAULT_LUCID_PROGRAM_DIR = Path(
    os.environ.get("LUCID_PROGRAM_DIR", os.environ.get("LUCID_TOPS_ROOT", "/mnt/myssd/LucidTops"))
)
HISTORY_DIR_NAME = "History"
MP4_EXTENSION = ".mp4"
SESSION_ID_FILENAME_PATTERN = re.compile(r"^[0-9a-z]{10}_[0-9]{4}-[0-9]{2}-[0-9]{2}\.mp4$")


def history_directory(*, user_id: str | None = None) -> Path:
    """Resolve the local History folder for a UserID console."""
    base = Path(os.environ.get("LUCID_USER_PROGRAM_DIR", DEFAULT_LUCID_PROGRAM_DIR))
    if user_id:
        return base / user_id / HISTORY_DIR_NAME
    return base / HISTORY_DIR_NAME


def recording_filename(*, session_id: str, created_at: str | None = None) -> str:
    if not validate_session_id(session_id):
        raise ValueError("sessionID must be valid for recording filename")
    if created_at:
        date_part = created_at[:10]
    else:
        date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{session_id.strip()}_{date_part}{MP4_EXTENSION}"


def recording_path(*, session_id: str, user_id: str, created_at: str | None = None) -> Path:
    directory = history_directory(user_id=user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / recording_filename(session_id=session_id, created_at=created_at)


def start_recording(*, session_id: str, user_id: str) -> dict[str, Any]:
    """Register an MP4 recording target for a session on the local console."""
    path = recording_path(session_id=session_id, user_id=user_id)
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "format": "mp4",
        "path": str(path.as_posix()),
        "status": "recording_registered",
        "timestamp": utc_now(),
    }


def finalize_recording(*, session_id: str, user_id: str, content: bytes) -> dict[str, Any]:
    """Write MP4 bytes to the History folder using sessionID and creation date."""
    if not content:
        raise ValueError("Recording content must not be empty")
    path = recording_path(session_id=session_id, user_id=user_id)
    path.write_bytes(content)
    return {
        "sessionID": session_id.strip(),
        "userID": user_id,
        "format": "mp4",
        "path": str(path.as_posix()),
        "size_bytes": len(content),
        "status": "saved",
        "timestamp": utc_now(),
    }


def list_recordings(*, user_id: str) -> list[dict[str, Any]]:
    directory = history_directory(user_id=user_id)
    if not directory.exists():
        return []
    results: list[dict[str, Any]] = []
    for item in sorted(directory.glob(f"*{MP4_EXTENSION}")):
        if SESSION_ID_FILENAME_PATTERN.fullmatch(item.name):
            results.append(
                {
                    "filename": item.name,
                    "path": str(item.as_posix()),
                    "size_bytes": item.stat().st_size,
                }
            )
    return results
