from rp_agent.config import get_config


def test_default_log_level():
    assert get_config(force_reload=True).log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("RP_AGENT_LOG_LEVEL", "DEBUG")
    assert get_config(force_reload=True).log_level == "DEBUG"


def test_singleton():
    assert get_config() is get_config()
