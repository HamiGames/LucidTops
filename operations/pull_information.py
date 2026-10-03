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
    """Create /app/secrets/operations.secrets during image build."""
    if CONSOLE_COPY.is_file() and CONSOLE_COPY.stat().st_size > 0:
        IN_IMAGE.parent.mkdir(parents=True, exist_ok=True)
        IN_IMAGE.write_text(CONSOLE_COPY.read_text(encoding="utf-8"), encoding="utf-8")
        if IN_IMAGE.stat().st_size == 0:
            raise RuntimeError(
                f"operations.secrets was not written at {IN_IMAGE.as_posix()}"
            )
        return IN_IMAGE
    from operations_secrets import write_operations_secrets_at_build

    return write_operations_secrets_at_build(
        master_secrets=Path("/tmp/ops-secrets-src/Master.secrets"),
        proxy_secrets=Path("/tmp/ops-secrets-src/proxy.secrets"),
        torrc=Path("/tmp/ops-secrets-src/torrc"),
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
