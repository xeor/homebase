from __future__ import annotations

import re

from textual.command import DiscoveryHit, Hit, Hits
from textual.system_commands import SystemCommandsProvider

_MARKUP_RE = re.compile(r"\[[^\]]+\]")
_TRAILING_TAG_RE = re.compile(r"\s+\\\[.+\]\s*$")
_COMMAND_ID_RE = re.compile(r"\(id=([^\)]+)\)")


def _command_sort_key(name: str) -> str:
    plain = _TRAILING_TAG_RE.sub("", str(name or ""))
    plain = _MARKUP_RE.sub("", plain)
    return " ".join(plain.split()).lower()


def _command_id_from_help(help_text: str) -> str:
    match = _COMMAND_ID_RE.search(str(help_text or ""))
    if match is None:
        return ""
    return str(match.group(1)).strip()


class HomebaseSystemCommandsProvider(SystemCommandsProvider):
    def _sorted_commands(self):
        return sorted(
            self.app.get_system_commands(self.screen),
            key=lambda command: (
                _command_sort_key(str(command[0])),
                _command_id_from_help(str(command[1])),
            ),
        )

    async def discover(self) -> Hits:
        for name, help_text, callback, discover in self._sorted_commands():
            if discover:
                yield DiscoveryHit(
                    name,
                    callback,
                    help=help_text,
                )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, help_text, callback, *_ in self._sorted_commands():
            name_str = str(name)
            score = matcher.match(name_str)
            if score <= 0:
                continue
            yield Hit(score, matcher.highlight(name_str), callback, help=help_text)


def get_homebase_system_commands_provider() -> type[HomebaseSystemCommandsProvider]:
    return HomebaseSystemCommandsProvider
