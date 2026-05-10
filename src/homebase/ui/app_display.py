from __future__ import annotations

from textual.widgets import DataTable

from ..core.constants import (
    COLOR_ACCENT_HEX,
    COLOR_ARCHIVE_HEX,
    COLOR_ERROR_HEX,
    COLOR_INTERACTIVE_HEX,
    COLOR_SUCCESS_HEX,
    COLOR_WARN_HEX,
    LEVEL_WARN,
    MODE_ACTIVE,
    WIDGET_PROJECTS,
)
from ..core.utils import fmt_age_short_from_iso, fmt_size_human, fmt_ymd
from ..metadata.api import load_base_data, property_defs_signature, property_tokens_text
from .side import tabs as textual_ui_side_tabs
from .table import render as textual_ui_table_render
from .table.layout import solve_visible_column_widths


class AppDisplayMixin:
    def _build_side_git_text(self, row) -> str:
        from .side import content as textual_ui_side_content

        return textual_ui_side_content.build_side_git_text(self, row)

    def _build_side_project_events_text(self, row) -> str:
        from .side import content as textual_ui_side_content

        return textual_ui_side_content.build_side_project_events_text(
            self,
            row,
            load_base_data=load_base_data,
            fmt_age_short_from_iso=fmt_age_short_from_iso,
        )

    def _build_side_files_text(self, row) -> str:
        from .side import content as textual_ui_side_content

        return textual_ui_side_content.build_side_files_text(
            self,
            row,
            file_view_exclude_patterns=self.ctx.file_view_exclude_patterns,
            fmt_size_human=fmt_size_human,
        )

    def _configure_table_columns(self) -> None:
        table = self.query_one(WIDGET_PROJECTS, DataTable)

        visible = self._table_visible_columns_for_view(self.view_mode)
        if not visible:
            visible = [
                col
                for col in self._table_columns_for_view(self.view_mode)
                if col.get("id") == "name"
            ]
            if not visible:
                visible = [
                    {
                        "id": "name",
                        "label": "NAME",
                        "enabled": True,
                        "width": 34,
                        "views": ["active", "archive"],
                    }
                ]
        base_widths: list[int] = []
        for col in visible:
            try:
                width = int(col.get("width", 12))
            except (TypeError, ValueError):
                width = 12
            base_widths.append(max(4, min(80, width)))

        if not base_widths:
            table.clear(columns=True)
            self._visible_column_effective_width_by_id = {}
            return

        table_size = getattr(table, "size", None)
        table_width = int(getattr(table_size, "width", 0) or 0)
        cell_padding = int(getattr(table, "cell_padding", 1) or 0)
        if table_width > 0:
            widths = solve_visible_column_widths(
                viewport_width=table_width,
                base_widths=base_widths,
                cell_padding=cell_padding,
            )
        else:
            widths = list(base_widths)

        column_signature = (
            self.view_mode,
            tuple(str(col.get("id", "")).strip() for col in visible),
            tuple(str(col.get("label", "")) for col in visible),
            tuple(int(width) for width in widths),
        )
        prev_signature = self._table_column_signature_by_view.get(self.view_mode)
        if prev_signature == column_signature:
            return
        self._table_column_signature_by_view[self.view_mode] = column_signature

        table.clear(columns=True)
        for col, width in zip(visible, widths):
            label = str(col.get("label", ""))
            try:
                table.add_column(label, width=width)
            except (RuntimeError, ValueError, TypeError):
                table.add_column(label)

        self._visible_column_effective_width_by_id = {
            str(col.get("id", "")).strip(): widths[i]
            for i, col in enumerate(visible)
        }

    def _refresh_table(self) -> None:
        textual_ui_table_render.refresh_table(
            self,
            widget_projects=WIDGET_PROJECTS,
            mode_active=MODE_ACTIVE,
            base_dir=self.base_dir,
            color_error_hex=COLOR_ERROR_HEX,
            color_success_hex=COLOR_SUCCESS_HEX,
            color_archive_hex=COLOR_ARCHIVE_HEX,
            color_accent_hex=COLOR_ACCENT_HEX,
            color_warn_hex=COLOR_WARN_HEX,
            color_interactive_hex=COLOR_INTERACTIVE_HEX,
            fmt_ymd=fmt_ymd,
            fmt_size_human=fmt_size_human,
            property_tokens_text=property_tokens_text,
            property_defs_signature=property_defs_signature(),
            table_date_color_ranges=self.table_date_color_ranges,
        )

    def _refresh_side(self) -> None:
        textual_ui_side_tabs.refresh_side(
            self,
            base_dir=self.base_dir,
            color_accent_hex=COLOR_ACCENT_HEX,
            level_warn=LEVEL_WARN,
        )
