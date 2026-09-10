#!/usr/bin/env python3
"""One-time script to launch and set up the LucidTops master server for the first time.
additions:
- the launch server will use the information from the console to determine the required ports and services to be installed and configured
- the launch server will start the tor daemon and configure the tor hidden service directories
- the launch server will configure the server environment variables to be used by the server
- the launch server will create the admin user and master class users
- the launch server will create the AdminUserID and MasterClassUserID( x5 MasterClassUsers max to exist)
- the launch server will use the information that it gains from the console to write the required *.secrets, torrc, docker network, and other required files to the console
- the launch server will configure the DockerDNS system according to the information from the console
- the launch server will operate the builderMasterServer.py script to build the master server, 
- the launch server will operate as a standalone script with the purpose of ensuring that the content for the master server container is built and configured correctly
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
ADMIN_USER_DIR = PROJECT_ROOT / "AdminUser"
MASTER_CLASS_USER_DIR = PROJECT_ROOT / "MasterClassUser"

HOST_TOR_SERVICE_DIR_ENV_KEYS: dict[str, str] = {
    "master_server": "HOST_TOR_SERVICE_DIR_MASTER",
    "frontend": "HOST_TOR_SERVICE_DIR_FRONTEND",
    "node_user": "HOST_TOR_SERVICE_DIR_NODE",
}


def _require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable {key} is missing")
    return value


def _require_env_int(key: str) -> int:
    raw = _require_env(key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"environment variable {key} must be an integer") from exc


@dataclass
class LaunchConfig:
    lucid_tops_root: Path
    secrets_dir: Path
    master_server_port: int
    gui_bridge_port: int
    mongodb_host: str
    mongodb_port: int
    docker_network_name: str
    enabled_services: tuple[str, ...]
    start_tor: bool = False
    non_interactive: bool = False

    def as_builder_dict(self) -> dict[str, Any]:
        return {
            "lucid_tops_root": self.lucid_tops_root.as_posix(),
            "secrets_dir": self.secrets_dir.as_posix(),
            "master_server_port": self.master_server_port,
            "gui_bridge_port": self.gui_bridge_port,
            "mongodb_host": self.mongodb_host,
            "mongodb_port": self.mongodb_port,
            "docker_network_name": self.docker_network_name,
            "enabled_services": self.enabled_services,
        }


def _prompt_value(
    label: str,
    current: str,
    *,
    non_interactive: bool,
) -> str:
    if non_interactive:
        if not current.strip():
            raise RuntimeError(f"non-interactive launch requires a value for: {label}")
        return current.strip()
    entered = input(f"{label} [{current}]: ").strip()
    value = entered or current
    if not value.strip():
        raise RuntimeError(f"required launch value missing for: {label}")
    return value.strip()


def _prompt_yes_no(label: str, default: bool, *, non_interactive: bool) -> bool:
    if non_interactive:
        return default
    default_label = "Y/n" if default else "y/N"
    entered = input(f"{label} [{default_label}]: ").strip().lower()
    if not entered:
        return default
    return entered in {"y", "yes", "1", "true"}


def collect_launch_config(args: argparse.Namespace) -> LaunchConfig:
    """Collect ports, services, and paths from the console or CLI flags."""
    from pull_information import bind_operation_environ, pull_realworld_information

    pull = pull_realworld_information()
    bind_operation_environ(pull)

    root_hint = (
        args.root
        or os.environ.get("LUCID_TOPS_ROOT", "").strip()
        or str(pull.get("lucid_tops_root") or "")
    )
    master_port_hint = str(
        args.master_port
        or os.environ.get("MASTER_SERVER_PORT", "")
        or pull.get("master_server_port")
        or ""
    ).strip()
    gui_port_hint = str(
        args.gui_port or os.environ.get("GUI_API_BRIDGE_PORT", "") or master_port_hint
    ).strip()
    mongodb_host_hint = (
        args.mongodb_host
        or os.environ.get("MONGODB_HOST", "")
        or str(pull.get("mongodb_host") or "")
    ).strip()
    mongodb_port_hint = str(
        args.mongodb_port
        or os.environ.get("MONGODB_PORT", "")
        or pull.get("mongodb_port")
        or ""
    ).strip()
    network_hint = (
        args.network
        or os.environ.get("DOCKER_NETWORK_NAME", "")
        or str(pull.get("docker_network_name") or "")
    ).strip()
    services_hint = (args.services or os.environ.get("ENABLED_SERVICES", "")).strip()
    non_interactive = args.yes

    if not non_interactive:
        print("LucidTops LaunchServer — console configuration")
        print(
            f"Hardware pull: IP={pull.get('primary_ip')} MAC={pull.get('primary_mac')} "
            f"host={pull.get('hostname')}"
        )
        print("Press Enter to accept values shown in [brackets] when provided by env/flags/pull.")

    root_text = _prompt_value("LucidTops root directory", root_hint, non_interactive=non_interactive)
    master_port_text = _prompt_value(
        "Master server port",
        master_port_hint,
        non_interactive=non_interactive,
    )
    gui_port_text = _prompt_value(
        "GUI bridge port",
        gui_port_hint,
        non_interactive=non_interactive,
    )
    mongodb_host = _prompt_value(
        "MongoDB Docker DNS host",
        mongodb_host_hint,
        non_interactive=non_interactive,
    )
    mongodb_port_text = _prompt_value(
        "MongoDB port",
        mongodb_port_hint,
        non_interactive=non_interactive,
    )
    network_name = _prompt_value(
        "Docker network name",
        network_hint,
        non_interactive=non_interactive,
    )
    services_text = _prompt_value(
        "Enabled services (comma-separated)",
        services_hint,
        non_interactive=non_interactive,
    )
    # Tor daemon is owned by Proxy; default off for MasterServer launch.
    start_tor = _prompt_yes_no(
        "Start local Tor daemon for hidden-service bootstrap",
        False if not getattr(args, "start_tor", False) else args.start_tor,
        non_interactive=non_interactive,
    )

    root_path = Path(root_text).expanduser()
    enabled = tuple(
        service.strip()
        for service in services_text.split(",")
        if service.strip()
    )
    if not enabled:
        raise RuntimeError("ENABLED_SERVICES must list at least one service")

    secrets_dir_hint = (
        args.secrets_dir
        or os.environ.get("SECRETS_DIR", "")
        or str(pull.get("secrets_dir") or "")
    ).strip()
    if not secrets_dir_hint:
        raise RuntimeError("SECRETS_DIR must be provided via --secrets-dir, environment, or hardware pull")

    return LaunchConfig(
        lucid_tops_root=root_path,
        secrets_dir=Path(secrets_dir_hint).expanduser(),
        master_server_port=int(master_port_text),
        gui_bridge_port=int(gui_port_text),
        mongodb_host=mongodb_host,
        mongodb_port=int(mongodb_port_text),
        docker_network_name=network_name,
        enabled_services=enabled,
        start_tor=start_tor,
        non_interactive=non_interactive,
    )


def _apply_launch_config_to_process_env(config: LaunchConfig) -> None:
    """Apply console-derived settings so builder/config modules resolve the same values."""
    os.environ["LUCID_TOPS_ROOT"] = config.lucid_tops_root.as_posix()
    os.environ["SECRETS_DIR"] = config.secrets_dir.as_posix()
    os.environ["SERVER_ENV_FILE"] = str(config.lucid_tops_root / "server.env")
    os.environ["SECRETS_ENV_FILE"] = str(config.lucid_tops_root / "secrets.env")
    os.environ["CONFIG_SECRETS_FILE"] = str(config.secrets_dir / "config.secrets")
    os.environ["OPERATIONS_SECRETS_FILE"] = str(config.secrets_dir / "operations.secrets")
    os.environ["HOST_TOR_CONFIG_TORRC"] = str(config.lucid_tops_root / "torrc")
    os.environ["MASTER_SERVER_PORT"] = str(config.master_server_port)
    os.environ["GUI_API_BRIDGE_PORT"] = str(config.gui_bridge_port)
    os.environ["MONGODB_HOST"] = config.mongodb_host
    os.environ["MONGODB_PORT"] = str(config.mongodb_port)
    os.environ["DOCKER_NETWORK_NAME"] = config.docker_network_name
    os.environ["ENABLED_SERVICES"] = ",".join(config.enabled_services)


def _host_tor_paths(config: LaunchConfig) -> dict[str, Path]:
    tor_root = config.lucid_tops_root / "data" / "tor"
    paths: dict[str, Path] = {}
    for key, env_key in HOST_TOR_SERVICE_DIR_ENV_KEYS.items():
        dirname = _require_env(env_key)
        paths[key] = tor_root / dirname
    return paths


def _ensure_tor_hidden_service_directories(config: LaunchConfig) -> list[str]:
    created: list[str] = []
    tor_root = config.lucid_tops_root / "data" / "tor"
    onion_dir = tor_root / "onion"
    for path in (*_host_tor_paths(config).values(), onion_dir, config.secrets_dir):
        path.mkdir(parents=True, exist_ok=True)
        created.append(path.as_posix())
    return created


def _build_host_torrc(config: LaunchConfig) -> Path:
    from config import get_config_int, get_config_value, utc_now

    tor_root = config.lucid_tops_root / "data" / "tor"
    host_torrc = config.lucid_tops_root / "configs" / "torrc.host"
    host_torrc.parent.mkdir(parents=True, exist_ok=True)
    paths = _host_tor_paths(config)
    forward_host = get_config_value("HIDDEN_SERVICE_FORWARD_HOST")
    socks_host = get_config_value("TOR_HOST")
    socks_port = get_config_int("TOR_SOCKS_PORT")
    control_port = get_config_int("TOR_CONTROL_PORT")
    lines = [
        "# LucidTops host bootstrap torrc - generated by backend/LaunchServer.py",
        f"# Generated: {utc_now()}",
        f"DataDirectory {tor_root.as_posix()}",
        "Log notice stdout",
        f"SocksPort {socks_host}:{socks_port}",
        f"ControlPort {socks_host}:{control_port}",
        "CookieAuthentication 1",
        "RunAsDaemon 0",
        "",
        f"HiddenServiceDir {paths['master_server'].as_posix()}",
        "HiddenServiceVersion 3",
        f"HiddenServicePort 80 {forward_host}:{config.master_server_port}",
        "",
        f"HiddenServiceDir {paths['frontend'].as_posix()}",
        "HiddenServiceVersion 3",
        f"HiddenServicePort 80 {forward_host}:{config.gui_bridge_port}",
        "",
        f"HiddenServiceDir {paths['node_user'].as_posix()}",
        "HiddenServiceVersion 3",
        f"HiddenServicePort 80 {forward_host}:{config.master_server_port}",
        "",
    ]
    host_torrc.write_text("\n".join(lines), encoding="utf-8")
    return host_torrc


def _start_tor_daemon(config: LaunchConfig) -> dict[str, Any]:
    tor_binary = shutil.which("tor")
    if tor_binary is None:
        return {"started": False, "reason": "tor binary not found on PATH"}

    host_torrc = _build_host_torrc(config)
    try:
        process = subprocess.Popen(
            [tor_binary, "-f", str(host_torrc)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return {"started": False, "reason": str(exc), "torrc": str(host_torrc)}

    return {
        "started": True,
        "pid": process.pid,
        "torrc": host_torrc.as_posix(),
        "process": process,
    }


def _tor_hostname_poll_settings() -> tuple[int, float]:
    return _require_env_int("TOR_HOSTNAME_POLL_SECONDS"), float(
        _require_env("TOR_HOSTNAME_POLL_INTERVAL")
    )


def _wait_for_onion_hostnames(config: LaunchConfig) -> dict[str, str | None]:
    poll_seconds, poll_interval = _tor_hostname_poll_settings()
    deadline = time.time() + poll_seconds
    addresses: dict[str, str | None] = {key: None for key in HOST_TOR_SERVICE_DIR_ENV_KEYS}
    host_paths = _host_tor_paths(config)
    while time.time() < deadline:
        for key, path in host_paths.items():
            if addresses[key]:
                continue
            addresses[key] = _read_onion_address(path)
        if all(addresses.values()):
            break
        time.sleep(poll_interval)
    return addresses


def _sync_onion_files(config: LaunchConfig, addresses: dict[str, str | None]) -> list[str]:
    written: list[str] = []
    onion_dir = config.lucid_tops_root / "data" / "tor" / "onion"
    onion_dir.mkdir(parents=True, exist_ok=True)
    for key, onion in addresses.items():
        if not onion:
            continue
        service_dir = _require_env(HOST_TOR_SERVICE_DIR_ENV_KEYS[key])
        path = onion_dir / f"{service_dir}.onion"
        path.write_text(onion + "\n", encoding="utf-8")
        written.append(path.as_posix())
    return written


def _print_generated_files_to_console(config: LaunchConfig, build_result: dict[str, Any]) -> None:
    print("\nGenerated configuration files:")
    for label, key in (
        ("server.env", "server_env"),
        ("secrets.env", "secrets_env"),
        ("torrc", "torrc"),
        ("docker-dns.env", "docker_dns_env"),
        ("docker-network.yml", "docker_network_yml"),
        ("build manifest", "manifest"),
    ):
        value = build_result.get(key)
        if value:
            print(f"  {label}: {value}")
    print("\nDockerDNS registry:")
    print(f"  network: {config.docker_network_name}")
    print(f"  mongodb: {config.mongodb_host}:{config.mongodb_port}")
    print(f"  services: {', '.join(config.enabled_services)}")
    print(f"  master port: {config.master_server_port}")
    print(f"  gui bridge port: {config.gui_bridge_port}")


def _read_onion_address(hidden_service_dir: Path) -> str | None:
    hostname_file = hidden_service_dir / "hostname"
    try:
        return hostname_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _onion_stem_map() -> dict[str, str]:
    return {
        _require_env("HOST_TOR_SERVICE_DIR_MASTER"): "master_server",
        _require_env("HOST_TOR_SERVICE_DIR_FRONTEND"): "frontend",
        _require_env("HOST_TOR_SERVICE_DIR_NODE"): "node_user",
    }


def _collect_onion_addresses(config: LaunchConfig | None = None) -> dict[str, str | None]:
    from config import CONTAINER_ONION_DIR, TOR_HIDDEN_SERVICE_DIRS, ensure_runtime_settings

    ensure_runtime_settings()
    addresses: dict[str, str | None] = {}
    if config is not None:
        for name, path in _host_tor_paths(config).items():
            addresses[name] = _read_onion_address(path)
    for name, path in TOR_HIDDEN_SERVICE_DIRS.items():
        if not addresses.get(name):
            addresses[name] = _read_onion_address(path)
    stem_map = _onion_stem_map()
    container_dir = CONTAINER_ONION_DIR
    if container_dir.exists():
        for item in container_dir.glob("*.onion"):
            mapped = stem_map.get(item.stem, item.stem)
            addresses[mapped] = item.read_text(encoding="utf-8").strip()
    if config is not None:
        onion_dir = config.lucid_tops_root / "data" / "tor" / "onion"
        if onion_dir.exists():
            for item in onion_dir.glob("*.onion"):
                mapped = stem_map.get(item.stem, item.stem)
                if not addresses.get(mapped):
                    addresses[mapped] = item.read_text(encoding="utf-8").strip()
    return addresses


def _update_server_env_onions(
    addresses: dict[str, str | None],
    *,
    server_env_path: Path | None = None,
) -> None:
    from builderMasterServer import TOR_ROUTES_MANIFEST_FILENAME, apply_tor_service_env_updates
    from config import SERVER_ENV_PATH

    env_path = server_env_path or SERVER_ENV_PATH
    if not env_path.exists():
        return
    tor_routes_path = env_path.parent / "configs" / TOR_ROUTES_MANIFEST_FILENAME
    apply_tor_service_env_updates(
        server_env_path=env_path,
        onions=addresses,
        tor_routes_manifest_path=tor_routes_path,
    )


def _write_account_file(
    directory: Path,
    filename: str,
    accounts: list[dict[str, str]],
) -> Path:
    from config import utc_now

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    lines = [
        "# LucidTops bootstrap credentials - store securely",
        f"# Generated: {utc_now()}",
        "",
    ]
    for index, account in enumerate(accounts, start=1):
        lines.append(f"[Account {index}]")
        for key, value in account.items():
            lines.append(f"{key}={value}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _create_admin_user(client: Any) -> Path | None:
    from config import get_master_db, utc_now
    from MasterDBSchema import ADMIN_USERS_COLLECTION

    db = get_master_db(client)
    if db[ADMIN_USERS_COLLECTION].count_documents({}) >= 1:
        existing_path = ADMIN_USER_DIR / "admin.txt"
        return existing_path if existing_path.exists() else None

    admin_id = secrets.token_hex(4)
    password = secrets.token_urlsafe(16)
    id_token = secrets.token_urlsafe(32)
    now = utc_now()
    record = {
        "adminUserID": admin_id,
        "IDToken": id_token,
        "access_level": "admin",
        "access_type": "bootstrap",
        "admin_registration_timestamp": now,
        "password": password,
        "created_at": now,
        "updated_at": now,
    }
    db[ADMIN_USERS_COLLECTION].update_one(
        {"adminUserID": admin_id},
        {"$set": record},
        upsert=True,
    )
    return _write_account_file(
        ADMIN_USER_DIR,
        "admin.txt",
        [{"adminUserID": admin_id, "password": password, "IDToken": id_token}],
    )


def _create_master_class_users(client: Any) -> Path | None:
    from config import get_config_int, get_master_db, utc_now
    from MasterDBSchema import MASTER_CLASS_USERS_COLLECTION

    max_users = get_config_int("MAX_MASTER_CLASS_USERS")
    db = get_master_db(client)
    existing_count = db[MASTER_CLASS_USERS_COLLECTION].count_documents({})
    if existing_count >= max_users:
        existing_path = MASTER_CLASS_USER_DIR / "master.txt"
        return existing_path if existing_path.exists() else None

    accounts: list[dict[str, str]] = []
    now = utc_now()
    to_create = max_users - existing_count
    for index in range(1, to_create + 1):
        mc_id = secrets.token_hex(4)
        password = secrets.token_urlsafe(16)
        id_token = secrets.token_urlsafe(32)
        db[MASTER_CLASS_USERS_COLLECTION].update_one(
            {"MasterClassUserID": mc_id},
            {
                "$set": {
                    "MasterClassUserID": mc_id,
                    "IDToken": id_token,
                    "access_level": "master_class",
                    "access_type": f"bootstrap_{index}",
                    "masterclass_registration_timestamp": now,
                    "password": password,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        accounts.append(
            {
                "MasterClassUserID": mc_id,
                "password": password,
                "IDToken": id_token,
            }
        )
    return _write_account_file(MASTER_CLASS_USER_DIR, "master.txt", accounts)


def launch_server(
    config: LaunchConfig,
    *,
    run_uvicorn: bool = False,
) -> dict[str, Any]:
    """Run builder, onion setup, bootstrap accounts, and optionally start the server."""
    _apply_launch_config_to_process_env(config)

    from builderMasterServer import (
        _get_mongo_client_for_launch,
        build_master_server,
    )

    tor_dirs = _ensure_tor_hidden_service_directories(config)

    build_result = build_master_server(config.as_builder_dict())
    _print_generated_files_to_console(config, build_result)

    tor_status: dict[str, Any] = {"started": False}
    if config.start_tor:
        tor_status = _start_tor_daemon(config)
        if tor_status.get("started"):
            polled = _wait_for_onion_hostnames(config)
            _sync_onion_files(config, polled)

    onion_addresses = _collect_onion_addresses(config)
    _update_server_env_onions(
        onion_addresses,
        server_env_path=config.lucid_tops_root / "server.env",
    )
    onion_files = _sync_onion_files(config, onion_addresses)

    admin_file: str | None = None
    master_file: str | None = None
    client = _get_mongo_client_for_launch(config.as_builder_dict())
    if client is not None:
        try:
            admin_path = _create_admin_user(client)
            master_path = _create_master_class_users(client)
            admin_file = str(admin_path) if admin_path else None
            master_file = str(master_path) if master_path else None
        finally:
            client.close()

    result = {
        **build_result,
        "tor_hidden_service_dirs": tor_dirs,
        "tor_daemon": {
            "started": tor_status.get("started", False),
            "torrc": tor_status.get("torrc"),
            "reason": tor_status.get("reason"),
        },
        "onion_addresses": {k: v for k, v in onion_addresses.items() if v},
        "onion_files": onion_files,
        "admin_credentials_file": admin_file,
        "master_class_credentials_file": master_file,
        "launch_complete": True,
    }

    if run_uvicorn:
        from main import run_server

        run_server()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LucidTops master server")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start uvicorn after setup (Docker container runtime)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Use defaults/flags without interactive console prompts",
    )
    parser.add_argument("--root", help="LucidTops root directory (SSD mount path)")
    parser.add_argument("--secrets-dir", help="Secrets directory override")
    parser.add_argument("--master-port", type=int, help="Master server port")
    parser.add_argument("--gui-port", type=int, help="GUI bridge port")
    parser.add_argument("--mongodb-host", help="MongoDB Docker DNS hostname")
    parser.add_argument("--mongodb-port", type=int, help="MongoDB port")
    parser.add_argument("--network", help="Docker network name")
    parser.add_argument(
        "--services",
        help="Comma-separated Docker services to enable (e.g. lucid-mongodb,lucid-server-default)",
    )
    parser.add_argument(
        "--start-tor",
        action="store_true",
        help="Start local Tor daemon for hidden-service bootstrap",
    )
    args = parser.parse_args()

    config = collect_launch_config(args)
    print(
        f"LaunchServer: root={config.lucid_tops_root} "
        f"secrets={config.secrets_dir} network={config.docker_network_name}"
    )
    result = launch_server(config, run_uvicorn=args.serve)
    print("LucidTops LaunchServer complete.")
    for key, value in result.items():
        print(f"  {key}: {value}")
    if not result.get("onion_addresses"):
        print(
            "  note: No *.onion hostnames found yet. Start tor daemon and re-run LaunchServer.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
