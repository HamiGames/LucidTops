"""Frontend handshake and registration validation over the console Tor process.

Both the User branch and the NodeUser branch call this module.
It talks to the Frontend onion. It does not start or call the Proxy container.
The Proxy remains MasterServer support that transports Frontend information.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from internal_routes import load_route_set

_HANDSHAKE_SUFFIX = "/connect-handshake"
_USER_REGISTER_SUFFIX = "/register"
_USER_LOGIN_SUFFIX = "/login"
_NODE_REGISTER_SUFFIX = "/node-registration"
_NODE_LOGIN_SUFFIX = "/login"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def session_state_path() -> Path:
    configured = _env("USERONLY_SESSION_STATE_FILE")
    if configured:
        return Path(configured).expanduser()
    secrets_dir = _env("SECRETS_DIR")
    if not secrets_dir:
        raise RuntimeError(
            "USERONLY_SESSION_STATE_FILE or SECRETS_DIR missing — create at time of operation"
        )
    return Path(secrets_dir) / "useronly_session.state"


def read_session_state() -> dict[str, Any]:
    path = session_state_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_session_state(state: dict[str, Any]) -> Path:
    path = session_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def clear_session_state() -> None:
    path = session_state_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            path.write_text("{}\n", encoding="utf-8")


def _route_value(routes: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = routes.get(key.upper(), "").strip()
        if value:
            return value
    return ""


def frontend_onion(routes: dict[str, str]) -> str:
    direct = _route_value(routes, "FRONTEND_ONION", "ONION_FRONTEND")
    if direct.endswith(".onion"):
        return direct.split("/")[0].lower()
    hostname_dir = _route_value(routes, "TOR_HS_DIR_FRONTEND")
    if not hostname_dir:
        raise RuntimeError(
            "Frontend onion missing from this branch route set — "
            "FRONTEND_ONION or TOR_HS_DIR_FRONTEND must be in the internalized routes"
        )
    hostname = Path(hostname_dir) / "hostname"
    if not hostname.is_file():
        raise RuntimeError(
            f"Frontend hostname file missing at {hostname.as_posix()} — "
            "pull the live onion on the operating console"
        )
    value = hostname.read_text(encoding="utf-8").strip().lower().split("/")[0]
    if not value.endswith(".onion"):
        raise RuntimeError("Frontend hostname file does not contain an onion address")
    return value


def _api_base(routes: dict[str, str]) -> str:
    base = _route_value(routes, "API_BASE_PATH", "PROXY_NGINX_LOCATION_API", "FRONTEND_BASE_PATH")
    if not base:
        raise RuntimeError("API base path missing from this branch route set")
    return "/" + base.strip("/")


def _join_api(routes: dict[str, str], suffix: str) -> str:
    return _api_base(routes).rstrip("/") + "/" + suffix.lstrip("/")


def _configured_api_path(routes: dict[str, str], *keys: str) -> str:
    """Use a configured API path. HTML page paths are not registration or login posts."""
    base = _api_base(routes).rstrip("/")
    for key in keys:
        value = _route_value(routes, key)
        if not value or value.endswith(".html"):
            continue
        if value == base or value.startswith(base + "/"):
            return value
        return _join_api(routes, value)
    return ""


def start_tor_background(command: str) -> dict[str, Any]:
    if not command.strip():
        raise RuntimeError("USER_TOR_START_COMMAND missing — recreate secrets at time of operation")
    proc = subprocess.Popen(command, shell=True)  # noqa: S602 — command from secrets
    return {"status": "started", "command": command, "pid": proc.pid, "started_at": utc_now()}


def _socks_connect(socks_host: str, socks_port: int, dest_host: str, dest_port: int) -> socket.socket:
    sock = socket.create_connection((socks_host, socks_port), timeout=20)
    sock.settimeout(60)
    sock.sendall(b"\x05\x01\x00")
    greeting = _recv_exact(sock, 2)
    if greeting != b"\x05\x00":
        sock.close()
        raise RuntimeError("local Tor SOCKS handshake failed")
    host_b = dest_host.encode("ascii")
    if len(host_b) > 255:
        sock.close()
        raise RuntimeError("onion host name is too long for SOCKS")
    request = b"\x05\x01\x00\x03" + bytes([len(host_b)]) + host_b + dest_port.to_bytes(2, "big")
    sock.sendall(request)
    header = _recv_exact(sock, 4)
    if header[1] != 0:
        sock.close()
        raise RuntimeError(f"local Tor SOCKS connect failed (code {header[1]})")
    atyp = header[3]
    if atyp == 1:
        _recv_exact(sock, 4)
    elif atyp == 3:
        length = _recv_exact(sock, 1)[0]
        _recv_exact(sock, length)
    elif atyp == 4:
        _recv_exact(sock, 16)
    _recv_exact(sock, 2)
    return sock


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        piece = sock.recv(count - len(chunks))
        if not piece:
            raise RuntimeError("Tor connection closed before the Frontend reply finished")
        chunks.extend(piece)
    return bytes(chunks)


def _local_socks(routes: dict[str, str]) -> tuple[str, int]:
    port_text = _route_value(routes, "TOR_SOCKS_PORT")
    candidates: list[tuple[str, int]] = []
    if port_text.isdigit():
        candidates.append(("127.0.0.1", int(port_text)))
    candidates.extend([("127.0.0.1", 9050), ("127.0.0.1", 9150)])
    seen: set[tuple[str, int]] = set()
    last_error = ""
    for host, port in candidates:
        if (host, port) in seen:
            continue
        seen.add((host, port))
        try:
            probe = socket.create_connection((host, port), timeout=2)
        except OSError as exc:
            last_error = str(exc)
            continue
        probe.close()
        return host, port
    raise RuntimeError(
        "local Tor SOCKS port is not accepting connections on this console"
        + (f" ({last_error})" if last_error else "")
    )


def http_over_tor(routes: dict[str, str], path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST JSON to the Frontend onion through the console Tor process."""
    onion = frontend_onion(routes)
    scheme = _route_value(routes, "USER_FRONTEND_SCHEME", "FRONTEND_SCHEME") or "http"
    if scheme not in {"http", "https"}:
        raise RuntimeError("frontend scheme in the route set must be http or https")
    dest_port = 443 if scheme == "https" else 80
    port_text = _route_value(routes, "FRONTEND_PORT")
    if port_text.isdigit():
        dest_port = int(port_text)
    socks_host, socks_port = _local_socks(routes)
    payload = json.dumps(body).encode("utf-8")
    request_path = path if path.startswith("/") else f"/{path}"
    header = (
        f"POST {request_path} HTTP/1.1\r\n"
        f"Host: {onion}\r\n"
        "Content-Type: application/json\r\n"
        "Accept: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    sock = _socks_connect(socks_host, socks_port, onion, dest_port)
    try:
        sock.sendall(header + payload)
        raw = bytearray()
        while True:
            piece = sock.recv(4096)
            if not piece:
                break
            raw.extend(piece)
    finally:
        sock.close()
    text = raw.decode("utf-8", errors="replace")
    head, _, rest = text.partition("\r\n\r\n")
    status_line = head.splitlines()[0] if head else ""
    parts = status_line.split()
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    parsed: Any
    try:
        parsed = json.loads(rest) if rest.strip() else {}
    except json.JSONDecodeError:
        parsed = {"raw": rest[:500]}
    if status and status >= 400:
        detail = parsed.get("detail") if isinstance(parsed, dict) else rest[:200]
        raise RuntimeError(f"Frontend rejected the request ({status}): {detail}")
    if not isinstance(parsed, dict):
        parsed = {"raw": parsed}
    parsed["_http_status"] = status
    return parsed


def write_post_file(driver_dir: Path, name: str, body: dict[str, Any]) -> Path:
    driver_dir.mkdir(parents=True, exist_ok=True)
    path = driver_dir / name
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def handshake(
    routes: dict[str, str],
    *,
    branch: str,
    hardware: dict[str, str],
    token_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Later session step. Rejects unless a TokenID and a SessionID already exist."""
    cleaned_token = str(token_id or "").strip()
    cleaned_session = str(session_id or "").strip()
    if not cleaned_token or not cleaned_session:
        raise RuntimeError("connect-handshake requires a stored TokenID and a SessionID")
    path = _configured_api_path(routes, "HANDSHAKE_PATH", "FRONTEND_HANDSHAKE_PATH")
    if not path:
        path = _join_api(routes, _HANDSHAKE_SUFFIX)
    body = {
        "api_key": cleaned_token,
        "TokenID": cleaned_token,
        "source": "connect-handshake.js",
        "session_id": cleaned_session,
        "connection_type": "ongoing",
        "branch": branch,
        "hostname": hardware.get("hostname", ""),
        "machine_id": hardware.get("machine_id", ""),
        "mac": hardware.get("primary_mac", ""),
    }
    reply = http_over_tor(routes, path, body)
    reply["handshake_path"] = path
    return reply


def registration_path(routes: dict[str, str], *, nodeuser: bool) -> str:
    if nodeuser:
        path = _configured_api_path(routes, "NODEUSER_REGISTER_PATH", "NODE_REGISTER_PATH")
        return path or _join_api(routes, _NODE_REGISTER_SUFFIX)
    path = _configured_api_path(routes, "USER_REGISTER_PATH", "FRONTEND_REGISTER_PATH")
    return path or _join_api(routes, _USER_REGISTER_SUFFIX)


def login_path(routes: dict[str, str], *, nodeuser: bool) -> str:
    if nodeuser:
        path = _configured_api_path(routes, "NODEUSER_LOGIN_PATH", "NODE_LOGIN_PATH")
        return path or _join_api(routes, _NODE_LOGIN_SUFFIX)
    path = _configured_api_path(routes, "USER_LOGIN_PATH", "FRONTEND_LOGIN_PATH")
    return path or _join_api(routes, _USER_LOGIN_SUFFIX)


def submit_validation(
    routes: dict[str, str],
    *,
    path: str,
    body: dict[str, Any],
    driver_dir: Path,
    file_name: str,
) -> dict[str, Any]:
    post_path = write_post_file(driver_dir, file_name, body)
    reply = http_over_tor(routes, path, body)
    return {"post_file": post_path.as_posix(), "reply": reply, "path": path}


def refuse_dockerdns(value: str) -> None:
    """UserOnly reaches other containers only through a Frontend path or onion."""
    text = value.strip()
    if not text or text.startswith("/"):
        return
    host = text
    if "://" in text:
        host = urlsplit(text).hostname or ""
    host = host.lower().split("%")[0]
    if host.endswith(".onion") or host in {"127.0.0.1", "localhost", "::1"}:
        return
    raise RuntimeError(
        "DockerDNS connection refused — this container reaches other containers only through the Frontend"
    )


def open_foreground_window(
    routes: dict[str, str], *, page: str, browser_command: str
) -> dict[str, Any]:
    """Open the Frontend onion in the foreground after Tor is already running."""
    onion = frontend_onion(routes)
    scheme = _route_value(routes, "USER_FRONTEND_SCHEME", "FRONTEND_SCHEME") or "http"
    if scheme not in {"http", "https"}:
        raise RuntimeError("frontend scheme in the route set must be http or https")
    suffix = page if page.startswith("/") else f"/{page}" if page else "/"
    url = f"{scheme}://{onion}{suffix}"
    refuse_dockerdns(url)
    proxy_path = _route_value(routes, "PROXY_FOREGROUND_PATH")
    if proxy_path:
        refuse_dockerdns(proxy_path)
    if "{url}" not in browser_command:
        raise RuntimeError(
            "USER_TOR_BROWSER_COMMAND missing {url} token — recreate secrets at time of operation"
        )
    proc = subprocess.Popen(  # noqa: S602 — command from the operating console secrets
        browser_command.replace("{url}", url),
        shell=True,
    )
    return {"status": "opened", "pid": proc.pid, "proxy_path_present": bool(proxy_path)}


def validate_selected_files(
    routes: dict[str, str],
    handshake_reply: dict[str, Any],
    files: list[str],
) -> dict[str, Any]:
    """Send selected files through the Frontend to the Node, or to the backend when no NodeID is online."""
    if node_online(handshake_reply):
        target = _route_value(routes, "VALIDATION_NODE_TARGET")
        destination = "node"
    else:
        target = _route_value(routes, "VALIDATION_BACKEND_TARGET")
        destination = "backend"
    if not target:
        raise RuntimeError(f"{destination} validation target missing from internal routes")
    refuse_dockerdns(target)
    if not target.startswith("/"):
        raise RuntimeError("validation target must be a Frontend path")
    reply = http_over_tor(
        routes,
        target,
        {"destination": destination, "files": files, "database": "LucidTops_UserDB"},
    )
    return {"destination": destination, "reply": reply}


def verify_userdb(routes: dict[str, str], identity: dict[str, str]) -> None:
    """Compare ID.secrets with LucidTops_UserDB through the Frontend."""
    path = _route_value(routes, "USERDB_VERIFY_PATH")
    if not path.startswith("/"):
        raise RuntimeError("LucidTops_UserDB path missing from internal routes")
    refuse_dockerdns(path)
    reply = http_over_tor(
        routes,
        path,
        {
            "database": "LucidTops_UserDB",
            "USER_ID": identity.get("USER_ID", ""),
            "TOKEN_ID": identity.get("TOKEN_ID", ""),
            "NODE_ID": identity.get("NODE_ID", ""),
            "ID_SECRETS_STAMP": identity.get("ID_SECRETS_STAMP", ""),
        },
    )
    status = str(reply.get("status") or "").strip().lower()
    matched = (
        reply.get("verified") is True
        or reply.get("match") is True
        or status in {"ok", "matched", "verified"}
    )
    remote_user = str(reply.get("UserID") or reply.get("USER_ID") or "").strip()
    if remote_user and remote_user != identity.get("USER_ID", ""):
        matched = False
    if not matched:
        raise RuntimeError("ID.secrets does not match LucidTops_UserDB")


def node_online(handshake_reply: dict[str, Any]) -> bool:
    for key in ("node_online", "NodeOnline", "nodeid_online"):
        value = handshake_reply.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "online"}:
            return True
    nodes = handshake_reply.get("online_node_ids") or handshake_reply.get("OnlineNodeIDs")
    return bool(nodes)


def terminate_pid(pid: int) -> dict[str, Any]:
    if pid <= 0:
        return {"pid": pid, "status": "invalid"}
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "pid": pid,
                "status": "terminated" if result.returncode == 0 else "taskkill_failed",
                "exit": result.returncode,
            }
        os.kill(pid, signal.SIGTERM)
        return {"pid": pid, "status": "terminated"}
    except ProcessLookupError:
        return {"pid": pid, "status": "not_running"}
    except OSError as exc:
        return {"pid": pid, "status": "error", "error": str(exc)}


def disconnect_session() -> dict[str, Any]:
    state = read_session_state()
    results: list[dict[str, Any]] = []
    browser_pid = int(state.get("browser_pid") or 0)
    tor_pid = int(state.get("tor_pid") or 0)
    if browser_pid:
        results.append({"target": "foreground", **terminate_pid(browser_pid)})
    if tor_pid and tor_pid != browser_pid:
        results.append({"target": "tor", **terminate_pid(tor_pid)})
    clear_session_state()
    return {
        "status": "disconnected",
        "terminated": results,
        "previous_branch": state.get("branch", ""),
        "disconnected_at": utc_now(),
    }


def routes_for(nodeuser: bool) -> dict[str, str]:
    return load_route_set("nodeuser" if nodeuser else "user")


def path_from_url(url: str) -> str:
    split = urlsplit(url)
    return split.path or "/"
