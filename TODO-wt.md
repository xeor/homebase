# TODO-wt — Worktree Support in `b`

Status: design draft, not implemented. Iterate inline.

## 1. Goal

Make long-lived (and short-lived) git worktrees first-class projects
in homebase so they show up in the TUI with their own tags, WIP flag,
opened-time, description, notes, etc. Branch-as-worktree should feel
as native as cloning a new project.

Concrete shape: one repo with three checked-out branches becomes three
rows in `b`: `foo`, `foo-featx`, `foo-bugfixy`. Each row is
independent for tagging/filtering but knows its parent.

## 2. Worktrunk

Looked at worktrunk.dev as a possible backend. Decision: not used.
Native implementation, no compat layer, no escape-hatch shell-out, no
hooks framework borrowed. The research is parked.

## 3. Data model

### 3.1 Layout & naming

Worktrees are sibling project directories under `<base>/`. Separator
is `-` (not `.`). Branches containing `/` get `/` → `--` for the
directory name. The raw branch name still lives in `.base.yml`.

```
<base>/
├── foo/                  # main project (regular clone)
│   ├── repo/             # working tree, branch = main
│   └── .base.yml
├── foo-featx/            # worktree project
│   ├── repo/             # git worktree, branch = featx
│   └── .base.yml         # has a worktree: block (see §3.2)
└── foo-feature--auth/    # worktree, branch = feature/auth
    ├── repo/
    └── .base.yml
```

Name collisions: if `<parent>-<sanitised-branch>` already exists
under `<base>/` (any kind — worktree, regular project, anything),
`b new` errors out. No auto-suffix, no prompt. User must pick a
different branch name or remove the conflict.

### 3.2 `.base.yml` schema

Add a single new top-level key, `worktree`, as a dict. Presence of
this key means the project is a worktree. No separate `kind` field.

```yaml
# only present on worktree projects:
worktree:
  of: foo                                   # required: parent project name (dir under <base>/)
  branch: feature/auth                      # required: raw git branch, unescaped
  parent_path: /Users/x/base/foo/repo       # absolute path to the parent's repo dir at create/move time
  gitdir_id: feature-auth                   # the <id> git assigned under parent/.git/worktrees/<id>
```

Regular projects: no change, no `worktree:` key.

`of` and `branch` are required; `parent_path` and `gitdir_id` are
written by `b` at create time and rewritten on every move, archive,
or rename (see §7). They're only read by repair code (`b fix`,
unpack), never required for normal operation — but they make
relocations and packed-archive recovery deterministic instead of
heuristic.

Add `worktree` to `BASE_META_ALLOWED_KEYS` and to the schema
validator (`metadata/utils.py`). Validator must check `of` and
`branch` are non-empty strings; `parent_path` (if present) is an
absolute path string; `gitdir_id` (if present) is a non-empty
string.

Nothing is copied from the parent's `.base.yml` on creation —
tags, description, WIP are all set explicitly per worktree.

### 3.3 Git detection (`.git` file vs dir)

Two concrete code changes:

1. `workspace/projects.py:git_info()` currently does
   `(.git).is_dir()` and returns `("-", "-", 0)` otherwise. That
   skips every worktree. Change to `.exists()` and let `git -C`
   handle both cases.
2. The GIT column rendering visibly distinguishes worktree from
   regular repo using format **(a)**: `featx*  ↪foo`. Branch first,
   dirty marker, then `↪<parent>` suffix. Regular repos render as
   `main*` / `featx*` only.

The built-in `GIT` property (`dir-exists: [.git]`) stays as-is. We
add an example to `docs/kitchen-sink-config.md` showing how a user
can configure a property that matches either form, or both.

## 4. Filter syntax

Introduce a dynamic structured-filter syntax in the query bar,
separate from `#tag` and free-text. Form: `:<key><op><value>`.

### 4.1 Migration

Existing bare-key filters (`last=@-7d`, `created>=2025-01-01`,
`opened<2025-03`, etc.) move under the `:` prefix. No back-compat:
`last=@-7d` is removed, `:last=@-7d` is the only spelling. Update:

- parser in `filter/engine.py`
- pretty-printer / normaliser
- saved filters and named filters in default config
- `docs/kitchen-sink-config.md` and any other doc that shows the
  old syntax
- onboarding hints / placeholder text

Hard cut. No migration helper, no warning at startup, no auto-
rewrite. Any old-syntax entry left in a user's config silently
matches nothing — the user is expected to update their own config.

### 4.2 Operators

The query language parses all of `=`, `!=`, `<`, `<=`, `>`, `>=`,
`~` (glob/regex) at the token level. Only `=` is *implemented* in
v1; other operators are parsed and recognised but the engine emits
"operator X not implemented for key Y" as a non-fatal hint and the
term matches nothing. This way, the syntax is stable from day one
and we wire operators per-key as needed without grammar changes.

### 4.3 Registered keys (v1)

- `:created=@-7d`, `:opened<=2025-01-01`, `:last>=2025-03-01`, …
  — migrated time filters
- `:repo=foo` — umbrella: `foo` itself + every worktree of `foo`
- `:worktree-of=foo` — strict: worktrees only, excludes the parent

Filter engine in `filter/engine.py` gains a registry
`key → matcher(row, op, value) -> bool` so adding a key is one
entry. Unknown keys parse but match nothing, with a non-fatal hint
in the input area. Aligns with [[feedback_no_migration_blocks]].

### 4.4 Syntax highlighting

The query input renders `:key<op>value` tokens with three distinct
colours (key, operator, value), the same way `#tag` and free-text
tokens are already coloured. Unknown keys render with a dim/warning
colour to signal "this filter is parsed but won't match".

## 5. Creating worktrees — via `b new`

No dedicated `b wt new` subcommand. Worktree creation lives in the
existing `b new` source plumbing with a new source kind: `worktree`.

### 5.1 CLI

```sh
# from anywhere — pick parent explicitly:
b new <branch> --as worktree --from <parent-project>

# shortcut when cwd is inside a git project — auto-defaults
# to worktree, parent is the enclosing project:
b new <branch>
```

