""" this is the SetDeamon for the LucidTops system, it is used to set the daemon for the system.
it sets the daemon for Tor Hidden Service and Docker Network using hardware pull at run time.
includes:
- pull_information(): pulls IP, MAC, binaries, listeners, Docker state from the host hardware
  at time of operation (when this script runs).
- apply_pull_to_daemon_configuration(): writes pulled IP/MAC into proxy.secrets and derives
  TOR_HS_TARGET_HOST, TOR_SOCKS_HOST, TOR_HS_ACTIVE, TOR_HS_FORWARD_PORTS, tor/nginx unit names.
- builds nginx reverse proxy config from pull-created secrets (MasterServer / Node / Frontend).
- builds Torrc HiddenServiceDir / HiddenServicePort stanzas from pulled HS dirs and forward map.
- starts/stops/reloads hardware Tor and nginx via systemctl / nginx binaries discovered on host.
- verify_tor_call(): Call Tor test against pulled SOCKS/control endpoints.
- compatible with uvicorn server and FastAPI system.

restrictions:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- at time of operation = the event when this script is run.
- values MUST be PULLED and configured from real-world hardware (IP, MAC, etc.)
  via pull_information (buildsecrets.pull_realworld_information).
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository for operational values.

"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROXY_DIR = Path(__file__).resolve().parent
if str(_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(_PROXY_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _PROXY_DIR / file_name
    registry = f"lucid_proxy_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_buildsecrets = _load_local("buildsecrets")
get_tor_hidden_service_dirs = _buildsecrets.get_tor_hidden_service_dirs
build_and_write_proxy_secrets = _buildsecrets.build_and_write_proxy_secrets
get_proxy_secret = _buildsecrets.get_proxy_secret
require_proxy_secret = _buildsecrets.require_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
parse_secrets_file = _buildsecrets.parse_secrets_file
write_secrets_file = _buildsecrets.write_secrets_file
pull_realworld_information = _buildsecrets.pull_realworld_information

_LAST_DAEMON_PULL: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def pull_information() -> dict[str, Any]:
    """
    Required pull-information entry for daemon setup.
    Pulls IP, MAC, binaries, listeners, Docker state from hardware at time of operation.
    """
    global _LAST_DAEMON_PULL
    pull = pull_realworld_information()
    _LAST_DAEMON_PULL = pull
    return pull


def _proxy_secrets_file() -> Path:
    return Path(require_proxy_secret("PROXY_SECRETS_FILE")).expanduser()


def _merge_proxy_secrets(updates: dict[str, str]) -> dict[str, str]:
    """Persist operational values into proxy.secrets (sensitive + runtime config)."""
    secrets_path = _proxy_secrets_file()
    current = parse_secrets_file(secrets_path)
    current.update({key: value for key, value in updates.items() if value})
    write_secrets_file(secrets_path, current)
    return load_proxy_secrets(reload=False)


def _normalize_token(value: str) -> str:
    return value.strip().lower().replace("-", "").replace("_", "")


def _pull_bin_from_hardware(pull: dict[str, Any], bin_key: str) -> str:
    bins = dict(pull.get("bins") or {})
    path = str(bins.get(bin_key) or "").strip()
    if path and Path(path).exists():
        return path
    found = shutil.which(bin_key)
    return found or ""


def _derive_active_hs_keys(
    pull: dict[str, Any], selected: frozenset[str]
) -> list[str]:
    """
    Decide which HiddenService dirs are active from pulled Docker containers
    and selected-container set created at operation.
    """
    hs_dirs = get_tor_hidden_service_dirs(pull=pull)
    containers = {
        _normalize_token(name): meta
        for name, meta in dict(pull.get("docker_containers") or {}).items()
    }
    selected_norm = {_normalize_token(item) for item in selected}
    active: list[str] = []

    for hs_key in hs_dirs:
        key_norm = _normalize_token(hs_key)
        matched = False
        for sel in selected_norm:
            if sel and (sel in key_norm or key_norm in sel):
                matched = True
                break
        if not matched:
            for cname in containers:
                if key_norm in cname or cname in key_norm:
                    matched = True
                    break
        if matched:
            active.append(hs_key)

    if not active:
        active = list(hs_dirs.keys())
    return active


def _forward_port_for_hs_key(hs_key: str, *, pull: dict[str, Any]) -> str:
    """
    Local forward port for an HS key from pull + secrets:
    MasterServer HS dir / backend DockerDNS match → MASTER_SERVER_PORT;
    otherwise → PROXY_NGINX_LISTEN_PORT.
    """
    key_norm = _normalize_token(hs_key)
    backend_dns = get_proxy_secret("PROXY_BACKEND_DNS")
    master_hs_dir = get_proxy_secret("TOR_HS_DIR_MASTER_SERVER")
    if master_hs_dir:
        master_name = _normalize_token(Path(master_hs_dir).name)
        if master_name and master_name == key_norm:
            return require_proxy_secret("MASTER_SERVER_PORT")

    containers = dict(pull.get("docker_containers") or {})
    for cname, meta in containers.items():
        cn = _normalize_token(cname)
        if not (key_norm in cn or cn in key_norm):
            continue
        ip = str(meta.get("ip") or "")
        name = str(meta.get("name") or "")
        if backend_dns and backend_dns in {ip, name, cname}:
            return require_proxy_secret("MASTER_SERVER_PORT")

    return require_proxy_secret("PROXY_NGINX_LISTEN_PORT")


def apply_pull_to_daemon_configuration(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """
    Create/refresh daemon-related proxy.secrets keys from real-world pull at operation.
    Tor unit must be tor@default (fixes.txt §17), never bare tor multi-instance master.
    """
    info = pull if pull is not None else pull_information()
    build_and_write_proxy_secrets(overwrite_keys=False)
    load_proxy_secrets(reload=False)
    prior = load_proxy_secrets(reload=False)

    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip or not primary_mac:
        raise RuntimeError(
            "pull_information failed — HARDWARE primary IP/MAC required for daemon setup"
        )

    systemctl_bin = _pull_bin_from_hardware(info, "systemctl")
    tor_bin = _pull_bin_from_hardware(info, "tor")
    nginx_bin = _pull_bin_from_hardware(info, "nginx")
    docker_bin = _pull_bin_from_hardware(info, "docker")

    socks_host, socks_port = _buildsecrets._pull_tor_socks_endpoint(info, prior=prior)
    tor_unit = str(info.get("tor_systemd_unit") or "").strip()
    tor_unit = _buildsecrets._pull_tor_systemd_unit(
        systemctl_bin or None,
        prior={**prior, "TOR_SYSTEMD_UNIT": tor_unit or prior.get("TOR_SYSTEMD_UNIT", "")},
    )

    updates: dict[str, str] = {
        "HARDWARE_PRIMARY_IP": primary_ip,
        "HARDWARE_PRIMARY_MAC": primary_mac,
        "HARDWARE_PRIMARY_IFACE": str(info.get("primary_iface") or ""),
        "HOSTNAME_CONSOLE": str(info.get("hostname") or ""),
        "TOR_HS_TARGET_HOST": primary_ip,
        "TOR_SOCKS_HOST": socks_host,
        "TOR_SOCKS_PORT": socks_port,
        "TOR_SYSTEMD_UNIT": tor_unit,
        "PROXY_FASTAPI_UPSTREAM_HOST": primary_ip,
        "PROXY_FASTAPI_BIND_HOST": get_proxy_secret("PROXY_FASTAPI_BIND_HOST")
        or primary_ip,
    }

    if tor_bin:
        updates["TOR_BIN"] = tor_bin
        updates["TOR_BIN_NAME"] = Path(tor_bin).name
    if nginx_bin:
        updates["NGINX_BIN"] = nginx_bin
        updates["NGINX_BIN_NAME"] = Path(nginx_bin).name
        updates["NGINX_SYSTEMD_UNIT"] = Path(nginx_bin).stem
    if systemctl_bin:
        updates["SYSTEMCTL_BIN"] = systemctl_bin
        updates["SYSTEMCTL_BIN_NAME"] = Path(systemctl_bin).name
    if docker_bin:
        updates["DOCKER_BIN"] = docker_bin
        updates["DOCKER_BIN_NAME"] = Path(docker_bin).name

    tor_listen = info.get("tor_listen")
    if isinstance(tor_listen, tuple) and len(tor_listen) == 2:
        listen_host, listen_port = tor_listen
        updates["TOR_SOCKS_HOST"] = str(listen_host or "127.0.0.1")
        if listen_port:
            updates["TOR_SOCKS_PORT"] = str(listen_port)

    nginx_listen = info.get("nginx_listen")
    if isinstance(nginx_listen, tuple) and len(nginx_listen) == 2:
        _nhost, nport = nginx_listen
        if nport:
            updates["PROXY_NGINX_LISTEN_PORT"] = str(nport)
            updates["TOR_HS_VIRTUAL_PORT"] = str(nport)

    selected = frozenset(
        item.strip().lower()
        for item in require_proxy_secret("PROXY_SELECTED_CONTAINERS").split(",")
        if item.strip()
    )
    active_hs = _derive_active_hs_keys(info, selected)
    updates["TOR_HS_ACTIVE"] = ",".join(active_hs)

    forward_pairs: list[str] = []
    for hs_key in active_hs:
        port_val = _forward_port_for_hs_key(hs_key, pull=info)
        forward_pairs.append(f"{hs_key}={port_val}")
    updates["TOR_HS_FORWARD_PORTS"] = ",".join(forward_pairs)

    return _merge_proxy_secrets(updates)


def _ensure_operational_secrets() -> dict[str, str]:
    """Pull hardware state, then ensure proxy.secrets daemon keys exist."""
    pull = pull_information()
    return apply_pull_to_daemon_configuration(pull)


def _require(key: str) -> str:
    value = get_proxy_secret(key)
    if value:
        return value
    _ensure_operational_secrets()
    value = get_proxy_secret(key)
    if not value:
        raise RuntimeError(
            f"{key} missing from {_proxy_secrets_file().as_posix()} — "
            "value must be pulled/created at time of operation"
        )
    return value


def _optional(key: str) -> str:
    return get_proxy_secret(key)


def _selected_containers() -> frozenset[str]:
    raw = _require("PROXY_SELECTED_CONTAINERS")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _none_linking_containers() -> frozenset[str]:
    raw = _require("PROXY_NONE_LINKING_CONTAINERS")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _systemctl_bin() -> str | None:
    path = _optional("SYSTEMCTL_BIN")
    if path and Path(path).exists():
        return path
    name = _optional("SYSTEMCTL_BIN_NAME")
    if name:
        found = shutil.which(name)
        if found:
            _merge_proxy_secrets({"SYSTEMCTL_BIN": found})
            return found
    pull = _LAST_DAEMON_PULL or pull_information()
    found = _pull_bin_from_hardware(pull, "systemctl")
    if found:
        _merge_proxy_secrets(
            {"SYSTEMCTL_BIN": found, "SYSTEMCTL_BIN_NAME": Path(found).name}
        )
        return found
    return None


def _nginx_bin() -> str | None:
    path = _optional("NGINX_BIN")
    if path and Path(path).exists():
        return path
    name = _optional("NGINX_BIN_NAME")
    if name:
        found = shutil.which(name)
        if found:
            _merge_proxy_secrets({"NGINX_BIN": found})
            return found
    pull = _LAST_DAEMON_PULL or pull_information()
    found = _pull_bin_from_hardware(pull, "nginx")
    if found:
        _merge_proxy_secrets({"NGINX_BIN": found, "NGINX_BIN_NAME": Path(found).name})
        return found
    return None


def _tor_unit() -> str:
    return _require("TOR_SYSTEMD_UNIT")


def _nginx_unit() -> str:
    return _require("NGINX_SYSTEMD_UNIT")


def _active_hs_from_secrets() -> list[str]:
    raw = _require("TOR_HS_ACTIVE")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _hs_forward_port_map() -> dict[str, str]:
    raw = _require("TOR_HS_FORWARD_PORTS")
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, _, port = item.partition("=")
        key = key.strip()
        port = port.strip()
        if key and port:
            mapping[key] = port
    if not mapping:
        raise RuntimeError(
            "TOR_HS_FORWARD_PORTS empty — pull_information must create HS forward map"
        )
    return mapping


def ensure_hidden_service_dirs() -> dict[str, str]:
    """Ensure Tor Hidden Service directories exist for active HS keys from pull."""
    if not get_proxy_secret("TOR_HS_ACTIVE"):
        _ensure_operational_secrets()
    created: dict[str, str] = {}
    active = set(_active_hs_from_secrets())
    pull = _LAST_DAEMON_PULL or pull_information()
    hs_dirs = get_tor_hidden_service_dirs(pull=pull)
    for key, path in hs_dirs.items():
        if key not in active:
            continue
        path.mkdir(parents=True, exist_ok=True)
        created[key] = path.as_posix()
    return created


def build_nginx_reverse_proxy_config() -> Path:
    """
    Write nginx reverse-proxy config for:
    - Tor Hidden Service + Docker Network
    - MasterServer (uvicorn / FastAPI) via Proxy container
    - NodeUser (NodeUserID hosted database) via Proxy container
    - Frontend -> selected containers only (documentation/proxy.txt)

    Sensitive tokens remain in proxy.secrets - never embedded in this file.
    All bind/upstream values come from pull-created proxy.secrets.
    """
    if not get_proxy_secret("HARDWARE_PRIMARY_IP"):
        _ensure_operational_secrets()
    conf_path = Path(_require("NGINX_CONF_PATH")).expanduser()
    conf_path.parent.mkdir(parents=True, exist_ok=True)

    listen_port = _require("PROXY_NGINX_LISTEN_PORT")
    proxy_port = _require("PROXY_PORT")
    fastapi_upstream = _require("PROXY_FASTAPI_UPSTREAM_HOST")
    frontend_dns = _require("PROXY_FRONTEND_DNS")
    frontend_port = _require("FRONTEND_PORT")
    api_prefix = _require("PROXY_API_PREFIX").rstrip("/")
    docker_network = _require("DOCKER_NETWORK_NAME")
    keepalive_proxy = _require("PROXY_NGINX_KEEPALIVE_PROXY")
    keepalive_frontend = _require("PROXY_NGINX_KEEPALIVE_FRONTEND")
    client_max_body = _require("PROXY_NGINX_CLIENT_MAX_BODY")
    loc_proxy = _require("PROXY_NGINX_LOCATION_PROXY")
    loc_api = _require("PROXY_NGINX_LOCATION_API")
    loc_rdp = _require("PROXY_NGINX_LOCATION_RDP")
    loc_node = _require("PROXY_NGINX_LOCATION_NODE")
    hardware_ip = _require("HARDWARE_PRIMARY_IP")
    hardware_mac = _require("HARDWARE_PRIMARY_MAC")
    selected = ",".join(sorted(_selected_containers()))
    blocked = ",".join(sorted(_none_linking_containers()))

    deny_blocks: list[str] = []
    for name in sorted(_none_linking_containers()):
        deny_blocks.append(
            f"""
    location /{name}/ {{
        return 403;
    }}
