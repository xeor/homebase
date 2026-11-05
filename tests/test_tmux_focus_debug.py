from __future__ import annotations

from pathlib import Path

from homebase.core.setup_model import (
    MainThreadActivator,
    SetupDebugOption,
    SetupDebugTool,
)
from homebase.tmux import client_focus, focus_debug


def test_build_focus_debug_tools_shape(tmp_path: Path) -> None:
    tools = focus_debug.build_focus_debug_tools(tmp_path)
    assert all(isinstance(t, SetupDebugTool) for t in tools)
    ids = [t.id for t in tools]
    assert ids == ["focus_switch", "list_clients", "macos_perms"]
    # ids must be valid Textual widget id suffixes (no spaces / dashes)
    assert all(tid.replace("_", "").isalnum() for tid in ids)


def test_focus_switch_has_method_options(tmp_path: Path) -> None:
    focus = focus_debug.build_focus_debug_tools(tmp_path)[0]
    assert focus.run is None
    assert focus.detail is not None
    assert all(isinstance(o, SetupDebugOption) for o in focus.options)
    assert [o.id for o in focus.options] == [
        "auto",
        "appkit",
        "osascript",
        "system_events",
        "system_events_osascript",
    ]


def test_focus_detail_reports_auto_method(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(focus_debug.sys, "platform", "darwin")
    monkeypatch.setattr(
        focus_debug,
        "resolve_external_tmux_target",
        lambda *_a, **_k: (None, [], lambda *_a: "300\n", "work"),
    )
    monkeypatch.setattr(
        client_focus, "process_ancestry", lambda pid: [(300, "tmux")]
    )
    monkeypatch.setattr(
        client_focus,
        "macos_app_for_client_pid",
        lambda pid: (100, Path("/Applications/kitty.app")),
    )
    # pyobjc available -> auto resolves to appkit
    monkeypatch.setattr(focus_debug, "_pyobjc_status", lambda: (True, "available"))
    detail = focus_debug._focus_detail(tmp_path)
    assert "auto-detect would use:" in detail
    assert "config tmux_focus.method:" in detail
    assert "AppKit" in detail
    assert "target session: work" in detail


def test_focus_detail_shows_enforced_method(tmp_path: Path, monkeypatch) -> None:
    from homebase.config import store as config_store

    config_store.save_global_config_dict(
        tmp_path, {"tmux_focus": {"method": "system_events"}}
    )
    monkeypatch.setattr(focus_debug, "resolve_external_tmux_target", lambda *_a, **_k: None)
    detail = focus_debug._focus_detail(tmp_path)
    assert "enforced" in detail
    assert "system_events" in detail


def test_enforce_hint_for_unconfigured_backend(tmp_path: Path) -> None:
    lines = focus_debug._enforce_hint(tmp_path, "system_events")
    text = "\n".join(lines)
    assert "tmux_focus:" in text
    assert "method: system_events" in text


def test_enforce_hint_debug_only_backend(tmp_path: Path) -> None:
    lines = focus_debug._enforce_hint(tmp_path, "system_events_osascript")
    text = "\n".join(lines)
    assert "debug-only" in text
    assert "tmux_focus:" not in text


def test_enforce_hint_when_already_configured(tmp_path: Path) -> None:
    from homebase.config import store as config_store

    config_store.save_global_config_dict(
        tmp_path, {"tmux_focus": {"method": "appkit"}}
    )
    lines = focus_debug._enforce_hint(tmp_path, "appkit")
    text = "\n".join(lines)
    assert "already the configured default" in text


def test_focus_detail_no_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        focus_debug, "resolve_external_tmux_target", lambda *_a, **_k: None
    )
    detail = focus_debug._focus_detail(tmp_path)
    assert "unavailable" in detail


def test_run_focus_no_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        focus_debug, "resolve_external_tmux_target", lambda *_a, **_k: None
    )
    report = focus_debug._run_focus(tmp_path, "auto", MainThreadActivator())
    assert "could not resolve a single tmux target" in report


def test_run_focus_auto_resolves_and_reports(tmp_path: Path, monkeypatch) -> None:
    # Non-darwin: resolution + auto-detect run, activation is skipped.
    monkeypatch.setattr(focus_debug.sys, "platform", "linux")
    monkeypatch.setattr(
        focus_debug,
        "resolve_external_tmux_target",
        lambda *_a, **_k: (None, [], lambda *_a: "300\n", "work"),
    )
    monkeypatch.setattr(
        client_focus,
        "process_ancestry",
        lambda pid: [(300, "tmux"), (100, "/Applications/kitty.app/Contents/MacOS/kitty")],
    )
    monkeypatch.setattr(
        client_focus,
        "macos_app_for_client_pid",
        lambda pid: (100, Path("/Applications/kitty.app")),
    )
    report = focus_debug._run_focus(tmp_path, "auto", MainThreadActivator())
    assert "target session: work" in report
    assert "client_pid:     300" in report
    assert "/Applications/kitty.app" in report
    assert "darwin-only" in report


