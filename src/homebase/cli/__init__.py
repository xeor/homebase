from __future__ import annotations

import sys

from .entry import main


def entrypoint() -> int:
    return int(main(sys.argv[1:]))


__all__ = ["entrypoint", "main"]
