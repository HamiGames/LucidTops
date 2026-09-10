""" this is the script that builds the FastAPI routing system for the Rdp container.
purpose:
1. the connection routes for a UserID to access the Rdp container.
2. the connection routes for a UserID to use the Rdp containers content.
3. the connection routes for a UserID to use the Rdp containers functions.

includes: 
- the Proxy container specific routes for the Rdp container.
- the ProxyGate specific routes to the Rdp container.
- the DockerDNS specific routes to the sessions container, from the Rdp container.
- the ProxyGate specific routes for the connection to the Rdp container from the Frontend container.
- the connection routes for the Rdp container to the Sessions container.
- the Rdp container specific routes to the SessionsDB (Backend [MasterServer])
- the Rdp container specific routes to the UserDB (Backend [MasterServer])

required:
- the conversion from FastAPI routing to DockerDNS routing.
- the conversion from DockerDNS routing to FastAPI routing.

concerns:
- the security of the Rdp container.
- the performance of the Rdp container.
- the scalability of the Rdp container.
- the reliability of the Rdp container.
- the compatibility of the Rdp container with the DockerDNS.
- the compatibility of the Rdp container with the FastAPI routing system.
- the compatibility of the Rdp container with the Proxy container.
- the compatibility of the Rdp container with the ProxyGate.

"""


from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

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
get_rdp_secret = _rdp_secrets.get_rdp_secret
load_rdp_secrets = _rdp_secrets.load_rdp_secrets

_RdpMain = _load_local("RdpMain")
_ScreenShare = _load_local("ScreenShare")
_MouseControl = _load_local("MouseControl")
_keyboardControl = _load_local("keyboardControl")
_FileShare = _load_local("FileShare")
_UserControl = _load_local("UserControl")
_AudioControl = _load_local("AudioControl")
_UsbControl = _load_local("UsbControl")
_gov = _load_local("Rdp-gov", "Rdp-gov.py")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RdpAuthPayload(BaseModel):
    UserID: str
    IDToken: str = Field(description="TokenID for the UserID")
    session_id: str | None = None


class MousePayload(RdpAuthPayload):
    x: int
    y: int
    button: str
    action: str


class KeyboardPayload(RdpAuthPayload):
    key: str
    action: str


class FileSharePayload(RdpAuthPayload):
    relative_path: str


class UsbAttachPayload(RdpAuthPayload):
    device_id: str


def _require_api_key(x_lucid_api_key: str | None) -> None:
    expected = require_rdp_secret("RDP_API_KEY")
    if not x_lucid_api_key or x_lucid_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="invalid API key")


def _require_session(payload: RdpAuthPayload) -> str:
    if not payload.session_id or not str(payload.session_id).strip():
        raise HTTPException(status_code=400, detail="session_id missing — SessionID required")
    return str(payload.session_id).strip()


def _gate_session_action(*, action: str, payload: RdpAuthPayload) -> dict[str, Any]:
    sid = _require_session(payload)
    try:
        _gov.validate_rdp_action(
            action=action, user_id=payload.UserID, id_token=payload.IDToken
        )
        validation = _RdpMain.validate_session_id(
            session_id=sid, user_id=payload.UserID, id_token=payload.IDToken
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return validation


def create_rdp_app() -> FastAPI:
    load_rdp_secrets()
    api_prefix = require_rdp_secret("RDP_API_PREFIX")
    app = FastAPI(
        title=require_rdp_secret("RDP_APP_TITLE"),
        description=require_rdp_secret("RDP_APP_DESCRIPTION"),
        version=require_rdp_secret("RDP_APP_VERSION"),
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "checked_at": utc_now(), **_RdpMain.status_rdp_container()}

    @app.get(f"{api_prefix}/view")
    def view_bootstrap() -> dict[str, Any]:
        """JSON bootstrap for Frontend view.js (criterion 10)."""
        return {
            "status": "ok",
            "view": "rdp",
            "api_prefix": api_prefix,
            "base_path": require_rdp_secret("RDP_BASE_PATH"),
            "sessions_dns": require_rdp_secret("RDP_SESSIONS_DNS"),
            "hardware_bound": bool(get_rdp_secret("HARDWARE_PRIMARY_MAC")),
            "checked_at": utc_now(),
        }

    @app.post(f"{api_prefix}/rdp-start")
    def rdp_start(x_lucid_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        return _RdpMain.start_rdp_container()

    @app.post(f"{api_prefix}/rdp-stop")
    def rdp_stop(x_lucid_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        return _RdpMain.stop_rdp_container()

    @app.post(f"{api_prefix}/rdp-status")
    def rdp_status_route(x_lucid_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        return _RdpMain.status_rdp_container()

    @app.post(f"{api_prefix}/sessions/sync")
    def sessions_sync(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="sessions_sync", payload=payload)
        return {
            "status": "synced",
            "validation": validation,
            "sessions_link": _RdpMain.sessions_link_health(),
            "synced_at": utc_now(),
        }

    @app.post(f"{api_prefix}/screen-share/start")
    def screen_share_start(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="screen_share", payload=payload)
        result = _ScreenShare.start_screen_share(
            session_id=str(payload.session_id),
            user_id=payload.UserID,
            id_token=payload.IDToken,
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/screen-share/stop")
    def screen_share_stop(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        sid = _require_session(payload)
        return _ScreenShare.stop_screen_share(session_id=sid)

    @app.post(f"{api_prefix}/mouse/event")
    def mouse_event(
        payload: MousePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="mouse_control", payload=payload)
        result = _MouseControl.apply_mouse_event(
            session_id=str(payload.session_id),
            x=payload.x,
            y=payload.y,
            button=payload.button,
            action=payload.action,
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/keyboard/event")
    def keyboard_event(
        payload: KeyboardPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="keyboard_control", payload=payload)
        result = _keyboardControl.apply_keyboard_event(
            session_id=str(payload.session_id),
            key=payload.key,
            action=payload.action,
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/file-share")
    def file_share(
        payload: FileSharePayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="file_share", payload=payload)
        result = _FileShare.share_file(
            session_id=str(payload.session_id), relative_path=payload.relative_path
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/user-control/enforce")
    def user_control_enforce(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        try:
            _gov.validate_rdp_action(
                action="user_control", user_id=payload.UserID, id_token=payload.IDToken
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return _UserControl.enforce_user_controls(
            user_id=payload.UserID, id_token=payload.IDToken
        )

    @app.post(f"{api_prefix}/audio/start")
    def audio_start(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="audio_control", payload=payload)
        result = _AudioControl.start_audio(
            session_id=str(payload.session_id),
            user_id=payload.UserID,
            id_token=payload.IDToken,
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/audio/stop")
    def audio_stop(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        sid = _require_session(payload)
        return _AudioControl.stop_audio(session_id=sid)

    @app.post(f"{api_prefix}/usb/list")
    def usb_list(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="usb_control", payload=payload)
        result = _UsbControl.list_usb_devices(
            session_id=str(payload.session_id), refresh=True
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/usb/attach")
    def usb_attach(
        payload: UsbAttachPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        validation = _gate_session_action(action="usb_control", payload=payload)
        result = _UsbControl.attach_usb(
            session_id=str(payload.session_id),
            device_id=payload.device_id,
            user_id=payload.UserID,
        )
        result["session_validation"] = validation
        return result

    @app.post(f"{api_prefix}/usb/detach")
    def usb_detach(
        payload: RdpAuthPayload,
        x_lucid_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _require_api_key(x_lucid_api_key)
        sid = _require_session(payload)
        return _UsbControl.detach_usb(session_id=sid)

    return app
