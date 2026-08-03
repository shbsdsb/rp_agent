from rp_agent.core.session import (
    append_message,
    create_session,
    list_sessions,
    load_session,
    save_session,
)


def test_create_session_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session()
    assert s.id
    assert s.connection == ""
    assert s.messages == []
    assert s.created_at
    assert s.updated_at


def test_save_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session(connection="deepseek")
    append_message(s, "user", "你好")
    append_message(s, "assistant", "你好!")
    save_session(s)
    loaded = load_session(s.id)
    assert loaded is not None
    assert loaded.connection == "deepseek"
    assert len(loaded.messages) == 2
    assert loaded.messages[0] == {"role": "user", "content": "你好"}


def test_append_updates_updated_at(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session()
    before = s.updated_at
    append_message(s, "user", "x")
    assert s.updated_at >= before
    assert len(s.messages) == 1


def test_load_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    assert load_session("nope") is None


def test_list_sessions_newest_first(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    # 用可控 _now 制造不同 updated_at,避免同秒创建导致排序不稳
    monkeypatch.setattr(
        "rp_agent.core.session._now", lambda: "2026-01-01T00:00:00+00:00"
    )
    s1 = create_session()
    save_session(s1)
    monkeypatch.setattr(
        "rp_agent.core.session._now", lambda: "2026-02-01T00:00:00+00:00"
    )
    s2 = create_session()
    save_session(s2)
    ids = [s.id for s in list_sessions()]
    assert ids == [s2.id, s1.id]  # updated_at 新的在最前


def test_session_id_is_safe_and_unique(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s1 = create_session()
    s2 = create_session()
    assert s1.id != s2.id
    assert ".." not in s1.id and "/" not in s1.id and "\\" not in s1.id
