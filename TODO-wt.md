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

CLAUDE-COMMENT: User-side config carryover. A user's
`<base>/.homebase/config.yaml` can already contain literal
`last=@-7d` strings under `filters.saved` or `filters.named` (the
README shows this). After the cut to `:last=…`, those entries
silently match nothing. Three options:
(a) Silent — entries don't match, no warning. User notices and
   updates the config when they realise.
(b) Warn at startup — scan `filters.*` once on load and emit a
   non-fatal log line listing each stale entry and the new
   spelling. No auto-fix.
(c) One-shot rewrite — startup detects old syntax and rewrites
   the user's `config.yaml` in place (with a backup copy). Logs
   what was changed.
Default proposal: (b). Aligns with the homebase rule "no migration
blocks" ([[feedback_no_migration_blocks]]) but doesn't surprise
the user by mutating their config.
COMMENT: A. No need to migrate anything since there is noone except me using this yet.

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
  parent is the *original* parent project (follow `worktree.of` to
  resolve the root). Worktrees are never nested under worktrees;
  they all sit as siblings of the root project.
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
- If the branch doesn't exist, it's created the same way plain
  `git worktree add -b <branch> <path>` would: from the parent's
  current HEAD, whatever state HEAD is in (detached, on a tag,
  etc.). The success message surfaces the actual base ref so the
  user sees what happened.

CLAUDE-COMMENT: Base ref when creating from a worktree row.
Scenario: I'm in `foo-featx` (a worktree on branch `featx`) and I
run `b new bugfix-y`. The new worktree's *parent* is `foo` (root
resolution from §5.1) — that's settled. But which ref does the
new branch fork from?
(a) The root parent's HEAD — same as if I had run the command from
   `foo` directly. New branch starts from `main` (or whatever
   `foo` has checked out).
(b) The selected row's branch — new branch forks from `featx`.
   This matches "I'm working on featx and want a side-branch off
   of it" intuition.
Default proposal: (b). The user's cwd / selection tells us what
they're conceptually branching off of; (a) ignores that context.
Plain git's `git worktree add -b new <path>` from inside the
featx worktree also forks from `featx`, so (b) matches upstream
behaviour too.
COMMENT: Lets do B. It is the less magic.

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

CLAUDE-COMMENT: Use git's own commands or hand-rewrite pointers?
Git ships two commands that do most of this work natively:
- `git worktree move <worktree> <new-path>` rewrites both
  pointers atomically. We could use it instead of hand-editing
  `parent/.git/worktrees/<id>/gitdir` ourselves.
- `git worktree repair` walks every worktree of a repo and fixes
  stale pointers. We could use it inside `b fix` (§7.4) instead
  of hand-rewriting.
Options:
(a) Use git's commands wherever they apply (move + repair); only
   hand-edit when we need to do something git won't (e.g. moving
   both ends in a single transaction during parent rename).
(b) Hand-rewrite everything — fewer subprocess calls, full
   control, but we own all the edge cases.
Default proposal: (a). Less surface, fewer ways to corrupt
`.git/`, and git's behaviour is the spec we'd otherwise be
re-implementing. Hand-rewrites stay reserved for cases git's CLI
genuinely can't handle.
COMMENT: Do A as much as possible

### 7.1 Rename / archive / move flows

1. **Renaming a worktree project** (`b mv foo-featx foo-newname`):
   `git worktree move <old-path> <new-path>` if available; else
   hand-rewrite the parent's `.git/worktrees/<id>/gitdir`.
2. **Archiving a worktree project**: same as rename, with the new
   path under `_archive/…`. The archived worktree must still be a
   working git repo when the user `cd`s into it.
3. **Renaming the parent project** (`b mv foo bar`): after the
   parent directory moves, run `git -C <new-parent>/repo worktree
   repair` to fix every linked worktree's `repo/.git`. Then walk
   every row with `worktree.of == foo` and update `worktree.of`
   and `worktree.parent_path` in their `.base.yml`.

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

  After the move, run the §7.1.3 rewrite (parent path change) so
  every archived worktree points at the archived parent.

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

