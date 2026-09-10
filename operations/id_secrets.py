"""Load approved operator ID.secrets at time of operation.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from operations_secrets import parse_secrets_file, resolve_accounts_dir, resolve_id_secrets_dir

OPERATOR_ID_KEYS: tuple[str, ...] = (
    "NodeID",
    "AdminID",
    "MasterUserID",
    "MasterServerID",
)

OPERATOR_ID_FIELD_ALIASES: dict[str, str] = {
    "NODEID": "NodeID",
    "NODE_ID": "NodeID",
    "ADMINID": "AdminID",
    "ADMIN_ID": "AdminID",
    "MASTERUSERID": "MasterUserID",
    "MASTER_USER_ID": "MasterUserID",
    "MASTERSERVERID": "MasterServerID",
    "MASTER_SERVER_ID": "MasterServerID",
}


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def id_secrets_candidates(operator_id: str | None = None) -> list[Path]:
    """Resolve candidate ID.secrets paths from env / pulled directories at operation time."""
    paths: list[Path] = []
    override = _env("OPERATOR_ID_SECRETS_FILE")
    if override:
        paths.append(Path(override).expanduser())

    id_dir = resolve_id_secrets_dir()
    accounts_dir = resolve_accounts_dir()
    if operator_id:
        oid = operator_id.strip()
        paths.append(id_dir / f"{oid}.secrets")
        paths.append(accounts_dir / f"{oid}.secrets")
        paths.append(id_dir / "ID.secrets")
        paths.append(accounts_dir / "ID.secrets")
    else:
        paths.append(id_dir / "ID.secrets")
        paths.append(accounts_dir / "ID.secrets")
    return paths


def load_id_secrets(*, operator_id: str | None = None) -> dict[str, str]:
    """
    Load the first existing ID.secrets for the operator.
    Present only after MasterServer registration approval.
    """
    for path in id_secrets_candidates(operator_id):
        if path.exists():
            return parse_secrets_file(path)
    raise RuntimeError(
        "ID.secrets missing — registration must be approved and ID.secrets "
        "written at time of operation before the operations container can run"
    )


def resolve_operator_from_id_secrets(
    secrets: dict[str, str] | None = None,
    *,
    operator_id: str | None = None,
) -> dict[str, Any]:
    """
    Extract exactly one operator ID type + TokenID + email from ID.secrets.
    """
    data = secrets if secrets is not None else load_id_secrets(operator_id=operator_id)
    normalized: dict[str, str] = {}
    for key, value in data.items():
        upper = key.strip().upper()
        canonical = OPERATOR_ID_FIELD_ALIASES.get(upper, upper)
        normalized[canonical] = value.strip()

    found: list[tuple[str, str]] = []
    for field in OPERATOR_ID_KEYS:
        value = normalized.get(field, "").strip()
        if value:
            found.append((field, value))

    if len(found) != 1:
        raise PermissionError(
            "ID.secrets must contain exactly one of NodeID, AdminID, "
            "MasterUserID, or MasterServerID"
        )

    id_type, id_value = found[0]
    token = (
        normalized.get("TOKENID", "").strip()
        or normalized.get("IDTOKEN", "").strip()
        or normalized.get("TOKEN_ID", "").strip()
    )
    if not token:
        raise RuntimeError("TokenID missing from ID.secrets at time of operation")

    email = normalized.get("EMAIL", "").strip() or normalized.get("EMAIL_ADDRESS", "").strip()
    if not email:
        raise RuntimeError("email missing from ID.secrets at time of operation")

    return {
        "id_type": id_type,
        "operator_id": id_value,
        "TokenID": token,
        "email": email,
        "raw": normalized,
    }
