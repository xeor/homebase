# TODO: Hooks system

Planning doc. Not implementation. Iterate here until shape is settled,
then peel off discrete tickets.

## Implementation status

- 2026-05-15: Hooks system v1 implementation phases completed (1-8).

- 2026-05-15: Phase 1 completed in-tree.
  - Added `hooks/` package skeleton (`api.py`, `loader.py`, `runtime.py` stub, bundled dir tree).
  - Added hook core/config models and parser (`HookSpec`, `HookTarget`, `PreResult`, `load_hook_specs`).
  - Wired runtime config/UI context/CLI startup, including hard-fail `verify_all_specs(...)`.
  - Added tests: `tests/test_config_hooks.py`, `tests/test_hooks_loader.py`.
- 2026-05-15: Phase 2 started.
  - Implemented threaded `dispatch_post` runtime path with view filtering, sequential hook execution,
    slow-hook warning loop, runtime-error routing, framing events for single-target dispatch,
    and `hook_recent` tracking.
  - Added rename trigger wiring and hook snapshot helper.
  - Added side-panel `Info -> Hooks` tab renderer.
  - Added tests: `tests/test_hooks_runtime.py` and rename dispatch assertion in
    `tests/test_item_edits.py`.
- 2026-05-15: Phase 3 started (post hooks on additional events).
  - Wired `tag_change` post-dispatch in `on_pick_tags`, `rename_tag_globally`, and
    `delete_tag_globally` with `plan` + `per_target` payloads.
  - Wired `new_project` post-dispatch in `on_new_project_submit` for both
    `after_create=open` and stay-in-TUI paths.
  - Wired `delete` post-dispatch in bulk action flow with pre-delete snapshots in
    both `ctx.targets` and `change.removed_snapshots`.
- 2026-05-15: Phase 4 started (custom loader/runtime hardening).
  - Added stdout/stderr capture around hook execution; routed captured output through
    runtime log path.
  - Added startup scan for `.homebase/hooks/pre/<event>/*.py` and explicit warning that
    custom pre-hooks are discovered but ignored until phase 7.
- 2026-05-15: Phase 5 started (bundled hooks port).
  - Added bundled post hooks: `notes_rename` and `tag_symlink_sync` for
    `rename`, plus `tag_symlink_sync` for `tag_change`, `new_project`, and `delete`.
  - Removed duplicate inline side effects at trigger sites where these bundled
    hooks now execute (`rename` note sync, direct tag-sync requests for
    `rename/tag_change/new_project/delete`).
  - Added default bundled post specs in config loader to preserve existing behavior
    on workspaces without explicit `hooks_post` config yet.
  - Added focused tests for bundled hook behavior:
    `tests/test_hooks_bundled_notes_rename.py` and
    `tests/test_hooks_bundled_tag_symlink_sync.py`.
- 2026-05-15: Phase 6 completed (CLI dispatch path).
  - Added synchronous CLI hook dispatcher (`dispatch_post_cli`) with stderr progress
    lines and stdout/stderr capture for hook code.
  - Wired CLI `b new` flow to dispatch `new_project` post hooks via callback from
    `cli.entry` into `workspace.new.cmd`.
  - Wired CLI `b rm` flow to dispatch `delete` post hooks with pre-delete snapshot payload.
  - Added CLI slow-hook warning loop + hook_started/hook_done framing events in
    `dispatch_post_cli`.
- 2026-05-15: Phase 7 completed (pre hooks).
  - Implemented functional `dispatch_pre` path (TUI runtime): sequential pre-hook
    execution, cancel/mutate handling via `PreResult`, and exception->cancel behavior.
  - Wired rename trigger to call `dispatch_pre` before filesystem rename, including
    support for mutated `new_path` returned by a pre-hook.
  - Wired `dispatch_pre` into `tag_change` and `delete` TUI trigger sites with
    cancel handling and mutable `plan` support for `tag_change`.
  - Added CLI `dispatch_pre_cli` runtime path and wired it into `b rm` delete flow.
  - Wired CLI `b new` through `pre_create_hook` callback path so pre-hooks can cancel
    or mutate request inputs before `plan_and_apply_one` executes.
  - Added conservative per-event mutation allowlist enforcement in runtime for both
    TUI and CLI pre-dispatch paths (unsupported keys are ignored with warning).
  - Implemented TUI `ctx.ask(...)` bridge for pre-hooks using modal screens
    (yes/no + text + choice via `SingleChoiceScreen`), with synchronous worker wait.
  - Added regression tests for pre-hook cancellation at `tag_change` and `delete`
    trigger sites (`tests/test_tag_actions.py`, `tests/test_bulk_dispatch.py`).
  - Added rename pre-hook trigger-site regressions for cancel + mutate behavior
    (`tests/test_item_edits.py`).
  - Added new-project pre-hook flow regression ensuring pre-mutations are applied
    before planning (`tests/test_project_create.py`).
  - Added CLI delete regression ensuring `b rm` honors pre-hook cancellation before
    entering workspace delete path (`tests/test_commands_workspace.py`).

## Self-evaluation vs plan

- Overall: implementation is ahead of the original phase ordering; phases 1-5 are functionally in place,
  phase 6 and 7 are substantially implemented, phase 8 docs not started.
- Phase 1 (skeleton/config/types): done and validated.
- Phase 2/3 (post runtime + all events in TUI): done for rename/tag_change/new_project/delete trigger sites.
- Phase 4 (custom loader/runtime hardening): mostly done (importlib load, startup verification,
  stdout/stderr capture, explicit warning for ignored custom pre folders).
- Phase 5 (bundled hooks + side-effect migration): done for `notes_rename` and `tag_symlink_sync` with
  duplicate inline side-effects removed from target trigger paths.
- Phase 6 (CLI post path): done for CLI-exposed new/delete operations (`b new`, `b rm`) with synchronous execution,
  slow-warn, and framing events.
- Phase 7 (pre hooks): done for v1 scope in runtime and trigger wiring.
  - Implemented `dispatch_pre` (TUI) and `dispatch_pre_cli` (CLI), cancel/mutate semantics, allowlist enforcement.
  - Wired pre hooks in TUI for rename/tag_change/delete/new_project and in CLI for delete/new_project.
  - Implemented `ctx.ask` for TUI and CLI.
  - Added bundled pre hook `confirm_delete` (disabled by default) to validate pre-hook contract.
- 2026-05-15: Phase 8 completed (docs).
  - Added `docs/hooks.md` reference covering config schema, runtime contract,
    dispatch semantics, mutation allowlist, payload shapes, and bundled hooks.
- Phase 8 (docs): done (`docs/hooks.md`).

Known deviations from original doc wording:

- `hooks_post` currently has bundled defaults injected by config loader to preserve behavior without explicit config.
  This diverges from the strict "hooks must be listed in config" rule and should be either documented as intentional
  compatibility behavior or reverted before finalizing v1 semantics.
- TUI `ctx.ask(kind="choice")` is now implemented via `SingleChoiceScreen`; CLI `choice` uses stdin text entry.

## Goal

A user-pluggable hook system that fires on workspace events and can
react (notify the user, append project event-log entries, run side
effects). Must be robust enough that existing in-tree side effects
(note-sync on rename, tag-sync on tag-change, etc.) can migrate into
it later.

## Scope (v1)

Triggers (events):

- `rename` — project folder renamed
- `tag_change` — tags added/removed on one or more projects
- `new_project` — project created
- `delete` — project permanently deleted

Hook sources:

- `bundled` — ships with `b`, registered in-tree
- `custom` — user file at `.homebase/hooks/<event>/<name>.py`

Timing: design covers **both pre- and post-event** in v1. Only post is
implemented in v1; pre is wired into the namespace and contract now so
no later rewrite is needed. See "Pre-event hooks" subsection.

UI requirement (post-event hooks): must not block the main thread.
Long hooks display a per-hook spinner in the busy area; UI stays
responsive.

UI requirement (pre-event hooks): **block** the operation by design —
they must complete before the file op runs. They may also prompt the
user (modal dialog in TUI, stdin prompt in CLI). See pre-event
subsection for how this is reconciled with "no UI freeze".

---

## Naming

- Event ids in code: `rename`, `tag_change`, `new_project`, `delete`
  (snake_case, valid Python identifiers).
- Custom hook directory uses the same snake_case
  (`.homebase/hooks/tag_change/...`) — avoids the hyphen/identifier
  mismatch.
- A "hook" = one named callable with one source (`bundled` or
  `custom`) bound to one event + timing (pre or post).

COMMENT: Should it ba called something other than "builtin"? If the python folder is named "builtin", it might collide with the python module with that name? Maybe the python folder should be renamed?

---

## On-disk layout

