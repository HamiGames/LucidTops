"""Associated pull_information script for the sessions container.

Delegates to sessions_pull_information. Secrets are written on the Pi
console under /mnt/myssd/LucidTops/Server/Secrets.
"""

from __future__ import annotations


def pull_information():
    from sessions_pull_information import pull_sessions_hardware

    return pull_sessions_hardware(bind_environ=True, overwrite=True)


def main() -> int:
    from sessions_pull_information import main as sessions_main

    return sessions_main()


if __name__ == "__main__":
    raise SystemExit(main())
