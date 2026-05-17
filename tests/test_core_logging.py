from __future__ import annotations

import os

from homebase.core.logging import configure_logging, verbose_enabled


def test_configure_logging_sets_verbose_env(monkeypatch) -> None:
    monkeypatch.delenv("HOMEBASE_VERBOSE", raising=False)
    configure_logging(2)
    assert verbose_enabled(2)
    assert not verbose_enabled(3)


def test_configure_logging_enables_homebase_debug_at_v3(monkeypatch) -> None:
    monkeypatch.delenv("HOMEBASE_DEBUG", raising=False)
    configure_logging(3)
    assert verbose_enabled(3)
    assert os.environ.get("HOMEBASE_DEBUG") == "1"
