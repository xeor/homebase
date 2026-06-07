import socket
from pathlib import Path

import pytest

from homebase_bts.backends.native import HostUnavailable, NativeBackend
from homebase_bts.models import Profile


def _profile() -> Profile:
    return Profile.model_validate(
        {"schema": 1, "id": "vacation", "tabs": [{"url": "https://maps.google.com/"}]}
    )


def test_snapshot_times_out_when_host_does_not_reply(monkeypatch):
    client, server = socket.socketpair()
    backend = NativeBackend(sock_path=Path("unused"), timeout=0.01)
    client.settimeout(backend.timeout)
    monkeypatch.setattr(backend, "_connect", lambda _timeout=None: client)

    try:
        with pytest.raises(HostUnavailable, match="did not reply"):
            backend.snapshot(_profile())
    finally:
        server.close()
