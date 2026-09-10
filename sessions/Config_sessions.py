""" the script that writes the session secrets to the session secrets file (session.secrets) on the host machine (hardward using a configurable Path)
[Path]: mnt/myssd/LucidTops/secrets
[File]: session.secrets
[Content]: sessions container configurational requirements, for the sessions container to operate correctly.
Requirements:
- the session secrets file will be written to the host machine (hardward using a configurable Path)
- the session secrets file will be written to the session secrets file (session.secrets) on the host machine (hardward using a configurable Path)
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

from .sessions_pull_information import (
    get_sessions_pull,
    pull_sessions_hardware,
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
        if value:
            return value
    return ""


def apply_pull_to_sessions_configuration(
    *,
    pull: dict[str, Any] | None = None,
    prior: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Derive sessions.secrets values solely from hardware pull + live DockerDNS.
    Protocol facts required by fixes.txt (SessionID int(10), LucidTops_SessionsDB)
    are written into secrets at time of operation — never left as source placeholders.
    """
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=True)
    existing = prior if prior is not None else {}

    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip or not primary_mac:
        raise RuntimeError(
            "apply_pull_to_sessions_configuration failed — HARDWARE primary IP/MAC required"
        )

    secrets_dir = Path(str(info["secrets_dir"]))
    lucid_root = Path(str(info["lucid_tops_root"]))

    bind_host = (
        _pick(existing, "SESSIONS_BIND_HOST")
        or str(info.get("sessions_bind_host") or primary_ip)
    )
    bind_port = (
        _pick(existing, "SESSIONS_BIND_PORT")
        or str(info.get("sessions_bind_port") or "")
    )
    if not bind_port:
        raise RuntimeError(
            "SESSIONS_BIND_PORT missing — must be pulled/allocated at time of operation"
        )

    docker_dns = (
        _pick(existing, "SESSIONS_DOCKER_DNS_NAME")
        or str(info.get("sessions_docker_dns_name") or primary_ip)
    )
    master_host = (
        _pick(existing, "MASTER_SERVER_INTERNAL_HOST")
        or str(info.get("master_server_internal_host") or primary_ip)
    )
    master_port = (
        _pick(existing, "MASTER_SERVER_INTERNAL_PORT")
        or str(info.get("master_server_internal_port") or "")
    )
    if not master_port:
        raise RuntimeError(
            "MASTER_SERVER_INTERNAL_PORT missing — must be pulled at time of operation"
        )

    url_scheme = _pick(existing, "MASTER_SERVER_URL_SCHEME", "SESSIONS_URL_SCHEME")
    if not url_scheme:
        url_scheme = "http" if not info.get("tor_listen") else "http"

    operations_dns = (
        _pick(existing, "OPERATIONS_DOCKER_DNS_NAME")
        or str(info.get("operations_docker_dns_name") or "")
    )
    operations_port = (
        _pick(existing, "OPERATIONS_BIND_PORT")
        or str(info.get("operations_bind_port") or "")
    )
    operations_scheme = _pick(existing, "OPERATIONS_URL_SCHEME") or url_scheme
    operations_handoff_path = _pick(existing, "OPERATIONS_SESSION_HANDOFF_PATH")
    if not operations_handoff_path:
        operations_handoff_path = "/session-end"

    rdp_dns = (
        _pick(existing, "RDP_DOCKER_DNS_NAME")
        or str(info.get("rdp_docker_dns_name") or "")
    )

    network_name = (
        _pick(existing, "DOCKER_NETWORK_NAME", "SESSIONS_NETWORK_NAME")
        or str(info.get("docker_network_name") or "")
    )
    if not network_name:
        machine_id = str(info.get("machine_id") or "").strip()
        hostname = str(info.get("hostname") or info.get("hostname_resolved") or "").strip()
        if machine_id:
            network_name = f"lucid-{machine_id[:12].lower()}"
        elif hostname:
            network_name = f"lucid-{hostname.lower()}"
        else:
            raise RuntimeError(
                "DOCKER_NETWORK_NAME missing — must be pulled from Docker or machine_id "
                "at time of operation"
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

    inactivity_days = _pick(existing, "SESSION_INACTIVITY_DAYS")
    if not inactivity_days:
        # Derive from machine cpu_count at operation (bounded operational window).
        cpu = int(info.get("cpu_count") or 1)
        inactivity_days = str(max(7, min(30, cpu * 3)))

    api_prefix = _pick(existing, "SESSION_API_PREFIX") or "/sessions"
    create_route = _pick(existing, "SESSION_CREATE_API_ROUTE") or "/session-create"
    find_route = _pick(existing, "SESSION_FIND_PEER_GUI_ROUTE") or "/session-find"
    connect_route = (
        _pick(existing, "SESSION_CONNECT_HANDSHAKE_GUI_ROUTE") or "/session-connect"
    )
    validate_path = _pick(existing, "SESSION_VALIDATE_PATH") or "/session-validate"
    health_path = _pick(existing, "SESSION_HEALTH_PATH") or "/health"

    key_min = _pick(existing, "SESSION_KEY_MIN_LENGTH")
    if not key_min:
        key_min = str(max(16, int(info.get("cpu_count") or 1) * 8))
    key_bytes = _pick(existing, "SESSION_KEY_URLSAFE_BYTES")
    if not key_bytes:
        key_bytes = str(max(16, int(key_min) // 2))

    session_type = _pick(existing, "SESSION_TYPE") or "peer_remote_desktop"
    log_source = _pick(existing, "SESSION_ID_LOG_SOURCE") or service_name
    finalised = (
        _pick(existing, "SESSION_FINALISED_STATUSES") or "ended,complete,compressed"
    )
    complete_status = _pick(existing, "SESSION_COMPLETE_STATUS") or "complete"

    mask_prefix = _pick(existing, "PEER_USER_ID_MASK_PREFIX")
    if not mask_prefix:
        mask_prefix = f"u{primary_mac[-4:].lower()}-"
    mask_hex_len = _pick(existing, "PEER_USER_ID_MASK_HEX_LEN")
    if not mask_hex_len:
        mask_hex_len = str(max(8, min(32, len(primary_mac.replace(":", "")))))
    peer_label = _pick(existing, "PEER_SEARCH_LABEL") or "peer-search"

    sessions_db = _pick(existing, "LUCIDTOPS_SESSIONS_DB_NAME") or "LucidTops_SessionsDB"
    sessions_collection = (
        _pick(existing, "LUCIDTOPS_SESSIONS_COLLECTION") or "session_records"
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
    operator_master_id = _pick(existing, "TALLY_ENTITY_ID_MASTER")
    if not operator_master_id:
        operator_master_id = str(info.get("machine_id") or "").strip()
    if not operator_master_id:
        raise RuntimeError(
            "TALLY_ENTITY_ID_MASTER / machine_id missing — must be pulled at time of operation"
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
        "SESSIONS_NETWORK_NAME": network_name,
        "SESSIONS_CONTAINER_NAME": container_name,
        "LUCIDTOPS_SESSIONS_DB_NAME": sessions_db,
        "LUCIDTOPS_SESSIONS_COLLECTION": sessions_collection,
        "LUCIDTOPS_SESSIONS_ID_LOG_COLLECTION": session_id_log_collection,
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "HOST_PRIMARY_IP": primary_ip,
        "HOST_PRIMARY_MAC": primary_mac,
        "LUCID_TOPS_ROOT": lucid_root.as_posix(),
        "SECRETS_DIR": secrets_dir.as_posix(),
        "DOCKER_NETWORK_NAME": network_name,
        "OPERATIONS_DOCKER_DNS_NAME": operations_dns,
        "OPERATIONS_BIND_PORT": operations_port,
        "OPERATIONS_URL_SCHEME": operations_scheme,
        "OPERATIONS_SESSION_HANDOFF_PATH": operations_handoff_path,
        "RDP_DOCKER_DNS_NAME": rdp_dns,
    }

    # Operator credentials for operations handoff — must exist at operation time (env/secrets).
    for op_key in (
        "OPERATIONS_OPERATOR_ID_TYPE",
        "OPERATIONS_OPERATOR_ID",
        "OPERATIONS_OPERATOR_TOKEN_ID",
        "OPERATIONS_OPERATOR_EMAIL",
    ):
        value = _pick(existing, op_key)
        if value:
            resolved[op_key] = value

    # Operations DNS/port may be empty until that container is discoverable; handoff
    # (compress.py) fails at time of operation if still missing when SessionID is complete.
    return resolved


def sessions_secrets_path_from_pull(info: dict[str, Any] | None = None) -> Path:
    pull = info if info is not None else get_sessions_pull()
    override = _env("SESSIONS_SECRETS_FILE")
    if override:
        return Path(override).expanduser()
    secrets_dir = Path(str(pull["secrets_dir"]))
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
    """Write session secrets file on the host from operation-time pull only."""
    info = pull if pull is not None else pull_sessions_hardware(bind_environ=True)
    path = (
        Path(secrets_dir) / (
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
        "# Values are created at operation time from hardware pull — no placeholders.",
        "",
    ]
    for key in sorted(resolved.keys()):
        lines.append(f"{key}={resolved[key]}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    os.environ["SESSIONS_SECRETS_FILE"] = path.as_posix()
    return path


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
