#!/usr/bin/env python3
"""Append-only onion key patch for Server/Secrets (Master.secrets + proxy.secrets).

Purpose:
  Publish ADMIN_ONION and BLOCKCHAIN_ONION into the shared seed files without
  erasing, reordering, or changing any existing key=value lines.

Seed targets (fixes.txt §19):
  /mnt/myssd/LucidTops/Server/Secrets/Master.secrets
  /mnt/myssd/LucidTops/Server/Secrets/proxy.secrets  (also Proxy.secrets)

Onion sources (first match wins, at time of operation):
  {LUCID_TOPS_ROOT}/tor/hidden_service/admin/hostname
  {LUCID_TOPS_ROOT}/tor/hidden_service/blockchain/hostname
  {LUCID_TOPS_ROOT}/onion/admin.onion
  {LUCID_TOPS_ROOT}/onion/blockchain.onion
  {LUCID_TOPS_ROOT}/onions/admin/hostname
  {LUCID_TOPS_ROOT}/onions/blockchain/hostname
  env ADMIN_ONION / BLOCKCHAIN_ONION

RULES:
- Never overwrite a key that already has a non-empty value in the target file.
- Never rewrite the whole secrets file; only append missing KEY=value lines.
- NO pull from GIT repository.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BLOCKCHAIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BLOCKCHAIN_DIR.parent

# Keys this patch may ADD (never edit if already present and non-empty).
PATCH_ONION_KEYS: tuple[str, ...] = (
    "ADMIN_ONION",
    "BLOCKCHAIN_ONION",
)

# service_key -> secrets key
SERVICE_TO_SECRET: dict[str, str] = {
    "admin": "ADMIN_ONION",
    "blockchain": "BLOCKCHAIN_ONION",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(key: str) -> str:
    return os.environ.get(key, "").strip()


def resolve_lucid_tops_root() -> Path:
    raw = _env("LUCID_TOPS_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    default = Path("/mnt/myssd/LucidTops")
    if default.is_dir():
        return default.resolve()
    # Dev / Windows checkout next to blockchain/
    if (PROJECT_ROOT / "proxy").is_dir() and (PROJECT_ROOT / "blockchain").is_dir():
        return PROJECT_ROOT.resolve()
    raise RuntimeError(
        "LUCID_TOPS_ROOT missing — set env or mount /mnt/myssd/LucidTops"
    )


def server_secrets_dir(lucid_root: Path) -> Path:
    override = _env("MASTER_SECRETS_DIR") or _env("SERVER_SECRETS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (lucid_root / "Server" / "Secrets").resolve()


def master_secrets_path(lucid_root: Path) -> Path:
    override = _env("MASTER_SECRETS_FILE")
    if override:
        return Path(override).expanduser().resolve()
    directory = server_secrets_dir(lucid_root)
    for name in ("Master.secrets", "master.secrets"):
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve()
    return (directory / "Master.secrets").resolve()


def proxy_secrets_path(lucid_root: Path) -> Path:
    override = _env("PROXY_SECRETS_FILE")
    if override:
        return Path(override).expanduser().resolve()
    directory = server_secrets_dir(lucid_root)
    for name in ("proxy.secrets", "Proxy.secrets"):
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve()
    return (directory / "proxy.secrets").resolve()


def _normalize_onion(raw: str) -> str:
    value = raw.strip().lower().split("/")[0]
    if value.endswith(".onion"):
        return value
    return ""


def _read_text_if_file(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return ""


def discover_onion(lucid_root: Path, service_key: str) -> str:
    """Pull onion hostname for one service from Tor HS / export paths / env."""
    secret_key = SERVICE_TO_SECRET[service_key]
    from_env = _normalize_onion(_env(secret_key))
    if from_env:
        return from_env

    candidates = [
        lucid_root / "tor" / "hidden_service" / service_key / "hostname",
        lucid_root / "onion" / f"{service_key}.onion",
        lucid_root / "onions" / service_key / "hostname",
        lucid_root / "onions" / f"{service_key}.onion",
    ]
    for path in candidates:
        onion = _normalize_onion(_read_text_if_file(path))
        if onion:
            return onion
    return ""


def discover_patch_values(lucid_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for service_key, secret_key in SERVICE_TO_SECRET.items():
        onion = discover_onion(lucid_root, service_key)
        if onion:
            values[secret_key] = onion
    return values


def parse_existing_keys(path: Path) -> dict[str, str]:
    """Parse key=value map for presence checks only (does not rewrite file)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot read secrets file: {path.as_posix()}: {exc}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def append_missing_keys(path: Path, candidates: dict[str, str]) -> dict[str, str]:
    """
    Append only keys that are absent or empty in the existing file.
    Existing lines are never modified, deleted, or reordered.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_existing_keys(path) if path.exists() else {}
    to_add: dict[str, str] = {}
    for key in PATCH_ONION_KEYS:
        value = candidates.get(key, "").strip()
        if not value:
            continue
        current = existing.get(key, "").strip()
        if current:
            continue
        to_add[key] = value

    if not to_add:
        return {}

    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"cannot read secrets file: {path.as_posix()}: {exc}") from exc
        if raw and not raw.endswith("\n"):
            raw += "\n"
    else:
        raw = (
            "# LucidTops Server/Secrets — created by blockchain/patch_server_secrets_onions.py\n"
            f"# Generated: {utc_now()}\n"
            "# Append-only onion patch (existing content is never rewritten by this script).\n"
            "\n"
        )

    block_lines = [
        "",
        f"# --- append-only onion patch {utc_now()} (blockchain/patch_server_secrets_onions.py) ---",
    ]
    for key, value in to_add.items():
        block_lines.append(f"{key}={value}")
    block_lines.append("")

    path.write_text(raw + "\n".join(block_lines), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return to_add


def patch_server_secrets(
    *,
    lucid_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    root = lucid_root if lucid_root is not None else resolve_lucid_tops_root()
    master_path = master_secrets_path(root)
    proxy_path = proxy_secrets_path(root)
    discovered = discover_patch_values(root)

    report: dict[str, object] = {
        "lucid_tops_root": root.as_posix(),
        "master_secrets_file": master_path.as_posix(),
        "proxy_secrets_file": proxy_path.as_posix(),
        "discovered": dict(discovered),
        "dry_run": dry_run,
        "master_added": {},
        "proxy_added": {},
        "skipped_present": {},
        "missing_sources": [],
    }

    for key in PATCH_ONION_KEYS:
        if key not in discovered:
            report["missing_sources"].append(key)

    skipped: dict[str, list[str]] = {"master": [], "proxy": []}
    for label, path in (("master", master_path), ("proxy", proxy_path)):
        existing = parse_existing_keys(path) if path.exists() else {}
        for key in PATCH_ONION_KEYS:
            if existing.get(key, "").strip() and key in discovered:
                skipped[label].append(key)
    report["skipped_present"] = skipped

    if dry_run:
        would_add_master = {
            k: v
            for k, v in discovered.items()
            if k in PATCH_ONION_KEYS
            and not parse_existing_keys(master_path).get(k, "").strip()
        }
        would_add_proxy = {
            k: v
            for k, v in discovered.items()
            if k in PATCH_ONION_KEYS
            and not parse_existing_keys(proxy_path).get(k, "").strip()
        }
        report["master_added"] = would_add_master
        report["proxy_added"] = would_add_proxy
        return report

    report["master_added"] = append_missing_keys(master_path, discovered)
    report["proxy_added"] = append_missing_keys(proxy_path, discovered)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Append ADMIN_ONION / BLOCKCHAIN_ONION to Server/Secrets Master.secrets "
            "and proxy.secrets without modifying existing lines."
        )
    )
    parser.add_argument(
        "--lucid-tops-root",
        default="",
        help="Override LUCID_TOPS_ROOT (default: env or /mnt/myssd/LucidTops)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be appended; do not write files",
    )
    args = parser.parse_args(argv)

    root = (
        Path(args.lucid_tops_root).expanduser().resolve()
        if args.lucid_tops_root.strip()
        else None
    )
    try:
        report = patch_server_secrets(lucid_root=root, dry_run=bool(args.dry_run))
    except RuntimeError as exc:
        print(f"patch_server_secrets_onions failed: {exc}", file=sys.stderr)
        return 1

    print(f"lucid_tops_root={report['lucid_tops_root']}")
    print(f"master_secrets_file={report['master_secrets_file']}")
    print(f"proxy_secrets_file={report['proxy_secrets_file']}")
    print(f"discovered={report['discovered']}")
    print(f"missing_sources={report['missing_sources']}")
    print(f"skipped_present={report['skipped_present']}")
    print(f"master_added={report['master_added']}")
    print(f"proxy_added={report['proxy_added']}")
    if args.dry_run:
        print("dry_run=true (no files written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