```
src/homebase/hooks/                # new top-level package
├── __init__.py
├── api.py                          # HookContext + helpers
├── runtime.py                      # dispatcher (pre + post)
├── loader.py                       # bundled + custom loaders
└── bundled/                        # was "builtin" — see naming note
    ├── __init__.py
    ├── pre/                        # pre-event hooks
    │   ├── rename/
    │   ├── tag_change/
    │   ├── new_project/
    │   └── delete/
    └── post/                       # post-event hooks
        ├── rename/
        │   └── notes_rename.py
        ├── tag_change/
        │   └── tag_symlink_sync.py
        ├── new_project/
        │   └── ...
        └── delete/
            └── ...

.homebase/hooks/                    # user, per-workspace
├── pre/
│   ├── rename/
│   ├── tag_change/
│   ├── new_project/
│   └── delete/
└── post/
    ├── rename/
    │   └── my_rename_hook.py
    ├── tag_change/
    │   └── sync_gitignore.py
    ├── new_project/
    └── delete/
```

Layering: `hooks/` slots in after `metadata/`, before `commands/` and
`ui/`. It depends on `core/`, `config/`, `metadata/`, and *only*
metadata/event-log helpers — never on `ui/` directly. The UI imports
`hooks/runtime` to dispatch.

---

## Config schema

Lives in the existing `.homebase/config.yaml` under two top-level keys
— `hooks_pre:` and `hooks_post:` — each indexed by event id:

```yaml
hooks_pre:
  rename:
    - name: validate_branch_name
      source: bundled
      enabled: true
      views: [active]               # list; default: [active, archive]
      config: {}
  tag_change: []
  new_project: []
  delete: []

hooks_post:
  rename:
    - name: notes_rename            # required
      source: bundled               # bundled | custom (default: custom)
      enabled: true                 # default: true
      views: [active, archive]      # list; default: [active, archive]
      config: {}                    # opaque per-hook config dict
      slow_warn_s: 30               # optional; emits a "still running" notification
  tag_change:
    - name: sync_gitignore
      source: custom
      enabled: true
      views: [active]
      config:
        include_tags: [oss, public]
  new_project: []
  delete: []
```


Notes:

- Hooks run in listed order. Order is stable.

- `views` filters by current view — empty list or omitted means
  `[active, archive]`. A hook with `views: [active]` will not fire
  when the operation runs in archive view.

- Hooks fire from one view at a time (the current `app.view_mode` /
  CLI equivalent), so there is never a mixed-view dispatch.

- `source: bundled` resolves against the bundled registry; unknown
  names cause a **hard fail on config load** — `b` refuses to start.
  `source: custom` missing file → same. The user must see that a
  configured hook is missing; silent skip is not acceptable.


- `config:` is opaque to the dispatcher; passed through to the hook
  on `ctx.hook.config`.

Loader: `config/hooks.py` (new module), mirroring
`config/property_defs.py`. Exposes
`load_hook_specs(base_dir) -> dict[("pre"|"post", event), list[HookSpec]]`.
`UIContext` and `RuntimeConfig` get a new `hook_specs` field.

---

## Hook contract

Each hook file (bundled or custom) exposes:

```python
from homebase.hooks.api import HookContext

# Post-event hook: return value is ignored.
def run(ctx: HookContext) -> None: ...

# Pre-event hook: return value is a PreResult (see Pre-event subsection).
def run(ctx: HookContext) -> "PreResult | None": ...
```

Optional module-level attributes a hook can set:

- `DESCRIPTION = "..."` — surfaced in the Info panel.
- `REQUIRES = {"git", "gh"}` — optional binary preflight (skip + log
  if missing).

Dispatch is always **batch**: `run()` is called once with the full
target list. Per-target work is the hook's responsibility (iterate
`ctx.targets`).

### HookContext

```python
@dataclass(frozen=True)
class HookContext:
    event: str                              # "rename" | "tag_change" | ...
    timing: str                             # "pre" | "post"
    view: str                               # current view: "active" | "archive"
                                            # — single value; `views:` in
                                            # config is the *filter list*.

    base_dir: Path
    targets: list[HookTarget]               # see below
    change: dict                            # event-specific payload
    runtime: HookRuntime                    # invoker, version, now
    hook: HookInfo                          # name, source, config

    # output channels (injected callables — closures, ctx stays frozen):
    add_event: Callable[[Path, str, dict], None]   # streams to project log
    notify:    Callable[[str, str], None]          # status line / stderr
    log:       Callable[[str, str], None]          # debug log / stdout

    # pre-event only: prompt the user for input. Blocks; returns answer.
    # In TUI: opens a modal. In CLI: reads from stdin.
    # Hook must call this only from a `pre` hook.
    ask: Callable[..., str | None]
```

`ctx.add_event` is the **single primary output channel**. It streams
project event-log entries during the hook (real-time), and is also
used to signal completion (e.g. `ctx.add_event(path, "hook_done",
{...})`). `ctx.notify` and `ctx.log` exist for UX surface (status
line, debug log) but carry no semantic side effect.

`HookTarget` snapshot (immutable copy at dispatch time):

```python
@dataclass(frozen=True)
class HookTarget:
    path: Path
    name: str
    archived: bool
    tags: list[str]
    properties: list[str]
    description: str
    wip: bool
    suffix: str | None
    packed: bool
    # full raw .base.yaml at snapshot time — anything not surfaced
    # above (log events, custom keys, etc.) lives here.
    base_meta: dict
    # cached row fields useful to hooks
    last_modified_ts: int
    created_ts: int
    archived_ts: int
    git_branch: str
    git_dirty: str
```

Snapshot policy:

- **pre-event** hooks see *current* state (before the operation).
- **post-event** hooks for `rename`/`delete` see *source* state
  (what the project was just before the op). For rename, the new
  path is in `change`. For delete, the snapshot is the only
  remaining record of the project's metadata, so it must be
  complete (`base_meta` dict included).
- **post-event** hooks for `tag_change`/`new_project` see
  *post-operation* state.

### Per-event `change` payload

**rename** (single target, always `len(targets) == 1`):
```python
{
    "old_path": Path,
    "new_path": Path,
    "old_name": str,
    "new_name": str,
}
```

**tag_change** (multiple targets):
```python
{
    "plan": {"tag1": "add", "tag2": "remove", ...},   # the original plan
    "per_target": {
        Path: {
            "before": ["t1", "t2"],
            "after":  ["t1", "t3"],
            "added":   ["t3"],
            "removed": ["t2"],
        },
        ...
    },
}
```

Why both `plan` and `per_target`: `plan` is what the user asked for;
`per_target` reflects what actually changed on each target (a row
that already had `tag2` removed sees an empty `removed` list).

**new_project** (single target):
```python
{
    "created_path": Path,
    "source": str,                  # "empty" | "git" | "local" | "downloaded" | "download"
    "template": str | None,
    "initial_tags": list[str],
    "post_commands": list[str],
    "after_create": str,            # "open" | "stay" | ...

    # Full inputs that drove the decision — the same Namespace that
    # plan_and_apply_one consumed (see ui/actions/project_create.py).
    "inputs": {
        "raw_input": str | None,    # what the user typed
        "explicit_name": str | None,
        "mode": str | None,         # builtin source key chosen
        "child_key": str | None,    # custom child source key
        "tmp": bool | None,
        "timestamp": bool | None,
        "ts_name": bool | None,
        "alpha_name": bool | None,
        "ask_name": bool | None,
        "ask_source": bool | None,
        "archive": bool | None,
        "multi": str | None,
    },

    # The resolved plan object (read-only) so hooks can inspect the
    # exact steps applied. Whatever `format_summary(plan)` summarizes
    # is available structurally here.
    "plan": dict,
}
```

**delete** (multiple targets):
```python
{
    "removed_paths": [Path, ...],   # same as [t.path for t in ctx.targets]
    # Full snapshot of each deleted project's metadata at delete time
    # — duplicates HookTarget.base_meta but indexed by path for ease.
    # A post-delete hook is the only place this data still exists.
    "removed_snapshots": {
        Path: {
            "name": str,
            "archived": bool,
            "tags": list[str],
            "properties": list[str],
            "description": str,
            "wip": bool,
            "suffix": str | None,
            "packed": bool,
            "base_meta": dict,      # full raw .base.yaml
        },
        ...
    },
}
```

Same data is intentionally reachable two ways
(`ctx.targets[i].base_meta` and `change.removed_snapshots[path]`).
Standard plugin-style convenience — hook authors pick whichever feels
natural for their iteration pattern.

### Side effects (post-event)

A post-event hook's return value is **ignored**. All output goes
through `ctx` callables:

- `ctx.add_event(path, kind, payload)` — primary channel. Streams
  event-log entries to a specific project. Use this both for progress
  events ("started", "step_done") and for completion
  ("hook_done"). Each call writes immediately to `.base.yaml` via
  `metadata.api.append_base_log`.
- `ctx.notify(text, level)` — surfaces a status-line message (TUI:
  `_set_runtime_status`; CLI: stderr). Level: `info|warn|error`.
- `ctx.log(text, level)` — debug log (TUI: `_log`; CLI: stdout).
  Routes through the same error-counted log path.

