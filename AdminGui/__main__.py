"""python -m AdminGui — launch the LucidTops AdminGui."""

from __future__ import annotations

from .admin_gui import run_gui


def main() -> int:
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
