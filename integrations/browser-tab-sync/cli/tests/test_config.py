import os
import stat

from homebase_bts import config


def test_host_socket_uses_runtime_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HBTS_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    assert config.host_sock() == tmp_path / "runtime" / "homebase-bts" / "host.sock"


def test_host_socket_prefers_xdg_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("HBTS_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg-runtime"))

    assert config.host_sock() == tmp_path / "xdg-runtime" / "homebase-bts" / "host.sock"


def test_ensure_dirs_creates_private_runtime_dir(tmp_path, monkeypatch):
    config_root = tmp_path / "config"
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("HBTS_RUNTIME_DIR", str(runtime_root))

    config.ensure_dirs()

    mode = stat.S_IMODE(os.stat(config.runtime_dir()).st_mode)
    assert config.config_dir().is_dir()
    assert config.log_dir().is_dir()
    assert mode == 0o700
