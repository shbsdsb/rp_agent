"""交互式 shell:供测试命令的 REPL 输入口。零依赖。"""
from __future__ import annotations

import logging
from typing import Callable

from rp_agent.config import get_config, reload_config
from rp_agent.storage import DATA_DIR, ensure_dirs

logger = logging.getLogger("rp_agent")

PROMPT = "rp-agent> "
_BANNER = "rp-agent 交互式 shell —— 输入 help 查看可用命令,exit 退出"
_history: list[str] = []


def parse_line(line: str) -> tuple[str, list[str]]:
    """解析输入行 → (命令名, 参数列表);空行 → ("", [])。"""
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _cmd_help(_args: list[str]) -> None:
    print("可用命令:")
    for name, (desc, _handler) in sorted(_COMMANDS.items()):
        print(f"  {name:<10} {desc}")
    print("  exit/quit  退出 shell")


def _cmd_config(_args: list[str]) -> None:
    cfg = get_config()
    print(f"log_level={cfg.log_level}")


def _cmd_reload(_args: list[str]) -> None:
    changed = reload_config()
    cfg = get_config()
    print(f"配置已重载,发生变化: {changed},log_level={cfg.log_level}")


def _cmd_storage(_args: list[str]) -> None:
    ensure_dirs()
    print(f"data 目录: {DATA_DIR}")
    for sub in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        items = sorted(p.name for p in sub.iterdir())
        print(f"  {sub.name}/: {items}")


def _cmd_hello(_args: list[str]) -> None:
    cfg = get_config()
    print(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("shell 中执行 hello")


def _cmd_history(_args: list[str]) -> None:
    for i, h in enumerate(_history, start=1):
        print(f"  {i:>3}  {h}")


_COMMANDS: dict[str, tuple[str, Callable[[list[str]], None]]] = {
    "help": ("显示帮助", _cmd_help),
    "?": ("显示帮助", _cmd_help),
    "config": ("显示当前配置", _cmd_config),
    "reload": ("热重载配置", _cmd_reload),
    "storage": ("列出 data 目录内容", _cmd_storage),
    "hello": ("冒烟命令", _cmd_hello),
    "history": ("显示输入历史", _cmd_history),
}


def run_shell(_input: Callable[[str], str] = input) -> None:
    """交互式主循环。_input 可注入(测试用);Ctrl+C/Ctrl+D 正常退出。"""
    _history.clear()
    print(_BANNER)
    while True:
        try:
            line = _input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print("退出")
            return
        cmd, args = parse_line(line)
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            print("退出")
            return
        if line.strip() not in _history:
            _history.append(line.strip())
        entry = _COMMANDS.get(cmd)
        if entry is None:
            print(f"未知命令: {cmd}(输入 help 查看可用命令)")
            continue
        try:
            entry[1](args)
        except Exception:
            logger.exception("命令执行失败: %s", cmd)
            print(f"命令执行出错: {cmd}(详情见日志)")