The dispatcher emits its own framing events around the hook run so
the side panel doesn't depend on the hook remembering to do it:

- `hook_started` (event-log entry with hook name + timing)
- `hook_done` (with duration + exception summary if any)

A hook can still emit its own `hook_done` if it wants a richer
payload — the dispatcher's entry is the fallback.

### Pre-event hooks (design, not implemented in v1)

Pre-event hooks differ from post-event hooks in three load-bearing
ways:

1. They run **before** the file operation. They can cancel it or
   mutate its inputs.
2. They are **synchronous** from the dispatcher's perspective —
   they must finish before the op proceeds.
3. They may **block on user input** via `ctx.ask(...)`.

Contract:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PreResult:
    decision: str                       # "proceed" | "cancel" | "mutate"
    reason: str = ""                    # surfaced to UI/CLI on cancel
    mutated_change: dict | None = None  # replaces ctx.change when "mutate"
```

A pre-event hook returns either `None` (= proceed unchanged) or a
`PreResult`. The dispatcher:

- Runs each pre-hook sequentially.
- If any returns `decision == "cancel"`, the operation aborts and
  the reason is surfaced. No further pre-hooks run; no file op
  happens; no post-hooks fire.
- If `decision == "mutate"`, the dispatcher merges
  `mutated_change` into the running `change` dict before the next
  pre-hook (and the eventual op) sees it.
- Mutation scope is event-specific and conservative — e.g.
  `rename` allows mutating `new_path`/`new_name` but not
  `old_path`; `new_project` allows mutating `initial_tags`,
  `template`, `post_commands` but not `source` once decided.
  Each event documents its mutable keys when pre-hooks are wired up.

`ctx.ask(...)` for pre-hooks (TUI: pushes a modal screen and
suspends the worker thread until the answer comes back via
`call_from_thread`; CLI: reads from stdin). Signature TBD when
implementing; sketch:

```python
ctx.ask(
    prompt="Confirm rename to {new_name}?",
    kind="yes_no" | "text" | "choice",
    choices=[...],          # for "choice"
    default=None,
) -> str | None             # None = cancelled
```

Why pre-events are pinned in v1 design even without implementation:
the dispatcher loop, config namespace (`hooks_pre:`), folder layout
(`bundled/pre/...`), `HookContext.timing` field, and `ctx.ask`
slot all need to exist from day one — otherwise migrating from a
post-only world later means rewriting every trigger site.

Note: the file op waits **only as long as the pre-hook itself runs**.
A fast pre-hook returning `None`/`proceed` adds milliseconds; a slow
one (or one that calls `ctx.ask`) is the only case where the user
notices a wait. The hook decides; the dispatcher just holds the op
until the decision is in.

---

## Dispatch (UI)

Trigger sites (existing code that needs to call the dispatcher):

| Event       | UI site                                                |
|-------------|--------------------------------------------------------|
| rename      | `ui/actions/item_edits.py::on_rename_item`             |
| tag_change  | `ui/actions/tag_actions.py::on_pick_tags`              |
|             | `ui/actions/tag_actions.py::rename_tag_globally`       |
|             | `ui/actions/tag_actions.py::delete_tag_globally`       |
| new_project | `ui/actions/project_create.py::on_new_project_submit`  |
| delete      | `ui/actions/bulk_dispatch.py::on_confirm_bulk` (action="delete") |

Each site wraps the existing op like this:

```python
# 1. PRE: synchronous (blocks the action; UI loop stays responsive)
pre_outcome = hooks_runtime.dispatch_pre(
    app,
    event="rename",
    targets=[snapshot_target(source_row)],
    change={"old_path": current, "new_path": target, ...},
)
if pre_outcome.cancelled:
    _rename_abort(app, pre_outcome.reason or "cancelled by hook")
    return
change = pre_outcome.change  # may have been mutated

# 2. Run the actual op (existing code) using the (possibly mutated)
#    change dict.
...

