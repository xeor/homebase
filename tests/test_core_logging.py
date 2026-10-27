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


def test_logger_skips_loguru_for_hidden_lines(monkeypatch) -> None:
    from homebase.core import logging as core_logging

    lazy = core_logging._LazyLogger()
    monkeypatch.setenv("HOMEBASE_VERBOSE", "0")
    lazy.debug("hidden {}", 1)
    lazy.info("hidden")
    lazy.trace("hidden")
    assert lazy._real is None


def test_logger_writes_shown_lines_to_stderr(monkeypatch, capsys) -> None:
    from homebase.core import logging as core_logging

    lazy = core_logging._LazyLogger()
    monkeypatch.setenv("HOMEBASE_VERBOSE", "2")
    lazy.debug("shown {}", 42)
    lazy.trace("still hidden")
    assert lazy._real is not None
    err = capsys.readouterr().err
    assert "shown 42" in err
    assert "still hidden" not in err
    lazy.reconfigure()
    lazy._real.remove()


def test_sink_levels() -> None:
    from homebase.core import logging as core_logging

    assert [core_logging._sink_level(n) for n in (0, 1, 2, 3, 5)] == [
        "WARNING", "INFO", "DEBUG", "TRACE", "TRACE",
    ]


def test_verbose_level_ignores_garbage(monkeypatch) -> None:
    monkeypatch.setenv("HOMEBASE_VERBOSE", "lots")
    assert verbose_enabled(1) is False