Auto-default rule for `b new <name>`:

- If `cwd` is inside a homebase project directory (walk up to find
  `.base.yml`) **and** that project has a working `.git` (file or
  directory), `--as worktree --from <enclosing>` is implied.
- If the enclosing project is itself a worktree, the new worktree's
  parent (administrative parent in git) is the *original* root
  project (follow `worktree.of` to resolve). Worktrees are never
  nested under worktrees; they all sit as siblings of the root
  project.
- Outside any project, or in a project without git, the auto-default
  is the existing one (empty/local/git/download based on `<input>`).
- To force a non-worktree project from inside a project dir, pass
  `--as empty` (or any explicit `--as` / built-in flag).

Path computation:

- Output: `<base>/<root-parent-name>-<sanitised-branch>/repo/`
- `.base.yml` written next to `repo/` with the §3.2 `worktree:`
  block, including `parent_path` and `gitdir_id`.

Branch handling:

- If the branch already exists locally, `git worktree add` checks
  it out into the new path.
- If the branch doesn't exist, the new branch is created from the
  **selected/cwd row's current branch**, not from the root
  parent's HEAD. That matches plain
  `git worktree add -b <new> <path>` semantics when run from
  inside the source worktree, and is the less surprising
  behaviour ("I'm working on `featx` and want to spin off a
  side-branch from here").
- The success message surfaces the actual base ref so the user
  sees what happened.

Constraints:

- Single-target only. Worktree creation never operates on a
  multi-selection.
- Hard error on directory-name collision (see §3.1).

### 5.2 TUI

Two TUI surfaces:

1. **`ctrl-n` (new project dialog).** No automatic pre-fill from
   the selected row. Behaves as today.
2. **New action: "New worktree".** Lives in the standard action
   list (`?` key, dispatch, etc.). Target scope, single-target.
   Opens the same dialog as `ctrl-n`, but pre-filled with:
   - source: `worktree`
   - parent: selected row's project name (chained to the root
     parent if the selected row is itself a worktree)
   - name field: empty, awaiting the branch name (the branch name
     drives both the new git branch and the computed directory
     name)

After creation, the post-create open/cd behaviour follows the
global `b new` default — no special case.

## 6. Removing worktrees — via existing delete

No dedicated `b wt rm`. The existing delete action learns to handle
worktree rows:

- Run `git worktree remove <path>` (or
  `git worktree remove --force` if the user confirms a dirty-tree
  force) instead of plain `rm -rf`.
- Clean up the parent repo's `.git/worktrees/<id>/` admin entry.
- Leave the branch alone by default. Branch deletion stays a manual
  git step until we have evidence it's wanted inside `b`.

### 6.1 Deleting a parent that still has worktrees

Show a warning that lists every worktree depending on this parent
and the action it implies (worktrees will become broken). If the
user accepts the warning, delete the parent and leave the worktrees
in place as **broken rows** (their gitdir pointer is now stale).
Broken rows surface a health warning in the info pane and are
candidates for `b fix` (§7.4) or the de-worktree action (§7.3).

The warning dialog also offers two alternatives, each one click
away:

- **De-worktree all first** — runs the de-worktree action (§7.3)
  on each worktree, turning them into standalone clones; then the
  parent can be deleted cleanly.
- **Move all together** — only relevant for archive-style
  deletes; see §7.2.

## 7. Reference integrity, moves, archive, repair

The hard part. A git worktree is held together by two pointers that
both contain absolute paths:

- `<worktree>/repo/.git` is a file with
  `gitdir: <absolute>/parent/.git/worktrees/<id>`
- `<parent>/.git/worktrees/<id>/gitdir` is a file with
  `<absolute>/worktree/repo/.git`

Any time `b` moves or archives a directory, those pointers must be
rewritten or the worktree silently breaks. All flows below must
work identically whether triggered from the TUI or the CLI — same
helper, same tests, no duplicate logic. Every successful rewrite
also updates `.base.yml`'s `worktree.parent_path` / `worktree.of`
to match.

**Pointer rewriting strategy**: prefer git's own commands —
`git worktree move` (atomic two-end rewrite for renames) and
`git worktree repair` (re-anchor every linked worktree of a repo).
We only hand-rewrite the pointer files when git's CLI genuinely
can't do the job (e.g. operations where both ends move together
and no individual `git worktree …` call covers it).

### 7.1 Rename / archive / move flows

1. **Renaming a worktree project** (`b mv foo-featx foo-newname`):
   `git worktree move <old-path> <new-path>`. If that fails, fall
   back to hand-rewriting the parent's `.git/worktrees/<id>/gitdir`.
2. **Archiving a worktree project**: same as rename, with the new
   path under `_archive/…`. The archived worktree must still be a
   working git repo when the user `cd`s into it.
3. **Renaming the parent project** (`b mv foo bar`): after the
   parent directory moves, run
   `git -C <new-parent>/repo worktree repair` to fix every linked
   worktree's `repo/.git`. Then walk every row with
   `worktree.of == foo` and update `worktree.of` and
   `worktree.parent_path` in their `.base.yml`.

### 7.2 Archiving the parent (with active worktrees)

Refuse the operation by default. The error message lists the
worktrees that block it and offers two actions:

- **De-worktree first** (recommended) — turn every worktree into
  a standalone clone (§7.3). After that, parent can be archived
  with no further consequence.
- **Move all together** — archive the parent and every worktree
  in one transaction. Worktrees land as flat siblings under the
  archive year:

  ```
  _archive/2026/2026-05-21_foo/
  _archive/2026/2026-05-21_foo-featx/
  _archive/2026/2026-05-21_foo-bugfixy/
  ```

  After the move, run the §7.1.3 rewrite (`git worktree repair`
  on the now-archived parent + `.base.yml` updates) so every
  archived worktree points at the archived parent.

### 7.3 De-worktree action (make worktree standalone)

