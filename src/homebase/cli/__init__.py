from __future__ import annotations

import sys

# First homebase import of the process: it stamps the moment Python finished
# booting, which `--startup-trace` measures the rest of the start-up against.
from ..core import startup_trace

startup_trace.mark("python interpreter")

from .entry import main  # noqa: E402  (every module b needs loads here)


def entrypoint() -> int:
    return int(main(sys.argv[1:]))


__all__ = ["entrypoint", "main", "startup_trace"]
