# Actions, Hotbar, Keys (Reference)

Technical reference for `<base>/.homebase/config.yaml` action dispatch.

## Model

- `actions`: map `action_id -> action_def`.
- `hotbar`: ordered target-scope actions; active entry controls Enter on row.
- `keys`: key chord map for direct action dispatch.

Built-ins come from code (`BUILTIN_ACTIONS`) plus tab auto-registration
(`tab.<top>` / `tab.<top>.<child>`).

## Action Definition

Allowed on all actions:

| Field | Type | Meaning |
|---|---|---|
| `label` | str | Display label |
| `confirm` | bool/str | Custom actions: `true`/`false`/string. Built-ins: string only |
| `raycast` | bool/map | Opt into Raycast Cmd-K actions. `true` or `{ enabled: true, title: "..." }` |

Custom-only fields:

| Field | Type | Meaning |
|---|---|---|
| `kind` | `shell`/`filepicker`/`note` | Required for custom action |
| `scope` | `target`/`workspace`/`tab` | Default `target` |
| `multi` | `joined`/`per_row` | `shell` dispatch mode |
| `hidden` | bool | Hide from picker |
| `view_scope` | list[str] | `active`/`archive` filter |

Kind-specific requirements:

| kind | Required | Scope |
|---|---|---|
| `shell` | `command` | `target` or `workspace` |
| `filepicker` | `list`, `command` | `target` only |
| `note` | `op: add_log` | `target` only |

## Dispatch Semantics

- `multi: joined` runs once and resolves list-form variables.
- `multi: per_row` runs once per selected row in current selection order.
- `filepicker` always does per-row list collection + one final command dispatch.
- `note` currently supports `add_log` only.

## Template Variables

Use `_q` variants in shell commands (`shlex.quote` style).

Example context used below:

- `base_dir=/Users/alex/base`
- selected row: `~/base/homebase` (`name=homebase`, `branch=main`)
- active view with 12 rows, 3 wip

Always available:

| Variable | Description | Example |
|---|---|---|
| `base_dir` | Absolute base workspace path. | `/Users/alex/base` |
| `base_dir_q` | Quoted `base_dir` for shell command use. | `'/Users/alex/base'` |
| `base_name` | Basename of `base_dir`. | `base` |
| `archive_dir` | Absolute archive path. | `/Users/alex/base/.archive` |
| `archive_dir_q` | Quoted `archive_dir`. | `'/Users/alex/base/.archive'` |
| `active_count` | Number of active (non-archived) rows. | `12` |
| `archive_count` | Number of archived rows. | `42` |
| `wip_count` | Number of rows tagged/flagged as wip. | `3` |
| `count` | Number of currently selected rows. | `2` |
| `view` | Current table view. | `active` |
| `filter` | Current filter expression text. | `#wip and branch=main` |
| `filter_q` | Quoted filter expression. | `'#wip and branch=main'` |
| `now` | Local datetime string. | `2026-05-10 14:21:33` |
| `now_iso` | ISO datetime string. | `2026-05-10T14:21:33+02:00` |
| `now_ts` | Unix timestamp integer string. | `1778415693` |
| `today` | Local date string. | `2026-05-10` |
| `user` | Current OS user. | `alex` |
| `home` | User home directory. | `/Users/alex` |
| `home_q` | Quoted home directory. | `'/Users/alex'` |

Per-row family (`multi: per_row`, filepicker `list`):

| Variable | Description | Example |
|---|---|---|
| `path` | Absolute project path for current row. | `/Users/alex/base/homebase` |
| `path_q` | Quoted `path`. | `'/Users/alex/base/homebase'` |
| `rel_path` | Project path relative to base dir. | `homebase` |
| `rel_path_q` | Quoted `rel_path`. | `'homebase'` |
| `name` | Row name (project directory name). | `homebase` |
| `name_q` | Quoted `name`. | `'homebase'` |
| `parent_path` | Parent directory absolute path. | `/Users/alex/base` |
| `parent_path_q` | Quoted `parent_path`. | `'/Users/alex/base'` |
| `branch` | Git branch if repo is detected. | `main` |
| `branch_q` | Quoted `branch`. | `'main'` |
| `dirty` | Git dirty state flag (`true`/`false`). | `false` |
| `description` | `.base.yaml` description value. | `Terminal workspace manager` |
| `description_q` | Quoted `description`. | `'Terminal workspace manager'` |
| `tags` | Comma-separated tags list. | `cli,python` |
| `tags_space` | Space-separated tags list. | `cli python` |
| `tags_space_q` | Quoted space-separated tags. | `'cli python'` |
| `properties` | Comma-separated active property tokens. | `GIT,EDT` |
| `suffix` | Row suffix (if present). | `tmp` |
| `wip` | WIP flag (`true`/`false`). | `true` |
| `archived` | Archived flag (`true`/`false`). | `false` |
| `packed` | Packed archive flag (`true`/`false`). | `false` |
| `created` | Local created datetime string. | `2026-05-01 10:11:12` |
| `created_iso` | ISO created datetime string. | `2026-05-01T10:11:12+02:00` |
| `created_ts` | Unix timestamp for created datetime. | `1777623072` |
| `modified` | Local last-modified datetime string. | `2026-05-10 13:00:00` |
| `modified_iso` | ISO last-modified datetime string. | `2026-05-10T13:00:00+02:00` |
| `modified_ts` | Unix timestamp for last-modified datetime. | `1778410800` |
| `active` | Local last-opened datetime string. | `2026-05-10 09:12:01` |
| `active_iso` | ISO last-opened datetime string. | `2026-05-10T09:12:01+02:00` |
| `active_ts` | Unix timestamp for last-opened datetime. | `1778397121` |
| `archived_at` | Local archived-at datetime string (or empty). | `` |
| `archived_at_iso` | ISO archived-at datetime string (or empty). | `` |
| `archived_at_ts` | Unix timestamp for archived-at datetime (or empty). | `` |
| `size_bytes` | Total directory size in bytes. | `528482` |
| `size_human` | Human-readable directory size. | `516K` |
| `note_path` | Resolved note path for row. | `/Users/alex/base/homebase/NOTES.md` |
| `note_path_q` | Quoted `note_path`. | `'/Users/alex/base/homebase/NOTES.md'` |