A new action: takes a worktree row and turns it into a regular
standalone project. After the action runs, the row has no
`worktree:` key, its `repo/.git` is a real directory, and it has
no relationship to the former parent.

Method: **wholesale copy of the parent's `.git/` directory**
(option C in the prior round) — `rsync -a <parent>/.git/
<worktree>/repo/.git/` (or equivalent `cp -a`). This carries the
full history, reflog, stash list, hooks, packed refs, and every
branch ref across. Then:

1. Delete `<worktree>/repo/.git/worktrees/` from the new
   standalone — those admin entries are about the parent's other
   worktrees and would confuse git into thinking siblings exist.
2. Repoint `HEAD` to the worktree's branch (a worktree's own HEAD
   lived under `parent/.git/worktrees/<id>/HEAD` and isn't in the
   rsynced tree — we set it explicitly).
3. Detach the parent's `.git/worktrees/<id>/` admin entry
   (`git worktree remove --force` against the parent, but the
   worktree directory we just rebuilt is left untouched).
4. Strip `worktree:` from the worktree's `.base.yml`.

Stash list and branch refs are intentionally duplicated onto the
new standalone (cheap, reversible, matches "git clone" expectations);
the user can `git stash drop` or `git branch -d` either side
later. Confirm prompt mentions both.

The directory name is left unchanged. `foo-featx` still reads as
"worktree of foo on featx", but after de-worktreeing it's just a
historical artefact — the user can rename via `b mv` if they
care.

### 7.4 `b fix`

A new explicit subcommand and matching TUI action that audits and
offers to repair the worktree references in `<base>/`. Invokable
three ways:

- `b fix` (CLI, dry-run by default; `--apply` to mutate)
- TUI action in the standard action list, target scope = workspace
- Auto-detect: a periodic scan surfaces broken worktrees via the
  existing notification system as a **sticky** corner popup that
  persists until dismissed or until the issue resolves on the next
  scan. See §7.4.1 for the performance constraint.

#### 7.4.1 Startup-performance constraint

The auto-detect scan must not slow TUI startup. Concretely:

- The audit runs **after the first frame renders**, not before.
- Audit results are cached in the existing SQLite cache
  (`<base>/.homebase/cache.sqlite3`) under a new
  `worktree_health` table keyed by project path + `mtime` of the
  worktree's `repo/.git` and the parent's `.git/worktrees/<id>/`
  admin files. A project whose inputs haven't changed since the
  last scan is skipped.
- The startup pre-check reads the cache only and surfaces the
  popup based on the *previous* scan's result. A background task
  refreshes the cache on a low-priority schedule and the popup
  updates if the new scan flips the state.

Refresh cadence + budget:

- Each refresh tick has a **200 ms wall-clock budget**. Long
  workspaces are audited progressively across ticks; partial
  scans persist their cursor so the next tick resumes where the
  previous one left off, never restarting from zero.
- Refresh fires on **TUI startup** and then every **60 seconds
  while the user is idle**, reusing whatever idle signal the
  existing background-refresh code already exposes (no scans
  during active scrolling/typing).

#### 7.4.2 Scope

- For every project with a `worktree:` block, verify:
  - `<worktree>/repo/.git` exists and is a file
  - The file's `gitdir:` pointer resolves to a real directory
  - That directory lives under `<worktree.of>/repo/.git/worktrees/`
  - The reverse pointer
    `<parent>/.git/worktrees/<id>/gitdir` exists and points back
    at this worktree
- For every parent with worktrees:
  - Each `.git/worktrees/<id>/gitdir` points at an existing
    worktree directory that has a matching `.base.yml`
  - Detect "orphaned" admin entries (point at deleted paths)
- Relocated base folder: every `gitdir` pointer inside every
  worktree references an absolute path. If the user moved
  `<base>/` to a new absolute path, all pointers are stale.
  `b fix` detects this by comparing the current `<base>` against
  each `.base.yml`'s `worktree.parent_path` and rewrites stale
  pointers in one pass (via `git worktree repair` on each parent).
- Packed-archive recovery: unpacking a worktree (§7.5) leaves
  stale pointers. `b fix` recomputes them from `worktree.of` +
  `worktree.gitdir_id` + the current parent's
  `.git/worktrees/<id>/`. If the gitdir_id no longer exists in
  the parent, `b fix` recreates the admin entry on the parent
  side using `git worktree repair`.

Orphan recovery (worktree's `worktree.of` points at a project
that no longer exists under `<base>/`): if `worktree.parent_path`
still resolves to a git repo on disk (even outside `<base>/`),
`b fix` suggests de-worktreeing using that parent. Otherwise it
suggests dropping the `worktree:` block — making the row a
regular project — and lets the user reconnect git manually.

#### 7.4.3 UX rules

- Default mode is **dry-run**: list every issue and the fix that
  would be applied. Requires `--apply` (CLI) or explicit confirm
  (TUI) to mutate.
- Never silently rewrites paths inside `.git/`. Every fix is
  logged to the project's `.base.yml` `log:` array
  ([[feedback_no_git_actions]]).

Exit codes (documented):

| Code | Meaning                                              |
| ---- | ---------------------------------------------------- |
| 0    | Clean — no issues detected.                          |
| 1    | Dry-run found issues (no mutations attempted).       |
| 2    | `--apply` ran and at least one fix failed mid-write. |
| 3    | Invalid invocation — no `<base>`, bad CLI args, etc. |

Sticky-popup dismissal is **session-scoped**: once dismissed, the
popup stays hidden until the TUI process exits. The next launch
re-surfaces it if broken worktrees still exist. No persisted
dismissal state — simpler, and a per-launch reminder is
acceptable noise given how rarely this state should arise.

### 7.5 Packed archives (`.tar.zst` etc.)

