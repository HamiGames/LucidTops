"""Generate Docker Compose YAML for LucidTops separate MongoDB containers at operation time.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from Dns_databases import ALL_NAMED_DB_CONTAINERS, DB_ZONE, secret_key_prefix
from databases_secrets import require_secret, utc_now


def _require_from_values(values: dict[str, str], key: str) -> str:
    value = str(values.get(key, "")).strip()
    if not value:
        value = require_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing — must be created at time of operation in databases.secrets"
        )
    return value


def _yaml_key(name: str) -> str:
    """Quote network/service keys when they contain YAML-sensitive characters."""
    if any(ch in name for ch in ("-", ":", "#", " ", "'", '"')):
        escaped = name.replace('"', '\\"')
        return f'"{escaped}"'
    return name


def _network_block(name: str, *, external: bool) -> list[str]:
    key = _yaml_key(name)
    if external:
        return [
            f"  {key}:",
            f"    name: {name}",
            "    external: true",
        ]
    return [
        f"  {key}:",
        f"    name: {name}",
        "    driver: bridge",
    ]


def build_databases_compose_yaml(values: dict[str, str]) -> str:
    """Emit compose YAML from secrets/pull values only — raises if any required key missing."""
    image = _require_from_values(values, "MONGODB_IMAGE")
    container_port = _require_from_values(values, "MONGODB_CONTAINER_PORT")
    data_in_container = _require_from_values(values, "MONGODB_DATA_PATH_IN_CONTAINER")
    tor_net = _require_from_values(values, "DOCKER_NETWORK_TOR_DB")
    nontor_net = _require_from_values(values, "DOCKER_NETWORK_NONTOR_DB")
    admin_user = _require_from_values(values, "MONGODB_ADMIN_USER")
    admin_password = _require_from_values(values, "MONGODB_ADMIN_PASSWORD")
    lucid_net = str(values.get("DOCKER_NETWORK_NAME", "")).strip()

    # Dedupe: when Master/proxy seed maps both zones to the same LucidDNS name,
    # emit a single networks: entry (YAML forbids duplicate mapping keys).
    network_names: list[str] = []
    for name in (tor_net, nontor_net):
        if name and name not in network_names:
            network_names.append(name)

    lines: list[str] = [
        "# LucidTops Databases compose — generated at time of operation",
        f"# Generated: {utc_now()}",
        "# Separate MongoDB container per named DB; Tor vs non-Tor networks.",
        "# Networks matching DOCKER_NETWORK_NAME (Proxy LucidDNS) are external.",
        "networks:",
    ]
    for name in network_names:
        external = bool(lucid_net) and name == lucid_net
        # Shared single-network alignment also treated as external LucidDNS join.
        if not external and len(network_names) == 1 and lucid_net and name == lucid_net:
            external = True
        if not external and len(network_names) == 1 and not lucid_net:
            # Only one network declared and no separate LucidDNS key — still may
            # already exist from Proxy; prefer external when tor==nontor.
            external = tor_net == nontor_net
        lines.extend(_network_block(name, external=external))

    lines.extend(["", "services:"])

    for db_name in ALL_NAMED_DB_CONTAINERS:
        prefix = secret_key_prefix(db_name)
        zone = DB_ZONE[db_name]
        network = tor_net if zone == "tor" else nontor_net
        data_mount = _require_from_values(values, f"{prefix}_DATA_MOUNT")
        host_port = _require_from_values(values, f"{prefix}_HOST_PORT")
        service_key = db_name.lower().replace("-", "_")

        lines.extend(
            [
                f"  {service_key}:",
                f"    image: {image}",
                f"    container_name: {db_name}",
                "    restart: unless-stopped",
                "    networks:",
                f"      - {_yaml_key(network)}",
                "    ports:",
                f'      - "{host_port}:{container_port}"',
                "    volumes:",
                f"      - {data_mount}:{data_in_container}",
                "    environment:",
                f"      MONGO_INITDB_ROOT_USERNAME: {admin_user}",
                f"      MONGO_INITDB_ROOT_PASSWORD: {admin_password}",
                f"      MONGO_INITDB_DATABASE: {db_name}",
                "    healthcheck:",
                '      test: ["CMD", "mongosh", "--eval", "db.adminCommand(\'ping\')"]',
                "      interval: 10s",
                "      timeout: 5s",
                "      retries: 8",
                "      start_period: 25s",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_databases_compose(
    values: dict[str, str],
    *,
    compose_path: Path | None = None,
) -> Path:
    path = compose_path
    if path is None:
        raw = values.get("DATABASES_COMPOSE_FILE", "").strip()
        if not raw:
            raise RuntimeError(
                "DATABASES_COMPOSE_FILE missing — must be set at time of operation"
            )
        path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = build_databases_compose_yaml(values)
    path.write_text(yaml_text, encoding="utf-8")
    return path


def compose_status(values: dict[str, str] | None = None) -> dict[str, Any]:
    values = values or {}
    compose_file = values.get("DATABASES_COMPOSE_FILE") or ""
    path = Path(compose_file) if compose_file else None
    return {
        "compose_file": compose_file,
        "compose_exists": bool(path and path.exists()),
        "services": list(ALL_NAMED_DB_CONTAINERS),
        "tor_network": values.get("DOCKER_NETWORK_TOR_DB", ""),
        "nontor_network": values.get("DOCKER_NETWORK_NONTOR_DB", ""),
        "lucid_network": values.get("DOCKER_NETWORK_NAME", ""),
    }
