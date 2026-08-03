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


def test_roundtrip_new_fields(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(
        name="d",
        base_url="https://x/v1",
        api_key="k",
        model="m",
        models_endpoint="/custom-models",
        last_tested="2026-08-03T00:00:00+00:00",
    )
    save_connection(conn)
    loaded = get_connection("d")
    assert loaded is not None
    assert loaded.models_endpoint == "/custom-models"
    assert loaded.last_tested == "2026-08-03T00:00:00+00:00"


def test_old_file_backward_compat(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    (tmp_path / "api" / "old.json").write_text(
        '{"name": "old", "base_url": "https://x", "api_key": "k", "model": "m"}',
        encoding="utf-8",
    )
    loaded = get_connection("old")
    assert loaded is not None
    assert loaded.models_endpoint == "/models"
    assert loaded.last_tested == ""
