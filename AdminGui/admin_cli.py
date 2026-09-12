"""Linux command line for AdminID when co-located with the MasterServer console.

allows for the AdminID to run a linux command line if on the same console as the
self-hosted MasterServer container.
Shell binary paths are discovered at time of operation (ADMIN_SHELL_BASH / ADMIN_SHELL_SH).
"""

from __future__ import annotations

import importlib.util
import platform
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_admingui_{module_name}"
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


_admin_secrets = _load_local("admin_secrets")
get_admin_secret = _admin_secrets.get_admin_secret
ensure_admin_secrets_from_pull = _admin_secrets.ensure_admin_secrets_from_pull


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_master_server_colocated() -> bool:
    ensure_admin_secrets_from_pull()
    flag = get_admin_secret("MASTER_SERVER_COLOCATED")
    return flag in {"1", "true", "True", "yes"}


def resolve_shell_bin() -> str:
    ensure_admin_secrets_from_pull()
    bash = get_admin_secret("ADMIN_SHELL_BASH")
    sh = get_admin_secret("ADMIN_SHELL_SH")
    for candidate in (bash, sh):
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "ADMIN_SHELL_BASH/ADMIN_SHELL_SH missing — pull shell paths at time of operation"
    )


def cli_availability() -> dict[str, Any]:
    ensure_admin_secrets_from_pull()
    system = (get_admin_secret("ADMIN_SYSTEM") or platform.system()).lower()
    colocated = is_master_server_colocated()
    available = colocated and system == "linux"
    shell = ""
    if available:
        try:
            shell = resolve_shell_bin()
        except RuntimeError as exc:
            return {
                "available": False,
                "colocated": colocated,
                "system": system,
                "reason": str(exc),
                "checked_at": utc_now(),
            }
    reason = ""
    if not colocated:
        reason = "not co-located with MasterServer console"
    elif system != "linux":
        reason = "linux command line requires linux console"
    return {
        "available": available,
        "colocated": colocated,
        "system": system,
        "shell": shell,
        "reason": reason,
        "checked_at": utc_now(),
    }


class AdminCliSession:
    """Non-interactive command runner + optional streaming interactive shell."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._on_output: Callable[[str], None] | None = None

    def run_command(self, command: str) -> dict[str, Any]:
        availability = cli_availability()
        if not availability.get("available"):
            raise RuntimeError(
                availability.get("reason")
                or "Admin Linux CLI unavailable on this console"
            )
        shell = str(availability["shell"])
        cleaned = command.strip()
        if not cleaned:
            raise RuntimeError("empty command")
        result = subprocess.run(
            [shell, "-lc", cleaned],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "status": "completed",
            "command": cleaned,
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "shell": shell,
            "ran_at": utc_now(),
        }

    def start_interactive(self, on_output: Callable[[str], None]) -> dict[str, Any]:
        availability = cli_availability()
        if not availability.get("available"):
            raise RuntimeError(
                availability.get("reason")
                or "Admin Linux CLI unavailable on this console"
            )
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("interactive shell already running")
        shell = str(availability["shell"])
        self._on_output = on_output
        self._proc = subprocess.Popen(
            [shell, "-i"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def _pump() -> None:
            assert self._proc is not None and self._proc.stdout is not None
            for line in self._proc.stdout:
                if self._on_output is not None:
                    self._on_output(line)

        self._reader = threading.Thread(target=_pump, daemon=True)
        self._reader.start()
        return {
            "status": "started",
            "pid": self._proc.pid,
            "shell": shell,
            "started_at": utc_now(),
        }

    def write(self, data: str) -> None:
        if self._proc is None or self._proc.stdin is None or self._proc.poll() is not None:
            raise RuntimeError("interactive shell is not running")
        self._proc.stdin.write(data if data.endswith("\n") else data + "\n")
        self._proc.stdin.flush()

    def stop(self) -> dict[str, Any]:
        if self._proc is None:
            return {"status": "idle", "stopped_at": utc_now()}
        pid = self._proc.pid
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._reader = None
        self._on_output = None
        return {"status": "stopped", "pid": pid, "stopped_at": utc_now()}
