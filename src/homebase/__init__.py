from __future__ import annotations

__version__ = "0.1.0"


def entrypoint() -> int:
    """Console-script entry point. Mirrored from `homebase.cli:entrypoint`."""
    from .cli import entrypoint as _entry

    return _entry()


__all__ = ["__version__", "entrypoint"]
