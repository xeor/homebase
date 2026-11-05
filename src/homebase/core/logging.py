from __future__ import annotations

import os
import sys
from typing import Any

# loguru takes ~20 ms to import and only the -v/-vv/-vvv debug lines use
# it, so it is imported on the first line that is actually shown.
_SINK_LEVELS = {1: "INFO", 2: "DEBUG"}


def _verbose_level() -> int:
    try:
        return int(str(os.environ.get("HOMEBASE_VERBOSE", "0") or "0"))
    except ValueError:
        return 0


def _sink_level(level: int) -> str:
    if level >= 3:
        return "TRACE"
    return _SINK_LEVELS.get(level, "WARNING")


class _LazyLogger:
    def __init__(self) -> None:
        self._real: Any = None

    def _logger(self) -> Any:
        if self._real is None:
            from loguru import logger as real

            real.remove()
            real.add(sys.stderr, level=_sink_level(_verbose_level()))
            self._real = real
        return self._real

    def _log(self, min_verbose: int, method: str, *args: Any, **kwargs: Any) -> None:
        if _verbose_level() >= min_verbose:
            getattr(self._logger(), method)(*args, **kwargs)

    def trace(self, *args: Any, **kwargs: Any) -> None:
        self._log(3, "trace", *args, **kwargs)

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self._log(2, "debug", *args, **kwargs)

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._log(1, "info", *args, **kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._log(0, "warning", *args, **kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._log(0, "error", *args, **kwargs)

    def reconfigure(self) -> None:
        if self._real is not None:
            self._real.remove()
            self._real.add(sys.stderr, level=_sink_level(_verbose_level()))


logger = _LazyLogger()


def configure_logging(verbose: int) -> int:
    level = max(0, int(verbose))
    os.environ["HOMEBASE_VERBOSE"] = str(level)
    if level >= 3 and not os.environ.get("HOMEBASE_DEBUG", "").strip():
        os.environ["HOMEBASE_DEBUG"] = "1"
    logger.reconfigure()
    return level


def verbose_enabled(level: int = 1) -> bool:
    return _verbose_level() >= level


__all__ = ["configure_logging", "logger", "verbose_enabled"]
