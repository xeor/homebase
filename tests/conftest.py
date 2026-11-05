from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_herdr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never talk to the herdr server the suite may run inside."""
    for name in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/nonexistent/herdr.sock")
