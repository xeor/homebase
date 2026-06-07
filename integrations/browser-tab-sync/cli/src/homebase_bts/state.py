"""Local state (SQLite). group_id/window_id are hints, never permanent identity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    file_path  TEXT NOT NULL,
    browser    TEXT NOT NULL,
    strategy   TEXT NOT NULL,
    last_seen  TEXT,
    last_hash  TEXT
);
CREATE TABLE IF NOT EXISTS bindings (
    profile_id      TEXT NOT NULL,
    browser         TEXT NOT NULL,
    browser_profile TEXT,
    window_id       INTEGER,
    group_id        INTEGER,
    last_seen       TEXT,
    confidence      TEXT,
    PRIMARY KEY (profile_id, browser, browser_profile)
);
CREATE TABLE IF NOT EXISTS tabs (
    profile_id          TEXT NOT NULL,
    tab_id              TEXT NOT NULL,
    url                 TEXT NOT NULL,
    normalized_url      TEXT,
    last_browser_tab_id INTEGER,
    last_seen           TEXT,
    PRIMARY KEY (profile_id, tab_id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
