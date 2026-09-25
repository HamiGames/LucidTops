"""AudioControl — peer-to-peer audio communication for the Rdp container.

purpose (documentation/fixes.txt §4 criterion 5):
- allows audio communication inside an active SessionID.

requirements:
- settings override via settings.js path from rdp.secrets
- compatible with nginx reverse proxy
- compatible with DockerDNS / FastAPI (RdpRoutes.py)
- SessionID mandatory

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
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

_RUNTIME: dict[str, Any] = {"sessions": {}, "chunks": {}}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audio_control_config() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "settings_js": Path(require_rdp_secret("RDP_SETTINGS_JS_PATH")).expanduser().as_posix(),
        "sample_rate": require_rdp_secret_int("RDP_AUDIO_SAMPLE_RATE"),
        "channels": require_rdp_secret_int("RDP_AUDIO_CHANNELS"),
        "socks_host": require_rdp_secret("TOR_SOCKS_HOST"),
        "socks_port": require_rdp_secret_int("TOR_SOCKS_PORT"),
        "checked_at": utc_now(),
    }


def start_audio(
    *, session_id: str, user_id: str, id_token: str, control_on: bool
) -> dict[str, Any]:
    if not control_on:
        raise RuntimeError("host control audio is off")
    if not str(session_id).strip():
        raise RuntimeError("session_id missing — SessionID required for audio")
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/IDToken missing for audio")
    cfg = audio_control_config()
    sid = str(session_id).strip()
    _RUNTIME["sessions"][sid] = {
        "user_id": user_id,
        "status": "streaming",
        "started_at": utc_now(),
    }
    _RUNTIME["chunks"].setdefault(sid, [])
    return {
        "status": "started",
        "session_id": sid,
        "user_id": user_id,
        "config": cfg,
        "started_at": _RUNTIME["sessions"][sid]["started_at"],
    }


def push_audio(*, session_id: str, chunk_b64: str, user_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    if sid not in _RUNTIME["sessions"]:
        raise RuntimeError("audio path is not open for this SessionID")
    if not chunk_b64.strip():
        raise RuntimeError("audio chunk missing")
    bucket: list[dict[str, str]] = _RUNTIME["chunks"].setdefault(sid, [])
    bucket.append({"user_id": user_id, "chunk_b64": chunk_b64, "at": utc_now()})
    return {"status": "queued", "session_id": sid, "queued": len(bucket), "queued_at": utc_now()}


def pull_audio(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    if sid not in _RUNTIME["sessions"]:
        raise RuntimeError("audio path is not open for this SessionID")
    bucket: list[dict[str, str]] = _RUNTIME["chunks"].get(sid) or []
    chunk = bucket.pop(0) if bucket else None
    return {
        "status": "pulled" if chunk else "empty",
        "session_id": sid,
        "chunk": chunk,
        "remaining": len(bucket),
        "pulled_at": utc_now(),
    }


def stop_audio(*, session_id: str) -> dict[str, Any]:
    sid = str(session_id).strip()
    if not sid:
        raise RuntimeError("session_id missing")
    previous = _RUNTIME["sessions"].pop(sid, None)
    _RUNTIME["chunks"].pop(sid, None)
    return {
        "status": "stopped",
        "session_id": sid,
        "previous": previous,
        "stopped_at": utc_now(),
    }


def audio_control_status(*, session_id: str | None = None) -> dict[str, Any]:
    if session_id:
        sid = str(session_id).strip()
        return {
            "session_id": sid,
            "active": sid in _RUNTIME["sessions"],
            "session": _RUNTIME["sessions"].get(sid),
            "config": audio_control_config(),
            "checked_at": utc_now(),
        }
    return {
        "active_sessions": list(_RUNTIME["sessions"].keys()),
        "config": audio_control_config(),
        "checked_at": utc_now(),
    }
