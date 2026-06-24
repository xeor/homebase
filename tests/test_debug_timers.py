from __future__ import annotations

import json
from pathlib import Path

from homebase.core import debug_timers


def test_timed_step_is_noop_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(debug_timers, "enabled", False)

    with debug_timers.timed_step(tmp_path, "some.step") as info:
        info["ok"] = True

    assert not debug_timers.debug_timers_log_path(tmp_path).exists()


def test_timed_step_appends_jsonl_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(debug_timers, "enabled", True)

    with debug_timers.timed_step(tmp_path, "some.step", extra="x") as info:
        info["ok"] = True

    with debug_timers.timed_step(tmp_path, "other.step"):
        pass

    log_path = debug_timers.debug_timers_log_path(tmp_path)
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [record["label"] for record in records] == ["some.step", "other.step"]
    assert records[0]["extra"] == "x"
    assert records[0]["ok"] is True
    assert isinstance(records[0]["seconds"], float)


def test_record_timing_is_noop_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(debug_timers, "enabled", False)

    debug_timers.record_timing(tmp_path, "some.step", 0.1)

    assert not debug_timers.debug_timers_log_path(tmp_path).exists()