# 3. POST: fire-and-forget; runs in background.
hooks_runtime.dispatch_post(
    app,
    event="rename",
    targets=[snapshot_target(updated_row)],
    change=change,
)
```

The dispatcher:

1. Resolves the hook spec list for `(timing, event)` from
   `ctx.hook_specs`.
2. Filters by `views`, by enabled.
3. For each hook: pre-flight binary checks (`REQUIRES`), then runs.
   - Pre-hooks run sequentially on a single worker thread; the
     trigger site waits via `threading.Event` for the outcome.
   - Post-hooks run sequentially on a single worker thread per
     event firing; trigger site does not wait.
4. Worker runs `run(ctx)` with stdout/stderr captured.
5. Worker streams `add_event`/`notify`/`log` calls back via
   `app.call_from_thread(...)`; main-thread handler applies them.
6. `_busy_start("hook: <timing>/<event>/<name>")` on dispatch start;
   `_busy_stop()` on hook finish. Multiple concurrent post chains →
   nested busy depth (existing pattern handles this).

Hooks for the same event+timing run **sequentially**. Ordering is
load-bearing (e.g. "rebuild git remote" before "notify webhook").

### Slow-hook detection (replaces timeout)

No hard timeout, no kill. Instead: if a hook runs longer than
`slow_warn_s` (default 30s, configurable per hook), the dispatcher
emits a `notify(..., level="warn")` saying "hook X has been running
N seconds". The warning re-fires every `slow_warn_s` seconds until
the hook completes. The hook is never interrupted. Surfaces both in
TUI (status line) and CLI (stderr).

### Failure modes

- Hook raises uncaught exception → captured, routed to
  `app._show_runtime_error(f"hook {name}", exc, traceback_tail=...)`.
  For post-hooks: subsequent hooks still run. For pre-hooks: the
  exception is treated as `decision="cancel"` with the exception
  message as the reason. The op is aborted.
- Hook tries to mutate `ctx.targets` (it's frozen) → AttributeError,
  caught and logged as a hook bug.
- A pre-hook that hangs forever blocks the operation forever (by
  design: no timeout). The user sees the "still running" warning
  every `slow_warn_s` and can either wait or cancel the action via
  the modal/Ctrl+C (CLI).

---

## Dispatch (CLI)

The same events fire from CLI: `b new`, `b rm` (`workspace.cmd_rm`),
tag updates via `b` interactive flow. Same dispatcher, different
result sinks:

- `ctx.add_event` → same `append_base_log` call
- `ctx.notify` → stderr, prefixed `[hook]`
- `ctx.log` → stdout

CLI status line: at hook start the dispatcher prints to stderr

```
[hook] pre/rename/validate_branch_name … running
```

and on completion (or every `slow_warn_s` while still running):

```
[hook] pre/rename/validate_branch_name done in 0.4s
[hook] post/delete/cache_purge still running (32s)
```

If stderr is a TTY, the "running" line is rewritten in place with
`\r` so the output stays compact. Non-TTY: each event prints on
its own line.

Pre-hooks run synchronously on the calling thread (no extra
threading). Post-hooks: for CLI we **also** run them synchronously
on the calling thread — there's no event loop to keep responsive,
and the caller often parses the command's exit status to detect
completion. A long post-hook simply delays the CLI return; the
status line keeps the user informed.

`ctx.ask` in CLI: pre-hook prompts read from stdin via the existing
`prompt_yes_no` helper for yes/no, plain `input()` for text/choice.

---

## Bundled hooks (initial set)

These ship in v1 by porting existing in-tree behavior into the hook
system. They validate the contract by exercising it on real code,
and they remove duplicate side-effect glue from the trigger sites.

| Timing | Event       | Name               | Replaces / does                                                       |
|--------|-------------|--------------------|-----------------------------------------------------------------------|
| post   | rename      | `notes_rename`     | Note-sync rename logic in `item_edits._sync_note_on_project_rename`   |
| post   | rename      | `tag_symlink_sync` | `cleanup_tag_symlinks_pointing_at` + `_request_tag_sync`              |
| post   | tag_change  | `tag_symlink_sync` | `app._request_tag_sync("tag update")`                                 |
| post   | new_project | `tag_symlink_sync` | Tag sync on creation                                                  |
| post   | delete      | `tag_symlink_sync` | Tag sync on delete                                                    |
| post   | delete      | `cache_purge`      | `cache_delete_paths` on removed paths                                 |

Per the user's request (open-question #6): port **both**
`notes_rename` and `tag_symlink_sync` in v1.

Order of execution at the rename trigger site (post): `notes_rename`
first (file move), then `tag_symlink_sync` (relinks). Listed in
config in that order so the user can see it.

If a bundled hook can't be expressed cleanly under this contract,
the contract has a gap — fix the contract, don't special-case the
hook.

---

## Side-panel surface

A new tab under **Info** (`SIDE_CHILD_TABS["info"]`): `hooks`. Shows:

- Configured hooks grouped by event, with `enabled`/`disabled`,
  source, and last-run timestamp + outcome.
- Last 20 hook events (event, hook name, duration, ok/fail).

State for this lives on the app instance:
`app.hook_recent: dict[str, list[HookRunRecord]]` (per event,
trimmed to N). Filled from the dispatch result handler.

---

## Implementation phases

1. **Skeleton** — package layout (`hooks/`, `hooks/bundled/{pre,post}/...`),
   `api.py` (HookContext, HookTarget, PreResult), `loader.py`,
   `runtime.py` with stub dispatcher, config schema parsing
   (`hooks_pre:` + `hooks_post:`), tests for config parsing. No
   trigger sites wired up yet.
2. **Threading + UI sink (post)** — wire post dispatcher into
   `rename` end-to-end. Spinner, side-panel `hooks` tab,
   `add_event`/`notify`/`log` routing. Slow-hook warning.
3. **All four events wired (post)** — extend to tag_change /
   new_project / delete. Per-event `change` builders at each trigger
   site. Pre-event slots are stubbed (`dispatch_pre` returns
   "proceed" immediately, since no pre-hooks exist).
4. **Custom hook loader** — discover `.homebase/hooks/post/...`,
   load via `importlib`, capture stdout/stderr, error-route.
   Custom pre folders are scanned but ignored (warning if non-empty)
   until phase 7.
5. **Bundled registry + port two bundles** — port `notes_rename`
   and `tag_symlink_sync` to bundled post-hooks. Remove duplicate
   inline logic from trigger sites.
6. **CLI dispatch path** — same runtime, different result sink.
   Stderr status line. Synchronous post-hooks.
7. **Pre-event implementation** — flesh out `dispatch_pre`,
   `PreResult`, `ctx.ask` (TUI modal + CLI stdin). Wire one pre-hook
   bundled to validate (e.g. `confirm_delete` if useful).
8. **Docs** — extend `docs/` with a hooks reference parallel to
   `docs/actions.md`.

Each phase shippable independently. Phase 1 is mostly pure-data and
has the highest test coverage payoff. Phase 7 is the only phase
that adds new UX surface (modal) and may slip without blocking the
rest.

---

## Tests

Per `AGENTS.md` §9: one test module per source module.

- `tests/test_hooks_loader.py` — config parsing (both `hooks_pre:`
  and `hooks_post:`), bundled/custom resolution, missing-file errors
  (raise, don't auto-disable), unknown bundled-name errors,
  malformed entries.
- `tests/test_hooks_runtime.py` — dispatch ordering, slow-warn
  emission, error containment, `add_event`/`notify`/`log` routing,
  pre-hook cancel/mutate semantics. Uses `tmp_path` for the custom
  hook dir and real `importlib` loads.
- `tests/test_hooks_api.py` — `HookContext` / `HookTarget` snapshot
  correctness, helper closures stay valid across the worker
  boundary.
- Integration: existing rename/tag/new/delete tests get empty
  `hooks_pre:` / `hooks_post:` config (zero-impact pass), then a
  second pass with a one-line hook that asserts payload shape +
  event-log entry.

No mocks for filesystem (`tmp_path`). Hook timing tests use a
controlled `Event`/`Barrier` to drive deterministic threading.

---

## Resolved decisions

| Decision |
|----------|
| Hooks fire from both TUI and CLI |
| Always batch dispatch; hook handles per-target iteration |
| Pre/post split via top-level keys `hooks_pre:` / `hooks_post:` |
| Only `ctx.add_event` (+ `notify` / `log`); no return-value side effects |
| No timeouts. Slow-hook warning re-fires every `slow_warn_s` (default 30s, warns in UI) |
| Port both `notes_rename` and `tag_symlink_sync` in v1 |
| Snake_case for event ids and folder names |
| `views: [active, archive]` list; empty/omitted = both |
| Reload config but not hook modules; warn user to restart TUI |
| Hooks must be listed in config; orphan files ignored |
| Stream notifications; dispatcher adds framing events |
| Minimal `HookContext` in v1; expand when a hook needs it |
| Pre-events designed in v1, implemented in phase 7 |
| Bundled hooks live under `bundled/` |
| Missing file / unknown bundled name → hard fail on config load; `b` refuses to start |
| Pre-hook on delete does not strip the existing CLI confirm prompt — keep both |
| Delete payload exposes data both via `ctx.targets` and `change.removed_snapshots` (intentional convenience duplication) |
| Pre-hooks hold the file op only as long as the hook itself runs; fast hooks add no perceivable wait |

## Deferred to phase 7 (pre-event impl)

- Per-event mutation allowlist (which keys in `change` a pre-hook may rewrite).
- Exact `ctx.ask(...)` signature (kinds, default handling, cancel semantics).

## Open questions

None right now. Design is ready to break into implementation
tickets per the "Implementation phases" section above.

---

# Implementation plan (detailed)

This section is written for a step-by-step executor. Each phase is
self-contained: it lists every file to add/edit, every symbol to
introduce (with type signatures), every integration anchor in
existing code, the tests to write, and the verification commands to
run before the phase is considered done.

## Conventions for the executor

Read once and apply throughout:

- **Paths are absolute** in this plan
  (`/Users/xeor/base/homebase/src/homebase/...`). Use them verbatim.
- **AGENTS.md rules are binding.** In particular:
  - No `except Exception:` / bare `except:`. Catch concrete types.
    Alias recurring catch tuples in `core/utils.py`.
  - Keep `try` blocks narrow.
  - No backwards-compat shims, no "previously…" comments, no
    "Phase X will…" comments.
  - No emojis in code/docs.
  - Constants shared across modules go in `core/constants.py`.
  - One test module per source module: `tests/test_<topic>.py`.
- **Layering** (from AGENTS.md §5): `hooks/` imports
  `core/`, `config/`, `metadata/` only. It must not import from
  `ui/`, `cli/`, `commands/`. The dispatcher takes the `app`
  instance as `Any`-typed argument (it cannot type-import it).
- **After each phase**: run both, both must be clean.
  ```
  uv run ruff check src/homebase/ tests/
  uv run pytest
  ```
- **Commits** are not part of this plan — do not commit unless the
  human asks. (See `feedback_no_git_actions` memory.)
- **Do not refactor outside the listed files** unless explicitly
  called out. A change "leaks" if it touches a file not in the
  current step.
- Existing trigger sites continue to do all the original work.
  Hook dispatch is **added around** them; existing side effects stay
  in place until phase 5 explicitly removes them.

---

## Phase 1 — Skeleton (no UI wiring yet)

**Goal:** Hook package exists, config parses, types are defined.
No trigger site calls the dispatcher yet. Empty config = zero impact.

### 1.1 Add constants

Edit `/Users/xeor/base/homebase/src/homebase/core/constants.py`.
Append a new block near the other top-level constant groups (after
`BASE_META_ALLOWED_KEYS`):

```python
HOOK_EVENTS: tuple[str, ...] = (
    "rename",
    "tag_change",
    "new_project",
    "delete",
)
HOOK_TIMINGS: tuple[str, ...] = ("pre", "post")
HOOK_VIEWS: tuple[str, ...] = ("active", "archive")
HOOK_SLOW_WARN_DEFAULT_S: float = 30.0
```

### 1.2 Add dataclasses to `core/models.py`

Append to `/Users/xeor/base/homebase/src/homebase/core/models.py`:

```python
@dataclass(frozen=True)
class HookSpec:
    timing: str                    # "pre" | "post"
    event: str                     # in HOOK_EVENTS
    name: str
    source: str                    # "bundled" | "custom"
    enabled: bool
    views: tuple[str, ...]         # subset of HOOK_VIEWS; () means all
    config: dict[str, object]
    slow_warn_s: float

@dataclass(frozen=True)
class HookTarget:
    path: Path
    name: str
    archived: bool
    tags: list[str]
    properties: list[str]
    description: str
    wip: bool
    suffix: str | None
    packed: bool
    base_meta: dict[str, object]
    last_modified_ts: int
    created_ts: int
    archived_ts: int
    git_branch: str
    git_dirty: str

@dataclass(frozen=True)
class HookRuntime:
    invoker: str                   # "tui" | "cli"
    homebase_version: str
    now_iso: str
    now_ts: int
    user: str

@dataclass(frozen=True)
class HookInfo:
    name: str
    source: str
    timing: str
    event: str
    config: dict[str, object]

@dataclass(frozen=True)
class PreResult:
    decision: str                  # "proceed" | "cancel" | "mutate"
    reason: str = ""
    mutated_change: dict[str, object] | None = None

@dataclass(frozen=True)
class PreOutcome:
    cancelled: bool
    reason: str
    change: dict[str, object]      # possibly mutated
```

`HookContext` is **not** in `core/models.py` — it lives in
`hooks/api.py` (see 1.3) because it carries injected callables.

### 1.3 Create `hooks/api.py`

Create `/Users/xeor/base/homebase/src/homebase/hooks/__init__.py`
(empty file).

Create `/Users/xeor/base/homebase/src/homebase/hooks/api.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..core.models import HookInfo, HookRuntime, HookTarget, PreResult

