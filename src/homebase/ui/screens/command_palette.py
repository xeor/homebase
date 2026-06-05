from __future__ import annotations

import re

from textual.binding import Binding
from textual.command import CommandInput, CommandList, CommandPalette

_COMMAND_ID_RE = re.compile(r"\(id=([^\)]+)\)")


class BCommandPalette(CommandPalette):
    BINDINGS = [
        *CommandPalette.BINDINGS,
        Binding("tab", "toggle_favorite", "Toggle favorite", show=False, priority=True),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._preferred_command_id = ""

    def _refresh_command_list(self, command_list: CommandList, commands, clear_current: bool) -> None:
        saved_scroll_y = command_list.scroll_y
        super()._refresh_command_list(command_list, commands, clear_current)
        preferred = str(self._preferred_command_id or "").strip()
        if preferred and command_list.option_count > 0:
            for idx in range(command_list.option_count):
                option = command_list.get_option_at_index(idx)
                hit = getattr(option, "hit", None)
                help_text = str(getattr(hit, "help", "") or "")
                match = _COMMAND_ID_RE.search(help_text)
                if match is None:
                    continue
                if str(match.group(1)).strip() == preferred:
                    command_list.highlighted = idx
                    break
        command_list.scroll_to(y=saved_scroll_y, animate=False, immediate=True)

    def action_toggle_favorite(self) -> None:
        command_list = self.query_one(CommandList)
        highlighted = command_list.highlighted
        if highlighted is None:
            return
        option = command_list.get_option_at_index(highlighted)
        hit = getattr(option, "hit", None)
        if hit is None:
            return
        help_text = str(getattr(hit, "help", "") or "")
        match = _COMMAND_ID_RE.search(help_text)
        if match is None:
            return
        command_id = str(match.group(1)).strip()
        if not command_id:
            return
        self._preferred_command_id = command_id
        app = self.app
        toggle = getattr(app, "_toggle_favorite_target", None)
        if not callable(toggle):
            return
        if not bool(toggle(command_id)):
            return
        value = self.query_one(CommandInput).value.strip()
        self._cancel_gather_commands()
        self._gather_commands(value)
