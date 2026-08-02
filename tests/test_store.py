from rp_agent.api.models import ApiConnection
from rp_agent.api.store import (
    delete_connection,
    get_connection,
    list_connections,
    save_connection,
)


def test_save_get_list_delete_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(
        name="demo",
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="gpt-4o",
    )
    save_connection(conn)
    assert list_connections() == ["demo"]
    loaded = get_connection("demo")
    assert loaded is not None
    assert loaded.base_url == "https://api.openai.com/v1"
    assert loaded.model == "gpt-4o"
    assert delete_connection("demo") is True
    assert get_connection("demo") is None
    assert delete_connection("demo") is False
    assert list_connections() == []


def test_get_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_connection("nope") is None