HookResult = None  # type alias for clarity in user code

AskCallable = Callable[..., "str | None"]
AddEventCallable = Callable[[Path, str, dict[str, object]], None]
NotifyCallable = Callable[[str, str], None]
LogCallable = Callable[[str, str], None]


@dataclass(frozen=True)
class HookContext:
    event: str
    timing: str
    view: str
    base_dir: Path
    targets: tuple[HookTarget, ...]
    change: dict[str, object]
    runtime: HookRuntime
    hook: HookInfo
    add_event: AddEventCallable
    notify: NotifyCallable
    log: LogCallable
    ask: AskCallable
```

`targets` is a tuple (frozen) — hooks can iterate but not mutate.

Re-export the key symbols in `hooks/__init__.py`:

```python
from .api import HookContext  # noqa: F401
from ..core.models import HookSpec, HookTarget, HookRuntime, HookInfo, PreResult, PreOutcome  # noqa: F401
```

### 1.4 Create `config/hooks.py`

Create `/Users/xeor/base/homebase/src/homebase/config/hooks.py`,
mirroring the style of `config/property_defs.py`:

```python
from __future__ import annotations

from pathlib import Path

from ..core.constants import (
    HOOK_EVENTS,
    HOOK_SLOW_WARN_DEFAULT_S,
    HOOK_TIMINGS,
    HOOK_VIEWS,
)
from ..core.models import HookSpec
from .store import load_global_config_dict


class HookConfigError(ValueError):
    """Raised on malformed or unresolvable hook config."""


def load_hook_specs(base_dir: Path) -> dict[tuple[str, str], list[HookSpec]]:
    raw = load_global_config_dict(base_dir)
    out: dict[tuple[str, str], list[HookSpec]] = {
        (timing, event): [] for timing in HOOK_TIMINGS for event in HOOK_EVENTS
    }
    for timing in HOOK_TIMINGS:
        key = f"hooks_{timing}"
        section = raw.get(key, {}) if isinstance(raw, dict) else {}
        if section is None:
            continue
        if not isinstance(section, dict):
            raise HookConfigError(f"{key!r} must be a mapping")
        for event, items in section.items():
            event_id = str(event).strip()
            if event_id not in HOOK_EVENTS:
                raise HookConfigError(
                    f"unknown hook event {event_id!r} under {key!r}"
                )
            if items in (None, []):
                continue
            if not isinstance(items, list):
                raise HookConfigError(
                    f"{key!r}.{event_id!r} must be a list"
                )
            out[(timing, event_id)] = [
                _parse_spec(timing, event_id, idx, item) for idx, item in enumerate(items)
            ]
    return out


def _parse_spec(timing: str, event: str, idx: int, item: object) -> HookSpec:
    if not isinstance(item, dict):
        raise HookConfigError(
            f"hooks_{timing}.{event}[{idx}] must be a mapping"
        )
    name = str(item.get("name", "")).strip()
    if not name:
        raise HookConfigError(
            f"hooks_{timing}.{event}[{idx}] is missing `name`"
        )
    source = str(item.get("source", "custom")).strip()
    if source not in {"bundled", "custom"}:
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: source must be `bundled` or `custom`"
        )
    enabled = bool(item.get("enabled", True))
    views_raw = item.get("views", [])
    if not isinstance(views_raw, list):
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: `views` must be a list"
        )
    views: list[str] = []
    for v in views_raw:
        text = str(v).strip()
        if text and text not in HOOK_VIEWS:
            raise HookConfigError(
                f"hooks_{timing}.{event}.{name}: unknown view {text!r}"
            )
        if text:
            views.append(text)
    config_raw = item.get("config", {})
    if not isinstance(config_raw, dict):
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: `config` must be a mapping"
        )
    slow_warn = item.get("slow_warn_s", HOOK_SLOW_WARN_DEFAULT_S)
    try:
        slow_warn_s = float(slow_warn)
    except (TypeError, ValueError) as exc:
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: invalid `slow_warn_s`: {exc}"
        ) from exc
    return HookSpec(
        timing=timing,
        event=event,
        name=name,
        source=source,
        enabled=enabled,
        views=tuple(views),
        config=dict(config_raw),
        slow_warn_s=max(1.0, slow_warn_s),
    )
```

Note: this parser does **not** verify that `name` resolves to a real
file or registry entry. That check lives in the loader (1.5) so the
spec object stays pure data.

### 1.5 Create `hooks/loader.py`

Create `/Users/xeor/base/homebase/src/homebase/hooks/loader.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from ..core.constants import HOMEBASE_DIR_NAME, HOOK_EVENTS, HOOK_TIMINGS
from ..core.models import HookSpec
from ..config.hooks import HookConfigError


_BUNDLED_REGISTRY: dict[tuple[str, str, str], ModuleType] = {}


def resolve_hook_module(spec: HookSpec, base_dir: Path) -> ModuleType:
    if spec.source == "bundled":
        return _load_bundled(spec)
    return _load_custom(spec, base_dir)


def _load_bundled(spec: HookSpec) -> ModuleType:
    key = (spec.timing, spec.event, spec.name)
    cached = _BUNDLED_REGISTRY.get(key)
    if cached is not None:
        return cached
    module_path = f"homebase.hooks.bundled.{spec.timing}.{spec.event}.{spec.name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise HookConfigError(
            f"bundled hook not found: {spec.timing}/{spec.event}/{spec.name} ({exc})"
        ) from exc
    if not hasattr(module, "run"):
        raise HookConfigError(
            f"bundled hook {spec.timing}/{spec.event}/{spec.name} missing `run` function"
        )
    _BUNDLED_REGISTRY[key] = module
    return module


