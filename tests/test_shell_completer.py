from prompt_toolkit.document import Document

from rp_agent.shell import ChatSessionCompleter


def _complete(monkeypatch, tmp_path, text: str):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    s.name = "三体会话"
    save_session(s)
    doc = Document(text)
    return list(ChatSessionCompleter().get_completions(doc, None))


def _names(result):
    return [c.text for c in result]


def test_rename_completer_suggests_after_prefix(monkeypatch, tmp_path):
    assert "三体会话" in _names(_complete(monkeypatch, tmp_path, "chat rename "))


def test_rename_completer_suggests_partial_word(monkeypatch, tmp_path):
    assert "三体会话" in _names(_complete(monkeypatch, tmp_path, "chat rename 三体"))


def test_get_completer_suggests(monkeypatch, tmp_path):
    assert "三体会话" in _names(_complete(monkeypatch, tmp_path, "chat get "))


def test_load_completer_suggests(monkeypatch, tmp_path):
    assert "三体会话" in _names(_complete(monkeypatch, tmp_path, "chat load "))


def test_slash_load_completer_suggests(monkeypatch, tmp_path):
    assert "三体会话" in _names(_complete(monkeypatch, tmp_path, "/load "))


def test_rename_completer_ignores_other_commands(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "api list") == []
    assert _complete(monkeypatch, tmp_path, "chat foobar ") == []


def test_completer_ignores_second_arg(monkeypatch, tmp_path):
    # chat rename <旧> <新> 已输入第二个参数 → 不再补全
    assert _complete(monkeypatch, tmp_path, "chat rename 三体会话 新") == []
    assert _complete(monkeypatch, tmp_path, "chat load 三体会话 ") == []
    assert _complete(monkeypatch, tmp_path, "/load 三体会话 ") == []
