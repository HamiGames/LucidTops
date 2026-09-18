"""DockerDNS HTTP client from operations → blockchain governance API.

Blockchain governance functions are only callable via the operations container.
POST /blockchain-create writes the local chain only and returns ledger_doc —
operations alone appends Master LucidTops_LedgerDB and {NodeID}_LedgerDB.
Blockchain Master-ledger write is genesis-only and must be revoked before
day-to-day create. Ledger public reads use the blockchain LucidLedger surface
separately.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from operations_secrets import (
    resolve_blockchain_api_prefix,
    resolve_blockchain_bind_port,
    resolve_blockchain_docker_dns_name,
    resolve_blockchain_secret,
    resolve_blockchain_secret_key,
)


def resolve_blockchain_governance_base_url() -> str:
    host = resolve_blockchain_docker_dns_name()
    port = resolve_blockchain_bind_port()
    prefix = resolve_blockchain_api_prefix().rstrip("/")
    return f"http://{host}:{port}{prefix}"


def _auth_headers() -> dict[str, str]:
    return {
        "X-Blockchain-Secret": resolve_blockchain_secret(),
        "X-Blockchain-Secret-Key": resolve_blockchain_secret_key(),
        "Content-Type": "application/json",
    }


def call_blockchain_create(
    *,
    actor_type: str,
    node_user_id: str | None = None,
    invoker: str | None = None,
    chain_id: str | None = None,
    reported_memory_gb: int | None = None,
    packet: list[dict[str, Any]] | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """
    POST /blockchain-create via DockerDNS.

    Blockchain writes local chain only and returns ledger_doc / BlockID.
    Caller (operations) owns Master/Node ledger append after this returns.
    """
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            "httpx is required for operations → blockchain DockerDNS create"
        ) from exc

    url = f"{resolve_blockchain_governance_base_url()}/blockchain-create"
    body: dict[str, Any] = {
        "actor_type": actor_type,
        "use_data_insert": packet is None,
    }
    if node_user_id:
        body["node_user_id"] = node_user_id
    if invoker:
        body["invoker"] = invoker
    if chain_id:
        body["chain_id"] = chain_id
    if reported_memory_gb is not None:
        body["reported_memory_gb"] = reported_memory_gb
    if packet is not None:
        body["packet"] = packet

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, json=body, headers=_auth_headers())
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json()
            except Exception:
                pass
            raise RuntimeError(
                f"blockchain governance create failed ({response.status_code}): {detail}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("blockchain governance create returned non-object JSON")
        return data
