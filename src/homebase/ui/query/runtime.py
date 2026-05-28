from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from textual.widgets import Static

from ...core.constants import CURSOR_BG_HEX, CURSOR_FG_HEX
from ...filter.engine import STRUCTURED_TERM_RE
from ...workspace.filter_compile import _FILTER_TOKEN_RE

_CURSOR_STYLE = f"{CURSOR_FG_HEX} on {CURSOR_BG_HEX}"


_KNOWN_STRUCTURED_KEYS: frozenset[str] = frozenset(
    {"created", "opened", "last", "repo", "worktree-of"}
)


def _esc_default(text: str) -> str:
    return text.replace("[", "\\[")


def _render_query_with_cursor(
    query: str,
    cursor: int,
    *,
    color_key: str,
    color_op: str,
    color_value: str,
    color_unknown: str,
    esc=_esc_default,
) -> str:
    pieces: list[str] = []
    last_end = 0
    for match in _FILTER_TOKEN_RE.finditer(query):
        start, end = match.span()
        if start > last_end:
            pieces.append(
                _styled_chunk(query[last_end:start], None, cursor, last_end, esc)
            )
        token = match.group(0)
        pieces.append(_render_token(token, cursor, start, color_key, color_op, color_value, color_unknown, esc))
        last_end = end
    if last_end < len(query):
        pieces.append(_styled_chunk(query[last_end:], None, cursor, last_end, esc))
    # Cursor at end-of-string: append a single highlighted space.
    if cursor >= len(query):
        pieces.append(f"[{_CURSOR_STYLE}] [/]")
    return "".join(pieces)


def _render_token(
    token: str,
    cursor: int,
    offset: int,
    color_key: str,
    color_op: str,
    color_value: str,
    color_unknown: str,
    esc,
) -> str:
    # Structured ':key<op>value' tokens get the three-colour treatment.
    match = STRUCTURED_TERM_RE.match(token.lower())
    if match:
        key_text = ":" + match.group(1)
        op_text = match.group(2)
        key_color = color_key if match.group(1) in _KNOWN_STRUCTURED_KEYS else color_unknown
        key_raw = token[: len(key_text)]
        op_raw = token[len(key_text) : len(key_text) + len(op_text)]
        value_raw = token[len(key_text) + len(op_text) :]
        pieces: list[str] = []
        pieces.append(_styled_chunk(key_raw, key_color, cursor, offset, esc))
        pieces.append(_styled_chunk(op_raw, color_op, cursor, offset + len(key_raw), esc))
        pieces.append(_styled_chunk(value_raw, color_value, cursor, offset + len(key_raw) + len(op_raw), esc))
        return "".join(pieces)
    # Sigil-prefixed tokens (#tag, @named, .suffix, !prop) get a
    # solid colour. The leading sigil keeps the operator colour so
    # the visual rhythm matches the structured tokens.
    if token and token[0] in "#@.!" and len(token) > 1:
        sigil = token[0]
        body_color = {
            "#": color_value,
            "@": color_key,
            ".": color_unknown,
            "!": color_value,
        }[sigil]
        pieces = []
        pieces.append(_styled_chunk(token[0], color_op, cursor, offset, esc))
        pieces.append(_styled_chunk(token[1:], body_color, cursor, offset + 1, esc))
        return "".join(pieces)
    # Boolean / grouping tokens stay neutral.
    if token.upper() in {"OR", "AND"} or token in {"(", ")", "|"}:
        return _styled_chunk(token, color_op, cursor, offset, esc)
    return _styled_chunk(token, None, cursor, offset, esc)


def _styled_chunk(text: str, color: str | None, cursor: int, offset: int, esc) -> str:
    if not text:
        return ""
    chunk_start = offset
    chunk_end = offset + len(text)
    if cursor < chunk_start or cursor >= chunk_end:
        body = esc(text)
        return f"[{color}]{body}[/]" if color else body
    rel = cursor - chunk_start
    left = esc(text[:rel])
    cur = esc(text[rel])
    right = esc(text[rel + 1 :])
    if color:
        left_part = f"[{color}]{left}[/]" if left else ""
        right_part = f"[{color}]{right}[/]" if right else ""
    else:
        left_part, right_part = left, right
    return f"{left_part}[{_CURSOR_STYLE}]{cur}[/]{right_part}"

