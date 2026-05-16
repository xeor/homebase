# Hooks (Reference)

Technical reference for workspace hook dispatch.

## Scope

- Events: `rename`, `tag_change`, `new_project`, `delete`
- Timings: `pre`, `post`
- Sources: `bundled`, `custom`

Hooks run in both TUI and CLI.

## Filesystem Layout

Bundled hooks:

```text
src/homebase/hooks/bundled/
  pre/<event>/<name>.py
  post/<event>/<name>.py
```

Custom hooks (per workspace):

```text
<base>/.homebase/hooks/
  pre/<event>/<name>.py
  post/<event>/<name>.py
```

## Config

In `<base>/.homebase/config.yaml`:

```yaml
hooks_pre:
  delete:
    - name: confirm_delete
      source: bundled
      enabled: false
      config:
        require_confirm: true

hooks_post:
  rename:
    - name: notes_rename
      source: bundled
      enabled: true
    - name: tag_symlink_sync
      source: bundled
      enabled: true
```

Hook entry fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | str | — | Required |
| `source` | `bundled`/`custom` | `custom` | |
| `enabled` | bool | `true` | |
| `views` | list[`active`/`archive`] | both | Empty/omitted = both |
| `config` | mapping | `{}` | Per-hook keys; see "Bundled Hooks" |
| `slow_warn_s` | number | `30.0` | Min `1.0` |
| `refresh_enabled` | bool | `false` | Opt-in for periodic refresh worker. Manual `b hooks refresh` ignores this |
| `refresh_min_interval_s` | number | `60.0` | Per-(project, hook) floor for worker scheduling |

Config load is strict:

- Unknown event/view -> startup error
- Missing custom file -> startup error
- Missing/unknown bundled module -> startup error

## Hook Module Contract

Each hook module must export `run(ctx)`.

- Post hooks: return value ignored
- Pre hooks: return `None` or `PreResult`

```python
from homebase.hooks.api import HookContext
from homebase.core.models import PreResult

def run(ctx: HookContext) -> None: ...
def run(ctx: HookContext) -> PreResult | None: ...
```

Optional module attributes:

- `DESCRIPTION = "..."`
- `REQUIRES = {"git", "gh"}`

## `HookContext`

Core fields:

- `event`, `timing`, `view`
- `base_dir`
- `targets: tuple[HookTarget, ...]`
- `change: dict[str, object]`
- `runtime`, `hook`

Output and interaction callables:

- `ctx.add_event(path, kind, payload)` -> append `.base.yaml` log
- `ctx.notify(text, level)` -> toast notification (`info|warn|error`)
- `ctx.status_update(text, level)` -> status-bar update (no toast)
- `ctx.log(text, level)` -> debug log
- `ctx.ask(...)` -> pre-hooks only

Use `notify` for prominent, transient messages the user must see.
Use `status_update` for ambient runtime feedback that belongs in the
status bar but should not pop a toast.

## Dispatch Semantics

Post:

- TUI: background worker thread, UI remains responsive
- CLI: synchronous on calling thread
- Per event firing: hooks run sequentially, config order is preserved
- Slow hooks: warning repeats every `slow_warn_s`
- Framing events for single-target dispatch: `hook_started`, `hook_done`

Pre:

- Always blocking relative to the operation
- Sequential execution
- `cancel` aborts operation
- `mutate` updates running `change` for subsequent pre-hooks and operation

## Pre Mutation Allowlist

Only these keys are accepted from `PreResult(mutated_change=...)`:

- `rename`: `new_path`, `new_name`
- `tag_change`: `plan`
- `new_project`: `initial_tags`, `template`, `post_commands`, `after_create`
- `delete`: none

Disallowed keys are ignored and logged as warnings.

## Event Payload Shapes

Implemented `change` payload keys used by trigger paths:

- `rename`: `old_path`, `new_path`, `old_name`, `new_name` (+ note fields used by bundled `notes_rename`)
- `tag_change`: `plan`, `per_target`
- `new_project`: `created_path`, `source`, `template`, `initial_tags`, `post_commands`, `after_create`, `inputs`, `plan`
- `delete`: `removed_paths`, `removed_snapshots`

## Bundled Hooks

Each bundled hook is referenced by `(timing, event, name)` and lives
at `homebase.hooks.bundled.<timing>.<event>.<name>`. The `config:`
mapping in the hook entry is the only knob exposed to users beyond
the common entry fields above.

### `post/rename/notes_rename`

Keeps the notes file in sync with a project rename. Uses the global
`notes:` config (`path_template`, `rename.command`) to render the
move; falls back to a plain `Path.rename` if no command is configured.

| Config key | Type | Default | Notes |
|---|---|---|---|
| _(none)_ | | | Reads global `notes:` config; no per-hook keys |

Defaults to `enabled: true`.

### `post/rename/tag_symlink_sync`<br>`post/tag_change/tag_symlink_sync`<br>`post/new_project/tag_symlink_sync`<br>`post/delete/tag_symlink_sync`

Rebuilds the `_tags/` symlink index in the workspace base so that
`<base>/_tags/<tag>/` reflects the current set of tagged projects.

