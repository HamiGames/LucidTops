""" The compression protocol and requuirements for the process of compressing the session data and transferring it to the blockchain system
compression protocol:
- session data must be compressed using a sha512 hash function
- all session fields must be valid and present in the session data
- the compression process will be performed on the master server database or NodeUser
- the completion of a compression will generate a TaskToken and added to the tally record system
- the sessionID is the returned value recieved by the UserID's that participated in the session

limitations:
- the compression process is only used for the session system
- the compression process is not used for any other purpose
- the compression process is not used for any other application
- the compression process is not used for any other system
- the compression process is not used for any other network
- the compression process is not used for any other internet
- the compression process is not used for any other world
- the compression process is not used for any other universe

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.

"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ._common import (
    complete_status_value,
    resolve_sessions_secret,
    session_records_collection,
    utc_now,
    with_mongo,
)
from .sessionID import (
    resolve_operations_handoff_url,
    resolve_session_secret,
    resolve_session_secret_int,
    touch_session_id_log,
    validate_session_id,
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _try_secret(key: str) -> str:
    try:
        return resolve_sessions_secret(key)
    except RuntimeError:
        return ""


def _operations_operator_payload() -> dict[str, Any]:
    """
    Handoff identity is MasterServerID from backend.secrets.
    OPERATIONS_OPERATOR_TOKEN_ID is not present in Server/Secrets and is not invented.
    """
    operator_id = _env("MASTER_SERVER_ID") or _try_secret("MASTER_SERVER_ID")
    if not operator_id:
        operator_id = _env("TALLY_ENTITY_ID_MASTER") or _try_secret("TALLY_ENTITY_ID_MASTER")
    if not operator_id:
        raise RuntimeError(
            "MASTER_SERVER_ID missing — must be seeded from backend.secrets "
            "before operations handoff"
        )
    return {"MasterServerID": operator_id}


def _hash_and_chunk(record: dict[str, Any]) -> dict[str, Any]:
    algorithm = resolve_session_secret("SESSION_HASH_ALGORITHM").lower()
    if algorithm != "sha512":
        raise RuntimeError(
            f"SESSION_HASH_ALGORITHM must be sha512 at time of operation (found {algorithm})"
        )
    chunk_size = resolve_session_secret_int("SESSION_CHUNK_SIZE_BYTES")
    if chunk_size < 1:
        raise RuntimeError("SESSION_CHUNK_SIZE_BYTES must be >= 1")
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"_id", "chunked_payload", "aggregate_hash"}
    }
    raw = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha512(raw).hexdigest()
    chunks = [
        raw[offset : offset + chunk_size].hex()
        for offset in range(0, len(raw), chunk_size)
    ] or [""]
    return {
        "aggregate_hash": digest,
        "chunked_payload": chunks,
        "compressed": True,
        "chunk_size_bytes": chunk_size,
        "hash_algorithm": algorithm,
    }


def _post_operations_handoff(*, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    url = resolve_operations_handoff_url()
    data = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(
            f"operations handoff rejected HTTP {exc.code}: {raw[:500]}"
        ) from exc
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"operations handoff failed: {exc}") from exc

    parsed: Any
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:500]}
    return {
        "url": url,
        "status_code": int(code),
        "response": parsed,
        "handed_off_at": utc_now(),
        "sessionID": session_id,
    }


@with_mongo
def handoff_complete_session_to_operations(
    *,
    session_id: str,
    client: Any,
) -> dict[str, Any]:
    """
    Thin handoff: SessionID_status complete → operations for chunk/New_BlockID.
    Sessions does not chunk or write ledger/blockchain collections (fixes.txt §5.10 / §12.21).
    """
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required for operations handoff")

    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")

    complete = complete_status_value()
    status = record.get("SessionID_status") or record.get("sessionStatus")
    if status != complete:
        raise ValueError(
            f"SessionID_status must be {complete!r} before operations handoff "
            f"(found {status!r})"
        )

    if record.get("operations_handoff", {}).get("status") == "handed_off":
        return dict(record["operations_handoff"])

    operator = _operations_operator_payload()
    body = {
        **operator,
        "sessionID": session_id.strip(),
        "UserID": record.get("hostUserID"),
        "SessionID_status": complete,
        "aggregate_hash": record.get("aggregate_hash"),
        "compressed": True,
    }
    result = _post_operations_handoff(session_id=session_id.strip(), body=body)
    handoff_doc = {
        "status": "handed_off",
        "operations_url": result["url"],
        "operations_status_code": result["status_code"],
        "operations_response_preview": str(result.get("response"))[:500],
        "handed_off_at": result["handed_off_at"],
        "non_standard_owner": "operations",
    }
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "operations_handoff": handoff_doc,
                "updated_at": utc_now(),
            }
        },
    )
    touch_session_id_log(session_id=session_id, status=complete, client=client)
    return handoff_doc


@with_mongo
def compress_session(
    *,
    session_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    client: Any,
) -> dict[str, Any]:
    """
    Compatibility entry: does not compress locally.
    Ensures SessionID_status is complete, then hands off to operations.
    entity_type/entity_id are ignored here — operations owns tally/chunk/block.
    """
    del entity_type, entity_id  # operations-owned; not applied in sessions
    if not validate_session_id(session_id):
        raise ValueError("A valid sessionID is required for compression handoff")

    record = session_records_collection(client).find_one({"sessionID": session_id.strip()})
    if not record:
        raise LookupError("Session not found")

    complete = complete_status_value()
    status = record.get("SessionID_status") or record.get("sessionStatus")
    if status not in {complete, "ended"}:
        raise ValueError("Session must have ended before operations handoff")
    if status == "ended":
        user_ids = list(record.get("userIDs") or [])
        ended_peers = list(record.get("ended_peers") or [])
        if not user_ids or not all(uid in ended_peers for uid in user_ids):
            raise ValueError("all peers must end before operations handoff")

    hashed = _hash_and_chunk(record)
    session_records_collection(client).update_one(
        {"sessionID": session_id.strip()},
        {
            "$set": {
                "sessionData": hashed["aggregate_hash"],
                "sessionStatus": complete,
                "SessionID_status": complete,
                "aggregate_hash": hashed["aggregate_hash"],
                "chunked_payload": hashed["chunked_payload"],
                "compressed": True,
                "hash_algorithm": hashed["hash_algorithm"],
                "chunk_size_bytes": hashed["chunk_size_bytes"],
                "updated_at": utc_now(),
            }
        },
    )
    touch_session_id_log(session_id=session_id, status=complete, client=client)

    handoff = handoff_complete_session_to_operations(
        session_id=session_id.strip(),
        client=client,
    )
    return {
        "sessionID": session_id.strip(),
        "compressed": True,
        "aggregate_hash": hashed["aggregate_hash"],
        "chunk_count": len(hashed["chunked_payload"]),
        "operations_handoff": handoff,
        "participantUserIDs": list(record.get("userIDs") or []),
    }
