"""AdminGui downloadable authentication — emailed 6-digit code at time of operation.

code criteria;(
    1. an emailed randomly generated 6 didget int is to be provided.
    2. genrated code is compared to the manually input code.
    3. email address is "lucidchain@proton.me"
    4. the only accepted email address is "lucidchain@proton.me")

SMTP credentials and destination email are read from secrets created at time of operation.
No credentials are stored in this module.
"""

from __future__ import annotations

import importlib.util
import secrets
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
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
require_admin_secret = _admin_secrets.require_admin_secret
ensure_admin_secrets_from_pull = _admin_secrets.ensure_admin_secrets_from_pull
admin_auth_secrets_path = _admin_secrets.admin_auth_secrets_path
parse_secrets_file = _admin_secrets.parse_secrets_file
load_admin_secrets = _admin_secrets.load_admin_secrets


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _write_auth_secrets(updates: dict[str, str]) -> Path:
    path = admin_auth_secrets_path()
    existing = parse_secrets_file(path) if path.exists() else {}
    existing.update({k.upper(): v for k, v in updates.items() if v is not None})
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops admin_auth.secrets — generated at time of operation",
        f"# updated_at={utc_now_iso()}",
    ]
    for key in sorted(existing.keys()):
        if existing[key] == "":
            continue
        lines.append(f"{key}={existing[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load_admin_secrets(reload=True)
    return path


def _accepted_email() -> str:
    """Destination must come from secrets; compared to accepted address also from secrets."""
    destination = require_admin_secret("ADMIN_DOWNLOAD_AUTH_EMAIL").lower()
    accepted = get_admin_secret("ADMIN_ACCEPTED_AUTH_EMAIL").lower()
    if not accepted:
        raise RuntimeError(
            "ADMIN_ACCEPTED_AUTH_EMAIL missing — must be set in secrets at time of operation"
        )
    if destination != accepted:
        raise RuntimeError(
            "ADMIN_DOWNLOAD_AUTH_EMAIL does not match ADMIN_ACCEPTED_AUTH_EMAIL — "
            "only the accepted address may receive download auth codes"
        )
    return destination


def generate_six_digit_code() -> str:
    """Randomly generated 6 digit int at time of operation."""
    return f"{secrets.randbelow(900000) + 100000:06d}"


def _smtp_settings() -> dict[str, str]:
    host = require_admin_secret("ADMIN_SMTP_HOST")
    port = require_admin_secret("ADMIN_SMTP_PORT")
    user = require_admin_secret("ADMIN_SMTP_USER")
    password = require_admin_secret("ADMIN_SMTP_PASSWORD")
    use_tls = get_admin_secret("ADMIN_SMTP_USE_TLS") or "1"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "use_tls": use_tls,
    }


def _send_code_email(*, destination: str, code: str) -> dict[str, Any]:
    smtp = _smtp_settings()
    message = EmailMessage()
    message["Subject"] = "LucidTops AdminGui download authentication code"
    message["From"] = smtp["user"]
    message["To"] = destination
    message.set_content(
        "LucidTops AdminGui download authentication.\n\n"
        f"Your one-time code: {code}\n\n"
        "Enter this code in the AdminGui Authenticate field.\n"
    )

    port = int(smtp["port"])
    use_tls = smtp["use_tls"].lower() not in {"0", "false", "no"}
    if use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp["host"], port, timeout=45) as client:
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
            client.login(smtp["user"], smtp["password"])
            client.send_message(message)
    else:
        with smtplib.SMTP(smtp["host"], port, timeout=45) as client:
            client.ehlo()
            client.login(smtp["user"], smtp["password"])
            client.send_message(message)

    return {
        "status": "sent",
        "destination": destination,
        "smtp_host": smtp["host"],
        "sent_at": utc_now_iso(),
    }


