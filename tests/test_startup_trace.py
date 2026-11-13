from __future__ import annotations

import time
from pathlib import Path

import pytest

from homebase.core import startup_trace
from homebase.core.constants import ENV_STARTUP_EPOCH, ENV_STARTUP_TRACE


def _parse(line: str) -> tuple[float, float, str]:
    """"    +  1.234s  (+0.500s)  label" -> (1.234, 0.5, "label")."""
    total, rest = line.strip().split("s  ", 1)
    delta, label = rest.split(")  ", 1)
    return float(total.lstrip("+")), float(delta.strip("(").rstrip("s")), label


@pytest.fixture(autouse=True)
def _clean_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_STARTUP_TRACE, raising=False)
    monkeypatch.delenv(ENV_STARTUP_EPOCH, raising=False)
    startup_trace.reset()
    yield
    startup_trace.reset()


def test_marks_are_not_written_until_enabled(tmp_path: Path) -> None:
    log = tmp_path / "trace.log"

    startup_trace.mark("before")
    assert not log.exists()

    startup_trace.enable(str(log))
    startup_trace.mark("after")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if line.startswith("---")) == 1
    assert [line.split("  ")[-1] for line in lines[1:]] == ["before", "after"]


def test_deltas_continue_across_writes(tmp_path: Path) -> None:
    log = tmp_path / "trace.log"
    startup_trace.enable(str(log))

    startup_trace.mark("one")
    time.sleep(0.05)
    startup_trace.mark("two")

    # Each mark is written on its own, so the second delta must be measured
    # from the first mark and not from the start of the run all over again.
    marks = [_parse(line) for line in log.read_text(encoding="utf-8").splitlines()[1:]]
    assert marks[1][1] == pytest.approx(marks[1][0] - marks[0][0], abs=0.01)


def test_environment_enables_tracing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "env-trace.log"
    monkeypatch.setenv(ENV_STARTUP_TRACE, str(log))

    startup_trace.mark("from env")

    assert "from env" in log.read_text(encoding="utf-8")


def test_launcher_epoch_is_the_zero_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "trace.log"
    monkeypatch.setenv(ENV_STARTUP_EPOCH, str(startup_trace._import_time - 5.0))
    startup_trace.enable(str(log))

    startup_trace.mark("python + imports")

    total, _, label = _parse(log.read_text(encoding="utf-8").splitlines()[1])
    assert label == "python + imports"
    assert total >= 5.0


def test_unusable_launcher_epoch_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "trace.log"
    # A value from the future (clock skew, a stale export) would make every
    # mark negative; the process start is used instead.
    monkeypatch.setenv(ENV_STARTUP_EPOCH, str(startup_trace._import_time + 600.0))
    startup_trace.enable(str(log))

    startup_trace.mark("python + imports")

    total, _, _ = _parse(log.read_text(encoding="utf-8").splitlines()[1])
    assert 0.0 <= total < 600.0


def test_unwritable_path_does_not_raise(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")

    startup_trace.enable(str(blocker / "sub" / "trace.log"))
    startup_trace.mark("still fine")
