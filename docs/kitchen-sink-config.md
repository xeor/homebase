# Kitchen-Sink Config

This is a copy/paste-oriented, heavily commented example for
`<base>/.homebase/config.yaml`.

- Keep only the sections you need.
- Prefer this file over stale snippets.
- Validate with `uv run b help actions` and by starting `uv run b`.
- Hotbar `style.when` reuses the same query language as the query bar.
- Hotbar styles are evaluated per hotbar item against the selected row.

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

# `b new` defaults and child sources.
# - top-level keys under each source are **options** (CLI-overridable).
# - `config:` sub-block holds structural settings (not CLI-overridable).
# - Built-in source keys: empty, local, git, download, downloaded.
# - Unknown keys must declare `parent: <key>` (built-in or child).
new:
  sources:
    # Built-in: override defaults for plain `b new myproj`.
    empty:
      cd: true                  # spawn shell on success
    local:
      cd: true

    git:
      cd: true
      config:
        # Host → forge-type. Forge types match the registered URL
        # adapters: github, gitlab, bitbucket, gitea, codeberg,
        # sourcehut. Self-hosted gitea/forgejo etc. must be declared
        # here; b cannot sniff the forge from a bare URL.
        hosts:
          git.example.com:    gitlab
          code.example.org:   gitea
          # subpath routing: longest-prefix match wins
          git.example.com/scm: bitbucket

    download:
      config:
        # Regex fallback for non-forge URLs (internal wikis, CMS, ...).
        # Forge adapters take precedence; this only fires when no
        # adapter matched.
        url_rewrites:
          - match: "^https://internal\\.example\\.com/wiki/(.+)$"
            rewrite: "https://internal.example.com/wiki/raw/\\1"

    downloaded:
      # Defaults to {tmp, timestamp, open, confirm} via the Source.
      config:
        folder: ~/Downloads

    # ---------------- child sources (`b new --as <key>`) ----------------

    # Reproduces today's `b c tmp` template: ts-based name + .tmp suffix.
    tmp:
      parent: empty
      timestamp: true           # YYYY-DD-MM_ folder-name prefix
      tmp: true                 # .tmp folder-name suffix
      ts-name: true             # use YYYYMMDD-HHMMSS as the name
      tags: [scratch]

    # Reproduces today's `b c feat`: ts prefix + feature tag.
    feat:
      parent: empty
      timestamp: true
      tags: [feature]

    # Pure-empty child with a project tag set.
    work:
      parent: empty
      tags: [work]

    # Git child that always uses --tmp (drafting a repo).
    git-tmp:
      parent: git
      tmp: true
      tags: [scratch]

    # Empty child wired to a copier template under <base>/.copier/python-uv.
    py:
      parent: empty
      template: python-uv
      tags: [python]
      cd: true

# Default open behavior for UI open actions.
open_mode:
  profile: shell_cd

# Notes integration for built-in notes actions.
notes:
  # Variables are rendered through action/template engine.
  # For archived rows, NAME_WITH_ARCHIVE_PREFIX resolves to
  # _archive/YYYY-MM-DD_<project-name> (filesystem-safe, no colon).
  path_template: "{{ PROJECT_PATH }}/NOTES.md"
  open_command: "${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  create_command: "mkdir -p \"$(dirname {{ NOTE_PATH_Q }})\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  log:
    section:
      # Section heading where log entries are inserted.
      title: Log
      # Heading level for section (entry heading is level+1).
      level: 2
    entry:
      # Default preserves current behavior.
      # You can set e.g. "%Y-%m-%d" for date-only headings.
      timestamp_format: iso-seconds
  rename:
    # Keep note file names in sync when project folder is renamed.
    enabled: true
    # Default if omitted: mv {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}
    # Override this for Obsidian/other apps.
    # Variables: OLD_NOTE_PATH, OLD_NOTE_PATH_Q, NEW_NOTE_PATH, NEW_NOTE_PATH_Q,
    #            OLD_NOTE_NAME, NEW_NOTE_NAME, OLD_NOTE_FILE, NEW_NOTE_FILE,
    #            OLD_PROJECT_NAME, NEW_PROJECT_NAME
    command: "mv {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}"
    # Example for Obsidian CLI (triggers refresh of linking to the renamed notes and so on):
    # command: "obsidian rename path=\"notes/{{ OLD_NOTE_FILE }}\" name=\"{{ NEW_NOTE_NAME }}\""

# Reconcile pacing settings.
reconcile:
  active:
    update_batch_size: 12
  archive:
    update_batch_size: 8

# Table behavior, columns, and date-color gradients.
table:
  behavior:
    pin_wip_top: false
    side_width_pct: 33

  columns:
    active:
      - id: name
        width: 28
        enabled: true
      - id: description
        width: 40
        enabled: true

  columns_style:
    date:
      all:
        # Shared baseline for both views.
        # Same meaning everywhere:
        # blue = new, green = fresh, yellow = aging, orange = old, red = very old
        last_modified:
          0: "#38bdf8"
          10: "#22c55e"
          100: "#facc15"
          250: "#f97316"
          365: "#ef4444"

      active:
        # Short recency emphasis.
        last_opened:
          0: "#38bdf8"
          3: "#22c55e"
          14: "#facc15"
          30: "#f97316"
          90: "#ef4444"

        # Slower aging than opened, but same color meaning.
        created:
          0: "#38bdf8"
          30: "#22c55e"
          120: "#facc15"
          365: "#f97316"
          730: "#ef4444"

        # Main age heatmap.
        last_modified:
          0: "#38bdf8"
          10: "#22c55e"
          100: "#facc15"
          250: "#f97316"
          365: "#ef4444"

      archive:
        # Same scale meaning as the others, just stretched for archive age.
        archived_at:
          0: "#38bdf8"
          30: "#22c55e"
          180: "#facc15"
          365: "#f97316"
          730: "#ef4444"

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
  # String shorthand still works.
  - open_selected

  # Rich style example: green if tmux pane exists.
  - action: open_selected
    label: open (tmux)
    style:
      - bg_color: "#bff4d3"
        fg_color: "#123b25"
        bold: true
        when: "!tmx"

  # Notes action styled when notes file marker/property exists.
  - action: notes_create
    label: Notes
    style:
      - bg_color: "#d8e9ff"
        fg_color: "#1b3558"
        underline: true
        when: "!n"

  # Log action can react to multiple conditions.
  - action: add_log_to_note
    label: Log
    style:
      # Same query syntax as the query bar. Evaluated on selected row.
      - bg_color: "#ffaaaa"
        fg_color: "#3f1010"
        bold: true
        when: "!rm"
      # Later rule overrides earlier fields when both match.
      - bg_color: "#ffe9b8"
        fg_color: "#5a4200"
        italic: true
        when: "#wip"
      # Suffix-based rule.
      - bg_color: "#ece7ff"
        fg_color: "#34296b"
        when: ".tmp"

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