List-form family (`multi: joined`):

| Variable | Description | Example |
|---|---|---|
| `paths` | Space-joined absolute paths for all selected rows. | `/Users/alex/base/homebase /Users/alex/base/dotfiles` |
| `paths_q` | Safely quoted selected paths. | `'/Users/alex/base/homebase' '/Users/alex/base/dotfiles'` |
| `rel_paths` | Space-joined selected relative paths. | `homebase dotfiles` |
| `rel_paths_q` | Quoted selected relative paths. | `'homebase' 'dotfiles'` |
| `names` | Space-joined selected row names. | `homebase dotfiles` |
| `names_q` | Quoted selected row names. | `'homebase' 'dotfiles'` |

Filepicker family:

| Variable | Description | Example |
|---|---|---|
| `selection` | Raw selected item from picker output. | `/Users/alex/base/homebase/README.md` |
| `selection_q` | Quoted `selection` for command execution. | `'/Users/alex/base/homebase/README.md'` |

Validation rules:

- Unknown/unavailable variables fail config load.
- Variables are validated against action scope + dispatch mode.

## Raycast Integration

Raycast only exposes actions that opt in with `raycast`.

Project ordering:

```yaml
raycast:
  # name (default) or opened
  sort: opened
  secondary_info:
    - "{{ opened_ago }}"
    - "{{ tags_space }}"
```

`secondary_info` entries are rendered from cached row data and indexed as
Raycast search keywords. Useful variables:

| Variable | Notes |
| --- | --- |
| `opened_ago` / `active_ago` | Human last-opened text, e.g. `2 hours ago` |
| `tags_space` | Tags separated by spaces |
| `tags` | Tags separated by commas |
| `branch`, `dirty`, `description`, `properties_space`, `suffix` | Cached row fields |
| `created_ago`, `modified_ago`, `size_human` | Cached derived fields |

```yaml
actions:
  notes_create:
    raycast: true
  notes_open:
    raycast: true

  open_item_in_codium:
    kind: shell
    scope: target
    multi: joined
    command: 'codium {{ paths_q }}'
    raycast:
      enabled: true
      title: Open in Codium
```

Supported Raycast actions:

- Built-ins: `open_selected`, `notes_create`, `notes_open`
- Custom shell actions with `scope: target` or `scope: workspace`

Notes are contextual. Missing note file exposes `notes_create` if enabled;
existing note file exposes `notes_open` if enabled.

## Hotbar and Keys

Hotbar:

- Entries: `"action_id"` or `{ action: ..., label: ... }`
- Only `scope: target` actions allowed.
- Optional per-slot `label` override.
- Optional per-slot `style` rules:

```yaml
hotbar:
  - action: add_log_to_note
    label: Log
    style:
      - bg_color: "#ffaaaa"
        when: "!rm"
```

- `when` uses the same query/filter language as the main query input.
- Rules are evaluated against the currently selected row.
- `bg_color` must be `#RRGGBB`.
- `fg_color` must be `#RRGGBB`.
- `bold`, `underline`, `italic` are supported.
- If multiple rules match, the last matching rule wins.

Use-cases:

```yaml
hotbar:
  - action: add_log_to_note
    label: Log
    style:
      - bg_color: "#ffaaaa"
        fg_color: "#2d0a0a"
        bold: true
        when: "!rm"

  - action: open_selected
    label: open (tmux)
    style:
      - bg_color: "#c8f7db"
        fg_color: "#10331f"
        when: "!tmx"

  - action: review_meta
    label: review meta
    style:
      - bg_color: "#ffe2e2"
        fg_color: "#6b1111"
        bold: true
        underline: true
        when: "!e"

  - action: archive
    style:
      - bg_color: "#fff2cf"
        fg_color: "#5e4300"
        when: "#wip"
      - bg_color: "#ece7ff"
        fg_color: "#322a6d"
        italic: true
        when: ".tmp"
```

`when` reminders:

- `!rm` means property `rm` is present (not negation).
- `#tag` matches tag.
- `.tmp` matches suffix.
- full expressions are valid (`#wip OR !e`, `(!rm AND #docs)`).

Keys:

- Entries: `'f5': action_id` or `'f5': { action: ..., label: ... }`
- Keys are unique.

## Tab Actions

Auto-registered:

- `tab.selected`, `tab.info`, `tab.settings`
- `tab.selected.overview`, `tab.info.events`, ...

`tab.*` actions dispatch side-panel navigation and are not hotbar-eligible.

## Discoverability

- CLI: `b help actions [--source builtin|config|overridden] [--bound bound|unbound] [--view active|archive] [--show-defaults]`
- TUI: `Info > Stats` shows live context variable resolution.
