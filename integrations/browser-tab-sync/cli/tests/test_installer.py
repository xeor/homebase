import json
from pathlib import Path

from homebase_bts import installer


def test_install_writes_single_manifest(tmp_path: Path):
    directory = tmp_path / "Chromium" / "NativeMessagingHosts"

    path = installer.install_native_host("abcdefghijklmnop", directory=directory)

    assert path == directory / f"{installer.HOST_NAME}.json"
    manifest = json.loads(path.read_text())
    assert manifest["name"] == installer.HOST_NAME
    assert manifest["type"] == "stdio"
    assert manifest["allowed_origins"] == ["chrome-extension://abcdefghijklmnop/"]
    assert manifest["path"].endswith("homebase-bts-host")


def test_install_requires_target():
    import pytest

    with pytest.raises(ValueError):
        installer.install_native_host("abcdefghijklmnop")


def test_install_into_explicit_dir(tmp_path: Path):
    # The dev flow writes into the dev profile's NativeMessagingHosts dir.
    directory = tmp_path / ".dev-profile" / "NativeMessagingHosts"
    path = installer.install_native_host("abcdefghijklmnop", directory=directory)
    assert path == directory / f"{installer.HOST_NAME}.json"
    assert path.exists()


def test_vivaldi_manifest_dir_on_macos(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert installer.manifest_dir(installer.Browser.vivaldi) == (
        tmp_path / "Library" / "Application Support" / "Vivaldi" / "NativeMessagingHosts"
    )


def test_install_vivaldi_manifest(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))

    path = installer.install_native_host("abcdefghijklmnop", browser=installer.Browser.vivaldi)

    assert path == (
        tmp_path
        / "Library"
        / "Application Support"
        / "Vivaldi"
        / "NativeMessagingHosts"
        / f"{installer.HOST_NAME}.json"
    )
    manifest = json.loads(path.read_text())
    assert manifest["allowed_origins"] == ["chrome-extension://abcdefghijklmnop/"]
    assert manifest["path"].endswith("homebase-bts-host")


def test_extension_id_for_path_golden():
    # Chrome's unpacked-extension ID derivation (verified against a real load).
    path = Path("/Users/xeor/base/browser-session-file/extension/.output/chrome-mv3")
    ext_id = installer.extension_id_for_path(path)
    assert ext_id == "jcomndlancedcpkmdoklcpjgocemlaei"
    assert len(ext_id) == 32
    assert all("a" <= c <= "p" for c in ext_id)


def test_uninstall_removes_manifest(tmp_path: Path):
    directory = tmp_path / "Chromium" / "NativeMessagingHosts"
    installer.install_native_host("abcdefghijklmnop", directory=directory)

    removed = installer.uninstall_native_host(dirs=[directory])

    assert removed == [directory / f"{installer.HOST_NAME}.json"]
    assert not (directory / f"{installer.HOST_NAME}.json").exists()


def test_doctor_checks_host_roundtrip_when_socket_exists(monkeypatch, tmp_path: Path):
    sock = tmp_path / "host.sock"
    sock.touch()
    monkeypatch.setattr(installer.config, "host_sock", lambda: sock)
    monkeypatch.setattr(
        installer,
        "_check_host_roundtrip",
        lambda path: installer.Check("host roundtrip", True, f"checked {path.name}"),
    )

    checks = installer.doctor()

    assert checks[-1] == installer.Check("host roundtrip", True, "checked host.sock")
