from __future__ import annotations

from ..core import startup_trace
from .app import run_textual_ui
from .context import UIContext, build_ui_context

# textual, rich and the whole widget tree are loaded by the import above: the
# single most expensive part of starting b.
startup_trace.mark("imports: ui (textual)")

__all__ = ["UIContext", "build_ui_context", "run_textual_ui"]