def _load_custom(spec: HookSpec, base_dir: Path) -> ModuleType:
    file_path = (
        base_dir
        / HOMEBASE_DIR_NAME
        / "hooks"
        / spec.timing
        / spec.event
        / f"{spec.name}.py"
    )
    if not file_path.is_file():
        raise HookConfigError(
            f"custom hook file not found: {file_path}"
        )
    module_name = f"_homebase_custom_hook_{spec.timing}_{spec.event}_{spec.name}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    module_spec = importlib.util.spec_from_file_location(module_name, file_path)
    if module_spec is None or module_spec.loader is None:
        raise HookConfigError(f"could not load custom hook: {file_path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except (SyntaxError, ImportError) as exc:
        sys.modules.pop(module_name, None)
        raise HookConfigError(
            f"custom hook {file_path} failed to load: {exc}"
        ) from exc
    if not hasattr(module, "run"):
        sys.modules.pop(module_name, None)
        raise HookConfigError(
            f"custom hook {file_path} missing `run` function"
        )
    return module


def verify_all_specs(
    specs: dict[tuple[str, str], list[HookSpec]], base_dir: Path
) -> None:
    """Resolve every spec at startup; raise on first failure."""
    for spec_list in specs.values():
        for spec in spec_list:
            if not spec.enabled:
                continue
            resolve_hook_module(spec, base_dir)
```

`verify_all_specs` is what enforces the "hard fail on config load"
decision.

### 1.6 Create `hooks/runtime.py` (stub)

Create `/Users/xeor/base/homebase/src/homebase/hooks/runtime.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.models import HookTarget, PreOutcome


def dispatch_pre(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> PreOutcome:
    return PreOutcome(cancelled=False, reason="", change=dict(change))


def dispatch_post(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> None:
    return None
```

Phase 1 stub: both dispatchers are no-ops. Phase 2 fills them in.

### 1.7 Wire into `RuntimeConfig` and `UIContext`

Edit `/Users/xeor/base/homebase/src/homebase/core/runtime_init.py`:

1. Add to `RuntimeConfig` dataclass (around line 10):
   ```python
   hook_specs: dict[tuple[str, str], list[Any]]
   ```
2. Add to `load_runtime_config` signature:
   ```python
   load_hook_specs: Callable[[Path], dict[tuple[str, str], list[Any]]],
   ```
3. In the `RuntimeConfig(...)` return (around line 58), add:
   ```python
   hook_specs=load_hook_specs(base_dir),
   ```

Edit `/Users/xeor/base/homebase/src/homebase/ui/context.py`:

1. Add to `UIContext` (after `cache_profile_table`):
   ```python
   hook_specs: dict[tuple[str, str], list[object]] = field(default_factory=dict)
   ```
2. Update `build_ui_context` to populate `hook_specs={}` (empty for the
   in-tree default constants snapshot).

Edit `/Users/xeor/base/homebase/src/homebase/cli/entry.py`:

1. Import `load_hook_specs`:
   ```python
   from ..config.hooks import load_hook_specs
   ```
2. Pass it to `load_runtime_config(...)` (around line 175).
3. Add `hook_specs=dict(runtime_cfg.hook_specs)` to the
   `UIContext(...)` constructor (around line 185).
4. Immediately after loading runtime_cfg, call:
   ```python
   from ..hooks.loader import verify_all_specs
   try:
       verify_all_specs(runtime_cfg.hook_specs, base_dir)
   except HookConfigError as exc:   # import this from ..config.hooks
       print(f"hook config error: {exc}", file=sys.stderr)
       return 1
   ```

### 1.8 Tests

Create `/Users/xeor/base/homebase/tests/test_config_hooks.py`:

Required cases:
- Empty config → all 8 `(timing, event)` keys present, all empty lists.
- One bundled rename pre-hook with all fields → parsed correctly.
- Missing `name` → `HookConfigError`.
- Unknown event id → `HookConfigError`.
- Bad `views` entry → `HookConfigError`.
- Non-mapping `config` field → `HookConfigError`.
- Invalid `slow_warn_s` → `HookConfigError`.
- Default `slow_warn_s` = 30.0 when omitted.

Create `/Users/xeor/base/homebase/tests/test_hooks_loader.py`:

Required cases:
- Custom hook with `def run(ctx): ...` → loaded module has `run`.
- Custom hook file missing → `HookConfigError`.
- Custom hook with syntax error → `HookConfigError`.
- Custom hook without `run` function → `HookConfigError`.
- Bundled hook that doesn't exist → `HookConfigError`.
- `verify_all_specs` raises on first bad entry.

Use `tmp_path` for the custom-hook tests. Build the file
structure (`<tmp>/.homebase/hooks/post/rename/foo.py`) inside each
test.

### 1.9 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest tests/test_config_hooks.py tests/test_hooks_loader.py -v
uv run pytest                       # full suite, must still pass
b ls                                 # smoke test: startup still works
```

**Definition of done:** all tests green; `b` starts on a fresh
workspace with no `hooks_*` keys (config parses to empty dicts); `b`
starts on a workspace with a malformed `hooks_pre:` and exits with a
clear error.

---

## Phase 2 — Post dispatcher + rename wired (TUI only)

**Goal:** one event end-to-end. `dispatch_post` actually runs hooks
on a worker thread; `ctx.add_event` / `notify` / `log` route to the
app; slow-warn timer works; side-panel "hooks" tab shows last runs.

### 2.1 Implement `dispatch_post`

Replace the stub in
`/Users/xeor/base/homebase/src/homebase/hooks/runtime.py`.

Required behavior:
- Resolve spec list for `("post", event)` from `app.ctx.hook_specs`.
- Filter: `spec.enabled` True; `view` is in `spec.views` (or
  `spec.views == ()`).
- For each surviving spec, resolve the module via `loader.resolve_hook_module`.
- Spawn a single `threading.Thread` that runs all hooks for this
  event sequentially.
- For each hook in the thread:
  - Build a `HookContext` with closures that call `app.call_from_thread`
    to apply `add_event` / `notify` / `log` on the main thread.
  - Start a `threading.Timer(spec.slow_warn_s, _emit_slow_warn)` that
    re-arms itself after firing (so it warns every `slow_warn_s`).
  - Call `module.run(ctx)`. Catch `(OSError, ValueError, TypeError,
    RuntimeError, KeyError, AttributeError)`. On exception, route
    through `app.call_from_thread(app._show_runtime_error, ...)`.
  - Cancel the timer when `run` returns/raises.
  - Append a framing event-log entry (`hook_started` before, `hook_done`
    after) — only for events where there's a sensible single target
    (rename has one, delete may have many; tag_change many). Skip
    framing for multi-target events to avoid log spam; emit a
    `notify` summary instead.
- Maintain `app.hook_recent` — append a `HookRunRecord` (define this
  small dataclass in `hooks/runtime.py`):
  ```python
  @dataclass(frozen=True)
  class HookRunRecord:
      timing: str
      event: str
      name: str
      duration_s: float
      ok: bool
      error: str
  ```
  Trim to last 20 entries per event.

Add to `core/utils.py` a recurring catch tuple:
```python
HOOK_RUN_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    RuntimeError,
    KeyError,
    AttributeError,
)
```
Import and use it in `runtime.py`.

### 2.2 Snapshot helper

Create `/Users/xeor/base/homebase/src/homebase/hooks/snapshot.py`:

```python
def snapshot_target(row: ProjectRow, base_meta: dict[str, object]) -> HookTarget: ...
```

Convert a `ProjectRow` + a freshly-loaded `.base.yaml` dict into a
frozen `HookTarget`. All list fields are copied (`list(row.tags)`).
For non-row contexts (e.g. snapshotting before delete), the caller
loads `base_meta` via `metadata.api.load_base_data(path)` first.

### 2.3 BApp state and helpers

Edit `/Users/xeor/base/homebase/src/homebase/ui/app.py`:

1. In `_init_*_state` group, add a new `_init_hooks_state(self)`:
   ```python
   self.hook_recent: dict[tuple[str, str], list[HookRunRecord]] = {}
   self.hook_running: dict[str, float] = {}   # spec_id -> started_ts
   ```
   Call it from `__init__` like the other init helpers.

2. No new BApp methods required for v1 routing — the dispatcher
   reaches into `app._log`, `app._set_runtime_status`,
   `app._busy_start`, `app._busy_stop` directly via closures.

### 2.4 Side-panel "hooks" tab

Edit `/Users/xeor/base/homebase/src/homebase/core/constants.py`:

In `SIDE_CHILD_TABS["info"]`, append `("hooks", "Hooks")` before the
final closing of the list.

Create `/Users/xeor/base/homebase/src/homebase/ui/side/hooks_panel.py`:

```python
def render_hooks_panel(app) -> str: ...
```

Pure function that returns the rendered text given:
- `app.ctx.hook_specs` — configured hooks
- `app.hook_recent` — last runs

Output: two grouped sections — "Configured" (timing/event/name/
source/enabled/views) and "Recent runs" (last 20).

Wire into the side-panel renderer (find the dispatch table for
`side_info_tab` in `ui/side/` — likely `ui/side/info.py` or
`ui/side/render.py`). Add a branch for `child_key == "hooks"`.

### 2.5 Trigger site: rename

Edit `/Users/xeor/base/homebase/src/homebase/ui/actions/item_edits.py`,
`on_rename_item` (starts at line 177):

After the rename has succeeded (after `app._upsert_row_local(updated)`,
line ~253, and after `_sync_note_on_project_rename(...)` line ~260),
add the post dispatch:

```python
from ...hooks import runtime as hooks_runtime
from ...hooks.snapshot import snapshot_target

hooks_runtime.dispatch_post(
    app,
    event="rename",
    targets=[snapshot_target(updated, load_base_data(updated.path))],
    change={
        "old_path": current,
        "new_path": target,
        "old_name": current.name,
        "new_name": target.name,
    },
    view=app.view_mode,
)
```

Imports go at the top of the file. `load_base_data` is already
imported via `metadata.api` somewhere — verify and import as needed.

### 2.6 Tests

Create `/Users/xeor/base/homebase/tests/test_hooks_runtime.py`:

Required cases (synchronous tests using `threading.Event` to wait
for the worker thread to finish):

- Dispatch with empty spec list → no thread spawned, no error.
- One post-hook that calls `ctx.notify("hi", "info")` → main thread
  observes a `_set_runtime_status` call.
- One post-hook that calls `ctx.add_event(path, "k", {...})` →
  `.base.yaml` event log gains an entry.
- Hook raises → exception captured, subsequent hooks still run,
  `hook_recent` records `ok=False` with error text.
- Two hooks in order → execution is sequential, `hook_recent` shows
  both with correct order.
- `views=["archive"]` hook + `view="active"` dispatch → hook skipped.
- Slow-warn fires after `slow_warn_s` (use a tiny value like 0.1s).

These tests need a stand-in for `app`. Build a minimal stub:

```python
class FakeApp:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.ctx = SimpleNamespace(hook_specs={...})
        self.hook_recent = {}
        self.hook_running = {}
        self.view_mode = "active"
        self.notifications = []
        # ... implement _log, _set_runtime_status, _busy_start,
        # _busy_stop, _show_runtime_error, call_from_thread
        # — call_from_thread can just execute inline for tests
```

Add an integration test in
`/Users/xeor/base/homebase/tests/test_actions_item_edits.py` (or
existing equivalent) that calls the rename flow and asserts a
post-hook is dispatched with the right `change` payload. If no such
test file exists, create one with a single happy-path test.

### 2.7 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest tests/test_hooks_runtime.py -v
uv run pytest
b                                    # smoke: rename a project, check
                                     # "Hooks" tab shows the run
```

**Definition of done:** A custom post-hook configured under
`hooks_post.rename` fires when a project is renamed; its
`ctx.notify` shows in the status line; its `ctx.add_event` lands in
`.base.yaml`. Empty config → zero observable change.

---

## Phase 3 — All four events wired (post)

**Goal:** `dispatch_post` called from every trigger site, with the
correct `change` payload per the event spec earlier in this doc.

### 3.1 tag_change

Edit `/Users/xeor/base/homebase/src/homebase/ui/actions/tag_actions.py`,
`on_pick_tags` (line 162). After the final `app._refresh_side()`
(line ~235), dispatch:

- `targets` = each successfully updated row → `snapshot_target(...)`.
- `change`:
  ```python
  {
      "plan": plan,                       # the dict passed in
      "per_target": {
          path: {
              "before": before_tags,      # captured pre-loop
              "after": after_tags,
              "added": sorted(set(after) - set(before)),
              "removed": sorted(set(before) - set(after)),
          }
          for path, (before, after) in ...
      },
  }
  ```
- Capture `before` tags inside the for-loop before mutation.

Same treatment for `rename_tag_globally` (line 50) — the "event" is
still `tag_change`; build a synthetic plan `{old_tag: "remove",
new_tag: "add"}` and per-target diffs.

Same for `delete_tag_globally` (line 98) — synthetic plan
`{tag: "remove"}`.

### 3.2 new_project

Edit `/Users/xeor/base/homebase/src/homebase/ui/actions/project_create.py`,
`on_new_project_submit` (line 82). After `app._upsert_row_local(new_row)`
(line ~157, in the `if after_create != "open"` branch), and before
the `return` in the `after_create == "open"` branch (line ~152),
dispatch:

```python
hooks_runtime.dispatch_post(
    app,
    event="new_project",
    targets=[snapshot_target(new_row, load_base_data(created))],
    change={
        "created_path": created,
        "source": ns.mode or ns.child_key or "auto",
        "template": ns.template or None,
        "initial_tags": list(payload.get("tags") or []),
        "post_commands": list(payload.get("post_commands") or []),
        "after_create": after_create,
        "inputs": {
            "raw_input": raw_input,
            "explicit_name": explicit_name,
            "mode": ns.mode,
            "child_key": ns.child_key,
            "tmp": ns.tmp,
            "timestamp": ns.timestamp,
            "ts_name": ns.ts_name,
            "alpha_name": ns.alpha_name,
            "ask_name": ns.ask_name,
            "ask_source": ns.ask_source,
            "archive": ns.archive,
            "multi": ns.multi,
        },
        "plan": _plan_to_dict(plan_obj) if plan_obj is not None else {},
    },
    view=app.view_mode,
)
```

Add a small helper `_plan_to_dict(plan)` in the same file that
extracts plan fields as a plain dict (mirror `format_summary` but
structured, not text).

For the `after_create == "open"` branch the new project's row may
not exist yet — load the row eagerly:
```python
new_row = project_row(created, archived=False)
```
before the dispatch.

### 3.3 delete

Edit `/Users/xeor/base/homebase/src/homebase/ui/actions/bulk_dispatch.py`,
`on_confirm_bulk` (line 119). The `delete` branch is at line 224.

Snapshots must be captured **before** `delete_internal` is called,
because after deletion `.base.yaml` is gone. Modify the loop:

```python
elif action == "delete":
    pre_snapshot = snapshot_target(
        source_row_for(path),
        load_base_data(path),
    )
    delete_internal(app.base_dir, path, sync_tags=False)
    deleted_snapshots[path] = pre_snapshot   # collect for dispatch
    ...
```

After the `try/finally` block (line ~275), and before the final
`app._refresh_side()` (line ~290), dispatch:

```python
if action == "delete" and deleted_snapshots:
    hooks_runtime.dispatch_post(
        app,
        event="delete",
        targets=list(deleted_snapshots.values()),
        change={
            "removed_paths": list(deleted_snapshots.keys()),
            "removed_snapshots": {
                p: _snapshot_to_dict(s) for p, s in deleted_snapshots.items()
            },
        },
        view=app.view_mode,
    )
```

Helper `_snapshot_to_dict(t: HookTarget) -> dict` in
`hooks/snapshot.py`.

### 3.4 Stubs for pre at every trigger site

Even though pre-hooks aren't implemented until phase 7, add the
`dispatch_pre` call **before** every op so the call sites are ready.
Since phase 1 stub returns `PreOutcome(cancelled=False, ...)`, the
behavior is unchanged. Pattern at each site:

```python
pre_outcome = hooks_runtime.dispatch_pre(
    app, event="rename", targets=[...], change={...}, view=app.view_mode,
)
if pre_outcome.cancelled:
    _abort_for_this_site(app, pre_outcome.reason)
    return
change = pre_outcome.change   # use this for the actual op
```

### 3.5 Tests

Extend `tests/test_hooks_runtime.py` with cases for the new payload
shapes (tag_change `per_target`, new_project `inputs`, delete
`removed_snapshots`). Add a test per event verifying that the
payload schema matches the spec earlier in this doc.

### 3.6 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
b                                    # smoke: rename, tag, new, delete
```

**Definition of done:** Each of the four events fires a post-hook
when one is configured; payloads match the schema; existing
behavior is unchanged with empty config.

---

## Phase 4 — Custom hook loader exposure

**Goal:** users can drop a `.py` into `.homebase/hooks/post/<event>/`,
list it in config, and have it run. (Phase 1 already wrote the
loader; this phase exercises it end-to-end and adds stdout/stderr
capture.)

### 4.1 Capture stdout/stderr

In `hooks/runtime.py`, wrap each `module.run(ctx)` call with
`contextlib.redirect_stdout` / `redirect_stderr` to an `io.StringIO`.
After return, if captured text is non-empty, route through
`ctx.log(captured, "info")`.

### 4.2 Custom-pre warning

When `verify_all_specs` runs and encounters a `pre` custom spec, the
loader succeeds (phase 1) but the dispatcher (phase 1 stub) ignores
it. Until phase 7, emit a one-time startup warning:

```python
[hook] pre hooks are configured but not yet supported in this build (will be in v1.x). 1 spec ignored.
```

Add this to `cli/entry.py` after `verify_all_specs`.

### 4.3 Tests

Add to `tests/test_hooks_runtime.py`:
- A custom hook writes to stdout → captured and routed through `log`.
- A custom hook raises a `ValueError` → captured, error recorded,
  next hook still runs.

### 4.4 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
# create .homebase/hooks/post/rename/say_hi.py with a one-liner hook
b                                    # rename → see say_hi's notify
```

**Definition of done:** A user-authored custom post-hook runs with
the same semantics as a bundled hook.

---

## Phase 5 — Port `notes_rename` and `tag_symlink_sync` to bundled

**Goal:** remove duplicate side-effect logic from trigger sites by
porting two existing in-tree behaviors into bundled hooks.

### 5.1 `notes_rename`

Create `/Users/xeor/base/homebase/src/homebase/hooks/bundled/__init__.py`
(empty), then `bundled/post/__init__.py`,
`bundled/post/rename/__init__.py`, and finally
`bundled/post/rename/notes_rename.py`:

```python
def run(ctx):
    change = ctx.change
    # Re-implement what _sync_note_on_project_rename does in
    # ui/actions/item_edits.py (lines 274-323). Use ctx.notify on
    # failure, ctx.add_event on success.
```

Edit `/Users/xeor/base/homebase/src/homebase/ui/actions/item_edits.py`:
remove `_sync_note_on_project_rename` and its call site (lines ~260
and 274-323). The call has been replaced by the bundled hook.

### 5.2 `tag_symlink_sync`

Bundled hook locations:
- `bundled/post/rename/tag_symlink_sync.py`
- `bundled/post/tag_change/tag_symlink_sync.py`
- `bundled/post/new_project/tag_symlink_sync.py`
- `bundled/post/delete/tag_symlink_sync.py`

Each calls `metadata.api.sync_tag_symlinks(base_dir)` (and for
rename/delete, additionally `cleanup_tag_symlinks_pointing_at`
before the full sync).

Remove the corresponding `app._request_tag_sync(...)` calls from:
- `ui/actions/item_edits.py::on_rename_item` (line ~259)
- `ui/actions/tag_actions.py::on_pick_tags` (line ~208)
- `ui/actions/tag_actions.py::rename_tag_globally` (line ~90)
- `ui/actions/tag_actions.py::delete_tag_globally` (line ~132)
- `ui/actions/project_create.py::on_new_project_submit` (lines ~150, ~167)
- `ui/actions/bulk_dispatch.py::on_confirm_bulk` (line ~280)

The dispatch_post call replaces them.

### 5.3 Default config

If the workspace config has no `hooks_post.<event>` entry for a
ported behavior, the user loses the side effect. Two options:

- (a) Make the loader inject default bundled specs when keys are
  absent (opaque "defaults"). User can disable explicitly.
- (b) Update workspace bootstrap (`b init` or first-run) to write
  the defaults into config.

**Pick (a)** — less surprising for users with old configs. In
`config/hooks.py::load_hook_specs`, after parsing, merge in
`_DEFAULT_BUNDLED_SPECS` if the user hasn't specified anything for
that `(timing, event)` slot. Document in the file.

### 5.4 Tests

Update `tests/test_actions_item_edits.py` (or equivalent) to expect
that the rename test triggers `notes_rename` via the hook system —
the test file move now happens inside the hook, not in
`on_rename_item`.

Add a test that confirms `tag_symlink_sync` runs after a tag change
and produces the expected symlinks.

### 5.5 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
b                                    # smoke: rename a project with
                                     # a NOTES.md file; verify the
                                     # note moves with it. Tag-change
                                     # smoke: verify _tags/ symlinks
                                     # update.
```

**Definition of done:** No `_sync_note_on_project_rename` or
`_request_tag_sync` calls remain in trigger sites. Default config
loads the bundled hooks transparently.

---

## Phase 6 — CLI dispatch path

**Goal:** `b new`, `b rm`, etc. fire hooks too. Synchronous, with
stderr status line.

### 6.1 Synchronous variant of the dispatcher

In `hooks/runtime.py`, add a parameter to `dispatch_post`:
```python
def dispatch_post(app, *, ..., synchronous: bool = False) -> None:
    ...
```

When `synchronous=True`, run the hook chain on the calling thread.
Replace `app.call_from_thread(fn, ...)` with direct calls. CLI
trigger sites pass `synchronous=True`.

For the CLI invoker, `app` is a small adapter object with the same
method names but stdout/stderr-routing implementations. Create
`/Users/xeor/base/homebase/src/homebase/hooks/cli_app.py`:

```python
class CLIHookApp:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.ctx = ...   # populated from runtime_cfg
        self.view_mode = "active"
        self.hook_recent = {}

    def _log(self, msg: str, level: str = "info") -> None:
        print(msg, file=sys.stderr if level in {"warn", "error"} else sys.stdout)

    def _set_runtime_status(self, text: str, level: str = "info", ttl_s: float = 12.0) -> None:
        print(f"[hook] {text}", file=sys.stderr)

    def _busy_start(self, label): pass
    def _busy_stop(self): pass
    def _show_runtime_error(self, context, exc, traceback_tail=""): ...
    def call_from_thread(self, fn, *args, **kw): fn(*args, **kw)
```

### 6.2 Stderr status line

When the dispatcher starts a hook with `synchronous=True`, emit:
```
[hook] post/rename/notes_rename … running
```
On success / failure, emit a final line with duration. If
`sys.stderr.isatty()`, rewrite in place with `\r`.

### 6.3 CLI trigger sites

Edit `/Users/xeor/base/homebase/src/homebase/commands/workspace.py::cmd_rm`
(line 185). After the successful `delete_internal(...)` call (line
208), build a `CLIHookApp` and dispatch the `delete` post-hook
(snapshot must be captured **before** `delete_internal`).

Similar for `b new` flow (find in `commands/`; the CLI `cmd_new` is
wired in `cli/dispatch.py` line 64). Hook dispatch happens after
`plan_and_apply_one` succeeds.

Tag changes from CLI happen through the interactive flow
(`commands/interactive_flow.py`) — check whether the CLI exposes a
tag-edit path; if so, mirror the TUI pattern.

CLI rename: there's no `b mv` today. Skip rename for CLI in phase 6.

### 6.4 Tests

Create `/Users/xeor/base/homebase/tests/test_hooks_cli.py`:

- `CLIHookApp` routes notify→stderr, log→stdout.
- Synchronous dispatch runs hooks in order on the calling thread.
- Slow-warn output appears on stderr after the threshold.

Integration: invoke `cmd_rm` (via direct call, not subprocess) with a
configured delete hook → hook fires.

### 6.5 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
b rm <some/test/project>             # see [hook] stderr lines
b new tmpproj                        # same
```

**Definition of done:** `b rm` and `b new` fire post-hooks; user
sees `[hook] ...` lines on stderr; existing CLI behavior unchanged
with no hooks configured.

---

## Phase 7 — Pre-event implementation

**Goal:** wire `dispatch_pre` to actually run pre-hooks, support
cancel / mutate, implement `ctx.ask`.

### 7.1 Implement `dispatch_pre`

Replace stub in `hooks/runtime.py`:

- Resolve and filter specs for `("pre", event)` like post.
- Run each spec sequentially on a worker thread (for TUI) or
  in-line (for CLI / `synchronous=True`).
- For TUI: the trigger site calls `dispatch_pre` and `.wait()` on a
  `threading.Event` set when the chain finishes.
- For each hook:
  - Build a `HookContext` with timing=`"pre"` and an `ask` callable
    (see 7.2).
  - Call `module.run(ctx)`. Expected return: `None` | `PreResult`.
  - On `None` → treat as `PreResult("proceed")`.
  - On `decision="cancel"` → stop chain; final `PreOutcome.cancelled = True`.
  - On `decision="mutate"`:
    - Merge `mutated_change` into the running change dict per the
      event's mutation allowlist (see 7.3). Reject any key outside
      the allowlist with `ctx.log(...)` warning + skip the mutation.
  - On exception → treat as `decision="cancel"` with exception
    message; log via `_show_runtime_error`.

### 7.2 `ctx.ask` implementation

For TUI: when `ctx.ask(...)` is called from the worker thread, push
a modal via `app.call_from_thread(app.push_screen, ...)` and block
the worker on a `threading.Event` that the modal's callback sets
along with the answer.

The modal can reuse `BasicInputScreen`,
`MultilineInputScreen`, or `ChoicesScreen` from
`ui/screens/`. Pick whichever matches the `kind` argument.

For CLI: read from stdin. For `kind="yes_no"`, call
`prompt_yes_no` from `commands/workspace.py`. For `text`/`choice`,
use `input()` / `input()` + validation against `choices`.

### 7.3 Per-event mutation allowlist

In `hooks/runtime.py` add:

```python
_PRE_MUTATION_ALLOWED: dict[str, frozenset[str]] = {
    "rename": frozenset({"new_path", "new_name"}),
    "tag_change": frozenset({"plan"}),
    "new_project": frozenset({"initial_tags", "template", "post_commands", "after_create"}),
    "delete": frozenset(),     # no mutation allowed; cancel only
}
```

When merging `mutated_change`, only keys in the allowlist pass
through. Unauthorized keys → `ctx.log("ignoring unauthorized
mutation: ...", "warn")`.

### 7.4 Trigger sites — wire up `pre_outcome.change`

Phase 3 already added `dispatch_pre` calls with a passthrough stub.
Now those calls do real work. Each trigger site already uses
`pre_outcome.change` for the op, so no changes needed — verify by
testing.

### 7.5 Tests

Add to `tests/test_hooks_runtime.py`:

- Pre-hook returning `None` → outcome.cancelled=False, change unchanged.
- Pre-hook returning `PreResult("proceed")` → same.
- Pre-hook returning `PreResult("cancel", reason="nope")` →
  cancelled=True, reason="nope".
- Pre-hook returning `PreResult("mutate", mutated_change={...})` →
  allowed keys merged, unauthorized keys logged as warn and dropped.
- Pre-hook raises → treated as cancel.
- `ctx.ask("yes_no")` in CLI reads from stdin (use `monkeypatch`
  on `builtins.input`).

### 7.6 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
# Configure a pre-hook that asks "really rename?" on rename;
# observe modal in TUI and stdin prompt in CLI.
```

**Definition of done:** Pre-hooks can cancel and mutate operations;
`ctx.ask` works in both invokers; trigger sites respect the outcome.

---

## Phase 8 — Docs

**Goal:** user-facing reference doc.

### 8.1 Create `docs/hooks.md`

Mirror the structure of `docs/actions.md`. Sections:

- Model (events, timings, sources)
- Hook contract (`run(ctx)`, `HookContext` fields)
- Configuration (`hooks_pre:` / `hooks_post:` schema)
- Side effects (`ctx.add_event`, `notify`, `log`, `ask`)
- Per-event payloads (rename, tag_change, new_project, delete)
- Pre-event semantics (cancel, mutate, mutation allowlist per event)
- Bundled hooks (notes_rename, tag_symlink_sync)
- Failure modes (config errors hard-fail; runtime errors logged)
- Example custom hook

Cross-reference from `README.md` (one-line link) and from
`docs/kitchen-sink-config.md` (add `hooks_pre:` / `hooks_post:`
examples in the relevant section).

### 8.2 Verify

```
uv run ruff check src/homebase/ tests/
uv run pytest
```

**Definition of done:** `docs/hooks.md` exists and is accurate
against the as-implemented code.

---

## Cross-phase checklist (executor sanity)

Before starting any phase, confirm:

- [x] All previous phases' tests still pass.
- [x] `ruff` is clean.
- [x] No file outside the phase's listed paths has been edited.
- [x] No `# previously…` / `# Phase X will…` comments anywhere.
- [x] No re-export shim modules added.
- [x] No new files in `core/` other than additions to `constants.py`
      and `models.py` (per layering).
- [x] `hooks/` imports only from `core/`, `config/`, `metadata/`.
