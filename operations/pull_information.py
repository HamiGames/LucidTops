"""Associated pull_information script for the operations container.

At image build, /app/secrets/operations.secrets is copied from
Server/Secrets/operations.secrets when that console file was placed in the
build context. Otherwise it is built from Master.secrets, proxy.secrets,
and torrc.
"""

from __future__ import annotations

import sys
from pathlib import Path

IN_IMAGE = Path("/app/secrets/operations.secrets")
CONSOLE_COPY = Path("/tmp/ops-secrets-src/operations.secrets")


def pull_information():
    from ops_pull_information import pull_operations_hardware

    return pull_operations_hardware(bind_environ=True, overwrite=True)


def write_in_image_secrets() -> Path:
    """Create /app/secrets/operations.secrets during image build from console secrets."""
    from operations_secrets import write_operations_secrets_at_build

    source = Path("/tmp/ops-secrets-src")
    return write_operations_secrets_at_build(
        master_secrets=source / "Master.secrets",
        proxy_secrets=source / "proxy.secrets",
        torrc=source / "torrc",
        databases_secrets=source / "databases.secrets",
        mongodb_secrets=source / "mongodb.secrets",
        server_secrets=source / "server.secrets",
        operations_secrets=source / "operations.secrets",
    )


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--write-image" in args:
        path = write_in_image_secrets()
        print(path.as_posix())
        return 0
    from ops_pull_information import main as ops_main

    return ops_main()


if __name__ == "__main__":
    raise SystemExit(main())
