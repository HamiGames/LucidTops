"""Associated pull_information script for the Rdp container.

Image build reads Master.secrets and proxy.secrets and writes
/app/Secrets/rdp.secrets. Runtime on a user console reads that file.
"""

from __future__ import annotations

from createRDP import main as create_main
from createRDP import pull_information as create_pull_information


def pull_information():
    return create_pull_information()


def main() -> int:
    return create_main()


if __name__ == "__main__":
    raise SystemExit(main())
