"""Profile file models. Mirror of schema/profile.schema.json."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Browser(StrEnum):
    chrome = "chrome"
    vivaldi = "vivaldi"
    brave = "brave"
    edge = "edge"
    firefox = "firefox"


class Strategy(StrEnum):
    tab_group = "tab-group"
    window = "window"


class GroupColor(StrEnum):
    grey = "grey"
    blue = "blue"
    red = "red"
    yellow = "yellow"
    green = "green"
    pink = "pink"
    purple = "purple"
    cyan = "cyan"
    orange = "orange"


class SyncMode(StrEnum):
    apply_only = "apply-only"
    two_way = "two-way"
    manual = "manual"


class MatchPolicy(StrEnum):
    exact_url = "exact-url"
    normalized_url = "normalized-url"
    title_url = "title-url"


class BrowserSpec(_Model):
    preferred: Browser = Browser.chrome
    strategy: Strategy = Strategy.tab_group
    window: Literal["current", "new"] = "current"


class GroupSpec(_Model):
    title: str | None = None
    color: GroupColor = GroupColor.grey
    collapsed: bool = False
    focus: str = "first"


class TabSpec(_Model):
    url: str
    title: str | None = None

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("tab url must be an absolute http(s) URL")
        return value


class SyncSpec(_Model):
    mode: SyncMode = SyncMode.two_way
    delete_missing: bool = False
    adopt_existing: bool = True
    match: MatchPolicy = MatchPolicy.normalized_url


class Profile(_Model):
    schema_version: Literal[1] = Field(1, alias="schema")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str | None = None
    browser: BrowserSpec = Field(default_factory=BrowserSpec)
    group: GroupSpec = Field(default_factory=GroupSpec)
    tabs: list[TabSpec]
    sync: SyncSpec = Field(default_factory=SyncSpec)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
