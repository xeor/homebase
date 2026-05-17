from __future__ import annotations

import os
import sys

from loguru import logger


def configure_logging(verbose: int) -> int:
    level = max(0, int(verbose))
    os.environ["HOMEBASE_VERBOSE"] = str(level)
    if level >= 3 and not os.environ.get("HOMEBASE_DEBUG", "").strip():
        os.environ["HOMEBASE_DEBUG"] = "1"
    logger.remove()
    sink_level = "WARNING"
    if level == 1:
        sink_level = "INFO"
    elif level == 2:
        sink_level = "DEBUG"
    elif level >= 3:
        sink_level = "TRACE"
    logger.add(sys.stderr, level=sink_level)
    return level


def verbose_enabled(level: int = 1) -> bool:
    try:
        current = int(str(os.environ.get("HOMEBASE_VERBOSE", "0") or "0"))
    except ValueError:
        return False
    return current >= level


__all__ = ["configure_logging", "logger", "verbose_enabled"]
