"""Internal User and NodeUser route sets.

Connection material is read at container creation from proxy.secrets and
Master.secrets, then stored inside this package as two route files.
Neither route file is a shared lookup table. Callers pass a branch and
receive only that branch's copy.

This module does not start, attach, or call the Proxy container.
"""

from __future__ import annotations

import os
from pathlib import Path

USERONLY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = USERONLY_DIR.parent
INTERNAL_DIR = USERONLY_DIR / "internal"
SOURCE_DIR = INTERNAL_DIR / "source"
INTERNAL_CONFIG_NAME = "internal.routes"
RDP_IMAGE = "pickme/lucidtops_rdp:v1.0.0"
PI_SECRETS_DIR = Path("/mnt/myssd/LucidTops/useronly/secrets")
SERVER_SECRETS_DIR = Path("/mnt/myssd/Server/Secrets")

_SKIP_PARTS = (
    "CLEARNET",
    "HMAC",
    "MONGODB",
    "PAYMENT",
    "PAYMENTS",
    "MERCHANT",
    "NGINX_CONF",
    "PROXY_HMAC",
    "PROXY_API_TOKEN",
    "PROXY_GATE",
    "PROXY_UVICORN",
    "PROXY_PID",
    "PROXY_LOG",
    "EMV_",
)

_BOTH_PARTS = (
    "FRONTEND",
    "HANDSHAKE",
    "REGISTER",
    "LOGIN",
    "API_BASE",
    "TOR_SOCKS",
    "TOR_BIN",
    "TOR_CONTROL",
)

_USER_PARTS = ("RDP", "SESSION")

_NODE_PARTS = (
    "NODE",
    "OPERATIONS",
    "BLOCKCHAIN",
    "NODEUSER",
    "PROXY_BACKEND",
    "DOCKER_NETWORK",
)

