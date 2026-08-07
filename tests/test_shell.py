import pytest

from rp_agent.api.store import get_connection
from rp_agent.shell import handle_line, parse_line, run_shell


@pytest.fixture(autouse=True)
def _reset_shell_state():
    """重置 shell 模块级状态(_chat_session/_current_mode/_quit_request 等),隔离测试间污染。"""
    import rp_agent.shell as shell_mod

    shell_mod._chat_session = None
    shell_mod._current_mode = "home"
    shell_mod._mode_switch_request = None
    shell_mod._quit_request = False
    # REPL 相关测试统一走 cli 分支(默认 tui 会在非 tty 下启动全屏 TUI 阻塞等待键盘)
    shell_mod._ui_mode = "cli"
    shell_mod._ui_switch_request = None
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
            ("", "normal"),  # name:回车保留原值 d
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


def test_shell_api_modify_set_rename(capsys, monkeypatch, tmp_path):
    """api modify --set name=新名 重命名连接:新名保存、旧名文件删除。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api modify d --set name=e",
                "api get e",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已更新连接: e" in out
    assert get_connection("e") is not None  # 新名存在
    assert get_connection("d") is None  # 旧名已删除
    assert get_connection("e").base_url == "https://x/v1"  # 其余字段保留


def test_shell_api_modify_set_rename_conflict(capsys, monkeypatch, tmp_path):
    """改名目标已存在 → 拒绝,原连接不受影响。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api add --name e --url https://y/v2 --key k2 --model m2",
                "api modify d --set name=e",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "连接已存在: e" in out
    assert get_connection("d") is not None
    assert get_connection("e").base_url == "https://y/v2"  # 未被覆盖


def test_shell_api_modify_set_rename_empty(capsys, monkeypatch, tmp_path):
    """--set name= 空名 → 拒绝。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api modify d --set name=",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "连接名不能为空" in out
    assert get_connection("d") is not None


def test_api_add_and_rename_produce_no_missing_file_warning(
    capsys, monkeypatch, tmp_path, caplog
):
    """存在性检查不得触发 json_read 的"读取 JSON 失败"告警(误导性日志)。"""
    import logging

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    with caplog.at_level(logging.WARNING, logger="rp_agent"):
        run_shell(
            _feed(
                [
                    "api add --name d --url https://x/v1 --key k --model m",
                    "api modify d --set name=e",
                    "api get e",
                    "exit",
                ]
            )
        )
    assert "读取 JSON 失败" not in caplog.text
    assert "连接已存在" not in capsys.readouterr().out  # 无冲突分支误触发


def test_modify_interactive_rename(monkeypatch, capsys, tmp_path):
    """交互模式首字段为 Name,可修改连接名并删除旧文件。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    responses = iter(
        [
            ("newname", "normal"),
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
                "api get newname",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存" in out
    conn = get_connection("newname")
    assert conn is not None
    assert conn.base_url == "https://new/v1"
    assert conn.model == "gpt-5"
    assert get_connection("d") is None  # 旧名已删除


def test_shell_api_list_marks_default(capsys, monkeypatch, tmp_path):
    """api list 对全局默认连接显示 * 标记,非默认不标记。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api add --name e --url https://y/v2 --key k2 --model m2",
                "api use d",
                "api list",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "d *" in out
    assert "e *" not in out


def test_shell_api_list_no_default_no_star(capsys, monkeypatch, tmp_path):
    """未设置默认连接 → 列表无星号。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api list",
                "exit",
            ]
        )
    )
    assert "*" not in capsys.readouterr().out


