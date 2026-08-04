import pytest

from rp_agent.api.store import get_connection
from rp_agent.shell import parse_line, run_shell


@pytest.fixture(autouse=True)
def _reset_shell_state():
    """重置 shell 模块级状态(_chat_session/_current_mode),隔离测试间污染。"""
    import rp_agent.shell as shell_mod

    shell_mod._chat_session = None
    shell_mod._current_mode = "home"
    yield


def _feed(lines: list[str]):
    """返回注入式 _input:按序返回行,耗尽后抛 EOFError。"""
    it = iter(lines)

    def _inner(_prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return _inner


def test_parse_line():
    assert parse_line("  hello  world  ") == ("hello", ["world"])
    assert parse_line("") == ("", [])
    assert parse_line("   ") == ("", [])


def test_run_shell_sequence(capsys):
    run_shell(_feed(["hello", "config", "exit"]))
    out = capsys.readouterr().out
    assert "你好" in out
    assert "log_level" in out
    assert "退出" in out


def test_run_shell_unknown_command(capsys):
    run_shell(_feed(["foobar", "exit"]))
    out = capsys.readouterr().out
    assert "未知命令" in out


def test_run_shell_eof(capsys):
    run_shell(_feed([]))  # 立即 EOFError
    out = capsys.readouterr().out
    assert "退出" in out


def test_help_lists_commands(capsys):
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    for name in ("help", "config", "reload", "hello", "history", "exit", "chat", "rp", "agent"):
        assert name in out


def test_shell_api_list_empty(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["api list", "exit"]))
    out = capsys.readouterr().out
    assert "(无连接)" in out


