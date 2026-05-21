from __future__ import annotations

import sys
from pathlib import Path

from ..workspace.health import audit_workspace, repair_issue


def cmd_fix_worktrees(base_dir: Path, *, apply: bool) -> int:
    issues = audit_workspace(base_dir)
    if not issues:
        print("worktree health: clean")
        return 0
    print(f"worktree health: {len(issues)} issue(s) detected")
    for issue in issues:
        print(f"  - [{issue.kind}] {issue.path}")
        print(f"      detail: {issue.detail}")
        print(f"      fix: {issue.fix_summary}")
    if not apply:
        return 1
    rc = 0
    for issue in issues:
        ok, detail = repair_issue(issue)
        status = "ok" if ok else "fail"
        print(f"  fix {issue.kind} for {issue.path}: {status} ({detail})", file=sys.stderr)
        if not ok:
            rc = 2
    return rc
