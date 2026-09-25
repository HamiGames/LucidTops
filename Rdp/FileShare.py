""" this is the script for the code required for a peer to peer file sharing system.
libraries:
- aiofiles
- torpy
- FastAPI
- DockerDNS
- stem

requirements:
- must all for settings override (settings.js file)
- compatible with nginx reverse proxy
- compatible with DockerDNS

concerns:
- Tor network block all connections to the file sharing system.
- the FastAPI routing system must be compatible with the file sharing system.
- the file sharing system must be compatible with the Rdp container.
"""


from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_rdp_{module_name.replace('-', '_')}"
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


_rdp_secrets = _load_local("rdp_secrets")
require_rdp_secret = _rdp_secrets.require_rdp_secret
require_rdp_secret_int = _rdp_secrets.require_rdp_secret_int
get_rdp_secret = _rdp_secrets.get_rdp_secret
load_rdp_secrets = _rdp_secrets.load_rdp_secrets
rdp_status = _rdp_secrets.rdp_status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_share_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "share_root": Path(require_rdp_secret("RDP_FILE_SHARE_ROOT")).expanduser().as_posix(),
        "max_bytes": require_rdp_secret_int("RDP_FILE_SHARE_MAX_BYTES"),
        "socks_host": require_rdp_secret("TOR_SOCKS_HOST"),
        "socks_port": require_rdp_secret_int("TOR_SOCKS_PORT"),
        "checked_at": utc_now(),
    }


_SHARED: dict[str, list[str]] = {}


def _path_allowed(relative_path: str, allowed: list[str] | None) -> bool:
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if not allowed:
        return True
    for item in allowed:
        prefix = str(item).strip().replace("\\", "/").lstrip("/")
        if not prefix:
            continue
        if cleaned == prefix or cleaned.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def share_file(
    *,
    session_id: str,
    relative_path: str,
    control_on: bool,
    allowed_paths: list[str] | None = None,
) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control transfer is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for file share")
    if not relative_path.strip():
        raise RuntimeError("relative_path missing")
    if not _path_allowed(relative_path, allowed_paths):
        raise RuntimeError("file path is outside host transfer_paths")
    cfg = file_share_config()
    root = Path(cfg["share_root"])
    root.mkdir(parents=True, exist_ok=True)
    target = (root / relative_path).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise RuntimeError("file path escapes RDP_FILE_SHARE_ROOT")
    if not target.exists():
        raise RuntimeError(f"shared file missing: {target.as_posix()}")
    size = target.stat().st_size
    if size > int(cfg["max_bytes"]):
        raise RuntimeError("shared file exceeds RDP_FILE_SHARE_MAX_BYTES")
    sid = str(session_id).strip()
    _SHARED.setdefault(sid, []).append(target.as_posix())
    return {
        "status": "shared",
        "session_id": sid,
        "path": target.as_posix(),
        "size": size,
        "config": cfg,
        "shared_at": utc_now(),
    }


def clear_file_share(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    previous = _SHARED.pop(sid, None)
    return {"status": "cleared", "session_id": sid, "previous": previous, "cleared_at": utc_now()}


def list_shareable(*, session_id: str) -> dict[str, Any]:
    if not str(session_id).strip():
        raise RuntimeError("session_id missing")
    cfg = file_share_config()
    root = Path(cfg["share_root"])
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size})
    return {
        "session_id": str(session_id).strip(),
        "files": files,
        "config": cfg,
        "listed_at": utc_now(),
    }