def test_shell_api_list_verbose_marks_default(capsys, monkeypatch, tmp_path):
    """verbose 视图同样标记默认连接。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api use d",
                "api list -v",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "d *" in out


def test_shell_api_list_default_deleted_no_warning(
    capsys, monkeypatch, tmp_path, caplog
):
    """默认连接指向已删除连接 → 无星号、无"读取 JSON 失败"告警。"""
    import logging

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    with caplog.at_level(logging.WARNING, logger="rp_agent"):
        run_shell(
            _feed(
                [
                    "api add --name d --url https://x/v1 --key k --model m",
                    "api use d",
                    "api del d -f",
                    "api list",
                    "exit",
                ]
            )
        )
    out = capsys.readouterr().out
    assert "*" not in out
    assert "读取 JSON 失败" not in caplog.text


def test_handle_line_switches_mode_and_quits(capsys):
    import rp_agent.shell as shell_mod

    handle_line("chat")
    # handle_line 写入切换请求并同步 _current_mode,模式由 run_shell/TUI 消费循环应用
    assert shell_mod._mode_switch_request == "chat"
    # 非 home 模式 /exit 回 home
    handle_line("/exit")
    assert shell_mod._mode_switch_request == "home"
    # home 模式 exit 置退出信号
    shell_mod._mode_switch_request = None
    handle_line("exit")
    assert shell_mod._quit_request is True


def test_handle_line_unknown_command_emits(capsys):
    handle_line("foobar")
    assert "未知命令" in capsys.readouterr().out


def test_reload_ui_switch_and_idempotent(capsys):
    import rp_agent.shell as shell_mod

    # 默认 TUI;reload --tui 幂等
    shell_mod._ui_mode = "tui"
    shell_mod._ui_switch_request = None
    handle_line("reload --tui")
    assert shell_mod._ui_switch_request is None
    assert "已是 tui 界面" in capsys.readouterr().out

    # reload --cli 请求切换
    handle_line("reload --cli")
    assert shell_mod._ui_switch_request == "cli"

    # 已在 cli 时 reload --cli 幂等
    shell_mod._ui_mode = "cli"
    shell_mod._ui_switch_request = None
    handle_line("reload --cli")
    assert shell_mod._ui_switch_request is None
    assert "已是 cli 界面" in capsys.readouterr().out

    # reload 无参数仍是热重载配置
    handle_line("reload")
    assert "配置已重载" in capsys.readouterr().out


def test_dispatch_loop_switches_ui(monkeypatch, capsys):
    import rp_agent.shell as shell_mod

    calls: list[str] = []
    real_tui_run = None
    monkeypatch.setattr(shell_mod, "_ui_mode", "cli")
    # 模拟:第一次跑 REPL 时注入 reload --tui + exit,应切到 tui 后真正退出
    monkeypatch.setattr(
        "rp_agent.tui.run",
        lambda initial_mode: calls.append(f"tui:{initial_mode}"),
    )
    # 用注入输入:cli 模式跑 REPL,输入 reload --tui 后退出
    shell_mod.run_shell(_feed(["reload --tui", "exit"]))
    assert calls == ["tui:home"]  # 分发循环:cli → 切 tui → 跑 tui.run → tui 内 exit → break


# --- TUI 下交互输入降级(Important 1) ---

def test_confirm_degrades_in_tui(monkeypatch):
    """TUI 下 _confirm 不弹 input,直接返回 False 拒绝并给提示。"""
    import rp_agent.shell as shell_mod
    from rp_agent import output

    def _boom(*_a, **_k):
        raise AssertionError("TUI 下不应调用 input")

    # raising=False:模块 dict 无 input 键(内置名),patch 后屏蔽 builtins 即可
    monkeypatch.setattr("rp_agent.shell.input", _boom, raising=False)
    collected: list[str] = []
    output.set_emit_target(collected.append)
    try:
        ans = shell_mod._confirm("确认删除连接 d? [y/N]: ")
    finally:
        output.reset_emit_target()
    assert ans is False
    assert collected == ["TUI 下不可交互确认,请加 -f 参数"]


def test_chat_rename_single_arg_degrades_in_tui(monkeypatch):
    """TUI 下 chat rename 单参数不交互,提示用完整形式。"""
    import rp_agent.shell as shell_mod
    from rp_agent import output

    def _boom(*_a, **_k):
        raise AssertionError("TUI 下不应调用 _read_line")

    monkeypatch.setattr("rp_agent.shell._read_line", _boom)
    collected: list[str] = []
    output.set_emit_target(collected.append)
    try:
        shell_mod._chat_rename(["旧会话"])
    finally:
        output.reset_emit_target()
    assert collected == ["TUI 下请使用完整形式:chat rename <会话> <新名称>"]


def test_api_modify_interactive_degrades_in_tui(monkeypatch, tmp_path):
    """TUI 下 api modify(无 --set)不进入交互编辑,提示用非交互形式。"""
    import rp_agent.shell as shell_mod
    from rp_agent import output
    from rp_agent.api.models import ApiConnection
    from rp_agent.api.store import save_connection

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    save_connection(
        ApiConnection(name="d", base_url="https://x/v1", api_key="k", model="m")
    )

    def _boom(*_a, **_k):
        raise AssertionError("TUI 下不应调用 _modify_interactive")

    monkeypatch.setattr("rp_agent.shell._modify_interactive", _boom)
    collected: list[str] = []
    output.set_emit_target(collected.append)
    try:
        shell_mod._cmd_api(["modify", "d"])
    finally:
        output.reset_emit_target()
    assert collected == [
        "TUI 下请使用非交互形式:api modify <name> --set field=value"
    ]


# --- tui._sync_mode_clear 主动清空(Important 2 提取的纯 helper) ---

def test_tui_sync_mode_clear_on_mismatch():
    import rp_agent.tui as tui

    tui._output_lines.clear()
    tui._output_lines.append("遗留行")
    tui._tail_offset = 3
    tui._current_mode_snapshot = "home"
    assert tui._sync_mode_clear("rp") is True
    assert tui._output_lines == []
    assert tui._tail_offset == 0
    assert tui._current_mode_snapshot == "rp"


def test_tui_sync_mode_clear_on_match_is_noop():
    import rp_agent.tui as tui

    tui._output_lines.clear()
    tui._output_lines.append("行")
    tui._tail_offset = 0
    tui._current_mode_snapshot = "rp"
    assert tui._sync_mode_clear("rp") is False
    assert len(tui._output_lines) == 1
    assert tui._current_mode_snapshot == "rp"
