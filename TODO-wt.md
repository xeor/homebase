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
  of: foo                 # parent project name (directory under <base>/)
  branch: feature/auth    # raw git branch, unescaped
```

Regular projects: no change, no `worktree:` key.

Add `worktree` to `BASE_META_ALLOWED_KEYS` and to the schema
validator (`metadata/utils.py`). Validator must check that `of` is a
non-empty string and `branch` is a non-empty string. Both required.

Nothing is copied from the parent's `.base.yml` on creation —
tags, description, WIP are all set explicitly per worktree.

CLAUDE-COMMENT: For packed-archive recovery (see §7), `b fix` needs
enough info in `.base.yml` to relocate a stale worktree. Two extra
fields would help: `worktree.parent_path` (absolute path of the
parent at creation/pack time) and `worktree.gitdir_id` (the
`<id>` git assigned under `parent/.git/worktrees/<id>`). They're
only read by repair code, never required for normal operation. Add
them, or trust `worktree.of` + parent's `.git/worktrees/` listing
to recover? Default proposal: add both, write at create + on every
move/archive. Cheap insurance.

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
- `:repo=foo` — see §4.4 below
- `:worktree-of=foo` — strict, worktrees only (excludes parent)

Filter engine in `filter/engine.py` gains a registry
`key → matcher(row, op, value) -> bool` so adding a key is one
entry. Unknown keys parse but match nothing, with a non-fatal hint
in the input area. Aligns with [[feedback_no_migration_blocks]].

### 4.4 Umbrella filter: parent + worktrees

There are two useful queries: "just the worktrees of foo" and
"foo itself plus all its worktrees". The strict one keeps the
literal name (`:worktree-of=foo`). The umbrella one needs a new
name.

CLAUDE-COMMENT: Pick a name for the umbrella filter (parent +
all its worktrees). Concrete options:
(a) `:repo=foo`           — short; reads as "everything for repo foo"
(b) `:git-repo=foo`       — explicit namespace
(c) `:family=foo`         — relationship metaphor
(d) `:tree=foo`           — riffs on "worktree"; short
(e) `:worktree-group=foo` — verbose but obvious
Default proposal: (a) `:repo=foo`. Short, intuitive, leaves
`:worktree-of=foo` for the strict variant.

### 4.5 Syntax highlighting

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
  block.

Branch handling:

- If the branch already exists locally, `git worktree add` checks
  it out into the new path.
- If the branch doesn't exist, it's created from the parent's
  current HEAD (`git worktree add -b <branch> <path>` default).
  This is the least surprising behaviour and matches plain git.

CLAUDE-COMMENT: If the parent's HEAD is detached, or on an unusual
ref (e.g. a tag), should `b new <branch>` from inside that project
still use HEAD, fall back to default branch (origin/HEAD), or
refuse and ask the user to pass an explicit base? Default proposal:
use HEAD anyway — that's still what plain `git worktree add -b`
does — but surface the actual base ref in the success message so
the user sees what happened.

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
helper, same tests, no duplicate logic.

### 7.1 Rename / archive / move flows

1. **Renaming a worktree project** (`b mv foo-featx foo-newname`):
   rewrite the parent's `.git/worktrees/<id>/gitdir` to the new
   worktree path. Worktree's own `repo/.git` is unchanged (it
   still points at the same parent admin entry).
2. **Archiving a worktree project**: same as rename, with the new
   path under `_archive/…`. The archived worktree must still be a
   working git repo when the user `cd`s into it.
3. **Renaming the parent project** (`b mv foo bar`): for every
   row with `worktree.of == foo`:
   - rewrite the worktree's `repo/.git` to the new parent path
   - update `worktree.of` in `.base.yml` to `bar`
   - rewrite `worktree.parent_path` if we track it (see §3.2
     open question)

### 7.2 Archiving the parent (with active worktrees)

Refuse the operation by default. The error message lists the
worktrees that block it and offers two actions:

- **De-worktree first** (recommended) — turn every worktree into
  a standalone clone (§7.3). After that, parent can be archived
  with no further consequence.
- **Move all together** — archive the parent and every worktree
  in one transaction. Layout question:

CLAUDE-COMMENT: When "move all together" is used to archive the
parent plus N worktrees, where do the worktrees land?
(a) Flat siblings under the archive year:
    `_archive/2026/2026-05-20_foo/`
    `_archive/2026/2026-05-20_foo-featx/`
(b) Nested under the parent's archive dir:
    `_archive/2026/2026-05-20_foo/`
    `_archive/2026/2026-05-20_foo/_worktrees/featx/`
Default proposal: (a). Matches the active layout one-to-one, no
discovery special-casing needed, no nested marker file rules.

### 7.3 De-worktree action (make worktree standalone)

A new action: takes a worktree row and turns it into a regular
standalone project. After the action runs, the row has no
`worktree:` key, its `repo/.git` is a real directory, and it has
no relationship to the former parent.

Concrete steps (proposed):

1. Run `git clone --local <parent-path> <tmp-clone>` to materialise
   a self-contained git dir using hardlinks where possible.
2. Replace `<worktree>/repo/.git` (the file) with the cloned
   `.git/` directory.
3. Restore branch state on the now-standalone repo (checkout the
   same branch, set upstream to match where applicable).
4. Detach the parent's `.git/worktrees/<id>/` admin entry
   (equivalent to `git worktree remove --force` on the parent,
   but without touching the worktree dir contents we just rebuilt).
5. Strip `worktree:` from the worktree's `.base.yml`.

CLAUDE-COMMENT: The de-worktree flow doesn't carry across local-
only artefacts: stashes, reflog, hooks installed in the parent's
`.git/`. Options:
(a) Document the loss, proceed silently — the typical worktree
   has no per-worktree stash/reflog state worth preserving.
(b) Detect stashes/local-only refs before running and prompt the
   user (proceed and lose them / cancel / open the parent to
   move them out first).
(c) Copy parent's `.git/` wholesale (rsync) instead of `git clone`,
   carrying everything including reflog and stash list.
Default proposal: (a). Document in the action's confirm prompt.
(c) is tempting but mixes the parent's stash list into the new
clone, which is wrong.

### 7.4 `b fix`

A new explicit subcommand (and matching TUI action) that audits
and offers to repair the worktree references in `<base>/`.

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
- Handle relocated base folder: if the user moved
  `<base>/` to a new absolute path, every `gitdir` file inside
  every worktree still references the old path. `b fix` detects
  this by comparing the current `<base>` against the path
  recorded in each `.base.yml`'s `worktree.parent_path` (or the
  derived parent path) and rewrites all stale pointers in one
  pass.
- Handle packed-archive recovery: unpacking a worktree (see §7.5)
  leaves stale pointers; `b fix` recomputes them from
  `worktree.of` + the current parent's `.git/worktrees/`.

UX rules:

- Default mode is **dry-run**: list every issue and the fix that
  would be applied. Requires `--apply` (CLI) or explicit confirm
  (TUI) to mutate.
- Never silently rewrites paths inside `.git/`. Every fix is
  logged to the project's `.base.yml` `log:` array
  ([[feedback_no_git_actions]]).

CLAUDE-COMMENT: Trigger. When does `b fix` run?
(a) Explicit only — user runs `b fix` or invokes the TUI action.
(b) Lazy auto-detect — on startup, scan; if any broken worktrees
   exist, surface a "X broken worktrees, run b fix" banner. No
   auto-repair.
(c) Auto-repair on startup — silently fix anything that's
   obviously fixable (e.g. relocated base folder), warn on the
   rest.
Default proposal: (b). (a) is too quiet, (c) violates "no git
actions without explicit ask" ([[feedback_no_git_actions]]).

### 7.5 Packed archives (`.tar.zst` etc.)

Allow packing a worktree. The packed tarball will contain a stale
`repo/.git` file (gitdir pointer freezes a path that probably
won't exist on restore). Mitigations:

- **At pack time**, ensure `.base.yml` carries enough info for
  later repair: `worktree.of`, `worktree.branch`, plus the
  optional `worktree.parent_path` / `worktree.gitdir_id` fields
  from the §3.2 open question. Emit a clear warning that the
  packed worktree depends on its parent existing at unpack time.
- **At unpack time**, detect that the unpacked dir is a worktree
  (has `worktree:` block) and that its `repo/.git` pointer is
  stale. Surface a "this is a stale worktree, run `b fix`"
  notice; do not auto-repair as part of unpack.
- `b fix` (§7.4) does the actual repair using
  `worktree.of` + the now-resolved parent location.

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
2. **Schema.** Add `worktree` (with `of`/`branch`, plus optional
   `parent_path`/`gitdir_id` if the §3.2 question resolves yes)
   to `BASE_META_ALLOWED_KEYS` and the validator. Tests.
3. **GIT column rendering.** Format `featx*  ↪foo` for worktree
   rows. Tests with a row containing/lacking the `worktree:` block.
4. **Filter framework migration.** Move existing
   `created=`/`opened=`/`last=` to the `:` prefix. Parse all
   operators; implement only `=`. Add registry. Update parser,
   normaliser, pretty-printer, saved/named filters, docs.
5. **Filter keys.** Register `:worktree-of=` (strict) and the
   chosen umbrella name (§4.4). Tests.
6. **`b new --as worktree`** (CLI) + auto-default rule when cwd is
   inside a git-enabled project. Chained-parent resolution. Tests
   with real git.
7. **New action: "New worktree"** in the TUI action list,
   single-target, opens prefilled `ctrl-n` dialog.
8. **Delete-action wiring** for worktree rows
   (`git worktree remove` + admin cleanup). Parent-delete warning
   + "de-worktree first" / "move all together" alternatives
   (the de-worktree branch lands in step 10).
9. **Rename / archive pointer rewriting.** §7.1 items 1–3, single
   helper used from both CLI and TUI. Tests for every code path
   that mutates a project's location.
10. **De-worktree action.** §7.3. CLI + action list entry. Tests.
11. **`b fix`.** §7.4. Audit + dry-run + `--apply`. Tests including
    a relocated-base-folder fixture.
12. **Packed archive flow.** §7.5. Warning on pack, detection on
    unpack, repair via `b fix`.

Items beyond 12 (merge, sync, prune, advanced status badges) are
parked until we see real friction.
