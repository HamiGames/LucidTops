"""python -m useronly — launch the LucidTops UsersOnly GUI."""

from __future__ import annotations

from .user_gui import run_gui


def main() -> int:
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
