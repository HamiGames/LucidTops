"""Associated pull_information script for the proxy container.

Content creation stays in Bootstrap. This module is the container entry
that calls Bootstrap.pull_information, then Bootstrap.main when run.
"""

from __future__ import annotations

from Bootstrap import main as bootstrap_main
from Bootstrap import pull_information as bootstrap_pull_information


def pull_information():
    return bootstrap_pull_information()


def main() -> int:
    pull_information()
    return bootstrap_main()


if __name__ == "__main__":
    raise SystemExit(main())
