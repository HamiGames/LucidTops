"""Viewer window launch for the UserID that joined a SessionID.

purpose:
- the viewer is the UserID that searched and joined via sessions searchpeer.
- this script returns the window the viewer opens to see the host desktop.
- the host UserID is the peer that requested SessionID creation.

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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def launch_viewer_window(
    *, validation: dict[str, Any], controls: dict[str, Any]
) -> dict[str, Any]:
    """Open the viewer window only for viewerUserID."""
    caller = str(validation.get("user_id") or validation.get("UserID") or "").strip()
    viewer = str(validation.get("viewerUserID") or "").strip()
    host = str(validation.get("hostUserID") or "").strip()
    session_id = str(validation.get("session_id") or validation.get("sessionID") or "").strip()
    if not session_id:
        raise RuntimeError("SessionID missing for viewer window")
    if not viewer or caller != viewer:
        raise RuntimeError(
            "viewer window is only for the UserID that searched and joined the SessionID"
        )
    if not host:
        raise RuntimeError("hostUserID missing — host is the UserID that created the SessionID")
    view_target = require_rdp_secret("RDP_VIEWER_WINDOW_TARGET")
    return {
        "status": "launched",
        "role": "viewer",
        "session_id": session_id,
        "hostUserID": host,
        "viewerUserID": viewer,
        "window": {
            "script": "ViewerWindow.py",
            "target": view_target,
            "stage": "host_desktop",
            "session_id": session_id,
            "controls": controls,
        },
        "launched_at": utc_now(),
    }


def host_desktop_source(*, validation: dict[str, Any]) -> dict[str, Any]:
    """Label the host peer. Does not open the viewer window."""
    caller = str(validation.get("user_id") or validation.get("UserID") or "").strip()
    host = str(validation.get("hostUserID") or "").strip()
    session_id = str(validation.get("session_id") or validation.get("sessionID") or "").strip()
    if not host or caller != host:
        raise RuntimeError("host desktop source is the UserID that created the SessionID")
    return {
        "status": "host_attached",
        "role": "host",
        "session_id": session_id,
        "hostUserID": host,
        "attached_at": utc_now(),
    }
