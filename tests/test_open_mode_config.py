from __future__ import annotations

from homebase.config import open_mode as open_mode_config


def test_load_open_mode_config_prefers_valid_profile() -> None:
    out = open_mode_config.load_open_mode_config(
        {"open_mode": {"profile": "tmux_tab", "tmux_session": "main"}},
        default_profile="shell_cd",
        known_profiles={"shell_cd", "tmux_tab"},
    )
    assert out == {"profile": "tmux_tab", "tmux_session": "main"}


def test_load_open_mode_config_supports_legacy_booleans() -> None:
    out = open_mode_config.load_open_mode_config(
        {
            "open_mode": {
                "use_tmux_tab": True,
                "run_tmux_load": True,
                "goto_existing_loaded": True,
            }
        },
        default_profile="shell_cd",
        known_profiles={"shell_cd", "tmux_tab_load_or_goto"},
    )
    assert out == {"profile": "tmux_tab_load_or_goto"}


def test_save_open_mode_config_falls_back_to_default() -> None:
    out = open_mode_config.save_open_mode_config(
        {},
        {"profile": "does-not-exist", "tmux_session": "main"},
        default_profile="shell_cd",
        known_profiles={"shell_cd", "tmux_tab"},
    )
    assert out["open_mode"] == {"profile": "shell_cd", "tmux_session": "main"}
