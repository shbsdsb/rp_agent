from rp_agent.api.models import ApiConnection
from rp_agent.api.store import (
    connection_exists,
    delete_connection,
    get_connection,
    get_default_connection,
    get_default_name,
    list_connections,
    save_connection,
    set_default_connection,
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


def test_default_connection_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(name="d", base_url="https://x/v1", api_key="k", model="m")
    save_connection(conn)
    assert get_default_connection() is None
    set_default_connection("d")
    loaded = get_default_connection()
    assert loaded is not None and loaded.name == "d"
    set_default_connection("d")  # 覆盖写幂等
    assert get_default_connection() is not None


def test_default_connection_missing_name_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_default_connection() is None


def test_get_connection_empty_name_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_connection("") is None


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


def test_connection_exists_checks_filename_only(monkeypatch, tmp_path, caplog):
    """存在性检查只查文件名:不存在/空名返回 False,且不打日志。"""
    import logging

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(name="demo", base_url="https://x/v1", api_key="k", model="m")
    save_connection(conn)
    with caplog.at_level(logging.WARNING, logger="rp_agent"):
        assert connection_exists("demo") is True
        assert connection_exists("nope") is False
        assert connection_exists("") is False
    assert "读取 JSON 失败" not in caplog.text
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


def test_get_default_name_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_default_name() is None  # 未设置
    set_default_connection("d")
    assert get_default_name() == "d"


def test_get_default_name_empty_and_corrupt(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    set_default_connection("")  # 空名
    assert get_default_name() is None
    (tmp_path / "default_connection.json").write_text("not a dict", encoding="utf-8")
    assert get_default_name() is None  # 损坏文件 → None,不崩溃
