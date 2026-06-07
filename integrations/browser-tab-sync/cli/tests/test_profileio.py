from homebase_bts.models import Profile
from homebase_bts.profileio import load, resolve, write_atomic


def _profile(url: str) -> Profile:
    return Profile.model_validate({"schema": 1, "id": "x", "tabs": [{"url": url}]})


def test_write_atomic_keeps_distinct_history_entries(tmp_path):
    path = tmp_path / "profile.json"

    write_atomic(path, _profile("https://example.com/1"))
    write_atomic(path, _profile("https://example.com/2"))
    write_atomic(path, _profile("https://example.com/3"))

    history = sorted((tmp_path / ".homebase-bts" / "history").glob("profile.*.json"))
    assert len(history) == 2
    assert len({p.name for p in history}) == 2


def test_resolve_directory_prefers_base_bts_yaml(tmp_path):
    profile = tmp_path / ".base-bts.yaml"
    profile.write_text("schema: 1\nid: x\ntabs:\n  - url: https://example.com\n", encoding="utf-8")
    (tmp_path / ".homebase-bts.json").write_text(
        '{"schema":1,"id":"other","tabs":[]}\n',
        encoding="utf-8",
    )

    assert resolve(str(tmp_path)) == profile


def test_resolve_relative_paths_from_invocation_cwd(tmp_path, monkeypatch):
    invocation = tmp_path / "user"
    process = tmp_path / "repo" / "cli"
    invocation.mkdir()
    process.mkdir(parents=True)
    profile = invocation / ".base-bts.yaml"
    profile.write_text("schema: 1\nid: x\ntabs:\n  - url: https://example.com\n", encoding="utf-8")
    monkeypatch.chdir(process)
    monkeypatch.setenv("MISE_ORIGINAL_CWD", str(invocation))

    assert resolve(".") == profile


def test_resolve_relative_file_from_invocation_cwd(tmp_path, monkeypatch):
    invocation = tmp_path / "user"
    process = tmp_path / "repo" / "cli"
    invocation.mkdir()
    process.mkdir(parents=True)
    profile = invocation / "profile.json"
    profile.write_text('{"schema":1,"id":"x","tabs":[]}\n', encoding="utf-8")
    monkeypatch.chdir(process)
    monkeypatch.setenv("MISE_ORIGINAL_CWD", str(invocation))

    assert resolve("profile.json") == profile


def test_load_yaml_profile(tmp_path):
    path = tmp_path / ".base-bts.yaml"
    path.write_text("schema: 1\nid: x\ntabs:\n  - url: https://example.com\n", encoding="utf-8")

    assert resolve(str(tmp_path)) == path
    assert load(path).id == "x"
