from __future__ import annotations

import difflib

# Checked in order; the file markers must precede the bare +/- prefixes.
_DIFF_LINE_STYLES: tuple[tuple[str, str], ...] = (
    ("---", "dim"),
    ("+++", "dim"),
    ("@@", "bright_cyan"),
    ("+", "bright_green"),
    ("-", "bright_red"),
)


def _style_diff_line(line: str) -> str:
    for prefix, style in _DIFF_LINE_STYLES:
        if line.startswith(prefix):
            return f"[{style}]{line}[/]"
    return f"[dim]{line}[/]"


def color_diff_lines(
    current_lines: list[str],
    desired_lines: list[str],
    *,
    header: str = "",
    max_lines: int = 80,
) -> tuple[str, ...]:
    """Return a coloured unified-diff representation as Rich-markup lines.

    - Removed lines are coloured red, added lines green, hunk headers
      cyan, and unchanged context dim.
    - Truncates the body at ``max_lines`` with a trailing summary so
      the preview pane never grows unbounded.
    - When both sides are identical, returns a single dim ``(no
      differences)`` line.
    """
    diff = list(
        difflib.unified_diff(
            current_lines,
            desired_lines,
            fromfile="current",
            tofile="desired",
            lineterm="",
            n=2,
        )
    )
    if not diff:
        return ((f"{header}\n" if header else "") + "[dim](no differences)[/]",)

    out: list[str] = []
    if header:
        out.append(f"[dim]{header}[/]")
    out.extend(_style_diff_line(line) for line in diff)
    if len(out) > max_lines:
        truncated = len(out) - max_lines
        out = out[:max_lines]
        out.append(f"[dim]… (diff truncated; {truncated} more line(s))[/]")
    return tuple(out)


def diff_counts(
    current_lines: list[str], desired_lines: list[str]
) -> tuple[int, int]:
    """Return ``(removed, added)`` line counts between the two sides."""
    removed = added = 0
    for line in difflib.unified_diff(
        current_lines, desired_lines, lineterm="", n=0
    ):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return removed, added


__all__ = ["color_diff_lines", "diff_counts"]
