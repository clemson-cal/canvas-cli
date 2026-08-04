"""Tests for .canvas.json / environment configuration loading."""

import json

from canvas_md import get_config

ENV_VARS = ["CANVAS_API_URL", "CANVAS_API_TOKEN", "CANVAS_COURSE_ID", "CANVAS_THEME_COLOR"]


def clear_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_reads_config_file(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    config_path = tmp_path / ".canvas.json"
    config_path.write_text(json.dumps({
        "api_url": "https://example.instructure.com",
        "api_token": "tok",
        "course_id": "42",
    }))
    config = get_config(config_path)
    assert config["api_url"] == "https://example.instructure.com"
    assert config["api_token"] == "tok"
    assert config["course_id"] == "42"


def test_env_overrides_file(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    config_path = tmp_path / ".canvas.json"
    config_path.write_text(json.dumps({"api_url": "https://file.example.com", "api_token": "file-tok"}))
    monkeypatch.setenv("CANVAS_API_URL", "https://env.example.com")
    monkeypatch.setenv("CANVAS_COURSE_ID", "99")
    config = get_config(config_path)
    assert config["api_url"] == "https://env.example.com"
    assert config["api_token"] == "file-tok"
    assert config["course_id"] == "99"


def test_missing_file_yields_env_only(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("CANVAS_API_TOKEN", "env-tok")
    config = get_config(tmp_path / "nonexistent.json")
    assert config == {"api_token": "env-tok"}
