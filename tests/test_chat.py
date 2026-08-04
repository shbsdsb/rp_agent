from rp_agent.core.chat import (
    list_sessions,
    load_session,
    new_session,
    send_message,
    set_connection,
    system_prompt,
)
from rp_agent.core.session import create_session, save_session


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.api.models import ApiConnection
    from rp_agent.api.store import save_connection

    save_connection(
        ApiConnection(name="demo", base_url="https://x/v1", api_key="k", model="m")
    )


def test_system_prompt_empty_returns_none():
    # 预设 system 已清空(用户要求),加载结果为 None → 对话不带 system 消息
    assert system_prompt() is None


def test_new_session_uses_default_connection(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from rp_agent.api.store import set_default_connection

    set_default_connection("demo")
    s = new_session()
    assert s.connection == "demo"


def test_new_session_no_default_prints_hint(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    new_session()
    out = capsys.readouterr().out
    assert "api use" in out  # 提示手动设置
    assert "demo" in out     # 列出可用连接


def test_send_message_success(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "rp_agent.core.chat.chat",
        lambda conn, messages, **kw: "你好呀!",
    )
    s = create_session(connection="demo")
    save_session(s)
    send_message(s, "你好")
    out = capsys.readouterr().out
    assert "assistant> " in out  # 回复带 assistant> 前缀
    assert "你好呀!" in out
    assert s.messages[-1] == {"role": "assistant", "content": "你好呀!"}
    from rp_agent.core.session import load_session

    loaded = load_session(s.id)
    assert loaded is not None and len(loaded.messages) == 2  # 已持久化


def test_send_message_no_connection(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    s = create_session()  # connection=""
    save_session(s)
    send_message(s, "你好")
    out = capsys.readouterr().out
    assert "未设置连接" in out
    assert len(s.messages) == 1  # user 消息保留,无 assistant


def test_send_message_api_error(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.api.client import ApiError

    monkeypatch.setattr(
        "rp_agent.core.chat.chat",
        lambda conn, messages, **kw: (_ for _ in ()).throw(ApiError("boom")),
    )
    s = create_session(connection="demo")
    save_session(s)
    send_message(s, "你好")
    out = capsys.readouterr().out
    assert "boom" in out
    assert len(s.messages) == 1  # 无 assistant 追加


def test_send_message_without_system_prompt(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    captured: dict = {}

    def fake_chat(conn, messages, **kw):
        captured["messages"] = list(messages)
        return "ok"

    monkeypatch.setattr("rp_agent.core.chat.chat", fake_chat)
    s = create_session(connection="demo")
    send_message(s, "hi")
    roles = {m["role"] for m in captured["messages"]}
    assert "system" not in roles  # 预设已清空,不带 system 消息
    assert captured["messages"][-1] == {"role": "user", "content": "hi"}


def test_send_message_uses_global_timeout(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    captured: dict = {}

    def fake_chat(conn, messages, **kw):
        captured["kwargs"] = kw
        return "ok"

    monkeypatch.setattr("rp_agent.core.chat.chat", fake_chat)
    s = create_session(connection="demo")
    send_message(s, "hi")
    from rp_agent.config import get_config

    assert captured["kwargs"].get("timeout") == get_config().timeout


def test_set_connection_updates_and_saves(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    s = create_session()
    set_connection(s, "demo")
    assert s.connection == "demo"
    assert "已切换" in capsys.readouterr().out
    from rp_agent.core.session import load_session

    assert load_session(s.id) is not None


def test_set_connection_missing_name(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    s = create_session()
    set_connection(s, "nope")
    assert "连接不存在" in capsys.readouterr().out
    assert s.connection == ""


def test_load_session_missing(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    assert load_session("nope") is None
    assert "会话不存在" in capsys.readouterr().out


def test_list_sessions_prints(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    s = create_session(connection="demo")
    save_session(s)
    list_sessions()
    out = capsys.readouterr().out
    assert s.id in out


def test_list_sessions_shows_name(monkeypatch, tmp_path, capsys):
    """rename 后 list 应显示可读名称而非文件 id。"""
    _setup(monkeypatch, tmp_path)
    s = create_session()
    s.name = "打招呼"
    save_session(s)
    list_sessions()
    out = capsys.readouterr().out
    assert "打招呼" in out


def test_find_session_by_id_and_name(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    s = create_session()
    s.name = "我的会话"
    save_session(s)
    from rp_agent.core.chat import find_session

    assert find_session(s.id).id == s.id
    assert find_session("我的会话").id == s.id
    assert find_session("nope") is None


def test_rename_session(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_session

    s = create_session()
    save_session(s)
    rename_session(s, "新名字")
    assert s.name == "新名字"
    assert "已重命名" in capsys.readouterr().out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "新名字"


def test_rename_session_empty_rejected(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_session

    s = create_session()
    rename_session(s, "   ")
    assert "名称不能为空" in capsys.readouterr().out
    assert s.name == ""


def test_rename_by_key(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_by_key

    s = create_session()
    save_session(s)
    rename_by_key(s.id, "重命名后")
    assert "已重命名" in capsys.readouterr().out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "重命名后"


def test_session_names_lists_name_or_id(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import session_names

    named = create_session()
    named.name = "甲"
    save_session(named)
    unnamed = create_session()
    save_session(unnamed)
    names = session_names()
    assert "甲" in names
    assert unnamed.id in names  # 未命名显示 id