def test_activate_with_appkit_warns_when_not_installed(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "AppKit":
            raise ImportError("No module named 'AppKit'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    ok, detail, elapsed = focus_debug._activate_with(
        "appkit", 123, None, [], MainThreadActivator()
    )
    assert ok is False
    assert "pyobjc is NOT installed" in detail
    assert elapsed == 0.0


class _FakeApp:
    def __init__(self, pid: int, name: str, bundle: str, *, active: bool = False):
        self._pid = pid
        self._name = name
        self._bundle = bundle
        self._active = active

    def processIdentifier(self):  # noqa: N802
        return self._pid

    def localizedName(self):  # noqa: N802
        return self._name

    def bundleIdentifier(self):  # noqa: N802
        return self._bundle

    def isActive(self):  # noqa: N802
        return self._active

    def activationPolicy(self):  # noqa: N802
        return 0

    def isFinishedLaunching(self):  # noqa: N802
        return True

    def isTerminated(self):  # noqa: N802
        return False

    def isHidden(self):  # noqa: N802
        return False

    def ownsMenuBar(self):  # noqa: N802
        return self._active


def test_appkit_diagnostics_reports_state_and_workspace() -> None:
    target = _FakeApp(123, "kitty", "net.kovidgoyal.kitty")
    frontmost = _FakeApp(456, "Terminal", "com.apple.Terminal", active=True)

    class _FakeWorkspace:
        def frontmostApplication(self):  # noqa: N802
            return frontmost

        def menuBarOwningApplication(self):  # noqa: N802
            return frontmost

    class _FakeNSWorkspace:
        @staticmethod
        def sharedWorkspace():  # noqa: N802
            return _FakeWorkspace()

    detail = "\n".join(
        focus_debug._appkit_diagnostics(target, 123, False, True, _FakeNSWorkspace)
    )
    assert "activate returned:  True" in detail
    assert "net.kovidgoyal.kitty" in detail
    assert "running pid:        123" in detail
    assert "regular (0)" in detail
    # the wrong app actually frontmost is the key diagnostic signal
    assert "workspace frontmost:" in detail
    assert "Terminal (pid 456, com.apple.Terminal)" in detail


def test_appkit_diagnostics_flags_pid_mismatch() -> None:
    target = _FakeApp(999, "kitty", "net.kovidgoyal.kitty")

    class _FakeWorkspace:
        def frontmostApplication(self):  # noqa: N802
            return None

        def menuBarOwningApplication(self):  # noqa: N802
            return None

    class _FakeNSWorkspace:
        @staticmethod
        def sharedWorkspace():  # noqa: N802
            return _FakeWorkspace()

    detail = "\n".join(
        focus_debug._appkit_diagnostics(target, 123, False, True, _FakeNSWorkspace)
    )
    assert "!= detected 123" in detail
    assert "workspace frontmost: <none>" in detail


def test_activation_policy_name_known_and_unknown() -> None:
    assert "regular" in focus_debug._activation_policy_name(0)
    assert "accessory" in focus_debug._activation_policy_name(1)
    assert "prohibited" in focus_debug._activation_policy_name(2)
    assert "unknown (7)" in focus_debug._activation_policy_name(7)


def test_activator_run_uses_installed_call() -> None:
    calls: list[object] = []

    def fake_call(fn):
        calls.append(fn)
        return fn()

    activator = MainThreadActivator(call=fake_call)
    assert activator.run(lambda: 42) == 42
    assert len(calls) == 1


def test_activator_run_inline_without_call() -> None:
    assert MainThreadActivator().run(lambda: "x") == "x"


def test_report_clients_lists_sessions_and_clients(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(focus_debug, "_known_sockets", lambda _bd: ["/tmp/sock"])
    monkeypatch.setattr(
        focus_debug,
        "resolve_external_tmux_target",
        lambda *_a, **_k: (None, [], None, "main"),
    )

    def fake_tmux(*args: str) -> str:
        if args[0] == "list-sessions":
            return "$1\tmain\t1\n$2\tother\t0\n"
        if args[0] == "list-clients":
            return "/dev/ttys001\t900\tmain\txterm\t123\n/dev/ttys002\t901\tmain\txterm\t124\n"
        raise AssertionError(args)

    monkeypatch.setattr(focus_debug, "_socket_tmux_fn", lambda _s: fake_tmux)

    report = focus_debug._report_clients(tmp_path)
    assert "main" in report and "other" in report
    assert "<- target" in report
    assert "pid=900" in report and "pid=901" in report
    assert "more than one client attached" in report


def test_report_clients_no_sockets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(focus_debug, "_known_sockets", lambda _bd: [])
    report = focus_debug._report_clients(tmp_path)
    assert "no tmux sockets found" in report


def test_report_macos_backends_non_darwin(monkeypatch) -> None:
    monkeypatch.setattr(focus_debug.sys, "platform", "linux")
    report = focus_debug._report_macos_backends()
    assert "not darwin" in report