Allow packing a worktree. The packed tarball will contain a stale
`repo/.git` file (gitdir pointer freezes a path that probably
won't exist on restore). Mitigations:

- **At pack time**, ensure `.base.yml` carries `worktree.of`,
  `worktree.branch`, `worktree.parent_path`, and
  `worktree.gitdir_id`. Emit a clear warning that the packed
  worktree depends on its parent existing at unpack time.
- **At unpack time**, detect that the unpacked dir is a worktree
  (has `worktree:` block) and that its `repo/.git` pointer is
  stale. Surface a "stale worktree, run `b fix`" notice; the
  §7.4 auto-detect popup will also surface this on next TUI
  startup. Do not auto-repair as part of unpack.
- `b fix` (§7.4) does the actual repair using the four fields
  above + the now-resolved parent location.

## 8. Risks and side-effects

- **Cache invalidation.** `git_info()` caches by
  `(refs_sig, head_sig)`. All worktrees of one repo share
  `.git/refs`, so any commit anywhere invalidates the row for
  every sibling worktree. Acceptable for v1; revisit if it
  becomes a hot path.
- **Tag symlinks.** A worktree and its parent can share tags. The
  symlink namer (`_safe_link_name`) already disambiguates by full
  project name, so `_tags/work/foo` and `_tags/work/foo-featx`
  coexist. Verify with a test.
- **Discovery prune.** Audit the walker so it doesn't treat a
  worktree's `.git` *file* as something special (current keying
  is on `.base.yml`, so probably fine — audit anyway).
- **Stale worktree rows.** A worktree directory can exist on disk
  while `git worktree list` no longer knows about it (e.g. the
  user ran `git worktree prune` manually). The row should still
  render, with a health warning + a suggestion to run `b fix`.

## 9. Implementation order

Each step ships independently and leaves the tool usable.

1. ~~**Fix `.git` detection.** `git_info()` and any siblings that
   special-case `.git` as a directory. Tests with a real worktree
   under `tmp_path`.~~ — `61cf16c`
2. ~~**Schema.** Add `worktree` (with `of`, `branch`, `parent_path`,
   `gitdir_id`) to `BASE_META_ALLOWED_KEYS` and the validator.
   Tests.~~ — `a764893`
3. ~~**GIT column rendering.** Format `featx*  ↪foo` for worktree
   rows. Tests with a row containing/lacking the `worktree:` block.~~ — pending commit
4. **Filter framework migration.** Move existing
   `created=`/`opened=`/`last=` to the `:` prefix. Parse all
   operators; implement only `=`. Add registry. Update parser,
   normaliser, pretty-printer, saved/named filters in defaults,
   docs. Hard cut, no migration helper.
5. **Filter keys.** Register `:worktree-of=` (strict) and
   `:repo=` (umbrella). Tests.
6. **`b new --as worktree`** (CLI) + auto-default rule when cwd is
   inside a git-enabled project. Chained-parent resolution.
   Branch forks from the selected/cwd row's branch (not the root
   parent's HEAD). Tests with real git, including a
   worktree-from-worktree fixture and parent-HEAD-detached
   fixtures.
7. **New action: "New worktree"** in the TUI action list,
   single-target, opens prefilled `ctrl-n` dialog.
8. **Delete-action wiring** for worktree rows
   (`git worktree remove` + admin cleanup). Parent-delete warning
   + "de-worktree first" / "move all together" alternatives
   (the de-worktree branch lands in step 10).
9. **Rename / archive pointer rewriting.** §7.1 items 1–3, single
   helper used from both CLI and TUI. Uses `git worktree move`
   and `git worktree repair`; falls back to hand-rewriting only
   when git's CLI can't do the job. Updates `worktree.of` /
   `worktree.parent_path` in `.base.yml` as part of each mutation.
   Tests for every code path that mutates a project's location.
10. **De-worktree action.** §7.3, rsync-of-`.git` method. CLI +
    action list entry. Tests.
11. **`b fix`.** §7.4. Audit + dry-run + `--apply` + documented
    exit codes + cached scan (§7.4.1) + sticky popup. Tests
    including a relocated-base-folder fixture and an
    orphan-worktree fixture.
12. **Packed archive flow.** §7.5. Warning on pack, detection on
    unpack, repair via `b fix`.

Items beyond 12 (merge, sync, prune, advanced status badges) are
parked until we see real friction.

## 10. Agent instructions — how to use this TODO

This section is for the AI agent (you) that is going to implement
the plan. Read it before touching code.

### 10.1 Before starting any step

1. **Re-read `AGENTS.md`** at both `/Users/xeor/base/AGENTS.md`
   and `/Users/xeor/base/homebase/AGENTS.md`. Conventions there
   (layering, error handling, no broad excepts, no backwards-
   compat shims, no comments referencing past state) override
   anything generic.
2. **Re-read this whole TODO.** Don't re-derive the design from
   scratch — every decision here was a back-and-forth and is
   the resolved answer. If you find a section that looks wrong
   or contradictory, ask before changing direction.
3. **Refresh the codebase view.** File paths and line numbers in
   §11 are pinned to a snapshot — verify with `grep`/`read`
   before relying on them. Rename/refactor in upstream code
   shifts them.
4. **Confirm the user wants this step now.** Don't open multiple
   steps in parallel; one step ships at a time, in order.

### 10.2 While implementing

- One step = one logical change set. Don't drag in unrelated
  refactors or drive-by cleanups (AGENTS rule).
- Keep `try` blocks narrow; catch only the exception types the
  call site actually raises. No `except Exception:` unless the
  user explicitly asks for a boundary handler.
- No comments that describe past state, the task, or what the
  caller does. Default to no comment.
- New built-in constants (paths, default fields, color hex,
  intervals) live in `core/constants.py`. Don't inline.
- Tests live next to the source module they cover:
  `tests/test_<topic>.py`. Use `tmp_path`, not mocks, for fs/git.
- Run after each change:
  - `uv run ruff check src/homebase/ tests/`
  - `uv run pytest -x --tb=short`
  Both must be green before the step is "done".
- Don't commit, push, or stash. Don't run `git worktree …`
  outside of test fixtures unless the user has approved it for
  this step. (See [[feedback_no_git_actions]].)

### 10.3 Keeping this TODO current

This document is the source of truth for the plan. Treat it
like code:

