from __future__ import annotations

from homebase.workspace.new.detect import classify_input, is_path_shaped, is_url


def test_url_http() -> None:
    assert is_url("https://github.com/foo/bar")
    assert classify_input("https://github.com/foo/bar") == "url"


def test_url_ssh_git() -> None:
    assert is_url("git@github.com:foo/bar.git")
    assert classify_input("git@github.com:foo/bar.git") == "url"


def test_path_dot_slash() -> None:
    assert is_path_shaped("./thing")
    assert classify_input("./thing") == "path"


def test_path_absolute() -> None:
    assert is_path_shaped("/abs/path")
    assert is_path_shaped("~/home/path")
    assert classify_input("/abs/path") == "path"


def test_path_trailing_slash() -> None:
    assert is_path_shaped("name/")
    assert classify_input("name/") == "path"


def test_path_with_separator() -> None:
    assert is_path_shaped("a/b")
    assert classify_input("a/b") == "path"


def test_bare_token() -> None:
    assert not is_path_shaped("myproj")
    assert classify_input("myproj") == "bare"


def test_empty_or_none() -> None:
    assert classify_input(None) == "empty"
    assert classify_input("") == "empty"


def test_path_single_dot() -> None:
    assert is_path_shaped(".")
    assert classify_input(".") == "path"
