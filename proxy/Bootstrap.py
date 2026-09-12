""" this is the bootstrap script for the Proxy module.
includes:
- creation of all required content for the Proxy containers operational needs.
- is a one-time operation at container create / first start (proxy.dockerfile or RunProxy).
- pull_information(): pulls real-world hardware/runtime state (IP, MAC, hostname, Docker,
  listeners, binaries, LucidTops root) at time of operation (when this script runs).
- starts / verifies Tor on the Creator's local hardware via SetDeamon
  (systemd unit tor@default per fixes.txt §17 — not bare tor.service master).
- adds / updates Torrc for Hidden Services from pull-created proxy.secrets.
- creates proxy.secrets via buildsecrets from the hardware pull (not pre-filled placeholders).
- writes generated *.onion addresses into proxy.secrets when Tor HS hostname files appear.
- adds uvicorn bind, DockerDNS, and Proxy self address from pull into proxy.secrets.
- creates secrets directories under the pulled LucidTops root (e.g. Server/Secrets on SSD).
- syncs proxy.secrets into Master.secrets at the Master secrets path created from the pull.
- runs Call Tor test (SOCKS/control) while bootstrapping the Proxy container.
- validates nginx, uvicorn, and DockerDNS configuration from pull-created secrets.
- builds required Docker networks named from pull/secrets.
- makes sure the Proxy container will function correctly when started.

RULES (clarification):
- no hardcoded values, all values are created at time of operation.
- no placeholder values, all values are created at time of operation.
- at time of operation = the event when this script is run.
- values MUST be PULLED and configured from real-world hardware content
  (IP, MAC, etc.) via pull_information / buildsecrets.pull_realworld_information.
- no sensitive data outside secrets files (proxy.secrets / Master.secrets).
- NO pull from GIT repository for operational values.

"""

from __future__ import annotations

import importlib.util
import shutil
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
_SetDeamon = _load_local("SetDeamon")

build_and_write_proxy_secrets = _buildsecrets.build_and_write_proxy_secrets
collect_onion_addresses = _buildsecrets.collect_onion_addresses
get_proxy_secret = _buildsecrets.get_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
parse_secrets_file = _buildsecrets.parse_secrets_file
pull_realworld_information = _buildsecrets.pull_realworld_information
require_proxy_secret = _buildsecrets.require_proxy_secret
resolve_master_secrets_path = _buildsecrets.resolve_master_secrets_path
sync_to_master_secrets = _buildsecrets.sync_to_master_secrets
write_secrets_file = _buildsecrets.write_secrets_file