_HOTBAR_ROW_STYLE_EVEN = "white on #2A2A2A"
_HOTBAR_ROW_STYLE_ODD = "white on #353535"


def _is_truthy_style_flag(value: str) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _hotbar_style_text(style: dict[str, str], fallback: str) -> str:
    parts: list[str] = []
    if _is_truthy_style_flag(str(style.get("bold", ""))):
        parts.append("bold")
    if _is_truthy_style_flag(str(style.get("underline", ""))):
        parts.append("underline")
    if _is_truthy_style_flag(str(style.get("italic", ""))):
        parts.append("italic")
    fg_color = str(style.get("fg_color", "")).strip()
    bg_color = str(style.get("bg_color", "")).strip()
    if fg_color and bg_color:
        parts.append(f"{fg_color} on {bg_color}")
    elif fg_color:
        parts.append(fg_color)
    elif bg_color:
        parts.append(f"white on {bg_color}")
    if not parts:
        return fallback
    return " ".join(parts)


def named_filters_sig(named_filters: dict[str, str]) -> str:
    if not named_filters:
        return ""
    return "|".join(f"{k}={named_filters[k]}" for k in sorted(named_filters.keys()))


def query_eval(
    app: Any,
    query_text: str,
    *,
    named_filters: dict[str, str],
    base_dir: Path,
    query_uses_filter_syntax: Callable[[str], bool],
    resolve_filter_expression: Callable[[Path, str], tuple[str, str | None]],
    compile_filter_expr: Callable[[str], tuple[Callable[[Any], bool], str | None]],
) -> tuple[bool, str, str | None, Callable[[Any], bool], str | None]:
    sig = named_filters_sig(named_filters)
    if sig != app.query_named_sig:
        app.query_named_sig = sig
        app.query_eval_cache.clear()
        app.query_eval_cache_order = []

    cached = app.query_eval_cache.get(query_text)
    if cached is not None:
        return cached

    query_mode = query_uses_filter_syntax(query_text)
    resolved_query, query_resolve_err = resolve_filter_expression(base_dir, query_text)
    query_pred, query_err = compile_filter_expr(resolved_query)
    value = (query_mode, resolved_query, query_resolve_err, query_pred, query_err)
    app.query_eval_cache[query_text] = value
    app.query_eval_cache_order.append(query_text)
    if len(app.query_eval_cache_order) > 256:
        old = app.query_eval_cache_order.pop(0)
        app.query_eval_cache.pop(old, None)
    return value


def queue_query_apply(app: Any) -> None:
    app.query_apply_pending = True
    app.query_apply_due_at = time.time() + app.query_apply_debounce_s
    app._refresh_search_display()
    app._refresh_side()


def flush_query_apply_if_due(app: Any) -> None:
    if not app.query_apply_pending:
        return
    if time.time() < app.query_apply_due_at:
        return
    app.query_apply_pending = False
    app._refresh_table()
    app._refresh_side()


