""" this is the package required for Clearnet access from MasterServer (uvicorn / FastAPI).
applications:
- used by PaySystems for clearnet payment processing.
- used by transport paths for clearnet egress.
- uses Tor SOCKS5 (TOR_SOCKS_HOST / TOR_SOCKS_PORT from proxy.secrets after hardware pull).
- uses EMV 3-D Secure headers; version/currency/timeouts from secrets created at operation.
- uses HMAC-SHA256 (CLEARNET_HMAC_KEY / payments secrets) to authenticate clearnet payloads.
- returns only payment valid/invalid results toward MasterServer (no raw card data).
- payment processor URLs and API keys live in payments.secrets (path from PAYMENTS_SECRETS_FILE
  in proxy.secrets — typically under the pulled LucidTops Secrets directory).

restrictions:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- at time of operation = when pull → proxy.secrets / payments.secrets were written.
- SOCKS5 endpoints MUST come from pulled/created secrets (hardware Tor), not baked IPs/ports.
- No sensitive data, all data is stored in the secrets file.

"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_PROXY_DIR = Path(__file__).resolve().parent
if str(_PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(_PROXY_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _PROXY_DIR / file_name
    registry = f"lucid_proxy_{module_name}"
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


_buildsecrets = _load_local("buildsecrets")
get_proxy_secret = _buildsecrets.get_proxy_secret
load_proxy_secrets = _buildsecrets.load_proxy_secrets
require_proxy_secret = _buildsecrets.require_proxy_secret
parse_secrets_file = _buildsecrets.parse_secrets_file

try:
    import socks  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    socks = None  # type: ignore[assignment]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def payments_secrets_path() -> Path:
    configured = os.environ.get("PAYMENTS_SECRETS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(require_proxy_secret("PAYMENTS_SECRETS_FILE")).expanduser()


def load_payments_secrets() -> dict[str, str]:
    path = payments_secrets_path()
    loaded = parse_secrets_file(path)
    for key, value in loaded.items():
        if not os.environ.get(key, "").strip():
            os.environ[key] = value
    return loaded


def clearnet_hmac_key() -> bytes:
    load_proxy_secrets()
    load_payments_secrets()
    key = (
        os.environ.get("CLEARNET_HMAC_KEY", "").strip()
        or get_proxy_secret("CLEARNET_HMAC_KEY")
        or os.environ.get("PAYMENTS_HMAC_KEY", "").strip()
        or get_proxy_secret("PAYMENTS_HMAC_KEY")
    )
    if not key:
        raise RuntimeError(
            "CLEARNET_HMAC_KEY missing — run buildsecrets before clearnet access"
        )
    return key.encode("utf-8")


def sign_clearnet_payload(payload: bytes, *, key: bytes | None = None) -> str:
    material = key if key is not None else clearnet_hmac_key()
    return hmac.new(material, payload, hashlib.sha256).hexdigest()


def verify_clearnet_signature(payload: bytes, signature: str, *, key: bytes | None = None) -> bool:
    expected = sign_clearnet_payload(payload, key=key)
    return hmac.compare_digest(expected, signature.strip().lower())


def _socks_endpoint() -> tuple[str, int]:
    load_proxy_secrets()
    host = require_proxy_secret("TOR_SOCKS_HOST")
    port = int(require_proxy_secret("TOR_SOCKS_PORT"))
    return host, port


def _install_socks5_opener() -> None:
    if socks is None:
        raise RuntimeError(
            "PySocks is required for SOCKS5 clearnet egress (pip install PySocks)"
        )
    host, port = _socks_endpoint()
    socks.set_default_proxy(socks.SOCKS5, host, port)
    # Route stdlib sockets through Tor SOCKS5 (user → MasterServer clearnet path).
    import socket as _socket

    _socket.socket = socks.socksocket  # type: ignore[misc, assignment]


def build_emv_3ds_headers(
    *,
    merchant_ref: str,
    amount: str,
    currency: str,
) -> dict[str, str]:
    """EMV 3-D Secure related request headers for payment processor egress."""
    emv_version = (
        os.environ.get("EMV_3DS_VERSION", "").strip()
        or require_proxy_secret("EMV_3DS_VERSION")
    )
    return {
        "X-EMV-3DS-Enabled": "true",
        "X-EMV-3DS-Version": emv_version,
        "X-EMV-Merchant-Ref": merchant_ref,
        "X-EMV-Amount": amount,
        "X-EMV-Currency": currency,
        "X-Lucid-Clearnet-Via": "socks5",
        "X-Lucid-Origin": "MasterServer",
        "Content-Type": "application/json",
    }


def _payment_api_url() -> str:
    load_payments_secrets()
    url = (
        os.environ.get("PAYMENTS_CLEARNET_API_URL", "").strip()
        or get_proxy_secret("PAYMENTS_CLEARNET_API_URL")
        or os.environ.get("NOWPAYMENTS_API_URL", "").strip()
        or get_proxy_secret("NOWPAYMENTS_API_URL")
    )
    if not url:
        raise RuntimeError(
            "PAYMENTS_CLEARNET_API_URL not set in payments.secrets — "
            f"expected at {payments_secrets_path().as_posix()}"
        )
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Invalid PAYMENTS_CLEARNET_API_URL: {url}")
    return url


def _valid_processor_statuses() -> frozenset[str]:
    raw = get_proxy_secret("CLEARNET_VALID_PAYMENT_STATUSES")
    if not raw:
        raise RuntimeError(
            "CLEARNET_VALID_PAYMENT_STATUSES missing — must be set at time of operation"
        )
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def request_clearnet_payment(
    *,
    payment_payload: dict[str, Any],
    signature: str | None = None,
) -> dict[str, Any]:
    """
    Exit to clearnet over Tor SOCKS5 for payment processing.
    Returns only payment validity for MasterServer — never raw card data.
    """
    body = json.dumps(payment_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if signature is None:
        signature = sign_clearnet_payload(body)
    elif not verify_clearnet_signature(body, signature):
        return {
            "payment_status": "invalid",
            "reason": "hmac_rejected",
            "timestamp": utc_now(),
            "source": "Clearnet-package",
        }

    merchant_ref_keys = get_proxy_secret("CLEARNET_MERCHANT_REF_KEYS")
    if not merchant_ref_keys:
        raise RuntimeError(
            "CLEARNET_MERCHANT_REF_KEYS missing — must be set at time of operation"
        )
    merchant_ref = ""
    for key in (item.strip() for item in merchant_ref_keys.split(",") if item.strip()):
        if payment_payload.get(key):
            merchant_ref = str(payment_payload.get(key))
            break
    if not merchant_ref:
        merchant_ref = hashlib.sha256(body).hexdigest()[
            : int(require_proxy_secret("CLEARNET_MERCHANT_REF_HASH_LEN"))
        ]

    amount_keys = require_proxy_secret("CLEARNET_AMOUNT_KEYS")
    amount = ""
    for key in (item.strip() for item in amount_keys.split(",") if item.strip()):
        if key in payment_payload and payment_payload.get(key) is not None:
            amount = str(payment_payload.get(key))
            break
    if not amount:
        raise RuntimeError("payment amount missing from payload — check CLEARNET_AMOUNT_KEYS")

    currency = str(
        payment_payload.get("currency")
        or os.environ.get("PAYMENTS_CURRENCY", "").strip()
        or require_proxy_secret("PAYMENTS_CURRENCY")
    )

    headers = build_emv_3ds_headers(
        merchant_ref=merchant_ref,
        amount=amount,
        currency=currency,
    )
    headers["X-Lucid-HMAC-SHA256"] = signature
    api_key = (
        os.environ.get("PAYMENTS_API_KEY", "").strip()
        or get_proxy_secret("PAYMENTS_API_KEY")
        or os.environ.get("NOWPAYMENTS_API_KEY", "").strip()
        or get_proxy_secret("NOWPAYMENTS_API_KEY")
    )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key

    _install_socks5_opener()
    url = _payment_api_url()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    context = ssl.create_default_context()
    timeout = float(require_proxy_secret("CLEARNET_HTTP_TIMEOUT"))

    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            raw = response.read()
            status_code = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        status_code = exc.code
    except Exception as exc:  # network / socks failures
        load_proxy_secrets()
        return {
            "payment_status": "invalid",
            "reason": "clearnet_unreachable",
            "detail": str(exc),
            "timestamp": utc_now(),
            "source": "Clearnet-package",
            "lucid_tops_root": require_proxy_secret("LUCID_TOPS_ROOT"),
        }

    processor_ok = 200 <= int(status_code) < 300
    parsed_body: dict[str, Any] = {}
    if raw:
        try:
            loaded = json.loads(raw.decode("utf-8"))
            if isinstance(loaded, dict):
                parsed_body = loaded
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed_body = {}

    status_keys = require_proxy_secret("CLEARNET_STATUS_KEYS")
    processor_status = ""
    for key in (item.strip() for item in status_keys.split(",") if item.strip()):
        if parsed_body.get(key):
            processor_status = str(parsed_body.get(key)).lower()
            break
    if not processor_status:
        processor_status = "valid" if processor_ok else "invalid"

    is_valid = processor_ok and processor_status in _valid_processor_statuses()

    # Only validity result is returned to MasterServer.
    return {
        "payment_status": "valid" if is_valid else "invalid",
        "processor_http_status": int(status_code),
        "merchant_ref": merchant_ref,
        "timestamp": utc_now(),
        "source": "Clearnet-package",
        "emv_3ds": True,
        "via": "socks5",
    }


def transport_clearnet_request(
    *,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    signature: str | None = None,
) -> dict[str, Any]:
    """SOCKS5 clearnet transport helper for the transport container path."""
    body = b""
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if body:
        if signature is None:
            signature = sign_clearnet_payload(body)
        elif not verify_clearnet_signature(body, signature):
            return {
                "ok": False,
                "reason": "hmac_rejected",
                "timestamp": utc_now(),
            }

    _install_socks5_opener()
    headers = {
        "Content-Type": "application/json",
        "X-Lucid-Clearnet-Via": "socks5",
    }
    if signature:
        headers["X-Lucid-HMAC-SHA256"] = signature
    request = urllib.request.Request(
        url,
        data=body if body else None,
        headers=headers,
        method=method.upper(),
    )
    timeout = float(require_proxy_secret("CLEARNET_HTTP_TIMEOUT"))
    try:
        with urllib.request.urlopen(
            request, context=ssl.create_default_context(), timeout=timeout
        ) as response:
            raw = response.read()
            return {
                "ok": True,
                "status": getattr(response, "status", 200),
                "body": raw.decode("utf-8", errors="replace"),
                "timestamp": utc_now(),
            }
    except Exception as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "timestamp": utc_now(),
        }


if __name__ == "__main__":
    load_proxy_secrets()
    load_payments_secrets()
    print(
        {
            "payments_secrets": payments_secrets_path().as_posix(),
            "socks": _socks_endpoint(),
            "hmac_ready": bool(get_proxy_secret("CLEARNET_HMAC_KEY")),
        }
    )
