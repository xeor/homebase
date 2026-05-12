# `b new` — unified project creation

Goal: collapse `b new` and `b migrate` into a single `b new` that auto-detects
the input type, supports name override, and is trivially extensible with new
input handlers.

---

## 1. Current state

- `b new` (parser.py:19, dispatch.py:58 → `workspace/projects.py:cmd_new`):
  launches the TUI with `start_new=True`. Interactive flow only.
- `b migrate [--archive] <path>...` (parser.py:54, dispatch.py:87 →
  `commands/archive.py:cmd_migrate` → `commands/workspace.py:cmd_migrate`):
  moves existing directories into `~/base/`, creates `.base.yaml`, appends
  `migration` log entry, syncs tag symlinks. Optional archive mode moves
  into `_archive/<year>/` with timestamped name.

Both die after `b new` becomes one command. The interactive TUI flow must
stay reachable (no-arg `b new`).

---

## 2. New surface

```
b new [<input>] [<name>] [mode-flag] [common-flags]
b n  ...
```

- `<input>`  optional. Filesystem path, git URL, or bare name.
- `<name>`   optional. Override for the final folder name under `~/base/`.
- mode-flag  optional, exclusive: `--local`, `--git`, `--empty`, `--archive`
             (today's `b migrate --archive`).
- common:    `--tag <tag>` (repeatable), `--no-open`, `--dry-run`, `--yes`,
             `--template <key>` (reuse `b c` templates).

No args → existing TUI new flow (unchanged).

Auto-detect rules, first match wins (override with mode-flag):

1. `<input>` ends in `.git` → git clone
2. `<input>` is a recognized git host URL (github.com, gitlab.com,
   bitbucket.org, codeberg.org, sr.ht, configurable list) → git clone
3. `<input>` is `git@host:owner/repo[.git]` SSH form → git clone
4. `<input>` resolves to an existing directory → migrate (move) into base
5. `<input>` is a bare token, not an existing path → create empty project
   named `<input>`
6. No `<input>` → interactive TUI (today's `cmd_new`)

Name resolution:

- Explicit `<name>` always wins (validated by `resolve_new_project_name`).
- Otherwise infer from input:
  - git: last URL path segment, strip `.git`
  - local dir: `path.name`
  - bare name: the input itself
- Conflict (`~/base/<name>` exists) → error with suggestion (`<name>-2`,
  date-prefix), no implicit overwrite.

For git inputs the clone target is `~/base/<name>/repo/` and `.base.yaml`
lives in `~/base/<name>/`. For local dir migration and bare-name empty
projects, `.base.yaml` sits at the project root.

---

## 3. Provider architecture

Single registry of "new sources" so adding a handler is one new file +
one registration. Lives in `src/homebase/workspace/new/`.

```
workspace/new/
├── __init__.py        # registry + dispatch
├── base.py            # Source protocol, NewPlan dataclass, NewResult
├── detect.py          # auto-detect: ordered match() across registry
├── name.py            # name inference, collision handling
├── git.py             # GitSource  (.git, host whitelist, ssh form)
├── local.py           # LocalDirSource  (existing directory → move)
├── empty.py           # EmptySource  (bare token → mkdir + marker)
├── interactive.py     # TUISource  (no-arg → existing flow)
└── archive.py         # ArchiveMigrateSource  (today's --archive)
```

`base.Source`:

```python
class Source(Protocol):
    key: str                      # "git", "local", "empty", ...
    def match(self, input: str | None, ns: Namespace) -> int:
        """Return confidence 0..100. Highest wins. 0 = skip."""
    def plan(self, input: str | None, name: str | None, ns: Namespace,
             ctx: NewContext) -> NewPlan:
        ...
    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        ...
```

`NewPlan` is pure data (source dir, target dir, clone url, tags, post
commands, signals shown to user). `apply()` is the only side-effecting
step and uses the shared helpers below.

Mode flags (`--git`, `--local`, `--empty`, `--archive`) bypass `detect`
and force one provider. Unknown combination (e.g. `--git` with a local
path) → fail before any disk action.

---

## 4. Shared helpers (reuse existing code)

- `resolve_new_project_name(...)`                    `workspace/projects.py`
- `ensure_base_marker(target)`                       `metadata/api.py`
- `save_base_tags(base_dir, target, tags)`           `metadata/api.py`
- `append_base_log(target, "creation"|"migration", payload)`
- `sync_tag_symlinks(base_dir)`                      `metadata/api.py`
- `cache_upsert_project_fast(base_dir, target)`      `cache/api.py`
- `run_post_commands(target, commands)`              `workspace/projects.py`
- `open_shell_in_dir(target)`                        `tmux/flow.py`

No new I/O primitives. Providers wire these together.

---

## 5. Per-provider behavior

### 5.1 EmptySource
- Input: bare token, no existing path, not URL-shaped.
- Action: `(~/base/<name>/).mkdir`, `ensure_base_marker`, write tags,
  `append_base_log("creation", {...})`, cache upsert.

### 5.2 LocalDirSource
- Input: path that resolves to existing dir.
- Refuse if already under `~/base/` (use `b a`/`b fix` instead).
- Action: `shutil.move(src, ~/base/<name>)`, `ensure_base_marker`,
  log `"migration"`, sync tag symlinks, cache upsert.
- Reuses today's `commands/workspace.py:cmd_migrate` plan/exec logic,
  refactored so a single-source migration is a one-liner.

### 5.3 GitSource
- Input: `.git` suffix, host whitelist match, or `git@…:…` SSH form.
- Layout: `~/base/<name>/` is the project, repo cloned into
  `~/base/<name>/repo/`. `.base.yaml` at the project root.
- Action: mkdir `~/base/<name>/`, `git clone <url> repo` (cwd =
  project root), `ensure_base_marker`, tags, log `"creation"` with
  `{"source": url, "kind": "git-clone"}`, cache upsert.
- Failed clone → roll back the empty project dir, do not leave a
  half-marker behind.
- Host whitelist is configurable: extend `core/constants.py` with
  `GIT_HOST_DOMAINS` (default github.com, gitlab.com, bitbucket.org,
  codeberg.org, git.sr.ht). User can override in prefs.

### 5.4 ArchiveMigrateSource
- Triggered only by `--archive`. Preserves today's `b migrate --archive`
  exactly: parse existing timestamp suffix if any, place under
  `_archive/<year>/`.

### 5.5 TUISource
- No input arg. Calls today's `cmd_new` (`workspace/projects.py:186`).
- Tags/`--no-open`/etc. are ignored in TUI mode (or surfaced as
  prefilled TUI state in a later iteration — out of scope here).

---

## 6. UX contract

```
$ b new
  → opens TUI

$ b new myproj
  → creates ~/base/myproj/ (empty + marker)

$ b new ./some-dir
  → moves ./some-dir → ~/base/some-dir/ (+ marker)

$ b new ./some-dir myproj
  → moves ./some-dir → ~/base/myproj/

$ b new https://github.com/foo/bar
  → mkdir ~/base/bar/, git clone https://github.com/foo/bar ~/base/bar/repo

$ b new https://github.com/foo/bar.git aprj
  → mkdir ~/base/aprj/, git clone <url> ~/base/aprj/repo

$ b new git@github.com:foo/bar.git
  → same as above, name = bar

$ b new path/to/dir myproj --tag wip --no-open
  → migrate with explicit tag, do not spawn shell

$ b new --archive ./old-thing
  → ~/base/_archive/<year>/<ts>_old-thing  (= today's b migrate --archive)

$ b new --dry-run https://github.com/foo/bar
  → print resolved plan, touch nothing
```

Default end-of-command behavior: print `created: <path>` and (unless
`--no-open`) `open_shell_in_dir(target)`, matching today's `b c`.

`--dry-run` prints the resolved provider, target, and post-actions.
`--yes` skips the confirm prompt.

Conflict policy: if target exists, fail with the suggested next name
the user can pass explicitly. No silent rename.

---

## 7. Parser / dispatch wiring

- parser.py:19 — replace `sub.add_parser("new")` with:
  ```python
  p_new = sub.add_parser("new")
  p_new.add_argument("input", nargs="?", default=None)
  p_new.add_argument("name", nargs="?", default=None)
  mode = p_new.add_mutually_exclusive_group()
  mode.add_argument("--local", action="store_true")
  mode.add_argument("--git", action="store_true")
  mode.add_argument("--empty", action="store_true")
  mode.add_argument("--archive", action="store_true")
  p_new.add_argument("--tag", action="append", default=[])
  p_new.add_argument("--no-open", action="store_true")
  p_new.add_argument("--dry-run", action="store_true")
  p_new.add_argument("--yes", action="store_true")
  p_new.add_argument("--template", default="")
  ```
- Add `n` alias: `sub.add_parser("n", parents=[p_new], add_help=False)`
  if argparse cooperates; otherwise expand inline. Update both
  dispatch.py and `cli/completion.py:_TOP_LEVEL_COMMANDS`.
- Remove `migrate` from parser + dispatch + completion. Keep
  `commands/workspace.py:cmd_migrate` for one cycle as the internal
  archive-mode worker called from `ArchiveMigrateSource`, then inline
  it once everything settles.
- dispatch.py: replace the two `if ns.command == "new"` /
  `"migrate"` branches with a single `cmd_new(ns, base_dir, cwd)`
  call that routes into the registry.
- cli/entry.py:323/330: drop `"migrate"` from the suppressed-error set,
  keep `"new"`.

---

## 8. Tests

`tests/test_new_*.py`, one per provider plus integration:

- `tests/test_new_detect.py` — `detect.match_source(...)` table tests:
  `.git` URL, bare github URL, ssh URL, existing dir under `tmp_path`,
  bare name, no-input, `--git` override on a local dir (error), etc.
- `tests/test_new_name.py` — name inference + collision suggestion.
- `tests/test_new_empty.py` — empty-project creation, idempotency
  guard on existing target, marker + tags written.
- `tests/test_new_local.py` — move from `tmp_path/src` into
  `tmp_path/base/...`, marker created, migration log appended,
  refuses if src already under base.
- `tests/test_new_git.py` — uses a local bare repo under `tmp_path`
  as the URL so the test never touches the network; verify clone
  lands at `~/base/<name>/repo`, marker at `~/base/<name>/`, creation
  log contains the URL.
- `tests/test_new_archive.py` — port the existing `b migrate
  --archive` cases so behavior is preserved.
- `tests/test_new_cli.py` — argparse parses each invocation form;
  mutually exclusive mode flags raise; `--dry-run` produces no fs
  side effects.

All tests use `tmp_path`. No mocks of fs or sqlite (AGENTS.md §9).

---

## 9. Migration / cleanup steps (commit order)

1. Add `workspace/new/` skeleton (`base.py`, `name.py`, empty registry).
   No behavior change yet. Lands with tests for `name.py` and
   `detect.py`.
2. Port empty-project creation into `EmptySource`. Wire `cmd_new(ns)`
   so `b new <name>` works; no-arg still goes to TUI. Old `b migrate`
   untouched.
3. Port `LocalDirSource` (single-path migrate). Update tests.
4. Port `GitSource` with host whitelist constant.
5. Port `ArchiveMigrateSource`. Remove `migrate` subcommand from
   parser, dispatch, completion, error suppression list. Update
   completion `_TOP_LEVEL_COMMANDS`.
6. Move TUI flow behind `TUISource`. `workspace/projects.py:cmd_new`
   becomes a thin shim calling the registry for the no-arg case.
7. Final pass: drop dead re-exports in `commands/archive.py`
   (`cmd_migrate`), remove the now-unused branches in
   `cli/dispatch.py`, prune `entry.py:330`.

Every step keeps `uv run pytest` and `uv run ruff check` green and is
shippable on its own (AGENTS.md §10).

---

## 10. Open questions (decide before step 1)

- Multi-path migration: today `b migrate a b c` accepts many paths.
  Drop in `b new` (one project at a time), or keep via repeated
  `<input>` positionals? Suggest **drop** — multi-path is rare and
  scriptable as a shell loop; one-arg-only keeps `<name>` override
  unambiguous.
- `b new <url>` without `.git` for a non-whitelisted host: hard fail,
  or fall through to "treat as bare name"? Suggest **hard fail** with
  hint to pass `--git` or add the host to the whitelist.
- Should `--template <key>` be allowed for git/local sources, or only
  for empty? Suggest **empty only** for now; templating an existing
  tree is a separate feature.
- `b new` with no input on a non-TTY: today's `cmd_new` already errors
  with "requires an interactive terminal". Keep that.
