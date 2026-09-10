"""Operations hardware pull at time of operation.

RULES of CODE CREATION:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

OPERATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OPERATIONS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for path in (PROJECT_ROOT, OPERATIONS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pull_information import (  # noqa: E402
    bind_operation_environ,
    export_shell_env,
    get_last_pull,
    pull_realworld_information,
)


def _normalize_mac(mac: str) -> str:
    return "".join(ch for ch in mac.upper() if ch.isalnum())


def pull_operations_hardware(*, bind_environ: bool = True, overwrite: bool = False) -> dict[str, Any]:
    """
    Pull live hardware facts (IP, MAC, paths, DockerDNS) at script/container run.
    Fails if primary IP or MAC cannot be read from hardware.
    """
    info = pull_realworld_information()
    primary_ip = str(info.get("primary_ip") or "").strip()
    primary_mac = str(info.get("primary_mac") or "").strip()
    if not primary_ip:
        raise RuntimeError(
            "operations pull failed — primary IPv4 not present on hardware at time of operation"
        )
    if not primary_mac:
        raise RuntimeError(
            "operations pull failed — primary MAC not present on hardware at time of operation"
        )

    if bind_environ:
        bind_operation_environ(info, overwrite=overwrite)
        os.environ["HOST_PRIMARY_MAC_NORMALIZED"] = _normalize_mac(primary_mac)

    return info


def get_operations_pull() -> dict[str, Any]:
    last = get_last_pull()
    if last.get("primary_ip") and last.get("primary_mac"):
        return last
    return pull_operations_hardware(bind_environ=True)


def live_primary_mac() -> str:
    info = get_operations_pull()
    mac = str(info.get("primary_mac") or "").strip()
    if not mac:
        raise RuntimeError("HOST_PRIMARY_MAC missing — must be pulled at time of operation")
    return mac


def live_primary_mac_normalized() -> str:
    env_mac = os.environ.get("HOST_PRIMARY_MAC_NORMALIZED", "").strip()
    if env_mac:
        return env_mac
    return _normalize_mac(live_primary_mac())


def live_primary_ip() -> str:
    info = get_operations_pull()
    ip_addr = str(info.get("primary_ip") or os.environ.get("HOST_PRIMARY_IP", "")).strip()
    if not ip_addr:
        raise RuntimeError("HOST_PRIMARY_IP missing — must be pulled at time of operation")
    return ip_addr


def operations_shell_env() -> str:
    info = pull_operations_hardware(bind_environ=True)
    return export_shell_env(info)


def main() -> int:
    info = pull_operations_hardware(bind_environ=True, overwrite=True)
    print(export_shell_env(info), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
