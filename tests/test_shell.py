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