build_nginx_reverse_proxy_config = _SetDeamon.build_nginx_reverse_proxy_config
build_torrc_hidden_service_snippet = _SetDeamon.build_torrc_hidden_service_snippet
ensure_hidden_service_dirs = _SetDeamon.ensure_hidden_service_dirs
reload_nginx = _SetDeamon.reload_nginx
set_tor_and_nginx_daemons = _SetDeamon.set_tor_and_nginx_daemons
verify_tor_call = _SetDeamon.verify_tor_call


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
    Required pull-information entry: real-world hardware/runtime content
    (IP, MAC, Docker endpoints, listeners, binaries, LucidTops root).
    """
    return pull_realworld_information()


def ensure_secrets_directories(pull: dict[str, Any] | None = None) -> dict[str, str]:
    """Create secrets directories from pulled LucidTops root on hardware."""
    info = pull if pull is not None else pull_information()
    _buildsecrets._bind_paths_from_pull(info)
    secrets_dir = Path(_buildsecrets.SECRETS_DIR)
    configs_dir = Path(_buildsecrets.CONFIGS_DIR)
    onion_dir = Path(_buildsecrets.ONION_EXPORT_DIR)
    proxy_secrets = Path(_buildsecrets.PROXY_SECRETS_FILE)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    onion_dir.mkdir(parents=True, exist_ok=True)
    proxy_secrets.parent.mkdir(parents=True, exist_ok=True)
    created = {
        "SECRETS_DIR": secrets_dir.as_posix(),
        "PROXY_CONFIGS_DIR": configs_dir.as_posix(),
        "CONTAINER_ONION_DIR": onion_dir.as_posix(),
        "PROXY_SECRETS_FILE": proxy_secrets.as_posix(),
        "HARDWARE_PRIMARY_IP": str(info.get("primary_ip") or ""),
        "HARDWARE_PRIMARY_MAC": str(info.get("primary_mac") or ""),
        "LUCID_TOPS_ROOT": str(info.get("lucid_tops_root") or ""),
    }
    master_path = resolve_master_secrets_path()
    master_path.parent.mkdir(parents=True, exist_ok=True)
    created["MASTER_SECRETS_DIR"] = master_path.parent.as_posix()
    created["MASTER_SECRETS_FILE"] = master_path.as_posix()
    return created


def ensure_docker_networks() -> dict[str, Any]:
    """Create Docker networks using names/driver pulled into proxy.secrets."""
    load_proxy_secrets()
    docker_bin = get_proxy_secret("DOCKER_BIN") or shutil.which(
        get_proxy_secret("DOCKER_BIN_NAME") or "docker"
    )
    if not docker_bin:
        raise RuntimeError(
            "docker binary not found on hardware — pull_information requires docker for DockerDNS"
        )

    names: list[str] = []
    primary = require_proxy_secret("DOCKER_NETWORK_NAME")
    names.append(primary)
    extra = get_proxy_secret("DOCKER_NETWORK_NAMES")
    if extra:
        for item in extra.split(","):
            item = item.strip()
            if item and item not in names:
                names.append(item)

    driver = get_proxy_secret("DOCKER_NETWORK_DRIVER")
    created: list[dict[str, Any]] = []
    for name in names:
        inspect = _run([docker_bin, "network", "inspect", name])
        if inspect.returncode == 0:
            created.append({"name": name, "action": "exists", "ok": True})
            continue
        cmd = [docker_bin, "network", "create"]
        if driver:
            cmd.extend(["--driver", driver])
        cmd.append(name)
        result = _run(cmd)
        created.append(
            {
                "name": name,
                "action": "create",
                "ok": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Docker network create failed for {name}: {result.stderr.strip()}"
            )

    return {
        "docker_bin": docker_bin,
        "networks": created,
        "timestamp": utc_now(),
    }


def _wait_frontend_onion() -> str:
    """Poll Tor HS hostname using wait values created from hardware pull."""
    load_proxy_secrets()
    attempts = int(require_proxy_secret("PROXY_ONION_WAIT_ATTEMPTS"))
    delay = float(require_proxy_secret("PROXY_ONION_WAIT_DELAY"))
    onion = ""
    for _ in range(max(1, attempts)):
        onions = collect_onion_addresses()
        onion = onions.get("frontend", "") or get_proxy_secret("FRONTEND_ONION")
        if onion:
            break
        time.sleep(delay)
    return onion


def verify_nginx_configuration() -> dict[str, Any]:
    """Validate or generate nginx conf. Host nginx binary is optional (proxy container)."""
    conf = build_nginx_reverse_proxy_config()
    nginx = get_proxy_secret("NGINX_BIN") or shutil.which(
        get_proxy_secret("NGINX_BIN_NAME") or "nginx"
    )
    if not nginx:
        # Host Bootstrap only needs the conf file written; nginx runs in the proxy image.
        return {
            "ok": True,
            "conf": conf.as_posix(),
            "nginx_bin": "",
            "deferred": True,
            "detail": (
                "nginx binary not on host — configuration written for container use"
            ),
            "timestamp": utc_now(),
        }
    test = _run([nginx, "-t", "-c", conf.as_posix()])
    ok = test.returncode == 0
    if not ok:
        raise RuntimeError(
            f"nginx configuration invalid: {test.stderr.strip() or test.stdout.strip()}"
        )
    return {
        "ok": ok,
        "conf": conf.as_posix(),
        "nginx_bin": nginx,
        "stderr": test.stderr.strip(),
        "timestamp": utc_now(),
    }


def verify_uvicorn_configuration() -> dict[str, Any]:
    app_target = require_proxy_secret("PROXY_UVICORN_APP")
    bind_host = require_proxy_secret("PROXY_FASTAPI_BIND_HOST")
    bind_port = require_proxy_secret("PROXY_PORT")
    port_num = int(bind_port)

    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("uvicorn not importable — install before bootstrap") from exc

    module_name, _, attr = app_target.partition(":")
    if not module_name or not attr:
        raise RuntimeError("PROXY_UVICORN_APP must be module:attr from operation pull")
    module_path = _PROXY_DIR / f"{module_name}.py"
    if not module_path.exists():
        raise RuntimeError(f"uvicorn app module missing: {module_path.as_posix()}")

    return {
        "ok": True,
        "uvicorn_app": app_target,
        "bind_host": bind_host,
        "bind_port": port_num,
        "module_path": module_path.as_posix(),
        "timestamp": utc_now(),
    }


def verify_dockerdns_configuration() -> dict[str, Any]:
    inventory_raw = require_proxy_secret("DOCKERDNS_INVENTORY_KEYS")
    mapping: dict[str, str] = {}
    for item in inventory_raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        name, _, secret_key = item.partition(":")
        name = name.strip().lower()
        secret_key = secret_key.strip()
        if name and secret_key:
            host = require_proxy_secret(secret_key)
            mapping[name] = host
    if not mapping:
        raise RuntimeError(
            "DOCKERDNS_INVENTORY_KEYS produced no resolvable DockerDNS entries from pull"
        )
    return {
        "ok": True,
        "inventory": mapping,
        "proxy_self_dns": require_proxy_secret("PROXY_SELF_DNS"),
        "proxy_backend_dns": require_proxy_secret("PROXY_BACKEND_DNS"),
        "hardware_ip": get_proxy_secret("HARDWARE_PRIMARY_IP"),
        "hardware_mac": get_proxy_secret("HARDWARE_PRIMARY_MAC"),
        "timestamp": utc_now(),
    }


def verify_socks5_secrets() -> dict[str, Any]:
    host = require_proxy_secret("TOR_SOCKS_HOST")
    port = int(require_proxy_secret("TOR_SOCKS_PORT"))
    return {
        "ok": True,
        "TOR_SOCKS_HOST": host,
        "TOR_SOCKS_PORT": port,
        "hardware_ip": get_proxy_secret("HARDWARE_PRIMARY_IP"),
        "has_username": bool(get_proxy_secret("TOR_SOCKS_USERNAME")),
        "has_password": bool(get_proxy_secret("TOR_SOCKS_PASSWORD")),
        "timestamp": utc_now(),
    }


def bootstrap_proxy(*, start_daemons: bool = True) -> dict[str, Any]:
    """
    One-time Proxy bootstrap at time of operation:
    1) pull_information (IP/MAC/Docker/listeners/paths)
    2) create proxy.secrets from pull
    3) Torrc / nginx / DockerDNS / networks / Master.secrets
    """
    report: dict[str, Any] = {"started_at": utc_now(), "ok": False}

    pull = pull_information()
    report["pull_information"] = {
        "primary_ip": pull.get("primary_ip"),
        "primary_mac": pull.get("primary_mac"),
        "hostname": pull.get("hostname"),
        "lucid_tops_root": pull.get("lucid_tops_root"),
        "docker_containers": sorted((pull.get("docker_containers") or {}).keys()),
        "docker_networks": [
            n.get("name") for n in (pull.get("docker_networks") or [])
        ],
        "bins": pull.get("bins"),
    }

    dirs = ensure_secrets_directories(pull)
    report["directories"] = dirs

    secrets_report = build_and_write_proxy_secrets()
    report["secrets"] = secrets_report

    socks = verify_socks5_secrets()
    report["socks5"] = socks

    hs_dirs = ensure_hidden_service_dirs()
    report["hidden_service_dirs"] = hs_dirs

    torrc = build_torrc_hidden_service_snippet()
    report["torrc_snippet"] = torrc.as_posix()
    torrc_path = Path(require_proxy_secret("TORRC_PATH")).expanduser()
    report["torrc_path"] = torrc_path.as_posix()
    report["torrc_exists"] = torrc_path.exists()

    if start_daemons:
        daemon_report = set_tor_and_nginx_daemons(start=True)
        report["daemons"] = daemon_report

    tor_test = verify_tor_call()
    report["call_tor_test"] = tor_test
    if not tor_test.get("ok"):
        raise RuntimeError(
            f"Call Tor test failed: {tor_test.get('socks', {}).get('detail', 'unknown')}. "
            "Ensure tor@default is running: sudo systemctl start tor@default "
            "&& ss -lntp | grep 9050"
        )

    nginx_check = verify_nginx_configuration()
    report["nginx"] = nginx_check
    if start_daemons and nginx_check.get("nginx_bin"):
        report["nginx_reload"] = reload_nginx(Path(nginx_check["conf"]))
    elif start_daemons:
        report["nginx_reload"] = {
            "ok": True,
            "action": "skipped",
            "detail": "host nginx binary absent — conf ready for proxy container",
            "conf": nginx_check.get("conf"),
        }

    uvicorn_check = verify_uvicorn_configuration()
    report["uvicorn"] = uvicorn_check

    dockerdns_check = verify_dockerdns_configuration()
    report["dockerdns"] = dockerdns_check

    networks = ensure_docker_networks()
    report["docker_networks"] = networks

    # Re-pull after Docker network create so DockerDNS IPs refresh into secrets
    refresh = build_and_write_proxy_secrets(overwrite_keys=False)
    report["secrets_refresh"] = {
        "proxy_secrets_file": refresh.get("proxy_secrets_file"),
        "pull": refresh.get("pull"),
    }

    frontend_onion = _wait_frontend_onion()
    if frontend_onion:
        updates = parse_secrets_file(
            Path(require_proxy_secret("PROXY_SECRETS_FILE")).expanduser()
        )
        updates["FRONTEND_ONION"] = frontend_onion
        write_secrets_file(
            Path(require_proxy_secret("PROXY_SECRETS_FILE")).expanduser(), updates
        )
        load_proxy_secrets(reload=False)
        report["frontend_onion"] = frontend_onion
    else:
        report["frontend_onion"] = get_proxy_secret("FRONTEND_ONION")
        report["frontend_onion_pending"] = not bool(report["frontend_onion"])

    master_path = sync_to_master_secrets()
    report["master_secrets_file"] = master_path.as_posix()
    report["master_secrets_exists"] = master_path.exists()

    criteria = {
        "pull_ip": bool(get_proxy_secret("HARDWARE_PRIMARY_IP")),
        "pull_mac": bool(get_proxy_secret("HARDWARE_PRIMARY_MAC")),
        "socks5_secrets": bool(
            get_proxy_secret("TOR_SOCKS_HOST") and get_proxy_secret("TOR_SOCKS_PORT")
        ),
        "torrc": torrc_path.exists(),
        "nginx_conf": Path(nginx_check["conf"]).exists(),
        "uvicorn_app": bool(get_proxy_secret("PROXY_UVICORN_APP")),
        "dockerdns": bool(dockerdns_check.get("inventory")),
        "docker_network": all(item.get("ok") for item in networks.get("networks", [])),
        "call_tor": bool(tor_test.get("ok")),
        "master_secrets": master_path.exists(),
        "proxy_secrets": Path(require_proxy_secret("PROXY_SECRETS_FILE")).exists(),
    }
    report["criteria"] = criteria
    report["ok"] = all(criteria.values())
    report["finished_at"] = utc_now()

    if not report["ok"]:
        failed = [key for key, value in criteria.items() if not value]
        raise RuntimeError(f"Proxy bootstrap criteria failed: {', '.join(failed)}")

    return report


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        result = bootstrap_proxy(start_daemons=True)
    except Exception as exc:
        print({"ok": False, "error": str(exc), "timestamp": utc_now()})
        return 1
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
