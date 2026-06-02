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


def test_save_base_data_writes_blank_for_empty(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    metadata_store.save_base_data(
        target,
        {},
        is_packed_archive_path=lambda _p: False,
        packed_write_base_data=lambda _p, _d: None,
        base_marker_file=".base.yaml",
    )
    assert (target / ".base.yaml").read_text() == "\n"


def test_save_base_data_packed_delegates(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def packed_write(p: Path, data: dict[str, object]) -> None:
        captured["path"] = p
        captured["data"] = data

    metadata_store.save_base_data(
        tmp_path,
        {"x": 1},
        is_packed_archive_path=lambda _p: True,
        packed_write_base_data=packed_write,
        base_marker_file=".base.yaml",
    )
    assert captured["data"] == {"x": 1}


def test_load_base_data_packed_delegates(tmp_path: Path) -> None:
    def packed_read(p: Path) -> dict[str, object]:
        assert p == tmp_path
        return {"x": 1}

    out = metadata_store.load_base_data(
        tmp_path,
        is_packed_archive_path=lambda _p: True,
        packed_read_base_data=packed_read,
        base_marker_file=".base.yaml",
    )
    assert out == {"x": 1}


def test_load_base_data_returns_empty_for_invalid_yaml(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text(":\n  not valid: [")
    out = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert out == {}


def test_load_base_data_returns_empty_for_non_dict_yaml(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("[1, 2, 3]\n")
    out = metadata_store.load_base_data(
        target,
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert out == {}


def test_load_base_data_missing_marker_returns_empty(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    out = metadata_store.load_base_data(
        tmp_path / "nope",
        is_packed_archive_path=lambda _p: False,
        packed_read_base_data=lambda _p: {},
        base_marker_file=".base.yaml",
    )
    assert out == {}


def test_ensure_base_marker_creates_when_missing(tmp_path: Path) -> None:
    metadata_store.ensure_base_marker(
        tmp_path,
        is_packed_archive_path=lambda _p: False,
        base_marker_file=".base.yaml",
    )
    assert (tmp_path / ".base.yaml").is_file()


def test_ensure_base_marker_packed_noop(tmp_path: Path) -> None:
    metadata_store.ensure_base_marker(
        tmp_path,
        is_packed_archive_path=lambda _p: True,
        base_marker_file=".base.yaml",
    )
    assert not (tmp_path / ".base.yaml").exists()


def test_ensure_base_marker_preserves_existing(tmp_path: Path) -> None:
    (tmp_path / ".base.yaml").write_text("tags: [keep]\n")
    metadata_store.ensure_base_marker(
        tmp_path,
        is_packed_archive_path=lambda _p: False,
        base_marker_file=".base.yaml",
    )
    assert (tmp_path / ".base.yaml").read_text() == "tags: [keep]\n"


def test_repair_base_metadata_normalises_and_saves(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("tags: ['a']\n")

    saved: dict[str, object] = {}

    def normalize(raw: dict[str, object]) -> tuple[dict[str, object], list[str]]:
        return ({"tags": list(raw.get("tags", []))}, ["normalised"])

    def save(_p: Path, data: dict[str, object]) -> None:
        saved.update(data)

    log_calls: list[tuple[str, dict[str, object] | None]] = []

    def append_log(_p: Path, event: str, payload: dict[str, object] | None) -> None:
        log_calls.append((event, payload))

    ok, msg = metadata_store.repair_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=normalize,
        save_base_data_fn=save,
        append_base_log_fn=append_log,
    )
    assert ok is True
    assert "repaired" in msg
    assert saved.get("tags") == ["a"]
    assert log_calls and log_calls[0][0] == "meta_repaired"


def test_repair_base_metadata_recovers_from_invalid_yaml(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("not yaml: [")

    def normalize(_raw: dict[str, object]) -> tuple[dict[str, object], list[str]]:
        return ({}, [])

    ok, _msg = metadata_store.repair_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=normalize,
        save_base_data_fn=lambda _p, _d: None,
        append_base_log_fn=lambda _p, _e, _payload: None,
    )
    assert ok is True


def test_normalize_base_metadata_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    ok, msg = metadata_store.normalize_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=lambda raw: (raw, []),
        save_base_data_fn=lambda _p, _d: None,
        append_base_log_fn=lambda _p, _e, _payload: None,
    )
    assert ok is False
    assert "missing" in msg


def test_normalize_base_metadata_invalid_yaml(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text(":\n  bad: [")
    ok, msg = metadata_store.normalize_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=lambda raw: (raw, []),
        save_base_data_fn=lambda _p, _d: None,
        append_base_log_fn=lambda _p, _e, _payload: None,
    )
    assert ok is False
    assert "invalid yaml" in msg


def test_normalize_base_metadata_non_mapping_root(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("[1, 2]\n")
    ok, msg = metadata_store.normalize_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=lambda raw: (raw, []),
        save_base_data_fn=lambda _p, _d: None,
        append_base_log_fn=lambda _p, _e, _payload: None,
    )
    assert ok is False
    assert "mapping" in msg


def test_normalize_base_metadata_empty_yaml_becomes_empty_dict(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("")
    saved: dict[str, object] = {}
    ok, msg = metadata_store.normalize_base_metadata(
        target,
        base_marker_file=".base.yaml",
        normalize_base_data_fn=lambda raw: (raw, ["empty"]),
        save_base_data_fn=lambda _p, data: saved.update(data),
        append_base_log_fn=lambda _p, _e, _payload: None,
    )
    assert ok is True
    assert "normalized" in msg


def test_rename_legacy_base_yaml_renames_when_clear(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yml").write_text("tags: []\n")
    logged: list[tuple[str, dict[str, object] | None]] = []
    ok, msg = metadata_store.rename_legacy_base_yaml(
        target,
        legacy_base_marker_file=".base.yml",
        base_marker_file=".base.yaml",
        append_base_log_fn=lambda _p, event, payload: logged.append((event, payload)),
    )
    assert ok is True
    assert "renamed" in msg
    assert (target / ".base.yaml").is_file()
    assert not (target / ".base.yml").exists()
    assert logged[0][0] == "meta_renamed_ext"


def test_rename_legacy_base_yaml_blocked_when_target_exists(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yml").write_text("a")
    (target / ".base.yaml").write_text("b")
    ok, msg = metadata_store.rename_legacy_base_yaml(
        target,
        legacy_base_marker_file=".base.yml",
        base_marker_file=".base.yaml",
        append_base_log_fn=lambda *_a: None,
    )
    assert ok is False
    assert "already exists" in msg


def test_rename_legacy_base_yaml_missing_source(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    ok, msg = metadata_store.rename_legacy_base_yaml(
        target,
        legacy_base_marker_file=".base.yml",
        base_marker_file=".base.yaml",
        append_base_log_fn=lambda *_a: None,
    )
    assert ok is False
    assert "missing" in msg


def test_open_meta_for_review_missing_returns_false(tmp_path: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    ok, msg = metadata_store.open_meta_for_review(
        target,
        base_marker_file=".base.yaml",
        legacy_base_marker_file=".base.yml",
    )
    assert ok is False
    assert "not found" in msg


def test_open_meta_for_review_falls_back_to_legacy(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yml").write_text("legacy\n")

    spawned: list[list[str]] = []

    class FakePopen:
        def __init__(self, args: list[str]) -> None:
            spawned.append(args)

    monkeypatch.setattr(metadata_store.shutil, "which", lambda _name: "/usr/bin/open")
    monkeypatch.setattr(metadata_store.subprocess, "Popen", FakePopen)

    ok, msg = metadata_store.open_meta_for_review(
        target,
        base_marker_file=".base.yaml",
        legacy_base_marker_file=".base.yml",
    )
    assert ok is True
    assert ".base.yml" in msg
    assert spawned and spawned[0][0] == "open"


def test_open_meta_for_review_no_open_command_returns_message(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "p"
    target.mkdir()
    (target / ".base.yaml").write_text("yaml\n")

    monkeypatch.setattr(metadata_store.shutil, "which", lambda _name: None)

    ok, msg = metadata_store.open_meta_for_review(
        target,
        base_marker_file=".base.yaml",
        legacy_base_marker_file=".base.yml",
    )
    assert ok is False
    assert "open manually" in msg


def test_load_base_data_cache_eviction(tmp_path: Path) -> None:
    metadata_store._clear_base_data_cache()
    metadata_store._BASE_DATA_CACHE_MAX
    # Force the cache to fill so the eviction branch (line ~40) is exercised.
    saved_max = metadata_store._BASE_DATA_CACHE_MAX
    try:
        metadata_store._BASE_DATA_CACHE_MAX = 2
        for i in range(3):
            sub = tmp_path / f"p{i}"
            sub.mkdir()
            (sub / ".base.yaml").write_text(f"tags: [t{i}]\n")
            metadata_store.load_base_data(
                sub,
                is_packed_archive_path=lambda _p: False,
                packed_read_base_data=lambda _p: {},
                base_marker_file=".base.yaml",
            )
        # After processing 3 paths with cap=2 we should have ≤ 2 entries.
        assert len(metadata_store._BASE_DATA_CACHE) <= 2
    finally:
        metadata_store._BASE_DATA_CACHE_MAX = saved_max
        metadata_store._clear_base_data_cache()
