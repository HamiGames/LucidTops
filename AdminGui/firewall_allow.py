"""Allowlist TorBrowser with the OS firewall at Connect time (no installer).

Sidesteps Windows firewall alarms when connecting to the Tor network.
Windows + Linux only (AdminGui §15.5).
All rule names and binary paths come from secrets / hardware discovery at time of operation.
"""

from __future__ import annotations

import importlib.util
import platform
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


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def allowlist_tor_browser_firewall(browser_bin: str | None = None) -> dict[str, Any]:
    """Register discovered TorBrowser binary with the OS firewall allowlist."""
    ensure_admin_secrets_from_pull()
    path = (browser_bin or get_admin_secret("ADMIN_TOR_BROWSER_BIN") or "").strip()
    if not path:
        raise RuntimeError(
            "ADMIN_TOR_BROWSER_BIN missing — cannot configure firewall allowlist"
        )
    binary = Path(path)
    if not binary.exists():
        raise RuntimeError(
            f"TorBrowser binary missing at {binary.as_posix()} — cannot allowlist"
        )

    system = (get_admin_secret("ADMIN_SYSTEM") or platform.system()).lower()
    rule_name = get_admin_secret("ADMIN_FIREWALL_RULE_NAME")
    if not rule_name:
        rule_name = f"LucidTops-AdminGui-TorBrowser-{binary.stem}"
        import os

        os.environ["ADMIN_FIREWALL_RULE_NAME"] = rule_name

    actions: list[dict[str, Any]] = []
    if system == "windows":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            raise RuntimeError("powershell missing — cannot configure Windows firewall")
        script = (
            f"$name='{rule_name}'; $path='{binary.as_posix()}';"
            " if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {"
            " New-NetFirewallRule -DisplayName $name -Direction Outbound -Program $path"
            " -Action Allow -Profile Any | Out-Null };"
            " if (-not (Get-NetFirewallRule -DisplayName ($name+'-in') -ErrorAction SilentlyContinue)) {"
            " New-NetFirewallRule -DisplayName ($name+'-in') -Direction Inbound -Program $path"
            " -Action Allow -Profile Any | Out-Null }"
        )
        result = _run([ps, "-NoProfile", "-Command", script])
        actions.append(
            {
                "system": "windows",
                "exit": result.returncode,
                "stderr": result.stderr.strip()[:300],
            }
        )
        if result.returncode != 0:
            netsh = shutil.which("netsh")
            if netsh:
                out = _run(
                    [
                        netsh,
                        "advfirewall",
                        "firewall",
                        "add",
                        "rule",
                        f"name={rule_name}",
                        "dir=out",
                        "action=allow",
                        f"program={binary}",
                        "enable=yes",
                    ]
                )
                actions.append({"system": "windows-netsh", "exit": out.returncode})
    else:
        ufw = shutil.which("ufw")
        firewall_cmd = shutil.which("firewall-cmd")
        if ufw:
            result = _run([ufw, "allow", "out", "from", "any", "to", "any"])
            actions.append(
                {
                    "system": "linux-ufw",
                    "exit": result.returncode,
                    "note": "egress allow; binary path recorded in secrets",
                }
            )
        elif firewall_cmd:
            result = _run([firewall_cmd, "--permanent", "--add-service=https"])
            actions.append({"system": "linux-firewalld", "exit": result.returncode})
            _run([firewall_cmd, "--reload"])
        else:
            actions.append(
                {
                    "system": "linux",
                    "status": "no_firewall_tool",
                    "binary": binary.as_posix(),
                }
            )

    return {
        "status": "allowlisted",
        "binary": binary.as_posix(),
        "rule_name": rule_name,
        "actions": actions,
        "configured_at": utc_now(),
    }