| Config key | Type | Default | Notes |
|---|---|---|---|
| _(none)_ | | | Re-runs `sync_tag_symlinks(base_dir)` |

Defaults to `enabled: true` on all four events. Failures surface via
`ctx.notify(...)` with `warn` level.

### `post/rename/notify`<br>`post/tag_change/notify`<br>`post/new_project/notify`<br>`post/delete/notify`

Reference hooks that emit a single toast describing the event. Useful
as a copy-paste starting point for custom hooks.

| Config key | Type | Default | Notes |
|---|---|---|---|
| `level` | `info`/`warn`/`error` | `info` | Severity passed to `ctx.notify(...)` |

Defaults to `enabled: false`. Per event, the toast text is:

- `rename`: `renamed: <old_name> -> <new_name>`
- `tag_change`: `tags on N project(s): +added -removed`
- `new_project`: `new project: <name> (source=…, template=…)`
- `delete`: `deleted N project(s)`

### `post/tag_change/tag_files_sync`

On tag add, symlinks files from `<root>/<tag>/` into each project.
On tag remove, unlinks only the symlinks that still point to the
recorded source. Refresh-capable: re-links new source files and
prunes orphan symlinks whose source vanished (driven by
`tag_files_linked` events recorded in `.base.yaml`).

| Config key | Type | Default | Notes |
|---|---|---|---|
| `root` | str (path) or empty | `<base>/.homebase/tag-files/` | Override the source root. Relative paths resolve against `base_dir`. Absolute paths and `~/...` are used as-is |
| `dry_run` | bool | `false` | Preview without making changes |

Common entry fields most useful here: `refresh_enabled`,
`refresh_min_interval_s` (see "Refresh" below). Defaults to
`enabled: false`.

Safety mechanisms (always on):

- Path traversal in the tag name (`..`) is rejected.
- Real files in the destination are never overwritten — warns instead.
- Existing symlinks pointing elsewhere are never replaced — warns instead.
- Symlinks in the source tree are skipped (traversal containment).
- Type conflicts (file ↔ directory) are detected and skipped.
- Remove path only unlinks symlinks whose `readlink` still matches the
  source path recorded at link time.

### `pre/delete/confirm_delete`

Pops a yes/no confirmation before delete proceeds. Cancels the
operation if the user declines.

| Config key | Type | Default | Notes |
|---|---|---|---|
| `require_confirm` | bool | `true` | When `false`, the hook is a no-op |

Defaults to `enabled: false`.

## Refresh

In addition to the event-driven `run(ctx)`, post-hook modules may
export an optional `refresh(ctx)` to re-run reconciliation without an
underlying event firing (e.g. files appeared/disappeared in the
source directory of `tag_files_sync`).

Hook module contract:

```python
def run(ctx: HookContext) -> None: ...        # required, event path
def refresh(ctx: HookContext) -> None: ...    # optional
```

- Absence ⇒ hook is not refreshable; refresh triggers skip it.
- `ctx.mode == "refresh"` is set during refresh dispatch.
- `ctx.timing` is always `"post"`; pre-hooks have no refresh contract.
- Idempotency: calling `refresh` twice in a row must be a no-op the
  second time. The bundled `tag_files_sync.refresh` is the
  reference example.
- Prefer `ctx.log(...)` over `ctx.notify(...)` for non-actionable
  output — the worker runs frequently and toast spam is not OK.

`change` payload under refresh, per event:

| Event | `change` |
|---|---|
| `tag_change` | `{"per_target": {path: {"current_tags": [...]}}}` |
| others | not refreshable in v1 |

### Trigger surfaces

- **CLI:** `b hooks refresh [--all] [--project PATH] [--tag TAG] [--filter EXPR] [--hook NAME] [--event EVENT] [--archived] [--dry-run]`
  Selectors compose AND-across-types, OR-within-type. Manual triggers
  ignore `refresh_enabled` and run any spec exposing `refresh`.
- **TUI actions:**
  - `hooks_refresh` (target scope) — refresh for selected row(s).
  - `hooks_refresh_view` (workspace scope) — refresh for all rows
    in the current view.
- **Periodic worker:** tick every `UI_TICK_HOOK_REFRESH_S` seconds.
  Only fires for specs with `refresh_enabled: true`, honoring
  per-spec `refresh_min_interval_s` floor per `(project, hook)`. Sees
  `views` filter. Bails when cache / reconcile worker is busy or
  fast-exit is set (overridable via
  `hooks_refresh.worker.skip_when_busy`).

### Observability

- `.base.yaml` events: `hook_refresh_started`, `hook_refresh_done`,
  each carrying `source` (`cli` | `tui-action` | `worker`) and
  `duration_s` / `error`.
- Stdout/stderr captured per refresh; piped to `ctx.log` (stdout) or
  warn-level log (stderr).

### Config additions

```yaml
hooks_post:
  tag_change:
    - name: tag_files_sync
      source: bundled
      enabled: true
      refresh_enabled: true            # opt-in for worker
      refresh_min_interval_s: 120      # floor per (project, hook)
      config:
        root: ~/sync/tag-overlays

hooks_refresh:
  enabled: false                       # default off; opt-in
  worker:
    batch_size: 4
    jitter_pct: 15
    skip_when_busy: true
```