- When a step lands, **strike it through** in §9 and §11 (use
  `~~step text~~`) and add the commit SHA at the end of the
  line. Don't delete the entry — future readers want to see
  what shipped.
- If implementation surfaces a new constraint or a fact that
  invalidates a design decision, **edit the relevant section
  in place**. Fold the new decision into the prose; don't leave
  a "previously we said X" trail.
- If a question comes up mid-implementation that the user
  hasn't answered, add a `CLAUDE-COMMENT:` block at the
  relevant section with options and a default proposal, and
  stop until the user replies. Don't invent semantics they
  haven't approved.
- If a step turns out to be larger than one commit's worth,
  split it inside §11 (e.g. `11.6a`, `11.6b`) and update §9 to
  match.

### 10.4 Done criteria

A step is done when **all** of:

- Code is in place and matches this TODO's design (no drift).
- New tests exist and pass; existing tests still pass.
- `ruff check` is clean (the project rule: no per-file ignores).
- The TODO entry is struck through with the commit SHA.
- The user has explicitly approved a commit (per AGENTS git
  rules) — until then, work sits uncommitted.

## 11. Detailed action plan

One subsection per implementation step from §9. Each carries:
**files** (concrete paths to read/edit), **do** (the change),
**tests** (what to add under `tests/`), **gotchas** (anything
that has already bitten us in the design phase), **done when**
(verification checklist).

Pinned file references below are from a snapshot taken during
design; verify with `grep` before editing.

### ~~11.1 Fix `.git` detection~~ — `61cf16c`

**Files**

- `src/homebase/workspace/projects.py` — `git_info()` around
  line 332 has `if not git_dir.is_dir(): return "-", "-", 0`.
- Any sibling helper in the same file that also checks
  `(path / ".git").is_dir()` — grep first.

**Do**

- Replace the `is_dir()` gate with an `exists()` gate. The
  subsequent `git -C <path> branch --show-current` call works
  for both gitdir-dir and gitdir-file forms.
- If a helper distinguishes "regular repo" vs "worktree", read
  the `.git` entry: a plain file starting with `gitdir:` means
  worktree; a directory means regular.

**Tests**

- New `tests/test_worktree_git_detection.py`:
  - fixture: `tmp_path` with `git init`, one commit, then
    `git worktree add ../wt branch-x`.
  - assert `git_info()` returns `("branch-x", …)` for the
    worktree path, not `("-", "-", 0)`.
  - assert `git_info()` still returns the right thing for the
    main repo path.

**Gotchas**

- The `_git_state_signature()` helper uses `.git/refs` paths to
  build a cache key. For a worktree, the relevant HEAD/refs
  live partly under `parent/.git/worktrees/<id>/`. Audit; if
  the existing signature already produces a unique key from
  the worktree's perspective, leave it; if not, derive the
  parent's `.git/worktrees/<id>/HEAD` mtime instead.

**Done when**