"""
        )
    deny_section = "".join(deny_blocks)

    conf = f"""# LucidTops nginx reverse proxy - generated {utc_now()}
# Docker Network: {docker_network}
# Hardware IP/MAC (pulled): {hardware_ip} / {hardware_mac}
# Selected: {selected}
# None-linking blocked: {blocked}
# Sensitive values: see proxy.secrets (not stored in this file)

upstream lucid_proxy_fastapi {{
    server {fastapi_upstream}:{proxy_port};
    keepalive {keepalive_proxy};
}}

upstream lucid_frontend {{
    server {frontend_dns}:{frontend_port};
    keepalive {keepalive_frontend};
}}

server {{
    listen {listen_port};
    server_name _;

    client_max_body_size {client_max_body};
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";

    location {api_prefix}/ {{
        proxy_pass http://lucid_proxy_fastapi;
    }}

    location {loc_proxy} {{
        proxy_pass http://lucid_proxy_fastapi;
    }}

    location {loc_api} {{
        proxy_pass http://lucid_proxy_fastapi;
    }}

    location {loc_rdp} {{
        proxy_pass http://lucid_proxy_fastapi;
    }}

    location {loc_node} {{
        proxy_pass http://lucid_proxy_fastapi;
    }}
{deny_section}
    location / {{
        proxy_pass http://lucid_frontend;
    }}
}}
"""
    conf_path.write_text(conf, encoding="utf-8")
    mode_raw = _optional("PROXY_CONF_FILE_MODE")
    if mode_raw:
        try:
            os.chmod(conf_path, int(mode_raw, 0))
        except (OSError, ValueError):
            pass
    return conf_path


def build_torrc_hidden_service_snippet() -> Path:
    """
    Write Tor Hidden Service stanza using pulled hardware IP/MAC and
    TOR_HS_ACTIVE / TOR_HS_FORWARD_PORTS created at time of operation.
    """
    if not get_proxy_secret("TOR_HS_ACTIVE"):
        _ensure_operational_secrets()
    torrc_path = Path(_require("TORRC_PATH")).expanduser()
    torrc_path.parent.mkdir(parents=True, exist_ok=True)
    hs_dirs = ensure_hidden_service_dirs()
    forward_map = _hs_forward_port_map()

    socks_port = _require("TOR_SOCKS_PORT")
    control_port = _require("TOR_CONTROL_PORT")
    docker_network = _require("DOCKER_NETWORK_NAME")
    hs_target_host = _require("TOR_HS_TARGET_HOST")
    cookie_auth = _require("TOR_COOKIE_AUTHENTICATION")
    hs_virtual_port = _require("TOR_HS_VIRTUAL_PORT")
    hardware_ip = _require("HARDWARE_PRIMARY_IP")
    hardware_mac = _require("HARDWARE_PRIMARY_MAC")

    lines = [
        f"# LucidTops Tor daemon - generated {utc_now()}",
        f"# Docker Network: {docker_network}",
        f"# Hardware IP/MAC (pulled): {hardware_ip} / {hardware_mac}",
        f"SocksPort {socks_port}",
        f"ControlPort {control_port}",
        f"CookieAuthentication {cookie_auth}",
    ]

    for key, hs_path in hs_dirs.items():
        local_port = forward_map.get(key)
        if not local_port:
            continue
        lines.append(f"HiddenServiceDir {hs_path}")
        lines.append(
            f"HiddenServicePort {hs_virtual_port} {hs_target_host}:{local_port}"
        )

    Path(require_proxy_secret("PROXY_CONFIGS_DIR")).mkdir(parents=True, exist_ok=True)
    snippet_path = Path(_require("PROXY_TORRC_SNIPPET_PATH")).expanduser()
    snippet_path.parent.mkdir(parents=True, exist_ok=True)
    snippet_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not torrc_path.exists():
        torrc_path.write_text(snippet_path.read_text(encoding="utf-8"), encoding="utf-8")
    return snippet_path


def _resolve_tor_unit() -> str:
    """Return tor@default (or pulled instance), never bare tor master (fixes.txt §17)."""
    systemctl = _systemctl_bin()
    prior_unit = _optional("TOR_SYSTEMD_UNIT")
    unit = _buildsecrets._pull_tor_systemd_unit(
        systemctl, prior={"TOR_SYSTEMD_UNIT": prior_unit}
    )
    if unit != prior_unit:
        _merge_proxy_secrets({"TOR_SYSTEMD_UNIT": unit})
    return unit


def _probe_tcp(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "connected"
    except OSError as exc:
        return False, str(exc)


def verify_tor_call() -> dict[str, Any]:
    """
    Call Tor test: probe SOCKS using pulled TOR_SOCKS_HOST/ports (fixes.txt §17).
    Only attempts systemctl start (non-interactive) when SOCKS is down.
    """
    import time

    if not get_proxy_secret("TOR_SOCKS_HOST"):
        _ensure_operational_secrets()

    pull = pull_information()
    prior = load_proxy_secrets(reload=False)
    socks_host, socks_port_s = _buildsecrets._pull_tor_socks_endpoint(pull, prior=prior)
    _merge_proxy_secrets(
        {
            "TOR_SOCKS_HOST": socks_host,
            "TOR_SOCKS_PORT": socks_port_s,
            "TOR_SYSTEMD_UNIT": _resolve_tor_unit(),
        }
    )

    host = _require("TOR_SOCKS_HOST")
    socks_port = int(_require("TOR_SOCKS_PORT"))
    control_port = int(_require("TOR_CONTROL_PORT"))
    tor_unit = _resolve_tor_unit()
    timeout = float(_require("PROXY_TOR_VERIFY_TIMEOUT"))

    # Probe localhost first — Debian tor@default binds 127.0.0.1:9050 (§17).
    probe_hosts = []
    for candidate in (host, "127.0.0.1", "localhost"):
        if candidate and candidate not in probe_hosts:
            probe_hosts.append(candidate)

    socks_ok = False
    socks_detail = ""
    for probe_host in probe_hosts:
        socks_ok, socks_detail = _probe_tcp(probe_host, socks_port, timeout)
        if socks_ok:
            host = probe_host
            _merge_proxy_secrets({"TOR_SOCKS_HOST": host})
            break

    control_ok, control_detail = _probe_tcp(host, control_port, timeout)

    daemon_status: dict[str, Any] = {"unit": tor_unit}
    if tor_unit:
        daemon_status["status"] = status_daemon(tor_unit)

    # Only start when SOCKS is down — never prompt for polkit if Tor already works.
    if not socks_ok and tor_unit:
        start_result = start_daemon(tor_unit)
        daemon_status["start"] = start_result
        time.sleep(min(3.0, max(0.5, timeout)))
        daemon_status["status"] = status_daemon(tor_unit)
        for probe_host in probe_hosts:
            socks_ok, socks_detail = _probe_tcp(probe_host, socks_port, timeout)
            if socks_ok:
                host = probe_host
                socks_detail = "connected_after_start"
                _merge_proxy_secrets({"TOR_SOCKS_HOST": host})
                break
        if not socks_ok:
            socks_detail = (
                f"{socks_detail}; start={start_result.get('ok')} "
                f"{start_result.get('stderr') or start_result.get('hint') or ''}"
            ).strip()
        control_ok, control_detail = _probe_tcp(host, control_port, timeout)

    return {
        "ok": socks_ok,
        "socks": {"host": host, "port": socks_port, "ok": socks_ok, "detail": socks_detail},
        "control": {
            "host": host,
            "port": control_port,
            "ok": control_ok,
            "detail": control_detail,
        },
        "daemon": daemon_status,
        "hardware_ip": _optional("HARDWARE_PRIMARY_IP"),
        "hardware_mac": _optional("HARDWARE_PRIMARY_MAC"),
        "timestamp": utc_now(),
    }


def daemon_available(unit: str) -> bool:
    systemctl = _systemctl_bin()
    if not systemctl:
        return False
    result = _run([systemctl, "list-unit-files", f"{unit}.service"])
    return unit in result.stdout


def start_daemon(unit: str) -> dict[str, Any]:
    systemctl = _systemctl_bin()
    if not systemctl:
        return {
            "unit": unit,
            "ok": False,
            "detail": "systemctl binary not found on hardware after pull_information",
        }
    normalized = _buildsecrets._normalize_systemd_unit(unit)
    # Upgrade bare "tor" master to tor@default (fixes.txt §17).
    if normalized == "tor" or (
        systemctl and _buildsecrets._unit_is_tor_instance_master(systemctl, normalized)
    ):
        normalized = _resolve_tor_unit()
    # Never block Bootstrap on interactive polkit password prompts.
    result = _run([systemctl, "--no-ask-password", "start", normalized])
    return {
        "unit": normalized,
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "hint": (
            f"If start failed, run: sudo systemctl start {normalized}"
            if result.returncode != 0
            else ""
        ),
    }


def stop_daemon(unit: str) -> dict[str, Any]:
    systemctl = _systemctl_bin()
    if not systemctl:
        return {
            "unit": unit,
            "ok": False,
            "detail": "systemctl binary not found on hardware after pull_information",
        }
    result = _run([systemctl, "stop", unit])
    return {
        "unit": unit,
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def restart_daemon(unit: str) -> dict[str, Any]:
    systemctl = _systemctl_bin()
    if not systemctl:
        return {
            "unit": unit,
            "ok": False,
            "detail": "systemctl binary not found on hardware after pull_information",
        }
    result = _run([systemctl, "restart", unit])
    return {
        "unit": unit,
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def status_daemon(unit: str) -> dict[str, Any]:
    systemctl = _systemctl_bin()
    if not systemctl:
        return {
            "unit": unit,
            "active": False,
            "detail": "systemctl binary not found on hardware after pull_information",
        }
    result = _run([systemctl, "is-active", unit])
    state = result.stdout.strip() or result.stderr.strip() or "unknown"
    return {"unit": unit, "active": state == "active", "state": state}


def reload_nginx(conf_path: Path | None = None) -> dict[str, Any]:
    path = conf_path or Path(_require("NGINX_CONF_PATH")).expanduser()
    nginx = _nginx_bin()
    if nginx is None:
        return {
            "ok": False,
            "detail": "nginx binary not found on hardware after pull_information",
            "conf": path.as_posix(),
        }
    test = _run([nginx, "-t", "-c", path.as_posix()])
    if test.returncode != 0:
        return {
            "ok": False,
            "detail": "nginx config test failed",
            "stderr": test.stderr.strip(),
            "conf": path.as_posix(),
        }
    reload = _run([nginx, "-s", "reload"])
    if reload.returncode != 0:
        start = start_daemon(_nginx_unit())
        return {
            "ok": bool(start.get("ok")),
            "action": "start",
            "conf": path.as_posix(),
            **start,
        }
    return {"ok": True, "action": "reload", "conf": path.as_posix()}


def set_tor_and_nginx_daemons(*, start: bool = True) -> dict[str, Any]:
    """
    Pull hardware state, then set Tor Hidden Service + nginx daemons for
    MasterServer / NodeUser / Frontend routes using pull-created proxy.secrets.
    """
    pull = pull_information()
    secrets = apply_pull_to_daemon_configuration(pull)
    hs_dirs = ensure_hidden_service_dirs()
    nginx_conf = build_nginx_reverse_proxy_config()
    tor_snippet = build_torrc_hidden_service_snippet()

    result: dict[str, Any] = {
        "generated_at": utc_now(),
        "pull_information": {
            "primary_ip": pull.get("primary_ip"),
            "primary_mac": pull.get("primary_mac"),
            "hostname": pull.get("hostname"),
            "lucid_tops_root": pull.get("lucid_tops_root"),
            "bins": pull.get("bins"),
        },
        "proxy_secrets_file": _proxy_secrets_file().as_posix(),
        "hidden_service_dirs": hs_dirs,
        "nginx_conf": nginx_conf.as_posix(),
        "torrc_snippet": tor_snippet.as_posix(),
        "docker_network": secrets.get("DOCKER_NETWORK_NAME", ""),
        "tor_hs_active": secrets.get("TOR_HS_ACTIVE", ""),
        "tor_hs_forward_ports": secrets.get("TOR_HS_FORWARD_PORTS", ""),
        "selected_containers": sorted(_selected_containers()),
        "none_linking_containers": sorted(_none_linking_containers()),
        "tor_bin": _optional("TOR_BIN"),
        "nginx_bin": _optional("NGINX_BIN"),
        "hardware_ip": secrets.get("HARDWARE_PRIMARY_IP", ""),
        "hardware_mac": secrets.get("HARDWARE_PRIMARY_MAC", ""),
        "uvicorn_compatible": True,
    }

    tor_unit = _optional("TOR_SYSTEMD_UNIT") or _resolve_tor_unit()
    nginx_unit = _optional("NGINX_SYSTEMD_UNIT")

    if start:
        # Probe SOCKS before any systemctl start — avoid polkit prompts when Tor is up.
        socks_host = secrets.get("TOR_SOCKS_HOST") or "127.0.0.1"
        try:
            socks_port = int(secrets.get("TOR_SOCKS_PORT") or "9050")
        except ValueError:
            socks_port = 9050
        socks_live = False
        live_host = socks_host
        for probe_host in (socks_host, "127.0.0.1"):
            ok, _detail = _probe_tcp(probe_host, socks_port, 2.0)
            if ok:
                socks_live = True
                live_host = probe_host
                if probe_host != socks_host:
                    _merge_proxy_secrets({"TOR_SOCKS_HOST": probe_host})
                break

        if socks_live:
            result["tor"] = {
                "ok": True,
                "unit": tor_unit,
                "action": "already_running",
                "detail": (
                    f"SOCKS reachable at {live_host}:{socks_port} — skipped systemctl start"
                ),
            }
        elif tor_unit:
            result["tor"] = start_daemon(tor_unit)
        else:
            result["tor"] = {
                "ok": False,
                "detail": "TOR_SYSTEMD_UNIT missing after pull_information",
            }

        if _nginx_bin():
            result["nginx"] = reload_nginx(nginx_conf)
        else:
            result["nginx"] = {
                "ok": True,
                "action": "deferred",
                "detail": (
                    "nginx binary not on host — conf written for proxy container; "
                    "host Bootstrap does not require host nginx"
                ),
                "conf": nginx_conf.as_posix(),
            }
        result["call_tor_test"] = verify_tor_call()
    else:
        result["tor"] = (
            status_daemon(tor_unit)
            if tor_unit
            else {
                "active": False,
                "detail": "TOR_SYSTEMD_UNIT missing after pull_information",
            }
        )
        result["nginx"] = (
            status_daemon(nginx_unit)
            if nginx_unit
            else {
                "active": False,
                "detail": "NGINX_SYSTEMD_UNIT missing or nginx not on host",
            }
        )

    return result


if __name__ == "__main__":
    report = set_tor_and_nginx_daemons(start=True)
    print(report)
