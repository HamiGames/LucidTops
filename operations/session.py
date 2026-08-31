""" the Session systems minimum requirements for transferring session data to the blockchain system
session requirements:
- sessionID: 10 characters (unique)
- 2 or more UserID's must be present in the session data
-2 or more session records must be present in the session 
- the session data must be compressed using a sha512 hash function
- the session must have ended before compression can occur
- the session must have a valid sessionID
- the session must have a valid sessionKey 
- all fields in the session must be complete and valid
- the session will not comence without an agreement from all participants
- the session will not comence without a valid sessionID
- the entering of a session must use a sessionID via the search peer function

limitations:
- the session will not comence without a valid sessionID
- the session will not comence without a valid sessionKey
- the session will not comence without a valid sessionData
- the session will not comence without a valid sessionStatus
- the session will not comence without a valid sessionType
- the session will not comence without a valid sessionTime
- the session will not comence without a valid sessionDate
- the session will not comence without 2 or more UserID's




"""

from __future__ import annotations

from sessions.compress import compress_session
from sessions.SessionCore import (
    agree_session,
    can_commence_session,
    connect_session,
    create_session,
    disconnect_session,
    end_session,
    find_session,
    generate_session_key,
    record_session_event,
    transfer_session_metadata,
    validate_session_key,
)
from sessions.sessionID import generate_session_id, validate_session_id

SESSION_ID_LENGTH = 10
SESSION_KEY_MIN_LENGTH = 16
SESSION_REQUIRED_FIELDS = (
    "sessionID",
    "sessionKey",
    "sessionData",
    "sessionStatus",
    "sessionType",
    "sessionTime",
    "sessionDate",
)
SESSION_STATUSES = frozenset({"pending", "active", "ended", "compressed"})

__all__ = (
    "agree_session",
    "can_commence_session",
    "compress_session",
    "connect_session",
    "create_session",
    "disconnect_session",
    "end_session",
    "find_session",
    "generate_session_id",
    "generate_session_key",
    "record_session_event",
    "transfer_session_metadata",
    "validate_session_id",
    "validate_session_key",
)