- Tests pass, ruff clean, the row for a worktree directory
  shows its branch in the existing GIT column (without §11.3's
  parent suffix yet — that's the next step).

### ~~11.2 Schema additions~~ — `a764893`

**Files**

- `src/homebase/core/constants.py:469` — `BASE_META_ALLOWED_KEYS`.
- `src/homebase/metadata/utils.py` — `base_meta_schema_issues`
  and friends.

**Do**

- Add `"worktree"` to `BASE_META_ALLOWED_KEYS`.
- Extend `base_meta_schema_issues` to validate the `worktree:`
  block when present:
  - root must be a dict
  - `of` and `branch` required, both non-empty strings
  - `parent_path` optional; if present, must be a non-empty
    string and must be an absolute path
  - `gitdir_id` optional; if present, must be a non-empty string
  - unknown keys inside `worktree:` → `schema_warn` issue
    (non-fatal)
- Helpers to read/write the worktree block live in
  `metadata/api.py` next to `save_base_tags`/`save_base_wip`.
  Add `save_base_worktree(path, of, branch, parent_path,
  gitdir_id)` and `load_base_worktree(path) -> dict | None`.

**Tests**

- Extend `tests/test_metadata_*.py` (find the existing schema
  test file with `grep -l 'base_meta_schema_issues' tests/`):
  - valid `worktree:` block passes
  - missing `of` / missing `branch` → error issue
  - `parent_path: relative/path` → warning issue
  - unknown subkey → schema_warn

**Gotchas**

- `save_base_*` helpers must call `ensure_base_marker` then
  `load_base_data` (mirror existing pattern). Don't bypass.

**Done when**

- Schema accepts and validates the block. Read/write round-trip
  test passes.

### ~~11.3 GIT column rendering~~ — pending commit

**Files**

- `src/homebase/ui/table/render.py` — branch rendering block
  around lines 314–324 (`if row.branch in {"-", "?"}: …` else
  builds `git_text = f"{row.branch}{dirty_part}"`).
- `src/homebase/workspace/rows.py` — `ProjectRow` builder.
  Decide where the parent name is sourced from.
- `src/homebase/core/models.py` — `ProjectRow` dataclass.

**Do**

- Add `worktree_of: str = ""` field to `ProjectRow` (empty for
  non-worktree rows).
- In `workspace/projects.py` row construction, populate
  `worktree_of` from `.base.yml`'s `worktree.of` if the block
  exists, else `""`.
- In `ui/table/render.py`, after `git_text = f"{row.branch}
  {dirty_part}"`, if `row.worktree_of`, append
  `f"  ↪{row.worktree_of}"` (use a new constant
  `COLOR_WORKTREE_PARENT_HEX` in `core/constants.py` for the
  suffix style; pick a dim accent).
- Width: the GIT column default is 20 chars. Don't expand it;
  if `↪<parent>` overflows, the cell truncates as today.

**Tests**

- `tests/test_table_render_worktree.py`: build a `ProjectRow`
  with `worktree_of="foo"`, branch=`"featx"`, dirty=`"*"` and
  assert the rendered cell text contains `featx*` and `↪foo`.

**Gotchas**

- The arrow character `↪` (U+21AA) renders in Textual today
  (used in other places via Rich markup) but verify by eye:
  start the TUI in the dev workspace with a real worktree and
  visually confirm.

**Done when**

- Worktree rows render `featx*  ↪foo`; regular rows unchanged.

### 11.4 Filter framework migration

**Files**

- `src/homebase/filter/engine.py` — bare-key regex at lines 182,
  192, 312, 316. The token regex and the per-term matcher.
- `src/homebase/workspace/filter_compile.py` — `_FILTER_TOKEN_RE`
  and `compile_filter_expr`.
- `src/homebase/core/constants.py` — `NAMED_FILTERS` (defaults
  may reference `last=`/`created=`/`opened=`).
- `docs/kitchen-sink-config.md` — search/replace old syntax.
- README.md, any `tests/test_filter_*.py`.

**Do**

- Update the token regex so a token may carry a leading `:`.
- Introduce a `StructuredTerm` parse node: `(key, op, value)`
  for any token matching `^:([a-z][a-z0-9-]*)(=|!=|<=|>=|<|>|~)(.+)$`.
- Replace the bare-key time regexes (`last=…`, `created…`,
  `opened…`) with `StructuredTerm` handlers keyed by
  `:created`, `:opened`, `:last`.
- Introduce a `FILTER_KEY_REGISTRY: dict[str, Matcher]` where
  `Matcher = Callable[[ProjectRow, str, str], bool]`. Register
  the three time keys here.
- Operator semantics for v1: `=` calls the matcher with the
  literal operator string; other operators (`!=`, `<`, `<=`,
  `>`, `>=`, `~`) are accepted by the parser but the matcher
  returns `False` and the engine surfaces a hint via the
  existing "filter error" channel (find it with
  `grep -rn "filter_error\|compile_filter_expr.*error" src`).
- Unknown keys: parser accepts; matcher returns `False`; hint
  emitted.

**Tests**

- `tests/test_filter_structured.py`:
  - `:created=@-7d` matches a row with `created_ts` within 7d
  - `:opened<=2025-01-01` matches a row opened on/before
  - `:unknown=foo` parses, matches no row, emits a hint
  - `:created!=@-7d` parses, returns False, emits "operator not
    implemented" hint
  - syntax-highlight token kinds returned by the tokeniser
    distinguish key/op/value

**Gotchas**

- Bare-key form is gone in this commit. Old saved/named
  filters in user `config.yaml` silently match nothing — by
  design (§4.1), no warning.
- Pretty-printer / normaliser at `pretty_filter_expression`
  must round-trip the new form (write back as `:key=value`).

**Done when**

- All bare-key references are removed from src/ and docs/.
  `grep -rn 'last=@\|created=@\|opened=@' src/ docs/ README.md`
  returns nothing. Old tests rewritten to new syntax.

### 11.5 Filter keys for worktrees

**Files**

- `src/homebase/filter/engine.py` (or wherever §11.4 placed the
  registry).

**Do**

- Register two matchers:
  - `:worktree-of=<name>` → returns True if
    `row.worktree_of == name`.
  - `:repo=<name>` → returns True if `row.name == name` OR
    `row.worktree_of == name`.

**Tests**

- `tests/test_filter_worktree_keys.py`: rows = `[foo,
  foo-featx, foo-bug, bar]`. `:repo=foo` matches first three;
  `:worktree-of=foo` matches `foo-featx` and `foo-bug`;
  neither matches `bar`.

**Done when**

- Tests pass; query bar accepts both keys.

### 11.6 `b new --as worktree` (CLI)

**Files**

- `src/homebase/workspace/new/sources/` — add `worktree.py`
  next to `git.py`, `local.py`, `empty.py`, `download.py`,
  `downloaded.py`.
- `src/homebase/workspace/new/registry.py` — register the new
  source kind.
- `src/homebase/workspace/new/cmd.py` — auto-default detection
  (cwd walk-up for `.base.yml`, check for git, follow
  `worktree.of` chain).
- `src/homebase/workspace/new/detect.py` — input
  classification; ensure auto-default behaviour fits here, not
  duplicated in `cmd.py`.
- `src/homebase/cli/parser.py` — `--as` already exists
  (parser.py:11); make sure `--from <name>` is accepted (add
  if missing).
- `src/homebase/cli/completion.py` — extend the source-key
  completion list (already references `--as`, line 88, 200).

**Do**

- New source module `sources/worktree.py`:
  - inputs: `name` (branch), `from_project` (root parent name)
  - logic:
    1. resolve root parent: if `from_project` itself is a
       worktree, walk `worktree.of` until we hit a non-worktree
    2. sanitise branch into a dir-safe form (`/` → `--`)
    3. compute output dir
       `<base>/<root-name>-<sanitised>/repo`
    4. hard-error on collision (§3.1)
    5. determine base ref: cwd's enclosing project's *current
       branch* (`git -C <enclosing>/repo branch --show-current`).
       If detached, use HEAD's commit. Surface what was used
       in the success message.
    6. `git -C <root-parent>/repo worktree add -b <branch>
       <out>/repo <base-ref>` (or no `-b` if branch already
       exists — let git decide and check exit code)
    7. read git's chosen `<gitdir_id>` from the parent's
       `.git/worktrees/` listing (the newest entry pointing at
       our path)
    8. write `.base.yml` with `worktree.of`, `worktree.branch`
       (raw), `worktree.parent_path`, `worktree.gitdir_id`
- Auto-default rule in `cmd.py`:
  - find enclosing project (walk up for `.base.yml`)
  - if found AND `(enclosing / "repo" / ".git").exists()`
    (file or dir, post §11.1), imply
    `--as worktree --from <enclosing-name>`
  - explicit `--as <other>` always wins
- Single-target only: assert no multi-selection at the call
  site.

**Tests**

- `tests/test_new_worktree.py`:
  - create a base, a project with `git init`+commit, run
    `b new featx --as worktree --from foo`; assert dir
    `<base>/foo-featx/repo` exists, `.base.yml` carries the
    expected `worktree:` block.
  - branch with `/`: `b new feature/auth …`; assert dir is
    `foo-feature--auth`, `worktree.branch == "feature/auth"`.
  - auto-default: chdir into `<base>/foo/repo/sub`, run
    `b new x`; assert it created `<base>/foo-x/repo`.
  - worktree-from-worktree: chdir into `<base>/foo-featx/repo`,
    run `b new bugfix-y`; assert created
    `<base>/foo-bugfix--y/repo`, `worktree.of == "foo"`,
    new branch starts from `featx`.
  - collision: prep `<base>/foo-featx/`, run again; assert
    hard error and no mutation.

**Gotchas**

- `git worktree add -b X path Y` fails if X already exists; we
  handle that by *not* passing `-b` when the branch is already
  present locally.
- The `gitdir_id` git assigns is sometimes branch-name with
  slashes replaced (varies by version). Don't predict; read it
  back from `parent/.git/worktrees/` listing right after the
  add.

**Done when**

- CLI path works end-to-end; auto-default works; tests cover
  the four scenarios above + collision.

### 11.7 TUI "New worktree" action

**Files**

- `src/homebase/core/constants.py:81` — `BUILTIN_ACTIONS` dict;
  add an entry `"new_worktree"`.
- `src/homebase/ui/actions/` — find the dispatcher
  (`grep -rn 'BUILTIN_ACTIONS\[' src/homebase/ui/`); register a
  handler.
- `src/homebase/ui/screens/` — the new-project dialog screen
  (find with `grep -rln 'ctrl+n\|new_project_dialog\|NewProjectScreen'`).
  Add a way to open it with `source` and `parent` pre-filled.

**Do**

- New `BuiltinActionMeta`:
  - id: `new_worktree`
  - default_label: `New worktree`
  - scope: `target`
  - view_scope: `("active",)` — no point on archived rows
  - help_text: "Open the new-project dialog pre-filled to make
    a worktree from this project"
- Handler:
  - require single target; bail with user-visible error if
    multi-selection
  - resolve root parent (walk `worktree.of` chain like §11.6)
  - open new-project dialog with `source=worktree`,
    `parent=<root>`, name field empty

**Tests**

- Unit test the handler's pre-fill payload by faking the dialog
  open call.

**Done when**

- Action shows up in the action list, single-target only,
  pre-fills the dialog correctly. No regression in plain
  ctrl-n behaviour.

### 11.8 Delete-action wiring for worktree rows

**Files**

- `src/homebase/archive/ops.py` — current delete flow.
- `src/homebase/ui/actions/` — delete action handler.

**Do**

- When the row to delete has a `worktree:` block:
  - run `git -C <parent>/repo worktree remove <worktree>/repo`
    (use `--force` if the user has confirmed a dirty-tree
    force in the prompt)
  - this removes both the directory and the parent's admin
    entry in one call
  - do *not* `rm -rf` after — git already removed the path
- Parent-delete flow:
  - scan for rows with `worktree.of == <parent-name>`
  - if any exist, show a warning dialog listing them
  - dialog has three actions: cancel / proceed-orphan
    (delete parent, leave worktrees broken) / "de-worktree
    first" (runs §11.10 on each, then deletes parent) /
    "move all together" (only shown for archive variant —
    §11.9 path)

**Tests**

- `tests/test_delete_worktree.py`:
  - prep parent + 2 worktrees; delete one worktree; assert
    worktree dir gone, parent admin clean, other worktree
    still works.
  - prep parent + 1 worktree; attempt parent delete; assert
    warning fires; choose "proceed orphan"; assert parent
    gone, worktree row still listed but its `repo/.git`
    points at a missing path.

**Done when**

- Worktree rows delete via git; parent-delete warning lists
  blockers; all dialog paths work.

### 11.9 Rename / archive pointer rewriting

**Files**

- `src/homebase/archive/ops.py` — archive move flow.
- Wherever `b mv` lives — grep for the CLI handler
  (`grep -rn 'def.*mv\b\|"mv"' src/homebase/commands/ src/homebase/cli/`).
- New shared helper: `src/homebase/workspace/worktree_paths.py`
  with `move_project(old_path, new_path)` that does the
  right thing for worktree and parent rows.

**Do**

- Shared helper `move_project(old, new)`:
  - read `.base.yml`. If row has a `worktree:` block (the row
    is a worktree):
    - prefer `git worktree move <old>/repo <new>/repo`
    - on failure, hand-rewrite
      `parent/.git/worktrees/<id>/gitdir`
    - update `worktree.parent_path` if relative to base — it
      isn't, but rewrite anyway to keep it canonical
  - if the row is a *parent* (any child rows have
    `worktree.of == name`):
    - move the parent dir on disk
    - run `git -C <new>/repo worktree repair` to fix every
      linked worktree's `repo/.git`
    - walk all `worktree.of == old-name` rows; rewrite their
      `.base.yml` (`worktree.of`, `worktree.parent_path`)
  - otherwise (plain project): existing rename/move logic.
- `b mv` and archive both call this helper.

**Tests**

- `tests/test_worktree_move.py`:
  - rename worktree → both ends still resolve.
  - rename parent → all worktrees still resolve, `.base.yml`
    blocks updated.
  - archive worktree → still a working git repo from the
    archive path.
  - archive parent → blocked unless §11.10/together-flow
    invoked; together-flow moves whole family.

**Done when**

- Every move path goes through the helper. Worktrees survive
  rename + archive both for themselves and their parent.

### 11.10 De-worktree action

**Files**

- `src/homebase/workspace/deworktree.py` — new module.
- `src/homebase/commands/deworktree.py` — CLI handler.
- Action registration: `core/constants.py:BUILTIN_ACTIONS`
  (`make_standalone` or `deworktree`).

**Do**

- `deworktree(path)`:
  - read `.base.yml`; assert `worktree:` block exists
  - resolve `parent_path` (use `worktree.parent_path`; fall
    back to `<base>/<worktree.of>/repo`)
  - copy parent `.git/` → `<path>/repo/.git/` using
    `shutil.copytree(..., symlinks=True)` (avoid shelling out
    to rsync — pure stdlib is portable)
  - `rmtree(<path>/repo/.git/worktrees)` if present
  - `git -C <path>/repo symbolic-ref HEAD refs/heads/<branch>`
    using `worktree.branch`
  - `git -C <parent_path> worktree remove --force <path>/repo`
  - rewrite `.base.yml`: drop the `worktree:` block, keep
    everything else
- CLI: `b deworktree <project>` or `b worktree standalone
  <project>` (pick one and document).
- Confirm prompt mentions stash + branch ref duplication.

**Tests**

- `tests/test_deworktree.py`:
  - prep parent + worktree, make a commit in the worktree,
    `git stash` something in parent and worktree separately
  - run de-worktree
  - assert new standalone has its `.git` as a directory,
    `git status` works, the worktree-branch commit is present,
    the worktree's commit history is visible from the
    standalone, the parent's admin entry is gone
  - assert `.base.yml` no longer has `worktree:`

**Done when**

- After the action, the directory is a self-contained git
  repo, the parent has no record of it, the row renders as a
  regular project (no `↪parent` suffix).

### 11.11 `b fix`

**Files**

- `src/homebase/commands/fix.py` — new CLI handler.
- `src/homebase/workspace/health.py` — new audit helper (pure
  data, no I/O orchestration).
- `src/homebase/cache/store.py` — add `worktree_health` table.
- `src/homebase/cache/api.py` — read/write helpers for the new
  table.
- `src/homebase/ui/runtime_feedback.py` (or wherever toasts are
  fired) — surface the sticky popup.
- `src/homebase/ui/app.py` — schedule the post-first-frame
  audit.
- `core/constants.py` — `UI_TICK_HEALTH_REFRESH_S = 60`, etc.
- Action registration: `BUILTIN_ACTIONS` adds `fix_worktrees`.

**Do**

- Audit fn: given a list of project rows + their `.base.yml`
  contents, return a list of `WorktreeIssue(path, kind,
  fix_summary)` (kind: `stale_gitdir`, `orphan_admin`,
  `missing_parent`, `relocated_base`, …).
- Cache table schema:
  - key: project path
  - cols: last_scan_ts, inputs_mtime, issue_count, issue_list
    (json)
  - skip rescan if `inputs_mtime` matches current
    `(repo/.git, parent/.git/worktrees/<id>)` mtimes
- CLI `b fix` (dry-run by default):
  - print issues, propose fixes, exit per the documented
    table (0/1/2/3)
  - `--apply`: try each fix in turn, prefer `git worktree
    repair` and `git worktree move`; hand-rewrite only when
    git can't. Log to each row's `.base.yml log:` array.
- TUI integration:
  - background task scheduled by `app.py` after first frame
    renders. Budget: 200 ms per tick (deadline-based loop),
    persistent cursor.
  - cadence: at startup + every 60 s while idle (reuse the
    existing idle detector — find with `grep -rn 'idle' src/`).
  - when audit shows issues, fire the existing toast helper
    with `sticky=True` semantics (extend the toast helper if
    needed — should be a small change).
  - dismissal is session-only; nothing persisted.
  - action handler `fix_worktrees` opens a modal that lists
    issues and offers "apply".

**Tests**

- `tests/test_health_audit.py`: each issue kind has a fixture
  (relocated base, orphan admin, stale gitdir, missing parent,
  packed-archive-restored).
- `tests/test_b_fix_cli.py`: exit codes for clean / dry-run-
  dirty / apply-success / apply-failure / invalid invocation.
- `tests/test_health_cache.py`: cached result is returned when
  mtimes match; rescans when they change.

**Gotchas**

- Don't run the full audit inline on startup — defer until
  after the first frame, otherwise startup time slips.
- The "idle signal" already exists in the background refresh
  code (used for `cache_profile.update_interval_s`); find and
  reuse, don't invent.

**Done when**

- `b fix` works from CLI; sticky popup appears when issues
  exist; dismissal is session-only; documented exit codes
  honoured; startup is not measurably slower.

### 11.12 Packed-archive flow

**Files**

- `src/homebase/archive/io.py` — pack/unpack.
- `src/homebase/archive/ops.py` — surface warning during pack,
  detection during unpack.

**Do**

- On pack of a worktree row:
  - ensure `.base.yml` has full `worktree:` block (warn + abort
    if incomplete; user can re-run after running `b fix`)
  - emit a one-line stderr/log warning: "packed worktree is
    stale until restored next to its parent and `b fix` is
    run"
- On unpack of a worktree row:
  - if `worktree:` block present and `repo/.git` resolves to a
    non-existent target, surface a one-shot toast: "stale
    worktree, run `b fix`"
  - the §11.11 startup scan will then catch it on the next
    boot anyway
- `b fix` (§11.11) already handles the actual repair via
  `git worktree repair` + admin recreation. No new repair
  logic here.

**Tests**

- `tests/test_archive_worktree.py`:
  - pack a worktree row, assert tarball has full meta, assert
    warning emitted
  - unpack into a base where the parent exists at the right
    path → `b fix --apply` repairs it
  - unpack where parent is gone → `b fix` flags as orphan with
    `parent_path` fallback suggestion

**Done when**

- Pack/unpack works without surprising the user; `b fix` is
  the only path that actually rewrites pointers.

### 11.13 Closing checklist

When all of §11.1–§11.12 are struck through:

- Run a manual smoke pass against the dev workspace:
  - create a worktree, edit something in it, rename it,
    archive it, restore it, de-worktree it.
  - rename the parent, run `b fix`, confirm clean.
  - move `<base>/` to a new path, run `b fix --apply`,
    confirm everything resolves.
- Update `README.md` with a "Worktrees" section (short — one
  paragraph + a four-line code block, per AGENTS doc rules).
- Mark this TODO as `Status: shipped`. Leave it in the repo
  as historical record; don't delete.
