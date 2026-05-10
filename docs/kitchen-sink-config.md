# Kitchen-Sink Config

This is a copy/paste-oriented, heavily commented example for
`<base>/.homebase/config.yaml`.

- Keep only the sections you need.
- Prefer this file over stale snippets.
- Validate with `uv run b help actions` and by starting `uv run b`.

```yaml
# homebase kitchen-sink config
# Path: <base>/.homebase/config.yaml

# Archive behavior and date interpretation.
archive:
  # IANA timezone used for archive date parsing/formatting.
  timezone: Europe/Oslo

# Saved and named filter expressions used by the query bar.
filters:
  saved:
    - "#wip"
    - "tags=0"
    - "last=@-7d"
  named:
    hot: "#cli OR #api"
    stale: "last<=@-60d"

# Dynamic property badges on project rows.
properties:
  GIT:
    label: Git repo
    key: git
    color: "#86b8ff"
    # Detector: project contains .git directory.
    dir-exists: [.git]

  EDT:
    label: editor active
    key: edt
    color: "#7dd3a7"
    # Cache this property for 8 seconds.
    cache_ttl_s: 8
    queries:
      # Detector: check tmux pane commands.
      - type: tmux_editor_commands
        commands: [code, code-insiders, codium, cursor, zed, nvim, vim]

  RECENT:
    label: opened recently in sqlite
    key: recent
    color: "#f4b183"
    queries:
      # Detector: inspect editor sqlite activity table.
      - type: sqlite_recent_paths
        db_path: "~/Library/Application Support/VSCodium/User/globalStorage/state.vscdb"
        table: ItemTable
        value_column: value
        where_like: "%file://%"

# Cache/reconcile strategy profile.
cache_profile:
  all:
    pri-2:
      update_interval_s: 10
      update_batch_size: 16
      # ttl|always|never depending on workflow.
      cache_mode: ttl
      cache_ttl_s: 30

# Quick-create templates for `b c <key>`.
create_templates:
  - key: tmp
    name: Quick tmp project
    options: [prefix-datetime, suffix-tmp, generate-ts-name]
    tags: [scratch]
  - key: feat
    name: feature worktree
    options: [prefix-datetime]
    tags: [feature]

# Default open behavior for UI open actions.
open_mode:
  profile: shell_cd

# Notes integration for built-in notes actions.
notes:
  # Variables are rendered through action/template engine.
  path_template: "{{ PROJECT_PATH }}/NOTES.md"
  open_command: "${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  create_command: "mkdir -p \"$(dirname {{ NOTE_PATH_Q }})\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}"

# Reconcile pacing settings.
reconcile:
  active:
    update_batch_size: 12
  archive:
    update_batch_size: 8

# Table behavior knobs.
table_behavior:
  pin_wip_top: false
  side_width_pct: 33

# Optional explicit column layout overrides.
table_columns:
  active:
    - id: name
      width: 28
      enabled: true
    - id: description
      width: 40
      enabled: true

# Optional suffix menu and file-view excludes.
suffixes: [tmp, fork, old]
file_view_exclude_patterns:
  - "*.min.js"
  - "node_modules/**"
  - ".git/**"

# Action registry.
# - Built-ins can override only label/confirm.
# - Custom actions require kind and kind-specific fields.
actions:
  # Built-in override.
  archive: { label: Archive }
  delete:
    label: Delete forever
    confirm: "Drop {{ count }} project(s) under {{ base_dir }}?"

  # Custom shell action, one dispatch with list variables.
  open_item_in_editor:
    kind: shell
    scope: target
    multi: joined
    command: "$EDITOR {{ paths_q }}"

  # Custom shell action, one dispatch per selected row.
  open_in_daisydisk:
    kind: shell
    scope: target
    multi: per_row
    command: "open -n -a DaisyDisk {{ path_q }}"

  # Workspace-scoped shell action.
  open_base_in_editor:
    kind: shell
    scope: workspace
    command: "$EDITOR {{ base_dir_q }}"

  # filepicker: list command -> choose one -> final command with selection vars.
  pick_markdown:
    kind: filepicker
    scope: target
    list: "find {{ path_q }} -type f -name '*.md'"
    command: "codium {{ selection_q }}"

  # note op: currently only add_log is supported.
  add_log_to_note:
    kind: note
    scope: target
    op: add_log

# Target-scope actions shown in hotbar.
hotbar:
  - open_selected
  - notes_create
  - { action: add_log_to_note, label: Log }

# Key chords mapped to actions.
keys:
  "f5": open_item_in_editor
  "ctrl+alt+r": refresh_cache
  "ctrl+l": tab.info.events

# New-project defaults for the interactive create flow.
new_project:
  name_options: []
  template: null
  post_commands: []
  tags: []
  after_create: open

# Persisted UI state.
state:
  view: active
  sort: last
  side_main: selected
  side_selected: overview
  side_info: events
  side_settings: table
```