_NODE_IMAGE_KEYS = (
    "NODE_IMAGE",
    "NODE_CONTAINER_IMAGE",
    "LUCID_NODE_IMAGE",
    "NODEUSER_IMAGE",
)


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def _write_route_file(path: Path, values: dict[str, str], *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# LucidTops internal {label}",
        "# Stored inside the useronly container. Not shown in the GUI.",
    ]
    for key in sorted(values):
        if values[key] == "":
            continue
        lines.append(f"{key}={values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _candidate_secret_dirs(lucid_root: Path | None) -> list[Path]:
    """Creation-time route files. The Pi path is first; the image copy is the fallback."""
    dirs: list[Path] = [SERVER_SECRETS_DIR, SOURCE_DIR]
    raw = _env("SERVER_SECRETS_DIR")
    if raw:
        dirs.append(Path(raw).expanduser())
    dirs.extend(
        [
            Path("/mnt/myssd/LucidTops/Server/Secrets"),
            PROJECT_ROOT / "LucidTops" / "Server" / "Secrets",
            PROJECT_ROOT / "Server" / "Secrets",
        ]
    )
    if lucid_root is not None:
        dirs.append(lucid_root / "Server" / "Secrets")
    seen: set[str] = set()
    ordered: list[Path] = []
    for directory in dirs:
        key = directory.as_posix()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(directory)
    return ordered


def _resolve_named(file_env: str, name: str, directories: list[Path]) -> Path | None:
    override = _env(file_env)
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
    for directory in directories:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def locate_creation_secrets(lucid_root: Path | None = None) -> tuple[Path, Path]:
    """Find proxy.secrets and Master.secrets. Both must exist."""
    copied_proxy = SOURCE_DIR / "proxy.secrets"
    copied_master = SOURCE_DIR / "Master.secrets"
    if copied_proxy.is_file() and copied_master.is_file():
        return copied_proxy, copied_master
    directories = _candidate_secret_dirs(lucid_root)
    proxy = _resolve_named("PROXY_SECRETS_FILE", "proxy.secrets", directories)
    if proxy is None:
        raise RuntimeError(
            "proxy.secrets missing — expected under /mnt/myssd/Server/Secrets "
            "or LucidTops/Server/Secrets at container creation"
        )
    proxy_values = parse_secrets_file(proxy)
    master_hint = proxy_values.get("MASTER_SECRETS_FILE", "")
    master = _resolve_named("MASTER_SECRETS_FILE", "Master.secrets", directories)
    if master is None and master_hint:
        hinted = Path(master_hint).expanduser()
        if hinted.is_file():
            master = hinted
    if master is None:
        expected = master_hint or "/mnt/myssd/Server/Secrets/Master.secrets"
        raise RuntimeError(
            f"Master.secrets missing — expected at {expected}. "
            "Both proxy.secrets and Master.secrets are required at container creation."
        )
    return proxy, master


def _bucket(key: str) -> str:
    upper = key.upper()
    if any(part in upper for part in _SKIP_PARTS):
        return "skip"
    if any(part in upper for part in _USER_PARTS):
        return "user"
    if any(part in upper for part in _NODE_PARTS) and "FRONTEND" not in upper:
        return "node"
    if any(part in upper for part in _BOTH_PARTS):
        return "both"
    return "skip"


def split_route_sets(source: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Copy matching keys into two independent route maps."""
    user: dict[str, str] = {}
    nodeuser: dict[str, str] = {}
    for key, value in source.items():
        if not value:
            continue
        bucket = _bucket(key)
        if bucket == "user":
            user[key] = value
        elif bucket == "node":
            nodeuser[key] = value
        elif bucket == "both":
            user[key] = value
            nodeuser[key] = value
    if not user:
        raise RuntimeError("User route set is empty after reading proxy.secrets and Master.secrets")
    if not nodeuser:
        raise RuntimeError(
            "NodeUser route set is empty after reading proxy.secrets and Master.secrets"
        )
    return user, nodeuser


def _copy_source(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _first_path(source: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = source.get(key, "").strip()
        if value:
            return value
    return ""


def explicit_route_criteria(source: dict[str, str]) -> dict[str, str]:
    """Copy the cross-container criteria this container is allowed to keep."""
    criteria: dict[str, str] = {"RDP_IMAGE": RDP_IMAGE}
    onion = _first_path(source, "FRONTEND_ONION", "ONION_FRONTEND")
    if onion.endswith(".onion"):
        criteria["FRONTEND_ONION"] = onion.split("/")[0].lower()
    api = _first_path(source, "API_BASE_PATH", "PROXY_API_PREFIX")
    handshake = _first_path(source, "HANDSHAKE_PATH", "FRONTEND_HANDSHAKE_PATH")
    if not handshake and api.startswith("/"):
        handshake = api.rstrip("/") + "/connect-handshake"
    if handshake.startswith("/"):
        criteria["HANDSHAKE_PATH"] = handshake
    node_target = _first_path(source, "VALIDATION_NODE_TARGET", "NODE_BASE_PATH")
    if node_target.startswith("/"):
        criteria["VALIDATION_NODE_TARGET"] = node_target
    backend_target = _first_path(
        source, "VALIDATION_BACKEND_TARGET", "BACKEND_VALIDATION_PATH", "API_BASE_PATH"
    )
    if backend_target.startswith("/"):
        criteria["VALIDATION_BACKEND_TARGET"] = backend_target
    proxy_route = _first_path(source, "PROXY_FOREGROUND_PATH", "PROXY_API_PREFIX", "API_BASE_PATH")
    if proxy_route.startswith("/"):
        criteria["PROXY_FOREGROUND_PATH"] = proxy_route
    userdb = _first_path(source, "USERDB_VERIFY_PATH")
    if not userdb and api.startswith("/"):
        userdb = api.rstrip("/") + "/LucidTops_UserDB"
    if userdb.startswith("/"):
        criteria["USERDB_VERIFY_PATH"] = userdb
    for key in _NODE_IMAGE_KEYS:
        image = source.get(key, "").strip()
        if image:
            criteria["NODE_IMAGE"] = image
            break
    return criteria


def _config_targets(secrets_dir: Path | None) -> list[Path]:
    targets: list[Path] = []
    if secrets_dir is not None:
        targets.append(secrets_dir / INTERNAL_CONFIG_NAME)
    env_dir = _env("SECRETS_DIR")
    if env_dir:
        targets.append(Path(env_dir).expanduser() / INTERNAL_CONFIG_NAME)
    if os.name != "nt" or PI_SECRETS_DIR.exists():
        targets.append(PI_SECRETS_DIR / INTERNAL_CONFIG_NAME)
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in targets:
        key = path.as_posix()
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def _write_internal_config(path: Path, user: dict[str, str], nodeuser: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops internal.routes",
        "# Runtime route source for this container. Not shown in the GUI.",
        "[user]",
    ]
    for key in sorted(user):
        if user[key]:
            lines.append(f"{key}={user[key]}")
    lines.append("[nodeuser]")
    for key in sorted(nodeuser):
        if nodeuser[key]:
            lines.append(f"{key}={nodeuser[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_internal_config(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {"user": {}, "nodeuser": {}}
    current = ""
    if not path.is_file():
        return sections
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip().lower()
            current = name if name in sections else ""
            continue
        if not current or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            sections[current][key] = value.strip()
    return sections


def locate_internal_config() -> Path | None:
    for path in _config_targets(None):
        if path.is_file():
            return path
    return None


def ingest_route_sets(
    lucid_root: Path | None = None, secrets_dir: Path | None = None
) -> dict[str, str]:
    """Read creation secrets and write internal.routes under the useronly secrets directory."""
    proxy_path, master_path = locate_creation_secrets(lucid_root)
    merged = parse_secrets_file(proxy_path)
    merged.update(parse_secrets_file(master_path))
    user, nodeuser = split_route_sets(merged)
    criteria = explicit_route_criteria(merged)
    for key, value in criteria.items():
        if key == "NODE_IMAGE":
            nodeuser[key] = value
            continue
        user[key] = value
        nodeuser[key] = value
    _copy_source(proxy_path, SOURCE_DIR / "proxy.secrets")
    _copy_source(master_path, SOURCE_DIR / "Master.secrets")
    written = ""
    for target in _config_targets(secrets_dir):
        try:
            _write_internal_config(target, user, nodeuser)
        except OSError:
            continue
        written = target.as_posix()
    if not written:
        raise RuntimeError(
            "internal.routes could not be written under the useronly secrets directory"
        )
    return {
        "proxy_secrets": (SOURCE_DIR / "proxy.secrets").as_posix(),
        "master_secrets": (SOURCE_DIR / "Master.secrets").as_posix(),
        "internal_routes": written,
        "user_route_file": written,
        "nodeuser_route_file": written,
    }


def load_route_set(branch: str) -> dict[str, str]:
    """Return one branch from internal.routes. Refuses the other branch's section."""
    normalized = branch.strip().lower()
    if normalized in {"user", "useronly", "false"}:
        label = "user"
    elif normalized in {"node", "nodeuser", "true"}:
        label = "nodeuser"
    else:
        raise RuntimeError(f"unknown route branch '{branch}'")
    path = locate_internal_config()
    if path is None:
        ingest_route_sets()
        path = locate_internal_config()
    if path is None:
        raise RuntimeError("internal.routes missing from the useronly secrets directory")
    values = parse_internal_config(path).get(label) or {}
    if not values:
        raise RuntimeError(f"{label} route set missing in {path.as_posix()}")
    return values


def node_image_name() -> str:
    routes = load_route_set("nodeuser")
    for key in _NODE_IMAGE_KEYS:
        value = routes.get(key, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    written = ingest_route_sets()
    print(written["user_route_file"])
    print(written["nodeuser_route_file"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
