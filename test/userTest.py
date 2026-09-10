""" a script to test the launch system for userID access
connects to the frontend/home_page.js via the *.onion address created from the master server launch script
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_USERONLY = Path(__file__).resolve().parents[1] / "useronly"
if str(_USERONLY) not in sys.path:
    sys.path.insert(0, str(_USERONLY))


def _load_useronly(module_name: str) -> Any:
    path = _USERONLY / f"{module_name}.py"
    registry = f"lucid_test_useronly_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    spec.loader.exec_module(module)
    return module


def test_user_launch_system() -> dict[str, Any]:
    """Verify user launch wiring against secrets (no hardcoded onion/paths)."""
    user_secrets = _load_useronly("user_secrets")
    launch = _load_useronly("LaunchUser")
    install = _load_useronly("install")

    user_secrets.load_user_secrets()
    secrets_status = install.ensure_user_secrets_present()
    url = launch.frontend_onion_url()
    if not url.strip():
        raise RuntimeError("frontend onion URL unresolved")
    return {
        "status": "ok",
        "url": url,
        "secrets": secrets_status,
        "user_status": user_secrets.user_status(),
    }


if __name__ == "__main__":
    result = test_user_launch_system()
    print(result)