def refresh_search_display(
    app: Any,
    *,
    color_interactive_hex: str,
    color_nav_hex: str,
    color_archive_hex: str,
    color_success_hex: str,
    color_error_hex: str,
    color_warn_hex: str,
    mode_active: str,
) -> None:
    disp_left = app.query_one("#global_meta_left", Static)
    disp_right = app.query_one("#global_meta_right", Static)

    def esc(text: str) -> str:
        return text.replace("[", "\\[")

    app._normalize_query_cursor()
    if app.query:
        active = _render_query_with_cursor(
            app.query,
            app.query_cursor,
            color_key=color_nav_hex,
            color_op=color_archive_hex,
            color_value=color_success_hex,
            color_unknown=color_warn_hex,
            esc=esc,
        )
    else:
        active = ""
    count = app.query_last_rows_count
    query_mode, _resolved_query, query_resolve_err, _qpred, query_err = app._query_eval(
        app.query
    )
    if not app.query_apply_pending:
        count = len(app._current_rows())
        app.query_last_rows_count = count
    query_badge = ""
    if query_mode:
        query_badge = f" [{color_interactive_hex}](expr)[/]"
        if query_resolve_err:
            query_badge = f" [red](expr: {query_resolve_err})[/]"
        elif query_err:
            query_badge = " [red](expr invalid)[/]"
    if app.query_apply_pending:
        query_badge += " [dim](typing)[/]"
    line1 = f"[bold {color_nav_hex}]QUERY[/] [bold white]{active}[/]{query_badge}"
    view_color = color_nav_hex if app.view_mode == mode_active else color_archive_hex
    cache_state = "warming" if app.cache_worker_running else "ready"
    cache_state_color = color_interactive_hex if app.cache_worker_running else color_success_hex
    select_color = color_success_hex if app.select_mode else color_error_hex
    line2 = (
        f"[bold {color_nav_hex}]VIEW[/]: [{view_color}]{app.view_mode}[/]"
        f"   [bold {color_nav_hex}]SORT[/]: [{color_interactive_hex}]{app.sort_mode}[/]"
        f"   [bold {color_nav_hex}]ROWS[/]: [white]{count}[/]"
        f"   [bold {color_nav_hex}]SELECT[/]: [{select_color}]{'ON' if app.select_mode else 'OFF'}[/]"
        f"   [bold {color_nav_hex}]CACHE[/]: [{cache_state_color}]{cache_state}[/]"
    )
    if app._critical_job_active():
        line2 += (
            f"   [{color_warn_hex}]![/] [{color_warn_hex}]{esc(app._critical_job_label())}[/]"
        )
    if app.select_mode:
        line2 += (
            f"   [bold {color_nav_hex}]SELECTED_COUNT[/]: [{color_interactive_hex}]"
            f"{len(app.multi_selected)}[/]"
        )
    if app._busy_depth > 0:
        spinner = app._busy_frames[app._busy_frame_index]
        line2 += f" [{color_interactive_hex}]{spinner} {esc(app._busy_label)}[/]"
    line2 += f"   [bold {color_nav_hex}]DETAILS[/]:"
    if app.detail_worker_running and app.detail_worker_path is not None:
        line2 += (
            f" [{color_interactive_hex}]refreshing {esc(app.detail_worker_path.name)}[/]"
        )
    if app.runtime_status_text:
        color = color_success_hex
        if app.runtime_status_level == "warn":
            color = color_warn_hex
        elif app.runtime_status_level == "error":
            color = color_error_hex
        line2 += f"   [bold {color_nav_hex}]STATUS[/]: [{color}]{esc(app.runtime_status_text)}[/]"
    text = f"{line1}\n{line2}"
    if app.select_mode:
        text += (
            "\n[bold yellow]select keys[/]: "
            f"[bold {color_nav_hex}]space[/] toggle "
            f"[bold {color_nav_hex}]a[/]ll "
            f"[bold {color_nav_hex}]c[/]lear "
            f"[bold {color_nav_hex}]u[/]ntagged"
        )
    disp_left.update(text)

    targets = app._hotbar_targets()
    if not targets:
        disp_right.update("")
        return
    app._normalize_hotbar_index()
    parts: list[str] = [f"[bold {color_nav_hex}]HOTBAR[/] [dim]^@[/]:"]
    for i, target in enumerate(targets):
        label = app._hotbar_target_label(target)
        rendered_label = esc(label)
        if app.select_mode and target in {"open_selected", "action:open_selected"}:
            rendered_label = f"{rendered_label} [1]"
        cell = f" {rendered_label} "
        style = app._resolve_hotbar_target_style(target)
        if i == app.hotbar_selected_index:
            parts.append(f"[{_CURSOR_STYLE}]{cell}[/]")
        else:
            fallback = _HOTBAR_ROW_STYLE_EVEN if i % 2 == 0 else _HOTBAR_ROW_STYLE_ODD
            row_style = _hotbar_style_text(style, fallback)
            parts.append(f"[{row_style}]{cell}[/]")
    disp_right.update("  ".join(parts))
