from __future__ import annotations

from homebase.config.prefs import load_table_date_color_ranges
from homebase.config.store import save_global_config_dict


def test_load_table_date_color_ranges_per_view_and_column(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_color_ranges": {
                    "all": {
                        "last_modified": {
                            "from_color": "#FFFFFF",
                            "to_color": "#555555",
                            "range_days": 365,
                        }
                    },
                    "active": {
                        "last_opened": {
                            "from_color": "#E8F7FF",
                            "to_color": "#5A6A72",
                            "range_days": 30,
                        }
                    },
                    "archive": {
                        "archived_at": {
                            "newer_color": "#FFF1D0",
                            "older_color": "#6B6252",
                            "range_days": 180,
                        }
                    },
                }
            }
        },
    )

    cfg = load_table_date_color_ranges(tmp_path)
    assert cfg["all"]["last_modified"] == {
        "from_color": "#FFFFFF",
        "to_color": "#555555",
        "range_days": 365.0,
    }
    assert cfg["active"]["last_opened"] == {
        "from_color": "#E8F7FF",
        "to_color": "#5A6A72",
        "range_days": 30.0,
    }
    assert cfg["archive"]["archived_at"] == {
        "from_color": "#FFF1D0",
        "to_color": "#6B6252",
        "range_days": 180.0,
    }


def test_load_table_date_color_ranges_skips_invalid_rules(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_color_ranges": {
                    "all": {
                        "last_modified": {
                            "from_color": "white",
                            "to_color": "#555555",
                            "range_days": 365,
                        },
                        "created": {
                            "from_color": "#FFFFFF",
                            "to_color": "#555555",
                            "range_days": "bad",
                        },
                    }
                }
            }
        },
    )

    cfg = load_table_date_color_ranges(tmp_path)
    assert cfg["all"] == {}
