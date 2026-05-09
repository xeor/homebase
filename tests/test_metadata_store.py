from __future__ import annotations

from pathlib import Path

from homebase.metadata import store as metadata_store


def test_save_and_load_base_data_roundtrip(tmp_path: Path) -> None:
    metadata_store.save_base_data(
        tmp_path,
        {"tags": ["x"]},
        is_packed_archive_path=lambda _p: False,
        packed_write_base_data=lambda _p, _d: None,
        base_marker_file=".base.yaml",
    )
    loaded = metadata_store.load_base_data(
        tmp_path,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert loaded.get("tags") == ["x"]


def test_load_base_data_caches_until_mtime_changes(tmp_path: Path, monkeypatch) -> None:
    metadata_store._clear_base_data_cache()

    target = tmp_path / "p"
    target.mkdir()
    metadata_store.save_base_data(
        target,
        {"tags": ["a"]},
        is_packed_archive_path=lambda _p: False,
        packed_write_base_data=lambda _p, _d: None,
        base_marker_file=".base.yaml",
    )

    parses = {"count": 0}
    real_safe_load = metadata_store.yaml.safe_load

    def counting_safe_load(text: str) -> object:
        parses["count"] += 1
        return real_safe_load(text)

    monkeypatch.setattr(metadata_store.yaml, "safe_load", counting_safe_load)

    loaded_a = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    loaded_b = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert loaded_a == {"tags": ["a"]}
    assert loaded_b == {"tags": ["a"]}
    assert parses["count"] == 1
    assert loaded_a is not loaded_b

    metadata_store.save_base_data(
        target,
        {"tags": ["b"]},
        is_packed_archive_path=lambda _p: False,
        packed_write_base_data=lambda _p, _d: None,
        base_marker_file=".base.yaml",
    )
    loaded_c = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert loaded_c == {"tags": ["b"]}
    assert parses["count"] == 2


def test_load_base_data_returns_independent_copy(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    target = tmp_path / "p2"
    target.mkdir()
    metadata_store.save_base_data(
        target,
        {"tags": ["x"], "log": {"events": [{"_event": "first"}]}},
        is_packed_archive_path=lambda _p: False,
        packed_write_base_data=lambda _p, _d: None,
        base_marker_file=".base.yaml",
    )
    first = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    first["tags"].append("mutated")
    first["log"]["events"].append({"_event": "second"})

    second = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert second["tags"] == ["x"]
    assert second["log"]["events"] == [{"_event": "first"}]


def test_append_base_log_keeps_reserved_keys(tmp_path: Path) -> None:
    state: dict[str, object] = {}

    def load(_path: Path) -> dict[str, object]:
        return dict(state) if isinstance(state, dict) else {}

    def save(_path: Path, data: dict[str, object]) -> None:
        state.clear()
        state.update(data)

    metadata_store.append_base_log(
        tmp_path,
        "evt",
        {"_event": "bad", "ok": 1},
        ensure_base_marker_fn=lambda _path: None,
        load_base_data_fn=load,
        save_base_data_fn=save,
        now_iso=lambda: "2025-01-01T00:00:00+00:00",
    )
    events = state.get("log", {}).get("events", [])  # type: ignore[union-attr]
    assert isinstance(events, list)
    assert events[-1]["_event"] == "evt"
    assert events[-1]["ok"] == 1
