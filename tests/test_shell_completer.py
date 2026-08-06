from prompt_toolkit.document import Document

from rp_agent.api.models import ApiConnection
from rp_agent.api.store import save_connection
from rp_agent.core.session import create_session, save_session
from rp_agent.shell import ShellCompleter


def _complete(monkeypatch, tmp_path, text: str):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    s = create_session()
    s.name = "三体会话"
    save_session(s)
    save_connection(
        ApiConnection(
            name="deepseek",
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model="deepseek-chat",
        )
    )
    doc = Document(text)
    return list(ShellCompleter().get_completions(doc, None))


def _names(result):
    return [c.text for c in result]


# --- 静态:命令名 / 子命令(沿用 Task 1) ---

def test_command_name_completes_after_prefix(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "a"))
    assert "api" in names and "agent" in names


def test_command_name_completes_empty_line(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, ""))
    assert "api" in names and "help" in names


def test_slash_command_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "/l"))
    assert "/load" in names


def test_subcommand_completes_after_prefix(monkeypatch, tmp_path):
    assert "list" in _names(_complete(monkeypatch, tmp_path, "api li"))


def test_unknown_command_offers_nothing(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "foobar ") == []


# --- 选项 ---

def test_option_completes_after_dash_prefix(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api add --n"))
    assert "--name" in names


def test_short_option_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api del -"))
    assert "-f" in names and "-v" in names


def test_option_does_not_match_unknown(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "api add --wat") == []


def test_option_completes_after_multiple_positional(monkeypatch, tmp_path):
    # 多参数后再补选项(规格:第 3+ 词以 - 开头 → 选项)
    names = _names(_complete(monkeypatch, tmp_path, "api add --name foo --m"))
    assert "--model" in names


# --- 位置参数:连接名 / 会话名 ---

def test_connection_name_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api get "))
    assert "deepseek" in names


def test_connection_name_partial(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api test deep"))
    assert "deepseek" in names


def test_session_name_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "chat get "))
    assert "三体会话" in names


def test_slash_load_completes_session(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "/load 三体"))
    assert "三体会话" in names


def test_second_arg_not_completed(monkeypatch, tmp_path):
    # chat rename 第二参(新名)不补全
    assert _complete(monkeypatch, tmp_path, "chat rename 三体会话 新") == []
    assert _complete(monkeypatch, tmp_path, "api get deepseek ") == []
