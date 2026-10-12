"""Associated pull_information script for the sessions container.

Delegates to sessions_pull_information. Secrets are written on the Pi
console under /mnt/myssd/LucidTops/Server/Secrets.

utc_now is loaded from backend/pull_information.py by file path so this
module can stay named pull_information.py without hiding that helper.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _backend_pull():
    existing = sys.modules.get("backend_pull_information")
    if existing is not None and hasattr(existing, "utc_now"):
        return existing
    backend_path = Path(__file__).resolve().parent.parent / "backend" / "pull_information.py"
    spec = importlib.util.spec_from_file_location("backend_pull_information", backend_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"backend pull_information.py missing at {backend_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["backend_pull_information"] = module
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    return _backend_pull().utc_now()


def pull_information():
    from sessions_pull_information import pull_sessions_hardware

    return pull_sessions_hardware(bind_environ=True, overwrite=True)


def main() -> int:
    from sessions_pull_information import main as sessions_main

    return sessions_main()


if __name__ == "__main__":
    raise SystemExit(main())
