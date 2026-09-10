""" this is the script that outlines the governance the Rdp system.
purpose:
1. to ensure rdp functions are controlled in accordance with the container design.
2. to outline the restrictions that are applied while using the Rdp system.
3. to outline the permissions that are applied while using the Rdp system.
4. to outline the logging that is applied while using the Rdp system.
5. to outline the error handling that is applied while using the Rdp system.
6. to outline the security that is applied while using the Rdp system.
7. to outline the performance that is applied while using the Rdp system.
8. to outline the scalability that is applied while using the Rdp system.
9. to outline the backup and recovery procedures for the Rdp system.
10. to outline the monitoring and alerting procedures for the Rdp system.
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


def governance_policy() -> dict[str, Any]:
    load_rdp_secrets()
    return {
        "permissions": require_rdp_secret("RDP_GOV_PERMISSIONS"),
        "restrictions": get_rdp_secret("RDP_GOV_RESTRICTIONS"),
        "logging_enabled": require_rdp_secret("RDP_GOV_LOGGING_ENABLED"),
        "security_mode": require_rdp_secret("RDP_GOV_SECURITY_MODE"),
        "backup_path": Path(require_rdp_secret("RDP_GOV_BACKUP_PATH")).expanduser().as_posix(),
        "alert_webhook": get_rdp_secret("RDP_GOV_ALERT_WEBHOOK"),
        "checked_at": utc_now(),
    }


def validate_rdp_action(*, action: str, user_id: str, id_token: str) -> dict[str, Any]:
    if not action.strip():
        raise RuntimeError("action missing")
    if not user_id.strip() or not id_token.strip():
        raise RuntimeError("UserID/IDToken missing")
    policy = governance_policy()
    allowed = {item.strip() for item in policy["permissions"].split(",") if item.strip()}
    blocked = {item.strip() for item in str(policy["restrictions"] or "").split(",") if item.strip()}
    if action in blocked:
        raise RuntimeError(f"action blocked by RDP governance: {action}")
    if allowed and action not in allowed:
        raise RuntimeError(f"action not permitted by RDP governance: {action}")
    return {
        "status": "allowed",
        "action": action,
        "user_id": user_id,
        "policy": policy,
        "validated_at": utc_now(),
    }
