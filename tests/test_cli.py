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
