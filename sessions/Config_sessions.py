""" the script that writes the session secrets to the session secrets file on the host machine
[Path]: /mnt/myssd/LucidTops/Server/Secrets
[File]: sessions.secrets
[Content]: sessions container configurational requirements, for the sessions container to operate correctly.
Requirements:
- the session secrets file will be written to the host machine (hardward using a configurable Path)
- the session secrets file will be written to the session secrets file (sessions.secrets) on the host machine (hardward using a configurable Path)
- Seed DockerDNS / network / master endpoints from Server/Secrets/Master.secrets + proxy.secrets
- NO Hardcoded values, all values are created at time of operation.
- No place holder values, all values are created at time of operation.

includes:
- all the configurational content required to build the sessions container (DockerDNS)
- all the connection content required to build the sessions container (DockerDNS)

operational requirements:
- compatible with the MasterServer (uvicorn server and FastAPI system)
- compatible with all containers in the DockerDNS system (LucidTops system)
- compatible with the Tor Hidden Service and Docker Network
- compatible with MongoDB 7.0.0 or higher
- compatible with nginx reverse proxy system

RULES:
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

try:
    from .sessions_pull_information import (
        get_sessions_pull,
        load_master_and_proxy_seed,
        map_seed_to_sessions_keys,
        master_secrets_path,
        proxy_secrets_path,
        pull_sessions_hardware,
        resolve_lucid_tops_root,
        sessions_secrets_dir,
        usable_secret_value,
    )
except ImportError:  # entrypoint: python -c "from Config_sessions import ..."
    from sessions_pull_information import (  # type: ignore[no-redef]
        get_sessions_pull,
        load_master_and_proxy_seed,
        map_seed_to_sessions_keys,
        master_secrets_path,
        proxy_secrets_path,
        pull_sessions_hardware,
        resolve_lucid_tops_root,
        sessions_secrets_dir,
        usable_secret_value,
    )


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def _pick(existing: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _env(key) or existing.get(key.upper(), "").strip() or existing.get(key, "").strip()
        if usable_secret_value(value):
            return value.strip()
    return ""


def _seed_prior_from_master_and_proxy(
    lucid_root: Path, prior: dict[str, str]
) -> dict[str, str]:
    """
    Seed sessions.secrets from Server/Secrets/Master.secrets + proxy.secrets.

    A usable value already in Server/Secrets wins. A previously written
    SESSIONS_BIND_PORT is kept so the listen port stays stable.
    Placeholder values such as "invalid IP" are ignored.
    """
    seed = map_seed_to_sessions_keys(load_master_and_proxy_seed(lucid_root))
    if not seed:
        return {key: value for key, value in prior.items() if usable_secret_value(value)}
    merged = {key: value for key, value in seed.items() if usable_secret_value(value)}
    for key, value in prior.items():
        if not usable_secret_value(value):
            continue
        if key == "SESSIONS_BIND_PORT" or not usable_secret_value(merged.get(key, "")):
            merged[key] = value
    # Record seed file paths for operators (not sensitive payloads).
    merged.setdefault("MASTER_SECRETS_FILE", master_secrets_path(lucid_root).as_posix())
    merged.setdefault("PROXY_SECRETS_FILE", proxy_secrets_path(lucid_root).as_posix())
    return merged


def apply_pull_to_sessions_configuration(
    *,
    pull: dict[str, Any] | None = None,
    prior: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Derive sessions.secrets from Server/Secrets plus the hardware pull.
    SessionID stays a 10-digit string. The sessions database name comes from databases.secrets.
    """
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=True)
    existing = prior if prior is not None else {}

    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip or not primary_mac:
        raise RuntimeError(
            "apply_pull_to_sessions_configuration failed — HARDWARE primary IP/MAC required"
        )

    lucid_root = resolve_lucid_tops_root(info)
    secrets_dir = sessions_secrets_dir(lucid_root)
    secrets_dir.mkdir(parents=True, exist_ok=True)

    existing = _seed_prior_from_master_and_proxy(lucid_root, existing)

    docker_dns = (
        _pick(existing, "SESSIONS_DOCKER_DNS_NAME", "PROXY_SESSIONS_DNS")
        or str(info.get("sessions_docker_dns_name") or "")
    )
    if not usable_secret_value(docker_dns):
        raise RuntimeError(
            "SESSIONS_DOCKER_DNS_NAME missing — PROXY_SESSIONS_DNS must be a real address "
            "in proxy.secrets"
        )
    bind_host = docker_dns
    reserved_ports = {
        port
        for port in (
            _pick(existing, "MASTER_SERVER_PORT"),
            _pick(existing, "MASTER_SERVER_INTERNAL_PORT"),
            _pick(existing, "MONGODB_PORT"),
            _pick(existing, "PROXY_PORT"),
            _pick(existing, "PROXY_NGINX_LISTEN_PORT"),
            _pick(existing, "FRONTEND_PORT"),
            _pick(existing, "NODE_PORT"),
            _pick(existing, "HIDDEN_SERVICE_PORT"),
        )
        if port.isdigit()
    }
    bind_port = _pick(existing, "SESSIONS_BIND_PORT") or str(info.get("sessions_bind_port") or "")
    if not bind_port or bind_port in reserved_ports:
        bind_port = str(info.get("sessions_bind_port") or "")
    if not bind_port or bind_port in reserved_ports:
        raise RuntimeError(
            "SESSIONS_BIND_PORT missing — must be allocated at time of operation "
            "and must not reuse MASTER_SERVER_PORT"
        )

    master_host = (
        _pick(existing, "MASTER_SERVER_INTERNAL_HOST", "PROXY_BACKEND_DNS")
        or str(info.get("master_server_internal_host") or "")
    )
    if not usable_secret_value(master_host):
        raise RuntimeError(
            "MASTER_SERVER_INTERNAL_HOST missing — PROXY_BACKEND_DNS must be seeded "
            "from proxy.secrets"
        )
    master_port = (
        _pick(existing, "MASTER_SERVER_INTERNAL_PORT", "MASTER_SERVER_PORT")
        or str(info.get("master_server_internal_port") or "")
    )
    if not master_port:
        raise RuntimeError(
            "MASTER_SERVER_INTERNAL_PORT missing — must be seeded from "
            "Master.secrets/proxy.secrets at time of operation"
        )

    url_scheme = "http"

    operations_dns = (
        _pick(existing, "OPERATIONS_DOCKER_DNS_NAME", "PROXY_OPERATIONS_DNS")
        or str(info.get("operations_docker_dns_name") or "")
    )
    if not usable_secret_value(operations_dns):
        raise RuntimeError(
            "OPERATIONS_DOCKER_DNS_NAME missing — PROXY_OPERATIONS_DNS must be a real "
            "address in proxy.secrets"
        )
    operations_port = (
        _pick(existing, "OPERATIONS_BIND_PORT")
        or str(info.get("operations_bind_port") or "")
    )
    operations_scheme = _pick(existing, "OPERATIONS_URL_SCHEME") or url_scheme
    operations_handoff_path = _pick(existing, "OPERATIONS_SESSION_HANDOFF_PATH")
    if not operations_handoff_path:
        public_routes = [
            item.strip()
            for item in _pick(existing, "API_PUBLIC_ROUTES").split(",")
            if item.strip()
        ]
        if "/session-end" in public_routes:
            operations_handoff_path = "/session-end"
    if not operations_handoff_path:
        raise RuntimeError(
            "OPERATIONS_SESSION_HANDOFF_PATH missing — /session-end must be listed "
            "in backend.secrets API_PUBLIC_ROUTES"
        )

    network_name = _pick(existing, "DOCKER_NETWORK_NAME") or str(
        info.get("docker_network_name") or ""
    )
    if not network_name:
        raise RuntimeError(
            "DOCKER_NETWORK_NAME missing — must be seeded from proxy.secrets or "
            "Master.secrets at time of operation"
        )

    service_name = _pick(existing, "SESSIONS_SERVICE_NAME")
    if not service_name:
        service_name = str(
            (info.get("sessions_container") or {}).get("name")
            or _env("SESSIONS_CONTAINER_NAME")
            or "sessions"
        )

    # SessionID = unique int(10) per fixes.txt §12.7 — encoded into secrets at operation time.
    session_id_length = _pick(existing, "SESSION_ID_LENGTH") or "10"
    session_id_alphabet = _pick(existing, "SESSION_ID_ALPHABET") or "0123456789"

    inactivity_days = _pick(existing, "SESSION_INACTIVITY_DAYS") or "15"

    api_prefix = ""
    create_route = _pick(existing, "SESSION_CREATE_API_ROUTE", "NODE_CREATE_SESSION_ROUTE")
    if not create_route:
        raise RuntimeError(
            "SESSION_CREATE_API_ROUTE missing — NODE_CREATE_SESSION_ROUTE must be "
            "seeded from Master.secrets"
        )
    find_route = _pick(existing, "SESSION_FIND_PEER_GUI_ROUTE") or "/session-find"
    connect_route = (
        _pick(existing, "SESSION_CONNECT_HANDSHAKE_GUI_ROUTE") or "/session-connect"
    )
    validate_path = _pick(existing, "SESSION_VALIDATE_PATH") or "/session-validate"
    health_path = _pick(existing, "SESSION_HEALTH_PATH") or "/health"

    key_min = _pick(existing, "SESSION_KEY_MIN_LENGTH")
    if not key_min:
        raise RuntimeError(
            "SESSION_KEY_MIN_LENGTH missing — must be seeded from Master.secrets"
        )
    key_bytes = _pick(existing, "SESSION_KEY_URLSAFE_BYTES")
    if not key_bytes or int(key_bytes) < int(key_min):
        key_bytes = str(int(key_min))

    session_type = _pick(existing, "SESSION_TYPE") or "peer_remote_desktop"
    log_source = _pick(existing, "SESSION_ID_LOG_SOURCE") or service_name
    finalised = _pick(existing, "SESSION_FINALISED_STATUSES", "SESSION_STATUSES")
    if not finalised:
        raise RuntimeError(
            "SESSION_STATUSES missing — must be seeded from Master.secrets"
        )
    status_items = {item.strip() for item in finalised.split(",") if item.strip()}
    if "compressed" not in status_items:
        raise RuntimeError(
            "SESSION_STATUSES must include compressed — sourced from Master.secrets"
        )
    complete_status = "compressed"

    mask_prefix = _pick(existing, "PEER_USER_ID_MASK_PREFIX")
    if not mask_prefix:
        mask_prefix = f"u{primary_mac[-4:].lower()}-"
    mask_hex_len = _pick(existing, "PEER_USER_ID_MASK_HEX_LEN")
    if not mask_hex_len:
        mask_hex_len = str(max(8, min(32, len(primary_mac.replace(":", "")))))
    peer_label = _pick(existing, "PEER_SEARCH_LABEL") or "peer-search"

    sessions_db = _pick(existing, "LUCIDTOPS_SESSIONS_DB_NAME", "MONGODB_SERVICE")
    if not sessions_db or sessions_db == "LucidTops_SessionsDB":
        raise RuntimeError(
            "LUCIDTOPS_SESSIONS_DB_NAME missing — databases.secrets "
            "LUCIDTOPS_*_SESSIONSDB_DATABASE is required"
        )
    sessions_db_url = _pick(existing, "LUCIDTOPS_SESSIONS_DB_URL")
    if not sessions_db_url:
        raise RuntimeError(
            "LUCIDTOPS_SESSIONS_DB_URL missing — databases.secrets "
            "LUCIDTOPS_*_SESSIONSDB_URL is required"
        )
    sessions_collection = _pick(
        existing, "LUCIDTOPS_SESSIONS_COLLECTION", "SESSION_RECORDS_COLLECTION"
    )
    if not sessions_collection:
        raise RuntimeError(
            "LUCIDTOPS_SESSIONS_COLLECTION missing — SESSION_RECORDS_COLLECTION "
            "must be seeded from Master.secrets"
        )
    session_id_log_collection = (
        _pick(existing, "LUCIDTOPS_SESSIONS_ID_LOG_COLLECTION") or "session_id_log"
    )

    tor_enabled = _pick(existing, "TOR_HIDDEN_SERVICES_ENABLED")
    if not tor_enabled:
        tor_enabled = "true" if info.get("tor_available") else "false"
    docker_enabled = _pick(existing, "DOCKER_NETWORK_ENABLED")
    if not docker_enabled:
        docker_enabled = (
            "true"
            if info.get("docker_network_available") or network_name
            else "false"
        )

    operator_master_type = _pick(existing, "TALLY_ENTITY_TYPE_MASTER") or "MasterServerID"
    operator_master_id = _pick(existing, "TALLY_ENTITY_ID_MASTER", "MASTER_SERVER_ID")
    if not operator_master_id:
        raise RuntimeError(
            "TALLY_ENTITY_ID_MASTER missing — MASTER_SERVER_ID must be seeded from "
            "backend.secrets at time of operation"
        )

    container_name = (
        _pick(existing, "SESSIONS_CONTAINER_NAME")
        or str((info.get("sessions_container") or {}).get("name") or service_name)
    )

    resolved: dict[str, str] = {
        "SESSION_ID_LENGTH": session_id_length,
        "SESSION_ID_ALPHABET": session_id_alphabet,
        "SESSION_ID_LOG_SOURCE": log_source,
        "SESSION_INACTIVITY_DAYS": inactivity_days,
        "SESSION_FINALISED_STATUSES": finalised,
        "SESSION_COMPLETE_STATUS": complete_status,
        "SESSION_API_PREFIX": api_prefix,
        "SESSION_CREATE_API_ROUTE": create_route,
        "SESSION_FIND_PEER_GUI_ROUTE": find_route,
        "SESSION_CONNECT_HANDSHAKE_GUI_ROUTE": connect_route,
        "SESSION_VALIDATE_PATH": validate_path,
        "SESSION_HEALTH_PATH": health_path,
        "MASTER_SERVER_INTERNAL_HOST": master_host,
        "MASTER_SERVER_INTERNAL_PORT": master_port,
        "MASTER_SERVER_URL_SCHEME": url_scheme,
        "TOR_HIDDEN_SERVICES_ENABLED": tor_enabled,
        "DOCKER_NETWORK_ENABLED": docker_enabled,
        "SESSION_KEY_MIN_LENGTH": key_min,
        "SESSION_KEY_URLSAFE_BYTES": key_bytes,
        "SESSION_TYPE": session_type,
        "TALLY_ENTITY_TYPE_MASTER": operator_master_type,
        "TALLY_ENTITY_ID_MASTER": operator_master_id,
        "PEER_USER_ID_MASK_PREFIX": mask_prefix,
        "PEER_USER_ID_MASK_HEX_LEN": mask_hex_len,
        "PEER_SEARCH_LABEL": peer_label,
        "SESSIONS_BIND_HOST": bind_host,
        "SESSIONS_BIND_PORT": bind_port,
        "SESSIONS_DOCKER_DNS_NAME": docker_dns,
        "SESSIONS_SERVICE_NAME": service_name,
        "SESSIONS_CONTAINER_NAME": container_name,
        "LUCIDTOPS_SESSIONS_DB_NAME": sessions_db,
        "LUCIDTOPS_SESSIONS_DB_URL": sessions_db_url,
        "LUCIDTOPS_SESSIONS_COLLECTION": sessions_collection,
        "LUCIDTOPS_SESSIONS_ID_LOG_COLLECTION": session_id_log_collection,
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "LUCID_TOPS_ROOT": lucid_root.as_posix(),
        "SECRETS_DIR": secrets_dir.as_posix(),
        "MASTER_SECRETS_FILE": _pick(existing, "MASTER_SECRETS_FILE")
        or master_secrets_path(lucid_root).as_posix(),
        "PROXY_SECRETS_FILE": _pick(existing, "PROXY_SECRETS_FILE")
        or proxy_secrets_path(lucid_root).as_posix(),
        "DOCKER_NETWORK_NAME": network_name,
        "OPERATIONS_DOCKER_DNS_NAME": operations_dns,
        "OPERATIONS_URL_SCHEME": operations_scheme,
        "OPERATIONS_SESSION_HANDOFF_PATH": operations_handoff_path,
        "SESSION_STATUSES": finalised,
        "SESSION_HASH_ALGORITHM": _pick(existing, "SESSION_HASH_ALGORITHM"),
        "SESSION_CHUNK_SIZE_BYTES": _pick(existing, "SESSION_CHUNK_SIZE_BYTES"),
        "MASTER_MONGODB_URL": _pick(existing, "MASTER_MONGODB_URL", "MONGODB_URL"),
        "MASTER_MONGODB_DATABASE": _pick(
            existing, "MASTER_MONGODB_DATABASE", "MONGODB_MAIN_DATABASE_NAME"
        ),
        "MASTER_SERVER_ID": operator_master_id,
    }
    if operations_port:
        resolved["OPERATIONS_BIND_PORT"] = operations_port
    if not resolved["SESSION_HASH_ALGORITHM"]:
        raise RuntimeError(
            "SESSION_HASH_ALGORITHM missing — must be seeded from Master.secrets"
        )
    if not resolved["SESSION_CHUNK_SIZE_BYTES"]:
        raise RuntimeError(
            "SESSION_CHUNK_SIZE_BYTES missing — must be seeded from Master.secrets"
        )
    if not resolved["MASTER_MONGODB_URL"] or not resolved["MASTER_MONGODB_DATABASE"]:
        raise RuntimeError(
            "MASTER_MONGODB_URL missing — backend.secrets MONGODB_URL is required"
        )
    resolved["MONGODB_URL"] = resolved["MASTER_MONGODB_URL"]
    resolved["MONGODB_MAIN_DATABASE_NAME"] = resolved["MASTER_MONGODB_DATABASE"]

    # Carry through Proxy/Master DockerDNS + Tor/Mongo facts when present in seed.
    for carry_key in (
        "PROXY_BACKEND_DNS",
        "PROXY_SESSIONS_DNS",
        "PROXY_OPERATIONS_DNS",
        "MASTER_SERVER_PORT",
        "MASTER_SERVER_ONION",
        "TOR_SOCKS_HOST",
        "TOR_SOCKS_PORT",
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_URL",
        "MONGODB_MAIN_DATABASE_NAME",
        "LUCIDTOPS_SESSIONS_DB_URL",
        "MASTER_MONGODB_URL",
        "MASTER_MONGODB_DATABASE",
        "SESSION_HASH_ALGORITHM",
        "SESSION_CHUNK_SIZE_BYTES",
        "SESSION_STATUSES",
        "MASTER_SERVER_ID",
    ):
        value = _pick(existing, carry_key)
        if value and carry_key not in {
            "MONGODB_URL",
            "MONGODB_MAIN_DATABASE_NAME",
            "MASTER_MONGODB_URL",
            "MASTER_MONGODB_DATABASE",
        }:
            resolved[carry_key] = value

    resolved["MONGODB_URL"] = resolved["MASTER_MONGODB_URL"]
    resolved["MONGODB_MAIN_DATABASE_NAME"] = resolved["MASTER_MONGODB_DATABASE"]
    return resolved