### 7.4 `b fix`

A new explicit subcommand and matching TUI action that audits and
offers to repair the worktree references in `<base>/`. Invokable
three ways:

- `b fix` (CLI, dry-run by default; `--apply` to mutate)
- TUI action in the standard action list, target scope = workspace
- Auto-detect: on TUI startup the workspace is scanned; if any
  broken worktrees are found, the existing timed-notification
  popup system surfaces a notice (corner toast, not status menu).
  See open question below for sticky-vs-timed behaviour.

Scope:

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
  pointers in one pass (preferring `git worktree repair` on each
  parent — see §7 framing question).
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

UX rules:

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

CLAUDE-COMMENT: Notification reuse. Existing timed-notification
popups auto-dismiss after a few seconds. A "you have N broken
worktrees" notice that vanishes that quickly is too easy to miss.
Options:
(a) Reuse the popup component verbatim — same auto-dismiss
   timing as other notices. Briefer visibility, but consistent.
(b) Reuse the popup component but mark the notice as "sticky":
   it stays in the corner until the user dismisses it (or until
   the underlying issue resolves on next scan).
(c) Fire the toast on every startup until resolved, with the
   normal timeout — repeated annoyance forces eventual action.
Default proposal: (b). It matches your earlier "persistent
banner" preference while still reusing the existing popup
mechanism instead of building a new banner widget.
COMMENT: Lets do B. Take special care when doing checks like this on startup to not slow the startuptime down.

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

1. **Fix `.git` detection.** `git_info()` and any siblings that
   special-case `.git` as a directory. Tests with a real worktree
   under `tmp_path`.
2. **Schema.** Add `worktree` (with `of`, `branch`, `parent_path`,
   `gitdir_id`) to `BASE_META_ALLOWED_KEYS` and the validator.
   Tests.
3. **GIT column rendering.** Format `featx*  ↪foo` for worktree
   rows. Tests with a row containing/lacking the `worktree:` block.
4. **Filter framework migration.** Move existing
   `created=`/`opened=`/`last=` to the `:` prefix. Parse all
   operators; implement only `=`. Add registry. Update parser,
   normaliser, pretty-printer, saved/named filters in defaults,
   docs. Add the startup hint for stale user-config entries
   (§4.1).
5. **Filter keys.** Register `:worktree-of=` (strict) and
   `:repo=` (umbrella). Tests.
6. **`b new --as worktree`** (CLI) + auto-default rule when cwd is
   inside a git-enabled project. Chained-parent resolution. Tests
   with real git, including parent-HEAD-detached fixtures.
7. **New action: "New worktree"** in the TUI action list,
   single-target, opens prefilled `ctrl-n` dialog.
8. **Delete-action wiring** for worktree rows
   (`git worktree remove` + admin cleanup). Parent-delete warning
   + "de-worktree first" / "move all together" alternatives
   (the de-worktree branch lands in step 10).
9. **Rename / archive pointer rewriting.** §7.1 items 1–3, single
   helper used from both CLI and TUI. Uses `git worktree
   move` / `git worktree repair` per the §7 framing question.
   Updates `worktree.of` / `worktree.parent_path` in `.base.yml`
   as part of each mutation. Tests for every code path that
   mutates a project's location.
10. **De-worktree action.** §7.3, rsync-of-`.git` method. CLI +
    action list entry. Tests.
11. **`b fix`.** §7.4. Audit + dry-run + `--apply` + startup
    popup + documented exit codes. Tests including a
    relocated-base-folder fixture and an orphan-worktree fixture.
12. **Packed archive flow.** §7.5. Warning on pack, detection on
    unpack, repair via `b fix`.

Items beyond 12 (merge, sync, prune, advanced status badges) are
parked until we see real friction.
