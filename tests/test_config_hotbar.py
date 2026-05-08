from __future__ import annotations

from homebase.config.prefs import load_custom_hotkeys, save_custom_hotkeys


def test_load_custom_hotkeys_supports_hotbar_without_hotkey(tmp_path) -> None:
    save_custom_hotkeys(
        tmp_path,
        [
            {"id": "hk1", "target": "action:archive", "hotbar": True},
        ],
    )
    loaded = load_custom_hotkeys(tmp_path)
    assert loaded == [{"id": "hk1", "target": "action:archive", "hotbar": True}]


def test_save_custom_hotkeys_drops_invalid_entries(tmp_path) -> None:
    save_custom_hotkeys(
        tmp_path,
        [
            {"id": "bad1", "target": "", "hotbar": True},
            {"id": "bad2", "target": "action:x"},
            {"id": "ok1", "target": "action:y", "hotkey": "f5"},
        ],
    )
    loaded = load_custom_hotkeys(tmp_path)
    assert loaded == [{"id": "ok1", "target": "action:y", "hotkey": "f5"}]


def test_save_custom_hotkeys_persists_optional_label(tmp_path) -> None:
    save_custom_hotkeys(
        tmp_path,
        [
            {
                "id": "hk1",
                "target": "action:archive",
                "hotbar": True,
                "label": "Archive now",
            },
        ],
    )
    loaded = load_custom_hotkeys(tmp_path)
    assert loaded == [
        {
            "id": "hk1",
            "target": "action:archive",
            "hotbar": True,
            "label": "Archive now",
        }
    ]
