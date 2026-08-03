from rp_agent.api.store import get_connection
from rp_agent.shell import parse_line, run_shell


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
    for name in ("help", "config", "reload", "storage", "hello", "history", "exit"):
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
