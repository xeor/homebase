from __future__ import annotations

LOG_HEADING = "## Log"


class NoteValidationError(Exception):
    """Raised when an existing note file cannot safely be modified."""


def detect_line_ending(content: str) -> str:
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def validate_note(content: str) -> None:
    log_lines = _find_log_heading_indices(content.splitlines(), log_heading=LOG_HEADING)
    if len(log_lines) > 1:
        nums = ", ".join(str(n + 1) for n in log_lines)
        raise NoteValidationError(
            f"duplicate '{LOG_HEADING}' sections at lines {nums}"
        )


def insert_log_entry(
    content: str | None,
    *,
    project_name: str,
    timestamp: str,
    text: str,
    section_title: str = "Log",
    section_level: int = 2,
) -> str:
    level = max(1, min(6, int(section_level)))
    log_heading = f"{'#' * level} {section_title}".strip()
    entry_heading = f"{'#' * min(6, level + 1)} {timestamp}"
    if content is None:
        return _create_new_note(
            project_name=project_name,
            log_heading=log_heading,
            entry_heading=entry_heading,
            text=text,
        )

    validate_note(content)
    line_ending = detect_line_ending(content)
    lines = content.splitlines()
    log_indices = _find_log_heading_indices(lines, log_heading=log_heading)
    entry_lines = _build_entry_lines(entry_heading=entry_heading, text=text)

    if not log_indices:
        new_lines = list(lines)
        while new_lines and new_lines[-1].strip() == "":
            new_lines.pop()
        if new_lines:
            new_lines.append("")
        new_lines.append(log_heading)
        new_lines.extend(entry_lines)
    else:
        log_idx = log_indices[0]
        end_idx = _find_section_end_index(lines, log_idx, section_level=level)
        section_end = end_idx
        while section_end > log_idx + 1 and lines[section_end - 1].strip() == "":
            section_end -= 1
        new_lines = lines[:section_end] + entry_lines + lines[end_idx:]

    result = line_ending.join(new_lines)
    if not result.endswith(line_ending):
        result += line_ending
    return result


def _create_new_note(
    *,
    project_name: str,
    log_heading: str,
    entry_heading: str,
    text: str,
) -> str:
    lines = [f"# {project_name}", "", log_heading]
    lines.extend(_build_entry_lines(entry_heading=entry_heading, text=text))
    return "\n".join(lines) + "\n"


def _build_entry_lines(*, entry_heading: str, text: str) -> list[str]:
    text_lines = text.splitlines() if text else [""]
    return ["", entry_heading, "", *text_lines, ""]


def _find_log_heading_indices(lines: list[str], *, log_heading: str) -> list[int]:
    out: list[int] = []
    in_fence = False
    fence_marker: str | None = None
    for i, raw in enumerate(lines):
        ls = raw.lstrip()
        if in_fence:
            if fence_marker and ls.startswith(fence_marker):
                in_fence = False
                fence_marker = None
            continue
        if ls.startswith("```"):
            fence_marker = "```"
            in_fence = True
            continue
        if ls.startswith("~~~"):
            fence_marker = "~~~"
            in_fence = True
            continue
        if raw.strip() == log_heading:
            out.append(i)
    return out


def _find_section_end_index(lines: list[str], log_idx: int, *, section_level: int) -> int:
    in_fence = False
    fence_marker: str | None = None
    for i in range(log_idx + 1, len(lines)):
        ls = lines[i].lstrip()
        if in_fence:
            if fence_marker and ls.startswith(fence_marker):
                in_fence = False
                fence_marker = None
            continue
        if ls.startswith("```"):
            fence_marker = "```"
            in_fence = True
            continue
        if ls.startswith("~~~"):
            fence_marker = "~~~"
            in_fence = True
            continue
        if ls.startswith("#"):
            hashes = 0
            for ch in ls:
                if ch == "#":
                    hashes += 1
                else:
                    break
            if hashes > 0 and len(ls) > hashes and ls[hashes] == " " and hashes <= section_level:
                return i
    return len(lines)
