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

| Field | Type | Notes |
|---|---|---|
| `name` | str | Required |
| `source` | `bundled`/`custom` | Default `custom` |
| `enabled` | bool | Default `true` |
| `views` | list[`active`/`archive`] | Empty/omitted = both |
| `config` | mapping | Passed through to hook |
| `slow_warn_s` | number | Default `30.0`, min `1.0` |

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

## Bundled Hooks (v1)

Post hooks:

- `rename/notes_rename`
- `rename/tag_symlink_sync`
- `rename/notify`
- `tag_change/tag_symlink_sync`
- `tag_change/notify`
- `new_project/tag_symlink_sync`
- `new_project/notify`
- `delete/tag_symlink_sync`
- `delete/notify`

Pre hooks:

- `delete/confirm_delete` (default disabled)

The `notify` hooks emit a status message via `ctx.notify(...)` and
serve as the simplest reference implementation for each event. They
accept an optional `config.level` (`info|warn|error`, default `info`).
