from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import PreOutcome
from homebase.ui.actions import project_create


class _App:
    def __init__(self) -> None:
        self.start_new_mode = False
        self.view_mode = "active"
        self._busy_depth = 0
        self.logs: list[tuple[str, str]] = []
        self.refreshed = 0
        self.notes_config = {}

    def _log(self, msg: str, level: str = "info") -> None:
        self.logs.append((level, msg))

    def _refresh_side(self) -> None:
        self.refreshed += 1

    def _busy_start(self, _label: str) -> None:
        self._busy_depth += 1

    def _busy_stop(self) -> None:
        self._busy_depth = max(0, self._busy_depth - 1)

    def exit(self, *_args, **_kwargs) -> None:
        return None

    def _show_runtime_error(self, *_args, **_kwargs) -> None:
        return None


def test_on_new_project_submit_aborts_on_pre_cancel(tmp_path: Path, monkeypatch) -> None:
    app = _App()
    called = {"plan": 0}

    monkeypatch.setattr(project_create, "load_new_sources", lambda _bd: {})
    monkeypatch.setattr(
        project_create.hooks_runtime,
        "dispatch_pre",
        lambda *_args, **_kwargs: PreOutcome(cancelled=True, reason="nope", change={}),
    )

    def _never_plan(*_args, **_kwargs):
        called["plan"] += 1
        return 1, None, None

    monkeypatch.setattr(project_create, "plan_and_apply_one", _never_plan)

    payload = {"input": "x", "source": "auto", "tags": [], "template": "", "after_create": "stay"}
    project_create.on_new_project_submit(app, payload, base_dir=tmp_path)
    assert called["plan"] == 0
    assert any("cancelled by hook" in msg for _lvl, msg in app.logs)


def test_apply_pre_new_project_mutations_updates_namespace() -> None:
    ns = SimpleNamespace(mode=None, child_key=None, tag=[], template="")
    payload: dict[str, object] = {"tags": [], "template": ""}
    project_create._apply_pre_new_project_mutations(
        payload=payload,
        ns=ns,
        change={
            "initial_tags": ["a", "b"],
            "template": "tpl",
            "source": "git",
        },
    )
    assert payload["tags"] == ["a", "b"]
    assert ns.tag == ["a", "b"]
    assert payload["template"] == "tpl"
    assert ns.template == "tpl"
    assert ns.mode == "git"