def test_shell_api_add_and_get(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name demo --url http://localhost:8000/v1 --key k --model gpt-4o",
                "api get demo",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "base_url=http://localhost:8000/v1" in out
    assert "api_key=****" in out  # key "k" 长度<=8


def test_shell_api_add_exists_without_modify(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api add --name d --url https://x/v1 --key k --model m",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "连接已存在" in out


def test_shell_api_add_modify_overwrites(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api add --modify --name d --url https://x/v2 --key k2 --model m2",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存连接" in out
    conn = get_connection("d")
    assert conn is not None and conn.base_url == "https://x/v2"


def test_shell_api_get_masks_key(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key sk-1234567890abcdef --model m",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "sk-1****cdef" in out
    assert "sk-1234567890abcdef" not in out


def test_shell_api_modify_set_atomic(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api modify d --set model=gpt-5 --set badfield=1",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "未知字段" in out
    assert "model=gpt-5" not in out  # 原子:未写入


def test_shell_api_del_confirm_decline(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    monkeypatch.setattr("rp_agent.shell._confirm", lambda _p: "n")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api del d",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已取消" in out
    assert get_connection("d") is not None  # 未删除


def test_shell_api_del_force(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api del d -f",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已删除连接" in out
    assert "连接不存在" in out


def test_modify_interactive_save(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    responses = iter(
        [
            ("https://new/v1", "normal"),
            ("newkey", "normal"),
            ("gpt-5", "save"),
        ]
    )
    monkeypatch.setattr(
        "rp_agent.shell._prompt_field",
        lambda _l, _c, _s: next(responses),
    )
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api modify d",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存" in out
    conn = get_connection("d")
    assert conn is not None
    assert conn.base_url == "https://new/v1"
    assert conn.model == "gpt-5"


def test_modify_interactive_cancel(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    monkeypatch.setattr(
        "rp_agent.shell._prompt_field",
        lambda _l, _c, _s: ("", "cancel"),
    )
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api modify d",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已放弃修改" in out
    conn = get_connection("d")
    assert conn is not None and conn.model == "m"  # 未修改


def test_shell_api_name_dash_m_equals_modify(monkeypatch, capsys, tmp_path):
    """api <name> -m 等价 api modify <name>(进入交互编辑)。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    monkeypatch.setattr(
        "rp_agent.shell._prompt_field",
        lambda _l, _c, _s: ("", "cancel"),
    )
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api d -m",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已放弃修改" in out  # 进入 modify 交互
    conn = get_connection("d")
    assert conn is not None and conn.model == "m"  # 未修改


def test_shell_api_unknown_subcommand(capsys):
    run_shell(_feed(["api foobar", "exit"]))
    out = capsys.readouterr().out
    assert "未知子命令" in out


def test_shell_api_name_dash_m_with_set(monkeypatch, capsys, tmp_path):
    """api <name> -m --set f=v 等价 api modify <name> --set f=v(非交互)。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api d -m --set model=gpt-5",
                "api get d",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已更新连接" in out
    conn = get_connection("d")
    assert conn is not None and conn.model == "gpt-5"


def test_shell_help_shows_alias_same_line(capsys):
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "exit/quit" in out
    assert "help/?" in out


def test_shell_command_dash_help(capsys):
    run_shell(_feed(["config --help", "exit"]))
    out = capsys.readouterr().out
    assert "用法" in out
    assert "config" in out


def test_shell_api_dash_help(capsys):
    run_shell(_feed(["api --help", "exit"]))
    out = capsys.readouterr().out
    assert "用法" in out
    assert "get <name>" in out


def test_shell_output_no_ansi_in_capsys(capsys):
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "\033" not in out  # capsys 非 tty,颜色关闭


def test_help_overview_desc_aligned(capsys):
    """help 概览 desc 同一列:不再使用 \t(短/长命令缩进不齐)。"""
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "\t" not in out


def test_storage_command_removed(capsys):
    run_shell(_feed(["storage", "exit"]))
    out = capsys.readouterr().out
    assert "未知命令: storage" in out


def test_shell_home_prompt_prefix():
    prompts: list[str] = []

    def _inner(p: str) -> str:
        prompts.append(p)
        return "exit"

    run_shell(_inner)
    assert prompts[0] == "home> "


def test_shell_switch_to_chat_mode(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    prompts: list[str] = []
    seq = iter(["chat", "你好呀", "/exit", "exit"])

    def _inner(p: str) -> str:
        prompts.append(p)
        try:
            return next(seq)
        except StopIteration:
            raise EOFError from None

    run_shell(_inner)
    out = capsys.readouterr().out
    assert "chat> " in prompts              # 前缀切换为 chat>
    assert "新会话" in out                   # 进入 chat 自动新建会话
    assert "home> " in prompts              # /exit 回到 home


def test_shell_mode_switch_among_modes(capsys):
    prompts: list[str] = []
    seq = iter(["chat", "/rp", "/agent", "/exit", "exit"])

    def _inner(p: str) -> str:
        prompts.append(p)
        try:
            return next(seq)
        except StopIteration:
            raise EOFError from None

    run_shell(_inner)
    assert "chat> " in prompts
    assert "rp> " in prompts
    assert "agent> " in prompts


def test_shell_escape_api_in_chat_mode(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat", "/api list", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "(无连接)" in out  # /api list 在 chat 模式可正常执行


def test_shell_exit_in_mode_is_placeholder(capsys):
    run_shell(_feed(["chat", "exit", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "[chat] 对话功能尚未实现" in out  # 模式内 exit 视为对话内容
    exits = [l for l in out.splitlines() if l == "退出"]
    assert len(exits) == 1  # 仅最终 home 模式 exit 退出


def test_shell_initial_mode_agent(capsys):
    prompts: list[str] = []
    seq = iter(["hello", "/exit", "exit"])

    def _inner(p: str) -> str:
        prompts.append(p)
        try:
            return next(seq)
        except StopIteration:
            raise EOFError from None

    run_shell(_inner, initial_mode="agent")
    assert prompts[0] == "agent> "  # 从 agent 模式启动


def test_config_shows_timeout(capsys):
    run_shell(_feed(["config", "exit"]))
    out = capsys.readouterr().out
    assert "timeout" in out


def test_config_set_timeout(monkeypatch, tmp_path, capsys):
    import json

    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "INFO", "timeout": 300}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    run_shell(_feed(["config timeout 500", "config", "exit"]))
    out = capsys.readouterr().out
    assert "已设置全局超时" in out
    assert "timeout=500.0s" in out


def test_shell_chat_message_sends(monkeypatch, tmp_path, capsys):
    """chat 模式普通输入调用 send_message(替换占位报错)。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.api.models import ApiConnection
    from rp_agent.api.store import save_connection

    save_connection(ApiConnection(name="demo", base_url="https://x/v1", api_key="k", model="m"))
    from rp_agent.api.store import set_default_connection

    set_default_connection("demo")
    monkeypatch.setattr(
        "rp_agent.core.chat.chat",
        lambda conn, messages, **kw: "回复内容",
    )
    run_shell(_feed(["chat", "你好", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "回复内容" in out


def test_shell_chat_new_list_load(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat", "/new", "/list", "/load nope", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "新会话" in out        # /new
    assert "无历史会话" in out or "(无历史会话)" in out
    assert "会话不存在" in out     # /load nope


def test_shell_api_use_home_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.api.models import ApiConnection
    from rp_agent.api.store import save_connection

    save_connection(ApiConnection(name="demo", base_url="https://x/v1", api_key="k", model="m"))
    run_shell(_feed(["api use demo", "chat", "/api use demo", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "已设置全局默认连接" in out   # home 可用
    assert "仅可在 home 模式使用" in out  # chat 模式(/api use)被拒


def test_shell_api_set_chat_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.api.models import ApiConnection
    from rp_agent.api.store import save_connection

    save_connection(ApiConnection(name="demo", base_url="https://x/v1", api_key="k", model="m"))
    run_shell(_feed(["api set demo", "chat", "/api set demo", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert "仅可在对话模式内使用" in out  # home 被拒
    assert "已切换会话连接" in out        # chat 模式(/api set)可用


def test_shell_chat_list_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat list", "exit"]))
    out = capsys.readouterr().out
    assert "(无历史会话)" in out  # chat list 走子命令而非进入模式


def test_shell_chat_rename_two_args(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat rename {s.id} 新名", "exit"]))
    out = capsys.readouterr().out
    assert "已重命名" in out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "新名"


def test_shell_chat_get_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat get {s.id}", "exit"]))
    assert "消息数" in capsys.readouterr().out


def test_shell_chat_load_enters_chat(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat load {s.id}", "exit"]))
    assert "已加载会话" in capsys.readouterr().out


def test_shell_rename_in_chat_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat", "/rename 新对话", "/exit", "exit"]))
    assert "已重命名" in capsys.readouterr().out


def test_shell_chat_unknown_subcommand(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat foobar", "exit"]))
    assert "未知子命令" in capsys.readouterr().out


def test_shell_reenter_chat_creates_new_session(monkeypatch, tmp_path, capsys):
    """每次进入 chat 模式都新建会话(不复用旧会话,以便拿到最新默认连接)。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat", "/exit", "chat", "/exit", "exit"]))
    out = capsys.readouterr().out
    assert out.count("新会话") == 2  # 两次进入各新建一次
