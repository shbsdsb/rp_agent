"""Typer CLI 入口:唯一命令注册点。未来子命令(chat/character/agent)在此注册。"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import typer

from rp_agent import __version__
from rp_agent.config import DEFAULT_CONFIG_PATH, get_config, reload_config
from rp_agent.logging_setup import setup_logging
from rp_agent.watch import Watcher

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


def _spawn_child(args: list[str]) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "rp_agent", *args]
    logger.info("[watch] 启动子进程: %s", " ".join(cmd))
    return subprocess.Popen(cmd)


def _run_watch(args: list[str]) -> None:
    """--watch 模式:代码变更重启子进程,配置变更热生效。"""
    src_dir = Path(__file__).parent
    child: subprocess.Popen | None = _spawn_child(args)

    def on_restart() -> None:
        nonlocal child
        logger.info("[watch] 检测到代码变更,重启子进程…")
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        child = _spawn_child(args)

    def on_reload() -> None:
        if reload_config():
            cfg = get_config()
            setup_logging(cfg.log_level)
            logger.info("[watch] 配置已热重载: log_level=%s", cfg.log_level)
        else:
            logger.info("[watch] 配置无变化")

    watcher = Watcher(
        py_dirs=[src_dir],
        config_files=[DEFAULT_CONFIG_PATH],
        on_restart=on_restart,
        on_reload=on_reload,
    )
    try:
        watcher.run()
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="显示版本并退出",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="开发热重载:代码变更自动重启,配置变更热生效",
    ),
) -> None:
    """rp-agent 全局入口:初始化配置与日志。"""
    cfg = get_config()
    setup_logging(cfg.log_level)
    if watch:
        args = [ctx.invoked_subcommand or ""] + list(ctx.args)
        args = [a for a in args if a]
        logger.debug("进入 --watch 模式,目标命令: %s", args or ["(无,显示帮助)"])
        _run_watch(args)
        raise typer.Exit()
    logger.debug("配置加载完成: log_level=%s", cfg.log_level)


@app.command()
def hello() -> None:
    """冒烟命令:验证 命令 → 配置 → 日志 全链路。"""
    cfg = get_config()
    typer.echo(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("hello 命令执行完成")


@app.command()
def shell() -> None:
    """进入交互式 shell(测试命令用)。"""
    from rp_agent.shell import run_shell

    run_shell()


@app.command()
def chat() -> None:
    """进入 AI 聊天模式(真实 AI 对话:多轮上下文 + 会话持久化)。"""
    from rp_agent.core.chat import run

    run()


@app.command()
def rp() -> None:
    """进入角色扮演模式(占位)。"""
    from rp_agent.core.rp import run

    run()


@app.command()
def agent() -> None:
    """进入 agent 模式(占位)。"""
    from rp_agent.core.agent import run

    run()