def issue_download_auth_code(*, ttl_minutes: int | None = None) -> dict[str, Any]:
    """Generate, persist, and email a 6-digit download auth code at time of operation."""
    ensure_admin_secrets_from_pull()
    destination = _accepted_email()
    code = generate_six_digit_code()
    minutes = ttl_minutes
    if minutes is None:
        ttl_raw = get_admin_secret("ADMIN_AUTH_CODE_TTL_MINUTES")
        minutes = int(ttl_raw) if ttl_raw.isdigit() else 15
    expires = utc_now() + timedelta(minutes=max(1, minutes))
    _write_auth_secrets(
        {
            "ADMIN_AUTH_CODE": code,
            "ADMIN_AUTH_CODE_EXPIRES_AT": expires.isoformat(),
            "ADMIN_AUTH_CODE_ISSUED_AT": utc_now_iso(),
            "ADMIN_AUTH_CODE_ATTEMPTS": "0",
            "ADMIN_AUTH_VERIFIED": "0",
            "ADMIN_DOWNLOAD_AUTH_EMAIL": destination,
        }
    )
    mail = _send_code_email(destination=destination, code=code)
    return {
        "status": "issued",
        "email": mail,
        "expires_at": expires.isoformat(),
        "code_digits": 6,
    }


def verify_download_auth_code(entered: str) -> dict[str, Any]:
    """Compare manually input code to the generated code stored in secrets."""
    ensure_admin_secrets_from_pull(reload=True)
    load_admin_secrets(reload=True)
    expected = get_admin_secret("ADMIN_AUTH_CODE")
    if not expected:
        raise RuntimeError(
            "ADMIN_AUTH_CODE missing — issue a download auth code at time of operation first"
        )
    expires_raw = get_admin_secret("ADMIN_AUTH_CODE_EXPIRES_AT")
    if expires_raw:
        try:
            expires = datetime.fromisoformat(expires_raw)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if utc_now() > expires:
                _write_auth_secrets(
                    {
                        "ADMIN_AUTH_CODE": "",
                        "ADMIN_AUTH_VERIFIED": "0",
                    }
                )
                raise RuntimeError("download auth code expired — issue a new code")
        except ValueError as exc:
            raise RuntimeError(
                "ADMIN_AUTH_CODE_EXPIRES_AT invalid — recreate auth secrets at time of operation"
            ) from exc

    attempts_raw = get_admin_secret("ADMIN_AUTH_CODE_ATTEMPTS") or "0"
    attempts = int(attempts_raw) if attempts_raw.isdigit() else 0
    max_raw = get_admin_secret("ADMIN_AUTH_MAX_ATTEMPTS")
    max_attempts = int(max_raw) if max_raw.isdigit() else 5

    normalized = "".join(ch for ch in str(entered).strip() if ch.isdigit())
    if normalized != expected:
        attempts += 1
        _write_auth_secrets({"ADMIN_AUTH_CODE_ATTEMPTS": str(attempts)})
        if attempts >= max_attempts:
            _write_auth_secrets(
                {
                    "ADMIN_AUTH_CODE": "",
                    "ADMIN_AUTH_VERIFIED": "0",
                    "ADMIN_AUTH_CODE_ATTEMPTS": str(attempts),
                }
            )
            raise RuntimeError(
                "download auth failed — too many attempts; issue a new code"
            )
        raise RuntimeError("download auth code mismatch")

    _write_auth_secrets(
        {
            "ADMIN_AUTH_CODE": "",
            "ADMIN_AUTH_VERIFIED": "1",
            "ADMIN_AUTH_VERIFIED_AT": utc_now_iso(),
            "ADMIN_AUTH_CODE_ATTEMPTS": "0",
        }
    )
    return {
        "status": "verified",
        "verified_at": utc_now_iso(),
    }


def is_download_auth_verified() -> bool:
    ensure_admin_secrets_from_pull()
    return get_admin_secret("ADMIN_AUTH_VERIFIED") in {"1", "true", "True", "yes"}


def require_download_auth_verified() -> None:
    if not is_download_auth_verified():
        raise RuntimeError(
            "download authentication required — issue and verify the emailed 6-digit code"
        )
