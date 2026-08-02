"""Typer CLI 入口:唯一命令注册点。未来子命令(chat/character/agent)在此注册。"""
from __future__ import annotations

import logging

import typer

from rp_agent import __version__
from rp_agent.config import get_config
from rp_agent.logging_setup import setup_logging

logger = logging.getLogger("rp_agent")

app = typer.Typer(
    name="rp-agent",
    help="AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern)",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rp-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="显示版本并退出",
    ),
) -> None:
    """rp-agent 全局入口:初始化配置与日志。"""
    cfg = get_config()
    setup_logging(cfg.log_level)
    logger.debug("配置加载完成: log_level=%s", cfg.log_level)


@app.command()
def hello() -> None:
    """冒烟命令:验证 命令 → 配置 → 日志 全链路。"""
    cfg = get_config()
    typer.echo(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("hello 命令执行完成")
