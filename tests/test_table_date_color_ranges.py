from __future__ import annotations

from homebase.config.prefs import load_table_date_column_styles
from homebase.config.store import save_global_config_dict


def test_load_table_date_color_ranges_per_view_and_column(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_columns": {
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

    cfg = load_table_date_column_styles(tmp_path)
    assert cfg["all"]["last_modified"] == {
        "stops": [
            {"days": 0.0, "color": "#FFFFFF"},
            {"days": 365.0, "color": "#555555"},
        ]
    }
    assert cfg["active"]["last_opened"] == {
        "stops": [
            {"days": 0.0, "color": "#E8F7FF"},
            {"days": 30.0, "color": "#5A6A72"},
        ]
    }
    assert cfg["archive"]["archived_at"] == {
        "stops": [
            {"days": 0.0, "color": "#FFF1D0"},
            {"days": 180.0, "color": "#6B6252"},
        ]
    }


def test_load_table_date_color_ranges_skips_invalid_rules(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_columns": {
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

    cfg = load_table_date_column_styles(tmp_path)
    assert cfg["all"] == {}


def test_load_table_date_color_ranges_scale_map(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_columns": {
                    "active": {
                        "last_opened": {
                            "scale": {
                                0: "#0000FF",
                                100: "#00FF00",
                                300: "#FFFF00",
                            }
                        }
                    }
                }
            }
        },
    )

    cfg = load_table_date_column_styles(tmp_path)
    assert cfg["active"]["last_opened"] == {
        "stops": [
            {"days": 0.0, "color": "#0000FF"},
            {"days": 100.0, "color": "#00FF00"},
            {"days": 300.0, "color": "#FFFF00"},
        ]
    }


def test_load_table_date_color_ranges_numeric_map_direct(tmp_path) -> None:
    save_global_config_dict(
        tmp_path,
        {
            "table": {
                "date_columns": {
                    "active": {
                        "last_modified": {
                            0: "#1F77FF",
                            100: "#38C172",
                            300: "#FFD43B",
                        }
                    }
                }
            }
        },
    )

    cfg = load_table_date_column_styles(tmp_path)
    assert cfg["active"]["last_modified"] == {
        "stops": [
            {"days": 0.0, "color": "#1F77FF"},
            {"days": 100.0, "color": "#38C172"},
            {"days": 300.0, "color": "#FFD43B"},
        ]
    }
