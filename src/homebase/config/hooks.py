from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.constants import HOOK_EVENTS, HOOK_SLOW_WARN_DEFAULT_S, HOOK_TIMINGS, HOOK_VIEWS
from ..core.models import HookSpec
from .store import load_global_config_dict


class HookConfigError(ValueError):
    """Raised on malformed or unresolvable hook config."""


@dataclass(frozen=True)
class HookRefreshWorkerConfig:
    batch_size: int = 4
    jitter_pct: float = 15.0
    skip_when_busy: bool = True


@dataclass(frozen=True)
class HookRefreshConfig:
    enabled: bool = False
    worker: HookRefreshWorkerConfig = HookRefreshWorkerConfig()


def load_hook_specs(base_dir: Path) -> dict[tuple[str, str], list[HookSpec]]:
    raw = load_global_config_dict(base_dir)
    out: dict[tuple[str, str], list[HookSpec]] = {
        (timing, event): [] for timing in HOOK_TIMINGS for event in HOOK_EVENTS
    }
    out.update(_default_post_specs())
    if not isinstance(raw, dict):
        return out
    for timing in HOOK_TIMINGS:
        key = f"hooks_{timing}"
        section = raw.get(key, {})
        if section is None:
            continue
        if not isinstance(section, dict):
            raise HookConfigError(f"{key!r} must be a mapping")
        for event, items in section.items():
            event_id = str(event).strip()
            if event_id not in HOOK_EVENTS:
                raise HookConfigError(f"unknown hook event {event_id!r} under {key!r}")
            if items in (None, []):
                continue
            if not isinstance(items, list):
                raise HookConfigError(f"{key!r}.{event_id!r} must be a list")
            out[(timing, event_id)] = [
                _parse_spec(timing, event_id, idx, item) for idx, item in enumerate(items)
            ]
    return out


def _default_post_specs() -> dict[tuple[str, str], list[HookSpec]]:
    return {
        ("pre", "delete"): [
            HookSpec(
                timing="pre",
                event="delete",
                name="confirm_delete",
                source="bundled",
                enabled=False,
                views=(),
                config={"require_confirm": True},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            )
        ],
        ("post", "rename"): [
            HookSpec(
                timing="post",
                event="rename",
                name="notes_rename",
                source="bundled",
                enabled=False,
                views=(),
                config={},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            ),
            HookSpec(
                timing="post",
                event="rename",
                name="tag_symlink_sync",
                source="bundled",
                enabled=False,
                views=(),
                config={},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            ),
        ],
        ("post", "tag_change"): [
            HookSpec(
                timing="post",
                event="tag_change",
                name="tag_symlink_sync",
                source="bundled",
                enabled=False,
                views=(),
                config={},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            )
        ],
        ("post", "new_project"): [
            HookSpec(
                timing="post",
                event="new_project",
                name="tag_symlink_sync",
                source="bundled",
                enabled=False,
                views=(),
                config={},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            )
        ],
        ("post", "delete"): [
            HookSpec(
                timing="post",
                event="delete",
                name="tag_symlink_sync",
                source="bundled",
                enabled=False,
                views=(),
                config={},
                slow_warn_s=HOOK_SLOW_WARN_DEFAULT_S,
            )
        ],
    }


def _parse_spec(timing: str, event: str, idx: int, item: object) -> HookSpec:
    if not isinstance(item, dict):
        raise HookConfigError(f"hooks_{timing}.{event}[{idx}] must be a mapping")
    name = str(item.get("name", "")).strip()
    if not name:
        raise HookConfigError(f"hooks_{timing}.{event}[{idx}] is missing `name`")
    source = str(item.get("source", "custom")).strip()
    if source not in {"bundled", "custom"}:
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: source must be `bundled` or `custom`"
        )
    enabled = bool(item.get("enabled", True))
    views_raw = item.get("views", [])
    if not isinstance(views_raw, list):
        raise HookConfigError(f"hooks_{timing}.{event}.{name}: `views` must be a list")
    views: list[str] = []
    for view in views_raw:
        text = str(view).strip()
        if text and text not in HOOK_VIEWS:
            raise HookConfigError(f"hooks_{timing}.{event}.{name}: unknown view {text!r}")
        if text:
            views.append(text)
    config_raw = item.get("config", {})
    if not isinstance(config_raw, dict):
        raise HookConfigError(f"hooks_{timing}.{event}.{name}: `config` must be a mapping")
    slow_warn = item.get("slow_warn_s", HOOK_SLOW_WARN_DEFAULT_S)
    try:
        slow_warn_s = float(slow_warn)
    except (TypeError, ValueError) as exc:
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: invalid `slow_warn_s`: {exc}"
        ) from exc
    refresh_enabled = bool(item.get("refresh_enabled", False))
    refresh_min = item.get("refresh_min_interval_s", 60.0)
    try:
        refresh_min_interval_s = float(refresh_min)
    except (TypeError, ValueError) as exc:
        raise HookConfigError(
            f"hooks_{timing}.{event}.{name}: invalid `refresh_min_interval_s`: {exc}"
        ) from exc
    return HookSpec(
        timing=timing,
        event=event,
        name=name,
        source=source,
        enabled=enabled,
        views=tuple(views),
        config=dict(config_raw),
        slow_warn_s=max(1.0, slow_warn_s),
        refresh_enabled=refresh_enabled,
        refresh_min_interval_s=max(1.0, refresh_min_interval_s),
    )


def load_hook_refresh_config(base_dir: Path) -> HookRefreshConfig:
    raw = load_global_config_dict(base_dir)
    if not isinstance(raw, dict):
        return HookRefreshConfig()
    section = raw.get("hooks_refresh")
    if section is None:
        return HookRefreshConfig()
    if not isinstance(section, dict):
        raise HookConfigError("'hooks_refresh' must be a mapping")
    enabled = bool(section.get("enabled", False))
    worker_raw = section.get("worker", {})
    if worker_raw is None:
        worker_raw = {}
    if not isinstance(worker_raw, dict):
        raise HookConfigError("'hooks_refresh.worker' must be a mapping")
    try:
        batch_size = int(worker_raw.get("batch_size", 4))
    except (TypeError, ValueError) as exc:
        raise HookConfigError(f"hooks_refresh.worker.batch_size: {exc}") from exc
    try:
        jitter_pct = float(worker_raw.get("jitter_pct", 15.0))
    except (TypeError, ValueError) as exc:
        raise HookConfigError(f"hooks_refresh.worker.jitter_pct: {exc}") from exc
    skip_when_busy = bool(worker_raw.get("skip_when_busy", True))
    return HookRefreshConfig(
        enabled=enabled,
        worker=HookRefreshWorkerConfig(
            batch_size=max(1, batch_size),
            jitter_pct=max(0.0, min(100.0, jitter_pct)),
            skip_when_busy=skip_when_busy,
        ),
    )
