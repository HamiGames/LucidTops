""" launch the connection to the frontend/home_page.js via the *.onion address created from the master server launch script
steps:
1. start tor connection on the user's device
2. connect to the frontend/home_page.js via the *.onion address or api route
3. authenticate the user via the api route
4. authorize the user via the api route
5. transfer the user to the frontend/home_page.js
6. display the user's dashboard
7. display the user's settings
8. display the user's profile
9. display the user's messages
10. display the user's notifications
11. display the user's alerts
12. display the user's errors
13. display the user's logs
14. display the user's alerts
"""


from __future__ import annotations

import importlib.util
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
user_status = _user_secrets.user_status

_install = _load_local("install")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def frontend_onion_url() -> str:
    load_user_secrets()
    onion = require_user_secret("FRONTEND_ONION")
    home = require_user_secret("FRONTEND_HOME_PAGE_PATH")
    scheme = require_user_secret("USER_FRONTEND_SCHEME")
    return f"{scheme}://{onion}/{home.lstrip('/')}"


def start_tor_background() -> dict[str, Any]:
    cmd = require_user_secret("USER_TOR_START_COMMAND")
    proc = subprocess.Popen(cmd, shell=True)  # noqa: S602 — command from secrets
    return {"status": "started", "command": cmd, "pid": proc.pid, "started_at": utc_now()}


def launch_user_session(*, user_id: str | None = None, id_token: str | None = None) -> dict[str, Any]:
    _install.ensure_user_secrets_present()
    tor = start_tor_background()
    url = frontend_onion_url()
    browser_cmd_template = require_user_secret("USER_TOR_BROWSER_COMMAND")
    browser_cmd = browser_cmd_template.replace("{url}", url)
    proc = subprocess.Popen(browser_cmd, shell=True)  # noqa: S602 — command from secrets
    return {
        "status": "launched",
        "url": url,
        "tor": tor,
        "browser_pid": proc.pid,
        "user_id": user_id,
        "authenticated": bool(user_id and id_token),
        **user_status(),
        "launched_at": utc_now(),
    }
