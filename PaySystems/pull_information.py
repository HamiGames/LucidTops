"""Associated pull_information script for the PaySystems container.

payments.secrets is written on the Pi console at image creation.
Connection constants are copied from Master.secrets and proxy.secrets.
Torrc is recorded when /mnt/myssd/LucidTops/torrc is present.
"""

from __future__ import annotations

import os
from pathlib import Path


_CONNECTION_KEYS = (
    "DOCKER_NETWORK_NAME",
    "PROXY_SELF_DNS",
    "MASTER_SERVER_ONION",
    "ADMIN_ONION",
    "FRONTEND_ONION",
    "PAYSYSTEMS_BIND_HOST",
    "PAYSYSTEMS_BIND_PORT",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def _parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key and value.strip():
            values[key] = value.strip()
    return values


def _secrets_dir() -> Path:
    raw = _env("SECRETS_DIR") or "/mnt/myssd/LucidTops/Server/Secrets"
    return Path(raw).expanduser()


def pull_information() -> dict[str, str]:
    directory = _secrets_dir()
    master = _parse(directory / "Master.secrets")
    proxy = _parse(directory / "proxy.secrets")
    merged = dict(proxy)
    for key, value in master.items():
        merged[key] = value
    root = Path(_env("LUCID_TOPS_ROOT") or "/mnt/myssd/LucidTops")
    torrc = root / "torrc"
    if torrc.is_file():
        merged["HOST_TOR_CONFIG_TORRC"] = torrc.as_posix()
    merged["SECRETS_DIR"] = directory.as_posix()
    merged["LUCID_TOPS_ROOT"] = root.as_posix()
    return merged


def write_payments_secrets_at_image_creation() -> Path:
    directory = _secrets_dir()
    directory.mkdir(parents=True, exist_ok=True)
    sourced = pull_information()
    if not sourced.get("DOCKER_NETWORK_NAME"):
        raise RuntimeError(
            "DOCKER_NETWORK_NAME missing from Master.secrets and proxy.secrets"
        )
    path = directory / "payments.secrets"
    values = _parse(path)
    for key in _CONNECTION_KEYS:
        if sourced.get(key):
            values[key] = sourced[key]
    if sourced.get("HOST_TOR_CONFIG_TORRC"):
        values["HOST_TOR_CONFIG_TORRC"] = sourced["HOST_TOR_CONFIG_TORRC"]
    values["SECRETS_DIR"] = directory.as_posix()
    values["PAYMENTS_SECRETS_FILE"] = path.as_posix()
    values["LUCID_TOPS_ROOT"] = sourced.get("LUCID_TOPS_ROOT", "")
    lines = [
        "# LucidTops payments.secrets — seeded at image creation from Master.secrets and proxy.secrets"
    ]
    for key in sorted(values):
        if values[key]:
            lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    path = write_payments_secrets_at_image_creation()
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
