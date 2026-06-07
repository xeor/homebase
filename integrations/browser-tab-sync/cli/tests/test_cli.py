import json

from typer.testing import CliRunner

from homebase_bts import config
from homebase_bts.cli import app


def _profile(path):
    path.write_text(
        '{"schema":1,"id":"x","tabs":[{"url":"https://example.com"}]}\n',
        encoding="utf-8",
    )


def test_status_reports_local_diff(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    _profile(profile)
    monkeypatch.setattr(config, "sim_store", lambda: tmp_path / "sim.json")

    result = CliRunner().invoke(app, ["status", str(profile), "--local"])

    assert result.exit_code == 0
    assert "browser: chrome (dry-run)" in result.stdout
    assert "tabs:    0 existing, 1 created" in result.stdout


def test_export_merges_local_snapshot_into_file(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    _profile(profile)
    sim = tmp_path / "sim.json"
    sim.write_text(
        json.dumps(
            {
                "x": {
                    "group_id": 1,
                    "next_tab_id": 3,
                    "tabs": [
                        {
                            "browser_tab_id": 1,
                            "url": "https://example.com",
                            "active": False,
                            "index": 0,
                        },
                        {
                            "browser_tab_id": 2,
                            "url": "https://news.ycombinator.com",
                            "active": False,
                            "index": 1,
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "sim_store", lambda: sim)

    result = CliRunner().invoke(app, ["export", str(profile), "--local"])

    assert result.exit_code == 0
    assert "file:    profile.json (updated)" in result.stdout
    assert "https://news.ycombinator.com" in profile.read_text(encoding="utf-8")


def test_apply_defaults_to_current_directory_profile_with_local_backend(tmp_path, monkeypatch):
    profile = tmp_path / ".base-bts.yaml"
    profile.write_text("schema: 1\nid: x\ntabs:\n  - url: https://example.com\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "sim_store", lambda: tmp_path / "sim.json")

    result = CliRunner().invoke(app, ["apply", "--local"])

    assert result.exit_code == 0
    assert "x" in result.stdout
    assert (tmp_path / "sim.json").is_file()
