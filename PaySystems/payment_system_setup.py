#!/usr/bin/env python3
""" this script will create a new tron node and wallet address for the payment system
all actions to be performed automatically and without user interaction via the Linux command line.
using the information found at: https://github.com/tronprotocol/wallet-cli
the address will be kept in the server container and not exposed to the public
the address will be used to receive payments for the payment system
the address will be used to send payments for the payment system
the address will be used to receive payments for the payment system

a second wallet address will be created using an annoimous wallet address provider, that doesn't require any personal information to be provided
this will be the alternative payment address for the payment system

all wallet addresses will be accessible using TOR
all wallet addresses will be accessible using the API routes for the payment system
none of the wallet addresses will be exposed to the public

all secrets for the address are to be written to a accounts.txt file located at /mnt/myssd/accounts.txt (linux command line only)
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PAYSYSTEMS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PAYSYSTEMS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from configPay import LUCID_TOPS_ROOT, get_payment_db, utc_now 

DEFAULT_ACCOUNTS_PATH = Path("/mnt/myssd/accounts.txt")
DEFAULT_PAYMENTS_SECRETS_NAME = "payments.secrets"
PAYMENT_WALLETS_COLLECTION = "payment_wallets"
WALLET_CLI_REPO = "https://github.com/tronprotocol/wallet-cli"
TRON_NETWORK = os.environ.get("TRON_NETWORK", "tron:mainnet")
WALLET_CLI_BIN = os.environ.get("WALLET_CLI_BIN", "wallet-cli")


@dataclass
class TronWallet:
    wallet_type: str
    label: str
    address: str
    private_key: str
    wallet_password: str
    source: str
    keystore_path: str | None = None
    network: str = TRON_NETWORK
    tor_only: bool = True
    public_exposed: bool = False

    def as_public_record(self) -> dict[str, Any]:
        return {
            "wallet_type": self.wallet_type,
            "label": self.label,
            "address": self.address,
            "source": self.source,
            "network": self.network,
            "tor_only": self.tor_only,
            "public_exposed": self.public_exposed,
            "keystore_path": self.keystore_path,
            "updated_at": utc_now(),
        }


def _keccak256(data: bytes) -> bytes:
    """Keccak-256 digest (TRON/Ethereum address derivation)."""
    state = [0] * 1600
    rate = 136
    mask = (1 << 64) - 1

    def rotl(value: int, shift: int) -> int:
        return ((value << shift) | (value >> (64 - shift))) & mask

    rc = [
        0x0000000000000001,
        0x0000000000008082,
        0x800000000000808A,
        0x8000000080008000,
        0x000000000000808B,
        0x0000000080000001,
        0x8000000080008081,
        0x8000000000008009,
        0x000000000000008A,
        0x0000000000000088,
        0x0000000080008009,
        0x000000008000000A,
        0x000000008000808B,
        0x800000000000008B,
        0x8000000000008089,
        0x8000000000008003,
        0x8000000000008002,
        0x8000000000000080,
        0x000000000000800A,
        0x800000008000000A,
        0x8000000080008081,
        0x8000000000008080,
        0x0000000080000001,
        0x8000000080008008,
    ]

    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)

    for offset in range(0, len(padded), rate):
        block = padded[offset : offset + rate]
        for i in range(len(block) // 8):
            state[i] ^= int.from_bytes(block[i * 8 : (i + 1) * 8], "little")

        for round_index in range(24):
            c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
            d = [c[(x - 1) % 5] ^ rotl(c[(x + 1) % 5], 1) for x in range(5)]
            for x in range(25):
                state[x] ^= d[x % 5]
            b = state[:]
            for x in range(25):
                state[x] = rotl(b[((x % 5) * 5) + ((x // 5 + [0, 1, 2, 3, 4][x % 5]) % 5)], [0, 1, 62, 28, 27][x % 5])
            for x in range(0, 25, 5):
                t = state[x]
                for y in range(4):
                    state[x + y] ^= (~state[x + ((y + 1) % 5)] & state[x + ((y + 2) % 5)])
                state[x + 4] ^= t
            state[0] ^= rc[round_index]

    output = bytearray()
    for lane in range(4):
        output.extend(int.to_bytes(state[lane], 8, "little"))
    return bytes(output[:32])


_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _encode_sec1_ec_private_key(private_key: bytes) -> bytes:
    return b"\x30\x2e\x02\x01\x01\x04\x20" + private_key + b"\xa0\x07\x06\x05\x2b\x81\x04\x00\x0a"


def _private_key_to_public_key(private_key: bytes) -> bytes:
    import tempfile

    der = _encode_sec1_ec_private_key(private_key)
    with tempfile.TemporaryDirectory() as tmp:
        der_path = Path(tmp) / "key.der"
        pub_path = Path(tmp) / "pub.der"
        der_path.write_bytes(der)
        completed = subprocess.run(
            [
                "openssl",
                "ec",
                "-inform",
                "DER",
                "-in",
                str(der_path),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(pub_path),
            ],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("openssl ec failed to derive TRON public key")
        pub_der = pub_path.read_bytes()
    if len(pub_der) < 65:
        raise RuntimeError("unexpected openssl public key output")
    uncompressed = pub_der[-65:]
    if uncompressed[0] != 0x04:
        raise RuntimeError("expected uncompressed secp256k1 public key")
    return uncompressed[1:]


def _base58check_encode_tron(payload: bytes) -> str:
    import hashlib

    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    data = payload + checksum
    num = int.from_bytes(data, "big")
    encoded = bytearray()
    while num > 0:
        num, remainder = divmod(num, 58)
        encoded.append(_BASE58_ALPHABET[remainder])
    prefix_zeros = len(data) - len(data.lstrip(b"\x00"))
    return (_BASE58_ALPHABET[0:1] * prefix_zeros + encoded[::-1]).decode("ascii")


def _tron_address_from_private_key_hex(private_key_hex: str) -> str:
    private_key = bytes.fromhex(private_key_hex)
    public_key = _private_key_to_public_key(private_key)
    address_bytes = b"\x41" + _keccak256(public_key)[12:32]
    return _base58check_encode_tron(address_bytes)


def _generate_tron_wallet_local(*, wallet_type: str, label: str, source: str) -> TronWallet:
    private_key_hex = secrets.token_hex(32)
    wallet_password = secrets.token_urlsafe(24)
    address = _tron_address_from_private_key_hex(private_key_hex)
    return TronWallet(
        wallet_type=wallet_type,
        label=label,
        address=address,
        private_key=private_key_hex,
        wallet_password=wallet_password,
        source=source,
        keystore_path=None,
    )


def _wallet_cli_available() -> str | None:
    path = shutil.which(WALLET_CLI_BIN)
    return path


def _create_wallet_via_wallet_cli(*, wallet_type: str, label: str) -> TronWallet | None:
    cli = _wallet_cli_available()
    if cli is None:
        return None

    wallet_password = secrets.token_urlsafe(24)
    command = [cli, "create", "--label", label, "--network", TRON_NETWORK, "-o", "json"]
    try:
        completed = subprocess.run(
            command,
            input=f"{wallet_password}\n{wallet_password}\n",
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    payload: dict[str, Any] | None = None
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payload = parsed
            break

    if payload is None:
        return None

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    address = str(data.get("address") or data.get("base58Address") or "").strip()
    private_key = str(data.get("privateKey") or data.get("private_key") or "").strip()
    keystore_path = str(data.get("keystorePath") or data.get("keystore_path") or "").strip() or None
    if not address or not private_key:
        return None

    return TronWallet(
        wallet_type=wallet_type,
        label=label,
        address=address,
        private_key=private_key,
        wallet_password=wallet_password,
        source=f"wallet-cli ({WALLET_CLI_REPO})",
        keystore_path=keystore_path,
    )


def _create_tron_primary_wallet() -> TronWallet:
    wallet = _create_wallet_via_wallet_cli(wallet_type="tron_primary", label="lucid-tron-primary")
    if wallet is not None:
        return wallet
    return _generate_tron_wallet_local(
        wallet_type="tron_primary",
        label="lucid-tron-primary",
        source="local_tron_generator (wallet-cli unavailable)",
    )


def _create_anonymous_alt_wallet() -> TronWallet:
    wallet = _create_wallet_via_wallet_cli(wallet_type="anonymous_alt", label="lucid-anonymous-alt")
    if wallet is not None:
        return wallet
    return _generate_tron_wallet_local(
        wallet_type="anonymous_alt",
        label="lucid-anonymous-alt",
        source="local_anonymous_generator (no personal information required)",
    )


def _write_accounts_file(path: Path, wallets: list[TronWallet]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LucidTops payment wallet accounts - store securely",
        f"# Generated: {utc_now()}",
        f"# wallet-cli reference: {WALLET_CLI_REPO}",
        "# Linux host path — not exposed to the public internet",
        "",
    ]
    for index, wallet in enumerate(wallets, start=1):
        lines.extend(
            [
                f"[Account {index}]",
                f"wallet_type={wallet.wallet_type}",
                f"label={wallet.label}",
                f"address={wallet.address}",
                f"private_key={wallet.private_key}",
                f"wallet_password={wallet.wallet_password}",
                f"source={wallet.source}",
                f"network={wallet.network}",
                f"tor_only={str(wallet.tor_only).lower()}",
                f"public_exposed={str(wallet.public_exposed).lower()}",
            ]
        )
        if wallet.keystore_path:
            lines.append(f"keystore_path={wallet.keystore_path}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def _write_payments_secrets(secrets_dir: Path, wallets: list[TronWallet]) -> Path:
    secrets_dir.mkdir(parents=True, exist_ok=True)
    path = secrets_dir / DEFAULT_PAYMENTS_SECRETS_NAME
    primary = next(w for w in wallets if w.wallet_type == "tron_primary")
    alternate = next(w for w in wallets if w.wallet_type == "anonymous_alt")
    lines = [
        "# LucidTops payments.secrets - loaded by Connect_wallet.py",
        f"# Generated: {utc_now()}",
        "# Tor-only payment wallet registry (not public clearnet)",
        "",
        "PAYMENT_WALLET_ACCESS=tor-only",
        "PAYMENT_API_SCOPE=PaymentRoutes.py",
        f"WALLET_CLI_SOURCE={WALLET_CLI_REPO}",
        f"TRON_NETWORK={TRON_NETWORK}",
        "",
        f"TRON_PRIMARY_ADDRESS={primary.address}",
        f"TRON_PRIMARY_PRIVATE_KEY={primary.private_key}",
        f"TRON_PRIMARY_WALLET_PASSWORD={primary.wallet_password}",
        "",
        f"TRON_ALT_ADDRESS={alternate.address}",
        f"TRON_ALT_PRIVATE_KEY={alternate.private_key}",
        f"TRON_ALT_WALLET_PASSWORD={alternate.wallet_password}",
        "",
        "PUBLIC_EXPOSED=false",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def _persist_wallets_to_database(wallets: list[TronWallet]) -> bool:
    try:
        from configPay import _get_mongo_client_for_launch
    except ImportError:
        return False

    client = _get_mongo_client_for_launch(
        {
            "mongodb_host": os.environ.get("MONGODB_HOST", "lucid-mongodb"),
            "mongodb_port": int(os.environ.get("MONGODB_PORT", "27017")),
        }
    )
    if client is None:
        return False

    try:
        db = get_payment_db(client)
        for wallet in wallets:
            db[PAYMENT_WALLETS_COLLECTION].update_one(
                {"wallet_type": wallet.wallet_type},
                {
                    "$set": wallet.as_public_record(),
                    "$setOnInsert": {
                        "wallet_id": secrets.token_hex(8),
                        "created_at": utc_now(),
                    },
                },
                upsert=True,
            )
        return True
    finally:
        client.close()


def setup_payment_system(
    *,
    accounts_path: Path | None = None,
    secrets_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create TRON payment wallets, write secrets, and register Tor-only wallet metadata."""
    accounts_file = accounts_path or Path(
        os.environ.get("PAYMENT_ACCOUNTS_FILE", DEFAULT_ACCOUNTS_PATH.as_posix())
    )
    payments_secrets_dir = secrets_dir or Path(
        os.environ.get("SECRETS_DIR", LUCID_TOPS_ROOT / "secrets")
    )

    if accounts_file.exists() and not force:
        return {
            "skipped": True,
            "reason": "accounts file already exists; use --force to regenerate",
            "accounts_file": accounts_file.as_posix(),
        }

    primary = _create_tron_primary_wallet()
    alternate = _create_anonymous_alt_wallet()
    wallets = [primary, alternate]

    accounts_written = _write_accounts_file(accounts_file, wallets)
    payments_secrets_written = _write_payments_secrets(payments_secrets_dir, wallets)
    database_saved = _persist_wallets_to_database(wallets)

    return {
        "skipped": False,
        "accounts_file": accounts_written.as_posix(),
        "payments_secrets": payments_secrets_written.as_posix(),
        "wallet_cli_used": _wallet_cli_available() is not None,
        "wallets": [
            {
                "wallet_type": wallet.wallet_type,
                "label": wallet.label,
                "address": wallet.address,
                "source": wallet.source,
                "tor_only": wallet.tor_only,
                "public_exposed": wallet.public_exposed,
            }
            for wallet in wallets
        ],
        "database_saved": database_saved,
        "setup_complete": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops payment system wallet setup")
    parser.add_argument(
        "--accounts-file",
        help=f"Accounts secrets file (default: {DEFAULT_ACCOUNTS_PATH.as_posix()})",
    )
    parser.add_argument(
        "--secrets-dir",
        help="Directory for payments.secrets (default: LUCID_TOPS_ROOT/secrets)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate wallets even if accounts file already exists",
    )
    args = parser.parse_args()

    accounts_path = Path(args.accounts_file) if args.accounts_file else None
    secrets_dir = Path(args.secrets_dir) if args.secrets_dir else None

    print(f"payment_system_setup: wallet-cli repo={WALLET_CLI_REPO}")
    result = setup_payment_system(
        accounts_path=accounts_path,
        secrets_dir=secrets_dir,
        force=args.force,
    )
    print("LucidTops payment system setup complete.")
    for key, value in result.items():
        if key == "wallets":
            print("  wallets:")
            for wallet in value:
                print(f"    - {wallet}")
        else:
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
