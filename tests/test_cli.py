from typer.testing import CliRunner

from rp_agent import __version__
from rp_agent.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_hello_command():
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "rp-agent" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    # Typer no_args_is_help 显示帮助,Click 以退出码 2 返回(版本相关)
    assert result.exit_code in (0, 2)
    assert "Usage" in result.stdout


def test_watch_with_subcommand(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "rp_agent.cli._run_watch", lambda args: captured.update(args=args)
    )
    result = runner.invoke(app, ["--watch", "hello"])
    assert result.exit_code == 0
    assert captured.get("args") == ["hello"]


def test_watch_without_subcommand_shows_help(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "rp_agent.cli._run_watch", lambda args: captured.update(args=args)
    )
    result = runner.invoke(app, ["--watch"])
    # no_args_is_help:无子命令时显示帮助并退出(与无参数行为一致),不进入 watch
    assert result.exit_code in (0, 2)
    assert "Usage" in result.stdout + result.stderr
    assert captured == {}


def test_shell_command_registered(monkeypatch):
    called: dict = {}
    monkeypatch.setattr("rp_agent.shell.run_shell", lambda: called.update(ok=True))
    result = runner.invoke(app, ["shell"])
    assert result.exit_code == 0
    assert called.get("ok") is True


def test_chat_command_registered(monkeypatch):
    called: dict = {}
    monkeypatch.setattr("rp_agent.core.chat.run", lambda: called.update(ok=True))
    result = runner.invoke(app, ["chat"])
    assert result.exit_code == 0
    assert called.get("ok") is True


def test_rp_command_registered(monkeypatch):
    called: dict = {}
    monkeypatch.setattr("rp_agent.core.rp.run", lambda: called.update(ok=True))
    result = runner.invoke(app, ["rp"])
    assert result.exit_code == 0
    assert called.get("ok") is True


def test_agent_command_registered(monkeypatch):
    called: dict = {}
    monkeypatch.setattr("rp_agent.core.agent.run", lambda: called.update(ok=True))
    result = runner.invoke(app, ["agent"])
    assert result.exit_code == 0
    assert called.get("ok") is True
