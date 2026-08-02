from rp_agent.config import get_config, load_config_file, reload_config


def test_default_log_level():
    assert get_config(force_reload=True).log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("RP_AGENT_LOG_LEVEL", "DEBUG")
    assert get_config(force_reload=True).log_level == "DEBUG"


def test_singleton():
    assert get_config() is get_config()


def test_load_config_file(tmp_path):
    import json

    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    assert load_config_file(p) == {"log_level": "WARNING"}


def test_load_config_missing_returns_empty(tmp_path):
    assert load_config_file(tmp_path / "nope.json") == {}


def test_load_config_broken_json_returns_empty(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_config_file(p) == {}


def test_file_overrides_default(monkeypatch, tmp_path):
    import json

    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    assert get_config(force_reload=True).log_level == "WARNING"


def test_env_overrides_file(monkeypatch, tmp_path):
    import json

    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    monkeypatch.setenv("RP_AGENT_LOG_LEVEL", "DEBUG")
    assert get_config(force_reload=True).log_level == "DEBUG"


def test_reload_config_changed_detection(monkeypatch, tmp_path):
    import json

    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "INFO"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    reload_config()
    assert reload_config() is False  # 内容未变
    p.write_text(json.dumps({"log_level": "DEBUG"}), encoding="utf-8")
    assert reload_config() is True  # 内容已变
