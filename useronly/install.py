""" import all required programs and files for the user system to be able to use the LucidTops system
install protocol:
- check for all required programs and files
- install all required programs and files
- verify all required programs and files are installed
- verify all required programs and files are working
- launch required programs in background
- open fontend/home_page.js in a new tor browser window
- open fontend/register.js in a new tor browser window
- use content from fontend/register.js to register to send request to the master server to create a new userID
- use content from fontend/login.js to login to the master server to access the user's dashboard


"""


from __future__ import annotations

import importlib.util
import shutil
import subprocess
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
    registry = f"lucid_useronly_{module_name}"
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


_user_secrets = _load_local("user_secrets")
require_user_secret = _user_secrets.require_user_secret
get_user_secret = _user_secrets.get_user_secret
load_user_secrets = _user_secrets.load_user_secrets
registration_secrets_path = _user_secrets.registration_secrets_path
id_secrets_path = _user_secrets.id_secrets_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def required_programs() -> list[str]:
    raw = require_user_secret("USER_REQUIRED_PROGRAMS")
    programs = [item.strip() for item in raw.split(",") if item.strip()]
    if not programs:
        raise RuntimeError("USER_REQUIRED_PROGRAMS empty — set at time of operation")
    return programs


def required_files() -> list[Path]:
    raw = require_user_secret("USER_REQUIRED_FILES")
    files = [Path(item.strip()).expanduser() for item in raw.split(",") if item.strip()]
    if not files:
        raise RuntimeError("USER_REQUIRED_FILES empty — set at time of operation")
    return files


def verify_required_programs() -> dict[str, Any]:
    missing = [name for name in required_programs() if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"required programs missing: {', '.join(missing)}")
    return {"programs": required_programs(), "verified_at": utc_now()}


def verify_required_files() -> dict[str, Any]:
    missing = [path.as_posix() for path in required_files() if not path.exists()]
    if missing:
        raise RuntimeError(f"required files missing: {', '.join(missing)}")
    return {"files": [p.as_posix() for p in required_files()], "verified_at": utc_now()}


def ensure_user_secrets_present() -> dict[str, Any]:
    load_user_secrets()
    reg = registration_secrets_path()
    ident = id_secrets_path()
    if not reg.exists():
        raise RuntimeError(f"registration.secrets missing at {reg.as_posix()}")
    if not ident.exists():
        raise RuntimeError(f"ID.secrets missing at {ident.as_posix()}")
    return {
        "registration_secrets": reg.as_posix(),
        "id_secrets": ident.as_posix(),
        "checked_at": utc_now(),
    }


def install_user_environment() -> dict[str, Any]:
    programs = verify_required_programs()
    files = verify_required_files()
    secrets = ensure_user_secrets_present()
    launch_cmd = require_user_secret("USER_BACKGROUND_LAUNCH_COMMAND")
    subprocess.Popen(launch_cmd, shell=True)  # noqa: S602 — command from secrets at operation time
    return {
        "status": "installed",
        "programs": programs,
        "files": files,
        "secrets": secrets,
        "background_launch": launch_cmd,
        "home_page": require_user_secret("FRONTEND_HOME_PAGE_PATH"),
        "register_page": require_user_secret("FRONTEND_REGISTER_PATH"),
        "installed_at": utc_now(),
    }
