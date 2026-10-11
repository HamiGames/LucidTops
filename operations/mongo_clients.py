"""Mongo clients for the six Databases containers.

URLs and database names come from operations.secrets. Those keys are copied
at image build from databases.secrets. The prefix database and MONGODB_URL
are not opened here.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from typing import Any

from operations_secrets import require_secret, resolve_secret

# Suffixes match Databases/Dns_databases.py CONTAINER_SPECS.
DB_ROLE_SUFFIX: dict[str, str] = {
    "sessions": "_SessionsDB",
    "ledger": "__LedgerDB",
    "user": "_UserDB",
    "node": "_NodeDB",
    "chain": "_ChainDB",
    "payment": "_PaymentDB",
}


def secret_key_prefix(db_name: str) -> str:
    """Match Databases/databases_secrets.py secret_key_prefix."""
    cleaned = db_name.strip().replace("-", "_")
    parts: list[str] = []
    buf = ""
    for ch in cleaned:
        if ch == "_":
            if buf:
                parts.append(buf)
                buf = ""
            continue
        buf += ch
    if buf:
        parts.append(buf)
    return "_".join(part.upper() for part in parts if part)


def main_database_prefix() -> str:
    return require_secret("MONGODB_MAIN_DATABASE_NAME")


def container_database_name(suffix: str) -> str:
    if suffix not in DB_ROLE_SUFFIX.values():
        raise RuntimeError(f"unknown database suffix {suffix!r}")
    return f"{main_database_prefix()}{suffix}"


def _prefix_for_suffix(suffix: str) -> str:
    return secret_key_prefix(container_database_name(suffix))


def database_url(suffix: str) -> str:
    return require_secret(f"{_prefix_for_suffix(suffix)}_URL")


def database_name(suffix: str) -> str:
    stored = resolve_secret(f"{_prefix_for_suffix(suffix)}_DATABASE")
    return stored or container_database_name(suffix)


def role_suffix(role: str) -> str:
    suffix = DB_ROLE_SUFFIX.get(role)
    if not suffix:
        raise RuntimeError(f"unknown database role {role!r}")
    return suffix


class OpsMongo:
    """One pymongo client per container URL. Callers select a role database."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def _client_for_url(self, url: str) -> Any:
        existing = self._clients.get(url)
        if existing is not None:
            return existing
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("pymongo is required for operations database access") from exc
        client = MongoClient(url, serverSelectionTimeoutMS=8000)
        self._clients[url] = client
        return client

    def database(self, role: str) -> Any:
        suffix = role_suffix(role)
        url = database_url(suffix)
        name = database_name(suffix)
        return self._client_for_url(url)[name]

    def sessions(self) -> Any:
        return self.database("sessions")

    def ledger(self) -> Any:
        return self.database("ledger")

    def user(self) -> Any:
        return self.database("user")

    def node(self) -> Any:
        return self.database("node")

    def chain(self) -> Any:
        return self.database("chain")

    def payment(self) -> Any:
        return self.database("payment")

    def node_ledger(self, operator_id: str) -> Any:
        """{operator_id}_LedgerDB on the node mongod, not the prefix database."""
        from operations_secrets import node_ledger_db_name_for_id

        suffix = role_suffix("node")
        url = database_url(suffix)
        return self._client_for_url(url)[node_ledger_db_name_for_id(operator_id)]

    def confirm_named_containers(self) -> list[str]:
        """Ping each of the six containers. Does not create databases."""
        names: list[str] = []
        for role in DB_ROLE_SUFFIX:
            db = self.database(role)
            db.command("ping")
            names.append(str(db.name))
        return names

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()


def open_ops_mongo() -> OpsMongo:
    return OpsMongo()
