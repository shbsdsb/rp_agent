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
                "api add demo http://localhost:8000/v1 gpt-4o",
                "api get demo",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "base_url=http://localhost:8000/v1" in out
    assert "api_key=(空)" in out


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
