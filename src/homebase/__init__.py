from __future__ import annotations

from .core.version import get_version


def __getattr__(name: str) -> str:
    # Resolved on first use: the package metadata lookup costs ~25 ms at
    # every start otherwise.
    if name == "__version__":
        return get_version()
    raise AttributeError(name)


__all__ = ["__version__"]