def sessions_secrets_path_from_pull(info: dict[str, Any] | None = None) -> Path:
    pull = info if info is not None else get_sessions_pull()
    override = _env("SESSIONS_SECRETS_FILE")
    if override:
        return Path(override).expanduser()
    lucid_root = resolve_lucid_tops_root(pull)
    secrets_dir = sessions_secrets_dir(lucid_root)
    name = _env("SESSIONS_SECRETS_NAME")
    if not name:
        container = _env("SESSIONS_CONTAINER_NAME")
        name = f"{container}.secrets" if container else "sessions.secrets"
    return secrets_dir / name


def write_session_secrets(
    *,
    secrets_dir: Path | None = None,
    force: bool = False,
    pull: dict[str, Any] | None = None,
) -> Path:
    """
    Write sessions.secrets on the host from Master/proxy seed + operation-time pull.

    Seed: Server/Secrets/Master.secrets + proxy.secrets
    Target: /mnt/myssd/LucidTops/Server/Secrets/sessions.secrets (or SESSIONS_SECRETS_FILE)
    """
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=True)
    lucid_root = resolve_lucid_tops_root(info)
    path = (
        Path(secrets_dir)
        / (
            _env("SESSIONS_SECRETS_NAME")
            or (
                f"{_env('SESSIONS_CONTAINER_NAME')}.secrets"
                if _env("SESSIONS_CONTAINER_NAME")
                else "sessions.secrets"
            )
        )
        if secrets_dir is not None
        else sessions_secrets_path_from_pull(info)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = _parse_secrets_file(path) if path.exists() else {}
    resolved = apply_pull_to_sessions_configuration(pull=info, prior=prior)
    if path.exists() and not force:
        existing_keys = set(_parse_secrets_file(path).keys())
        needs_fill = any(
            (k not in existing_keys) or (not prior.get(k)) for k in resolved
        )
        if not needs_fill:
            os.environ["SESSIONS_SECRETS_FILE"] = path.as_posix()
            os.environ["SECRETS_DIR"] = path.parent.as_posix()
            return path

    try:
        from pull_information import utc_now as _utc_now
    except ImportError:
        from datetime import datetime, timezone

        def _utc_now() -> str:
            return datetime.now(timezone.utc).isoformat()

    lines = [
        "# LucidTops sessions.secrets - loaded by sessions/sessionID.py",
        f"# Generated: {_utc_now()}",
        f"# Container: {resolved.get('SESSIONS_CONTAINER_NAME', 'sessions')}",
        f"# Seeded from: {resolved.get('MASTER_SECRETS_FILE', master_secrets_path(lucid_root).as_posix())}",
        f"# Seeded from: {resolved.get('PROXY_SECRETS_FILE', proxy_secrets_path(lucid_root).as_posix())}",
        "# Values are created at operation time from Master/proxy seed + hardware pull — no placeholders.",
        "",
    ]
    for key in sorted(resolved.keys()):
        lines.append(f"{key}={resolved[key]}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    os.environ["SESSIONS_SECRETS_FILE"] = path.as_posix()
    os.environ["SECRETS_DIR"] = path.parent.as_posix()
    os.environ["MONGODB_URL"] = resolved.get("MONGODB_URL", "")
    os.environ["MASTER_MONGODB_URL"] = resolved.get("MASTER_MONGODB_URL", "")
    os.environ["LUCIDTOPS_SESSIONS_DB_URL"] = resolved.get("LUCIDTOPS_SESSIONS_DB_URL", "")
    return path


def export_sessions_secrets_shell() -> None:
    """Print shell exports for the written sessions.secrets file."""
    import shlex

    raw_path = _env("SESSIONS_SECRETS_FILE")
    path = Path(raw_path) if raw_path else sessions_secrets_path_from_pull()
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key:
            lines.append(f"export {key}={shlex.quote(value.strip())}")
    print("\n".join(lines))


def session_secrets_status() -> dict[str, Any]:
    """Return non-sensitive status for the sessions secrets file."""
    info = get_sessions_pull()
    path = sessions_secrets_path_from_pull(info)
    loaded = _parse_secrets_file(path)
    try:
        required = apply_pull_to_sessions_configuration(pull=info, prior=loaded)
        required_keys = list(required.keys())
    except RuntimeError as exc:
        return {
            "secrets_file": path.as_posix(),
            "secrets_file_exists": path.exists(),
            "error": str(exc),
            "keys_present": list(loaded.keys()),
            "master_secrets_file": str(info.get("master_secrets_file") or ""),
            "proxy_secrets_file": str(info.get("proxy_secrets_file") or ""),
        }
    present: list[str] = []
    missing: list[str] = []
    for key in required_keys:
        env_value = _env(key)
        file_value = loaded.get(key.upper(), "").strip() or loaded.get(key, "").strip()
        if env_value or file_value:
            present.append(key)
        else:
            missing.append(key)
    return {
        "secrets_file": path.as_posix(),
        "secrets_file_exists": path.exists(),
        "required_keys": required_keys,
        "keys_present": present,
        "missing_keys": missing,
        "hardware_primary_ip": info.get("primary_ip"),
        "hardware_primary_mac": info.get("primary_mac"),
        "master_secrets_file": str(info.get("master_secrets_file") or ""),
        "proxy_secrets_file": str(info.get("proxy_secrets_file") or ""),
    }


# Compatibility alias used by sessionID / __init__
def write_sessions_secrets(
    secrets_dir_path: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    return write_session_secrets(secrets_dir=secrets_dir_path, force=force)


if __name__ == "__main__":
    written = write_session_secrets(force=True)
    print(f"Wrote {written.as_posix()}")
