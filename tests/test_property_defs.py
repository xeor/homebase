from __future__ import annotations

from pathlib import Path

from homebase.config.property_defs import load_property_defs


def test_load_property_defs_token_keyed_map(tmp_path: Path) -> None:
    conf = tmp_path / ".base-conf.yaml"
    conf.write_text(
        """
properties:
  GIT:
    label: Git
    color: '#87afff'
    dir-exists: [.git]
  ACT:
    label: active
    color: '#ffb86c'
    cache_ttl_s: 3
    queries:
      - type: tmux_open_panes
""".strip()
    )
    defs = load_property_defs(tmp_path)
    by_key = {p.key: p for p in defs}
    assert "git" in by_key
    assert by_key["git"].token == "GIT"
    assert by_key["git"].color == "#87afff"
    assert "act" in by_key
    assert by_key["act"].queries
    assert by_key["act"].cache_ttl_s == 3


def test_load_property_defs_supports_variables(tmp_path: Path) -> None:
    conf = tmp_path / ".base-conf.yaml"
    conf.write_text(
        """
variables:
  _COLOR_DYN: '#ffb86c'
  _NOTES_ROOT: /tmp/notes
properties:
  ACT:
    label: '{{ _COLOR_DYN }} active'
    color: '{{ _COLOR_DYN }}'
    queries:
      - type: tmux_open_panes
  N:
    label: notes
    color: '{{ _COLOR_DYN }}'
    file-exists:
      - '{{ _NOTES_ROOT }}/{{ NAME_WITH_ARCHIVE_PREFIX }}.md'
""".strip()
    )
    defs = load_property_defs(tmp_path)
    by_key = {p.key: p for p in defs}
    assert by_key["act"].color == "#ffb86c"
    assert by_key["act"].label == "#ffb86c active"
    assert by_key["n"].file_exists == ("/tmp/notes/{{ NAME_WITH_ARCHIVE_PREFIX }}.md",)
