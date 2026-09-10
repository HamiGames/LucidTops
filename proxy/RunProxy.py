""" this is the Main controller for the Proxy container (RunProxy.py).
includes:
- lifecycle: start, stop, restart, check, monitor, log, debug, update, upgrade,
  install, uninstall, configure, secure, validate, run (foreground uvicorn).
- install/start/run invoke Bootstrap.bootstrap_proxy (hardware pull → secrets → Tor/nginx).
- configure builds secrets + nginx/torrc and ensure_docker_networks from pull/secrets.
- nginx reverse proxy for Tor Hidden Service + Docker Network and MasterServer/NodeUser paths.
- compatible with uvicorn/FastAPI, Tor HS, nginx, and DockerDNS inventory for
  MasterServer, Frontend, Node, Rdp, Sessions, Operations, Blockchain, PaySystems
  (routability governed by ProxyGate selected / none-linking lists in secrets).

operational requirements:
- nginx reverse proxy for Tor Hidden Service / Docker Network and MasterServer (uvicorn/FastAPI).
- all bind hosts, ports, and DNS names come from proxy.secrets created by hardware pull
  at time of operation (when Bootstrap/buildsecrets/SetDeamon run).

restrictions:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- at time of operation = the event when bootstrap/pull scripts run.
- values MUST be PULLED from real-world hardware (IP, MAC, etc.) before secrets drive this controller.
- No sensitive data, all data is stored in the secrets file.

"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import time
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
_ProxyGate = _load_local("ProxyGate")
_SetDeamon = _load_local("SetDeamon")
_Bootstrap = _load_local("Bootstrap")

build_and_write_proxy_secrets = _buildsecrets.build_and_write_proxy_secrets
get_proxy_secret = _buildsecrets.get_proxy_secret
require_proxy_secret = _buildsecrets.require_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
get_none_linking_containers = _ProxyGate.get_none_linking_containers
get_selected_containers = _ProxyGate.get_selected_containers
get_proxy_gate = _ProxyGate.get_proxy_gate
NONE_LINKING_CONTAINERS = _ProxyGate.NONE_LINKING_CONTAINERS
SELECTED_CONTAINERS = _ProxyGate.SELECTED_CONTAINERS
build_nginx_reverse_proxy_config = _SetDeamon.build_nginx_reverse_proxy_config
build_torrc_hidden_service_snippet = _SetDeamon.build_torrc_hidden_service_snippet
reload_nginx = _SetDeamon.reload_nginx
restart_daemon = _SetDeamon.restart_daemon
set_tor_and_nginx_daemons = _SetDeamon.set_tor_and_nginx_daemons
start_daemon = _SetDeamon.start_daemon
status_daemon = _SetDeamon.status_daemon
stop_daemon = _SetDeamon.stop_daemon
bootstrap_proxy = _Bootstrap.bootstrap_proxy
ensure_docker_networks = _Bootstrap.ensure_docker_networks

PROXY_DIR = _PROXY_DIR


def _pid_file() -> Path:
    return Path(require_proxy_secret("PROXY_PID_FILE")).expanduser()


def _log_dir() -> Path:
    return Path(require_proxy_secret("PROXY_LOG_DIR")).expanduser()


def _dockerdns_services() -> dict[str, str]:
    """Map inventory names → secret keys; keys come from operation-time secrets."""
    raw = get_proxy_secret("DOCKERDNS_INVENTORY_KEYS")
    if not raw:
        raise RuntimeError(
            "DOCKERDNS_INVENTORY_KEYS missing — must be set at time of operation "
            "(format: name:SECRET_KEY,name:SECRET_KEY)"
        )
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        name, _, secret_key = item.partition(":")
        name = name.strip().lower()
        secret_key = secret_key.strip()
        if name and secret_key:
            mapping[name] = secret_key
    if not mapping:
        raise RuntimeError("DOCKERDNS_INVENTORY_KEYS produced no entries")
    return mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_runtime_dirs() -> None:
    load_proxy_secrets()
    _pid_file().parent.mkdir(parents=True, exist_ok=True)
    _log_dir().mkdir(parents=True, exist_ok=True)
    Path(require_proxy_secret("PROXY_CONFIGS_DIR")).mkdir(parents=True, exist_ok=True)


def _write_pid(pid: int) -> None:
    _ensure_runtime_dirs()
    _pid_file().write_text(f"{pid}\n", encoding="utf-8")


def _read_pid() -> int | None:
    try:
        raw = _pid_file().read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError, RuntimeError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def configure_proxy() -> dict[str, Any]:
    secrets_report = build_and_write_proxy_secrets()
    nginx_conf = build_nginx_reverse_proxy_config()
    tor_snippet = build_torrc_hidden_service_snippet()
    networks = ensure_docker_networks()
    return {
        "timestamp": utc_now(),
        "secrets": secrets_report,
        "nginx_conf": nginx_conf.as_posix(),
        "torrc_snippet": tor_snippet.as_posix(),
        "docker_networks": networks,
        "selected": sorted(get_selected_containers()),
        "none_linking": sorted(get_none_linking_containers()),
    }


def secure_proxy() -> dict[str, Any]:
    load_proxy_secrets(reload=True)
    conf = Path(require_proxy_secret("NGINX_CONF_PATH")).expanduser()
    secrets_file = Path(require_proxy_secret("PROXY_SECRETS_FILE")).expanduser()
    mode_raw = require_proxy_secret("PROXY_SECURE_FILE_MODE")
    hardened: list[str] = []
    for path in (conf, secrets_file):
        if path.exists():
            try:
                os.chmod(path, int(mode_raw, 0))
                hardened.append(path.as_posix())
            except (OSError, ValueError):
                pass
    return {"hardened_paths": hardened, "timestamp": utc_now()}


def validate_proxy() -> dict[str, Any]:
    load_proxy_secrets(reload=True)
    gate = get_proxy_gate()
    checks = {
        "proxy_secrets_present": bool(get_proxy_secret("PROXY_HMAC_KEY")),
        "nginx_conf_exists": Path(require_proxy_secret("NGINX_CONF_PATH")).exists(),
        "frontend_to_backend_allowed": gate.allows_route(source="frontend", target="backend"),
        "frontend_to_sessions_blocked": not gate.allows_route(
            source="frontend", target="sessions"
        ),
        "direct_operations_blocked": not gate.allows_route(
            source="frontend", target="operations"
        ),
    }
    try:
        import uvicorn  # noqa: F401

        checks["uvicorn_importable"] = True
    except ImportError:
        checks["uvicorn_importable"] = False
    checks["uvicorn_on_path"] = shutil.which("uvicorn") is not None
    checks["ok"] = all(
        [
            checks["proxy_secrets_present"],
            checks["nginx_conf_exists"],
            checks["frontend_to_backend_allowed"],
            checks["frontend_to_sessions_blocked"],
            checks["direct_operations_blocked"],
            checks["uvicorn_importable"],
        ]
    )
    return checks


def dockerdns_inventory() -> dict[str, Any]:
    load_proxy_secrets()
    selected = get_selected_containers()
    none_linking = get_none_linking_containers()
    inventory: dict[str, Any] = {}
    for name, env_key in _dockerdns_services().items():
        host = get_proxy_secret(env_key)
        if not host:
            continue
        inventory[name] = {
            "dns": host,
            "selected": name in selected or name == "masterserver",
            "none_linking": name in none_linking,
            "routable_via_gate": name in selected or name == "masterserver",
        }
    return inventory


def install_proxy() -> dict[str, Any]:
    bootstrapped = bootstrap_proxy(start_daemons=False)
    secured = secure_proxy()
    daemons = set_tor_and_nginx_daemons(start=False)
    return {"bootstrap": bootstrapped, "secure": secured, "daemons": daemons}


def uninstall_proxy() -> dict[str, Any]:
    stop_result = stop_proxy()
    removed: list[str] = []
    conf = Path(require_proxy_secret("NGINX_CONF_PATH")).expanduser()
    if conf.exists():
        conf.unlink()
        removed.append(conf.as_posix())
    pid_path = _pid_file()
    if pid_path.exists():
        pid_path.unlink()
        removed.append(pid_path.as_posix())
    return {"stopped": stop_result, "removed": removed, "timestamp": utc_now()}


def start_proxy(*, configure_daemons: bool = True) -> dict[str, Any]:
    bootstrap_report = bootstrap_proxy(start_daemons=configure_daemons)
    _ensure_runtime_dirs()
    secure_proxy()
    daemon_report: dict[str, Any] = bootstrap_report.get("daemons") or {}

    bind_host = require_proxy_secret("PROXY_FASTAPI_BIND_HOST")
    bind_port = int(require_proxy_secret("PROXY_PORT"))
    log_name = require_proxy_secret("PROXY_UVICORN_LOG_NAME")
    log_path = _log_dir() / log_name
    start_delay = float(require_proxy_secret("PROXY_START_PROBE_DELAY"))

    existing = _read_pid()
    if existing and _pid_alive(existing):
        return {
            "ok": True,
            "already_running": True,
            "pid": existing,
            "bind": f"{bind_host}:{bind_port}",
            "daemons": daemon_report,
        }

    module_target = require_proxy_secret("PROXY_UVICORN_APP")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        module_target,
        "--host",
        bind_host,
        "--port",
        str(bind_port),
        "--app-dir",
        PROXY_DIR.as_posix(),
    ]
    log_handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        cwd=PROXY_DIR.as_posix(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(process.pid)
    time.sleep(start_delay)
    alive = _pid_alive(process.pid)
    return {
        "ok": alive,
        "pid": process.pid,
        "bind": f"{bind_host}:{bind_port}",
        "log": log_path.as_posix(),
        "daemons": daemon_report,
        "nginx": reload_nginx(),
        "timestamp": utc_now(),
    }


def stop_proxy() -> dict[str, Any]:
    pid = _read_pid()
    stopped = False
    detail = "not_running"
    term_signal = int(require_proxy_secret("PROXY_STOP_TERM_SIGNAL"))
    kill_signal = int(require_proxy_secret("PROXY_STOP_KILL_SIGNAL"))
    wait_loops = int(require_proxy_secret("PROXY_STOP_WAIT_LOOPS"))
    wait_delay = float(require_proxy_secret("PROXY_STOP_WAIT_DELAY"))
    nginx_unit = require_proxy_secret("NGINX_SYSTEMD_UNIT")

    if pid and _pid_alive(pid):
        try:
            os.kill(pid, term_signal)
            for _ in range(wait_loops):
                if not _pid_alive(pid):
                    stopped = True
                    break
                time.sleep(wait_delay)
            if _pid_alive(pid):
                os.kill(pid, kill_signal)
                stopped = True
            detail = "terminated"
        except OSError as exc:
            detail = str(exc)
    pid_path = _pid_file()
    if pid_path.exists():
        try:
            pid_path.unlink()
        except OSError:
            pass
    return {
        "ok": stopped or pid is None,
        "pid": pid,
        "detail": detail,
        "nginx": stop_daemon(nginx_unit),
        "timestamp": utc_now(),
    }


def restart_proxy() -> dict[str, Any]:
    stop_report = stop_proxy()
    start_report = start_proxy(configure_daemons=True)
    restart_daemon(require_proxy_secret("NGINX_SYSTEMD_UNIT"))
    return {"stop": stop_report, "start": start_report, "timestamp": utc_now()}


def check_proxy() -> dict[str, Any]:
    pid = _read_pid()
    return {
        "pid": pid,
        "running": bool(pid and _pid_alive(pid)),
        "validation": validate_proxy(),
        "tor": status_daemon(require_proxy_secret("TOR_SYSTEMD_UNIT")),
        "nginx": status_daemon(require_proxy_secret("NGINX_SYSTEMD_UNIT")),
        "dockerdns": dockerdns_inventory(),
        "timestamp": utc_now(),
    }


def monitor_proxy() -> dict[str, Any]:
    status = check_proxy()
    gate = get_proxy_gate().status()
    return {"check": status, "gate": gate, "timestamp": utc_now()}


def log_proxy(*, lines: int | None = None) -> dict[str, Any]:
    if lines is None:
        lines = int(require_proxy_secret("PROXY_LOG_LINES"))
    log_path = _log_dir() / require_proxy_secret("PROXY_UVICORN_LOG_NAME")
    if not log_path.exists():
        return {"log": log_path.as_posix(), "lines": [], "timestamp": utc_now()}
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "log": log_path.as_posix(),
        "lines": content[-max(1, lines) :],
        "timestamp": utc_now(),
    }


def debug_proxy() -> dict[str, Any]:
    load_proxy_secrets()
    return {
        "check": check_proxy(),
        "validate": validate_proxy(),
        "inventory": dockerdns_inventory(),
        "env": {
            "LUCID_TOPS_ROOT": require_proxy_secret("LUCID_TOPS_ROOT"),
            "PROXY_DIR": PROXY_DIR.as_posix(),
            "PYTHON": sys.executable,
        },
        "timestamp": utc_now(),
    }


def update_proxy() -> dict[str, Any]:
    """Refresh secrets + nginx/tor configs from current operational environment."""
    report = configure_proxy()
    nginx = reload_nginx()
    return {"configure": report, "nginx": nginx, "timestamp": utc_now()}


def upgrade_proxy() -> dict[str, Any]:
    updated = update_proxy()
    restarted = restart_proxy()
    return {"update": updated, "restart": restarted, "timestamp": utc_now()}


def run_foreground() -> None:
    """Run uvicorn FastAPI proxy in the foreground (container CMD entry)."""
    bootstrap_proxy(start_daemons=True)
    secure_proxy()
    bind_host = require_proxy_secret("PROXY_FASTAPI_BIND_HOST")
    bind_port = int(require_proxy_secret("PROXY_PORT"))
    import uvicorn

    uvicorn.run(
        require_proxy_secret("PROXY_UVICORN_APP"),
        host=bind_host,
        port=bind_port,
        app_dir=PROXY_DIR.as_posix(),
        reload=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LucidTops Proxy container controller")
    parser.add_argument(
        "action",
        choices=[
            "start",
            "stop",
            "restart",
            "check",
            "monitor",
            "log",
            "debug",
            "update",
            "upgrade",
            "install",
            "uninstall",
            "configure",
            "secure",
            "validate",
            "run",
        ],
        help="Proxy lifecycle action",
    )
    parser.add_argument("--log-lines", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    action = args.action

    handlers = {
        "start": lambda: start_proxy(configure_daemons=True),
        "stop": stop_proxy,
        "restart": restart_proxy,
        "check": check_proxy,
        "monitor": monitor_proxy,
        "log": lambda: log_proxy(lines=args.log_lines),
        "debug": debug_proxy,
        "update": update_proxy,
        "upgrade": upgrade_proxy,
        "install": install_proxy,
        "uninstall": uninstall_proxy,
        "configure": configure_proxy,
        "secure": secure_proxy,
        "validate": validate_proxy,
    }

    if action == "run":
        run_foreground()
        return 0

    result = handlers[action]()
    print(result)
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    if isinstance(result, dict) and "validation" in result:
        validation = result.get("validation") or {}
        if validation.get("ok") is False:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
